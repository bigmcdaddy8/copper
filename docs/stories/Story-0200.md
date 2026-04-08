# Story-0200 — Individual Score Columns in Output Spreadsheet

**Status**: Completed  
**Phase**: 7 — Maintenance & Enhancements  
**Addresses**: Backlog-0050

---

## Goal

Append all 13 individual quality scores (0.0–5.0) as columns in `trade_signals.xlsx`, positioned immediately after the `Trade Score` column. Currently only the final weighted Trade Score is visible; exposing the components lets the user understand why a ticker ranked where it did.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | `calculate_scores()` returns `tuple[float, dict[str, float]]` instead of `float` |
| `apps/trade_hunter/src/trade_hunter/pipeline/runner.py` | Unpack both return values; attach individual score columns to each candidate row |
| `apps/trade_hunter/src/trade_hunter/output/workbook.py` | Add 13 score columns after `Trade Score`; format all as `0.00` |
| `apps/trade_hunter/tests/test_scoring.py` | Update tests for new return signature |
| `apps/trade_hunter/tests/test_workbook.py` | Verify 13 new columns present in output |

---

## Detailed Design

### `scoring.py` — new return type

`calculate_scores()` currently computes individual scores internally and discards them. Change the signature to return both:

```python
def calculate_scores(row: pd.Series, side: str, active_sectors: list[str], active_buckets: list[str]) -> tuple[float, dict[str, float]]:
    """
    Returns:
        trade_score: weighted average, clamped [0.0, 5.0], rounded to 2 d.p.
        scores: dict mapping metric name to its 0.0–5.0 score
    """
```

The `scores` dict keys match the output column names exactly:

```python
scores = {
    "IVR Score": ivr_quality(row["IV Rank"]),
    "IVP Score": ivp_quality(row["IV %tile"]),
    "Open Interest Score": open_interest_quality(row["Open Interest"]),
    "Spread% Score": spread_pct_quality(row["Bid"], row["Ask"]),
    "BPR Score": bpr_quality(...),
    "Cyclical Diversity Score": cyclical_diversity_quality(...),
    "Quant Rating Score": quant_rating_quality(...),
    "Sector Diversity Score": sector_diversity_quality(...),
    "Earnings Date Score": earnings_date_quality(...),
    "Growth Score": growth_quality(...) if is_growth_bucket else 0.0,
    "Momentum Score": momentum_quality(...),
    "Bid Score": bid_quality(row["Bid"]),
    "Liquidity Score": liquidity_quality(row["Liquidity"]),
}
```

### `runner.py` — attach scores to DataFrame

```python
trade_score, individual_scores = calculate_scores(row, side, active_sectors, active_buckets)
# attach individual scores as new columns on the candidate row/DataFrame
for col, val in individual_scores.items():
    df.at[idx, col] = val
```

### `workbook.py` — new columns

After the existing `Trade Score` entry in `_OUTPUT_COLUMNS`, add:

```python
("IVR Score",               "0.00"),
("IVP Score",               "0.00"),
("Open Interest Score",     "0.00"),
("Spread% Score",           "0.00"),
("BPR Score",               "0.00"),
("Cyclical Diversity Score","0.00"),
("Quant Rating Score",      "0.00"),
("Sector Diversity Score",  "0.00"),
("Earnings Date Score",     "0.00"),
("Growth Score",            "0.00"),
("Momentum Score",          "0.00"),
("Bid Score",               "0.00"),
("Liquidity Score",         "0.00"),
```

Total output columns becomes 36 (23 existing + 13 new).

---

## Acceptance Criteria

1. Output spreadsheet contains 36 columns; the 13 new score columns appear immediately after `Trade Score`.
2. Each individual score value is in range 0.00–5.00 and formatted to 2 decimal places.
3. `Growth Score` is `0.00` for tickers whose `Sector Bucket` is not Growth (consistent with the weighted score excluding it).
4. All existing tests pass; new tests in `test_workbook.py` verify column presence.
5. `test_scoring.py` updated to unpack and assert on the new tuple return.

---

## Verification Steps

```bash
# Unit tests
uv run pytest apps/trade_hunter/tests/test_scoring.py apps/trade_hunter/tests/test_workbook.py -v

# Full test suite
uv run pytest apps/trade_hunter/tests/

# Inspect output: confirm 36 columns present
python3 -c "
import openpyxl
wb = openpyxl.load_workbook('/tmp/th_out/trade_signals.xlsx')
ws = wb['BULL-ish']
headers = [ws.cell(1, c).value for c in range(1, ws.max_column + 1)]
print(f'Column count: {len(headers)}')
print([h for h in headers if 'Score' in (h or '')])
"
```
