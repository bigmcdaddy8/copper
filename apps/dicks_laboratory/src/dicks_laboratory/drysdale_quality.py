"""Drysdale candidate quality scope and validation eligibility (0AB-C): DRYSDALE_CANDIDATE_QUALITY_V1.

Additive and read-only. It reads a frozen DRYSDALE_SETUP_ANALYSIS_V1 (drysdale.py, DRYSDALE_V1, unchanged)
and the MARKET_STUDY_SNAPSHOT_V1 at the same cutoff, and explains each candidate's quality:

    DRYSDALE_SETUP_CANDIDATES_V1 (frozen)  candidate.quality == analysis.status == the snapshot's Globex
                                           (SESSION_OPEN) VWAP component status, for every candidate alike
    DRYSDALE_QUALITY_SCOPE_V1 (this file)  every qualification as a typed reason with its interval, its
                                           SCOPE (where the fact lives) and its MATERIALITY to the
                                           candidate (which evidence of the candidate it touches)
    DRYSDALE_VALIDATION_ELIGIBILITY_V1     ELIGIBLE_UNQUALIFIED / ELIGIBLE_QUALITY_QUALIFIED / NOT_ELIGIBLE

Reasons are derived from structured snapshot fields (capture start, known gap intervals, the active
interruption, the as-of lifecycle), never from inferred observation timing. Every status-driving reason
string of the Globex VWAP is accounted for (an unexplained one makes the candidate NOT_ELIGIBLE).
No tolerance exists: a capture that began 0.000363 s after 17:00 CT is CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR
exactly like a capture that began two hours late; the duration is recorded as a fact.

Candidate evidence window (DRYSDALE_QUALITY_SCOPE_V1): [start of the bar before the earliest bar the
candidate's conditions, events or acceptance episodes reference, end of the completing bar). The preceding
bar is included because several proxies compare with the previous complete bar. Upstream of that window
the bands themselves depend on every trade in [17:00 CT anchor, window start) (VWAP and sigma are
cumulative). Supporting context (volume baseline, opposing references) is not a condition input.

QUALITY_QUALIFIED is not INVALID, not a false setup and not automatically unusable: its meaning is the
reason, scope and materiality listed here.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from dicks_laboratory import drysdale as dry
from dicks_laboratory import market_study_state as mss

SCHEMA = "DRYSDALE_CANDIDATE_QUALITY_V1"
SCOPE_POLICY = "DRYSDALE_QUALITY_SCOPE_V1"
ELIGIBILITY_POLICY = "DRYSDALE_VALIDATION_ELIGIBILITY_V1"
_BAR = timedelta(minutes=5)


class ReasonCode(StrEnum):
    CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR = "CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR"  # boundary coverage not proven
    CAPTURE_INTERVAL_NOT_RECORDED = "CAPTURE_INTERVAL_NOT_RECORDED"  # coverage unverifiable
    CAPTURE_ENDED_BEFORE_SESSION_END = "CAPTURE_ENDED_BEFORE_SESSION_END"
    KNOWN_GAP = "KNOWN_GAP"
    SUSPECTED_GAP = "SUSPECTED_GAP"
    ACTIVE_INTERRUPTION = "ACTIVE_INTERRUPTION"  # disconnected and not reconnected at the knowledge cutoff
    LIFECYCLE_NOT_FINALIZED = "LIFECYCLE_NOT_FINALIZED"  # as of the cutoff (OPEN while the capture runs)
    UNTRADED_INTERVAL = "UNTRADED_INTERVAL"  # a 5-minute slot in the window with no retained trade (not a gap)
    UNEXPLAINED_UPSTREAM_REASON = "UNEXPLAINED_UPSTREAM_REASON"


class Scope(StrEnum):
    SESSION_BOUNDARY = "SESSION_BOUNDARY"  # [17:00 CT anchor, capture start) / capture end vs 16:00 CT
    GLOBEX_VWAP = "GLOBEX_VWAP"  # trades in [anchor, clock) that VWAP_BANDS_GLOBEX_V1 accumulates
    SETUP_EVIDENCE_WINDOW = "SETUP_EVIDENCE_WINDOW"  # the bars the candidate's conditions read
    DATASET_LIFECYCLE = "DATASET_LIFECYCLE"
    CURRENT_STATE = "CURRENT_STATE"  # the last known price at the cutoff


class Materiality(StrEnum):
    LOCAL_EVIDENCE = "LOCAL_EVIDENCE"  # overlaps the candidate evidence window
    UPSTREAM_REFERENCE = "UPSTREAM_REFERENCE"  # inside [anchor, window start): the bands the window reads
    PROVENANCE = "PROVENANCE"  # a recorded fact about the dataset that touches no bar the candidate reads
    NOT_A_DEPENDENCY = "NOT_A_DEPENDENCY"  # after the candidate completed
    UNKNOWN = "UNKNOWN"


class Eligibility(StrEnum):
    ELIGIBLE_UNQUALIFIED = "ELIGIBLE_UNQUALIFIED"
    ELIGIBLE_QUALITY_QUALIFIED = "ELIGIBLE_QUALITY_QUALIFIED"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NOT_A_CANDIDATE = "NOT_A_CANDIDATE"  # DEVELOPING / NOT_AVAILABLE: no candidate to count


class BoundaryStatus(StrEnum):
    PROVEN = "PROVEN"  # capture started at or before 17:00:00 CT
    NOT_PROVEN = "NOT_PROVEN"  # capture started after the anchor: earlier trades cannot be ruled out
    NOT_RECORDED = "NOT_RECORDED"


@dataclass(frozen=True)
class QualityReason:
    code: ReasonCode
    scope: Scope
    materiality: Materiality
    interval_start_utc: datetime | None
    interval_end_utc: datetime | None
    duration: timedelta | None
    detail: str  # the upstream reason text it explains, or the fact


@dataclass(frozen=True)
class CandidateQuality:
    candidate_id: str
    family: dry.SetupFamily
    direction: object
    state: dry.CandidateState
    candidate_quality: str  # the frozen field (= analysis status), unchanged
    first_event_utc: datetime
    completed_at_utc: datetime | None
    evidence_window_start_utc: datetime
    evidence_window_end_utc: datetime
    evidence_bars: tuple[int, int]  # first and last bar index of the window (analysis /bars)
    boundary_status: BoundaryStatus
    reasons: tuple[QualityReason, ...]
    gaps_overlapping_window: int  # KNOWN / SUSPECTED / ACTIVE intervals overlapping the window
    gaps_upstream: int
    gaps_after_candidate: int
    local_evidence_complete: bool  # no gap, interruption, untraded slot or unproven boundary in the window
    eligibility: Eligibility
    eligibility_basis: tuple[str, ...]


@dataclass(frozen=True)
class PropagationStep:
    step: str
    quality_input: str
    quality_output: str
    reasons: tuple[str, ...]
    note: str


@dataclass(frozen=True)
class DrysdaleQualityAudit:
    schema: str
    policies: tuple[str, ...]
    analysis_sha256: str
    cutoff: object
    analysis_status: str
    analysis_reasons: tuple[str, ...]
    boundary_status: BoundaryStatus
    capture_started_at: datetime | None
    globex_anchor_utc: datetime
    explained: tuple[tuple[str, str], ...]  # (analysis reason text, ReasonCode or CONTEXT:<code>)
    propagation: tuple[PropagationStep, ...]
    candidates: tuple[CandidateQuality, ...]


# --- reason text -> code (the producers are market_study_state._vwap_study, replay._developing_status and
# replay._quality_as_of; one pattern each) -------------------------------------------------------------------

_PATTERNS = (
    (re.compile(r"^capture began .* after the (anchor|window start)$"), ReasonCode.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR),
    (re.compile(r"^capture interval not recorded"), ReasonCode.CAPTURE_INTERVAL_NOT_RECORDED),
    (re.compile(r"^capture ended .* before the session end$"), ReasonCode.CAPTURE_ENDED_BEFORE_SESSION_END),
    (re.compile(r"^KNOWN_GAP (overlaps|evidence known)"), ReasonCode.KNOWN_GAP),
    (re.compile(r"^SUSPECTED_GAP (overlaps|evidence known)"), ReasonCode.SUSPECTED_GAP),
    (re.compile(r"^ACTIVE_INTERRUPTION since "), ReasonCode.ACTIVE_INTERRUPTION),
    (re.compile(r"^lifecycle \S+ \(not FINALIZED\)$"), ReasonCode.LIFECYCLE_NOT_FINALIZED),
    # dataset-quality context: OVERNIGHT / CASH_PROFILE / OPENING coverage is capture start / end only
    (re.compile(r"^(OVERNIGHT|CASH_PROFILE|OPENING) window not captured through the clock$"),
     ReasonCode.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR),
    (re.compile(r"^capture not started at the knowledge cutoff$"), ReasonCode.CAPTURE_INTERVAL_NOT_RECORDED),
)


def classify_reason(text: str) -> ReasonCode:
    for pattern, code in _PATTERNS:
        if pattern.search(text):
            return code
    return ReasonCode.UNEXPLAINED_UPSTREAM_REASON


def _overlaps(s: datetime, e: datetime, ws: datetime, we: datetime) -> bool:
    return s < we and e > ws


def evidence_window(c: dry.DrysdaleSetupCandidate, bars: tuple[dry.GlobexBar, ...]) -> tuple[int, int]:
    """First and last bar index of the candidate evidence window (see the module docstring)."""
    by_end = {b.end_utc: b.index for b in bars}
    idx = [k.bar_index for k in c.conditions if k.bar_index is not None]
    idx += [e.bar_index for e in c.events]
    for a in c.acceptance:
        idx += [by_end[t] for t in (a.first_bar_end_utc, a.last_bar_end_utc) if t in by_end]
    if c.first_event_utc in by_end:
        idx.append(by_end[c.first_event_utc])
    end = by_end.get(c.completed_at_utc) if c.completed_at_utc is not None else None
    last = end if end is not None else max(idx, default=len(bars) - 1)
    first = max(0, min(idx, default=last) - 1)
    return first, last


def _untraded(bars: tuple[dry.GlobexBar, ...], first: int, last: int) -> list[tuple[datetime, datetime]]:
    return [(bars[i - 1].end_utc, bars[i].start_utc) for i in range(first + 1, last + 1)
            if bars[i].start_utc > bars[i - 1].end_utc]


def _gap_reason(code, s, e, ws, we, anchor, detail) -> QualityReason:
    if _overlaps(s, e, ws, we):
        scope, mat = Scope.SETUP_EVIDENCE_WINDOW, Materiality.LOCAL_EVIDENCE
    elif e <= ws and e > anchor:
        scope, mat = Scope.GLOBEX_VWAP, Materiality.UPSTREAM_REFERENCE
    elif s >= we:
        scope, mat = Scope.GLOBEX_VWAP, Materiality.NOT_A_DEPENDENCY
    else:  # before the anchor: outside the Globex VWAP interval
        scope, mat = Scope.SESSION_BOUNDARY, Materiality.NOT_A_DEPENDENCY
    return QualityReason(code, scope, mat, s, e, e - s, detail)


def candidate_quality(c: dry.DrysdaleSetupCandidate, a: dry.DrysdaleSetupAnalysis, snap) -> CandidateQuality:
    """DRYSDALE_QUALITY_SCOPE_V1 + DRYSDALE_VALIDATION_ELIGIBILITY_V1 for one candidate of `a`."""
    bars, anchor = a.bars, a.bands.anchor_utc
    first, last = evidence_window(c, bars)
    ws, we = bars[first].start_utc, bars[last].end_utc
    d, q = snap.current_dataset, snap.dataset_quality
    reasons: list[QualityReason] = []
    started = d.capture_started_at
    if started is None:
        boundary = BoundaryStatus.NOT_RECORDED
        reasons.append(QualityReason(ReasonCode.CAPTURE_INTERVAL_NOT_RECORDED, Scope.SESSION_BOUNDARY,
                                     Materiality.LOCAL_EVIDENCE, None, None, None,
                                     "capture interval not recorded; coverage of the window cannot be verified"))
    elif started > anchor:
        boundary = BoundaryStatus.NOT_PROVEN
        local = _overlaps(anchor, started, ws, we)
        reasons.append(QualityReason(
            ReasonCode.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR, Scope.SESSION_BOUNDARY,
            Materiality.LOCAL_EVIDENCE if local else Materiality.PROVENANCE, anchor, started, started - anchor,
            f"capture began {started - anchor} after the 17:00 CT Globex anchor; trades in that interval cannot "
            "be ruled out (exact boundary completeness not proven)"))
    else:
        boundary = BoundaryStatus.PROVEN
    if d.capture_ended_at is not None and d.capture_ended_at < we:
        reasons.append(QualityReason(ReasonCode.CAPTURE_ENDED_BEFORE_SESSION_END, Scope.SESSION_BOUNDARY,
                                     Materiality.LOCAL_EVIDENCE, d.capture_ended_at, we, we - d.capture_ended_at,
                                     "capture ended inside the evidence window"))
    for g in q.gaps:
        reasons.append(_gap_reason(ReasonCode(g.evidence_type), g.start_utc, g.end_utc, ws, we, anchor,
                                   f"{g.evidence_type} {mss.encode(g.start_utc)} .. {mss.encode(g.end_utc)}"))
    if q.active_interruption is not None:
        r = _gap_reason(ReasonCode.ACTIVE_INTERRUPTION, q.active_interruption.start_utc,
                        q.active_interruption.end_utc, ws, we, anchor, "disconnected and not reconnected at the "
                        "knowledge cutoff: the last known price may be stale")
        reasons.append(r if r.materiality is Materiality.LOCAL_EVIDENCE else
                       QualityReason(r.code, Scope.CURRENT_STATE, r.materiality, r.interval_start_utc,
                                     r.interval_end_utc, r.duration, r.detail))
    if d.lifecycle_as_of != "FINALIZED" and any(classify_reason(x) is ReasonCode.LIFECYCLE_NOT_FINALIZED
                                                for x in a.reasons):
        reasons.append(QualityReason(ReasonCode.LIFECYCLE_NOT_FINALIZED, Scope.DATASET_LIFECYCLE,
                                     Materiality.PROVENANCE, None, None, None,
                                     f"lifecycle {d.lifecycle_as_of} at the cutoff: final completeness accounting "
                                     "not yet known (not a gap)"))
    for s, e in _untraded(bars, first, last):
        reasons.append(QualityReason(ReasonCode.UNTRADED_INTERVAL, Scope.SETUP_EVIDENCE_WINDOW,
                                     Materiality.LOCAL_EVIDENCE, s, e, e - s,
                                     "no retained trade in this interval; consecutive bars are not adjacent in "
                                     "time (BARS_5M_V1); no gap is inferred"))
    unexplained = [x for x in a.reasons if classify_reason(x) is ReasonCode.UNEXPLAINED_UPSTREAM_REASON]
    for x in unexplained:
        reasons.append(QualityReason(ReasonCode.UNEXPLAINED_UPSTREAM_REASON, Scope.GLOBEX_VWAP,
                                     Materiality.UNKNOWN, None, None, None, x))
    gap_codes = (ReasonCode.KNOWN_GAP, ReasonCode.SUSPECTED_GAP, ReasonCode.ACTIVE_INTERRUPTION)
    gaps = [r for r in reasons if r.code in gap_codes]
    local_bad = [r for r in reasons if r.materiality is Materiality.LOCAL_EVIDENCE]
    eligibility, basis = _eligibility(c, reasons)
    return CandidateQuality(
        c.candidate_id, c.family, c.direction, c.state, c.quality, c.first_event_utc, c.completed_at_utc, ws, we,
        (first, last), boundary, tuple(reasons),
        sum(r.materiality is Materiality.LOCAL_EVIDENCE for r in gaps),
        sum(r.materiality is Materiality.UPSTREAM_REFERENCE for r in gaps),
        sum(r.materiality is Materiality.NOT_A_DEPENDENCY and r.interval_start_utc >= we for r in gaps),
        not local_bad, eligibility, basis)


def _eligibility(c, reasons) -> tuple[Eligibility, tuple[str, ...]]:
    """DRYSDALE_VALIDATION_ELIGIBILITY_V1.

    NOT_A_CANDIDATE       the instance is DEVELOPING (or there is no analysis)
    NOT_ELIGIBLE          a KNOWN_GAP / SUSPECTED_GAP / ACTIVE_INTERRUPTION overlaps the evidence window, the
                          capture interval is not recorded, the capture ended inside the window, or an upstream
                          reason is unexplained: the setup evidence itself is impaired or unverifiable
    ELIGIBLE_QUALITY_QUALIFIED  every other recorded reason that is a dependency (boundary not proven, an
                          upstream gap in the bands' accumulation, lifecycle not yet FINALIZED, an untraded slot)
    ELIGIBLE_UNQUALIFIED  no reason that is a dependency of the candidate
    """
    if c.state not in (dry.CandidateState.CANDIDATE, dry.CandidateState.QUALITY_QUALIFIED):
        return Eligibility.NOT_A_CANDIDATE, (f"state {c.state.value}",)
    blocking = [r for r in reasons if (
        r.code in (ReasonCode.KNOWN_GAP, ReasonCode.SUSPECTED_GAP, ReasonCode.ACTIVE_INTERRUPTION,
                   ReasonCode.CAPTURE_ENDED_BEFORE_SESSION_END) and r.materiality is Materiality.LOCAL_EVIDENCE)
        or r.code in (ReasonCode.CAPTURE_INTERVAL_NOT_RECORDED, ReasonCode.UNEXPLAINED_UPSTREAM_REASON)]
    if blocking:
        return Eligibility.NOT_ELIGIBLE, tuple(f"{r.code.value}/{r.scope.value}/{r.materiality.value}"
                                               for r in blocking)
    qualifying = [r for r in reasons if r.materiality is not Materiality.NOT_A_DEPENDENCY]
    if qualifying:
        return Eligibility.ELIGIBLE_QUALITY_QUALIFIED, tuple(
            f"{r.code.value}/{r.scope.value}/{r.materiality.value}" for r in qualifying)
    return Eligibility.ELIGIBLE_UNQUALIFIED, ()


def propagation(a: dry.DrysdaleSetupAnalysis, snap) -> tuple[PropagationStep, ...]:
    """The dependency chain as it is implemented (DRYSDALE_V1 unchanged), with the quality at each step."""
    vw = next(v for v in snap.vwap if v.anchor_kind.value == "SESSION_OPEN")
    q, d = snap.dataset_quality, snap.current_dataset
    cands = [c for c in a.candidates]
    states = sorted({c.quality for c in cands})
    return (
        PropagationStep("dataset / capture coverage", "capture start, gap intervals, lifecycle (as of the cutoff)",
                        q.status.value, tuple(q.reasons),
                        f"capture_started_at {mss.encode(d.capture_started_at)}; lifecycle {d.lifecycle_as_of}; "
                        f"{len(q.gaps)} gap interval(s) known"),
        PropagationStep("Globex VWAP (snapshot SESSION_OPEN)", "capture start vs anchor; gaps in [anchor, clock); "
                        "lifecycle (window complete) or STOPPED-not-FINALIZED (developing)", vw.status.value,
                        tuple(vw.reasons), f"maturity {vw.maturity.value}"),
        PropagationStep("VWAP_BANDS_GLOBEX_V1 / DRYSDALE_VALUE_AREA_V1", vw.status.value, a.status,
                        a.reasons[:len(vw.reasons)], "analysis.status is the Globex VWAP status unchanged; "
                        "analysis.reasons append the dataset-quality reasons (context, not status-driving)"),
        PropagationStep("BARS_5M_V1 bars and per-bar bands", a.status, "no per-bar quality field", (),
                        "complete bars carry no quality of their own; they read the cumulative bands"),
        PropagationStep("Laboratory V1 conditions", "no per-condition quality field", "ConditionStatus only", (),
                        "conditions read bars only"),
        PropagationStep("DRYSDALE_SETUP_CANDIDATES_V1 candidate", a.status, ",".join(states) or "none", (),
                        "every candidate's quality is the analysis status (the same value for all); a "
                        "candidate with every condition satisfied is QUALITY_QUALIFIED when it is not AVAILABLE"),
    )


def audit(a: dry.DrysdaleSetupAnalysis, snap) -> DrysdaleQualityAudit:
    if snap.cutoff != a.cutoff:
        raise ValueError("the snapshot and the analysis must share one cutoff")
    explained = tuple((x, classify_reason(x).value) for x in a.reasons)
    d = snap.current_dataset
    anchor = a.bands.anchor_utc
    boundary = (BoundaryStatus.NOT_RECORDED if d.capture_started_at is None else
                BoundaryStatus.NOT_PROVEN if d.capture_started_at > anchor else BoundaryStatus.PROVEN)
    return DrysdaleQualityAudit(
        SCHEMA, (SCOPE_POLICY, ELIGIBILITY_POLICY), dry.drysdale_sha256(a), a.cutoff, a.status, a.reasons,
        boundary, d.capture_started_at, anchor, explained, propagation(a, snap),
        tuple(candidate_quality(c, a, snap) for c in a.candidates if a.bars))


def audit_payload(x: DrysdaleQualityAudit) -> dict:
    return mss.encode(x)


def audit_sha256(x: DrysdaleQualityAudit) -> str:
    return hashlib.sha256(mss._dumps(audit_payload(x)).encode("ascii")).hexdigest()


def counts(x: DrysdaleQualityAudit) -> dict[str, int]:
    """Separate counts; never collapsed (validation statistics keep all four)."""
    out = {"total_candidates": 0, **{e.value: 0 for e in Eligibility if e is not Eligibility.NOT_A_CANDIDATE}}
    for c in x.candidates:
        if c.eligibility is not Eligibility.NOT_A_CANDIDATE:
            out["total_candidates"] += 1
            out[c.eligibility.value] += 1
    return out


def render(x: DrysdaleQualityAudit) -> str:
    lines = [f"{SCHEMA} at {mss.encode(x.cutoff.market_time_cutoff_utc)}  analysis {x.analysis_status}",
             f"  Globex boundary {x.boundary_status.value} (capture started {mss.encode(x.capture_started_at)})"]
    for c in x.candidates:
        if c.eligibility is Eligibility.NOT_A_CANDIDATE:
            continue
        lines.append(f"  {c.candidate_id} {c.state.value} -> {c.eligibility.value}")
        for r in c.reasons:
            lines.append(f"    - {r.code.value} [{r.scope.value} / {r.materiality.value}] {r.detail}")
        lines.append(f"    gaps overlapping the evidence window: {c.gaps_overlapping_window}; local evidence "
                     f"complete: {c.local_evidence_complete}")
    return "\n".join(lines)
