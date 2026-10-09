"""Continuous day-structure strength / asymmetry facts beside the V1 day-type label (0Y-E).

A derived layer over an accepted `DayTypeClassification` (0Y-C); it never alters
the classification, its facts or its thresholds. The named V1 candidate stays the
reference taxonomy; this object is the vector of continuous structural evidence
that says how one-sided, extended and persistent the same day actually was.

  DAY_TYPE_V1                 named reference taxonomy (tpo_day_structure, frozen)
  DAY_STRUCTURE_STRENGTH_V1   continuous measurements (this module)

No score, no weighting, no threshold, no interpretation. Every ratio with a zero
denominator is None ("undefined"), never 0 or infinity. A future policy change
gets a new policy ID; it never mutates either V1. See
docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md §33-§39.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.tpo_day_structure import (
    DAY_TYPE_POLICY_ID,
    DAY_TYPE_POLICY_VERSION,
    ClassificationOutcome,
    DayType,
    DayTypeClassification,
    Direction,
    DirectionalState,
    ExtensionDirection,
    QualityGrade,
)
from dicks_laboratory.tpo_profile import PERIOD_LABELS

DAY_TYPE_V1 = "DAY_TYPE_V1"
DAY_STRUCTURE_STRENGTH_V1 = "DAY_STRUCTURE_STRENGTH_V1"
# Short policy key <- the exact (policy_id, policy_version) the classifier stamps on
# every result. A new day-type policy is a new entry here, never an edit of this one.
DAY_TYPE_POLICY_KEYS = {(DAY_TYPE_POLICY_ID, DAY_TYPE_POLICY_VERSION): DAY_TYPE_V1}


def day_type_policy_key(day: DayTypeClassification) -> str:
    try:
        return DAY_TYPE_POLICY_KEYS[(day.policy_id, day.policy_version)]
    except KeyError:
        raise ValueError(f"unknown day-type policy {day.policy_id} {day.policy_version}") from None


class DominantExtension(StrEnum):
    UP = "UP"  # extension above IB > extension below IB
    DOWN = "DOWN"
    TIE = "TIE"  # equal, non-zero, on both sides
    NONE = "NONE"  # no extension beyond the IB on either side


class StrengthScope(StrEnum):
    FULL_STUDY_WINDOW = "FULL_STUDY_WINDOW"  # V1 evaluated; quality UNQUALIFIED
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # V1 evaluated; gap evidence / lifecycle reasons apply
    RAW_FACTS_ONLY = "RAW_FACTS_ONLY"  # V1 NOT_CLASSIFIED: not a full-day strength assessment


@dataclass(frozen=True)
class DayStructureStrength:
    policy_id: str  # DAY_STRUCTURE_STRENGTH_V1
    day_type_policy: str  # DAY_TYPE_V1
    # V1 reference label, restated (never recomputed here)
    day_type_outcome: ClassificationOutcome
    day_type: DayType | None
    day_type_direction: Direction | None
    scope: StrengthScope
    scope_reasons: tuple[str, ...]  # why the assessment is qualified or not full-day
    # extension asymmetry (None: no Initial Balance; ratios None: zero denominator)
    ib_range_ticks: int | None
    ib_share_of_range: Decimal | None
    directional_state: DirectionalState | None
    extension_above_ticks: int | None
    extension_below_ticks: int | None
    extension_above_points: Decimal | None
    extension_below_points: Decimal | None
    extension_above_per_ib: Decimal | None
    extension_below_per_ib: Decimal | None
    dominant_extension: DominantExtension | None
    dominant_extension_ticks: int | None  # the larger side (either side on a TIE)
    counter_extension_ticks: int | None  # the smaller side
    dominant_per_ib: Decimal | None
    counter_per_ib: Decimal | None
    counter_to_dominant: Decimal | None  # = smaller / larger; None when dominant = 0
    dominant_share_of_total: Decimal | None  # larger / (above + below); None when total = 0
    # terminal location (last eligible trade before the window end; not the settlement)
    terminal_price: Decimal | None
    terminal_timestamp_utc: datetime | None
    terminal_percentile: Decimal | None  # None when profile range = 0
    terminal_from_high_ticks: int | None
    terminal_from_low_ticks: int | None
    terminal_from_high_per_range: Decimal | None
    terminal_from_low_per_range: Decimal | None
    # directional persistence (post-IB new-extreme periods; traded-period runs)
    new_high_periods: str
    new_low_periods: str
    new_high_period_count: int
    new_low_period_count: int
    max_consecutive_new_high_periods: int
    max_consecutive_new_low_periods: int
    longest_higher_low_run: int
    longest_lower_high_run: int
    first_extension_direction: ExtensionDirection | None
    last_extension_direction: ExtensionDirection | None
    # structural context (0Y-B facts, by reference)
    upper_tail_rows: int
    upper_tail_ticks: int
    lower_tail_rows: int
    lower_tail_ticks: int
    interior_one_tpo_zone_count: int
    interior_one_tpo_rows: int
    poc_percentile: Decimal | None
    ib_midpoint_percentile: Decimal | None
    value_area_midpoint_percentile: Decimal | None


def build_day_structure_strength(day: DayTypeClassification, price_increment: Decimal) -> DayStructureStrength:
    """Every value is read or derived from `day.facts`; nothing is re-measured from trades."""
    f = day.facts
    above, below = f.extension_above_ticks, f.extension_below_ticks
    if above is None:
        dominant = larger = smaller = None
    else:
        dominant = (DominantExtension.UP if above > below else DominantExtension.DOWN if below > above
                    else DominantExtension.TIE if above else DominantExtension.NONE)
        larger, smaller = max(above, below), min(above, below)
    ib_ticks = f.ib_range_ticks
    t = f.terminal
    return DayStructureStrength(
        policy_id=DAY_STRUCTURE_STRENGTH_V1,
        day_type_policy=day_type_policy_key(day),
        day_type_outcome=day.outcome,
        day_type=day.primary,
        day_type_direction=day.direction,
        scope=_scope(day),
        scope_reasons=(day.not_classified_reasons if day.outcome is ClassificationOutcome.NOT_CLASSIFIED
                       else day.quality.reasons),
        ib_range_ticks=ib_ticks,
        ib_share_of_range=f.ib_share_of_range,
        directional_state=f.directional_state,
        extension_above_ticks=above,
        extension_below_ticks=below,
        extension_above_points=f.extension_above,
        extension_below_points=f.extension_below,
        extension_above_per_ib=f.extension_above_multiple_of_ib,
        extension_below_per_ib=f.extension_below_multiple_of_ib,
        dominant_extension=dominant,
        dominant_extension_ticks=larger,
        counter_extension_ticks=smaller,
        dominant_per_ib=_ratio(larger, ib_ticks),
        counter_per_ib=_ratio(smaller, ib_ticks),
        counter_to_dominant=_ratio(smaller, larger),
        dominant_share_of_total=_ratio(larger, None if above is None else above + below),
        terminal_price=None if t is None else t.price,
        terminal_timestamp_utc=None if t is None else t.timestamp_utc,
        terminal_percentile=None if t is None else t.percentile_in_range,
        terminal_from_high_ticks=None if t is None else int(t.distance_from_high / price_increment),
        terminal_from_low_ticks=None if t is None else int(t.distance_from_low / price_increment),
        terminal_from_high_per_range=None if t is None else _ratio(t.distance_from_high, f.profile_range),
        terminal_from_low_per_range=None if t is None else _ratio(t.distance_from_low, f.profile_range),
        new_high_periods=f.new_post_ib_high_periods,
        new_low_periods=f.new_post_ib_low_periods,
        new_high_period_count=len(f.new_post_ib_high_periods),
        new_low_period_count=len(f.new_post_ib_low_periods),
        max_consecutive_new_high_periods=max_consecutive_periods(f.new_post_ib_high_periods),
        max_consecutive_new_low_periods=max_consecutive_periods(f.new_post_ib_low_periods),
        longest_higher_low_run=f.longest_higher_low_run,
        longest_lower_high_run=f.longest_lower_high_run,
        first_extension_direction=f.first_extension_direction,
        last_extension_direction=f.last_extension_direction,
        upper_tail_rows=f.upper_extreme.tail_level_count,
        upper_tail_ticks=f.upper_extreme.tail_tick_count,
        lower_tail_rows=f.lower_extreme.tail_level_count,
        lower_tail_ticks=f.lower_extreme.tail_tick_count,
        interior_one_tpo_zone_count=len(f.interior_one_tpo_zones),
        interior_one_tpo_rows=sum(z.level_count for z in f.interior_one_tpo_zones),
        poc_percentile=f.poc_percentile,
        ib_midpoint_percentile=f.ib_midpoint_percentile,
        value_area_midpoint_percentile=f.value_area_midpoint_percentile,
    )


def max_consecutive_periods(letters: str) -> int:
    """Longest run of chronologically adjacent period letters (e.g. "DEFH" -> 3)."""
    best = run = 0
    prev = None
    for index in sorted(PERIOD_LABELS.index(c) for c in letters):
        run = run + 1 if prev is not None and index == prev + 1 else 1
        best, prev = max(best, run), index
    return best


def _ratio(numerator, denominator) -> Decimal | None:
    if numerator is None or not denominator:
        return None
    return Decimal(numerator) / Decimal(denominator)


def _scope(day: DayTypeClassification) -> StrengthScope:
    if day.outcome is ClassificationOutcome.NOT_CLASSIFIED:
        return StrengthScope.RAW_FACTS_ONLY
    if day.quality.grade is QualityGrade.QUALITY_QUALIFIED:
        return StrengthScope.QUALITY_QUALIFIED
    return StrengthScope.FULL_STUDY_WINDOW


def strength_to_json(strength: DayStructureStrength) -> str:
    """One JSON line; Decimals as exact strings, enums by value, timestamps ISO-8601."""
    data = {}
    for key, value in asdict(strength).items():
        if isinstance(value, StrEnum):
            value = value.value
        elif isinstance(value, Decimal):
            value = str(value)
        elif isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, tuple):
            value = list(value)
        data[key] = value
    return json.dumps(data, sort_keys=True)
