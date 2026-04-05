# Story-0100 — Core Quality Metrics

**Status**: Completed  
**Phase**: 4 — Hard Filters & Scoring Engine

---

## Goal

Implement the five "Tradier-sourced or TastyTrade-sourced" quality metric calculations that
feed the Trade Score: **IVR**, **IVP**, **Open Interest**, **Spread%**, and **BPR**. Each
metric is a pure function (value in → quality float out) with no I/O or side effects. Story-0120
(Trade Score Calculator) will compose all quality metrics into the final weighted score.

---

## Background

From `docs/PROJECT_INTENT.md` — metric weights:

| Metric | Weight | Source |
|---|---|---|
| IVR | 3.0 | TastyTrade `IV Rank` |
| IVP | 3.0 | TastyTrade `IV %tile` |
| Open Interest | 3.0 | Tradier selected option |
| Spread% | 3.0 | Tradier `Bid` + `Ask` |
| BPR | 3.0 | Tradier `Last Price` + `Strike` + `Bid` |

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | Quality metric functions |
| `apps/trade_hunter/tests/test_scoring_core.py` | Unit tests |

No config, CLI, or dependency changes required.

---

## Module Design

### `pipeline/scoring.py`

Five focused functions, all pure. Each takes a numeric value and returns a `float` quality
score in the range `0.0`–`5.0`.

```python
def ivr_quality(iv_rank: float) -> float:
    """Map TastyTrade IV Rank to a quality score."""

def ivp_quality(iv_percentile: float) -> float:
    """Map TastyTrade IV %tile to a quality score."""

def open_interest_quality(open_interest: int | float) -> float:
    """Map selected option open interest to a quality score."""

def spread_pct_quality(bid: float, ask: float) -> float:
    """Compute Spread% = (ask - bid) / ((ask + bid) / 2) and map to quality."""

def bpr_quality(
    underlying_price: float,
    strike: float,
    bid: float,
    option_type: str,
) -> float:
    """Compute Buying Power Reduction and map to quality.

    option_type: "put" or "call"
    premium = bid (conservative, consistent with trade entry)
    """
```

---

## Quality Tables

### IVR Quality (`iv_rank`)

| Condition | Quality |
|---|---|
| `<= 10.0` | `0.0` |
| `> 10.0` and `<= 20.0` | `1.0` |
| `> 20.0` and `<= 30.0` | `2.0` |
| `> 30.0` and `<= 50.0` | `4.0` |
| `> 50.0` | `5.0` |

### IVP Quality (`iv_percentile`) — identical table

| Condition | Quality |
|---|---|
| `<= 10.0` | `0.0` |
| `> 10.0` and `<= 20.0` | `1.0` |
| `> 20.0` and `<= 30.0` | `2.0` |
| `> 30.0` and `<= 50.0` | `4.0` |
| `> 50.0` | `5.0` |

### Open Interest Quality

| Condition | Quality |
|---|---|
| `<= 10` | `0.0` |
| `> 10` and `<= 100` | `2.0` |
| `> 100` and `<= 1000` | `4.5` |
| `> 1000` | `5.0` |

### Spread% Quality

Formula: `spread_pct = (ask - bid) / ((ask + bid) / 2)`

| Spread% | Quality |
|---|---|
| `<= 2%` | `5.0` |
| `> 2%` and `<= 4%` | `4.5` |
| `> 4%` and `<= 6%` | `4.0` |
| `> 6%` and `<= 8%` | `3.0` |
| `> 8%` and `<= 12%` | `2.0` |
| `> 12%` and `<= 20%` | `1.0` |
| `> 20%` | `0.0` |

### BPR Quality

`premium = bid` (option bid, conservative entry price)

For puts: `OTM_amount = underlying_price - put_strike`  
For calls: `OTM_amount = call_strike - underlying_price`

```
BPR = max(
    0.20 * underlying_price - OTM_amount + premium,
    0.10 * underlying_price + premium,
    2.50 + premium,
) * 100
```

| BPR | Quality |
|---|---|
| `<= 500` | `3.0` |
| `> 500` and `<= 1500` | `5.0` |
| `> 1500` and `<= 3000` | `3.5` |
| `> 3000` and `<= 4500` | `1.5` |
| `> 4500` | `0.0` |

---

## Acceptance Criteria

1. `ivr_quality` and `ivp_quality` return correct quality for each table band, including exact
   boundary values.
2. `open_interest_quality` returns correct quality for each band and its boundaries.
3. `spread_pct_quality` computes the mid-price formula and maps to the correct band.
4. `bpr_quality` with `option_type="put"` computes OTM_amount as
   `underlying_price - put_strike`.
5. `bpr_quality` with `option_type="call"` computes OTM_amount as
   `call_strike - underlying_price`.
6. BPR result maps to the correct quality band.
7. `uv run pytest` passes (all existing + new tests).
8. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_scoring_core.py`)

All tests use direct function calls with known inputs and expected outputs.

**`ivr_quality` / `ivp_quality`** (same table — tested independently):
- Boundary at 10.0 → `0.0`; just above 10.0 → `1.0`
- Boundary at 20.0 → `1.0`; just above 20.0 → `2.0`
- Boundary at 30.0 → `2.0`; just above 30.0 → `4.0`
- Boundary at 50.0 → `4.0`; just above 50.0 → `5.0`
- Mid-band values: 5.0 → `0.0`; 15.0 → `1.0`; 25.0 → `2.0`; 40.0 → `4.0`; 75.0 → `5.0`

**`open_interest_quality`**:
- Boundary at 10 → `0.0`; 11 → `2.0`
- Boundary at 100 → `2.0`; 101 → `4.5`
- Boundary at 1000 → `4.5`; 1001 → `5.0`

**`spread_pct_quality`**:
- bid=0.99, ask=1.01 → spread≈2.0% → `5.0`
- bid=0.97, ask=1.03 → spread≈6.0% → `4.0` (boundary at 6%)
- bid=0.90, ask=1.10 → spread≈20.0% → `1.0` (boundary at 20%)
- bid=0.85, ask=1.15 → spread≈28.6% → `0.0`

**`bpr_quality`**:
- `test_bpr_put_quality`: SPY underlying=500, put_strike=480, bid=2.00 →
  OTM=20, BPR=max(0.20×500−20+2, 0.10×500+2, 2.50+2)×100 = max(82,52,4.5)×100 = 8200 → `0.0`
- `test_bpr_call_quality`: SPY underlying=500, call_strike=520, bid=2.00 →
  OTM=20, same formula → 8200 → `0.0`
- `test_bpr_mid_band`: underlying=100, strike=95 (put), bid=0.80 →
  OTM=5, BPR=max(0.20×100−5+0.80, 0.10×100+0.80, 2.50+0.80)×100 = max(15.8,10.8,3.3)×100 = 1580 → `3.5`
- `test_bpr_sweet_spot`: choose inputs that land in the 500–1500 band → `5.0`

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
