# 0Z-C — Replay Evidence Player: real-data proof (2026-10-10)

Reference: `REPLAY_EVIDENCE_PLAYER.md`. Evidence: `evidence/0Z-C/` (player views,
canonical deltas in JSON and text, logs, database sha256, harness).

## 1. Method

- Code: `b8b682b7ae876cbb0548f338a43999cdebda1b91` (feature),
  `55c1664cfb9c613c58c5c8f63a29429eb054d445` (view header fix),
  `16e1e9b2670ba62928d48aef3f58dea010ecd6fb` (test expectation). The proof ran
  at `16e1e9b2` with a clean worktree.
- One process per dataset, sequential (no process holds more than one prepared
  day plus its prior). Every delta was computed twice — once through the
  session cache, once from freshly built snapshots — and compared byte for byte.
- Databases: 2026-09-30 (+ prior 09-29), 2026-10-02, 2026-09-21 (INCOMPLETE: one
  overnight KNOWN_GAP), 2026-08-31 `c9ebc043` (INTERRUPTED; + prior 08-28 with no
  profile). sha256 before and after: unchanged (`db_sha_before.txt` =
  `db_sha_after.txt`).

## 2. Canonical examples (2026-09-30)

### 12:14:00 → 12:14:01 CT — late prints (market time ≠ knowledge)

```
newly known source records: 754 (with market time before the earlier cutoff: 750, max receipt lag 20.293056 s)
[LATE_OBSERVATION_ADDED] /evidence/newly_known_records_with_market_time_before_earlier_cutoff: 0 -> 750
[OBSERVATION_ADDED] /current_dataset/counts/accepted_known: 890628 -> 891382
[VALUE_CHANGED] /volume_profile/total_volume: 805943.0 -> 806881.0
[VALUE_CHANGED] /tpo/profile/value_area/low: 7764.25 -> 7763.75   (and value_area/high 7777.25 -> 7776.75)
[RELATION_CHANGED] /relations/last_price_vs_developing_volume_value_area: INSIDE -> BELOW
```

750 trades whose market time was before 12:14:00 became known in that second;
the snapshot hash changed (`2b942cb5…` → `6246c5d1…`) and the
volume increased by 938 contracts. A deterministic fact, not a signal.

### 09:29 → 09:30 CT — opening-type maturity

```
[COMPONENT_MATURED] /maturity/opening_type: NOT_YET_DETERMINED -> WINDOW_COMPLETE
[COMPONENT_MATURED] /maturity/opening_facts, /maturity/initial_balance, /cash_opening/windows/60min/maturity
[CANDIDATE_AVAILABLE] /opening_type/matched/OPEN_AUCTION_IN_RANGE: null -> OPEN_AUCTION_IN_RANGE (QUALITY_QUALIFIED)
[CANDIDATE_AVAILABLE] /opening_type/matched/OPEN_TEST_DRIVE DOWN: null -> OPEN_TEST_DRIVE DOWN (QUALITY_QUALIFIED)
[RELATION_CHANGED] /relations/last_price_vs_cash_vwap: BELOW -> ABOVE
```

At 09:29 the player shows `OPENING TYPE (OPENING_TYPE_V1) [NOT_YET_DETERMINED]`;
at 09:30 the frozen V1 candidates appear. QUALITY_QUALIFIED is the as-of grade
("lifecycle OPEN (not FINALIZED)", 0Z-B §6).

### 14:59 → 15:00 CT — final-study maturity

```
[COMPONENT_MATURED] /maturity/{volume_profile, tpo}: DEVELOPING -> WINDOW_COMPLETE
[COMPONENT_MATURED] /maturity/{tpo_structure, day_type, day_strength, study_window_terminal}: NOT_YET_DETERMINED -> WINDOW_COMPLETE
[VALUE_AVAILABLE] /prices/study_window_terminal_price: null -> 7712.75
[VALUE_AVAILABLE] /day_strength/strength/dominant_extension: null -> DOWN
[CANDIDATE_AVAILABLE] /tpo_structure/structure/{upper,lower}/excess_candidate: null -> YES
[CANDIDATE_AVAILABLE] /day_type/classification/outcome: null -> CANDIDATE;  primary: null -> NEUTRAL_DAY
```

31 changes in all (`2026-09-30_delta_1459_1500.txt`).

## 3. Quality, cancel and unavailable components on authentic data

- **2026-09-21, a real disconnect** (Sunday 2026-09-20, 21:55 CT):
  - 21:55:11 → 21:55:12.5 CT: `connection_as_of CONNECTED -> DISCONNECTED`;
    `active_interruption null -> {start 02:55:11.948328Z}` "first knowable at
    2026-09-21T02:55:11.948328Z (SOURCE_DISCONNECTED observed)"; completeness
    `COMPLETE -> INCOMPLETE`.
  - 21:55:12.5 → 21:55:14 CT: `DISCONNECTED -> CONNECTED`; the interruption is
    replaced by `KNOWN_GAP [02:55:11.948328Z, 02:55:13.502084Z)` "first
    knowable at 2026-09-21T02:55:13.502084Z (interval closed at reconnect / close)".
  - The earlier snapshot never shows the later degradation.
- **2026-10-02, the real CANCEL** (received 07:40:04.790478Z): one second
  before → after receipt: `CANCEL_KNOWN 0 -> 1`, `RECONSTRUCTION_ANOMALY_KNOWN
  0 -> 1` (TARGET_SOURCE_EVENT_NOT_FOUND). No `CANCEL_APPLIED`: its original
  trade was never captured, and the player does not imply it existed. The
  synthetic before / after sequence (original visible → corrected / canceled) is
  covered by `test_correction_then_cancel`.
- **2026-08-31, interrupted capture** (capture stopped 08:48 CT, 4 KNOWN_GAPs):
  the player stays useful — `DATA / QUALITY [QUALITY_QUALIFIED]`, lifecycle
  INTERRUPTED once the stop is known, cash open COMPLETE but opening windows and
  OPENING_TYPE_V1 `NOT_AVAILABLE` with the accepted reason, prior day
  `NOT_AVAILABLE` (prior has no profile). After the capture stop the cash-window
  components stay `DEVELOPING, QUALITY_QUALIFIED` by the clock (no further
  evidence will arrive; the reasons say why) and DAY_TYPE_V1 stays
  `NOT_YET_DETERMINED` until 15:00 (its final result is NOT_CLASSIFIED, per 0Z-A).

## 4. Determinism

All 8 real-data deltas: identical canonical JSON from the cached and the
freshly built snapshots (`deterministic True` in each log). Delta sha256 values
are in the logs and the JSON files.

## 5. Performance and memory

| Dataset | Prepare session | First snapshot | Subsequent seek | Compare (cached) | Peak RSS |
|---|---|---|---|---|---|
| 2026-09-30 + prior | 204.4 s (incl. the prior day) | 12.0 s (09:47) | 7.9–23.5 s | 0.7–0.9 s (both cached); 18.2 s (one new snapshot) | 3.86 GB |
| 2026-10-02 | 85.3 s | 9.1 s | — | 5.4 s | 3.69 GB |
| 2026-09-21 | 54.3 s | 2.8 s | — | 1.6–2.9 s | 2.37 GB |
| 2026-08-31 | 14.8 s | 3.4 s | 2.8–3.4 s | 0.1 s | 0.64 GB |

A comparison costs the snapshots it needs plus a scan of the prepared record for
newly known evidence; with both snapshots cached it is under a second.

Observation (not a claim): the 2026-09-30 session with its prior peaked at
3.86 GB here, versus 5.8 GB in 0Z-B where the current day was prepared before
the prior. `MarketReplay.load` loads the prior first; the difference is
consistent with allocator reuse. The replay-memory optimization backlog item
remains open and separate.

## 6. Read-only

All six databases' sha256 unchanged; no network, broker or Azure access by the
player.
