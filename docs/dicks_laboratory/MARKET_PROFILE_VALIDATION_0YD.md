# Market Profile Day-Type Blind Validation (0Y-D)

Status: validation only. The 0Y-C V1 policy (`DICKS_LAB_DAY_TYPE_POLICY` /
`V1_DIRECTIONAL_STATE_X_IB_SHARE`) was frozen throughout. No threshold, rule or
quality gate changed. Nothing here is a trading claim.

- Corpus: `MARKET_PROFILE_CORPUS_0YD.md`
- Raw evidence: `evidence/0Y-D/`
- Code: `tpo_validation.py` (records and diagnostics),
  `scripts/dicks_lab_mp_validation.py` (`run`, then `analyze`)

## 1. Method (blind, two-stage)

1. **Frozen policy.** `tpo_day_structure.py`, `tpo_structure.py`,
   `tpo_profile.py` and `tpo_analysis.py` are unchanged since `fbbb095`
   (`git diff fbbb095` is empty). The `tpo_day_structure.py` sha256 is
   `8d745aab0e6b6bba3f6a2092e4e679e89a97a0629509d715522d5600e4cfef88`.
2. **`run`.** Classified all 22 authentic local ES datasets in one pass. For
   each it wrote:
   - a raw report: TPO matrix, 0Y-B structure and 0Y-C day structure
   - a `DayRecord`

   `records.jsonl` was then frozen with sha256
   `b15fef0c059b0c2cf4f4368579aa4c3c8d881ceec177ccbc0fe3baa38ce5ae4e`.
   No profile was inspected before this point.
3. **`analyze`.** Refuses to run if the records' sha256 has changed. It
   computes every table in `evidence/0Y-D/blind_run/validation_report.md`
   mechanically.
4. **Shortlist.** The selection rules (`SHORTLIST_RULES`) were written into
   code before `analyze` first ran. Ties go to the earlier date.
5. **Afterwards.** The assessment (§9) and hypotheses (§10) were written.

The database sha256 values were identical before and after the run.

## 2. Corpus outcome (quality rules unchanged)

| Eligibility | Days | Dates |
|---|---|---|
| **ELIGIBLE** (blind classification) | **12** | 09-02, 09-15, 09-21, 09-23, 09-24, 09-25, 09-28, 09-29, 09-30, 10-01, 10-02, 10-06 |
| QUALITY_QUALIFIED | 0 | — (no gap evidence inside any full window) |
| NOT_CLASSIFIED | 5 | 08-31 ×2, 09-11 (window not captured); 09-08 (coverage unknown, lifecycle OPEN); 09-07 (Labor Day, H–M empty) |
| NO_PROFILE | 5 | 08-26, 08-27, 08-28, 09-01, 09-10 (overnight or short verification captures) |

Quality-rule counts:
- window not fully captured → NOT_CLASSIFIED: **3**
- coverage unknown → NOT_CLASSIFIED: **1**
- gap inside window → QUALITY_QUALIFIED: **0**
- gap only outside window, still ELIGIBLE: **3** (09-02, 09-21, 09-29)

## 3. Classification distribution (ELIGIBLE, n = 12)

| Outcome | Count | % |
|---|---|---|
| NORMAL_DAY | 0 | 0.0 |
| NORMAL_VARIATION_DAY | 6 (UP 3, DOWN 3) | 50.0 |
| TREND_DAY | 1 (UP) | 8.3 |
| NEUTRAL_DAY | 5 | 41.7 |
| UNCLASSIFIED | 0 | 0.0 |
| AMBIGUOUS | 0 | 0.0 |

IB share over the eligible days: min 0.2739, q25 0.4330, median 0.6440, q75
0.7450, max 0.8431.

Pathology screen, facts first:
- 11 of 12 days (92 %) fall into two types.
- **No day reached IB share ≥ 0.85.** Every eligible day extended the IB by at
  least one tick, so `NORMAL_DAY` cannot occur in this sample.
- `NEUTRAL_DAY` is 42 % of days, and most of those Neutrals are very
  asymmetric (§5).
- Trend candidates are rare (1).
- UNCLASSIFIED is 0, so the partition never declined to name an eligible day.

No distribution is assumed correct. Some descriptive references claim Normal
days are "the most common" (50–60 %). That is an unverified secondary claim and
was not used as ground truth. It is recorded only because the observed 0 / 12
contrasts with it.

## 4. Boundary proximity (|IB share − boundary| ≤ 0.05)

| TD | Boundary | IB share | Side | State | V1 result |
|---|---|---|---|---|---|
| 09-29 | 0.50 | 0.5135 | at/above | DOWN_ONLY | NORMAL_VARIATION DOWN |
| 09-24 | 0.50 | 0.4807 | below | BOTH_SIDES | NEUTRAL |
| 10-01 | 0.85 | 0.8431 | below | BOTH_SIDES | NEUTRAL |
| 09-02 | 0.85 | 0.8187 | below | UP_ONLY | NORMAL_VARIATION UP |

Only 09-29 and 09-02 were *decided* by an IB-share boundary.
- **09-29:** 0.0135 above 0.50. At ≤ 0.4999 it would have been tested against
  TREND, and it would pass: 4 new-low periods and terminal at 0.44 (below the
  midpoint).
- **09-02:** 0.0313 below 0.85.

09-24 and 10-01 are near a boundary, but `BOTH_SIDES` makes them NEUTRAL
whatever their share.

## 5. NEUTRAL_DAY sensitivity (5 candidates)

| TD | Ext ↑ ticks | Ext ↓ ticks | Smaller/IB | Larger/IB | Smaller/larger | Terminal pct |
|---|---|---|---|---|---|---|
| 09-30 | 10 | 155 | 0.0794 | 1.2302 | 0.0645 | 0.0515 |
| 10-02 | 6 | 78 | 0.0426 | 0.5532 | 0.0769 | 0.4444 |
| 10-01 | 5 | 38 | 0.0216 | 0.1645 | 0.1316 | 0.7774 |
| 09-24 | 102 | 19 | 0.1696 | 0.9107 | 0.1863 | 0.6910 |
| 09-28 | 44 | 131 | 0.6667 | 1.9848 | 0.3359 | 0.3402 |

Distributions:
- smaller/larger: min 0.0645, median 0.1316, max 0.3359
- smaller/IB: min 0.0216, median 0.0794, max 0.6667

Observations:
- 3 of 5 Neutrals have a counter-extension of at most 10 ticks (≤ 0.08 × IB).
- 4 of 5 have a smaller extension below 0.17 × IB.
- Only 09-28 has a smaller extension of the same order as the IB (0.67 × IB).
- No cutoff for "roughly two-sided" is chosen. The continuous values are
  above.

## 6. NORMAL_VARIATION_DAY sensitivity (6 candidates)

| TD | Dir | IB share | Ext/IB | Ext/range | Extending periods | New-extreme periods | Terminal pct |
|---|---|---|---|---|---|---|---|
| 09-02 | UP | 0.8187 | 0.2215 | 0.1813 | 5 | 3 | 0.7306 |
| 09-15 | DOWN | 0.7633 | 0.3101 | 0.2367 | 9 | 1 | 0.3136 |
| 10-06 | UP | 0.7450 | 0.3423 | 0.2550 | 3 | 1 | 0.3423 |
| 09-23 | DOWN | 0.7201 | 0.3886 | 0.2799 | 9 | 4 | 0.2164 |
| 09-25 | UP | 0.6613 | 0.5122 | 0.3387 | 8 | 2 | 0.8387 |
| 09-29 | DOWN | 0.5135 | 0.9474 | 0.4865 | 11 | 4 | 0.4378 |

Extension/IB: min 0.2215, q25 0.3101, median 0.3655, q75 0.5122, max 0.9474.

Observations:
- Half the candidates (3 of 6) extend less than 0.35 × IB.
- Two candidates set a new extreme in only one post-IB period.
- Only 09-29 approaches the "range roughly double the IB" description
  (extension ≈ 1 × IB).
- Small extensions do receive the label regularly.

## 7. TREND_DAY sensitivity (1 candidate)

**09-21 UP** (`64d684c9`):
- IB share 0.3680; extension 56.25 points (225 ticks) = 1.7176 × IB.
- **10** post-IB periods set new highs (CDEFGHIJKM), and all 11 post-IB
  periods traded above the IB.
- Terminal at 0.8427; counter-extension 0 (by construction).
- Tails 10 / 38 rows; 6 interior one-TPO zones.

It satisfies every condition by a wide margin. It is persistent, not a
marginal one-sided pass. With n = 1, though, the rule's *rate* can't be
judged.

Counterfactual, a diagnostic that changes no rule: **09-30** satisfies three
of TREND's four conditions in the DOWN direction:
- IB share 0.4330 < 0.50
- 2 new-low periods (KM)
- terminal at the 0.05 percentile, below the midpoint

It fails only `directional_state`, because of a 10-tick upside
counter-extension. That same 10 ticks makes it NEUTRAL.

## 8. NORMAL_DAY sensitivity

No candidates. Historical "wide IB" context: **NOT EVALUATED** (V1 condition
`ib_wide_vs_history`). Recent-day percentile logic was not retrofitted.

The closest day is 10-01: IB share 0.8431, extensions of 5 ticks up and 38
ticks down, so `BOTH_SIDES` and therefore NEUTRAL.

## 9. Policy robustness assessment (engineering, not trading)

| Policy | Assessment | Evidence |
|---|---|---|
| `NEUTRAL_DAY` | **STRUCTURALLY OVER-PERMISSIVE** | The 1-tick-per-side rule admits token counter-extensions. 3 / 5 candidates have a smaller side of at most 10 ticks (≤ 0.08 × IB). It also captures days the other rules would otherwise evaluate: 09-30 meets every other TREND condition, and 10-01 / 10-02 sit in the NORMAL_VARIATION share band. |
| `NORMAL_VARIATION_DAY` | **PLAUSIBLE BUT NEEDS MORE EVIDENCE** | All 6 are genuinely one-sided and lie within the band. Half extend less than 0.35 × IB and two have only one new-extreme period, so the low end is permissive relative to "meaningful". It is not pathological at n = 6. |
| `TREND_DAY` | **PLAUSIBLE BUT NEEDS MORE EVIDENCE** | Its one candidate is unambiguous: 10 new-high periods, 1.72 × IB, terminal at 0.84. n = 1. The strict no-counter-extension condition, combined with NEUTRAL's 1-tick rule, may make it **under-permissive** (09-30). |
| `NORMAL_DAY` | **INSUFFICIENT EVIDENCE** | 0 / 12. No eligible day reached IB share 0.85, and every day extended at least 1 tick. Rule behaviour can't be assessed from zero hits. Its reachability is also reduced by NEUTRAL's 1-tick rule (10-01). |
| Quality gates | **ROBUST ENOUGH FOR NEXT PHASE** | Every truncated, holiday, unknown-coverage and overnight-only capture was refused with a correct, specific reason. Outside-window gaps (3 days) did not block. |
| Directional-state / fact layer | **ROBUST ENOUGH FOR NEXT PHASE** | Deterministic on 22 datasets; database hashes unchanged; the facts carry the full sensitivity analysis above. |

## 10. Follow-up hypotheses (for a future policy experiment; NOT accepted values)

These are what-if counts over the frozen records, from
`evidence/0Y-D/hypothesis_whatif.py`. The grid points are illustrative, not
proposals.

- **H1.** NEUTRAL should require both extensions ≥ X × IB.
  - X = 0.10 keeps 2 of 5 (09-24, 09-28).
  - X = 0.25 or 0.50 keeps 1 (09-28).
  - Observed smaller/IB values: 0.0216, 0.0426, 0.0794, 0.1696, 0.6667.
    There is a wide empty interval between 0.17 and 0.67.
- **H2.** NORMAL_VARIATION should require extension ≥ Y × IB.
  - Y = 0.25 drops 09-02.
  - Y = 0.50 keeps 2 of 6.
  - Observed: 0.2215, 0.3101, 0.3423, 0.3886, 0.5122, 0.9474.
- **H3.** A "token counter-extension" (smaller side < X × IB) should not stop
  the directional rules from evaluating the dominant side. At X = 0.10 that
  affects 09-30, 10-01 and 10-02, all dominant DOWN. Days released from
  NEUTRAL would then need TREND / NORMAL_VARIATION to accept a dominant side.
  H1 and H3 must be designed together, or released days fall into
  UNCLASSIFIED.
- **H4.** NORMAL_DAY can't be tested on this sample. A meaningful test needs
  either historical IB context or the H3 change (10-01 would then be one-sided
  with share 0.8431, still just below 0.85).

Any experiment should be pre-registered and re-run blind. This corpus has now
been inspected, so a held-out set of future days is preferable.

## 11. Mechanical inspection shortlist

Rendered profiles: `evidence/0Y-D/blind_run/reports/` (matrix, 0Y-B
structure, 0Y-C explanation).

| Slot (rule) | TD | V1 result |
|---|---|---|
| representative NORMAL_DAY (nearest the type's median IB share) | — | none in sample |
| representative NORMAL_VARIATION_DAY | 10-06 | NV UP (0.7450) |
| representative TREND_DAY | 09-21 | TREND UP |
| representative NEUTRAL_DAY | 09-24 | NEUTRAL (0.4807) |
| nearest 0.50 boundary | 09-29 | NV DOWN (0.5135) |
| nearest 0.85 boundary | 10-01 | NEUTRAL (0.8431) |
| most asymmetric NEUTRAL_DAY (min smaller/larger) | 09-30 | NEUTRAL (0.0645) |
| smallest-extension NORMAL_VARIATION_DAY (min ext/IB) | 09-02 | NV UP (0.2215) |
| strongest TREND_DAY (most new-extreme periods, then ext/IB) | 09-21 | TREND UP |
| first UNCLASSIFIED | — | none in sample |

## 12. Raw structural outliers (type-independent)

| Measure | Day(s) |
|---|---|
| largest profile/IB | 09-28 (3.6515) |
| smallest profile/IB | 10-01 (1.1861) |
| largest one-sided extension/IB | 09-21 (1.7176) |
| most symmetric two-sided extension | 09-28 (0.3359) |
| most asymmetric two-sided extension | 09-30 (0.0645) |
| largest upper tail | 09-23 (83 rows) |
| largest lower tail | 09-30 (152 rows) |
| most new-high periods | 09-21 (10) |
| most new-low periods | 09-23, 09-29 (4) |
| terminal nearest high | 09-21 (0.8427) |
| terminal nearest low | 09-30 (0.0515) |

## 13. Data caveats

- **09-15 is ESU6 in expiry week** (`2026-09`, after the September roll): a
  100 MB file against about 440–840 MB for the Z6 days. It is authentic and
  was kept blind, but it profiles a thinning contract.
- **12 eligible days is still a small sample.** Every rate above is
  descriptive, not statistical.
- **Contracts:** U6 through 09-15, Z6 from 09-21.

## 14. Performance

The blind run took 1,385 s (23.1 min) wall time for 22 datasets, sequentially
on 4 cores / 11 GB. Full sessions took 76–142 s each, dominated by the shared
`prepare_scoped_dataset` tape load (backlog, unchanged). That did not block
this campaign, so nothing was optimised.

## 15. Flaky WAL test (not a WAL phase)

`test_checkpoint_force_bound_overrides_busy`, all runs during 0Y-D:

| Condition | Pass | Fail |
|---|---|---|
| isolated, during the 7 GB corpus copy (disk/CPU load) | 23 | 7 |
| isolated, idle | 30 | 0 |
| whole file, idle | 5 | 0 |
| Lab suite + full repository suite (final regression, idle) | 2 | 0 |

It is intermittent and load-correlated, not reliably reproducible on an idle
machine. It is flagged for separate maintenance, not fixed here.
