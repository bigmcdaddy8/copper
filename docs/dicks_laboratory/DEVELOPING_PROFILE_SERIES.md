# Phase 0R — Developing VWAP / POC / Value Area Time Series

`dicks_laboratory.developing_profile` extends the accepted 0Q static Volume
Profile analysis into a deterministic **cumulative** time series. It introduces
no new VWAP, POC, or Value Area formula — every snapshot reapplies the
accepted 0O/0P engines to a growing prefix of the same anchored, coverage-aware
selection already used in 0N/0Q.

## Developing ≠ rolling

```text
A 5-minute slice does NOT mean "the last five minutes."

It means "cumulative retained evidence from the anchor,
observed at five-minute checkpoints."
```

Each snapshot's VWAP, POC, VAL, and VAH are computed over **every** retained
trade from the anchor through that snapshot's cutoff — never only the trades
since the previous checkpoint. There is no rolling/moving-window profile in
0R.

## Worked example

Anchor `17:00 CT` (session open), first retained trade `18:16:03.749 CT`,
5-minute slice interval:

```text
Cutoff    New Trades   Cumulative Trades   VWAP        POC       VAL       VAH
18:20         243             243         7691.42    7691.00   7690.75   7691.75
18:25         189             432         7691.68    7692.00   7691.25   7692.25
18:30         446             878         7693.22    7695.00   7692.00   7695.00
18:35 (T)     304            1182         7693.87    7695.00   7692.25   7696.75
```

The `18:35` snapshot is terminal — it contains every retained selected trade
and exactly reproduces the accepted static 0Q result for the same dataset,
anchor, and source mode.

## Slice policy — `DICKS_LAB_DEVELOPING_PROFILE_SLICE_POLICY` / `V1_WALL_CLOCK_ALIGNED_HALF_OPEN_CUMULATIVE_NO_PRECAPTURE_TERMINAL_INCLUSIVE`

Time slicing is itself an explicit, versioned Laboratory policy (there is no
exchange or universal vendor standard for developing-profile checkpoints):

- **Supported intervals**: `ONE_MINUTE`, `FIVE_MINUTES`, `FIFTEEN_MINUTES`
  (default `FIVE_MINUTES`). No seconds, hours, or calendar-day buckets.
- **Wall-clock alignment**: cutoffs align to UTC minute boundaries where
  `minute % interval_minutes == 0`. Because America/Chicago differs from UTC
  by a whole number of hours (never a fractional minute), this UTC alignment
  lands on the same clock minutes in America/Chicago for all three supported
  intervals.
- **Cumulative, not rolling**: every snapshot's analytics cover
  `anchor <= event_timestamp < cutoff`.
- **Half-open regular cutoffs**: a trade exactly at a cutoff belongs to the
  *next* snapshot, not the one ending there — the same half-open convention
  0N already uses for anchor selection.
- **No synthetic pre-capture snapshots**: the first emitted cutoff is the
  first aligned boundary *strictly after* the first retained selected trade.
  Wall-clock slices that precede any retained observation (e.g. `17:05`
  through `18:15` in the worked example above) are never emitted as empty
  snapshots.
- **Terminal snapshot is inclusive**: the last cutoff is the first aligned
  boundary strictly after the *last* retained selected trade, guaranteeing
  every retained trade — including one that lands exactly on a boundary — is
  included in the terminal snapshot.

## Pre-capture coverage vs. observed zero activity

If the requested anchor precedes the first retained trade
(`DATASET_BEGINS_AFTER_ANCHOR`), the unobserved interval before capture began
is **never** represented as a snapshot with zero trades and an unchanged
profile. That would imply the interval was observed and inactive. The correct
statement is "no retained observation coverage for that interval," not
"observed zero market activity." 0R simply does not emit a snapshot for time
that was never captured.

## No-new-trade slices are not gaps

Once the series has started, a later wall-clock slice may retain zero new
trades (e.g. a quiet period, or a genuine feed gap). 0R still emits that
snapshot, with `new_trade_count = 0` and unchanged cumulative analytics. This
proves only that **no new retained observations** arrived in that interval —
it does not prove the market was inactive, and it does not prove the capture
was complete. Absence of retained events is not evidence of absence of market
activity.

## Effective-tape historical semantics (0R design checkpoint)

This is the most important architectural decision in 0R.

The accepted 0K6 `reconstruct_effective_tape` produces only the **final**
reconstructed effective state: for a given source index it applies every
`CORRECTION`/`CANCEL` in `(source_order, source_index, source_record_ref)`
order and returns the resulting `EffectiveTrade`. Nothing in that structure
retains a per-instant "as the feed had told us up to this wall-clock moment"
view — an `EffectiveTrade`'s `event_timestamp` reflects the (possibly
corrected) *trade's own* timestamp, not when a correction or cancel arrived
relative to other events, and no arrival/received time survives into the
final `EffectiveTrade`.

Therefore, the 0R `EFFECTIVE_TAPE` developing series is explicitly a
**retrospectively reconstructed effective-tape series**: each snapshot
reflects the final, accepted lifecycle interpretation of source events,
sliced by each effective trade's own timestamp. It is **not** a model of
"what the feed had told us by that instant" (point-in-time feed-knowledge
reconstruction). Building that would require new architecture — durable
per-event arrival ordering and a way to answer lifecycle queries as of an
arbitrary historical instant — which 0R deliberately does not build. A later
phase could add feed-knowledge-time modeling if it becomes useful; 0R's goal
is market-state development over the already-accepted analytical tape, not a
new provenance model.

The `CANONICAL_NEW_ONLY` series has no such caveat: it is built directly from
immutable `NEW` trade observations and never reflects corrections or cancels.

## VWAP / POC / Value Area evolution are facts, not interpretation

Across snapshots, POC may migrate (e.g. `7694.75 -> 7695.00 -> 7694.75`) and
VAL/VAH may widen, narrow, or shift. 0R records the exact `Decimal` values at
every snapshot and nothing more — no "bullish/bearish," "acceptance/rejection,"
or other interpretive labels. `cumulative_trade_count` and `cumulative_volume`
are monotonically non-decreasing by construction (each snapshot's trade set is
a superset of the previous one); POC, VWAP, VAL, and VAH are **not**
monotonic and may move in either direction between snapshots.

## Reused, not reimplemented

Every snapshot calls the exact same accepted engines used elsewhere in the
Laboratory:

- `dicks_laboratory.volume_profile.build_volume_at_price_profile` (0O) for
  Volume-at-Price and POC (`DICKS_LAB_POC_TIE_POLICY`).
- `dicks_laboratory.value_area.compute_value_area` (0P) for Value Area / VAL /
  VAH (`DICKS_LAB_VALUE_AREA_POLICY`).
- `dicks_laboratory.analysis.prepare_scoped_dataset` (0Q) for anchor
  resolution, trading-date scoping, and coverage classification.

0R contains no developing-specific POC, Value Area, or VWAP algorithm. A
straightforward full recomputation over each cumulative prefix is used
deliberately (0R is a semantic foundation, not a performance optimization);
it is proven exactly equal to the accepted static analysis at the terminal
snapshot.

## Analytical limitations

- Reflects retained captured observations only.
- Absence of retained events in a slice does not prove absence of market
  trades, and does not prove the capture was complete.
- Ordinary CME schedule only; holiday and early-close overrides are not
  modeled.
- The `EFFECTIVE_TAPE` series is a retrospective reconstruction of the final
  accepted lifecycle state, not a point-in-time feed-knowledge model.
- No rolling/moving windows.
- No TPO/Market Profile (letters, Initial Balance, single prints, etc.).
- No volume delta (bid/ask, aggressor side).
- No charting — this is the data/model foundation only.
- No persistence — every series is recomputed on demand from immutable
  durable trades.
- No AI or trading interpretation of any kind.
