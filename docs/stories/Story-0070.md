# Story-0070 — Expiration & Option Selection

**Status**: Completed  
**Phase**: 3 — Tradier API Integration

---

## Goal

Build the pure-logic selection layer that sits between `TradierClient` (Story-0060) and the
enrichment pass (Story-0080). Given a list of expiration date strings from Tradier and an option
chain, this module applies the business rules from `docs/PROJECT_INTENT.md` to return the
selected expiration and the correct contract. No API calls are made here — all inputs are plain
Python data structures.

---

## Background

From `docs/PROJECT_INTENT.md`:

### Expiration Selection Rule

> When multiple monthly expirations qualify, select the nearest monthly expiration whose DTE is
> between 30 and 60 calendar days inclusive.

### Monthly Cycle Rule

> The program should use the standard monthly expiration cycle. If Tradier exposes sufficient
> metadata to identify monthly contracts directly, use that metadata. Otherwise, infer the monthly
> cycle using the standard monthly expiration convention.

**Decision:** Tradier's expirations endpoint (with `includeAllRoots=false`) still returns weekly
expirations. The selector will infer monthly contracts by checking whether each expiration date
falls on the **third Friday of its month** — the standard CBOE monthly option expiration day.

### Option Selection Rule

> - BULL-ish candidate: use the put whose delta is less than or equal to `-0.21` and is closest
>   to `-0.21`.
> - BEAR-ish candidate: use the call whose delta is greater than or equal to `0.21` and is
>   closest to `0.21`.
> - If no qualifying option exists for the required side, log a warning and skip the ticker.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/tradier/selector.py` | Pure selection logic |
| `apps/trade_hunter/tests/test_tradier_selector.py` | Unit tests |

## Modified Files

None — this story adds a standalone module only.

---

## Module Design

### `tradier/selector.py`

Three focused functions plus one private helper.

```python
from datetime import date

def select_expiration(
    expirations: list[str],
    run_date: date,
    min_dte: int = 30,
    max_dte: int = 60,
) -> str | None:
    """Return the nearest qualifying monthly expiration string, or None.

    A qualifying expiration:
      - Falls on the third Friday of its month (standard monthly cycle).
      - Has DTE in [min_dte, max_dte] inclusive (calendar days from run_date).

    When multiple dates qualify, the one with the lowest DTE is returned.
    Returns None if no expiration qualifies.
    """

def select_put(chain: list[dict]) -> dict | None:
    """Return the put contract with delta <= -0.21 closest to -0.21 (highest/least-negative).

    Returns None if no qualifying put exists in the chain.
    Delta is read from the top-level "delta" key of each contract dict (Tradier greeks
    are inlined at the top level when greeks=true is requested).
    """

def select_call(chain: list[dict]) -> dict | None:
    """Return the call contract with delta >= 0.21 closest to 0.21 (lowest positive).

    Returns None if no qualifying call exists in the chain.
    """
```

### Monthly expiration helper (private)

```python
def _is_monthly_expiration(exp_date: date) -> bool:
    """Return True if exp_date is the third Friday of its month."""
    first_of_month = date(exp_date.year, exp_date.month, 1)
    days_to_first_friday = (4 - first_of_month.weekday()) % 7  # weekday 4 = Friday
    third_friday = date(exp_date.year, exp_date.month, 1 + days_to_first_friday + 14)
    return exp_date == third_friday
```

### Delta field note

When `TradierClient.get_option_chain` is called with `greeks=true`, Tradier inlines the greek
values at the top level of each contract dict. The `delta` key is read directly from the
contract — no nested `greeks` dict access is required.

---

## Selection Logic Details

### `select_expiration`

1. Parse each string to `date`.
2. Discard dates that are not third-Friday monthly expirations.
3. Compute DTE = `(expiration_date - run_date).days`.
4. Discard dates where `DTE < min_dte` or `DTE > max_dte`.
5. Return the string corresponding to the lowest DTE among survivors.
6. Return `None` if the survivor list is empty.

### `select_put` (BULL-ish)

1. Filter to contracts where `option_type == "put"`.
2. Filter to contracts where `delta` is not `None` and `delta <= -0.21`.
3. Return the contract with the **maximum** delta (least negative, closest to −0.21).
4. Return `None` if no contract survives.

### `select_call` (BEAR-ish)

1. Filter to contracts where `option_type == "call"`.
2. Filter to contracts where `delta` is not `None` and `delta >= 0.21`.
3. Return the contract with the **minimum** delta (smallest positive, closest to 0.21).
4. Return `None` if no contract survives.

---

## Acceptance Criteria

1. `select_expiration` returns `None` for an empty expiration list.
2. `select_expiration` returns `None` when no expiration falls within the DTE window.
3. `select_expiration` skips non-third-Friday dates (weekly expirations).
4. `select_expiration` returns the nearest qualifying expiration (lowest DTE) when multiple qualify.
5. DTE boundaries are inclusive: an expiration at exactly `min_dte` or `max_dte` qualifies.
6. `select_put` returns `None` for an empty chain.
7. `select_put` returns `None` when all puts have delta > −0.21.
8. `select_put` returns the put with delta closest to −0.21 (maximum qualifying delta).
9. `select_call` returns `None` when all calls have delta < 0.21.
10. `select_call` returns the call with delta closest to 0.21 (minimum qualifying delta).
11. `select_put` and `select_call` skip contracts where `delta` is `None`.
12. `uv run pytest` passes (all existing + new tests).
13. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_tradier_selector.py`)

All tests use inline synthetic data — no mocking required.

**`select_expiration`:**
- `test_select_expiration_nearest_monthly`: three qualifying monthlies; returns the one with lowest DTE.
- `test_select_expiration_skips_weekly`: mix of weekly and monthly dates within DTE window; only monthlies returned.
- `test_select_expiration_no_qualifying_dte`: all monthlies outside DTE window → `None`.
- `test_select_expiration_empty_list`: empty input → `None`.
- `test_select_expiration_boundary_dte_min`: expiration at exactly `min_dte` → qualifies.
- `test_select_expiration_boundary_dte_max`: expiration at exactly `max_dte` → qualifies.
- `test_select_expiration_dte_just_outside`: DTE of 29 and 61 → `None`.

**`select_put`:**
- `test_select_put_picks_closest_to_threshold`: puts at −0.19, −0.21, −0.25, −0.35; returns −0.21 contract.
- `test_select_put_no_qualifying_delta`: all puts have delta −0.15 → `None`.
- `test_select_put_empty_chain`: empty list → `None`.
- `test_select_put_skips_none_delta`: contract with `delta=None` is ignored; valid contract returned.

**`select_call`:**
- `test_select_call_picks_closest_to_threshold`: calls at 0.15, 0.21, 0.25, 0.35; returns 0.21 contract.
- `test_select_call_no_qualifying_delta`: all calls have delta 0.15 → `None`.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
