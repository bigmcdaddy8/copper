# Story-0030 — SeekingAlpha Loaders

**Status**: Completed  
**Phase**: 2 — Data Ingestion Layer

---

## Goal

Load the SeekingAlpha BULL-ish and BEAR-ish Excel files, validate required columns, and return
clean DataFrames for use in candidate filtering and scoring. Both files support the same
pattern as the TastyTrade loader: explicit path via CLI option or automatic discovery from
the downloads directory.

---

## Background

From `docs/PROJECT_INTENT.md`:

> One file contains BULL-ish candidates. One file contains BEAR-ish candidates.
> The file names are not yet fixed by business rule, so the program should accept them
> explicitly or discover them via configurable patterns.

File naming convention provided by the Vibe Engineer:

| Side | Glob pattern | Example |
|---|---|---|
| BULL-ish | `Copper_BULLish *.xlsx` | `Copper_BULLish 2026-04-01.xlsx` |
| BEAR-ish | `Copper_BEARish *.xlsx` | `Copper_BEARish 2026-03-28.xlsx` |

When multiple files match, the one with the **newest `YYYY-MM-DD`** in the filename is used.
The BULL-ish and BEAR-ish dates do not need to match.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/loaders/seekingalpha.py` | Load, discover, and validate SeekingAlpha BULL/BEAR Excel files |
| `apps/trade_hunter/tests/test_seekingalpha_loader.py` | Unit tests |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/config.py` | Make `bull_file` and `bear_file` optional (`Path \| None = None`) |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Make `--bull-file` and `--bear-file` optional; update summary |

No new dependencies — `openpyxl` is already pulled in transitively by `pandas` for `.xlsx` reads.

---

## Column Specification

### Required columns (missing any → `ValueError`, fail the run)

| Column | Use |
|---|---|
| `Symbol` | Candidate ticker |
| `Quant Rating` | Numeric `1.0`–`5.0`; scoring input |
| `Growth` | Letter grade `A+`–`F`; scoring input for Growth-bucket tickers |
| `Momentum` | Letter grade `A+`–`F`; scoring input |

### Optional columns (absent is allowed; stored as NaN if present)

| Column | Use |
|---|---|
| `Upcoming Announce Date` | Fallback earnings date (primary = TastyTrade `Earnings At`) |
| `Company Name` | Informational pass-through |

All other columns in the file are ignored and not retained in the output.

---

## Module Design

### `loaders/seekingalpha.py`

```python
BULL_GLOB = "Copper_BULLish *.xlsx"
BEAR_GLOB = "Copper_BEARish *.xlsx"

REQUIRED_COLUMNS = ["Symbol", "Quant Rating", "Growth", "Momentum"]

_OUTPUT_COLUMNS = [
    "Symbol",
    "Company Name",         # optional — included if present
    "Quant Rating",
    "Growth",
    "Momentum",
    "Upcoming Announce Date",  # optional — included if present
]

def discover_seekingalpha_file(downloads_dir: Path, glob: str) -> Path:
    """
    Return the newest matching Excel file in downloads_dir.
    'Newest' is determined by the YYYY-MM-DD suffix in the filename stem.

    Raises:
        FileNotFoundError: if no matching file is found.
    """

def load_seekingalpha(
    downloads_dir: Path,
    explicit_path: Path | None = None,
    side: str = "BULL",        # "BULL" or "BEAR" — used only in warning messages
) -> tuple[pd.DataFrame, list[str]]:
    """
    Load a SeekingAlpha Excel file and return (DataFrame, warnings).

    If explicit_path is provided it is used directly; otherwise the appropriate
    glob (BULL_GLOB or BEAR_GLOB) is used for discovery based on `side`.

    Raises:
        FileNotFoundError: if explicit_path does not exist, or discovery finds no files.
        ValueError: if any required column is missing from the file.
    """
```

**Discovery logic in `discover_seekingalpha_file`:**

1. Glob `downloads_dir` for the given pattern.
2. Extract the date string from each filename stem: the final space-delimited segment
   (`stem.split(' ')[-1]`), which is the `YYYY-MM-DD` portion.
3. Return `max(candidates, key=...)` — ISO date strings sort correctly lexicographically.
4. Raise `FileNotFoundError` with a clear message if no files are found.

**`load_seekingalpha` selects the glob based on `side`:**

```python
glob = BULL_GLOB if side == "BULL" else BEAR_GLOB
```

### `RunConfig` changes

```python
@dataclass
class RunConfig:
    journal_file: Path            # unchanged — still required
    output_dir: Path              # unchanged — still required
    tradier_api_key: str          # unchanged — still required
    downloads_dir: Path = ...     # unchanged
    tastytrade_file: Path | None = None  # unchanged
    bull_file: Path | None = None        # was required, now optional
    bear_file: Path | None = None        # was required, now optional
    ...
```

---

## Warning & Error Behaviour

| Condition | Behaviour |
|---|---|
| File not found (explicit or discovery) | Raise `FileNotFoundError` — caller fails the run |
| No files match discovery glob | Raise `FileNotFoundError` with message listing pattern and directory |
| Required column missing | Raise `ValueError` listing all missing column names — caller fails the run |
| Null/empty Symbol | Append `"[SeekingAlpha BULL] Row with null Symbol dropped"` to warnings; drop row |

Warnings are returned as `list[str]`. The loader does not call `print` or `logging` directly.

---

## Function Signatures Summary

```python
# loaders/seekingalpha.py
def discover_seekingalpha_file(downloads_dir: Path, glob: str) -> Path: ...
def load_seekingalpha(downloads_dir: Path, explicit_path: Path | None = None, side: str = "BULL") -> tuple[pd.DataFrame, list[str]]: ...
```

---

## Acceptance Criteria

1. `discover_seekingalpha_file` returns the file with the latest `YYYY-MM-DD` when multiple matches exist.
2. `discover_seekingalpha_file` raises `FileNotFoundError` when no matching files exist.
3. `load_seekingalpha` uses `explicit_path` when provided, skipping discovery.
4. `load_seekingalpha` raises `FileNotFoundError` when an explicit path does not exist.
5. `load_seekingalpha` raises `ValueError` listing all missing required columns when any are absent.
6. A row with a null/empty Symbol is dropped and a warning is returned.
7. The returned DataFrame retains `Symbol`, `Quant Rating`, `Growth`, `Momentum`, and optional columns when present.
8. `--bull-file` and `--bear-file` are optional in `trade_hunter run --help`.
9. `uv run pytest` passes (all existing + new tests).
10. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests

### `tests/test_seekingalpha_loader.py`

**Discovery:**
- `test_discover_newest_bull_file`: two matching BULL files with different dates; assert newer is returned.
- `test_discover_no_files`: empty temp dir; assert `FileNotFoundError`.

**Error cases:**
- `test_load_explicit_path_missing`: non-existent explicit path; assert `FileNotFoundError`.
- `test_load_missing_required_columns`: xlsx missing `"Momentum"`; assert `ValueError` mentioning `"Momentum"`.

**Warning cases:**
- `test_load_null_symbol`: one row with null Symbol is dropped; warning returned.

**Happy path:**
- `test_load_bull_happy_path`: valid xlsx with all required columns; assert output has correct columns, correct row count.
- `test_load_bear_uses_bear_glob`: temp dir with one BEAR file and no BULL file; call with `side="BEAR"` and no explicit path; assert loaded successfully.
- `test_load_optional_columns_included`: xlsx with `Company Name` and `Upcoming Announce Date` present; assert both appear in output.
- `test_load_optional_columns_absent`: xlsx without optional columns; assert no error, output still has required columns.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m trade_hunter run --help   # confirm --bull-file and --bear-file are optional
```
