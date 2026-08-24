# Value Area / VAH / VAL Policy

There is no CME-mandated Value Area algorithm. Value Area is a Market/Volume Profile
analytical convention, not an exchange product rule, and vendors differ in how much of
their algorithm they publish. This document separates what is general convention, what
is one vendor's documented behavior, and what Dick's Laboratory has adopted as explicit
policy.

## Terms

- **Value Area**: a contiguous region of price levels around the POC that together
  hold at least the target fraction of the profile's total traded volume.
- **Target percentage**: conventionally **70%**, widely described (informally) as an
  analogy to one standard deviation (≈68.2%) rounded to a number that's easy to
  configure in software. This is a described rationale, not a mathematical identity —
  volume distributions are not assumed normal. Dick's Laboratory represents the target
  as an exact `Decimal("0.70")`, not a float, and the target is a configurable
  parameter (`0 < fraction <= 1`), not hard-coded to 70% in the algorithm itself.
- **VAL / VAH**: the lowest and highest **included price levels** (tick-grid prices,
  the same level objects the 0O Volume-at-Price profile already produces) — not
  half-tick row edges. For a discrete tick-based model, level centers are the cleanest
  representation and match how 0O already reports prices.

## What research found

- **General convention** (multiple independent secondary descriptions, e.g. GoCharting's
  documentation): expansion starts at POC, compares the row immediately above and
  below the current region, adds the greater-volume row, and continues until the
  cumulative volume "matches or slightly surpasses" the target — i.e. overshoot by
  including a full row is expected and normal, not an error.
- **Vendor-documented convention** (TradingView's own support article, "Volume profile
  indicators: basic concepts", fetched during this phase): expansion is single-row at a
  time, starting from POC; ties between the above/below candidate are broken by
  choosing the row **closer to the POC**, and a still-tied first comparison is broken by
  choosing the row **above**. This is TradingView's documented behavior — presented here
  as one vendor's convention, not an exchange fact.
- **Not found**: Sierra Chart's public documentation states only that the Value Area
  comprises "the volume bars centered at the point of control... which are the Value
  Area Percentage of the total volume" — it does not publish algorithmic detail (single
  vs. paired rows, tie-break rule). It is not used as a source for algorithm specifics
  here.
- The historical Steidlmayer/CBOT Market Profile (TPO-based) convention sometimes
  compared **pairs** of TPO rows at a time — a consequence of that method's finer,
  half-hour-letter row granularity. Dick's Laboratory's Volume-at-Price levels are
  already coarse (one row per exchange tick), so single-row expansion — the convention
  actually documented for volume-based profiles above — was adopted rather than the
  TPO-specific paired convention.

## Dick's Laboratory policy — `DICKS_LAB_VALUE_AREA_POLICY` / `V1_SINGLE_ROW_GREATER_VOLUME_NEAREST_POC_TIE_ABOVE`

This is an explicit, versioned Laboratory policy choice, informed by (but not claimed to
be identical to) the TradingView-documented convention above:

1. Seed the Value Area with the POC level alone.
2. While included volume is below the target volume and at least one candidate level
   remains: compare the next **occupied** profile level immediately above the current
   region to the next occupied level immediately below it. Add whichever has the
   greater volume. If only one side has a candidate, add that side.
3. **Tie policy**: if the above and below candidates have equal volume, add the one
   fewer occupied levels away from the POC (i.e. the side that has expanded less so
   far); if that is still tied (always true on the very first comparison), add the
   level **above** the POC.
4. A full price level is always included, even if it pushes included volume past the
   target — **levels are never split**. The achieved fraction can therefore exceed the
   target fraction; both `target_fraction` and `included_fraction` are reported so this
   is never hidden.
5. **Sparse levels**: candidates are the next *occupied* levels, not raw adjacent
   tick-grid positions. 0O's Volume-at-Price profile never fabricates zero-volume rows,
   so an untraded tick between two occupied levels simply does not appear as data —
   VAL/VAH can therefore bound a price interval that contains untraded ticks. This
   preserves a contiguous *price* interval while never inventing volume that wasn't
   traded.

Termination is deterministic: the loop only adds full levels and stops as soon as the
target is met/exceeded or no candidate remains (in which case the entire profile is the
Value Area).

## POC is upstream, not re-decided here

The Value Area always starts from and always includes the profile's already-resolved
POC (`DICKS_LAB_POC_TIE_POLICY` from Phase 0O). This phase never re-resolves or
overrides that choice.

## Result model

`ValueAreaResult` is a pure derived artifact, kept structurally distinct from raw
`VolumeAtPriceProfile` facts: policy id/version, target fraction/volume, included
volume/fraction, POC, VAL, VAH, the included levels (ascending price order), and an
optional expansion trace (debug-only; never persisted). No interpretation
("balanced"/"imbalanced"/etc.) is included.

## Deliberately deferred

TPO/Market Profile (letters, initial balance, single prints), volume delta, developing
(event-by-event) Value Area, and persistence of derived POC/VAL/VAH are all out of
scope. The profile and Value Area are always recomputed on demand from immutable
durable trades.

## Analytical limitations

- Reflects the retained captured interval only — not a full session's Value Area.
- Static, finite-profile calculation only; no developing/rolling Value Area yet.
- 70% is a target, not a guarantee: the achieved included fraction is reported exactly
  and may exceed 70% because full price levels are never split.
