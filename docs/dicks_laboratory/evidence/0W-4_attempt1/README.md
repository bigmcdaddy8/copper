# 0W-4 Attempt 1 — Five-Day Autonomous Soak Evidence (2026-09-20 → 2026-09-25)

Durable copy of the final-audit evidence, preserved in 0W-4D before Azure
Automation job history and `dragon` journald (`MaxRetentionSec=1month`) age
out. Interpretation lives in `../../FULL_SESSION_MULTIDAY_SOAK_REPORT.md`
(§0W-4, MA–MF). No token values, credentials or databases are stored here;
token evidence is limited to non-secret `issued_at` / `expires_at` / remaining
seconds, exactly as the collector logged them.

**Result: FAIL — DATA COMPLETENESS / DAILY ROTATION.** Host endurance and
autonomous scheduling PASS; 4/5 datasets; 2026-09-21 `KNOWN_GAP=1`
(server 1012); 2026-09-22 no dataset (horizon guard correctly refused a
short-lived token minted by the Day-1 reconnect); 2026-09-23/24/25 complete.

## Files

| Path | Contents |
|---|---|
| `azure/automation_jobs.json` | Start-Dragon / Stop-Dragon job records + output streams (scheduled Sunday start, scheduled Friday stop, audit restart/deallocate) |
| `azure/activity_log_write_ops.json` | every non-read ARM operation on `rg-dev-environment`, 2026-09-19..25 (only the one start and one deallocate) |
| `azure/resource_health.json` | VM availability statuses in the soak window |
| `azure/vm_metrics_1min.csv` | Azure Monitor 1-minute CPU %, CPU credits, available memory, data/OS disk write IOPS, data-disk IOPS-consumed %, queue depth (Sun 20:33Z → Fri 21:47Z) |
| `journal/dicks-lab-es-session.service.journal.txt` | full collector unit journal for the week (launch lines, token metadata, reconnect lines, Day-2 refusal, final JSON summaries incl. writer metrics, `Consumed`/memory-peak) |
| `journal/dicks-lab-preflight-gate.service.journal.txt`, `journal/dicks-lab-launch-gate.service.journal.txt`, `journal/dicks-lab-gate-timers.journal.txt` | daily 16:42 preflight (`PREFLIGHT_RESULT`, `quote_token_requested=false`) and 16:55 launch-gate runs ×5 |
| `journal/day1_disconnect_window_all_units_2026-09-21T0250-0300Z.journal.txt` | ALL journal entries (every unit, kernel) 02:50–03:00Z around the 1012 |
| `journal/day2_horizon_refusal_window_all_units_2026-09-21T2154-2156Z.journal.txt` | ALL journal entries around the Day-2 refusal |
| `journal/systemd-dicks-lab-unit-lifecycle.journal.txt` | systemd start/finish/consumed lines for dicks-lab units |
| `journal/soak_boot_history_and_failures.journal.txt` | boot list, kernel warnings, reloads, failed units, shutdown tail for soak boot `6d561348…` |
| `journal/soak_week_ssh_logins_and_sudo.journal.txt` | every SSH login to `dragon` during the soak + sudo count (0) |
| `datasets/db_audit.json` | per-dataset read-only audit: identity, lifecycle, quick/integrity check, quality events, accounting, rejection rows, deferred, boundary trades, gap brackets, per-minute busiest / 08:20–09:00 CT rates |
| `datasets/manifests_and_independent_sha256.txt` | the four manifests + independent `sha256sum` + file sizes |
| `datasets/analytics_smoke_*.txt` | read-only VWAP / volume-profile / developing-profile smoke outputs |
| `host/host_state_2026-09-25_audit_boot.txt` | audit-boot host state (git, unit hashes, timers, disk, journald config) |
| `host/robby_boot_history.txt` | workstation boot history (robby was on, but not in any collection path) |
| `tooling/db_audit.py`, `tooling/host_audit.sh` | exact read-only scripts used |

## Host lifecycle / Azure

| | Sunday start | Friday stop |
|---|---|---|
| Schedule → runbook | `dicks-futures-dragon-start` → Start-Dragon | `dicks-futures-dragon-stop` → Stop-Dragon |
| Job | `ca99579a-0ad1-46ea-905b-65d0c8d90030` | `123d0e04-fabe-4295-947f-c30f7e1f6bce` |
| Job created | 2026-09-20T20:30:04.72Z (15:30 CDT) | 2026-09-25T21:45:03.48Z (16:45 CDT) |
| ARM op | `start/action` 20:31:17Z → Succeeded 20:32:25Z | `deallocate/action` 21:46:07.69Z → Succeeded 21:46:26.70Z |
| Caller | `0c24e4c8-…` = automation-dragon system-assigned MI | same |
| Output | `deallocated -> running` | `running -> deallocated` |

One guest boot all week (`6d561348…`, 20:31:51Z Sun → 21:46:12Z Fri);
unexpected reboots 0; unexpected deallocations 0; only failed unit = the
Day-2 collector exit. Friday margin: collector exited 21:10:02Z, stop job
started 21:45:52Z (+35m50s).

## Daily scheduling / rotation

Preflight fired 21:42:00.86Z (16:42 CT) all five evenings, `PREFLIGHT_RESULT=PASS`,
`quote_token_requested=false`. Launch gate 21:55:00.86Z (16:55 CT) passed its
ExecCondition all five evenings (marker = launch-evening CT date; directly
observed `2026-09-20` for Day 1, tmpfs-lost afterwards). `Restart=no`.

| Trading date | Service start (Z) | PID | End (Z) | Exit / Result | Dataset |
|---|---|---|---|---|---|
| 2026-09-21 | 09-20 21:55:00.964 | 1904 | 09-21 21:10:02.155 | 0 / success | `64d684c9-c22b-4a87-8224-a2a9f7b17e40` |
| 2026-09-22 | 09-21 21:55:00.956 | 9814 | 09-21 21:55:02.166 | **2 INVALIDARGUMENT / exit-code** | **none** |
| 2026-09-23 | 09-22 21:55:00.954 | 16213 | 09-23 21:10:02.123 | 0 / success | `b2856c52-17a5-43f4-941c-aa311e8558e9` |
| 2026-09-24 | 09-23 21:55:00.951 | 22955 | 09-24 21:10:02.389 | 0 / success | `31c92a57-242c-4b25-a983-0086c811ed9a` |
| 2026-09-25 | 09-24 21:55:00.963 | 29362 | 09-25 21:10:02.049 | 0 / success | `c690ff8e-28ac-4d7b-9107-e896987a6520` |

All datasets: `FUTURE:CME:ES:2026-12`, `TASTYTRADE_DXLINK:/ESZ26:XCME:TimeAndSale`,
`collector_git_commit 21e41f631eb678e92f5957952b968b9d93556c3b`, FINALIZED.
No duplicate or wrong-contract datasets.

## Session boundaries

| TD | CAPTURE_STARTED | SOURCE_CONNECTED | first trade (CT) | last trade (CT) | CAPTURE_STOPPED / closed_at | Open | 16:00 close |
|---|---|---|---|---|---|---|---|
| 09-21 | 22:00:00.0003Z | +1.188s | 17:00:01.251 | 15:59:59.867 | 21:00:00.173Z | PASS | PASS |
| 09-22 | — | — | — | — | — | FAIL | FAIL |
| 09-23 | 22:00:00.0003Z | +1.359s | 17:00:01.850 | 15:59:59.991 | 21:00:00.367Z | PASS | PASS |
| 09-24 | 22:00:00.0003Z | +1.273s | 17:00:01.563 | 15:59:59.204 | 21:00:00.266Z | PASS | PASS |
| 09-25 | 22:00:00.0003Z | +1.154s | 17:00:01.224 | 15:59:59.002 | 21:00:00.263Z | PASS | PASS |

`CAPTURE_STOPPED` (~21:00:00Z) is dataset finalization at session close; the
service itself deactivates at ~21:10:02Z when the 83,700s duration elapses.

## Lifecycle / gaps

| TD | STARTED | CONNECTED | DISCONNECTED | RECONNECTED | KNOWN_GAP | SUSPECTED_GAP | STOPPED |
|---|---|---|---|---|---|---|---|
| 09-21 | 1 | 1 | 1 | 1 | **1** | 0 | 1 |
| 09-22 | — | — | — | — | — | — | — |
| 09-23 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 09-24 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |
| 09-25 | 1 | 1 | 0 | 0 | 0 | 0 | 1 |

The only disconnect of the week:

```
SOURCE_DISCONNECTED 2026-09-21T02:55:11.948328Z (Sun 21:55:11.948 CT)
  source_disconnected; attempt=1; episode=1; stage=SOCKET_RECEIVE;
  error=DXLink connection error while receiving: received 1012 (service restart)
  Service Restart; then sent 1012 (service restart) Service Restart
KNOWN_GAP 02:55:11.948328Z -> 02:55:13.502084Z (1.554s)
  disconnect_to_reconnect_interval; no automatic recovery assumed
SOURCE_RECONNECTED 02:55:13.502084Z
last trade before: dataset_seq 40259, event 02:55:08.839Z
first trade after: dataset_seq 40260, event 02:55:13.894Z
```

## Token horizon (required = 83,700 + 900 = 84,600s)

| TD | issued_at (Z) | expires_at (Z) | remaining at launch | margin | oauth_refreshed at launch | later |
|---|---|---|---|---|---|---|
| 09-21 | 09-20 21:55:01.976 | 09-21 21:55:01.976 | 86,400 | +1,800 | false | reconnect 02:55:13Z: `oauth_refreshed=true`, NEW token issued 02:55:13.309Z exp 09-22 02:55:13.309Z |
| 09-22 | **09-21 02:55:13.311** | **09-22 02:55:13.311** | **18,011** | **−66,589 → REFUSED** | false | — |
| 09-23 | 09-22 21:55:01.984 | 09-23 21:55:01.984 | 86,400 | +1,800 | false | none |
| 09-24 | 09-23 21:55:01.812 | 09-24 21:55:01.812 | 86,400 | +1,800 | false | none |
| 09-25 | 09-24 21:55:01.881 | 09-25 21:55:01.881 | 86,400 | +1,800 | false | none |

Day-1 sequence: disconnect 02:55:11.948 → reconnect log +1.000s → OAuth
refresh + new token issued +1.361s → reconnected +1.554s. The token in use at
the disconnect was 5h00m10s old with 18h59m50s remaining. Day-to-day launch
token requests land within ±0.2s of the prior token's expiry (Day 4: new
token issued 0.172s *before* prior expiry; Day 5: 0.069s after).

## Event accounting

| TD | raw (= max source_order) | accepted | rejected | deferred | corrections | cancels | source_order holes/dups | dataset_seq holes/dups |
|---|---|---|---|---|---|---|---|---|
| 09-21 | 883,643 | 883,642 | 1 | 0 | 0 | 0 | 0 / 0 | 0 / 0 |
| 09-23 | 1,091,415 | 1,091,399 | 14 | 2 | 0 | 2 (deferred `DXLINK_CANCEL`) | 0 / 0 | 0 / 0 |
| 09-24 | 1,304,779 | 1,304,777 | 2 | 0 | 0 | 0 | 0 / 0 | 0 / 0 |
| 09-25 | 1,208,527 | 1,208,525 | 2 | 0 | 0 | 0 | 0 / 0 | 0 / 0 |

**Real-market >1,000,000-event proof: PASS** — three trading dates exceeded
1,000,000 source events without stopping.

Rejections (all `INVALID_DXLINK_TICK`, detail NULL, class NEW, flags 0,
whole-point prices, received 2–10 min after `event_time`): 09-21 source_order
112102; 09-23 24159, 57239, 57732, 57950, 57974, 58076, 62914, 62966, 63029,
63811, 66403, 66678, 97637, 98489; 09-24 73760, 891274; 09-25 92246, 98170.
The two 09-23 deferred cancels target events not present in the dataset
(effective-tape `TARGET_SOURCE_EVENT_NOT_FOUND ×2`, cancels applied 0).
Open follow-up questions — not investigated in 0W-4D.

## Integrity

All four: `quick_check ok`, `integrity_check ok`, `journal_mode delete`, no
`-wal/-shm/-journal` sidecars, manifest FINALIZED, independent sha256 = manifest
= journal summary (`2e596889…`, `64ad1f3a…`, `c8a3524b…`, `a57cc42d…`);
closing summary = SQL counts = journal JSON. Finalization uses the
`SELECT COUNT(*)` path.

## Writer metrics and resources

| TD | persisted | flushes | batch max | queue_depth_max | max_persist_lag | overloaded | peak minute (events) | service CPU | MemoryPeak | DB size |
|---|---|---|---|---|---|---|---|---|---|---|
| 09-21 | 883,643 | 95,205 | 250 | 16,432 | 66.8s | false | 14:59 CT (30,638) | 7m25s | 585 MiB | 441,995,264 B |
| 09-23 | 1,091,415 | 100,842 | 250 | 21,352 | 86.4s | false | 14:59 CT (35,304) | 8m23s | 696 MiB | 546,938,880 B |
| 09-24 | 1,304,779 | 136,664 | 250 | 11,330 | 45.4s | false | 14:59 CT (23,346) | 10m20s | 833 MiB | 654,155,776 B |
| 09-25 | 1,208,527 | 118,231 | 250 | 11,170 | 45.1s | false | 14:59 CT (22,997) | 9m32s | 748 MiB | 605,577,216 B |

Queue depth / lag track the peak-minute rate (the 15:00 CT cash-close burst),
not reconnects, and are not increasing. Azure: CPU mean 1.3–1.8%, 1-min max
≤6%; CPU credits at the 924 cap from Mon 16:57 CT onward; available memory
≥6.89 GiB; data-disk IOPS-consumed hit 100% in 1–4 minute bursts every
collection day (mostly 15:01–15:03 CT; also Thu 11:18–11:21, Fri 11:36 91%)
with queue depth up to ~130. **B2ms PASS; 256 GiB StandardSSD WATCH.**

08:20–09:00 CT: 81,683 / 105,288 / 97,917 / 116,563 events (09-21/23/24/25);
08:30 minute 6,811 / 7,933 / 9,261 / 9,809; CPU max 4.2–4.8%; data-disk IOPS
consumed max 42–58%.

Disk: 2.09 GiB for four datasets (~536 MiB/day, ~500 B/event); 235 GiB free
→ ~12.2 GB/month, ~21 months runway. Journal 49 MB of `SystemMaxUse=2G`, no
rotation loss (oldest entry 2026-09-09 retained at audit).

## Analytics smoke (session-open)

| TD | VWAP | POC | VAL | VAH | VA % | volume | developing terminal = static |
|---|---|---|---|---|---|---|---|
| 09-21 | 7803.2716 | 7835.75 | 7787.00 | 7847.00 | 70.14 | 1,289,683 | yes |
| 09-23 | 7787.5156 | 7771.25 | 7762.75 | 7792.50 | 70.47 | 1,484,525 | yes |
| 09-24 | 7753.5201 | 7770.00 | 7741.00 | 7780.75 | 70.34 | 1,686,194 | yes |
| 09-25 | 7788.0682 | 7803.50 | 7777.75 | 7811.50 | 70.45 | 1,566,271 | yes |

## Autonomy

No manual launch, restart, token refresh or daily action; every collector
start followed its launch gate by ≤60 ms; no `daemon-reload` after boot; 0
sudo commands. Read-only SSH checks did occur (robby Mon 21:15–21:30Z; weasel
Mon 20:04Z, Wed 16:02Z, Fri 17:10Z) — none required. robby was powered on
but is in no collection path. No code, unit, contract, VM or disk change
during the soak (dragon HEAD = GitHub master = `21e41f6`, clean tree, unit
sha256 = repo, Activity Log shows only start + deallocate).

## State at end of audit / change in 0W-4D

At audit end (2026-09-25): timers `dicks-lab-preflight-gate.timer` /
`dicks-lab-launch-gate.timer` enabled (next Sun 2026-09-27 16:42/16:55 CDT),
`dicks-lab-es-session.timer` static; Azure `dicks-futures-dragon-start`
(next 2026-09-27T15:30-05:00) / `-stop` enabled. **0W-4D disabled all four
(Azure 2026-09-26T03:04:25Z; guest timers 2026-09-26T03:17Z)** — see the
report §MF.
