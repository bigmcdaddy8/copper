# 0W-4 Attempt 2 — Five-Day Autonomous Soak Evidence (2026-09-27 → 2026-10-02)

Durable copy of the final-audit evidence (audit run 2026-10-04, audit boot
`95913c82…`). It was captured before Azure Automation job history and the
`dragon` journald (`MaxRetentionSec=1month`; the Attempt-2 entries age out
around 2026-10-27 to 11-02) lose it. No token values, credentials or
databases are stored here. Token evidence is limited to the non-secret
`issued_at` / `expires_at` / remaining seconds the collector logged.

**Product Owner decision (2026-10-04): 0W-4 Attempt 2 OPERATIONAL PASS —
five-day autonomous multi-day capture proven; dataset-quality qualification
2026-09-29 INCOMPLETE (`KNOWN_GAP=1`, 1.593s); 0W-4 ACCEPTED / CLOSED.** The
PO separated collector/host resilience from individual dataset completeness.
See `../../FULL_SESSION_MULTIDAY_SOAK_REPORT.md` §MH. The 2026-09-29 dataset
remains `KNOWN_GAP=1` / DATA COMPLETENESS = FAIL permanently.

Audit-time classification under the then-current bar (kept for the record):
**FAIL — DATA COMPLETENESS (2026-09-29 `KNOWN_GAP=1`).** Host
endurance, autonomous scheduling, daily rotation (5/5 datasets),
finalization, accounting and integrity all PASS. 2026-09-29 had one
provider-side WebSocket abnormal closure at 04:14:58.865 CT. It recovered
automatically in 1.593s and **reused the process quote token** (the 0W-4D
correction worked in production). The next day launched normally with a fresh
86,400s token. Under the unchanged daily bar (`KNOWN_GAP=0`), 2026-09-29
fails DATA COMPLETENESS.

## Files

| Path | Contents |
|---|---|
| `azure/automation_jobs.json` | Start-Dragon / Stop-Dragon jobs from 2026-09-26T03:30Z on (Sep-26 arming pair, scheduled Sunday start, scheduled Friday stop): trigger, status, output streams |
| `azure/activity_log_write_ops_and_health.json` | every non-read ARM op + ResourceHealth event on `rg-dev-environment`, 2026-09-25 → 2026-10-04T15:00Z |
| `azure/vm_metrics_1min.csv` | Azure Monitor 1-min CPU avg/max, CPU credits, available memory min, data-disk write IOPS avg/max, data-disk IOPS-consumed % max, data-disk queue depth max, OS-disk write IOPS, data-disk read IOPS max (Sun 20:30Z → Fri 21:50Z) |
| `azure/azure_daily_summary.txt` | per-trading-date (17:00→16:00 CT) reduction of the metrics CSV |
| `journal/dicks-lab-es-session.service.journal.txt` | full collector unit journal for the week (launch/token metadata, reconnect + credential decision, final JSON summaries incl. writer metrics, `Consumed` / memory peak) |
| `journal/dicks-lab-preflight-gate.service.journal.txt`, `journal/dicks-lab-launch-gate.service.journal.txt`, `journal/dicks-lab-gate-timers.journal.txt` | the 16:42 preflight and 16:55 launch gate ×5, plus timer start/stop (soak boot and audit boot) |
| `journal/systemd-dicks-lab-unit-lifecycle.journal.txt` | systemd start/finish/consumed lines for the dicks-lab units |
| `journal/day2_reconnect_window_all_units_2026-09-29T0910-0920Z.journal.txt` | ALL journal entries (every unit and the kernel), 09:10–09:20Z around the 09-29 disconnect |
| `journal/soak_boot_history_and_failures.journal.txt` | boot list, soak-boot first/last lines, kernel warnings, OOM/I/O grep, err+ entries, failed units, reloads, SSH logins, sudo (0), apt, clock |
| `datasets/db_audit.json` | per-dataset read-only audit: identity, lifecycle, quick/integrity check, quality events, accounting, rejection rows, deferred, boundary trades, gap brackets, busiest minutes, 08:20–09:00 CT rates |
| `datasets/manifests_and_independent_sha256.txt` | the five manifests + independent `sha256sum` + sizes + sidecar check |
| `datasets/deferred_cancel_2026-10-02.txt` | the one deferred CANCEL and the rejected print it targets |
| `datasets/analytics_smoke_*.txt` | read-only VWAP / volume-profile / developing-profile outputs |
| `token/token_lifecycle_summary.txt` | per-launch token horizon table + every reconnect credential decision (metadata only) |
| `host/host_state_2026-10-04_audit_boot.txt` | audit-boot host state (git, unit hashes, timers after disable, disk, journald) |
| `host/sep26_arming_boot.journal.txt` | the Sep-26 03:33–03:38Z arming boot (ff-merge, daemon-reload, timer enable) |
| `host/robby_boot_history.txt` | workstation boot history (robby was on, but is not in any collection path) |
| `tooling/db_audit.py`, `tooling/host_audit.sh` | the exact read-only scripts used (identical to Attempt 1 except the date window) |

## Host lifecycle / Azure

| | Sunday start | Friday stop |
|---|---|---|
| Schedule → runbook | `dicks-futures-dragon-start` → Start-Dragon | `dicks-futures-dragon-stop` → Stop-Dragon |
| Job (name prefix `SCH_` = schedule-triggered) | `a10e743e-313f-4834-a2cc-df3d63a59cfd` | `e93f792c-7365-40e8-a621-2e1ba588c9c2` |
| Job created | 2026-09-27T20:30:07.03Z (15:30 CDT) | 2026-10-02T21:45:03.61Z (16:45 CDT) |
| ARM op | `start/action` 20:31:10.10Z → Succeeded 20:32:05.95Z | `deallocate/action` 21:45:56.11Z → Succeeded 21:46:08.82Z |
| Caller | `0c24e4c8-…` = automation-dragon system-assigned MI | same |
| Output | `deallocated -> running` | `running -> deallocated` |
| Status | Completed | Completed |

The week had one guest boot (`0ff441d5…`, 20:31:40Z Sun → 21:46:01Z Fri,
5d 1h 14m 21s). Activity Log between the two ops: **zero** write
operations, so no resize, redeploy, disk change or extra start/stop.
ResourceHealth: Available from 20:31:14Z Sun until the user-initiated
"Stopping and deallocating" at 21:45:56Z Fri, with no unplanned events.
Unexpected reboots 0. Unexpected deallocations 0. OOM 0. Filesystem/I/O
errors 0 (the three `hv_storvsc … cmd 0xa1 … srb 0x86` lines at 21:16Z Sun
are rejected ATA pass-through probes. Attempt 1 logged the identical three
at a similar post-boot offset). err+ journal entries 0. Failed units 0.

## Sep-26 arming session (pre-soak, not a soak event)

| Time (Z) | Event |
|---|---|
| 03:32:28 | Start-Dragon job `5ae8d8bc-c428-4d05-81ab-8e88a7952378` (user-started), boot `3dd99777…` 03:33:43 |
| 03:34:15 | `git merge --ff-only` `cd216e5` → `6f5247f` (reflog) |
| 03:34:55 | `sudo systemctl daemon-reload` |
| 03:35:07 | `sudo systemctl enable --now dicks-lab-preflight-gate.timer dicks-lab-launch-gate.timer` |
| 03:35:19–20 | Azure `dicks-futures-dragon-start` / `-stop` `schedules/write` (re-enabled) |
| 03:37:19 | Stop-Dragon job `5705bcb5-b966-4f0c-bcaf-e669e11e3c81` (user-started), deallocate Succeeded 03:38:21 |

This pair came after the documented 0W-4D deployment pair
(`2825b519…` / `8de66cfb…`, 03:15–03:23Z) and is classified as
**pre-soak arming/deployment activity**. It is distinct from the autonomous
Sunday production start (`a10e743e…`, schedule-triggered, 09-27 20:30Z).

## Daily scheduling / rotation

Preflight ran at 21:42:00.0Z (16:42 CT) on all five evenings:
`PREFLIGHT_RESULT=PASS`, `quote_token_requested=false`, `/ESZ6` resolves,
streamer symbol `/ESZ26:XCME` matches. The launch gate ran at 21:55:00.0Z
(16:55 CT) and passed its ExecCondition (date-scoped tmpfs marker = the
launch-evening CT date) on all five evenings, starting the collector 54–59 ms
later. `Restart=no`, `NRestarts=0`.

| Trading date | Authorized (launch eve) | Service start (Z) | PID | End (Z) | Exit / Result | Dataset |
|---|---|---|---|---|---|---|
| 2026-09-28 | 2026-09-27 | 09-27 21:55:00.116 | 1902 | 09-28 21:10:01.415 | 0 / success | `843a6ca0-3cf3-4878-b53c-a848e72bece5` |
| 2026-09-29 | 2026-09-28 | 09-28 21:55:00.111 | 9051 | 09-29 21:10:01.344 | 0 / success | `6af08205-90f9-4735-809f-c7b8a62bda65` |
| 2026-09-30 | 2026-09-29 | 09-29 21:55:00.112 | 16226 | 09-30 21:10:01.504 | 0 / success | `9ac5a21e-a5c0-427c-91fc-af300539b711` |
| 2026-10-01 | 2026-09-30 | 09-30 21:55:00.110 | 22595 | 10-01 21:10:01.190 | 0 / success | `fe280370-99f6-4265-8bf1-a4ce7580f940` |
| 2026-10-02 | 2026-10-01 | 10-01 21:55:00.113 | 29037 | 10-02 21:10:01.366 | 0 / success | `7e8d7b5e-d7b8-4286-92a2-320bfd26723d` |

All datasets: `FUTURE:CME:ES:2026-12`, `TASTYTRADE_DXLINK:/ESZ26:XCME:TimeAndSale`,
`collector_git_commit 6f5247faeac00ef67b41318996de19ff5820299c`, FINALIZED.
No missing, duplicate or wrong-contract datasets.

## Token horizon (required = 83,700 + 900 = 84,600s)

| TD | issued_at (Z) | expires_at (Z) | remaining at launch | margin | requests at startup | oauth_refreshed | vs prior expiry | class |
|---|---|---|---|---|---|---|---|---|
| 09-28 | 09-27 21:55:01.225 | 09-28 21:55:01.225 | 86,400 | +1,800 | 1 | false | — | FRESH TOKEN IMMEDIATELY |
| 09-29 | 09-28 21:55:01.108 | 09-29 21:55:01.108 | 86,400 | +1,800 | 1 | false | −117 ms | FRESH TOKEN IMMEDIATELY |
| 09-30 | 09-29 21:55:01.099 | 09-30 21:55:01.099 | 86,400 | +1,800 | 1 | false | −9 ms | FRESH TOKEN IMMEDIATELY |
| 10-01 | 09-30 21:55:00.999 | 10-01 21:55:00.999 | 86,400 | +1,800 | 1 | false | −100 ms | FRESH TOKEN IMMEDIATELY |
| 10-02 | 10-01 21:55:01.252 | 10-02 21:55:01.252 | 86,400 | +1,800 | 1 | false | +253 ms | FRESH TOKEN IMMEDIATELY |

The near-expiry path (`startup_quote_token: imminent_expiry=true`, bounded
wait, re-request) **never executed**: 0 lines, 0 waits, 0 re-requests. Each
launch received a full-lifetime token on its single request, including the
three launches whose request reached the provider 9–117 ms before the
standing token's expiry.

## Reconnect / token reuse

The only disconnect of the week:

```
TD 2026-09-29, PID 9051
SOURCE_DISCONNECTED 2026-09-29T09:14:58.864763Z (Tue 04:14:58.865 CT)
  attempt=1; episode=1; stage=SOCKET_RECEIVE;
  error=DXLink connection error while receiving: no close frame received or sent
reconnect: attempt=1 refresh_collector_invoked=true
reconnect_credentials: quote_token_reused=true quote_token_requested=false
  quote_token_remaining_seconds=45601 required_seconds=43801
KNOWN_GAP 09:14:58.864763Z -> 09:15:00.457408Z (1.593s)
  disconnect_to_reconnect_interval; no automatic recovery assumed
SOURCE_RECONNECTED 09:15:00.457408Z
last trade before: dataset_seq 133612 / source_order 133617, event 09:14:58.022Z
first trade after: dataset_seq 133613 / source_order 133618, event 09:15:00.898Z
```

The process had no OAuth refresh (`oauth_refreshed=true` appears 0 times all
week) and made no quote-token request for the reconnect. The token in use
had 12h40m01s remaining, 1,800s more than required. Host at that minute:
CPU 1.6%, data-disk IOPS-consumed ≤4%, no kernel, network or Tailscale
event (see the all-units window). The next launch (TD 09-30) received a
fresh 86,400s token. **This is the exact Attempt-1 failure sequence
(reconnect → next-day horizon refusal), and it did not recur.** Journal
timestamps of in-run collector lines are stdout flush times (09:14:59.865Z).
The DB quality events are authoritative.

## Session boundaries

| TD | CAPTURE_STARTED (Z) | SOURCE_CONNECTED | first trade (CT) | last trade (CT) | CAPTURE_STOPPED (Z) | Open | 16:00 close |
|---|---|---|---|---|---|---|---|
| 09-28 | 09-27 22:00:00.0003 | +1.350s | 17:00:01.354 | 15:59:58.977 | 21:00:00.320 | PASS | PASS |
| 09-29 | 09-28 22:00:00.0003 | +1.330s | 17:00:01.340 | 15:59:58.111 | 21:00:00.597 | PASS | PASS |
| 09-30 | 09-29 22:00:00.0004 | +1.167s | 17:00:01.352 | 15:59:59.992 | 21:00:00.189 | PASS | PASS |
| 10-01 | 09-30 22:00:00.0004 | +1.000s | 17:00:01.145 | 15:59:59.885 | 21:00:00.167 | PASS | PASS |
| 10-02 | 10-01 22:00:00.0002 | +0.928s | 17:00:01.000 | 15:59:59.993 | 21:00:00.220 | PASS | PASS |

## Lifecycle / gaps

| TD | STARTED | CONNECTED | DISCONNECTED | RECONNECTED | KNOWN_GAP | SUSPECTED_GAP | STOPPED |
|---|---|---|---|---|---|---|---|
| 09-28 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 09-29 | 1 | 1 | 1 | 1 | **1** | 0 | 1 |
| 09-30 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 10-01 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 10-02 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |

No received-to-received silence > 60s in any dataset.

## Event accounting

| TD | raw (= max source_order) | accepted | rejected | deferred | corrections | cancels | source_order holes/dups | dataset_seq (min–max, distinct) | dataset_seq holes/dups |
|---|---|---|---|---|---|---|---|---|---|
| 09-28 | 1,264,734 | 1,264,733 | 1 | 0 | 0 | 0 | 0 / 0 | 1–1,264,733, 1,264,733 | 0 / 0 |
| 09-29 | 1,194,189 | 1,194,184 | 5 | 0 | 0 | 0 | 0 / 0 | 1–1,194,184, 1,194,184 | 0 / 0 |
| 09-30 | 1,396,936 | 1,396,931 | 5 | 0 | 0 | 0 | 0 / 0 | 1–1,396,931, 1,396,931 | 0 / 0 |
| 10-01 | 1,667,661 | 1,667,659 | 2 | 0 | 0 | 0 | 0 / 0 | 1–1,667,659, 1,667,659 | 0 / 0 |
| 10-02 | 1,387,088 | 1,387,081 | 6 | 1 | 0 | 1 (deferred `DXLINK_CANCEL`) | 0 / 0 | 1–1,387,081, 1,387,081 | 0 / 0 |

source_order spans 1..max, with distinct = max = accepted + rejected + deferred
on every day. The accounting has zero unexplained loss. All accepted rows are
`NEW`. Total for the week: 6,910,608 source events. All five trading dates
exceeded 1,000,000.

**Rejections** (all `INVALID_DXLINK_TICK`, detail NULL, class NEW, flags 0,
whole-point prices, received 16s–39m44s after `event_time`; 10-02 rows
are all exchange `B`, sale condition `B`, `valid_tick=0`), by source_order:
09-28 191891; 09-29 81434, 102398, 102514, 105999, 106385; 09-30 36822,
36823, 61847, 90051, 118946; 10-01 249785, 250117; 10-02 80283, 105221,
105621, 134545, 148471, 167980.

**Deferred cancel (10-02).** source_order 105305 `DXLINK_CANCEL`, received
07:40:04.790Z. Its `source_index 7691961727608577538` / `source_sequence
155138` (07:00:00Z, 7750 × 6) are identical to **rejected** INVALID_DXLINK_TICK
source_order 105221, received 20.5s earlier. The cancel targets a print that
was never accepted, so the accepted tape is unaffected. Preserved for later
semantics work. Not investigated further.

## Integrity

All five: `quick_check ok`, `integrity_check ok`, `journal_mode delete`, no
`-wal/-shm/-journal` sidecars, manifest FINALIZED, independent sha256 =
manifest = journal summary:

| TD | sha256 | size (B) |
|---|---|---|
| 09-28 | `c3159322fc15a56d1da981b623b9e44bbc550b853207cd53f2383c04f33f1917` | 633,470,976 |
| 09-29 | `0b59b7197d486c7ed5fcf5afa08f83e42ec19ed889b44ef421f1eecbf3d07dde` | 598,822,912 |
| 09-30 | `61489eea4ace51dee3aafaa1e1dff5fc7d843e491205f42c2e0dbd098a8aa17c` | 700,641,280 |
| 10-01 | `58545a1b7507ab0dc934adef9e6699fb11cc17745d7526e413b00897093bd95e` | 836,493,312 |
| 10-02 | `cd47e987c8edbec758d590c7580d4a4bb982ed802da18d21fea338f020c3fae2` | 695,705,600 |

The closing summary (`dataset_closing_summaries`) = SQL counts = journal JSON
on every day. Finalization completed ~0.2–0.6s after 16:00 CT, and memory
peaks show no finalization spike, so the full-materialization finalization
regression is absent.

## Writer metrics

| TD | persisted | flushes | batch max | queue_depth_max | max_persist_lag | overloaded | peak minute (CT, events) |
|---|---|---|---|---|---|---|---|
| 09-28 | 1,264,734 | 133,985 | 250 | 17,667 | 70.9s | false | 14:59 (30,987) |
| 09-29 | 1,194,189 | 123,427 | 250 | 19,719 | 79.1s | false | 14:59 (32,474) |
| 09-30 | 1,396,936 | 127,706 | 250 | **46,236** | **185.9s** | false | 14:59 (**55,416**) |
| 10-01 | 1,667,661 | 163,494 | 250 | 20,420 | 81.2s | false | 14:59 (33,247) |
| 10-02 | 1,387,088 | 138,255 | 250 | 12,454 | 48.8s | false | 14:59 (24,232) |
| Attempt-1 max | | | | 21,352 | 86.4s | false | 14:59 (35,304) |

The writer queue's hard bound is `queue_maxsize = 50,000` (default, with
`overload_grace_seconds = 10`). The 09-30 peak used **92.5%** of it (3,764
events of headroom). Queue depth and lag still track the 15:00 CT cash-close
burst, not elapsed days, so there is no drift. The peak, however, is a new
maximum at 2.2× Attempt 1.

## Resources (Azure, per trading date 17:00→16:00 CT)

| TD | CPU mean | CPU 1-min max | credits min / end | avail. mem min | data-disk write IOPS peak | IOPS-consumed max | min ≥95% consumed (CT) | queue depth max | service CPU | MemoryPeak |
|---|---|---|---|---|---|---|---|---|---|---|
| 09-28 | 1.86% | 6.5% | 109.8 / 886.1 | 6.90 GiB | 603 | 100% | 3 (12:14, 15:01–02) | 129.7 | 9m52s | 851.3M |
| 09-29 | 1.87% | 30.5%¹ | 920.6 / 924 | 6.92 GiB | 603 | 100% | 3 (13:03, 15:02–03) | 131.3 | 9m14s | 752.2M |
| 09-30 | 1.84% | 7.0% | 924 / 924 | 6.87 GiB | 603 | 100% | **6 (15:02–15:07)** | 131.7 | 10m03s | 922M |
| 10-01 | 1.94% | 6.6% | 924 / 924 | 6.86 GiB | 603 | 100% | 3 (12:33, 15:02–03) | 132.3 | 12m13s | 1G |
| 10-02 | 1.85% | 5.9% | 924 / 924 | 6.86 GiB | 582 | 100% | 2 (15:01, 15:03) | 126.3 | 10m20s | 878.6M |

¹ 2026-09-29T00:43Z, during a read-only robby checkpoint SSH session.
Credits rose from 60.5 at boot to the 924 cap by Mon 17:06 CT and stayed
there. Data disk: `dragon-data1`, StandardSSD_LRS, 256 GiB, 500 provisioned
IOPS / 100 MBps, host caching None. The observed write ceiling is ~603 IOPS.
**B2ms: PASS. StandardSSD: WATCH.**

## Storage / journal

Datasets: 3,465,134,080 B (3.23 GiB) for five days, avg 660.9 MiB/day,
~501 B/event. `/srv/dicks_laboratory`: 5.9 G used, 249,343,094,784 B
(232 GiB) free. Projected ~14.6 GB/month (21 trading dates), giving ~17
months runway. Journal: 57 M of `SystemMaxUse=2G`, `MaxRetentionSec=1month`.
Oldest entry 2026-09-09 is still retained, so there is no rotation loss yet,
but the retention clock will drop the Attempt-1 soak entries ~2026-10-20 and
Attempt-2 ~2026-10-27.

## Analytics smoke (session-open, read-only, run 2026-10-04 on dragon)

| TD | VWAP | POC | VAL | VAH | VA % | volume | developing terminal (15m) = static |
|---|---|---|---|---|---|---|---|
| 09-28 | 7757.9973 | 7746.25 | 7735.00 | 7768.75 | 70.18 | 1,667,765 | yes |
| 09-29 | 7733.3211 | 7731.00 | 7721.75 | 7745.50 | 70.52 | 1,534,206 | yes |
| 09-30 | 7752.8945 | 7754.50 | 7746.25 | 7779.00 | 70.09 | 1,887,514 | yes |
| 10-01 | 7713.4384 | 7730.00 | 7694.50 | 7745.00 | 70.43 | 2,124,784 | yes |
| 10-02 | 7777.7450 | 7775.00 | 7764.50 | 7797.25 | 70.55 | 1,761,755 | yes |

Canonical NEW-only = effective tape on all five (corrections/cancels applied
0, including 10-02, whose one cancel targets a rejected print). The exact
VWAP strings are in `datasets/analytics_smoke_*.txt`. Runtimes were ~2–3
min per script per dataset on a cold page cache, right after the integrity
pass.

## Autonomy

No manual launch, restart, token refresh, daily action or dataset rescue.
Every collector start followed its launch gate by ≤60 ms. No `daemon-reload`
after boot and 0 sudo commands during the soak boot. Read-only SSH checks from
robby did occur (Sun 09-27 22:43–22:45Z; Mon→Tue 09-29 00:41–00:42Z). They
were not required. robby was powered on all week but is in no collection
path. No code, unit, contract, VM, disk or package change during the soak:
dragon HEAD = GitHub master = `6f5247f`, clean tree, unit sha256 = repo,
unit mtimes 2026-09-16, apt history empty since 2026-09-09, Activity Log
shows only the start and the deallocate.

## Friday shutdown margins (2026-10-02)

| Event | Time (Z) | Δ from CAPTURE_STOPPED |
|---|---|---|
| CAPTURE_STOPPED (dataset FINALIZED) | 21:00:00.220 | 0 |
| collector service deactivated | 21:10:01.366 | +10m01.1s |
| Stop-Dragon job created / started | 21:45:03.6 / 21:45:41.5 | +45m03s / +45m41s |
| `deallocate/action` Started | 21:45:56.1 | +45m56s |
| guest journal stopped | 21:46:01.2 | +46m01s |
| `deallocate/action` Succeeded | 21:46:08.8 | +46m08.6s |

Service deactivation → deallocation Succeeded: **36m07.5s**.

## Audit-time actions (2026-10-04, post-soak)

- 14:37:57–58Z: Azure `dicks-futures-dragon-start` (prior: enabled, nextRun
  2026-10-04T15:30-05:00) and `dicks-futures-dragon-stop` (prior: enabled,
  nextRun 2026-10-09T16:45-05:00) set `isEnabled=false`. The runbook links
  (`jobSchedules`) were retained. Legacy `automation-k9` schedules were
  already disabled.
- 14:41:18Z: Start-Dragon job `61ccaf6a-91e9-4a60-8a80-b04e2f20688b`
  (user-started) for the audit, boot `95913c82…` 14:42:58Z.
- 14:43:29Z: `systemctl disable --now dicks-lab-preflight-gate.timer
  dicks-lab-launch-gate.timer` (prior: enabled/active, next 21:42Z / 21:55Z).
  `dicks-lab-es-session.timer` was static/inactive. No preflight, launch
  gate, collector or quote-token request was run.
- 14:44–16:13Z: read-only host audit, DB audit (`mode=ro`) + independent
  sha256, analytics smoke. Temp files removed from dragon `/tmp`.
- 16:14:06Z final guest state: both gate timers disabled/inactive,
  `dicks-lab-es-session.timer` static/inactive, collector inactive, no
  dicks timers scheduled, 0 failed units, HEAD `6f5247f`, clean tree.
- 16:14:14Z: Stop-Dragon job `4459269b-d91a-42d0-99ee-3c85eb215c93`
  (user-started), Completed 16:15:45Z, `running -> deallocated`. Final
  `PowerState/deallocated`. Azure start/stop schedules re-verified
  `isEnabled=false`. No automatic collection is armed.

## Per-day acceptance (unchanged standard)

| TD | HOST / PROCESS | SCHEDULING | FINALIZATION / ACCOUNTING | DATA COMPLETENESS |
|---|---|---|---|---|
| 2026-09-28 | PASS | PASS | PASS | PASS |
| 2026-09-29 | PASS | PASS | PASS | **FAIL** (`KNOWN_GAP=1`, 1.593s, 04:14:58.865 CT) |
| 2026-09-30 | PASS | PASS | PASS | PASS |
| 2026-10-01 | PASS | PASS | PASS | PASS |
| 2026-10-02 | PASS | PASS | PASS | PASS |

Audit-time verdict (2026-10-04, superseded by the PO decision the same day):

```
0W-4 ATTEMPT 2: FAIL — DATA COMPLETENESS (2026-09-29 KNOWN_GAP=1)
0W-4: OPEN
```

PO decision (final). The per-day table above is unchanged:

```
0W-4 ATTEMPT 2: OPERATIONAL PASS — FIVE-DAY AUTONOMOUS MULTI-DAY CAPTURE PROVEN
DATASET QUALITY QUALIFICATION: 2026-09-29 INCOMPLETE — KNOWN_GAP=1 (1.593 s)
0W-4: ACCEPTED / CLOSED
```

## Open-issue inventory (evidence + severity only; agenda is the PO's)

| | Item | Evidence | Label |
|---|---|---|---|
| — | Overnight provider WebSocket drops vs `KNOWN_GAP=0` bar | 2 of 9 collected trading dates across Attempts 1–2 had one ~1.5s auto-recovered gap (09-21 server 1012 at 21:55 CT; 09-29 abnormal closure at 04:14 CT). There was no host cause either time. Under the current bar, this alone failed Attempt 2. | was BLOCKING under the audit-time bar; resolved by the PO operational-vs-completeness decision |
| A | StandardSSD IOPS / persist lag | IOPS-consumed hit 100% every day, 6 consecutive min on 09-30. Writer queue peaked at 46,236 of its 50,000 hard bound (92.5%), lag 185.9s. `writer_overloaded=false`, no loss. | IMPORTANT → 0W-5A |
| B | INVALID_DXLINK_TICK late prints | 19 this week (1/5/5/2/6), all NEW, whole-point, received 16s–39m44s late; 10-02 rows exchange B / cond B / `valid_tick=0` | BACKLOG |
| C | Orphan / deferred cancel | 1 (10-02). It targets rejected print 105221 exactly (same source_index/sequence), so it has no tape effect | BACKLOG |
| D | Reconnect token reuse | **Naturally observed** 09-29: reused, no OAuth, no quote-token request, next launch unaffected | resolved (informational) |
| E | Near-expiry startup path | **Not naturally observed**: offsets −117 / −9 / −100 / +253 ms, a full-lifetime token every time | BACKLOG (test-covered) |
| F | Contract roll / instrument universe | All five runs on `/ESZ6` (Dec-2026). The 0W-4B selection is generalized, but no live roll has been exercised yet. The Dec roll falls in early-mid December | IMPORTANT (time-bound) |
| G1 | Evidence durability | dragon journald `MaxRetentionSec=1month` drops Attempt-1 soak entries ~10-20 and Attempt-2 ~10-27. This copy is uncommitted | resolved: committed with the 0W-4 closeout |
| G2 | Collector stdout buffering | In-run journal lines carry flush time, not event time (reconnect lines logged 1.0s after the DB disconnect) | BACKLOG |
| G3 | 0W-4D record omits the Sep-26 arming pair | see "Sep-26 arming session" above | BACKLOG (doc) |
