# Replay / As-Of Semantics — MARKET_STUDY_SNAPSHOT_V1 (0Z-B)

> ## MARKET-TIME CUTOFF ≠ FEED-KNOWLEDGE CUTOFF
>
> A trade with market time 09:55 that the Laboratory received at 10:05 is
> **NOT YET KNOWN** at 10:00, even though its market time is earlier. At 10:10
> it enters the effective tape, subject to the market-time cutoff.
>
> A snapshot at T shows only the evidence a trader / the Laboratory could have
> known at T. It never shows what the final database knows now.

- **Schema:** `MARKET_STUDY_SNAPSHOT_V1` (`replay.SNAPSHOT_SCHEMA`); a breaking
  change is `MARKET_STUDY_SNAPSHOT_V2`. `MARKET_STUDY_STATE_V1` is unchanged.
- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/replay.py`.
- **CLI:** `scripts/dicks_lab_replay.py`.
- **Tests:** `apps/dicks_laboratory/tests/test_replay.py`.
- **Real-data proof:** `MARKET_REPLAY_0ZB.md`, `evidence/0Z-B/`.

## 1. Source-field audit (what the retained data can prove)

| Evidence | Market time | Knowledge time | Order | Sufficient? |
|---|---|---|---|---|
| Accepted NEW trade | `trade_observations.event_timestamp` | `observation_source_provenance.received_at` | `source_order` (also `dataset_sequence`, not used) | **Yes** |
| CORRECTION / CANCEL | `deferred_dxlink_timesale_events.event_time` | its own `received_at` | its own `source_order`; target by `source_index` | **Yes** |
| Rejected record | `rejected_dxlink_timesale_source_records.event_time` | its `received_at` | `source_order` | **Yes** for DXLink rejections; a non-DXLink rejection has no `received_at` and is counted as `rejected_knowledge_time_unrecorded`, never as known |
| Lifecycle point evidence (CAPTURE_STARTED, SOURCE_CONNECTED / DISCONNECTED / RECONNECTED, CAPTURE_STOPPED) | — | `observed_at` | — | **Yes**, with the limitation below |
| KNOWN_GAP / SUSPECTED_GAP | `interval_start`, `interval_end` | no write time is stored; the collector writes the interval at reconnect or close, i.e. at `interval_end` | — | **Yes**, by that recorded rule |
| `datasets.lifecycle_state`, `capture_ended_at`, closing summary | — | written at close | — | revealed only once the stop is known |

Findings:
- `received_at` is the collector's receipt instant (knowledge), not the SQLite
  commit instant. The commit lag (up to 186 s on 09-30, `writer_max_persist_lag_s`)
  is a persistence detail; the Laboratory knew the record at receipt.
- `dataset_sequence` is never used for knowledge order: rejected and deferred
  records consume `source_order` but not `dataset_sequence`.
- **Limitation (documented, not hidden):** on a terminal connection loss that
  ended a run outside the reconnect loop, the collector writes a
  SOURCE_DISCONNECTED back-dated to the last progress instant (0W-2B §8). Its
  true write time is the close. Replay treats `observed_at` as the knowledge
  time, so such a disconnect could appear up to (close − last progress) early.
  No such event exists in the 0Z-B proof dataset (2026-09-30); 2026-08-31
  (INTERRUPTED) is the kind of dataset where it can occur.
- Authentic receipt lag on 2026-09-30: 0.013 s to 20.3 s; 3,280 trades arrived
  more than 1 s after their market time and 1,023 more than 5 s. 2026-10-02 holds
  a real CANCEL received 40 minutes after its market time (its target trade was
  never retained; see `MARKET_REPLAY_0ZB.md` §4). The distinction is material,
  not theoretical.

## 2. ReplayCutoff

`ReplayCutoff(market_time_cutoff_utc, knowledge_time_cutoff_utc,
knowledge_source_order_cutoff=None)`:
- two separate fields, always; `ReplayCutoff.at(T)` sets both to T for ordinary
  historical replay;
- timezone-aware input only (naive times are refused), canonical in UTC;
  presentation in America/Chicago;
- `clock = min(market, knowledge)`: maturity is judged on it, because nothing
  received after the knowledge cutoff can be used.

## 3. Inclusion semantics (exact)

1. **Knowledge.** A source record is known iff `received_at <
   knowledge_time_cutoff_utc` (strict) and, when the cursor is set,
   `source_order <= knowledge_source_order_cutoff`.
2. **Corrections / cancels.** The accepted reconstruction
   (`reconstruct_effective_tape`) runs over the known NEW records and the known
   CORRECTION / CANCEL records only, in `source_order`. A correction or cancel
   received later is never applied backward: at 10:00 the 09:55 trade shows its
   original price; at 10:10 (after a 10:05 correction) the corrected one.
3. **Market.** A known effective trade enters analytics iff `event_timestamp <
   market_time_cutoff_utc` (strict) and it belongs to the trading-date session.
   A record whose market time is at or after the cutoff (e.g. a provider
   timestamp ahead of receipt) is known but excluded, and counted in
   `known_records_with_market_time_at_or_after_cutoff`.
4. **Tie-breaking.** Records with the same `received_at` are either both known
   or both unknown at a time cutoff; the source-order cursor separates them.
   The reconstruction applies them in `source_order`.
5. **Lifecycle evidence.** Point evidence is known iff `observed_at < knowledge
   cutoff`. A gap interval is known iff `interval_end < knowledge cutoff`.
6. **Active interruption.** A known SOURCE_DISCONNECTED with no known
   reconnect / stop is an `ACTIVE_INTERRUPTION [disconnect, knowledge cutoff)`.
   It qualifies quality like a KNOWN_GAP. After the reconnect is known, the
   recorded fixed interval replaces it.
7. **Windows are half-open.** At a cutoff exactly at 08:30:00 the 08:30:00.000
   print is not yet included; at 09:30:00 the snapshot holds exactly A and B.

## 4. Gap discovery lifecycle

| Time | What is known |
|---|---|
| before the disconnect | nothing: a later disconnect never qualifies an earlier snapshot |
| disconnect observed, no reconnect yet | `connection_as_of: DISCONNECTED`, `ACTIVE_INTERRUPTION` from the disconnect to the cutoff; quality QUALITY_QUALIFIED |
| reconnect observed | the KNOWN_GAP interval is fixed; `connection_as_of: CONNECTED` |
| capture stopped | lifecycle and closing summary become known |

## 5. Snapshot maturity

`Maturity`: `NOT_YET_AVAILABLE` (its window or anchor has not begun),
`DEVELOPING` (values over `[start, clock)`), `WINDOW_COMPLETE` (its market window
ended before the clock), `NOT_YET_DETERMINED` (a final-study component before its
window completes), `NOT_AVAILABLE` (the window passed without the evidence it
needs).

`WINDOW_COMPLETE` means the market window is over. Values still reflect only
what was received by the knowledge cutoff; a late print received afterwards
appears in a later snapshot. That is intentional: history revised by newly
received evidence.

| Component | Before | Developing | Complete / determined at (CT) |
|---|---|---|---|
| Dataset identity, contract, policy registry, analysis commit | — | — | known from replay start |
| Lifecycle | `NOT_STARTED` | `OPEN_AS_OF` | the stored state once the stop is known |
| Closing summary, capture end, final counts | — | as-of counts only | after the recorded close |
| Prior-day context | `NOT_YET_AVAILABLE` until the prior dataset's recorded close | — | REPLAY_READY from then |
| VWAP (Globex anchor) | before 17:00 | 17:00 → 16:00 | 16:00 session end |
| VWAP (cash anchor) | before 08:30 | 08:30 → 16:00 | 16:00 |
| Overnight facts | before 17:00 | developing high / low / range / last | 08:30 (accepted OVERNIGHT_CONTEXT_V1) |
| Cash open | before the print (≤ 60 s) | — | at the print; NOT_AVAILABLE after 08:31 without one |
| Prior range / value location, gap | — | — | at the cash open print |
| Opening windows 5 / 15 / 30 / 60 min | NOT_YET_DETERMINED | — | 08:35 / 08:45 / 09:00 / 09:30 |
| OPENING_AUCTION_FACTS_V1, OPENING_PATH_FACTS_V1 | NOT_YET_DETERMINED | — | 09:30; the fields in `fields_developing_until_study_window_end` stay DEVELOPING until 15:00 |
| OPENING_TYPE_V1 | NOT_YET_DETERMINED (no temporary candidate) | — | 09:30, frozen V1 over the evidence known then |
| Volume Profile POC / VAL / VAH | before 08:30 | 08:30 → 15:00 | 15:00 |
| TPO profile, TPO POC / VAL / VAH | before 08:30 | only periods begun before the clock; the current period partial; no future period | 15:00 |
| Initial Balance | — | DEVELOPING before 09:30 | 09:30 |
| TPO structure (excess / poor / one-TPO zones / tails) | NOT_YET_DETERMINED | — | 15:00 |
| DAY_TYPE_V1, DAY_STRUCTURE_STRENGTH_V1 | NOT_YET_DETERMINED | — | 15:00 |
| Study-window terminal price | NOT_YET_DETERMINED (`last_known_price` is a separate as-of fact) | — | 15:00 |

Opening-fact fields that read the cash path after 09:30 (DEVELOPING until
15:00, listed in every 09:30–15:00 snapshot):
- opening quality `gaps_later_in_study_window`, `study_window_truncated`;
- early TPO `a_only_rows_full_day`, `a_only_rows_at_day_high`,
  `a_only_rows_at_day_low`;
- `one_timeframing` (all fields);
- prior value / range zone `first_entry_utc`, `first_exit_above_utc`,
  `first_exit_below_utc`, `first_return_utc`, `time_to_return`;
- OPENING_TYPE_V1 strength `opening_higher_low_run`, `opening_lower_high_run`
  (continuous facts, never conditions).

## 6. Quality as of

- Gaps, interruptions and lifecycle evidence count only when known (§3).
  A 10:15 disconnect never qualifies a 09:45 snapshot.
- Developing components are qualified only by the capture start and by gaps
  known to overlap `[window start, clock)`.
- Complete components use the accepted quality rules with the as-of lifecycle.
  While the capture is running that is `OPEN`, so the accepted rule adds
  "lifecycle OPEN (not FINALIZED)": an intraday opening-type candidate is
  QUALITY_QUALIFIED until the dataset is finalized. That is the honest as-of
  grade; after the stop is known it becomes the stored state.
- The capture end handed to the accepted rules while running is
  `min(knowledge cutoff, recorded end)`: the capture is known to be running
  through the cutoff, and nothing later is claimed.

## 7. No final-metadata leakage

Before the stop is known a snapshot has: lifecycle `OPEN_AS_OF`, no capture end,
no closing summary (`NOT_YET_DETERMINED`), as-of counts only, no gap learned
later, no terminal price, no day type, no strength, no structure. The final
database file checksum is never in a snapshot (it is a property of the final
file). Replay evidence records it outside the canonical snapshot.

## 8. Canonical snapshot and identity

- Same encoding as MARKET_STUDY_STATE_V1 (sorted keys, Decimal strings, UTC
  microsecond timestamps, exact durations, null never 0, no floats, no
  generation time); shared sub-objects as `$ref` with the same pointers.
- `market_study_snapshot_sha256 = sha256(canonical payload without the hash field)`.
- The payload includes the cutoff (market, knowledge, source-order cursor), the
  analysis commit and the policy registry (with `MARKET_STUDY_SNAPSHOT_V1`), so
  each is part of the hash.
- `snapshot_identity(s)`: dataset id, schema, both cutoffs, cursor, analysis
  commit, snapshot sha256.

## 9. Anti-lookahead guarantees (tested)

- Mutating a trade, a correction or a quality event received at 14:00 leaves the
  10:00 snapshot byte-identical (same hash) and changes the 15:00 snapshot.
- Late print, correction, cancel, out-of-order market time, equal receipt time
  split by source order, and future market timestamp fixtures, each with its
  visibility reason.

## 10. Final-state convergence

At a cutoff after the capture stop (e.g. 17:00 CT), the overlapping components
equal the MARKET_STUDY_STATE_V1 objects exactly (dataclass equality): contract,
Volume Profile, TPO profile, structure, DAY_TYPE_V1, strength, prior day,
overnight session and context, opening and path facts, OPENING_TYPE_V1, VWAP
studies, terminal price, lifecycle, capture interval, closing-summary counts,
known gaps.

Expected differences, by design: `schema`, `state_temporality`, the cutoff and
its semantics, the maturity table, the as-of counts, the quality-matrix shape,
the `MARKET_STUDY_SNAPSHOT` registry entry, and no `database_sha256`.

At 09:30 the OPENING_TYPE_V1 candidates and every condition already equal the
final ones (types, results, directions, condition statuses); only candidate
quality differs, by the lifecycle rule in §6.

## 11. Replay API (for a player, tutor or lesson engine)

```python
replay = MarketReplay.load(db, provenance, prior_database=prior_db)
state = replay.snapshot(at=T)                                  # both clocks at T
state = replay.snapshot(cutoff=ReplayCutoff(market, knowledge, source_order))
states = replay.snapshots([t1, t2, ...])
steps = replay.source_order_steps(market, knowledge, [n1, n2, ...])  # event-by-event
audit = replay.visibility(cutoff)                              # why each record is / is not visible
```

The database is read once (`prepare_replay`); snapshots are pure and never
sleep. Intended future capability (not implemented): at historical time T, show
only what could have been known at T — "What would you have concluded at
09:45?", "What changed by 10:15?", "Which evidence appeared after your
decision?". The same cutoff discipline is what later tutoring around
acceptance / rejection, VWAP and value interaction, or breakout and
return-to-value sequences (the deferred Drysdale backlog) needs to stay free of
hindsight. No setup labels exist.
