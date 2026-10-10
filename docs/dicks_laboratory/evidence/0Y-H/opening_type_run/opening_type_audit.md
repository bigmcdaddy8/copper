# OPENING_TYPE_V1 descriptive audit

OPENING_TYPE_V1 is a pre-registered Laboratory candidate policy, not an industry-standard mechanical definition. Candidates are descriptive taxonomy, not signals.

Cohorts: DEVELOPMENT 17.
DEVELOPMENT = inspected before or at the freeze: **NOT VALIDATION**. Only VALIDATION records (unseen dates after the freeze, scored by the unmodified frozen source) are validation evidence.

## Counts — DEVELOPMENT (NOT VALIDATION)

| Item | Count |
|---|---|
| profiled days | 17 |
| NOT_CLASSIFIED days | 2 |
| classified days with no candidate | 0 |
| classified days with one candidate | 11 |
| classified days with several candidates | 4 |
| matched candidates that are QUALITY_QUALIFIED | 3 |
| candidate OPEN_AUCTION | 7 |
| candidate OPEN_AUCTION_IN_RANGE | 4 |
| candidate OPEN_AUCTION_OUT_OF_RANGE | 2 |
| candidate OPEN_DRIVE DOWN | 2 |
| candidate OPEN_TEST_DRIVE DOWN | 4 |
| overlap OPEN_AUCTION + OPEN_TEST_DRIVE | 1 |
| overlap OPEN_AUCTION_IN_RANGE + OPEN_TEST_DRIVE | 2 |
| overlap OPEN_AUCTION_OUT_OF_RANGE + OPEN_TEST_DRIVE | 1 |

## Per-day candidate table

| Date | Dataset | Cohort | Opening q. | Prior | Overnight q. | Open vs prior range / value | Open Drive | OAIR | OAOR | OA (no prior) | Open Test Drive | TD reference | Matched | Qualified candidates |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 | befb7b0e | DEVELOPMENT | NOT_AVAILABLE | NO_PRIOR_PROFILE | NOT_AVAILABLE | -- | NOT_CLASSIFIED | | | | | | 0 | |
| 2026-08-31 | c9ebc043 | DEVELOPMENT | NOT_AVAILABLE | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | NOT_CLASSIFIED | | | | | | 0 | |
| 2026-09-02 | 9c76e79c | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | no | -- | 1 | -- |
| 2026-09-07 | 85eccb13 | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | no | -- | 1 | -- |
| 2026-09-08 | e3110b72 | DEVELOPMENT | QUALITY_QUALIFIED | PRIOR_PROFILE_INCOMPLETE / UNQUALIFIED | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | no | -- | 1 | OPEN_AUCTION |
| 2026-09-11 | 3716af9f | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | no | -- | 1 | -- |
| 2026-09-15 | b07e92d4 | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | YES DOWN | n/c | n/c | no | no | -- | 1 | -- |
| 2026-09-21 | 64d684c9 | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | no | OVERNIGHT_HIGH | 1 | -- |
| 2026-09-23 | b2856c52 | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | no | OVERNIGHT_LOW | 1 | -- |
| 2026-09-24 | 31c92a57 | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | BELOW_PRIOR_RANGE / BELOW_PRIOR_VALUE | no | no | YES | -- | no | -- | 1 | -- |
| 2026-09-25 | c690ff8e | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | INSIDE_PRIOR_RANGE / INSIDE_PRIOR_VALUE | no | YES | no | -- | YES DOWN | PRIOR_VAH | 2 | -- |
| 2026-09-28 | 843a6ca0 | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | INSIDE_PRIOR_RANGE / BELOW_PRIOR_VALUE | no | YES | no | -- | no | -- | 1 | -- |
| 2026-09-29 | 6af08205 | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | INSIDE_PRIOR_RANGE / INSIDE_PRIOR_VALUE | YES DOWN | no | no | -- | no | PRIOR_VAL | 1 | -- |
| 2026-09-30 | 9ac5a21e | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | INSIDE_PRIOR_RANGE / ABOVE_PRIOR_VALUE | no | YES | no | -- | YES DOWN | PRIOR_HIGH | 2 | -- |
| 2026-10-01 | fe280370 | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | INSIDE_PRIOR_RANGE / BELOW_PRIOR_VALUE | no | YES | no | -- | no | -- | 1 | -- |
| 2026-10-02 | 7e8d7b5e | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | QUALITY_QUALIFIED | ABOVE_PRIOR_RANGE / ABOVE_PRIOR_VALUE | no | no | YES | -- | YES DOWN | OVERNIGHT_HIGH | 2 | OPEN_TEST_DRIVE |
| 2026-10-06 | 2b6cc528 | DEVELOPMENT | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | -- | no | n/c | n/c | YES | YES DOWN | OVERNIGHT_HIGH | 2 | OPEN_TEST_DRIVE |

Legend: YES = CANDIDATE; no = NOT_CANDIDATE; n/c = NOT_CLASSIFIED; -- = NOT_APPLICABLE. OPEN_REJECTION_REVERSE is DEFERRED (REFERENCE_DEFINITION_CONFLICT) on every day.
