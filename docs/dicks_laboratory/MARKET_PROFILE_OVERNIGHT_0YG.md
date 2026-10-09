# Overnight Context & Multi-Scale Opening Path — Corpus Study (0Y-G)

Status: factual foundation only. **No opening type and no inventory label is
implemented or named.** `OvernightContext != trading bias`;
`OpeningProbeFacts (ReferenceEncounter) != Open Test Drive`;
`OpeningScaleFacts != Open Drive`. Nothing here is a trading claim.
- Design and definitions: `TPO_MARKET_PROFILE_0YA.md` §51–§64.
- Evidence: `evidence/0Y-G/`.
- Corpus: the 0Y-D research corpus, read only. No dragon boot.

## 1. Method

```
uv run python scripts/dicks_lab_mp_overnight_study.py OUT_DIR <22 corpus databases>
```

1. Every database is analysed once with the unchanged 0Y-A–0Y-F pipeline,
   plus the overnight session.
2. Each profiled day (17) is paired with its prior trading date exactly as in
   0Y-F, giving the same 7 AVAILABLE pairs.
3. The inspection rules (`tpo_overnight_study.SELECTION_RULES`) were written
   in code before the run and not changed afterwards.

Results of the run:
- The database sha256 values are identical before and after.
- Overnight and opening-path facts for all 17 days took **7.9 s** once
  loaded, against 1,476 s of shared tape loading. (Second run; see the
  evidence README.)

## 2. Quality (kept separate)

| Context | Outcome |
|---|---|
| CURRENT_OPEN | Unchanged from 0Y-F: 14 UNQUALIFIED, 1 QUALITY_QUALIFIED (09-08), 2 NOT_AVAILABLE (08-31 ×2) |
| PRIOR_DAY | Unchanged from 0Y-F: 7 AVAILABLE, 7 NO_PRIOR_PROFILE, 1 PRIOR_PROFILE_INCOMPLETE, 2 with no usable open |
| OVERNIGHT | **16 QUALITY_QUALIFIED, 1 NOT_AVAILABLE** (08-31 befb7b0e: capture began 21 h 33 min after 17:00 and holds no overnight trade) |

The overnight grade needs a PO decision:
- Every dataset whose capture began on the session evening (16 of 17;
  08-31 befb7b0e began the next afternoon) began **0.18–0.36 ms after
  17:00:00 CT**. Under the strict rule (§53 of the design doc), a trade in that
  sub-millisecond gap cannot be ruled out. So every overnight is
  QUALITY_QUALIFIED, and **no Globex open print is claimed on any day**.
- On most days that lateness is the only reason. Additional reasons:
  - a KNOWN_GAP overlaps the overnight on 09-02, 09-21, 09-29 and 08-31
    (c9ebc043);
  - 09-08 has a capture start (0.235 ms late) but no recorded capture end,
    and is lifecycle OPEN;
  - 08-31 (c9ebc043) is also INTERRUPTED.
- The first retained overnight trade came 0.597–1.939 s after 17:00 CT.
  `FIRST_OVERNIGHT_PRINT_VS_PRIOR_TERMINAL` is therefore reported under its
  own name, and `GLOBEX_OPEN_VS_PRIOR_TERMINAL` is absent on every day.
- Whether a capture that starts within some bound of 17:00 counts as covering
  the Globex open is a **data-coverage policy for the PO**. It is not a market
  threshold. 0Y-G does not choose it.

## 3. Overnight findings (facts)

Full table: `evidence/0Y-G/overnight_run/overnight_study.md`.

1. **The cash open was inside the overnight range on 15 of 15 days**, with a
   percentile of 0.19 to 0.86.
2. **Cash open − overnight terminal was 0 or ±1 tick on all 15 days.** The
   carry from 08:29:59 to the open print is essentially nil. The overnight
   move is in `FIRST_OVERNIGHT_PRINT → OVERNIGHT_TERMINAL`, not at 08:30.
3. **Overnight range** was 98–357 ticks (median 208, over 16 overnights).
4. **Overnight vs the prior cash profile** (7 pairs):
   - The overnight traded beyond the prior high on 3 days (09-25 69 ticks,
     09-30 51, 10-02 246) and below the prior low on 3 (09-24 208, 09-29 40,
     10-01 17). On 09-28 it stayed inside the prior range.
   - It was never entirely inside prior value.
5. **Occupancy vs the prior cash terminal** (time fraction above / below):
   - 09-24 0.079 / 0.921
   - 09-25 0.530 / 0.464
   - 09-28 0.000 / 1.000
   - 09-29 0.349 / 0.644
   - 09-30 0.939 / 0.057
   - 10-01 0.982 / 0.017
   - 10-02 0.985 / 0.011

   The TPO-row and volume splits are in the table, each family separate. The
   measure spans almost the whole [0, 1] interval on only 7 days. No split
   has been chosen.

## 4. Multi-scale opening findings (facts)

1. **Tick path:** the open was crossed within 5 min on all 15 days (0 of 15
   uncrossed), as 0Y-F found.
2. **Grace-instant diagnostics** (DIAGNOSTIC ONLY). Days whose held side at
   the instant was *not* crossed within the window:

| Instant | no cross in 5 min | no cross in 15 min | no cross in 30 min |
|---|---|---|---|
| tick path | 0 / 15 | 0 / 15 | 0 / 15 |
| +1 s | 1 (09-29) | 1 | 1 |
| +5 s | 2 (09-29, 09-02) | 1 (09-29) | 1 |
| +15 s | 2 | 1 | 1 |
| +30 s | 2 | 1 | 1 |
| +60 s | 3 (09-29, 09-02, 09-15) | 2 (09-29, 09-15) | 2 |
| A-period (A traded on one side of the open only) | — | — | 0 / 15 |

   - Every day had left the open by +1 s, so no day had an undefined held side.
   - 09-29 is the only day that is uncrossed at every grace instant and every
     window. Its tick path re-crossed three times within the first 0.932 s,
     with at most 4 ticks on the other side.
   - At A-period (TPO) granularity no day is one-sided: every period A
     printed on both sides of the open.
3. **Dominance depends on the scale.** The dominant side at 30 s differs
   from the 30-minute side on 7 of 15 days (one of them a 30 s TIE), and at
   5 min on 4 of 15. The
   30-minute scale equals period A by construction.
4. **Open-cross persistence:**
   - The last open cross in the first 30 min ranged from 0.932 s (09-29) to
     1,795.6 s (09-28; 10-02 was 1,794.8 s).
   - The longest single-side residence in the first hour ranged from 1,177 s
     (09-11) to 3,599 s (09-29).
   - 09-24 stayed above the open for 3,509 s from 13:31:31Z.
5. **Reference encounters, first 30 min:**
   - 8 days reached no prior or overnight reference (5 of them have no
     usable prior context, so only ONH and ONL were in play).
   - 7 days reached at least one reference. On 4 of them the open was
     crossed afterwards: 09-25 PRIOR_VAH +0.099 s, 09-30 PRIOR_HIGH
     +91.3 s, 10-02 ONH +548 s, 10-06 ONH +231 s.
   - The other 3 reached a reference and did not cross back: 09-21 ONH,
     09-23 ONL, 09-29 PRIOR_VAL.

## 5. Mechanical inspection set

| Slot | Day | Fact |
|---|---|---|
| largest overnight range | 09-11 | 357 ticks |
| smallest overnight range | 09-23 | 98 ticks |
| cash open nearest ON high | 10-06 | open − ONH = −21 ticks |
| cash open nearest ON low | 09-23 | open − ONL = 19 ticks |
| most one-sided 5m opening | 09-29 | up 4 / down 67, counter/dominant 0.0597 |
| most one-sided 30m opening | 09-29 | up 4 / down 91, 0.0440 |
| latest last open cross (60-min scale) | 09-11 | 2,867.0 s after the open print |
| longest residence above open | 09-24 | 3,509.0 s from 13:31:31Z |
| longest residence below open | 09-29 | 3,599.1 s from 13:30:00Z |
| fastest reference reach → open cross | 09-25 | PRIOR_VAH reached, open crossed 0.099 s later |
| largest opposite excursion after reference reach | 09-25 | PRIOR_HIGH reach, cross 27 min later, 99 ticks beyond the open within 30 min of the cross |

Per-day reports are in `evidence/0Y-G/overnight_run/reports/`. No day is
described as any opening type.

## 6. Updated feasibility

| Future type | 0Y-F | 0Y-G | Why |
|---|---|---|---|
| `OPEN_DRIVE` | READY (scale decision mandatory) | **READY FOR POLICY DESIGN** | The facts now express any candidate scale directly: tick path, grace instants (held side, cross within 5/15/30 min, favourable/counter excursion), the 30 s–60 min scales (counter/dominant, crossings, last cross, residence), and the A period. The corpus count of "uncrossed" days goes 0 → 1 → 2 → 3 of 15 as the scale coarsens, and is 0 again at A-period granularity. That is, the outcome is **wholly determined by the scale**. The choice belongs to the PO and must be pre-registered and validated prospectively. No winning scale is chosen. |
| `OPEN_TEST_DRIVE` | NEEDS MORE FACTS | **READY FOR POLICY DESIGN**, for the variant where the probe must **reach an exact reference** | The chain *reach a prior/overnight reference → cross the open → expand on the other side* is now represented deterministically: `ReferenceEncounter` (reach, touch, before-reach excursions, cross after, delay, opposite excursion over 5/15/30 min), the ordered event sequence, ONH/ONL as references. The variant where price moves *toward* a reference without touching it stays **REFERENCE DEFINITION TOO SUBJECTIVE**: it needs a "near" policy, which 0Y-G does not create. Policy design must also fix which references qualify, the reach horizon, and any minimum opposite expansion (a pre-registered threshold). |
| `OPEN_REJECTION_REVERSE` | TOO SUBJECTIVE | **REFERENCE DEFINITION TOO SUBJECTIVE** (retained) | The mechanics are measurable: an initial run and a later cross back through the open (grace held side, A-extreme follow-through, reach → cross). But the sources still disagree on its core: whether a reference must be hit (marketcalls yes, NexusFi no), and ATAS's OTD wording matches others' ORR. If a reference is required, ORR and the OTD variant above become hard to tell apart by facts. They are not collapsed to complete the taxonomy. A PO definition is needed first. |
| `OPEN_AUCTION` / `_IN_RANGE` / `_OUT_OF_RANGE` | READY | **READY FOR POLICY DESIGN** | 0Y-G adds more defensible rotational descriptors: time above / below / at the open per scale, the last-cross time, the longest single-side residence, and counter/dominant at every scale beside A/B overlap. None is thresholded. Location remains the 0Y-F range/value location; overnight location adds that all 15 opens were inside the overnight range. |

## 7. Prospective-validation rule

The corpus has been inspected in 0Y-D, 0Y-E, 0Y-F and 0Y-G. Any opening-type
threshold must be:
- pre-registered, then tested prospectively on unseen future dates.

This covers maximum counter excursion, minimum directional excursion, grace
time, reference proximity, maximum open crossings, minimum A/B overlap, an
inventory split, and the capture-start bound of §2. A threshold is not
validated because it organises these 7 pairs / 15 opens well.

## 8. Caveats

- **Sample:** 7 AVAILABLE pairs; 15 available opens; 16 overnights with
  facts (all QUALITY_QUALIFIED, §2).
- **Settlement:** the inventory sources mostly use the prior *settlement*,
  which the Laboratory does not record. `PRIOR_TERMINAL` (last cash-window
  trade before 15:00 CT) is a different reference.
- **Overnight TPO profile** was deferred (design doc §56).
- **Holiday calendar:** none is modelled. Labor Day's overnight (09-07 for
  09-08) is an ordinary 17:00 → 08:30 window.
