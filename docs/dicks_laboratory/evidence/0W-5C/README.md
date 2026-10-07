# 0W-5C — One-Day Live WAL Proof Evidence (TD 2026-10-06)

Durable copy of the final post-run audit evidence (audit run 2026-10-07
01:44–02:03Z = 2026-10-06 20:44–21:03 CDT, audit boot `b89b71f0…`). It was
captured before Azure Automation job history (~30 days) and the `dragon`
journald (`MaxRetentionSec=1month`; the production boot `cd2a0fbc…` ages out
~2026-11-05) lose it. No token values, credentials, keys, subscription/tenant
IDs or database files are stored here. Token evidence is limited to the
non-secret `issued_at` / `expires_at` / remaining seconds the collector logged.

Runtime: `a27013b24dc6f010d00c93d5d730544c2cdcead9` (0W-5B WAL-decoupled
persistence). Contract: `/ESZ6` → `/ESZ26:XCME` → `FUTURE:CME:ES:2026-12`.

**Product Owner decision (2026-10-06 CDT):**

```
0W-5C: PASS / ACCEPTED / CLOSED
0W-5: ACCEPTED / CLOSED
LIVE WAL PERSISTENCE: PROVEN
STANDARDSSD: PASS — SUFFICIENT WITH WAL
CAPTURE / PERSISTENCE INFRASTRUCTURE: READY TO LEAVE ACTIVE DEVELOPMENT
```

## Headline — LIVE 2026-10-06

| | |
|---|---|
| submitted | **893,081** |
| persisted | **893,081** |
| difference | **0** |
| queue peak | **568 / 50,000 = 1.14%** |
| max persist lag | **2.497 s** |
| writer_overloaded | **false** |
| peak WAL | **405.8 MiB** (425,521,872 B) |
| checkpoint count | **662** |
| longest checkpoint | **24.693 s** |
| peak StandardSSD IOPS consumed | **59%** (15:01 CT; 0 minutes ≥ 95%) |
| finalization | **12.4 s** (CAPTURE_STOPPED → manifest) |
| journal after FINALIZED | **DELETE** |
| sidecars | **NONE** |
| integrity / checksum | **PASS** (quick + integrity ok; sha256 agrees 3 ways) |

**Load qualification.** The 2026-10-06 live peak minute had **26,243**
events. The 2026-09-30 historical peak minute had **55,416**. The live tape
was lighter. The harder case is covered by the Part-A **actual StandardSSD 2×
authentic 09-30 replay: queue 48.8%, lag 14.5 s, no overload, exact
accounting** (`calibration/results_table.md`). The lighter live tape and the
harder actual-disk replay together support the production decision.

**Persistence architecture decision:** WAL + `synchronous=FULL` is the
ACCEPTED PRODUCTION DESIGN. StandardSSD is SUFFICIENT. A premium disk is NOT
REQUIRED. An additional persistence soak is NOT REQUIRED. Historical
DELETE-mode evidence (0W-4, 0W-5A, 0W-5B) is retained unchanged.

**Remaining persistence backlog (non-blocking, not implemented):**
per-checkpoint production timestamps (BACKLOG); live
commit-latency-during-checkpoint telemetry (BACKLOG); collector memory peak
increase to ~1.2 GiB (INFORMATIONAL, with ample capacity: ≥ 6.7 GiB available).

## Files

| Path | Contents |
|---|---|
| `calibration/` | Part-A actual-disk calibration (2026-10-05 00:11–01:14Z, arming boot `469e9320…`, on `dragon-data1`): `campaign.sh`, `campaign.log`, the four result JSONs + logs, `bench_0w5c.py` (scratch benchmark variant; not in the repo), `results_table.md` |
| `azure/automation_jobs.json` | Arming pair + the two schedule-triggered 0W-5C jobs: name (`SCH_<jobScheduleId>_…` = schedule-triggered), status, times, output streams |
| `azure/job_schedules.json`, `azure/schedules_pre_audit.json`, `azure/schedules_post_audit.json` | runbook↔schedule links; schedule state before the audit restart and at the end of the audit |
| `azure/schedule_housekeeping_2026-10-07.json`, `azure/schedules_after_housekeeping.json` | the expired one-time schedules (identity, description, last-modified) before they were disabled, the disable calls, and all six schedules afterwards |
| `azure/audit_pair_jobs.json` | the audit's own user-started Start-Dragon / Stop-Dragon jobs |
| `azure/activity_log_write_ops_and_health.json` | every non-read ARM op + ResourceHealth event on `rg-dev-environment`, 2026-10-04T16:30Z → 2026-10-07T02:00Z |
| `azure/vm_metrics_1min.csv` | Azure Monitor 1-min CPU avg/max, CPU credits min, available memory min, data-disk write IOPS avg/max, IOPS-consumed % max/avg, queue depth max/avg, write bytes/s, bandwidth-consumed %, read IOPS max, OS-disk write IOPS (10-05 20:30Z → 10-06 21:35Z). Unsampled minutes are blank. |
| `azure/azure_daily_summary.txt` | per-trading-date, burst-window and whole-boot reductions + per-minute 14:50–15:15 and 15:58–16:12 CT tables |
| `azure/vm_config.json`, `azure/disks.json` | VM size and disk SKU/IOPS at audit time |
| `journal/dicks-lab-es-session.service.journal.{txt,json}` | collector unit journal: launch, token metadata, final JSON summary, `Consumed` / memory peak |
| `journal/dicks-lab-{preflight,launch}-gate.service.journal.txt`, `journal/dicks-lab-gate-timers.journal.txt` | 16:42 preflight, 16:55 launch gate, timer start/stop (arming, production and audit boots) |
| `journal/systemd-dicks-lab-unit-lifecycle.journal.txt`, `journal/all-dicks-lab-lines.journal.txt` | systemd lifecycle lines; every journal line mentioning `dicks-lab` (incl. sudo) |
| `datasets/db_audit.json` | read-only (`mode=ro`) audit: identity, lifecycle, quick/integrity check, quality events, closing summary, accounting, rejection rows, boundary trades, busiest minutes, 08:20–09:00 and 14:55–15:10 CT per-minute rates |
| `datasets/manifests_and_independent_sha256.txt` | pre-open sidecar check, `stat`, independent `sha256sum`, manifest |
| `datasets/analytics_smoke.txt` | DatasetAudit + VWAP + volume profile + developing profile (read-only), with pre/post sidecar + sha256 checks |
| `token/token_lifecycle_summary.txt` | launch token horizon (metadata only) |
| `host/host_state_2026-10-07_audit_boot.txt` | audit-boot host state (git, unit hashes, timers, disk, journald, apt/dpkg, sudo, SSH, reloads) |
| `host/audit_boot_timer_disable_2026-10-07.txt` | timer states before/after the audit-boot disable, and the final guest check |
| `host/robby_boot_history.txt` | workstation boot history (robby was on, but is in no collection path) |
| `tooling/` | the exact read-only scripts used (`host_audit.sh`, `db_audit.py` adapted from 0W-4 Attempt 2; `analytics_smoke.sh`) |

## Host lifecycle / Azure

| | One-time start | One-time stop |
|---|---|---|
| Schedule (type) → runbook | `dicks-0w5c-dragon-start` (OneTime) → Start-Dragon | `dicks-0w5c-dragon-stop` (OneTime) → Stop-Dragon |
| Armed | 2026-10-05T01:27:07Z (`schedules/write`) + jobSchedule `9fc4a295…` 01:27:09Z | 01:27:08Z + jobSchedule `fa4f56a7…` 01:27:10Z |
| Fire time | Mon 2026-10-05 15:30 CDT (20:30Z) | Tue 2026-10-06 16:30 CDT (21:30Z) |
| Job | `496a6b1b-c300-4bc6-b6cf-e8f94c677641` | `030ddc03-a293-434d-94a2-060639329ab5` |
| Job name | `SCH_9fc4a295…_639268290000000000` | `SCH_fa4f56a7…_639269190000000000` |
| Created / started / ended (Z) | 20:30:02.710 / 20:30:39.167 / 20:32:15.986 | 21:30:04.968 / 21:31:11.697 / 21:32:10.773 |
| ARM op | `start/action` 20:30:53.940 → Succeeded 20:32:02.027 | `deallocate/action` 21:31:29.073 → Succeeded 21:31:41.441 |
| Caller | `0c24e4c8-b561-49d2-9b48-3e0f47ed2649` = automation-dragon system-assigned MI | same |
| Output | `PowerState/deallocated -> PowerState/running` | `PowerState/running -> PowerState/deallocated` |
| Status | Completed | Completed |

Both schedules are `OneTime` with `expiryTime = startTime` and `nextRun = null`,
so neither can recur. They still read `isEnabled=true`, but they are expired
and cannot fire. The permanent weekly `dicks-futures-dragon-{start,stop}` and the
legacy `automation-k9` schedules stayed `isEnabled=false` throughout.

Production boot `cd2a0fbc…`: kernel 20:31:34Z Mon → journal end 21:31:33Z Tue.
Activity Log between `start/action` Succeeded (10-05 20:32:02Z) and
`deallocate/action` Started (10-06 21:31:29Z): **zero** write operations, so
there was no resize, disk change, redeploy or extra start/stop. ResourceHealth showed no
unplanned event. Final PowerState before the audit restart was
`PowerState/deallocated` (ProvisioningState time 21:31:40.9Z).

Arming boot `469e9320…` (10-05 00:07:33Z → 01:28:46Z, user-started Start-Dragon `dd067591…` / Stop-Dragon `9f799457…`):
`git merge --ff-only` → `a27013b` at 00:08:08Z, `systemd-analyze verify` at
00:08:09Z, Part-A calibration 00:11–01:14Z, `systemctl enable --now` of both
gate timers at 01:26:25Z, then one-time schedules written at 01:27Z. All of it
is pre-run arming activity.

## Autonomous execution chain (CDT)

| Step | Time (CDT) | Evidence |
|---|---|---|
| Azure one-time start | Mon 15:30:02.7 job → 15:32:02.0 start Succeeded | `SCH_` job, MI caller |
| dragon boot | 15:31:34; gate timers active 15:31:46 | boot `cd2a0fbc…` |
| 16:42 preflight | 16:42:00.422 → `PREFLIGHT_RESULT=PASS` 16:42:03.371 | timer-triggered, 3.0s, 0 quote-token requests |
| 16:55 launch gate | 16:55:00.402, ExecCondition passed | marker check |
| collector | Started 16:55:00.499 (+97 ms), PID 1883 | `Restart=no`, one `Started` line |
| 17:00 session open | CAPTURE_STARTED 17:00:00.000209 | DB |
| 16:00 capture close | CAPTURE_STOPPED 16:00:00.436 Tue | DB / manifest `closed_at` |
| WAL finalization | closing writes done 16:00:11.296 (DB mtime); manifest 16:00:12.850 | `stat` |
| service exit | 16:10:02.033 (bounded duration 83,700s ends 16:10:00.5) | systemd |
| Azure one-time stop | 16:30:04.97 job → 16:31:41.44 deallocate Succeeded | `SCH_` job, MI caller |

## Preflight / launch / token

Preflight: `rest_reachable=true`, futures endpoint usable (533), `/ESZ6`
resolves, streamer symbol `/ESZ26:XCME` matches, `quote_token_requested=false`,
`PREFLIGHT_RESULT=PASS`. The collector logged `Instrument:
FUTURE:CME:ES:2026-12 Streamer symbol: /ESZ26:XCME`.

Token (required 83,700 + 900 = 84,600s): issued 2026-10-05T21:55:01.869Z,
expires 2026-10-06T21:55:01.869Z, remaining 86,400s, margin +1,800s,
`oauth_refreshed=false`, 1 quote-token request (startup only), 0 reconnects,
near-expiry path not exercised. Token expiry was 55m01s after CAPTURE_STOPPED.

## Dataset

| | |
|---|---|
| dataset_id | `2b6cc528-8928-4c2b-a27d-77794fc61d26` |
| database_path | `/srv/dicks_laboratory/data/sessions/es_20261006_2b6cc528.sqlite3` |
| trading_date / instrument | 2026-10-06 / `FUTURE:CME:ES:2026-12` |
| source_locator | `TASTYTRADE_DXLINK:/ESZ26:XCME:TimeAndSale` |
| collector_git_commit | `a27013b24dc6f010d00c93d5d730544c2cdcead9` |
| lifecycle_state | FINALIZED (the only dataset for this TD) |
| size | 447,324,160 B (109,210 pages × 4096, freelist 0) |
| sha256 | `a97c6ba09853bb418d6f65d48cf1e53f3ae554535f9d874849cd3ff9ceef9bf3` (independent = manifest = collector JSON; re-verified after the analytics smoke) |
| journal_mode / sidecars | `delete` / none (`-wal`, `-shm`, `-journal` absent before and after every read) |
| quick_check / integrity_check | ok / ok |

Session boundaries: CAPTURE_STARTED 22:00:00.000209Z, SOURCE_CONNECTED
+1.711s, first trade event 22:00:01.939Z (17:00:01.939 CT), last trade
20:59:59.122Z (15:59:59.122 CT), CAPTURE_STOPPED 21:00:00.436Z. Opening PASS,
16:00 close PASS. No received-to-received silence > 60s.

Lifecycle: STARTED 1, CONNECTED 1, DISCONNECTED 0, RECONNECTED 0, KNOWN_GAP 0,
SUSPECTED_GAP 0, STOPPED 1.

Accounting: raw 893,081 = accepted 893,077 + rejected 4 + deferred 0.
Corrections 0, cancels 0 (all accepted rows `NEW`). source_order 1–893,081,
893,081 distinct (holes 0 / dups 0). dataset_sequence 1–893,077, 893,077
distinct (holes 0 / dups 0).

Submitted vs persisted (all four agree, difference 0):

| Source | submitted | persisted | difference |
|---|---|---|---|
| closing summary (`dataset_closing_summaries`) | 893,081 | 893,081 | 0 |
| manifest | 893,081 | 893,081 | 0 |
| CAPTURE_STOPPED detail | 893,081 | 893,081 | 0 |
| collector JSON (journal) | 893,081 | 893,081 | 0 |

Rejections (all `INVALID_DXLINK_TICK`, NEW, flags 0, price 7835.0):
source_order 21700 + 21701 (event 01:47:00Z, size 19 each, received 7m05.2s /
7m05.9s late, same price/size/event_time); 41550 (06:06:00Z, size 120, 6m35.2s
late); 41566 (06:06:00Z, size 30, 6m36.3s late). Preserved for backlog, not
investigated.

## Writer / WAL (production-emitted aggregates)

| Metric | Live 2026-10-06 |
|---|---|
| persisted_events | 893,081 |
| flush_count | 98,805 |
| batch_size_max | 1,398 |
| queue_depth_max | 568 (1.14% of 50,000) |
| max_persist_lag | 2.497s |
| writer_overloaded | false |
| wal_checkpoint_count | 662 |
| wal_checkpoint_seconds_max | 24.693s |
| wal_bytes_max | 425,521,872 B (405.8 MiB; 39.6% of the 1 GiB force bound) |

Forced 1 GiB checkpoint: **no**. WAL size is sampled after every commit and
every checkpointer poll, and its maximum never reached
`checkpoint_force_wal_bytes`. Checkpoint error: **no**. A checkpointer
failure raises `CaptureWriterError` at drain, which would have meant
INTERRUPTED plus a `stopped_reason`. The dataset is FINALIZED with
`stopped_reason=null`. Production does not emit per-checkpoint timestamps,
frame counts or total checkpoint seconds. The metrics above are the only
durable checkpointer facts.

## Burst 14:55–15:10 CT (Azure 1-min + DB per-minute received counts)

| CT | events | write IOPS | IOPS-consumed % max | queue depth max | CPU avg / max % |
|---|---|---|---|---|---|
| 14:55 | 4,434 | 168.7 | 30 | 42.8 | 3.06 / 3.92 |
| 14:56 | 2,200 | 191.1 | 34 | 47.9 | 3.17 / 4.74 |
| 14:57 | 2,533 | 13.8 | 2 | 0.0 | 2.52 / 3.83 |
| 14:58 | 5,815 | 15.3 | 19 | 0.0 | 2.87 / 4.36 |
| **14:59** | **26,243** | 179.5 | 15 | 42.2 | 3.39 / 4.14 |
| 15:00 | 4,668 | 181.9 | 32 | 46.0 | 6.55 / 7.36 |
| **15:01** | 1,127 | **334.1** | **59** | **89.1** | 3.43 / 5.46 |
| 15:02 | 805 | 10.1 | – | 0.0 | 2.31 / 3.62 |
| 15:03–15:06 | 488–770 | 6.2–7.6 | ≤1 | 0.0 | ~2.0 |
| 15:07 | 393 | 107.6 | 0 | 29.0 | 2.20 / 3.45 |
| 15:08–15:10 | 198–424 | 2.7–25.7 | ≤23 | ≤5.3 | ~1.9 |

Available memory ≥ 6.705 GiB throughout. The peak event minute was 14:59 and the peak disk
minute was 15:01. There were 0 minutes at ≥95% IOPS consumed (the whole session max was 59%).

What can be concluded: the disk stayed below its provisioned IOPS through the
cash-close burst, and the writer's whole-day queue and lag maxima (568 / 2.5s)
bound whatever happened in this window. The two-minute offset of the disk peak
is *consistent with* the checkpointer deferring work until ingestion is quiet,
as designed. What cannot be concluded: when individual checkpoints ran or how
long each took, or when the 2.5s lag maximum occurred. Production records only
aggregates, and no per-checkpoint timeline exists.

Load context: 26,243 events in the peak minute and 893,081 for the day. That
is lighter than 2026-09-30 (55,416 / 1,396,936), the source of the Part-A
calibration. The closest DELETE-mode like-for-like day is 2026-10-02
(24,232-event peak minute): queue 12,454 (24.9%), lag 48.8s, IOPS-consumed
100%.

## Finalization (only what production records)

| Event | Time (Z) | Δ from CAPTURE_STOPPED |
|---|---|---|
| CAPTURE_STOPPED (`observed_at`, = `closed_at`) | 21:00:00.436 | 0 |
| last DB write (closing writes; DB mtime) | 21:00:11.296 | +10.861s |
| checksum read begins (DB atime) | 21:00:11.301 | +10.866s |
| manifest created / written | 21:00:12.848 / 12.850 | +12.414s |
| collector JSON printed | 21:10:01.967 | +10m01.5s (idle until bounded duration end) |
| service deactivated | 21:10:02.033 | +10m01.6s |

The writer drain, checkpointer stop/join, final checkpoint, TRUNCATE collapse,
switch to DELETE and quick_check all fall inside the +10.861s interval. None
is individually timestamped. Azure 16:01 CT: 77.9 write IOPS avg, queue
depth 20.2, 13% IOPS consumed. **Total finalization wall time 12.4s (warm
target ≤ 2 min: PASS).**

## Downstream compatibility (read-only, on dragon, 01:51–01:58Z)

DatasetAudit (`LaboratoryStore(read_only=True)` + `audit_dataset`) PASS:
893,077 trades, dataset_sequence 1–893,077, instrument
`FUTURE:CME:ES:2026-12`, 0 gaps. VWAP PASS: 7873.9100635818…. Volume profile
PASS: POC 7874.50, VAL 7864.25, VAH 7890.25, VA 70.01%, volume 1,196,726.
Developing profile (15m) PASS: terminal = static. Canonical NEW-only =
effective tape. No sidecars before or after, and sha256 unchanged. No tool needs WAL
sidecars.

## Resources

Service: 7min 40.719s CPU over 23h 15min 1.572s, MemoryPeak 1.2G (cgroup,
includes page cache). TD window: CPU mean 2.00%, 1-min max 7.36% (15:00 CT).
Credits: min 110.2 at session open (boot 60.8), end of boot 900.9. Available
memory min 6.705 GiB. Data disk: 232 GiB free (248,894,349,312 B), 6.4 G used.
B2ms PASS.

## Azure stop margin

CAPTURE_STOPPED 21:00:00.436Z → service exit 21:10:02.033Z (+10m01.6s) →
Stop job created 21:30:04.97Z (+30m04.5s) → `deallocate/action` Started
21:31:29.07Z (+31m28.6s) → Succeeded 21:31:41.44Z (+31m41.0s). From service
exit to deallocation start there were **21m27.0s**.

## Calibration vs live

| | Part-A actual-disk 1× (09-30 burst replay) | Live 2026-10-06 |
|---|---|---|
| queue peak | 2,758 (5.5%) | 568 (1.14%) |
| max lag | 5.621s | 2.497s |
| peak WAL | 1,099.7 MiB (paced, inherited from a 4.27 GB full-speed prefill) | 405.8 MiB |
| checkpoints | 52 in a ~9 min paced window | 662 over 23h |
| longest checkpoint | 44.864s | 24.693s |
| writer overload | false | false |
| submitted / persisted | 111,862 / 111,862 | 893,081 / 893,081 |
| finalization | core 9.36s (warm, measured per step) | 12.4s CAPTURE_STOPPED → manifest |

Live was better than the calibration, on a lighter tape (peak minute ≈ 47% of 09-30).
Relative to its own load, live is *consistent with* the calibration.

## Audit-time actions (2026-10-07Z)

- 01:44Z: Azure stop evidence, schedules, jobs, Activity Log and metrics
  captured *before* any restart.
- 01:46:18Z: Start-Dragon `67860992-b824-4620-826e-2f220a1c5e5a`
  (user-started), boot `b89b71f0…` 01:47:39Z.
- 01:48:22Z: `systemctl disable --now dicks-lab-preflight-gate.timer
  dicks-lab-launch-gate.timer` (prior: enabled/active, next 10-07 21:42Z /
  21:55Z). `dicks-lab-es-session.timer` static/inactive. No preflight, launch
  gate, collector or quote-token request was run.
- 01:48–01:58Z: read-only host audit, independent sha256, DB audit
  (`mode=ro`), analytics smoke. Temp files removed from dragon `/tmp`.
- 02:01:02Z final guest state: both gate timers disabled/inactive,
  `dicks-lab-es-session.timer` static/inactive, collector inactive, 0 dicks
  timers scheduled, 0 failed units, HEAD `a27013b`, clean tree.
- 02:01:13Z: Stop-Dragon `1bd703e9-8571-4325-a431-258aa850385b`
  (user-started), Completed 02:02:42Z. Final `PowerState/deallocated`.

## Post-decision housekeeping (2026-10-07Z)

- 02:18:58–59Z: the expired OneTime schedules `dicks-0w5c-dragon-start` and
  `dicks-0w5c-dragon-stop` (previously `isEnabled=true`, `nextRun=null`) were
  set `isEnabled=false`. They were disabled, not deleted, following the
  0W-4 convention. The `jobSchedules` runbook links were retained.
- Afterwards all six schedules were disabled: the 0W-5C start/stop, the
  permanent weekly `dicks-futures-dragon-{start,stop}`, and the legacy
  `automation-k9` `dragon-start-{weekday,saturday}`. dragon was not booted
  and stayed `PowerState/deallocated`. The guest gate timers stay
  disabled/inactive (last verified at 02:01:02Z) and
  `dicks-lab-es-session.timer` stays static/inactive.
