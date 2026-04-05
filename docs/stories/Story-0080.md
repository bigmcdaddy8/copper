# Story-0080 — Tradier Enrichment Pass

**Status**: Completed  
**Phase**: 3 — Tradier API Integration

---

## Goal

Wire `TradierClient` (Story-0060) and the selector functions (Story-0070) into a single
enrichment function that iterates over the joined candidate DataFrames produced by Story-0050
and appends all Tradier-sourced fields needed for hard filtering and scoring (Stories 0090–0120).
Tickers that fail at any step are skipped with a warning; survivors return as an enriched
DataFrame.

---

## Background

From `docs/PROJECT_INTENT.md`, processing pipeline step 11:

> 11. Retrieve required Tradier data for remaining joined candidates.

Required Tradier fields per ticker:

| Field | Source |
|---|---|
| `Expiration Date` | `select_expiration` applied to `get_option_expirations` result |
| `DTE` | `(expiration_date − run_date).days` |
| `Last Price` | Tradier `/markets/quotes` — current underlying last trade price |
| `Strike` | Selected option contract `strike` |
| `Option Type` | `"put"` (BULL) or `"call"` (BEAR) |
| `Delta` | Selected option contract `delta` |
| `Open Interest` | Selected option contract `open_interest` |
| `Bid` | Selected option contract `bid` |
| `Ask` | Selected option contract `ask` |

`Strike`, `Delta`, `Open Interest`, `Bid`, `Ask`, and `Option Type` use generic names in the
enriched DataFrame since each row is already side-specific. The output workbook (Story-0130)
maps them to `Put Strike` / `Call Strike` etc. at write time.

`Last Price` requires a dedicated `/markets/quotes` call per ticker (current price, not the
stale TastyTrade `Last` column). This means **three API calls per ticker** — expirations,
quote, chain — at 0.5 s inter-request delay ≈ 1.5 s/ticker. For a typical run of ~20
candidates per side, expect ~60 s total. No optimisation is needed for v1.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/tradier/enrichment.py` | `enrich_candidates()` function |
| `apps/trade_hunter/tests/test_tradier_enrichment.py` | Mock-based unit tests |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/tradier/client.py` | Add `get_last_price(symbol) -> float` |
| `apps/trade_hunter/tests/test_tradier_client.py` | Add `test_get_last_price_parses_response` |

---

## New Client Method

```python
# tradier/client.py

def get_last_price(self, symbol: str) -> float:
    """Return the current last trade price for the underlying symbol.

    Calls GET /markets/quotes?symbols=<symbol>.
    Raises TradierAPIError on non-2xx responses or if the symbol is not found.
    """
```

Tradier quotes response shape:
```json
{
  "quotes": {
    "quote": { "symbol": "SPY", "last": 594.21, ... }
  }
}
```

`last` is extracted from `data["quotes"]["quote"]["last"]`.  If the key path is absent or
`last` is `None`, raise `TradierAPIError(0, "no last price returned for <symbol>")`.

---

## Module Design

### `tradier/enrichment.py`

```python
from datetime import date

import pandas as pd

from trade_hunter.tradier.client import TradierAPIError, TradierClient
from trade_hunter.tradier.selector import select_call, select_expiration, select_put


def enrich_candidates(
    candidates: pd.DataFrame,
    side: str,
    client: TradierClient,
    run_date: date,
    min_dte: int = 30,
    max_dte: int = 60,
) -> tuple[pd.DataFrame, list[str]]:
    """Fetch Tradier data for each candidate and return an enriched DataFrame.

    For each ticker in candidates["Symbol"]:
      1. Fetch option expirations → select nearest monthly in DTE window.
         Skip with warning if none qualifies.
      2. Fetch current underlying last price (quotes endpoint).
         Skip with warning on API error.
      3. Fetch option chain for selected expiration.
         Apply select_put (BULL) or select_call (BEAR).
         Skip with warning if no qualifying option found.
      4. Append all required Tradier fields to the enriched row.

    Args:
        candidates:  Joined DataFrame from filter_and_join (Symbol + all prior columns).
        side:        "BULL" or "BEAR" — determines put vs call selection.
        client:      Configured TradierClient instance.
        run_date:    Date used for DTE calculation (normally today).
        min_dte:     Minimum DTE threshold (inclusive).
        max_dte:     Maximum DTE threshold (inclusive).

    Returns:
        (enriched_df, warnings)
        enriched_df has all original columns plus the Tradier fields listed above.
        An empty DataFrame is returned (not an error) if all tickers are skipped.
    """
```

### Enrichment columns added

The following columns are appended to each surviving row:

| Column | Type | Notes |
|---|---|---|
| `Expiration Date` | `str` | `"YYYY-MM-DD"` |
| `DTE` | `int` | Calendar days from `run_date` |
| `Last Price` | `float` | Underlying last trade price |
| `Strike` | `float` | Selected option strike |
| `Option Type` | `str` | `"put"` or `"call"` |
| `Delta` | `float` | |
| `Open Interest` | `int` | |
| `Bid` | `float` | |
| `Ask` | `float` | |

### Warning messages

| Condition | Warning format |
|---|---|
| No qualifying monthly expiration | `"[BULL] 'XYZ' — no qualifying monthly expiration found, skipped"` |
| No qualifying option contract | `"[BULL] 'XYZ' — no qualifying put for 2025-04-18, skipped"` |
| Tradier API error | `"[BULL] 'XYZ' — Tradier API error (HTTP 429: ...), skipped"` |

### Skip behaviour

A ticker is skipped (not added to the enriched output) if:
- `select_expiration` returns `None`
- `select_put` / `select_call` returns `None`
- `TradierAPIError` is raised at any step

All other tickers continue processing regardless. The API error warning includes both the
status code and message from `TradierAPIError`.

---

## Acceptance Criteria

1. A BULL candidate with a valid expiration and qualifying put is enriched with all 9 Tradier
   columns.
2. A BEAR candidate produces a contract with `Option Type == "call"`.
3. A ticker with no qualifying monthly expiration is skipped; a warning is appended.
4. A ticker with no qualifying option contract is skipped; a warning is appended.
5. A `TradierAPIError` on any of the three API calls causes that ticker to be skipped with a
   warning; other tickers continue.
6. An empty input DataFrame returns an empty enriched DataFrame with no API calls made.
7. Two candidates where one fails and one succeeds: output has one row and one warning.
8. `get_last_price` returns the `last` value from the quotes response.
9. `get_last_price` raises `TradierAPIError` on a non-2xx response.
10. `uv run pytest` passes (all existing + new tests).
11. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_tradier_enrichment.py`)

All tests use `unittest.mock.MagicMock` to stub `TradierClient` methods — no HTTP transport
needed.

- `test_enrich_bull_success`: one BULL ticker; mocked expirations, last price, chain → one
  enriched row with correct `Option Type`, `Strike`, `Delta`, `DTE`, `Last Price`.
- `test_enrich_bear_success`: one BEAR ticker; call selected; `Option Type == "call"`.
- `test_enrich_no_expiration`: `get_option_expirations` returns no qualifying monthly →
  warning present, empty DataFrame returned.
- `test_enrich_no_qualifying_option`: chain has no put with delta ≤ −0.21 → warning, empty.
- `test_enrich_api_error_expirations`: `get_option_expirations` raises `TradierAPIError` →
  warning, empty DataFrame.
- `test_enrich_api_error_chain`: `get_option_chain` raises `TradierAPIError` → warning, empty.
- `test_enrich_multiple_one_fails`: two tickers; second fails expiration step → one enriched
  row, one warning.
- `test_enrich_empty_candidates`: empty input → empty output, no client methods called.

`tests/test_tradier_client.py` addition:
- `test_get_last_price_parses_response`: mock returns valid quotes JSON; assert float returned.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
