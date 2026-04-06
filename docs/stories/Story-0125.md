# Story-0125 — Liquidity Quality Metric

**Status**: Completed  
**Phase**: 4 — Hard Filters & Scoring Engine

---

## Goal

Add `liquidity_quality()` to `pipeline/scoring.py`, include `Liquidity` in the weighted Trade
Score with weight `1.0`, and update all affected tests. This story covers scoring only — the
workbook display transform ("X stars" text) is handled in Story-0130.

---

## Background

From `docs/PROJECT_INTENT.md`:

> The liquidity column in the tastytrade data contains binary that represent encoded star
> symbols that are used to indicate the level of liquidity — from 0 stars (very illiquid) to
> 4 stars (very liquid).

The quality mapping is **non-linear**:

| Stars | Raw string (Unicode) | Quality |
|---|---|---|
| ☆☆☆☆ (0 stars) | `"\u2606\u2606\u2606\u2606"` | `0.0` |
| ★☆☆☆ (1 star)  | `"\u2605\u2606\u2606\u2606"` | `0.5` |
| ★★☆☆ (2 stars) | `"\u2605\u2605\u2606\u2606"` | `2.0` |
| ★★★☆ (3 stars) | `"\u2605\u2605\u2605\u2606"` | `4.5` |
| ★★★★ (4 stars) | `"\u2605\u2605\u2605\u2605"` | `5.0` |

`Liquidity` is already present in the Universal Data Set (passed through from the TastyTrade
loader in Story-0020). No loader changes are required.

---

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | Add `_LIQUIDITY_QUALITY_MAP`, `liquidity_quality()`, add `"Liquidity": 1.0` to `_WEIGHTS`, update `calculate_scores()` |
| `apps/trade_hunter/tests/test_trade_score.py` | Add `Liquidity` to `_base_row()`, recalculate expected known-value score |

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/tests/test_scoring_liquidity.py` | Unit tests for `liquidity_quality()` |

---

## Implementation

### `liquidity_quality()` function

```python
_LIQUIDITY_QUALITY_MAP: dict[int, float] = {
    0: 0.0,
    1: 0.5,
    2: 2.0,
    3: 4.5,
    4: 5.0,
}

_FILLED_STAR = "\u2605"  # ★


def liquidity_quality(liquidity_str: str) -> float:
    """Map TastyTrade Liquidity star string to a quality score.

    Counts filled stars (★, U+2605) in the raw string. Returns 0.0 for any
    unrecognized value.
    """
    stars = liquidity_str.count(_FILLED_STAR)
    return _LIQUIDITY_QUALITY_MAP.get(stars, 0.0)
```

### `_WEIGHTS` update

Add one entry:

```python
"Liquidity": 1.0,
```

### `calculate_scores()` update

Inside the per-row loop, add one quality entry alongside the existing ones:

```python
"Liquidity": liquidity_quality(str(row["Liquidity"])),
```

`Liquidity` is always active — there is no Active Weight Rule exclusion for this metric.

### Required DataFrame column

| Column | Source |
|---|---|
| `Liquidity` | TastyTrade CSV, passed through Universal Data Set join |

---

## Known-value test update (`test_trade_score.py`)

### `_base_row()` amendment

Add `"Liquidity"` to the base row using ★★★☆ (3 filled stars = quality 4.5):

```python
"Liquidity": "\u2605\u2605\u2605\u2606",  # ★★★☆ → quality 4.5
```

### Recalculated expected score

Old: numerator = 96.0, denominator = 25, score = **3.84**

With Liquidity (weight 1.0, quality 4.5):
- numerator = 96.0 + (1.0 × 4.5) = **100.5**
- denominator = 25 + 1.0 = **26**
- score = 100.5 / 26 = 3.8653… → **3.87**

Update `test_score_known_value` docstring and assertion:

```python
assert result.iloc[0]["Trade Score"] == pytest.approx(3.87, abs=1e-4)
```

---

## Acceptance Criteria

1. `liquidity_quality("★★★☆")` returns `4.5`.
2. `liquidity_quality("☆☆☆☆")` returns `0.0`.
3. `liquidity_quality("★★★★")` returns `5.0`.
4. An unrecognized string (e.g. empty string, garbage) returns `0.0` without raising.
5. `"Liquidity": 1.0` is present in `_WEIGHTS`.
6. `calculate_scores()` includes Liquidity in the weighted average for every row.
7. The known-value test passes with the updated expected score of `3.87`.
8. `uv run pytest` passes (all existing + new tests).
9. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_scoring_liquidity.py`)

- `test_liquidity_0_stars`: `"☆☆☆☆"` → `0.0`
- `test_liquidity_1_star`: `"★☆☆☆"` → `0.5`
- `test_liquidity_2_stars`: `"★★☆☆"` → `2.0`
- `test_liquidity_3_stars`: `"★★★☆"` → `4.5`
- `test_liquidity_4_stars`: `"★★★★"` → `5.0`
- `test_liquidity_unknown_returns_zero`: empty string `""` → `0.0`

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
