# OPENING_TYPE_V1 — Opening-Type Candidate Policy (0Y-H, FROZEN)

> **OPENING_TYPE_V1 is a pre-registered Laboratory candidate policy, not an
> industry-standard mechanical definition.**
>
> Every result is a **CANDIDATE**. A candidate is descriptive taxonomy over
> deterministic facts. It is not a trading signal and implies no bias.

- **Status:** frozen for prospective validation on 2026-10-09.
  - The sha256 of `tpo_opening_type.py` and of this document are recorded in
    `tpo_opening_type_record.py`, and a test asserts both.
  - Changing any rule or constant below requires `OPENING_TYPE_V2`. V1 is
    never mutated.
- **Policy id:** `OPENING_TYPE_V1`.
- **Version string:** `V1_A_PERIOD_60S_GRACE_EXACT_REFERENCE_TEST_PRIOR_RANGE_ANCHOR`.
- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/tpo_opening_type.py`.
- **Inputs:** `OpeningPathFacts`, which carries the unchanged
  `OPENING_AUCTION_FACTS_V1`, `OVERNIGHT_CONTEXT_V1` and
  `OPENING_PATH_FACTS_V1` facts. `DAY_TYPE_V1`, `DAY_STRUCTURE_STRENGTH_V1` and
  the 0Y-A–0Y-G facts are unchanged.

## 1. Constants (part of V1)

| Constant | Value | Status |
|---|---|---|
| Horizon | period A = [cash open print, end of A). A must be 30 minutes, otherwise the result is NOT_CLASSIFIED. | PO decision |
| Grace | 60 s after the cash open print. The grace price is the last traded price at or before that instant. | Laboratory observation scale. **Not from the Market Profile literature. Not validated.** |
| Reference-touch policy | `EXACT`: the exact reference price is traded at, or traded through. There is never a "within N ticks" rule. | PO decision |
| Test-drive references | PRIOR_HIGH, PRIOR_VAH, PRIOR_POC, PRIOR_VAL, PRIOR_LOW, OVERNIGHT_HIGH, OVERNIGHT_LOW (fixed order) | PO decision |
| Test-drive probe rule | `FIRST_REFERENCE_REACHED` (§5) | Laboratory definition |
| Open-auction location anchor | `PRIOR_RANGE`, inclusive. INSIDE, AT_PRIOR_HIGH and AT_PRIOR_LOW count as IN_RANGE. | PO decision |
| Open Rejection Reverse | DEFERRED (`REFERENCE_DEFINITION_CONFLICT`) | PO decision |

**Why 60 s.** At tick resolution the open was re-crossed within 0.988 s on
every observed session (0Y-F), so the literal "never crosses the open" rule
was rejected. 60 s:
- discards the first minute of opening microstructure;
- is 1/30 of period A, leaving most of A to observe persistence;
- is simple and reproducible.

It must be tested prospectively.

**Why period A.** It is the established Market Profile opening period, and
surveyed sources frame the opening type in roughly the first 30 minutes. It
also avoids classifying from individual sub-second prints. The 5, 15 and 60
minute facts and the tick path stay as supporting evidence. Nothing is
classified from the whole day.

## 2. Shared definitions

- **Open:** the 0Y-F cash open print (`CashOpen`). Its tick is the reference
  tick.
- **Cross:** the 0Y-F tick-grid definition. A cross is a change of strict side;
  trades at the open tick keep the prior side.
- **Post-grace observation:** the grace price, plus every trade after the
  grace instant and before the end of A.
- **A terminal:** the last traded price before the end of A.

## 3. OPEN_DRIVE

| Code | Condition |
|---|---|
| D1 `GRACE_PRICE_OFF_OPEN` | The grace price is strictly above or strictly below the open. That side is the direction (UP / DOWN). |
| D2 `NO_POST_GRACE_OPEN_CROSS` | After the grace instant, no trade before the end of A is strictly on the other side of the open. |
| D3 `A_TERMINAL_ON_GRACE_SIDE` | The A terminal price is strictly on the grace side. |

- If the price is exactly at the open at the grace instant, D1 fails and the
  result is NO. D2 and D3 are then NOT_EVALUABLE.
- **Not required:** minimum excursion, range or volume; outside-value or
  outside-range opening; one-timeframing. These facts are printed beside the
  candidate.

## 4. OPEN_AUCTION family

| Code | Condition |
|---|---|
| R1 `BOTH_SIDES_AFTER_GRACE` | The post-grace observation is strictly above the open at some point and strictly below it at some point. |
| R2 `POST_GRACE_OPEN_CROSS` | At least one open cross after the grace instant and before the end of A. |
| L `PRIOR_RANGE_LOCATION` | Open location against the inclusive prior range. |

| Type | Result |
|---|---|
| `OPEN_AUCTION_IN_RANGE` | R1, R2, and the open INSIDE_PRIOR_RANGE / AT_PRIOR_HIGH / AT_PRIOR_LOW |
| `OPEN_AUCTION_OUT_OF_RANGE` | R1, R2, and the open ABOVE_PRIOR_RANGE / BELOW_PRIOR_RANGE (strictly beyond) |
| `OPEN_AUCTION` | R1 and R2 when there is no usable prior range. Then IN_RANGE / OUT_OF_RANGE are `NOT_CLASSIFIED`; no prior reference is invented. When a prior range exists, this row is NOT_APPLICABLE. |

- Open-auction candidates have no direction.
- The grace only suppresses the initial burst.
- **Not required:** a minimum number of crosses, a specific A/B overlap, a
  counter/dominant ratio, a quiet range, or low volume.
- Prior-value location is printed, but V1 does not use it.

## 5. OPEN_TEST_DRIVE (exact-reference form only)

The **probe reference** is the qualifying reference reached first during A,
using the 0Y-G `ReferenceEncounter` reach. Reach means the first trade at or
beyond the reference, coming from the open's side. Ties keep the fixed
reference order. A reference at the open tick is never a probe reference.

| Code | Condition |
|---|---|
| T1 `EXACT_REFERENCE_REACHED_IN_A` | A qualifying reference is reached before the end of A. |
| T2 `REFERENCE_ON_PROBE_SIDE` | The probe reference lies strictly on the probe side of the open. |
| T3 `OPEN_CROSSED_AFTER_REACH_IN_A` | After the reach, the first trade strictly on the opposite side of the open occurs before the end of A. |
| T4 `OPPOSITE_SIDE_AFTER_CROSS_IN_A` | At or after that cross, and before the end of A, a trade is strictly on the opposite side of the open. |

- **Direction:** the post-cross side, which is opposite to the probe. It is
  never the probe direction.
- **Two conditions are structurally implied, and the CLI still states them:**
  - Under V1, T2 holds whenever T1 does, because the probe side is the side
    of the reference that was reached.
  - Under the tick-grid cross, T4 holds whenever T3 does, because the crossing
    trade is itself strictly on the opposite side. The size of that move is
    reported as evidence.
- **"Initial" is defined by the probe rule.** The initial probe is the move
  that first reaches a qualifying reference; it is not the first tick away
  from the open. The first tick direction is sub-second microstructure: see
  0Y-F finding 2. A cross that happens before the probe reference is reached
  does not count.
- **No "near" rule:**
  - If no reference is reached, T1 fails and the minimum reference distance is
    still reported.
  - A reference reached only after A does not count.
- **Not required:** a minimum opposite excursion. Its size is reported.
- **Evidence:** the reference and its source, price, reach time, exact-touch
  time and probe side; the open-to-reference distance in ticks and points;
  the time from reach to cross; the opposite excursion after the cross within
  A; the A terminal; other references reached in A; and the minimum reference
  distance.

## 6. OPEN_REJECTION_REVERSE — DEFERRED

`DEFERRED`, reason `REFERENCE_DEFINITION_CONFLICT`. Surveyed sources disagree
on three points:
- whether a reference must be reached;
- how large the initial run must be;
- what distinguishes ORR from Open Test Drive.

V1 does not resolve that disagreement by inventing a rule. ORR is not
collapsed into Open Test Drive.

## 7. Candidate-set semantics

- Each evaluation is CANDIDATE, NOT_CANDIDATE, NOT_CLASSIFIED,
  NOT_APPLICABLE or DEFERRED.
- Zero, one or several candidates may match. For example, an Open Test Drive
  together with an Open Auction, or an Open Test Drive together with an Open
  Drive when the test drive's cross came before the grace instant.
- There is no precedence, no `primary_opening_type`, no composite score, and
  no strength word ("strong drive", "weak auction", "high confidence").
- Continuous facts are printed beside every candidate:
  - 5, 15 and 30 minute excursions and counter/dominant ratios;
  - open-cross counts and the last cross;
  - the longest residence on one side;
  - A/B overlap and one-timeframing;
  - reference-touch timing;
  - prior and overnight location.
- These facts are evidence, never conditions.

## 8. Quality (dependency-aware)

- **Opening facts NOT_AVAILABLE**, or A not 30 minutes: the whole
  classification is `NOT_CLASSIFIED`. ORR stays DEFERRED.
- **Current open QUALITY_QUALIFIED:** every candidate is QUALITY_QUALIFIED,
  with reasons.
- **Each candidate also reads only its own inputs:**

| Candidate | Inputs |
|---|---|
| OPEN_DRIVE, generic OPEN_AUCTION | current open only |
| OPEN_AUCTION_IN_RANGE / OUT_OF_RANGE | current open + prior day (the prior's 0Y-C quality grade) |
| OPEN_TEST_DRIVE with a prior-day probe reference | current open + prior day |
| OPEN_TEST_DRIVE with an ONH / ONL probe reference | current open + overnight |
| OPEN_TEST_DRIVE with no reach | current open + prior day (when prior references were evaluated) |

- **A qualified overnight never contaminates prior-only candidates.** The
  observed overnight range is a subset of the true one, so missed early
  activity can only make the true ONH higher or the true ONL lower. "Not
  reached" and "a prior reference was reached first" are therefore robust to
  it. Only a reach of ONH / ONL depends on it.
- **The Globex-open decision** (no tolerance; §9) qualifies overnight facts
  only. It never blocks the cash open, prior range/value, open crossing,
  Open Drive or OAIR/OAOR.

## 9. Globex-open coverage (PO decision, 0Y-H)

- **No tolerance.** The Globex open price is claimed only when the capture
  start is *recorded* at or before 17:00:00 America/Chicago.
  - If the start is after that instant by any amount, or not recorded:
    `globex_open_price` is NOT CLAIMED.
  - `first_observed_overnight_trade` and its timestamp are still reported, and
    never renamed as the Globex open.
- Overnight facts stay computable, graded `QUALITY_QUALIFIED`, with the reason
  that coverage at 17:00 CT is not proven. They are measured from the retained
  overnight tape; activity before the first observation cannot be ruled out.

## 10. Development vs validation

| Evidence | Role |
|---|---|
| The existing research corpus (inspected in 0Y-D–0Y-G) | **DEVELOPMENT / DESCRIPTIVE ONLY** |
| Unseen trading dates after 2026-10-09, scored by the unmodified frozen source | **VALIDATION** |
| Any record whose policy source sha256 differs from the freeze | `POLICY_MODIFIED` — never validation |

- V1 was not revised after its corpus output was seen. Odd results are
  documented, not tuned.
- No statistical sample target is set. A first review is practical after
  several new ordinary trading dates. No rule changes opportunistically
  between them.
