"""Multi-scale opening path, reference encounters and probe/reversal facts (0Y-G).

Derived from an accepted `OpeningAuctionFacts` (OPENING_AUCTION_FACTS_V1, unchanged)
and an `OvernightContext` (OVERNIGHT_CONTEXT_V1):

  OpeningScaleFacts      the open's path at fixed observational horizons
                         (30 s .. 60 min): excursions, dominance, open crossings,
                         last cross, time above/below/at the open, longest
                         uninterrupted residence on each side.
  GraceDiagnostic        DIAGNOSTIC ONLY: the price and side at 1/5/15/30/60 s
                         after the open print, and what followed.
  ReferenceEncounter     per prior/overnight reference: first reach (touch or
                         trade beyond), whether the open was crossed afterwards,
                         and the opposite-side excursion after that cross.
  OpeningReferenceSequence  the first 30 minutes as an ordered, deduplicated list
                         of deterministic events.
  OpeningPathFacts       all of the above with CURRENT_OPEN / PRIOR_DAY /
                         OVERNIGHT quality kept separate.

OpeningScaleFacts != Open Drive. GraceDiagnostic is not a grace policy.
OpeningProbeFacts (ReferenceEncounter) != Open Test Drive. No scale, grace period,
"near" distance or tolerance is chosen; no opening type is named. Tick-grid touch /
cross definitions are those of tpo_opening. See TPO_MARKET_PROFILE_0YA.md §57-§63.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.tpo_day_strength import DominantExtension
from dicks_laboratory.tpo_day_structure import QualityGrade
from dicks_laboratory.tpo_opening import (
    ContextOutcome,
    OpeningAuctionFacts,
    OpeningQualityGrade,
    PathPoint,
    ReferenceInteraction,
    Side,
    _crossings,
    _dominance,
    _interactions,
    _ratio,
    _sign,
)
from dicks_laboratory.tpo_overnight import OvernightContext, OvernightQualityGrade

OPENING_PATH_POLICY_ID = "OPENING_PATH_FACTS_V1"
# Fixed observational horizons from 08:30:00 CT (3600 s repeats the accepted 60-minute window).
OPENING_SCALE_SECONDS = (30, 60, 180, 300, 900, 1800, 3600)
# DIAGNOSTIC ONLY: candidate instants after the open print; none is preferred.
GRACE_SECONDS = (1, 5, 15, 30, 60)
GRACE_HORIZON_MINUTES = (5, 15, 30)  # opening windows [08:30, 08:30+N)
SEQUENCE_MINUTES = 30
PROBE_REACH_MINUTES = 30  # references reached in [08:30, 09:00)
PROBE_AFTER_CROSS_MINUTES = (5, 15, 30)  # windows [cross, cross+N)
PRIOR_REFERENCE_ORDER = ("PRIOR_HIGH", "PRIOR_VAH", "PRIOR_POC", "PRIOR_VAL", "PRIOR_LOW")
OVERNIGHT_REFERENCE_ORDER = ("OVERNIGHT_HIGH", "OVERNIGHT_LOW")


class EventKind(StrEnum):
    OPEN = "OPEN"
    OPEN_CROSS_FIRST = "OPEN_CROSS_FIRST"
    OPEN_CROSS_LAST = "OPEN_CROSS_LAST"  # only when different from the first
    REFERENCE_TOUCH = "REFERENCE_TOUCH"  # first trade exactly at the reference
    REFERENCE_CROSS = "REFERENCE_CROSS"  # first strict side change through the reference
    WINDOW_HIGH_FIRST_REACHED = "WINDOW_HIGH_FIRST_REACHED"
    WINDOW_LOW_FIRST_REACHED = "WINDOW_LOW_FIRST_REACHED"


_EVENT_ORDER = tuple(EventKind)


@dataclass(frozen=True)
class OpeningScaleFacts:
    """[08:30, 08:30 + horizon) from the open print. A residence is the time between strict sides
    changes (a cross): it starts at the first trade strictly on that side and lasts to the next
    cross or the horizon end; trades at the open inside a residence do not interrupt it."""

    horizon_seconds: int
    end_utc: datetime
    high: Decimal
    low: Decimal
    last_price: Decimal
    excursion_up_ticks: int
    excursion_down_ticks: int
    dominant: DominantExtension
    counter_to_dominant: Decimal | None  # smaller / larger; None when both 0
    open_cross_count: int
    first_open_cross_utc: datetime | None
    last_open_cross_utc: datetime | None
    open_to_last_cross: timedelta | None  # last cross - open print
    seconds_above_open: Decimal  # last-traded-price time strictly above the open tick
    seconds_below_open: Decimal
    seconds_at_open: Decimal
    seconds_observed: Decimal  # open print to horizon end
    longest_up_residence: timedelta | None
    longest_up_residence_start_utc: datetime | None
    longest_down_residence: timedelta | None
    longest_down_residence_start_utc: datetime | None


@dataclass(frozen=True)
class GraceHorizon:
    minutes: int  # opening window [08:30, 08:30+N)
    applicable: bool  # False when the grace instant is not before the window end
    crossed_open: bool  # a later trade strictly on the side opposite to the held side
    first_cross_utc: datetime | None
    max_favorable_ticks: int | None  # beyond the open on the held side, from the grace instant on
    max_counter_ticks: int | None  # beyond the open on the other side


@dataclass(frozen=True)
class GraceDiagnostic:
    """DIAGNOSTIC ONLY -- not a grace-period policy."""

    grace_seconds: int
    instant_utc: datetime  # open print + grace
    price: Decimal  # last traded price at or before the instant
    offset_ticks: int  # price - open
    side: Side  # where that price is: UP / DOWN / NONE (= at the open)
    held_side: Side  # strict side held under the cross definition (last off-open trade); NONE if none yet
    horizons: tuple[GraceHorizon, ...]


@dataclass(frozen=True)
class ReferenceEncounter:
    """OpeningProbeFacts for one reference. Never an 'Open Test Drive'.

    reached = the first trade at the reference or beyond it, coming from the open's side
    (a price jump over a reference reaches it without an exact touch). The open crossing
    after the reach is a trade strictly on the opposite side of the open from the reference.
    """

    reference: str
    price: Decimal
    open_offset_ticks: int  # open - reference (V1 convention)
    side_of_open: Side  # UP = reference above the open; NONE = reference at the open tick
    min_distance_ticks: int  # over [08:30, 08:30 + PROBE_REACH_MINUTES)
    reached_utc: datetime | None
    reach_beyond_ticks: int | None  # how far past the reference the reaching trade printed
    first_touch_utc: datetime | None  # exact touch, same horizon
    excursion_toward_before_reach_ticks: int | None  # max distance from the open toward the reference before the reach
    opposite_excursion_before_reach_ticks: int | None  # max beyond the open on the other side before the reach
    crossed_open_after: bool | None  # None when the reference is at the open or not reached
    first_open_cross_after_utc: datetime | None
    reach_to_cross: timedelta | None
    opposite_excursion_after_cross: tuple[tuple[int, int], ...]  # (minutes, ticks beyond the open) in [cross, cross+N)


@dataclass(frozen=True)
class OpeningEvent:
    timestamp_utc: datetime
    kind: EventKind
    reference: str | None
    price: Decimal


@dataclass(frozen=True)
class OpeningReferenceSequence:
    horizon_minutes: int
    references: tuple[str, ...]  # references included, in fixed order
    open_cross_count: int  # all crosses inside the horizon (only first and last appear as events)
    events: tuple[OpeningEvent, ...]


@dataclass(frozen=True)
class ContextQuality:
    """CURRENT_OPEN_QUALITY, PRIOR_DAY_QUALITY and OVERNIGHT_QUALITY, never merged."""

    current_open: OpeningQualityGrade
    current_open_reasons: tuple[str, ...]
    prior_day_outcome: ContextOutcome
    prior_day_quality: QualityGrade | None
    prior_day_reasons: tuple[str, ...]
    overnight: OvernightQualityGrade | None  # None = overnight not built
    overnight_reasons: tuple[str, ...]


@dataclass(frozen=True)
class OpeningPathFacts:
    policy_id: str
    opening: OpeningAuctionFacts  # accepted V1 facts, unchanged
    overnight: OvernightContext | None
    quality: ContextQuality
    overnight_reference_interactions: tuple[ReferenceInteraction, ...] = ()  # ONH / ONL per V1 horizon
    scales: tuple[OpeningScaleFacts, ...] = ()
    grace: tuple[GraceDiagnostic, ...] = ()
    encounters: tuple[ReferenceEncounter, ...] = ()
    sequence: OpeningReferenceSequence | None = None

    def scale(self, seconds: int) -> OpeningScaleFacts | None:
        return next((s for s in self.scales if s.horizon_seconds == seconds), None)

    def encounter(self, reference: str) -> ReferenceEncounter | None:
        return next((e for e in self.encounters if e.reference == reference), None)

    @property
    def first_reference_reached(self) -> ReferenceEncounter | None:
        """Earliest reach among references off the open tick; ties -> fixed reference order."""
        reached = [e for e in self.encounters if e.reached_utc is not None and e.side_of_open is not Side.NONE]
        return min(reached, key=lambda e: e.reached_utc, default=None)


def build_opening_path_facts(opening: OpeningAuctionFacts, overnight: OvernightContext | None) -> OpeningPathFacts:
    s, prior = opening.session, opening.prior
    on = overnight.session if overnight is not None else None
    quality = ContextQuality(
        current_open=s.quality.grade, current_open_reasons=s.quality.reasons,
        prior_day_outcome=prior.outcome,
        prior_day_quality=prior.quality_grade, prior_day_reasons=prior.reasons,
        overnight=on.quality.grade if on is not None else None,
        overnight_reasons=on.quality.reasons if on is not None else ("overnight session not built",))
    if not s.available:
        return OpeningPathFacts(OPENING_PATH_POLICY_ID, opening, overnight, quality)
    refs = []
    if prior.usable:
        refs += [("PRIOR_HIGH", prior.profile_high), ("PRIOR_VAH", prior.value_area_high), ("PRIOR_POC", prior.poc),
                 ("PRIOR_VAL", prior.value_area_low), ("PRIOR_LOW", prior.profile_low)]
    on_refs = []
    if on is not None and on.available:
        on_refs = [("OVERNIGHT_HIGH", on.high), ("OVERNIGHT_LOW", on.low)]
    refs += on_refs
    return OpeningPathFacts(
        policy_id=OPENING_PATH_POLICY_ID,
        opening=opening,
        overnight=overnight,
        quality=quality,
        overnight_reference_interactions=_interactions(s, on_refs),
        scales=tuple(_scale(s.path, s.cash_open.cash_open_utc, secs) for secs in OPENING_SCALE_SECONDS),
        grace=tuple(_grace(s.path, s.cash_open.cash_open_utc, g) for g in GRACE_SECONDS),
        encounters=tuple(_encounter(s.path, s.cash_open.cash_open_utc, name, price, s.price_increment)
                         for name, price in refs),
        sequence=_sequence(s.path, s.cash_open.cash_open_utc, refs, s.price_increment),
    )


def _span(a: datetime, b: datetime) -> Decimal:
    return Decimal(str((b - a).total_seconds()))


def _occupancy(pts, ref: int, end: datetime) -> tuple[Decimal, Decimal, Decimal]:
    above = below = at = Decimal(0)
    for i, p in enumerate(pts):
        span = _span(p.timestamp_utc, pts[i + 1].timestamp_utc if i + 1 < len(pts) else end)
        if p.tick > ref:
            above += span
        elif p.tick < ref:
            below += span
        else:
            at += span
    return above, below, at


def _residences(pts, ref: int, end: datetime) -> list[tuple[int, datetime, datetime]]:
    """(side, start, end) runs between strict side changes; see OpeningScaleFacts."""
    runs, side, start = [], 0, None
    for p in pts:
        s = _sign(p.tick - ref)
        if s == 0:
            continue
        if side == 0:
            side, start = s, p.timestamp_utc
        elif s != side:
            runs.append((side, start, p.timestamp_utc))
            side, start = s, p.timestamp_utc
    if side:
        runs.append((side, start, end))
    return runs


def _longest(runs, side: int) -> tuple[timedelta | None, datetime | None]:
    best = None
    for s, a, b in runs:  # strict improvement only: ties keep the earlier run
        if s == side and (best is None or b - a > best[1] - best[0]):
            best = (a, b)
    return (None, None) if best is None else (best[1] - best[0], best[0])


def _scale(path: tuple[PathPoint, ...], open_utc: datetime, seconds: int) -> OpeningScaleFacts:
    end = open_utc + timedelta(seconds=seconds)
    pts = [p for p in path if p.timestamp_utc < end]
    o = pts[0].tick
    hi, lo = max(p.tick for p in pts), min(p.tick for p in pts)
    up, down = hi - o, o - lo
    crosses = _crossings(pts, o)
    above, below, at = _occupancy(pts, o, end)
    runs = _residences(pts, o, end)
    up_len, up_at = _longest(runs, 1)
    dn_len, dn_at = _longest(runs, -1)
    return OpeningScaleFacts(
        horizon_seconds=seconds, end_utc=end,
        high=next(p.price for p in pts if p.tick == hi), low=next(p.price for p in pts if p.tick == lo),
        last_price=pts[-1].price, excursion_up_ticks=up, excursion_down_ticks=down, dominant=_dominance(up, down),
        counter_to_dominant=_ratio(min(up, down), max(up, down)), open_cross_count=len(crosses),
        first_open_cross_utc=crosses[0] if crosses else None, last_open_cross_utc=crosses[-1] if crosses else None,
        open_to_last_cross=crosses[-1] - pts[0].timestamp_utc if crosses else None,
        seconds_above_open=above, seconds_below_open=below, seconds_at_open=at,
        seconds_observed=above + below + at,
        longest_up_residence=up_len, longest_up_residence_start_utc=up_at,
        longest_down_residence=dn_len, longest_down_residence_start_utc=dn_at)


def _side(sign: int) -> Side:
    return Side.UP if sign > 0 else Side.DOWN if sign < 0 else Side.NONE


def _grace(path: tuple[PathPoint, ...], open_utc: datetime, grace: int) -> GraceDiagnostic:
    o = path[0].tick
    instant = path[0].timestamp_utc + timedelta(seconds=grace)
    upto = [p for p in path if p.timestamp_utc <= instant]
    current = upto[-1]
    held = next((_sign(p.tick - o) for p in reversed(upto) if p.tick != o), 0)
    horizons = []
    for minutes in GRACE_HORIZON_MINUTES:
        end = open_utc + timedelta(minutes=minutes)
        if instant >= end:
            horizons.append(GraceHorizon(minutes, False, False, None, None, None))
            continue
        after = [p for p in path if instant < p.timestamp_utc < end]
        if held:
            cross = next((p.timestamp_utc for p in after if _sign(p.tick - o) == -held), None)
            seen = [current] + after
            fav = max(0, max(held * (p.tick - o) for p in seen))
            counter = max(0, max(-held * (p.tick - o) for p in seen))
        else:
            crosses = _cross_points(after, o)
            cross = crosses[0].timestamp_utc if crosses else None
            fav = counter = None
        horizons.append(GraceHorizon(minutes, True, cross is not None, cross, fav, counter))
    return GraceDiagnostic(grace, instant, current.price, current.tick - o, _side(_sign(current.tick - o)),
                           _side(held), tuple(horizons))


def _encounter(path, open_utc: datetime, name: str, price: Decimal, inc: Decimal) -> ReferenceEncounter:
    o, ref = path[0].tick, int(price / inc)
    end = open_utc + timedelta(minutes=PROBE_REACH_MINUTES)
    pts = [p for p in path if p.timestamp_utc < end]
    sign = _sign(ref - o)
    touch = next((p.timestamp_utc for p in pts if p.tick == ref), None)
    base = dict(reference=name, price=price, open_offset_ticks=o - ref, side_of_open=_side(sign),
                min_distance_ticks=min(abs(p.tick - ref) for p in pts), first_touch_utc=touch)
    if sign == 0:
        return ReferenceEncounter(**base, reached_utc=path[0].timestamp_utc, reach_beyond_ticks=0,
                                  excursion_toward_before_reach_ticks=0, opposite_excursion_before_reach_ticks=0,
                                  crossed_open_after=None, first_open_cross_after_utc=None, reach_to_cross=None,
                                  opposite_excursion_after_cross=())
    i = next((k for k, p in enumerate(pts) if sign * (p.tick - ref) >= 0), None)
    if i is None:
        return ReferenceEncounter(**base, reached_utc=None, reach_beyond_ticks=None,
                                  excursion_toward_before_reach_ticks=max(0, max(sign * (p.tick - o) for p in pts)),
                                  opposite_excursion_before_reach_ticks=max(0, max(-sign * (p.tick - o) for p in pts)),
                                  crossed_open_after=None, first_open_cross_after_utc=None, reach_to_cross=None,
                                  opposite_excursion_after_cross=())
    reach, before = pts[i], pts[:i]
    cross = next((p.timestamp_utc for p in path[i + 1:] if _sign(p.tick - o) == -sign), None)  # pts is a prefix of path
    after = []
    if cross is not None:
        for minutes in PROBE_AFTER_CROSS_MINUTES:
            stop = cross + timedelta(minutes=minutes)
            window = [p for p in path if cross <= p.timestamp_utc < stop]
            after.append((minutes, max(0, max(-sign * (p.tick - o) for p in window))))
    return ReferenceEncounter(
        **base, reached_utc=reach.timestamp_utc, reach_beyond_ticks=sign * (reach.tick - ref),
        excursion_toward_before_reach_ticks=max((sign * (p.tick - o) for p in before), default=0),
        opposite_excursion_before_reach_ticks=max(0, max((-sign * (p.tick - o) for p in before), default=0)),
        crossed_open_after=cross is not None, first_open_cross_after_utc=cross,
        reach_to_cross=None if cross is None else cross - reach.timestamp_utc,
        opposite_excursion_after_cross=tuple(after))


def _sequence(path, open_utc: datetime, refs, inc: Decimal) -> OpeningReferenceSequence:
    end = open_utc + timedelta(minutes=SEQUENCE_MINUTES)
    pts = [p for p in path if p.timestamp_utc < end]
    o = pts[0]
    events = [OpeningEvent(o.timestamp_utc, EventKind.OPEN, None, o.price)]
    crosses = _cross_points(pts, o.tick)
    if crosses:
        events.append(OpeningEvent(crosses[0].timestamp_utc, EventKind.OPEN_CROSS_FIRST, None, crosses[0].price))
        if len(crosses) > 1:
            events.append(OpeningEvent(crosses[-1].timestamp_utc, EventKind.OPEN_CROSS_LAST, None, crosses[-1].price))
    for name, price in refs:
        ref = int(price / inc)
        touch = next((p for p in pts if p.tick == ref), None)
        if touch is not None:
            events.append(OpeningEvent(touch.timestamp_utc, EventKind.REFERENCE_TOUCH, name, price))
        ref_crosses = _cross_points(pts, ref)
        if ref_crosses:
            events.append(OpeningEvent(ref_crosses[0].timestamp_utc, EventKind.REFERENCE_CROSS, name,
                                       ref_crosses[0].price))
    hi, lo = max(pts, key=lambda p: p.tick).tick, min(pts, key=lambda p: p.tick).tick
    hi_p = next(p for p in pts if p.tick == hi)
    lo_p = next(p for p in pts if p.tick == lo)
    events.append(OpeningEvent(hi_p.timestamp_utc, EventKind.WINDOW_HIGH_FIRST_REACHED, None, hi_p.price))
    events.append(OpeningEvent(lo_p.timestamp_utc, EventKind.WINDOW_LOW_FIRST_REACHED, None, lo_p.price))
    names = [n for n, _ in refs]
    events.sort(key=lambda e: (e.timestamp_utc, _EVENT_ORDER.index(e.kind),
                               names.index(e.reference) if e.reference else -1))
    return OpeningReferenceSequence(SEQUENCE_MINUTES, tuple(names), len(crosses), tuple(events))


def _cross_points(pts, ref: int) -> list[PathPoint]:
    """The crossing trades themselves (same rule as tpo_opening._crossings, which returns timestamps)."""
    side, out = 0, []
    for p in pts:
        s = _sign(p.tick - ref)
        if s == 0:
            continue
        if side and s != side:
            out.append(p)
        side = s
    return out


# --- text rendering ----------------------------------------------------------------------------

def _t(ts: datetime | None) -> str:
    return "--" if ts is None else ts.strftime("%H:%M:%S.%f")[:-3] + "Z"


def _d(td: timedelta | None) -> str:
    return "--" if td is None else f"{td.total_seconds():.3f}s"


def _r(value: Decimal | None) -> str:
    return "undefined" if value is None else str(value.quantize(Decimal("0.0001")))


def _scale_label(seconds: int) -> str:
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m"


def render_opening_path(f: OpeningPathFacts) -> list[str]:
    """Numbers and ordered events only; never an opening-type name, preferred scale or interpretation."""
    q = f.quality
    lines = [f"OPENING PATH DETAIL ({f.policy_id}):",
             f"  Quality (kept separate): CURRENT_OPEN {q.current_open.value}; PRIOR_DAY {q.prior_day_outcome.value}"
             + (f" / {q.prior_day_quality.value}" if q.prior_day_quality else "")
             + f"; OVERNIGHT {q.overnight.value if q.overnight else 'NOT_BUILT'}"]
    s = f.opening.session
    if not s.available:
        return lines + ["  No opening path facts are computed (no trustworthy cash open).", ""]
    lines.append("  Multi-scale opening facts (from 08:30:00 CT; observational scales, not thresholds):")
    lines.append("    scale  high       low        last       up  dn  dominant c/d        crosses  first-cross   "
                 "last-cross    open->last   sec>open    sec<open   sec=open  longest-up  longest-dn")
    for x in f.scales:
        lines.append(
            f"    {_scale_label(x.horizon_seconds):<5}  {str(x.high):<9}  {str(x.low):<9}  {str(x.last_price):<9}  "
            f"{x.excursion_up_ticks:>2}  {x.excursion_down_ticks:>2}  {x.dominant.value:<8} {_r(x.counter_to_dominant):<10}"
            f"  {x.open_cross_count:>7}  {_t(x.first_open_cross_utc):<12}  {_t(x.last_open_cross_utc):<12}  "
            f"{_d(x.open_to_last_cross):>10}  {x.seconds_above_open:>9.3f}  {x.seconds_below_open:>9.3f}  "
            f"{x.seconds_at_open:>8.3f}  {_d(x.longest_up_residence):>10}  {_d(x.longest_down_residence):>10}")
    e, ot = s.early_tpo, s.one_timeframing
    a = s.window(30)
    lines.append("  Scale comparison: dominance "
                 + ", ".join(f"{_scale_label(x.horizon_seconds)} {x.dominant.value} ({_r(x.counter_to_dominant)})"
                             for x in f.scales if x.horizon_seconds <= 300)
                 + f"; A-period {a.dominant.value} ({_r(a.counter_to_dominant)}); A/B overlap {_r(e.ab_overlap_ratio)}; "
                 f"A-only rows {e.a_only_rows_full_day}; one-timeframing run from A: higher lows "
                 f"{ot.opening_higher_low_run}, lower highs {ot.opening_lower_high_run}")
    lines.append("  Grace-instant diagnostics (DIAGNOSTIC ONLY; no grace period is preferred):")
    for g in f.grace:
        cells = "  ".join(
            f"{h.minutes}m " + ("n/a" if not h.applicable else
                                f"cross {'yes' if h.crossed_open else 'no'} {_t(h.first_cross_utc)} fav "
                                f"{'--' if h.max_favorable_ticks is None else h.max_favorable_ticks} ctr "
                                f"{'--' if h.max_counter_ticks is None else h.max_counter_ticks}")
            for h in g.horizons)
        lines.append(f"    +{g.grace_seconds:>2}s  {str(g.price):<9} {g.offset_ticks:+d}t  side {g.side.value:<4} "
                     f"held {g.held_side.value:<4}  {cells}")
    if f.overnight_reference_interactions:
        lines.append("  Overnight references (min distance ticks / touched / crossed, per horizon; first touch / "
                     "first cross over 60 min):")
        for name in dict.fromkeys(r.reference for r in f.overnight_reference_interactions):
            rows = [r for r in f.overnight_reference_interactions if r.reference == name]
            last = rows[-1]
            cells = "  ".join(f"{r.horizon_minutes}m {r.min_distance_ticks}/{'yes' if r.touched else 'no'}/"
                              f"{'yes' if r.crossed else 'no'}" for r in rows)
            lines.append(f"    {name:<14} {str(last.price):<9} open{last.open_offset_ticks:+d}t  {cells}  "
                         f"touch {_t(last.first_touch_utc)}  cross {_t(last.first_cross_utc)}")
    if f.encounters:
        lines.append(f"  Reference encounters in the first {PROBE_REACH_MINUTES} min (reach = touch or trade beyond; "
                     "a touch is not a 'test'):")
        for x in f.encounters:
            if x.side_of_open is Side.NONE:
                lines.append(f"    {x.reference:<14} {str(x.price):<9} at the open tick")
                continue
            if x.reached_utc is None:
                lines.append(f"    {x.reference:<14} {str(x.price):<9} {x.side_of_open.value:<4} of open "
                             f"({-x.open_offset_ticks:+d}t): not reached; min distance {x.min_distance_ticks} ticks")
                continue
            after = ", ".join(f"{m}m {t}" for m, t in x.opposite_excursion_after_cross) or "--"
            lines.append(f"    {x.reference:<14} {str(x.price):<9} {x.side_of_open.value:<4} of open "
                         f"({-x.open_offset_ticks:+d}t): reached {_t(x.reached_utc)} (beyond {x.reach_beyond_ticks}t, "
                         f"touch {_t(x.first_touch_utc)}); opposite before {x.opposite_excursion_before_reach_ticks}t; "
                         f"open crossed after {'yes' if x.crossed_open_after else 'no'} {_t(x.first_open_cross_after_utc)}"
                         f" (+{_d(x.reach_to_cross)}); opposite excursion after cross: {after}")
        first = f.first_reference_reached
        lines.append(f"    first reference reached: {first.reference if first else 'none'}")
    if f.sequence is not None:
        seq = f.sequence
        lines.append(f"  Event sequence, first {seq.horizon_minutes} min ({seq.open_cross_count} open crosses; "
                     "first/last shown):")
        for ev in seq.events:
            lines.append(f"    {_t(ev.timestamp_utc)}  {ev.kind.value:<26} {ev.reference or '':<14} {ev.price}".rstrip())
    lines += ["  Facts only: no opening type, preferred scale, tolerance, bias or signal.", ""]
    return lines
