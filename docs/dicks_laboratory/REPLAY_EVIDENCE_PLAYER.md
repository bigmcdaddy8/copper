# Replay Evidence Player and Tutor Evidence Interface (0Z-C)

> The player answers three questions with deterministic facts only:
> **What was knowable at T? What changed by T2? Which facts appeared, matured,
> changed or disappeared?** It does not interpret the market and it is not an
> AI tutor.

- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/replay_player.py`.
- **CLI:** `scripts/dicks_lab_replay.py` (extended from 0Z-B).
- **Tests:** `apps/dicks_laboratory/tests/test_replay_player.py`.
- **Real-data proof:** `MARKET_REPLAY_PLAYER_0ZC.md`, `evidence/0Z-C/`.
- **Engine:** the accepted `MARKET_STUDY_SNAPSHOT_V1` (0Z-B). Cutoffs, the
  market / knowledge semantics, source-order ties, correction / cancel handling,
  quality timing and maturity are unchanged; the player only consumes them.

## 1. ReplaySession

```python
session = ReplaySession.load(db, provenance, prior_database=prior_db)  # prepared once, read-only
session.snapshot("09:47")              # HH:MM[:SS] America/Chicago on the session
session.snapshot("2026-09-30T12:14:00-05:00")
session.timeline()                     # structural milestones
session.step("09:45", "+5m")           # +Nm, +Ns, or "next" milestone
delta = session.compare("12:14:00", "12:14:01")
```

- **Seeking** computes the snapshot from the prepared record (no SQLite reload).
  Recent snapshots are cached per cutoff; computation never sleeps.
- **Clock times:** `HH:MM` before 17:00 is on the trading date; at or after
  17:00 it is on the session's opening evening (Sunday for a Monday trading
  date). ISO input must carry an offset; naive times are refused.
- **Milestones:** GLOBEX_OPEN 17:00 (previous evening), CASH_OPEN 08:30,
  OPENING_5MIN 08:35, OPENING_15MIN 08:45, PERIOD_A_END 09:00, IB_END 09:30,
  CASH_STUDY_END 15:00, SESSION_END 16:00.

## 2. Player view (maturity and quality rendering)

Sections, in order: REPLAY TIME, DATA / QUALITY, CURRENT PRICE / RANGE, VWAP,
VOLUME PROFILE, TPO (with IB), PRIOR DAY, OVERNIGHT, CASH OPEN / OPENING FACTS,
OPENING TYPE, DAY TYPE, NOT-YET-DETERMINED / NOT-YET-AVAILABLE ITEMS.

Every component carries an explicit marker; the Human never infers maturity
from the clock:

| Marker | Meaning |
|---|---|
| `DEVELOPING` | its window is in progress; values cover [start, cutoff) |
| `COMPLETE` | its market window has ended (snapshot maturity `WINDOW_COMPLETE`) |
| `NOT_YET_DETERMINED` | a final-study item (OPENING_TYPE_V1 before 09:30; DAY_TYPE_V1, strength, structure, terminal before 15:00) |
| `NOT_YET_AVAILABLE` | its window or anchor has not begun |
| `NOT_AVAILABLE` | its window passed without the evidence it needs |
| `…, QUALITY_QUALIFIED` | computed, with quality reasons |

**COMPLETE, not "FINAL".** A complete window still reflects only what was
received by the knowledge cutoff; a later late print can revise it (on
2026-09-30 the 15:00 terminal is 7712.75 and the 16:00 / final terminal is
7713.00). "FINAL" would overstate that. For OPENING_TYPE_V1 the header reads
`OPENING TYPE (OPENING_TYPE_V1) [COMPLETE…]`: evaluated, frozen V1.

The view also shows deterministic price relations at the cutoff (last known
price ABOVE / AT / BELOW each VWAP; ABOVE / INSIDE / BELOW the developing TPO and
volume value areas, the IB and the prior value area). They are facts, e.g.
"price moved from BELOW to ABOVE the cash VWAP", never conclusions.

## 3. MarketStudyDelta (`MARKET_STUDY_DELTA_V1`)

`compare_snapshot_states(before, after, newly_known=None)` →

```
MarketStudyDelta(schema, dataset_id, from_snapshot_sha256, to_snapshot_sha256,
                 from_cutoff, to_cutoff, newly_known, changes[])
EvidenceChange(domain, path, kind, before, after, evidence_kind,
               status_after, maturity_after, note)
```

- `path` is a JSON pointer into the snapshot, or a named derived fact under
  `/relations/…` or `/evidence/…`.
- `before` / `after` are canonical JSON values; `null` means not available and
  is never confused with `0` or `false`.
- `evidence_kind` reuses the 0Z-A `EvidenceKind` (OBSERVED_FACT, DERIVED_FACT,
  CANDIDATE, QUALITY_QUALIFICATION, LABORATORY_POLICY).
- `newly_known` (from `ReplaySession.compare`): source records known at the
  later cutoff but not the earlier one, how many have market times before the
  earlier market cutoff (late receipt), their maximum lag, and newly known
  corrections / cancels.

| ChangeKind | When |
|---|---|
| OBSERVATION_ADDED | more accepted records known |
| LATE_OBSERVATION_ADDED | newly known records with market time before the earlier cutoff (history revised by newly received evidence) |
| VALUE_AVAILABLE / VALUE_CHANGED / VALUE_WITHDRAWN | a tracked fact null → value, value → value, value → null |
| RELATION_CHANGED | a price relation changed (e.g. BELOW → ABOVE the cash VWAP) |
| COMPONENT_MATURED | a maturity changed (component or opening window) |
| QUALITY_CHANGED | dataset or component quality changed; new gaps / interruptions carry a `note` with the time they first became knowable |
| LIFECYCLE_CHANGED | capture status, lifecycle, connection, closing-summary maturity |
| CANDIDATE_AVAILABLE / CANDIDATE_REMOVED | an OPENING_TYPE_V1 / DAY_TYPE_V1 / structure candidate became determined or disappeared |
| CORRECTION_KNOWN / CORRECTION_APPLIED, CANCEL_KNOWN / CANCEL_APPLIED | corrections / cancels became known / were applied by the accepted reconstruction |
| REJECTION_KNOWN, RECONSTRUCTION_ANOMALY_KNOWN | rejected records / reconstruction anomalies became known |

- Changes are ordered deterministically by domain, then path.
- `canonical_delta_json` uses the 0Z-A encoding; `market_study_delta_sha256` is
  computed over the payload without the hash field. The same two snapshots give
  the same delta, bytes and hash. No current-time field.
- Tracked values are a curated set (prices, VWAPs, Volume Profile and TPO
  headline levels, IB, overnight, cash open and location, prior outcome,
  terminal, strength dominance, structure candidates); the full snapshots stay
  available through their hashes.

## 4. Tutor-facing interface

```python
tutor = TutorEvidenceSession(session)
tutor.state_at("09:45")                 # MARKET_STUDY_SNAPSHOT_V1
tutor.changes_between("09:45", "10:15")  # MarketStudyDelta
tutor.timeline()
```

Nothing else is exposed; a future tutor never touches cutoffs or reconstruction.
No AI behavior is implemented.

The 0AA-A tutor foundation (`AI_TUTOR_EVIDENCE_FOUNDATION.md`) builds lessons on
`ReplaySession` snapshots and deltas without redefining any of them.

## 5. Human replay workflow

1. Choose the trading date's database (and the prior trading date's, if any).
2. `uv run python scripts/dicks_lab_replay.py DB --prior-db PRIOR --milestones`
3. Seek: `… --at 09:47` (repeat `--at` for several times).
4. Inspect the evidence and its markers.
5. Advance: `… --compare 09:47 +5m` or `… --compare 09:10 next`.
6. Read what changed (`--json` for the canonical delta).

Canonical examples on 2026-09-30 (`MARKET_REPLAY_PLAYER_0ZC.md`):
`--compare 12:14:00 12:14:01` (late prints), `--compare 09:29 09:30`
(opening-type maturity), `--compare 14:59 15:00` (day-type maturity).

## 6. Drysdale VWAP Wave — evidence-readiness inventory (audit only)

Source: *VWAP Wave Core Setup Guide* pages 2–6 (local copy, not redistributed;
`DRYSDALE_VWAP_SETUP_GUIDE.md`) and `docs/trading_strategies/STRATEGY_RESEARCH_BACKLOG.md`
(SETUP-01 … 04, CFG-07). No setup is implemented; nothing is defined here.

| Evidence the curriculum needs | Status | Notes |
|---|---|---|
| Session VWAP (cash 08:30 anchor; Globex 17:00 anchor), developing, as of T | **FACT AVAILABLE NOW** | snapshot `vwap`; numerical parity with the NinjaTrader template is not verified (CFG-03) |
| Price above / at / below VWAP at T, and its change T1 → T2 | **FACT AVAILABLE NOW** | `relations`, `RELATION_CHANGED` |
| VWAP change over an interval (e.g. 10 minutes) | **FACT AVAILABLE NOW** | two snapshots + delta; any threshold is playbook policy |
| Count / path of VWAP crossings over an interval ("choppy", "break and reclaim") | NEEDS IMPLEMENTATION | path facts exist for the open only (0Y-G) |
| **VWAP deviation bands** ("VWAP value area") | **NEEDS POLICY DEFINITION**, then implementation | formula, multiplier(s), anchor, session; CFG-07 deferred. Likely prerequisite for every setup. Not implemented in 0Z-C |
| Position inside / outside the VWAP value bands; band "test" / "touch" / "proximity" | NEEDS POLICY DEFINITION | depends on the bands; touch vs proximity needs a rule |
| Breakout out of / break back into VWAP value | NEEDS POLICY DEFINITION | depends on the bands |
| "Acceptance" (time or distance outside / inside value) | NEEDS POLICY DEFINITION | the guide offers "time or distance"; no definition is invented |
| Time spent outside value over an interval | NEEDS IMPLEMENTATION (+ band policy for VWAP value) | exists only for the overnight vs prior value (OVERNIGHT_CONTEXT_V1 occupancy) and period A vs prior zones |
| Backtest / retest ("backtest pullback of the deviation band") | NEEDS POLICY DEFINITION | an encounter model exists for fixed references in period A (0Y-G), not for moving bands |
| "First sign of strength / weakness", "rejection" | NEEDS POLICY DEFINITION | undefined; not invented |
| Price-action confirmation (5-minute candles, closes, wicks) | NEEDS IMPLEMENTATION + POLICY | no 5-minute OHLC facts exist (TPO periods are 30-minute high / low); PB-TREND's two-close proxy is a playbook rule |
| Volatility context ("higher volatility days") | NEEDS IMPLEMENTATION + POLICY | ATR(13) (CFG-06) is not a Laboratory fact |
| Initial Balance context | **FACT AVAILABLE NOW** | developing / complete IB, extensions |
| Volume Profile context (developing and prior POC / VAH / VAL) | **FACT AVAILABLE NOW** | Laboratory value area is 70 % (CFG-05 uses 68 % in NinjaTrader): separate policies, not interchangeable |
| Prior value zone as a reference / objective | **FACT AVAILABLE NOW** | prior H / L / VAH / VAL / POC, as-of known from the prior close |
| Developing value migration (VPOC / value midpoint over 10 minutes) | **FACT AVAILABLE NOW** | two snapshots + delta; thresholds are playbook policy |
| No hindsight for any of the above at time T | **AVAILABLE NOW** | the replay cutoff discipline (0Z-B) |

## 7. Not in 0Z-C

No AI tutor, no natural-language interpretation, no setup labels, no VWAP bands,
no acceptance / rejection definitions, no real-time playback, no GUI.
