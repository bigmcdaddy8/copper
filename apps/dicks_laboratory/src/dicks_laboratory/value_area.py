"""Deterministic Value Area / VAH / VAL policy over an accepted Volume-at-Price profile.

Consumes an already-built VolumeAtPriceProfile (0O); it does not recompute raw
volume-at-price aggregation or re-resolve the profile's Point of Control. Profile
facts and Value Area policy are kept strictly separate.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.models import InstrumentIdentity
from dicks_laboratory.volume_profile import VolumeAtPriceLevel, VolumeAtPriceProfile

# There is no CME-mandated Value Area algorithm; Value Area is a Market/Volume
# Profile analytical convention. This policy adopts the single-row, POC-anchored,
# alternating expansion documented by TradingView's own support materials
# ("Volume profile indicators: basic concepts") as a deliberately chosen Dick's
# Laboratory policy -- not an exchange fact, and not claimed to be the only
# vendor convention (Sierra Chart does not publish its exact algorithm).
VALUE_AREA_POLICY_ID = "DICKS_LAB_VALUE_AREA_POLICY"
VALUE_AREA_POLICY_VERSION = "V1_SINGLE_ROW_GREATER_VOLUME_NEAREST_POC_TIE_ABOVE"

DEFAULT_VALUE_AREA_FRACTION = Decimal("0.70")


@dataclass(frozen=True)
class ValueAreaExpansionStep:
    """One step of the deterministic expansion trace; not persisted, debug-only."""

    step: int
    added_level: VolumeAtPriceLevel | None  # None for step 0 (the POC seed)
    included_volume: Decimal


@dataclass(frozen=True)
class ValueAreaResult:
    """Immutable derived Value Area; strictly separate from raw profile facts."""

    instrument: InstrumentIdentity
    source_mode: VwapSourceMode

    value_area_policy_id: str
    value_area_policy_version: str

    target_fraction: Decimal
    target_volume: Decimal

    profile_total_volume: Decimal
    profile_level_count: int

    included_volume: Decimal
    included_fraction: Decimal

    point_of_control: VolumeAtPriceLevel
    value_area_low: VolumeAtPriceLevel
    value_area_high: VolumeAtPriceLevel

    included_levels: tuple[VolumeAtPriceLevel, ...]  # ascending price order
    included_level_count: int

    expansion_trace: tuple[ValueAreaExpansionStep, ...]


def compute_value_area(
    profile: VolumeAtPriceProfile,
    target_fraction: Decimal = DEFAULT_VALUE_AREA_FRACTION,
) -> ValueAreaResult:
    """Expand a contiguous region outward from the profile's POC to the target fraction.

    Algorithm (see module docstring for provenance):
      1. Seed the region with the POC level alone.
      2. While included volume is below target and a candidate remains:
         compare the next occupied level immediately above the region to the
         next occupied level immediately below it; add whichever has the
         greater volume. If only one side has a candidate, add that side.
      3. On a volume tie, add the candidate nearer to the POC (fewer occupied
         levels away); if still tied, add the level above.
      4. A full level is always included even if it pushes included volume
         past the target -- levels are never split.
    """
    if target_fraction.is_nan():
        raise ValueError("target_fraction must not be NaN.")
    if not (Decimal("0") < target_fraction <= Decimal("1")):
        raise ValueError("target_fraction must satisfy 0 < fraction <= 1.")
    levels = profile.levels
    if not levels:
        raise ValueError("Cannot compute a Value Area for an empty profile.")

    poc_index = levels.index(profile.point_of_control)
    target_volume = profile.total_volume * target_fraction

    lo = hi = poc_index
    included_volume = levels[poc_index].volume
    trace = [ValueAreaExpansionStep(0, None, included_volume)]

    while included_volume < target_volume:
        below = levels[lo - 1] if lo > 0 else None
        above = levels[hi + 1] if hi < len(levels) - 1 else None
        if below is None and above is None:
            break
        add_above = _choose_side(below, above, lo, hi, poc_index)
        if add_above:
            hi += 1
            included_volume += levels[hi].volume
            trace.append(ValueAreaExpansionStep(len(trace), levels[hi], included_volume))
        else:
            lo -= 1
            included_volume += levels[lo].volume
            trace.append(ValueAreaExpansionStep(len(trace), levels[lo], included_volume))

    included_levels = levels[lo : hi + 1]
    return ValueAreaResult(
        instrument=profile.instrument,
        source_mode=profile.source_mode,
        value_area_policy_id=VALUE_AREA_POLICY_ID,
        value_area_policy_version=VALUE_AREA_POLICY_VERSION,
        target_fraction=target_fraction,
        target_volume=target_volume,
        profile_total_volume=profile.total_volume,
        profile_level_count=len(levels),
        included_volume=included_volume,
        included_fraction=included_volume / profile.total_volume,
        point_of_control=profile.point_of_control,
        value_area_low=included_levels[0],
        value_area_high=included_levels[-1],
        included_levels=included_levels,
        included_level_count=len(included_levels),
        expansion_trace=tuple(trace),
    )


def _choose_side(
    below: VolumeAtPriceLevel | None,
    above: VolumeAtPriceLevel | None,
    lo: int,
    hi: int,
    poc_index: int,
) -> bool:
    """Return True to add the above candidate, False to add the below candidate."""
    if below is None:
        return True
    if above is None:
        return False
    if above.volume > below.volume:
        return True
    if below.volume > above.volume:
        return False
    distance_above = (hi + 1) - poc_index
    distance_below = poc_index - (lo - 1)
    if distance_below < distance_above:
        return False
    return True
