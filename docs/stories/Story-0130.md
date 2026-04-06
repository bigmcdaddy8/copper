# Story-0130 — Excel Workbook Output

**Status**: Completed  
**Phase**: 5 — Output

---

## Goal

Write the scored BULL-ish and BEAR-ish DataFrames to `trade_signals.xlsx` with two worksheets,
all 23 output columns in the correct order, and number/date formats matching
`docs/PROJECT_INTENT.md`. Overwrite any existing file on each run.

---

## Background

From `docs/PROJECT_INTENT.md`:

> Write the output workbook to `uploads/trade_signals.xlsx`.
> Create two worksheets: `BULL-ish` and `BEAR-ish`.
> Each worksheet should be sorted in descending order by `Trade Score`.

The output directory is provided via `RunConfig.output_dir` (CLI `--output-dir`). The file
is written to `output_dir / "trade_signals.xlsx"`.

---

## Pre-condition: two missing scored columns

`calculate_scores` (Story-0120) resolves `Earnings Date` and computes `BPR` internally but
does not store them in the returned DataFrame. Both are required output columns. This story
adds them as a minor amendment to `pipeline/scoring.py` before the workbook writer is built.

`Liquidity` quality was added in Story-0125 and the raw `Liquidity` column is already present
in the scored DataFrame — no additional scoring.py work is needed for it.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/output/__init__.py` | Empty package marker |
| `apps/trade_hunter/src/trade_hunter/output/workbook.py` | `write_workbook()` function |
| `apps/trade_hunter/tests/test_workbook.py` | Unit tests |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | Extract `_bpr_value()` helper; store `Earnings Date` (str) and `BPR` (float) columns in `calculate_scores` output |
| `apps/trade_hunter/tests/test_trade_score.py` | Assert `Earnings Date` and `BPR` columns present in scored output |

---

## `calculate_scores` amendment

Extract the BPR dollar-value computation into a private `_bpr_value()` helper (reused by
`bpr_quality()`). Inside the per-row loop, capture:

- `resolved_earnings.isoformat()` → appended to `earnings_date_strs` list
- `_bpr_value(...)` → appended to `bpr_values` list

After the loop, append both as columns alongside `Trade Score`:

- `Earnings Date` — ISO date string `"YYYY-MM-DD"`
- `BPR` — raw dollar float (not the quality score)

---

## Column mapping

The scored DataFrame uses internal column names that differ from the workbook output headers.
The writer renames only the columns that change:

| DataFrame column | Workbook header |
|---|---|
| `Symbol` | `Ticker` |
| `Last Price` | `Price` |
| `IV Idx` | `IVx` |
| `IV Rank` | `IVR` |
| `IV %tile` | `IVP` |

All other column names pass through unchanged.

`Spread%` is computed in the writer as `(Ask - Bid) / ((Ask + Bid) / 2)` from the `Bid` and
`Ask` columns before column renaming.

`Option Type` values are title-cased (`"put"` → `"Put"`, `"call"` → `"Call"`) before writing.

`Earnings Date` and `Expiration Date` string values (`"YYYY-MM-DD"`) are parsed to
`datetime.date` objects before writing so openpyxl can apply the `MM/DD/YYYY` date format.

`Liquidity` raw star strings (e.g. `"★★★☆"`) are converted to `"X stars"` text by counting
filled star characters (★, U+2605): `f"{value.count('\u2605')} stars"`.

---

## Output column order (23 columns)

```
Ticker, Sector Bucket, Sector, Option Type, Expiration Date, Earnings Date,
DTE, Price, Strike, Bid, Ask, Spread%, Delta, Open Interest, Trade Score,
Quant Rating, Liquidity, Growth, Momentum, IVx, IVR, IVP, BPR
```

---

## Number formats (openpyxl)

Applied per-column using `cell.number_format`:

| Workbook header | openpyxl format string |
|---|---|
| `Ticker`, `Sector Bucket`, `Sector`, `Option Type`, `Liquidity`, `Growth`, `Momentum` | *(no format — text)* |
| `Expiration Date`, `Earnings Date` | `"MM/DD/YYYY"` |
| `DTE`, `Strike`, `Open Interest` | `"0"` |
| `Price`, `Trade Score`, `Quant Rating`, `IVR` | `"0.00"` |
| `Bid`, `Ask`, `Delta` | `"0.00"` |
| `Spread%`, `IVx`, `IVP` | `"0.0%"` |
| `BPR` | `"$#,##0"` |

`Spread%`, `IVx`, and `IVP` are stored as fractions (e.g. `0.087` for 8.7%) so that
openpyxl's `"0.0%"` format renders them correctly. The writer divides `IV Idx` and `IV %tile`
by 100 if their values appear to be stored as whole-number percentages (i.e. > 1.0).

---

## Function signature

```python
# output/workbook.py

from datetime import date
from pathlib import Path

import pandas as pd


def write_workbook(
    bull_scored: pd.DataFrame,
    bear_scored: pd.DataFrame,
    output_dir: Path,
) -> Path:
    """Write BULL-ish and BEAR-ish worksheets to output_dir/trade_signals.xlsx.

    Each sheet is sorted descending by Trade Score.
    Creates output_dir if it does not exist.
    Overwrites any existing trade_signals.xlsx.

    Returns the Path to the written file.
    """
```

---

## Acceptance Criteria

1. Output file is written to `output_dir / "trade_signals.xlsx"`.
2. Workbook contains exactly two worksheets named `"BULL-ish"` and `"BEAR-ish"`.
3. Each sheet has exactly 23 column headers in the order specified above.
4. Each sheet is sorted descending by `Trade Score`.
5. An existing `trade_signals.xlsx` is overwritten without error.
6. `output_dir` is created if it does not exist.
7. `Option Type` values are title-cased (`Put` / `Call`).
8. Date columns contain `datetime.date` values (not strings) so openpyxl formats them correctly.
9. `Spread%`, `IVx`, and `IVP` are stored as fractions.
10. `Liquidity` is written as `"X stars"` text.
11. `calculate_scores` output now includes `Earnings Date` and `BPR` columns.
12. `uv run pytest` passes (all existing + new tests).
13. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_workbook.py`)

All tests write to a `tmp_path` directory (pytest fixture) — no permanent files created.

- `test_workbook_creates_file`: call `write_workbook` with minimal scored DataFrames; assert
  file exists at `tmp_path / "trade_signals.xlsx"`.
- `test_workbook_sheet_names`: assert exactly `["BULL-ish", "BEAR-ish"]` sheets present.
- `test_workbook_column_headers`: assert all 23 expected headers are present in each sheet.
- `test_workbook_sorted_by_trade_score`: provide rows with scores 3.0, 4.5, 2.1; assert first
  row has score 4.5.
- `test_workbook_overwrites_existing`: write twice to same path; assert no error and file
  contains second write's data.
- `test_workbook_creates_output_dir`: pass a non-existent subdirectory; assert it is created.
- `test_workbook_option_type_titlecased`: row with `Option Type="put"`; assert cell value is
  `"Put"`.
- `test_workbook_empty_bear_sheet`: BEAR DataFrame is empty; assert sheet exists with headers
  but zero data rows.
- `test_workbook_liquidity_stars_text`: row with `Liquidity="★★★☆"`; assert cell value is
  `"3 stars"`.

`tests/test_trade_score.py` additions:
- `test_scored_has_earnings_date_column`: assert `Earnings Date` column present in result.
- `test_scored_has_bpr_column`: assert `BPR` column present in result.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
