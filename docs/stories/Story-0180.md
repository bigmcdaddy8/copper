# Story-0180 — Ticker Fixes & Monthly Cycle Holiday Fallback

**Status**: Completed  
**Phase**: 7 — Maintenance & Enhancements  
**Addresses**: Backlog-0030, Backlog-0060

---

## Goal

Two small isolated fixes:

1. **Drop `GOOG`** from BULL/BEAR candidate lists — `GOOG` and `GOOGL` are identical for our purposes; always use `GOOGL`.

2. **Accept 3rd Thursday as a monthly expiration fallback** — the current `_is_monthly_expiration()` only accepts the 3rd Friday. When a market holiday falls on the 3rd Friday (e.g. Good Friday, Juneteenth), the exchange moves the expiry to the 3rd Thursday. Tradier's returned expiration list is the source of truth: if Thursday is listed but Friday is not, Thursday should be accepted.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/candidates.py` | Pre-filter: drop `Symbol == "GOOG"` before any other processing; warn to run_log |
| `apps/trade_hunter/src/trade_hunter/tradier/selector.py` | `_is_monthly_expiration()`: also return `True` when date == 3rd Thursday |

---

## Detailed Design

### 1. GOOG Filter (`pipeline/candidates.py`)

In `filter_and_join()`, add a pre-filter step before the active-trade exclusion:

```python
goog_mask = df["Symbol"] == "GOOG"
if goog_mask.any():
    run_log.warn(f"[{side}] 'GOOG' dropped — use GOOGL")
    df = df[~goog_mask]
```

Applied to both the BULL and BEAR candidate DataFrames independently before any joins.

### 2. 3rd Thursday Fallback (`tradier/selector.py`)

Modify `_is_monthly_expiration()`:

```python
def _is_monthly_expiration(exp_date: date) -> bool:
    """Return True if exp_date is the 3rd Friday or 3rd Thursday (holiday fallback) of its month."""
    first = date(exp_date.year, exp_date.month, 1)
    days_to_friday = (4 - first.weekday()) % 7  # weekday 4 = Friday
    third_friday = date(exp_date.year, exp_date.month, 1 + days_to_friday + 14)
    third_thursday = third_friday - timedelta(days=1)
    return exp_date == third_friday or exp_date == third_thursday
```

No changes needed to `select_expiration()` — it already iterates Tradier's returned list and picks the first qualifying date within the DTE window.

---

## Acceptance Criteria

1. When GOOG appears in a BULL or BEAR input file, it is absent from the output spreadsheet and a warning appears in the run_log.
2. When GOOGL also appears in the same file, GOOGL is unaffected.
3. For a date set where Tradier lists the 3rd Thursday but not 3rd Friday of a month (e.g. Good Friday 2025-04-17/18), the 3rd Thursday is selected as the monthly expiration.
4. Normal 3rd Friday expirations continue to work unchanged.
5. All existing tests pass.

---

## Verification Steps

```bash
# Unit tests
uv run pytest apps/trade_hunter/tests/

# Manual: confirm 3rd Thursday logic
python3 -c "
from datetime import date, timedelta
# Good Friday 2025: April 18 is 3rd Friday; April 17 is 3rd Thursday
from trade_hunter.tradier.selector import _is_monthly_expiration
assert _is_monthly_expiration(date(2025, 4, 18))  # 3rd Friday — should still match
assert _is_monthly_expiration(date(2025, 4, 17))  # 3rd Thursday — now also matches
assert not _is_monthly_expiration(date(2025, 4, 16))  # Wednesday — should not match
print('OK')
"
```
