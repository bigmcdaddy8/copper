"""Deterministic TPO / Market Profile over an already-selected trade set (0Y-A).

A TPO (Time-Price Opportunity) records that a price was *available* during a
time period -- not how often it printed or how much volume traded there. For
each period, every profile price level from the period low through the period
high (inclusive) receives exactly one TPO for that period. A price's TPO count
is the number of distinct periods whose range includes it. Trade count and
contract volume never enter the TPO count; they belong to Volume Profile.

Kept deliberately separate from `volume_profile` / `value_area`: TPO shares only
the exact `PriceGrid` (tick-index arithmetic) with them. POC tie-breaking and
Value Area expansion are TPO-specific Laboratory policies (see
docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md). Derived analytics only: this
module reads trades and never mutates source data.
"""
from __future__ import annotations

import string
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from dicks_laboratory.volume_profile import PriceGrid


@dataclass(frozen=True)
class StudyWindow:
    """A Laboratory profile study window in exchange-local wall-clock time, [start, end)."""

    window_id: str
    policy_version: str
    timezone_name: str
    start_local: time
    end_local: time

    @property
    def minutes(self) -> int:
        start = self.start_local.hour * 60 + self.start_local.minute
        end = self.end_local.hour * 60 + self.end_local.minute
        return end - start

    def bounds_utc(self, trading_date: date) -> tuple[datetime, datetime]:
        tz = ZoneInfo(self.timezone_name)
        return (
            datetime.combine(trading_date, self.start_local, tzinfo=tz).astimezone(timezone.utc),
            datetime.combine(trading_date, self.end_local, tzinfo=tz).astimezone(timezone.utc),
        )


# A Laboratory cash-session *study* window -- not the CME Globex trading session,
# which runs 17:00-16:00 CT and remains the dataset's capture scope.
US_CASH_PROFILE = StudyWindow(
    window_id="US_CASH_PROFILE",
    policy_version="US_CASH_PROFILE_V1",
    timezone_name="America/Chicago",
    start_local=time(8, 30),
    end_local=time(15, 0),
)

DEFAULT_PERIOD_MINUTES = 30
INITIAL_BALANCE_MINUTES = 60
DEFAULT_TPO_VALUE_AREA_FRACTION = Decimal("0.70")

# Periods are lettered A-Z then a-z, chronologically from the window start.
PERIOD_LABELS = string.ascii_uppercase + string.ascii_lowercase

# Laboratory policies (no exchange or universal vendor standard exists).
TPO_POC_POLICY_ID = "DICKS_LAB_TPO_POC_POLICY"
TPO_POC_POLICY_VERSION = "V1_MAX_TPO_NEAREST_RANGE_MIDPOINT_THEN_LOWER_PRICE"
TPO_VALUE_AREA_POLICY_ID = "DICKS_LAB_TPO_VALUE_AREA_POLICY"
TPO_VALUE_AREA_POLICY_VERSION = "V1_TWO_ROW_GREATER_SUM_TIE_ABOVE"


@dataclass(frozen=True)
class TpoPeriodSlot:
    index: int
    label: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class TpoPeriod:
    """One period's facts; high/low are None when no eligible trade fell in it."""

    index: int
    label: str
    start_utc: datetime
    end_utc: datetime
    trade_count: int
    high: Decimal | None
    low: Decimal | None


@dataclass(frozen=True)
class TpoLevel:
    price: Decimal
    tpo_count: int
    periods: str  # period labels, chronological, one per period


@dataclass(frozen=True)
class InitialBalance:
    period_labels: str  # periods inside the IB interval that had trades
    high: Decimal
    low: Decimal
    range: Decimal
    extension_above: Decimal  # 0 when no later period traded above IB high
    extension_below: Decimal
    first_extension_above_period: str | None
    first_extension_below_period: str | None


@dataclass(frozen=True)
class TpoValueAreaStep:
    step: int
    side: str  # "POC", "ABOVE" or "BELOW"
    added_prices: tuple[Decimal, ...]
    added_tpos: int
    included_tpos: int


@dataclass(frozen=True)
class TpoValueArea:
    policy_id: str
    policy_version: str
    target_fraction: Decimal
    target_tpos: Decimal
    included_tpos: int
    included_fraction: Decimal
    low: Decimal
    high: Decimal
    trace: tuple[TpoValueAreaStep, ...]


@dataclass(frozen=True)
class TpoProfile:
    """Immutable derived TPO profile; facts only, no interpretation."""

    window: StudyWindow
    trading_date: date
    start_utc: datetime
    end_utc: datetime
    period_minutes: int
    price_increment: Decimal
    price_grid_policy_id: str
    periods: tuple[TpoPeriod, ...]  # every slot in the window, including empty ones
    levels: tuple[TpoLevel, ...]  # ascending, every grid price from low to high
    total_tpo_count: int
    profile_high: Decimal
    profile_low: Decimal
    profile_range: Decimal
    poc: Decimal
    poc_policy_id: str
    poc_policy_version: str
    value_area: TpoValueArea
    initial_balance: InitialBalance | None
    selected_trade_count: int
    invalid_tick_trade_count: int

    @property
    def periods_present(self) -> str:
        return "".join(period.label for period in self.periods if period.trade_count)


def build_period_slots(
    trading_date: date,
    period_minutes: int = DEFAULT_PERIOD_MINUTES,
    window: StudyWindow = US_CASH_PROFILE,
) -> tuple[TpoPeriodSlot, ...]:
    """Lettered half-open periods tiling the study window in local wall-clock time."""
    if period_minutes <= 0:
        raise ValueError("period_minutes must be positive.")
    if window.minutes % period_minutes:
        raise ValueError(f"period_minutes={period_minutes} does not tile the {window.minutes}-minute study window.")
    if INITIAL_BALANCE_MINUTES % period_minutes:
        raise ValueError(f"period_minutes={period_minutes} does not tile the {INITIAL_BALANCE_MINUTES}-minute initial balance.")
    count = window.minutes // period_minutes
    if count > len(PERIOD_LABELS):
        raise ValueError(f"{count} periods exceed the {len(PERIOD_LABELS)} available period labels.")
    tz = ZoneInfo(window.timezone_name)
    start_local = datetime.combine(trading_date, window.start_local, tzinfo=tz)
    step = timedelta(minutes=period_minutes)
    return tuple(
        TpoPeriodSlot(
            index=i,
            label=PERIOD_LABELS[i],
            start_utc=(start_local + i * step).astimezone(timezone.utc),
            end_utc=(start_local + (i + 1) * step).astimezone(timezone.utc),
        )
        for i in range(count)
    )


def build_tpo_profile(
    trades: tuple,
    grid: PriceGrid,
    trading_date: date,
    period_minutes: int = DEFAULT_PERIOD_MINUTES,
    window: StudyWindow = US_CASH_PROFILE,
    target_fraction: Decimal = DEFAULT_TPO_VALUE_AREA_FRACTION,
) -> TpoProfile | None:
    """Build the TPO profile of `trades` inside the study window; None if none are eligible.

    `trades` need only `event_timestamp` (aware UTC) and `price`. Trades outside
    [window start, window end) are ignored; off-grid prices are excluded and counted.
    """
    if not (Decimal("0") < target_fraction <= Decimal("1")):
        raise ValueError("target_fraction must satisfy 0 < fraction <= 1.")
    slots = build_period_slots(trading_date, period_minutes, window)
    start_utc, end_utc = slots[0].start_utc, slots[-1].end_utc
    step = timedelta(minutes=period_minutes)

    highs: dict[int, int] = {}
    lows: dict[int, int] = {}
    counts: dict[int, int] = {}
    invalid = 0
    for trade in trades:
        ts = trade.event_timestamp
        if ts.tzinfo is not timezone.utc:
            raise ValueError("TPO profiling requires timezone-aware UTC timestamps.")
        if not (start_utc <= ts < end_utc):
            continue
        tick = grid.tick_index(trade.price)
        if tick is None:
            invalid += 1
            continue
        # UTC elapsed time equals wall-clock elapsed time inside the window (no DST
        # transition occurs between 08:30 and 15:00 CT), so integer division is exact.
        i = (ts - start_utc) // step
        counts[i] = counts.get(i, 0) + 1
        highs[i] = max(highs.get(i, tick), tick)
        lows[i] = min(lows.get(i, tick), tick)

    if not counts:
        return None

    periods = tuple(
        TpoPeriod(
            index=slot.index, label=slot.label, start_utc=slot.start_utc, end_utc=slot.end_utc,
            trade_count=counts.get(slot.index, 0),
            high=grid.price_at(highs[slot.index]) if slot.index in counts else None,
            low=grid.price_at(lows[slot.index]) if slot.index in counts else None,
        )
        for slot in slots
    )

    low_tick, high_tick = min(lows.values()), max(highs.values())
    letters: dict[int, list[str]] = {tick: [] for tick in range(low_tick, high_tick + 1)}
    for i in sorted(counts):
        for tick in range(lows[i], highs[i] + 1):
            letters[tick].append(PERIOD_LABELS[i])  # one TPO per period per price
    levels = tuple(
        TpoLevel(price=grid.price_at(tick), tpo_count=len(letters[tick]), periods="".join(letters[tick]))
        for tick in range(low_tick, high_tick + 1)
    )
    total = sum(level.tpo_count for level in levels)
    profile_high, profile_low = grid.price_at(high_tick), grid.price_at(low_tick)
    poc_index = resolve_tpo_poc_index(levels, profile_low, profile_high)

    return TpoProfile(
        window=window,
        trading_date=trading_date,
        start_utc=start_utc,
        end_utc=end_utc,
        period_minutes=period_minutes,
        price_increment=grid.tick_size,
        price_grid_policy_id=grid.policy_id,
        periods=periods,
        levels=levels,
        total_tpo_count=total,
        profile_high=profile_high,
        profile_low=profile_low,
        profile_range=profile_high - profile_low,
        poc=levels[poc_index].price,
        poc_policy_id=TPO_POC_POLICY_ID,
        poc_policy_version=TPO_POC_POLICY_VERSION,
        value_area=compute_tpo_value_area(levels, poc_index, target_fraction),
        initial_balance=compute_initial_balance(periods, start_utc + timedelta(minutes=INITIAL_BALANCE_MINUTES)),
        selected_trade_count=sum(counts.values()),
        invalid_tick_trade_count=invalid,
    )


def resolve_tpo_poc_index(levels: tuple[TpoLevel, ...], profile_low: Decimal, profile_high: Decimal) -> int:
    """Highest TPO count; ties -> nearest the profile-range midpoint, then the lower price."""
    best = max(level.tpo_count for level in levels)
    midpoint = (profile_low + profile_high) / 2
    candidates = [i for i, level in enumerate(levels) if level.tpo_count == best]
    return min(candidates, key=lambda i: (abs(levels[i].price - midpoint), levels[i].price))


def compute_tpo_value_area(
    levels: tuple[TpoLevel, ...],
    poc_index: int,
    target_fraction: Decimal = DEFAULT_TPO_VALUE_AREA_FRACTION,
) -> TpoValueArea:
    """Two-row expansion from the POC until included TPOs reach the target.

      1. Seed with the POC row.
      2. While included < target and a row remains: sum the TPOs of the next two
         rows above the region and the next two rows below it (fewer at a profile
         edge). Add the whole pair with the greater sum; if only one side has rows,
         add that side.
      3. Equal sums: add the pair above.
      4. Pairs are never split, so the achieved fraction may exceed the target.
    Rows are every grid price between profile low and high; a zero-TPO row (a
    price gap between non-overlapping periods) contributes 0.
    """
    total = sum(level.tpo_count for level in levels)
    target = Decimal(total) * target_fraction
    lo = hi = poc_index
    included = levels[poc_index].tpo_count
    trace = [TpoValueAreaStep(0, "POC", (levels[poc_index].price,), included, included)]
    while included < target:
        above = levels[hi + 1 : hi + 3]
        below = levels[max(lo - 2, 0) : lo]
        if not above and not below:
            break
        sum_above = sum(level.tpo_count for level in above)
        sum_below = sum(level.tpo_count for level in below)
        if above and (not below or sum_above >= sum_below):
            hi += len(above)
            included += sum_above
            trace.append(TpoValueAreaStep(len(trace), "ABOVE", tuple(lv.price for lv in above), sum_above, included))
        else:
            lo -= len(below)
            included += sum_below
            trace.append(TpoValueAreaStep(len(trace), "BELOW", tuple(lv.price for lv in reversed(below)), sum_below, included))
    return TpoValueArea(
        policy_id=TPO_VALUE_AREA_POLICY_ID,
        policy_version=TPO_VALUE_AREA_POLICY_VERSION,
        target_fraction=target_fraction,
        target_tpos=target,
        included_tpos=included,
        included_fraction=Decimal(included) / Decimal(total),
        low=levels[lo].price,
        high=levels[hi].price,
        trace=tuple(trace),
    )


def compute_initial_balance(periods: tuple[TpoPeriod, ...], ib_end_utc: datetime) -> InitialBalance | None:
    """IB = range of the periods inside [window start, start + 60 min); facts only."""
    ib = [p for p in periods if p.end_utc <= ib_end_utc and p.trade_count]
    if not ib:
        return None
    later = [p for p in periods if p.start_utc >= ib_end_utc and p.trade_count]
    ib_high = max(p.high for p in ib)
    ib_low = min(p.low for p in ib)
    above = [p for p in later if p.high > ib_high]
    below = [p for p in later if p.low < ib_low]
    return InitialBalance(
        period_labels="".join(p.label for p in ib),
        high=ib_high,
        low=ib_low,
        range=ib_high - ib_low,
        extension_above=max((p.high for p in above), default=ib_high) - ib_high,
        extension_below=ib_low - min((p.low for p in below), default=ib_low),
        first_extension_above_period=above[0].label if above else None,
        first_extension_below_period=below[0].label if below else None,
    )
