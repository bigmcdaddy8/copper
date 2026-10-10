"""OPENING_TYPE_V1: pre-registered, versioned opening-type CANDIDATE policy (0Y-H).

OPENING_TYPE_V1 is a pre-registered Laboratory candidate policy, not an
industry-standard mechanical definition. Every result is a CANDIDATE, never a
trading signal, and the existing research corpus is development evidence only:
validation needs unseen sessions collected after the freeze.

Input: `OpeningPathFacts` (OPENING_PATH_FACTS_V1 over the unchanged
OPENING_AUCTION_FACTS_V1 and OVERNIGHT_CONTEXT_V1 facts). Nothing is recomputed
from the tape except the post-grace observation below.

Policy (every constant below is part of V1; changing any one needs OPENING_TYPE_V2):

  horizon     period A: [cash open print, end of A); A must be 30 minutes.
  grace       60 s after the cash open print (a Laboratory observation scale,
              not from the Market Profile literature, not validated). The grace
              price is the last traded price at or before that instant.
  post-grace observation
              the grace price plus every trade after the grace instant and
              before the end of A.
  cross       the tpo_opening tick-grid definition (strict side change; trades
              at the open tick keep the prior side).

  OPEN_DRIVE                      D1 grace price strictly off the open (its side = direction)
                                  D2 no trade strictly on the other side of the open after the grace instant
                                  D3 the A terminal price is strictly on the grace side
  OPEN_AUCTION_IN_RANGE           R1 the post-grace observation is strictly above AND strictly below the open
  OPEN_AUCTION_OUT_OF_RANGE       R2 at least one open cross after the grace instant
                                  L  open location vs the inclusive prior range: INSIDE / AT_PRIOR_HIGH /
                                     AT_PRIOR_LOW -> IN_RANGE; ABOVE / BELOW -> OUT_OF_RANGE
  OPEN_AUCTION                    R1 + R2 when the prior range is unavailable (location NOT_CLASSIFIED)
  OPEN_TEST_DRIVE                 T1 an exact qualifying reference is reached during A (traded at or through
                                     its exact price; never "within N ticks"). The probe reference is the
                                     first reference reached (ties: fixed reference order).
                                  T2 the reference lies strictly on the probe side of the open
                                  T3 the open is crossed after the reach, before the end of A
                                  T4 a trade strictly on the opposite side of the open at or after that
                                     cross, before the end of A
                                  direction = the post-cross side (opposite to the probe)
  OPEN_REJECTION_REVERSE          DEFERRED (REFERENCE_DEFINITION_CONFLICT)

Candidates are a set: zero, one or several may match. No primary opening type,
no precedence, no composite score, no strength word. See
docs/dicks_laboratory/OPENING_TYPE_V1_POLICY.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.tpo_day_strength import DominantExtension
from dicks_laboratory.tpo_day_structure import QualityGrade
from dicks_laboratory.tpo_opening import (
    OpeningQualityGrade,
    PathPoint,
    RangeLocation,
    Side,
    ValueLocation,
    _sign,
)
from dicks_laboratory.tpo_opening_path import (
    OVERNIGHT_REFERENCE_ORDER,
    PRIOR_REFERENCE_ORDER,
    ContextQuality,
    OpeningPathFacts,
    ReferenceEncounter,
)
from dicks_laboratory.tpo_overnight import OvernightQualityGrade, OvernightRangeLocation

OPENING_TYPE_POLICY_ID = "OPENING_TYPE_V1"
OPENING_TYPE_POLICY_VERSION = "V1_A_PERIOD_60S_GRACE_EXACT_REFERENCE_TEST_PRIOR_RANGE_ANCHOR"
OPENING_TYPE_GRACE = timedelta(seconds=60)  # Laboratory observation scale; not validated
OPENING_TYPE_GRACE_ANCHOR = "CASH_OPEN_PRINT"
OPENING_TYPE_HORIZON = "PERIOD_A"
OPENING_TYPE_HORIZON_MINUTES = 30
REFERENCE_TOUCH_POLICY = "EXACT"  # at or through the exact reference price; no proximity rule
TEST_DRIVE_PROBE_RULE = "FIRST_REFERENCE_REACHED"
TEST_DRIVE_REFERENCES = PRIOR_REFERENCE_ORDER + OVERNIGHT_REFERENCE_ORDER
OPEN_AUCTION_LOCATION_ANCHOR = "PRIOR_RANGE"  # inclusive: the prior high/low belong to the range
IN_RANGE_LOCATIONS = (RangeLocation.INSIDE_PRIOR_RANGE, RangeLocation.AT_PRIOR_HIGH, RangeLocation.AT_PRIOR_LOW)
ORR_DEFERRAL_REASON = "REFERENCE_DEFINITION_CONFLICT"

POLICY_CONSTANTS = (
    ("policy_id", OPENING_TYPE_POLICY_ID),
    ("policy_version", OPENING_TYPE_POLICY_VERSION),
    ("grace_seconds", str(int(OPENING_TYPE_GRACE.total_seconds()))),
    ("grace_anchor", OPENING_TYPE_GRACE_ANCHOR),
    ("horizon", OPENING_TYPE_HORIZON),
    ("horizon_minutes", str(OPENING_TYPE_HORIZON_MINUTES)),
    ("reference_touch_policy", REFERENCE_TOUCH_POLICY),
    ("test_drive_probe_rule", TEST_DRIVE_PROBE_RULE),
    ("test_drive_references", ",".join(TEST_DRIVE_REFERENCES)),
    ("open_auction_location_anchor", OPEN_AUCTION_LOCATION_ANCHOR),
    ("in_range_locations", ",".join(x.value for x in IN_RANGE_LOCATIONS)),
    ("open_rejection_reverse", f"DEFERRED:{ORR_DEFERRAL_REASON}"),
)


class OpeningTypeName(StrEnum):
    OPEN_DRIVE = "OPEN_DRIVE"
    OPEN_AUCTION_IN_RANGE = "OPEN_AUCTION_IN_RANGE"
    OPEN_AUCTION_OUT_OF_RANGE = "OPEN_AUCTION_OUT_OF_RANGE"
    OPEN_AUCTION = "OPEN_AUCTION"  # location NOT_CLASSIFIED (no usable prior range)
    OPEN_TEST_DRIVE = "OPEN_TEST_DRIVE"
    OPEN_REJECTION_REVERSE = "OPEN_REJECTION_REVERSE"


class CandidateResult(StrEnum):
    CANDIDATE = "CANDIDATE"
    NOT_CANDIDATE = "NOT_CANDIDATE"
    NOT_CLASSIFIED = "NOT_CLASSIFIED"  # inputs missing: the rule cannot be evaluated
    NOT_APPLICABLE = "NOT_APPLICABLE"  # generic OPEN_AUCTION when the prior range location is classified
    DEFERRED = "DEFERRED"


class ConditionStatus(StrEnum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"
    NOT_EVALUABLE = "NOT_EVALUABLE"


class ClassificationStatus(StrEnum):
    CLASSIFIED = "CLASSIFIED"  # every rule evaluated (a candidate set, possibly empty)
    NOT_CLASSIFIED = "NOT_CLASSIFIED"


@dataclass(frozen=True)
class OpeningTypeCondition:
    code: str
    description: str
    status: ConditionStatus
    detail: str

    @property
    def satisfied(self) -> bool:
        return self.status is ConditionStatus.SATISFIED


@dataclass(frozen=True)
class GraceObservation:
    """The post-grace observation shared by OPEN_DRIVE and the OPEN_AUCTION family."""

    instant_utc: datetime  # cash open print + grace
    horizon_end_utc: datetime  # end of period A
    price: Decimal  # last traded price at or before the instant
    offset_ticks: int  # price - open
    side: Side  # NONE = exactly at the open
    held_side: Side  # last strict side at or before the instant (cross-definition state)
    traded_above_after: bool  # post-grace observation strictly above the open
    traded_below_after: bool
    first_above_after_utc: datetime | None  # first trade after the instant strictly above the open
    first_below_after_utc: datetime | None
    open_cross_count: int  # crosses after the instant, before the end of A
    first_open_cross_utc: datetime | None
    last_open_cross_utc: datetime | None
    max_up_ticks: int  # beyond the open, over the post-grace observation
    max_down_ticks: int
    a_high: Decimal
    a_low: Decimal
    a_terminal_price: Decimal  # last traded price before the end of A
    a_terminal_offset_ticks: int
    a_terminal_side: Side


@dataclass(frozen=True)
class TestDriveEvidence:
    __test__ = False  # not a pytest class

    reference: str | None  # the probe reference (first reached); None when none is reached
    reference_source: str | None  # PRIOR_DAY or OVERNIGHT
    reference_price: Decimal | None
    reached_utc: datetime | None
    exact_touch_utc: datetime | None  # first trade exactly at the reference (None = traded through only)
    reach_beyond_ticks: int | None
    probe_side: Side | None
    open_to_reference_ticks: int | None  # reference - open (signed)
    open_to_reference_points: Decimal | None
    open_cross_after_reach_utc: datetime | None  # inside A only
    reach_to_cross: timedelta | None
    opposite_excursion_after_cross_ticks: int | None  # beyond the open, [cross, end of A)
    opposite_excursion_after_cross_points: Decimal | None
    a_terminal_offset_ticks: int
    a_terminal_side: Side
    other_references_reached: tuple[tuple[str, datetime], ...]  # in A, excluding the probe reference
    minimum_reference_distance_ticks: int | None  # over every qualifying reference, during A
    minimum_reference_distance_reference: str | None


@dataclass(frozen=True)
class OpeningTypeCandidate:
    type: OpeningTypeName
    direction: Side | None  # UP / DOWN; None where the type has no direction
    result: CandidateResult
    quality: OpeningQualityGrade  # UNQUALIFIED / QUALITY_QUALIFIED; NOT_AVAILABLE when NOT_CLASSIFIED
    quality_reasons: tuple[str, ...]
    conditions: tuple[OpeningTypeCondition, ...]
    reasons: tuple[str, ...]  # why NOT_CLASSIFIED / NOT_APPLICABLE / DEFERRED
    evidence: GraceObservation | TestDriveEvidence | None
    policy_id: str = OPENING_TYPE_POLICY_ID

    @property
    def matched(self) -> bool:
        return self.result is CandidateResult.CANDIDATE


@dataclass(frozen=True)
class WindowStrength:
    """Continuous facts at one opening horizon (from OPENING_PATH_FACTS_V1 scales)."""

    minutes: int
    excursion_up_ticks: int
    excursion_down_ticks: int
    dominant: DominantExtension
    counter_to_dominant: Decimal | None
    open_cross_count: int
    last_open_cross_utc: datetime | None
    longest_up_residence: timedelta | None
    longest_down_residence: timedelta | None


@dataclass(frozen=True)
class OpeningStrengthFacts:
    """Continuous facts printed beside every candidate. Never a score; never a condition."""

    windows: tuple[WindowStrength, ...]  # 5 / 15 / 30 minutes
    ab_overlap_ratio: Decimal | None
    opening_higher_low_run: int
    opening_lower_high_run: int
    first_reference_reached: str | None
    first_reference_reached_utc: datetime | None
    range_location: RangeLocation | None  # None without a usable prior context
    value_location: ValueLocation | None
    overnight_location: OvernightRangeLocation | None
    open_percentile_in_overnight_range: Decimal | None
    overnight_range_ticks: int | None


@dataclass(frozen=True)
class OpeningTypeClassification:
    policy_id: str
    policy_version: str
    policy_constants: tuple[tuple[str, str], ...]
    status: ClassificationStatus
    reasons: tuple[str, ...]
    quality: ContextQuality  # CURRENT_OPEN / PRIOR_DAY / OVERNIGHT, never merged
    candidates: tuple[OpeningTypeCandidate, ...]  # every evaluation, in fixed type order
    strength: OpeningStrengthFacts | None
    facts: OpeningPathFacts

    @property
    def matched(self) -> tuple[OpeningTypeCandidate, ...]:
        return tuple(c for c in self.candidates if c.matched)

    @property
    def matched_types(self) -> tuple[OpeningTypeName, ...]:
        return tuple(c.type for c in self.matched)

    def candidate(self, name: OpeningTypeName | str) -> OpeningTypeCandidate:
        return next(c for c in self.candidates if c.type == name)


# --- classification ----------------------------------------------------------------------------

def classify_opening_type(facts: OpeningPathFacts) -> OpeningTypeClassification:
    s = facts.opening.session
    base = dict(policy_id=OPENING_TYPE_POLICY_ID, policy_version=OPENING_TYPE_POLICY_VERSION,
                policy_constants=POLICY_CONSTANTS, quality=facts.quality, facts=facts)
    blockers = []
    if not s.available:
        blockers.append("opening facts NOT_AVAILABLE: " + "; ".join(s.quality.reasons))
    elif s.a_end_utc - s.cash_open.cash_open_utc != timedelta(minutes=OPENING_TYPE_HORIZON_MINUTES):
        blockers.append(f"period A is not {OPENING_TYPE_HORIZON_MINUTES} minutes (V1 is defined on 30-minute A)")
    if blockers:
        reasons = tuple(blockers)
        out = tuple(_not_classified(t, reasons) for t in OpeningTypeName if t is not OpeningTypeName.OPEN_REJECTION_REVERSE)
        return OpeningTypeClassification(**base, status=ClassificationStatus.NOT_CLASSIFIED, reasons=reasons,
                                         candidates=out + (_orr(),), strength=None)
    obs = _observe(s.path, s.cash_open.timestamp_utc + OPENING_TYPE_GRACE, s.a_end_utc)
    candidates = (_drive(facts, obs), *_auctions(facts, obs), _test_drive(facts, obs), _orr())
    return OpeningTypeClassification(**base, status=ClassificationStatus.CLASSIFIED, reasons=(),
                                     candidates=candidates, strength=_strength(facts))


def _side(sign: int) -> Side:
    return Side.UP if sign > 0 else Side.DOWN if sign < 0 else Side.NONE


def _observe(path: tuple[PathPoint, ...], instant: datetime, a_end: datetime) -> GraceObservation:
    o = path[0].tick
    upto = [p for p in path if p.timestamp_utc <= instant]
    cur = upto[-1]
    held = next((_sign(p.tick - o) for p in reversed(upto) if p.tick != o), 0)
    after = [p for p in path if instant < p.timestamp_utc < a_end]
    seen = [cur] + after
    crosses, state = [], held
    for p in after:
        sign = _sign(p.tick - o)
        if sign == 0:
            continue
        if state and sign != state:
            crosses.append(p.timestamp_utc)
        state = sign
    in_a = [p for p in path if p.timestamp_utc < a_end]
    terminal = in_a[-1]
    return GraceObservation(
        instant_utc=instant, horizon_end_utc=a_end, price=cur.price, offset_ticks=cur.tick - o,
        side=_side(cur.tick - o), held_side=_side(held),
        traded_above_after=any(p.tick > o for p in seen), traded_below_after=any(p.tick < o for p in seen),
        first_above_after_utc=next((p.timestamp_utc for p in after if p.tick > o), None),
        first_below_after_utc=next((p.timestamp_utc for p in after if p.tick < o), None),
        open_cross_count=len(crosses), first_open_cross_utc=crosses[0] if crosses else None,
        last_open_cross_utc=crosses[-1] if crosses else None,
        max_up_ticks=max(0, max(p.tick - o for p in seen)), max_down_ticks=max(0, max(o - p.tick for p in seen)),
        a_high=max(in_a, key=lambda p: p.tick).price, a_low=min(in_a, key=lambda p: p.tick).price,
        a_terminal_price=terminal.price, a_terminal_offset_ticks=terminal.tick - o,
        a_terminal_side=_side(terminal.tick - o))


def _t(ts: datetime | None) -> str:
    return "--" if ts is None else ts.strftime("%H:%M:%S.%f")[:-3] + "Z"


def _cond(code: str, description: str, ok: bool | None, detail: str) -> OpeningTypeCondition:
    status = (ConditionStatus.NOT_EVALUABLE if ok is None else
              ConditionStatus.SATISFIED if ok else ConditionStatus.NOT_SATISFIED)
    return OpeningTypeCondition(code, description, status, detail)


def _open_quality(q: ContextQuality) -> tuple[bool, list[str]]:
    if q.current_open is OpeningQualityGrade.QUALITY_QUALIFIED:
        return True, [f"current open: {r}" for r in q.current_open_reasons]
    return False, []


def _prior_quality(q: ContextQuality) -> tuple[bool, list[str]]:
    if q.prior_day_quality is not None and q.prior_day_quality is not QualityGrade.UNQUALIFIED:
        return True, [f"prior day {q.prior_day_quality.value}: {r}" for r in q.prior_day_reasons] or [
            f"prior day {q.prior_day_quality.value}"]
    return False, []


def _overnight_quality(q: ContextQuality) -> tuple[bool, list[str]]:
    if q.overnight is OvernightQualityGrade.QUALITY_QUALIFIED:
        return True, [f"overnight: {r}" for r in q.overnight_reasons]
    return False, []


def _grade(*parts: tuple[bool, list[str]]) -> tuple[OpeningQualityGrade, tuple[str, ...]]:
    """Dependency-aware: only the inputs a candidate's conditions read are combined."""
    reasons = [r for _, rs in parts for r in rs]
    qualified = any(flag for flag, _ in parts)
    return (OpeningQualityGrade.QUALITY_QUALIFIED if qualified else OpeningQualityGrade.UNQUALIFIED), tuple(reasons)


def _result(conditions) -> CandidateResult:
    return CandidateResult.CANDIDATE if all(c.satisfied for c in conditions) else CandidateResult.NOT_CANDIDATE


def _not_classified(name: OpeningTypeName, reasons: tuple[str, ...]) -> OpeningTypeCandidate:
    return OpeningTypeCandidate(name, None, CandidateResult.NOT_CLASSIFIED, OpeningQualityGrade.NOT_AVAILABLE, (), (),
                                reasons, None)


def _orr() -> OpeningTypeCandidate:
    return OpeningTypeCandidate(
        OpeningTypeName.OPEN_REJECTION_REVERSE, None, CandidateResult.DEFERRED, OpeningQualityGrade.NOT_AVAILABLE, (),
        (), (f"{ORR_DEFERRAL_REASON}: sources disagree on whether a reference must be reached, how large the initial "
             "run must be, and what distinguishes it from Open Test Drive",), None)


def _drive(f: OpeningPathFacts, obs: GraceObservation) -> OpeningTypeCandidate:
    g = int(OPENING_TYPE_GRACE.total_seconds())
    side = obs.side
    d1 = _cond("D1_GRACE_PRICE_OFF_OPEN", f"price at +{g} s is strictly above or below the cash open",
               side is not Side.NONE,
               f"price at {_t(obs.instant_utc)} = {obs.price} ({obs.offset_ticks:+d} ticks): "
               + ("exactly at the open" if side is Side.NONE else side.value))
    if side is Side.NONE:
        d2 = _cond("D2_NO_POST_GRACE_OPEN_CROSS", "no later trade on the other side of the open through the end of A",
                   None, "no grace side to hold (price at the open at the grace instant)")
        d3 = _cond("D3_A_TERMINAL_ON_GRACE_SIDE", "the A terminal price is on the grace side of the open", None,
                   f"no grace side; A terminal {obs.a_terminal_price} ({obs.a_terminal_offset_ticks:+d} ticks)")
    else:
        other = obs.first_below_after_utc if side is Side.UP else obs.first_above_after_utc
        d2 = _cond("D2_NO_POST_GRACE_OPEN_CROSS", "no later trade on the other side of the open through the end of A",
                   other is None,
                   "no trade strictly " + ("below" if side is Side.UP else "above") + f" the open to {_t(obs.horizon_end_utc)}"
                   if other is None else
                   f"first cross {_t(other)}; {obs.open_cross_count} post-grace crosses, last {_t(obs.last_open_cross_utc)}")
        d3 = _cond("D3_A_TERMINAL_ON_GRACE_SIDE", "the A terminal price is on the grace side of the open",
                   obs.a_terminal_side is side,
                   f"A terminal {obs.a_terminal_price} ({obs.a_terminal_offset_ticks:+d} ticks): {obs.a_terminal_side.value}")
    conditions = (d1, d2, d3)
    result = _result(conditions)
    grade, reasons = _grade(_open_quality(f.quality))
    return OpeningTypeCandidate(OpeningTypeName.OPEN_DRIVE, side if result is CandidateResult.CANDIDATE else None,
                                result, grade, reasons, conditions, (), obs)


def _rotation(obs: GraceObservation) -> tuple[OpeningTypeCondition, OpeningTypeCondition]:
    g = int(OPENING_TYPE_GRACE.total_seconds())
    both = obs.traded_above_after and obs.traded_below_after
    r1 = _cond("R1_BOTH_SIDES_AFTER_GRACE", f"from +{g} s to the end of A price is strictly above and strictly below "
               "the open", both,
               f"above: {'yes' if obs.traded_above_after else 'no'} (max {obs.max_up_ticks} ticks), below: "
               f"{'yes' if obs.traded_below_after else 'no'} (max {obs.max_down_ticks} ticks)")
    r2 = _cond("R2_POST_GRACE_OPEN_CROSS", f"at least one strict open cross after +{g} s, before the end of A",
               obs.open_cross_count >= 1,
               f"{obs.open_cross_count} post-grace crosses; first {_t(obs.first_open_cross_utc)}, last "
               f"{_t(obs.last_open_cross_utc)}")
    return r1, r2


def _auctions(f: OpeningPathFacts, obs: GraceObservation) -> tuple[OpeningTypeCandidate, ...]:
    r1, r2 = _rotation(obs)
    op = f.opening
    open_q = _open_quality(f.quality)
    out = []
    if op.range_location is None:
        why = (f"IN_RANGE / OUT_OF_RANGE: NOT_CLASSIFIED -- prior context {op.outcome.value}; no prior range",)
        for name in (OpeningTypeName.OPEN_AUCTION_IN_RANGE, OpeningTypeName.OPEN_AUCTION_OUT_OF_RANGE):
            loc = _cond("L_PRIOR_RANGE_LOCATION", "open location vs the inclusive prior range", None,
                        f"prior context {op.outcome.value}")
            out.append(OpeningTypeCandidate(name, None, CandidateResult.NOT_CLASSIFIED, OpeningQualityGrade.NOT_AVAILABLE,
                                            (), (r1, r2, loc), why, obs))
        loc = _cond("L_PRIOR_RANGE_UNAVAILABLE", "no usable prior range (location NOT_CLASSIFIED)", True,
                    f"prior context {op.outcome.value}")
        conditions = (r1, r2, loc)
        grade, reasons = _grade(open_q)
        out.append(OpeningTypeCandidate(OpeningTypeName.OPEN_AUCTION, None, _result(conditions), grade, reasons,
                                        conditions, (), obs))
        return tuple(out)
    location = op.range_location
    inside = location in IN_RANGE_LOCATIONS
    detail = (f"open {op.session.cash_open.price} {location.value} (prior range {op.prior.profile_low}-"
              f"{op.prior.profile_high}; open - high {op.open_vs_prior_high_ticks} ticks, open - low "
              f"{op.open_vs_prior_low_ticks} ticks)")
    grade, reasons = _grade(open_q, _prior_quality(f.quality))
    for name, ok, text in ((OpeningTypeName.OPEN_AUCTION_IN_RANGE, inside,
                            "open inside the inclusive prior range (AT_PRIOR_HIGH / AT_PRIOR_LOW count as inside)"),
                           (OpeningTypeName.OPEN_AUCTION_OUT_OF_RANGE, not inside,
                            "open strictly above the prior high or strictly below the prior low")):
        conditions = (r1, r2, _cond("L_PRIOR_RANGE_LOCATION", text, ok, detail))
        out.append(OpeningTypeCandidate(name, None, _result(conditions), grade, reasons, conditions, (), obs))
    out.append(OpeningTypeCandidate(OpeningTypeName.OPEN_AUCTION, None, CandidateResult.NOT_APPLICABLE,
                                    grade, reasons, (), ("prior range location classified: see "
                                                         "OPEN_AUCTION_IN_RANGE / OPEN_AUCTION_OUT_OF_RANGE",), obs))
    return tuple(out)


def _source(reference: str) -> str:
    return "OVERNIGHT" if reference in OVERNIGHT_REFERENCE_ORDER else "PRIOR_DAY"


def _test_drive(f: OpeningPathFacts, obs: GraceObservation) -> OpeningTypeCandidate:
    s = f.opening.session
    a_end, inc, o = s.a_end_utc, s.price_increment, s.path[0].tick
    encounters = [e for e in f.encounters if e.reference in TEST_DRIVE_REFERENCES]
    name = OpeningTypeName.OPEN_TEST_DRIVE
    if not encounters:
        why = (f"no qualifying reference: prior context {f.quality.prior_day_outcome.value}; overnight "
               f"{f.quality.overnight.value if f.quality.overnight else 'NOT_BUILT'}",)
        return OpeningTypeCandidate(name, None, CandidateResult.NOT_CLASSIFIED, OpeningQualityGrade.NOT_AVAILABLE, (),
                                    (), why, None)
    in_a = [e for e in encounters if e.reached_utc is not None and e.side_of_open is not Side.NONE
            and e.reached_utc < a_end]
    probe: ReferenceEncounter | None = min(in_a, key=lambda e: e.reached_utc, default=None)  # stable: fixed order
    off_open = [e for e in encounters if e.side_of_open is not Side.NONE]
    closest = min(off_open, key=lambda e: e.min_distance_ticks, default=None)
    others = tuple((e.reference, e.reached_utc) for e in in_a if e is not probe)
    common = dict(a_terminal_offset_ticks=obs.a_terminal_offset_ticks, a_terminal_side=obs.a_terminal_side,
                  other_references_reached=others,
                  minimum_reference_distance_ticks=closest.min_distance_ticks if closest else None,
                  minimum_reference_distance_reference=closest.reference if closest else None)
    prior_used = any(_source(e.reference) == "PRIOR_DAY" for e in encounters)
    if probe is None:
        distances = ", ".join(f"{e.reference} {e.min_distance_ticks}" for e in off_open) or "none off the open tick"
        t1 = _cond("T1_EXACT_REFERENCE_REACHED_IN_A", "an exact qualifying reference is reached during A (at or "
                   "through its price; no proximity rule)", False,
                   f"no reference reached before {_t(a_end)}; minimum distance (ticks): {distances}")
        rest = tuple(_cond(code, text, None, "no reference reached") for code, text in _TD_LATER)
        conditions = (t1,) + rest
        evidence = TestDriveEvidence(None, None, None, None, None, None, None, None, None, None, None, None, None,
                                     **common)
        grade, reasons = _grade(_open_quality(f.quality), _prior_quality(f.quality) if prior_used else (False, []))
        return OpeningTypeCandidate(name, None, CandidateResult.NOT_CANDIDATE, grade, reasons, conditions, (), evidence)
    sign = 1 if probe.side_of_open is Side.UP else -1
    cross = probe.first_open_cross_after_utc
    cross = cross if cross is not None and cross < a_end else None
    opposite = None
    if cross is not None:
        window = [p for p in s.path if cross <= p.timestamp_utc < a_end]
        opposite = max(0, max(-sign * (p.tick - o) for p in window))
    ref_ticks = -probe.open_offset_ticks  # reference - open
    t1 = _cond("T1_EXACT_REFERENCE_REACHED_IN_A", "an exact qualifying reference is reached during A (at or through "
               "its price; no proximity rule)", True,
               f"{probe.reference} {probe.price} reached {_t(probe.reached_utc)} ("
               + ("exact touch" if probe.reach_beyond_ticks == 0 else f"traded through by {probe.reach_beyond_ticks} ticks")
               + "); first reference reached")
    t2 = _cond("T2_REFERENCE_ON_PROBE_SIDE", "the reference lies on the probe side of the open", True,
               f"{probe.reference} is {ref_ticks:+d} ticks from the open: probe {probe.side_of_open.value}")
    t3 = _cond("T3_OPEN_CROSSED_AFTER_REACH_IN_A", "price crosses the cash open after the reach, before the end of A",
               cross is not None,
               f"first cross {_t(cross)} (+{(cross - probe.reached_utc).total_seconds():.3f} s after the reach)"
               if cross is not None else
               "no open cross before the end of A" + (f" (first cross after A at {_t(probe.first_open_cross_after_utc)})"
                                                     if probe.first_open_cross_after_utc else ""))
    if cross is None:
        t4 = _cond("T4_OPPOSITE_SIDE_AFTER_CROSS_IN_A", "after that cross price trades strictly on the opposite side "
                   "of the open before the end of A", None, "no open cross in A")
    else:
        t4 = _cond("T4_OPPOSITE_SIDE_AFTER_CROSS_IN_A", "after that cross price trades strictly on the opposite side "
                   "of the open before the end of A", opposite >= 1,
                   f"max {opposite} ticks beyond the open on the {_side(-sign).value} side to {_t(a_end)}")
    conditions = (t1, t2, t3, t4)
    result = _result(conditions)
    evidence = TestDriveEvidence(
        reference=probe.reference, reference_source=_source(probe.reference), reference_price=probe.price,
        reached_utc=probe.reached_utc, exact_touch_utc=probe.first_touch_utc, reach_beyond_ticks=probe.reach_beyond_ticks,
        probe_side=probe.side_of_open, open_to_reference_ticks=ref_ticks, open_to_reference_points=ref_ticks * inc,
        open_cross_after_reach_utc=cross, reach_to_cross=None if cross is None else cross - probe.reached_utc,
        opposite_excursion_after_cross_ticks=opposite,
        opposite_excursion_after_cross_points=None if opposite is None else opposite * inc, **common)
    ref_q = _overnight_quality(f.quality) if _source(probe.reference) == "OVERNIGHT" else _prior_quality(f.quality)
    grade, reasons = _grade(_open_quality(f.quality), ref_q)
    return OpeningTypeCandidate(name, _side(-sign) if result is CandidateResult.CANDIDATE else None, result, grade,
                                reasons, conditions, (), evidence)


_TD_LATER = (
    ("T2_REFERENCE_ON_PROBE_SIDE", "the reference lies on the probe side of the open"),
    ("T3_OPEN_CROSSED_AFTER_REACH_IN_A", "price crosses the cash open after the reach, before the end of A"),
    ("T4_OPPOSITE_SIDE_AFTER_CROSS_IN_A", "after that cross price trades strictly on the opposite side of the open "
     "before the end of A"),
)


def _strength(f: OpeningPathFacts) -> OpeningStrengthFacts:
    windows = []
    for minutes in (5, 15, 30):
        x = f.scale(minutes * 60)
        windows.append(WindowStrength(minutes, x.excursion_up_ticks, x.excursion_down_ticks, x.dominant,
                                      x.counter_to_dominant, x.open_cross_count, x.last_open_cross_utc,
                                      x.longest_up_residence, x.longest_down_residence))
    s, op, on = f.opening.session, f.opening, f.overnight
    first = f.first_reference_reached
    on_available = on is not None and on.session.available
    return OpeningStrengthFacts(
        windows=tuple(windows), ab_overlap_ratio=s.early_tpo.ab_overlap_ratio,
        opening_higher_low_run=s.one_timeframing.opening_higher_low_run,
        opening_lower_high_run=s.one_timeframing.opening_lower_high_run,
        first_reference_reached=first.reference if first else None,
        first_reference_reached_utc=first.reached_utc if first else None,
        range_location=op.range_location, value_location=op.value_location,
        overnight_location=on.open_location if on is not None else None,
        open_percentile_in_overnight_range=on.open_percentile_in_overnight_range if on is not None else None,
        overnight_range_ticks=on.session.range_ticks if on_available else None)


# --- text rendering ----------------------------------------------------------------------------

def _r(value: Decimal | None) -> str:
    return "undefined" if value is None else str(value.quantize(Decimal("0.0001")))


def _d(td: timedelta | None) -> str:
    return "--" if td is None else f"{td.total_seconds():.3f}s"


_MARK = {ConditionStatus.SATISFIED: "[satisfied]    ", ConditionStatus.NOT_SATISFIED: "[NOT satisfied]",
         ConditionStatus.NOT_EVALUABLE: "[not evaluable]"}


def render_opening_types(c: OpeningTypeClassification) -> list[str]:
    """Why each candidate matched or failed. Candidate taxonomy only: no bias, signal or trade language."""
    q = c.quality
    lines = ["OPENING-TYPE CANDIDATES:",
             f"  Policy: {c.policy_id} ({c.policy_version})",
             "  Pre-registered Laboratory candidate policy, not an industry-standard mechanical definition.",
             "  Constants: " + "; ".join(f"{k}={v}" for k, v in c.policy_constants[2:]),
             f"  Quality inputs (kept separate): CURRENT_OPEN {q.current_open.value}; PRIOR_DAY "
             f"{q.prior_day_outcome.value}" + (f" / {q.prior_day_quality.value}" if q.prior_day_quality else "")
             + f"; OVERNIGHT {q.overnight.value if q.overnight else 'NOT_BUILT'}"]
    if c.status is ClassificationStatus.NOT_CLASSIFIED:
        lines.append("  OPENING TYPE: NOT_CLASSIFIED")
        lines += [f"    - {r}" for r in c.reasons]
        lines += ["  OPEN_REJECTION_REVERSE: DEFERRED -- " + ORR_DEFERRAL_REASON, ""]
        return lines
    matched = c.matched
    lines.append("  Matched candidates: " + (", ".join(
        m.type.value + (f" {m.direction.value}" if m.direction else "")
        + (" (QUALITY_QUALIFIED)" if m.quality is OpeningQualityGrade.QUALITY_QUALIFIED else "") for m in matched)
        if matched else "none") + f"   ({len(matched)} matched; candidate set -- no primary type)")
    for cand in c.candidates:
        lines.append("")
        if cand.result is CandidateResult.DEFERRED:
            lines.append(f"  {cand.type.value}")
            lines.append(f"    DEFERRED -- {cand.reasons[0]}")
            continue
        lines.append(f"  {cand.type.value}")
        for cond in cand.conditions:
            lines.append(f"    {_MARK[cond.status]} {cond.description}")
            lines.append(f"                    {cond.detail}")
        lines += [f"    {r}" for r in cand.reasons]
        result = cand.result.value + (f" {cand.direction.value}" if cand.direction else "")
        lines.append(f"    Result: {result}"
                     + ("" if cand.result in (CandidateResult.NOT_CLASSIFIED,) else f"   quality {cand.quality.value}"))
        lines += [f"      - {r}" for r in cand.quality_reasons]
        ev = cand.evidence
        if isinstance(ev, TestDriveEvidence):
            if ev.reference is not None:
                lines.append(f"    Evidence: {ev.reference} ({ev.reference_source}) {ev.reference_price}; reached "
                             f"{_t(ev.reached_utc)}; exact touch {_t(ev.exact_touch_utc)}; probe side "
                             f"{ev.probe_side.value}; open->reference {ev.open_to_reference_ticks:+d} ticks "
                             f"({ev.open_to_reference_points} pts); reach->cross {_d(ev.reach_to_cross)}; opposite "
                             f"excursion after cross in A "
                             + ("--" if ev.opposite_excursion_after_cross_ticks is None else
                                f"{ev.opposite_excursion_after_cross_ticks} ticks "
                                f"({ev.opposite_excursion_after_cross_points} pts)")
                             + f"; A terminal {ev.a_terminal_offset_ticks:+d} ticks ({ev.a_terminal_side.value})")
            others = ", ".join(f"{n} {_t(t)}" for n, t in ev.other_references_reached) or "none"
            lines.append(f"    Other references reached in A: {others}; minimum reference distance "
                         + ("--" if ev.minimum_reference_distance_ticks is None else
                            f"{ev.minimum_reference_distance_ticks} ticks ({ev.minimum_reference_distance_reference})"))
    obs = next((x.evidence for x in c.candidates if isinstance(x.evidence, GraceObservation)), None)
    if obs is not None:
        lines += ["", f"  Post-grace observation (+{int(OPENING_TYPE_GRACE.total_seconds())} s = "
                  f"{_t(obs.instant_utc)} to end of A {_t(obs.horizon_end_utc)}):",
                  f"    grace price {obs.price} ({obs.offset_ticks:+d} ticks, side {obs.side.value}, held "
                      f"{obs.held_side.value}); post-grace crosses {obs.open_cross_count} (last "
                  f"{_t(obs.last_open_cross_utc)}); max up {obs.max_up_ticks} / down {obs.max_down_ticks} ticks",
                  f"    A high {obs.a_high} low {obs.a_low} terminal {obs.a_terminal_price} "
                  f"({obs.a_terminal_offset_ticks:+d} ticks, {obs.a_terminal_side.value})"]
    st = c.strength
    lines += ["", "  Continuous facts beside every candidate (evidence only; not conditions, not a score):"]
    for w in st.windows:
        lines.append(f"    {w.minutes:>2}m  up {w.excursion_up_ticks} / down {w.excursion_down_ticks} ticks "
                     f"({w.dominant.value}, counter/dominant {_r(w.counter_to_dominant)}); open crosses "
                     f"{w.open_cross_count}, last {_t(w.last_open_cross_utc)}; longest residence up "
                     f"{_d(w.longest_up_residence)} / down {_d(w.longest_down_residence)}")
    lines.append(f"    A/B overlap {_r(st.ab_overlap_ratio)}; one-timeframing run from A: higher lows "
                 f"{st.opening_higher_low_run}, lower highs {st.opening_lower_high_run}; first reference reached "
                 f"{st.first_reference_reached or 'none'} {_t(st.first_reference_reached_utc)}")
    lines.append("    open vs prior: " + (f"{st.range_location.value}; {st.value_location.value}"
                                          if st.range_location else "not available")
                 + "; open vs overnight: " + (f"{st.overnight_location.value}, percentile "
                                              f"{_r(st.open_percentile_in_overnight_range)}, overnight range "
                                              f"{st.overnight_range_ticks} ticks" if st.overnight_location else
                                              "not available"))
    lines += ["  Candidates are descriptive taxonomy only: not a bias and not a signal.", ""]
    return lines
