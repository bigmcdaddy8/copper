"""0Y-G: hand-verified overnight context, multi-scale opening path and reference-encounter facts.

Overnight rows are (seconds after 17:00 CT on the previous evening, price[, size]); cash rows are
(seconds after 08:30:00 CT, price). Every expected value was worked by hand. ES grid 0.25: 1 point =
4 ticks. Trading date Tue 2026-10-06 (CDT): overnight window [2026-10-05 22:00Z, 2026-10-06 13:30Z),
55,800 s. Prior day (unless stated): range 90-110, value 95-105, POC 100, terminal 99.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid5

import pytest

from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import DxLinkTimeAndSaleProvenance
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_analysis import (
    analyze_tpo_dataset,
    opening_auction_facts,
    opening_path_facts,
    overnight_context,
    render_tpo_report,
)
from dicks_laboratory.tpo_day_strength import DominantExtension
from dicks_laboratory.tpo_day_structure import build_day_structure_facts, study_window_terminal
from dicks_laboratory.tpo_opening import (
    ContextOutcome,
    ExtremeOrder,
    OpeningQualityGrade,
    PriorContext,
    Side,
    build_cash_open_session,
    build_opening_auction_facts,
    cash_open_utc,
    render_opening_facts,
)
from dicks_laboratory.tpo_opening_path import (
    OPENING_SCALE_SECONDS,
    EventKind,
    build_opening_path_facts,
    render_opening_path,
)
from dicks_laboratory.tpo_overnight import (
    OvernightQualityGrade,
    OvernightRangeLocation,
    build_overnight_context,
    build_overnight_session,
    overnight_window_utc,
    render_overnight_facts,
)
from dicks_laboratory.tpo_profile import build_tpo_profile
from dicks_laboratory.tpo_structure import build_profile_structure
from dicks_laboratory.volume_profile import ES_PRICE_GRID

D = Decimal
TD = date(2026, 10, 6)
OPEN = cash_open_utc(TD)
ON_START = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)
ESZ6 = "FUTURE:CME:ES:2026-12"


def _s(seconds):
    return ON_START + timedelta(seconds=seconds)


def _at(seconds):
    return OPEN + timedelta(seconds=seconds)


def _on(rows, *, started=ON_START, ended=None, gaps=(), lifecycle="FINALIZED", unknown_capture=False):
    trades = tuple(SimpleNamespace(event_timestamp=_s(r[0]), price=D(str(r[1])), size=D(r[2] if len(r) > 2 else 1))
                   for r in rows)
    if unknown_capture:
        started = ended = None
    else:
        ended = ended or OPEN + timedelta(hours=8)
    return build_overnight_session(trades, ES_PRICE_GRID, TD, ESZ6, started, ended, gaps, lifecycle)


def _cash(rows, gaps=()):
    trades = tuple(SimpleNamespace(event_timestamp=_at(s), price=D(str(p))) for s, p in rows)
    profile = build_tpo_profile(trades, ES_PRICE_GRID, TD)
    facts = build_day_structure_facts(profile, build_profile_structure(profile),
                                      study_window_terminal(trades, profile, ES_PRICE_GRID))
    return build_cash_open_session(trades, profile, facts, ES_PRICE_GRID, ON_START - timedelta(minutes=1),
                                   OPEN + timedelta(hours=8), gaps, "FINALIZED")


def _prior(outcome=ContextOutcome.AVAILABLE, terminal=99, contract=ESZ6):
    return PriorContext(outcome, (), date(2026, 10, 5), ESZ6, prior_trading_date=date(2026, 10, 5),
                        prior_dataset_id="prior", prior_contract=contract, same_contract=contract == ESZ6,
                        profile_high=D(110), profile_low=D(90), poc=D(100), value_area_high=D(105),
                        value_area_low=D(95), ib_high=D(104), ib_low=D(96), terminal_price=D(terminal))


def _ctx(on_rows, cash_rows=((0, 102),), prior=None, **kw):
    return build_overnight_context(_on(on_rows, **kw), _cash(cash_rows), prior or _prior())


def _path(cash_rows, on_rows=((0, 100), (10, 106)), prior=None):
    opening = build_opening_auction_facts(_cash(cash_rows), prior or _prior())
    return build_opening_path_facts(opening, build_overnight_context(_on(on_rows), opening.session, opening.prior))


FULL = [(0, 100, 2), (3600, 104, 3), (7200, 98, 5), (50000, 101, 7)]


# --- window and DST ---------------------------------------------------------------------------------

def test_overnight_window_uses_session_anchors_and_is_dst_correct():
    assert overnight_window_utc(TD) == (ON_START, OPEN)  # CDT
    assert overnight_window_utc(date(2026, 12, 1)) == (datetime(2026, 11, 30, 23, 0, tzinfo=timezone.utc),
                                                      datetime(2026, 12, 1, 14, 30, tzinfo=timezone.utc))  # CST
    # Monday after DST ends (Sun 2026-11-01): Sunday 17:00 CST -> Monday 08:30 CST
    assert overnight_window_utc(date(2026, 11, 2)) == (datetime(2026, 11, 1, 23, 0, tzinfo=timezone.utc),
                                                      datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc))
    # Monday after DST starts (Sun 2026-03-08): Sunday 17:00 CDT -> Monday 08:30 CDT
    assert overnight_window_utc(date(2026, 3, 9)) == (datetime(2026, 3, 8, 22, 0, tzinfo=timezone.utc),
                                                     datetime(2026, 3, 9, 13, 30, tzinfo=timezone.utc))
    # a Monday's overnight starts Sunday evening, never Friday
    assert overnight_window_utc(date(2026, 10, 5))[0] == datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc)
    for d in (TD, date(2026, 12, 1), date(2026, 11, 2), date(2026, 3, 9)):
        start, end = overnight_window_utc(d)
        assert end - start == timedelta(hours=15, minutes=30)


def test_membership_is_half_open_and_ignores_trades_outside():
    s = _on([(-1, 50), (0, 100), (55799.999, 101), (55800, 200)])
    assert (s.first_price, s.high, s.low, s.terminal_price) == (D(100), D(101), D(100), D(101))
    assert s.terminal_utc == _s(55799.999)


# --- quality ----------------------------------------------------------------------------------------

def test_overnight_fully_captured_core_facts():
    s = _on(FULL)
    assert (s.quality.grade, s.quality.reasons) == (OvernightQualityGrade.AVAILABLE, ())
    assert (s.first_price, s.first_utc, s.globex_open_price, s.globex_open_delay) == (D(100), ON_START, D(100),
                                                                                      timedelta(0))
    assert (s.high, s.time_of_high_utc, s.low, s.time_of_low_utc) == (D(104), _s(3600), D(98), _s(7200))
    assert (s.range_ticks, s.range_points, s.extreme_order) == (24, D(6), ExtremeOrder.HIGH_FIRST)
    assert (s.terminal_price, s.terminal_utc) == (D(101), _s(50000))
    assert [b.index for b in s.brackets] == [0, 2, 4, 27]
    assert s.quality.contract == ESZ6 and s.quality.contract_consistent


def test_overnight_starts_late_is_qualified_and_claims_no_globex_open():
    s = _on([(700, 100), (800, 101)], started=_s(600))
    assert s.quality.grade is OvernightQualityGrade.QUALITY_QUALIFIED
    assert s.quality.reasons == ("capture began 0:10:00 after 17:00 CT (overnight window starts late)",)
    assert (s.first_price, s.globex_open_price, s.quality.capture_begins_after_window_start) == (D(100), None, True)
    ctx = build_overnight_context(s, _cash([(0, 102)]), _prior())
    assert [g.name for g in ctx.gaps] == ["FIRST_OVERNIGHT_PRINT_VS_PRIOR_TERMINAL", "CASH_OPEN_VS_PRIOR_TERMINAL",
                                          "CASH_OPEN_VS_OVERNIGHT_TERMINAL"]
    assert ctx.gap("GLOBEX_OPEN_VS_PRIOR_TERMINAL") is None


def test_first_trade_beyond_globex_delay_is_not_the_globex_open_but_quality_unchanged():
    s = _on([(120, 100)])
    assert (s.quality.grade, s.globex_open_price) == (OvernightQualityGrade.AVAILABLE, None)
    assert s.globex_open_unavailable_reason == "first eligible trade 0:02:00 after 17:00 CT (> 0:01:00)"


def test_overnight_gap_qualifies_overnight_but_not_the_cash_opening():
    gap = (("KNOWN_GAP", _s(3600), _s(3660)),)
    s = _on(FULL, gaps=gap)
    assert (s.quality.grade, s.quality.known_gaps_in_window) == (OvernightQualityGrade.QUALITY_QUALIFIED, 1)
    assert "KNOWN_GAP overlaps the overnight window: 1" in s.quality.reasons
    cash = _cash([(0, 102)], gaps=gap)
    assert cash.quality.grade is OpeningQualityGrade.UNQUALIFIED
    f = build_opening_path_facts(build_opening_auction_facts(cash, _prior()),
                                 build_overnight_context(s, cash, _prior()))
    q = f.quality
    assert (q.current_open, q.prior_day_outcome, q.overnight) == (
        OpeningQualityGrade.UNQUALIFIED, ContextOutcome.AVAILABLE, OvernightQualityGrade.QUALITY_QUALIFIED)


def test_unknown_capture_lifecycle_and_missing_overnight():
    assert _on(FULL, unknown_capture=True).quality.reasons == (
        "capture interval not recorded; overnight coverage unverified",)
    assert "lifecycle OPEN (not FINALIZED)" in _on(FULL, lifecycle="OPEN").quality.reasons
    partial = build_overnight_session(  # start recorded (late), end not recorded: both are stated
        tuple(SimpleNamespace(event_timestamp=_s(5), price=D(100), size=D(1)) for _ in (0,)), ES_PRICE_GRID, TD, ESZ6,
        _s(0.0002), None, (), "OPEN")
    assert partial.quality.reasons == ("capture began 0:00:00.000200 after 17:00 CT (overnight window starts late)",
                                       "capture end not recorded; coverage to 08:30 CT unverified",
                                       "lifecycle OPEN (not FINALIZED)")
    assert (partial.globex_open_price, partial.quality.capture_ends_before_window_end) == (None, None)
    assert _on(FULL, ended=_s(50000)).quality.capture_ends_before_window_end is True
    none = _on([])
    assert (none.quality.grade, none.path, none.high) == (OvernightQualityGrade.NOT_AVAILABLE, (), None)
    ctx = build_overnight_context(none, _cash([(0, 102)]), _prior())
    assert (ctx.prior_relation, ctx.inventory, ctx.open_location) == (None, (), None)
    assert "overnight session NOT_AVAILABLE" in ctx.reasons
    assert [g.name for g in ctx.gaps] == ["CASH_OPEN_VS_PRIOR_TERMINAL"]


# --- relationship to the prior cash profile -------------------------------------------------------

def test_overnight_entirely_inside_prior_value():
    r = _ctx(FULL).prior_relation
    assert (r.onh_vs_prior_high_ticks, r.onl_vs_prior_low_ticks, r.onh_vs_vah_ticks, r.onl_vs_val_ticks) == (
        -24, 32, -4, 12)
    assert (r.onh_vs_vah_points, r.onl_vs_val_points) == (D(-1), D(3))
    assert (r.inside_prior_value, r.inside_prior_range, r.overlaps_prior_value, r.overlaps_prior_range) == (
        True, True, True, True)
    assert (r.excursion_above_prior_high_ticks, r.excursion_below_prior_low_ticks, r.excursion_above_vah_ticks,
            r.excursion_below_val_ticks) == (0, 0, 0, 0)


def test_overnight_high_above_prior_high():
    r = _ctx([(0, 100), (10, 111)]).prior_relation
    assert (r.onh_vs_prior_high_ticks, r.excursion_above_prior_high_ticks, r.excursion_above_prior_high_points) == (
        4, 4, D(1))
    assert (r.excursion_above_vah_ticks, r.excursion_above_vah_points, r.inside_prior_range) == (24, D(6), False)


def test_overnight_low_below_prior_low():
    r = _ctx([(0, 100), (10, 88)]).prior_relation
    assert (r.onl_vs_prior_low_ticks, r.excursion_below_prior_low_ticks, r.excursion_below_val_ticks) == (-8, 8, 28)
    assert (r.excursion_below_prior_low_points, r.overlaps_prior_value) == (D(2), True)


def test_overnight_completely_above_prior_range_does_not_overlap():
    r = _ctx([(0, 111), (10, 112)]).prior_relation
    assert (r.overlaps_prior_range, r.overlaps_prior_value, r.excursion_above_prior_high_ticks) == (False, False, 8)


# --- gaps -------------------------------------------------------------------------------------------

def test_three_gaps_are_kept_separate():
    ctx = _ctx(FULL)
    got = {g.name: (g.from_price, g.to_price, g.points, g.ticks, g.direction) for g in ctx.gaps}
    assert got == {
        "GLOBEX_OPEN_VS_PRIOR_TERMINAL": (D(99), D(100), D(1), 4, Side.UP),
        "FIRST_OVERNIGHT_PRINT_VS_PRIOR_TERMINAL": (D(99), D(100), D(1), 4, Side.UP),
        "CASH_OPEN_VS_PRIOR_TERMINAL": (D(99), D(102), D(3), 12, Side.UP),
        "CASH_OPEN_VS_OVERNIGHT_TERMINAL": (D(101), D(102), D(1), 4, Side.UP),
    }
    down = _ctx(FULL, cash_rows=((0, 100.5),))
    assert down.gap("CASH_OPEN_VS_OVERNIGHT_TERMINAL").direction is Side.DOWN
    assert down.gap("CASH_OPEN_VS_OVERNIGHT_TERMINAL").ticks == -2


# --- cash open within the overnight range ---------------------------------------------------------

def test_cash_open_inside_overnight_range():
    ctx = _ctx(FULL)
    assert (ctx.open_location, ctx.open_vs_onh_ticks, ctx.open_vs_onl_ticks) == (
        OvernightRangeLocation.INSIDE_OVERNIGHT_RANGE, -8, 16)
    assert ctx.open_percentile_in_overnight_range == D(16) / D(24)


def test_cash_open_at_overnight_high_and_low():
    hi = _ctx([(0, 100), (10, 104)], cash_rows=((0, 104),))
    assert (hi.open_location, hi.open_vs_onh_ticks, hi.open_percentile_in_overnight_range) == (
        OvernightRangeLocation.AT_OVERNIGHT_HIGH, 0, D(1))
    lo = _ctx([(0, 100), (10, 104)], cash_rows=((0, 100),))
    assert (lo.open_location, lo.open_vs_onl_ticks, lo.open_percentile_in_overnight_range) == (
        OvernightRangeLocation.AT_OVERNIGHT_LOW, 0, D(0))
    above = _ctx([(0, 100), (10, 104)], cash_rows=((0, 105),))
    assert (above.open_location, above.open_vs_onh_ticks) == (OvernightRangeLocation.ABOVE_OVERNIGHT_HIGH, 4)
    flat = _ctx([(0, 100)], cash_rows=((0, 100),))
    assert flat.open_percentile_in_overnight_range is None  # zero overnight range: undefined


# --- inventory as continuous facts ------------------------------------------------------------------

def test_time_mostly_below_prior_terminal_with_brackets_and_volume():
    o = _ctx(FULL).occupancy("PRIOR_TERMINAL")
    assert (o.seconds_above, o.seconds_below, o.seconds_at, o.seconds_observed) == (D(13000), D(42800), D(0), D(55800))
    assert o.fraction_below == D(42800) / D(55800)
    assert (o.brackets_traded, o.brackets_entirely_above, o.brackets_entirely_below,
            o.brackets_touching_or_spanning) == (4, 3, 1, 0)
    assert (o.tpo_rows_above, o.tpo_rows_below, o.tpo_rows_at) == (3, 1, 0)
    assert (o.range_above_ticks, o.range_below_ticks, o.terminal_vs_reference_ticks) == (20, 4, 8)
    assert (o.volume_above, o.volume_below, o.volume_at) == (D(12), D(5), D(0))


def test_time_mostly_above_prior_terminal():
    o = _ctx([(0, 100), (100, 98), (200, 101)]).occupancy("PRIOR_TERMINAL")
    assert (o.seconds_above, o.seconds_below, o.seconds_observed) == (D(55700), D(100), D(55800))


def test_equal_occupancy_and_time_at_the_reference():
    o = _ctx([(0, 100), (27900, 98)]).occupancy("PRIOR_TERMINAL")
    assert (o.seconds_above, o.seconds_below, o.fraction_above, o.fraction_below) == (
        D(27900), D(27900), D("0.5"), D("0.5"))
    at = _ctx([(0, 99), (1800, 99.25), (1801, 98.75)]).occupancy("PRIOR_TERMINAL")
    assert (at.seconds_at, at.seconds_above, at.seconds_below) == (D(1800), D(1), D(53999))
    # bracket 0 printed 99 only; bracket 1's range 98.75-99.25 fills row 99 too (TPO rows span the bracket range)
    assert (at.brackets_touching_or_spanning, at.tpo_rows_at, at.tpo_rows_above, at.tpo_rows_below) == (2, 2, 1, 1)


def test_inventory_references_include_prior_poc_and_value_edges():
    ctx = _ctx(FULL)
    assert [o.reference for o in ctx.inventory] == ["PRIOR_TERMINAL", "PRIOR_POC", "PRIOR_VAH", "PRIOR_VAL"]
    poc = ctx.occupancy("PRIOR_POC")  # 100: 100 is AT for [0, 3600)
    assert (poc.seconds_at, poc.seconds_above, poc.seconds_below) == (D(3600), D(9400), D(42800))


def test_contract_change_suppresses_prior_relative_overnight_facts():
    ctx = _ctx(FULL, prior=_prior(ContextOutcome.CONTRACT_CHANGED, contract="FUTURE:CME:ES:2026-09"))
    assert (ctx.prior_relation, ctx.inventory) == (None, ())
    assert [g.name for g in ctx.gaps] == ["CASH_OPEN_VS_OVERNIGHT_TERMINAL"]
    assert "prior context CONTRACT_CHANGED: prior-relative facts not computed" in ctx.reasons
    assert ctx.open_location is OvernightRangeLocation.INSIDE_OVERNIGHT_RANGE  # same-dataset facts remain


# --- multi-scale opening facts ------------------------------------------------------------------------

def test_open_cross_inside_first_second_and_residence():
    f = _path([(0, 100), (0.2, 101), (0.5, 99), (10, 98), (400, 97)])
    x = f.scale(30)
    assert (x.high, x.low, x.last_price, x.excursion_up_ticks, x.excursion_down_ticks) == (D(101), D(98), D(98), 4, 8)
    assert (x.dominant, x.counter_to_dominant) == (DominantExtension.DOWN, D("0.5"))
    assert (x.open_cross_count, x.first_open_cross_utc, x.last_open_cross_utc, x.open_to_last_cross) == (
        1, _at(0.5), _at(0.5), timedelta(seconds=0.5))
    assert (x.seconds_above_open, x.seconds_below_open, x.seconds_at_open, x.seconds_observed) == (
        D("0.3"), D("29.5"), D("0.2"), D(30))
    assert (x.longest_up_residence, x.longest_up_residence_start_utc) == (timedelta(seconds=0.3), _at(0.2))
    assert (x.longest_down_residence, x.longest_down_residence_start_utc) == (timedelta(seconds=29.5), _at(0.5))
    assert [s.horizon_seconds for s in f.scales] == list(OPENING_SCALE_SECONDS)


def test_no_cross_after_one_second_grace_diagnostic():
    f = _path([(0, 100), (0.2, 101), (0.5, 99), (10, 98), (400, 97)])
    g = f.grace[0]
    assert (g.grace_seconds, g.instant_utc, g.price, g.offset_ticks, g.side, g.held_side) == (
        1, _at(1), D(99), -4, Side.DOWN, Side.DOWN)
    h5, h15, h30 = g.horizons
    assert (h5.minutes, h5.applicable, h5.crossed_open, h5.first_cross_utc, h5.max_favorable_ticks,
            h5.max_counter_ticks) == (5, True, False, None, 8, 0)
    assert (h15.max_favorable_ticks, h15.crossed_open) == (12, False)


def test_cross_after_30_seconds():
    f = _path([(0, 100), (5, 101), (45, 99)])
    assert (f.scale(30).open_cross_count, f.scale(60).open_cross_count, f.scale(60).first_open_cross_utc) == (
        0, 1, _at(45))
    g1, g5 = f.grace[0], f.grace[1]
    assert (g1.side, g1.held_side, g1.horizons[0].crossed_open, g1.horizons[0].first_cross_utc) == (
        Side.NONE, Side.NONE, True, _at(45))
    assert g1.horizons[0].max_favorable_ticks is None  # no held side yet: favorable is undefined
    assert (g5.side, g5.horizons[0].first_cross_utc, g5.horizons[0].max_favorable_ticks,
            g5.horizons[0].max_counter_ticks) == (Side.UP, _at(45), 4, 4)
    assert [g.grace_seconds for g in f.grace] == [1, 5, 15, 30, 60]


def test_late_last_cross():
    f = _path([(0, 100), (1, 101), (2, 99), (1500, 101), (1600, 102)])
    assert (f.scale(900).open_cross_count, f.scale(900).last_open_cross_utc) == (1, _at(2))
    x = f.scale(1800)
    assert (x.open_cross_count, x.last_open_cross_utc, x.open_to_last_cross) == (2, _at(1500), timedelta(seconds=1500))


def test_long_residence_above_and_below_open():
    up = _path([(0, 100), (1, 101), (3000, 99)]).scale(3600)
    assert (up.longest_up_residence, up.longest_down_residence) == (timedelta(seconds=2999), timedelta(seconds=600))
    dn = _path([(0, 100), (1, 99), (3000, 101)]).scale(3600)
    assert (dn.longest_down_residence, dn.longest_down_residence_start_utc) == (timedelta(seconds=2999), _at(1))
    assert dn.longest_up_residence == timedelta(seconds=600)


def test_sixty_minute_scale_matches_accepted_window():
    rows = [(0, 100), (0.2, 101), (0.5, 99), (10, 98), (400, 97), (1500, 103), (3000, 99), (3599, 104), (3700, 90)]
    f = _path(rows)
    x, w = f.scale(3600), f.opening.session.window(60)
    assert (x.high, x.low, x.last_price, x.open_cross_count, x.first_open_cross_utc) == (
        w.high, w.low, w.last_price, w.open_cross_count, w.first_open_cross_utc)


# --- reference encounters (probe / reversal facts) -----------------------------------------------------

def test_reference_touch_then_open_cross():
    f = _path([(0, 104), (60, 105), (120, 103), (400, 102)])
    e = f.encounter("PRIOR_VAH")
    assert (e.side_of_open, e.open_offset_ticks, e.reached_utc, e.reach_beyond_ticks, e.first_touch_utc) == (
        Side.UP, -4, _at(60), 0, _at(60))
    assert (e.excursion_toward_before_reach_ticks, e.opposite_excursion_before_reach_ticks) == (0, 0)
    assert (e.crossed_open_after, e.first_open_cross_after_utc, e.reach_to_cross) == (
        True, _at(120), timedelta(seconds=60))
    assert e.opposite_excursion_after_cross == ((5, 8), (15, 8), (30, 8))
    hi = f.encounter("PRIOR_HIGH")
    assert (hi.reached_utc, hi.min_distance_ticks, hi.crossed_open_after) == (None, 20, None)
    assert f.first_reference_reached.reference == "PRIOR_VAH"
    seq = f.sequence
    assert [(e.timestamp_utc, e.kind, e.reference, e.price) for e in seq.events] == [
        (_at(0), EventKind.OPEN, None, D(104)),
        (_at(60), EventKind.REFERENCE_TOUCH, "PRIOR_VAH", D(105)),
        (_at(60), EventKind.WINDOW_HIGH_FIRST_REACHED, None, D(105)),
        (_at(120), EventKind.OPEN_CROSS_FIRST, None, D(103)),
        (_at(400), EventKind.WINDOW_LOW_FIRST_REACHED, None, D(102)),
    ]
    assert seq.open_cross_count == 1


def test_reference_touch_without_open_cross():
    e = _path([(0, 104), (60, 105), (120, 104.5)]).encounter("PRIOR_VAH")
    assert (e.reached_utc, e.crossed_open_after, e.first_open_cross_after_utc, e.opposite_excursion_after_cross) == (
        _at(60), False, None, ())


def test_reference_jumped_over_is_reached_without_a_touch():
    e = _path([(0, 104), (60, 106), (70, 103)]).encounter("PRIOR_VAH")
    assert (e.reached_utc, e.reach_beyond_ticks, e.first_touch_utc, e.crossed_open_after) == (_at(60), 4, None, True)


def test_multiple_references_touched_including_overnight():
    f = _path([(0, 104), (60, 105), (120, 103), (180, 100), (240, 99)])
    poc = f.encounter("PRIOR_POC")
    assert (poc.side_of_open, poc.reached_utc, poc.excursion_toward_before_reach_ticks,
            poc.opposite_excursion_before_reach_ticks, poc.crossed_open_after) == (Side.DOWN, _at(180), 4, 4, False)
    onl = f.encounter("OVERNIGHT_LOW")  # overnight 100-106
    assert (onl.reached_utc, onl.first_touch_utc) == (_at(180), _at(180))
    assert f.encounter("OVERNIGHT_HIGH").min_distance_ticks == 4
    assert f.first_reference_reached.reference == "PRIOR_VAH"
    kinds = [(e.kind, e.reference) for e in f.sequence.events if e.timestamp_utc == _at(180)]
    assert kinds == [(EventKind.REFERENCE_TOUCH, "PRIOR_POC"), (EventKind.REFERENCE_TOUCH, "OVERNIGHT_LOW")]
    crosses = [(e.timestamp_utc, e.reference) for e in f.sequence.events if e.kind is EventKind.REFERENCE_CROSS]
    assert crosses == [(_at(240), "PRIOR_POC"), (_at(240), "OVERNIGHT_LOW")]


def test_overnight_extremes_join_the_reference_interactions():
    f = _path([(0, 104), (60, 105), (120, 103), (180, 100), (240, 99)])
    rows = {(r.reference, r.horizon_minutes): r for r in f.overnight_reference_interactions}
    assert sorted({k[0] for k in rows}) == ["OVERNIGHT_HIGH", "OVERNIGHT_LOW"]
    onh, onl = rows[("OVERNIGHT_HIGH", 5)], rows[("OVERNIGHT_LOW", 5)]
    assert (onh.open_offset_ticks, onh.min_distance_ticks, onh.touched, onh.crossed) == (-8, 4, False, False)
    assert (onl.open_offset_ticks, onl.touched, onl.first_touch_utc, onl.crossed, onl.first_cross_utc) == (
        16, True, _at(180), True, _at(240))
    # the accepted V1 reference set is unchanged
    assert {r.reference for r in f.opening.reference_interactions} == {
        "PRIOR_HIGH", "PRIOR_LOW", "PRIOR_VAH", "PRIOR_VAL", "PRIOR_POC", "CASH_OPEN"}


def test_reference_at_the_open_tick_is_not_a_first_reach():
    f = _path([(0, 105), (60, 106), (120, 104)])
    e = f.encounter("PRIOR_VAH")
    assert (e.side_of_open, e.reached_utc, e.crossed_open_after) == (Side.NONE, _at(0), None)
    assert f.first_reference_reached is None or f.first_reference_reached.reference != "PRIOR_VAH"


def test_no_prior_and_no_overnight_still_gives_open_scales():
    opening = build_opening_auction_facts(_cash([(0, 100), (5, 101)]), _prior(ContextOutcome.NO_PRIOR_PROFILE))
    f = build_opening_path_facts(opening, None)
    assert (f.encounters, f.overnight_reference_interactions, f.quality.overnight) == ((), (), None)
    assert f.scale(30).excursion_up_ticks == 4 and f.sequence.references == ()


def test_unavailable_cash_open_gives_no_path_facts():
    opening = build_opening_auction_facts(_cash([(120, 100)]), _prior())
    f = build_opening_path_facts(opening, None)
    assert (f.scales, f.grace, f.encounters, f.sequence) == ((), (), (), None)
    assert f.quality.current_open is OpeningQualityGrade.NOT_AVAILABLE


# --- datasets, Monday / Friday, CLI ------------------------------------------------------------------

_NS = UUID("0e5a0000-0000-4000-8000-0000000000f1")


def _db(tmp_path, td, rows, *, contract=(2026, 12)):
    """FINALIZED ES dataset captured from 17:00 CT on the previous session evening; rows = (s after 08:30, price)."""
    dataset_id = uuid5(_NS, str(td))
    es = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", *contract)
    o = cash_open_utc(td)
    trades = tuple(TradeObservation(uuid5(dataset_id, str(i)), dataset_id, i + 1, es, o + timedelta(seconds=s),
                                    D(str(p)), D(1)) for i, (s, p) in enumerate(rows))
    path = tmp_path / f"on-{td}.sqlite3"
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(dataset_id, DatasetKind.HISTORICAL_IMPORT, "overnight-test",
                                       capture_started_at=overnight_window_utc(td)[0],
                                       capture_ended_at=o + timedelta(hours=7)))
    store.save_trade_observations(trades)
    store.save_dxlink_time_and_sale_provenance(tuple(
        DxLinkTimeAndSaleProvenance(t.observation_id, f"evt:{t.dataset_sequence}", t.dataset_sequence,
                                    t.dataset_sequence, t.dataset_sequence, t.dataset_sequence, t.event_timestamp,
                                    event_classification="NEW") for t in trades))
    store.save_quality_events(())
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.FINALIZED)
    store.close()
    store = LaboratoryStore(path, read_only=True)
    try:
        return analyze_tpo_dataset(store, dataset_id)
    finally:
        store.close()


def _full_day(low, high):
    return [(1800 * i + m, p) for i in range(13) for m, p in ((5, low), (6, high))]


def test_monday_overnight_starts_sunday_and_pairs_with_friday(tmp_path):
    fri = _db(tmp_path, date(2026, 10, 2), _full_day(90, 110))  # terminal 110
    mon_open = cash_open_utc(date(2026, 10, 5))
    sunday = (datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc) - mon_open).total_seconds()
    mon = _db(tmp_path, date(2026, 10, 5), [(sunday, 100), (-3600, 101), (0, 102)] + _full_day(99, 103))
    assert (mon.overnight.window_start_utc, mon.overnight.globex_open_price, mon.overnight.quality.grade) == (
        datetime(2026, 10, 4, 22, 0, tzinfo=timezone.utc), D(100), OvernightQualityGrade.AVAILABLE)
    ctx = overnight_context(mon, [fri])
    assert ctx.prior.prior_trading_date == date(2026, 10, 2)
    g = ctx.gap("GLOBEX_OPEN_VS_PRIOR_TERMINAL")
    assert (g.from_price, g.to_price, g.ticks, g.direction) == (D(110), D(100), -40, Side.DOWN)
    assert ctx.occupancy("PRIOR_TERMINAL").seconds_below == D(55800)
    f = opening_path_facts(mon, [fri])
    assert f.quality.prior_day_outcome is ContextOutcome.AVAILABLE and f.overnight.session is mon.overnight
    # accepted 0Y-F facts are identical when computed through the 0Y-G path
    assert f.opening == opening_auction_facts(mon, [fri])
    text = render_tpo_report(mon, overnight=ctx, opening_path=f)
    assert "OVERNIGHT CONTEXT (OVERNIGHT_CONTEXT_V1):" in text and "OPENING PATH DETAIL (OPENING_PATH_FACTS_V1):" in text


def test_dataset_contract_change_overnight(tmp_path):
    prior = _db(tmp_path, date(2026, 10, 5), _full_day(90, 110), contract=(2026, 9))
    cur = _db(tmp_path, date(2026, 10, 6), [(-50000, 100), (0, 102)] + _full_day(99, 103))
    ctx = overnight_context(cur, [prior])
    assert (ctx.prior.outcome, ctx.prior_relation, ctx.inventory) == (ContextOutcome.CONTRACT_CHANGED, None, ())


def test_default_and_opening_outputs_unchanged_without_new_flags(tmp_path):
    fri = _db(tmp_path, date(2026, 10, 2), _full_day(90, 110))
    mon = _db(tmp_path, date(2026, 10, 5), [(-3600, 101), (0, 102)] + _full_day(99, 103))
    plain = render_tpo_report(mon)
    assert "OVERNIGHT" not in plain and "OPENING PATH" not in plain
    opening = render_tpo_report(mon, opening=opening_auction_facts(mon, [fri]))
    assert "OVERNIGHT" not in opening and "OPENING PATH" not in opening


# --- output and immutability ----------------------------------------------------------------------------

FORBIDDEN = ("open drive", "open_drive", "test drive", "test_drive", "rejection reverse", "open auction", "bullish",
             "bearish", "fade", "buy", "sell", "continuation", "probability", "accepted", "rejected", "initiative",
             "responsive", "inventory long", "inventory short", "long inventory", "short inventory", "neutral",
             "strong", "near", "probe")


def test_render_has_no_label_or_interpretation():
    f = _path([(0, 104), (60, 105), (120, 103), (180, 100), (240, 99)])
    text = "\n".join(render_overnight_facts(f.overnight) + render_opening_path(f)).lower()
    text = text.replace("no inventory label, acceptance/rejection, bias or signal", "").replace(
        "no opening type, preferred scale, tolerance, bias or signal", "")
    for word in FORBIDDEN:
        assert word not in text, word
    for needle in ("diagnostic only", "gap cash_open_vs_overnight_terminal", "prior_terminal = last eligible prior-day "
                   "trade before 15:00 ct; it is not the cme settlement", "reference_touch", "first reference reached"):
        assert needle in text, needle
    v1 = "\n".join(render_opening_facts(f.opening))
    assert v1 == "\n".join(render_opening_facts(build_opening_auction_facts(f.opening.session, f.opening.prior)))


def test_facts_are_immutable():
    f = _path([(0, 104), (60, 105)])
    with pytest.raises(FrozenInstanceError):
        f.scales = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        f.overnight.session.high = D(1)  # type: ignore[misc]


def test_study_script_smoke(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    _db(tmp_path, date(2026, 10, 2), _full_day(90, 110))
    _db(tmp_path, date(2026, 10, 5), [(-3600, 101), (0, 102), (60, 112), (400, 99)] + _full_day(99, 103))
    dbs = [str(tmp_path / f"on-{td}.sqlite3") for td in (date(2026, 10, 2), date(2026, 10, 5))]
    before = [Path(p).read_bytes() for p in dbs]
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, "scripts/dicks_lab_mp_overnight_study.py", str(out), *dbs], cwd=repo, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    report = (out / "overnight_study.md").read_text()
    for needle in ("| 2026-10-05 |", "## Multi-scale opening facts", "## Grace-instant diagnostics (DIAGNOSTIC ONLY)",
                   "## Mechanical inspection set", "first reference reached"):
        assert needle in report, needle
    assert len(list((out / "reports").iterdir())) == 2
    assert [Path(p).read_bytes() for p in dbs] == before
    lowered = report.lower()
    for word in ("open drive", "test drive", "rejection reverse", "bullish", "bearish", "long inventory",
                 "short inventory", "accepted", "rejected"):
        assert word not in lowered, word


def test_profile_cli_new_flags(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    _db(tmp_path, date(2026, 10, 2), _full_day(90, 110))
    _db(tmp_path, date(2026, 10, 5), [(-3600, 101), (0, 102)] + _full_day(99, 103))
    cur, prior = tmp_path / "on-2026-10-05.sqlite3", tmp_path / "on-2026-10-02.sqlite3"
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}

    def run(*args):
        r = subprocess.run([sys.executable, "scripts/dicks_lab_tpo_profile.py", str(cur), *args], cwd=repo, env=env,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout

    base = run("--opening-facts", "--prior-database", str(prior))
    both = run("--opening-facts", "--overnight-facts", "--opening-path-detail", "--prior-database", str(prior))
    assert "OVERNIGHT CONTEXT" not in base and "OPENING PATH DETAIL" not in base
    assert "OVERNIGHT CONTEXT (OVERNIGHT_CONTEXT_V1):" in both and "OPENING PATH DETAIL" in both
    head, tail = base.split("\nTPO matrix", 1)
    assert both.startswith(head) and both.endswith("\nTPO matrix" + tail)  # the accepted sections are unchanged
