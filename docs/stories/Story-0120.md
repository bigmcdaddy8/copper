# Story-0120 — Trade Score Calculator

**Status**: Completed  
**Phase**: 4 — Hard Filters & Scoring Engine

---

## Goal

Implement `calculate_scores()` — a function that takes a filtered, enriched DataFrame and
computes a `Trade Score` column (0.00–5.00) for each row by composing the twelve quality
functions from Stories 0100 and 0110 into the weighted average formula from
`docs/PROJECT_INTENT.md`. This is the last story in Phase 4.

---

## Background

From `docs/PROJECT_INTENT.md`:

```
Trade Score = sum(weight * quality) / sum(active weights)
```

**Active Weight Rule:** All weights participate except `Growth`, which is excluded when the
candidate's `Sector Bucket` is not `"Growth"`.

| Metric | Weight |
|---|---|
| IVR | 3.0 |
| IVP | 3.0 |
| Open Interest | 3.0 |
| Spread% | 3.0 |
| BPR | 3.0 |
| Cyclical Diversity | 3.0 |
| Quant Rating | 2.0 |
| Sector Diversity | 1.0 |
| Earnings Date | 1.0 |
| Growth | 1.0 |
| Momentum | 1.0 |
| Bid | 1.0 |

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | Add `calculate_scores()` |
| `apps/trade_hunter/tests/test_trade_score.py` | Unit tests |

---

## Design

### Diversity inputs

Both `cyclical_diversity_quality` and `sector_diversity_quality` require a list of sector
buckets / sectors for all **active** (open-trade) tickers. The caller must supply this as two
parallel lists derived from the Universal Data Set join with the active symbol set.

```python
def calculate_scores(
    enriched: pd.DataFrame,
    side: str,
    run_date: date,
    active_buckets: list[str],
    active_sectors: list[str],
) -> pd.DataFrame:
```

`active_buckets` and `active_sectors` each contain one entry per deduplicated active ticker
(their `Sector Bucket` and `Sector` from the Universal Data Set respectively). The caller
builds these lists before calling `calculate_scores`.

### Earnings date resolution

Inside `calculate_scores`, for each row, the earnings date is resolved with the
three-source precedence rule:

1. TastyTrade `Earnings At` — if present and non-null, use it.
2. SeekingAlpha `Upcoming Announce Date` — if present and non-null, use it.
3. Fallback: `run_date + 70 calendar days`.

The resolved date is then passed to `earnings_date_quality(earnings_date, expiration_date)`.

Both `Earnings At` and `Upcoming Announce Date` may be absent from the DataFrame (optional
columns). The resolver must handle `KeyError` and `NaN`/`NaT` gracefully.

### Return value

`calculate_scores` returns the input DataFrame with one new column appended:

| Column | Type | Notes |
|---|---|---|
| `Trade Score` | `float` | Rounded to 2 decimal places; clamped to 0.00–5.00 |

The input DataFrame is not mutated — a copy with the new column is returned.

### Score clamping

The weighted average formula is mathematically bounded to [0.0, 5.0] when all quality values
are in [0.0, 5.0], but floating-point arithmetic may produce values fractionally outside this
range. The final score is clamped with `max(0.0, min(5.0, score))` before rounding.

---

## Function Signature

```python
# pipeline/scoring.py

def calculate_scores(
    enriched: pd.DataFrame,
    side: str,
    run_date: date,
    active_buckets: list[str],
    active_sectors: list[str],
) -> pd.DataFrame:
    """Compute Trade Score for each row and return DataFrame with 'Trade Score' column appended.

    Args:
        enriched:        Filtered, enriched DataFrame from apply_hard_filters().
        side:            "BULL" or "BEAR" — passed to side-sensitive quality functions.
        run_date:        Used as fallback earnings date base (run_date + 70 days).
        active_buckets:  One sector bucket per deduplicated active ticker.
        active_sectors:  One sector per deduplicated active ticker.

    Returns:
        Copy of enriched with 'Trade Score' column added (float, 2 d.p., clamped 0–5).
    """
```

---

## Required DataFrame Columns

| Column | Used by |
|---|---|
| `IV Rank` | `ivr_quality` |
| `IV %tile` | `ivp_quality` |
| `Open Interest` | `open_interest_quality` |
| `Bid` | `spread_pct_quality`, `bpr_quality`, `bid_quality` |
| `Ask` | `spread_pct_quality` |
| `Last Price` | `bpr_quality` |
| `Strike` | `bpr_quality` |
| `Option Type` | `bpr_quality` |
| `Sector Bucket` | Active Weight Rule for Growth; `cyclical_diversity_quality` |
| `Sector` | `sector_diversity_quality` |
| `Quant Rating` | `quant_rating_quality` |
| `Growth` | `growth_quality` (Growth bucket only) |
| `Momentum` | `momentum_quality` |
| `Expiration Date` | `earnings_date_quality` |
| `Earnings At` | Earnings date resolution (optional) |
| `Upcoming Announce Date` | Earnings date resolution (optional) |

---

## Acceptance Criteria

1. A BULL candidate in the Growth sector bucket has Growth included in the weighted average.
2. A BULL candidate NOT in the Growth sector bucket has Growth excluded (weight and quality
   both dropped from numerator and denominator).
3. Score is clamped to 0.00 minimum and 5.00 maximum.
4. Score is rounded to 2 decimal places.
5. When both `Earnings At` and `Upcoming Announce Date` are absent/null, the fallback
   `run_date + 70` is used.
6. `Earnings At` takes precedence over `Upcoming Announce Date`.
7. An empty input DataFrame returns an empty DataFrame with no errors.
8. Known-input → known-output: a hand-computed score matches within floating-point tolerance.
9. `uv run pytest` passes (all existing + new tests).
10. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_trade_score.py`)

All tests use inline synthetic DataFrames. The known-score test hand-computes the expected
weighted average from first principles to verify the formula is wired correctly end-to-end.

- `test_score_growth_bucket_included`: candidate in Growth bucket → Growth weight active;
  spot-check `Trade Score` column present and in [0.0, 5.0].
- `test_score_non_growth_bucket_excluded`: candidate in Economic bucket → Growth excluded;
  assert score differs from Growth-included result for the same row data.
- `test_score_known_value`: fully specified row with hand-computed expected score; assert
  `pytest.approx` match within 1e-4.
- `test_score_earnings_at_precedence`: row has both `Earnings At` and `Upcoming Announce Date`;
  assert `Earnings At` is used.
- `test_score_earnings_fallback`: both earnings columns absent/null → fallback = run_date + 70.
- `test_score_empty_input`: empty DataFrame → empty output, no error.
- `test_score_clamped`: construct a pathological row where raw weighted average would slightly
  exceed 5.0 due to floating-point; assert output is clamped to 5.0.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
