# Drysdale prospective validation plan (0AB-D) — pre-registered, frozen before the cohort is opened

Plan id `DRYSDALE_PROSPECTIVE_VALIDATION_PLAN_V1`; machinery `DRYSDALE_PROSPECTIVE_VALIDATION_V1`
(`apps/dicks_laboratory/src/dicks_laboratory/drysdale_validation.py`, CLI
`scripts/dicks_lab_drysdale_validation.py`).

Written 2026-10-12, before any analytical inspection of a campaign date. No campaign date was opened,
analyzed, summarized or previewed to write it. The freeze record is
[evidence/0AB-D/FREEZE.md](evidence/0AB-D/FREEZE.md).

## 1. What is being validated, and what is not

The question is no longer "can the code produce Drysdale candidates?" (0AB-B answered that). It is:

```text
Does frozen DRYSDALE_V1 behave coherently on unseen market dates?
```

Three questions are kept apart:

| | Question | In 0AB-D |
|---|---|---|
| A. IMPLEMENTATION VALIDITY | Does frozen V1 behave exactly and deterministically as specified? | yes |
| B. STRUCTURAL VALIDITY | Do the candidates look like coherent manifestations of the source-inspired setup structure? | yes |
| C. TRADING EDGE | Would acting on these candidates produce useful trades? | **no** |

**Boundary.** This is a prospective *structural* validation of a mechanical educational representation. It
does not prove, test or estimate profitability, predictive power or trade expectancy. No PnL, win rate,
expectancy, profit factor, entry price, stop, target or position size is defined, computed or reported.

**Source vs proxy.** Drysdale source concepts are not the Laboratory V1 operational proxies. V1 is the
Laboratory's mechanical training representation of the source concepts
([DRYSDALE_VWAP_TRAINING_CANDIDATES.md](DRYSDALE_VWAP_TRAINING_CANDIDATES.md)). A validation result is a
statement about the proxies, not about the source.

What is tested: stability, frequency, selectivity, sequence coherence, context coherence, quality behavior,
time-of-day behavior, setup overlap, and candidate persistence / maturity.

## 2. Frozen inputs (nothing here changes during the first readout)

| Item | Status |
|---|---|
| `DRYSDALE_V1` (`drysdale.py`, `price_action.py`, the policy doc, `test_drysdale.py`) | frozen in 0AB-B (`553ac27`); unchanged |
| `DRYSDALE_QUALITY_SCOPE_V1`, `DRYSDALE_VALIDATION_ELIGIBILITY_V1` (`drysdale_quality.py`, [DRYSDALE_QUALITY_SCOPE.md](DRYSDALE_QUALITY_SCOPE.md)) | accepted in 0AB-C; **frozen for the first prospective readout** |
| Quality reporting pre-registration ([DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md](DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md)) | accepted; used unchanged |
| This plan and the validation machinery | frozen by 0AB-D |

## 3. Validation cohort

The bounded campaign, trading dates **2026-10-12 through 2026-11-06**: 20 ordinary trading dates
(campaign record §2; no exchange exception). Every one stays UNSEEN until this plan is frozen.

**Date eligibility** (pre-existing rules only; evaluated by the harness, recorded per date):

| Date status | Rule |
|---|---|
| `NOT_CAPTURED` | no dataset for the date |
| `CONTRACT_MISMATCH` | the dataset is not `/ESZ6` (ES, 2026-12), the campaign pin |
| `NOT_FINALIZED` | the dataset lifecycle at final knowledge is not FINALIZED |
| `ANALYSIS_NOT_AVAILABLE` | frozen V1 returns NOT_AVAILABLE (no Globex VWAP) |
| `ELIGIBLE` | otherwise |

Known gaps never exclude a date; they act per candidate through `DRYSDALE_VALIDATION_ELIGIBILITY_V1`. Every
excluded date is listed with its reason. **No outcome cherry-picking:** the first readout includes every
captured cohort date that meets these rules. No date is dropped for being interesting, boring, volatile,
quiet, or a holiday after the fact.

**Prior-day input.** The prior trading date's dataset is used when it was captured. Otherwise the date is run
without it: prior-day context facts are then `NOT_AVAILABLE`, which never changes date eligibility or any
candidate (V1 uses the prior day only as breakout context).

## 4. Evaluation point and the unit of analysis

Each date is evaluated once at **final knowledge**: market cutoff 16:00 CT, knowledge cutoff the later of
16:30 CT and 1 µs after the latest recorded receipt or quality observation in the dataset. The unit is the
**candidate**: a V1 instance in state CANDIDATE or QUALITY_QUALIFIED at final knowledge (DEVELOPING instances
are `NOT_A_CANDIDATE` and are used only by the funnel, §8).

**Eligible candidates** are `ELIGIBLE_UNQUALIFIED` plus `ELIGIBLE_QUALITY_QUALIFIED`. All primary outcomes,
flags, overlap and samples use eligible candidates. Total and NOT_ELIGIBLE are always reported beside them.

## 5. Quality reporting (fixed by the accepted pre-registration; unchanged)

```text
total candidates
ELIGIBLE_UNQUALIFIED
ELIGIBLE_QUALITY_QUALIFIED:
- boundary PROVENANCE
- boundary LOCAL_EVIDENCE
- UPSTREAM_REFERENCE
NOT_ELIGIBLE
```

The sub-counts may overlap; the exact reason combinations (code/materiality, `NOT_A_DEPENDENCY` excluded) are
reported so that every `ELIGIBLE_QUALITY_QUALIFIED` candidate is counted exactly once. The four top-level
counts must sum to the total. Expected baseline (PO, 0AB-C): `ELIGIBLE_QUALITY_QUALIFIED`, with
`ELIGIBLE_UNQUALIFIED` expected 0 for Globex-anchored candidates.

**Strata** (registered; the only partitions allowed in the first readout):

| Stratum | Candidate reference time = end of the completing 5-minute bar |
|---|---|
| `FIRST_GLOBEX_HOUR` | ≤ 18:00 CT (anchor + 1 h) |
| `LATER_OVERNIGHT` | 18:00 < reference ≤ 08:30 CT |
| `US_CASH_SESSION` | completing bar inside [08:30, 15:00) CT (`US_CASH_SESSION_V1` study window) |
| `POST_CASH` | completing bar inside [15:00, 16:00) CT; never merged into another stratum |
| overnight | `FIRST_GLOBEX_HOUR` + `LATER_OVERNIGHT` = completing bar inside [17:00, 08:30) CT |
| time since anchor | continuous, minutes (integer: bar ends are on the 5-minute grid from 17:00) |

No new bin is registered by 0AB-D.

## 6. Setup families (each reported separately; never collapsed into one "Drysdale signal")

`PRICE_DISCOVERY_CONTINUATION_CANDIDATE_V1` (PDC), `FADE_VALUE_AREA_EXTREME_CANDIDATE_V1` (FADE),
`RETURN_TO_VALUE_CANDIDATE_V1` (RTV), `VWAP_BOUNCE_CANDIDATE_V1` (BOUNCE). For each: count, direction, time,
quality, overlap, state sequence and supporting context.

## 7. Primary descriptive outcomes (per family, and for all families together)

- candidate count per date, and per eligible date (mean, median, min, max)
- UP count, DOWN count (descriptive only; no balance threshold — a four-week sample may be directional)
- count and rate per eligible date by stratum: first Globex hour, later overnight, cash session, POST_CASH
- time from the Globex anchor to completion (all values; min, median, max)
- quality eligibility distribution (§5)
- overlap frequency (candidates in a sequence overlap, §12)
- distinct families represented per date
- dates with zero, one, and multiple eligible candidates

Success is never decided from one count alone.

## 8. Condition funnel (where structures fail to mature)

For each family, over every V1 instance at final knowledge (any state): the number reaching at least
condition 1..n in order (leading SATISFIED conditions), the number satisfying each condition, and the
distribution of the **first unsatisfied condition** (order, policy, NOT_SATISFIED or still PENDING at 16:00).

| Family | Conditions in order (V1) | An instance exists from |
|---|---|---|
| PDC | breakout trigger · acceptance outside · retest · directional confirmation | the trigger |
| FADE | inside acceptance · boundary test · rejection · confirmation toward the interior | the boundary test |
| RTV | outside acceptance · return close inside · inside acceptance | the return |
| BOUNCE | prior outside close · return inside · trend context · VWAP test · confirmation away from VWAP | the VWAP test |

Structures that never become instances (for example inside acceptance never followed by a boundary test) are
not counted; V1 does not create them.

## 9. Implementation validity checks (any failure is a defect, not a market finding)

**Sequence coherence.** For every completed candidate: every condition SATISFIED with its timestamp equal to
its bar's end, completion = the last condition, first event ≤ completion, and the family's required order:

| Family | Required order of condition bars b1..bn |
|---|---|
| PDC | b2 = b1+1; b3 ≥ b1+2; b4 = b3+1 |
| FADE | b2 ≥ b1+1; b3 = b2; b4 = b3+1 |
| RTV | b2 > b1; b3 = b2+1 |
| BOUNCE | b2 > b1; b2 ≤ b4; b3 = b4−1; b4 > b1; b5 = b4+1 |

Expected **0** sequence violations.

**Typed semantics, re-checked independently on the bars** (implementation-level hypotheses):

- PDC: the trigger starts the outside episode; every close from trigger to retest is outside; the retest bar
  trades at or through the broken boundary; the confirmation bar closes in the direction past the retest bar.
- **H-FADE-1:** prior inside-value acceptance under the frozen proxy (every close from the acceptance
  episode start to the bar before the test is inside).
- **H-FADE-2:** the tested ±1σ boundary shows the frozen rejection close before directional confirmation
  toward the interior.
- **H-RTV-1:** a demonstrable prior accepted-outside state up to the return; **H-RTV-2:** no retest condition.
- **H-BOUNCE-1:** a real VWAP test under `LAB_VWAP_TEST_V1`; **H-BOUNCE-2:** confirmation away from VWAP.
- Trend context (BOUNCE) re-checked as frozen: Globex VWAP RISING / FALLING and the close on the trend side.

Expected **0** semantic violations. Any sequence or semantic violation: **STOP**, investigate before interpreting
that candidate, record the attribution (`FROZEN_RULE`, `HARNESS` or `DATA`).

**Determinism.** For every date: the frozen analysis is run twice on identical inputs and cutoffs — once
through the replay session (cached snapshot, resumable pass), once cold (snapshot and as-of tape rebuilt, no
checkpoint) — and `drysdale_sha256` and the quality audit sha256 must be identical. In addition the `date`
command is re-run in a separate process for the **first and the last eligible date** (calendar order), and the
`record_sha256` must be identical. Any unexplained nondeterminism is a **VALIDATION BLOCKER**.

**Knowledge-time integrity** (market cutoff ≠ knowledge cutoff; no future evidence leaks backward). For
**every** candidate (not a sample, so no selection is involved):

- the candidate's **first-known time** is the earliest ordinary replay instant (market = knowledge cutoff)
  at which frozen V1, given only what was received by then, shows it with its final structure (same id, a
  completed state, the same condition bars);
- the search runs over the only instants at which that can change: the completion instant, then 1 µs after
  each later receipt of a record with an earlier market time (scanned forward, then bisected);
- proof: **absent** at the preceding probe (1 µs before completion when the first-known time is the
  completion itself), **present** at the first-known probe;
- a lookahead defect is: present before its completing bar ended, an evidence window ending after the
  first-known time, or present at the preceding probe.

Also reported: candidates known at an hourly replay cutoff (18:00 … 16:00 CT) that are absent from, or
structurally different at, final knowledge (`withdrawn_or_revised`). This is persistence / maturity, not a
defect: late prints legitimately revise.

## 10. Candidate first-known time

For every candidate: completion time, first-known time, and the receipt delay between them (seconds, exact to
1 µs), with its eligibility both at first-known time and at final knowledge. The tutor needs this distinction:
*the market event occurred* vs *the system could know it*. A receipt delay is never turned into a market-quality
judgment.

## 11. Context facts (CONTEXT FACTS, never candidate requirements; no new threshold)

Per candidate, over its own bars (first condition bar … completing bar), at final knowledge:

- Globex VWAP slope at the first condition bar and at the completing bar (exact `LAB_VWAP_SLOPE_V1`)
- completing close distance beyond ±1σ (points) and position in sigma units
- whether ±2σ was traded at or through on the candidate's bars
- maximum excursion (PDC: beyond the broken boundary; RTV: of the outside episode; FADE / BOUNCE: through
  the tested level)
- time outside value and completed closes outside value (PDC, RTV; BOUNCE: the prior outside run)
- breakout-bar volume (PDC) and the completing bar's volume with its ratio to the 12-bar baseline mean and
  median (`LAB_VOLUME_CONTEXT_V1`)
- IB, prior-day and overnight high / low interaction: `TRADED_THROUGH`, `NOT_TRADED`, `NOT_YET_AVAILABLE` or
  `NOT_AVAILABLE` (a reference counts only from when it was known)
- time of day (CT) and stratum
- return into value by the session end (PDC; labelled post-completion)

## 12. Setup overlap (descriptive; overlap is not declared bad)

Among one date's eligible candidates, per pair:

| Kind | Definition |
|---|---|
| same-time overlap | the same completion time |
| sequence overlap | the evidence windows (`DRYSDALE_QUALITY_SCOPE_V1`) intersect |
| family overlap | a sequence overlap between different families |
| directional conflict | a sequence overlap with opposite directions |

Exact family-pair combinations are reported (for example `PDC+RTV`, `FADE+BOUNCE`, `PDC+PDC`). Primary
question: does overlap reveal coherent transitions, or does V1 produce excessive redundant labeling? The source
defines no setup exclusivity. No tuning on overlap frequency.

## 13. Pre-registered structural hypotheses (descriptive; no pass / fail unless stated)

**Price Discovery Continuation**

- **H-PDC-1:** PDC candidates usually complete after sustained movement beyond ±1σ, not a single transient
  touch. Reported: outside closes from trigger to completion, seconds beyond the boundary, trigger distance in
  sigma.
- **H-PDC-2:** a meaningful fraction shows supporting context. Reported per candidate and as a 0–4 count:
  VWAP slope aligned at the trigger; ±2σ reached by completion; breakout volume above the 12-bar baseline
  median; a reference break at the trigger (an available static reference traded through with the close beyond
  it, or a new Globex-session extreme).
- **H-PDC-3:** PDC may occur overnight or in cash hours; V1 assumes neither. Reported by stratum.

**±2σ context question.** How often do PDC candidates reach or approach ±2σ? One mutually exclusive category per
candidate, by the first bar of its outside episode (trigger … episode end at final knowledge) that trades at or
through ±2σ on the breakout side:

| Category | First reach |
|---|---|
| `REACHED_AT_BREAKOUT_BAR` | the trigger bar itself (before completion) |
| `REACHED_AFTER_BREAKOUT_BEFORE_COMPLETION` | after the trigger bar, up to and including the completing bar |
| `REACHED_AFTER_COMPLETION` | after the completing bar, within the same outside episode |
| `NEVER_DURING_SEQUENCE` | not within the episode |

"Approach" is the continuous maximum distance beyond ±2σ up to completion (negative: how far short), in points
and in sigma. ±2σ is not required for V1 validity. No tuning on the first result.

**Volume context question.** Do PDC candidates tend to occur with higher relative volume than their immediately
preceding context? "Higher" is literal: the breakout bar's volume ratio to the 12-bar baseline median (and,
separately, mean) is > 1 (`HIGHER`), = 1 (`EQUAL`), < 1 (`LOWER`), or `NOT_AVAILABLE`. Candidate-bar volume is
reported too. No `STRONG_VOLUME` is defined, now or after seeing the campaign.

**VWAP slope context question.** For PDC: is the Globex VWAP slope aligned with the direction? `ALIGNED` /
`FLAT` (exactly unchanged) / `OPPOSED` / `NOT_AVAILABLE`, at the trigger bar (primary) and at the completing bar,
with the exact slope semantics. No slope tolerance; alignment is never made mandatory.

**Fade Value Area Extreme.** H-FADE-1 and H-FADE-2 are implementation-level (§9; a failure is a defect).
**H-FADE-3** (structural observation): fade candidates are distinguishable from continuation candidates by
their condition sequence even on the same date. Reported: same-date FADE/PDC pairs and how many share an
identical condition-bar sequence (expected 0).

**Return to Value.** H-RTV-1 and H-RTV-2 are implementation-level (§9). **H-RTV-3:** a later retest, when
present, is context only. Reported: RTV with a later retest and without one (by the session end). A later
retest is never made mandatory after seeing results.

**VWAP Bounce.** H-BOUNCE-1 and H-BOUNCE-2 are implementation-level (§9). **H-BOUNCE-3:** trend-context evidence
may vary (V1 has no sophisticated trend classifier). Reported separately: slope at the trend bar, at the test bar
and at the confirmation bar, and bars from the outside close to the test. V1 is not strengthened retroactively
because some bounces look weak.

## 14. Challenge conditions (Laboratory validation thresholds, not Drysdale concepts; flag ≠ fail)

| Flag | Fires when | Meaning |
|---|---|---|
| `CANDIDATE_DENSITY_CHALLENGED` | median eligible candidates per eligible date > 20 | the proxies may be too permissive for useful educational discrimination |
| `CANDIDATE_SCARCITY_CHALLENGED` | more than 50% of eligible dates have zero eligible candidates (any family) | the system may be over-restrictive |
| `FAMILY_DOMINANCE_FOR_REVIEW` | one family > 80% of all eligible candidates | inspect whether one proxy mechanically subsumes the taxonomy; not evaluated (shown as `null`) below 20 eligible candidates |

20 is intentionally generous: it catches obvious setup proliferation; it does not optimize frequency. A flag
requires PO review. **No threshold is ever changed automatically.**

## 15. Dedicated subsets

- **First Globex hour** (0AB-C showed it is the most boundary-sensitive): candidate count; eligible-qualified
  boundary PROVENANCE and boundary LOCAL_EVIDENCE; candidates whose eligibility at first-known time differs from
  final knowledge; first-hour candidates withdrawn or revised. Always displayed separately; never excluded
  automatically.
- **`US_CASH_SESSION_V1` subset** (completing 08:30–15:00 CT): all primary outcomes reported separately. The
  Drysdale setup is not redefined as cash-only.
- **POST_CASH** (15:00–16:00 CT): reported as POST_CASH, never merged later because counts are small.

## 16. Date-level and cohort-level summaries

**Per eligible date** (deterministic; notes factual only, no narrative): trading date, dataset id, contract,
quality status and reason codes, total candidates, counts by family, UP / DOWN, first-hour / overnight / cash /
POST_CASH candidates, overlaps, not-eligible candidates, known gaps / interruption, notes.

**Cohort:** dates captured, finalized cleanly, eligible, with quality qualifications; candidate totals;
median, mean and range per date; zero-candidate dates; family, direction, time-of-day, quality and overlap
distributions. Descriptive statistics only: **no inferential hypothesis testing** in V1.

## 17. Minimum samples

- **10 eligible dates** for cohort-level structural interpretation; fewer: `INCONCLUSIVE` (unless BLOCKED / FAIL
  applies). Descriptive results are still reported.
- **20 eligible candidates** for setup-family distribution interpretation; fewer: distribution conclusions
  `INCONCLUSIVE` and the dominance flag is not evaluated. The campaign is never enlarged post hoc to reach a
  count; a later cohort is planned separately.
- **5 eligible candidates per family**; fewer: `FAMILY SAMPLE TOO SMALL FOR STRUCTURAL CONCLUSION`. The family
  is not called invalid; no family is required to produce candidates.

## 18. Cohort classification (precedence top to bottom)

| Outcome | When |
|---|---|
| `BLOCKED — IMPLEMENTATION / DATA QUALITY` | nondeterminism; a lookahead defect; an unresolved first-known time; a date that cannot be evaluated; incoherent quality accounting (counts that do not sum, or an `UNEXPLAINED_UPSTREAM_REASON`); or any sequence / semantic violation that is pending investigation, attributed to the harness or the data, or a single frozen-rule occurrence |
| `FAIL — STRUCTURAL BREAKDOWN` | the Human investigation attributes the violations to the frozen rules and they occur in **two or more** candidates (repeatedly), with no other blocker |
| `INCONCLUSIVE` | fewer than 10 eligible dates |
| `PASS WITH CHALLENGES` | implementation sound, but one or more challenge flags fire |
| `PASS — STRUCTURALLY COHERENT` | deterministic; no sequence, semantic or lookahead defect; density and scarcity not challenged; no family dominance (no obvious proxy collapse); quality accounting coherent |

FAIL is never defined by profitability.

## 19. Discipline during the first readout

- **DRYSDALE_V1 stays frozen** for the whole first readout. No change to the breakout trigger, acceptance
  bars, retest, rejection, directional confirmation, value area, VWAP anchor, VWAP bands, VWAP test, trend proxy
  or candidate composition, even if results look poor. Findings are recorded first; any change is `DRYSDALE_V2`
  with a fresh prospective cohort.
- **Quality policies stay frozen** (`DRYSDALE_QUALITY_SCOPE_V1`, `DRYSDALE_VALIDATION_ELIGIBILITY_V1`). No date
  or candidate is reclassified after seeing results. A change is V2 and never rewrites the first cohort.
- **No new stratification after opening.** Allowed: the registered strata and continuous measurements. New time,
  volatility, volume or session buckets are `POST-HOC / EXPLORATORY`, labelled as such and kept apart from the
  pre-registered results.
- **Harness.** The validation machinery is frozen with this plan. A defect found in it may be fixed only under a
  recorded addendum that lists old and new sha256s, changes no V1 or quality code and no registered outcome
  definition, and re-runs every date.

## 20. Human review layer

The first report reserves a section for Human review that is **not** filled automatically. A deterministic sample
is listed for later Human inspection, per family: the **earliest** eligible candidate (by trading date,
completion time, id) and the **lower-median** eligible candidate by minutes since the anchor among the rest (ties:
trading date, id). Fewer than two in a family: all of them. Never chosen by chart appearance. 0AB-D inspects no
chart.

## 21. Tutor-relevance (curriculum) questions

The report answers, with tables: which setup states occur often enough to teach; which intermediate condition
failures are common (funnel); which overlaps are common; which quality warnings need tutor explanation (the reason
combinations); which families are too sparse for useful lessons; which family × stratum cells produce enough
examples. "Enough" reuses the registered 5 eligible candidates as a Laboratory curriculum convenience. These are
curriculum questions, never trading recommendations.

## 22. Readout procedure (after the campaign has ended)

1. `scripts/dicks_lab_drysdale_validation.py guard <dataset> --frozen-plan <plan sha256>` on each dataset
   (metadata only) — the freeze must verify.
2. For each cohort date in calendar order: `... date <dataset> --prior-db <prior dataset, if captured>
   --frozen-plan <plan sha256> --out <date>_record.json`. Re-run the first and the last eligible date in a new
   process; the `record_sha256` must match.
3. `... cohort <records> --frozen-plan <plan sha256> --json-out ... --md-out ...` (default expected dates: the 20
   cohort dates). If BLOCKED: stop, investigate, record the attribution (`--attribution`), never tune.
4. Publish the machine readout with the empty Human review section, plus the dataset sha256s before and after
   (unchanged).

## 23. Campaign data access guard

The harness refuses a dataset whose recorded trading date is on or after 2026-10-12, or unknown, or whose capture
began at or after the first cohort session's Globex anchor — unless `evidence/0AB-D/FREEZE.md` exists, every file
it lists verifies by sha256, and `--frozen-plan` equals the plan sha256 it lists. The check reads dataset metadata
only, before any trade is loaded. The `cohort` command applies the same rule to records of campaign dates.

## 24. Development shakedown (not validation)

The harness was exercised on synthetic fixtures (tests) and on the already-inspected development corpus
(2026-09-29 … 2026-10-02). Those dates are DEVELOPMENT / DESCRIPTIVE, never validation, and no threshold above
was set or adjusted from them (every threshold was given by the PO in the 0AB-D brief). See
[evidence/0AB-D/dev_shakedown/README.md](evidence/0AB-D/dev_shakedown/README.md).

## 25. Interpretations registered here (where the brief left a choice)

1. ±2σ: the four categories in §13 are made mutually exclusive by the first reach within the candidate's outside
   episode ("before completion" = at the breakout bar; "after breakout but before completion"; "after
   completion"; "never").
2. Density, scarcity and dominance use eligible candidates; dominance is not evaluated below 20.
3. FAIL needs a recorded Human attribution to the frozen rules in two or more candidates; otherwise a violation
   is BLOCKED.
4. An `UNEXPLAINED_UPSTREAM_REASON` makes the quality accounting incoherent (BLOCKED).
5. Overlap is measured on eligible candidates' evidence windows.
6. "Higher relative volume" is the literal ratio to the 12-bar baseline median > 1 (mean reported too).
7. Slope alignment is primary at the trigger bar.
8. Post-completion facts (RTV later retest, PDC return into value, ±2σ after completion) are labelled as such.
