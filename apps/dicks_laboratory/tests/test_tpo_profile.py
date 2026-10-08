"""0Y-A: hand-verified TPO profile fixtures.

Every expected row below was worked out by hand; see
docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md for the rules being checked.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from dicks_laboratory.tpo_profile import (
    US_CASH_PROFILE,
    build_period_slots,
    build_tpo_profile,
)
from dicks_laboratory.volume_profile import ES_PRICE_GRID, PriceGrid

D = Decimal
TD = date(2026, 10, 6)  # CDT: 08:30 CT = 13:30Z
OPEN = datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)


def _t(minutes, price, td_open=OPEN):
    return SimpleNamespace(event_timestamp=td_open + timedelta(minutes=minutes), price=D(str(price)))


def _rows(profile):
    """(price, count, letters) descending -- the rendered order."""
    return [(str(lv.price), lv.tpo_count, lv.periods) for lv in reversed(profile.levels)]


def _range(period, low, high):
    """One trade at the low and one at the high of `period` (0 = A)."""
    return [_t(period * 30 + 1, low), _t(period * 30 + 2, high)]


# --- periods --------------------------------------------------------------------

def test_cash_window_has_thirteen_lettered_half_open_periods():
    slots = build_period_slots(TD)
    assert "".join(s.label for s in slots) == "ABCDEFGHIJKLM"
    assert slots[0].start_utc == OPEN and slots[0].end_utc == OPEN + timedelta(minutes=30)
    assert slots[-1].label == "M" and slots[-1].end_utc == datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc)
    assert all(a.end_utc == b.start_utc for a, b in zip(slots, slots[1:]))


@pytest.mark.parametrize("minutes,labels", [(15, "ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
                                            (10, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklm")])
def test_other_period_lengths_label_deterministically(minutes, labels):
    assert "".join(s.label for s in build_period_slots(TD, minutes)) == labels


@pytest.mark.parametrize("minutes", [0, -30, 45, 20, 7, 390, 1])
def test_period_lengths_that_do_not_tile_window_and_ib_are_rejected(minutes):
    with pytest.raises(ValueError):
        build_period_slots(TD, minutes)


def test_study_window_is_explicitly_a_laboratory_cash_window():
    assert US_CASH_PROFILE.window_id == "US_CASH_PROFILE"
    assert US_CASH_PROFILE.timezone_name == "America/Chicago" and US_CASH_PROFILE.minutes == 390


# --- occupancy ------------------------------------------------------------------

def test_single_period_profile():
    p = build_tpo_profile((_t(1, "100.00"), _t(2, "100.50"), _t(3, "100.25")), ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.50", 1, "A"), ("100.25", 1, "A"), ("100.00", 1, "A")]
    assert p.total_tpo_count == 3 and p.periods_present == "A"
    # three-way tie -> nearest the range midpoint 100.25
    assert p.poc == D("100.25")
    # seed 1; above(100.50)=1 vs below(100.00)=1 tie -> above; then only below remains
    assert (p.value_area.low, p.value_area.high, p.value_area.included_tpos) == (D("100.00"), D("100.50"), 3)
    assert [s.side for s in p.value_area.trace] == ["POC", "ABOVE", "BELOW"]


def test_two_overlapping_periods():
    trades = _range(0, "100.00", "101.00") + _range(1, "100.50", "101.50")
    p = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD)
    assert _rows(p) == [
        ("101.50", 1, "B"), ("101.25", 1, "B"), ("101.00", 2, "AB"), ("100.75", 2, "AB"),
        ("100.50", 2, "AB"), ("100.25", 1, "A"), ("100.00", 1, "A"),
    ]
    assert p.total_tpo_count == 10
    assert (p.profile_high, p.profile_low, p.profile_range) == (D("101.50"), D("100.00"), D("1.50"))
    # three-way tie at 2 TPOs; midpoint 100.75 is itself a candidate
    assert p.poc == D("100.75")
    # target 7.0: seed 2; above {101.00,101.25}=3 vs below {100.50,100.25}=3 tie -> above (5);
    # above {101.50}=1 vs below {100.50,100.25}=3 -> below (8 >= 7) stop
    va = p.value_area
    assert [(s.side, s.added_tpos, s.included_tpos) for s in va.trace] == [("POC", 2, 2), ("ABOVE", 3, 5), ("BELOW", 3, 8)]
    assert (va.low, va.high) == (D("100.25"), D("101.25"))
    assert va.included_fraction == D("0.8") and va.target_tpos == D("7.00")


def test_one_tpo_per_period_per_price_regardless_of_trade_count():
    trades = [_t(60 + (i % 29), "100.00") for i in range(1000)] + [_t(90, "100.00")]
    p = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.00", 2, "CD")]
    assert p.selected_trade_count == 1001 and p.total_tpo_count == 2


def test_non_overlapping_periods_leave_zero_tpo_rows():
    p = build_tpo_profile((_t(1, "100.00"), _t(31, "101.00")), ES_PRICE_GRID, TD)
    assert _rows(p) == [("101.00", 1, "B"), ("100.75", 0, ""), ("100.50", 0, ""), ("100.25", 0, ""), ("100.00", 1, "A")]
    assert p.poc == D("100.00")  # 100.00 and 101.00 equidistant from 100.50 -> lower price
    assert (p.value_area.low, p.value_area.high) == (D("100.00"), D("101.00"))


# --- POC ------------------------------------------------------------------------

def test_poc_tie_equidistant_from_midpoint_takes_lower_price():
    trades = _range(0, "100.00", "100.25") + _range(1, "100.00", "100.25") + _range(2, "99.75", "100.50")
    p = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.50", 1, "C"), ("100.25", 3, "ABC"), ("100.00", 3, "ABC"), ("99.75", 1, "C")]
    assert p.poc == D("100.00")


def test_poc_tie_prefers_nearest_midpoint_over_lower_price():
    trades = [_t(1, "100.00"), _t(31, "101.00")] + _range(2, "100.00", "101.25")
    p = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD)
    counts = {str(lv.price): lv.tpo_count for lv in p.levels}
    assert counts["100.00"] == counts["101.00"] == 2
    assert p.poc == D("101.00")  # midpoint 100.625: 101.00 is 0.375 away, 100.00 is 0.625


def test_poc_is_independent_of_input_order():
    trades = _range(0, "100.00", "101.00") + _range(1, "100.50", "101.50") + _range(4, "99.00", "100.25")
    forward = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD)
    backward = build_tpo_profile(tuple(reversed(trades)), ES_PRICE_GRID, TD)
    assert forward == backward


# --- value area -----------------------------------------------------------------

def test_value_area_tie_adds_pair_above():
    # symmetric profile: every expansion compares equal sums
    trades = _range(0, "99.50", "100.50") + _range(1, "99.75", "100.25") + _range(2, "100.00", "100.00")
    p = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.50", 1, "A"), ("100.25", 2, "AB"), ("100.00", 3, "ABC"), ("99.75", 2, "AB"), ("99.50", 1, "A")]
    va = p.value_area  # total 9, target 6.3: seed 3; above 3 == below 3 -> above (6); above none -> below (9)
    assert [(s.side, s.included_tpos) for s in va.trace] == [("POC", 3), ("ABOVE", 6), ("BELOW", 9)]
    assert va.trace[1].added_prices == (D("100.25"), D("100.50"))
    assert va.trace[2].added_prices == (D("99.75"), D("99.50"))


def test_value_area_target_reached_exactly_stops():
    trades = _range(0, "100.00", "100.50") + _range(1, "100.25", "100.50") + _range(2, "100.25", "100.50")
    p = build_tpo_profile(tuple(trades), ES_PRICE_GRID, TD, target_fraction=D("0.5"))
    # rows 100.50 ABC(3), 100.25 ABC(3), 100.00 A(1): total 7; tie at 3 -> midpoint 100.25 -> POC 100.25
    assert p.poc == D("100.25")
    # target 3.5: seed 3; above {100.50}=3 vs below {100.00}=1 -> above (6) stop
    assert (p.value_area.low, p.value_area.high, p.value_area.included_tpos) == (D("100.25"), D("100.50"), 6)


# --- initial balance ------------------------------------------------------------

def _ib(*extra):
    return _range(0, "100.00", "101.00") + _range(1, "100.50", "101.50") + list(extra)


def test_ib_no_extension():
    p = build_tpo_profile(tuple(_ib(*_range(2, "100.75", "101.25"))), ES_PRICE_GRID, TD)
    ib = p.initial_balance
    assert (ib.period_labels, ib.high, ib.low, ib.range) == ("AB", D("101.50"), D("100.00"), D("1.50"))
    assert (ib.extension_above, ib.extension_below) == (D("0"), D("0"))
    assert ib.first_extension_above_period is None and ib.first_extension_below_period is None


def test_ib_extension_above_only():
    p = build_tpo_profile(tuple(_ib(*_range(2, "101.00", "102.00"), *_range(5, "101.00", "101.75"))), ES_PRICE_GRID, TD)
    ib = p.initial_balance
    assert (ib.extension_above, ib.first_extension_above_period) == (D("0.50"), "C")
    assert (ib.extension_below, ib.first_extension_below_period) == (D("0"), None)


def test_ib_extension_below_only():
    p = build_tpo_profile(tuple(_ib(*_range(2, "100.50", "101.00"), *_range(3, "99.00", "100.50"))), ES_PRICE_GRID, TD)
    ib = p.initial_balance
    assert (ib.extension_above, ib.first_extension_above_period) == (D("0"), None)
    assert (ib.extension_below, ib.first_extension_below_period) == (D("1.00"), "D")


def test_ib_extension_both_directions():
    p = build_tpo_profile(tuple(_ib(*_range(2, "101.00", "102.00"), *_range(4, "99.50", "100.25"),
                                   *_range(12, "99.25", "100.00"))), ES_PRICE_GRID, TD)
    ib = p.initial_balance
    assert (ib.extension_above, ib.first_extension_above_period) == (D("0.50"), "C")
    assert (ib.extension_below, ib.first_extension_below_period) == (D("0.75"), "E")
    assert p.periods_present == "ABCEM"


def test_ib_uses_only_periods_present_in_first_hour():
    p = build_tpo_profile(tuple(_range(1, "100.00", "100.50") + _range(2, "99.00", "101.00")), ES_PRICE_GRID, TD)
    assert p.initial_balance.period_labels == "B"
    assert build_tpo_profile(tuple(_range(2, "100.00", "100.50")), ES_PRICE_GRID, TD).initial_balance is None


# --- boundaries -----------------------------------------------------------------

def test_trade_exactly_at_0830_is_period_a_and_just_before_is_excluded():
    p = build_tpo_profile((_t(0, "100.00"), SimpleNamespace(event_timestamp=OPEN - timedelta(microseconds=1),
                                                            price=D("90.00"))), ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.00", 1, "A")] and p.selected_trade_count == 1


def test_trade_exactly_at_0900_is_period_b_not_a():
    p = build_tpo_profile((_t(30, "100.00"), _t(29.999, "100.25")), ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.25", 1, "A"), ("100.00", 1, "B")]


def test_trade_exactly_at_1500_is_excluded():
    close = datetime(2026, 10, 6, 20, 0, tzinfo=timezone.utc)
    p = build_tpo_profile((SimpleNamespace(event_timestamp=close, price=D("200.00")),
                           SimpleNamespace(event_timestamp=close - timedelta(microseconds=1), price=D("100.00"))),
                          ES_PRICE_GRID, TD)
    assert _rows(p) == [("100.00", 1, "M")] and p.selected_trade_count == 1


def test_no_trades_in_window_returns_none():
    assert build_tpo_profile((_t(-5, "100.00"), _t(391, "100.00")), ES_PRICE_GRID, TD) is None


def test_naive_timestamps_rejected():
    with pytest.raises(ValueError):
        build_tpo_profile((SimpleNamespace(event_timestamp=datetime(2026, 10, 6, 14, 0), price=D("1")),), ES_PRICE_GRID, TD)


# --- non-ES tick size -----------------------------------------------------------

def test_non_es_tick_size_and_off_grid_exclusion():
    cl = PriceGrid("CL", D("0.01"), "TEST_CL_GRID", "TEST_CL_GRID_V1")
    p = build_tpo_profile((_t(1, "70.00"), _t(2, "70.03"), _t(3, "70.005"), _t(31, "70.02"), _t(32, "70.04")), cl, TD)
    assert _rows(p) == [("70.04", 1, "B"), ("70.03", 2, "AB"), ("70.02", 2, "AB"), ("70.01", 1, "A"), ("70.00", 1, "A")]
    assert p.price_increment == D("0.01") and p.invalid_tick_trade_count == 1
    assert p.poc == D("70.02")  # 70.02/70.03 tie; 70.02 is the range midpoint itself


def test_fractional_binary_tick_grid():
    zn = PriceGrid("ZN", D("0.015625"), "TEST_ZN_GRID", "TEST_ZN_GRID_V1")
    p = build_tpo_profile((_t(1, "110.5"), _t(2, "110.53125")), zn, TD)
    assert [str(lv.price) for lv in p.levels] == ["110.500000", "110.515625", "110.531250"]


# --- Chicago time / DST -----------------------------------------------------------

@pytest.mark.parametrize("td,open_utc_hour", [
    (date(2026, 12, 7), 14),   # CST
    (date(2026, 7, 7), 13),    # CDT
    (date(2026, 10, 30), 13),  # Friday before DST ends (CDT)
    (date(2026, 11, 2), 14),   # Monday after DST ends 2026-11-01 (CST)
    (date(2026, 3, 6), 14),    # Friday before DST starts 2026-03-08 (CST)
    (date(2026, 3, 9), 13),    # Monday after DST starts (CDT)
])
def test_window_is_0830_1500_chicago_regardless_of_utc_offset(td, open_utc_hour):
    slots = build_period_slots(td)
    assert slots[0].start_utc == datetime(td.year, td.month, td.day, open_utc_hour, 30, tzinfo=timezone.utc)
    assert slots[-1].end_utc == datetime(td.year, td.month, td.day, open_utc_hour + 7, 0, tzinfo=timezone.utc)
    assert US_CASH_PROFILE.bounds_utc(td) == (slots[0].start_utc, slots[-1].end_utc)


def test_cst_date_excludes_1430_utc_minus_one_hour():
    td = date(2026, 12, 7)
    cst_open = datetime(2026, 12, 7, 14, 30, tzinfo=timezone.utc)
    p = build_tpo_profile((_t(-60, "100.00", cst_open), _t(0, "101.00", cst_open)), ES_PRICE_GRID, td)
    assert _rows(p) == [("101.00", 1, "A")]  # 13:30Z is 07:30 CST -- outside the window
