"""Deterministic Market Profile structural facts over an accepted TPO profile (0Y-B).

A derived layer on top of `tpo_profile.TpoProfile`; it never alters the profile.
Everything here is either an OBSERVED FACT (one-TPO levels and zones, extreme
facts, IB-extension and period range facts) or an explicit, versioned
LABORATORY STRUCTURAL POLICY (the two CANDIDATE labels). Nothing here is a
market interpretation (no day type, no "unfinished auction", no direction).
See docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md §13-§20.

Adjacency is integer row arithmetic: `TpoProfile.levels` holds every grid row
from profile low to high, so consecutive indices are adjacent grid prices. A
zero-TPO row or a row with 2+ TPOs breaks a one-TPO run.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.tpo_profile import INITIAL_BALANCE_MINUTES, PERIOD_LABELS, TpoLevel, TpoProfile

# --- Laboratory structural policies (survey: TPO_MARKET_PROFILE_0YA.md §15) -------
STRUCTURE_POLICY_ID = "DICKS_LAB_TPO_STRUCTURE_POLICY"
STRUCTURE_POLICY_VERSION = "V1_EXCESS_TAIL_GE_2_ROWS_POOR_EXTREME_GE_2_TPOS"
# EXCESS_*_CANDIDATE: the extreme one-TPO run (tail) spans at least this many rows.
EXCESS_MIN_TAIL_LEVELS = 2
# POOR_*_CANDIDATE: at least this many distinct periods printed the exact extreme price.
POOR_EXTREME_MIN_TPOS = 2


class ZoneLocation(StrEnum):
    UPPER_EXTREME = "UPPER_EXTREME"  # touches PROFILE_HIGH
    LOWER_EXTREME = "LOWER_EXTREME"  # touches PROFILE_LOW
    INTERIOR = "INTERIOR"
    ENTIRE_PROFILE = "ENTIRE_PROFILE"  # touches both (every row is one-TPO)


class IbRelation(StrEnum):
    ABOVE_IB = "ABOVE_IB"
    BELOW_IB = "BELOW_IB"
    INSIDE_IB = "INSIDE_IB"
    OVERLAPPING_IB = "OVERLAPPING_IB"
    NO_IB = "NO_IB"


class ValueRelation(StrEnum):
    ABOVE_VAH = "ABOVE_VAH"
    BELOW_VAL = "BELOW_VAL"
    INSIDE_VALUE = "INSIDE_VALUE"
    OVERLAPPING_BOUNDARY = "OVERLAPPING_BOUNDARY"


class CandidateStatus(StrEnum):
    YES = "YES"
    NO = "NO"
    NOT_CLASSIFIED = "NOT_CLASSIFIED"  # fewer than two periods traded: no auction across time


@dataclass(frozen=True)
class OneTpoZone:
    """Adjacent grid rows that each hold exactly one TPO."""

    low: Decimal
    high: Decimal
    level_count: int  # grid rows in the zone
    tick_count: int  # ticks covered; equals level_count because V1 rows are instrument ticks
    span_points: Decimal  # high - low (0 for a one-row zone)
    periods: str  # distinct period letters, chronological
    level_periods: tuple[tuple[Decimal, str], ...]  # (price, letter) ascending
    location: ZoneLocation
    ib_relation: IbRelation
    value_relation: ValueRelation


@dataclass(frozen=True)
class ExtremeStructure:
    side: str  # "HIGH" or "LOW"
    price: Decimal
    letters_at_extreme: str
    tpo_count_at_extreme: int
    tail_level_count: int  # one-TPO rows contiguous inward from the extreme (0 if none)
    tail_tick_count: int
    tail_span_points: Decimal  # 0 when tail_level_count <= 1
    tail_inner_price: Decimal | None  # innermost row of the tail
    tail_periods: str
    tail_formed_in_final_period: bool  # raw fact; some references discount closing tails
    excess_candidate: CandidateStatus
    poor_candidate: CandidateStatus


@dataclass(frozen=True)
class IbExtensionDetail:
    ib_high: Decimal
    ib_low: Decimal
    ib_range: Decimal
    ib_range_is_zero: bool
    max_extension_above: Decimal
    max_extension_above_ticks: int
    max_extension_below: Decimal
    max_extension_below_ticks: int
    extension_above_fraction_of_ib: Decimal | None  # None when ib_range == 0
    extension_below_fraction_of_ib: Decimal | None
    periods_new_post_ib_high: str  # each beat every earlier high, IB high included
    periods_new_post_ib_low: str


@dataclass(frozen=True)
class PeriodStructure:
    """Range facts for one period; None where not applicable (no trades, no prior, IB period)."""

    label: str
    high: Decimal | None
    low: Decimal | None
    new_profile_high: bool | None  # high above every earlier period's high
    new_profile_low: bool | None
    extended_ib_high: bool | None  # post-IB periods only
    extended_ib_low: bool | None
    high_extension: Decimal | None  # max(0, high - IB high)
    low_extension: Decimal | None  # max(0, IB low - low)


@dataclass(frozen=True)
class ProfileStructure:
    policy_id: str
    policy_version: str
    excess_min_tail_levels: int
    poor_extreme_min_tpos: int
    one_tpo_levels: tuple[TpoLevel, ...]  # ascending
    zones: tuple[OneTpoZone, ...]  # ascending
    upper: ExtremeStructure
    lower: ExtremeStructure
    ib_extension: IbExtensionDetail | None
    periods: tuple[PeriodStructure, ...]

    @property
    def interior_zones(self) -> tuple[OneTpoZone, ...]:
        return tuple(z for z in self.zones if z.location is ZoneLocation.INTERIOR)


def build_profile_structure(profile: TpoProfile) -> ProfileStructure:
    levels = profile.levels
    zones = tuple(_zone(profile, levels[a : b + 1], a, b) for a, b in _one_tpo_runs(levels))
    traded_periods = sum(1 for p in profile.periods if p.trade_count)
    final_label = profile.periods[-1].label
    return ProfileStructure(
        policy_id=STRUCTURE_POLICY_ID,
        policy_version=STRUCTURE_POLICY_VERSION,
        excess_min_tail_levels=EXCESS_MIN_TAIL_LEVELS,
        poor_extreme_min_tpos=POOR_EXTREME_MIN_TPOS,
        one_tpo_levels=tuple(level for level in levels if level.tpo_count == 1),
        zones=zones,
        upper=_extreme("HIGH", tuple(reversed(levels)), traded_periods, final_label),
        lower=_extreme("LOW", levels, traded_periods, final_label),
        ib_extension=_ib_extension(profile),
        periods=_period_structure(profile),
    )


def _one_tpo_runs(levels: tuple[TpoLevel, ...]) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start = None
    for i, level in enumerate(levels):
        if level.tpo_count == 1:
            if start is None:
                start = i
        elif start is not None:
            runs.append((start, i - 1))
            start = None
    if start is not None:
        runs.append((start, len(levels) - 1))
    return runs


def _chrono(letters) -> str:
    return "".join(sorted(set(letters), key=PERIOD_LABELS.index))


def _zone(profile: TpoProfile, rows: tuple[TpoLevel, ...], a: int, b: int) -> OneTpoZone:
    low, high = rows[0].price, rows[-1].price
    at_low, at_high = a == 0, b == len(profile.levels) - 1
    location = (ZoneLocation.ENTIRE_PROFILE if at_low and at_high else ZoneLocation.UPPER_EXTREME if at_high
                else ZoneLocation.LOWER_EXTREME if at_low else ZoneLocation.INTERIOR)
    ib = profile.initial_balance
    return OneTpoZone(
        low=low,
        high=high,
        level_count=len(rows),
        tick_count=len(rows),
        span_points=high - low,
        periods=_chrono(r.periods for r in rows),
        level_periods=tuple((r.price, r.periods) for r in rows),
        location=location,
        ib_relation=IbRelation.NO_IB if ib is None else _relation(
            low, high, ib.low, ib.high, IbRelation.ABOVE_IB, IbRelation.BELOW_IB, IbRelation.INSIDE_IB,
            IbRelation.OVERLAPPING_IB),
        value_relation=_relation(
            low, high, profile.value_area.low, profile.value_area.high, ValueRelation.ABOVE_VAH,
            ValueRelation.BELOW_VAL, ValueRelation.INSIDE_VALUE, ValueRelation.OVERLAPPING_BOUNDARY),
    )


def _relation(low, high, ref_low, ref_high, above, below, inside, overlapping):
    if low > ref_high:
        return above
    if high < ref_low:
        return below
    if low >= ref_low and high <= ref_high:
        return inside
    return overlapping


def _extreme(side: str, outward_first: tuple[TpoLevel, ...], traded_periods: int, final_label: str) -> ExtremeStructure:
    """`outward_first` starts at the extreme row and walks inward."""
    extreme = outward_first[0]
    tail: list[TpoLevel] = []
    for level in outward_first:
        if level.tpo_count != 1:
            break
        tail.append(level)
    if traded_periods < 2:
        excess = poor = CandidateStatus.NOT_CLASSIFIED
    else:
        excess = CandidateStatus.YES if len(tail) >= EXCESS_MIN_TAIL_LEVELS else CandidateStatus.NO
        poor = CandidateStatus.YES if extreme.tpo_count >= POOR_EXTREME_MIN_TPOS else CandidateStatus.NO
    tail_periods = _chrono(level.periods for level in tail)
    return ExtremeStructure(
        side=side,
        price=extreme.price,
        letters_at_extreme=extreme.periods,
        tpo_count_at_extreme=extreme.tpo_count,
        tail_level_count=len(tail),
        tail_tick_count=len(tail),
        tail_span_points=abs(tail[-1].price - tail[0].price) if tail else Decimal("0"),
        tail_inner_price=tail[-1].price if tail else None,
        tail_periods=tail_periods,
        tail_formed_in_final_period=final_label in tail_periods,
        excess_candidate=excess,
        poor_candidate=poor,
    )


def _ib_extension(profile: TpoProfile) -> IbExtensionDetail | None:
    ib = profile.initial_balance
    if ib is None:
        return None
    inc = profile.price_increment
    zero = ib.range == 0
    new_highs, new_lows = [], []
    running_high, running_low = ib.high, ib.low
    for p in _post_ib(profile):
        if p.high > running_high:
            new_highs.append(p.label)
            running_high = p.high
        if p.low < running_low:
            new_lows.append(p.label)
            running_low = p.low
    return IbExtensionDetail(
        ib_high=ib.high,
        ib_low=ib.low,
        ib_range=ib.range,
        ib_range_is_zero=zero,
        max_extension_above=ib.extension_above,
        max_extension_above_ticks=int(ib.extension_above / inc),
        max_extension_below=ib.extension_below,
        max_extension_below_ticks=int(ib.extension_below / inc),
        extension_above_fraction_of_ib=None if zero else ib.extension_above / ib.range,
        extension_below_fraction_of_ib=None if zero else ib.extension_below / ib.range,
        periods_new_post_ib_high="".join(new_highs),
        periods_new_post_ib_low="".join(new_lows),
    )


def _post_ib(profile: TpoProfile):
    ib_end = profile.start_utc + timedelta(minutes=INITIAL_BALANCE_MINUTES)
    return [p for p in profile.periods if p.start_utc >= ib_end and p.trade_count]


def _period_structure(profile: TpoProfile) -> tuple[PeriodStructure, ...]:
    ib = profile.initial_balance
    post_ib = {p.label for p in _post_ib(profile)}
    out = []
    prior_high = prior_low = None
    for p in profile.periods:
        if not p.trade_count:
            out.append(PeriodStructure(p.label, None, None, None, None, None, None, None, None))
            continue
        in_post = p.label in post_ib and ib is not None
        out.append(PeriodStructure(
            label=p.label,
            high=p.high,
            low=p.low,
            new_profile_high=None if prior_high is None else p.high > prior_high,
            new_profile_low=None if prior_low is None else p.low < prior_low,
            extended_ib_high=p.high > ib.high if in_post else None,
            extended_ib_low=p.low < ib.low if in_post else None,
            high_extension=max(p.high - ib.high, ib.high - ib.high) if in_post else None,  # 0 keeps grid scale
            low_extension=max(ib.low - p.low, ib.low - ib.low) if in_post else None,
        ))
        prior_high = p.high if prior_high is None else max(prior_high, p.high)
        prior_low = p.low if prior_low is None else min(prior_low, p.low)
    return tuple(out)
