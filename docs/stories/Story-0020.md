# Story-0020 — TastyTrade Loader & Universal Data Set

**Status**: Completed  
**Phase**: 2 — Data Ingestion Layer

---

## Goal

Load the TastyTrade CSV file, validate required columns, apply sector normalization and bucket
assignment, and produce the **Universal Data Set** — the authoritative ticker universe for the
entire pipeline. Any ticker absent from this set is out of scope for the run.

Supports both explicit file path (via `--tastytrade-file`) and automatic file discovery from a
configurable downloads directory when no explicit path is given.

---

## Background

From `docs/PROJECT_INTENT.md`:

> The Universal Data Set is the TastyTrade file after sector normalization and basic validation.
> Any SeekingAlpha candidate not present in the Universal Data Set is out of scope for this run.

> Initial implementation should support explicit input paths via CLI options. If file discovery
> is added, it should use configurable glob patterns rather than hard-coded filenames.

This story introduces file discovery. The TastyTrade filename follows the pattern:

```
tastytrade_watchlist_m8investments_Russell 1000_YYMMDD.csv
```

When `--tastytrade-file` is not provided, the loader discovers the newest matching file in the
downloads directory by comparing the `YYMMDD` date suffix in the filename.

This story also establishes the two normalization tables (sector map and bucket map) in
`pipeline/normalize.py`, which are reused by diversity scoring in Story-0110.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/loaders/__init__.py` | Empty package marker |
| `apps/trade_hunter/src/trade_hunter/loaders/tastytrade.py` | Load, discover, and validate the TastyTrade CSV |
| `apps/trade_hunter/src/trade_hunter/pipeline/__init__.py` | Empty package marker |
| `apps/trade_hunter/src/trade_hunter/pipeline/normalize.py` | Sector normalization + bucket mapping tables and functions |
| `apps/trade_hunter/tests/test_tastytrade_loader.py` | Unit tests for the TastyTrade loader |
| `apps/trade_hunter/tests/test_normalize.py` | Unit tests for sector normalization and bucket mapping |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/pyproject.toml` | Add `pandas>=2.2` dependency |
| `apps/trade_hunter/src/trade_hunter/config.py` | Add `downloads_dir` field; make `tastytrade_file` optional (`Path \| None`) |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Make `--tastytrade-file` optional; add `--downloads-dir` option |

---

## Dependencies

Add to `apps/trade_hunter`:

```
pandas>=2.2
```

---

## CLI Changes

### `--downloads-dir` (new option)

```
--downloads-dir    PATH    Directory to search for input files when explicit paths are omitted.
                           Default: /home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/downloads
```

### `--tastytrade-file` (now optional)

```
--tastytrade-file  PATH    TastyTrade CSV download. If omitted, auto-discovered from --downloads-dir
                           using pattern: tastytrade_watchlist_m8investments_Russell 1000_*.csv
```

### `RunConfig` changes

```python
@dataclass
class RunConfig:
    # tastytrade_file: Path | None  ← was required Path, now optional
    downloads_dir: Path = Path("/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/downloads")
    tastytrade_file: Path | None = None   # None → auto-discover at load time
    bull_file: Path                       # unchanged — explicit still required for SA files
    ...
```

The resolved file path (discovered or explicit) is logged in the dry-run summary.

---

## Module Design

### `pipeline/normalize.py`

Defines two lookup tables as module-level constants and two pure functions.

```python
# Sector normalization: TastyTrade raw value → standard sector name
SECTOR_MAP: dict[str, str] = {
    "Basic Materials":       "Materials",
    "Capital Goods":         "Industrials",
    "Consumer Cyclical":     "Consumer Discretionary",
    "Consumer/Non-Cyclical": "Consumer Staples",
    "Energy":                "Energy",
    "Financial":             "Financials",
    "Healthcare":            "Health Care",
    "Services":              "Communication Services",
    "Technology":            "Information Technology",
    "Transportation":        "Consumer Discretionary",
    "Utilities":             "Utilities",
    "Real Estate":           "Real Estate",
    "REIT":                  "Real Estate",
}

# Bucket assignment: standard sector name → cyclical bucket
BUCKET_MAP: dict[str, str] = {
    "Materials":              "Economic",
    "Industrials":            "Economic",
    "Consumer Discretionary": "Growth",
    "Consumer Staples":       "Defensive",
    "Energy":                 "Economic",
    "Financials":             "Economic",
    "Health Care":            "Defensive",
    "Communication Services": "Growth",
    "Information Technology": "Growth",
    "Utilities":              "Defensive",
    "Real Estate":            "Economic",
}

def normalize_sector(raw: str) -> str | None:
    """Return the standard sector name, or None if unrecognized."""

def assign_bucket(standard_sector: str) -> str:
    """Return the sector bucket for a standard sector name."""
```

### `loaders/tastytrade.py`

```python
REQUIRED_COLUMNS = ["Symbol", "IV Idx", "IV Rank", "IV %tile", "Sector"]

TASTYTRADE_GLOB = "tastytrade_watchlist_m8investments_Russell 1000_*.csv"

def discover_tastytrade_file(downloads_dir: Path) -> Path:
    """
    Return the newest TastyTrade CSV in downloads_dir matched by TASTYTRADE_GLOB.
    'Newest' is determined by the YYMMDD suffix in the filename.

    Raises:
        FileNotFoundError: if no matching file is found.
    """

def load_tastytrade(
    downloads_dir: Path,
    explicit_path: Path | None = None,
) -> tuple[pd.DataFrame, list[str]]:
    """
    Load TastyTrade CSV and return the Universal Data Set DataFrame plus warnings.

    If explicit_path is given, use it directly.
    Otherwise discover the newest matching file in downloads_dir.

    Raises:
        FileNotFoundError: if explicit_path does not exist, or discovery finds no files.
        ValueError: if any required column is missing from the file.
    """
```

**File selection logic in `discover_tastytrade_file`:**

1. Glob `downloads_dir` for `TASTYTRADE_GLOB`.
2. For each match, extract the `YYMMDD` suffix (the 6-character segment before `.csv`).
3. Sort candidates descending by that suffix string (lexicographic order is correct for `YYMMDD`).
4. Return the first (newest). If no files found, raise `FileNotFoundError` with a clear message.

**Return columns** from `load_tastytrade`:

| Output Column | Source Column | Notes |
|---|---|---|
| `Symbol` | `Symbol` | Whitespace stripped |
| `Name` | `Name` | Pass-through; may be NaN |
| `Liquidity` | `Liquidity` | Pass-through; may be NaN |
| `IV Idx` | `IV Idx` | Numeric |
| `IV Rank` | `IV Rank` | Numeric |
| `IV %tile` | `IV %tile` | Numeric |
| `Earnings At` | `Earnings At` | String/NaN (parsed downstream) |
| `Sector` | `Sector` | Normalized standard name |
| `Sector Bucket` | _(derived)_ | Assigned from `BUCKET_MAP` |

Rows where `Symbol` is null/empty are dropped with a warning.
Rows with an unrecognized sector are dropped with a warning.

---

## Warning & Error Behaviour

| Condition | Behaviour |
|---|---|
| File not found (explicit or discovery) | Raise `FileNotFoundError` — caller fails the run |
| No files match discovery pattern | Raise `FileNotFoundError` with message listing the pattern and directory |
| Required column missing | Raise `ValueError` with the missing column name(s) — caller fails the run |
| Unrecognized sector value | Append `"[TastyTrade] Unknown sector '<val>' for '<sym>' — skipped"` to warnings list; drop row |
| Null/empty Symbol | Append `"[TastyTrade] Row with null Symbol dropped"` to warnings list; drop row |

Warnings are returned as `list[str]`. The loader does **not** call `print` or `logging` directly.

---

## Function Signatures Summary

```python
# pipeline/normalize.py
def normalize_sector(raw: str) -> str | None: ...
def assign_bucket(standard_sector: str) -> str: ...

# loaders/tastytrade.py
def discover_tastytrade_file(downloads_dir: Path) -> Path: ...
def load_tastytrade(downloads_dir: Path, explicit_path: Path | None = None) -> tuple[pd.DataFrame, list[str]]: ...
```

---

## Acceptance Criteria

1. `discover_tastytrade_file` returns the file with the latest `YYMMDD` suffix when multiple matches exist.
2. `discover_tastytrade_file` raises `FileNotFoundError` when no matching files exist.
3. `load_tastytrade` uses `explicit_path` when provided, skipping discovery.
4. `load_tastytrade` raises `FileNotFoundError` when an explicit path does not exist.
5. `load_tastytrade` raises `ValueError` listing missing column names when any required column is absent.
6. A row with an unrecognized sector is dropped and a warning string is returned.
7. A row with a null Symbol is dropped and a warning string is returned.
8. All 13 TastyTrade sector values in `SECTOR_MAP` map to the correct standard sector name.
9. All 11 standard sector names in `BUCKET_MAP` map to the correct bucket.
10. The returned DataFrame contains `Sector` (standardized) and `Sector Bucket` columns.
11. `--tastytrade-file` is optional in `trade_hunter run --help`; `--downloads-dir` appears with the correct default.
12. `uv run pytest` passes (all existing + new tests).
13. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests

### `tests/test_normalize.py`
- `test_sector_map_complete`: assert all 13 raw TastyTrade sector names are present in `SECTOR_MAP`.
- `test_bucket_map_complete`: assert all 11 standard sector names are present in `BUCKET_MAP`.
- `test_normalize_sector_known`: spot-check several known mappings (e.g., `"REIT"` → `"Real Estate"`).
- `test_normalize_sector_unknown`: assert `normalize_sector("Bogus")` returns `None`.
- `test_assign_bucket`: spot-check several bucket assignments (e.g., `"Information Technology"` → `"Growth"`).

### `tests/test_tastytrade_loader.py`
- `test_discover_newest_file`: create two temp CSV files with different YYMMDD suffixes; assert the newer one is returned.
- `test_discover_no_files`: assert `FileNotFoundError` when directory has no matching files.
- `test_load_explicit_path_missing`: assert `FileNotFoundError` for non-existent explicit path.
- `test_load_missing_required_column`: synthetic CSV missing `"IV Rank"`; assert `ValueError`.
- `test_load_unknown_sector`: synthetic row with unrecognized sector is dropped; warning returned.
- `test_load_null_symbol`: synthetic row with null Symbol is dropped; warning returned.
- `test_load_happy_path`: synthetic DataFrame with all required columns; assert output has `Sector` and `Sector Bucket` columns and correct row count.
- `test_load_sector_normalized`: assert raw `"Technology"` becomes `"Information Technology"` in output.
- `test_load_uses_discovery_when_no_explicit_path`: temp dir with one matching CSV; assert it is loaded without providing `explicit_path`.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m trade_hunter run --help   # confirm --tastytrade-file is optional, --downloads-dir present
```
