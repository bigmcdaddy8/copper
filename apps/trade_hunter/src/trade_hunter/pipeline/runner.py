"""Full pipeline orchestration for trade_hunter."""

from datetime import date, datetime
from pathlib import Path

from trade_hunter.config import RunConfig
from trade_hunter.loaders.journal import load_journal
from trade_hunter.loaders.sector_cache import SectorCache
from trade_hunter.loaders.seekingalpha import load_seekingalpha
from trade_hunter.loaders.tastytrade import load_tastytrade
from trade_hunter.output.run_log import RunLog
from trade_hunter.output.workbook import write_workbook
from trade_hunter.pipeline.candidates import check_active_symbols_in_universe, filter_and_join
from trade_hunter.pipeline.filters import apply_hard_filters
from trade_hunter.pipeline.normalize import BUCKET_MAP
from trade_hunter.pipeline.scoring import build_active_diversity_lists, calculate_scores
from trade_hunter.tradier.client import TradierClient
from trade_hunter.tradier.enrichment import enrich_candidates


def run_pipeline(
    config: RunConfig,
    client: TradierClient,
    run_date: date | None = None,
) -> tuple[Path, Path]:
    """Orchestrate the full trade_hunter pipeline.

    Args:
        config:    RunConfig populated from CLI arguments.
        client:    TradierClient to use for all API calls.
        run_date:  Date of the run (defaults to date.today()).

    Returns:
        (workbook_path, log_path) — paths of the written output files.

    Raises:
        FileNotFoundError: if any required input file cannot be found.
        ValueError: if any required input file fails schema validation.
    """
    if run_date is None:
        run_date = date.today()

    log = RunLog(run_start=datetime.now(), verbose=config.verbose)

    # 1. Load Universal Data Set
    universal, warnings = load_tastytrade(config.downloads_dir, config.tastytrade_file)
    log.add_warnings(warnings)

    # 2. Load active trades
    active_symbols, warnings = load_journal(config.worksheets_dir, config.journal_file)
    log.add_warnings(warnings)

    # 3. Warn about active symbols absent from the Universal Data Set
    log.add_warnings(check_active_symbols_in_universe(active_symbols, universal))

    # 4. Instantiate sector cache once — shared across active-trade and candidate resolution.
    sector_cache = SectorCache(config.cache_dir)

    # 5. Resolve sectors for active trade symbols via yfinance, updating the universal dataset
    #    in-place so that diversity calculations use yfinance sectors rather than TastyTrade
    #    sectors. Also pre-warms the cache for any candidates that overlap with active trades.
    #    Misses are silent — the existing TastyTrade sector remains as-is.
    for sym in sorted(active_symbols):
        resolved = sector_cache.get(sym)
        if resolved:
            mask = universal["Symbol"] == sym
            if mask.any():
                universal.loc[mask, "Sector"] = resolved
                universal.loc[mask, "Sector Bucket"] = BUCKET_MAP.get(
                    resolved, universal.loc[mask, "Sector Bucket"].values[0]
                )

    # 6. Build diversity inputs (uses yfinance-resolved sectors for active trades)
    active_buckets, active_sectors = build_active_diversity_lists(active_symbols, universal)

    # 7. Load SeekingAlpha candidates
    bull_sa, warnings = load_seekingalpha(config.downloads_dir, config.bull_file, side="BULL")
    log.add_warnings(warnings)
    bear_sa, warnings = load_seekingalpha(config.downloads_dir, config.bear_file, side="BEAR")
    log.add_warnings(warnings)

    # 8. Filter candidates (open-trade exclusion + universe join)
    bull_joined, warnings = filter_and_join(bull_sa, universal, active_symbols, "BULL")
    log.add_warnings(warnings)
    bear_joined, warnings = filter_and_join(bear_sa, universal, active_symbols, "BEAR")
    log.add_warnings(warnings)

    # 9. Resolve sectors for candidates via yfinance (cache already warm from step 5)
    for side_label, df in (("BULL", bull_joined), ("BEAR", bear_joined)):
        for idx, row in df.iterrows():
            resolved = sector_cache.get(str(row["Symbol"]))
            if resolved:
                df.at[idx, "Sector"] = resolved
                df.at[idx, "Sector Bucket"] = BUCKET_MAP.get(resolved, row["Sector Bucket"])
            else:
                log.warn(
                    f"[{side_label}] '{row['Symbol']}' — yfinance sector miss, using TastyTrade fallback"
                )

    # 11. Tradier enrichment
    bull_enriched, warnings = enrich_candidates(
        bull_joined, "BULL", client, run_date, config.min_dte, config.max_dte,
        verbose=config.verbose,
    )
    log.add_warnings(warnings)
    bear_enriched, warnings = enrich_candidates(
        bear_joined, "BEAR", client, run_date, config.min_dte, config.max_dte,
        verbose=config.verbose,
    )
    log.add_warnings(warnings)

    # 12. Hard filters
    bull_filtered, warnings = apply_hard_filters(
        bull_enriched, "BULL", config.min_open_interest, config.min_bid, config.max_spread_pct
    )
    log.add_warnings(warnings)
    bear_filtered, warnings = apply_hard_filters(
        bear_enriched, "BEAR", config.min_open_interest, config.min_bid, config.max_spread_pct
    )
    log.add_warnings(warnings)

    # 13. Score
    bull_scored = calculate_scores(bull_filtered, "BULL", run_date, active_buckets, active_sectors)
    bear_scored = calculate_scores(bear_filtered, "BEAR", run_date, active_buckets, active_sectors)

    # 14. Write workbook
    workbook_path = write_workbook(bull_scored, bear_scored, config.output_dir)

    # 15. Write run log with summary counts
    summary: dict[str, int] = {
        "Loaded (BULL)": len(bull_sa),
        "Loaded (BEAR)": len(bear_sa),
        "Active trades": len(active_symbols),
        "Enriched (BULL)": len(bull_enriched),
        "Enriched (BEAR)": len(bear_enriched),
        "Filtered out (BULL)": len(bull_enriched) - len(bull_filtered),
        "Filtered out (BEAR)": len(bear_enriched) - len(bear_filtered),
        "Scored (BULL)": len(bull_scored),
        "Scored (BEAR)": len(bear_scored),
    }
    log_path = log.write(config.output_dir, summary=summary)

    return workbook_path, log_path
