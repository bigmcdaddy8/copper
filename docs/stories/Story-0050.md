# Story-0050 — Candidate Filtering & Universe Join

**Status**: Completed  
**Phase**: 2 — Data Ingestion Layer

---

## Goal

Apply the two exclusion rules from the processing pipeline and join the surviving candidates to
the Universal Data Set, producing enriched BULL-ish and BEAR-ish DataFrames ready for Tradier
enrichment in Phase 3.

---

## Background

From `docs/PROJECT_INTENT.md` processing pipeline, steps 8–10:

> 8. Remove any candidate already present in the open-trade symbol set.
> 9. Remove any candidate not present in the Universal Data Set.
> 10. Join remaining candidates to the Universal Data Set.

And from the data normalization rules:

> Any SeekingAlpha candidate not present in the Universal Data Set is out of scope for this run,
> should be logged as a warning, and should be skipped.
>
> Any open-trade ticker not present in the Universal Data Set should also be logged as a warning
> but should not stop processing.

This story also handles the second warning above — active-trade symbols that don't appear in the
Universal Data Set — which was deliberately deferred from Story-0040.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/candidates.py` | Filtering and join logic |
| `apps/trade_hunter/tests/test_candidates.py` | Unit tests |

No CLI, config, or dependency changes required.

---

## Module Design

### `pipeline/candidates.py`

Two focused functions.

```python
def check_active_symbols_in_universe(
    active_symbols: frozenset[str],
    universal_dataset: pd.DataFrame,
) -> list[str]:
    """
    Return a warning string for each active symbol absent from the Universal Data Set.
    Does not raise — missing active symbols are informational, not a blocking error.
    """

def filter_and_join(
    candidates: pd.DataFrame,
    universal_dataset: pd.DataFrame,
    active_symbols: frozenset[str],
    side: str,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Apply open-trade exclusion and universe membership filter, then join to Universal Data Set.

    Steps:
      1. Remove rows whose Symbol is in active_symbols (open-trade exclusion).
      2. Remove rows whose Symbol is not in universal_dataset (log warning per ticker).
      3. Merge remaining rows with universal_dataset on Symbol (inner join).

    Args:
        candidates:       SeekingAlpha DataFrame (Symbol, Quant Rating, Growth, Momentum, …).
        universal_dataset: TastyTrade DataFrame (Symbol, IV Rank, IV %tile, Sector, …).
        active_symbols:   Deduplicated set of open-trade tickers.
        side:             "BULL" or "BEAR" — used only for warning message labels.

    Returns:
        (joined_df, warnings)
    """
```

### Join output columns

After the inner merge on `Symbol`, the resulting DataFrame contains all columns from both
sources (no column name collisions exist between the two loaders):

| Source | Columns |
|---|---|
| SeekingAlpha | `Symbol`, `Quant Rating`, `Growth`, `Momentum`, `Upcoming Announce Date`\*, `Company Name`\* |
| Universal Data Set | `Name`\*, `Liquidity`\*, `IV Idx`, `IV Rank`, `IV %tile`, `Earnings At`\*, `Sector`, `Sector Bucket` |

\* Optional — present only if the source file contained the column.

---

## Warning Messages

| Condition | Warning format |
|---|---|
| Active symbol not in Universal Data Set | `"[Journal] Active symbol 'XYZ' not found in Universal Data Set"` |
| Candidate excluded (open-trade) | `"[BULL] 'XYZ' excluded — active open trade"` |
| Candidate missing from Universal Data Set | `"[BULL] 'XYZ' not in Universal Data Set — skipped"` |

The `side` label (`"BULL"` or `"BEAR"`) appears in warnings from `filter_and_join`.
Warnings from `check_active_symbols_in_universe` always use the `[Journal]` prefix.

---

## Acceptance Criteria

1. `check_active_symbols_in_universe` returns one warning per active symbol absent from the
   Universal Data Set and returns an empty list when all symbols are present.
2. `filter_and_join` removes candidates whose Symbol is in `active_symbols`.
3. A warning is appended for each candidate removed by the open-trade exclusion.
4. `filter_and_join` removes candidates whose Symbol is not in the Universal Data Set.
5. A warning is appended for each candidate removed because it is missing from the universe.
6. Surviving candidates are merged with the Universal Data Set; the output contains columns
   from both sources.
7. A candidate present in both the open-trade set and absent from the universe triggers the
   open-trade exclusion warning only (open-trade check runs first).
8. An empty candidate DataFrame returns an empty joined DataFrame with no errors.
9. `uv run pytest` passes (all existing + new tests).
10. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests

### `tests/test_candidates.py`

**`check_active_symbols_in_universe`:**
- `test_active_all_in_universe`: no warnings when all active symbols are present.
- `test_active_missing_from_universe`: warning returned for each symbol absent from universe.
- `test_active_empty_set`: empty `frozenset` produces no warnings.

**`filter_and_join` — exclusion:**
- `test_open_trade_excluded`: candidate in `active_symbols` is removed; warning present.
- `test_not_in_universe_excluded`: candidate absent from `universal_dataset` is removed; warning present.
- `test_open_trade_check_runs_first`: symbol that is both an open trade and absent from the
  universe triggers only the open-trade warning, not the missing-universe warning.

**`filter_and_join` — join:**
- `test_join_columns_combined`: output DataFrame contains columns from both SeekingAlpha and
  Universal Data Set sources.
- `test_join_row_count`: only symbols surviving both filters appear in the output.
- `test_empty_candidates`: empty input DataFrame returns empty output without error.
- `test_no_exclusions`: all candidates pass both filters; joined row count equals input count.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
