# Story-0090 — Hard Filters

**Status**: Completed  
**Phase**: 4 — Hard Filters & Scoring Engine

---

## Goal

Apply the four hard filters from `docs/PROJECT_INTENT.md` to the enriched BULL-ish and
BEAR-ish DataFrames produced by Story-0080. Rows that fail any filter are removed and logged
with a reason. Survivors are passed to the scoring engine (Stories 0100–0120).

---

## Background

From `docs/PROJECT_INTENT.md`:

> Apply these filters to both BULL-ish and BEAR-ish candidates after Tradier enrichment.
> For BULL-ish candidates, use the selected put fields.
> For BEAR-ish candidates, use the selected call fields.

| Filter | Rule |
|---|---|
| Monthly Cycle | A valid monthly cycle expiration was found |
| Open Interest | `>= 8` |
| Bid | `>= 0.55` |
| Spread% | `(ask - bid) / ((ask + bid) / 2) <= 13%` |

> These thresholds must be configurable through CLI options, config file support, or another
> convenient configuration mechanism.
> Be sure to log the criteria failure as they occur.

### Spread% formula

`Spread% = (option ask - option bid) / ((option ask + option bid) / 2)`

This measures the spread relative to the option's mid price — scale-invariant across strikes
and expirations and a direct proxy for execution friction. The hard filter threshold is **13%**.
Bid and Ask are already present in the enriched DataFrame from Story-0080; no additional column
is required.

---

## Monthly Cycle Filter Note

The Monthly Cycle filter ("a valid monthly cycle expiration was found") is already guaranteed
by `select_expiration` in Story-0070, which only returns third-Friday monthly expirations. Any
ticker that survived the enrichment pass already has a monthly expiration. This filter is
therefore a no-op in the current pipeline and does not need a separate code check — it is
satisfied by construction.

It is listed here for completeness and traceability against PROJECT_INTENT.md, but no row will
ever be dropped by it.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/filters.py` | `apply_hard_filters()` function |
| `apps/trade_hunter/tests/test_filters.py` | Unit tests |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/config.py` | Change `max_spread_pct` default from `0.08` to `0.13` |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Update `--max-spread-pct` help text to reflect new default |

---

## Module Design

### `pipeline/filters.py`

```python
import pandas as pd


def apply_hard_filters(
    enriched: pd.DataFrame,
    side: str,
    min_open_interest: int = 8,
    min_bid: float = 0.55,
    max_spread_pct: float = 0.13,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply hard filters to the enriched candidate DataFrame.

    Filters applied in order:
      1. Open Interest >= min_open_interest
      2. Bid >= min_bid
      3. Spread% = (Ask - Bid) / ((Ask + Bid) / 2) <= max_spread_pct

    The Monthly Cycle filter is satisfied by construction (select_expiration
    guarantees a monthly expiration) and is not checked here.

    Args:
        enriched:           Enriched DataFrame from enrich_candidates().
        side:               "BULL" or "BEAR" — used in warning messages only.
        min_open_interest:  Minimum open interest (default 8).
        min_bid:            Minimum bid (default 0.55).
        max_spread_pct:     Maximum spread fraction (default 0.13 = 13%).

    Returns:
        (surviving_df, warnings)
        One warning per filtered-out row, stating the symbol and reason.
    """
```

### Filter logic

Each filter is applied as a mask. Rows that fail are collected into warnings before being
dropped. Filters run in order; a row that fails the first filter is not re-checked against
later filters (it is already gone).

### Warning messages

| Condition | Warning format |
|---|---|
| Open interest too low | `"[BULL] 'XYZ' filtered — open interest 5 < 8"` |
| Bid too low | `"[BULL] 'XYZ' filtered — bid 0.42 < 0.55"` |
| Spread too wide | `"[BULL] 'XYZ' filtered — spread 14.2% > 13.0%"` |

Spread% in the warning is displayed as a percentage rounded to one decimal place.

---

## Acceptance Criteria

1. A row with `Open Interest < min_open_interest` is removed; warning contains `"open interest"`.
2. A row with `Bid < min_bid` is removed; warning contains `"bid"`.
3. A row with `(Ask - Bid) / ((Ask + Bid) / 2) > max_spread_pct` is removed; warning contains
   `"spread"`.
4. A row passing all three filters survives unchanged.
5. Filters are applied in order — a row that fails open interest does not also generate a bid
   warning.
6. An empty input DataFrame returns an empty DataFrame with no warnings.
7. All three thresholds are respected from the function arguments (not hard-coded).
8. `config.py` default `max_spread_pct` is updated to `0.13`.
9. `uv run pytest` passes (all existing + new tests).
10. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_filters.py`)

All tests use inline synthetic DataFrames.

- `test_passes_all_filters`: OI=500, bid=1.10, ask=1.20 → spread≈8.7% → survives, no warnings.
- `test_fails_open_interest`: OI=5 → filtered, warning mentions `"open interest"`.
- `test_fails_bid`: bid=0.40 → filtered, warning mentions `"bid"`.
- `test_fails_spread`: bid=1.00, ask=1.25 → spread≈22.2% → filtered, warning mentions `"spread"`.
- `test_open_interest_boundary`: OI exactly equal to `min_open_interest` → passes.
- `test_bid_boundary`: bid exactly equal to `min_bid` → passes.
- `test_spread_boundary`: spread exactly equal to `max_spread_pct` → passes.
- `test_open_interest_checked_first`: row fails both OI and bid → only OI warning generated.
- `test_multiple_candidates_partial_failure`: three rows; one fails bid, two pass → two rows
  in output, one warning.
- `test_empty_input`: empty DataFrame → empty output, no warnings.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
