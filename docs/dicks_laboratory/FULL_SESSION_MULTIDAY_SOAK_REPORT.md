# Phase 0W — Full-Session / Multi-Day Robby Soak & Capacity Study

**Status: OPEN — partially completed.** This document records real, measured
evidence for the stages actually run so far (0W-1, 0W-5). Stages 0W-2, 0W-3,
and 0W-4 require real elapsed market time (≈23 hours, a full session-close/
reopen boundary, and 2–3 trading days respectively) that could not fit inside
this interactive working session. **Phase 0W is not closed.** Exact commands
for Human to run the remaining stages on `robby` are provided in §AH.

**Date:** 2026-08-25 (soak), report written 2026-08-25
**Accepted baseline commit:** `b205eca` (Phase 0V — Resilient Long-Running Capture Foundation)
**Host:** `robby`

---

## A. Baseline

- Branch `master`, HEAD `b205eca`, clean, synced with `origin/master` — confirmed before starting.
- Governing documents read: `LONG_HORIZON_DATA_REPLAY_READINESS_AUDIT.md` (0U), `RESILIENT_LONG_RUNNING_CAPTURE.md` (0V). Their invariants (reconnect ≠ recovery, FINALIZED ≠ complete tape, scheduled maintenance ≠ KNOWN_GAP, no trades observed ≠ no market activity, source_order ≠ dataset_sequence, market-time cutoff ≠ feed-knowledge cutoff) are treated as binding throughout this report.
- Pre-soak baseline test run: 282/282 Laboratory tests, 8/8 K9 DXLink tests — confirmed passing before starting real capture.
- The retained real 0L dataset (`es_20260823T231601Z_997555.sqlite3`) and the 0T smoke-test PNGs were not touched (verified mtime/size unchanged throughout).

## B. Robby Environment

| Property | Value |
|---|---|
| OS | Ubuntu 25.10 (questing) |
| Python | 3.13.7 |
| CPU | Intel(R) Core(TM) i7-6500U @ 2.50GHz, 4 threads |
| RAM | 11 GiB (1.5 GiB free / 4.9 GiB available at soak start) |
| Filesystem (data dir) | ext4, `/dev/sda2`, 233G total, 113G available |
| Power | AC (Mains) |
| Network | Wi-Fi, connected |
| System clock | `System clock synchronized: yes`, `NTP service: active` (confirmed via `timedatectl status` immediately before the soak) |
| Suspend | `sleep-inactive-ac-type` already `nothing` (AC-idle-sleep disabled system-wide); soak additionally wrapped in `systemd-inhibit --what=sleep:idle` as a second guarantee |

## C. Exact Contract / Session Dates

- Instrument: `FUTURE:CME:ES:2026-09` (streamer symbol `/ESU26:XCME`) — the same exact contract used throughout 0L–0V. No contract rollover occurred or was needed during this soak.
- 0W-1 trading date: **2026-08-26** (session opened 2026-08-25 17:00 CT).
- Ordinary-schedule check: 2026-08-25/26 is an ordinary Tuesday/Wednesday CME equity-index session — no holiday/early-close exception applies.

---

## D. 0W-1 Active-Session Soak

**Command run:**
```bash
systemd-inhibit --what=sleep:idle --why="Dicks Laboratory 0W-1 soak test" \
  uv run python scripts/dicks_lab_collect_es.py --duration 2h --data-dir apps/dicks_laboratory/data/0w_soak
```
(Run in an isolated `0w_soak/` subdirectory to avoid colliding with an unrelated 2-minute test dataset already claiming today's trading date from 0V-A's own acceptance capture.)

- **Start:** 2026-08-25 17:48:26 CDT (2026-08-25 22:48:26 UTC)
- **End:** 2026-08-25 19:48:27 CDT (2026-08-26 00:48:27 UTC)
- **Wall-clock duration:** 2h00m00.5s (requested 2h)
- **Trading date:** 2026-08-26
- **Dataset:** `apps/dicks_laboratory/data/0w_soak/es_20260826_30960d24.sqlite3`
- **Dataset ID:** `30960d24-c597-4644-96df-133ceb50a260`
- **Final state:** `FINALIZED`
- **Collector commit recorded in closing summary:** `b205ecaa7f2d23aa4f414ca290087260b4d6b29f` (matches accepted 0V baseline exactly)

### Counts

| Metric | Value |
|---|---|
| Accepted NEW | 12,570 |
| CORRECTION | 0 |
| CANCEL | 0 |
| Rejected | 0 |
| Total source events | 12,570 (source_order 1..12,570, no gaps in the counter) |
| First source_order | 1 |
| Last source_order | 12,570 |
| Known gaps | 0 |
| Suspected gaps | 0 |
| Reconnect count | 0 |

First retained market timestamp: `2026-08-25T22:49:13.741Z` (18:49:13.741 CT). Last retained market timestamp: `2026-08-26T00:48:25.450Z` (19:48:25.450 CT). Unobserved pre-capture interval: ~49m13.7s (session opened 17:00 CT; first retained trade 17:49:13.741 CT) — a real, honestly-reported `DATASET_BEGINS_AFTER_ANCHOR` interval, not treated as zero activity.

## E. Connection Stability

Durable lifecycle evidence for the entire 2-hour run, in order:

```
CAPTURE_STARTED   2026-08-25T22:48:26.920237+00:00
SOURCE_CONNECTED  2026-08-25T22:48:27.579863+00:00
CAPTURE_STOPPED   2026-08-26T00:48:27.395327+00:00
```

**`SOURCE_CONNECTED = 1`, `SOURCE_DISCONNECTED = 0`, `SOURCE_RECONNECTED = 0`, `KNOWN_GAP = 0`.** This is exactly the target outcome the 0V-A correction was designed to produce: one continuous DXLink subscription for the full 2-hour span, with zero orchestration-driven or provider/network-driven reconnects. No real disconnect occurred during this run, so there is no real reconnect/backfill evidence to report from this stage (see §Y).

## F. Source-Event Counts

Already covered in §D. No CORRECTION/CANCEL/rejection events occurred in this 2-hour window — effective tape and canonical tape are therefore identical for this dataset (0 corrections applied, 0 cancels applied; not independently exercised as a divergence case here, since none occurred naturally — divergence behavior remains covered by the existing deterministic fixture tests from 0K6/0V).

## G. Source Metadata Availability

Sampled across all 12,570 accepted NEW rows (not a sub-sample — the full dataset):

| Field | Populated | Notes |
|---|---:|---|
| `bid_price` | 12,570 / 12,570 (100%) | Always present |
| `ask_price` | 12,570 / 12,570 (100%) | Always present |
| `aggressor_side` | 12,570 / 12,570 (100%) | BUY: 6,025 (47.9%), SELL: 6,545 (52.1%) |
| `exchange_code` | 12,570 / 12,570 (100%) | Always the single value `"G"` |
| `exchange_sale_conditions` | 0 / 12,570 (0%) | Always empty in practice for this contract/session |
| `spread_leg` | 12,570 / 12,570 field present, 0 `true` | Field always populated but always `False` — no spread-leg prints observed on the outright |
| `extended_trading_hours` | 12,570 / 12,570 field present, 0 `true` | Always `False` — the provider does not flag ordinary Globex hours as "extended" for this futures contract |
| `event_flags` | 12,570 / 12,570 (100%), always `0` | Confirms the 0U finding: always zero under our regular (non-time-series) subscription |
| `trade_through_exempt` | 12,570 / 12,570 present as empty string | Never a meaningful value observed — supports 0U's "low priority, likely not meaningful for CME futures" classification with real evidence rather than assumption |
| `valid_tick` | 12,570 / 12,570, always `True` | Expected — only `validTick == True` rows are ever accepted |

**Interpretation:** the provider populates `bidPrice`/`askPrice`/`aggressorSide`/`exchangeCode` reliably and usefully in practice; `exchangeSaleConditions`, `spreadLeg`, `extendedTradingHours`, and `tradeThroughExempt` carry no discriminating information for this real ES contract session — they are durably retained (per 0V's field-parity fix) but were, in this real sample, uniformly empty/false/zero. This is real evidence, not an assumption, and it directly answers 0U's open question about `tradeThroughExempt`: **always empty in practice; no evidence it carries CME-futures-relevant information.**

## H. CPU / Memory / Disk

Sampled via `ps` at four points during the 2-hour run (process could not be sampled after it exited, since the run completed cleanly and the OS process no longer exists):

| Elapsed | RSS (KB) | %CPU | Trades so far |
|---:|---:|---:|---:|
| ~1 min | 50,720 | 0.4% | — |
| ~33 min | 49,808 | 0.0% | 728 |
| ~64 min | 51,192 | 0.1% | 3,528 |
| ~95 min | 52,064 | 0.2% | 7,717 |

**RSS memory was flat (~50–52 MB) across the entire run — no observed growth trend.** CPU utilization was negligible throughout (well under 1% of one core), consistent with an I/O-bound, low-event-rate workload for this instrument. Disk file size grew smoothly and linearly with trade count (see §J).

## I. 0W-2 Full Trading-Date Capture

**Not completed in this session.** A full CME equity-index trading date spans ~23 hours (17:00 CT open to 16:00 CT close the next day), which cannot fit inside one interactive working session. See §AH for the exact command and instructions for Human to run this stage on `robby`.

## J. Full-Day Capacity Metrics (extrapolated from the 2-hour sample only)

**These are 2-hour-sample-based estimates, explicitly not a full-day measurement.** 0W-2 must supply the real full-day figures.

- Observed bytes/trade (this 2h dataset): 6,270,976 bytes / 12,570 trades = **498.9 bytes/accepted-trade** (durable SQLite file size ÷ trade count, including all schema overhead, indices, and full source-field parity for every row).
- Observed average rate: 12,570 / 7200.5s = **1.746 trades/second** average over this specific 2-hour window.
- **This average rate is a property of this specific 2-hour window (18:49–20:48 CT, Tuesday evening), not a claimed representative full-session or peak rate.** 0W-2's full trading date (spanning the RTH open, economic-release windows, and quiet overnight Globex hours) is expected to show a much wider range.

## K. Peak Event Rates

| Metric | Value |
|---|---|
| Peak 1-second accepted-NEW count | **360** trades in one second |
| Time of peak (UTC) | 2026-08-26T00:28:17Z |
| Time of peak (Chicago) | 2026-08-25 19:28:17 CDT |
| Peak 1-minute accepted-NEW count | 764 trades (2026-08-26T00:28 UTC / 19:28 CDT) |
| Second-highest 1-second count | 141 (00:28:18Z, immediately following the peak second) |

A real, sharp volume burst was captured intact — 360 trades landed in a single second with no evidence of write backlog, dropped events, or `source_order` discontinuity around that burst (the counter remained strictly sequential through it). This is meaningful real evidence that the current per-event SQLite write path comfortably absorbed at least this burst size.

## L. Corrections / Cancels / Rejections

Zero of each occurred in this 2-hour window (see §D/§F). No representative examples exist for this dataset. Effective-tape reconstruction was exercised trivially (canonical == effective, both 12,570 trades) — genuine correction/cancel divergence in a full real session remains untested by 0W-1 specifically, though it is already covered by deterministic fixture tests elsewhere in the suite (0K6/0V).

## M. SQLite Size / Growth

- Final file size: 6,270,976 bytes (~5.98 MiB) for 12,570 trades over 2 hours.
- Manifest sidecar: 438 bytes.
- Growth was smooth and monotonic; no anomalous jumps observed during the four resource samples.

## N. Audit Performance

`audit_dataset()` on the full 12,570-row dataset: **0.2008 seconds.**

## O. VWAP Performance

`analyze_anchored_vwap_dataset(SESSION_OPEN)`: **0.9092 seconds.** Selected trade count 12,570; effective VWAP `7682.340746149761019649495486`.

## P. Volume Profile / Value Area Performance

`analyze_volume_profile_dataset(SESSION_OPEN)`: **0.9675 seconds.** 67 occupied price levels; POC `7681.50`; VAL `7677.75`; VAH `7685.00`.

## Q. Developing-Series Performance

`build_developing_profile_series(SESSION_OPEN, 5m)`: **1.1240 seconds.** 25 snapshots produced (2h ÷ 5m + 1 terminal). Terminal snapshot exactly matches the static analysis above (VWAP `7682.340746149761019649495486`, POC `7681.50`, VAL `7677.75`, VAH `7685.00`) — confirming the cross-analysis-path consistency invariant holds under real full-scale data.

## R. Visualization Result

`dicks_lab_plot_developing_profile.py --interval 5m`: **2.236 seconds**, headless, PNG generated successfully. Visually legible at 25 checkpoints — no clutter observed at this scale (real ES price moved from ~7692 down to ~7682 over the 2 hours, a genuine declining-market sample). No 0T redesign needed at this scale; a much longer full-day series (0W-2, ~275 checkpoints at 5m) should be checked for legibility as future UI work if it becomes cluttered, not redesigned preemptively here.

## S. 0W-3 Session Rotation

**Not completed in this session** — requires spanning a real 16:00 CT session close, the 16:00–17:00 CT maintenance interval, and the 17:00 CT reopen, which did not occur during this session's real-time window. See §AH for the exact command for Human to run this stage. (Note: this exact mechanism — clean session close, maintenance wait with no dataset/no gap, fresh `SOURCE_CONNECTED` at reopen — was already proven with deterministic fake-time tests during the 0V-A correction; 0W-3's job is to confirm it holds under a *real* session boundary, not to re-derive the logic.)

## T. Maintenance-Interval Evidence

Not gathered in this session (see §S). No maintenance interval was crossed during the 2-hour active-session soak.

## U. 0W-4 Multi-Day Soak

**Not completed in this session** — requires 2–3 real trading days. See §AH.

## V. Daily Dataset Inventory

Only one dataset produced by 0W so far:

| Trading date | Dataset ID | File | State | Size | Accepted | Deferred | Rejected | Known gaps | Reconnects | Checksum |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---|
| 2026-08-26 | `30960d24-...` | `es_20260826_30960d24.sqlite3` | FINALIZED | 6,270,976 B | 12,570 | 0 | 0 | 0 | 0 | `45d14cc9cf5ae04c89dab87313ad3b86ec7c342ca899738c5705ff2ce9074437` (verified) |

`PRAGMA integrity_check` on this file: **`ok`.**

## W. Resource Stability Across Days

Not applicable yet (0W-4 not run). Within the single 2-hour run, RSS was flat (§H).

## X. Real Reconnect Evidence

**None occurred.** No real disconnect happened during the 2-hour soak — the network/provider connection was stable for the entire window. This is reported plainly as an absence of evidence, not as proof that reconnect logic is unnecessary; the 0V-A deterministic fake-time tests remain the actual proof of correct reconnect/gap-capping behavior. A future soak stage (0W-2 or 0W-4, spanning much longer real time) is more likely to eventually encounter a genuine disconnect and should report it fully per the original brief's instructions (§8/§9) rather than being treated as a failed run.

## Y. Reconnect-Backfill Observations

**Inconclusive — no real disconnect occurred, so this question could not be evidenced in 0W-1.** The 0U open question ("does a regular DXLink TimeAndSale subscription ever backfill/replay after reconnect?") remains unresolved by this soak stage. It should be re-examined the moment a real disconnect occurs in a future stage (0W-2/0W-4), by inspecting `source_index` continuity and event timestamps immediately around the reconnect.

## Z. SQLite Recommendation

**Continue SQLite.** No write-health issues, no locking errors, no slow commits observed; a real 360-events/second burst was absorbed cleanly with no evidence of backlog. This single 2-hour sample is not yet sufficient to make a full-day/multi-day capacity claim — 0W-2/0W-4 should re-confirm at larger scale — but there is no evidence against SQLite from this stage.

## AA. WAL Recommendation

**Keep current journal mode.** No concurrent-write contention was tested (0W-1 was a single writer, no simultaneous analysis attempted), and no measured issue points to needing WAL. See §41 (concurrent-analysis experiment) — not run in this session; recommended for 0W-2 continuation since a full-day dataset provides a more meaningful concurrent-read target.

## AB. Batching Recommendation

**No change indicated.** Per-event commit behavior handled the observed peak (360 events/second) without any observed backlog or slowdown. No batching redesign is recommended based on this evidence.

## AC. Quote Experiment

**Completed** — a 10-minute isolated experiment, run entirely separately from the accepted serious-collector contract (via a new throwaway diagnostic script, `scripts/dicks_lab_quote_rate_experiment.py`, which persists nothing to any Laboratory SQLite dataset).

**Command:**
```bash
uv run python scripts/dicks_lab_quote_rate_experiment.py --duration-seconds 600 --include-timesale
```

**Window:** 2026-08-25 19:56:09–20:06:09 CDT (10 minutes, immediately following the 0W-1 soak, same real market conditions).

| Metric | Quote | TimeAndSale (raw, for comparison) |
|---|---:|---:|
| Total events | 1,050 | 1,774 |
| Average rate (events/sec) | 1.749 | 2.955 |
| Peak 1-second count | 4 | 55 |
| Approx. raw JSON bytes/event | 142.4 | 450.0 |
| Approx. projected bytes/hour (raw JSON) | 896,322 (~0.90 MB/hr) | 4,786,378 (~4.79 MB/hr) |

**Important caveats:**
- These are **raw JSON payload sizes** measured directly from the DXLink wire event, *not* the durable SQLite schema footprint 0V actually uses for TimeAndSale (which measured ~499 bytes/accepted-trade in §J, including full field-parity schema overhead, indices, etc.). A future real Quote-persistence implementation's actual on-disk cost would need its own schema-level measurement — this experiment estimates *event rate and raw payload volume* only, deliberately not a persisted-schema projection, per the explicit isolation requirement.
- In this specific 10-minute, moderately-active window, Quote's average rate (1.75/s) was actually *lower* than the TimeAndSale raw event rate (2.96/s) — this is real, measured, sample-specific data, not a general claim that Quote updates less often than trades print; a longer/differently-timed sample could show otherwise.
- Quote's raw payload is smaller per-event (fewer fields) than TimeAndSale's.

## AD. Quote Retention Recommendation

**C — run a longer/broader Quote experiment before deciding**, leaning toward eventual (B) rather than (A) based on this sample:

- Event rate and raw payload volume in this sample (~0.90 MB/hr raw) is real but not dramatically larger than TimeAndSale's own raw volume (~4.79 MB/hr raw) — Quote would not obviously dominate storage.
- However, this is a single 10-minute sample from one moderately active evening window. A representative decision needs at least one quiet-period sample and one RTH-active sample, per the original brief's own suggested approach (§53), which this 0W pass only partially satisfies (one sample, not two).
- Future AI-tutor/order-flow usefulness of continuous BBO evolution (§AE below) is real but not yet weighed against a fuller cost picture.
- **Recommendation: gather the second (quiet-period) sample during a future soak stage before making a final (A) or (B) call.** Do not implement standalone Quote persistence in the interim.

## AE. Quote Replay Value (qualitative)

Beyond the trade-time `bidPrice`/`askPrice` already retained on every TimeAndSale row (§G), a standalone Quote stream would add: continuous BBO evolution *between* trades (not just at trade moments), spread evolution over time, and market-state context during quiet intervals with no prints at all. This remains a real potential value for a future AI tutor or order-flow study — not implemented or analyzed further here.

## AF. Storage Projection

Using only the 2-hour 0W-1 sample, linearly scaled to a 23-hour ordinary CME equity-index session (**explicitly an extrapolation, not a full-day measurement** — 0W-2 must supply the real figure):

| Horizon | Projected size (TimeAndSale-only, current schema) |
|---|---:|
| 1 trading day (23h, scaled) | ~72.1 MB |
| 20 trading days (~1 month) | ~1.44 GB |
| 60 trading days (~1 quarter) | ~4.33 GB |
| 250 trading days (~1 year) | ~18.0 GB |

These numbers assume the observed 2-hour rate holds uniformly across a full session, which real markets do not do (RTH open/close and news windows run hotter; overnight Globex hours run much quieter). **Treat these strictly as a rough order-of-magnitude placeholder pending 0W-2's real full-day measurement**, not a capacity commitment.

## AG. Issues Found / Fixes

**None found in 0W-1.** No collector crashes, no `source_order` duplication or gaps, no SQLite errors, no manifest/checksum mismatches, no unexpectedly slow analytics. `PRAGMA integrity_check` returned `ok`. Checksum tamper-detection was independently verified (a byte appended to a copy of the file correctly failed `verify_checksum`).

## AH. Recommended Next Actions — Exact Commands for Human

### 0W-2 — Full trading-date capture (~23 hours)

```bash
systemd-inhibit --what=sleep:idle --why="Dicks Laboratory 0W-2 full-day soak" \
  uv run python scripts/dicks_lab_collect_es.py --duration 24h --data-dir apps/dicks_laboratory/data/0w_soak
```
- Start this at or shortly after a session open (17:00 CT) for the cleanest full-day sample.
- `--duration 24h` is deliberately longer than one session (~23h) so the run naturally reaches the session's own scheduled close and finalizes there (per the 0V-A architecture, the session's own close bounds the run before the 24h Human deadline would).
- **Expected output/log:** stdout prints a JSON summary on completion (redirect to a file if running detached, e.g. `... > /tmp/0w2.log 2>&1 &`).
- **To stop cleanly early:** `Ctrl+C` — this is treated as a deliberate clean stop → `FINALIZED` with truthfully partial coverage, not `INTERRUPTED`.
- **What should appear:** one new `es_20260826_<id>.sqlite3` (or the then-current trading date) file plus its `.manifest.json` sidecar in `apps/dicks_laboratory/data/0w_soak/`.
- **What to send back:** the JSON summary, plus `sqlite3 <file> "SELECT * FROM dataset_closing_summaries;"` and `sqlite3 <file> "PRAGMA integrity_check;"` output.

### 0W-3 — Real rotation through maintenance

Simplest path: let the 0W-2 run above continue past its own session close — since `--duration 24h` exceeds one session, the architecture will (per 0V-A) wait through the 16:00–17:00 CT maintenance interval and open the next trading date's dataset automatically, within the same invocation. No separate command is needed if 0W-2 is run with a sufficiently long `--duration` (e.g. `26h`) to span the full rotation. **What to check afterward:** two dataset files (old trading date `FINALIZED`, new trading date `OPEN` or `FINALIZED` depending on when the run was stopped), and confirm zero `KNOWN_GAP` evidence was created during the maintenance window itself.

### 0W-4 — Multi-day unattended soak (2–3 trading days)

```bash
systemd-inhibit --what=sleep:idle --why="Dicks Laboratory 0W-4 multi-day soak" \
  uv run python scripts/dicks_lab_collect_es.py --duration 72h --data-dir apps/dicks_laboratory/data/0w_soak \
  > /tmp/0w4_soak.log 2>&1 &
disown
```
- Run detached (`disown`) so it survives the invoking shell session ending.
- **Verification during the run:** `ps aux | grep dicks_lab_collect_es`, `ls -la apps/dicks_laboratory/data/0w_soak/`, `tail -f /tmp/0w4_soak.log`.
- **What to send back when done:** the final JSON summary, a directory listing of `0w_soak/` (all dataset files + manifests), and `sqlite3 <each file> "SELECT * FROM dataset_closing_summaries;"`.

### 0W-5 — Second Quote sample (recommended before a final retention decision)

```bash
# Quiet-period sample (e.g. late evening/overnight Globex hours)
uv run python scripts/dicks_lab_quote_rate_experiment.py --duration-seconds 600 --include-timesale
```
Run once during a quiet period to compare against the moderately-active sample already gathered in this report (§AC).

---

## AI. Files Changed

- **Added:** `scripts/dicks_lab_quote_rate_experiment.py` (isolated diagnostic, does not touch the accepted serious-collector contract or persist to any Laboratory dataset).
- **Added:** `docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md` (this document).
- **No other production code changed.** 0W was measurement-only against the already-accepted 0V collector.
- **Runtime artifacts (not committed, gitignored):** `apps/dicks_laboratory/data/0w_soak/es_20260826_30960d24.sqlite3` + `.manifest.json`; a temporary visualization PNG and dataset copy were created under the session scratchpad and are not part of the repository.

## AJ. Validation

- Pre-soak baseline: `uv run pytest apps/dicks_laboratory/tests -q` → 282/282 passed. `uv run pytest apps/K9/tests/test_tastytrade_dxlink.py apps/K9/tests/test_tastytrade_dxlink_source.py -q` → 8/8 passed.
- Post-soak (no production code changed, so this simply reconfirms the same baseline): re-run at report-writing time, see final numbers in the handoff.
- `uv run ruff check scripts/dicks_lab_quote_rate_experiment.py` → clean.
- `git diff --check` → clean (only one new untracked file; no modified tracked files).

## AK. Git Status

Not committed, not pushed. Only `scripts/dicks_lab_quote_rate_experiment.py` and this report are new, untracked files. Runtime soak data remains under gitignored `apps/dicks_laboratory/data/0w_soak/`.

---

# ADDENDUM — 0W-2 Full-Trading-Date Attempts, 0W-2A Correction, 0W-3

**Appended 2026-08-31 (read-only forensic audit; no code changed, no commit).**
Phase 0W remains **OPEN**. This addendum preserves the history of the 0W-2 attempts
run on `robby` after the original 0W-1 report above. Nothing here is rewritten out.

## AL. 0W-2 Attempt 1 — INTERRUPTED (durability PASS, reconnect defect)

- **Collector commit:** `b205eca` (original Phase 0V foundation, pre-reconnect-fix).
- **Result:** ran ~**2h56m** of stable capture, then a single real DXLink disconnect.
  The reconnect path retried using the **collector/quote-token captured once at
  startup**; that token had already expired, so every retry failed authentication,
  the bounded retry budget was exhausted, and the dataset closed **INTERRUPTED**.
- **Durability:** PASS — all trades to that point were durable, `integrity_check ok`,
  a `KNOWN_GAP` was recorded, lifecycle evidence intact.
- **Defect:** reconnect reused stale credentials → could never recover from a real
  disconnect. This is the defect `a19af8c` was written to fix.

## AM. 0W-2A — Root Cause + Correction (5h10m PASS-A)

- **Root cause of Attempt 1:** a quote token obtained once at process start is only
  valid for a bounded lifetime; the reconnect path replayed it instead of asking
  Tastytrade for a fresh one.
- **Correction (commit `a19af8c`, "fix: refresh DXLink credentials on reconnect"):**
  every genuine reconnect now calls `refresh_collector()` →
  `client.get_api_quote_token()` (re-authenticating the underlying OAuth access
  token first if needed) and constructs a **fresh `DxLinkSourceCollector`** before
  retrying. A healthy connection is still never torn down proactively (0V-A).
  Disconnect evidence was also enriched (`attempt=N; stage=…; error=…`, credential-free).
- **Verification run:** ~**5h10m** clean capture, no disconnect encountered →
  **PASS-A** (correct *non-regression* of the always-on connection; did not itself
  exercise a real reconnect).

## AN. 0W-2 Attempt 2 — FAIL / INTERRUPTED (first real exercise of `a19af8c`)

Scheduled via `dicks-0w2-attempt2.timer` → `.service`
(`systemd-inhibit --what=sleep:idle … scripts/dicks_lab_collect_es.py --duration 94200
--data-dir apps/dicks_laboratory/data/0w2_attempt2`).

| Field | Value |
|---|---|
| Collector commit (closing summary) | `a19af8caeddaf3816a4305557aa21b52151360da` — matches HEAD ✓ |
| Service start | 2026-08-30 16:55:00 CDT (21:55:00 UTC) |
| Service exit | 2026-08-31 08:48:19 CDT (13:48:19 UTC), `code=exited status=1/FAILURE`, `Result=exit-code` |
| Service wall-clock | 15h 53m 19s |
| Planned end | ~2026-08-31 19:05 CT (94 200 s); planned session close 2026-08-31 16:00 CT |
| Exit vs. plan | **~7h12m before the Monday 16:00 CT session close** → full-trading-date objective not reachable |
| Dataset | `apps/dicks_laboratory/data/0w2_attempt2/es_20260831_c9ebc043.sqlite3` (107,008,000 B) |
| Dataset ID | `c9ebc043-beaa-4931-a5d6-29064f7a6e3c` |
| Instrument / trading date | `FUTURE:CME:ES:2026-09` / `2026-08-31` |
| Lifecycle state | **INTERRUPTED** |
| capture_started_at / capture_ended_at | 2026-08-30T22:00:00.000177Z / 2026-08-31T13:48:13.715015Z |
| First / last retained market ts | 2026-08-30T22:00:00.599Z / 2026-08-31T13:47:35.894Z |
| Accepted / deferred / rejected | 216,519 / 0 / 9 (all `INVALID_DXLINK_TICK`) |
| Known gaps / suspected gaps | 4 / 0 (total known-gap duration 21.07 s) |
| first / last source_order | 1 / 216,528 (9 unused ordinals = the 9 rejected ticks; 0 non-monotonic; continuous across every reconnect) |
| `PRAGMA integrity_check` | `ok` |
| Manifest / checksum sidecar | **ABSENT** (crash path bypassed `_build_result`); file SHA-256 computed for record: `cc8e92aec77809dacda80c1d788987d8defb99f758e9a18a2a2de34f232d3e37` |
| Mem peak / CPU (systemd) | 542.8 M RSS (20.8 M swap) / 5m 31s CPU over 15h53m |

### Lifecycle / reconnect evidence

```
CAPTURE_STARTED     2026-08-30T22:00:00.000177Z   (17:00:00.0 CDT)
SOURCE_CONNECTED    2026-08-30T22:00:00.614731Z   (17:00:00.6 CDT)
SOURCE_DISCONNECTED 2026-08-31T12:09:41.684176Z   attempt=1 stage=SOCKET_RECEIVE  (07:09:41.7 CDT)
SOURCE_RECONNECTED  2026-08-31T12:09:43.569919Z   gap 1.886 s                     (07:09:43.6 CDT)
SOURCE_DISCONNECTED 2026-08-31T13:30:24.212970Z   attempt=2 stage=SOCKET_RECEIVE  (08:30:24.2 CDT)
SOURCE_RECONNECTED  2026-08-31T13:30:27.242151Z   gap 3.029 s                     (08:30:27.2 CDT)
SOURCE_DISCONNECTED 2026-08-31T13:32:27.278439Z   attempt=3 stage=SOCKET_RECEIVE  (08:32:27.3 CDT)
SOURCE_RECONNECTED  2026-08-31T13:32:32.887785Z   gap 5.609 s                     (08:32:32.9 CDT)
SOURCE_DISCONNECTED 2026-08-31T13:35:33.303623Z   attempt=4 stage=SOCKET_RECEIVE  (08:35:33.3 CDT)
SOURCE_RECONNECTED  2026-08-31T13:35:43.846892Z   gap 10.543 s                    (08:35:43.8 CDT)
CAPTURE_STOPPED     2026-08-31T13:48:13.715015Z                                   (08:48:13.7 CDT)
```

Every `SOURCE_DISCONNECTED.detail` (credential-free):
`source_disconnected; attempt=N; stage=SOCKET_RECEIVE; error=DXLink connection error while receiving: sent 1011 (internal error) keepalive ping timeout; no close frame received`

### Live reconnect classification: **LIVE RECONNECT PASS (4 / 4 real disconnects recovered)**

All PASS criteria met for each of the 4 handled disconnects: `SOURCE_DISCONNECTED`
→ fresh-collector retry path → `SOURCE_RECONNECTED`, `KNOWN_GAP` retained, **same
`dataset_id`**, `source_order` strictly continuous across every boundary, no
duplicate-index redelivery. Time to first disconnect was **14h09m41s** of stable
capture — far longer than Attempt 1's 2h56m or 0W-2A's 5h10m.

**Fresh-token limitation (§K equivalent):** the reconnect code calls
`refresh_collector()` → `get_api_quote_token()` per retry, but the operational log
carries no per-reconnect line and there is **no runtime trace/metric that
independently proves `get_api_quote_token()` was invoked on each of the 4 retries**
or whether an OAuth access-token refresh was triggered. It is supported only by
(a) source code and (b) the circumstantial contrast that all 4 retries succeeded
whereas Attempt 1's stale-token retry failed immediately. No credential material
appears anywhere in the persisted evidence.

### Why the run still ended INTERRUPTED — new defect

A **5th** disconnect (~08:48 CDT) surfaced on the DXLink **KEEPALIVE send** path, not
the receive path. `DxLinkCollector._send()` passes `socket.send()` straight through
with no exception translation (unlike `_receive()`, which converts errors to
`DxLinkError`), so a `websockets.exceptions.ConnectionClosedError` raised there is
**not a `DxLinkError`** and escapes every `except DxLinkError` handler — including
the reconnect loop in `_run_one_trading_date_session`. It was caught only by the
generic `except Exception:` that finalizes the dataset INTERRUPTED and re-raises →
process exit 1. **The reconnect budget was not exhausted (4 of 5 attempts used).**

Two evidence-completeness consequences of exiting via that path:
1. **No `SOURCE_DISCONNECTED` / `KNOWN_GAP` for the terminal outage.**
   `known_gap_count = 4` undercounts the true gap-interval count by one; the ~30 s
   between the last retained trade (13:47:35.9Z) and `CAPTURE_STOPPED` (13:48:13.7Z)
   is unattributed.
2. **No manifest/checksum sidecar** — the crash path never reaches
   `_build_result()` → `compute_sha256()` / `write_manifest()`.

### Trigger for the terminal disconnect — client-side ingest backpressure

The final minute was the **busiest of the entire run**: peak 1-minute = **5,047**
accepted trades, peak 1-second = **1,690** (all bearing market ts `13:47:35`). Those
1,690 prints were *received* over ~24 s wall-clock (13:47:41.2Z → 13:48:05.8Z) —
i.e. the synchronous per-event SQLite write path fell ~30 s behind real time. That
starved the `websockets` client keepalive thread (log: `keepalive ping failed` /
`sync/connection.py:784 in keepalive`), the library closed the socket with 1011,
and the next `_send()` raised the uncaught `ConnectionClosedError`. No NetworkManager
connectivity flap coincides with this moment (nearest is 08:50:35, after the crash).

### Host network / power evidence (window 06:45–09:00 CDT)

- **Wi-Fi:** `NetworkManager state is now CONNECTED_SITE` → `CONNECTED_GLOBAL`
  transient "limited connectivity" flaps at 07:10, 07:25, 07:30, 08:05, 08:30,
  08:50, 08:55 CDT (~2–5 s each). The 07:10 and 08:30 flaps fall within ~1 min of
  `SOURCE_DISCONNECTED` #1 and #2.
- **PCIe:** continuous kernel `pcieport 0000:00:1c.4 … AER: Correctable … RxErr`
  every 1–2 min for the whole window. `00:1c.4` = PCIe Root Port #5, host of
  `02:00.0 Intel Wireless 7265` (the Wi-Fi NIC). Chronic correctable receiver
  errors on the Wi-Fi link.
- No `wpa_supplicant` deauth/disassoc, no carrier down/up, no driver reset logged.
- **Power/suspend: ABSENT** — no suspend/resume/hibernate/lid/sleep events; the
  `systemd-inhibit --what=sleep:idle` wrapper held; host stayed awake; no reboot.
- **Classification:** host-network evidence **PRESENT** for disconnects #1–#2
  (unstable uplink); **INCONCLUSIVE/ABSENT** for the fatal #5, which correlates with
  the ingest burst instead. NM connectivity checks are periodic, so absence at
  08:47 is not proof the RF link was clean then.

### Partial capacity metrics (PARTIAL — not full-day; do not extrapolate)

| Metric | Value |
|---|---|
| Captured market span | 15h 47m 35s (22:00:00.6Z → 13:47:35.9Z) |
| Accepted trades | 216,519 |
| Average accepted rate | ~3.81 trades/s over the captured span |
| Peak 1-second | 1,690 (final second, `13:47:35Z`) |
| Peak 1-minute | 5,047 (final minute) |
| File size | 107,008,000 B → ~494 bytes/accepted-trade (consistent with 0W-1's ~499) |
| Mem peak (RSS) | 542.8 MB (vs. ~50 MB flat in the 2h 0W-1 run — grew over 15h; not characterised further here) |
| CPU | 5m 31s over 15h53m (I/O-bound) |

### Analytics sanity (read-only, on a scratch copy)

- `audit_dataset()` runs clean; lifecycle/gap/rejection counts as above.
- Session-open anchored VWAP: **7697.9217** over 216,519 trades / 270,454 contracts;
  effective tape = canonical (0 corrections, 0 cancels). Artifact remains
  analytically usable.

## AO. 0W-3 — NOT REACHED / NOT TESTED

Attempt 2 exited at 08:48 CT Monday, well before the 16:00 CT session close. The
session-close → 16:00–17:00 maintenance → 17:00 reopen rotation was never reached.
This is **not** a rotation failure — the mechanism was simply never exercised by a
real boundary in this run (it remains covered by the 0V-A fake-time tests only).

## AP. Root-Cause Classification — MULTIPLE_CAUSES

- **Initial disconnects (#1–#4):** `HOST_NETWORK_FAILURE` (transient) — unstable
  Wi-Fi uplink (NM "limited connectivity" flaps + chronic PCIe RxErr on the 7265
  link) causing `websockets` keepalive PING/PONG timeouts → 1011 close.
  **All four recovered** by the `a19af8c` fresh-token reconnect path.
- **Fatal exit (#5):** two-part —
  (a) *Trigger:* `LOCAL_PROCESS` backpressure — the busiest market minute of the run
  (5,047 prints) drained through the synchronous per-event SQLite write path ~30 s
  behind real time, starving the keepalive thread → 1011 close.
  (b) *Why fatal not recovered:* `RECONNECT_IMPLEMENTATION_FAILURE` — a
  `ConnectionClosedError` from the KEEPALIVE **send** path is not translated to
  `DxLinkError`, so it bypasses the (otherwise working) reconnect loop and crashes
  the process. Reconnect budget was **not** exhausted.
- Initial feed-disconnect cause (host network) ≠ reason recovery failed (send-path
  exception-translation gap + write backpressure).

## AQ. Attempt 1 vs Attempt 2

| | Attempt 1 | Attempt 2 |
|---|---|---|
| Commit | `b205eca` | `a19af8c` |
| Reconnect design | stale startup collector/token replayed | fresh token + fresh collector per retry (+ enriched disconnect detail) |
| Stable time before 1st disconnect | ~2h56m | **14h09m41s** |
| Real disconnects | 1 | 5 |
| Recovered | 0 / 1 | **4 / 4** genuine live reconnects |
| Fatal mechanism | stale-token retry → auth fail → budget exhausted → INTERRUPTED | 5th disconnect on KEEPALIVE **send** → uncaught `ConnectionClosedError` → crash; reconnect never attempted; **budget not exhausted** |
| Data durability | PASS | PASS (2 evidence-completeness caveats: no terminal `KNOWN_GAP`, no manifest) |
| Dataset state | INTERRUPTED | INTERRUPTED |

**Net:** `a19af8c` is a demonstrated improvement — it recovered 4 consecutive real
disconnects the Attempt-1 architecture could not. A new, narrower defect (send-path
exception translation) plus a per-event-write throughput ceiling now bound the run.

## AR. Durability Classification — PASS (with two qualifications)

PASS basis: INTERRUPTED correctly recorded; 216,519 trades durable with full
provenance; `integrity_check ok`; `source_order` monotonic and fully accounted;
4 `KNOWN_GAP`s with intervals for the 4 handled disconnects; closing summary with
correct git commit; analytics run clean.
Qualification 1: terminal (5th) disconnect not recorded as `SOURCE_DISCONNECTED` /
`KNOWN_GAP`. Qualification 2: no manifest/checksum sidecar emitted.
Neither involves lost or corrupted trade data.

## AS. 0W-2 Attempt-2 Classification — FAIL / INTERRUPTED

Exited ~7h before the Monday 16:00 CT session close; cannot serve as full-trading-
date proof. Partial diagnostics above are retained as useful but explicitly partial.

## AT. Recommendation — narrow corrective slice ("0W-2B"), NOT implemented here

1. **Translate send-path failures** — wrap `DxLinkCollector._send()` so `websockets`
   connection errors raise `DxLinkError` (mirror `_receive()`), so a disconnect on
   the KEEPALIVE send is handled by the existing proven reconnect loop.
2. **Record the terminal disconnect** — set `disconnected_at` and emit
   `SOURCE_DISCONNECTED` + capped `KNOWN_GAP` on any connection-loss exception (not
   only `DxLinkError`), and still write the checksum/manifest sidecar for a
   crash-finalized INTERRUPTED dataset.
3. **Keepalive resilience under load** (larger; PO may defer) — move SQLite writes
   off the socket-reading thread, or service the WS PONG / app KEEPALIVE
   independently of per-event processing, so an inbound burst cannot starve it.

Product Owner to decide whether 0W-2B is warranted before re-attempting 0W-2.

## AU. Temporary systemd units

Not removed. All service/journal evidence for Attempt 2 is now captured, so after
PO accepts this addendum the following are **safe to remove**:
`dicks-0w2-attempt2.service`, `dicks-0w2-attempt2.timer`,
`dicks-0w2-attempt2-prearm-inhibit.service`, and the stale Attempt-1 pair
`dicks-0w2-soak.service` / `dicks-0w2-soak.timer` (timer still `active` but
`Trigger: n/a`, inert). Do **not** remove the runtime artifacts under
`apps/dicks_laboratory/data/0w2_attempt2/`.

## AV. Files changed / Git (as of the Attempt-2 audit)

At the time of the Attempt-2 audit only this file was edited. The 0W-2B
implementation section below records subsequent code changes (not committed).

---

# 0W-2B — Burst Throughput & Complete Disconnect Handling (implementation)

**Product Owner accepted the Attempt-2 findings and authorised the narrow 0W-2B
corrective slice.** Implemented on branch `master` (HEAD `a19af8c`), **not
committed, not pushed** — returned for Product Owner review. Phase 0W remains
OPEN. No full-session soak launched. No analytics code touched.

## BA. Three defects addressed

| | Defect | Fix |
|---|---|---|
| A | `DxLinkCollector._receive()` translates websocket connection failures to `DxLinkError`; `_send()` did not, so a `ConnectionClosedError` from a KEEPALIVE send bypassed the reconnect loop. | `_send()` now catches `websockets.exceptions.ConnectionClosed`, `OSError`, `TimeoutError` and re-raises `DxLinkError("...connection error while sending: ...")`. `TypeError`/`ValueError`/serialization errors still propagate raw — no programming error is disguised as a transport disconnect. `json.dumps` runs *before* the `try`. |
| B | A connection loss that surfaced outside `except DxLinkError` left no terminal `SOURCE_DISCONNECTED` and no `KNOWN_GAP`. | One common finalization block now runs for **every** exit path. A terminal exception that `_looks_like_connection_loss()` recognises (and that is not local backpressure/writer failure) gets a synthetic `SOURCE_DISCONNECTED` (`attempt=terminal`, sanitized stage/error) anchored at the last known-progress instant, and a `KNOWN_GAP` to `close_moment` — only when that interval is strictly positive (no fabricated zero-width gap). |
| C | Synchronous per-event SQLite persistence (2 fsync-bearing `commit()`s per accepted trade) on the DXLink feed-reader thread let the final-minute burst (5,047 prints; 1,690 in one second) fall ~30 s behind and starve the websocket keepalive. | A bounded-queue + single durable-writer-thread boundary (below). |

## BB. Chosen throughput architecture — and why it is the smallest safe change

```
DXLink RECEIVE loop (feed thread)        assigns source_order, O(1) bounded put
        ↓  queue.Queue(maxsize=N)         finite, ordered handoff
single DurableWriter thread              normalize + dedup + batch
        ↓  one transaction per batch      LaboratoryStore.transaction()
SQLite
```

New module `apps/dicks_laboratory/src/dicks_laboratory/durable_writer.py`.

- **`collect()` transport is unchanged.** It already calls an `on_event`
  callback per event; 0W-2B only changes what that callback does — from
  "normalize + several committing `store.save_*` calls" to a single
  `queue.put`. The feed thread returns to `recv()` (and to servicing the
  websocket keepalive) almost immediately.
- **Ordering is ingestion order, not completion order (§15/§16).** `source_order`
  is assigned on the feed thread at the canonical ingestion point and travels
  with each queue item. A single writer thread draining a FIFO queue preserves
  that order with no sort/merge. `dataset_sequence` is still assigned only to
  *accepted* observations by the normalizer — the two remain distinct.
- **Lifecycle markers ride the same queue.** `SOURCE_CONNECTED` /
  `SOURCE_RECONNECTED` / `SOURCE_DISCONNECTED` / `KNOWN_GAP` are emitted by the
  writer thread in the exact position they occurred relative to the trades
  around them (§19). A marker forces a flush of pending trades first.
- **Alternatives rejected:** a batching-only layer (no separate thread) still
  runs `normalize_dxlink_time_and_sales` + `execute()` for every event on the
  feed thread and gives no clean bounded-memory story; a full async/streaming
  platform is far more than this defect needs. The queue+writer is the minimal
  structure that satisfies the hard rule "the feed reader must not spend
  enough time on synchronous persistence that a burst starves the keepalive".
- `LaboratoryStore` gained `transaction()` (batches many `save_*` into one
  commit; per-call `commit()` suppressed while active; `rollback()` on error)
  and an opt-in `check_same_thread=False` used only on this path, with a strict
  hand-off discipline (feed thread reads resume state → `writer.start()` →
  feed thread never touches the store again → `writer.drain_and_stop()` joins →
  feed thread reclaims the store for finalize). No concurrent access.

## BC. Bounded memory — mandatory (§13/§14)

`WriterFlushPolicy(max_events=250, max_interval_seconds=0.1, queue_maxsize=50_000,
overload_grace_seconds=10.0)`.

- The queue is hard-bounded at `queue_maxsize`. `submit_event` does
  `queue.put(item, timeout=overload_grace_seconds)`; on `queue.Full` it raises
  **`CaptureBackpressureError`** — an explicit, truthful overload. Never
  drop-oldest / drop-newest / sample / skip-persistence / lossy-coalesce.
- On overload the run terminates **INTERRUPTED** with a truthful
  `CAPTURE_STOPPED` detail (`reason=writer_backpressure_overload;
  last_assigned_source_order=N; ... writer_overloaded=true`). `source_order`
  ends as a clean contiguous prefix (the ordinal is consumed only after a
  successful enqueue), so the shortfall is self-evident.
- **Measured (directional, §32):** a deliberately over-fast producer pushing
  300,000 events with `queue_maxsize=50,000` pinned the queue at exactly
  50,000, never above, and RSS went 29.6 MB → ~88 MB and **plateaued** — flat
  from the halfway mark through post-drain, i.e. it does not track events-sent.
  Peak growth ≈ one queue's worth of `DxLinkSourceEvent` objects (~1.1 KB
  each). glibc keeps the freed pages resident but they are reused, not stacked.

## BD. Buffer / batch durability semantics (§18)

An event in the queue or an un-flushed batch is **not durable** and is never
reported as such. `drain_and_stop()` (clean stop / session close / recoverable
disconnect handling / rotation) flushes and commits everything accepted, then
joins. On a process crash only committed rows count — the in-flight batch is
rolled back by `transaction()`; everything committed before it stays. The
manifest/checksum is now written for **every** cleanly-closed artifact —
FINALIZED, retry-exhaustion INTERRUPTED, and crash-finalized INTERRUPTED —
via the common finalization path (§9). If the manifest write itself fails
(§10), `manifest_error` is recorded on the result, the dataset stays
INTERRUPTED (never rewritten to FINALIZED), and the original exception still
propagates — verified by test.

## BE. Reconnect while backlogged (§19)

Trades enqueued before a disconnect are flushed in source order before the
`SOURCE_DISCONNECTED` marker is written; `SOURCE_RECONNECTED` + `KNOWN_GAP`
land after them; the reconnect continues `source_order` from where it left
off. Regression `test_send_path_disconnect_reconnects_and_continues_source_order`
drives a send-path `DxLinkError` through the full path and asserts
`source_order == [1,2,3]` across the boundary with `stage=SOCKET_SEND`.

## BF. Retry-budget semantics audit (§2 / **AE**)

**RETRY SEMANTICS: DEFECT CONFIRMED / CORRECTED.**

The Attempt-2 code incremented one `reconnect_count` on every `except
DxLinkError` for the whole trading-date session and never reset it. Four
disconnects spread across ~90 minutes — each *immediately* recovered — would
have walked that counter toward `max_attempts` regardless of the healthy time
between them. An ~80-minute healthy interval did **not** restore the budget.

Correction: two independent bounds on `ReconnectPolicy`.

- `max_attempts` (default 5) now bounds **consecutive failed reconnect
  attempts within one outage episode**. It resets to 0 the moment the source
  genuinely comes back (`on_connected` fires as a reconnect). A later,
  unrelated disconnect after a long healthy stretch gets a full fresh budget.
- `max_disconnect_episodes` (default 50) is the separate anti-flapping circuit
  breaker over the whole session — a connection that keeps dropping seconds
  after every reconnect still terminates INTERRUPTED
  (`reason=disconnect_episode_circuit_breaker`) instead of looping forever on a
  perpetually-reset per-episode budget. Set generously so a handful of
  spread-out real blips in a full session never trips it.

Disconnect detail now reads `attempt=<within-episode>; episode=<session-wide>`.
Regressions: `test_healthy_interval_resets_reconnect_budget` (two episodes,
each using 2 of 2 attempts, separated by a long healthy gap → still FINALIZED;
without the reset the cumulative 4 > 2 would INTERRUPT),
`test_connection_flapping_trips_episode_circuit_breaker` (proves termination,
no infinite loop). The real collector only fires `on_connected` after a full
connect+auth+subscribe, so a genuinely failing reconnect never resets the
budget — the scripted fake gained `connect_fails=True` to model that exactly.

## BG. SQLite / filesystem size-limit verification (§1 / **AD**)

**FILE-SIZE LIMIT: RULED OUT.**

On a forensic copy of `es_20260831_c9ebc043.sqlite3`:
`PRAGMA page_size` = 4096, `PRAGMA page_count` = 26125, `PRAGMA max_page_count`
= 4294967294, `PRAGMA freelist_count` = 0. `4096 × 26125 = 107,008,000` —
exactly the file size. The number is ordinary SQLite page alignment (26,125
whole pages), not a ceiling; `max_page_count` permits ~17.6 TB.

Host: ext4 on `/dev/sda2`, 233 G total, **114 G free** (49 % used) —
`findmnt` `rw,relatime`, no quota. systemd unit has no `Limit*` directives;
effective `LimitFSIZE=infinity`, `LimitAS=infinity`; shell `ulimit -f`
unlimited. The DB stopped growing because the process died mid-burst at
~08:48, not because anything capped it.

## BH. Hardware vs architecture (§3 / **AF**)

Current evidence category: **SOFTWARE / TRANSACTION / BACKPRESSURE LIMIT**
(now corrected) **+ NETWORK RELIABILITY ISSUE**. Not a raw-disk-throughput
limit, not a raw-network-bandwidth limit.

- Logical DB growth at the Attempt-2 peak: 1,690 trades/s × ~494 B/trade ≈
  **0.8 MB/s** — orders of magnitude below any SSD's sequential bandwidth. The
  bottleneck was ~2 fsync-bearing `commit()`s per event on the feed thread
  (~3,380 fsync/s attempted), i.e. **transaction/commit latency**, not bytes.
- The new batched writer sustained **~53,000 events/s** on this same machine
  in the §32 probe (300,000 events drained in 5.6 s) — ~31× the real
  Attempt-2 1-second peak. Hardware is not the constraint.
- The four Attempt-2 disconnects correlate with transient NetworkManager
  "limited connectivity" flaps and chronic PCIe correctable RxErr on the Wi-Fi
  NIC — **Wi-Fi reliability / transient connectivity**, distinct from Wi-Fi
  *bandwidth saturation* (a 0.8 MB/s feed does not saturate Wi-Fi). Wired
  Ethernet remains available later as a controlled A/B diagnostic; the
  environment was **not** changed as part of 0W-2B.

Recommendation: do **not** replace or upgrade hardware on the strength of a
synchronous-persistence bottleneck that has now been removed in software.

## BI. Operational observability added (§22 / §23)

- **Writer metrics** (operational, not canonical): `flush_count`,
  `batch_size_max`, `queue_depth_max`, `max_persist_lag_seconds`,
  `persisted_events`, `overloaded` — surfaced on `LongHorizonCaptureResult`,
  appended to the `CAPTURE_STOPPED` detail string, and printed in the
  collector script's JSON summary. Not logged per event.
- **Reconnect-auth evidence:** `run_long_horizon_capture` gained an
  `on_reconnect_attempt(attempt)` hook, called immediately before
  `refresh_collector()`. The collector script logs
  `reconnect: attempt=N refresh_collector_invoked=true` and, from
  `fresh_collector()`, `quote_token_requested=true fresh_dxlink_collector=true
  oauth_refreshed=<bool>` — the bool derived from a new safe
  `TastytradeClient.access_token_refresh_count` (a count, never the token,
  header, password, or account id).
- Healthy-connection rule preserved: credential refresh still happens only for
  a genuine reconnect; no periodic reconnects introduced.

## BJ. Test evidence

`uv run pytest apps/dicks_laboratory/tests apps/K9/tests -q` → **503 passed**
(was 479; +24 new). Full repo: see §BL. Ruff clean on all changed files.
`git diff --check` clean.

| Area | Tests |
|---|---|
| Send-path translation (§6/§7) | `apps/K9/tests/test_tastytrade_dxlink_send.py` — 4: `ConnectionClosed`→`DxLinkError`, `OSError`→`DxLinkError`, `TypeError` NOT translated, end-to-end KEEPALIVE-send failure in `collect()` surfaces as `DxLinkError`. |
| Ordering / `source_order` (§15/§16) | strict monotonic 1..N, `dataset_sequence` 1..N distinct. |
| Synthetic burst (§25) | 2,000 and 4,000 events "within one second" → no loss, no reorder, no duplication, queue bounded, `submit` of whole burst < 5 s (vs Attempt-2's ~24 s to drain 1,690). |
| Sustained throughput (§26) | 3,000 events paced → `flush_count > 5`, all persisted. |
| Backpressure saturation (§27) | gated slow writer, `queue_maxsize=8` → `CaptureBackpressureError` raised, `qsize` never > 8, contiguous prefix persisted after release, `overloaded=true`. |
| Backpressure integration | slow store through `run_long_horizon_capture` → INTERRUPTED, `writer_backpressure_overload` in `CAPTURE_STOPPED`, contiguous `source_order` prefix. |
| Memory bounded (§32/§33) | 60k-event over-fast producer → `queue_depth_max ≤ cap`, RSS plateaus (< 60 MB drift mid→end), nothing lost. |
| Buffered ≠ durable (§18) | events invisible until `drain_and_stop()`. |
| Rejections / deferred / duplicates (§20/§21) | every ordinal 1..6 consumed exactly once across accept/defer/reject; `DUPLICATE_SOURCE_INDEX_ACROSS_RECONNECT` still rejected-not-dropped. |
| Send failure → reconnect (§28) | send-path `DxLinkError` → reconnect, same dataset, `source_order` continues, `stage=SOCKET_SEND`. |
| Terminal unexpected exception (§29) | INTERRUPTED + `CAPTURE_STOPPED` + closing summary + manifest + checksum verifies + `integrity_check ok`; original `RuntimeError` propagates; NO fabricated `SOURCE_DISCONNECTED`. |
| Terminal connection loss (§8/B) | raw non-`DxLinkError` ws loss → synthetic `SOURCE_DISCONNECTED` (`attempt=terminal`) + `KNOWN_GAP` + manifest; original error propagates. |
| Manifest failure (§10) | `write_manifest` raises → state stays INTERRUPTED, `manifest_error` set, `checksum_sha256=None`, closing summary intact, no `.manifest.json`. |
| Retry-budget reset (§2/AE) | healthy interval restores full per-episode budget; flapping trips the episode circuit breaker (terminates, no loop). |
| Retry exhaustion (§30) | one episode, every reconnect connect-fails → INTERRUPTED after `max_attempts`, `reconnect_retry_budget_exhausted`; also with `refresh_collector` (bounded, no infinite retry). |
| Session rotation (§31) | existing rotation regressions still pass — writer drains at the FINALIZED boundary, fresh `SOURCE_CONNECTED` next date, no maintenance-interval `KNOWN_GAP`. |
| Reconnect-auth hook (§23) | `on_reconnect_attempt` fires per retry with the within-episode attempt number, in order. |
| Writer metrics (§22) | present on the result and in `CAPTURE_STOPPED` detail. |

## BK. Files changed (0W-2B, uncommitted)

- **Added** `apps/dicks_laboratory/src/dicks_laboratory/durable_writer.py`
- **Added** `apps/dicks_laboratory/tests/test_durable_writer.py`
- **Added** `apps/K9/tests/test_tastytrade_dxlink_send.py`
- **Modified** `apps/K9/src/K9/tastytrade/dxlink.py` — `_send()` translation
- **Modified** `apps/K9/src/K9/tastytrade/client.py` — `access_token_refresh_count`
- **Modified** `apps/dicks_laboratory/src/dicks_laboratory/store.py` —
  `transaction()`, `_maybe_commit()`, `check_same_thread`
- **Modified** `apps/dicks_laboratory/src/dicks_laboratory/long_running_capture.py` —
  durable-writer wiring, common finalization, terminal-disconnect evidence,
  manifest-on-abnormal, two-bound reconnect policy, `on_reconnect_attempt`,
  writer metrics on the result
- **Modified** `apps/dicks_laboratory/tests/test_long_running_capture.py` —
  `connect_fails` fake support, updated 2 exhaustion tests, 9 new 0W-2B tests
- **Modified** `scripts/dicks_lab_collect_es.py` — reconnect-auth logging,
  writer metrics in summary, `CaptureBackpressureError`/`CaptureWriterError`
  handled with a clean nonzero exit
- **Modified** this report — this 0W-2B section

No analytics/VWAP/volume-profile/value-area/session code touched. No commit,
no push.

## BL. Validation

- `uv run pytest apps/dicks_laboratory/tests apps/K9/tests -q` → 503 passed.
- Full `uv run pytest -q` → **1160 passed** (was 1136; +24 new 0W-2B tests), 0 failures.
- Ruff clean on every changed file (`ruff check <changed .py>` → All checks
  passed). Pre-existing lint debt in unrelated files
  (`engine/order.py`, `market_calendar.py`, `holodeck_sim.py`, …) left as-is.
- `git diff --check` → clean.

## BM. Recommended real verification (do NOT start without Product Owner sign-off)

```
synthetic burst / capacity tests   ← DONE (this slice)
        ↓
short real 4–6 hour capture on robby   ← recommended next, PO-authorised
        ↓
Product Owner architecture review
        ↓
fresh full-session 0W-2 Attempt 3
```

Do not arm another ~26-hour run. Inspect the architecture first.

---

# 0W-2B1 — Real Writer Verification + 0W-3 Live Session Rotation Proof

**Appended 2026-08-31 (read-only post-run audit; no code changed, no restart, no
commit, no push).** Phase 0W remains **OPEN**. This section records the real
6-hour verification of the 0W-2B hardened collector (bounded queue + dedicated
durable writer + batched SQLite + send-path disconnect translation + corrected
retry semantics) and the opportunistic live futures-session rotation that fell
inside its window. Nothing above is rewritten.

## BN. Run setup

- **Collector commit:** `6cba2296ae206c367178872ae15a4e9fc2c01406` (HEAD of
  `master`; recorded identically in both dataset closing summaries and manifests).
- **Unit:** `dicks-0w2b1-verify.service` (user scope, `Type=simple`,
  `Restart=no`), wrapping
  `systemd-inhibit --what=sleep:idle … uv run python scripts/dicks_lab_collect_es.py
  --duration 21600s --data-dir apps/dicks_laboratory/data/0w2b1_verification`.
- `StandardOutput`/`StandardError` → `…/0w2b1_verification/0w2b1_verify_20260831.log`.
- **Host:** `robby`. System clock synchronized, NTP active (confirmed at audit
  time: `Mon 2026-08-31 20:42 CDT` / `01:42 UTC`).

## BO. Service result

| Field | Value |
|---|---|
| Started | 2026-08-31 14:32:54 CDT (19:32:54 UTC) |
| Exited | 2026-08-31 20:32:56 CDT (01:32:56 UTC, 2026-09-01) |
| Wall-clock runtime | 6h 00m 02s |
| Exit | `ExecMainCode=0`, `ExecMainStatus=0`, `Result=success`, `SubState=dead` |
| CPU time | 1 min 18.947 s over 6 h (I/O-bound) |
| Peak memory | 379.4 MB |
| Peak swap | 6.7 MB |
| Process at audit | none (`ps -ef | grep '[d]icks_lab_collect_es'` empty) |

(`systemctl show` reported `MemoryPeak=[not set]` etc. because the unit's cgroup
was already released; the authoritative figures are the systemd
`"Consumed 1min 18.947s CPU time, 379.4M memory peak, 6.7M memory swap peak"`
journal line at stop.)

**Classification: COMPLETED SUCCESSFULLY.** Ran the full bounded 21 600 s, closed
both datasets cleanly, exited 0.

## BP. Artifact inventory

`apps/dicks_laboratory/data/0w2b1_verification/`:

| File | Size | mtime | Manifest |
|---|---:|---|---|
| `es_20260831_befb7b0e.sqlite3` (Dataset A) | 68 MB | 2026-08-31 16:00 | `…​.manifest.json` (438 B) present |
| `es_20260901_bb8cce1f.sqlite3` (Dataset B) | 11 MB | 2026-08-31 20:32 | `…​.manifest.json` (438 B) present |
| `0w2b1_verify_20260831.log` | 1.2 KB | 2026-08-31 20:32 | — |

The operational log carries the startup banner, one `fresh_collector:
quote_token_requested=true fresh_dxlink_collector=true oauth_refreshed=false`
line (emitted when Dataset B's collector was built at rotation), and the single
JSON summary the CLI prints for its final dataset (Dataset B). Dataset A's
finalization is fully recorded in its own SQLite lifecycle rows — the CLI wrapper
only summarizes the last dataset of a rotation by design, not a logging defect.
The journal retains only the two systemd framing lines (no app stdout goes to the
journal on this unit).

## BQ. Dataset A — trading date 2026-08-31

| Field | Value |
|---|---|
| File | `es_20260831_befb7b0e.sqlite3` |
| `dataset_id` | `befb7b0e-9a69-4001-ac2b-90405e0c28ed` |
| Instrument | `FUTURE:CME:ES:2026-09` |
| `lifecycle_state` | **FINALIZED** |
| `capture_started_at` | 2026-08-31T19:32:55.472Z (14:32:55.5 CDT) |
| `capture_ended_at` | 2026-08-31T21:00:00.435Z (**16:00:00.4 CDT**) |
| `collector_git_commit` | `6cba2296…` ✓ |
| accepted / deferred / rejected | **141 963 / 0 / 0** |
| known gaps / suspected gaps | 0 / 0 |
| reconnect_count | 0 |
| first / last source_order | 1 / 141 963 |
| Lifecycle events | `CAPTURE_STARTED` 19:32:55.472Z → `SOURCE_CONNECTED` 19:32:56.096Z → `CAPTURE_STOPPED` 21:00:00.435Z |
| `SOURCE_DISCONNECTED` / `SOURCE_RECONNECTED` / `KNOWN_GAP` / extra `CAPTURE_STOPPED` | none |
| Market-ts span | 19:32:56.575Z → 20:59:59.515Z |
| Effective span | 87 min 05 s → avg 27.2 accepted/s |
| Peak ingestion | ~5 258 events in one wall-clock second (received_at 19:59:59Z); peak market-ts second 5 718; peak market-ts minute 47 001 (19:59Z burst, ~27 min into the run) |
| VWAP (all trades) | 7700.11 on 275 465 contracts; px 7689.75–7708.25 |
| `PRAGMA integrity_check` | `ok` |
| Manifest | `state=FINALIZED`, `closed_at` 2026-08-31T21:00:00.435Z, `sha256 ca92dab0…` |
| File SHA-256 recomputed | `ca92dab0c386a6e7785130cdf90afbfb505f693180f120b7276d1d2433d4fdfa` — **matches manifest** ✓ |
| Closing-summary reconciliation | `accepted_trade_count=141963` == live `COUNT(trade_observations)=141963`; first/last source_order match — **no discrepancy** |
| Trade actions | 141 963 `NEW`; 0 `CORRECTION`, 0 `CANCEL` |
| source_order integrity | count 141 963, distinct 141 963, min 1, max 141 963 → fully contiguous 1..N; 0 non-monotonic; 0 duplicates; `dataset_sequence` == `source_order` for every row |

### Dataset A writer metrics (from `CAPTURE_STOPPED` detail)

| Metric | Value |
|---|---:|
| `writer_persisted_events` | 141 963 (== accepted) |
| `writer_flush_count` | 8 786 |
| `writer_batch_size_max` | 250 (the configured `max_events` cap) |
| `writer_queue_depth_max` | **3 522** of 50 000 (7 %) |
| `writer_max_persist_lag_seconds` | **1.475** |
| `writer_overloaded` | **false** |

The 19:59Z burst (≈5 258 events in one wall-clock second — over 3× the
1 690-events/s burst that crashed Attempt 2) drove the queue to only 7 % of its
bound and peak enqueue→persist lag to 1.475 s, well under the 10 s overload
grace. No keepalive starvation, no disconnect, no overload.

## BR. 0W-3 first half — Dataset A closed at the genuine scheduled session close

`segment_deadline = min(overall_deadline, session_close)` =
`min(2026-08-31 20:32:54 CDT, 2026-08-31 16:00:00 CDT)` = **16:00:00 CDT**.
Dataset A's `CAPTURE_STOPPED` / `capture_ended_at` is
2026-08-31T21:00:00.435Z = **2026-08-31 16:00:00.4 CDT**, i.e. the ES Globex
scheduled session close for trading date 2026-08-31, not the Human 6-hour
deadline (which was still ~4½ h away) and not a manual stop. State = FINALIZED.

### Writer drain at the 16:00 boundary

`writer_persisted_events` (141 963) == `accepted_trade_count` (141 963) ==
live row count. The final minute of the tape was calm (206 events in 20:59Z),
the writer flushed its pending batch and joined, and only then was the dataset
finalized, checksummed and manifested (`closed_at` == `CAPTURE_STOPPED` ==
`capture_ended_at`, all 21:00:00.435Z). `writer_overloaded=false`. No evidence
of buffered-event loss at the boundary.

## BS. 0W-3 middle — 16:00–17:00 CDT maintenance interval

Window 2026-08-31T21:00:00.435Z → 2026-08-31T22:00:00.000Z (16:00:00.4 →
17:00:00.0 CDT):

- **No dataset open** — Dataset A already FINALIZED at 21:00:00.435Z; Dataset B's
  first row (`CAPTURE_STARTED`) is 22:00:00.000Z. No third SQLite file exists.
- **No fabricated `SOURCE_DISCONNECTED`** — neither dataset carries one, anywhere.
- **No fabricated `SOURCE_RECONNECTED`** — none in either dataset.
- **No `KNOWN_GAP`** created for the closed-market hour — `known_gap_count = 0`
  in both datasets; no `dataset_quality_events` rows in the interval.

Result: scheduled maintenance wait only, exactly as designed.

## BT. Dataset B — trading date 2026-09-01

| Field | Value |
|---|---|
| File | `es_20260901_bb8cce1f.sqlite3` |
| `dataset_id` | `bb8cce1f-5c8c-478f-81c9-1ce1b4ef2de5` (**≠ Dataset A**) |
| `parent_dataset_id` | NULL (independent dataset, own source_order sequence) |
| Instrument | `FUTURE:CME:ES:2026-09` |
| `lifecycle_state` | **FINALIZED** |
| `capture_started_at` | 2026-08-31T22:00:00.000Z (**17:00:00.0 CDT**) |
| `capture_ended_at` | 2026-09-01T01:32:56.149Z (**20:32:56.1 CDT**) |
| `collector_git_commit` | `6cba2296…` ✓ |
| accepted / deferred / rejected | **21 905 / 0 / 0** |
| known gaps / suspected gaps | 0 / 0 |
| reconnect_count | 0 |
| first / last source_order | 1 / 21 905 |
| Lifecycle events | `CAPTURE_STARTED` 22:00:00.000Z → `SOURCE_CONNECTED` 22:00:00.856Z → `CAPTURE_STOPPED` 2026-09-01T01:32:56.149Z |
| `SOURCE_DISCONNECTED` / `SOURCE_RECONNECTED` / `KNOWN_GAP` | none |
| Market-ts span | 22:00:00.826Z → 2026-09-01T01:32:55.847Z |
| Effective span | 3 h 32 min 56 s → avg 1.71 accepted/s (overnight Globex, expected low) |
| Peak rate | peak market-ts second 185; peak market-ts minute 804 |
| VWAP (all trades) | 7703.29 on 25 575 contracts; px 7698.00–7708.00 |
| `PRAGMA integrity_check` | `ok` |
| Manifest | `state=FINALIZED`, `closed_at` 2026-09-01T01:32:56.149Z, `sha256 92e95813…` |
| File SHA-256 recomputed | `92e958135d5e3bb6f8cacbdb5346bcef627a56d7ba40c98de3c6a1533643dc43` — **matches manifest and the CLI summary `checksum_sha256`** ✓ |
| Closing-summary reconciliation | `accepted_trade_count=21905` == live `COUNT=21905`; first/last source_order match — **no discrepancy** |
| Trade actions | 21 905 `NEW`; 0 `CORRECTION`, 0 `CANCEL` |
| source_order integrity | count 21 905, distinct 21 905, min 1, max 21 905 → contiguous 1..N; 0 non-monotonic; 0 duplicates; `dataset_sequence` == `source_order` every row |

### Dataset B writer metrics

| Metric | Value |
|---|---:|
| `writer_persisted_events` | 21 905 (== accepted) |
| `writer_flush_count` | 5 104 |
| `writer_batch_size_max` | 97 |
| `writer_queue_depth_max` | 45 |
| `writer_max_persist_lag_seconds` | 0.152 |
| `writer_overloaded` | false |

## BU. 0W-3 second half — Dataset B opened at the 17:00 reopen with a fresh SOURCE_CONNECTED

Dataset B's first lifecycle row is `SOURCE_CONNECTED` (evidence_type
**`SOURCE_CONNECTED`, not `SOURCE_RECONNECTED`**) at 2026-08-31T22:00:00.856Z =
**17:00:00.9 CDT**, 0.86 s after `CAPTURE_STARTED`. New `dataset_id`, new
`trading_date` 2026-09-01, own `source_order` sequence from 1, `parent_dataset_id`
NULL. This is a new-trading-date connection, not a recovery from an outage.

## BV. Dataset B bounded completion

The 6-hour Human deadline (14:32:54 CDT + 21 600 s ≈ 20:32:54 CDT) bounded
Dataset B before the 2026-09-01 session close. Dataset B drained its writer
(`persisted_events` 21 905 == accepted), was finalized FINALIZED at
20:32:56.1 CDT (~2 s of drain past the deadline), wrote its closing summary,
manifest and checksum, and the service then exited status 0. A partial
trading-date dataset FINALIZED here is correct — the experiment deliberately
stopped.

## BW. 0W-3 LIVE ROTATION classification

```
0W-3 LIVE ROTATION: PASS
```

All PASS criteria met:

- Dataset A FINALIZED at the scheduled 16:00 CDT session close (not the Human
  deadline, not a manual stop).
- 16:00–17:00 CDT maintenance: no active dataset, no false `KNOWN_GAP`, no false
  `SOURCE_DISCONNECTED` / `SOURCE_RECONNECTED`.
- Dataset B opened after maintenance at 17:00 CDT.
- Dataset B has a new `dataset_id`, `trading_date` 2026-09-01, and a fresh
  `SOURCE_CONNECTED` (not `SOURCE_RECONNECTED`).

This closes 0W-3 (the live rotation mechanism) even though Dataset A is only a
partial trading-date capture. It does **not** close the full-day 0W-2 objective.

## BX. Natural disconnect / reconnect

Neither dataset experienced a real disconnect (`reconnect_count = 0`, no
`SOURCE_DISCONNECTED` / `SOURCE_RECONNECTED` events, `writer_overloaded=false`).

```
LIVE RECONNECT: NOT EXERCISED IN 0W-2B1
```

This does not undo Attempt 2's previously accepted **LIVE RECONNECT PASS — 4/4**.
The corrected retry semantics (per-episode `attempt`, session-wide `episode`,
send-path translation) were therefore not exercised against a real outage in this
run — they remain covered by the 0W-2B regression suite only. The rotation did
exercise the `fresh_collector()` credential path once (`quote_token_requested=true
fresh_dxlink_collector=true oauth_refreshed=false` — a scheduled new-session
connect, no OAuth refresh needed).

## BY. Anti-flapping fuse

Total disconnect episodes: **0** — far below `max_disconnect_episodes = 50`. Not
tuned.

## BZ. Backpressure / overload

No `CaptureBackpressureError`, no `CaptureWriterError`, no
`writer_backpressure_overload`, no `writer_overloaded=true`, no queue-saturation
evidence in either dataset, the operational log, or the journal.
`writer_queue_depth_max` peaked at 3 522 / 50 000 (Dataset A) and 45 / 50 000
(Dataset B). Queue/batch parameters unchanged.

## CA. Writer capacity classification

```
WRITER CAPACITY: COMFORTABLE
```

- Dataset A: 141 963 events / 87 min (avg 27/s) with a >5 000-events/s ingestion
  burst → queue 7 % full, max persist lag 1.475 s, 0 overload.
- Dataset B: trivial load → queue depth 45, lag 0.152 s.
- Persistence kept up on both. **The exact burst class that crashed Attempt 2
  (~1 690 events/s → ~30 s lag → keepalive starvation → crash) was absorbed here
  at ~3× the rate with 1.475 s lag and no incident.**

### Lag comparison (labeled — not like-for-like)

| Measurement | Value | What it is |
|---|---:|---|
| Attempt 2 (old synchronous path) | ~30 s | feed-thread processing fell behind real time during the terminal burst |
| Initial 0W-2B1 short sample | ~104 ms | brief end-to-end sample, light load |
| **This run — Dataset A** | **1.475 s** | max writer enqueue→persist lag high-water mark, under a >5 000-events/s burst |
| **This run — Dataset B** | **0.152 s** | same metric, light overnight load |

## CB. Memory classification

```
MEMORY: BOUNDED / HEALTHY  (flagged for watch on the full-day run)
```

Peak RSS 379.4 MB, peak swap 6.7 MB, CPU 78.9 s over 6 h, clean exit 0. No
growth signature (queue never exceeded 7 % of its 50 000 bound; lag stayed
< 1.5 s; process exited normally). Directional comparison:

| Run | Peak RSS | Swap |
|---|---:|---:|
| 0W-1 (old architecture, 2 h) | ~50 MB | — |
| Attempt 2 (old architecture, 15h53m, crashed) | 542.8 MB | 20.8 MB |
| 0W-2B synthetic saturation | ~88 MB | — |
| **0W-2B1 (this run, 6 h)** | **379.4 MB** | **6.7 MB** |

Below the known-bad Attempt 2, but ~4× the synthetic-saturation baseline. Swap
negligible and no runaway, so HEALTHY — but RSS trajectory should be sampled
during 0W-2 Attempt 3 rather than assumed flat.

## CC. Source-order integrity

| | Dataset A | Dataset B |
|---|---:|---:|
| min source_order | 1 | 1 |
| max source_order | 141 963 | 21 905 |
| row / accounting count | 141 963 | 21 905 |
| distinct source_order | 141 963 | 21 905 |
| non-monotonic violations | 0 | 0 |
| unused ordinals (deferred/rejected) | 0 | 0 |

Contiguous 1..N in each dataset, no holes, no duplicates, no reset within a
dataset. Dataset B legitimately starts its own sequence at 1.
`dataset_sequence == source_order` for every row in both (no deferrals/rejections
to separate them here).

## CD. Rejections / corrections / cancels

Both datasets: `NEW` only — 0 `CORRECTION`, 0 `CANCEL`, 0 rejected, 0 deferred.
No reason distribution to report. Effective tape == canonical tape for both.

## CE. SQLite integrity / manifest / checksums

| Dataset | `integrity_check` | Manifest present | Manifest `state` | Checksum matches recompute |
|---|---|---|---|---|
| A `es_20260831_befb7b0e` | `ok` | yes | FINALIZED | yes (`ca92dab0…`) |
| B `es_20260901_bb8cce1f` | `ok` | yes | FINALIZED | yes (`92e95813…`) |

No file was regenerated or overwritten during the audit.

## CF. Analytics sanity (read-only)

- **Dataset A:** session-open anchoring is **PARTIAL** by construction — capture
  began 14:32 CDT, ~87 min before the 16:00 close, so it covers only the tail of
  trading date 2026-08-31. All-trade VWAP 7700.11 over 275 465 contracts; monotone
  tape; audit-level counts reconcile. Coverage truthfully partial.
- **Dataset B:** capture began exactly at the 17:00 CDT session open, so
  session-open VWAP has full anchor coverage for the captured interval
  (17:00–20:32 CDT). All-trade VWAP 7703.29 over 25 575 contracts; monotone tape;
  counts reconcile.

## CG. 0W-2B1 classification

```
0W-2B1: PASS
```

- Real capture operated through the full intended 6 h window (both segments).
- Writer never overloaded (`writer_overloaded=false` both; queue ≤ 7 % of bound).
- Memory bounded (379 MB peak, 6.7 MB swap, no growth signature, clean exit 0).
- Source ordering / accounting correct (contiguous 1..N, 0 non-monotonic, 0
  duplicates, `persisted == accepted`, `dataset_sequence == source_order`).
- Datasets integrity-clean (`integrity_check ok` both).
- Manifests / checksums valid (both SHA-256 recompute-match).
- No new transport or persistence defect observed.

A natural handled reconnect was not required (Attempt 2 already established live
reconnect 4/4) and did not occur.

## CH. Full-day 0W-2 status

```
0W-2 FULL TRADING-DATE CAPTURE: STILL OUTSTANDING
```

Dataset A (~87 min tail of 2026-08-31) and Dataset B (~3 h 33 min of 2026-09-01)
are both deliberately partial. This 6-hour test cannot close the full trading-date
objective.

## CI. Temporary service cleanup

All service, journal, and runtime-artifact evidence for `dicks-0w2b1-verify.service`
has been captured in this section. The journal retains only the two systemd
framing lines; every authoritative lifecycle record lives in the two SQLite files
plus their manifests plus the operational log, all on disk and independent of the
unit. **`dicks-0w2b1-verify.service` is safe to remove** after Product Owner
review (`systemctl --user disable --now dicks-0w2b1-verify.service`, remove the
unit file, `systemctl --user daemon-reload`). Do **not** delete the runtime
artifacts under `apps/dicks_laboratory/data/0w2b1_verification/`. Not removed by
this audit.

## CJ. Recommendation

0W-2B1 PASS + 0W-3 PASS. The hardened collector ran a real multi-hour capture,
absorbed a >5 000-events/s burst (the Attempt-2 failure class) with 1.475 s lag
and no overload, and demonstrated the full live session-rotation lifecycle
(scheduled close → clean FINALIZED + manifest/checksum → maintenance with no
false gap → fresh next-trading-date dataset with `SOURCE_CONNECTED`).

**Recommended next step: prepare 0W-2 Attempt 3** as the full-session proof
(start at/just after a 17:00 CT open; `--duration` long enough to reach the
following 16:00 CT close, e.g. `26h`; dedicated data dir). **Do not arm it in
this audit.** One watch item for Attempt 3: sample the collector RSS trajectory
periodically (peak here was 379 MB vs 88 MB synthetic) — no defect, but confirm
it plateaus over a full day rather than assuming it.

No new defect was found, so no corrective slice precedes Attempt 3.

## CK. Files changed / Git (0W-2B1 audit)

- **Modified:** this file (`docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md`)
  — this 0W-2B1 / 0W-3 section only.
- No source, test, or config changes. No collector restart. No commit, no push.
- `git status --short`: `docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md`
  and `scripts/dicks_lab_quote_rate_experiment.py` untracked (pre-existing).
- `git diff --check`: clean.
- Branch `master`, HEAD `6cba2296ae206c367178872ae15a4e9fc2c01406`, tracked tree
  clean vs HEAD.

---

# 0W-2 Attempt 3 — ARMED (full trading-date proof)

**Appended 2026-08-31 ~21:00 CDT.** Product Owner accepted and closed 0W-2B1 and
0W-3; 0W-2 (full trading-date capture) remains **OPEN**. Attempt 3 is armed to
capture one complete ordinary ES trading date end to end. Not yet run. No source
commit (accepted collector `6cba2296` is already committed/pushed).

## CL. Objective

Capture `FUTURE:CME:ES:2026-09`, `trading_date = 2026-09-02`, continuously from
the real 17:00 CT session open (Tue 2026-09-01) through the real 16:00 CT session
close (Wed 2026-09-02), FINALIZED, with `KNOWN_GAP = 0` and `SUSPECTED_GAP = 0`.
A run that merely survives the day is **not** sufficient — any real `KNOWN_GAP`
means the endurance/lifecycle behaviour may still PASS but the *pristine full-day
dataset* criterion does not.

## CM. 0W-2B1 temporary service cleanup — DONE

`dicks-0w2b1-verify.service` stopped, disabled, unit file removed,
`systemctl --user daemon-reload` run. Runtime artifacts under
`apps/dicks_laboratory/data/0w2b1_verification/` **retained** (both SQLite files
+ manifests + operational log, byte-for-byte).

## CN. Session-model confirmation

`ES_GLOBEX` (`sessions.py`): open 17:00 CT, close 16:00 CT, "ordinary CME
schedule only; holiday and early-close overrides are not modeled."
`classify_es_session` for Tue 2026-09-01 17:00 CT → `IN_SESSION`,
`trading_date = 2026-09-02`; Wed 2026-09-02 is weekday 2 (not Fri/Sat/Sun).
Real-calendar check: Sep 1–2 2026 are Tue/Wed; US Labor Day 2026 is Mon Sep 7 —
no market holiday in the window. Ordinary open trading date confirmed.

## CO. Armed configuration (operational, outside Git)

| Unit | Role | State |
|---|---|---|
| `dicks-0w2-attempt3.timer` | one-shot launch `OnCalendar=2026-09-01 16:55:00` (local CT), `Persistent=false`, `AccuracySec=1s` | enabled + active; **NEXT = Tue 2026-09-01 16:55:00 CDT** |
| `dicks-0w2-attempt3.service` | `Type=simple`, `Restart=no`, `KillSignal=SIGINT`, `TimeoutStopSec=180`, `MemoryAccounting=yes`; `ExecStart=systemd-inhibit --what=sleep:idle uv run python scripts/dicks_lab_collect_es.py --duration 83700 --data-dir apps/dicks_laboratory/data/0w2_attempt3` | inactive (timer-triggered; no `[Install]`) |
| `dicks-0w2-attempt3-prearm-inhibit.service` | `systemd-inhibit --what=sleep:idle sleep 86400` — bridges arming→launch | active (block inhibitor present) |
| `dicks-0w2-attempt3-memsample.timer` | `OnCalendar=*-*-* *:00/15:00` (~15 min), `Persistent=false` | enabled + active |
| `dicks-0w2-attempt3-memsample.service` | `Type=oneshot` → `mem_sample.sh`, one CSV row/append | oneshot |

`systemd-analyze --user verify` on all five units: clean (no warnings).

`--duration 83700` (= 23 h 15 m; the parser accepts bare seconds and `<n>s`
only — `23h15m` is **not** a valid token). Launch 16:55 CT Tue → collector waits
~5 min for the 17:00 open → captures → Dataset A closes at the 16:00 CT Wed
session boundary (`segment_deadline = min(overall_deadline 16:10 CT Wed,
session_close 16:00 CT Wed)`), FINALIZES, then the supervisor idles in the
maintenance window until the 16:10 CT overall deadline and returns Dataset A
**without opening the next trading date** (verified against the
`run_long_horizon_capture` loop: after a scheduled FINALIZE it only continues if
`now < overall_deadline` *and* a new trading date resolves — here the deadline is
reached first). Service then exits 0.

## CP. Runtime directory

`apps/dicks_laboratory/data/0w2_attempt3/` (gitignored):
`preflight_credentials.py`, `mem_sample.sh`, `mem_samples.csv` (baseline row
written), and — after launch — `0w2_attempt3_20260901.log` and
`es_20260902_<id>.sqlite3` (+ `.manifest.json`).

## CQ. Credential preflight — PASS

`uv run python apps/dicks_laboratory/data/0w2_attempt3/preflight_credentials.py`
(non-interactive, prints only booleans/lengths):
`tastytrade_client_constructed=true`, `list_futures` → 529 items, `/ESU6`
resolves and `streamer-symbol == /ESU26:XCME`, fresh quote token obtained
(len 103), DXLink `wss://` URL obtained, no OAuth refresh needed.
`PREFLIGHT_RESULT=PASS`. No token/credential value printed or stored.

## CR. Provenance

Branch `master`; HEAD == `origin/master` == `6cba2296ae206c367178872ae15a4e9fc2c01406`;
tracked tree clean vs HEAD (`git status --short` shows only the two pre-existing
untracked files). Attempt-3 closing summary must record
`collector_git_commit = 6cba2296ae206c367178872ae15a4e9fc2c01406`.

## CS. Host / power / space

Host `robby`; clock synchronized, NTP active; time at arming ~Mon 2026-08-31
21:00 CDT. AC online (`ADP1/online = 1`). `linger = yes` (services survive with
no login session). GNOME `sleep-inactive-ac-type = nothing` (no AC idle-suspend);
our `sleep:idle` inhibitors cover idle + programmatic sleep. **Residual
dependency: `HandleLidSwitch` is at the logind default (`suspend`) and is *not*
inhibited — the laptop lid must stay physically OPEN for the full run.** Data
filesystem `/dev/sda2`: 113 GB free (49 % used) — ample for an expected
~150–250 MB full-day dataset.

## CT. Expected timeline

| Instant (CT) | Event |
|---|---|
| Tue 2026-09-01 16:55:00 | `dicks-0w2-attempt3.timer` fires → service starts → collector waits for open |
| Tue 2026-09-01 17:00 | `CAPTURE_STARTED` + fresh `SOURCE_CONNECTED`, `trading_date 2026-09-02` |
| Wed 2026-09-02 ~08:30 | U.S. cash-equity / RTH open in America/Chicago (the accepted `_CASH_OPEN = time(8, 30)` CT anchor; 09:30 ET). Treat ~08:25–08:45 CT as an especially interesting activity/capacity window, alongside any empirically observed peak-event windows. |
| Wed 2026-09-02 16:00:00 | scheduled session close → writer drain → Dataset A `FINALIZED` + manifest + checksum |
| Wed 2026-09-02 ~16:10 | overall deadline reached in the maintenance wait → supervisor returns → service exits 0 |

## CU. Human operator commands (no Claude / terminal / desktop needed after arming)

```bash
# timer state
systemctl --user list-timers --all | grep -E 'UNIT|attempt3'
# main service state / result
systemctl --user status dicks-0w2-attempt3.service
# live log
tail -f ~/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt3/0w2_attempt3_20260901.log
# memory-sampler trace
tail -f ~/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt3/mem_samples.csv
# CANCEL before launch (Tue < 16:55 CT)
systemctl --user disable --now dicks-0w2-attempt3.timer
systemctl --user stop dicks-0w2-attempt3-prearm-inhibit.service
# CLEAN STOP while running (SIGINT → deliberate clean stop → FINALIZED, truthfully partial)
systemctl --user stop dicks-0w2-attempt3.service
```

## CV. Post-run

When the Human returns after ~Wed 16:10 CT, a **separate audit** performs the
full capacity analysis (lifecycle/gaps/reconnects; NEW/CORRECTION/CANCEL/reject
counts; source-order accounting; DB size + bytes/event + bytes/accepted-trade;
writer metrics; peak event rates; memory trajectory from `mem_samples.csv`;
integrity/manifest/checksum; dataset audit; session-open VWAP; volume
profile/POC/value area; developing 5m series; terminal-vs-static reconciliation;
full-session visualization; analytics runtimes; and 20/60/250-trading-date storage
projections **only if Attempt 3 produced a clean full-day dataset**). That audit
also removes the four temporary `dicks-0w2-attempt3*` units (artifacts retained).

---

# ADDENDUM — 0W-2 Attempt 3 Post-Run Audit (full trading-date proof, trading_date 2026-09-02)

**Audit run:** 2026-09-02 ~20:33 CT on `robby`, ~4h20m after the service exited.
**Collector under test:** committed `6cba2296ae206c367178872ae15a4e9fc2c01406` (HEAD == origin/master, tracked tree clean; only the two pre-existing untracked files present).
**Result in one line:** **0W-2 ATTEMPT 3 — ENDURANCE PASS / DATA COMPLETENESS FAIL.** The collector captured the 2026-09-02 ES trading date from the actual 17:00 CT session open (SOURCE_CONNECTED +0.6 s) through the actual 16:00 CT session close (last retained trade 15:59:59.983 CT), survived 23 h, kept the writer comfortable, produced a valid FINALIZED SQLite dataset + matching manifest/checksum, and fully accounted for every source ordinal — **but the tape contains one real `KNOWN_GAP` of 1.795 s** (2026-09-01 21:00:25.134–21:00:26.929 CT) caused by an auth-token expiry, auto-recovered in 1.8 s. Per §10 gap-acceptance, any `KNOWN_GAP > 0` fails the *complete-trading-date* bar even though collector resilience passes (1/1 recovery).

## DA. Actual host time

`date` → Wed 2026-09-02 20:33:59 CDT; `timedatectl` → UTC Thu 2026-09-03 01:33:59; System clock synchronized: yes; NTP service: active.

## DB. Repository baseline

Branch `master`; HEAD `6cba2296ae206c367178872ae15a4e9fc2c01406`; `git status --short` shows only `?? docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md` and `?? scripts/dicks_lab_quote_rate_experiment.py`. Collector tracked source clean vs HEAD. `git diff --check` clean.

## DC. Timer result

`dicks-0w2-attempt3.timer` fired once at **Tue 2026-09-01 16:55:00 CDT** (matches plan). No timer failure. Timer now `inactive (dead)`, Duration 1d 19h 9min.

## DD. Service result

| Field | Value |
|---|---|
| ExecMainStartTimestamp | Tue 2026-09-01 16:55:00 CDT |
| ExecMainExitTimestamp | Wed 2026-09-02 16:10:01 CDT |
| Wall-clock runtime | 23 h 15 min 01 s (`--duration 83700`) |
| Exit code | 0 (`ExecMainStatus=0`, `ExecMainCode=1`=CLD_EXITED) |
| Result | `success` |
| CPU (`CPUUsageNSec`) | 466,110,288,000 ns ≈ 7 min 46 s (≈0.56 % of wall) |
| Mem peak (`MemoryPeak`) | 2,207,784,960 B ≈ 2,105 MiB ≈ 2.21 GB |
| Swap peak (`MemorySwapPeak`) | 0 |
| Process alive now? | No (`ps -ef | grep '[d]icks_lab_collect_es'` → none) |

**Classification: COMPLETED SUCCESSFULLY.** The dataset closed at the real 16:00 CT session boundary (`capture_ended_at = 2026-09-02T21:00:00.4Z`, SQLite mtime 16:00); the process then idled through the maintenance window and systemd exited 0 at 16:10 CT on its configured duration — not a manual stop, not a crash, not the Human deadline, not `systemctl stop`.

## DE. Artifact inventory

`apps/dicks_laboratory/data/0w2_attempt3/`:

| File | Size | Note |
|---|---|---|
| `es_20260902_9c76e79c.sqlite3` | 449 MiB (470,568,960 B) | the one canonical trading-date dataset |
| `es_20260902_9c76e79c.sqlite3.manifest.json` | 438 B | FINALIZED manifest |
| `0w2_attempt3_20260901.log` | 1.3 KB | operational log incl. closing-summary JSON |
| `mem_samples.csv` | 17 KB | 15-min memory sampler trace (still appending; benign) |
| `mem_sample.sh`, `preflight_credentials.py` | — | scaffolding |

**No 2026-09-03 dataset** — as predicted, the run ended inside the 16:00–17:00 CT maintenance interval before the next open.

## DF. Dataset identity

| Field | Value |
|---|---|
| path | `apps/dicks_laboratory/data/0w2_attempt3/es_20260902_9c76e79c.sqlite3` |
| dataset_id | `9c76e79c-f4dd-45c7-acb9-d9890dc20671` |
| parent_dataset_id | (none) |
| instrument | `FUTURE:CME:ES:2026-09` (root ES, CME, 2026-09) |
| trading_date | `2026-09-02` |
| lifecycle_state | `FINALIZED` |
| capture_started_at | `2026-09-01T22:00:00.000239Z` = 2026-09-01 17:00:00.000 CT |
| capture_ended_at | `2026-09-02T21:00:00.425526Z` = 2026-09-02 16:00:00.426 CT |
| collector_git_commit | `6cba2296ae206c367178872ae15a4e9fc2c01406` ✅ matches |
| collector_version | `phase-0v-serious-collection-v1` |
| file size | 470,568,960 B |

No identity mismatch.

## DG. Trading-date boundary proof

| Marker | UTC | America/Chicago |
|---|---|---|
| CAPTURE_STARTED | 2026-09-01T22:00:00.000Z | 2026-09-01 17:00:00.000 |
| SOURCE_CONNECTED | 2026-09-01T22:00:00.608Z | 2026-09-01 17:00:00.608 |
| first retained market event | evt 2026-09-01T22:00:00.606Z / rcv 22:00:00.639Z | 2026-09-01 17:00:00.606 |
| last retained market event | evt 2026-09-02T20:59:59.983Z / rcv 21:00:00.112Z | 2026-09-02 15:59:59.983 |
| CAPTURE_STOPPED | 2026-09-02T21:00:00.426Z | 2026-09-02 16:00:00.426 |
| dataset capture_ended_at | 2026-09-02T21:00:00.426Z | 2026-09-02 16:00:00.426 |

Capture began **0.606 s** after the real 17:00:00 CT open (connection latency only — not materially late). Last retained trade landed **0.017 s** before the 16:00:00 CT close; capture stopped on the real scheduled session boundary.

**SESSION BOUNDARY COVERAGE: PASS** (open and close both covered to sub-second). Trading-date *completeness* is nonetheless broken by the mid-session gap — see DH/DI.

## DH. Lifecycle / gap evidence

| Evidence type | Count | Timestamp(s) |
|---|---|---|
| CAPTURE_STARTED | 1 | 2026-09-01 17:00:00.000 CT |
| SOURCE_CONNECTED | 1 | 2026-09-01 17:00:00.608 CT |
| SOURCE_DISCONNECTED | 1 | 2026-09-01 21:00:25.134 CT — `attempt=1; episode=1; stage=OTHER; error=Your authentication token has expired, reauthentication is required` |
| SOURCE_RECONNECTED | 1 | 2026-09-01 21:00:26.929 CT |
| KNOWN_GAP | **1** | interval 2026-09-01 21:00:25.134 → 21:00:26.929 CT, **duration 1.794927 s**, detail `disconnect_to_reconnect_interval; no automatic recovery assumed` |
| SUSPECTED_GAP | 0 | — |
| CAPTURE_STOPPED | 1 | 2026-09-02 16:00:00.426 CT — `writer_flushes=96423; writer_batch_max=250; writer_queue_depth_max=2060; writer_max_persist_lag_s=0.893; writer_persisted_events=938899; writer_overloaded=false` |

Event-stream evidence around the gap: last pre-gap accepted event `source_order=28645` (rcv 21:00:24.382 CT), first post-gap `source_order=28646` (rcv 21:00:27.658 CT) — source_order is contiguous across the gap (no ordinals assigned to whatever printed on CME during the blackout; that is exactly what `KNOWN_GAP` records).

## DI. Natural reconnect evidence

One real disconnect in 23 h. Episode 1 / within-episode attempt 1. Disconnect stage `OTHER`; sanitized error = auth-token expiry. Recovery (from log): `quote_token_requested=true`, `fresh_dxlink_collector=true`, `oauth_refreshed=true` — a full fresh-collector + OAuth refresh, succeeding on the first attempt in **1.795 s**. Same `dataset_id` retained; `source_order` continuity preserved. **1 / 1 real recovery.** (Attempt 2's accepted live-reconnect proof of 4/4 remains the multi-disconnect reference; Attempt 3 adds a single clean auth-expiry recovery.) No credential material exposed anywhere in artifacts.

## DJ. Retry-episode semantics

`disconnect_episode_count = 1`. New independent outage began at `attempt=1` with `episode=1` (session-wide episode counter) — corrected semantics confirmed. Anti-flapping fuse `max_disconnect_episodes=50` not remotely approached (1/50 = 2 %). Not tuned.

## DK. Writer metrics

| Metric | Value |
|---|---|
| persisted_events | 938,899 |
| accepted events | 938,891 |
| rejected events | 8 |
| deferred events | 0 |
| total source events (max source_order) | 938,899 |
| flush_count | 96,423 |
| batch_size_max | 250 (configured cap; reached) |
| queue_depth_max | 2,060 / 50,000 = **4.12 %** |
| max_persist_lag_seconds | **0.8932** |
| writer_overloaded | **false** |
| capture duration (accepted span) | ≈ 82,799 s (≈23 h) |
| average accepted rate | ≈ 11.3 events/s |

## DL. Peak event rates (durable timestamps)

| Window | Peak (accepted) | When (UTC) | When (America/Chicago) |
|---|---|---|---|
| 1 s (event_timestamp) | 3,224 | 2026-09-02 19:59:59Z | 2026-09-02 14:59:59 |
| 1 s (received_at) | 3,587 | 2026-09-02 19:59:59Z | 2026-09-02 14:59:59 |
| 5 s (received_at) | 8,833 | 2026-09-02 19:59:55–59Z | 2026-09-02 14:59:55–59 |
| 1 min (event_timestamp) | 22,891 | 2026-09-02 19:59Z | 2026-09-02 14:59 |
| 1 min (received_at) | 22,850 | 2026-09-02 19:59Z | 2026-09-02 14:59 |
| all-source 1 s / 1 min | ≈ same (only 8 rejects all day) | — | — |

Busiest hour: 2026-09-02 14:00–15:00 CT (184,459 accepted), i.e. the run-up into the **15:00 CT / 16:00 ET U.S. equity cash close (MOC / closing auction)** — *not* the 08:30 CT cash open. The 08:25–08:45 CT window was a real but secondary burst (peak 1,886/s at 08:45:56 CT ≈ half the 14:59:59 CT peak); a third burst hit 2,146/s at 13:18:45 CT.

## DM. Writer-capacity comparison & classification

| Reference | Queue max | Max persist lag | Overloaded? |
|---|---|---|---|
| Attempt 2 (old arch.) | n/a | ~30 s backlog | yes → eventual failure |
| 0W-2B1 (hardened, synthetic burst) | 3,522 / 50,000 | 1.475 s | false |
| **0W-2 Attempt 3 (real full day)** | **2,060 / 50,000** | **0.893 s** | **false** |

Attempt 3 sat comfortably inside the 0W-2B1 envelope on a real trading day (peak ~3,587 accepted/s sustained with sub-second lag; queue never above 4.1 %). **WRITER CAPACITY: COMFORTABLE.** No `CaptureBackpressureError`, `CaptureWriterError`, `writer_backpressure_overload`, `writer_overloaded=true`, or "queue full" anywhere in artifacts.

## DN. Memory trajectory (`mem_samples.csv`, active-service samples)

First active sample 2026-09-01 17:00:00 CT; last active sample 2026-09-02 16:00:00 CT (76 active samples at 15-min cadence).

| Time (CT) | MemoryCurrent | DB bytes | MemCurrent − DB |
|---|---|---|---|
| 09-01 17:00 | 79.2 MB | 0.1 MB | 79.1 MB |
| 09-01 20:00 | 90.8 MB | 8.2 MB | 82.6 MB |
| 09-02 00:00 | 96.5 MB | 22.0 MB | 74.5 MB |
| 09-02 04:00 | 118.9 MB | 40.7 MB | 78.2 MB |
| 09-02 08:00 | 169.5 MB | 80.6 MB | 88.9 MB |
| 09-02 09:00 | 236.9 MB | 139.8 MB | 97.1 MB |
| 09-02 10:00 | 350.4 MB | 232.4 MB | 118.0 MB |
| 09-02 12:00 | 472.3 MB | 325.2 MB | 147.1 MB |
| 09-02 14:00 | 561.0 MB | 404.0 MB | 157.0 MB |
| 09-02 15:00 | 622.8 MB | 455.3 MB | 167.5 MB |
| 09-02 16:00 | 637.7 MB | 470.6 MB | 167.1 MB |
| (finalization 16:00–16:10) | **MemoryPeak 2,105 MiB** | 470.6 MB | transient |

- MemoryCurrent: min ≈ 79.2 MB, median ≈ 118.9 MB, max active-sample ≈ 637.7 MB. SwapCurrent = 0 throughout; SwapPeak = 0. TasksCurrent = 7 (constant after startup; 4 at the first sample). CPU accrual roughly linear with event volume.
- MemoryCurrent tracks the growing SQLite file almost 1:1 (bulk of the 638 MB is reclaimable OS page cache for the DB attributed to the cgroup).
- The non-file working-set component (`MemCurrent − DB`) still grew from ~79 MB to ~167 MB over the day, accelerating through the high-volume cash session, **without a clear plateau**.
- `MemoryPeak` 2.21 GB was a one-shot finalization spike (SHA-256 over the 449 MiB file + closing-summary aggregation + manifest write during 16:00–16:10 CT), ~3.5× steady state.

## DO. Memory classification

**MEMORY: WATCH.** One trading date does not demonstrate a plateau: the working set grew roughly in proportion to cumulative events / DB size, and finalization required a ~2.2 GB transient. Nothing here is catastrophic (swap stayed at 0, host coped, most resident bytes are reclaimable page cache), but before an always-on / multi-day deployment 0W-4 must add **process-RSS-specific** sampling (RSS vs page-cache disambiguation) and confirm the finalization spike does not scale unbounded with per-day DB size under rotation.

## DP. Database / storage metrics

`PRAGMA integrity_check` → **ok**. `page_size = 4096`, `page_count = 114,885`, `freelist_count = 0`. 4096 × 114,885 = 470,568,960 B = exact file size. No freelist bloat.

## DQ. Storage projections — *empirical extrapolation from one ES trading date*

- bytes / total source event = 470,568,960 / 938,899 = **501.2 B**
- bytes / accepted observation = 470,568,960 / 938,891 = **501.2 B**

| Trading dates | Projected size |
|---|---|
| 20 | ≈ 9.4 GB |
| 60 | ≈ 28.2 GB |
| 250 | ≈ 117.6 GB (≈110 GiB) |

Basis: 2026-09-02 was an active-but-ordinary day (938,891 accepted trades). One-DB-file-per-trading-date (0W-3 rotation) assumed; no cross-day schema overhead modelled. `/dev/sda2` has 113 GB free, so ~250 trading dates is near the current single-disk headroom — flag for 0W-4+ planning.

## DR. Source-order accounting

| Quantity | Value |
|---|---|
| min source_order | 1 |
| max source_order | 938,899 |
| accepted (distinct provenance source_order) | 938,891 |
| rejected (durable, source_order in-range) | 8 → {60307, 62505, 74612, 74613, 75497, 75570, 129794, 607133} |
| deferred / correction / cancel / duplicate-replay | 0 / 0 / 0 / 0 |
| distinct source_order (accepted) | 938,891 |
| non-monotonic violations | 0 |
| unexplained missing ordinals | 0 |
| duplicate source_order | 0 |

938,891 accepted + 8 rejected = 938,899 = contiguous 1…938,899. **Single clean monotonic sequence, fully accounted.**

## DS. Dataset sequence

`trade_observations.dataset_sequence` = 1…938,891, 938,891 distinct, contiguous. Independent of source-order accounting (the 8 rejected ordinals live only in the source-order space). No anomaly.

## DT. NEW / CORRECTION / CANCEL / rejection counts

| Class | Count | % of accepted |
|---|---|---|
| NEW | 938,891 | 100.000 % |
| CORRECTION | 0 | 0 % |
| CANCEL | 0 | 0 % |

Effective tape == canonical tape (CLI confirms "Differs from effective tape: no"); no correction/cancel reconstruction needed, no anomalies.

Rejections: 8, all `INVALID_DXLINK_TICK`, all `DXLINK_TIME_AND_SALE`, all NEW-classification source records with `exchange_sale_conditions = 'B'`, prices 7635–7680, sizes 2–26. Full structured source evidence retained in `rejected_dxlink_timesale_source_records` with `source_order` preserved. Deferred: 0.

## DU. Source metadata availability (accepted NEW, n = 938,891)

| Field | Present |
|---|---|
| bidPrice | 100.00 % |
| askPrice | 100.00 % |
| aggressorSide | 100.00 % |
| exchangeCode | 100.00 % |
| exchangeSaleConditions | 100.00 % |
| eventFlags | 100.00 % |
| tradeThroughExempt | 100.00 % |
| extendedTradingHours | 100.00 % present (all value 0) |
| valid_tick | 100.00 % |
| spreadLeg | 0.00 % (never populated) |

## DV. Bid / ask availability (accepted NEW)

both bid+ask present: 938,891 (100.00 %); bid only: 0; ask only: 0; both missing: 0.

## DW. Aggressor-side distribution (accepted NEW)

SELL: 471,740 (50.24 %); BUY: 467,151 (49.76 %); UNDEFINED: 0; null/other: 0.

## DX. SQLite integrity

`PRAGMA integrity_check;` → **ok**.

## DY. Manifest / checksum

Manifest present; `state = FINALIZED`; `dataset_id = 9c76e79c-…-dc20671`; `collector_git_commit = 6cba2296…c01406`; `sha256 = 24efe7e84859550978f8b278eef4d82b2ed239e5f6d6e4e24d61cf82389e1079`. Independently recomputed `sha256sum` of the dataset = identical; closing-summary JSON in the log carries the same digest. **CHECKSUM: MATCH.** Manifest not modified.

## DZ. Closing-summary reconciliation

`dataset_closing_summaries` (frozen) vs fresh read-only recount:

| Field | Frozen | Fresh | Match |
|---|---|---|---|
| accepted_trade_count | 938,891 | 938,891 | ✅ |
| deferred_event_count | 0 | 0 | ✅ |
| rejected_record_count | 8 | 8 | ✅ |
| known_gap_count | 1 | 1 | ✅ |
| suspected_gap_count | 0 | 0 | ✅ |
| first_source_order | 1 | 1 | ✅ |
| last_source_order | 938,899 | 938,899 | ✅ |

No discrepancy. `closed_at = 2026-09-02T21:00:00.425526Z`.

## EA. Dataset audit (read-only `audit_dataset`)

accepted 938,891; rejected 8 (INVALID_DXLINK_TICK ×8, all DXLINK_TIME_AND_SALE); deferred 0; lifecycle counts CAPTURE_STARTED 1 / SOURCE_CONNECTED 1 / SOURCE_DISCONNECTED 1 / SOURCE_RECONNECTED 1 / CAPTURE_STOPPED 1; known_gap 1 (Σ duration 1.794927 s); suspected_gap 0; first/last trade event_timestamp 2026-09-01T22:00:00.606Z → 2026-09-02T20:59:59.983Z; dataset_sequence 1…938,891; single instrument `FUTURE:CME:ES:2026-09`.

## EB. Session-open VWAP

Anchor = CME equity-index session open (2026-09-01 17:00:00 CT / 2026-09-01T22:00:00Z). trade count 938,891; contract volume 1,262,179; **VWAP 7667.974373088127753670438187**; coverage `DATASET_BEGINS_AFTER_ANCHOR` (unobserved pre-capture interval 0.606 s; dataset ends 0.017 s before session end) — i.e. effectively full session, the deltas being connect latency and last-trade timing only.

## EC. Volume profile / POC / value area

POC 7679.00 (volume 29,836; 20,747 prints); VAL 7661.75; VAH 7690.25; value-area target 70.00 %, **achieved 70.1161 %** (115 included levels); profile price range 7618.50–7691.25 (292 occupied levels, tick 0.25); total profile volume 1,262,179. Canonical NEW-only == effective tape.

## ED. Developing 5-minute series

snapshot count 276; first snapshot 17:05 CT; last snapshot 16:00* CT (terminal analytical cutoff; last retained trade 15:59:59.983 CT); source = effective tape; runtime 258.5 s.

## EE. Terminal static-vs-developing equality

| Metric | Static full-dataset | Developing terminal (16:00*) | Equal? |
|---|---|---|---|
| VWAP | 7667.974373088127753670438187 | 7667.9744 (exact 7667.9743730881…) | ✅ |
| POC | 7679.00 | 7679.00 | ✅ |
| VAL | 7661.75 | 7661.75 | ✅ |
| VAH | 7690.25 | 7690.25 | ✅ |

**TERMINAL EQUALITY: PASS** (effective population == canonical; 0 corrections/cancels).

## EF. Visualization

`scripts/dicks_lab_plot_developing_profile.py … --anchor session-open --interval 5m`. Output PNG **1500 × 900** RGBA, 152 KB, valid PNG signature, headless success, generation runtime 263.8 s. Visual sanity check: four labelled series (VWAP/POC/VAL/VAH) plus terminal-cutoff diamond at ≈7668, x-axis spans 2026-09-01 16:00 → 2026-09-02 16:00 CT, coverage caption present. Not malformed. (Runtime PNG kept out of Git per policy; generated to the audit scratchpad.)

## EG. Analytics performance (first true full-trading-date evidence, 938,891 trades)

| Analysis | Wall-clock |
|---|---|
| dataset audit (read-only) | ≈ few seconds |
| session-open VWAP | 90.9 s |
| volume profile / POC / value area | 86.5 s |
| developing 5 m series (276 snapshots) | 258.5 s |
| full-session visualization | 263.8 s |
| effective-tape reconstruction | folded into the above (no corrections/cancels) |

Static analytics ≈ 1.5 min each; developing + plot ≈ 4.3 min each. Decimal-heavy Python aggregation dominates — acceptable for research cadence, worth an optimisation pass before routine multi-day use.

## EH. Local host / SQLite capacity classification

**SQLITE / LOCAL HOST CAPACITY: COMFORTABLE**, with two WATCH items.

| Dimension | Evidence | Verdict |
|---|---|---|
| raw disk throughput | 449 MiB over 23 h, 96,423 flushes (~5 KB/s avg, low-MB/s peak), freelist 0 | COMFORTABLE |
| writer transaction architecture | queue ≤4.1 %, lag ≤0.893 s, `writer_overloaded=false` | COMFORTABLE |
| network reliability | 1 disconnect / 23 h (auth-token expiry), auto-recovered 1.8 s — but produced a real KNOWN_GAP | WATCH |
| memory trajectory | working set grew ~with cumulative events; 2.2 GB finalization transient; no plateau proven in one day | WATCH |
| CPU load | 7 min 46 s CPU / 23 h wall ≈ 0.56 % | COMFORTABLE |

No hardware upgrade indicated by this run (250-date storage headroom is the nearest limit; see DQ).

## EI. 0W-2 Attempt 3 — final classification

```
0W-2 ATTEMPT 3:
ENDURANCE PASS / DATA COMPLETENESS FAIL
```

- Endurance / resilience / durability / accounting: **PASS** — 23 h clean run, exit 0, dataset FINALIZED, integrity ok, checksum MATCH, closing summary reconciles, source-order fully accounted, writer comfortable, 1/1 reconnect recovery, correct episode semantics.
- Complete-trading-date data: **FAIL** — `KNOWN_GAP = 1` (1.795 s, 2026-09-01 21:00:25–27 CT, auth-token expiry). §10 requires `KNOWN_GAP = 0` and `SUSPECTED_GAP = 0` for the *complete-trading-date* bar. `SUSPECTED_GAP = 0` is satisfied; `KNOWN_GAP` is not. The gap fell in a low-volume overnight period but its contents are genuinely unrecoverable from this tape, so this particular source tape is not complete and must not be represented as such.

Not `PASS — COMPLETE TRADING-DATE DATASET` (gap), not `FAIL / INTERRUPTED` (the service and dataset both completed cleanly), not `INCONCLUSIVE` (evidence is complete and unambiguous).

## EJ. 0W-2 closure recommendation

**0W-2: NOT yet ready to close.** Attempt 3 established almost everything the bar demands — real 17:00→16:00 coverage, truthful lifecycle, bounded-enough memory, complete accounting, valid durable artifacts — but the standing acceptance text for 0W-2 is *"one complete ordinary ES trading date … with no known or suspected capture gap."* A `KNOWN_GAP` is present, so one more attempt is needed that reaches a full trading date with `KNOWN_GAP = 0` **or** a Product-Owner decision to redefine the 0W-2 bar to accept a sub-2 s auto-recovered auth-expiry gap during overnight Globex (the collector-resilience half is already proven twice: Attempt 2 4/4, Attempt 3 1/1).

The auth-token expiry at ~4 h into the run is the actionable root cause: proactively refreshing the DXLink/OAuth credential *before* expiry (rather than reactively on disconnect) would likely have avoided the gap entirely.

## EK. 0W-3 status

**0W-3: ACCEPTED / CLOSED — unchanged.** Attempt 3 was a single-dataset bounded run by design (`--duration 83700`, ended in the maintenance interval) and never rotated; that does not reopen 0W-3.

## EL. 0W-4 recommendation

Evidence now supports **preparing** 0W-4 (2–3 day unattended soak) but not a full green light, because 0W-2's complete-trading-date proof is still outstanding and two 0W-4-relevant WATCH items were raised: (a) memory trajectory needs RSS-specific confirmation over multiple days, and (b) proactive credential refresh should be considered so multi-day runs don't accumulate one auth-expiry gap per token lifetime. Recommendation: obtain the clean 0W-2 full-day dataset (or the PO bar redefinition) first, fold in proactive credential refresh, then start 0W-4. **Do not start 0W-4 — await Product Owner authorization.**

## EM. Soak report update

This addendum. Full history preserved: 0W-1, 0W-2 Attempt 1, 0W-2A, 0W-2 Attempt 2, 0W-2B, 0W-2B1, 0W-3, 0W-2 Attempt 3. No failed attempt erased. No commit.

## EN. Temporary units — safe to remove?

All systemd status, journal, timer, memory-sampling, and artifact evidence for Attempt 3 has now been captured. Per §44 the units are preserved for this handoff; once Product Owner has reviewed this audit the following are safe to remove:

- `dicks-0w2-attempt3.service` / `dicks-0w2-attempt3.timer` (both `inactive (dead)`, job done)
- `dicks-0w2-attempt3-memsample.service` / `dicks-0w2-attempt3-memsample.timer` (timer still active every 15 min, sampling an inactive service — harmless but now pointless; stop + disable when convenient)
- `dicks-0w2-attempt3-prearm-inhibit.service` (prearm inhibitor)

**Do not delete `apps/dicks_laboratory/data/0w2_attempt3/`.** Removal not performed by this audit (0W-2 still open).

## EO. Files changed / Git

Only this file (`docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md`, still untracked) was modified. `scripts/dicks_lab_quote_rate_experiment.py` untracked, unchanged. No source changes. `git diff --check` clean. No commit, no push.

---

# ADDENDUM — 0W-2C: Quote-Token Lifetime Provenance + Finalization Memory Audit

**Audit run:** 2026-09-02 evening on `robby`. **No source changed** (audit + operational only). Product Owner accepted the Attempt-3 forensic result: `0W-2 Attempt 3 = ENDURANCE PASS / DATA COMPLETENESS FAIL`; `0W-2` remains OPEN (`KNOWN_GAP = 0` and `SUSPECTED_GAP = 0` still required); `0W-3` remains ACCEPTED / CLOSED. The 0W-2 completeness bar is **not** redefined.

**Two findings, both with direct evidence:**
1. **The 21:00:25 CT disconnect was the DXLink _quote token_ (not the OAuth REST token) hitting its 24-hour expiry — and that 24h clock had started at the Monday pre-arm preflight, ~20 h before the Tuesday 17:00 session connection.** A live experiment proves tastytrade's `/api-quote-tokens` returns the *same* token with a *non-advancing* `expires-at` on repeated requests inside its validity window, so the collector's `get_api_quote_token()` at 17:00 got back the ~20-h-old preflight token with only ~4 h of life left. **PREFLIGHT TOKEN SIDE EFFECT: CONFIRMED.**
2. **The ~2.21 GB finalization `MemoryPeak` is a confirmed, measured inefficiency:** `_write_closing_summary()` calls `store.load_trade_observations()` — materialising all 938,891 rows as `TradeObservation` dataclasses (with `Decimal`/`datetime`/`UUID`/nested `InstrumentIdentity`) — purely to take `len()`. Measured cost on the Attempt-3 DB: **+1,514 MB max-RSS, 22 s**, versus **`SELECT COUNT(*)` = +0 MB, 1.5 s**. **FINALIZATION MEMORY: DEFECT CONFIRMED** (non-blocking on Attempt 3; scales linearly with accepted-trade count).

## FA. Attempt-3 PO classification recorded

```
0W-2 Attempt 3 : ENDURANCE PASS / DATA COMPLETENESS FAIL
0W-2           : OPEN  (requires KNOWN_GAP = 0 AND SUSPECTED_GAP = 0)
0W-3           : ACCEPTED / CLOSED
```
Not starting 0W-4 / 0W-5b / 0X / 0Y. Not arming Attempt 4. Completeness bar unchanged.

## FB. Official credential-lifetime model — two separate credentials

| Credential | Endpoint | Purpose | Documented lifetime | Observed lifetime (this audit) | Where it lives in our code |
|---|---|---|---|---|---|
| **OAuth REST access token** | `POST /oauth/token` (`grant_type=refresh_token`) | Bearer auth for all tastytrade REST calls | short (~15 min) | not directly measured; consistent with ~15 min (a fresh one was minted on the reconnect REST call ~4 h after the previous REST activity) | `TastytradeClient._access_token`, lazily minted, cleared + re-minted on any `401`; counter `access_token_refresh_count` |
| **DXLink API quote token** | `GET /api-quote-tokens` | `AUTH` frame to the dxfeed DXLink websocket | ~24 h (community); **confirmed 24 h exactly by live test — see FF** | **86,399 s ≈ 24 h 00 m 00 s** | returned raw by `TastytradeClient.get_api_quote_token()`; passed once into `DxLinkSourceCollector(url, token)` and sent once in the `AUTH` frame |

These are independent. The DXLink websocket stays up on the quote token alone; the OAuth token is only needed to *fetch* a quote token over REST.

## FC. Monday preflight → Tuesday expiry timing

| Instant | Source | Time (CT) | Time (UTC) |
|---|---|---|---|
| Pre-arm scaffolding started (`dicks-0w2-attempt3-prearm-inhibit.service`) | `journalctl --user` | 2026-08-31 21:00:48 | 2026-09-01 02:00:48 |
| First `mem_samples.csv` row (arming script ran) | artifact | 2026-08-31 21:00:35 | 2026-09-01 02:00:35 |
| **Credential preflight `get_api_quote_token()`** (manual, not a unit — time *inferred* from the arming window) | inference | **2026-08-31 ~21:00–21:02** | **2026-09-01 ~02:00–02:02** |
| Timer fired → collector launched | `systemd` | 2026-09-01 16:55:00 | 2026-09-01 21:55:00 |
| Collector `get_api_quote_token()` at startup (`fresh_collector()` initial call) | code path (proven) + log | 2026-09-01 ~16:55–17:00 | 2026-09-01 ~21:55–22:00 |
| `SOURCE_CONNECTED` | dataset quality event | 2026-09-01 17:00:00.608 | 2026-09-01 22:00:00.608 |
| **`SOURCE_DISCONNECTED`** — `error=Your authentication token has expired` | dataset quality event | **2026-09-01 21:00:25.134** | **2026-09-02 02:00:25.134** |
| `SOURCE_RECONNECTED` | dataset quality event | 2026-09-01 21:00:26.929 | 2026-09-02 02:00:26.929 |

- **preflight → disconnect ≈ 23 h 59 m** (2026-09-01 ~02:01 UTC → 2026-09-02 02:00:25 UTC). Within ~1–2 min of exactly 24 h.
- **session connect → disconnect ≈ 4 h 00 m** (22:00:00 UTC → 02:00:25 UTC). Nowhere near 24 h.
- If the token in use at 17:00 had been genuinely fresh, its 24 h expiry would have been **~2026-09-02 17:00 CT** — ~1 h *after* the 16:00 CT session close, i.e. the whole trading date would have been covered by one token.

The 24-h-from-*preflight* correlation is decisive; the 4-h-from-*connect* interval rules out a fresh token at connect.

## FD. `get_api_quote_token()` implementation audit

`apps/K9/src/K9/tastytrade/client.py:107`
```python
def get_api_quote_token(self) -> dict[str, Any]:
    """Return the short-lived DXLink quote token and endpoint."""
    return self._data(self._get_json("/api-quote-tokens"))
```
- Every call performs a live `GET /api-quote-tokens` (through `_get_json`, which transparently refreshes the OAuth token once on a `401`).
- Returns the endpoint's `data` object **verbatim and complete** — no field stripping. So `issued-at` / `expires-at` (see FF) are **already available to callers today**; nothing in our code reads or retains them.
- The docstring's "short-lived" is a **mislabel** — the token is a 24 h credential. (Unchanged since commit `666dc72`; predates Attempt 3.)

## FE. Client-side token-caching audit

| Question | Answer | Evidence |
|---|---|---|
| Quote token cached in `TastytradeClient`? | **No.** No field stores it; each `get_api_quote_token()` is a fresh HTTP GET. | `client.py` — the only cached credential is `self._access_token` (the OAuth token) |
| Persisted to disk / env / keyring between processes? | **No.** `TastytradeClient` does zero file/env I/O for tokens. | whole class reviewed |
| Could Monday's preflight process share memory with Tuesday's collector? | **No.** Separate processes (`preflight_credentials.py` vs the systemd-launched `dicks_lab_collect_es.py`), hours apart. | unit definitions + script provenance |
| So how did the Monday token reach Tuesday? | **Provider-side reuse.** tastytrade returns the same still-valid token for the account on repeated `/api-quote-tokens` calls. | live experiment, FF |
| `issued-at` / `expires-at` currently discarded? | **Yes** — `get_api_quote_token()` returns them but no caller reads them; the collector takes only `token` + `dxlink-url`. | `dicks_lab_collect_es.py:71–84`, `preflight_credentials.py:36–42` |

The `fresh_collector()` comment in `scripts/dicks_lab_collect_es.py:63–69` ("`get_api_quote_token()` always asks Tastytrade for a fresh one") encodes the **incorrect mental model** that produced this gap: the call always *asks*, but the provider *answers with the existing token* until it is at/near expiry.

## FF. Safe repeated-token API experiment

Two `GET /api-quote-tokens` calls, ~2 s apart, on the production account. Only non-secret metadata reported; token value never printed, only compared in memory via SHA-256 digest.

| Field | Request 1 | Request 2 (~2 s later) |
|---|---|---|
| `data` key names | `dxlink-url, expires-at, issued-at, level, token` | identical |
| `issued-at` | `2026-09-03T02:53:45.218+00:00` | `2026-09-03T02:53:45.221Z` |
| `expires-at` | `2026-09-04T02:53:45.218+00:00` | `2026-09-04T02:53:45.221Z` |
| lifetime (`expires-at − issued-at`) | **86,400 s = 24 h 00 m** | 86,400 s = 24 h 00 m |
| `remaining_lifetime_seconds` (`expires-at − now`) | 86,399 | 86,397 |
| token is a JWT? | no (opaque, length 103) | no |
| **`same_token_as_previous`** | — | **`true`** |

**Conclusions:**
- The response **does** carry `issued-at` and `expires-at`. Token lifetime is **exactly 24 h**.
- Repeated requests inside the validity window return the **byte-identical token**.
- `expires-at` advanced only **~3 ms** between calls made **~2 s** apart → the expiry is **anchored to first issuance, not refreshed per request**. (The 3 ms wobble is response-serialisation jitter — note the `+00:00` vs `Z` formatting change — not a real 2 s extension.)
- Therefore a token obtained early (e.g. Monday preflight) is handed back later (Tuesday 17:00) **with its original expiry**, exactly matching Attempt 3.

*Side effect of this experiment:* it rotated the account's current quote token (harmless — the next real capture just fetches a fresh one).

## FG. Attempt-3 initial token-acquisition path

Runtime + source trace of Tue 2026-09-01 ~16:55–17:00 CT:

| Step | Proof type | Finding |
|---|---|---|
| `TastytradeClient(...)` constructed | source | fresh object, `_access_token = None` |
| `client.list_futures()` (symbol resolution) | source | forces first OAuth mint of the process, then `GET /instruments/futures` |
| `fresh_collector()` called once for the initial connect | source (`dicks_lab_collect_es.py:106`) | — |
| → `client.get_api_quote_token()` | source + log line `fresh_collector: quote_token_requested=true ... oauth_refreshed=false` | **the HTTP `GET /api-quote-tokens` did occur** |
| → did it refresh OAuth first? | log (`oauth_refreshed=false` on the startup line) | **no** — the OAuth token minted moments earlier by `list_futures()` was still valid |
| → did it return a token issued earlier? | **inference** from FF (provider reuse) + FC (24-h-from-preflight correlation) | **yes — the Monday preflight token, ~20 h old, ~4 h of life left** |
| any quote token read from disk / env / cache? | source (FE) | **no** — impossible in this codebase |
| did the collector have access to the Monday preflight token? | inference | **only via the provider handing back the same token** |

Proven: the HTTP call happened; no local caching exists; OAuth was not refreshed at startup. Inferred (strongly, from FF + FC): the provider returned the pre-existing preflight token.

## FH. Most likely identity of the expired credential

**The DXLink API quote token.** Reasons:
- The disconnect error string is the DXLink/dxfeed auth-expiry message, raised when the **streaming** token is rejected — the websocket is authed by the quote token, never by the OAuth token.
- Timing = 24 h after the *preflight quote-token fetch* (FC), which is precisely the quote token's measured lifetime (FF). The OAuth token's ~15 min lifetime cannot produce a *single* clean expiry ~4 h into a socket that had been streaming continuously.
- `oauth_refreshed=true` on the **reconnect** line is a *secondary* effect: the reconnect path had to call `GET /api-quote-tokens` again, and by then (~4 h since the last REST call) the ~15 min OAuth token was stale, so `_get_json` did its one-shot refresh before the quote-token GET succeeded.

Do **not** state "OAuth access-token expiry caused the websocket disconnect" — the evidence points to the quote token.

## FI. Attempt-3 quote token `issued_at` / `expires_at`

**Exact values: UNAVAILABLE.** The preflight printed only booleans/lengths; the collector logs only `quote_token_requested=true`; neither recorded `issued-at`/`expires-at`, and `TastytradeClient` discards them.

**Reconstruction (labelled as such):** working back from the observed expiry (`SOURCE_DISCONNECTED` 2026-09-02T02:00:25 UTC) and the measured 24 h lifetime:
- quote token `issued-at` ≈ **2026-09-01T02:00:25 UTC ± ~2 min** (= 2026-08-31 ~21:00 CT — the preflight instant)
- quote token `expires-at` ≈ **2026-09-02T02:00:25 UTC** (the observed disconnect)
- remaining lifetime at the 17:00 CT / 22:00 UTC session connect ≈ **4 h 00 m** (of a 24 h token)

## FJ. Preflight side-effect assessment

```
PREFLIGHT TOKEN SIDE EFFECT: CONFIRMED
```
`apps/dicks_laboratory/data/0w2_attempt3/preflight_credentials.py:36` calls `client.get_api_quote_token()` during pre-arm — its own docstring says "obtains a fresh quote token (same call the collector's reconnect path uses)". Given provider-side reuse (FF), that call **started the 24 h clock ~20 h before the capture connection**, leaving the live capture only ~4 h of usable token lifetime. A preflight should verify *reachability/credentials/instrument resolution* without consuming the production quote token's lifetime. The other three preflight checks (OAuth usable via `list_futures()`, REST reachable, `/ESU6 → /ESU26:XCME` resolution) do **not** require fetching a quote token and are unaffected.

## FK. In-place DXLink re-authentication capability

```
IN-PLACE REAUTH (current implementation): NOT SUPPORTED
IN-PLACE REAUTH (provider/protocol feasibility): UNCLEAR — untested
```
- `DxLinkSourceCollector` (`apps/K9/src/K9/tastytrade/dxlink.py:407–578`) takes `quote_token` at construction, sends exactly one `AUTH` frame in `_setup()`, and has **no** path to (a) detect imminent expiry, (b) obtain a replacement token, or (c) send a second `AUTH` on the live socket. Token expiry surfaces as a `DxLinkError` from `_receive`/`_read_feed_config` (an `ERROR` frame or a transport close) → the orchestration layer does a **full reconnect** (new `fresh_collector()` → new `DxLinkSourceCollector` → new websocket → new SETUP/AUTH/CHANNEL/FEED_SUBSCRIPTION).
- The DXLink protocol authenticates channel 0 with `{"type":"AUTH","channel":0,"token":...}`; re-sending it on an already-`AUTHORIZED` connection to swap an expiring token is **not demonstrated** by our client, our tests, or the reference `tastyware/tastytrade` streamer (which likewise fetches the token once and never refreshes it). Whether the provider keeps FEED subscriptions alive across a re-`AUTH` is unverified.

## FL. Recommended smallest credential correction (NOT implemented)

Priority order, smallest first:

1. **Do not fetch a quote token during pre-arm preflight.** Change `preflight_credentials.py` to prove OAuth + REST reachability + instrument resolution only (drop the `get_api_quote_token()` call, or make it opt-in). This alone would have given Attempt 3 a full-lifetime token at 17:00. *(scaffolding file, not product code — lowest risk.)*
2. **Surface quote-token lifetime at connect (observability, FN).** Have `fresh_collector()` read `issued-at`/`expires-at` from the (already-returned) response and log `quote_token_remaining_seconds_at_connect` (integer) — never the token. Lets any future soak answer this directly.
3. **Lifetime-vs-session guard at connect.** If `remaining_lifetime < expected_remaining_session + margin`, emit a loud operational warning (not a gap). *Do not pick `margin` in this audit* — first confirm provider behaviour over a couple of real fetches; a genuinely fresh 24 h token vs a ~23 h ES session leaves only ~1 h of headroom, so lifetime awareness matters even in the happy path.
4. **Only if 1–3 prove insufficient:** design a *make-before-break* overlapping reconnect (open + AUTH + FEED_SUBSCRIBE a second socket, confirm data flow, then drop the first) so a mid-session token roll costs **no** `KNOWN_GAP`. A plain break-before-make reconnect-before-expiry is **not** a completeness solution — it manufactures the very gap 0W-2 forbids. Do not build this yet.

## FM. Is another full-day attempt justified yet?

```
NO — root cause first.
```
The root cause is now established with evidence (FF + FC + FJ), and correction **1** (preflight stops minting the token) is a trivial, low-risk change that directly removes the Attempt-3 failure mode. The evidence-based next step is: apply correction 1 (+ ideally observability 2), then arm Attempt 4 expecting a genuinely fresh ~24 h token at 17:00 that covers the ~23 h session with ~1 h margin — rather than re-running the same configuration and hoping. Await Product Owner authorization for both the code change and Attempt 4.

## FN. cgroup memory composition

The Attempt-3 service cgroup no longer exists (unit removed — FS), so its `memory.stat` breakdown cannot be read post hoc. Composition is therefore **inferred**, not measured:

- `systemd MemoryCurrent` = cgroup-v2 `memory.current`; `MemoryPeak` = `memory.peak`. Both count **everything** charged to the unit's cgroup — anonymous (heap/stack), **file page cache for files this cgroup first faulted in** (including the SQLite DB, read via `pread`), kernel, socket buffers, tmpfs. Reclaimable page cache is **included**, nothing subtracted.
- Evidence the bulk was page cache: `MemoryCurrent − db_bytes` held at **~75–90 MB for the first ~15 h** (overnight, DB 0→90 MB) and drifted to **~167 MB** by 16:00 CT, while `MemoryCurrent` tracked `db_bytes` almost 1:1 (638 MB total vs 471 MB DB at session end).
- `MemorySwapCurrent` / `MemorySwapPeak` = **0** throughout → no anonymous-memory pressure; the true process anon working set was modest.
- **Best decomposition of the 638 MB at 16:00 CT:** ~470 MB reclaimable file page cache (the DB) · ~100 MB interpreter + libs + writer queue + socket buffers baseline · ~70 MB genuine anon growth over the day (queue high-water, dict/`Decimal` churn, allocator fragmentation).

**So "the collector working set grew to 638 MB" is misleading.** The process's private (anon) RSS almost certainly stayed in the low-100s of MB; the cgroup figure is dominated by reclaimable DB page cache. The soak-report Attempt-3 memory sections (DN/DO) should be read with this caveat. `MEMORY: WATCH` still stands only because the audit lacks a *measured* anon-vs-file split and the anon component did drift upward without a proven plateau.

## FO. Process-RSS observability recommendation (operational sampler only — no source change)

For the next live run, extend the operational sampler (`mem_sample.sh` equivalent) to also record, per collector PID:

- `/proc/<pid>/status` → `VmRSS`, `VmHWM`, `VmSize`
- `/proc/<pid>/smaps_rollup` → `Rss`, `Pss`, `Private_Dirty`, `Private_Clean` (cheap; one read)
- cgroup `memory.stat` → `anon`, `file`, `inactive_file`, `active_file`, `slab`, `sock`, plus `memory.current` / `memory.peak`

That makes the anon-vs-page-cache question answerable from data instead of inference, and isolates any real Python-heap growth. **Do not modify collector source to collect this** — the sampler runs beside the process.

## FP. Finalization memory-path audit

Path: writer drain → `_finalize()` → `_write_closing_summary()` → `_build_result()` → `compute_sha256()` → `write_manifest()` (`apps/dicks_laboratory/src/dicks_laboratory/long_running_capture.py`).

| Step | Memory behaviour | Verdict |
|---|---|---|
| `compute_sha256()` (`:911`) | streaming, `handle.read(1024*1024)` chunks into `hashlib.sha256` | **fine** — O(1) memory, not the culprit |
| `write_manifest()` (`:926`) | builds a ~10-key dict, `manifest_path.write_text(...)` | **fine** — bytes, trivial |
| `_build_result()` closing-summary reads | `load_dataset_closing_summary` (1 row), `load_quality_events` (6 rows) | fine |
| **`_write_closing_summary()` (`:834`)** | **`trades = store.load_trade_observations(dataset_id)`** then `accepted_trade_count=len(trades)` (`:846`) | **DEFECT** |
| same pattern, crash-finalize path (`:407`) | `accepted_count = len(store.load_trade_observations(dataset_id))` | **DEFECT (same)** |

`store.load_trade_observations()` (`store.py:676`) does `SELECT o.*, i.… FROM trade_observations JOIN instruments … .fetchall()` then builds a **tuple of 938,891 `TradeObservation` dataclasses**, each carrying a nested `InstrumentIdentity`, two `Decimal`s, a `datetime`, three `UUID`s and an enum. The `fetchall()` `Row` list and the dataclass tuple are alive simultaneously. It is called here **only to obtain `len()`**. `LaboratoryStore` has **no** `COUNT(*)` helper.

**Measured on the Attempt-3 DB (read-only, child process, `getrusage` max-RSS):**

| Operation | Wall time | max-RSS high-water |
|---|---|---|
| `SELECT COUNT(*) FROM trade_observations` | **1.5 s** | **+0 MB** (stayed ~33 MB) |
| `store.load_trade_observations()` → `len()` | **22.3 s** | **~1,514 MB** (peak 1,550,732 KB) |

`0.6 GB` steady-state + `~1.5 GB` this materialisation ≈ **`2.1 GB`**, matching the observed `MemoryPeak` `2.21 GB` and the `mem_samples.csv` jump from the 16:00 CT sample (638 MB) to the post-exit `MemoryPeak`. Root cause of the finalization spike is **pinned**.

No `path.read_bytes()` or equivalent whole-file slurp exists; the spike is entire-**result-set** materialisation, not entire-file.

## FQ. Finalization memory classification

```
FINALIZATION MEMORY: DEFECT CONFIRMED
```
Non-blocking on Attempt 3 (completed, swap stayed 0, host had headroom), but it is an obvious full-dataset materialisation used only for a row count, it scales **linearly** with accepted-trade count, and it already reached ~1.5 GB on an ordinary ES day. A busier day, a wider instrument set, or a smaller host turns it blocking.

**Smallest correction (NOT implemented here):** add `LaboratoryStore.count_trade_observations(dataset_id) -> int` doing `SELECT COUNT(*) FROM trade_observations WHERE dataset_id = ?`, and use it at `long_running_capture.py:846` and `:407` in place of `len(load_trade_observations(...))`. Expected effect: finalization RSS delta ~1.5 GB → ~0; finalization time for the count 22 s → 1.5 s. `load_trade_observations()` itself stays as-is for the analytics that genuinely need the objects. This is a one-method, two-call-site change plus a smoke test — defer to a dedicated corrective slice with Product Owner sign-off.

## FR. Analytics performance — recorded, no action

First full-trading-date research-performance evidence (from the Attempt-3 audit, 938,891 trades): session-open VWAP ~91 s · Volume Profile / POC / Value Area ~87 s · developing 5 m series (276 snapshots) ~259 s · full-session visualisation ~264 s · dataset audit a few seconds. **No analytics optimisation in 0W-2C** — candidate for a later phase.

## FS. Storage finding — accepted, no action

Preserved from the Attempt-3 audit: full trading-date DB `470,568,960 B`; `~501 B` per source event / per accepted observation; empirical extrapolation ~9.4 GB (20 dates) / ~28.2 GB (60) / ~117.6 GB (250). No hardware action; not a storage-redesign trigger.

## FT. Attempt-3 temporary unit cleanup — DONE

All systemd status / journal / timer / memory-sampling / artifact evidence was captured in the Attempt-3 forensic addendum and above. Unit **definitions preserved** in FU below. Then:

```
systemctl --user stop  dicks-0w2-attempt3-memsample.timer dicks-0w2-attempt3-memsample.service
systemctl --user disable dicks-0w2-attempt3-memsample.timer
systemctl --user stop  dicks-0w2-attempt3.timer
systemctl --user disable dicks-0w2-attempt3.timer
systemctl --user stop  dicks-0w2-attempt3-prearm-inhibit.service
systemctl --user stop  dicks-0w2-attempt3.service
rm ~/.config/systemd/user/dicks-0w2-attempt3.service \
   ~/.config/systemd/user/dicks-0w2-attempt3.timer \
   ~/.config/systemd/user/dicks-0w2-attempt3-prearm-inhibit.service \
   ~/.config/systemd/user/dicks-0w2-attempt3-memsample.service \
   ~/.config/systemd/user/dicks-0w2-attempt3-memsample.timer
systemctl --user daemon-reload
```

Verified afterward: `systemctl --user list-unit-files | grep dicks` → nothing; `list-timers` → nothing. The memory sampler (which had kept appending an `inactive`-service row every 15 min after capture ended — last row `2026-09-02T21:45` CT) is now stopped.

**`apps/dicks_laboratory/data/0w2_attempt3/` was NOT deleted** — the dataset, manifest, log, `mem_samples.csv`, `mem_sample.sh`, and `preflight_credentials.py` all remain (verified: 449 MiB DB present).

## FU. Preserved Attempt-3 unit definitions (removed from `~/.config/systemd/user/`)

```ini
# dicks-0w2-attempt3.service
[Unit]
Description=Dicks Laboratory Phase 0W-2 Attempt 3 - one full ordinary ES trading-date capture (trading_date 2026-09-02), committed collector 6cba2296 (temporary experiment scaffolding, not product code)
[Service]
Type=simple
WorkingDirectory=/home/temckee8/Documents/REPOs/copper
Environment=PATH=/home/temckee8/.local/bin:/usr/local/bin:/usr/bin:/bin
Environment=HOME=/home/temckee8
MemoryAccounting=yes
ExecStart=/usr/bin/systemd-inhibit --what=sleep:idle --why="Dicks Laboratory 0W-2 Attempt 3 full trading-date ES capture" /home/temckee8/.local/bin/uv run python scripts/dicks_lab_collect_es.py --duration 83700 --data-dir apps/dicks_laboratory/data/0w2_attempt3
StandardOutput=append:/home/temckee8/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt3/0w2_attempt3_20260901.log
StandardError=append:/home/temckee8/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt3/0w2_attempt3_20260901.log
KillSignal=SIGINT
TimeoutStopSec=180
Restart=no

# dicks-0w2-attempt3.timer
[Unit]
Description=Timer for Dicks Laboratory Phase 0W-2 Attempt 3 - fires once at 2026-09-01 16:55:00 America/Chicago
[Timer]
OnCalendar=2026-09-01 16:55:00
Persistent=false
AccuracySec=1s
RemainAfterElapse=no
[Install]
WantedBy=timers.target

# dicks-0w2-attempt3-prearm-inhibit.service
[Unit]
Description=Dicks Laboratory 0W-2 Attempt 3 pre-arm sleep/idle inhibit - bridges from arming until the 16:55 CT launch (temporary experiment scaffolding)
[Service]
Type=simple
Environment=HOME=/home/temckee8
ExecStart=/usr/bin/systemd-inhibit --what=sleep:idle --why="Dicks Laboratory 0W-2 Attempt 3 pre-arm hold until 16:55 CT launch" /usr/bin/sleep 86400
Restart=no

# dicks-0w2-attempt3-memsample.service
[Unit]
Description=Dicks Laboratory 0W-2 Attempt 3 memory/trajectory sampler (one append per activation; ~15 min cadence via .timer)
[Service]
Type=oneshot
WorkingDirectory=/home/temckee8/Documents/REPOs/copper
Environment=HOME=/home/temckee8
ExecStart=/usr/bin/bash /home/temckee8/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt3/mem_sample.sh

# dicks-0w2-attempt3-memsample.timer
[Unit]
Description=Timer for Dicks Laboratory 0W-2 Attempt 3 memory sampler - every 15 minutes
[Timer]
OnCalendar=*-*-* *:00/15:00
Persistent=false
AccuracySec=5s
[Install]
WantedBy=timers.target
```

## FV. 0W-2C conclusions

1. **Why did the DXLink credential expire ~4 h after Tuesday's connect when its lifetime is ~24 h?** Because the 24 h clock started at the **Monday pre-arm preflight** (`preflight_credentials.py` calls `get_api_quote_token()`), and tastytrade's `/api-quote-tokens` returns the **same token with its original `expires-at`** on repeated requests within validity (live-tested: 24 h lifetime, identical token on a 2 s-apart re-request, expiry not advancing). Tuesday's 17:00 collector fetched that ~20-h-old token and had ~4 h left. `PREFLIGHT TOKEN SIDE EFFECT: CONFIRMED`. The expired credential was the **quote token**, not the OAuth REST token; the reconnect's OAuth refresh was a secondary effect of a stale ~15 min REST token.
2. **Was Attempt-3's memory growth process memory or page cache, and why did finalization hit ~2.2 GB?** The steady-state cgroup figure (~638 MB) is **mostly reclaimable SQLite page cache** (`MemoryCurrent` tracked DB size ~1:1, swap stayed 0); true process anon RSS was likely low-100s of MB — "working set grew to 638 MB" overstates it, and 0W-2C recommends per-PID RSS + `memory.stat` sampling next run to measure it. The **~2.2 GB `MemoryPeak` is a confirmed finalization defect**: `_write_closing_summary()` materialises all 938,891 trade rows as dataclasses just to `len()` them — **measured +1,514 MB / 22 s**, versus `SELECT COUNT(*)` at **+0 MB / 1.5 s**. `FINALIZATION MEMORY: DEFECT CONFIRMED` (non-blocking here, scales linearly).

Neither finding is fixed in this audit. Recommended smallest corrections: (a) stop the preflight fetching a quote token; (b) add a `COUNT(*)` helper and use it in the two closing-summary call sites; (c) log `quote_token_remaining_seconds_at_connect`. All require Product Owner sign-off. **No proactive-reconnect machinery** should be added before (a) is tried.

## FW. Files changed / Git (0W-2C)

Only `docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md` (still untracked). No source files changed. `scripts/dicks_lab_quote_rate_experiment.py` untracked, unchanged. `git diff --check` clean. No commit, no push. (Operational: 5 temporary `dicks-0w2-attempt3*` systemd unit files removed from `~/.config/systemd/user/` — outside the repo, definitions preserved in FU.)

---

# ADDENDUM — 0W-2D: Credential-Lifetime + Finalization-Memory Correction

**Committed:** `c5be3ffc8f49b59d1f3fa7a40518097f99d49337` on `master`, pushed to
`origin/master` 2026-09-03 16:12 CT. Rebased once onto concurrent upstream
commits `b1e8c25` / `1c433e3` (no file overlap; clean).

Product Owner accepted the 0W-2C root causes (`PREFLIGHT TOKEN SIDE EFFECT:
CONFIRMED`; `FINALIZATION MEMORY: DEFECT CONFIRMED`). 0W-2D is exactly three
production corrections plus tests. `0W-2` stays OPEN (`KNOWN_GAP = 0` **and**
`SUSPECTED_GAP = 0` still required); bar unchanged. `0W-3` stays CLOSED.
No proactive-reconnect machinery, no hardware change, no SQLite durability
change. 0W-4 / 0W-5b / 0X / 0Y not started.

## GA. Correction A — preflight must not obtain a quote token

- New `apps/dicks_laboratory/src/dicks_laboratory/preflight.py`:
  `run_credential_preflight(client, display_symbol, expected_streamer_symbol)`
  returns a `CredentialPreflightResult` (booleans + a count, no secrets). It
  makes **one** authenticated `list_futures()` call -- which exercises the
  OAuth refresh, REST reachability, and the futures endpoint at once -- then
  checks the display -> streamer symbol mapping. It **never** calls
  `get_api_quote_token()`.
- New tracked script `scripts/dicks_lab_preflight.py` wires that function to
  `TastytradeClient` + `.env` and prints `rest_reachable`,
  `futures_endpoint_usable count=N`, `symbol_/ESU6_resolves`,
  `streamer_symbol_matches_/ESU26:XCME`, `quote_token_requested=false`,
  `PREFLIGHT_RESULT=PASS|FAIL` (exit 1 on FAIL).
- The old per-attempt scaffolding `apps/dicks_laboratory/data/0w2_attempt3/
  preflight_credentials.py` (which *did* call `get_api_quote_token()`) is
  data-dir, untracked, and superseded -- future arming runs
  `scripts/dicks_lab_preflight.py`.
- Operational doc updated: `RESILIENT_LONG_RUNNING_CAPTURE.md` -> `## CLI` ->
  new "Pre-arm preflight (0W-2D)" and "Connect-time quote-token lifetime
  guard (0W-2D)" subsections.

## GB. Correction B — safe quote-token lifetime observability

In `scripts/dicks_lab_collect_es.py`:
- `_parse_api_timestamp()` -- tolerant ISO parse of `issued-at` / `expires-at`
  (`+00:00` and `Z` spellings; junk -> `None`, never raises).
- `_quote_token_lifetime(token_data, now=None)` -> `(issued_at, expires_at,
  remaining_seconds)`.
- `fresh_collector()` now logs, on every acquisition (initial + reconnect):
  `quote_token_issued_at=<iso> quote_token_expires_at=<iso>
  quote_token_remaining_seconds=<int>` on the existing
  `fresh_collector: quote_token_requested=true ...` stderr line.
- **Never** logged: token value, token hash, Authorization header, refresh
  token, account id. Only the two non-secret timestamps and a derived count.

## GC. Correction D — connect-time lifetime guard

- `_QUOTE_TOKEN_HORIZON_MARGIN_SECONDS = 900.0` (15 min). Rationale is
  documented inline and in `RESILIENT_LONG_RUNNING_CAPTURE.md`: an ordinary ES
  trading date is ~23h and the token is ~24h (0W-2C measured 86,400 s
  exactly), so a genuinely fresh token has ~1h of natural headroom; requiring
  `remaining >= duration + 900s` clears a fresh token by a comfortable margin
  while rejecting an early-minted one. Not an arbitrary large margin, not a
  refresh mechanism.
- `fresh_collector(enforce_horizon_seconds: float | None = None)`: the
  **initial** launch calls `fresh_collector(duration_seconds)`; if
  `remaining_seconds` is known and `< duration_seconds + 900`, it raises
  `typer.BadParameter` with an explicit safe diagnostic (no secrets) and the
  canonical capture is never opened. **Reconnects** call `fresh_collector()`
  with no horizon -- a freshly minted token on a mid-session reconnect is
  normal and must not abort a running capture; the existing KNOWN_GAP
  machinery still covers any real future expiry.

## GD. Correction C — closing-summary counting via SQL COUNT(*)

- New `LaboratoryStore.count_trade_observations(dataset_id) -> int`:
  `SELECT COUNT(*) FROM trade_observations WHERE dataset_id = ?`. O(1) memory.
- `long_running_capture.py` call-site corrections (audited fresh; the
  0W-2C line numbers had shifted):
  - resume path: `accepted_count = len(store.load_trade_observations(...))`
    -> `accepted_count = store.count_trade_observations(dataset_id)`
  - `_write_closing_summary()`: `trades = store.load_trade_observations(...)`
    + `accepted_trade_count=len(trades)` -> `accepted_trade_count =
    store.count_trade_observations(dataset_id)` used directly.
- `load_trade_observations()` unchanged and still used everywhere real
  observations are needed (analytics, audit, developing series).
- `compute_sha256()` untouched (already 1 MiB-chunk streamed; 0W-2C confirmed
  it is not the memory defect).

## GE. Finalization-memory regression proof (structural, no RSS thresholds)

`apps/dicks_laboratory/tests/test_closing_summary_no_materialization.py`
wraps a real store in a spy whose `load_trade_observations` raises
`AssertionError` and whose `count_trade_observations` is counted, then calls
`_write_closing_summary`:
- `load_trade_observations` is **never** reached.
- `count_trade_observations` **is** called.
- `accepted_trade_count` in the written summary equals the prior
  `len(load_trade_observations(...))` semantics; `rejected_record_count`,
  `deferred_event_count`, `known_gap_count`, `suspected_gap_count` unchanged.
- second call is a frozen-snapshot no-op (would explode on the spy if it
  re-materialized).

## GF. Attempt-3 DB capacity comparison

Not re-run in 0W-2D. The directional numbers are the 0W-2C measurement on the
real Attempt-3 DB (read-only, `getrusage` max-RSS in a child process):

| Path | Wall | max-RSS delta |
|---|---|---|
| `SELECT COUNT(*)` (the new `count_trade_observations` query) | 1.5 s | +0 MB (~33 MB) |
| `load_trade_observations()` -> `len()` (removed from the count sites) | 22.3 s | ~1,514 MB |

## GG. Tests

| Suite | Result |
|---|---|
| new: `test_count_trade_observations.py` (0 / N / multi-dataset isolation / == full-load len) | 4 pass |
| new: `test_closing_summary_no_materialization.py` (structural no-materialization + count regression + frozen snapshot) | 3 pass |
| new: `test_preflight.py` (no quote-token call; PASS on resolved symbol; FAIL on wrong streamer / missing symbol / REST error; script never references `get_api_quote_token`) | 6 pass |
| new: `test_quote_token_lifetime.py` (ISO parse `+00:00`/`Z`/junk; remaining-seconds math; guard blocks short token; guard allows fresh 24h token) | 6 pass |
| targeted total | **19 pass** |
| `apps/dicks_laboratory/tests` | **325 pass** |
| `apps/K9/tests` | **197 pass** (pre-rebase); **199 pass** (post-rebase, upstream added 2) |
| full repo `uv run pytest -q` | **1181 pass**, 0 fail (post-rebase) |
| `ruff check` (10 changed/new files) | All checks passed |
| `git diff --check` | clean |

## GH. Attempt 4 — NOT ARMED

`0W-2D` correction/validation/commit/push completed at **2026-09-03 16:12 CT**.
The conditional Attempt-4 launch window was **16:55 CT the same day** (~43 min
later). Safely arming requires: 5 fresh temporary systemd units for
`0w2_attempt4/`, a **new** enhanced memory sampler (0W-2D §13/§U mandate
per-PID `VmRSS`/`VmHWM`/`smaps_rollup` + cgroup `memory.stat` breakdown --
the Attempt-3 `mem_sample.sh` only captured `MemoryCurrent`/`MemoryPeak` and
must be rewritten and dry-run), a live `dicks_lab_preflight.py` broker check,
and timer verification. That cannot be done without rushing, which 0W-2D §17
forbids ("Do not rush tests to catch the market").

```
ATTEMPT 4: NOT ARMED — MISSED SAFE LAUNCH WINDOW
```

**Calendar (verified):** Labor Day is **Mon 2026-09-07**. CME E-mini S&P 500
trades Sun-Fri 17:00->16:00 CT with a daily 16:00-17:00 CT maintenance halt.
**Fri 2026-09-04 is an ordinary trading day** (the Friday *before* the long
weekend, not the holiday) -- tonight's Thu 09-03 17:00 -> Fri 09-04 16:00 CT
session was a valid Attempt-4 target and agrees with our session model
(`sessions.py`: `open 17:00`, `close 16:00`, `maintenance 16:00-17:00`,
"Ordinary CME schedule only"). It simply cannot be armed safely in the time
remaining. There is **no** Friday-night session (weekly close Fri 16:00 CT;
Globex reopens Sun 17:00 CT).

**Recommended next target (do NOT arm without reporting first, per §18):**
the Sun 09-06 reopen through Labor Day Mon 09-07 is a holiday-shortened
session. The first **unambiguously** ordinary full session clear of the
holiday on both sides is:

```
service launch:   Tue 2026-09-08 16:55 CT
session open:      Tue 2026-09-08 17:00 CT
canonical trading_date: 2026-09-09
session close:     Wed 2026-09-09 16:00 CT
duration:          ~83,700 s (~23h 15m)
data dir:          apps/dicks_laboratory/data/0w2_attempt4/
```

(The Mon 09-07 17:00 -> Tue 09-08 16:00 session opens at the normal time but
immediately follows the shortened holiday session; the Tuesday launch is the
cleaner proof.)

## GI. Attempt-4 credential + acceptance expectations (when it is armed)

- Pre-arm: `scripts/dicks_lab_preflight.py` only -- **no** quote token.
- At collector startup, the log must show
  `quote_token_issued_at` / `quote_token_expires_at` /
  `quote_token_remaining_seconds` with `remaining_seconds` >~ `83,700 + 900`
  (a fresh ~24h token). If the guard fires, the launch aborts loudly with a
  safe diagnostic -- that itself would confirm the 0W-2C diagnosis.
- Acceptance bar unchanged: trading-date boundary coverage PASS; `KNOWN_GAP =
  0`; `SUSPECTED_GAP = 0`; `writer_overloaded = false`; source-order
  accounting complete; SQLite integrity ok; manifest/checksum valid.
- Attempt 4 is completion of 0W-2. **0W-4 stays NOT STARTED** even once
  Attempt 4 is armed.

## GJ. Attempt-4 memory-sampling method (to build at arming time)

Operational sampler only -- **no** collector source change. ~15 min cadence,
one CSV row per tick, capturing for the collector Python PID:
`/proc/<pid>/status` -> `VmRSS`, `VmHWM`, `VmSize`;
`/proc/<pid>/smaps_rollup` -> `Rss`, `Pss`, `Private_Dirty`, `Private_Clean`;
and cgroup: `memory.current`, `memory.peak`, `memory.stat` (`anon`, `file`,
`inactive_file`, `active_file`, `slab`, `sock`); plus the DB file size. This
separates real process/private memory from reclaimable SQLite page cache --
the open question from 0W-2C §FN (the Attempt-3 sampler recorded only
`MemoryCurrent`/`MemoryPeak`, so the anon-vs-page-cache split there is
inferred, not measured).

## GK. Files changed / Git (0W-2D)

Committed in `c5be3ff` (10 files, +644 / -14):
`apps/dicks_laboratory/src/dicks_laboratory/store.py`,
`apps/dicks_laboratory/src/dicks_laboratory/long_running_capture.py`,
`apps/dicks_laboratory/src/dicks_laboratory/preflight.py` (new),
`scripts/dicks_lab_collect_es.py`,
`scripts/dicks_lab_preflight.py` (new),
`apps/dicks_laboratory/tests/test_count_trade_observations.py` (new),
`apps/dicks_laboratory/tests/test_closing_summary_no_materialization.py` (new),
`apps/dicks_laboratory/tests/test_preflight.py` (new),
`apps/dicks_laboratory/tests/test_quote_token_lifetime.py` (new),
`docs/dicks_laboratory/RESILIENT_LONG_RUNNING_CAPTURE.md`.

**Not committed** (as instructed): `docs/dicks_laboratory/
FULL_SESSION_MULTIDAY_SOAK_REPORT.md` (this file), `scripts/
dicks_lab_quote_rate_experiment.py`. Both remain untracked. `git status` after
push: `## master...origin/master` (in sync) plus those two `??` entries.

---

# 0W-2 Attempt 4 — ARMED (gap-free full trading-date proof)

**Armed:** 2026-09-03 16:31 CT on `robby`. **Operational only — no source change.**
`0W-2D` is accepted / closed (`c5be3ff`). This run is the remaining 0W-2
completeness proof; the acceptance bar (`KNOWN_GAP = 0` **and**
`SUSPECTED_GAP = 0`, full boundary coverage, FINALIZED, writer not overloaded,
complete source-order accounting, SQLite ok, manifest+checksum valid) is
unchanged. 0W-4 / 0W-5b / 0X / 0Y NOT started; Attempt 4 is still 0W-2.

## HA. Target session — calendar re-verified

| | |
|---|---|
| service launch | **Tue 2026-09-08 16:55:00 CT** |
| session open | Tue 2026-09-08 17:00:00 CT |
| canonical `trading_date` | **2026-09-09** |
| session close | Wed 2026-09-09 16:00:00 CT |
| collector duration end | ~Wed 2026-09-09 16:10:00 CT (10 min into maintenance) |
| next 17:00 open | Wed 2026-09-09 17:00 CT — NOT reached; no second dataset |

`sessions.py` `resolve_anchor(SESSION_OPEN, 2026-09-09)` → `2026-09-08
22:00:00Z` = Tue 17:00:00 CT; `US_CASH_OPEN` → `2026-09-09 13:30:00Z` = Wed
08:30 CT; `close_time_local = 16:00`. `classify_es_session`: Tue 17:00 CT →
IN_SESSION, trading_date 2026-09-09; Wed through 16:00 CT → IN_SESSION; 16:00
CT → maintenance. Ordinary. **Labor Day is Mon 2026-09-07** — two days before;
it does not touch this Tue 17:00 → Wed 16:00 window. CME published schedule
(equity-index Globex Sun–Fri 17:00→16:00 CT, daily 16:00–17:00 maintenance)
agrees. 0W-3 already CLOSED — no rotation proof needed.

## HB. Collector provenance

`branch master`; `HEAD == origin/master == c5be3ffc8f49b59d1f3fa7a40518097f99d49337`;
tracked collector source (`scripts/`, `apps/dicks_laboratory/src/`) clean vs
HEAD. The closing summary will record
`collector_git_commit = c5be3ffc8f49b59d1f3fa7a40518097f99d49337` and
`collector_version = phase-0v-serious-collection-v1`.

## HC. Runtime directory

`apps/dicks_laboratory/data/0w2_attempt4/` (fresh; gitignored). Contents at
arming: `mem_sample.sh` (enhanced sampler), `mem_samples.csv` (header only).
Expected products: `es_20260909_<id>.sqlite3` + `.manifest.json`,
`0w2_attempt4_20260908.log`, populated `mem_samples.csv`. Not mixed with any
prior attempt.

## HD. Preflight result (0W-2D `scripts/dicks_lab_preflight.py`, run 2026-09-03 16:31 CT)

```
rest_reachable=true
futures_endpoint_usable=true count=530
symbol_/ESU6_resolves=true
streamer_symbol_matches_/ESU26:XCME=true
quote_token_requested=false
PREFLIGHT_RESULT=PASS
```

Exit 0. **`get_api_quote_token()` was NOT called** — no quote-token 24h clock
started at arming. This is the direct correction for the Attempt-3 gap.

## HE. Temporary systemd units (all under `~/.config/systemd/user/`)

| Unit | Type | Trigger / role |
|---|---|---|
| `dicks-0w2-attempt4.timer` | timer | `OnCalendar=2026-09-08 16:55:00`, `Persistent=false`, `AccuracySec=1s`, `RemainAfterElapse=no`. **enabled, active (waiting)** → next elapse **Tue 2026-09-08 16:55:00 CDT**. |
| `dicks-0w2-attempt4.service` | simple | `ExecStart=/usr/bin/systemd-inhibit --what=sleep:idle --why="…" /home/temckee8/.local/bin/uv run python scripts/dicks_lab_collect_es.py --duration 83700 --data-dir apps/dicks_laboratory/data/0w2_attempt4`. `WorkingDirectory` = repo root. `MemoryAccounting=yes`. `KillSignal=SIGINT`, `TimeoutStopSec=180`, `Restart=no`. stdout+stderr append → `…/0w2_attempt4_20260908.log`. |
| `dicks-0w2-attempt4-memsample.timer` | timer | `OnCalendar=*-*-* *:00/15:00` (15-min baseline) **plus** `2026-09-09 15:50..59:00/20` and `2026-09-09 16:00..09:00/20` (20-s cadence across the close/finalization window, 0W-2D §13). **enabled, active** now → produces `inactive`-marked rows until Tue, exactly as Attempt 3. |
| `dicks-0w2-attempt4-memsample.service` | oneshot | `ExecStart=/usr/bin/bash …/0w2_attempt4/mem_sample.sh`. |
| `dicks-0w2-attempt4-prearm-inhibit.timer` | timer | `OnCalendar=2026-09-08 16:45:00`. **enabled, active (waiting)** → next elapse **Tue 2026-09-08 16:45:00 CDT** (10 min before launch — NOT held for days). |
| `dicks-0w2-attempt4-prearm-inhibit.service` | simple | `ExecStart=/usr/bin/systemd-inhibit --what=sleep:idle --why="…" /usr/bin/sleep 1200` (holds sleep:idle 16:45 → 17:05 Tue). |

`systemd-analyze --user verify` clean on all 6. `daemon-reload` done.
`list-timers` shows the three timers with the exact next-elapse times above.
The memsample oneshot was manually triggered once at arming (`Result=success`,
`ExecMainStatus=0`) and produced a well-formed `inactive` row; the CSV was
then reset to header-only.

## HF. Sleep / idle / lid / power

- `sleep:idle` protection: `prearm-inhibit` (16:45→17:05 Tue) then the main
  service's own `systemd-inhibit` wrapper (16:55 Tue → ~16:10 Wed). Continuous
  from 16:45 Tue to 16:10 Wed. **Nothing is inhibited between now and Tue
  16:45** — the machine may sleep normally until then.
- `loginctl … Linger = yes` (units survive with no login session).
- AC: `ADP1/online = 1` (Mains). GNOME `sleep-inactive-ac-type = nothing`
  (no AC idle-suspend).
- **RESIDUAL DEPENDENCY — the laptop lid must stay physically OPEN from
  Tue 16:45 CT through Wed 16:10 CT.** `HandleLidSwitch` is at the logind
  default (`suspend`) and is *not* covered by a `sleep:idle` inhibitor
  (same caveat as Attempts 1–3).
- Wi-Fi connected (no switch to Ethernet — 0W-2D §19: validate the corrected
  software in the same environment).
- No permanent power-setting changes.

## HG. Enhanced memory sampler (0W-2D §13 / soak §GJ)

`apps/dicks_laboratory/data/0w2_attempt4/mem_sample.sh`. Per tick it locates
the collector **python** PID inside the service cgroup (`cgroup.procs` →
`/proc/<pid>/comm` == python*) and records:

- process: `/proc/<pid>/status` → `VmRSS`, `VmHWM`, `VmSize`;
  `/proc/<pid>/smaps_rollup` → `Rss`, `Pss`, `Private_Dirty`, `Private_Clean`
- service cgroup: `memory.current`, `memory.peak`; `memory.stat` → `anon`,
  `file`, `inactive_file`, `active_file`, `sock`, `slab`
- systemd view: `MemoryCurrent`, `MemoryPeak`, `TasksCurrent`, `CPUUsageNSec`
- dataset file size via `stat()` only — **never opens or queries the SQLite DB**
- ISO-8601 timestamp; missing values written as `NA`

CSV header (23 columns): `timestamp,main_active,pid,proc_VmRSS_kB,
proc_VmHWM_kB,proc_VmSize_kB,proc_Rss_kB,proc_Pss_kB,proc_Private_Dirty_kB,
proc_Private_Clean_kB,cg_mem_current_bytes,cg_mem_peak_bytes,cg_stat_anon,
cg_stat_file,cg_stat_inactive_file,cg_stat_active_file,cg_stat_sock,
cg_stat_slab,systemd_MemoryCurrent,systemd_MemoryPeak,tasks,cpu_nsec,db_bytes`

Purpose: separate real process RSS/private memory from reclaimable SQLite
filesystem page cache (the inferred-not-measured split in 0W-2C §FN), and
capture the finalization window at 20-s resolution to confirm the ~2.2 GB
Attempt-3 spike is gone now that `_write_closing_summary` uses
`SELECT COUNT(*)` (0W-2D correction C).

## HH. Sampler dry run

- syntax `bash -n` clean.
- inactive path (no service): well-formed row, `main_active=inactive`, all
  process/cgroup fields `NA`.
- active path exercised against a transient `python3 -c "time.sleep(90)"`
  unit named `dicks-0w2-attempt4.service`: correctly resolved the PID and read
  `VmRSS=9032 kB`, `VmHWM=9032 kB`, `VmSize=20180 kB`, `Rss=9032`, `Pss=4193`,
  `Private_Dirty=2836`, `Private_Clean=600`, cgroup `memory.current=3149824`,
  `memory.peak=3149824`, `memory.stat` `anon=2904064 file=0 inactive_file=0
  active_file=4096 sock=0 slab=33296`, `tasks=1`, `db_bytes=NA`. Transient
  unit removed; CSV reset to header-only.

## HI. Quote-token runtime expectations (the real 0W-2C test)

At ~16:55–17:00 Tue the collector's `fresh_collector()` will call
`get_api_quote_token()` for the first time this run and log (stderr → the run
log), **without** the token/hash/header/refresh-token/account-id:

```
fresh_collector: quote_token_requested=true fresh_dxlink_collector=true oauth_refreshed=<bool> \
  quote_token_issued_at=<iso> quote_token_expires_at=<iso> quote_token_remaining_seconds=<int>
```

Connect-time guard (initial launch only): opens the canonical capture **iff**
`remaining_seconds >= 83700 + 900`. A genuinely fresh 24 h token → ~86,400 s
remaining vs 84,600 s required → **~1,800 s (30 min) headroom** → passes.

If the guard **rejects** the token, the service fails with an explicit safe
`typer.BadParameter` diagnostic and no canonical dataset is opened. **Do NOT
bypass it, reduce the 900 s margin, or hand-reconnect around it** — that
outcome is itself important evidence that provider token behaviour differs
from the 0W-2C model. Preserve the log and report.

## HJ. Expected timeline

| Instant (CT) | Event |
|---|---|
| Tue 2026-09-08 16:45:00 | `prearm-inhibit` timer → `systemd-inhibit sleep:idle` for 1200 s |
| Tue 2026-09-08 16:55:00 | `dicks-0w2-attempt4.timer` fires → service starts → `uv`/collector boot, symbol resolve, first `get_api_quote_token()`, lifetime guard |
| Tue 2026-09-08 17:00:00 | `CAPTURE_STARTED` + fresh `SOURCE_CONNECTED`; Dataset A opens; `trading_date 2026-09-09`; first `mem_samples.csv` active row |
| Wed 2026-09-09 08:30 | U.S. cash-equity open (08:25–08:45 CT activity/capacity window) |
| Wed 2026-09-09 15:50–16:10 | memory sampler at 20-s cadence across close + finalization |
| Wed 2026-09-09 16:00:00 | scheduled session close → writer drain → Dataset A `FINALIZED` + manifest + checksum |
| Wed 2026-09-09 ~16:10:00 | overall `--duration 83700` deadline reached during maintenance → service exits 0 |
| Wed 2026-09-09 17:00:00 | NOT reached — no second trading-date dataset |

## HK. Acceptance bar (unchanged)

`trading_date = 2026-09-09` · capture from the actual 17:00 CT open ·
continuous through the actual 16:00 CT close · `lifecycle = FINALIZED` ·
**`KNOWN_GAP = 0`** · **`SUSPECTED_GAP = 0`** · `writer_overloaded = false` ·
source-order accounting complete/explained · `PRAGMA integrity_check = ok` ·
manifest present · checksum valid. A real auto-recovered disconnect that
produces any `KNOWN_GAP` is `ENDURANCE PASS / DATA COMPLETENESS FAIL` — not a
0W-2 close. Writer settings unchanged from 0W-2B (`queue_maxsize=50000`,
`batch cap=250`, explicit-failure overload, no silent drops).

## HL. Human status / cancel commands (no Claude / terminal / desktop needed after arming)

```bash
# timers
systemctl --user list-timers --all | grep -E 'UNIT|attempt4'
# main service state / result (after Tue 16:55)
systemctl --user status dicks-0w2-attempt4.service
# live run log
tail -f ~/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt4/0w2_attempt4_20260908.log
# memory trace
tail -f ~/Documents/REPOs/copper/apps/dicks_laboratory/data/0w2_attempt4/mem_samples.csv

# CANCEL before launch (any time before Tue 16:55 CT)
systemctl --user disable --now dicks-0w2-attempt4.timer dicks-0w2-attempt4-prearm-inhibit.timer dicks-0w2-attempt4-memsample.timer

# CLEAN STOP while running (SIGINT → deliberate clean stop → FINALIZED, truthfully partial)
systemctl --user stop dicks-0w2-attempt4.service
```

If the machine misses the Tue 16:55 CT launch (`Persistent=false`, so a missed
trigger does **not** fire late): **do not start late; a partial trading date
cannot become Attempt 4.** Report and pick the next ordinary session.

## HM. Git

Committed 0W-2D source is already on `origin/master` (`c5be3ff`). Attempt-4
arming is operational only — **no** new source or test changes. `git status`:
`## master...origin/master` (in sync) plus the two untracked open-phase files
(`FULL_SESSION_MULTIDAY_SOAK_REPORT.md`, `scripts/dicks_lab_quote_rate_experiment.py`).
This report is not committed.

---

# 0W-H1 — Labor Day Holiday Session Characterization

> **EXPLORATORY / OUT-OF-ORDER OPPORTUNISTIC STUDY.** This is **not** a numbered
> prerequisite between 0W-2D and 0W-2 Attempt 4, and it does **not** close,
> modify, delay, or substitute for 0W-2. `0W-2 Attempt 4` remains the formal
> acceptance test, armed and untouched for Tue 2026-09-08 16:55 CT. 0W-H1 runs
> the **same committed collector `c5be3ff`** on the once-a-year Labor Day
> schedule to observe how the ordinary-session-oriented Laboratory behaves when
> CME's holiday trade-date semantics differ from "17:00 CT -> 16:00 CT next
> calendar day = one ordinary trading date". A model/CME mismatch here is the
> desired finding, not a failure. Gap-free is **not** required for H1.

**Armed:** 2026-09-03 16:50 CT on `robby`. Operational only; **no source change**
(none authorized for H1). Two independent legs (a ~24 h DXLink quote token
cannot cover the ~47 h holiday span, and the 0W-2D connect-time horizon guard
correctly refuses a horizon longer than the token -- not bypassed).

## IA. CME Labor Day 2026 ES schedule -- VERIFIED (secondary sources; CME product page timed out)

| Boundary | America/Chicago | UTC |
|---|---|---|
| Sunday open | **Sun 2026-09-06 17:00:00 CT** | 2026-09-06 22:00 |
| Labor Day early halt (equity-index / ES) | **Mon 2026-09-07 ~12:00:00 CT (noon)** | 2026-09-07 17:00 |
| Labor Day reopen | **Mon 2026-09-07 17:00:00 CT** | 2026-09-07 22:00 |
| Tuesday regular Globex close | **Tue 2026-09-08 16:00:00 CT** | 2026-09-08 21:00 |

```
CME HOLIDAY SCHEDULE: VERIFIED
```

Converging references: crosstrade.io CME-2026, metrotrade.com, discounttrading.com,
market-clock.com -- all give the equity-index Monday-holiday early halt as
**12:00 CT** with a **17:00 CT** reopen, standard **16:00 CT** Tuesday close.
CME publishes finalized product-specific holiday hours ~2 weeks out; the
`cmegroup.com` calendar pages did not load during arming. **If CME's finalized
ES notice states a different halt minute, that time governs -- the exact halt
minute only affects H1 *analysis* (where the last pre-halt trade lands), not
arming.** No collector logic keys off the halt time.

## IB. CME holiday trade-date semantics

Per the CME Labor Day notice (and crosstrade's summary: *"Day orders entered
after Sunday's pre-opening are for Tuesday's trade date and continue working
until Tuesday's Globex close"*): the whole holiday period **Sun 2026-09-06
17:00 CT -> Tue 2026-09-08 16:00 CT**, including the Sunday-evening/Monday-
morning pre-halt sub-session AND the Monday-17:00-reopen -> Tuesday sub-session,
is **CME exchange trade date Tuesday 2026-09-08**. There is no Monday
(2026-09-07) exchange trade date this week.

## IC. Current Laboratory model prediction (`sessions.py`, unchanged, `ES_GLOBEX` ordinary rule)

`classify_es_session` / `resolve_current_trading_date` for the holiday window:

| Instant (CT) | model state | model `trading_date` |
|---|---|---|
| Sun 09-06 17:00 (open) | IN_SESSION | **2026-09-07** |
| Sun 09-06 20:00 | IN_SESSION | 2026-09-07 |
| Mon 09-07 08:30 | IN_SESSION | 2026-09-07 |
| Mon 09-07 11:59 (pre-halt) | IN_SESSION | 2026-09-07 |
| **Mon 09-07 12:00 (CME halt)** | IN_SESSION | 2026-09-07 |
| Mon 09-07 14:00 (holiday quiet) | IN_SESSION | 2026-09-07 |
| Mon 09-07 15:59 | IN_SESSION | 2026-09-07 |
| **Mon 09-07 16:00** | CLOSED_INTERVAL (ordinary maintenance) | none |
| Mon 09-07 16:30 | CLOSED_INTERVAL | none |
| **Mon 09-07 17:00 (CME reopen)** | IN_SESSION | **2026-09-08** |
| Mon 09-07 20:00 | IN_SESSION | 2026-09-08 |
| Tue 09-08 08:30 | IN_SESSION | 2026-09-08 |
| Tue 09-08 15:59 | IN_SESSION | 2026-09-08 |
| Tue 09-08 16:00 (CME close) | CLOSED_INTERVAL | none |

Collector consequence (`run_long_horizon_capture`, verified by simulation):
- **H1A** opens Dataset A `trading_date=2026-09-07`, model `session_close =
  Mon 2026-09-07 16:00 CT` -> FINALIZES there; overall deadline (Mon ~16:10)
  then ends the run inside the model maintenance window -> **one dataset**,
  `es_20260907_<id>.sqlite3`.
- **H1B** opens Dataset A `trading_date=2026-09-08`, model `session_close =
  Tue 2026-09-08 16:00 CT` -> FINALIZES there -> **one dataset**,
  `es_20260908_<id>.sqlite3`.

## ID. CME-vs-Laboratory mismatch table

| Time / concept | CME expectation | Current Lab model | Match? |
|---|---|---|---|
| Sun 09-06 17:00 open | session begins; activity -> **trade date Tue 2026-09-08** | session begins; `trading_date = 2026-09-07` | **MISMATCH** (date label) |
| Sun evening / Mon overnight | trade date Tue 2026-09-08 | `trading_date = 2026-09-07` | **MISMATCH** (date label) |
| **Mon 09-07 ~12:00 CT** | **early halt** -- market closes, feed goes quiet until 17:00 | IN_SESSION, no halt concept; expects continuous data | **MISMATCH** (no holiday-halt model) |
| Mon 09-07 12:00-17:00 CT | closed / no trading (legitimate ~5 h dead feed) | IN_SESSION -- "quiet, not a gap" territory | **MISMATCH** (model thinks in-session) |
| **Mon 09-07 16:00 CT** | nothing (no Monday boundary this week) | CLOSED_INTERVAL -> H1A Dataset A **FINALIZES** here | **MISMATCH** (phantom close, 4 h into the real dead period) |
| Mon 09-07 16:00-17:00 CT | still closed (part of the 12:00->17:00 halt) | ordinary maintenance interval | partial coincidence, wrong reason |
| **Mon 09-07 17:00 CT reopen** | session resumes; trade date Tue 2026-09-08 | fresh session; `trading_date = 2026-09-08` | **MATCH** (date label + boundary) |
| Mon night / Tue | trade date Tue 2026-09-08 | `trading_date = 2026-09-08` | **MATCH** |
| **Tue 09-08 16:00 CT** | regular Globex close, trade date Sep 8 ends | CLOSED_INTERVAL -> H1B Dataset A FINALIZES | **MATCH** |

Net: H1A's whole capture carries the "wrong" ordinary date label (`2026-09-07`
vs CME `2026-09-08`) **and** straddles an un-modelled ~5 h holiday halt with a
phantom 16:00 CT finalize. H1B lines up with CME on both date and boundaries.
**This is captured deliberately and not corrected before the experiment.**

## IE. Why H1 uses two legs

1. **Token lifetime.** DXLink quote token ~24 h; the holiday span is ~47 h. One
   collector cannot cover it, and the 0W-2D connect-time guard (`remaining >=
   duration + 900 s`) would rightly reject a 47 h horizon. Not bypassed.
2. **Deliberate comparison.** Leg A (Sunday-open, ordinary-model
   `trading_date 2026-09-07`, spans the halt + phantom close) vs Leg B
   (Monday-reopen, ordinary-model `trading_date 2026-09-08`, matches CME) --
   two datasets from identical code that let us see exactly where the ordinary
   model and CME's holiday trade date diverge.

## IF. H1A -- units, timer, directory

| | |
|---|---|
| units | `dicks-0wh1a.service` / `.timer`; `dicks-0wh1a-prearm-inhibit.service` / `.timer`; `dicks-0wh1a-memsample.service` / `.timer` |
| prearm | `dicks-0wh1a-prearm-inhibit.timer` -> **Sun 2026-09-06 16:45:00 CT** (`systemd-inhibit sleep:idle` for 1500 s) |
| launch | `dicks-0wh1a.timer` -> **Sun 2026-09-06 16:55:00 CT** (`Persistent=false`, `AccuracySec=1s`) |
| command | `/usr/bin/systemd-inhibit --what=sleep:idle --why="…" /home/temckee8/.local/bin/uv run python scripts/dicks_lab_collect_es.py --duration 83700 --data-dir apps/dicks_laboratory/data/0wh1_labor_day/h1a` |
| duration | 83,700 s (~23 h 15 m); overall deadline Mon 2026-09-07 ~16:10 CT |
| hard stop | `RuntimeMaxSec=86400` (SIGINT via `KillSignal=SIGINT`, `TimeoutStopSec=180`) |
| directory | `apps/dicks_laboratory/data/0wh1_labor_day/h1a/` -> `h1a_20260906.log`, `es_20260907_<id>.sqlite3`(+manifest), `mem_samples.csv` |
| expected dataset | `trading_date = 2026-09-07`, open Sun 17:00 CT, FINALIZE Mon 16:00 CT; does **not** reach Mon 17:00 reopen (intentional) |

## IG. H1B -- units, timer, directory

| | |
|---|---|
| units | `dicks-0wh1b.service` / `.timer`; `dicks-0wh1b-prearm-inhibit.service` / `.timer`; `dicks-0wh1b-memsample.service` / `.timer` |
| prearm | `dicks-0wh1b-prearm-inhibit.timer` -> **Mon 2026-09-07 16:45:00 CT** (`systemd-inhibit sleep:idle` for 1500 s) |
| launch | `dicks-0wh1b.timer` -> **Mon 2026-09-07 16:55:00 CT** (`Persistent=false`, `AccuracySec=1s`) |
| command | `/usr/bin/systemd-inhibit … uv run python scripts/dicks_lab_collect_es.py --duration 83700 --data-dir apps/dicks_laboratory/data/0wh1_labor_day/h1b` |
| duration | 83,700 s; overall deadline Tue 2026-09-08 ~16:10 CT (clean self-terminate) |
| **hard stop** | **`RuntimeMaxSec=84600`** -> systemd SIGINT by **Tue 2026-09-08 16:25:00 CT** at the latest, +180 s to SIGKILL = fully dead by ~16:28 CT -- **>= 17 min before 0W-2 Attempt 4's Tue 16:45 CT pre-arm** |
| directory | `apps/dicks_laboratory/data/0wh1_labor_day/h1b/` -> `h1b_20260907.log`, `es_20260908_<id>.sqlite3`(+manifest), `mem_samples.csv` |
| expected dataset | `trading_date = 2026-09-08`, open Mon 17:00 CT, FINALIZE Tue 16:00 CT (matches CME trade date Sep 8) |

## IH. Token / preflight safety (both legs)

`scripts/dicks_lab_preflight.py` run 2026-09-03 16:50 CT: `rest_reachable=true`,
`futures_endpoint_usable=true count=530`, `symbol_/ESU6_resolves=true`,
`streamer_symbol_matches_/ESU26:XCME=true`, **`quote_token_requested=false`**,
`PREFLIGHT_RESULT=PASS`, exit 0. No DXLink quote token requested at arming.
Each leg obtains its own token at its own ~16:55-17:00 CT startup; the collector
logs `quote_token_issued_at / quote_token_expires_at /
quote_token_remaining_seconds` (never the token/hash/credentials). The 0W-2D
connect-time horizon guard is active for both legs and must not be bypassed; if
it rejects a token, that leg fails safely and the outcome is itself evidence.

## II. Attempt-4 isolation audit

Baseline SHA-256 of all 6 `dicks-0w2-attempt4*` unit files was captured before
any H1 work; re-hashed after writing/reloading all 12 H1 units:

```
6/6 dicks-0w2-attempt4* unit files: BYTE-IDENTICAL to pre-H1 baseline
apps/dicks_laboratory/data/0w2_attempt4/mem_sample.sh: sha256 unchanged
  (b96c79a4729ff645dee509da153b852db1e3678a5755837e7eb3550d09a46014)
dicks-0w2-attempt4.timer trigger: unchanged -> Tue 2026-09-08 16:55:00 CDT
dicks-0w2-attempt4-prearm-inhibit.timer: unchanged -> Tue 2026-09-08 16:45:00 CDT
```

No H1 unit shares a name, `ExecStart`, data directory, log, sampler script, or
CSV with Attempt 4. `daemon-reload` did not alter Attempt-4 unit contents or
enablement. `apps/dicks_laboratory/data/0w2_attempt4/` not touched.

## IJ. Unit validation

`systemd-analyze --user verify` clean on all 12 H1 units. `daemon-reload` done.
All 6 H1 timers `enabled` + `active (waiting)`. Minimal sampler
`apps/dicks_laboratory/data/0wh1_labor_day/h1_mem_sample.sh` (cgroup +
`stat()` only -- never opens SQLite; **separate script + separate per-leg CSVs**
from Attempt 4's `mem_sample.sh`): `bash -n` clean; dry-run both legs produced
well-formed `inactive` rows; both `dicks-0wh1{a,b}-memsample.service` oneshots
triggered via systemd (`Result=success`, status 0); CSVs reset to header-only.
`RuntimeMaxSec` backstops verified by calendar math (IG).

## IK. Timer-armed evidence (chronological)

```
Sun 2026-09-06 16:45:00 CDT   dicks-0wh1a-prearm-inhibit.timer
Sun 2026-09-06 16:55:00 CDT   dicks-0wh1a.timer                 <- H1A launch
Mon 2026-09-07 16:45:00 CDT   dicks-0wh1b-prearm-inhibit.timer
Mon 2026-09-07 16:55:00 CDT   dicks-0wh1b.timer                 <- H1B launch
Tue 2026-09-08 16:45:00 CDT   dicks-0w2-attempt4-prearm-inhibit.timer   (untouched)
Tue 2026-09-08 16:55:00 CDT   dicks-0w2-attempt4.timer                  (untouched) <- Attempt 4
```

One launch per calendar day; no overlap. H1B's hard stop (~Tue 16:28 CT worst
case) precedes Attempt 4's pre-arm (Tue 16:45 CT) by >= 17 min.

## IL. Expected holiday timeline

| Instant (CT) | Expected event |
|---|---|
| Sun 09-06 16:45 | H1A prearm inhibitor |
| Sun 09-06 16:55 | H1A service starts; collector waits for open; first `get_api_quote_token()` + guard |
| Sun 09-06 17:00 | H1A `CAPTURE_STARTED` + `SOURCE_CONNECTED`; Dataset A opens `trading_date 2026-09-07` |
| Mon 09-07 ~12:00 | **CME ES early halt** -- last real trades; feed goes quiet. Watch: does the socket stay up (quiet, no gap) or drop (disconnect -> reconnect attempts against a closed market)? |
| Mon 09-07 12:00-16:00 | legitimate dead feed; model still thinks IN_SESSION. Expect **no** `KNOWN_GAP`/`SUSPECTED_GAP` from mere quiet (accepted principle: quiet != gap) |
| Mon 09-07 16:00 | model `session_close` -> H1A Dataset A **FINALIZES** (`capture_ended_at` 16:00; last retained trade ~12:00) |
| Mon 09-07 ~16:10 | H1A overall deadline in model maintenance -> service exits 0 |
| Mon 09-07 16:45 | H1B prearm inhibitor |
| Mon 09-07 16:55 | H1B service starts |
| Mon 09-07 17:00 | **CME reopen** -> H1B fresh `CAPTURE_STARTED` + `SOURCE_CONNECTED`; Dataset A opens `trading_date 2026-09-08` |
| Tue 09-08 08:30 | U.S. cash-equity open |
| Tue 09-08 16:00 | CME regular close -> H1B Dataset A FINALIZES (matches CME trade date Sep 8) |
| Tue 09-08 ~16:10 | H1B overall deadline -> service exits 0 (hard cap 16:25) |
| Tue 09-08 16:45 / 16:55 | **0W-2 Attempt 4** prearm / launch -- unaffected |

## IM. Key evidence to preserve

For each leg: `systemctl --user status`/`show` (ActiveState, Result, ExecMain*,
MemoryPeak, CPU, RuntimeMaxSec hit?); the run log; the SQLite dataset + manifest;
`mem_samples.csv`. Analytical anchors to recover later (UTC + America/Chicago):
last retained trade **before** the Monday CME halt; whether activity actually
stops near the published halt; whether the quiet interval produced any
`KNOWN_GAP` / `SUSPECTED_GAP` / `SOURCE_DISCONNECTED` (expected: none from quiet
alone); H1A Dataset A `capture_ended_at` / FINALIZE time vs the real halt; H1B
Dataset A open time (Monday reopen) and `SOURCE_CONNECTED`; first retained trade
**after** the Monday 17:00 reopen; Tuesday last retained trade and Dataset A
close. Plus source counts, writer metrics
(`writer_overloaded`, queue depth, persist lag), lifecycle event counts,
`trading_date` each leg's dataset actually recorded, and each leg's
`quote_token_issued_at/expires_at/remaining_seconds`. Rough volume/rate profile
across: Sunday evening, overnight, Labor Day morning, last hour before the halt,
Monday 17:00 reopen, Tuesday overnight, Tuesday 08:30 cash open, Tuesday
afternoon (market-structure characterization only -- no strategy inference; no
VWAP/session-logic change for H1).

## IN. Human status / cancel commands

```bash
# all dicks timers
systemctl --user list-timers --all | grep -E 'UNIT|dicks-0wh1|attempt4'
# a leg's state (after its launch)
systemctl --user status dicks-0wh1a.service      # or dicks-0wh1b.service
tail -f ~/Documents/REPOs/copper/apps/dicks_laboratory/data/0wh1_labor_day/h1a/h1a_20260906.log
tail -f ~/Documents/REPOs/copper/apps/dicks_laboratory/data/0wh1_labor_day/h1b/h1b_20260907.log

# CANCEL a leg before it launches
systemctl --user disable --now dicks-0wh1a.timer dicks-0wh1a-prearm-inhibit.timer dicks-0wh1a-memsample.timer
systemctl --user disable --now dicks-0wh1b.timer dicks-0wh1b-prearm-inhibit.timer dicks-0wh1b-memsample.timer

# CLEAN STOP a running leg (SIGINT -> FINALIZED, truthfully partial)
systemctl --user stop dicks-0wh1a.service        # or dicks-0wh1b.service

# PRIORITY: if H1B is somehow still active near Tue 16:35 CT, stop it immediately
#           (RuntimeMaxSec should already have; this is the manual backstop):
systemctl --user stop dicks-0wh1b.service
# 0W-2 Attempt 4 units are never to be disabled for H1's sake.
```

Missed launch (`Persistent=false`) is **not** run late; a partial holiday
capture is still useful but must be reported, not silently extended.

## IO. Git

No source or test change (none authorized for H1). H1 lives entirely in
`~/.config/systemd/user/dicks-0wh1*` (outside the repo) and
`apps/dicks_laboratory/data/0wh1_labor_day/` (gitignored). `git status`:
`## master...origin/master`, `HEAD == origin/master == c5be3ff`, only the two
pre-existing untracked open-phase files. This report not committed.

## IP. Token-timing correction (2026-09-03 ~17:00 CT) — supersedes IF/IG timer + duration values

**Finding.** 0W-2C proved tastytrade re-serves the *same* DXLink quote token
for its full ~24 h validity. With H1A/H1B/Attempt-4 all acquiring at `~16:55`
on consecutive days, two 24-h-boundary races appear. The unacceptable one:
**H1B's token (issued Mon ~16:55, expiring Tue ~16:55) would expire at
essentially the exact Attempt-4 startup instant**, so Attempt 4 could receive a
seconds-from-expiry token. Attempt 4 has priority. Fix is **operational
scheduling only** — no token-code change, no guard change, no source change.

**Correction: each holiday leg launches 10 min earlier so its ~24 h token
expires ~10 min before the *next* day's `16:55` acquisition; duration is
raised 600 s to keep the same ~16:10 next-day shutdown.**

| Item | Was (IF/IG) | Now |
|---|---|---|
| H1A prearm | Sun 2026-09-06 16:45:00 CT | **Sun 2026-09-06 16:35:00 CT** |
| H1A launch (`dicks-0wh1a.timer`) | Sun 2026-09-06 16:55:00 CT | **Sun 2026-09-06 16:45:00 CT** |
| H1A `--duration` | 83700 | **84300** (23 h 25 m) |
| H1A `RuntimeMaxSec` | 86400 | **84900** (hard stop Mon ~16:20 CT; SIGKILL by ~16:23) |
| H1A overall deadline / clean exit | Mon ~16:10 CT | **Mon ~16:10 CT** (unchanged) |
| H1B prearm | Mon 2026-09-07 16:45:00 CT | **Mon 2026-09-07 16:35:00 CT** |
| H1B launch (`dicks-0wh1b.timer`) | Mon 2026-09-07 16:55:00 CT | **Mon 2026-09-07 16:45:00 CT** |
| H1B `--duration` | 83700 | **84300** |
| H1B `RuntimeMaxSec` | 84600 | **85200** (hard stop Tue ~16:25 CT; SIGKILL by ~16:28) |
| H1B overall deadline / clean exit | Tue ~16:10 CT | **Tue ~16:10 CT** (unchanged) |

The collector still simply waits for the real 17:00 CT open/reopen after each
earlier launch. `--duration 84300` still produces one dataset per leg
(`es_20260907_<id>` for H1A `trading_date 2026-09-07`; `es_20260908_<id>` for
H1B `trading_date 2026-09-08`) — the model close (16:00 CT) is still the
binding `segment_deadline` and finalize point; the overall deadline (~16:10 CT)
still lands inside the model maintenance window, so no second dataset.
`dicks-0wh1{a,b}-memsample.timer` (15-min baseline) unchanged.

**Horizon-guard math (verified against `scripts/dicks_lab_collect_es.py`):**
`_parse_duration('84300') = 84300.0`; `_QUOTE_TOKEN_HORIZON_MARGIN_SECONDS =
900.0`; required remaining at launch `= 84300 + 900 = 85200 s`; a genuinely
fresh ~24 h token has ~`86400 s` → **headroom ~1200 s (20 min)**, guard passes.
Guard and margin untouched. If the provider returns a stale token and the guard
rejects it, that leg fails safely — do not override; preserve evidence.

**Corrected token issuance / expiry chain:**

```
H1A token:  GET Sun ~16:45  ->  expires Mon ~16:45
H1B token:  GET Mon ~16:45  ->  H1A's token is expiring at ~that minute; provider should
                                mint a fresh ~24h token (if it returns H1A's near-dead
                                token, the guard rejects and H1B fails safe -- Attempt 4
                                is still protected).  H1B token expires Tue ~16:45
Attempt-4:  GET Tue ~16:55  ->  H1B's token expired ~10 min earlier -> fresh ~24h token
```

**16:45 coincidence (acceptable):** H1B's token expiry (~Tue 16:45) and
Attempt-4's prearm (Tue 16:45) may fall in the same minute. Attempt-4 prearm
runs only `systemd-inhibit … sleep`; it does **not** call `get_api_quote_token`
(`dicks_lab_preflight.py` is the arming check and shows `quote_token_requested=
false`; the prearm-inhibit unit touches no credential path). Attempt 4's real
token request is Tue ~16:55, ~10 min later.

**Revised timer chronology (verified `systemd-analyze --user verify` clean on all 12 H1 units):**

```
Sun 2026-09-06 16:35:00 CDT   dicks-0wh1a-prearm-inhibit.timer
Sun 2026-09-06 16:45:00 CDT   dicks-0wh1a.timer                        <- H1A launch / token GET
Sun 2026-09-06 17:00        (market open)
Mon 2026-09-07 ~16:10       (H1A clean exit; hard-dead by ~16:23)
Mon 2026-09-07 16:35:00 CDT   dicks-0wh1b-prearm-inhibit.timer
Mon 2026-09-07 16:45:00 CDT   dicks-0wh1b.timer                        <- H1B launch / token GET
Mon 2026-09-07 17:00        (market reopen)
Tue 2026-09-08 ~16:10       (H1B clean exit; hard-dead by ~16:28)
Tue 2026-09-08 16:45:00 CDT   dicks-0w2-attempt4-prearm-inhibit.timer  (UNCHANGED)
Tue 2026-09-08 16:55:00 CDT   dicks-0w2-attempt4.timer                 (UNCHANGED) <- Attempt 4 token GET
Tue 2026-09-08 17:00        (Attempt-4 formal session begins)
```

**Hard-stop safety margins (recomputed):**
- H1A worst-case death (RuntimeMaxSec 84900 + TimeoutStopSec 180) = Mon ~16:23 CT → **12 min** before H1B prearm (Mon 16:35 CT).
- H1B worst-case death (RuntimeMaxSec 85200 + 180) = Tue ~16:28 CT → **17 min** before Attempt-4 prearm (Tue 16:45 CT).

**Attempt-4 isolation re-audit (post-correction):** SHA-256 of all 6
`dicks-0w2-attempt4*` unit files = **byte-identical to the original pre-H1
baseline**; `apps/dicks_laboratory/data/0w2_attempt4/mem_sample.sh` sha256
unchanged (`b96c79a4…46014`); `dicks-0w2-attempt4.timer` →
`2026-09-08 16:55:00`, `dicks-0w2-attempt4-prearm-inhibit.timer` →
`2026-09-08 16:45:00`, all three Attempt-4 timers still `enabled`;
`0w2_attempt4/` directory contents untouched (only its own 15-min memsample
timer appends to its own CSV). No source or test change; no commit.

## IQ. Final token-timing correction — H1A only (2026-09-03 ~17:05 CT) — supersedes IP's H1A row

IP removed the H1B↔Attempt-4 same-minute expiry race but left H1A's token
expiring (~Mon 16:45) in the same minute H1B acquires. The guard makes that
safe, but to avoid losing the rare holiday leg over a few seconds of provider
grace, **H1A is moved 5 min earlier again and its duration raised 300 s** to
keep the same ~Mon 16:10 shutdown. **H1B and Attempt 4 are not touched.**

| Item | IP value | Final |
|---|---|---|
| H1A prearm (`dicks-0wh1a-prearm-inhibit.timer`) | Sun 2026-09-06 16:35:00 CT | **Sun 2026-09-06 16:30:00 CT** |
| H1A launch (`dicks-0wh1a.timer`) | Sun 2026-09-06 16:45:00 CT | **Sun 2026-09-06 16:40:00 CT** |
| H1A `--duration` | 84300 | **84600** (23 h 30 m) |
| H1A `RuntimeMaxSec` | 84900 | **85200** (systemd: 23h 40min) |
| H1A overall deadline / model finalize / clean exit | Mon ~16:10 / Mon 16:00 / Mon ~16:10 CT | **unchanged** (Mon 16:10:00 / Mon 16:00 / Mon ~16:10) |
| H1A worst-case hard death (RuntimeMaxSec 85200 + TimeoutStopSec 180) | — | **Mon 2026-09-07 16:23:00 CT** (SIGINT 16:20:00 → SIGKILL 16:23:00) |
| **H1B — all values** | Mon prearm 16:35 / launch 16:45 / `--duration 84300` / `RuntimeMaxSec 85200` | **UNCHANGED** |
| **Attempt 4 — all values** | Tue prearm 16:45 / launch 16:55 / everything | **UNCHANGED (byte-identical)** |

**H1A horizon-guard math (verified against `scripts/dicks_lab_collect_es.py`):**
`_parse_duration('84600') = 84600.0`; margin `_QUOTE_TOKEN_HORIZON_MARGIN_SECONDS
= 900.0`; required remaining at launch `= 84600 + 900 = 85500 s`; a genuinely
fresh ~24 h token `≈ 86400 s` → **headroom ≈ 900 s (~15 min)**, guard passes.
Guard and 900 s margin untouched. A stale-token rejection remains a fail-safe
outcome to preserve.

**systemd arithmetic (verified, not assumed):**
Sun 16:40:00 + `--duration 84600` = **Mon 16:10:00 CT** (collector overall
deadline / clean self-terminate). Sun 16:40:00 + `RuntimeMaxSec 85200` =
**Mon 16:20:00 CT** (systemd SIGINT backstop); + `TimeoutStopSec 180` →
**Mon 16:23:00 CT** SIGKILL. The current Laboratory model still finalizes
Dataset A at **Mon 16:00 CT** (`_session_close_for(2026-09-07)`), 10 min before
the overall deadline. Still one dataset per leg (`es_20260907_<id>` H1A,
`es_20260908_<id>` H1B).

**Final token issuance / expiry chain (both same-minute races removed):**

```
H1A token:  GET Sun ~16:40  ->  expires Mon ~16:40
H1B token:  GET Mon 16:45   ->  ~5 min after H1A expiry  -> fresh/current ~24h token expected
H1B token:  ...                 expires Tue ~16:45
Attempt-4:  GET Tue 16:55   ->  ~10 min after H1B expiry -> fresh/current ~24h token expected
```

**Hard-stop safety margins (recomputed):**
- H1A worst-case death **Mon 2026-09-07 16:23:00 CT** → **12 min** before H1B prearm (Mon 16:35:00 CT).
- H1B worst-case death **Tue 2026-09-08 16:28:00 CT** (unchanged: `RuntimeMaxSec 85200` from Mon 16:45 launch + 180 s) → **17 min** before Attempt-4 prearm (Tue 16:45:00 CT).

**Final timer chronology (`systemd-analyze --user verify` clean on all 12 H1 units; all 6 H1 timers `enabled` + `active (waiting)`):**

```
Sun 2026-09-06 16:30:00 CDT   dicks-0wh1a-prearm-inhibit.timer
Sun 2026-09-06 16:40:00 CDT   dicks-0wh1a.timer                        <- H1A launch / token GET
Sun 2026-09-06 17:00        (market open)
Mon 2026-09-07 16:00        (H1A Dataset A FINALIZE - model close)
Mon 2026-09-07 ~16:10       (H1A clean exit; hard-dead by 16:23)
Mon 2026-09-07 16:35:00 CDT   dicks-0wh1b-prearm-inhibit.timer         (UNCHANGED)
Mon 2026-09-07 16:45:00 CDT   dicks-0wh1b.timer                        (UNCHANGED) <- H1B launch / token GET
Mon 2026-09-07 17:00        (market reopen)
Tue 2026-09-08 16:00        (H1B Dataset A FINALIZE - CME regular close)
Tue 2026-09-08 ~16:10       (H1B clean exit; hard-dead by 16:28)
Tue 2026-09-08 16:45:00 CDT   dicks-0w2-attempt4-prearm-inhibit.timer  (UNCHANGED)
Tue 2026-09-08 16:55:00 CDT   dicks-0w2-attempt4.timer                 (UNCHANGED) <- Attempt 4 token GET
Tue 2026-09-08 17:00        (Attempt-4 formal session begins)
```

**Attempt-4 isolation audit (post-final-correction):** SHA-256 of all 6
`dicks-0w2-attempt4*` unit files = **byte-identical to the original pre-H1
baseline**. `apps/dicks_laboratory/data/0w2_attempt4/mem_sample.sh` sha256
unchanged (`b96c79a4…46014`). `dicks-0w2-attempt4.timer` →
`2026-09-08 16:55:00`, `dicks-0w2-attempt4-prearm-inhibit.timer` →
`2026-09-08 16:45:00`, all three Attempt-4 timers still `enabled`.
`0w2_attempt4/` directory contents untouched (only its own 15-min memsample
timer appends to its own `mem_samples.csv`). No source/test change; no commit.

---

# 0W-H1F — Labor Day Evidence + Sep-8 Power-Loss Forensics

**Phase run:** 2026-09-08 evening CT (host `robby`, boot 0 after an unplanned
reboot). Final evidence-recovery phase on `robby` before the Azure migration
phase. Collector commit under study unchanged: `c5be3ff`. No collector source
or test file was modified in 0W-H1F.

## JA. Host / reboot forensics

**Reported (Human):** `robby` suffered an unexpected host failure Tue
2026-09-08 ~15:55 CT; cause given as local power outage / host crash; host
believed to have restarted on its own.

**Last pre-failure evidence:**

| Signal | Timestamp |
|---|---|
| `journalctl --list-boots` boot −1 end | Tue 2026-09-08 15:56:12 CDT |
| Last journal line, boot −1 (code-tunnel poll) | 2026-09-08 15:56:12 −05:00 |
| Last kernel line, boot −1 (UFW BLOCK spam) | 2026-09-08 15:54:53 −05:00 |
| H1B SQLite file mtime (last durable write) | 2026-09-08 15:56:31.446 −05:00 |
| H1B last durable trade `received_at` | 2026-09-08 15:56:31.357 −05:00 (20:56:31.357Z) |

**Reboot:** kernel start (boot 0) Tue 2026-09-08 20:59:13 CDT; user manager
`systemd[2061]` 20:59:26. **Downtime ≈ 5 h 3 min.**

**Graceful shutdown? NO.** Boot −1 has no `Reached target …Shutdown/Power-Off`,
no `systemd-shutdown`, no `Unmounting`, no `Powering off` — the log stops mid
kernel-spam.

**Next-boot corroboration of abrupt loss (boot 0):**
- `systemd-fsck[366]: /dev/sda2: recovering journal`
- `EXT4-fs (sda2): orphan cleanup on readonly fs` + ~20 × `Clearing orphaned inode …`
- `systemd-journald: File /var/log/journal/…/system.journal corrupted or uncleanly shut down, renaming and replacing` (and the same for `user-1000.journal`)
- `systemd-journald: Forwarding to syslog missed 195 messages`

**No** kernel panic / oops / MCE / thermal / watchdog in boot −1. PCIe AER
**correctable** errors at 15:53:55–15:53:57 are routine link-layer noise
(non-fatal, not causal).

**Classification: HOST LOSS — ABRUPT / UNGRACEFUL.** Corroborated by logs, not
only by the Human report. Logs confirm the machine stopped instantaneously
with no OS involvement; they do not themselves distinguish "mains power
outage" from any other instantaneous kill, so the specific physical cause
rests on the Human report, which the abrupt-loss signature is fully
consistent with.

## JB. Repository baseline (before any change)

- Branch `master`, HEAD `c5be3ffc8f49b59d1f3fa7a40518097f99d49337`
  ("fix: align quote-token lifetime with capture").
- `git status --short`: `?? docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md`,
  `?? scripts/dicks_lab_quote_rate_experiment.py`.
- **Concurrent upstream change found** (do-not-assume check paid off):
  `git fetch` → `c5be3ff..9f7cff5  master -> origin/master`.
  `origin/master` = `9f7cff591faf4b263f6a4c86206b2d38b8604d99`
  ("fix: narrow datetime to date in earnings-date resolution", Todd McKee,
  Tue Sep 8 11:21:43 2026). Touches only
  `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` (+3) and
  `apps/trade_hunter/tests/test_scoring_core.py` (+13). Unrelated to the
  futures collector. Local `master` is exactly 1 commit behind with no local
  commits ahead → clean fast-forward.

## JC. H1A — service result

- `dicks-0wh1a.timer` (`OnCalendar=2026-09-06 16:40:00`, `Persistent=false`)
  fired once. `prearm-inhibit.service` started Sun 2026-09-06 16:30:00 CT.
- **`dicks-0wh1a.service` started Sun 2026-09-06 16:40:00 CT.** Token GET
  logged `quote_token_issued_at=2026-09-06T21:40:01Z`,
  `quote_token_expires_at=2026-09-07T21:40:01Z`, `remaining_seconds=86400`
  (fresh ~24 h token accepted).
- Service stop line Mon 2026-09-07 16:10:01 CT:
  `Consumed 2min 13.875s CPU time, 112.2M memory peak, 36M memory swap peak`
  — clean graceful stop at the bounded-duration backstop; no failure logged.
- Dataset FINALIZED before the stop (see JE).

## JD. H1A — dataset identity

| Field | Value |
|---|---|
| `dataset_id` | `85eccb13-9432-4163-a078-f9bdbb2f5973` |
| label | `long-horizon-es-2026-09-07` |
| `trading_date` | **2026-09-07** |
| `lifecycle_state` | **FINALIZED** |
| DB | `apps/dicks_laboratory/data/0wh1_labor_day/h1a/es_20260907_85eccb13.sqlite3` (59,105,280 B) |
| `capture_started_at` | 2026-09-06T22:00:00.000263Z (Sun 17:00:00.000 CT) |
| `capture_ended_at` | 2026-09-07T21:00:00.643331Z (Mon 16:00:00.643 CT) |
| manifest `sha256` | `bd829b118873bbe06894c7357c6eaf760b7dda74b6dce305215ecb19173abb34` |
| manifest `state` / `collector_git_commit` | FINALIZED / `c5be3ff` |

**Independent checksum verification: `sha256sum -c` → OK.**

## JE. H1A — holiday-halt evidence (UTC / America-Chicago)

| Event | UTC | Chicago |
|---|---|---|
| CAPTURE_STARTED | 2026-09-06T22:00:00.000263Z | Sun 17:00:00.000 CT |
| SOURCE_CONNECTED | 2026-09-06T22:00:00.780768Z | Sun 17:00:00.781 CT |
| first retained trade (seq 1) | 2026-09-06T22:00:00.824Z | Sun 17:00:00.824 CT |
| last retained trade (seq 119808) | 2026-09-07T16:59:59.523Z | **Mon 11:59:59.523 CT** |
| last retained `received_at` | 2026-09-07T16:59:59.556Z | Mon 11:59:59.556 CT |
| CAPTURE_STOPPED (model finalize) | 2026-09-07T21:00:00.643331Z | **Mon 16:00:00.643 CT** |
| service exit | — | Mon ~16:10:01 CT |

The trade tape stops dead at **11:59:59.523 CT Monday**. The published CME
Labor Day (2026-09-07) ES early halt is **12:00:00 CT** (17:00 UTC) — the
last-trade edge matches to under one second (halt inferred from the published
schedule, corroborated by the tape edge; not fabricated from absence). From
12:00 CT to the 16:00 CT phantom close (**4 h 00 m**) zero trades arrived
while the socket stayed connected.

## JF. H1A — quiet-interval behavior

`dataset_quality_events` = exactly {CAPTURE_STARTED, SOURCE_CONNECTED,
CAPTURE_STOPPED}. **No SOURCE_DISCONNECTED, no SOURCE_RECONNECTED, no
KNOWN_GAP, no SUSPECTED_GAP.** `reconnect_count = 0`. The 4-hour holiday
silence produced no disconnect and no false gap record — socket stayed up,
no data, correctly not treated as a capture gap.

**HOLIDAY QUIET INTERVAL HANDLING: PASS.**

## JG. H1A — lifecycle / durability

- lifecycle **FINALIZED**; accepted 119,808; deferred 0; rejected 1; known_gap 0; suspected_gap 0.
- Rejection: `source_order` 50973, `DXLINK_TIME_AND_SALE` / `INVALID_DXLINK_TICK`.
- `first_source_order` 1, `last_source_order` 119809; provenance distinct `source_order` = 119,808. `(119809 − 1 + 1) − 119808 = 1` missing ordinal **== the 1 rejected record**. Sequence fully explained, zero unexplained holes.
- `dataset_sequence` 1..119808, 119,808 distinct, contiguous.
- Writer (CAPTURE_STOPPED detail + log JSON): `writer_flush_count` 25,744; `writer_batch_size_max` 250; `writer_queue_depth_max` 166; `writer_max_persist_lag_seconds` 1.4203; `writer_persisted_events` 119,809; `writer_overloaded` **false**.
- SQLite: `journal_mode=delete`; `PRAGMA integrity_check` **ok**; `quick_check` **ok**. Manifest present, checksum independently verified, closing summary present and internally consistent.

## JH. H1A — CME-vs-Laboratory holiday-semantics finding

- **CME:** the Sunday-evening open + holiday-Monday activity belongs to
  exchange trade date **2026-09-08** (Monday is a CME holiday; the trade date
  rolls forward to the next business day).
- **Current Laboratory model** (`sessions.py`, `ES_GLOBEX` ordinary rule,
  unchanged): records the Sunday-open leg as `trading_date` **2026-09-07**.
- **Observed runtime:** dataset `trading_date` = **2026-09-07** — matches the
  Lab model, i.e. the label is the expected "conceptually wrong" one. This is
  the documented H1 finding, **not** an experiment failure.
- **Phantom ordinary close:** the Lab finalized Dataset A at
  **Mon 2026-09-07 16:00:00.643 CT** (`_session_close_for(2026-09-07)`),
  exactly the ordinary-session boundary, even though CME's holiday trade-date
  concept continued conceptually through Tuesday. **Phantom close CONFIRMED**
  — one of the main reasons H1 existed.

## JI. H1B — raw artifact inventory (ORIGINAL, pre-inspection)

Directory `apps/dicks_laboratory/data/0wh1_labor_day/h1b/`:

| file | size (B) | mtime (CT) | SHA-256 |
|---|---|---|---|
| `es_20260908_e3110b72.sqlite3` | 495,636,480 | 2026-09-08 15:56:31.445707369 | `bbcbf73813d1c86e30955572ded44f566474a6af87a1e21490eb1dffa4d7396f` |
| `h1b_20260907.log` | 444 | 2026-09-07 16:45:01.325885085 | `818370b4791707f319af32777a3eaffc9e0a0d3847b3ec32dad0745fa0c75693` |
| `mem_samples.csv` | 37,567 | 2026-09-08 22:30:01.376 (still appended post-reboot by its own memsample timer) | `67503cc7bfaf7ea3807f2265f4acdaf3772eeeb42cd417dc5f3ec7c5326b8cc1` |

- DB `Birth: 2026-09-07 17:00:00.007 CT` — created at market reopen, not at
  the 16:45 service start.
- **No sidecars at all:** no `.sqlite3-wal`, no `.sqlite3-shm`, no
  `-journal`, no `.tmp`, no `etilqs_*`, no `*.manifest.json`, no closing
  summary file (`find` for every one of these returned nothing).
- `h1b_20260907.log` (444 B) holds only: dataset-dir line, instrument line,
  `Bounded duration: 84300`, `Connecting...`, and the `fresh_collector` token
  line (`quote_token_issued_at=2026-09-07T21:45:01.282Z`,
  `expires_at=2026-09-08T21:45:01.282Z`, `remaining_seconds=86400`). Nothing
  after — buffered stdout never flushed.
- Stored dataset lifecycle: **OPEN** (see JP).

## JJ. H1B — forensic snapshot / hashes

- Snapshot dir:
  `apps/dicks_laboratory/data/0wh1_labor_day/forensic_snapshot_h1b_20260909T033421Z/`
  (gitignored under `.gitignore:43 data/`; stays on `robby` as runtime evidence).
- `cp -a` byte-for-byte copy of the entire `h1b/` directory, plus
  `SHA256SUMS.h1b.original.txt`, `SHA256SUMS.h1b.snapshot.txt`,
  `STAT.h1b.original.txt`.
- Snapshot hashes **== original hashes** for all three files. Original
  re-hashed after the copy: **unchanged** (`sha256sum -c` OK). The canonical
  original was never modified.
- All subsequent DB inspection was done **read-only against the snapshot
  copy** (`sqlite3 -readonly`, `file:…?mode=ro`).

## JK. H1B — service / host-loss result

- `dicks-0wh1b.timer` (`OnCalendar=2026-09-07 16:45:00`, `Persistent=false`)
  fired once. `prearm-inhibit.service` started Mon 2026-09-07 16:35:00 CT.
- **`dicks-0wh1b.service` started Mon 2026-09-07 16:45:00 CT.** Boot −1
  journal shows **no subsequent line for the unit** — no `Consumed … CPU`, no
  `Deactivated`, no `Stopped`, no `Finished`. systemd never observed the
  service end; the host vanished while the `Type=simple` service was still
  active. Abrupt-loss signature.
- No post-reboot relaunch (spent one-shot timer; see JT for
  `Persistent=false` semantics).

## JL. H1B — SQLite power-loss classification

- `file(1)`: `SQLite 3.x database, last written using SQLite version
  3046001, … database pages 121005 … version-valid-for 98506`; file change
  counter 98506 **== version-valid-for** → header internally consistent, no
  hot journal pending.
- `page count 121005 × 4096 = 495,636,480` = **exact file size** → no torn
  trailing page.
- `journal_mode = delete` (rollback journal, not WAL) → no `-wal`/`-shm`
  expected; none present; nothing to replay.
- Opening the snapshot copy read-only created **no** sidecars and triggered
  **no** recovery.
- `PRAGMA integrity_check` = **ok**; `PRAGMA quick_check` = **ok**; full
  schema (10 tables, 11 indexes) reads correctly.

**SQLITE AFTER ABRUPT POWER LOSS: INTACT.** No repair performed or needed.
Canonical original untouched. SQLite `journal_mode=delete` on `ext4`
(`data=ordered`) remained fully trustworthy through an ungraceful host
disappearance ~0.09 s after its last commit.

## JM. H1B — last durable observation

| Field | Value |
|---|---|
| last durable trade `dataset_sequence` | 988,709 |
| last durable trade `event_timestamp` | 2026-09-08T20:56:31.319000Z = **Tue 2026-09-08 15:56:31.319 CT** (price 7678.0, size 1.0, NEW) |
| last durable provenance `source_order` | **988,713** |
| last durable `received_at` | 2026-09-08T20:56:31.357340Z = **Tue 2026-09-08 15:56:31.357 CT** |
| DB file final mtime | 2026-09-08 15:56:31.446 CT (final commit fsync ~88 ms later) |

**Proximity to host loss:** Human's approximate power loss ~15:55 CT; last
journal flush 15:56:12 CT; DB last write 15:56:31.446 CT. The database
persisted ~19 s *past* the last journal flush, and durable persistence
tracked the feed to within **~0.09 s** of the machine disappearing. The
writer was effectively caught up at the instant of loss.

## JN. H1B — source-order accounting (durable records)

- accepted 988,709; rejected **4** (all `DXLINK_TIME_AND_SALE` /
  `INVALID_DXLINK_TICK`, `source_order` 85967, 86096, 93679, 107852 — all
  early in the run, long before the crash); deferred 0; corrections 0;
  cancels 0 (`event_classification`: 988,709 × NEW only); duplicates 0.
- provenance `source_order` min 1, max 988,713, distinct 988,709, n 988,709.
- `(988713 − 1 + 1) − 988709 = 4` missing ordinals **== the 4 rejected
  records**. **Every durably-present source ordinal is explained; zero
  unexplained holes.**
- `dataset_sequence` 1..988,709, 988,709 distinct, contiguous.

**Binding caveat:** `source_order` continuity *among durable records* does
**not** prove the upstream feed had no gaps before host loss. It proves only
that what was persisted is internally complete and self-consistent.

## JO. H1B — writer / backlog evidence before the crash

- **No CAPTURE_STOPPED, no `dataset_closing_summaries` row** → the final
  writer metrics (final queue depth, final persist lag, `writer_overloaded`
  flag) were **never written**; the host vanished before graceful finalize.
- Best available evidence — `mem_samples.csv`, active-service rows. Last
  active row **Tue 2026-09-08 15:45:00 CT** (11 min before loss):
  `active`, `mem_current` 539,451,392 B, `mem_peak` 541,159,424 B, `tasks` 7,
  `db_bytes` 494,817,280. Preceding active rows: 15:00 → 526 MB, 15:15 →
  535 MB, 15:30 → 538 MB, 15:45 → 539 MB — flat, no runaway growth, no
  backlog blow-up in the final hour.
- Indirect: last `received_at` (15:56:31.357) sat ~0.04 s behind the last
  `event_timestamp` (15:56:31.319) → sub-second persistence lag at the moment
  of loss. **Final queue emptiness cannot be inferred** and is not claimed.

## JP. H1B — lifecycle state (stored vs forensic interpretation)

- **Stored `lifecycle_state` = OPEN**; `capture_ended_at` NULL; no closing
  summary.
- **Stored state is the correct representation** of a process never given the
  chance to finalize. The dataset is **not** relabelled INTERRUPTED — nothing
  in the run performed an interruption; the machine disappeared.
- **Forensic interpretation:** abrupt host-loss termination at
  **~2026-09-08 15:56:31 CT**, ~3.5 min before the intended Tue 16:00 CT CME
  regular close.

## JQ. H1B — manifest / closing-summary state

- manifest: **absent.** checksum: **absent.** closing summary row:
  **absent.** CAPTURE_STOPPED: **absent.**
- Only quality events: CAPTURE_STARTED (2026-09-07T22:00:00.000235Z /
  Mon 17:00:00.000 CT) and SOURCE_CONNECTED (2026-09-07T22:00:00.576758Z /
  Mon 17:00:00.577 CT).
- This total absence of any closing artifact is itself the **expected,
  informative signature** of abrupt host disappearance. Nothing unexpected
  predates the crash.

## JR. H1B — gap semantics

- **No KNOWN_GAP / SUSPECTED_GAP record was created** (and none should be —
  a persisted gap needs source-level evidence, which a host crash does not
  provide).
- Recorded interpretation: *dataset terminated by host loss; the interval
  from ~15:56:31 CT to the intended Tue 16:00 CT CME regular close (~3 min
  29 s) and the phantom finalization were not observed.*
- Distinction preserved for future recovery architecture: this is **host
  unavailable / capture ceased**, not a **feed gap**.

## JS. H1B — holiday-market characterization (market-structure only)

- **Mon 17:00 CT reopen:** first retained trade seq 1 @
  2026-09-07T22:00:00.597Z = Mon 17:00:00.597 CT, price 7709.75. Reopen hour
  (22:00 UTC) 3,558 trades.
- **Tue overnight Globex** (00–06 UTC / 19:00–01:00 CT): ~4.5k–9.8k trades/hr.
- **Tue 08:30 CT US cash open:** 13:00 UTC hour (08:00–09:00 CT) jumps to
  **130,112**; 14:00 UTC hour (09:00–10:00 CT) **156,288** — session peak.
- **Tue afternoon** 15:00–20:00 UTC (10:00–15:00 CT): sustained 90k–150k
  trades/hr.
- **Final partial hour** 20:00 UTC (15:00 CT): 26,708 trades over
  20:00:00–20:56:31 UTC, then host loss.
- **Total durable:** 988,709 accepted trades,
  2026-09-07T22:00:00.6Z → 2026-09-08T20:56:31.3Z = **22 h 56 m 31 s** of the
  ~23 h 00 m nominal session (~99.7%); unobserved tail ≈ the final ~3.5 min
  before the 16:00 CT close plus the phantom finalize.
- `aggressor_side`: BUY 500,021 / SELL 488,688.

No trading-strategy conclusions drawn.

## JT. Attempt 4 — timer / service audit

- **`dicks-0w2-attempt4-prearm-inhibit.timer`** (`OnCalendar=2026-09-08
  16:45:00`, `Persistent=false`): host was down 15:56→20:59 CT. Boot −1: did
  not fire. Boot 0 (re-`Started` 20:59:26): calendar time already past +
  `Persistent=false` → systemd marks the timer `active (elapsed)` **without**
  running the service. `prearm-inhibit.service`: `inactive (dead)`,
  `ExecMainStartTimestamp` empty, `ConditionResult=no` — **never ran**.
- **`dicks-0w2-attempt4.timer`** (`OnCalendar=2026-09-08 16:55:00`,
  `Persistent=false`, `RemainAfterElapse=no`): `LastTriggerUSec` = *(empty)*
  — **never triggered**. Boot −1: no fire (host down). Boot 0: re-`Started`
  20:59:26 then immediately `inactive (dead)` — past one-shot, not
  persistent. **No catch-up run.**
- **`dicks-0w2-attempt4.service`:** `ActiveState=inactive`, `SubState=dead`,
  `Result=success`, `ExecMainStartTimestamp` empty, `ExecMainExitTimestamp`
  empty, `NRestarts=0`, `ConditionResult=no`, `AssertResult=no` — **the
  collector process never executed.**
- **No quote token requested** (no collector; and there is no Attempt-4
  collector log of any kind).
- **No Attempt-4 dataset created.**
- Only `dicks-0w2-attempt4-memsample.timer` (recurring `*:00/15:00`) resumed
  after reboot and kept firing (21:00, 21:15 … 22:30 CT), appending
  `inactive`-marked rows to `0w2_attempt4/mem_samples.csv`.
- The 2026-09-03 16:28 `time.sleep(90)` journal line is the original unit
  dry-run during arming, not a launch.

## JU. `Persistent=false` verification in reality

After reboot, `dicks-0w2-attempt4.timer` did **not** perform a late launch —
it stayed spent / `dead`. `Persistent=false` on the one-shot `OnCalendar`
timer **correctly suppressed the missed activation**. Same for the
prearm-inhibit timer (elapsed; service not run). No late partial run exists,
so there is nothing to stop or quarantine.

## JV. Attempt 4 — final classification

**0W-2 ATTEMPT 4: MISSED — NEVER LAUNCHED DUE HOST OUTAGE.**

## JW. Attempt-4 runtime directory

`apps/dicks_laboratory/data/0w2_attempt4/`:
- `mem_sample.sh` (3,872 B, 2026-09-03 16:28 — unchanged)
- `mem_samples.csv` (still growing; every row after boot 0 is
  `inactive,[not set]…`)
- **NO** `es_*.sqlite3`, **NO** `*.manifest.json`, **NO**
  `0w2_attempt4_20260908.log`, **NO** collector log with any startup or token
  request.

Exactly the "never launched" expected state.

## JX. Temporary unit cleanup — DONE

All Dick's Laboratory experiment unit definitions were captured (contents
recorded in this session's handoff; the H1 unit set is also described in
§IF/§IG/§IP/§IQ and the Attempt-4 set in §HE / §GH). Then, after evidence
capture:

```
systemctl --user disable --now  \
  dicks-0wh1a.timer dicks-0wh1a-prearm-inhibit.timer dicks-0wh1a-memsample.timer \
  dicks-0wh1b.timer dicks-0wh1b-prearm-inhibit.timer dicks-0wh1b-memsample.timer \
  dicks-0w2-attempt4.timer dicks-0w2-attempt4-prearm-inhibit.timer dicks-0w2-attempt4-memsample.timer
systemctl --user stop  <all 9 matching .service units>
rm  ~/.config/systemd/user/dicks-0wh1a*  ~/.config/systemd/user/dicks-0wh1b*  ~/.config/systemd/user/dicks-0w2-attempt4*   # 18 unit files
systemctl --user daemon-reload
```

Result: 9 `timers.target.wants` symlinks removed; 18 unit files deleted;
`daemon-reload` ok. `systemctl --user list-unit-files | grep -i dick` →
none. `systemctl --user list-units --all | grep -i dick` → none.
`systemctl --user list-timers --all` → only 4 unrelated OS timers
(`snap.firmware-updater…`, `launchpadlib-cache-clean`, `ubuntu-insights-*`).
**No stale Dick's Laboratory experiment timer can fire.**

## JY. Runtime evidence preserved

Not deleted (all remain gitignored under `.gitignore:43 data/`, on `robby`):
`apps/dicks_laboratory/data/0wh1_labor_day/` (`h1a/`, `h1b/`,
`forensic_snapshot_h1b_20260909T033421Z/`),
`apps/dicks_laboratory/data/0w2_attempt4/`,
`apps/dicks_laboratory/data/0w2_attempt3/`, and all prior soak evidence
(`0w_soak/`, `0w2_attempt2/`, `0w2a_verification/`, `0w2b1_verification/`,
etc.). The Azure migration phase can decide later whether/how to copy runtime
evidence off-host.

## JZ. CME-vs-Laboratory holiday findings — combined H1 table

| Concept | CME holiday semantics | Lab model | H1 observed behavior |
|---|---|---|---|
| Sun 2026-09-06 17:00 CT open | belongs to trade date **Tue 2026-09-08** | trade date **Mon 2026-09-07** (ordinary rule) | H1A opened, `trading_date=2026-09-07`; first trade 17:00:00.824 CT |
| Mon 2026-09-07 holiday early halt | **12:00 CT** (17:00 UTC) | no holiday rule → expects ordinary session | H1A last trade **11:59:59.523 CT**; then 4 h silence, socket stayed connected, no gap record — PASS |
| Mon 12:00–17:00 CT closed interval | market closed (holiday) | treated as ordinary trading | H1A: 0 trades, 0 disconnects, 0 false gaps |
| Mon 16:00 CT "Lab phantom close" | not a CME boundary on a holiday Monday | `_session_close_for(2026-09-07)` finalizes Dataset A | H1A **FINALIZED 16:00:00.643 CT** — phantom close CONFIRMED |
| Mon 2026-09-07 17:00 CT reopen | start of trade date **2026-09-08** | new ordinary session, `trading_date=2026-09-08` | H1B opened **17:00:00.597 CT**, `trading_date=2026-09-08` |
| Tuesday trade-date identity | Sun-eve + Mon + Tue all = trade date **2026-09-08** | split across two datasets: `2026-09-07` (H1A) then `2026-09-08` (H1B) | Observed exactly that two-dataset split |
| Tue 2026-09-08 16:00 CT close | CME regular close, end of trade date 2026-09-08 | H1B would FINALIZE Dataset A here | **NOT OBSERVED — abrupt host power loss ~15:56:31 CT, ~3.5 min before the close** |

## KA. Repository checkpoint

- **Fast-forward:** local `master` `c5be3ff` → `origin/master` `9f7cff5`
  (unrelated `trade_hunter` earnings-date scoring fix; clean FF, no collector
  code touched, no local commits rebased).
- **Files added in the 0W-H1F checkpoint commit:**
  - `docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md` — this
    canonical historical record for 0W-1 … 0W-H1F (previously untracked).
  - `scripts/dicks_lab_quote_rate_experiment.py` — Phase 0W-5 diagnostic tool
    (see KB).
- No production source or test file changed in 0W-H1F. `git diff --check`
  clean.
- Commit hash / message / push result are recorded in the 0W-H1F session
  handoff (the checkpoint commit necessarily post-dates this file's content).

## KB. Quote-rate experiment disposition

`scripts/dicks_lab_quote_rate_experiment.py` — **intentional Laboratory
diagnostic tooling** (Phase 0W-5; referenced in §AC / §AD / §AH of this
report). Typer CLI (`measure`), bounded by `--duration-seconds`,
diagnostic-only: does **not** touch the accepted serious-collector contract,
does **not** persist to any Laboratory SQLite dataset, does **not** change
TimeAndSale retention; reuses the K9 credential-resolution pattern. Style
matches its committed siblings (`scripts/dicks_lab_*.py`).

Validation: `ruff check` → *All checks passed*; `python -m py_compile` → OK;
`--help` → OK; `git diff --check` → clean. `ruff format --diff` would
restyle it, but it restyles every committed `dicks_lab_*` sibling too (the
repo does not gate `scripts/` on `ruff format`), so it is left exactly as
authored. There is **no pre-existing per-script pytest coverage** for any
`scripts/dicks_lab_*.py` in the repo — this script matches that norm; no live
market experiment was run to justify committing it.

**Disposition: valid intentional tooling → committed** in the 0W-H1F
checkpoint.

## KC. 0W-H1F phase status

| Item | Status |
|---|---|
| 0W-H1 | **COMPLETE / FORENSICALLY REVIEWED** |
| H1A | **HOLIDAY CHARACTERIZATION COMPLETE** — FINALIZED, checksum verified, holiday quiet-interval PASS, phantom close confirmed |
| H1B | **ABRUPT HOST-LOSS FORENSIC CAPTURE** — SQLite INTACT, 22 h 56 m durable, lifecycle stored OPEN (correct), no closing artifacts (expected) |
| 0W-2 Attempt 4 | **MISSED — NEVER LAUNCHED DUE HOST OUTAGE** (`Persistent=false` correctly suppressed a late launch) |
| 0W-2 | **OPEN** (Attempt 4 never completed) |
| 0W-3 | **ACCEPTED / CLOSED** (unchanged) |
| 0W-4 | **BLOCKED** — needs a trustworthy collection host + the formal full-day proof |
| Temporary experiment units | **REMOVED** (18 files; no stale timer can fire) |
| Runtime evidence | **PRESERVED** (gitignored, on `robby`) |
| Repository checkpoint | fast-forwarded to `9f7cff5`; doc + 0W-5 script committed and pushed — see 0W-H1F handoff for the hash |
| NEXT | Azure host inventory / migration (separate phase; not started here) |

---

# 0W-AZ — Azure Migration (dragon) — pointer

The Azure host inventory, clean Ubuntu-26.04.1 rebuild, power scheduling and
daily-collector unit design live in
**`docs/dicks_laboratory/AZURE_COLLECTION_HOST_MIGRATION.md`** (phases
0W-AZ1 … 0W-AZ4). Summary of the first live Azure run:

## LA. 0W-AZ4 — SHORT LIVE AZURE VERIFICATION (NOT a full-session proof)

**2026-09-09 22:38–00:38 UTC**, `dragon` Generation 1 (Ubuntu 26.04.1,
Trusted Launch, `Standard_B2ms`, 256 GiB StandardSSD data disk at
`/srv/dicks_laboratory`), collector commit
`f8ef3401bfbbe27e9b3a76d66a8ed05953d977ad`. The **real production**
`dicks-lab-es-session.service` was exercised via a temporary `/run`-only
override (`--duration 7200`, `--data-dir …/az4_live_verification`); the tracked
unit was byte-unchanged and restored afterward.

- **Partial window** of CME trading date **2026-09-10** — began ~38 min after
  the 17:00 CT reopen; **not** 17:00→16:00 coverage.
- Dataset `f6553efa…` → **FINALIZED**. accepted **10,914** · rejected 0 ·
  deferred 0 · **KNOWN_GAP 0 · SUSPECTED_GAP 0** · reconnect 0 · disconnect 0.
- `dataset_sequence` 1..10,914 contiguous; `source_order` 1..10,914, zero
  unexplained ordinals, zero duplicate accepted ordinals.
- SQLite `quick_check` / `integrity_check` **ok**; manifest + checksum
  independently verified (`b5cf4fa5…`); closing summary == direct SQL counts.
- Writer: `queue_depth_max` 47, `max_persist_lag` 0.322 s, **`writer_overloaded`
  false**.
- Resources: ~0.19 % avg CPU (14.5 s over 2 h), ~51 MB peak service memory,
  B-series CPU credits **accrued** (~+66); `Standard_B2ms` — **no capacity
  concern**.
- VWAP / volume-profile / developing-profile smoke all compute and agree
  (VWAP 7651.80; POC 7653.50 / VAL 7651.00 / VAH 7656.00).
- Deployment fix (not a code defect): dragon's `uv sync` must be
  `uv sync --frozen --all-packages` (the workspace root is empty; deps live in
  `apps/*`).

```
0W-AZ4: PASS / CLOSED — DRAGON LIVE COLLECTOR VERIFIED
Daily collector timer: DISABLED.  Old 24.04 OS disk: RETAINED (through Attempt 4).
NEXT: prepare 0W-2 Attempt 4 on dragon (formal full trading-date proof).
```

## LB. 0W-2 ATTEMPT 4 — FORMAL FULL-SESSION PROOF ON DRAGON (AZURE)

Trading date **2026-09-11** (session open Thu 2026-09-10 17:00 CT → close Fri
2026-09-11 16:00 CT). Pinned commit
`f27a04373d4fb3aea5ce732455cf24cfb008bd5e` (per the Human's binding
correction — no auto-fast-forward; verified via launch `CMDLINE`, dragon
`git rev-parse HEAD`, the dataset's `collector_git_commit`, and the manifest —
all four agree). `uv sync --frozen --all-packages`.

**This is the AZURE run. It is a separate attempt from, and must not be
confused with, ROBBY ATTEMPT 4 (§JV): "0W-2 ATTEMPT 4: MISSED — NEVER
LAUNCHED DUE HOST OUTAGE."** Robby's attempt never launched at all. This
attempt launched, ran unattended for ~21h41m, and did produce a large,
internally-consistent, checksum-verified dataset — but did **not** cleanly
complete, for reasons documented below.

### Launch (binding requirement: production timer must perform the launch)

`dicks-lab-es-session.timer` (real, unmodified, tracked unit — sha256
`eebe8a9c…` — byte-identical before and after the run) fired **automatically**
at `Thu 2026-09-10 21:55:00 UTC` (16:55:00 CT), confirmed live
(`TIMER LastTrigger`/`Result=success`, service `ActiveState=active` observed
at 16:55:02 CT, `MainPID=5063`). No manual rescue was needed or used. Timer
was disabled 8 s later without disturbing the running collector
(`MainPID` unchanged 5063→5063). **PRODUCTION SCHEDULING: PASS.**

Safe preflight (16:42:17 CT, before arming) confirmed
`quote_token_requested=false`, REST/futures/streamer-symbol resolution all
`true` — no token was spent by the preflight.

### What happened

- Session-anchor / dataset identity: `trading_date=2026-09-11` (correct).
  First retained trade `2026-09-10T22:00:01.300000+00:00` = **17:00:01.300
  CT** — clean open coverage.
- The service ran as **one continuous process** the entire time (`MainPID`
  5063/5066 unchanged across every check; `journalctl --list-boots` shows
  exactly one boot; exactly one `Starting`/`Started` pair for the unit) — no
  crash, no reconnect-driven restart, no host reboot.
- At `2026-09-11T19:36:11.163899Z` (**14:36:11 CT Fri**) the collector
  **cleanly self-finalized** the dataset: `dataset_quality_events` shows the
  expected lifecycle — `CAPTURE_STARTED` → `SOURCE_CONNECTED` →
  `CAPTURE_STOPPED` (detail: `writer_flushes=108501,
  writer_batch_max=250, writer_queue_depth_max=6175,
  writer_max_persist_lag_s=23.707, writer_persisted_events=1000000,
  writer_overloaded=false`). `lifecycle_state=FINALIZED`. A valid manifest
  (`sha256=007fd66f…`) was written and independently verified to match the
  on-disk file, both on `dragon` and on the copy preserved to `robby`.
- **Root cause of the early stop: the production systemd unit's `ExecStart`
  never overrides the collector CLI's default `--max-events 1,000,000`, and
  a full ES trading date evidently produces more than 1,000,000 raw
  TimeAndSale events.** `writer_persisted_events=1000000` in the
  `CAPTURE_STOPPED` detail and `total events processed = 1,000,000` in the
  closing summary confirm the cap — not the 16:00 CT session close and not
  the `--duration 83700` ceiling — is what ended the capture, roughly **84
  minutes before the true CME 16:00 CT close** (14:36 CT vs. 16:00 CT).
- Because `--duration 83700` had **not** yet elapsed, the same still-running
  process (Restart=no; no restart occurred or was performed — correct, per
  the Human's binding instruction) continued executing after its own
  finalize and made a further dataset-open attempt, which hit its own
  idempotency guard: `Collection error: A dataset for FUTURE:CME:ES:2026-09
  on 2026-09-11 already exists at
  /srv/dicks_laboratory/data/sessions/es_20260911_3716af9f.sqlite3 in state
  FINALIZED. Refusing to overwrite or duplicate it.` The process then exited
  `status=2/INVALIDARGUMENT` at `2026-09-11T19:36:16Z` (14:36:16 CT).
- **Final systemd state:** `ActiveState=failed`, `SubState=failed`,
  `Result=exit-code`, `ExecMainStatus=2` — **not** `Result=success`.

### Data quality within the captured window (clean)

- `datasets`: `lifecycle_state=FINALIZED`,
  `capture_started_at=2026-09-10T22:00:00.000314Z`,
  `capture_ended_at=2026-09-11T19:36:11.163899Z`.
- `dataset_closing_summaries`: accepted **999,996** · rejected **4** ·
  deferred **0** · known_gap **0** · suspected_gap **0** ·
  `first_source_order=1` · `last_source_order=1,000,000` ·
  `collector_git_commit=f27a04373d4fb3aea5ce732455cf24cfb008bd5e`.
- `trade_observations.dataset_sequence`: 1..999,996, count = distinct =
  999,996 — **fully contiguous, zero duplicates, zero unexplained holes.**
- `observation_source_provenance.source_order`: 1..1,000,000, count = distinct
  = 999,996 (the 4-ordinal deficit reconciles exactly with the 4 rejected
  records).
- `PRAGMA quick_check` / `integrity_check`: **ok** / **ok**.
- File size 501,538,816 B; sha256 `007fd66fe63d0ee1a6bc07a8edbc3e2f3b3f23edabfc764a75244dea6e07bc19`
  — matches the manifest and matches independently on both `dragon` and the
  `robby`-preserved copy.
- No `SOURCE_DISCONNECTED`, no reconnects, no known/suspected gaps recorded
  anywhere in the captured window.

**Everything captured is truthful and internally consistent — the defect is
coverage, not data integrity.** The dataset does **not** cover the full
trading date: the last ~84 minutes of the session (~14:36–16:00 CT) are
**missing**, and the service's own final exit does not meet the
`Result=success` bar.

### Resource / capacity (not the cause)

Azure Monitor, full run window (2026-09-10 21:26Z → 2026-09-11 21:27Z):
`Percentage CPU` avg ~1%, max 18.53%; `CPU Credits Remaining` never
approached zero (climbed from ~77 to ~888 — B2ms **accrued** credit, never
throttled); `Available Memory Bytes` steady ~7.5 GB of 8 GB; `Data Disk IOPS
Consumed %` briefly peaked 89% (non-sustained), disk 238 GiB free of 251 GiB
(1% used). **B2ms CPU CAPACITY: PASS. DISK CAPACITY: PASS.** The early stop
is a software cap/rotation defect, not a resource-starvation symptom.

### Evidence preservation

Copied off `dragon` to `robby:~/secure/att4/` before the scheduled 16:45 CT
Azure Stop-Dragon, with independent sha256 verification (matches the
on-dragon file and the manifest):
`es_20260911_3716af9f.sqlite3`, `es_20260911_3716af9f.sqlite3.manifest.json`,
`att4_samples.csv` (5-min on-host resource sampler), and a captured text
snapshot of the final `systemctl show` / full unit journal / disk & git
state (`att4_final_evidence.txt`).

### Post-run host state

- `dicks-lab-es-session.timer`: `disabled` / `inactive` (unchanged from the
  post-launch disarm — reconfirmed, not re-enabled).
- Tracked unit files unchanged (`.service` sha256 `b48f39db…`, `.timer`
  sha256 `eebe8a9c…`) — byte-identical to the production copies committed in
  the repo.
- Old 24.04 rollback disk `dragon_disk1_bb48fd67c68342b4b4596a45879297f9`:
  **retained, unattached, unchanged.**
- Azure weekly Automation schedules `dicks-futures-dragon-start` /
  `dicks-futures-dragon-stop`: confirmed **enabled**, next-run times intact.
- Per instruction, `dragon` was **not** manually deallocated; the scheduled
  16:45 CT `dicks-futures-dragon-stop` Automation run was left to fire
  naturally to also prove the production Friday shutdown path (verification
  pending, tracked separately).

### 0W-2 ATTEMPT 4 (AZURE) — decision

```
0W-2 ATTEMPT 4 (AZURE): FAIL — PARTIAL-COVERAGE / NON-CLEAN EXIT

Root cause: production systemd unit does not override the collector CLI's
default --max-events=1,000,000; a full ES trading date exceeds that cap.
The collector cleanly self-finalized at 14:36:11 CT (valid manifest+checksum,
0 gaps within the captured window) but this was ~84 minutes before the true
16:00 CT session close. Because --duration had not elapsed, the still-running
process then hit its own "dataset already FINALIZED" guard and exited
status=2 (Result=exit-code), not Result=success.

ROBBY ATTEMPT 4:  MISSED — NEVER LAUNCHED DUE HOST OUTAGE  (§JV)
AZURE ATTEMPT 4:  FAIL — PARTIAL COVERAGE, NON-CLEAN SERVICE EXIT  (this §)

PRODUCTION TIMER LAUNCH: PASS (automatic, real timer, no manual rescue)
FULL TRADING-DATE COVERAGE: FAIL (~14:36–16:00 CT missing, ~84 min)
SERVICE FINAL RESULT: FAIL (Result=exit-code, not success)
DATA INTEGRITY WITHIN CAPTURED WINDOW: PASS (checksum, contiguity, 0 gaps)
HOST/RESOURCE CAPACITY: PASS (not the cause)

0W-2: OPEN — Attempt 4 did not achieve a full clean pass; do not close.
0W-4: BLOCKED pending a corrected Attempt 5 (fix --max-events on the
      production unit, then re-attempt under a new Attempt identity).

NEXT: Human review of this defect finding. Per instruction, no quiet
fix-and-rerun under the Attempt-4 identity was performed — evidence
preserved and reported first. Recommended fix (for Human authorization,
not applied in this phase): pass an explicit --max-events far above one
session's expected event volume (or 0/None if the CLI supports "unbounded
within duration") in dicks-lab-es-session.service's ExecStart, and add
explicit handling so a duration-bounded run that finishes its data before
`--duration` elapses exits 0/success (idle-wait or clean early exit) rather
than attempting a second dataset open and hitting the FINALIZED guard.
```

## LC. 0W-2E — Production Event-Cap & Terminal-Stop Correction

Accepted: **0W-2 ATTEMPT 4 (AZURE): FAIL — PARTIAL COVERAGE / NON-CLEAN
EXIT.** 0W-2 is **OPEN**; 0W-4 **BLOCKED**. Attempt 4 is NOT rerun and its
evidence (`~/secure/att4/` on robby, `dragon`'s own copies, manifest,
checksums, journals, this report's §LB/§AZ5, commit `b7f073c`) is retained
unmodified as permanent experiment history.

**Exact control-flow audit.** `run_long_horizon_capture`'s outer loop
computes, per trading date, `segment_deadline = min(overall_deadline,
session_close)` and calls `_run_one_trading_date_session`, which returns
`(result, stop)`. The inner reconnect loop's clean-return branch (comment:
`"remaining time (or max_events) genuinely elapsed: clean stop"`) treated
*both* stop causes identically — but only a time-exhausted return means
"this trading date's session ended on schedule"; a `max_events`-exhausted
return can happen with real session time still remaining. Because that
branch never set `stop=True`, and `_run_one_trading_date_session` returns
`target_state=FINALIZED` unconditionally on that path, the outer loop's
check (`if stop or current_time >= overall_deadline: return result`) took
the else branch — "wait through maintenance, continue to the next trading
date" — even though the market was still open. `resolve_current_trading_date`
then resolved the **same** `trading_date=2026-09-11` again (session hadn't
closed), `_open_or_resume_dataset` found the just-FINALIZED dataset for that
exact instrument+date, and raised `LongHorizonCaptureError("... already
exists ... FINALIZED. Refusing to overwrite or duplicate it.")` — uncaught
outside `resolve_current_trading_date`, propagating to the CLI's
`except LongHorizonCaptureError: raise typer.Exit(code=2)`. This exactly
reproduces Attempt 4's `Result=exit-code`/`ExecMainStatus=2` failure.

**999,996 vs 1,000,000 accounting (fully explained, not assumed).**
`total_events_seen` (the counter `max_events` bounds) increments once per
*raw source event* handed to `on_event`, before accept/reject/defer
classification — not once per accepted trade. Attempt 4's closing summary:
`accepted_trade_count=999,996`, `rejected_record_count=4`,
`deferred_event_count=0`, `last_source_order=1,000,000`. **999,996 + 4 + 0 =
1,000,000, exactly matching the fuse.** The four "missing" accepted trades
are the four durably rejected records (already present and explained in the
Attempt-4 `normalization_rejections` table); nothing is unaccounted for.

**Fix (implemented, `apps/dicks_laboratory/src/dicks_laboratory/
long_running_capture.py`):**
- After each `collector.collect()` call returns without a `DxLinkError`,
  explicitly check `total_events_seen >= max_events`. If true, the safety
  fuse — not the clock — ended the call: set `stop=True` and a durable
  `stopped_reason="max_events_safety_fuse_reached; max_events=...;
  total_events_seen=..."`, so the outer loop returns immediately instead of
  attempting another trading-date rotation. **No second dataset. No second
  `CAPTURE_STARTED`. No duplicate-open attempt.**
- The dataset itself still finalizes truthfully and cleanly
  (`lifecycle_state=FINALIZED`, writer drained, manifest/checksum written) —
  a fuse trip is not a crash and must not be reported as one.
- The lost tail of the session (`[close_moment, segment_deadline)`) is now
  recorded as a `KNOWN_GAP` using the **existing** gap-evidence machinery
  (`_close_known_gap`, already used by the reconnect path) — no new
  lifecycle schema invented, per instruction. `FINALIZED != COMPLETE` is now
  externally visible in the dataset's own quality evidence.
- `LongHorizonCaptureResult` gained a `stopped_reason: str | None = None`
  field (default-safe; every existing construction/read path unaffected)
  threaded through `_build_result`, so the CLI can classify a fuse-triggered
  stop without re-parsing dataset internals.
- `scripts/dicks_lab_collect_es.py`: when `stopped_reason` starts with
  `"max_events_safety_fuse_reached"`, the process now exits **code 3**
  (distinct from success=0 and genuine `INTERRUPTED`=1) — "dataset evidence
  cleanly finalized; overall process explicitly non-success" per the
  required semantics. Duration-expiry / session-close completion is
  completely unaffected (`stopped_reason=None`, exit 0, as before).

**Production `--max-events` decision:** `5,000,000` (~5x Attempt 4's
observed ~1,000,000-event trading date), pinned explicitly on the tracked
unit — never left to the CLI default again. Dataset size scales at
~501.5 bytes/event (measured: 501,538,816 bytes ÷ 1,000,000 events from
Attempt 4); 5,000,000 events ⇒ **~2.5 GiB worst case**, trivial against the
256 GiB persistent data disk (238 GiB free, 1% used at Attempt-4 end). The
writer handled 1,000,000 events with `queue_depth_max=6,175`,
`max_persist_lag_s=23.7`, `writer_overloaded=false` — no backpressure margin
concern at 5x. **VM/disk are not resized** (not required; not authorized in
this phase).

**Production unit changes
(`deploy/dicks_laboratory/systemd/dicks-lab-es-session.service`):**
`ExecStart` now reads `... --duration 83700 --max-events 5000000
--data-dir /srv/dicks_laboratory/data/sessions` (was missing `--max-events`
entirely). `Restart=no` unchanged. A new deploy-validation test
(`apps/dicks_laboratory/tests/test_production_unit_config.py`) reads the
tracked unit file directly and fails if `--max-events 5000000`,
`--duration 83700`, `--data-dir ...`, or `Restart=no` is ever silently
dropped.

**Regression tests added** (`test_long_running_capture.py`):
`test_max_events_fuse_finalizes_truthfully_without_second_dataset` (fuse
trips early → exactly one dataset, `FINALIZED`, truthful
`stopped_reason`, durable `KNOWN_GAP`, exactly one `collect()` call — no
second dataset-open) and
`test_duration_completes_before_max_events_no_fuse_no_regression` (ordinary
completion with `max_events=5,000,000` far above event volume →
`stopped_reason=None`, no `KNOWN_GAP`, unchanged behavior). Pre-existing
session-close / maintenance-rotation / reconnect suites (`test_session_
close_is_a_clean_stop_not_a_disconnect`,
`test_maintenance_wait_produces_no_gap_and_fresh_connect_at_reopen`,
`test_trading_date_rotation_finalizes_old_dataset_and_opens_new_one`,
`test_trading_date_rotation_across_real_maintenance_wait`, and the full
reconnect/backpressure/checksum suite) all re-verified unaffected — the new
branch is guarded strictly behind `total_events_seen >= max_events`, which
none of those scenarios approach.

**Test results:** targeted (42) → Lab suite (331) → K9 suite (199) → full
repository suite (**1,188 passed, 0 failed**). `ruff check` on every file
touched this phase: **all checks passed** (13 pre-existing errors elsewhere
in the repo, in unrelated untouched scripts, are unchanged). `git diff
--check`: clean. Secret audit: clean.

**Dragon deployment validation:** `dragon` was started explicitly
(Start-Dragon runbook) *after* the scheduled Friday 16:45 CT Stop-Dragon had
already fired naturally (confirmed `PowerState/deallocated` beforehand),
fast-forwarded cleanly to this phase's commit, `uv sync --frozen
--all-packages` re-verified clean, and the updated unit deployed and
verified. The collector timer was **not armed**; it was left/confirmed
`disabled`/`inactive`. Dragon was then explicitly deallocated again — not
left running for development (development occurred on `robby`).

**0W-2E decision: PASS / READY FOR PO REVIEW.** 0W-2 remains **OPEN**;
Attempt 5 is **NOT STARTED** in this phase (not authorized here); the daily
collector timer is **DISABLED**; the old 24.04 rollback disk
(`dragon_disk1_bb48fd67c68342b4b4596a45879297f9`) remains **RETAINED**.
