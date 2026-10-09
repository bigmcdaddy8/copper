# Opening-Auction Facts & Prior-Day Context — Corpus Study (0Y-F)

Status: factual foundation only. **No opening type is implemented or named.**
`OpeningAuctionFacts != OpeningType`. Nothing here is a trading claim.
- Design and definitions: `TPO_MARKET_PROFILE_0YA.md` §40–§50.
- Evidence: `evidence/0Y-F/`.
- Corpus: the 0Y-D research corpus (`MARKET_PROFILE_CORPUS_0YD.md`), read only.
  No dragon boot was needed.

## 1. Method

```
uv run python scripts/dicks_lab_mp_opening_study.py OUT_DIR <22 corpus databases>
```

1. Every database is analysed once (unchanged 0Y-A–0Y-E pipeline).
2. Every profiled day (17) gets a `CashOpenSession`.
3. Each day is paired with the dataset for its **prior trading date**
   (previous weekday; never the previous calendar day). No closures were
   needed in this date range.
4. The inspection-set rules (`tpo_opening_study.SELECTION_RULES`) were written
   in code before the study ran. They were not changed after seeing results.

Results of the run:
- The database sha256 values are identical before and after.
- Opening facts for all 17 days took **2.2 s** once loaded, against 1,482 s
  of shared tape loading.

## 2. Pairing and quality outcome (17 profiled days)

| Context outcome | Days | Dates |
|---|---|---|
| `AVAILABLE` (same contract, prior UNQUALIFIED) | **7** | 09-24, 09-25, 09-28 (prior Fri 09-25), 09-29, 09-30, 10-01, 10-02 |
| `NO_PRIOR_PROFILE` | 7 | 09-02 (prior 09-01 has no profile), 09-07 (09-04 not in corpus), 09-11 (09-10 no profile), 09-15, 09-21, 09-23, 10-06 |
| `PRIOR_PROFILE_INCOMPLETE` | 1 | 09-08: prior 09-07 is Labor Day, whose cash session stopped after G (H–M empty) |
| `CURRENT_OPEN_INCOMPLETE` | 2 | both 08-31 datasets: capture does not cover [08:30, 09:30) |
| `CONTRACT_CHANGED` | 0 | none in the corpus. ESU6 → ESZ6 days are never adjacent here. Covered by fixtures. |
| `MULTIPLE_PRIOR_DATASETS` | 0 | 08-31 has two datasets but is never anyone's prior with a profile. Covered by a fixture. |

Opening quality:
- **NOT_AVAILABLE: 2** (08-31 ×2).
- **QUALITY_QUALIFIED: 1.** 09-08 has no capture interval recorded (so its
  08:30 coverage is unverified), and its lifecycle is OPEN.
- **UNQUALIFIED: 14.**
- No KNOWN_GAP or SUSPECTED_GAP overlaps any opening window. The overnight
  gaps on 09-02, 09-21 and 09-29 did not qualify their openings, as intended.
- 09-11's capture ends before 15:00 (`study_window_truncated: yes`). Its
  opening is unqualified, but its full-window entry/exit facts are truncated.

## 3. Facts table

The full table is in `evidence/0Y-F/opening_run/opening_study.md`. Per-day
reports (all facts plus an A/B TPO matrix marked with the open and prior
references) are in `evidence/0Y-F/opening_run/reports/`.

Location of the open, over the 7 AVAILABLE pairs:

| Date | vs prior range | vs prior value | Gap (ticks) | 30m up/down | A/B overlap |
|---|---|---|---|---|---|
| 09-24 | BELOW_PRIOR_RANGE (100 t below low) | BELOW | −158 | 59 / 17 | 0.2500 |
| 09-25 | INSIDE | INSIDE (2 t below VAH) | +48 | 65 / 41 | 0.7944 |
| 09-28 | INSIDE | BELOW | −128 | 10 / 56 | 1.0000 |
| 09-29 | INSIDE | INSIDE | +44 | 4 / 91 | 1.0000 |
| 09-30 | INSIDE | ABOVE | +77 | 64 / 15 | 0.3188 |
| 10-01 | INSIDE | BELOW | +67 | 41 / 79 | 0.0909 |
| 10-02 | ABOVE_PRIOR_RANGE (193 t above high) | ABOVE | +254 | 61 / 64 | 0.8532 |

## 4. Findings that matter for opening-type design

1. **The cash open is well defined on this tape.**
   - Every available day printed within 0.161 s of 08:30:00 CT (13 of 15 at
     0.000 s).
   - The 60 s tolerance was never approached.
2. **The open is re-crossed almost immediately, every day.**
   - The first strict cross of the open tick happened within **0.988 s** on
     all 15 available days (13 within 0.4 s).
   - 60-minute open-cross counts were 3–66 (median 34).
   - So the literal Open Drive rule, "never trades back through the open",
     is satisfied on **0 of 15** days at tick resolution. A usable drive
     policy must state an explicit scale: a tolerance in ticks, a time after
     the open, or period/TPO granularity. That is a policy decision. The
     facts to express any such rule are in place.
3. **The "largest initial move before an opposite open cross" slot selected
   10-02 with only 8 ticks.** The first cross comes so early that the initial
   move before it is always tiny. This is the same finding as (2) from the
   path-ordering side.
4. **A-extreme follow-through.** On every available day, at least one of the
   two period-A extremes was followed by trade strictly on the other side of
   the open before 09:30; on 5 days both were. This is the raw material for
   any rejection-style rule. It is not labelled.
5. **Reference touches happen.** On 09-25 the open was 2 ticks under the
   prior VAH, which was touched and crossed 46 ms after the open, and the
   prior high was touched 4 min 17 s in. Touch/cross timing is measured to
   the millisecond. Deciding which touch is a "test" is not.
6. **Outside-value openings re-entered value slowly or not at all**
   (09-24: 2 h 47 min; 09-28: 2 h 57 min; 09-30: 6 h 18 min; 10-01 and
   10-02: never). The inspection slot "fastest outside-value re-entry" is
   therefore 2 h 47 min. The study window is long enough to observe this.

## 5. Mechanical inspection set

| Slot | Day | Fact |
|---|---|---|
| largest open above prior range | 10-02 | 193 ticks above prior high |
| largest open below prior range | 09-24 | 100 ticks below prior low |
| most one-sided first 30 min | 09-29 | up 4 / down 91 ticks, counter/dominant 0.0440 |
| most balanced first 30 min | 10-02 | up 61 / down 64, counter/dominant 0.9531 |
| largest initial move then opposite open cross | 10-02 | 8 ticks up before the first cross at +0.359 s |
| most open-price crossings (60 min) | 10-02 | 66 |
| fastest outside-value re-entry | 09-24 | 2 h 46 min 42 s |

The rendered facts and the early TPO matrix for each day are in
`evidence/0Y-F/opening_run/reports/`. No day is described as any opening
type.

## 6. Opening-type classification feasibility

| Future type | Assessment | Why |
|---|---|---|
| `OPEN_AUCTION_IN_RANGE` | **READY FOR POLICY DESIGN** | The location half is already exact (`range_location`, `value_location`). The "auction" half needs an explicit, pre-registered rotation rule over facts that exist: 30/60-min counter/dominant excursion, open crossings, A/B overlap ratio, one-timeframing runs. Sources agree on the shape (rotation around the open, inside the prior range). |
| `OPEN_AUCTION_OUT_OF_RANGE` | **READY FOR POLICY DESIGN** | As above, with `ABOVE/BELOW_PRIOR_RANGE`. Only 2 such opens are in the corpus, so validation must be prospective. |
| `OPEN_AUCTION` | **READY FOR POLICY DESIGN** | The union of the two above. Sources split on whether the anchor is prior range (marketcalls) or prior value (LuxAlgo). Both are measured, so the policy must pick one. |
| `OPEN_DRIVE` | **READY FOR POLICY DESIGN** (one explicit scale decision is mandatory) | The facts are sufficient: excursions, counter/dominant, open crossings and their timestamps, A-extreme follow-through, one-timeframing. But the literal reference rule fails 15/15 at tick resolution (finding 2), so a tolerance or time-scale must be chosen and documented as a Laboratory policy. "Strong" and "persistent" stay unencoded. |
| `OPEN_TEST_DRIVE` | **NEEDS MORE FACTS** | Requires identifying a *probe* toward a reference, followed by a move away through the open. Reference touch/cross timing exists for the prior-day references. Still missing: (a) the overnight high/low, which practitioners also probe and 0Y-F defers; (b) a deterministic "probe extreme then reversal" segmentation of the early path (which extreme was the probe, and the move away from it before and after the open cross). |
| `OPEN_REJECTION_REVERSE` | **REFERENCE DEFINITION TOO SUBJECTIVE** | Sources disagree on its core: whether a reference must be hit (marketcalls yes, NexusFi no), and ATAS describes OTD in words others use for ORR. "Rejected" / "initial run" have no agreed scale, and since every day re-crosses the open within a second, any ORR rule is wholly determined by the unchosen scale. It needs a PO decision on which definition is adopted before policy design. |

## 7. Overnight inventory (deferred; next dependency)

None of the surveyed definitions of the six types *requires* overnight data,
so 0Y-F isolates the cash opening as requested. Overnight high/low (and
inventory) is nevertheless the **next dependency**:
- an Open-Test-Drive probe is often of the overnight extreme, not a prior-day
  reference;
- Dalton-style preparation uses the overnight inventory.

The corpus datasets already contain the overnight Globex tape, so this needs
no new collection.

## 8. Caveats

- **Sample size:** 7 AVAILABLE pairs and 15 available opens. Everything above
  is descriptive, and any threshold chosen from it would be fitted to
  inspected days. Policy validation should be pre-registered and run on future
  dates (§38 principle).
- **Tick resolution:** the path is the tick-by-tick effective tape. The
  findings in §4 (2) and (3) are properties of that resolution, not errors.
- **Holiday calendar:** none is modelled. 09-07 (Labor Day, early close) is
  correctly a trading date and its truncated profile surfaced as
  PRIOR_PROFILE_INCOMPLETE for 09-08.
