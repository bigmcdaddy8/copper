# 0Z-B — Deterministic As-Of Replay: formal real-data proof (2026-10-10)

Semantics: `REPLAY_AS_OF_SEMANTICS.md`. Evidence: `evidence/0Z-B/`.

> **MARKET-TIME CUTOFF ≠ FEED-KNOWLEDGE CUTOFF — proven on authentic data.**
> At 12:14:00 CT on 2026-09-30, **750** trades with market times before 12:14:00
> had not yet been received (up to **20.293 s** late). They are absent from the
> 12:14:00 snapshot and present one second later. The snapshot hash and the
> derived volume change accordingly.

## 1. Code and method

- Replay code: commit `a8edf2fb676f041af6f9dd013b31e47e260a77f2`
  ("feat: deterministic as-of market replay foundation").
- The proof ran at HEAD `62ca5ec50af5e549bab3dc7987e0e6b13e29ce63`. Every
  commit after `a8edf2fb` touches only `docs/trading_strategies/`; `git diff
  a8edf2fb HEAD -- apps scripts` is empty (recorded in `run.log`). Every snapshot
  records that HEAD with `analysis_worktree_modified: false`.
- Dataset: 2026-09-30 `9ac5a21e` (1,396,931 trades, FINALIZED, COMPLETE), prior
  2026-09-29 `6af08205`; plus 2026-10-02 `7e8d7b5e` for the real CANCEL.
- **Split-process harness** (`evidence/0Z-B/harness/`), run sequentially:

| Process | Work | Wall | Peak RSS |
|---|---|---|---|
| A | prepare the current day once; load the prior day's final inputs; 11 cutoffs × 2 builds; late-print cutoffs; visibility audits; terminal snapshot | 10:32 | 5.95 GB |
| B | MARKET_STUDY_STATE_V1 through the accepted 0Z-A CLI | 4:12 | 3.68 GB |
| C | component comparison of the two canonical documents | 0.06 s | 13 MB |
| D | 2026-10-02 real CANCEL | 2:04 | 3.67 GB |

- Database sha256 were taken before process A and after process D.

## 2. Determinism and maturity — 11 cutoffs (America/Chicago)

Each cutoff was built twice in process A; every pair is byte-identical
(`snapshots.tsv`).

| Cutoff | Periods | Overnight | Cash open | 5/15/30/60-min windows | IB | OPENING_TYPE_V1 | VP / TPO value | DAY_TYPE_V1 | Terminal | Lifecycle | Known accepted |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 07:00 | – | DEVELOPING | not yet | not yet | – | not yet | not yet | not yet | – | OPEN_AS_OF | 157,736 |
| 08:29 | – | DEVELOPING | not yet | not yet | – | not yet | not yet | not yet | – | OPEN_AS_OF | 260,862 |
| 08:31 | A | complete | known | NYD ×4 | DEVELOPING | NYD | DEVELOPING | NYD | NYD | OPEN_AS_OF | 271,033 |
| 08:35 | A | complete | known | ✓ NYD NYD NYD | DEVELOPING | NYD | DEVELOPING | NYD | NYD | OPEN_AS_OF | 289,782 |
| 09:00 | A | complete | known | ✓ ✓ ✓ NYD | DEVELOPING | NYD | DEVELOPING | NYD | NYD | OPEN_AS_OF | 383,713 |
| 09:30 | AB | complete | known | ✓ ✓ ✓ ✓ | **complete** | **evaluated** | DEVELOPING | NYD | NYD | OPEN_AS_OF | 501,743 |
| 10:00 | ABC | complete | known | ✓ ✓ ✓ ✓ | complete | evaluated | DEVELOPING | NYD | NYD | OPEN_AS_OF | 607,145 |
| 12:00 | A–G | complete | known | ✓ ✓ ✓ ✓ | complete | evaluated | DEVELOPING | NYD | NYD | OPEN_AS_OF | 871,506 |
| 14:59 | A–M | complete | known | ✓ ✓ ✓ ✓ | complete | evaluated | DEVELOPING | NYD | NYD | OPEN_AS_OF | 1,264,743 |
| 15:00 | A–M | complete | known | ✓ ✓ ✓ ✓ | complete | evaluated | complete | **evaluated** | **7712.75** | OPEN_AS_OF | 1,320,159 |
| 16:00 | A–M | complete | known | ✓ ✓ ✓ ✓ | complete | evaluated | complete | evaluated | **7713.00** | OPEN_AS_OF | 1,396,922 |

NYD = NOT_YET_DETERMINED; ✓ = WINDOW_COMPLETE.

What the table shows:
- No future TPO period ever appears: at 08:31 only A, at 10:00 exactly A–C.
- The Initial Balance and OPENING_TYPE_V1 mature at 09:30; DAY_TYPE_V1, strength,
  structure and the terminal price only at 15:00.
- **Knowledge-time revision on real data:** the 15:00 terminal is 7712.75; at
  16:00 it is 7713.00, the final value. Trades with market times before 15:00
  that were received after 15:00 entered the history once they were known.
- The 16:00 snapshot is still `OPEN_AS_OF` and knows 1,396,922 of 1,396,931
  trades: the capture stopped at 16:00:00.19 CT and the last 9 trades were
  received after 16:00:00. Lifecycle, capture end and closing summary appear
  only after the stop.
- No quality event exists on 09-30 (zero known gaps at every cutoff), so no
  future gap could leak. Gap and interruption timing is proven by fixtures and
  the mutation tests (§6).
- **09:30 vs final:** the OPENING_TYPE_V1 candidates (OPEN_AUCTION_IN_RANGE,
  OPEN_TEST_DRIVE DOWN), their results, directions and every condition status
  at 09:30 equal the final state (`opening_type_0930_vs_final.json`). Only
  candidate quality differs: QUALITY_QUALIFIED at 09:30 ("lifecycle OPEN (not
  FINALIZED)", the honest as-of grade), UNQUALIFIED after finalization.

## 3. Authentic late-print proof (2026-09-30 12:14 CT)

| Cutoff | Known trades with market time < cutoff that were not yet received | Max lag | Snapshot sha256 | Cash-window volume |
|---|---|---|---|---|
| 12:14:00 CT | **750** — absent | 20.293 s | `3c8aac73…d23029f6` | 805,943 |
| 12:14:01 CT | **0** — present | — | `9de0740c…cd636e31` | 806,881 |

- `visibility_121400.tsv` lists the latest of them with market time, receipt
  time, source order and reason (`NOT_YET_RECEIVED: received at/after the
  knowledge cutoff`), e.g. source order 890634: market 17:13:40.073Z, received
  17:14:00.366Z.
- Both snapshots are in `snapshots/2026-09-30_121400.json` and `_121401.json`.
- At 10:00 no trade straddled the cutoff (0); the visibility audit then shows
  the day's largest lags, all NOT_YET_RECEIVED at 10:00.

## 4. Authentic CANCEL (2026-10-02)

The retained source evidence:

| Field | Value |
|---|---|
| Record | CANCEL, `source_order` 105305, `source_index` 7691961727608577538 |
| Market (event) time | 2026-10-02T07:00:00.000Z (02:00 CT) |
| Received (knowledge) time | 2026-10-02T07:40:04.790478Z |
| Original NEW record with that `source_index` | **not retained in the dataset** |

| Cutoff | CANCEL | Deferred / cancels known | Applied | Anomalies | Snapshot sha256 |
|---|---|---|---|---|---|
| received − 1 s | NOT_YET_RECEIVED | 0 / 0 | 0 | none | `e1738def…3125b312` |
| received + 1 s | known → ANOMALY `TARGET_SOURCE_EVENT_NOT_FOUND` | 1 / 1 | 0 | 1 | `8542e52f…88f926cc` |

What this real event proves, and what it does not:
- **Proven:** the CANCEL is invisible before its receipt and becomes known only
  at its knowledge time; nothing about it, not even the reconstruction anomaly,
  leaks backward into the earlier snapshot.
- **Not provable from this event:** "original trade visible, then removed".
  Its target was never captured (no NEW record with that `source_index`; none
  matches its time, price 7750 and size 6 either), so the effective tape is the
  same on both sides of the receipt. The 3 additional effective trades and +4
  volume between the two cutoffs are ordinary trades received in those two
  seconds, not an effect of the CANCEL.
- The only other corpus corrections / cancels (2026-09-23, two CANCELs received
  ~8.5 minutes after their market time) also have no retained target.
- The full "original visible at 10:00, corrected / canceled at 10:10" sequence
  is therefore proven by the deterministic fixtures
  (`test_correction_is_not_applied_backward`, `test_cancel_is_not_applied_backward`).

## 5. Final-state convergence (17:00 CT, after the capture stop)

**57 of 57 component comparisons equal** (`convergence.json`): provenance,
contract, Volume Profile, TPO profile / status / reasons, TPO structure,
DAY_TYPE_V1, DAY_STRUCTURE_STRENGTH_V1, prior day, overnight session / context /
status / reasons / Globex flags (5), opening facts, path facts, opening status /
reasons, OPENING_TYPE_V1, both VWAP studies, terminal price, lifecycle,
accepted / corrections / cancels applied, closing-summary accepted / rejected /
deferred / submitted / persisted / closed-at / difference, 15 dataset identity
fields, 5 dataset-quality fields, and the policy registry.

Expected differences, by design only: schema and temporality fields, the cutoff
and its semantics, the maturity table, the quality-matrix shape, the as-of
counts beyond accepted / applied, the `MARKET_STUDY_SNAPSHOT_V1` registry entry,
the absence of `database_sha256` (a final-file property), the 0Z-A evidence
classification, and the as-of dataset-quality window model.

## 6. Anti-lookahead (deterministic tests)

`test_replay.py` (29 tests), including:
- mutating a trade, a correction and a quality event received at 14:00 CT
  leaves the 10:00 snapshot byte-identical (same hash) and changes 15:00;
- late print, correction, cancel, out-of-order market time, equal receipt time
  split only by source order, future market timestamp, knowledge cutoff earlier
  than the market cutoff;
- no lifecycle / capture end / closing summary / final counts / file checksum
  before the stop; a 10:15 disconnect never qualifies 09:45; an active
  interruption becomes a fixed gap at reconnect;
- CDT and CST boundary instants (16:59:59, 17:00, 08:29:59, 08:30, 08:35, 08:45,
  09:00, 09:30, 15:00, 16:00);
- terminal convergence to MARKET_STUDY_STATE_V1 on fixtures.

## 7. Database immutability

`db_sha_before.txt` = `db_sha_after.txt` for all three databases:
`61489eea…a8aa17c` (09-30), `0b59b719…07dde` (09-29), `cd47e987…c3fae2` (10-02).

## 8. Performance and memory

- Prepare the 1.4M-trade day once: 91.8 s (preliminary run 93.4 s), 3.57 GB.
- Snapshot after preparation: 3.2 s (07:00) to 30.2 s (16:00), growing with
  the number of trades before the cutoff.
- Prior day's final inputs: 119.8 s, +2.2 GB (5.8 GB with the prepared day).
- The first formal run (one process) was stopped by host memory pressure when
  it began a third full-day representation (the final-state build) on top of
  the prepared day and the prior day, on an 11 GB host. Splitting the
  convergence into its own process keeps every process under 6 GB; peak 5.95 GB
  (process A).
- **Backlog — replay memory / prepared-tape optimization (not 0Z-B):** one
  prepared full day holds ~3.6 GB of Python objects (trades, provenance,
  effective trades). Options for later: compact / columnar prepared tape,
  streaming reconstruction, sharing the prior day's derived summary instead of
  its full inputs, incremental snapshots. Replay is functional as is.

## 9. Regression and the WAL flake

Final regression on the proof commit:

| Suite | Result |
|---|---|
| replay (`test_replay.py`) | 29 passed |
| Lab | 809 passed (rerun; see below) |
| K9 | 199 passed |
| full repository | 1,666 passed |

`test_wal_persistence.py` is the known timing flake (backlog, not fixed in
0Z-B). Every occurrence during 0Z-B:
1. a Lab-suite run before the feature commit: 1 failure (name not captured; the
   immediate rerun passed 809);
2. 6 standalone runs of `test_wal_persistence.py`: 2 failures,
   `test_B_crash_during_checkpoint_loses_nothing_and_stays_consistent[0.05]` and
   `test_checkpoint_waits_while_ingestion_is_busy`;
3. the first final Lab run: 1 failure, `test_checkpoint_waits_while_ingestion_is_busy`;
   the rerun passed 809.

Those tests import none of the replay, TPO or market-study modules, and the full
repository run passed both times it ran in 0Z-B. Nothing links the flake to 0Z-B.
