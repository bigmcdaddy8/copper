# 0AB-D freeze addendum 1: bar-interval session-boundary assignment

Additive record. [FREEZE.md](FREEZE.md) is not edited: its sha256 lines stay as written at the original freeze
(2026-10-13T03:09:13Z, plan commit `1a0a20b`).

| Field | Value |
|---|---|
| Recorded | 2026-10-13T23:32:21Z (2026-10-13 18:32 CDT) |
| Base commit (before this addendum) | `5cb1fa94f250da5ad578a68ef4c9f4f616872799` |
| Authorized by | Product Owner, 0AB-D plan review (§25 approved as written; one boundary clarification required) |
| Reason | clarify bar-interval session-boundary assignment |
| Campaign data inspected | **NONE** (fixtures and development records only) |

## Clarification

The candidate reference time stays the end of the completing 5-minute bar. A time-of-day stratum is assigned from
the completing bar's interval, not by applying half-open session boundaries naively to the bar-end timestamp:

```text
FIRST_GLOBEX_HOUR   bars 17:00-17:05 .. 17:55-18:00 CT   (bar end <= 18:00)
LATER_OVERNIGHT     bars 18:00-18:05 .. 08:25-08:30 CT   (bar end <= 08:30)
US_CASH_SESSION     bars 08:30-08:35 .. 14:55-15:00 CT
POST_CASH           bars 15:00-15:05 .. 15:55-16:00 CT

completion 08:30 -> LATER_OVERNIGHT (overnight)    completion 08:35 -> US_CASH_SESSION
completion 15:00 -> US_CASH_SESSION                completion 15:05 -> POST_CASH
```

Exactly one time-of-day stratum per candidate, with no overlap or gap at 08:30 or 15:00.

The frozen `stratum()` function already assigned strata this way (its 0AB-D test asserted 08:30 -> overnight and
15:00 -> cash). No stratum assignment changes, and the development shakedown records remain valid as committed.

## Hash changes (applied by the campaign guard; `old -> new  path`)

```text
6aa461bb6a5e49bdddd534bbcea6c2e1c36b3b8ff8786eae263879904a7be377 -> 4bb30c09f9c08cc0479f903ec7df3d3c0c915019e4f1b0f50590023a3792fef7  docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md
ba188eb55998b2ae21358dcbb988a9ab4112f5e1b857f2f80bf30999b8ea3133 -> 42ce737f074a5aad406c721713b0069d9c7a02f91e1639a2d04802fb1d67af03  apps/dicks_laboratory/src/dicks_laboratory/drysdale_validation.py
```

- **Plan:** in §5, the strata table is restated by bar interval and a boundary-semantics paragraph is added. §15
  names the cash and POST_CASH subsets by bar interval. §23 describes how an addendum is applied.
- **`drysdale_validation.py`:** the `Stratum` comments are restated by bar interval. The access guard now applies
  numbered `FREEZE_ADDENDUM_<n>.md` files in order: a hash is replaced only if its stated old sha256 is the one in
  force, and an unnumbered addendum blocks access. Without this, the original guard would refuse every campaign
  date after any recorded addendum. `stratum()`, `date_record` and every cohort, flag and classification function
  are byte-for-byte unchanged.

All other frozen files are unchanged and still verify as listed in FREEZE.md:
`DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md` (`49b07a71…fa0a`), the four DRYSDALE_V1 market-rule files, the
two quality-policy files and the CLI `scripts/dicks_lab_drysdale_validation.py` (`b14c9675…ee8cbe`).

## Semantic effects

```text
no market policy change
no quality-policy change
no challenge-threshold change
no hypothesis change
no new stratification
no campaign data inspected
```

## Tests

- `test_stratum_boundaries_follow_the_completing_bar_interval` covers the four PO examples (CDT, and the first CST
  session after the DST change). It also checks all 276 session bars: each gets exactly one stratum, strata are
  contiguous, and the counts are 12 first-hour, 78 cash and 12 POST_CASH.
- `test_every_development_candidate_has_exactly_one_stratum` runs on the committed development records (dates
  before 2026-10-12) only.
- `test_guard_refuses_campaign_dates_until_the_plan_freeze_verifies` covers addendum handling: the new plan
  sha256 opens the guard, the superseded one is refused, a wrong old sha256 blocks access and an unnumbered
  addendum blocks access.

From now on, `--frozen-plan` must be the plan sha256 in force:
`4bb30c09f9c08cc0479f903ec7df3d3c0c915019e4f1b0f50590023a3792fef7`.
