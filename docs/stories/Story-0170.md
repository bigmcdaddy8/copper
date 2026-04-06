# Story-0170 — Verbose Progress & Adaptive Throttling

**Status**: Completed  
**Phase**: 6 — Integration & Polish

---

## Goal

Make `trade_hunter` observable during the Tradier enrichment phase and eliminate the
unnecessarily conservative fixed-delay throttling.

Two problems are solved together because they share the same code path:

1. **Silence** — a run with ~170 candidates currently produces zero output for 7+ minutes
   while making ~500 Tradier API calls. There is no way to distinguish "working" from "hung."

2. **Over-throttling** — a fixed 0.5 s sleep after every call adds ~4 minutes of pure wait
   time regardless of remaining rate-limit headroom. The client already reads the
   `X-Ratelimit-Available` and `X-Ratelimit-Expiry` headers but only acts on them at ≤5
   remaining, leaving the fixed delay as the dominant cost.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/cli.py` | Add `--verbose` flag; pass to `run_pipeline` |
| `apps/trade_hunter/src/trade_hunter/config.py` | Add `verbose: bool = False` field to `RunConfig` |
| `apps/trade_hunter/src/trade_hunter/pipeline/runner.py` | Thread `verbose` into `enrich_candidates` calls |
| `apps/trade_hunter/src/trade_hunter/tradier/enrichment.py` | Accept `verbose` param; per-ticker progress, throttle-change notices, periodic throughput, end-of-side summary |
| `apps/trade_hunter/src/trade_hunter/tradier/client.py` | Replace fixed delay with adaptive throttling; expose rate-limit state for callers |
| `apps/trade_hunter/tests/test_tradier_client.py` | Tests for adaptive throttle logic |
| `apps/trade_hunter/tests/test_tradier_enrichment.py` | Tests for verbose output path |

---

## Detailed Design

### 1. `--verbose` CLI flag

Add to the `run` command:

```python
verbose: bool = typer.Option(False, "--verbose", help="Print per-ticker enrichment progress and rate-limit state")
```

Stored in `RunConfig.verbose` and threaded through `run_pipeline` → `enrich_candidates`.

### 2. Per-ticker progress line

When `verbose=True`, `enrich_candidates` prints one line per ticker before the API calls:

```
[BULL]  12/87 — enriching NVDA    (rate: 423 avail, resets in 47s | pace: 0.21s/call)
[BULL]  13/87 — enriching AAPL    (rate: 420 avail, resets in 46s | pace: 0.21s/call)
```

Format:
- `[{side}]` — padded to 6 chars
- `{n}/{total}` — right-aligned index, fixed width
- `— enriching {symbol}` — ticker padded to 8 chars
- `(rate: N avail, resets in Xs | pace: Y.YYs/call)` — from client's last-seen headers;
  `rate:` section omitted before first response; `pace:` shows the delay computed after the
  previous ticker's last API call

### 3. Throttle-change notice

When the computed inter-request delay changes by more than 50% relative to the previous
value, a standalone notice line is printed **before** the per-ticker line:

```
[throttle] pacing adjusted: 0.16s → 0.52s/call  (rate: 45 avail, resets in 38s)
```

This fires when available headroom shrinks (slowdown) or a window resets (speedup).
Tracked via a `_prev_delay` variable in the `enrich_candidates` loop.

### 4. Periodic throughput line

Every 30 wall-clock seconds during enrichment, a throughput line is printed:

```
[BULL] throughput: 28 API calls in 32s = 52.5 calls/min
```

`API calls` counts every Tradier request made (3 per successfully enriched ticker, fewer for
skipped tickers). Tracked via a `_api_call_count` counter incremented in the enrichment loop
and a `_last_report_time` timestamp.

### 5. End-of-side summary line

The existing complete line is extended with total throughput:

```
[BULL] complete — enriched 71/87, skipped 16  (213 API calls in 7m 12s = 29.4 calls/min)
```

### 6. Adaptive throttling in `TradierClient`

Replace the fixed `request_delay` / `time.sleep` with a `_compute_delay` method:

```
TARGET_UTILIZATION = 0.90   # stay at or below 90% of capacity
MIN_DELAY          = 0.05   # floor — always a small pause between calls
MAX_DELAY          = 2.00   # ceiling — never sleep longer than 2 s
DEFAULT_DELAY      = 0.20   # used before any rate-limit headers received
```

Algorithm (called after each response in `_get`):

```
if available is None:
    delay = DEFAULT_DELAY
else:
    remaining_seconds = max(1, (expiry_ms / 1000) - now)
    safe_calls        = available * TARGET_UTILIZATION
    delay             = remaining_seconds / max(safe_calls, 1)
    delay             = clamp(delay, MIN_DELAY, MAX_DELAY)
```

The hard-throttle at ≤5 remaining is retained as a safety backstop.
Remove the `request_delay` constructor parameter (it is no longer needed).

### 7. Rate-limit state accessor

Add a property to `TradierClient` so `enrich_candidates` can read state for verbose output
without coupling to private attributes:

```python
@property
def rate_limit_state(self) -> tuple[int | None, int | None]:
    """Return (available, expiry_ms) from the most recent response headers."""
    return self._ratelimit_available, self._ratelimit_expiry
```

### 8. API call counting

`enrich_candidates` increments a local counter after each successful Tradier call (not per
ticker — per individual HTTP request). This enables accurate calls/min reporting even when
tickers are skipped mid-way through their calls.

---

## Acceptance Criteria

1. `uv run trade_hunter run --help` shows `--verbose` with a description.
2. Without `--verbose`, output is identical to before (no new lines during enrichment).
3. With `--verbose`:
   a. Each ticker prints one progress line before its API calls, including pace.
   b. A throttle-change notice fires when delay shifts >50% from previous.
   c. A throughput line prints every ~30 seconds of wall-clock time.
   d. The end-of-side summary includes total API calls, elapsed time, and calls/min.
4. The `rate:` annotation is present when header data is available, absent before first response.
5. `TradierClient` no longer accepts or uses a `request_delay` constructor parameter.
6. `TradierClient._compute_delay` is unit-tested: covers `available=None`, low-available,
   normal mid-window, clamp-to-min, and clamp-to-max cases.
7. All existing tests continue to pass.
8. A live `--verbose` run clearly shows per-ticker progress, throttle changes, and throughput.

---

## Verification Steps

```bash
# Unit tests
uv run pytest

# Live smoke — verbose mode should print progress lines throughout enrichment
uv run trade_hunter run \
  --output-dir /tmp/trade_hunter_live/output \
  --verbose \
  2>&1 | tee /tmp/trade_hunter_verbose.log

# Confirm throttle notices and throughput lines appear in the log
grep -E "\[throttle\]|\[BULL\] throughput|\[BEAR\] throughput" /tmp/trade_hunter_verbose.log
```
