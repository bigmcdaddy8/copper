"""0Y-F: hand-verified opening-auction facts and prior-trading-date context.

Each fixture lists its trades as (seconds after 08:30:00 CT, price); every
expected value was worked by hand from that list. ES grid 0.25: 1 point = 4 ticks.
Prior day (unless stated): range 90-110, value 95-105, POC 100, terminal 99.
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
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, build_prior_context, opening_auction_facts, render_tpo_report
from dicks_laboratory.tpo_day_strength import DominantExtension
from dicks_laboratory.tpo_day_structure import build_day_structure_facts, study_window_terminal
from dicks_laboratory.tpo_opening import (
    CASH_OPEN_MAX_DELAY,
    ContextOutcome,
    ExtremeOrder,
    GapExtent,
    OpeningQualityGrade,
    PriorContext,
    RangeLocation,
    Side,
    ValueLocation,
    build_cash_open_session,
    build_opening_auction_facts,
    cash_open_utc,
    prior_trading_date,
    render_opening_facts,
)
from dicks_laboratory.tpo_profile import build_tpo_profile
from dicks_laboratory.tpo_structure import build_profile_structure
from dicks_laboratory.volume_profile import ES_PRICE_GRID

D = Decimal
TD = date(2026, 10, 6)  # CDT: 08:30 CT = 13:30Z
OPEN = cash_open_utc(TD)
ESZ6 = "FUTURE:CME:ES:2026-12"


def _trades(rows, td=TD):
    o = cash_open_utc(td)
    return tuple(SimpleNamespace(event_timestamp=o + timedelta(seconds=s), price=D(str(p))) for s, p in rows)


def _session(rows, *, td=TD, started=None, ended=None, gaps=(), lifecycle="FINALIZED", unknown_capture=False):
    trades = _trades(rows, td)
    o = cash_open_utc(td)
    profile = build_tpo_profile(trades, ES_PRICE_GRID, td)
    facts = build_day_structure_facts(profile, build_profile_structure(profile),
                                      study_window_terminal(trades, profile, ES_PRICE_GRID))
    if unknown_capture:
        started = ended = None
    else:
        started = started or o - timedelta(hours=10)
        ended = ended or o + timedelta(hours=8)
    return build_cash_open_session(trades, profile, facts, ES_PRICE_GRID, started, ended, gaps, lifecycle)


def _prior(high=110, low=90, vah=105, val=95, poc=100, terminal=99, outcome=ContextOutcome.AVAILABLE):
    return PriorContext(outcome, (), date(2026, 10, 5), ESZ6, prior_trading_date=date(2026, 10, 5),
                        prior_dataset_id="prior", prior_contract=ESZ6, same_contract=True,
                        profile_high=D(high), profile_low=D(low), poc=D(poc), value_area_high=D(vah),
                        value_area_low=D(val), ib_high=D(104), ib_low=D(96), terminal_price=D(terminal))


def _facts(rows, prior=None, **kw):
    return build_opening_auction_facts(_session(rows, **kw), prior or _prior())


def _at(seconds):
    return OPEN + timedelta(seconds=seconds)


def _ref(facts, name, minutes):
    return next(r for r in facts.reference_interactions if r.reference == name and r.horizon_minutes == minutes)


# --- cash open ------------------------------------------------------------------------------------

def test_cash_open_is_first_trade_at_or_after_0830_ct_and_dst_correct():
    assert cash_open_utc(date(2026, 10, 6)) == datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)  # CDT
    assert cash_open_utc(date(2026, 12, 1)) == datetime(2026, 12, 1, 14, 30, tzinfo=timezone.utc)  # CST
    assert cash_open_utc(date(2026, 11, 2)) == datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)  # Monday after DST end
    s = _session([(-5, 99), (0.25, 100), (1, 101)])  # -5 s is before 08:30 and ignored
    co = s.cash_open
    assert (co.price, co.timestamp_utc, co.delay, co.unavailable_reason) == (D(100), _at(0.25), timedelta(seconds=0.25), None)
    assert s.quality.grade is OpeningQualityGrade.UNQUALIFIED


def test_cst_trading_date_opens_at_1430z():
    s = _session([(0, 100), (60, 101)], td=date(2026, 12, 1))
    assert s.cash_open.timestamp_utc == datetime(2026, 12, 1, 14, 30, tzinfo=timezone.utc)
    assert s.window(5).high == D(101)


def test_open_within_tolerance_records_delay():
    s = _session([(30, 100), (60, 101)])
    assert (s.cash_open.price, s.cash_open.delay, CASH_OPEN_MAX_DELAY) == (D(100), timedelta(seconds=30), timedelta(seconds=60))


def test_missing_opening_prints_never_invent_a_price():
    s = _session([(120, 100), (180, 101)])
    assert (s.cash_open.price, s.quality.grade, s.windows, s.path) == (None, OpeningQualityGrade.NOT_AVAILABLE, (), ())
    assert "0:02:00 after 08:30:00 CT" in s.cash_open.unavailable_reason
    f = build_opening_auction_facts(s, _prior())
    assert (f.outcome, f.range_location, f.reference_interactions) == (ContextOutcome.CURRENT_OPEN_INCOMPLETE, None, ())
    assert "*** OPENING FACTS NOT AVAILABLE ***" in "\n".join(render_opening_facts(f))


def test_capture_starting_after_open_is_not_available_and_unknown_capture_is_qualified():
    late = _session([(0, 100)], started=_at(10))
    assert late.quality.grade is OpeningQualityGrade.NOT_AVAILABLE
    assert late.quality.reasons[0] == "opening window [08:30, 09:30) CT not fully captured"
    unknown = _session([(0, 100)], unknown_capture=True)
    assert unknown.quality.grade is OpeningQualityGrade.QUALITY_QUALIFIED and unknown.cash_open.price == D(100)
    assert unknown.quality.reasons == ("capture interval not recorded; 08:30 opening coverage unverified",)


def test_gap_in_opening_window_qualifies_but_overnight_and_later_gaps_do_not():
    rows = [(0, 100), (60, 101)]
    known = _session(rows, gaps=(("KNOWN_GAP", _at(600), _at(660)),))
    assert (known.quality.grade, known.quality.known_gaps_in_opening_window) == (OpeningQualityGrade.QUALITY_QUALIFIED, 1)
    assert "KNOWN_GAP overlaps the opening window: 1" in known.quality.reasons
    overnight = _session(rows, gaps=(("KNOWN_GAP", _at(-5 * 3600), _at(-5 * 3600 + 2)),))
    assert overnight.quality.grade is OpeningQualityGrade.UNQUALIFIED
    later = _session(rows, gaps=(("SUSPECTED_GAP", _at(4 * 3600), _at(4 * 3600 + 5)),))
    assert (later.quality.grade, later.quality.gaps_later_in_study_window) == (OpeningQualityGrade.UNQUALIFIED, 1)
    assert _session(rows, lifecycle="OPEN").quality.grade is OpeningQualityGrade.QUALITY_QUALIFIED


# --- location and gap --------------------------------------------------------------------------

def test_open_inside_prior_value():
    f = _facts([(0, 100), (60, 101)])
    assert (f.outcome, f.range_location, f.value_location) == (
        ContextOutcome.AVAILABLE, RangeLocation.INSIDE_PRIOR_RANGE, ValueLocation.INSIDE_PRIOR_VALUE)
    assert (f.open_vs_prior_high_ticks, f.open_vs_prior_low_ticks) == (-40, 40)
    assert (f.open_vs_vah_ticks, f.open_vs_val_ticks, f.open_vs_poc_ticks) == (-20, 20, 0)
    assert (f.open_vs_vah_points, f.open_vs_val_points, f.open_vs_poc_points) == (D(-5), D(5), D(0))
    assert (f.gap_points, f.gap_ticks, f.gap_direction, f.gap_extent) == (
        D(1), 4, Side.UP, GapExtent.WITHIN_PRIOR_RANGE)


def test_open_outside_value_inside_range():
    f = _facts([(0, 107)])
    assert (f.range_location, f.value_location, f.open_vs_vah_ticks) == (
        RangeLocation.INSIDE_PRIOR_RANGE, ValueLocation.ABOVE_PRIOR_VALUE, 8)


def test_open_above_and_below_prior_range():
    above = _facts([(0, 112)])
    assert (above.range_location, above.value_location, above.gap_extent, above.gap_ticks, above.gap_direction) == (
        RangeLocation.ABOVE_PRIOR_RANGE, ValueLocation.ABOVE_PRIOR_VALUE, GapExtent.BEYOND_PRIOR_RANGE, 52, Side.UP)
    below = _facts([(0, 88)])
    assert (below.range_location, below.value_location, below.open_vs_prior_low_ticks, below.gap_direction) == (
        RangeLocation.BELOW_PRIOR_RANGE, ValueLocation.BELOW_PRIOR_VALUE, -8, Side.DOWN)


@pytest.mark.parametrize(("price", "rng", "val"), [
    (105, RangeLocation.INSIDE_PRIOR_RANGE, ValueLocation.AT_PRIOR_VAH),
    (95, RangeLocation.INSIDE_PRIOR_RANGE, ValueLocation.AT_PRIOR_VAL),
    (110, RangeLocation.AT_PRIOR_HIGH, ValueLocation.ABOVE_PRIOR_VALUE),
    (90, RangeLocation.AT_PRIOR_LOW, ValueLocation.BELOW_PRIOR_VALUE),
])
def test_open_exactly_at_reference(price, rng, val):
    f = _facts([(0, price)], prior=_prior(terminal=price))
    assert (f.range_location, f.value_location, f.gap_ticks, f.gap_direction) == (rng, val, 0, Side.NONE)
    assert f.gap_extent is GapExtent.WITHIN_PRIOR_RANGE


# --- windows, revisits, crossings --------------------------------------------------------------

def test_open_moves_only_up_never_revisited():
    s = _session([(0, 100), (60, 100.25), (120, 100.5), (400, 101), (1000, 101.5), (2000, 102)])
    w5, w30 = s.window(5), s.window(30)
    assert (w5.high, w5.low, w5.range_ticks, w5.last_price) == (D("100.5"), D(100), 2, D("100.5"))
    assert (w5.excursion_up_ticks, w5.excursion_down_ticks, w5.dominant, w5.counter_to_dominant) == (
        2, 0, DominantExtension.UP, D(0))
    assert (w5.first_direction, w5.first_above_open_utc, w5.first_below_open_utc) == (Side.UP, _at(60), None)
    assert (w5.time_of_high_utc, w5.time_of_low_utc, w5.extreme_order) == (_at(120), _at(0), ExtremeOrder.LOW_FIRST)
    assert (w30.excursion_up_ticks, w30.first_open_revisit_utc, w30.open_cross_count) == (6, None, 0)
    assert (w30.traded_above_open, w30.traded_below_open) == (True, False)
    assert s.window(60).excursion_up_ticks == 8


def test_open_moves_only_down():
    w = _session([(0, 100), (60, 99.75), (120, 99)]).window(5)
    assert (w.excursion_up_ticks, w.excursion_down_ticks, w.dominant, w.first_direction) == (
        0, 4, DominantExtension.DOWN, Side.DOWN)
    assert (w.extreme_order, w.up_first_then_crossed_below) == (ExtremeOrder.HIGH_FIRST, False)


def test_up_then_crosses_below_open():
    # 100 open; 101 @60; 102 @120 (5m high); 99 @400 (cross below); 100 @1000 (revisit); 103 @1500 (cross above)
    s = _session([(0, 100), (60, 101), (120, 102), (400, 99), (1000, 100), (1500, 103)])
    w5, w15, w30 = s.window(5), s.window(15), s.window(30)
    assert (w5.excursion_up_ticks, w5.excursion_down_ticks, w5.open_cross_count) == (8, 0, 0)
    assert (w15.excursion_down_ticks, w15.open_cross_count, w15.first_open_cross_utc) == (4, 1, _at(400))
    assert (w15.up_first_then_crossed_below, w15.down_first_then_crossed_above) == (True, False)
    assert (w15.extreme_order, w15.dominant, w15.counter_to_dominant) == (ExtremeOrder.HIGH_FIRST, DominantExtension.UP,
                                                                         D("0.5"))
    assert w15.first_open_revisit_utc is None
    assert (w30.first_open_revisit_utc, w30.open_cross_count, w30.high) == (_at(1000), 2, D(103))


def test_down_then_crosses_above_open():
    w = _session([(0, 100), (60, 99), (200, 100.5)]).window(5)
    assert (w.first_direction, w.down_first_then_crossed_above, w.first_open_cross_utc, w.open_cross_count) == (
        Side.DOWN, True, _at(200), 1)


def test_open_revisited_once_without_crossing():
    w = _session([(0, 100), (60, 101), (120, 100), (180, 101.5)]).window(5)
    assert (w.first_open_revisit_utc, w.open_cross_count, w.first_open_cross_utc) == (_at(120), 0, None)


def test_open_crossed_multiple_times_through_and_via_touch():
    # above, below, above, at-open (keeps side), below
    w = _session([(0, 100), (30, 100.5), (60, 99.5), (90, 100.5), (100, 100), (120, 99.5)]).window(5)
    assert (w.open_cross_count, w.first_open_cross_utc, w.first_open_revisit_utc) == (3, _at(60), _at(100))


# --- reference interactions ----------------------------------------------------------------------

def test_touch_prior_vah_then_move_away():
    f = _facts([(0, 103), (60, 104), (120, 105), (180, 104), (240, 102)])
    r = _ref(f, "PRIOR_VAH", 5)
    assert (r.price, r.open_offset_ticks, r.min_distance_ticks, r.touched, r.first_touch_utc, r.crossed) == (
        D(105), -8, 0, True, _at(120), False)
    assert _ref(f, "PRIOR_HIGH", 5).min_distance_ticks == 20 and not _ref(f, "PRIOR_HIGH", 5).touched


def test_touch_prior_val_then_move_away():
    f = _facts([(0, 97), (60, 95), (120, 96.5)])
    r = _ref(f, "PRIOR_VAL", 15)
    assert (r.touched, r.first_touch_utc, r.crossed, r.min_distance_ticks, r.open_offset_ticks) == (
        True, _at(60), False, 0, 8)


def test_crossing_a_reference_and_cash_open_reference_always_present():
    f = _facts([(0, 104), (60, 105.5), (120, 104)])
    r = _ref(f, "PRIOR_VAH", 5)
    assert (r.touched, r.crossed, r.first_cross_utc, r.min_distance_ticks) == (False, True, _at(60), 2)
    o = _ref(f, "CASH_OPEN", 60)
    assert (o.open_offset_ticks, o.touched, o.first_touch_utc) == (0, True, _at(0))
    no_prior = build_opening_auction_facts(f.session, _prior(outcome=ContextOutcome.NO_PRIOR_PROFILE))
    assert {r.reference for r in no_prior.reference_interactions} == {"CASH_OPEN"}
    assert (no_prior.outcome, no_prior.value_zone, no_prior.gap_ticks) == (ContextOutcome.NO_PRIOR_PROFILE, None, None)


# --- prior value / range entry and exit ------------------------------------------------------------

def test_outside_value_open_reenters_value():
    f = _facts([(0, 107), (600, 106), (900, 105), (1200, 106)])
    v, r = f.value_zone, f.range_zone
    assert (v.open_inside, v.first_entry_utc, v.first_exit_above_utc) == (False, _at(900), None)
    # inside value only from 900 to 1200 during A (A = first 1800 s)
    assert (v.seconds_inside_during_a, v.a_seconds_observed) == (D(300), D(1800))
    assert (v.a_rows_inside, v.a_rows) == (1, 9)  # A 105-107: only the 105 row is in value
    assert (r.open_inside, r.first_entry_utc, r.first_exit_above_utc, r.first_return_utc) == (True, None, None, None)


def test_outside_range_open_reenters_range():
    z = _facts([(0, 112), (300, 110.5), (600, 110)]).range_zone
    assert (z.open_inside, z.first_entry_utc) == (False, _at(600))


def test_inside_value_open_exits_and_returns():
    z = _facts([(0, 100), (300, 105.5), (600, 104)]).value_zone
    assert (z.open_inside, z.first_exit_above_utc, z.first_exit_below_utc) == (True, _at(300), None)
    assert (z.first_return_utc, z.time_to_return) == (_at(600), timedelta(seconds=300))
    assert (z.seconds_inside_during_a, z.a_rows_inside, z.a_rows) == (D(1500), 21, 23)


# --- early TPO, follow-through, one-timeframing -------------------------------------------------------

def test_ab_overlap_and_a_only_rows():
    # A 100-102 (9 rows), B 101-104 (13 rows): overlap 101-102 = 5 rows; 5 / 9
    e = _session([(0, 100), (60, 102), (1800, 101), (1860, 104)]).early_tpo
    assert (e.a_rows, e.b_rows, e.ab_overlap_rows, e.ab_overlap_ratio) == (9, 13, 5, D(5) / D(9))
    assert (e.ab_low, e.ab_high, e.ab_range_ticks) == (D(100), D(104), 16)
    assert (e.a_rows_above_b, e.a_rows_below_b, e.b_high_above_a, e.b_low_below_a) == (0, 4, True, False)
    assert (e.a_only_rows_full_day, e.a_only_rows_at_day_low, e.a_only_rows_at_day_high) == (4, 4, 0)


def test_ab_without_overlap_has_zero_ratio_and_missing_b_is_none():
    e = _session([(0, 100), (60, 101), (1800, 102), (1860, 103)]).early_tpo
    assert (e.ab_overlap_rows, e.ab_overlap_ratio, e.a_rows_below_b) == (0, D(0), 5)
    assert _session([(0, 100), (60, 101)]).early_tpo.b_rows is None


def test_a_extreme_follow_through():
    # A high 102 @60; then 101 @120, 98 @2000 (period B) -> crosses below open 100
    s = _session([(0, 100), (60, 102), (120, 101), (2000, 98)])
    hi, lo = s.a_extremes
    assert (hi.extreme, hi.price, hi.reached_utc, hi.max_move_away_ticks) == ("A_HIGH", D(102), _at(60), 16)
    assert (hi.crossed_open_after, hi.first_open_cross_after_utc, hi.time_to_open_cross) == (
        True, _at(2000), timedelta(seconds=1940))
    assert hi.opposite_excursion_beyond_open_ticks == 8
    assert (lo.price, lo.reached_utc, lo.crossed_open_after, lo.first_open_cross_after_utc) == (
        D(100), _at(0), True, _at(60))


def test_one_timeframing_from_the_open():
    # A 100-101, B 100.5-102, C 101-103, D 100-101.5 -> higher lows A,B,C then broken
    rows = [(0, 100), (60, 101), (1800, 100.5), (1860, 102), (3600, 101), (3660, 103), (5400, 100), (5460, 101.5)]
    ot = _session(rows).one_timeframing
    assert (ot.first_higher_low_period, ot.opening_higher_low_run, ot.longest_higher_low_run) == ("B", 3, 3)
    assert (ot.first_lower_high_period, ot.opening_lower_high_run) == ("D", 1)


# --- prior trading date --------------------------------------------------------------------------

def test_prior_trading_date_is_not_calendar_minus_one():
    assert prior_trading_date(date(2026, 10, 6)) == date(2026, 10, 5)
    assert prior_trading_date(date(2026, 10, 5)) == date(2026, 10, 2)  # Monday -> Friday
    assert prior_trading_date(date(2026, 11, 2)) == date(2026, 10, 30)  # weekend + DST change
    assert prior_trading_date(date(2026, 9, 8)) == date(2026, 9, 7)  # Labor Day early close is a trading date
    assert prior_trading_date(date(2026, 11, 27), frozenset({date(2026, 11, 26)})) == date(2026, 11, 25)
    assert prior_trading_date(date(2026, 4, 6), frozenset({date(2026, 4, 3)})) == date(2026, 4, 2)  # Good Friday


# --- prior context from real analysed datasets ---------------------------------------------------------

_NS = UUID("0e5a0000-0000-4000-8000-0000000000f0")


def _db(tmp_path, td, rows, *, contract=(2026, 12), started=None, name="x"):
    """FINALIZED ES dataset; rows are (seconds after 08:30 CT on `td`, price)."""
    dataset_id = uuid5(_NS, f"{name}-{td}")
    es = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", *contract)
    o = cash_open_utc(td)
    trades = tuple(TradeObservation(uuid5(dataset_id, str(i)), dataset_id, i + 1, es, o + timedelta(seconds=s),
                                    D(str(p)), D(1)) for i, (s, p) in enumerate(rows))
    path = tmp_path / f"{name}-{td}.sqlite3"
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(dataset_id, DatasetKind.HISTORICAL_IMPORT, "open-test",
                                       capture_started_at=started or o - timedelta(hours=15),
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
    """Every 30-minute period trades low then high."""
    return [(1800 * i + m, p) for i in range(13) for m, p in ((5, low), (6, high))]


def test_prior_context_available_from_prior_trading_date_across_weekend(tmp_path):
    fri = _db(tmp_path, date(2026, 10, 2), _full_day(90, 110))
    mon = _db(tmp_path, date(2026, 10, 5), [(0, 100)] + _full_day(99, 101))
    p = build_prior_context(mon, [fri])
    assert (p.outcome, p.prior_trading_date, p.same_contract, p.profile_high, p.profile_low) == (
        ContextOutcome.AVAILABLE, date(2026, 10, 2), True, D(110), D(90))
    f = opening_auction_facts(mon, [fri])
    assert (f.outcome, f.range_location, f.session.cash_open.price) == (
        ContextOutcome.AVAILABLE, RangeLocation.INSIDE_PRIOR_RANGE, D(100))
    text = render_tpo_report(mon, opening=f)
    assert "OPENING AUCTION FACTS (OPENING_AUCTION_FACTS_V1):" in text and "Early TPO matrix" in text


def test_missing_prior_day_and_calendar_day_is_not_used(tmp_path):
    older = _db(tmp_path, date(2026, 10, 1), _full_day(90, 110))  # Thursday: never "the" prior of Monday
    mon = _db(tmp_path, date(2026, 10, 5), [(0, 100)] + _full_day(99, 101))
    p = build_prior_context(mon, [older])
    assert (p.outcome, p.expected_prior_date, p.reasons) == (
        ContextOutcome.NO_PRIOR_PROFILE, date(2026, 10, 2), ("no dataset for prior trading date 2026-10-02",))


def test_different_prior_contract_is_never_stitched(tmp_path):
    prior = _db(tmp_path, date(2026, 10, 5), _full_day(90, 110), contract=(2026, 9))
    cur = _db(tmp_path, date(2026, 10, 6), [(0, 100)] + _full_day(99, 101))
    f = opening_auction_facts(cur, [prior])
    assert (f.outcome, f.prior.same_contract, f.prior.profile_high, f.range_location) == (
        ContextOutcome.CONTRACT_CHANGED, False, None, None)
    assert f.prior.prior_contract == "FUTURE:CME:ES:2026-09"


def test_incomplete_prior_profile_is_not_used(tmp_path):
    prior = _db(tmp_path, date(2026, 10, 5), [(1800 * i + 5, 100) for i in range(6)])  # H..M empty
    cur = _db(tmp_path, date(2026, 10, 6), [(0, 100)] + _full_day(99, 101))
    f = opening_auction_facts(cur, [prior])
    assert (f.outcome, f.range_location) == (ContextOutcome.PRIOR_PROFILE_INCOMPLETE, None)
    assert any("period(s) with no retained trades: GHIJKLM" in r for r in f.reasons)


def test_multiple_prior_datasets_are_not_chosen_between(tmp_path):
    a = _db(tmp_path, date(2026, 10, 5), _full_day(90, 110), name="a")
    b = _db(tmp_path, date(2026, 10, 5), _full_day(91, 109), name="b")
    cur = _db(tmp_path, date(2026, 10, 6), [(0, 100)] + _full_day(99, 101))
    assert build_prior_context(cur, [a, b]).outcome is ContextOutcome.MULTIPLE_PRIOR_DATASETS


def test_cst_dataset_opening_session(tmp_path):
    r = _db(tmp_path, date(2026, 12, 1), [(0, 100), (60, 101)] + _full_day(99, 101))
    assert r.opening.cash_open.timestamp_utc == datetime(2026, 12, 1, 14, 30, tzinfo=timezone.utc)


# --- output and immutability ----------------------------------------------------------------------------

def test_render_has_no_opening_type_or_interpretation():
    f = _facts([(0, 100), (60, 101), (120, 102), (400, 99), (1000, 100), (1500, 103)])
    text = "\n".join(render_opening_facts(f)).lower().replace("no opening type, acceptance/rejection, bias or signal", "")
    for word in ("open drive", "open_drive", "test drive", "rejection", "reverse", "open auction", "bullish", "bearish",
                 "fade", "buy", "sell", "continuation", "probability", "accepted", "strong"):
        assert word not in text, word
    for needle in ("cash open (08:30:00 ct = 13:30:00.000z): 100.00 at 13:30:00.000z", "open location: inside_prior_range",
                   "gap (open - prior terminal): 1.00 pts = 4 ticks, up, within_prior_range", "prior_vah"):
        assert needle in text, needle


def test_facts_are_immutable():
    f = _facts([(0, 100)])
    with pytest.raises(FrozenInstanceError):
        f.gap_ticks = 0  # type: ignore[misc]


def test_study_script_smoke(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    dbs = []
    for td, rows in ((date(2026, 10, 2), _full_day(90, 110)),
                     (date(2026, 10, 5), [(0, 100), (60, 112), (400, 99)] + _full_day(99, 101))):
        _db(tmp_path, td, rows)
        dbs.append(str(tmp_path / f"x-{td}.sqlite3"))
    before = [Path(p).read_bytes() for p in dbs]
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, "scripts/dicks_lab_mp_opening_study.py", str(out), *dbs], cwd=repo, env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    report = (out / "opening_study.md").read_text()
    assert "| 2026-10-05 |" in report and "AVAILABLE" in report and "## Mechanical inspection set" in report
    assert len(list((out / "reports").iterdir())) == 2
    assert [Path(p).read_bytes() for p in dbs] == before


def test_truncated_study_window_is_reported_without_qualifying_the_opening():
    s = _session([(0, 100), (60, 101)], ended=_at(3 * 3600))
    assert (s.quality.grade, s.quality.study_window_truncated) == (OpeningQualityGrade.UNQUALIFIED, True)
    assert _session([(0, 100)]).quality.study_window_truncated is False
    assert _session([(0, 100)], unknown_capture=True).quality.study_window_truncated is None
