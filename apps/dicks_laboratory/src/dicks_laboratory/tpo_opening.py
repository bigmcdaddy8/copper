"""Deterministic opening-auction facts and prior-trading-date context (0Y-F).

A derived layer over the accepted cash-window tape, `TpoProfile` (0Y-A) and
`DayStructureFacts` (0Y-C). Two objects, kept apart:

  CashOpenSession       current-day facts that need no prior day: cash open
                        print, 5/15/30/60-minute windows, open revisits and
                        crossings, path ordering, A-extreme follow-through,
                        early TPO (A/B) and one-timeframing facts, opening quality.
  OpeningAuctionFacts   the session joined to an explicit `PriorContext`:
                        location vs prior range/value, gap, reference
                        interactions, prior value/range entry and exit.

OpeningAuctionFacts != OpeningType. Nothing here names or implies an opening
type (drive, test, rejection, auction), a bias or a signal. No word such as
"material", "near", "strong" or "test" is turned into a threshold. Every ratio
with a zero denominator is None ("undefined"). See
docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md §40-§50.

Tick-grid definitions (all prices are exact grid ticks):
  away     a trade at a tick != the reference tick
  touch    a trade at exactly the reference tick
  cross    a change of strict side: the latest trade strictly above the
           reference after the previous strictly-off-reference trade was
           strictly below it, or vice versa (trades at the reference keep the
           prior side). The starting side is the open's side when the open is
           off the reference, else the first off-reference trade.
  revisit  (cash open only) a touch of the open tick after price first traded
           away from it
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.sessions import AnchorKind, resolve_anchor
from dicks_laboratory.tpo_day_strength import DayStructureStrength, DominantExtension
from dicks_laboratory.tpo_day_structure import DayStructureFacts, QualityGrade
from dicks_laboratory.tpo_profile import INITIAL_BALANCE_MINUTES, US_CASH_PROFILE, TpoProfile
from dicks_laboratory.volume_profile import PriceGrid

OPENING_FACTS_POLICY_ID = "OPENING_AUCTION_FACTS_V1"
# Laboratory data-coverage bound, not a market concept: the opening print must
# occur within this delay of 08:30:00 CT or no cash open price is claimed.
CASH_OPEN_MAX_DELAY = timedelta(seconds=60)
OPENING_WINDOW_MINUTES = (5, 15, 30, 60)  # 30 = period A, 60 = A+B (IB) under 30-minute periods
OPENING_QUALITY_WINDOW_MINUTES = INITIAL_BALANCE_MINUTES  # gaps in [08:30, 09:30) qualify opening facts


class Side(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    NONE = "NONE"


class ExtremeOrder(StrEnum):
    HIGH_FIRST = "HIGH_FIRST"  # the window high was first reached before the window low
    LOW_FIRST = "LOW_FIRST"
    NO_RANGE = "NO_RANGE"  # high == low


class RangeLocation(StrEnum):
    ABOVE_PRIOR_RANGE = "ABOVE_PRIOR_RANGE"
    AT_PRIOR_HIGH = "AT_PRIOR_HIGH"
    INSIDE_PRIOR_RANGE = "INSIDE_PRIOR_RANGE"
    AT_PRIOR_LOW = "AT_PRIOR_LOW"
    BELOW_PRIOR_RANGE = "BELOW_PRIOR_RANGE"


class ValueLocation(StrEnum):
    ABOVE_PRIOR_VALUE = "ABOVE_PRIOR_VALUE"
    AT_PRIOR_VAH = "AT_PRIOR_VAH"
    INSIDE_PRIOR_VALUE = "INSIDE_PRIOR_VALUE"
    AT_PRIOR_VAL = "AT_PRIOR_VAL"
    BELOW_PRIOR_VALUE = "BELOW_PRIOR_VALUE"


class GapExtent(StrEnum):
    BEYOND_PRIOR_RANGE = "BEYOND_PRIOR_RANGE"  # open strictly above prior high or below prior low
    WITHIN_PRIOR_RANGE = "WITHIN_PRIOR_RANGE"  # prior low <= open <= prior high


class OpeningQualityGrade(StrEnum):
    UNQUALIFIED = "UNQUALIFIED"
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # facts computed; evidence they may be incomplete
    NOT_AVAILABLE = "NOT_AVAILABLE"  # no trustworthy cash open: facts not computed


class ContextOutcome(StrEnum):
    AVAILABLE = "AVAILABLE"
    NO_PRIOR_PROFILE = "NO_PRIOR_PROFILE"
    CONTRACT_CHANGED = "CONTRACT_CHANGED"
    PRIOR_PROFILE_INCOMPLETE = "PRIOR_PROFILE_INCOMPLETE"
    MULTIPLE_PRIOR_DATASETS = "MULTIPLE_PRIOR_DATASETS"
    CURRENT_OPEN_INCOMPLETE = "CURRENT_OPEN_INCOMPLETE"


# --- prior trading date ----------------------------------------------------------------------

def prior_trading_date(trading_date: date, closures: frozenset[date] = frozenset()) -> date:
    """The previous weekday not in `closures` (full CME closures, supplied explicitly).

    Ordinary schedule only: no holiday calendar is modelled, so a full-closure date
    must be passed in. Early-close days (e.g. Labor Day) are trading dates.
    """
    day = trading_date - timedelta(days=1)
    while day.weekday() >= 5 or day in closures:
        day -= timedelta(days=1)
    return day


# --- current-day facts -------------------------------------------------------------------------

@dataclass(frozen=True)
class PathPoint:
    """One price change on the cash-window tape: the first trade at a new tick."""

    timestamp_utc: datetime
    tick: int
    price: Decimal


@dataclass(frozen=True)
class CashOpen:
    cash_open_utc: datetime  # 08:30:00 America/Chicago for the trading date
    max_delay: timedelta
    price: Decimal | None  # first eligible on-grid trade at/after 08:30 within max_delay
    tick: int | None
    timestamp_utc: datetime | None
    delay: timedelta | None  # timestamp - 08:30:00 CT
    unavailable_reason: str | None


@dataclass(frozen=True)
class OpeningQuality:
    grade: OpeningQualityGrade
    reasons: tuple[str, ...]
    opening_window_end_utc: datetime
    known_gaps_in_opening_window: int
    suspected_gaps_in_opening_window: int
    gaps_later_in_study_window: int  # affect full-window entry/exit facts only
    study_window_truncated: bool | None  # capture ended before 15:00 CT; None = capture not recorded


@dataclass(frozen=True)
class OpeningWindowFacts:
    """Facts over [08:30, 08:30 + minutes) from the open print on."""

    minutes: int
    end_utc: datetime
    high: Decimal
    low: Decimal
    range_ticks: int
    last_price: Decimal
    excursion_up_ticks: int  # high - open
    excursion_down_ticks: int  # open - low
    dominant: DominantExtension
    larger_excursion_ticks: int
    smaller_excursion_ticks: int
    counter_to_dominant: Decimal | None  # smaller / larger; None when both are 0
    first_direction: Side  # side of the first trade away from the open
    first_above_open_utc: datetime | None
    first_below_open_utc: datetime | None
    time_of_high_utc: datetime  # first reached
    time_of_low_utc: datetime
    extreme_order: ExtremeOrder
    traded_above_open: bool
    traded_below_open: bool
    first_open_revisit_utc: datetime | None
    first_open_cross_utc: datetime | None
    open_cross_count: int
    up_first_then_crossed_below: bool
    down_first_then_crossed_above: bool


@dataclass(frozen=True)
class ExtremeFollowThrough:
    """What followed the period-A high (or low), through the end of the IB. No 'rejection' label."""

    extreme: str  # "A_HIGH" or "A_LOW"
    price: Decimal
    reached_utc: datetime
    horizon_end_utc: datetime
    max_move_away_ticks: int  # largest distance back from the extreme after it was reached
    crossed_open_after: bool  # traded strictly on the other side of the open afterwards
    first_open_cross_after_utc: datetime | None
    time_to_open_cross: timedelta | None
    opposite_excursion_beyond_open_ticks: int  # how far past the open, on the other side


@dataclass(frozen=True)
class EarlyTpo:
    a_high: Decimal | None
    a_low: Decimal | None
    a_range_ticks: int | None
    a_rows: int | None
    b_high: Decimal | None
    b_low: Decimal | None
    b_rows: int | None
    ab_overlap_rows: int | None  # grid rows printed by both A and B
    ab_overlap_ratio: Decimal | None  # overlap rows / rows of the smaller of A, B
    ab_high: Decimal | None
    ab_low: Decimal | None
    ab_range_ticks: int | None
    a_rows_above_b: int | None  # A-only rows of the A+B profile
    a_rows_below_b: int | None
    b_high_above_a: bool | None
    b_low_below_a: bool | None
    a_only_rows_full_day: int | None  # rows whose only letter at the close is A
    a_only_rows_at_day_high: int | None  # contiguous A-only rows down from the profile high
    a_only_rows_at_day_low: int | None


@dataclass(frozen=True)
class OneTimeframing:
    first_higher_low_period: str | None  # first period whose low > the previous period's low
    first_lower_high_period: str | None
    opening_higher_low_run: int  # periods from A, each low > the previous (A counts 1)
    opening_lower_high_run: int
    longest_higher_low_run: int  # 0Y-C fact, by reference
    longest_lower_high_run: int


@dataclass(frozen=True)
class CashOpenSession:
    policy_id: str
    trading_date: date
    price_increment: Decimal
    a_end_utc: datetime  # end of period A (the first TPO period)
    cash_open: CashOpen
    quality: OpeningQuality
    path: tuple[PathPoint, ...]  # whole study window, from the open print; empty if no open
    windows: tuple[OpeningWindowFacts, ...]
    a_extremes: tuple[ExtremeFollowThrough, ...]
    early_tpo: EarlyTpo
    one_timeframing: OneTimeframing

    @property
    def available(self) -> bool:
        return self.quality.grade is not OpeningQualityGrade.NOT_AVAILABLE

    def window(self, minutes: int) -> OpeningWindowFacts | None:
        return next((w for w in self.windows if w.minutes == minutes), None)


def cash_open_utc(trading_date: date) -> datetime:
    """08:30:00 America/Chicago on the trading date (DST-correct; no fixed UTC offset)."""
    return resolve_anchor(AnchorKind.US_CASH_OPEN, trading_date).anchor_timestamp_utc


def build_cash_open_session(
    trades,
    profile: TpoProfile,
    facts: DayStructureFacts,
    grid: PriceGrid,
    capture_started_at: datetime | None,
    capture_ended_at: datetime | None,
    gap_intervals: tuple[tuple[str, datetime, datetime], ...],
    lifecycle_state: str | None,
) -> CashOpenSession:
    """`trades` = the cash-window effective tape; `gap_intervals` = (KNOWN_GAP|SUSPECTED_GAP, start, end)."""
    if profile.window != US_CASH_PROFILE:
        raise ValueError("Opening facts are defined for the US_CASH_PROFILE study window only.")
    open_utc = cash_open_utc(profile.trading_date)
    if open_utc != profile.start_utc:
        raise ValueError("Study window does not start at the cash open.")
    points = _path(trades, grid, open_utc, profile.end_utc)
    cash_open = _cash_open(open_utc, points)
    quality = _opening_quality(open_utc, profile.end_utc, cash_open, capture_started_at, capture_ended_at,
                               gap_intervals, lifecycle_state)
    if quality.grade is OpeningQualityGrade.NOT_AVAILABLE:
        points = ()
    windows, extremes = (), ()
    if points:
        windows = tuple(_window(points, open_utc, m) for m in OPENING_WINDOW_MINUTES)
        extremes = _a_extremes(points, profile, open_utc + timedelta(minutes=INITIAL_BALANCE_MINUTES), grid)
    return CashOpenSession(
        policy_id=OPENING_FACTS_POLICY_ID,
        trading_date=profile.trading_date,
        price_increment=grid.tick_size,
        a_end_utc=profile.periods[0].end_utc,
        cash_open=cash_open,
        quality=quality,
        path=points,
        windows=windows,
        a_extremes=extremes,
        early_tpo=_early_tpo(profile, grid),
        one_timeframing=_one_timeframing(profile, facts),
    )


def _path(trades, grid: PriceGrid, start: datetime, end: datetime) -> tuple[PathPoint, ...]:
    """On-grid trades in [start, end), ordered by (timestamp, tape position), reduced to price changes."""
    rows = []
    for position, trade in enumerate(trades):
        ts = trade.event_timestamp
        if start <= ts < end:
            tick = grid.tick_index(trade.price)
            if tick is not None:
                rows.append((ts, position, tick))
    rows.sort()
    out: list[PathPoint] = []
    for ts, _, tick in rows:
        if not out or out[-1].tick != tick:
            out.append(PathPoint(ts, tick, grid.price_at(tick)))
    return tuple(out)


def _cash_open(open_utc: datetime, points: tuple[PathPoint, ...]) -> CashOpen:
    first = points[0] if points else None
    if first is None or first.timestamp_utc - open_utc > CASH_OPEN_MAX_DELAY:
        reason = ("no eligible trade in the study window" if first is None else
                  f"first eligible trade {first.timestamp_utc - open_utc} after 08:30:00 CT "
                  f"(> {CASH_OPEN_MAX_DELAY})")
        return CashOpen(open_utc, CASH_OPEN_MAX_DELAY, None, None, None, None, reason)
    return CashOpen(open_utc, CASH_OPEN_MAX_DELAY, first.price, first.tick, first.timestamp_utc,
                    first.timestamp_utc - open_utc, None)


def _opening_quality(open_utc, window_end, cash_open, started, ended, gap_intervals, lifecycle) -> OpeningQuality:
    q_end = open_utc + timedelta(minutes=OPENING_QUALITY_WINDOW_MINUTES)
    known = sum(1 for kind, s, e in gap_intervals if kind == "KNOWN_GAP" and s < q_end and e > open_utc)
    suspected = sum(1 for kind, s, e in gap_intervals if kind == "SUSPECTED_GAP" and s < q_end and e > open_utc)
    later = sum(1 for _, s, e in gap_intervals if s < window_end and e > q_end)
    truncated = None if started is None or ended is None else ended < window_end
    blockers, reasons = [], []
    if started is not None and ended is not None:
        if started > open_utc or ended < q_end:
            blockers.append("opening window [08:30, 09:30) CT not fully captured")
    else:
        reasons.append("capture interval not recorded; 08:30 opening coverage unverified")
    if cash_open.price is None:
        blockers.append(cash_open.unavailable_reason)
    if known:
        reasons.append(f"KNOWN_GAP overlaps the opening window: {known}")
    if suspected:
        reasons.append(f"SUSPECTED_GAP overlaps the opening window: {suspected}")
    if lifecycle != "FINALIZED":
        reasons.append(f"lifecycle {lifecycle or 'UNTRACKED'} (not FINALIZED)")
    if blockers:
        grade, reasons = OpeningQualityGrade.NOT_AVAILABLE, blockers + reasons
    else:
        grade = OpeningQualityGrade.QUALITY_QUALIFIED if reasons else OpeningQualityGrade.UNQUALIFIED
    return OpeningQuality(grade, tuple(reasons), q_end, known, suspected, later, truncated)


def _sign(value: int) -> int:
    return (value > 0) - (value < 0)


def _crossings(points, ref_tick: int) -> list[datetime]:
    """Timestamps of every strict-side change relative to `ref_tick` (see module docstring)."""
    side, out = 0, []
    for p in points:
        s = _sign(p.tick - ref_tick)
        if s == 0:
            continue
        if side and s != side:
            out.append(p.timestamp_utc)
        side = s
    return out


def _dominance(up: int, down: int) -> DominantExtension:
    if up > down:
        return DominantExtension.UP
    if down > up:
        return DominantExtension.DOWN
    return DominantExtension.TIE if up else DominantExtension.NONE


def _ratio(numerator, denominator) -> Decimal | None:
    return None if not denominator else Decimal(numerator) / Decimal(denominator)


def _window(points: tuple[PathPoint, ...], open_utc: datetime, minutes: int) -> OpeningWindowFacts:
    end = open_utc + timedelta(minutes=minutes)
    pts = [p for p in points if p.timestamp_utc < end]
    o = pts[0].tick
    hi = max(p.tick for p in pts)
    lo = min(p.tick for p in pts)
    hi_at = next(p.timestamp_utc for p in pts if p.tick == hi)
    lo_at = next(p.timestamp_utc for p in pts if p.tick == lo)
    up, down = hi - o, o - lo
    first_away = next((p for p in pts if p.tick != o), None)
    first_dir = Side.NONE if first_away is None else Side.UP if first_away.tick > o else Side.DOWN
    crosses = _crossings(pts, o)
    revisit = next((p.timestamp_utc for p in pts[1:] if p.tick == o), None)
    return OpeningWindowFacts(
        minutes=minutes,
        end_utc=end,
        high=_price(pts, hi),
        low=_price(pts, lo),
        range_ticks=hi - lo,
        last_price=pts[-1].price,
        excursion_up_ticks=up,
        excursion_down_ticks=down,
        dominant=_dominance(up, down),
        larger_excursion_ticks=max(up, down),
        smaller_excursion_ticks=min(up, down),
        counter_to_dominant=_ratio(min(up, down), max(up, down)),
        first_direction=first_dir,
        first_above_open_utc=next((p.timestamp_utc for p in pts if p.tick > o), None),
        first_below_open_utc=next((p.timestamp_utc for p in pts if p.tick < o), None),
        time_of_high_utc=hi_at,
        time_of_low_utc=lo_at,
        extreme_order=(ExtremeOrder.NO_RANGE if hi == lo else
                       ExtremeOrder.HIGH_FIRST if hi_at < lo_at else ExtremeOrder.LOW_FIRST),
        traded_above_open=up > 0,
        traded_below_open=down > 0,
        first_open_revisit_utc=revisit,
        first_open_cross_utc=crosses[0] if crosses else None,
        open_cross_count=len(crosses),
        up_first_then_crossed_below=first_dir is Side.UP and bool(crosses),
        down_first_then_crossed_above=first_dir is Side.DOWN and bool(crosses),
    )


def _price(pts, tick: int) -> Decimal:
    return next(p.price for p in pts if p.tick == tick)


def _a_extremes(points, profile: TpoProfile, horizon_end: datetime, grid: PriceGrid) -> tuple[ExtremeFollowThrough, ...]:
    a = profile.periods[0]
    if not a.trade_count:
        return ()
    o = points[0].tick
    out = []
    for name, price, sign in (("A_HIGH", a.high, 1), ("A_LOW", a.low, -1)):
        tick = grid.tick_index(price)
        reached = next(p for p in points if p.tick == tick and p.timestamp_utc < a.end_utc)
        after = [p for p in points if reached.timestamp_utc < p.timestamp_utc < horizon_end]
        away = max((sign * (tick - p.tick) for p in after), default=0)
        cross = next((p.timestamp_utc for p in after if sign * (p.tick - o) < 0), None)
        beyond = max((sign * (o - p.tick) for p in after), default=0)
        out.append(ExtremeFollowThrough(
            extreme=name, price=price, reached_utc=reached.timestamp_utc, horizon_end_utc=horizon_end,
            max_move_away_ticks=max(away, 0), crossed_open_after=cross is not None,
            first_open_cross_after_utc=cross,
            time_to_open_cross=None if cross is None else cross - reached.timestamp_utc,
            opposite_excursion_beyond_open_ticks=max(beyond, 0)))
    return tuple(out)


def _early_tpo(profile: TpoProfile, grid: PriceGrid) -> EarlyTpo:
    a = profile.periods[0]
    b = profile.periods[1] if len(profile.periods) > 1 else None
    if not a.trade_count:
        return EarlyTpo(*([None] * 19))
    t = grid.tick_index
    ah, al = t(a.high), t(a.low)
    a_only = [lv.periods == "A" for lv in profile.levels]
    top = next((i for i, flag in enumerate(reversed(a_only)) if not flag), len(a_only))
    bottom = next((i for i, flag in enumerate(a_only) if not flag), len(a_only))
    base = dict(a_high=a.high, a_low=a.low, a_range_ticks=ah - al, a_rows=ah - al + 1,
                a_only_rows_full_day=sum(a_only), a_only_rows_at_day_high=top, a_only_rows_at_day_low=bottom)
    if b is None or not b.trade_count:
        return EarlyTpo(**base, b_high=None, b_low=None, b_rows=None, ab_overlap_rows=None, ab_overlap_ratio=None,
                        ab_high=None, ab_low=None, ab_range_ticks=None, a_rows_above_b=None, a_rows_below_b=None,
                        b_high_above_a=None, b_low_below_a=None)
    bh, bl = t(b.high), t(b.low)
    overlap = max(0, min(ah, bh) - max(al, bl) + 1)
    return EarlyTpo(
        **base, b_high=b.high, b_low=b.low, b_rows=bh - bl + 1, ab_overlap_rows=overlap,
        ab_overlap_ratio=Decimal(overlap) / Decimal(min(ah - al, bh - bl) + 1),
        ab_high=max(a.high, b.high), ab_low=min(a.low, b.low), ab_range_ticks=max(ah, bh) - min(al, bl),
        a_rows_above_b=max(0, ah - max(bh, al - 1)), a_rows_below_b=max(0, min(bl, ah + 1) - al),
        b_high_above_a=bh > ah, b_low_below_a=bl < al)


def _one_timeframing(profile: TpoProfile, facts: DayStructureFacts) -> OneTimeframing:
    traded = [p for p in profile.periods if p.trade_count]
    first_hl = first_lh = None
    for prev, cur in zip(profile.periods, profile.periods[1:]):
        if prev.trade_count and cur.trade_count:
            if first_hl is None and cur.low > prev.low:
                first_hl = cur.label
            if first_lh is None and cur.high < prev.high:
                first_lh = cur.label
    return OneTimeframing(
        first_higher_low_period=first_hl,
        first_lower_high_period=first_lh,
        opening_higher_low_run=_opening_run(profile, lambda p, c: c.low > p.low) if traded else 0,
        opening_lower_high_run=_opening_run(profile, lambda p, c: c.high < p.high) if traded else 0,
        longest_higher_low_run=facts.longest_higher_low_run,
        longest_lower_high_run=facts.longest_lower_high_run,
    )


def _opening_run(profile: TpoProfile, step_holds) -> int:
    periods = profile.periods
    if not periods[0].trade_count:
        return 0
    run = 1
    for prev, cur in zip(periods, periods[1:]):
        if not cur.trade_count or not step_holds(prev, cur):
            break
        run += 1
    return run


# --- prior context ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PriorContext:
    outcome: ContextOutcome
    reasons: tuple[str, ...]
    expected_prior_date: date
    current_contract: str
    prior_trading_date: date | None = None
    prior_dataset_id: str | None = None
    prior_contract: str | None = None
    same_contract: bool | None = None
    profile_high: Decimal | None = None
    profile_low: Decimal | None = None
    poc: Decimal | None = None
    value_area_high: Decimal | None = None
    value_area_low: Decimal | None = None
    ib_high: Decimal | None = None
    ib_low: Decimal | None = None
    terminal_price: Decimal | None = None
    day_type_outcome: str | None = None
    day_type: str | None = None
    day_type_direction: str | None = None
    strength: DayStructureStrength | None = None
    quality_grade: QualityGrade | None = None  # the prior day's 0Y-C classification quality
    quality_reasons: tuple[str, ...] = ()
    dataset_quality: str | None = None

    @property
    def usable(self) -> bool:
        return self.outcome is ContextOutcome.AVAILABLE


# --- joined facts ----------------------------------------------------------------------------

@dataclass(frozen=True)
class ReferenceInteraction:
    reference: str  # PRIOR_HIGH, PRIOR_LOW, PRIOR_VAH, PRIOR_VAL, PRIOR_POC, CASH_OPEN
    price: Decimal
    horizon_minutes: int
    open_offset_ticks: int  # open - reference
    min_distance_ticks: int
    touched: bool
    first_touch_utc: datetime | None
    crossed: bool
    first_cross_utc: datetime | None


@dataclass(frozen=True)
class ZoneInteraction:
    """Prior value area or prior range [low, high], inclusive, over the whole study window."""

    zone: str  # PRIOR_VALUE or PRIOR_RANGE
    low: Decimal
    high: Decimal
    open_inside: bool
    first_entry_utc: datetime | None  # open outside only
    first_exit_above_utc: datetime | None  # open inside only
    first_exit_below_utc: datetime | None
    first_return_utc: datetime | None  # first trade back inside after the first exit
    time_to_return: timedelta | None
    seconds_inside_during_a: Decimal  # last-trade-price time inside, from the open print to A end
    a_seconds_observed: Decimal
    a_rows_inside: int  # rows of period A's range inside the zone
    a_rows: int


@dataclass(frozen=True)
class OpeningAuctionFacts:
    policy_id: str
    session: CashOpenSession
    prior: PriorContext
    outcome: ContextOutcome
    reasons: tuple[str, ...]
    # None unless outcome is AVAILABLE
    range_location: RangeLocation | None = None
    value_location: ValueLocation | None = None
    open_vs_prior_high_ticks: int | None = None  # open - prior high (signed)
    open_vs_prior_low_ticks: int | None = None
    open_vs_vah_ticks: int | None = None
    open_vs_val_ticks: int | None = None
    open_vs_poc_ticks: int | None = None
    open_vs_vah_points: Decimal | None = None
    open_vs_val_points: Decimal | None = None
    open_vs_poc_points: Decimal | None = None
    gap_points: Decimal | None = None  # open - prior terminal
    gap_ticks: int | None = None
    gap_direction: Side | None = None
    gap_extent: GapExtent | None = None
    reference_interactions: tuple[ReferenceInteraction, ...] = ()  # cash open always when the open exists
    value_zone: ZoneInteraction | None = None
    range_zone: ZoneInteraction | None = None


def build_opening_auction_facts(session: CashOpenSession, prior: PriorContext) -> OpeningAuctionFacts:
    if not session.available:
        return OpeningAuctionFacts(OPENING_FACTS_POLICY_ID, session, prior, ContextOutcome.CURRENT_OPEN_INCOMPLETE,
                                   session.quality.reasons)
    open_refs = _interactions(session, (("CASH_OPEN", session.cash_open.price),))
    if not prior.usable:
        return OpeningAuctionFacts(OPENING_FACTS_POLICY_ID, session, prior, prior.outcome, prior.reasons,
                                   reference_interactions=open_refs)
    inc, o = session.price_increment, session.cash_open.price
    ticks = _ticks(inc)
    refs = (("PRIOR_HIGH", prior.profile_high), ("PRIOR_LOW", prior.profile_low), ("PRIOR_VAH", prior.value_area_high),
            ("PRIOR_VAL", prior.value_area_low), ("PRIOR_POC", prior.poc))
    gap = o - prior.terminal_price
    return OpeningAuctionFacts(
        policy_id=OPENING_FACTS_POLICY_ID,
        session=session,
        prior=prior,
        outcome=ContextOutcome.AVAILABLE,
        reasons=prior.reasons,
        range_location=_locate(o, prior.profile_low, prior.profile_high, RangeLocation),
        value_location=_locate(o, prior.value_area_low, prior.value_area_high, ValueLocation),
        open_vs_prior_high_ticks=ticks(o - prior.profile_high),
        open_vs_prior_low_ticks=ticks(o - prior.profile_low),
        open_vs_vah_ticks=ticks(o - prior.value_area_high),
        open_vs_val_ticks=ticks(o - prior.value_area_low),
        open_vs_poc_ticks=ticks(o - prior.poc),
        open_vs_vah_points=o - prior.value_area_high,
        open_vs_val_points=o - prior.value_area_low,
        open_vs_poc_points=o - prior.poc,
        gap_points=gap,
        gap_ticks=ticks(gap),
        gap_direction=Side.UP if gap > 0 else Side.DOWN if gap < 0 else Side.NONE,
        gap_extent=(GapExtent.BEYOND_PRIOR_RANGE if o > prior.profile_high or o < prior.profile_low
                    else GapExtent.WITHIN_PRIOR_RANGE),
        reference_interactions=_interactions(session, refs) + open_refs,
        value_zone=_zone(session, "PRIOR_VALUE", prior.value_area_low, prior.value_area_high),
        range_zone=_zone(session, "PRIOR_RANGE", prior.profile_low, prior.profile_high),
    )


def _ticks(inc: Decimal):
    def convert(points: Decimal) -> int:
        value = points / inc
        if value != value.to_integral_value():
            raise ValueError(f"{points} is not a whole number of {inc} ticks")
        return int(value)
    return convert


def _locate(price: Decimal, low: Decimal, high: Decimal, kind):
    names = list(kind)  # above, at high, inside, at low, below
    if price > high:
        return names[0]
    if price == high:
        return names[1]
    if price > low:
        return names[2]
    if price == low:
        return names[3]
    return names[4]


def _interactions(session: CashOpenSession, refs) -> tuple[ReferenceInteraction, ...]:
    inc, o = session.price_increment, session.cash_open.tick
    out = []
    for name, price in refs:
        ref = int(price / inc)
        for minutes in OPENING_WINDOW_MINUTES:
            end = session.cash_open.cash_open_utc + timedelta(minutes=minutes)
            pts = [p for p in session.path if p.timestamp_utc < end]
            crosses = _crossings(pts, ref)
            touch = next((p.timestamp_utc for p in pts if p.tick == ref), None)
            out.append(ReferenceInteraction(
                reference=name, price=price, horizon_minutes=minutes, open_offset_ticks=o - ref,
                min_distance_ticks=min(abs(p.tick - ref) for p in pts), touched=touch is not None,
                first_touch_utc=touch, crossed=bool(crosses), first_cross_utc=crosses[0] if crosses else None))
    return tuple(out)


def _zone(session: CashOpenSession, name: str, low: Decimal, high: Decimal) -> ZoneInteraction:
    inc, path = session.price_increment, session.path
    lo, hi = int(low / inc), int(high / inc)
    inside = [lo <= p.tick <= hi for p in path]
    open_inside = inside[0]
    entry = exit_above = exit_below = ret = None
    if not open_inside:
        entry = next((p.timestamp_utc for p, ok in zip(path, inside) if ok), None)
    else:
        exit_above = next((p.timestamp_utc for p in path if p.tick > hi), None)
        exit_below = next((p.timestamp_utc for p in path if p.tick < lo), None)
        first_exit = min((t for t in (exit_above, exit_below) if t is not None), default=None)
        if first_exit is not None:
            ret = next((p.timestamp_utc for p, ok in zip(path, inside) if ok and p.timestamp_utc > first_exit), None)
    a_end = session.a_end_utc
    seconds = observed = Decimal(0)
    for i, p in enumerate(path):
        if p.timestamp_utc >= a_end:
            break
        until = min(path[i + 1].timestamp_utc, a_end) if i + 1 < len(path) else a_end
        span = Decimal(str((until - p.timestamp_utc).total_seconds()))
        observed += span
        if inside[i]:
            seconds += span
    et = session.early_tpo
    if et.a_high is None:
        a_rows_inside, a_rows = 0, 0
    else:
        ah, al = int(et.a_high / inc), int(et.a_low / inc)
        a_rows_inside, a_rows = max(0, min(ah, hi) - max(al, lo) + 1), ah - al + 1
    return ZoneInteraction(
        zone=name, low=low, high=high, open_inside=open_inside, first_entry_utc=entry,
        first_exit_above_utc=exit_above, first_exit_below_utc=exit_below, first_return_utc=ret,
        time_to_return=None if ret is None else ret - min(t for t in (exit_above, exit_below) if t is not None),
        seconds_inside_during_a=seconds, a_seconds_observed=observed, a_rows_inside=a_rows_inside, a_rows=a_rows)


# --- text rendering ----------------------------------------------------------------------------

def _t(ts: datetime | None) -> str:
    return "--" if ts is None else ts.strftime("%H:%M:%S.%f")[:-3] + "Z"


def _r(value: Decimal | None) -> str:
    return "undefined" if value is None else str(value.quantize(Decimal("0.0001")))


def _yn(value: bool | None) -> str:
    return "--" if value is None else ("yes" if value else "no")


def render_opening_facts(facts: OpeningAuctionFacts) -> list[str]:
    """Numbers and exact tick-grid facts only; never an opening-type name or interpretation."""
    s, p, co = facts.session, facts.prior, facts.session.cash_open
    lines = [f"OPENING AUCTION FACTS ({facts.policy_id}):"]
    q = s.quality
    if q.grade is OpeningQualityGrade.NOT_AVAILABLE:
        lines.append("  *** OPENING FACTS NOT AVAILABLE ***")
    elif q.grade is OpeningQualityGrade.QUALITY_QUALIFIED:
        lines.append("  *** OPENING FACTS ARE QUALITY-QUALIFIED ***")
    lines += [f"    - {reason}" for reason in q.reasons]
    lines.append(f"  Current-day opening quality: {q.grade.value}   (opening window to {_t(q.opening_window_end_utc)}; "
                 f"KNOWN_GAP {q.known_gaps_in_opening_window}, SUSPECTED_GAP {q.suspected_gaps_in_opening_window}; "
                 f"gaps later in the study window {q.gaps_later_in_study_window}; study window truncated "
                 f"{_yn(q.study_window_truncated)})")
    lines.append(f"  Cash open (08:30:00 CT = {_t(co.cash_open_utc)}): "
                 + (f"{co.price} at {_t(co.timestamp_utc)}, delay {co.delay.total_seconds():.3f}s "
                    f"(max {co.max_delay.total_seconds():.0f}s; first eligible on-grid trade)"
                    if co.price is not None else f"none -- {co.unavailable_reason}"))
    lines.append(f"  Prior context: {facts.outcome.value}   expected prior trading date {p.expected_prior_date}")
    lines += [f"    - {reason}" for reason in facts.reasons]
    if p.prior_trading_date is not None:
        lines.append(f"    prior dataset {p.prior_dataset_id}  contract {p.prior_contract} vs current "
                     f"{p.current_contract} (same contract: {_yn(p.same_contract)})")
    if p.profile_high is not None and p.same_contract:
        lines += [
            f"    prior range {p.profile_low}-{p.profile_high}   value {p.value_area_low}-{p.value_area_high}   "
            f"POC {p.poc}   IB {p.ib_low}-{p.ib_high}   terminal {p.terminal_price}",
            f"    prior V1 day type {p.day_type or p.day_type_outcome or '--'}"
            + (f" {p.day_type_direction}" if p.day_type_direction else "")
            + f"; prior quality {p.quality_grade.value if p.quality_grade else '--'}; dataset {p.dataset_quality}",
        ]
    if facts.outcome is ContextOutcome.AVAILABLE:
        lines += [
            f"  Open location: {facts.range_location.value}; {facts.value_location.value}",
            f"    open - prior high {facts.open_vs_prior_high_ticks} ticks; open - prior low "
            f"{facts.open_vs_prior_low_ticks} ticks",
            f"    open - VAH {facts.open_vs_vah_ticks} ticks ({facts.open_vs_vah_points} pts); open - VAL "
            f"{facts.open_vs_val_ticks} ticks ({facts.open_vs_val_points} pts); open - POC {facts.open_vs_poc_ticks} "
            f"ticks ({facts.open_vs_poc_points} pts)",
            f"  Gap (open - prior terminal): {facts.gap_points} pts = {facts.gap_ticks} ticks, "
            f"{facts.gap_direction.value}, {facts.gap_extent.value}",
        ]
    if not s.available:
        lines += ["  No opening-window, crossing or reference facts are computed.", ""]
        return lines
    lines.append("  Opening windows (from the open print; [08:30, 08:30+N)):")
    lines.append("     N  high       low        rng  last       up  dn  dominant c/d     first  hi-time        "
                 "lo-time        order       revisit        crosses  1st-cross")
    for w in s.windows:
        lines.append(
            f"    {w.minutes:>2}  {str(w.high):<9}  {str(w.low):<9}  {w.range_ticks:>3}  {str(w.last_price):<9}  "
            f"{w.excursion_up_ticks:>2}  {w.excursion_down_ticks:>2}  {w.dominant.value:<8} {_r(w.counter_to_dominant):<7}"
            f"  {w.first_direction.value:<5}  {_t(w.time_of_high_utc)}  {_t(w.time_of_low_utc)}  "
            f"{w.extreme_order.value:<10}  {_t(w.first_open_revisit_utc):<13}  {w.open_cross_count:>7}  "
            f"{_t(w.first_open_cross_utc)}")
    w60 = s.window(60)
    lines.append(f"  Path order (60 min): first above open {_t(w60.first_above_open_utc)}, first below open "
                 f"{_t(w60.first_below_open_utc)}; up first then crossed below: "
                 f"{_yn(w60.up_first_then_crossed_below)}; down first then crossed above: "
                 f"{_yn(w60.down_first_then_crossed_above)}")
    for x in s.a_extremes:
        lines.append(f"  {x.extreme} {x.price} at {_t(x.reached_utc)}: max move away {x.max_move_away_ticks} ticks; "
                     f"crossed open after: {_yn(x.crossed_open_after)}"
                     + (f" at {_t(x.first_open_cross_after_utc)} (+{x.time_to_open_cross.total_seconds():.3f}s)"
                        if x.crossed_open_after else "")
                     + f"; beyond open on the other side {x.opposite_excursion_beyond_open_ticks} ticks "
                     f"(to {_t(x.horizon_end_utc)})")
    lines.append("  Reference interactions (min distance ticks / touched / crossed, per horizon; "
                 "first touch / first cross over 60 min):")
    for name in dict.fromkeys(r.reference for r in facts.reference_interactions):
        rows = [r for r in facts.reference_interactions if r.reference == name]
        last = rows[-1]
        cells = "  ".join(f"{r.horizon_minutes}m {r.min_distance_ticks}/{_yn(r.touched)}/{_yn(r.crossed)}" for r in rows)
        lines.append(f"    {name:<10} {str(last.price):<9} open{last.open_offset_ticks:+d}t  {cells}  "
                     f"touch {_t(last.first_touch_utc)}  cross {_t(last.first_cross_utc)}")
    for z in (facts.value_zone, facts.range_zone):
        if z is None:
            continue
        if z.open_inside:
            move = (f"opened inside; first exit above {_t(z.first_exit_above_utc)}, below {_t(z.first_exit_below_utc)}"
                    f"; first return {_t(z.first_return_utc)}"
                    + (f" (+{z.time_to_return.total_seconds():.3f}s)" if z.time_to_return is not None else ""))
        else:
            move = f"opened outside; first entry {_t(z.first_entry_utc)}"
        lines.append(f"  {z.zone} {z.low}-{z.high}: {move}; inside during A {z.seconds_inside_during_a:.3f}s of "
                     f"{z.a_seconds_observed:.3f}s; A rows inside {z.a_rows_inside}/{z.a_rows}")
    e, ot = s.early_tpo, s.one_timeframing
    lines.append(f"  Early TPO: A {e.a_low}-{e.a_high} ({e.a_range_ticks} ticks, {e.a_rows} rows); "
                 + (f"B {e.b_low}-{e.b_high} ({e.b_rows} rows); A/B overlap {e.ab_overlap_rows} rows = "
                    f"{_r(e.ab_overlap_ratio)} of the smaller; A+B {e.ab_low}-{e.ab_high} ({e.ab_range_ticks} ticks); "
                    f"A-only vs B: {e.a_rows_above_b} above, {e.a_rows_below_b} below; B beyond A: high "
                    f"{_yn(e.b_high_above_a)}, low {_yn(e.b_low_below_a)}" if e.b_rows is not None else "B: no trades"))
    lines.append(f"    A-only rows at the close: {e.a_only_rows_full_day} (contiguous at day high "
                 f"{e.a_only_rows_at_day_high}, at day low {e.a_only_rows_at_day_low})")
    lines.append(f"  One-timeframing: first higher low {ot.first_higher_low_period or 'none'}, first lower high "
                 f"{ot.first_lower_high_period or 'none'}; run from A: higher lows {ot.opening_higher_low_run}, "
                 f"lower highs {ot.opening_lower_high_run}; longest: {ot.longest_higher_low_run} / "
                 f"{ot.longest_lower_high_run}")
    lines += ["  Facts only: no opening type, acceptance/rejection, bias or signal.", ""]
    return lines


def render_early_matrix(facts: OpeningAuctionFacts, profile: TpoProfile) -> list[str]:
    """A and B letters only, over the A+B range, with the open and prior references marked."""
    e = facts.session.early_tpo
    if e.a_high is None:
        return []
    high = e.ab_high if e.ab_high is not None else e.a_high
    low = e.ab_low if e.ab_low is not None else e.a_low
    p = facts.prior
    marks = {}
    if facts.session.cash_open.price is not None:
        marks.setdefault(facts.session.cash_open.price, []).append("OPEN")
    if facts.outcome is ContextOutcome.AVAILABLE:
        for tag, price in (("pH", p.profile_high), ("pVAH", p.value_area_high), ("pPOC", p.poc),
                           ("pVAL", p.value_area_low), ("pL", p.profile_low)):
            marks.setdefault(price, []).append(tag)
    lines = ["  Early TPO matrix (A/B letters only; p* = prior-day reference):"]
    for level in reversed(profile.levels):
        if low <= level.price <= high:
            letters = "".join(c for c in level.periods if c in "AB")
            lines.append(f"    {str(level.price):>9}  {letters:<2}  {' '.join(marks.get(level.price, []))}".rstrip())
    outside = [f"{' '.join(tags)} {price}" for price, tags in sorted(marks.items(), reverse=True)
               if not (low <= price <= high)]
    if outside:
        lines.append("    outside the A+B range: " + "; ".join(outside))
    return lines + [""]
