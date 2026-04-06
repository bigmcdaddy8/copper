# Story-0150 — End-to-End Integration

**Status**: Completed  
**Phase**: 6 — Integration & Polish

---

## Goal

Wire the full pipeline into a `run_pipeline()` function, update `cli.py` to call it, and write
an end-to-end integration test that exercises every stage with synthetic input files and a
mocked Tradier client. This story is the primary regression guard for the full pipeline.

---

## Background

`cli.py` currently builds a `RunConfig` and prints a summary, ending with:

```python
console.print("[yellow]Configuration loaded. Pipeline not yet implemented.[/yellow]")
```

This story replaces that stub with a real pipeline call. All pipeline stages exist and are
independently tested; this story orchestrates them in order and verifies the seam.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/runner.py` | New — `run_pipeline()` orchestration function |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Replace stub with `TradierClient` creation + `run_pipeline()` call |
| `apps/trade_hunter/tests/test_integration.py` | New — end-to-end test with synthetic files + mock client |

---

## `run_pipeline()` design

### Location and signature

```python
# pipeline/runner.py

from datetime import date, datetime
from pathlib import Path

from trade_hunter.config import RunConfig
from trade_hunter.tradier.client import TradierClient


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
```

### Pipeline call sequence

```python
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
    bull_joined, "BULL", client, run_date, config.min_dte, config.max_dte
)
log.add_warnings(warnings)
bear_enriched, warnings = enrich_candidates(
    bear_joined, "BEAR", client, run_date, config.min_dte, config.max_dte
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
summary = {
    "Loaded (BULL)":        len(bull_sa),
    "Loaded (BEAR)":        len(bear_sa),
    "Active trades":        len(active_symbols),
    "Enriched (BULL)":      len(bull_enriched),
    "Enriched (BEAR)":      len(bear_enriched),
    "Filtered out (BULL)":  len(bull_enriched) - len(bull_filtered),
    "Filtered out (BEAR)":  len(bear_enriched) - len(bear_filtered),
    "Scored (BULL)":        len(bull_scored),
    "Scored (BEAR)":        len(bear_scored),
}
log_path = log.write(config.output_dir, summary=summary)

return workbook_path, log_path
```

---

## `cli.py` update

Replace the stub block (everything after `_print_summary(config)`) with:

```python
from datetime import date

from trade_hunter.pipeline.runner import run_pipeline
from trade_hunter.tradier.client import TradierClient

# (inside the run() command, after _print_summary)
try:
    tradier_client = TradierClient(api_key=config.tradier_api_key, sandbox=config.sandbox)
    workbook_path, log_path = run_pipeline(config, tradier_client, run_date=date.today())
    console.print(f"[green]Workbook written:[/green] {workbook_path}")
    console.print(f"[green]Run log written:[/green]  {log_path}")
except (FileNotFoundError, ValueError) as exc:
    console.print(f"[red]Error:[/red] {exc}", err=True)
    raise typer.Exit(code=1)
```

---

## Integration test (`tests/test_integration.py`)

### Fixture setup

The test writes all required input files to `tmp_path` and uses a `MagicMock` TradierClient
to eliminate real HTTP calls. `run_date` is fixed to `date(2025, 3, 19)` for determinism.

**TastyTrade CSV** (written to `tmp_path / "tt.csv"`):

| Symbol | Sector | Liquidity | IV Idx | IV Rank | IV %tile | Earnings At | Last | Name |
|---|---|---|---|---|---|---|---|---|
| AAPL | Technology | ★★★☆ | 22.5 | 45.0 | 55.0 | 2025-05-28 | 100.0 | Apple |

(`"Technology"` normalizes to `"Information Technology"` → bucket `"Growth"`)

**SeekingAlpha BULL and BEAR Excel** (identical, each to `tmp_path / "bull.xlsx"` / `"bear.xlsx"`):

| Symbol | Quant Rating | Growth | Momentum |
|---|---|---|---|
| AAPL | 4.0 | B | A- |

**Journal (`tmp_path / "journal.xlsx"`, worksheet `daJournal`)**:

| Symbol |
|---|
| MSFT |

(MSFT is the active trade — AAPL is not excluded)

**Mock TradierClient**:

```python
mock_client.get_option_expirations.return_value = ["2025-04-18"]
mock_client.get_last_price.return_value = 100.0
mock_client.get_option_chain.return_value = [
    {"option_type": "put",  "strike": 95.0,  "delta": -0.21,
     "open_interest": 500, "bid": 1.10, "ask": 1.20},
    {"option_type": "call", "strike": 105.0, "delta":  0.21,
     "open_interest": 300, "bid": 0.90, "ask": 1.00},
]
```

`"2025-04-18"` is the third Friday of April 2025 (DTE = 30 from run_date). Both options pass
all hard filters (OI ≥ 8, bid ≥ 0.55, spread ≤ 13%).

### Test assertions

- `test_integration_workbook_exists`: assert `workbook_path.exists()`.
- `test_integration_log_exists`: assert `log_path.exists()`.
- `test_integration_bull_sheet_has_data`: BULL-ish sheet has at least 1 data row.
- `test_integration_bear_sheet_has_data`: BEAR-ish sheet has at least 1 data row.
- `test_integration_bull_ticker_is_aapl`: first row Ticker column == `"AAPL"`.
- `test_integration_column_count`: each sheet has exactly 23 columns.

All six assertions may be expressed as a single parameterless test function
`test_full_pipeline_run` or as individual test functions — implementer's choice, but they must
be individually readable.

---

## Acceptance Criteria

1. `run_pipeline(config, client)` returns `(workbook_path, log_path)` with both files written.
2. All pipeline warnings are captured in the log file.
3. `cli.py` `run` command calls `run_pipeline` and prints the output paths on success.
4. `cli.py` `run` command exits with code 1 and an error message on `FileNotFoundError` /
   `ValueError`.
5. Integration test passes with synthetic files and no real API calls.
6. `uv run pytest` passes (all existing + new tests).
7. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
