from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.effective_tape import EffectiveTrade
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.value_area import (
    DEFAULT_VALUE_AREA_FRACTION,
    VALUE_AREA_POLICY_ID,
    VALUE_AREA_POLICY_VERSION,
    compute_value_area,
)
from dicks_laboratory.volume_profile import ES_PRICE_GRID, build_volume_at_price_profile

UTC = timezone.utc
INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)


def _trade(sequence: int, price: str, size: str) -> TradeObservation:
    return TradeObservation(
        UUID(f"d5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        UUID("d5d7d1e4-3c38-4c16-9e04-e6f7c8a7c999"),
        sequence,
        INSTRUMENT,
        datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        Decimal(price),
        Decimal(size),
    )


def _effective(sequence: int, price: str, size: str) -> EffectiveTrade:
    return EffectiveTrade(
        UUID(f"e5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        UUID(f"f5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        INSTRUMENT,
        datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        Decimal(price),
        Decimal(size),
        sequence,
        sequence,
    )


def _profile(price_volume_pairs, source_mode=VwapSourceMode.CANONICAL_NEW_ONLY, effective=False):
    trades = []
    for index, (price, size) in enumerate(price_volume_pairs, start=1):
        trades.append(_effective(index, price, size) if effective else _trade(index, price, size))
    result = build_volume_at_price_profile(tuple(trades), ES_PRICE_GRID, source_mode)
    assert result.profile is not None
    return result.profile


# A. Policy identity/version
def test_policy_identity_and_version_are_versioned_strings():
    assert VALUE_AREA_POLICY_ID == "DICKS_LAB_VALUE_AREA_POLICY"
    assert VALUE_AREA_POLICY_VERSION.startswith("V1_")


# B. Default 70% Decimal target
def test_default_target_is_exact_decimal_070():
    assert DEFAULT_VALUE_AREA_FRACTION == Decimal("0.70")
    profile = _profile([("100.00", "10")])
    result = compute_value_area(profile)
    assert result.target_fraction == Decimal("0.70")


# C. Invalid target fractions
@pytest.mark.parametrize("fraction", [Decimal("0"), Decimal("-0.1"), Decimal("1.01"), Decimal("NaN")])
def test_invalid_target_fractions_rejected(fraction):
    profile = _profile([("100.00", "10")])
    with pytest.raises(ValueError):
        compute_value_area(profile, fraction)


# D. POC always included
def test_poc_always_included():
    profile = _profile([("99.50", "5"), ("99.75", "20"), ("100.00", "50"), ("100.25", "15"), ("100.50", "5")])
    result = compute_value_area(profile, Decimal("0.10"))
    assert profile.point_of_control in result.included_levels


# E. Single-level profile
def test_single_level_profile_val_equals_vah_equals_poc():
    profile = _profile([("100.00", "10")])
    result = compute_value_area(profile)
    assert result.value_area_low == result.value_area_high == profile.point_of_control
    assert result.included_fraction == Decimal("1")


# F. POC alone reaches target
def test_poc_alone_reaches_low_target():
    profile = _profile([("99.75", "5"), ("100.00", "50"), ("100.25", "5")])
    result = compute_value_area(profile, Decimal("0.5"))
    assert result.included_levels == (profile.point_of_control,)
    assert result.value_area_low == result.value_area_high == profile.point_of_control


# G. Normal bilateral expansion (asymmetric, two-step, no tie)
def test_normal_bilateral_expansion_alternates_sides():
    profile = _profile([
        ("70.00", "2"), ("70.25", "8"), ("70.50", "12"), ("70.75", "40"),
        ("71.00", "25"), ("71.25", "10"), ("71.50", "3"),
    ])
    assert profile.point_of_control.price == Decimal("70.75")
    result = compute_value_area(profile, Decimal("0.70"))
    prices = [level.price for level in result.included_levels]
    assert prices == [Decimal("70.50"), Decimal("70.75"), Decimal("71.00")]
    assert result.included_volume == Decimal("77")
    assert result.target_volume == Decimal("70.00")


# H. Upper/lower candidate tie (prompt's symmetric fixture)
def test_symmetric_tie_resolved_by_nearest_to_poc_then_above():
    profile = _profile([
        ("99.50", "5"), ("99.75", "10"), ("100.00", "30"), ("100.25", "40"),
        ("100.50", "30"), ("100.75", "10"), ("101.00", "5"),
    ])
    assert profile.point_of_control.price == Decimal("100.25")
    result = compute_value_area(profile, Decimal("0.70"))
    prices = [level.price for level in result.included_levels]
    assert prices == [Decimal("100.00"), Decimal("100.25"), Decimal("100.50")]
    assert result.value_area_low.price == Decimal("100.00")
    assert result.value_area_high.price == Decimal("100.50")
    assert result.included_volume == Decimal("100")
    assert result.target_volume == Decimal("91.00")


# I. Tie output independent of input order
def test_tie_result_independent_of_input_trade_order():
    pairs = [
        ("99.50", "5"), ("99.75", "10"), ("100.00", "30"), ("100.25", "40"),
        ("100.50", "30"), ("100.75", "10"), ("101.00", "5"),
    ]
    forward = _profile(pairs)
    backward = _profile(list(reversed(pairs)))
    forward_result = compute_value_area(forward, Decimal("0.70"))
    backward_result = compute_value_area(backward, Decimal("0.70"))
    assert forward_result.included_levels == backward_result.included_levels
    assert forward_result.value_area_low == backward_result.value_area_low
    assert forward_result.value_area_high == backward_result.value_area_high


# J. Overshoot includes full price level, never splits volume
def test_overshoot_includes_full_level_without_splitting():
    profile = _profile([
        ("70.00", "2"), ("70.25", "8"), ("70.50", "12"), ("70.75", "40"),
        ("71.00", "25"), ("71.25", "10"), ("71.50", "3"),
    ])
    result = compute_value_area(profile, Decimal("0.70"))
    pre_final_step = result.expansion_trace[-2].included_volume
    final_step = result.expansion_trace[-1]
    assert pre_final_step < result.target_volume
    assert result.included_volume > result.target_volume
    assert result.included_volume - pre_final_step == final_step.added_level.volume
    assert result.included_fraction == Decimal("0.77")


# K. POC at lower boundary
def test_poc_at_lower_boundary_expands_only_upward():
    profile = _profile([("100.00", "50"), ("100.25", "20"), ("100.50", "10"), ("100.75", "5")])
    assert profile.point_of_control.price == Decimal("100.00")
    result = compute_value_area(profile, Decimal("0.70"))
    assert result.value_area_low.price == Decimal("100.00")
    assert result.included_levels[0].price == Decimal("100.00")


# L. POC at upper boundary
def test_poc_at_upper_boundary_expands_only_downward():
    profile = _profile([("99.25", "5"), ("99.50", "10"), ("99.75", "20"), ("100.00", "50")])
    assert profile.point_of_control.price == Decimal("100.00")
    result = compute_value_area(profile, Decimal("0.70"))
    assert result.value_area_high.price == Decimal("100.00")
    assert result.included_levels[-1].price == Decimal("100.00")


# M. One side exhausted; expansion continues on the remaining side
def test_one_side_exhausted_continues_on_remaining_side():
    profile = _profile([
        ("99.50", "8"), ("99.75", "12"), ("100.00", "40"),  # POC
        ("100.25", "5"), ("100.50", "5"), ("100.75", "5"),
        ("101.00", "5"), ("101.25", "5"), ("101.50", "5"),
    ])
    result = compute_value_area(profile, Decimal("0.90"))
    prices = {level.price for level in result.included_levels}
    assert Decimal("99.50") in prices and Decimal("99.75") in prices  # below side exhausted early
    assert Decimal("101.50") not in prices  # target reached before the last above level was needed
    assert result.included_level_count == len(profile.levels) - 1


# N. 100% target returns entire profile
def test_full_target_fraction_includes_entire_profile():
    profile = _profile([("99.00", "1"), ("99.25", "50"), ("99.50", "3"), ("99.75", "70"), ("100.00", "2")])
    result = compute_value_area(profile, Decimal("1"))
    assert result.included_level_count == len(profile.levels)
    assert result.included_volume == profile.total_volume


# O. Sparse/untraded tick behavior
def test_sparse_untraded_ticks_allowed_inside_contiguous_region():
    profile = _profile([("100.00", "5"), ("100.50", "30"), ("101.25", "15")])
    assert profile.point_of_control.price == Decimal("100.50")
    result = compute_value_area(profile, Decimal("0.70"))
    assert result.value_area_low.price == Decimal("100.50")
    assert result.value_area_high.price == Decimal("101.25")
    # a real gap of untraded ticks exists between VAL and VAH
    assert result.value_area_high.price - result.value_area_low.price > ES_PRICE_GRID.tick_size


# P. Exact target volume arithmetic
def test_exact_target_volume_arithmetic():
    profile = _profile([
        ("99.50", "5"), ("99.75", "10"), ("100.00", "30"), ("100.25", "40"),
        ("100.50", "30"), ("100.75", "10"), ("101.00", "5"),
    ])
    result = compute_value_area(profile, Decimal("0.70"))
    assert result.profile_total_volume == Decimal("130")
    assert result.target_volume == Decimal("130") * Decimal("0.70")
    assert result.target_volume == Decimal("91.00")


# Q / R. Exact included volume arithmetic and sum invariant
def test_included_volume_equals_exact_sum_of_included_levels():
    profile = _profile([("100.00", "40"), ("100.25", "5"), ("99.75", "5"), ("100.50", "10")])
    result = compute_value_area(profile, Decimal("0.70"))
    assert result.included_volume == sum((level.volume for level in result.included_levels), Decimal("0"))
    assert result.included_volume <= result.profile_total_volume


# S. Contiguous Value Area invariant
def test_included_levels_are_contiguous_within_profile_levels():
    profile = _profile([
        ("70.00", "2"), ("70.25", "8"), ("70.50", "12"), ("70.75", "40"),
        ("71.00", "25"), ("71.25", "10"), ("71.50", "3"),
    ])
    result = compute_value_area(profile, Decimal("0.70"))
    indices = sorted(profile.levels.index(level) for level in result.included_levels)
    assert indices == list(range(indices[0], indices[-1] + 1))


# T. VAL <= POC <= VAH
@pytest.mark.parametrize("fraction", [Decimal("0.10"), Decimal("0.50"), Decimal("0.70"), Decimal("1.0")])
def test_val_le_poc_le_vah(fraction):
    profile = _profile([
        ("70.00", "2"), ("70.25", "8"), ("70.50", "12"), ("70.75", "40"),
        ("71.00", "25"), ("71.25", "10"), ("71.50", "3"),
    ])
    result = compute_value_area(profile, fraction)
    assert result.value_area_low.price <= result.point_of_control.price <= result.value_area_high.price


# U. Canonical/effective profile compatibility
def test_compute_value_area_supports_canonical_and_effective_profiles():
    canonical_profile = _profile([("100.00", "5"), ("100.25", "20")])
    effective_profile = _profile([("100.00", "5"), ("100.25", "20")], source_mode=VwapSourceMode.EFFECTIVE_TAPE, effective=True)
    canonical_result = compute_value_area(canonical_profile)
    effective_result = compute_value_area(effective_profile)
    assert canonical_result.source_mode is VwapSourceMode.CANONICAL_NEW_ONLY
    assert effective_result.source_mode is VwapSourceMode.EFFECTIVE_TAPE


# V. Canonical/effective Value Area difference fixture
def test_correction_changes_value_area_between_canonical_and_effective():
    canonical_profile = _profile([("100.00", "1"), ("102.00", "1")])
    corrected_effective_profile = _profile([("104.00", "3")], source_mode=VwapSourceMode.EFFECTIVE_TAPE, effective=True)

    canonical_result = compute_value_area(canonical_profile)
    effective_result = compute_value_area(corrected_effective_profile)

    assert canonical_result.point_of_control.price == Decimal("100.00")
    assert canonical_result.value_area_low.price == Decimal("100.00")
    assert canonical_result.value_area_high.price == Decimal("102.00")

    assert effective_result.point_of_control.price == Decimal("104.00")
    assert effective_result.value_area_low == effective_result.value_area_high == effective_result.point_of_control


# I. Empty profile: no VAL=0/VAH=0 fabrication
def test_empty_profile_raises_instead_of_fabricating_zero():
    from dicks_laboratory.volume_profile import VolumeAtPriceProfile

    empty_profile = VolumeAtPriceProfile(
        instrument=INSTRUMENT,
        source_mode=VwapSourceMode.CANONICAL_NEW_ONLY,
        tick_size=ES_PRICE_GRID.tick_size,
        price_grid_policy_id=ES_PRICE_GRID.policy_id,
        price_grid_policy_version=ES_PRICE_GRID.policy_version,
        selected_trade_count=0,
        total_volume=Decimal("0"),
        lowest_price=Decimal("0"),
        highest_price=Decimal("0"),
        levels=(),
        point_of_control=None,
        poc_policy_id="n/a",
        poc_policy_version="n/a",
    )
    with pytest.raises(ValueError):
        compute_value_area(empty_profile)
