# Story-0190 — Verbose Rejection Logging

**Status**: Completed  
**Phase**: 7 — Maintenance & Enhancements  
**Addresses**: Backlog-0070

---

## Goal

When `--verbose` is active, every ticker rejection — not just enrichment-stage skips — should print to the console in real time. Currently, filter-stage and candidate-stage rejections are captured in the run_log file only; the user has no visibility during execution.

The fix is wired at the `RunLog` level so no changes to `candidates.py` or `filters.py` are needed — they already call `run_log.warn()` for every rejection.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/output/run_log.py` | Add `verbose: bool = False` to `RunLog.__init__`; `warn()` also prints to stdout when `verbose=True` |
| `apps/trade_hunter/src/trade_hunter/pipeline/runner.py` | Pass `verbose=cfg.verbose` when instantiating `RunLog` |
| `apps/trade_hunter/tests/test_run_log.py` | Tests: `warn()` prints to stdout iff `verbose=True`; file output unaffected either way |

---

## Detailed Design

### `RunLog.__init__` change

```python
class RunLog:
    def __init__(self, verbose: bool = False) -> None:
        self._entries: list[str] = []
        self._verbose = verbose
```

### `RunLog.warn()` change

```python
def warn(self, message: str) -> None:
    entry = f"[WARN] {message}"
    self._entries.append(entry)
    if self._verbose:
        print(entry)
```

### `runner.py` change

```python
run_log = RunLog(verbose=cfg.verbose)
```

### Console output format

Matches existing enrichment verbose style. Examples:

```
[WARN] [BULL] 'GOOG' dropped — use GOOGL
[WARN] [BULL] 'TSLA' excluded — active open trade
[WARN] [BEAR] 'XYZ' not in Universal Data Set — skipped
[WARN] [BULL] 'ABC' filtered — open interest 5 < 10
[WARN] [BEAR] 'DEF' filtered — bid 0.30 < 0.55
```

---

## Acceptance Criteria

1. `--verbose` run prints every `run_log.warn()` entry to stdout at the moment it is logged.
2. Without `--verbose`, no new console output from these stages (behavior identical to before).
3. All rejection entries continue to appear in the run_log file regardless of the verbose flag.
4. `test_run_log.py` verifies both paths (verbose=True prints; verbose=False does not).

---

## Verification Steps

```bash
# Unit tests
uv run pytest apps/trade_hunter/tests/test_run_log.py -v

# Full test suite
uv run pytest apps/trade_hunter/tests/

# Live smoke — filter rejections should appear in terminal output
uv run trade_hunter run \
  --output-dir /tmp/th_out \
  --verbose \
  2>&1 | grep "\[WARN\]"
```
