# Story-0110 — Diversity & SeekingAlpha Metrics

**Status**: Completed  
**Phase**: 4 — Hard Filters & Scoring Engine

---

## Goal

Implement the remaining seven quality metric functions needed by the Trade Score calculator:
**Cyclical Diversity**, **Sector Diversity**, **Quant Rating**, **Growth**, **Momentum**,
**Earnings Date**, and **Bid**. Like Story-0100, all functions are pure — value(s) in, quality
float out. They are added to the existing `pipeline/scoring.py`.

---

## Background

From `docs/PROJECT_INTENT.md` — metric weights:

| Metric | Weight | Source |
|---|---|---|
| Cyclical Diversity | 3.0 | Active trade sector buckets vs candidate's bucket |
| Quant Rating | 2.0 | SeekingAlpha `Quant Rating` (1.0–5.0) |
| Sector Diversity | 1.0 | Active trade sectors vs candidate's sector |
| Earnings Date | 1.0 | TastyTrade `Earnings At` → SA `Upcoming Announce Date` → +70 days |
| Growth | 1.0 | SeekingAlpha `Growth` grade (Growth bucket only) |
| Momentum | 1.0 | SeekingAlpha `Momentum` grade |
| Bid | 1.0 | Selected option bid |

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | Add seven quality functions |
| `apps/trade_hunter/tests/test_scoring_diversity.py` | Tests for Cyclical/Sector Diversity |
| `apps/trade_hunter/tests/test_scoring_seekingalpha.py` | Tests for Quant Rating, Growth, Momentum, Earnings Date, Bid |

Two test files keep related concerns together without creating an unwieldy single file.

---

## Module Design

### Functions added to `pipeline/scoring.py`

```python
def cyclical_diversity_quality(
    candidate_bucket: str,
    active_buckets: list[str],
) -> float:
    """Quality based on how concentrated active trades are in the candidate's sector bucket.

    active_buckets: one entry per deduplicated active ticker (their sector bucket).
    If active_buckets is empty, return 5.0 (no concentration).
    """

def sector_diversity_quality(
    candidate_sector: str,
    active_sectors: list[str],
) -> float:
    """Quality based on how concentrated active trades are in the candidate's exact sector.

    active_sectors: one entry per deduplicated active ticker (their standardized sector).
    If active_sectors is empty, return 5.0 (no concentration).
    """

def quant_rating_quality(quant_rating: float, side: str) -> float:
    """Map SeekingAlpha Quant Rating (1.0–5.0) to quality.

    BULL: quality = quant_rating (use directly).
    BEAR: quality = 6.0 - quant_rating (inverted).
    """

def grade_quality(grade: str) -> float:
    """Map a letter grade (A+…F) to a bullish quality score (0.0–5.0).

    Used by both growth_quality and momentum_quality before BEAR inversion.
    """

def growth_quality(grade: str, side: str) -> float:
    """Map SeekingAlpha Growth grade to quality.

    Only called when the candidate is in the Growth sector bucket.
    BULL: bullish mapping. BEAR: 5.0 - bullish_quality.
    """

def momentum_quality(grade: str, side: str) -> float:
    """Map SeekingAlpha Momentum grade to quality.

    BULL: bullish mapping. BEAR: 5.0 - bullish_quality.
    """

def earnings_date_quality(
    earnings_date: date,
    expiration_date: date,
) -> float:
    """Map EaE = (earnings_date - expiration_date).days to quality.

    EaE <= -14: 3.0  (earnings well past expiration)
    -14 < EaE <= 1:  0.0  (earnings near or during trade)
    EaE > 1:         5.0  (earnings safely after expiration)
    """

def bid_quality(bid: float) -> float:
    """Map option bid to quality."""
```

---

## Quality Tables

### Cyclical Diversity

Percentage = count of active tickers in the same bucket / total active tickers.

| Bucket Allocation % | Quality |
|---|---|
| `<= 21%` | `5.0` |
| `> 21%` and `<= 55%` | `2.0` |
| `> 55%` | `0.0` |

### Sector Diversity

Percentage = count of active tickers in the same sector / total active tickers.

| Sector Allocation % | Quality |
|---|---|
| `<= 3%` | `5.0` |
| `> 3%` and `<= 13%` | `2.0` |
| `> 13%` | `0.0` |

### Quant Rating

- BULL: quality = `quant_rating` (already on 1.0–5.0 scale)
- BEAR: quality = `6.0 - quant_rating`

### Grade mapping (Growth & Momentum — bullish)

| Grade | Quality |
|---|---|
| `A+` | `5.0` |
| `A` | `4.5` |
| `A-` | `4.0` |
| `B+` | `3.0` |
| `B` | `2.5` |
| `B-` | `2.0` |
| `C+` | `1.25` |
| `C` | `1.0` |
| `C-` | `0.75` |
| `D+` | `0.5` |
| `D` | `0.25` |
| `D-` | `0.1` |
| `F` | `0.0` |

BEAR quality = `5.0 - bullish_quality`.

### Earnings Date (`EaE = earnings_date − expiration_date` in calendar days)

| EaE | Quality |
|---|---|
| `<= -14` | `3.0` |
| `> -14` and `<= 1` | `0.0` |
| `> 1` | `5.0` |

### Bid

| Bid | Quality |
|---|---|
| `<= 0.55` | `0.0` |
| `> 0.55` and `<= 0.89` | `1.0` |
| `> 0.89` and `<= 1.44` | `2.5` |
| `> 1.44` and `<= 2.33` | `3.5` |
| `> 2.33` and `<= 3.77` | `4.5` |
| `> 3.77` and `<= 6.10` | `2.5` |
| `> 6.10` | `0.0` |

---

## Design Notes

### `grade_quality` helper

Both `growth_quality` and `momentum_quality` share the identical bullish grade-to-quality
mapping. Rather than duplicating a 13-entry dict twice, a private `grade_quality(grade)` helper
holds the table and is called by both. This is purely an internal DRY concern — the public API
remains `growth_quality` and `momentum_quality`.

### Earnings date — caller responsibility

`earnings_date_quality` receives two `date` objects and computes `EaE` internally. The caller
(Story-0120 Trade Score Calculator) is responsible for resolving the earnings date using the
three-source precedence rule (TastyTrade → SeekingAlpha → run_date + 70 days) before calling
this function. That resolution logic lives in Story-0120, not here.

### Empty active set

Both diversity functions return `5.0` when `active_buckets` / `active_sectors` is empty (no
active trades → no concentration → maximum diversity score).

---

## Acceptance Criteria

1. `cyclical_diversity_quality` returns `5.0` for empty active list.
2. `cyclical_diversity_quality` returns correct quality for each concentration band.
3. `sector_diversity_quality` returns `5.0` for empty active list.
4. `sector_diversity_quality` returns correct quality for each concentration band.
5. `quant_rating_quality` returns `quant_rating` directly for BULL.
6. `quant_rating_quality` returns `6.0 - quant_rating` for BEAR.
7. `grade_quality` maps all 13 grades correctly.
8. `growth_quality` returns `5.0 - bullish` for BEAR.
9. `momentum_quality` returns `5.0 - bullish` for BEAR.
10. `earnings_date_quality` returns correct quality for each EaE band including boundaries.
11. `bid_quality` returns correct quality for each band including the non-monotonic return
    to `2.5` above `3.77` and `0.0` above `6.10`.
12. `uv run pytest` passes (all existing + new tests).
13. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests

### `tests/test_scoring_diversity.py`

**`cyclical_diversity_quality`:**
- `test_cyclical_empty_active` → `5.0`
- `test_cyclical_low_concentration`: 2 of 10 active in same bucket = 20% → `5.0`
- `test_cyclical_boundary_21pct`: exactly 21% (e.g. 21 of 100) → `5.0`
- `test_cyclical_mid_concentration`: 22 of 100 in same bucket = 22% → `2.0`
- `test_cyclical_high_concentration`: 6 of 10 in same bucket = 60% → `0.0`
- `test_cyclical_boundary_55pct`: exactly 55 of 100 → `2.0`; 56 of 100 → `0.0`

**`sector_diversity_quality`:**
- `test_sector_empty_active` → `5.0`
- `test_sector_low_concentration`: 1 of 50 in same sector = 2% → `5.0`
- `test_sector_boundary_3pct`: exactly 3 of 100 → `5.0`; 4 of 100 → `2.0`
- `test_sector_mid_concentration`: 10 of 100 in same sector = 10% → `2.0`
- `test_sector_high_concentration`: 14 of 100 in same sector = 14% → `0.0`

### `tests/test_scoring_seekingalpha.py`

**`quant_rating_quality`:**
- `test_quant_bull`: rating=4.2 → `4.2`
- `test_quant_bear`: rating=4.2 → `6.0 - 4.2 = 1.8`
- `test_quant_bull_min_max`: 1.0 → `1.0`; 5.0 → `5.0`

**`grade_quality` / `growth_quality` / `momentum_quality`:**
- `test_all_grades`: all 13 grades mapped correctly for bullish
- `test_growth_bear_inversion`: `A+` bull=5.0, bear=0.0; `F` bull=0.0, bear=5.0
- `test_momentum_bear_inversion`: same inversion pattern

**`earnings_date_quality`:**
- `test_eae_well_past`: EaE = -20 → `3.0`
- `test_eae_boundary_minus14`: EaE = -14 → `3.0`; EaE = -13 → `0.0`
- `test_eae_danger_zone`: EaE = 0 → `0.0`
- `test_eae_boundary_1`: EaE = 1 → `0.0`; EaE = 2 → `5.0`
- `test_eae_safely_after`: EaE = 30 → `5.0`

**`bid_quality`:**
- `test_bid_zero`: bid=0.55 → `0.0`
- `test_bid_low`: bid=0.70 → `1.0`
- `test_bid_mid_low`: bid=1.10 → `2.5`
- `test_bid_mid`: bid=2.00 → `3.5`
- `test_bid_sweet_spot`: bid=3.00 → `4.5`
- `test_bid_high_fallback`: bid=5.00 → `2.5` (non-monotonic — tests the return to 2.5)
- `test_bid_very_high`: bid=7.00 → `0.0`

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
