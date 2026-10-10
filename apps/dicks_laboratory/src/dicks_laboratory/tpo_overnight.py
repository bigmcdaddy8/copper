"""Deterministic overnight (Globex) context before the cash open (0Y-G).

One Laboratory overnight study window per trading date, built from the existing
session semantics:

  start  SESSION_OPEN anchor (17:00 America/Chicago on the previous evening;
         Sunday 17:00 for a Monday)
  end    US_CASH_OPEN anchor (08:30 America/Chicago on the trading date)
  membership [start, end), canonical timestamps UTC

Two objects, kept apart:

  OvernightSession   prior-independent facts: first print, Globex open print,
                     high/low/range and their times, terminal print before 08:30,
                     30-minute bracket ranges, volume at tick, overnight quality.
  OvernightContext   the session joined to the cash open and an explicit
                     `PriorContext`: cash open vs the overnight range, overnight
                     vs prior range/value, separately named gaps, and continuous
                     occupancy ("inventory") facts relative to prior references.

OvernightContext != trading bias. No LONG/SHORT/NEUTRAL inventory label, no
accepted/rejected/initiative/responsive word, no threshold. Time, TPO-bracket and
volume measures are reported separately and never combined into a score. The
Laboratory has no CME settlement price: the prior *cash terminal* (last eligible
trade before 15:00 CT) is a different reference and is named as such. See
docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md §51-§56.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.sessions import AnchorKind, resolve_anchor
from dicks_laboratory.tpo_opening import (
    CashOpenSession,
    ExtremeOrder,
    PathPoint,
    PriorContext,
    Side,
    _path,
    _ratio,
    cash_open_utc,
)
from dicks_laboratory.volume_profile import PriceGrid

OVERNIGHT_CONTEXT_POLICY_ID = "OVERNIGHT_CONTEXT_V1"
# Laboratory data-coverage bound (same value as the cash-open bound): the Globex
# open print must occur within this delay of 17:00 CT or no Globex open is claimed.
GLOBEX_OPEN_MAX_DELAY = timedelta(seconds=60)
OVERNIGHT_BRACKET_MINUTES = 30  # TPO-style brackets from 17:00 CT; descriptive only
OVERNIGHT_INVENTORY_REFERENCES = ("PRIOR_TERMINAL", "PRIOR_POC", "PRIOR_VAH", "PRIOR_VAL")
# FIRST_OVERNIGHT_PRINT is reported separately because it is the Globex open only when one is claimed.
GAP_NAMES = ("GLOBEX_OPEN_VS_PRIOR_TERMINAL", "FIRST_OVERNIGHT_PRINT_VS_PRIOR_TERMINAL", "CASH_OPEN_VS_PRIOR_TERMINAL",
             "CASH_OPEN_VS_OVERNIGHT_TERMINAL")


class OvernightQualityGrade(StrEnum):
    AVAILABLE = "AVAILABLE"  # computed; no evidence of incompleteness
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # computed; evidence they may be incomplete
    NOT_AVAILABLE = "NOT_AVAILABLE"  # no overnight trade retained: nothing computed


class OvernightRangeLocation(StrEnum):
    ABOVE_OVERNIGHT_HIGH = "ABOVE_OVERNIGHT_HIGH"
    AT_OVERNIGHT_HIGH = "AT_OVERNIGHT_HIGH"
    INSIDE_OVERNIGHT_RANGE = "INSIDE_OVERNIGHT_RANGE"
    AT_OVERNIGHT_LOW = "AT_OVERNIGHT_LOW"
    BELOW_OVERNIGHT_LOW = "BELOW_OVERNIGHT_LOW"


def overnight_window_utc(trading_date: date) -> tuple[datetime, datetime]:
    """[Globex open, cash open) for the trading date via the session anchors (never calendar arithmetic)."""
    return resolve_anchor(AnchorKind.SESSION_OPEN, trading_date).anchor_timestamp_utc, cash_open_utc(trading_date)


@dataclass(frozen=True)
class OvernightQuality:
    grade: OvernightQualityGrade
    reasons: tuple[str, ...]
    window_start_utc: datetime
    window_end_utc: datetime
    capture_begins_after_window_start: bool | None  # None = capture interval not recorded
    capture_ends_before_window_end: bool | None
    known_gaps_in_window: int
    suspected_gaps_in_window: int
    lifecycle_state: str | None
    contract: str
    contract_consistent: bool  # one instrument across the dataset (enforced by scoping)


@dataclass(frozen=True)
class OvernightBracket:
    """A 30-minute bracket from 17:00 CT with at least one eligible trade (every trade, not only price changes)."""

    index: int
    start_utc: datetime
    end_utc: datetime
    high_tick: int
    low_tick: int


@dataclass(frozen=True)
class OvernightSession:
    policy_id: str
    trading_date: date
    price_increment: Decimal
    contract: str
    window_start_utc: datetime
    window_end_utc: datetime
    quality: OvernightQuality
    path: tuple[PathPoint, ...]  # price changes in the window; empty if NOT_AVAILABLE
    brackets: tuple[OvernightBracket, ...]
    volume_at_tick: tuple[tuple[int, Decimal], ...] | None  # None when trade sizes are not available
    # None unless the session is available
    first_price: Decimal | None = None
    first_utc: datetime | None = None
    # claimed only when the capture start is recorded at/before 17:00 CT and the first eligible trade is
    # within GLOBEX_OPEN_MAX_DELAY of 17:00 CT; otherwise None (first_price is still reported)
    globex_open_price: Decimal | None = None
    globex_open_utc: datetime | None = None
    globex_open_delay: timedelta | None = None
    globex_open_unavailable_reason: str | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    range_ticks: int | None = None
    range_points: Decimal | None = None
    time_of_high_utc: datetime | None = None  # first reached
    time_of_low_utc: datetime | None = None
    extreme_order: ExtremeOrder | None = None
    terminal_price: Decimal | None = None  # last eligible trade before 08:30 CT
    terminal_utc: datetime | None = None

    @property
    def available(self) -> bool:
        return self.quality.grade is not OvernightQualityGrade.NOT_AVAILABLE

    @property
    def globex_open_boundary_proven(self) -> bool:
        """Capture is recorded as starting at or before 17:00:00 CT (no tolerance)."""
        return self.quality.capture_begins_after_window_start is False

    @property
    def high_tick(self) -> int | None:
        return None if self.high is None else int(self.high / self.price_increment)

    @property
    def low_tick(self) -> int | None:
        return None if self.low is None else int(self.low / self.price_increment)


def build_overnight_session(
    trades,
    grid: PriceGrid,
    trading_date: date,
    contract: str,
    capture_started_at: datetime | None,
    capture_ended_at: datetime | None,
    gap_intervals: tuple[tuple[str, datetime, datetime], ...],
    lifecycle_state: str | None,
) -> OvernightSession:
    """`trades` = the trading date's effective Globex tape (any superset); only [17:00, 08:30) CT is used."""
    start, end = overnight_window_utc(trading_date)
    points = _path(trades, grid, start, end)
    quality = _overnight_quality(start, end, bool(points), contract, capture_started_at, capture_ended_at,
                                 gap_intervals, lifecycle_state)
    base = dict(policy_id=OVERNIGHT_CONTEXT_POLICY_ID, trading_date=trading_date, price_increment=grid.tick_size,
                contract=contract, window_start_utc=start, window_end_utc=end, quality=quality)
    if not points:
        return OvernightSession(**base, path=(), brackets=(), volume_at_tick=None)
    hi = max(p.tick for p in points)
    lo = min(p.tick for p in points)
    hi_at = next(p.timestamp_utc for p in points if p.tick == hi)
    lo_at = next(p.timestamp_utc for p in points if p.tick == lo)
    first = points[0]
    late_capture = quality.capture_begins_after_window_start
    if late_capture:
        g_reason = "capture began after 17:00 CT; the first retained trade is not the Globex open"
    elif late_capture is None:  # no tolerance: coverage at 17:00:00 CT must be demonstrable
        g_reason = "capture start not recorded; exact Globex-open boundary coverage not proven"
    elif first.timestamp_utc - start > GLOBEX_OPEN_MAX_DELAY:
        g_reason = f"first eligible trade {first.timestamp_utc - start} after 17:00 CT (> {GLOBEX_OPEN_MAX_DELAY})"
    else:
        g_reason = None
    return OvernightSession(
        **base,
        path=points,
        brackets=_brackets(trades, grid, start, end),
        volume_at_tick=_volume_at_tick(trades, grid, start, end),
        first_price=first.price,
        first_utc=first.timestamp_utc,
        globex_open_price=None if g_reason else first.price,
        globex_open_utc=None if g_reason else first.timestamp_utc,
        globex_open_delay=None if g_reason else first.timestamp_utc - start,
        globex_open_unavailable_reason=g_reason,
        high=grid.price_at(hi),
        low=grid.price_at(lo),
        range_ticks=hi - lo,
        range_points=grid.price_at(hi) - grid.price_at(lo),
        time_of_high_utc=hi_at,
        time_of_low_utc=lo_at,
        extreme_order=(ExtremeOrder.NO_RANGE if hi == lo else
                       ExtremeOrder.HIGH_FIRST if hi_at < lo_at else ExtremeOrder.LOW_FIRST),
        terminal_price=points[-1].price,
        terminal_utc=_last_trade_utc(trades, grid, start, end),
    )


def _last_trade_utc(trades, grid: PriceGrid, start: datetime, end: datetime) -> datetime:
    """Timestamp of the last eligible trade (the path keeps only the first trade at each price change)."""
    return max(t.event_timestamp for t in trades
               if start <= t.event_timestamp < end and grid.tick_index(t.price) is not None)


def _overnight_quality(start, end, has_trades, contract, started, ended, gap_intervals, lifecycle) -> OvernightQuality:
    known = sum(1 for kind, s, e in gap_intervals if kind == "KNOWN_GAP" and s < end and e > start)
    suspected = sum(1 for kind, s, e in gap_intervals if kind == "SUSPECTED_GAP" and s < end and e > start)
    late = None if started is None else started > start
    early_end = None if ended is None else ended < end
    blockers, reasons = [], []
    if not has_trades:
        blockers.append("no eligible trade in the overnight window [17:00, 08:30) CT")
    if started is None and ended is None:
        reasons.append("capture interval not recorded; overnight coverage unverified")
    else:  # start and end are judged independently: a recorded late start is never hidden
        if started is None:
            reasons.append("capture start not recorded; coverage from 17:00 CT unverified")
        elif late:
            reasons.append(f"capture began {started - start} after 17:00 CT (overnight window starts late)")
        if ended is None:
            reasons.append("capture end not recorded; coverage to 08:30 CT unverified")
        elif early_end:
            reasons.append(f"capture ended {end - ended} before 08:30 CT")
    if known:
        reasons.append(f"KNOWN_GAP overlaps the overnight window: {known}")
    if suspected:
        reasons.append(f"SUSPECTED_GAP overlaps the overnight window: {suspected}")
    if lifecycle != "FINALIZED":
        reasons.append(f"lifecycle {lifecycle or 'UNTRACKED'} (not FINALIZED)")
    if blockers:
        grade, reasons = OvernightQualityGrade.NOT_AVAILABLE, blockers + reasons
    else:
        grade = OvernightQualityGrade.QUALITY_QUALIFIED if reasons else OvernightQualityGrade.AVAILABLE
    return OvernightQuality(grade, tuple(reasons), start, end, late, early_end, known, suspected, lifecycle,
                            contract, True)


def _brackets(trades, grid: PriceGrid, start: datetime, end: datetime) -> tuple[OvernightBracket, ...]:
    # UTC elapsed time equals wall-clock elapsed time inside [17:00, 08:30): US DST changes
    # happen at 02:00 on a Sunday, while the Globex session is closed.
    step = timedelta(minutes=OVERNIGHT_BRACKET_MINUTES)
    highs: dict[int, int] = {}
    lows: dict[int, int] = {}
    for t in trades:
        if start <= t.event_timestamp < end:
            tick = grid.tick_index(t.price)
            if tick is None:
                continue
            i = (t.event_timestamp - start) // step
            highs[i] = max(highs.get(i, tick), tick)
            lows[i] = min(lows.get(i, tick), tick)
    return tuple(OvernightBracket(i, start + i * step, min(start + (i + 1) * step, end), highs[i], lows[i])
                 for i in sorted(highs))


def _volume_at_tick(trades, grid: PriceGrid, start: datetime, end: datetime):
    volume: dict[int, Decimal] = {}
    for t in trades:
        if start <= t.event_timestamp < end:
            tick = grid.tick_index(t.price)
            if tick is None:
                continue
            size = getattr(t, "size", None)
            if size is None:
                return None
            volume[tick] = volume.get(tick, Decimal(0)) + size
    return tuple(sorted(volume.items()))


# --- joined context --------------------------------------------------------------------------

@dataclass(frozen=True)
class GapFact:
    """to_price - from_price; the different gaps are never conflated."""

    name: str  # one of GAP_NAMES
    from_price: Decimal
    to_price: Decimal
    points: Decimal
    ticks: int
    direction: Side


@dataclass(frozen=True)
class OvernightPriorRelation:
    """Overnight range vs the prior cash profile (same contract). Signed values = overnight - prior."""

    onh_vs_prior_high_ticks: int
    onh_vs_prior_high_points: Decimal
    onl_vs_prior_low_ticks: int
    onl_vs_prior_low_points: Decimal
    onh_vs_vah_ticks: int
    onh_vs_vah_points: Decimal
    onl_vs_val_ticks: int
    onl_vs_val_points: Decimal
    overlaps_prior_value: bool  # inclusive
    overlaps_prior_range: bool
    inside_prior_value: bool  # VAL <= ONL and ONH <= VAH
    inside_prior_range: bool
    excursion_above_prior_high_ticks: int  # max(0, ONH - prior high)
    excursion_above_prior_high_points: Decimal
    excursion_below_prior_low_ticks: int
    excursion_below_prior_low_points: Decimal
    excursion_above_vah_ticks: int
    excursion_above_vah_points: Decimal
    excursion_below_val_ticks: int
    excursion_below_val_points: Decimal


@dataclass(frozen=True)
class OvernightOccupancy:
    """Continuous facts about where the overnight session traded relative to one reference.

    Time: last traded price holds until the next price change, from the first overnight
    print to 08:30:00 CT (a gap is not filled: the last price simply carries).
    Brackets/TPO rows: 30-minute brackets; a row = one tick of a bracket's range.
    Volume: contracts at ticks strictly above / below / at the reference.
    The three families are reported separately; nothing is weighted or combined.
    """

    reference: str
    price: Decimal
    seconds_above: Decimal
    seconds_below: Decimal
    seconds_at: Decimal
    seconds_observed: Decimal
    fraction_above: Decimal | None  # seconds_above / seconds_observed
    fraction_below: Decimal | None
    brackets_traded: int
    brackets_entirely_above: int
    brackets_entirely_below: int
    brackets_touching_or_spanning: int
    tpo_rows_above: int
    tpo_rows_below: int
    tpo_rows_at: int
    range_above_ticks: int  # max(0, ONH - reference)
    range_below_ticks: int  # max(0, reference - ONL)
    terminal_vs_reference_ticks: int  # overnight terminal - reference
    volume_above: Decimal | None
    volume_below: Decimal | None
    volume_at: Decimal | None


@dataclass(frozen=True)
class OvernightContext:
    policy_id: str
    session: OvernightSession
    prior: PriorContext
    reasons: tuple[str, ...]  # why any part below is absent
    # need the overnight session and the cash open print
    open_location: OvernightRangeLocation | None = None
    open_vs_onh_ticks: int | None = None  # cash open - ONH
    open_vs_onl_ticks: int | None = None
    open_percentile_in_overnight_range: Decimal | None = None  # (open - ONL) / (ONH - ONL); None if range 0
    # need a usable (AVAILABLE, same-contract) prior context as well
    prior_relation: OvernightPriorRelation | None = None
    inventory: tuple[OvernightOccupancy, ...] = ()
    gaps: tuple[GapFact, ...] = ()

    def occupancy(self, reference: str) -> OvernightOccupancy | None:
        return next((o for o in self.inventory if o.reference == reference), None)

    def gap(self, name: str) -> GapFact | None:
        return next((g for g in self.gaps if g.name == name), None)


def build_overnight_context(session: OvernightSession, opening: CashOpenSession, prior: PriorContext) -> OvernightContext:
    reasons = []
    inc = session.price_increment
    to_ticks = _to_ticks(inc)
    gaps = []
    cash = opening.cash_open.price if opening.available else None
    if not session.available:
        reasons.append("overnight session NOT_AVAILABLE")
    if cash is None:
        reasons.append("no cash open print: cash-open comparisons not computed")
    if not prior.usable:
        reasons.append(f"prior context {prior.outcome.value}: prior-relative facts not computed")
    loc = vs_h = vs_l = pct = None
    if session.available and cash is not None:
        loc = _locate(cash, session.low, session.high)
        vs_h, vs_l = to_ticks(cash - session.high), to_ticks(cash - session.low)
        pct = _ratio(to_ticks(cash - session.low), session.range_ticks)
        gaps.append(_gap("CASH_OPEN_VS_OVERNIGHT_TERMINAL", session.terminal_price, cash, to_ticks))
    relation, inventory = None, ()
    if prior.usable:
        if session.available and session.globex_open_price is not None:
            gaps.append(_gap("GLOBEX_OPEN_VS_PRIOR_TERMINAL", prior.terminal_price, session.globex_open_price,
                             to_ticks))
        elif session.available:
            reasons.append(f"no Globex open print: {session.globex_open_unavailable_reason}")
        if session.available:
            gaps.append(_gap("FIRST_OVERNIGHT_PRINT_VS_PRIOR_TERMINAL", prior.terminal_price, session.first_price,
                             to_ticks))
        if cash is not None:
            gaps.append(_gap("CASH_OPEN_VS_PRIOR_TERMINAL", prior.terminal_price, cash, to_ticks))
        if session.available:
            relation = _relation(session, prior, to_ticks)
            refs = dict(zip(OVERNIGHT_INVENTORY_REFERENCES,
                            (prior.terminal_price, prior.poc, prior.value_area_high, prior.value_area_low)))
            inventory = tuple(_occupancy(session, name, price) for name, price in refs.items() if price is not None)
    gaps.sort(key=lambda g: GAP_NAMES.index(g.name))
    return OvernightContext(OVERNIGHT_CONTEXT_POLICY_ID, session, prior, tuple(reasons), loc, vs_h, vs_l, pct,
                            relation, inventory, tuple(gaps))


def _to_ticks(inc: Decimal):
    def convert(points: Decimal) -> int:
        value = points / inc
        if value != value.to_integral_value():
            raise ValueError(f"{points} is not a whole number of {inc} ticks")
        return int(value)
    return convert


def _locate(price: Decimal, low: Decimal, high: Decimal) -> OvernightRangeLocation:
    if price > high:
        return OvernightRangeLocation.ABOVE_OVERNIGHT_HIGH
    if price == high:
        return OvernightRangeLocation.AT_OVERNIGHT_HIGH
    if price > low:
        return OvernightRangeLocation.INSIDE_OVERNIGHT_RANGE
    if price == low:
        return OvernightRangeLocation.AT_OVERNIGHT_LOW
    return OvernightRangeLocation.BELOW_OVERNIGHT_LOW


def _gap(name: str, start: Decimal, end: Decimal, to_ticks) -> GapFact:
    points = end - start
    return GapFact(name, start, end, points, to_ticks(points),
                   Side.UP if points > 0 else Side.DOWN if points < 0 else Side.NONE)


def _relation(s: OvernightSession, p: PriorContext, to_ticks) -> OvernightPriorRelation:
    zero = Decimal(0)
    up_h, dn_l = max(zero, s.high - p.profile_high), max(zero, p.profile_low - s.low)
    up_v, dn_v = max(zero, s.high - p.value_area_high), max(zero, p.value_area_low - s.low)
    return OvernightPriorRelation(
        onh_vs_prior_high_ticks=to_ticks(s.high - p.profile_high), onh_vs_prior_high_points=s.high - p.profile_high,
        onl_vs_prior_low_ticks=to_ticks(s.low - p.profile_low), onl_vs_prior_low_points=s.low - p.profile_low,
        onh_vs_vah_ticks=to_ticks(s.high - p.value_area_high), onh_vs_vah_points=s.high - p.value_area_high,
        onl_vs_val_ticks=to_ticks(s.low - p.value_area_low), onl_vs_val_points=s.low - p.value_area_low,
        overlaps_prior_value=s.low <= p.value_area_high and s.high >= p.value_area_low,
        overlaps_prior_range=s.low <= p.profile_high and s.high >= p.profile_low,
        inside_prior_value=p.value_area_low <= s.low and s.high <= p.value_area_high,
        inside_prior_range=p.profile_low <= s.low and s.high <= p.profile_high,
        excursion_above_prior_high_ticks=to_ticks(up_h), excursion_above_prior_high_points=up_h,
        excursion_below_prior_low_ticks=to_ticks(dn_l), excursion_below_prior_low_points=dn_l,
        excursion_above_vah_ticks=to_ticks(up_v), excursion_above_vah_points=up_v,
        excursion_below_val_ticks=to_ticks(dn_v), excursion_below_val_points=dn_v,
    )


def _occupancy(s: OvernightSession, name: str, price: Decimal) -> OvernightOccupancy:
    ref = int(price / s.price_increment)
    above = below = at = Decimal(0)
    path = s.path
    for i, p in enumerate(path):
        until = path[i + 1].timestamp_utc if i + 1 < len(path) else s.window_end_utc
        span = Decimal(str((until - p.timestamp_utc).total_seconds()))
        if p.tick > ref:
            above += span
        elif p.tick < ref:
            below += span
        else:
            at += span
    observed = above + below + at
    b_above = sum(1 for b in s.brackets if b.low_tick > ref)
    b_below = sum(1 for b in s.brackets if b.high_tick < ref)
    rows_above = sum(max(0, b.high_tick - max(b.low_tick, ref + 1) + 1) for b in s.brackets)
    rows_below = sum(max(0, min(b.high_tick, ref - 1) - b.low_tick + 1) for b in s.brackets)
    rows_at = sum(1 for b in s.brackets if b.low_tick <= ref <= b.high_tick)
    vol = s.volume_at_tick
    return OvernightOccupancy(
        reference=name, price=price,
        seconds_above=above, seconds_below=below, seconds_at=at, seconds_observed=observed,
        fraction_above=None if not observed else above / observed,
        fraction_below=None if not observed else below / observed,
        brackets_traded=len(s.brackets), brackets_entirely_above=b_above, brackets_entirely_below=b_below,
        brackets_touching_or_spanning=len(s.brackets) - b_above - b_below,
        tpo_rows_above=rows_above, tpo_rows_below=rows_below, tpo_rows_at=rows_at,
        range_above_ticks=max(0, s.high_tick - ref), range_below_ticks=max(0, ref - s.low_tick),
        terminal_vs_reference_ticks=int(s.terminal_price / s.price_increment) - ref,
        volume_above=None if vol is None else sum((v for t, v in vol if t > ref), Decimal(0)),
        volume_below=None if vol is None else sum((v for t, v in vol if t < ref), Decimal(0)),
        volume_at=None if vol is None else sum((v for t, v in vol if t == ref), Decimal(0)),
    )


# --- text rendering ----------------------------------------------------------------------------

def _t(ts: datetime | None) -> str:
    return "--" if ts is None else ts.strftime("%m-%d %H:%M:%S.%f")[:-3] + "Z"


def _r(value: Decimal | None) -> str:
    return "undefined" if value is None else str(value.quantize(Decimal("0.0001")))


def _yn(value: bool | None) -> str:
    return "--" if value is None else ("yes" if value else "no")


def render_overnight_facts(ctx: OvernightContext) -> list[str]:
    """Numbers only; no inventory label, bias or interpretation."""
    s, q = ctx.session, ctx.session.quality
    lines = [f"OVERNIGHT CONTEXT ({ctx.policy_id}):",
             f"  Window [{_t(s.window_start_utc)}, {_t(s.window_end_utc)}) = [17:00 CT previous session evening, "
             "08:30 CT cash open)"]
    if q.grade is OvernightQualityGrade.NOT_AVAILABLE:
        lines.append("  *** OVERNIGHT FACTS NOT AVAILABLE ***")
    elif q.grade is OvernightQualityGrade.QUALITY_QUALIFIED:
        lines.append("  *** OVERNIGHT FACTS ARE QUALITY-QUALIFIED ***")
    lines += [f"    - {reason}" for reason in q.reasons]
    lines.append(f"  Overnight quality: {q.grade.value}   (capture starts late {_yn(q.capture_begins_after_window_start)}; "
                 f"ends early {_yn(q.capture_ends_before_window_end)}; KNOWN_GAP {q.known_gaps_in_window}, "
                 f"SUSPECTED_GAP {q.suspected_gaps_in_window}; lifecycle {q.lifecycle_state or 'UNTRACKED'}; "
                 f"contract {q.contract}, consistent {_yn(q.contract_consistent)})")
    if not s.available:
        lines += ["  No overnight facts are computed.", ""]
        return lines
    lines += [
        f"  First print {s.first_price} at {_t(s.first_utc)}; Globex open "
        + (f"{s.globex_open_price} (delay {s.globex_open_delay.total_seconds():.3f}s, max "
           f"{GLOBEX_OPEN_MAX_DELAY.total_seconds():.0f}s)" if s.globex_open_price is not None
           else f"none -- {s.globex_open_unavailable_reason}"),
        f"  ON high {s.high} at {_t(s.time_of_high_utc)}; ON low {s.low} at {_t(s.time_of_low_utc)}; "
        f"range {s.range_points} pts = {s.range_ticks} ticks; {s.extreme_order.value}",
        f"  ON terminal {s.terminal_price} at {_t(s.terminal_utc)} (last eligible trade before 08:30 CT)",
        f"  Brackets with trades: {len(s.brackets)} x {OVERNIGHT_BRACKET_MINUTES} min",
    ]
    if ctx.open_location is not None:
        lines.append(f"  Cash open vs overnight: {ctx.open_location.value}; open - ONH {ctx.open_vs_onh_ticks} ticks, "
                     f"open - ONL {ctx.open_vs_onl_ticks} ticks; percentile in ON range "
                     f"{_r(ctx.open_percentile_in_overnight_range)}")
    lines += [f"    - {reason}" for reason in ctx.reasons]
    for g in ctx.gaps:
        lines.append(f"  Gap {g.name}: {g.to_price} - {g.from_price} = {g.points} pts = {g.ticks} ticks, "
                     f"{g.direction.value}")
    r = ctx.prior_relation
    if r is not None:
        lines += [
            f"  ON vs prior (signed, ON - prior): ONH - prior high {r.onh_vs_prior_high_ticks} ticks "
            f"({r.onh_vs_prior_high_points} pts); ONL - prior low {r.onl_vs_prior_low_ticks} ticks "
            f"({r.onl_vs_prior_low_points} pts); ONH - VAH {r.onh_vs_vah_ticks} ticks ({r.onh_vs_vah_points} pts); "
            f"ONL - VAL {r.onl_vs_val_ticks} ticks ({r.onl_vs_val_points} pts)",
            f"    overlaps prior value {_yn(r.overlaps_prior_value)}, prior range {_yn(r.overlaps_prior_range)}; "
            f"inside prior value {_yn(r.inside_prior_value)}, prior range {_yn(r.inside_prior_range)}",
            f"    excursion above prior high {r.excursion_above_prior_high_ticks} ticks "
            f"({r.excursion_above_prior_high_points} pts), below prior low {r.excursion_below_prior_low_ticks} ticks "
            f"({r.excursion_below_prior_low_points} pts), above VAH {r.excursion_above_vah_ticks} ticks "
            f"({r.excursion_above_vah_points} pts), below VAL {r.excursion_below_val_ticks} ticks "
            f"({r.excursion_below_val_points} pts)",
        ]
    if ctx.inventory:
        lines.append("  Overnight occupancy vs prior references (time / brackets+TPO rows / volume kept separate):")
        lines.append("    reference       price      sec above    sec below   sec at   observed  frac up frac dn  "
                     "brk up/dn/span  rows up/dn/at  rng up/dn  term-ref  vol up/dn/at")
        for o in ctx.inventory:
            vol = ("--" if o.volume_above is None else f"{o.volume_above}/{o.volume_below}/{o.volume_at}")
            lines.append(
                f"    {o.reference:<14}  {str(o.price):<9} {o.seconds_above:>11.3f}  {o.seconds_below:>11.3f}  "
                f"{o.seconds_at:>7.3f}  {o.seconds_observed:>9.3f}  {_r(o.fraction_above):<7} {_r(o.fraction_below):<7} "
                f"{o.brackets_entirely_above}/{o.brackets_entirely_below}/{o.brackets_touching_or_spanning:<10}  "
                f"{o.tpo_rows_above}/{o.tpo_rows_below}/{o.tpo_rows_at:<9}  {o.range_above_ticks}/{o.range_below_ticks:<6}  "
                f"{o.terminal_vs_reference_ticks:>+8d}  {vol}")
        lines.append("    PRIOR_TERMINAL = last eligible prior-day trade before 15:00 CT; it is NOT the CME settlement.")
    lines += ["  Facts only: no inventory label, acceptance/rejection, bias or signal.", ""]
    return lines
