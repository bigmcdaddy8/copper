"""Full pipeline orchestration for trade_hunter."""

from datetime import date, datetime
from pathlib import Path

from trade_hunter.config import RunConfig
from trade_hunter.loaders.journal import load_journal
from trade_hunter.loaders.seekingalpha import load_seekingalpha
from trade_hunter.loaders.tastytrade import load_tastytrade
from trade_hunter.output.run_log import RunLog
from trade_hunter.output.workbook import write_workbook
from trade_hunter.pipeline.candidates import check_active_symbols_in_universe, filter_and_join
from trade_hunter.pipeline.filters import apply_hard_filters
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

    log = RunLog(run_start=datetime.now())

    # 1. Load Universal Data Set
    universal, warnings = load_tastytrade(config.downloads_dir, config.tastytrade_file)
    log.add_warnings(warnings)

    # 2. Load active trades
    active_symbols, warnings = load_journal(config.worksheets_dir, config.journal_file)
    log.add_warnings(warnings)

    # 3. Warn about active symbols absent from the Universal Data Set
    log.add_warnings(check_active_symbols_in_universe(active_symbols, universal))

    # 4. Build diversity inputs (computed once; reused for both sides)
    active_buckets, active_sectors = build_active_diversity_lists(active_symbols, universal)

    # 5. Load SeekingAlpha candidates
    bull_sa, warnings = load_seekingalpha(config.downloads_dir, config.bull_file, side="BULL")
    log.add_warnings(warnings)
    bear_sa, warnings = load_seekingalpha(config.downloads_dir, config.bear_file, side="BEAR")
    log.add_warnings(warnings)

    # 6. Filter candidates (open-trade exclusion + universe join)
    bull_joined, warnings = filter_and_join(bull_sa, universal, active_symbols, "BULL")
    log.add_warnings(warnings)
    bear_joined, warnings = filter_and_join(bear_sa, universal, active_symbols, "BEAR")
    log.add_warnings(warnings)

    # 7. Tradier enrichment
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

    # 8. Hard filters
    bull_filtered, warnings = apply_hard_filters(
        bull_enriched, "BULL", config.min_open_interest, config.min_bid, config.max_spread_pct
    )
    log.add_warnings(warnings)
    bear_filtered, warnings = apply_hard_filters(
        bear_enriched, "BEAR", config.min_open_interest, config.min_bid, config.max_spread_pct
    )
    log.add_warnings(warnings)

    # 9. Score
    bull_scored = calculate_scores(bull_filtered, "BULL", run_date, active_buckets, active_sectors)
    bear_scored = calculate_scores(bear_filtered, "BEAR", run_date, active_buckets, active_sectors)

    # 10. Write workbook
    workbook_path = write_workbook(bull_scored, bear_scored, config.output_dir)

    # 11. Write run log with summary counts
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
