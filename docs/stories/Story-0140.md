# Story-0140 — Per-Run Log File

**Status**: Completed  
**Phase**: 5 — Output

---

## Goal

Create a `RunLog` class that accumulates warning and informational messages throughout a
pipeline run and writes a timestamped log file to `output_dir`. The class is designed for
simple accumulation — pipeline stages that already return `list[str]` warnings (e.g.
`enrich_candidates`, `apply_hard_filters`) hand their lists to the caller, which feeds them
into the RunLog. Full CLI wiring is covered in Story-0150.

---

## Background

From `docs/PROJECT_INTENT.md`:

> The run log should include at minimum:
> - Missing required files
> - Input schema problems
> - Unknown sector values
> - Candidate tickers missing from the Universal Data Set
> - Open-trade tickers missing from the Universal Data Set
> - Tradier API failures or throttling events
> - Tickers skipped because no valid monthly cycle or no qualifying option was found
> - Summary counts for loaded, filtered, skipped, scored, and written records

Existing pipeline stages that return `list[str]` warnings (ready to feed in):

| Stage | Return type |
|---|---|
| `enrich_candidates()` | `(pd.DataFrame, list[str])` |
| `apply_hard_filters()` | `(pd.DataFrame, list[str])` |

Loader-level issues (unknown sectors, missing symbols) are currently logged via `warnings.warn`
in the existing code. Story-0140 does not change those call sites — that retrofit is deferred
to Story-0150.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/output/run_log.py` | `RunLog` class |
| `apps/trade_hunter/tests/test_run_log.py` | Unit tests |

No existing files are modified by this story.

---

## Design

### `RunLog` class

```python
# output/run_log.py

from datetime import datetime
from pathlib import Path


class RunLog:
    def __init__(self, run_start: datetime) -> None:
        """Create a RunLog for a run that started at run_start."""

    def warn(self, message: str) -> None:
        """Append a [WARN] entry."""

    def add_warnings(self, warnings: list[str]) -> None:
        """Append all items from an existing warnings list as [WARN] entries."""

    def info(self, message: str) -> None:
        """Append an [INFO] entry."""

    def write(self, output_dir: Path, summary: dict[str, int] | None = None) -> Path:
        """Write the log file to output_dir and return its path.

        Creates output_dir if it does not exist.
        File name: run_log_YYYYMMDD_HHMMSS.txt  (timestamp = run_start)
        """
```

### `add_warnings()` convenience method

Pipeline stages that return a `list[str]` can be drained with one call:

```python
enriched, warnings = enrich_candidates(...)
run_log.add_warnings(warnings)
```

### Log file format

```
trade_hunter run log — 2025-03-19 14:30:22
==================================================

[WARN] [BULL] 'SPY' — no qualifying monthly expiration found, skipped
[WARN] [BULL] 'AAPL' — Tradier API error (500), skipped
[INFO] Run date: 2025-03-19

--------------------------------------------------
Summary
--------------------------------------------------
Loaded (BULL):         45
Loaded (BEAR):         38
Active trades:          8
Filtered (hard):       12
Skipped (API/select):   3
Scored (BULL):         28
Scored (BEAR):         21
Written (BULL):        28
Written (BEAR):        21
```

Rules:

- Header line: `trade_hunter run log — YYYY-MM-DD HH:MM:SS`
- Followed by a `=` separator (50 chars) and a blank line
- Each entry on its own line, already prefixed with `[WARN]` or `[INFO]`
- If there are no entries, the section between the separator and the summary is empty
- Summary section: `--` separator (50 chars), `Summary` heading, `--` separator, then
  one line per key-value pair — key left-aligned, value right-aligned in a fixed-width
  field (column at position 25)
- If `summary` is `None` or empty, the summary section is omitted

### File naming

`run_log_{run_start.strftime("%Y%m%d_%H%M%S")}.txt`

Example: `run_log_20250319_143022.txt`

`run_start` is provided to the constructor — it is not captured internally — so tests can
pass a fixed datetime for deterministic filenames.

---

## Acceptance Criteria

1. `RunLog.warn("msg")` adds `"[WARN] msg"` to entries.
2. `RunLog.add_warnings(["a", "b"])` appends both as `[WARN]` entries.
3. `RunLog.info("msg")` adds `"[INFO] msg"` to entries.
4. `write()` creates the file at `output_dir / "run_log_YYYYMMDD_HHMMSS.txt"`.
5. `write()` creates `output_dir` if it does not exist.
6. The written file contains all accumulated entries.
7. The written file contains the summary section when `summary` is non-empty.
8. The summary section is omitted when `summary` is `None`.
9. An empty RunLog (no entries, no summary) still produces a valid file with just the header.
10. `uv run pytest` passes (all existing + new tests).
11. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_run_log.py`)

All tests write to `tmp_path` (pytest fixture) — no permanent files created.

- `test_runlog_creates_file`: write a RunLog; assert file exists at the expected path.
- `test_runlog_filename_format`: assert filename matches `run_log_YYYYMMDD_HHMMSS.txt`.
- `test_runlog_warn_in_file`: `warn("foo")`; assert `"[WARN] foo"` in file content.
- `test_runlog_info_in_file`: `info("bar")`; assert `"[INFO] bar"` in file content.
- `test_runlog_add_warnings`: `add_warnings(["x", "y"])`; assert both `[WARN]` lines present.
- `test_runlog_summary_in_file`: `write(..., summary={"Loaded (BULL)": 10})`; assert `"Loaded (BULL)"` in file.
- `test_runlog_summary_omitted_when_none`: `write(..., summary=None)`; assert `"Summary"` not in file.
- `test_runlog_empty_log_produces_file`: no entries, no summary; assert file exists with header line.
- `test_runlog_creates_output_dir`: non-existent subdir; assert created and file written.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
