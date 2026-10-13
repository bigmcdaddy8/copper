# Drysdale prospective validation — first readout (DRYSDALE_PROSPECTIVE_VALIDATION_V1)

Dates 2026-09-29 .. 2026-10-02; expected 4 dates (NOT the registered validation cohort: development / descriptive only).

**Classification: INCONCLUSIVE** — 4 eligible dates < 10

## Dates

| | |
|---|---|
| captured | 4 |
| finalized_cleanly | 4 |
| eligible | 4 |
| with_quality_qualifications | 4 |
| excluded | none |

## Date-level summary

| Date | Status | Quality | Total | Eligible | PDC | FADE | RTV | BOUNCE | UP | DOWN | First hour | Overnight | Cash | POST_CASH | Overlaps | Not eligible | Gaps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-29 | ELIGIBLE | QUALITY_QUALIFIED | 15 | 14 | 3 | 2 | 8 | 1 | 6 | 8 | 1 | 13 | 1 | 0 | 6 | 1 | 1 |
| 2026-09-30 | ELIGIBLE | QUALITY_QUALIFIED | 21 | 21 | 2 | 4 | 11 | 4 | 11 | 10 | 0 | 15 | 6 | 0 | 10 | 0 | 0 |
| 2026-10-01 | ELIGIBLE | QUALITY_QUALIFIED | 15 | 15 | 3 | 2 | 8 | 2 | 8 | 7 | 0 | 10 | 5 | 0 | 8 | 0 | 0 |
| 2026-10-02 | ELIGIBLE | QUALITY_QUALIFIED | 15 | 15 | 4 | 1 | 7 | 3 | 7 | 8 | 1 | 11 | 4 | 0 | 5 | 0 | 0 |

## Quality accounting (pre-registered)

```text
total candidates             66
ELIGIBLE_UNQUALIFIED         0
ELIGIBLE_QUALITY_QUALIFIED   65
  - BOUNDARY_PROVENANCE        64
  - BOUNDARY_LOCAL_EVIDENCE    1
  - UPSTREAM_REFERENCE         3
NOT_ELIGIBLE                 1
```

Exact combinations:

- `CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/LOCAL_EVIDENCE`: 1
- `CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE`: 61
- `CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE+KNOWN_GAP/UPSTREAM_REFERENCE`: 3

## Families

### PRICE_DISCOVERY_CONTINUATION

- eligible candidates 12 (UP 6, DOWN 6); per eligible date mean 3, median 3, range 2..4
- by stratum: FIRST_GLOBEX_HOUR 0, LATER_OVERNIGHT 10, US_CASH_SESSION 2, POST_CASH 0
- minutes since anchor: min 65, median 475, max 1195
- dates zero / one / multiple: 0 / 0 / 4
- in sequence overlap: 9 of 12
- funnel (instances 88): reached at least condition 1..4: [88, 54, 26, 12]; first unsatisfied: {'2:LAB_ACCEPTANCE_TIME_V1:NOT_SATISFIED': 34, '3:LAB_RETEST_V1:NOT_SATISFIED': 27, '3:LAB_RETEST_V1:PENDING': 1, '4:LAB_DIRECTIONAL_CONFIRMATION_V1:NOT_SATISFIED': 14}

### FADE_VALUE_AREA_EXTREME

- eligible candidates 9 (UP 7, DOWN 2); per eligible date mean 2.25, median 2, range 1..4
- by stratum: FIRST_GLOBEX_HOUR 1, LATER_OVERNIGHT 6, US_CASH_SESSION 2, POST_CASH 0
- minutes since anchor: min 45, median 260, max 1320
- dates zero / one / multiple: 0 / 1 / 3
- in sequence overlap: 6 of 9
- funnel (instances 61): reached at least condition 1..4: [61, 61, 31, 9]; first unsatisfied: {'3:LAB_REJECTION_V1:NOT_SATISFIED': 30, '4:LAB_DIRECTIONAL_CONFIRMATION_V1:NOT_SATISFIED': 22}

### RETURN_TO_VALUE

- eligible candidates 34 (UP 13, DOWN 21); per eligible date mean 8.5, median 8, range 7..11
- by stratum: FIRST_GLOBEX_HOUR 1, LATER_OVERNIGHT 24, US_CASH_SESSION 9, POST_CASH 0
- minutes since anchor: min 25, median 610, max 1265
- dates zero / one / multiple: 0 / 0 / 4
- in sequence overlap: 19 of 34
- funnel (instances 53): reached at least condition 1..3: [53, 53, 34]; first unsatisfied: {'3:LAB_ACCEPTANCE_TIME_V1:NOT_SATISFIED': 19}

### VWAP_BOUNCE

- eligible candidates 10 (UP 6, DOWN 4); per eligible date mean 2.5, median 2.5, range 1..4
- by stratum: FIRST_GLOBEX_HOUR 0, LATER_OVERNIGHT 7, US_CASH_SESSION 3, POST_CASH 0
- minutes since anchor: min 100, median 525, max 1215
- dates zero / one / multiple: 0 / 1 / 3
- in sequence overlap: 8 of 10
- funnel (instances 31): reached at least condition 1..5: [31, 31, 31, 31, 11]; first unsatisfied: {'5:LAB_DIRECTIONAL_CONFIRMATION_V1:NOT_SATISFIED': 20}

## Hypotheses (descriptive)

```json
{"2SD":{"NEVER_DURING_SEQUENCE":3,"REACHED_AFTER_BREAKOUT_BEFORE_COMPLETION":7,"REACHED_AFTER_COMPLETION":1,"REACHED_AT_BREAKOUT_BAR":1},"H-BOUNCE-3":{"vwap_slope_at_confirmation_bar":{"ALIGNED":9,"OPPOSED":1},"vwap_slope_at_test_bar":{"ALIGNED":9,"OPPOSED":1}},"H-FADE-3":{"identical_condition_bar_sequences":0,"same_date_fade_pdc_pairs":24},"H-PDC-1":{"outside_closes_trigger_to_completion":{"10":1,"16":1,"25":1,"26":1,"4":4,"6":2,"7":1,"9":1},"seconds_beyond_trigger_to_completion":["813.241","850.619","952.851","1127.775","1577.18","1715.194","1721.513","2627.659","2726.869","4410.283","7346.193","7454.621"]},"H-PDC-2":{"REACHED_2SD_BY_COMPLETION":8,"REFERENCE_BREAK":3,"SLOPE_ALIGNED":12,"VOLUME_ABOVE_BASELINE_MEDIAN":5,"of":12,"supporting_facts_present":{"1":2,"2":5,"3":4,"4":1}},"H-PDC-3":{"LATER_OVERNIGHT":10,"US_CASH_SESSION":2},"H-RTV-3":{"with_later_retest":19,"without_later_retest":15},"SLOPE":{"at_completion":{"ALIGNED":12},"at_trigger":{"ALIGNED":12}},"VOLUME":{"breakout_vs_baseline_mean":{"HIGHER":4,"LOWER":8},"breakout_vs_baseline_median":{"HIGHER":5,"LOWER":7}}}
```

## Overlap

{'pair_combinations': {'FADE+BOUNCE': 3, 'FADE+RTV': 5, 'PDC+BOUNCE': 1, 'PDC+FADE': 1, 'PDC+RTV': 9, 'RTV+BOUNCE': 9, 'RTV+RTV': 1}, 'candidates_in_sequence_overlap': 42, 'of': 65}

## First Globex hour

{"candidates":2,"eligibility_changed_after_first_known":0,"quality":{"ELIGIBLE_QUALITY_QUALIFIED":2,"ELIGIBLE_UNQUALIFIED":0,"NOT_ELIGIBLE":0,"coherent":true,"eligible_quality_qualified_combinations":{"CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/LOCAL_EVIDENCE":1,"CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE":1},"eligible_quality_qualified_subcounts":{"BOUNDARY_LOCAL_EVIDENCE":1,"BOUNDARY_PROVENANCE":1,"UPSTREAM_REFERENCE":0},"not_eligible_combinations":{},"total":2},"withdrawn_or_revised":0}

## Flags

{"CANDIDATE_DENSITY_CHALLENGED":false,"CANDIDATE_SCARCITY_CHALLENGED":false,"FAMILY_DOMINANCE_FOR_REVIEW":false,"_inputs":{"eligible_dates":4,"largest_family_share":"0.5230769230769230769230769231","median_eligible_per_date":"15","zero_candidate_dates":0}}

## Sample rules

{"distribution_conclusions":"INTERPRETABLE","eligible_candidates":65,"eligible_dates":4,"family_sample_too_small":[],"min_eligible_candidates":20,"min_eligible_dates":10}

## Human-review sample (deterministic)

- PRICE_DISCOVERY_CONTINUATION: 2026-09-29/PDC-DOWN-20260929T0020Z, 2026-10-02/PDC-UP-20261002T0740Z
- FADE_VALUE_AREA_EXTREME: 2026-09-29/FADE-UP-20260928T2350Z, 2026-09-30/FADE-UP-20260930T0215Z
- RETURN_TO_VALUE: 2026-09-29/RTV-DOWN-20260928T2220Z, 2026-09-30/RTV-DOWN-20260930T0810Z
- VWAP_BOUNCE: 2026-09-29/BOUNCE-UP-20260928T2315Z, 2026-10-02/BOUNCE-UP-20261002T0650Z

## Curriculum questions

```json
{"families_too_sparse_for_lessons":[],"family_counts":{"FADE_VALUE_AREA_EXTREME":9,"PRICE_DISCOVERY_CONTINUATION":12,"RETURN_TO_VALUE":34,"VWAP_BOUNCE":10},"family_stratum_cells_with_enough_examples":["FADE_VALUE_AREA_EXTREME/LATER_OVERNIGHT","PRICE_DISCOVERY_CONTINUATION/LATER_OVERNIGHT","RETURN_TO_VALUE/LATER_OVERNIGHT","RETURN_TO_VALUE/US_CASH_SESSION","VWAP_BOUNCE/LATER_OVERNIGHT"],"most_common_first_unsatisfied":{"FADE_VALUE_AREA_EXTREME":"3:LAB_REJECTION_V1:NOT_SATISFIED","PRICE_DISCOVERY_CONTINUATION":"2:LAB_ACCEPTANCE_TIME_V1:NOT_SATISFIED","RETURN_TO_VALUE":"3:LAB_ACCEPTANCE_TIME_V1:NOT_SATISFIED","VWAP_BOUNCE":"5:LAB_DIRECTIONAL_CONFIRMATION_V1:NOT_SATISFIED"},"overlap_combinations":{"FADE+BOUNCE":3,"FADE+RTV":5,"PDC+BOUNCE":1,"PDC+FADE":1,"PDC+RTV":9,"RTV+BOUNCE":9,"RTV+RTV":1},"quality_warnings_to_explain":{"CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/LOCAL_EVIDENCE":1,"CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE":61,"CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE+KNOWN_GAP/UPSTREAM_REFERENCE":3,"NOT_ELIGIBLE:CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE+KNOWN_GAP/LOCAL_EVIDENCE":1}}
```

## Human review

RESERVED FOR HUMAN REVIEW (not filled automatically)
