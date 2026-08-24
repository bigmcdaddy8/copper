from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.effective_tape import EffectiveTrade
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.volume_profile import (
    ES_PRICE_GRID,
    build_volume_at_price_profile,
    price_grid_for_instrument,
)

UTC = timezone.utc
INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)


def _trade(sequence: int, price: str, size: str, minute: int = 0) -> TradeObservation:
    return TradeObservation(
        UUID(f"a5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        UUID("a5d7d1e4-3c38-4c16-9e04-e6f7c8a7c999"),
        sequence,
        INSTRUMENT,
        datetime(2026, 8, 24, 14, minute, tzinfo=UTC),
        Decimal(price),
        Decimal(size),
    )


def _effective(sequence: int, price: str, size: str, correction_count: int = 0) -> EffectiveTrade:
    return EffectiveTrade(
        UUID(f"b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        UUID(f"c5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        INSTRUMENT,
        datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
        Decimal(price),
        Decimal(size),
        sequence,
        sequence,
        correction_count,
    )


# A. ES tick size definition
def test_es_tick_size_is_quarter_point():
    assert ES_PRICE_GRID.tick_size == Decimal("0.25")
    assert ES_PRICE_GRID.instrument_family == "ES"
    assert price_grid_for_instrument(INSTRUMENT) is ES_PRICE_GRID


# B. Valid tick price accepted
def test_valid_tick_price_accepted():
    assert ES_PRICE_GRID.tick_index(Decimal("7694.25")) == 30777
    assert ES_PRICE_GRID.price_at(30777) == Decimal("7694.25")


# C. Invalid tick price rejected
def test_invalid_tick_price_rejected_not_rounded():
    assert ES_PRICE_GRID.tick_index(Decimal("7694.30")) is None
    trades = (_trade(1, "7694.30", "1"),)
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.profile is None
    assert len(result.invalid_tick_trades) == 1
    assert result.invalid_tick_trades[0].reason == "PRICE_NOT_ON_TICK_GRID"
    assert result.invalid_tick_trades[0].price == Decimal("7694.30")


# D. Exact price-level aggregation
def test_exact_price_level_aggregation_matches_fixture():
    trades = (
        _trade(1, "7693.75", "1"),
        _trade(2, "7694.00", "2"),
        _trade(3, "7694.00", "3"),
        _trade(4, "7694.25", "1"),
        _trade(5, "7694.25", "1"),
        _trade(6, "7694.50", "4"),
        _trade(7, "7694.50", "2"),
        _trade(8, "7694.75", "1"),
    )
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    profile = result.profile
    by_price = {level.price: level.volume for level in profile.levels}
    assert by_price == {
        Decimal("7693.75"): Decimal("1"),
        Decimal("7694.00"): Decimal("5"),
        Decimal("7694.25"): Decimal("2"),
        Decimal("7694.50"): Decimal("6"),
        Decimal("7694.75"): Decimal("1"),
    }
    assert profile.point_of_control.price == Decimal("7694.50")
    assert profile.point_of_control.volume == Decimal("6")


# E. Exact volume conservation
def test_exact_volume_conservation():
    trades = (_trade(1, "100", "1.5"), _trade(2, "100", "2.25"), _trade(3, "100.25", "3"))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    total_level_volume = sum((level.volume for level in result.profile.levels), Decimal("0"))
    total_trade_size = sum((trade.size for trade in trades), Decimal("0"))
    assert total_level_volume == total_trade_size == result.profile.total_volume


# F. Trade-count conservation
def test_trade_count_conservation():
    trades = (_trade(1, "100", "1"), _trade(2, "100", "1"), _trade(3, "100.25", "1"))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    total_trade_count = sum(level.trade_count for level in result.profile.levels)
    assert total_trade_count == len(trades) == result.profile.selected_trade_count


# G. Deterministic ascending level ordering
def test_levels_are_ascending_price_order():
    trades = (_trade(1, "100.50", "1"), _trade(2, "100.00", "1"), _trade(3, "100.25", "1"))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    prices = [level.price for level in result.profile.levels]
    assert prices == sorted(prices)


# H. Single-level profile
def test_single_level_profile():
    trades = (_trade(1, "100", "2"), _trade(2, "100", "3"))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert len(result.profile.levels) == 1
    assert result.profile.point_of_control.price == Decimal("100")
    assert result.profile.total_volume == Decimal("5")


# I. Empty input behavior
def test_empty_input_produces_no_profile():
    result = build_volume_at_price_profile((), ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.profile is None
    assert result.invalid_tick_trades == ()


# J. Unique POC
def test_unique_poc_is_max_volume_level():
    trades = (_trade(1, "100", "5"), _trade(2, "100.25", "9"), _trade(3, "100.50", "3"))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.profile.point_of_control.price == Decimal("100.25")


# K. Tied POC deterministic policy
def test_tied_poc_resolves_to_level_nearest_volume_weighted_mean_then_lower_price():
    # 100.00 and 100.50 tie at volume 4; mean price is closer to 100.00 given the extra low-volume level.
    trades = (
        _trade(1, "100.00", "4"),
        _trade(2, "100.25", "1"),
        _trade(3, "100.50", "4"),
    )
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.profile.point_of_control.price == Decimal("100.00")


def test_fully_tied_poc_prefers_lower_price():
    trades = (_trade(1, "100.00", "4"), _trade(2, "100.50", "4"))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.profile.point_of_control.price == Decimal("100.00")


# L. POC independent of input ordering
def test_poc_independent_of_input_order():
    trades_forward = (_trade(1, "100", "1"), _trade(2, "100.25", "9"), _trade(3, "100.50", "3"))
    trades_reversed = tuple(reversed(trades_forward))
    forward = build_volume_at_price_profile(trades_forward, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    backward = build_volume_at_price_profile(trades_reversed, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert forward.profile.point_of_control == backward.profile.point_of_control
    assert forward.profile.levels == backward.profile.levels


# M. Same-time/same-price distinct trades both contribute
def test_same_time_same_price_distinct_trades_are_not_deduplicated():
    trades = (_trade(1, "100", "1", minute=5), _trade(2, "100", "1", minute=5))
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.profile.levels[0].volume == Decimal("2")
    assert result.profile.levels[0].trade_count == 2


# N. Decimal exactness
def test_decimal_exactness_no_float_conversion():
    trades = (_trade(1, "7694.25", "1.123456789012345678901234"),)
    result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    level = result.profile.levels[0]
    assert isinstance(level.volume, Decimal)
    assert isinstance(level.price, Decimal)
    assert level.volume == Decimal("1.123456789012345678901234")
    assert level.price == Decimal("7694.25")


# O. Canonical NEW-only profile / P. Effective corrected profile / Q. Effective canceled profile
def test_canonical_vs_corrected_effective_profile_diverge():
    canonical = (_trade(1, "100", "1"), _trade(2, "102", "1"))
    corrected_effective = (_effective(1, "104", "3", correction_count=1),)
    canonical_result = build_volume_at_price_profile(canonical, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    effective_result = build_volume_at_price_profile(corrected_effective, ES_PRICE_GRID, VwapSourceMode.EFFECTIVE_TAPE)
    assert canonical_result.profile.total_volume == Decimal("2")
    assert effective_result.profile.total_volume == Decimal("3")
    assert canonical_result.profile.point_of_control.price != effective_result.profile.point_of_control.price


def test_effective_canceled_trade_absent_while_canonical_retains_it():
    canonical = (_trade(1, "100", "1"), _trade(2, "102", "1"))
    effective_after_cancel = (_effective(1, "100", "1"),)  # trade 2 canceled upstream, absent here
    canonical_result = build_volume_at_price_profile(canonical, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    effective_result = build_volume_at_price_profile(effective_after_cancel, ES_PRICE_GRID, VwapSourceMode.EFFECTIVE_TAPE)
    assert canonical_result.profile.total_volume == Decimal("2")
    assert effective_result.profile.total_volume == Decimal("1")
    assert Decimal("102") not in {level.price for level in effective_result.profile.levels}


# R. Canonical/effective source mode metadata
def test_source_mode_metadata_is_explicit():
    trades = (_trade(1, "100", "1"),)
    canonical_result = build_volume_at_price_profile(trades, ES_PRICE_GRID, VwapSourceMode.CANONICAL_NEW_ONLY)
    effective_result = build_volume_at_price_profile((_effective(1, "100", "1"),), ES_PRICE_GRID, VwapSourceMode.EFFECTIVE_TAPE)
    assert canonical_result.profile.source_mode is VwapSourceMode.CANONICAL_NEW_ONLY
    assert effective_result.profile.source_mode is VwapSourceMode.EFFECTIVE_TAPE


def test_unsupported_instrument_root_raises():
    unsupported = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "NQ", 2026, 9)
    with pytest.raises(ValueError):
        price_grid_for_instrument(unsupported)
