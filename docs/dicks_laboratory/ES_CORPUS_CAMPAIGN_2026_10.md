# /ES Prospective Corpus Campaign: trading dates 2026-10-12 .. 2026-11-06

Operations record for routine research data acquisition. This is not an
architecture change: the accepted production capture path (Azure Automation →
dragon → systemd gates → collector, WAL persistence, `/ESZ6` pin) is used
unchanged.

## 1. Corpus classification

| Field | Value |
|---|---|
| CORPUS PURPOSE | PROSPECTIVE_REPLAY_AND_VALIDATION |
| ANALYTIC INSPECTION | NOT YET PERFORMED (no day / opening / Drysdale / VWAP / direction inspection during collection) |
| Drysdale V1 (DRYSDALE_SETUP_CANDIDATES_V1 and its proxies) | frozen at `553ac27` (pushed hash; authored locally as `1c96138` and rebased without change to any frozen file; FREEZE.md sha256s verify) on 2026-10-11, before 2026-10-12: every campaign date is **POST_POLICY_FREEZE / VALIDATION_ELIGIBLE** |
| OPENING_TYPE_V1, DAY_TYPE_V1 and the earlier frozen Laboratory policies | frozen before 2026-10-12: POST_POLICY_FREEZE / VALIDATION_ELIGIBLE |
| A policy frozen after a campaign date | that date is PRE_FREEZE / UNINSPECTED for that policy, never strict prospective validation |

Allowed operational checks only: dataset opened, contract, event flow, writer
health, queue depth, lag, lifecycle, finalization, checksum, submitted =
persisted, disk capacity.

## 2. Dates (20 ordinary trading dates; no exchange exception found)

| Week | Trading dates (each launched the previous evening at 16:55 CT) |
|---|---|
| 1 | 10-12, 10-13, 10-14, 10-15, 10-16 |
| 2 | 10-19, 10-20, 10-21, 10-22, 10-23 |
| 3 | 10-26, 10-27, 10-28, 10-29, 10-30 |
| 4 | 11-02, 11-03, 11-04, 11-05, 11-06 |

No Saturday or Sunday trading dates are captured: the gate timers fire
Sun–Thu only, so there is no Friday launch. No date after 2026-11-06 is
captured.

## 3. Exchange-hours verification (2026-10-11)

- **Columbus Day, Mon 2026-10-12: ordinary full session.** The broker's
  exchange-derived CME session record (Tastytrade `/market-time/sessions/current`,
  instrument collection CME, read on dragon) gives the next session as opening
  at 2026-10-11T22:00Z (17:00 CDT) and closing at 2026-10-12T21:00Z (16:00 CDT),
  with no early halt. The broker's 2026 market holiday list has no date between
  10-12 and 11-06; the next entries are 11-26 (holiday) and 11-27 (half day),
  both outside the campaign. Secondary calendars agree that Columbus Day is not
  a CME Globex holiday. CME's own advisory PDF (2026 Columbus Day clearing
  advisory) could not be fetched by an automated client (HTTP 403); it concerns
  clearing / banking.
- **DST, Sun 2026-11-01:** America/Chicago goes from CDT to CST. Globex hours
  are defined in Chicago clock time (17:00–16:00), so only the UTC mapping
  changes.

## 4. Scheduling layers and DST handling

| Layer | Mechanism | Time basis | DST proof |
|---|---|---|---|
| Azure VM start | 3 OneTime schedules `es-corpus-2026-10-start-{1018,1025,1101}` → runbook Start-Dragon | explicit offset + `timeZone America/Chicago` | 10-18 / 10-25 at 15:30 −05:00; **11-01 at 15:30 −06:00** |
| Azure VM stop | 4 OneTime schedules `es-corpus-2026-10-stop-{1016,1023,1030,1106}` → runbook Stop-Dragon | same | 10-16 / 10-23 / 10-30 at 16:45 −05:00; **11-06 at 16:45 −06:00** |
| Tonight's start | dragon started manually (`az vm start`, the accepted administrative path) at 15:03 CDT 2026-10-11 | — | — |
| Guest preflight | `dicks-lab-preflight-gate.timer`, `OnCalendar=Sun..Thu 16:42 America/Chicago` | tz-aware (systemd) | systemd-analyze: Oct 21:42Z, Nov 22:42Z |
| Guest launch | `dicks-lab-launch-gate.timer`, `Sun..Thu 16:55 America/Chicago` → gate (date-scoped preflight marker) → `dicks-lab-es-session.service` | tz-aware | Oct 21:55Z, Nov 22:55Z |
| Campaign end | `dicks-lab-campaign-end.timer`, `2026-11-06 16:30 America/Chicago` | tz-aware | 2026-11-06 22:30Z |
| Collector session resolver | `sessions.classify_es_session` (America/Chicago zoneinfo) | tz-aware | accepted |

The weekly open-ended pair `dicks-futures-dragon-start` / `-stop` stays
**disabled** and is not used.

## 5. Azure start/stop behavior

dragon runs continuously through each Sunday–Friday block (one boot per week),
as in the accepted 0W-4D pattern. Each Friday the 16:45 CT stop deallocates it,
after the Friday trading-date collector has exited (~16:10 CT) and finalized.
Each Sunday the 15:30 CT start boots it, ahead of the 16:42 preflight.

## 6. Collector configuration (unchanged, tracked unit `dicks-lab-es-session.service`)

- `--symbol /ESZ6`
- `--duration 83700` (23h15m)
- `--max-events 5000000`, about 5× an ordinary session; never the historical CLI default of 1,000,000
- `RuntimeMaxSec=84300`
- `Restart=no`
- data directory `/srv/dicks_laboratory/data/sessions`

The token horizon is the accepted 0W-4 lifecycle: a fresh token at launch,
duration plus the 900 s guard (84,600 s) against a ~24 h token, which leaves
about 1,800 s of headroom.

Writer: the accepted 0W-5C baseline (open dataset WAL + synchronous FULL,
checkpoint worker, DELETE collapse at finalization, submitted − persisted = 0
for FINALIZED).

## 7. Contract and capacity

- **Roll readiness:** `dicks_lab_roll_check.py check` was run on dragon for
  trading dates 2026-10-12 and 2026-11-06. Result: CURRENT (OK), production
  readiness **PASS**. The customary roll is 2026-12-14 and its warning window
  starts 2026-11-30, after the campaign. There is no auto-roll; the December
  roll stays a separate Human action.
- **Capacity:** `/srv/dicks_laboratory` is 251 G with 232 G available.
  - Recent authentic datasets are 0.45–0.84 GB each (the largest so far is 0.84 GB, 10-01).
  - Expected campaign size: 20 × ~0.7 GB ≈ 14 GB.
  - Conservative high-volume case: 20 × 2.0 GB = 40 GB.
  - Free space after the campaign: about 190 G or more. **PASS**; no resize needed.

## 8. Failure behavior (accepted semantics)

- **A date fails:** its evidence is preserved and is never mutated or inspected.
- **Next evening:** a new preflight and a new process run, so the next date proceeds on its own.
- **Untrustworthy conditions fail closed at the 16:42 gate** (no marker, so no launch): invalid or stale pin, authentication failure, or a missing data mount.
- **No late catch-up:** `Persistent=false` on both gate timers.

## 9. Campaign end

- 2026-11-06 16:30 CST: `dicks-lab-campaign-end.timer` disables the preflight and launch gate timers, then itself.
- 16:45 CST: the last Stop-Dragon deallocates dragon.
- All campaign Azure schedules are one-time and expire.

Final state: **DEALLOCATED / COLLECTION DISARMED**. Re-arming needs a new,
separately authorized campaign.

## 10. Per-date health records

These are recorded after each date with the existing audit tooling (no new
telemetry). The fields are:

- **identity:** trading date, dataset_id, contract, start / end, lifecycle;
- **counts:** source, accepted, rejected, submitted, persisted and their difference;
- **continuity:** known gaps, disconnects / reconnects;
- **writer:** writer_overloaded, queue_depth_max, max_persist_lag;
- **finalization:** checksum, integrity, database size, finalization duration.
