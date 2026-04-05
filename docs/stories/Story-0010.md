# Story-0010 — `run` Command Scaffold

**Status**: Completed  
**Phase**: 1 — CLI Skeleton & Configuration

---

## Goal

Replace the hello-world placeholder with the real `run` command entry point. The command accepts
all required input file paths and configurable filter thresholds. It loads `TRADIER_API_KEY` from
the environment and fails loudly if it is missing. When all inputs are valid it prints a dry-run
configuration summary and exits cleanly. No data processing happens yet — that begins in Phase 2.

---

## Background

The pipeline defined in `docs/PROJECT_INTENT.md` requires three input files, one output directory,
a Tradier API key, and several configurable filter thresholds. Establishing the full CLI surface
now means every subsequent story can read from `RunConfig` without revisiting the interface.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/config.py` | `RunConfig` dataclass holding all resolved runtime settings |

## Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/cli.py` | Replace `hello` command with `run` command |
| `apps/trade_hunter/pyproject.toml` | Add `python-dotenv>=1.0` dependency |
| `apps/trade_hunter/tests/test_smoke.py` | Update smoke test to call `run --help` |
| `apps/trade_hunter/tests/test_cli.py` | New file: unit tests for `run` command behaviour |

---

## CLI Interface

```
trade_hunter run [OPTIONS]
```

### Required options (no defaults — missing any fails the run)

| Option | Type | Description |
|---|---|---|
| `--tastytrade-file` | PATH | TastyTrade CSV download |
| `--bull-file` | PATH | SeekingAlpha BULL-ish Excel download |
| `--bear-file` | PATH | SeekingAlpha BEAR-ish Excel download |
| `--journal-file` | PATH | `journal.xlsx` containing active trades |
| `--output-dir` | PATH | Directory where `trade_signals.xlsx` will be written |

### Optional filter threshold options (with defaults from `PROJECT_INTENT.md`)

| Option | Default | Description |
|---|---|---|
| `--min-open-interest` | `8` | Minimum open interest hard filter |
| `--min-bid` | `0.55` | Minimum option bid hard filter |
| `--max-spread-pct` | `0.08` | Maximum spread % hard filter (`(ask-bid)/last`) |
| `--min-dte` | `30` | Minimum days-to-expiration for expiration selection |
| `--max-dte` | `60` | Maximum days-to-expiration for expiration selection |

### Environment variable

| Variable | Required | Description |
|---|---|---|
| `TRADIER_API_KEY` | Yes | Tradier API bearer token. Loaded from environment or `.env` file via `python-dotenv`. Fails with a clear error if absent. |

---

## `RunConfig` Dataclass

`config.py` defines a plain dataclass (no external dependencies beyond stdlib):

```python
@dataclass
class RunConfig:
    tastytrade_file: Path
    bull_file: Path
    bear_file: Path
    journal_file: Path
    output_dir: Path
    tradier_api_key: str
    min_open_interest: int = 8
    min_bid: float = 0.55
    max_spread_pct: float = 0.08
    min_dte: int = 30
    max_dte: int = 60
```

`cli.py` constructs a `RunConfig` from the resolved CLI args and env var, then passes it
downstream (to pipeline functions in later stories).

---

## Dry-Run Summary Output

After successfully constructing `RunConfig`, the command prints a summary table and exits 0.
Example (Rich-formatted):

```
trade_hunter run
─────────────────────────────────────────
  TastyTrade file   : /path/to/tastytrade.csv
  BULL-ish file     : /path/to/bull.xlsx
  BEAR-ish file     : /path/to/bear.xlsx
  Journal file      : /path/to/journal.xlsx
  Output directory  : /path/to/uploads/
  Tradier API key   : ****  (set)
─────────────────────────────────────────
  Min open interest : 8
  Min bid           : 0.55
  Max spread %      : 8.0%
  DTE window        : 30 – 60
─────────────────────────────────────────
Configuration loaded. Pipeline not yet implemented.
```

---

## Error Behaviour

| Condition | Behaviour |
|---|---|
| `TRADIER_API_KEY` not set | Print clear error message, exit code 1 |
| Required `--option` not provided | Typer prints usage error automatically, exit code 2 |

---

## Acceptance Criteria

1. `trade_hunter run --help` exits 0 and lists all options with their defaults.
2. Running `run` with all required options and `TRADIER_API_KEY` set prints the dry-run summary and exits 0.
3. Running `run` without `TRADIER_API_KEY` in the environment exits 1 with a clear error message.
4. `RunConfig` is importable from `trade_hunter.config` and its field defaults match the PROJECT_INTENT thresholds.
5. `uv run pytest` passes (smoke test + new unit tests).
6. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests

### `tests/test_smoke.py` (update)
- `test_help`: assert `trade_hunter run --help` exits 0 and contains `"Usage"`.

### `tests/test_cli.py` (new)
- `test_run_missing_api_key`: invoke `run` with all file args but no `TRADIER_API_KEY` in env; assert exit code 1.
- `test_run_dry_run_summary`: invoke `run` with all file args and `TRADIER_API_KEY` set; assert exit code 0 and summary output contains expected labels.

### `tests/test_config.py` (new)
- `test_runconfig_defaults`: instantiate `RunConfig` with required fields only and assert all threshold defaults match PROJECT_INTENT values.

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m trade_hunter run --help
```
