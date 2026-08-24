# Volume-at-Price / Point of Control Foundation

## Terms

- **Volume at Price**: exact traded volume (Decimal `size`, summed, never deduplicated
  or weighted) accumulated at each valid price level within an already-selected trade
  set. It is an aggregation fact, not a policy decision.
- **Price level**: one exact tick-grid price, plus its accumulated volume and trade
  count.
- **Tick size**: the instrument's minimum price increment. For ES this is `0.25` index
  points, per CME's published contract specification (corroborated by multiple broker
  contract-spec pages, since CME's own JS-rendered site could not be machine-fetched
  directly; see Phase 0O report for sources). Value is defined once, versioned, in
  `volume_profile.ES_PRICE_GRID`.
- **Point of Control (POC)**: the price level with the greatest accumulated traded
  volume. `POC = price with greatest traded volume` — strictly a volume-maximization
  fact, never nearest-to-VWAP except as an explicit tie-break (see below).
- **Canonical vs. effective profile**: a profile built from `CANONICAL_NEW_ONLY` trades
  reflects only accepted NEW prints; a profile built from `EFFECTIVE_TAPE` trades
  reflects the 0K6 correction/cancel-aware reconstruction. The profile engine does not
  recompute lifecycle semantics itself — it consumes whichever trade tuple the caller
  selected and records that choice as `source_mode` metadata.

## POC tie policy

A volume tie between two or more price levels is possible. There is **no exchange or
universal vendor standard** for resolving this — Point of Control is a Market Profile
analytical convention (not a CME product rule), and different charting vendors break
ties differently (or don't guarantee determinism at all).

Dick's Laboratory adopts an explicit, versioned, Laboratory-only policy:
`DICKS_LAB_POC_TIE_POLICY` / `V1_NEAREST_VOLUME_WEIGHTED_MEAN_THEN_LOWER_PRICE`.

1. If exactly one level holds the maximum volume, it is the POC.
2. If multiple levels tie for maximum volume, select the tied level whose price is
   closest to the volume-weighted mean price of the *entire* profile.
3. If still tied, select the lower price.

This is a Laboratory policy choice, not an exchange fact or a claimed universal vendor
convention — documented and versioned so it can be revisited without silently changing
past results.

## Price-grid validation

Every selected trade's price must land exactly on the instrument's tick grid. Validation
is exact Decimal round-trip arithmetic (`tick_index = round(price / tick_size)`, then
`tick_index * tick_size == price`) — no binary float modulo, no silent rounding onto the
nearest tick. An off-grid price becomes an explicit `PRICE_NOT_ON_TICK_GRID` anomaly,
reported separately from the profile; the source trade is never mutated.

## Deliberately deferred

Value Area (VAH/VAL, 70% convention), TPO/Market Profile letters, developing
(event-by-event) POC, and buy/sell volume delta are all explicitly out of scope for this
phase — each embeds its own policy choices and belongs to a later phase (Value Area is
expected next). This phase produces the raw Volume-at-Price aggregation and a single
finite-set POC only.

## Analytical limitations

- Profiles reflect the retained captured interval only — not proof of a complete
  session's tape.
- No Value Area, no TPO, no volume delta, no developing/rolling POC yet.
- The profile engine recomputes on demand from durable trades; no derived profile is
  persisted to SQLite.
