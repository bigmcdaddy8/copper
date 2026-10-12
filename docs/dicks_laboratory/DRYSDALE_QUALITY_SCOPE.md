# Drysdale Candidate Quality Scope and Validation Eligibility (0AB-C)

**At a glance**

- `QUALITY_QUALIFIED` does **not** mean the candidate is **invalid**.
- It does **not** mean the setup is **false**.
- It does **not** make the candidate **automatically unusable**.
- Its meaning is the **reason**, the **scope** and the **materiality** recorded beside it.

This document is the reference for `DRYSDALE_CANDIDATE_QUALITY_V1`, implemented in
`apps/dicks_laboratory/src/dicks_laboratory/drysdale_quality.py`.

That schema carries two policies:

- `DRYSDALE_QUALITY_SCOPE_V1`: the reason, scope, materiality and evidence window of each qualification.
- `DRYSDALE_VALIDATION_ELIGIBILITY_V1`: whether a candidate can be counted in prospective validation.

The layer is **additive and read-only**. It reads the frozen
`DRYSDALE_SETUP_ANALYSIS_V1` (DRYSDALE_V1; see
[DRYSDALE_VWAP_TRAINING_CANDIDATES.md](DRYSDALE_VWAP_TRAINING_CANDIDATES.md)) and the
`MARKET_STUDY_SNAPSHOT_V1` at the same cutoff, and changes neither. No market rule,
threshold, anchor or tolerance is changed. The real-data proof is in
[DRYSDALE_QUALITY_PROPAGATION_0ABC.md](DRYSDALE_QUALITY_PROPAGATION_0ABC.md).

## 1. What frozen V1 does (unchanged)

The analysis status is the snapshot's Globex VWAP component status. Every candidate
copies that one value (policy doc §6: "V1 is conservative: it does not attribute a gap
to individual bars"), so a candidate whose conditions are all satisfied is
`QUALITY_QUALIFIED` whenever the Globex VWAP is qualified. The status is
analysis-wide, and it says nothing about which evidence of which candidate is touched.

## 2. Dependency propagation

```text
dataset / capture coverage      capture_started_at, KNOWN_GAP / SUSPECTED_GAP intervals, ACTIVE_INTERRUPTION, lifecycle
  -> Globex VWAP (SESSION_OPEN)  status + reasons: capture began after the anchor; gaps in [anchor, clock);
                                lifecycle not FINALIZED (window complete) / STOPPED-not-FINALIZED (developing)
  -> VWAP_BANDS_GLOBEX_V1        analysis.status = that status, unchanged; analysis.reasons append the dataset
                                quality reasons (context only, not status-driving)
  -> BARS_5M_V1 + per-bar bands  no quality field of their own; every bar reads the cumulative VWAP and sigma
  -> Laboratory V1 conditions   ConditionStatus only
  -> candidate                  candidate.quality = analysis.status (the same value for every candidate)
```

`dq.propagation(analysis, snapshot)` returns this chain with the actual status and
reasons at each step, which is the machine-readable dependency proof. The audit's
`explained` list maps every analysis reason string to a `ReasonCode`. A reason with no
match becomes `UNEXPLAINED_UPSTREAM_REASON`, which makes the candidate NOT_ELIGIBLE.

## 3. Reason, scope, materiality

Reasons come from **structured** snapshot fields. Gaps are never inferred from
observation timing.

| ReasonCode | Meaning |
|---|---|
| `CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR` | capture began after 17:00:00 CT, so trades in [anchor, capture start) cannot be ruled out; the duration is a recorded fact and **no tolerance** applies |
| `CAPTURE_INTERVAL_NOT_RECORDED` | coverage cannot be verified |
| `CAPTURE_ENDED_BEFORE_SESSION_END` | the capture ended inside the evidence window |
| `KNOWN_GAP` / `SUSPECTED_GAP` | a recorded gap interval |
| `ACTIVE_INTERRUPTION` | disconnected and not reconnected at the knowledge cutoff, so the last price may be stale |
| `LIFECYCLE_NOT_FINALIZED` | as of the cutoff, final completeness accounting is not yet known (it is OPEN while the capture runs); this is not a gap |
| `UNTRADED_INTERVAL` | a 5-minute slot in the window with no retained trade, so consecutive BARS_5M_V1 bars are not adjacent in time; no gap is inferred |
| `UNEXPLAINED_UPSTREAM_REASON` | an upstream reason this layer cannot classify |

| Scope | Where the fact lives |
|---|---|
| `SESSION_BOUNDARY` | [17:00 CT anchor, capture start), and the capture end compared with the window |
| `GLOBEX_VWAP` | the trades `VWAP_BANDS_GLOBEX_V1` accumulates in [anchor, clock) |
| `SETUP_EVIDENCE_WINDOW` | the bars the candidate's conditions read |
| `DATASET_LIFECYCLE` | the dataset lifecycle as of the cutoff |
| `CURRENT_STATE` | the last known price at the cutoff |

| Materiality | Relation to the candidate |
|---|---|
| `LOCAL_EVIDENCE` | the interval overlaps the candidate evidence window |
| `UPSTREAM_REFERENCE` | the interval lies inside [anchor, window start): the VWAP and σ the window reads were accumulated over it |
| `PROVENANCE` | a recorded dataset fact that touches no bar the candidate reads (the boundary before the window; the lifecycle) |
| `NOT_A_DEPENDENCY` | after the candidate completed (it still qualifies the analysis-wide status) |
| `UNKNOWN` | for an unexplained reason |

**Candidate evidence window.** It starts at the start of the bar *before* the earliest bar
that the candidate's conditions, events or acceptance episodes reference. The preceding bar
is included because several proxies (trigger, slope, trend context, confirmation) compare
with the previous complete bar. The window ends at the end of the completing bar.

Supporting context is not a condition input: the 12-bar volume baseline, the opposing
references and the prior-day, overnight and IB statics.

The boundary is LOCAL_EVIDENCE only when the window includes the first Globex bar.

## 4. Validation eligibility (`DRYSDALE_VALIDATION_ELIGIBILITY_V1`)

| Outcome | Rule |
|---|---|
| `NOT_A_CANDIDATE` | the instance is DEVELOPING; it is not counted |
| `NOT_ELIGIBLE` | any of: a KNOWN_GAP, SUSPECTED_GAP or ACTIVE_INTERRUPTION overlaps the evidence window; the capture ended inside the window; the capture interval is not recorded; an upstream reason is unexplained |
| `ELIGIBLE_QUALITY_QUALIFIED` | any other dependency reason: boundary not proven, an upstream gap, lifecycle not FINALIZED, an untraded slot |
| `ELIGIBLE_UNQUALIFIED` | no reason that is a dependency of the candidate. This is possible even when the frozen state is QUALITY_QUALIFIED, for example when the only gap came after the candidate completed |

A candidate is **not** excluded merely because it carries an explicitly scoped
boundary-completeness qualification. A materially compromised setup interval is
never counted as clean.

Validation statistics keep all four counts separate: total candidates,
ELIGIBLE_UNQUALIFIED, ELIGIBLE_QUALITY_QUALIFIED and NOT_ELIGIBLE (`dq.counts`). They
are never collapsed.

**Evaluation cutoff for validation.** The cutoff is market 16:00 CT, with a
knowledge cutoff after the capture stop (the audit uses 16:30 CT). The dataset is
then FINALIZED, every gap record is known, and `LIFECYCLE_NOT_FINALIZED` no longer
applies.

The eligibility of a candidate is a property of its evidence. It is not a judgement
about the market. The rule was fixed before any campaign date was inspected.

## 5. Examples

| Case | Frozen V1 | Reasons (code / scope / materiality) | Eligibility |
|---|---|---|---|
| Capture began 0.000363 s after 17:00 CT; candidate at 08:55 | QUALITY_QUALIFIED | CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR / SESSION_BOUNDARY / PROVENANCE | ELIGIBLE_QUALITY_QUALIFIED |
| KNOWN_GAP 10:15:00–10:15:30 inside the candidate evidence window | QUALITY_QUALIFIED | KNOWN_GAP / SETUP_EVIDENCE_WINDOW / LOCAL_EVIDENCE | NOT_ELIGIBLE |
| KNOWN_GAP at 02:00 CT; candidate at 08:55 | QUALITY_QUALIFIED | KNOWN_GAP / GLOBEX_VWAP / UPSTREAM_REFERENCE | ELIGIBLE_QUALITY_QUALIFIED |
| KNOWN_GAP at 10:15; candidate completed at 08:55 | QUALITY_QUALIFIED | KNOWN_GAP / GLOBEX_VWAP / NOT_A_DEPENDENCY | ELIGIBLE_UNQUALIFIED |
| Disconnected at 09:10 (no reconnect), cutoff 09:20, candidate at 08:55 | QUALITY_QUALIFIED | ACTIVE_INTERRUPTION / CURRENT_STATE / NOT_A_DEPENDENCY | ELIGIBLE_UNQUALIFIED |
| Boundary not proven plus a 02:00 gap | QUALITY_QUALIFIED | two reasons, each scoped | ELIGIBLE_QUALITY_QUALIFIED |

All of these are tested in `tests/test_drysdale_quality.py`.

## 6. Tutor wording (`TUTOR_SYSTEM_PROMPT_V4_DRYSDALE_QUALITY`)

V4 is opt-in through `drysdale_lesson(..., quality_scope=True)` or
`dicks_lab_tutor_lesson.py --lesson drysdale --quality-scope`, which also offers question 10:
"Why is each candidate quality-qualified, and does any quality reason touch its own
evidence window?". It is V3 plus rule 10.

V3 stays registered and byte-identical. Its prompt hash equals the one in the 0AB-B
run records, which is tested. A Drysdale lesson without the flag is still a V3 lesson.

**Evidence** (`SourceRole.DRYSDALE_QUALITY`, `EvidenceDomain.DRYSDALE_QUALITY`) cites:

- the boundary status;
- the capture start;
- the analysis status;
- per family and direction:
  - the eligibility;
  - the evidence window;
  - the gap counts (overlapping, upstream, after);
  - local evidence complete;
  - each reason's code, scope and materiality.

**Good wording** (each sentence is a claim that cites and asserts the item):

- "The setup candidate is mechanically present." (the DRYSDALE candidate state)
- "The candidate is quality-qualified because exact 17:00 Globex-boundary completeness cannot be proven." (boundary status `NOT_PROVEN`)
- "No known gap overlaps the setup evidence window." (gaps overlapping the window: `0`)
- versus "The setup candidate depends on bars overlapping a known gap." (materiality `LOCAL_EVIDENCE`, eligibility `NOT_ELIGIBLE`)

**Guard** (`GuardCode.QUALITY_SCOPE_MISSTATED`): "unreliable / invalid / compromised /
unusable / false setup / bad data / impaired" is refused unless the claim, or for the
answer text some claim, asserts a DRYSDALE_QUALITY value of `LOCAL_EVIDENCE` or
`NOT_ELIGIBLE`. The grounding validator checks every asserted value against the evidence.

The answer key adds two incorrect claims:

- `QUALIFIED_MEANS_UNRELIABLE`;
- `BOUNDARY_AS_GAP`.

## 7. What is not here

- **No change to frozen code:** no change to the Drysdale market rules, the VWAP anchor or the boundary rule, and no tolerance.
- **No first-trade relabeling:** the first observed trade is never called the Globex opening trade.
- **Receipt-lag unit:** stays deferred. `TUTOR_EVIDENCE_CONTEXT_V1` was not re-versioned in this phase.
