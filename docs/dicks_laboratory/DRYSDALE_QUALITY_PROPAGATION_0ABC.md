# 0AB-C: Drysdale Quality Propagation & Validation Readiness Audit

This is a quality-semantics audit on the **development corpus** (2026-09-29 .. 10-02,
already inspected in 0AB-B). It is DEVELOPMENT / DESCRIPTIVE evidence, not validation, and
it contains no trade advice.

- **DRYSDALE_V1 market rules:** unchanged; the freeze hashes verify.
- **Prospective campaign data (2026-10-12 .. 11-06):** not analyzed.

The reference for the new semantics is [DRYSDALE_QUALITY_SCOPE.md](DRYSDALE_QUALITY_SCOPE.md).
The evidence is in [evidence/0AB-C/](evidence/0AB-C/):

- harness `qc_audit.py` / `run_qc.sh` / `qc_table.py`;
- per-date `*_quality.json` and logs;
- `propagation_table.md`;
- `propagation_summary.json`;
- the database sha256 before and after (unchanged).

The harness imported a pinned copy of `drysdale_quality.py` whose sha256
(`1d54d63e…`, recorded in `run.log`) equals the committed module.

## 1. Answer: why 66 / 66 candidates were QUALITY_QUALIFIED

**Mechanism (frozen V1, verified at every hourly cutoff on every date).**

- `analysis.status` is the snapshot's Globex (SESSION_OPEN) VWAP status, and every candidate copies that one value.
- There were zero failures of the dependency proof:

  ```text
  analysis.status == vw.status
  analysis.reasons[:n] == vw.reasons
  candidate.quality == analysis.status   (for every candidate)
  ```

- Candidates carry no reason of their own.

**Cause.** The Globex VWAP was QUALITY_QUALIFIED at every cutoff on every date because
**the capture began 0.203–0.363 ms after 17:00:00 CT**. The strict boundary rule has no
tolerance:

| Date | Capture started after the anchor | First observed trade after the anchor |
|---|---|---|
| 09-29 | 0.000256 s | 1.340 s |
| 09-30 | 0.000363 s | 1.352 s |
| 10-01 | 0.000351 s | 1.145 s |
| 10-02 | 0.000203 s | 1.000 s |

**The Product Owner hypothesis is confirmed as the dominant cause; it was verified, not
assumed.**

- The boundary reason is present, and alone sufficient, for **all 66**.
- At the candidate's first-known cutoff, the status-driving reasons were:
  - the boundary only, for **62**;
  - the boundary + KNOWN_GAP, for **4** (09-29, after the 1.6 s disconnect at 04:14:58 CT was known).
- At the 16:00 as-of cutoff, `LIFECYCLE_NOT_FINALIZED` is also added (the capture was still running). It disappears with the final-knowledge cutoff (16:30 knowledge, FINALIZED).
- `OVERNIGHT window not captured through the clock` is a context reason: the same boundary fact, seen from the OVERNIGHT window. It does not drive the status.

**Operational root (recorded; not changed).** The collector opens the dataset at
session open, so `capture_started_at` is always a few hundred microseconds after 17:00:00 CT.
Under the strict rule every campaign date will therefore carry
`CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR`, and `ELIGIBLE_UNQUALIFIED` is
structurally unreachable for Globex-anchored candidates in this campaign.

This is the correct consequence of not inventing a tolerance. Validation therefore
counts `ELIGIBLE_QUALITY_QUALIFIED` separately. A capture that starts before the
anchor would be a separate, PO-authorized operational change; none was made, and the campaign is
untouched.

## 2. Completeness uncertainty vs evidence unreliability

Frozen V1 conflates the two meanings, because its one analysis-wide status covers:

- A, boundary completeness uncertainty;
- B, a real gap inside a candidate's own window.

The additive `DRYSDALE_QUALITY_SCOPE_V1` separates them per candidate, from structured
fields:

| Meaning | ReasonCode / materiality | Candidates (first known) |
|---|---|---|
| A: boundary not proven, outside the window | CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR / PROVENANCE | 65 |
| A: boundary not proven, window includes the first bar | CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR / LOCAL_EVIDENCE | 1 (09-29 RTV-DOWN-20260928T2220Z, window 17:00–17:25) |
| B: recorded gap inside the window | KNOWN_GAP / LOCAL_EVIDENCE | 1 (09-29 BOUNCE-UP-20260929T0935Z) |
| upstream: the gap lies in the bands' accumulation before the window | KNOWN_GAP / UPSTREAM_REFERENCE | 3 |
| after the candidate (16:00 / final knowledge only) | KNOWN_GAP / NOT_A_DEPENDENCY | 10 (09-29 candidates that completed before 04:14:58) + 1 |

These are the same KNOWN_GAP the frozen analysis-wide status attaches to all 15
09-29 candidates at 16:00. Only 1 of them depends on it locally, and 3 depend on it upstream.

## 3. Dependency propagation (machine-readable)

`propagation_16_00` in each `*_quality.json`, from `dq.propagation`:

1. **dataset / capture coverage:** capture start, gaps, lifecycle as of the cutoff.
2. **Globex VWAP:** status and reasons.
3. **VWAP_BANDS_GLOBEX_V1:** status unchanged.
4. **BARS_5M_V1:** no own field.
5. **conditions:** ConditionStatus only.
6. **candidate:** equals the analysis status.

`status_by_cutoff` gives the status-driving reasons and their codes at all 23
hourly cutoffs. Every analysis reason on every date was classified; none was
`UNEXPLAINED_UPSTREAM_REASON`.

## 4. Real-data proof table (66 candidates)

The full table, one row per candidate, is in
[evidence/0AB-C/propagation_table.md](evidence/0AB-C/propagation_table.md). Its columns are:

- date, candidate, family, direction, first-known cutoff;
- frozen quality;
- reasons (code / scope / materiality);
- Globex-boundary status;
- known gap in the window, untraded slot in the window;
- local evidence complete;
- eligibility at first known and at the final-knowledge cutoff.

Representative rows:

| Date | Candidate | First known | Window (CT) | Reasons | Gap in window | Local complete | Eligibility |
|---|---|---|---|---|---|---|---|
| 09-30 | PDC-DOWN-20260930T0940Z | 07:00 | 04:30–06:45 | boundary / PROVENANCE | no | yes | ELIGIBLE_QUALITY_QUALIFIED |
| 09-29 | RTV-DOWN-20260928T2220Z | 18:00 | 17:00–17:25 | boundary / **LOCAL_EVIDENCE** | no | no | ELIGIBLE_QUALITY_QUALIFIED |
| 09-29 | BOUNCE-UP-20260929T0935Z | 05:00 | 03:40–04:40 | boundary / PROVENANCE; KNOWN_GAP / **LOCAL_EVIDENCE** | **yes** | no | **NOT_ELIGIBLE** |
| 09-29 | PDC-DOWN-20260929T1555Z | 13:00 | 10:45–12:55 | boundary / PROVENANCE; KNOWN_GAP / UPSTREAM_REFERENCE | no | yes | ELIGIBLE_QUALITY_QUALIFIED |
| 10-01 | FADE-DOWN-20261001T1915Z | 15:00 | 13:55–15:00 | boundary / PROVENANCE | no | yes | ELIGIBLE_QUALITY_QUALIFIED |

**Stale evidence.** There is none: no ACTIVE_INTERRUPTION at any cutoff, and no untraded 5-minute
slot inside any candidate window.

## 5. Representative case types (item 11)

| Case | Development corpus |
|---|---|
| Boundary-only qualification | 61 candidates (e.g. 09-30 PDC-DOWN-20260930T0940Z) |
| Actual known gap | 09-29, KNOWN_GAP 04:14:58.865–04:15:00.457 CT (1.59 s, disconnect → reconnect) |
| Late capture start | **does not exist**: every capture began within 0.4 ms of 17:00 CT (the sub-millisecond boundary is the only "late start") |
| Stale / interrupted dataset | **does not exist**: all four FINALIZED; no ACTIVE_INTERRUPTION. The 16:00 as-of `lifecycle OPEN` is a not-yet-stopped capture, not an interruption |
| Clean setup interval with boundary uncertainty | e.g. 09-30 PDC-DOWN-20260930T0940Z, 10-01 FADE-DOWN-20261001T1915Z |
| Long-established Globex VWAP | 09-29 PDC-DOWN-20260929T1555Z (window 10:45–12:55, about 18 h after the anchor) |
| Setup interval overlaps a real quality event | 09-29 BOUNCE-UP-20260929T0935Z (NOT_ELIGIBLE) |

The fixtures also cover the missing types (late start, stale price, ACTIVE_INTERRUPTION inside a window,
unrecorded capture). See `tests/test_drysdale_quality.py`.

## 6. Summary statistics (item 23)

| Measure | Count |
|---|---|
| Total development candidates | **66** (all frozen QUALITY_QUALIFIED) |
| Qualified (status-driving, at first known) because of the Globex boundary only | **62** |
| … an actual gap (with the boundary) | **4** (09-29), of which 1 is local, 3 upstream |
| … a stale or interrupted capture | **0** |
| … multiple reasons | **4** |
| Clean validation eligible (ELIGIBLE_UNQUALIFIED) | **0** |
| Qualified but validation eligible (ELIGIBLE_QUALITY_QUALIFIED) | **65** |
| Validation ineligible (NOT_ELIGIBLE) | **1** |

The eligibility counts are identical at the first-known cutoff, the 16:00 as-of cutoff and the
final-knowledge cutoff. On every date the candidate set at 16:00 as-of equals the set at
final knowledge.

## 7. VWAP sensitivity, as illustration (item 13)

This section is **SENSITIVITY ANALYSIS ONLY**. The hypothetical trades are not source truth and never
written. It is not an acceptance gate and not a rule.

**Method.** For each date, one hypothetical trade was placed **at** 17:00:00.000 CT, inside the
unproven [anchor, capture start) interval. Its price was the first observed price −20, 0 or +20 ticks,
and its size 1, 10, 100 or 1,000 contracts. It was prepended to an in-memory copy of the 16:00 as-of
tape, and DRYSDALE_V1 was re-run.

**Scale.**

- The unproven interval is **0.20–0.36 ms** long.
- The first observed trade came 1.0–1.35 s after the anchor.
- The whole first 5-minute bar traded 689–1,852 contracts.

So 1 contract is a plausible worst case inside a sub-millisecond window. 1,000 contracts is
deliberately implausible and only marks an upper bound.

| Hypothetical size | Runs (of 12) changing any candidate | Max \|ΔVWAP\| at the 09:30 bar | Max \|ΔVWAP\| at 16:00 |
|---|---|---|---|
| 1 | 1 | 0.0003 tick | 0.0001 tick |
| 10 | 2 | 0.0032 tick | 0.0013 tick |
| 100 | 7 | 0.032 tick | 0.013 tick |
| 1,000 | 12 | 0.32 tick | 0.13 tick |

**When changes happen.** Every changed candidate completed in the first hours of
the Globex session:

- the latest completed at 05:20 CT (12 h 20 m after the anchor), and only at 1,000 contracts;
- **none completed in 08:30–16:00 CT**.

**Early-session sensitivity.** In the first hour σ is built from few trades, and VWAP shifts
at the 18:00 bar reach 0.5–5 ticks at 100–1,000 contracts. On 10-01, a single hypothetical contract
at −20 ticks created a candidate that does not exist in the observed data: PDC-UP-20260930T2210Z, which
would complete at 17:25 CT. The "changed" counts are symmetric differences, so they count
candidates that appear, disappear or change completion time.

**Lesson.**

- **Real but tiny later:** the boundary uncertainty is technically real and materially negligible for a long-established Globex VWAP later in the day.
- **Not negligible early:** for candidates in the first Globex hour it is **not** negligible. That is exactly where `LOCAL_EVIDENCE` / early-window scope matters.
- **No rule:** this is not converted into a rule or a tolerance.

## 8. Validation eligibility (defined before any campaign date is inspected)

`DRYSDALE_VALIDATION_ELIGIBILITY_V1` is defined in DRYSDALE_QUALITY_SCOPE.md §4. It is evaluated
at market 16:00 CT with knowledge after finalization. Statistics keep these counts separate:

- total;
- ELIGIBLE_UNQUALIFIED;
- ELIGIBLE_QUALITY_QUALIFIED;
- NOT_ELIGIBLE.

The reporting sub-counts and stratification were pre-registered after PO acceptance in
[DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md](DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md).

## 9. Not changed

- **DRYSDALE_V1:** thresholds, proxies, the VWAP anchor and the boundary rule; no tolerance was added.
- **Production:** campaign schedules, timers and the collector.
- **Receipt-lag label:** deferred, because `TUTOR_EVIDENCE_CONTEXT_V1` was not re-versioned.
- **Tutor:** changed only additively (V4, opt-in; V3 registered). See [evidence/0AB-C/FREEZE_ADDENDUM.md](evidence/0AB-C/FREEZE_ADDENDUM.md).

## 10. Product Owner acceptance (2026-10-11)

```text
0AB-C:
PASS / ACCEPTED / CLOSED

DRYSDALE_V1:
FROZEN / UNCHANGED

DRYSDALE_QUALITY_SCOPE_V1:
ACCEPTED

DRYSDALE_VALIDATION_ELIGIBILITY_V1:
ACCEPTED
```

PO decision:

```text
DO NOT change capture-start behavior during the current
2026-10-12 through 2026-11-06 campaign.

Use ELIGIBLE_QUALITY_QUALIFIED as the expected validation
baseline for Globex-anchored Drysdale candidates.
```

- **Pre-registration:** separate reporting and stratification, in
  [DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md](DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md).
- **Backlog:** `PRE-ANCHOR CAPTURE READINESS`, a separate production-engineering phase after the
  campaign; see [BACKLOG.md](BACKLOG.md).
- **Campaign:** ARMED; analytic inspection NONE; production configuration UNCHANGED.
