# 0AB-B Real-Data Study: Drysdale VWAP Training Candidates V1

This is a descriptive study. Its corpus is **DEVELOPMENT / DESCRIPTIVE**: it is
not validation, not a backtest, and not trade advice. The candidates are
Laboratory training labels. They are not signals, and nothing below is a
statement about outcomes.

Policy reference: [DRYSDALE_VWAP_TRAINING_CANDIDATES.md](DRYSDALE_VWAP_TRAINING_CANDIDATES.md).
Evidence: [evidence/0AB-B/](evidence/0AB-B/).

## 1. Freeze before the audit

DRYSDALE_V1 was frozen before any real-data run. FREEZE.md records the sha256 of
6 files:

- `drysdale.py`
- the policy doc
- `test_drysdale.py`
- `price_action.py`
- `tutor_evidence.py`
- `tutor_ai.py`

- **Hash note:** the audit ran at local commit `1c96138`, so every log line says
  "frozen DRYSDALE_V1 at 1c961381…". That commit was then rebased onto the
  updated origin and pushed as `553ac27` (`feat: versioned Drysdale VWAP
  training candidates`). The rebase changed no frozen file: the tree content
  for the frozen paths is identical and the FREEZE.md sha256s verify against
  `553ac27`.
- **Nothing tuned:** no threshold, proxy or family rule was changed after the
  results were seen. A change would be V2.
- **Read-only:** the harness never wrote the corpus. The database sha256s are
  identical before and after (`db_sha_before.txt` = `db_sha_after.txt`, and
  `run.log` says `DATABASE SHA256 UNCHANGED`).

## 2. Corpus and method

The corpus is four authenticated pre-campaign trading dates, 2026-09-29 to
2026-10-02. Each date is prepared with the previous date's dataset, so the
Globex session starts at 17:00 CT the evening before. None of these dates
belong to the prospective 2026-10-12 to 11-06 campaign, which is not inspected.

The harness (`evidence/0AB-B/harness/dr_audit.py`, driven by `run_dr.sh`)
analyses each date as follows:

- **Hourly replay cutoffs:** `analyze` runs at each cutoff from 18:00 to 16:00 CT
  (23 steps) through one shared `DrysdaleCache`, the same path a lesson uses.
- **Cold analysis at 16:00:** a cold analysis is run twice for determinism,
  compared with the resumed result, and timed against the 0AB-A
  PRICE_ACTION_FACTS_V1 reference.
- **Cross-checks:** the Globex VWAP is compared with the snapshot SESSION_OPEN
  VWAP, and the last ATR_5M_V1 with the 0AB-A fact.
- **Lessons:** Drysdale lessons are built at 10:00 and 12:00 and the reference
  answer is passed through the tutor pipeline.

## 3. Correctness cross-checks (all dates)

| Check | 09-29 | 09-30 | 10-01 | 10-02 |
|---|---|---|---|---|
| Cold run twice gives identical bytes | ✔ | ✔ | ✔ | ✔ |
| Resumed analysis = cold analysis at 16:00 | ✔ | ✔ | ✔ | ✔ |
| Globex VWAP = snapshot SESSION_OPEN VWAP | ✔ | ✔ | ✔ | ✔ |
| Last-bar ATR = PRICE_ACTION_FACTS_V1 ATR_5M_V1 | ✔ | ✔ | ✔ | ✔ |
| Lesson reference answer | GROUNDED (V3) | GROUNDED (V3) | GROUNDED (V3) | GROUNDED (V3) |
| Analysis JSON size | 857,987 B | 990,958 B | 858,560 B | 828,976 B |

## 4. Counts at 16:00 CT (276 complete Globex 5-minute bars per date)

Candidates are instances that satisfied all conditions:

| Family | Direction | 09-29 | 09-30 | 10-01 | 10-02 | Total |
|---|---|---|---|---|---|---|
| PRICE_DISCOVERY_CONTINUATION | UP | 0 | 0 | 2 | 4 | 6 |
| PRICE_DISCOVERY_CONTINUATION | DOWN | 3 | 2 | 1 | 0 | 6 |
| FADE_VALUE_AREA_EXTREME | UP | 2 | 4 | 1 | 0 | 7 |
| FADE_VALUE_AREA_EXTREME | DOWN | 0 | 0 | 1 | 1 | 2 |
| RETURN_TO_VALUE | UP | 3 | 5 | 4 | 1 | 13 |
| RETURN_TO_VALUE | DOWN | 5 | 6 | 4 | 6 | 21 |
| VWAP_BOUNCE | UP | 2 | 2 | 1 | 2 | 7 |
| VWAP_BOUNCE | DOWN | 0 | 2 | 1 | 1 | 4 |
| **Candidates** | | **15** | **21** | **15** | **15** | **66** |
| Instances still DEVELOPING | | 36 | 60 | 39 | 32 | 167 |
| Candidates whose first event is in 08:35–16:00 CT | | 1 | 6 | 5 | 3 | 15 |

The intermediate stage of each DEVELOPING instance is listed in the
per-date logs.

| Family | Stage reached and stopped at |
|---|---|
| PRICE_DISCOVERY_CONTINUATION | BREAKOUT_TRIGGERED, ACCEPTED_OUTSIDE, RETEST_OBSERVED |
| FADE_VALUE_AREA_EXTREME | BOUNDARY_TESTED, REJECTION_OBSERVED |
| RETURN_TO_VALUE | RETURNED_TO_VALUE |
| VWAP_BOUNCE | VWAP_TESTED |

**Overlaps:**

- On 09-29, one bar (18:55) completed two candidates.
- Cross-family candidate pairs whose first-to-completion intervals intersect: 1, 2, 0 and 0 (by date).

**First-known timestamps:** every candidate is first visible at the first
hourly cutoff at or after its completing bar. No candidate appeared at an
earlier cutoff, and none became visible before its completing bar closed. The
per-candidate first, completed and first-seen times are in each date's log.

## 5. Quality

**Every candidate on every date is QUALITY_QUALIFIED.** The analysis inherits
the Globex VWAP qualification:

- capture began 0.2–0.4 ms after the 17:00 CT anchor;
- the dataset lifecycle is OPEN, not FINALIZED, in the as-of replay;
- the OVERNIGHT window was not captured through the clock;
- on 09-29 one KNOWN_GAP overlaps the VWAP interval.

None of these candidates reaches the unqualified CANDIDATE state. This is the
quality propagation working as intended. It is not a defect to tune away.

## 6. Descriptive context (PDC instances)

| Measure | 09-29 | 09-30 | 10-01 | 10-02 |
|---|---|---|---|---|
| PDC instances (all stages) | 19 | 31 | 22 | 16 |
| … reached ±2σ (outer context) | 7 (36.8%) | 11 (35.5%) | 7 (31.8%) | 5 (31.3%) |
| PDC candidates that reached ±2σ | 2/3 | 1/2 | 3/3 | 3/4 |
| Trigger-bar volume ÷ mean of preceding bars (median) | 0.88 | 0.97 | 0.84 | 0.92 |
| … triggers with ratio > 1 | 5/19 | 15/30 | 6/22 | 7/16 |
| VWAP slope in the trigger direction | 19/19 | 30/30 (1 unavailable) | 22/22 | 16/16 |
| LAB_ACCEPTANCE_TIME_V1 satisfied | 11/19 | 19/31 | 14/22 | 10/16 |
| LAB_RETEST_V1 satisfied | 8/19 | 7/31 | 4/22 | 7/16 |
| Triggers in the first two Globex hours (17:00–19:00 CT) | 1 | 3 | 3 | 3 |

What these numbers say:

- **±2σ:** about a third of PDC instances reached the outer band. This counts
  occurrences. It measures no outcome.
- **Trigger volume:** the median volume of a trigger bar is near the recent
  mean, so volume is a context fact and not a discriminator. In V1 it carries
  no label.
- **Slope:** at the trigger, slope agrees with the trigger direction in every
  case where slope is available. This follows mechanically from a close beyond
  a band that is moving with price, and in V1 slope carries no label.

## 7. Known V1 behaviors confirmed (documented, not tuned)

- **Early Globex triggers are frequent.** In the first hours σ is small, so
  closes beyond ±1σ come easily (policy doc §10). Of the 66 candidates, 51
  have their first event before 08:35 CT.
- **RETURN_TO_VALUE is the most frequent family** (34 of 66). Its proxy only
  needs one accepted outside episode followed by an inside close, a common
  sequence on a two-sided day.
- **Most PDC instances stop before CONDITIONS_SATISFIED.** LAB_RETEST_V1 is the
  most frequent unmet condition.

These are inputs for a possible V2. Any V2 must be frozen before the
prospective campaign data are inspected for it (see
[ES_CORPUS_CAMPAIGN_2026_10.md](ES_CORPUS_CAMPAIGN_2026_10.md) §1).

## 8. Performance

At the 16:00 CT cutoff:

| Measure | 09-29 | 09-30 | 10-01 | 10-02 |
|---|---|---|---|---|
| Trades in the as-of scope | 1,194,184 | 1,396,922 | 1,667,659 | 1,387,079 |
| Prepare session (once) | 222.8 s | 238.8 s | 244.6 s | 267.5 s |
| Snapshot | 25.7 s | 34.0 s | 33.6 s | 29.4 s |
| As-of tape | 10.6 s | 13.7 s | 13.6 s | 11.2 s |
| **Drysdale cold analysis, given the tape** | **9.1 s** | **9.5 s** | **11.4 s** | **9.4 s** |
| 0AB-A PRICE_ACTION_FACTS_V1, given the tape (reference) | 41.6 s | 42.9 s | 49.3 s | 39.8 s |
| Cache hit (same cutoff) | 0.08 ms | 0.07 ms | 0.05 ms | 0.05 ms |
| Lesson build, and a second question at the same time | 0.1 s / 0.1–0.2 s | 0.1 s / 0.1 s | 0.1 s / 0.1 s | 0.1 s / 0.1 s |
| Hourly steps: resumed / full recompute (of 23) | 20 / 3 | 20 / 3 | 19 / 4 | 18 / 5 |
| Peak RSS (whole harness process) | 3.39 GB | 3.93 GB | 4.78 GB | 4.49 GB |
| Additional RSS from the analysis | ≈0 | ≈0 | ≈0 | ≈0 |

How to read these timings:

- **Hourly step times** rise from about 2.5 s at 18:00 to 45–62 s at 16:00.
  The snapshot and the as-of tape dominate that growth, and the existing
  replay recomputes both at every cutoff. The Drysdale pass itself is
  resumable.
- **Full recomputes:** the resume was refused correctly, and the pass was
  recomputed from the anchor, whenever newly known records between two
  cutoffs had a market time before the earlier market cutoff (late prints).
  The resumed result at 16:00 was byte-identical to the cold result.

## 9. Conclusion

DRYSDALE_SETUP_CANDIDATES_V1 behaves as specified on four real dates:

- it is deterministic;
- the resumed analysis is identical to the cold analysis;
- it agrees with the snapshot VWAP and the 0AB-A ATR;
- quality propagates (all candidates are QUALITY_QUALIFIED, none plain CANDIDATE);
- a lesson is answered from the cache in about 0.1 s;
- the tutor reference answers are GROUNDED under TUTOR_SYSTEM_PROMPT_V3_DRYSDALE.

This is development evidence only. It is not validation of any setup, and it
makes no claim about what happens after a candidate. Prospective evaluation, if
any, belongs to separately authorized work on post-freeze data.
