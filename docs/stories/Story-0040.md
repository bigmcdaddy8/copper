# Story-0040 — Active Trades Loader

**Status**: Completed  
**Phase**: 2 — Data Ingestion Layer

---

## Goal

Load the active trades journal (`journal.xlsx`, worksheet `daJournal`), extract the `Symbol`
column, deduplicate it, and return a set of active ticker symbols. This set is used downstream
for two purposes: open-trade exclusion (Story-0050) and diversity scoring (Stories-0110).

The file must be opened **read-only**. This program must never modify the journal under any
circumstances.

---

## Background

From `docs/PROJECT_INTENT.md`:

> Active trades are stored in `worksheets/journal.xlsx`, worksheet `daJournal`. For
> `trade_hunter`, only the `Symbol` column is required. If multiple rows exist for the same
> ticker, that ticker is still treated as one active underlying.

Unlike the dated TastyTrade and SeekingAlpha files, the journal has a fixed filename with no
date suffix. No glob-based discovery is needed — the file is resolved as
`worksheets_dir / "journal.xlsx"`, with both the directory and filename configurable via CLI.

> **Note:** The warning about active-trade tickers not present in the Universal Data Set (per
> PROJECT_INTENT.md) belongs in the pipeline join layer (Story-0050), not here. This loader
> is only responsible for reading and cleaning the symbol list.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/loaders/journal.py` | Load `daJournal` worksheet and return deduplicated symbol set |
| `apps/trade_hunter/tests/test_journal_loader.py` | Unit tests |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/config.py` | Add `worksheets_dir`; make `journal_file` optional (`Path \| None = None`) |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Add `--worksheets-dir`; make `--journal-file` optional |
| `apps/trade_hunter/tests/test_config.py` | Update for `RunConfig` signature change |
| `apps/trade_hunter/tests/test_cli.py` | Remove `--journal-file` from `DUMMY_ARGS` |

---

## Default Paths

| Constant | Value |
|---|---|
| `_DEFAULT_WORKSHEETS_DIR` | `/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/worksheets` |
| Default journal file | `_DEFAULT_WORKSHEETS_DIR / "journal.xlsx"` |

---

## Module Design

### `loaders/journal.py`

```python
WORKSHEET_NAME = "daJournal"

def load_journal(
    worksheets_dir: Path,
    explicit_path: Path | None = None,
) -> tuple[frozenset[str], list[str]]:
    """
    Load the daJournal worksheet and return a frozenset of deduplicated active symbols.

    If explicit_path is provided it is used directly; otherwise the file is resolved
    as worksheets_dir / "journal.xlsx".

    The file is opened read-only. No modifications are ever made to the source file.

    Raises:
        FileNotFoundError: if the resolved path does not exist.
        ValueError: if the 'Symbol' column is missing from the worksheet.
        ValueError: if the worksheet 'daJournal' does not exist in the workbook.
    """
```

**Read-only guarantee:** Use `openpyxl.load_workbook(path, read_only=True, data_only=True)` to
open the file, then hand the data to pandas. This makes the read-only intent explicit at the
library level, not just by convention.

**Return type:** `frozenset[str]` — immutable, prevents accidental downstream mutation, and
communicates that order is irrelevant.

### `RunConfig` changes

```python
@dataclass
class RunConfig:
    output_dir: Path                    # unchanged — still required
    tradier_api_key: str                # unchanged — still required
    downloads_dir: Path = ...           # unchanged
    worksheets_dir: Path = field(...)   # new — default _DEFAULT_WORKSHEETS_DIR
    tastytrade_file: Path | None = None # unchanged
    bull_file: Path | None = None       # unchanged
    bear_file: Path | None = None       # unchanged
    journal_file: Path | None = None    # was required, now optional
    ...
```

---

## Warning & Error Behaviour

| Condition | Behaviour |
|---|---|
| File not found | Raise `FileNotFoundError` — caller fails the run |
| Worksheet `daJournal` not found | Raise `ValueError` — caller fails the run |
| `Symbol` column missing | Raise `ValueError` — caller fails the run |
| Null/empty Symbol value | Append `"[Journal] Row with null/empty Symbol dropped"` to warnings; drop row |
| Zero symbols after cleaning | Append `"[Journal] No active trade symbols found after cleaning"` to warnings; return empty frozenset (not an error — an empty journal is valid) |

---

## Function Signature

```python
# loaders/journal.py
def load_journal(worksheets_dir: Path, explicit_path: Path | None = None) -> tuple[frozenset[str], list[str]]: ...
```

---

## Acceptance Criteria

1. `load_journal` opens the file using `openpyxl` with `read_only=True`.
2. `load_journal` raises `FileNotFoundError` when the resolved path does not exist.
3. `load_journal` raises `ValueError` when worksheet `daJournal` is not present.
4. `load_journal` raises `ValueError` when the `Symbol` column is missing.
5. Rows with null/empty Symbol are dropped with a warning.
6. Duplicate symbols are deduplicated — one ticker with multiple rows counts once.
7. The return type is `frozenset[str]`.
8. `--journal-file` is optional in `trade_hunter run --help`; `--worksheets-dir` appears with the correct default.
9. `uv run pytest` passes (all existing + new tests).
10. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests

### `tests/test_journal_loader.py`

- `test_load_file_not_found`: non-existent path raises `FileNotFoundError`.
- `test_load_missing_worksheet`: xlsx with no `daJournal` sheet raises `ValueError`.
- `test_load_missing_symbol_column`: `daJournal` sheet exists but has no `Symbol` column; raises `ValueError`.
- `test_load_null_symbol_dropped`: one null Symbol row is dropped; warning returned.
- `test_load_deduplication`: three rows with two unique symbols returns frozenset of size 2.
- `test_load_happy_path`: valid xlsx returns correct symbols, empty warnings.
- `test_load_returns_frozenset`: assert return type is `frozenset`.
- `test_load_uses_default_path`: explicit_path=None with file at `worksheets_dir/"journal.xlsx"` loads successfully.
- `test_load_empty_journal`: all Symbol values are null; returns empty frozenset with a warning.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m trade_hunter run --help   # confirm --journal-file optional, --worksheets-dir present
```
