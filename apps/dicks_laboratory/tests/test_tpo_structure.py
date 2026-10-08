"""0Y-B: hand-verified Market Profile structural facts.

Each fixture's rows are written out in a comment and the expected zones,
extremes and candidates were worked by hand from those rows.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from dicks_laboratory.tpo_profile import build_tpo_profile
from dicks_laboratory.tpo_structure import (
    EXCESS_MIN_TAIL_LEVELS,
    POOR_EXTREME_MIN_TPOS,
    CandidateStatus,
    IbRelation,
    ValueRelation,
    ZoneLocation,
    build_profile_structure,
)
from dicks_laboratory.volume_profile import ES_PRICE_GRID, PriceGrid

D = Decimal
TD = date(2026, 10, 6)
OPEN = datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)
YES, NO, NC = CandidateStatus.YES, CandidateStatus.NO, CandidateStatus.NOT_CLASSIFIED


def _r(period, low, high):
    return [SimpleNamespace(event_timestamp=OPEN + timedelta(minutes=period * 30 + 1), price=D(low)),
            SimpleNamespace(event_timestamp=OPEN + timedelta(minutes=period * 30 + 2), price=D(high))]


def _build(*ranges, grid=ES_PRICE_GRID):
    trades = [t for period, low, high in ranges for t in _r(period, low, high)]
    profile = build_tpo_profile(tuple(trades), grid, TD)
    return profile, build_profile_structure(profile)


def _zones(s):
    return [(str(z.low), str(z.high), z.level_count, z.tick_count, str(z.span_points), z.periods, z.location)
            for z in s.zones]


def test_policy_thresholds_are_explicit():
    assert (EXCESS_MIN_TAIL_LEVELS, POOR_EXTREME_MIN_TPOS) == (2, 2)


# --- one-TPO zones ----------------------------------------------------------------

def test_no_one_tpo_levels_and_flat_extremes_printed_by_multiple_periods():
    # 100.00..100.50 all AB
    p, s = _build((0, "100.00", "100.50"), (1, "100.00", "100.50"))
    assert s.one_tpo_levels == () and s.zones == ()
    for ex, price in ((s.upper, "100.50"), (s.lower, "100.00")):
        assert (str(ex.price), ex.letters_at_extreme, ex.tpo_count_at_extreme) == (price, "AB", 2)
        assert (ex.tail_level_count, ex.tail_tick_count, ex.tail_span_points, ex.tail_inner_price) == (0, 0, D("0"), None)
        assert (ex.excess_candidate, ex.poor_candidate) == (NO, YES)  # candidate poor high and poor low


def test_one_interior_zone_exactly_one_tick():
    # 101.00 AC | 100.75 AC | 100.50 A | 100.25 AB | 100.00 AB
    p, s = _build((0, "100.00", "101.00"), (1, "100.00", "100.25"), (2, "100.75", "101.00"))
    assert [(str(lv.price), lv.periods) for lv in s.one_tpo_levels] == [("100.50", "A")]
    assert _zones(s) == [("100.50", "100.50", 1, 1, "0.00", "A", ZoneLocation.INTERIOR)]
    z = s.zones[0]
    assert (p.value_area.low, p.value_area.high) == (D("100.25"), D("101.00"))
    assert (z.ib_relation, z.value_relation) == (IbRelation.INSIDE_IB, ValueRelation.INSIDE_VALUE)
    assert s.interior_zones == s.zones


def test_multiple_separated_interior_zones_and_multi_tick_run():
    # A 100.00-103.00; B 100.00-100.25; C 101.00-101.25; D 102.75-103.00
    p, s = _build((0, "100.00", "103.00"), (1, "100.00", "100.25"), (2, "101.00", "101.25"), (3, "102.75", "103.00"))
    assert _zones(s) == [
        ("100.50", "100.75", 2, 2, "0.25", "A", ZoneLocation.INTERIOR),
        ("101.50", "102.50", 5, 5, "1.00", "A", ZoneLocation.INTERIOR),
    ]
    assert s.zones[1].level_periods == tuple((D(x), "A") for x in ("101.50", "101.75", "102.00", "102.25", "102.50"))
    # hand-worked VA: POC 101.25, expands to 100.25-102.75 (15/19)
    assert (p.poc, p.value_area.low, p.value_area.high) == (D("101.25"), D("100.25"), D("102.75"))
    assert all(z.value_relation is ValueRelation.INSIDE_VALUE and z.ib_relation is IbRelation.INSIDE_IB for z in s.zones)
    assert (s.upper.poor_candidate, s.lower.poor_candidate) == (YES, YES)


# --- extremes / tails ---------------------------------------------------------------

def test_upper_extreme_tail_and_excess_high_candidate():
    # 101.25 B | 101.00 B | 100.75 B | 100.50..100.00 AB
    p, s = _build((0, "100.00", "100.50"), (1, "100.00", "101.25"))
    assert _zones(s) == [("100.75", "101.25", 3, 3, "0.50", "B", ZoneLocation.UPPER_EXTREME)]
    u = s.upper
    assert (str(u.price), u.letters_at_extreme, u.tpo_count_at_extreme) == ("101.25", "B", 1)  # one period
    assert (u.tail_level_count, u.tail_tick_count, u.tail_span_points, u.tail_inner_price) == (3, 3, D("0.50"), D("100.75"))
    assert (u.tail_periods, u.tail_formed_in_final_period) == ("B", False)
    assert (u.excess_candidate, u.poor_candidate) == (YES, NO)
    assert (s.lower.excess_candidate, s.lower.poor_candidate) == (NO, YES)


def test_lower_extreme_tail_and_excess_low_candidate():
    # 101.25..100.75 AB | 100.50 B | 100.25 B | 100.00 B
    p, s = _build((0, "100.75", "101.25"), (1, "100.00", "101.25"))
    assert _zones(s) == [("100.00", "100.50", 3, 3, "0.50", "B", ZoneLocation.LOWER_EXTREME)]
    lo = s.lower
    assert (lo.tail_level_count, lo.tail_inner_price, lo.excess_candidate, lo.poor_candidate) == (3, D("100.50"), YES, NO)
    assert (s.upper.excess_candidate, s.upper.poor_candidate) == (NO, YES)


def test_tails_on_both_extremes():
    # 101.50 B | 101.25 B | 101.00..100.50 AB | 100.25 A | 100.00 A
    p, s = _build((0, "100.00", "101.00"), (1, "100.50", "101.50"))
    assert _zones(s) == [("100.00", "100.25", 2, 2, "0.25", "A", ZoneLocation.LOWER_EXTREME),
                         ("101.25", "101.50", 2, 2, "0.25", "B", ZoneLocation.UPPER_EXTREME)]
    assert (s.upper.excess_candidate, s.lower.excess_candidate) == (YES, YES)
    assert (s.upper.poor_candidate, s.lower.poor_candidate) == (NO, NO)
    assert s.zones[0].value_relation is ValueRelation.OVERLAPPING_BOUNDARY  # VA 100.25-101.25
    assert s.zones[1].value_relation is ValueRelation.OVERLAPPING_BOUNDARY


def test_one_row_tails_are_neither_excess_nor_poor():
    # 100.75 B | 100.50 AB | 100.25 AB | 100.00 A
    p, s = _build((0, "100.00", "100.50"), (1, "100.25", "100.75"))
    for ex in (s.upper, s.lower):
        assert (ex.tpo_count_at_extreme, ex.tail_level_count, ex.tail_span_points) == (1, 1, D("0"))
        assert (ex.excess_candidate, ex.poor_candidate) == (NO, NO)


def test_tail_formed_by_final_period_is_reported_not_filtered():
    # M (period 12) prints 99.00-100.00 below A/B
    p, s = _build((0, "100.00", "101.00"), (1, "100.00", "101.00"), (12, "99.00", "100.00"))
    lo = s.lower
    assert (lo.tail_level_count, lo.tail_periods, lo.tail_formed_in_final_period) == (4, "M", True)
    assert lo.excess_candidate is YES


def test_zone_can_span_two_periods_and_overlap_ib_and_value_boundary():
    # 102.00..101.25 C | 101.00 A | 100.75 A | 100.50..100.00 AB ; IB 100.00-101.00, VA 100.00-101.50
    p, s = _build((0, "100.00", "101.00"), (1, "100.00", "100.50"), (2, "101.25", "102.00"))
    assert _zones(s) == [("100.75", "102.00", 6, 6, "1.25", "AC", ZoneLocation.UPPER_EXTREME)]
    z = s.zones[0]
    assert (p.value_area.low, p.value_area.high) == (D("100.00"), D("101.50"))
    assert (z.ib_relation, z.value_relation) == (IbRelation.OVERLAPPING_IB, ValueRelation.OVERLAPPING_BOUNDARY)
    assert s.upper.tail_periods == "AC"


def test_zone_above_ib_and_above_vah():
    # 102.00..101.25 C | 101.00 ABC | 100.75 ABC | 100.50..100.00 AB ; VA 100.00-101.00
    p, s = _build((0, "100.00", "101.00"), (1, "100.00", "101.00"), (2, "100.75", "102.00"))
    z = s.zones[0]
    assert (str(z.low), str(z.high), z.periods) == ("101.25", "102.00", "C")
    assert (z.ib_relation, z.value_relation) == (IbRelation.ABOVE_IB, ValueRelation.ABOVE_VAH)


def test_single_period_profile_is_not_classified():
    p, s = _build((0, "100.00", "100.50"))
    assert _zones(s) == [("100.00", "100.50", 3, 3, "0.50", "A", ZoneLocation.ENTIRE_PROFILE)]
    assert {s.upper.excess_candidate, s.upper.poor_candidate, s.lower.excess_candidate} == {NC}


# --- tick-grid adjacency --------------------------------------------------------------

def test_es_adjacent_one_tpo_rows_form_one_zone():
    # 7771.00 AB | 7770.75 AB | 7770.50 A | 7770.25 A | 7770.00 A
    p, s = _build((0, "7770.00", "7771.00"), (1, "7770.75", "7771.00"))
    assert _zones(s) == [("7770.00", "7770.50", 3, 3, "0.50", "A", ZoneLocation.LOWER_EXTREME)]


def test_es_rows_separated_by_a_multi_tpo_row_do_not_join():
    # 7770.50 A | 7770.25 AB | 7770.00 A
    p, s = _build((0, "7770.00", "7770.50"), (1, "7770.25", "7770.25"))
    assert _zones(s) == [("7770.00", "7770.00", 1, 1, "0.00", "A", ZoneLocation.LOWER_EXTREME),
                         ("7770.50", "7770.50", 1, 1, "0.00", "A", ZoneLocation.UPPER_EXTREME)]


def test_es_rows_separated_by_an_untraded_row_do_not_join():
    # 7770.50 B | 7770.25 (0 TPOs) | 7770.00 A
    p, s = _build((0, "7770.00", "7770.00"), (1, "7770.50", "7770.50"))
    assert [lv.tpo_count for lv in p.levels] == [1, 0, 1]
    assert _zones(s) == [("7770.00", "7770.00", 1, 1, "0.00", "A", ZoneLocation.LOWER_EXTREME),
                         ("7770.50", "7770.50", 1, 1, "0.00", "B", ZoneLocation.UPPER_EXTREME)]


def test_non_es_tick_grid_adjacency():
    cl = PriceGrid("CL", D("0.01"), "TEST_CL_GRID", "TEST_CL_GRID_V1")
    # A 70.00-70.03, B 70.03-70.05, C 70.01
    p, s = _build((0, "70.00", "70.03"), (1, "70.03", "70.05"), (2, "70.01", "70.01"), grid=cl)
    # rows: 70.05 B, 70.04 B, 70.03 AB, 70.02 A, 70.01 AC, 70.00 A
    assert [(str(lv.price), lv.periods) for lv in reversed(p.levels)] == [
        ("70.05", "B"), ("70.04", "B"), ("70.03", "AB"), ("70.02", "A"), ("70.01", "AC"), ("70.00", "A")]
    assert _zones(s) == [("70.00", "70.00", 1, 1, "0.00", "A", ZoneLocation.LOWER_EXTREME),
                         ("70.02", "70.02", 1, 1, "0.00", "A", ZoneLocation.INTERIOR),
                         ("70.04", "70.05", 2, 2, "0.01", "B", ZoneLocation.UPPER_EXTREME)]
    assert s.upper.excess_candidate is YES and s.lower.excess_candidate is NO


# --- IB extension detail and period range facts ----------------------------------------

_IB = ((0, "100.00", "101.00"), (1, "100.50", "101.50"))  # IB 100.00-101.50, range 1.50


def test_ib_extension_above_only():
    p, s = _build(*_IB, (2, "101.00", "102.00"), (5, "101.00", "101.75"))
    x = s.ib_extension
    assert (x.max_extension_above, x.max_extension_above_ticks, x.max_extension_below) == (D("0.50"), 2, D("0"))
    assert x.extension_above_fraction_of_ib == D("0.50") / D("1.50") and x.extension_below_fraction_of_ib == 0
    assert (x.periods_new_post_ib_high, x.periods_new_post_ib_low) == ("C", "")
    by = {ps.label: ps for ps in s.periods}
    assert (by["C"].new_profile_high, by["C"].extended_ib_high, by["C"].high_extension, by["C"].low_extension) == (
        True, True, D("0.50"), D("0"))
    assert (by["F"].new_profile_high, by["F"].extended_ib_high, by["F"].high_extension) == (False, True, D("0.25"))
    assert (by["F"].extended_ib_low, by["F"].new_profile_low) == (False, False)


def test_ib_extension_below_only():
    p, s = _build(*_IB, (2, "100.50", "101.00"), (3, "99.00", "100.50"))
    x = s.ib_extension
    assert (x.max_extension_below, x.max_extension_below_ticks, x.periods_new_post_ib_low) == (D("1.00"), 4, "D")
    assert (x.max_extension_above, x.periods_new_post_ib_high) == (D("0"), "")
    by = {ps.label: ps for ps in s.periods}
    assert (by["D"].new_profile_low, by["D"].extended_ib_low, by["D"].low_extension) == (True, True, D("1.00"))
    assert (by["C"].extended_ib_high, by["C"].extended_ib_low) == (False, False)


def test_ib_extension_both_ways_lists_every_new_post_ib_extreme():
    p, s = _build(*_IB, (2, "101.00", "102.00"), (4, "99.50", "100.25"), (12, "99.25", "100.00"))
    x = s.ib_extension
    assert (x.periods_new_post_ib_high, x.periods_new_post_ib_low) == ("C", "EM")
    assert (x.max_extension_above, x.max_extension_below, x.max_extension_below_ticks) == (D("0.50"), D("0.75"), 3)
    assert x.extension_below_fraction_of_ib == D("0.75") / D("1.50")


def test_no_ib_extension():
    p, s = _build(*_IB, (2, "100.75", "101.25"))
    x = s.ib_extension
    assert (x.max_extension_above, x.max_extension_below) == (D("0"), D("0"))
    assert (x.periods_new_post_ib_high, x.periods_new_post_ib_low) == ("", "")
    assert x.extension_above_fraction_of_ib == 0


def test_zero_ib_range_has_no_fraction():
    p, s = _build((0, "100.00", "100.00"), (1, "100.00", "100.00"), (2, "100.00", "100.25"))
    x = s.ib_extension
    assert (x.ib_range, x.ib_range_is_zero, x.max_extension_above) == (D("0.00"), True, D("0.25"))
    assert x.extension_above_fraction_of_ib is None and x.extension_below_fraction_of_ib is None


def test_period_facts_for_ib_and_empty_periods_are_not_applicable():
    p, s = _build(*_IB, (3, "100.00", "101.75"))
    by = {ps.label: ps for ps in s.periods}
    assert (by["A"].new_profile_high, by["A"].extended_ib_high) == (None, None)  # no prior; IB period
    assert (by["B"].new_profile_high, by["B"].new_profile_low, by["B"].extended_ib_high) == (True, False, None)
    assert by["C"] == type(by["C"])("C", None, None, None, None, None, None, None, None)  # no trades
    assert (by["D"].new_profile_high, by["D"].extended_ib_high, by["D"].high_extension) == (True, True, D("0.25"))


def test_structure_does_not_mutate_profile():
    p, _ = _build(*_IB, (2, "101.00", "102.00"))
    before = repr(p)
    build_profile_structure(p)
    assert repr(p) == before
