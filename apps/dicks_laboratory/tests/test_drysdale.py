"""0AB-B: Drysdale VWAP Wave Laboratory V1 training candidates (DRYSDALE_SETUP_ANALYSIS_V1).

Two fixture kinds:
- hand-built COMPLETE 5-minute bars fed to the pure policy layer (`evaluate`): VWAP 100 and sigma 2 unless
  stated, so +1 sigma = 102, -1 sigma = 98, +2 sigma = 104, -2 sigma = 96;
- synthetic replay datasets (test_replay._db: rows are seconds after 08:30 CT, price, receipt delay) for the
  Globex anchor, the single pass, late prints, quality, caching and the tutor.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from dicks_laboratory import drysdale as dry
from dicks_laboratory.drysdale import (
    LAB,
    SOURCE_MODEL,
    CandidateState,
    ConditionStatus,
    GlobexBar,
    Level,
    LevelTouch,
    SetupFamily,
    Slope,
    SourceStatus,
    Stage,
    ValuePosition,
    analyze,
    canonical_analysis_json,
    drysdale_sha256,
    evaluate,
)
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.price_action import BandZone, BarDirection, Direction, Side, build_price_action_facts
from dicks_laboratory.replay import MarketReplay
from dicks_laboratory.replay_player import ReplaySession

sys.path.insert(0, str(Path(__file__).parent))
import test_replay as fx_mod  # noqa: E402  (shared 0Z-B fixtures)

S, N, P = ConditionStatus.SATISFIED, ConditionStatus.NOT_SATISFIED, ConditionStatus.PENDING
T0 = datetime(2026, 10, 5, 13, 30, tzinfo=timezone.utc)  # 08:30 CT


# --- hand-built bars ---------------------------------------------------------------------------------

def _touch(level: Level, L: D, o, h, lo, c, vol) -> LevelTouch:
    def side(x):
        return Side.ABOVE if x > L else Side.BELOW if x < L else Side.AT

    half = D(150) if lo < L < h else D(0)
    return LevelTouch(level, L, side(c), h > L, L in (o, h, lo, c), lo < L, h - L, L - lo,
                      timedelta(seconds=300 if lo > L else int(half)), timedelta(seconds=300 if h < L else int(half)),
                      vol if lo > L else vol / 2 if h > L else D(0), vol if h < L else vol / 2 if lo < L else D(0),
                      1 if lo < L < h else 0)


def mk(spec) -> tuple[GlobexBar, ...]:
    """spec: (open, high, low, close[, volume[, vwap[, sigma]]]) per bar, in order."""
    out, prev = [], None
    for i, row in enumerate(spec):
        o, h, lo, c = (D(str(x)) for x in row[:4])
        vol = D(str(row[4])) if len(row) > 4 else D(100)
        vwap = D(str(row[5])) if len(row) > 5 else D(100)
        sigma = D(str(row[6])) if len(row) > 6 else D(2)
        u1, l1 = vwap + sigma, vwap - sigma
        pos = (ValuePosition.ABOVE_VALUE if c > u1 else ValuePosition.BELOW_VALUE if c < l1
               else ValuePosition.INSIDE_VALUE)

        def zone(k):
            u, lw = vwap + k * sigma, vwap - k * sigma
            return (BandZone.ABOVE_UPPER_BAND if c > u else BandZone.AT_UPPER_BAND if c == u else
                    BandZone.BELOW_LOWER_BAND if c < lw else BandZone.AT_LOWER_BAND if c == lw else
                    BandZone.AT_VWAP if c == vwap else BandZone.BETWEEN_VWAP_AND_UPPER_BAND if c > vwap
                    else BandZone.BETWEEN_VWAP_AND_LOWER_BAND)

        delta = None if prev is None else vwap - prev
        slope = None if delta is None else Slope.RISING if delta > 0 else Slope.FALLING if delta < 0 else Slope.FLAT
        levels = tuple(_touch(lv, vwap + k * sigma, o, h, lo, c, vol) for lv, k in dry._LEVELS)
        out.append(GlobexBar(i, T0 + timedelta(minutes=5 * i), T0 + timedelta(minutes=5 * (i + 1)), o, h, lo, c,
                             BarDirection.UP if c > o else BarDirection.DOWN if c < o else BarDirection.FLAT, 10, vol,
                             vwap, sigma, pos, zone(1), zone(2), delta, slope, D(4), levels))
        prev = vwap
    return tuple(out)


def ev(spec, quality="AVAILABLE", statics=()):
    return evaluate(mk(spec), quality, list(statics), D("0.25"))


def one(cands, family, direction=None):
    found = [c for c in cands if c.family is family and (direction is None or c.direction is direction)]
    assert len(found) == 1, [c.candidate_id for c in found]
    return found[0]


def st(c):
    return [k.status for k in c.conditions]


IN = (100, 101, 99, 100)  # an inside bar
PDC_UP = [IN, IN,
          (100, 103, 100, 103, 300),  # 2 trigger: closes above +1 sigma (102)
          (103, 103.5, 102.5, 103.25),  # 3 acceptance (second close beyond)
          (103.25, 103.5, 101.5, 103),  # 4 retest: trades through 102, closes outside
          (103, 104.5, 102.75, 104.25)]  # 5 confirmation: up bar, close > 103.5 (retest high)


def test_price_discovery_continuation_up_candidate_with_breakout_evidence():
    c = one(ev(PDC_UP), SetupFamily.PRICE_DISCOVERY_CONTINUATION, Direction.UP)
    assert st(c) == [S, S, S, S] and c.state is CandidateState.CANDIDATE and c.stage is Stage.CONDITIONS_SATISFIED
    assert [k.bar_index for k in c.conditions] == [2, 3, 4, 5] and c.completed_at_utc == T0 + timedelta(minutes=30)
    assert [k.policy_id for k in c.conditions] == ["LAB_BREAKOUT_TRIGGER_V1", "LAB_ACCEPTANCE_TIME_V1",
                                                   "LAB_RETEST_V1", "LAB_DIRECTIONAL_CONFIRMATION_V1"]
    assert c.candidate_policy == "PRICE_DISCOVERY_CONTINUATION_CANDIDATE_V1" and not c.can_still_complete
    b = c.breakout
    assert b.boundary is Level.UPPER_1SD and b.distance_beyond_points == D(1) and b.distance_beyond_ticks == D(4)
    assert b.distance_beyond_sigma == D("0.5") and b.distance_beyond_atr == D("0.25")
    assert b.reached_2sd and b.first_2sd_reach_bar_end_utc == T0 + timedelta(minutes=30)  # bar 5 high 104.5 >= 104
    assert b.volume.ratio_to_mean == D(3) and b.volume.baseline_bars == 2 and b.volume.ratio_to_prior == D(3)
    assert b.prior_inside_closes == 2 and b.prior_inside_lab_accepted and b.completed_closes_beyond == 4
    assert b.vwap_slope is Slope.FLAT and b.slope_in_breakout_direction is False  # FLAT only when exactly unchanged
    assert b.not_available == ("CORRELATED_MARKET_NQ", "MARKET_INTERNALS", "ORDER_FLOW_AGGRESSION", "NEWS_CATALYST")
    assert b.bar_end_ct == "08:45" and b.in_us_cash_session and not b.returned_inside
    assert c.acceptance[0].lab_acceptance_time_v1 and c.acceptance[0].distance_acceptance == \
        "SOURCE CONCEPT PRESENT; MECHANICAL THRESHOLD NOT SPECIFIED"


def test_two_sigma_not_reached_and_down_mirror():
    flat = [r[:3] + (r[3],) for r in PDC_UP[:5]] + [(103, 103.9, 102.75, 103.75)]  # confirmation high < 104
    c = one(ev(flat), SetupFamily.PRICE_DISCOVERY_CONTINUATION, Direction.UP)
    assert st(c) == [S, S, S, S] and not c.breakout.reached_2sd
    mirror = [(200 - o, 200 - lo, 200 - h, 200 - c, *rest) for o, h, lo, c, *rest in PDC_UP]  # reflect around 100
    d = one(ev(mirror), SetupFamily.PRICE_DISCOVERY_CONTINUATION, Direction.DOWN)
    assert st(d) == [S, S, S, S] and d.breakout.boundary is Level.LOWER_1SD and d.breakout.reached_2sd


def test_breakout_only_and_breakout_without_acceptance():
    ended = one(ev([IN, IN, (100, 103, 100, 103), IN]), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(ended) == [S, N, N, N] and ended.stage is Stage.BREAKOUT_TRIGGERED and not ended.can_still_complete
    assert ended.breakout.returned_inside and ended.breakout.time_to_return == timedelta(minutes=5)
    live = one(ev([IN, IN, (100, 103, 100, 103)]), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(live) == [S, P, P, P] and live.can_still_complete and live.state is CandidateState.DEVELOPING


def test_acceptance_without_retest_reports_the_closest_approach():
    spec = PDC_UP[:4] + [(103.25, 104, 102.5, 103.5)]  # low 102.5 stays above +1 sigma: an approach, no retest
    c = one(ev(spec), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(c) == [S, S, P, P] and c.stage is Stage.ACCEPTED_OUTSIDE and c.can_still_complete
    assert dict(c.supporting)["closest_approach_after_acceptance_points"] == D("0.5")
    ended = one(ev(spec + [IN]), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(ended) == [S, S, N, N] and not ended.can_still_complete


def test_retest_without_confirmation_and_a_later_retest_that_confirms():
    failed = PDC_UP[:5] + [(103, 103.25, 102.5, 102.75)]  # down bar: no confirmation, still outside
    c = one(ev(failed), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(c) == [S, S, S, N] and c.stage is Stage.RETEST_OBSERVED and c.can_still_complete
    waiting = one(ev(PDC_UP[:5]), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(waiting) == [S, S, S, P] and waiting.stage is Stage.WAITING_FOR_CONFIRMATION
    again = failed + [(102.75, 103.5, 101.75, 103.25), (103.25, 104, 103, 103.9)]  # second retest, confirmed
    c2 = one(ev(again), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(c2) == [S, S, S, S] and c2.conditions[2].bar_index == 6  # bar 5 (low 102.5) only approached
    assert [(e.bar_index, e.confirmation) for e in c2.events] == [(4, N), (6, S)]


FADE_UP = [IN, IN, (100, 102.5, 100, 101), (101, 101.25, 99, 99.5)]  # test 102.5, close 101; next closes < 100


def test_fade_upper_and_lower_band_candidates():
    c = one(ev(FADE_UP), SetupFamily.FADE_VALUE_AREA_EXTREME, Direction.DOWN)
    assert st(c) == [S, S, S, S] and c.state is CandidateState.CANDIDATE
    assert [k.bar_index for k in c.conditions] == [1, 2, 2, 3]
    assert c.events[0].excursion_points == D("0.5") and c.events[0].next_distance_back_points == D(3)
    lower = [IN, IN, (100, 100, 97.5, 99), (99, 101, 98.75, 100.5)]
    u = one(ev(lower), SetupFamily.FADE_VALUE_AREA_EXTREME, Direction.UP)
    assert st(u) == [S, S, S, S] and u.events[0].level is Level.LOWER_1SD


def test_fade_test_without_rejection_and_rejection_without_confirmation():
    at_band = [IN, IN, (100, 102.5, 100, 102)]  # closes AT +1 sigma: inside value, not strictly back inside
    c = one(ev(at_band), SetupFamily.FADE_VALUE_AREA_EXTREME)
    assert st(c) == [S, S, N, P] and c.stage is Stage.BOUNDARY_TESTED and c.can_still_complete  # a later test may
    no_conf = [IN, IN, (100, 102.5, 100, 101), (101, 101.75, 100.5, 101.5)]
    c2 = one(ev(no_conf), SetupFamily.FADE_VALUE_AREA_EXTREME)
    assert st(c2) == [S, S, S, N] and c2.stage is Stage.REJECTION_OBSERVED


def test_fade_acceleration_instead_of_rejection():
    spec = [IN, IN, (100, 103, 100, 102.75, 100), (102.75, 104, 102.5, 103.75, 250)]
    c = one(ev(spec), SetupFamily.FADE_VALUE_AREA_EXTREME)
    assert st(c) == [S, S, N, N] and not c.can_still_complete
    e = c.events[0]  # acceleration facts only, no ACCELERATION label
    assert e.traded_through and not e.proxy_satisfied and e.close_side is Side.ABOVE
    assert e.next_close_beyond is True and e.next_volume_change == D(150) and e.next_excursion_added_points == D(1)
    assert not hasattr(e, "acceleration")


RTV_DOWN = [IN, (100, 103, 100, 103), (103, 103.5, 102.5, 103.25), (103.25, 103.5, 101, 101.5),
            (101.5, 101.75, 100.5, 101)]


def test_return_to_value_from_above_and_below():
    c = one(ev(RTV_DOWN), SetupFamily.RETURN_TO_VALUE, Direction.DOWN)
    assert st(c) == [S, S, S] and c.state is CandidateState.CANDIDATE and [k.bar_index for k in c.conditions] == [2, 3, 4]
    assert dict(c.supporting) ["RETURN_TO_VALUE_RETEST_PRESENT"] is False and dict(c.supporting)["retest_required"] is False
    assert [a.region for a in c.acceptance] == ["OUTSIDE_ABOVE", "INSIDE"]
    mirror = [(200 - o, 200 - lo, 200 - h, 200 - cl) for o, h, lo, cl in RTV_DOWN]
    u = one(ev(mirror), SetupFamily.RETURN_TO_VALUE, Direction.UP)
    assert st(u) == [S, S, S]


def test_return_without_inside_acceptance_and_with_a_later_retest():
    back_out = RTV_DOWN[:4] + [(101.5, 103, 101.5, 102.75)]
    c = one(ev(back_out), SetupFamily.RETURN_TO_VALUE)
    assert st(c) == [S, S, N] and c.stage is Stage.RETURNED_TO_VALUE
    live = one(ev(RTV_DOWN[:4]), SetupFamily.RETURN_TO_VALUE)
    assert st(live) == [S, S, P] and live.can_still_complete
    retest = RTV_DOWN + [(101, 102.25, 100.75, 101.25)]  # trades through +1 sigma, closes inside value
    c2 = one(ev(retest), SetupFamily.RETURN_TO_VALUE)
    assert st(c2) == [S, S, S] and dict(c2.supporting)["RETURN_TO_VALUE_RETEST_PRESENT"] is True
    assert c2.events[0].kind == "RETURN_RETEST" and c2.events[0].bar_index == 5


# bounce UP: VWAP rising; bar 1 above +1 sigma, bar 2 back inside above VWAP, bar 3 tests VWAP, bar 4 confirms
BOUNCE_UP = [(100, 101, 99.5, 100.5, 100, 100), (100.5, 103.5, 100.5, 103.25, 100, 100.5),
             (103.25, 103.5, 101.25, 101.5, 100, 101), (101.5, 101.75, 100.75, 101.25, 100, 101.25),
             (101.25, 102.5, 101, 102.25, 100, 101.5)]


def test_vwap_bounce_up_and_down():
    c = one(ev(BOUNCE_UP), SetupFamily.VWAP_BOUNCE, Direction.UP)
    assert st(c) == [S, S, S, S, S] and c.state is CandidateState.CANDIDATE
    assert [k.policy_id for k in c.conditions] == ["DRYSDALE_VALUE_AREA_V1", "LAB_RETURN_TO_VALUE_V1",
                                                   "LAB_TREND_CONTEXT_V1", "LAB_VWAP_TEST_V1",
                                                   "LAB_DIRECTIONAL_CONFIRMATION_V1"]
    assert c.events[0].kind == "VWAP_TEST" and c.events[0].trend_context is S and c.events[0].bar_index == 3
    mirror = [(200 - o, 200 - lo, 200 - h, 200 - cl, v, 200 - w) for o, h, lo, cl, v, w in BOUNCE_UP]
    d = one(ev(mirror), SetupFamily.VWAP_BOUNCE, Direction.DOWN)
    assert st(d) == [S, S, S, S, S]


def test_vwap_test_without_confirmation_or_trend_context():
    no_conf = BOUNCE_UP[:4] + [(101.25, 101.5, 100.5, 100.75, 100, 101.5)]
    c = one(ev(no_conf), SetupFamily.VWAP_BOUNCE)
    assert st(c) == [S, S, S, S, N] and c.can_still_complete  # still inside value: a later test may confirm
    falling = [r[:5] + (w,) for r, w in zip(BOUNCE_UP, (100, 100.5, 100.25, 101, 100.9))]  # VWAP fell at bar 2
    c2 = one(ev(falling), SetupFamily.VWAP_BOUNCE)
    assert c2.conditions[2].status is N and c2.conditions[4].status is P and c2.state is CandidateState.DEVELOPING
    assert c2.stage is Stage.VWAP_TESTED


def test_setup_overlap_is_allowed_without_precedence():
    spec = PDC_UP + [(104.25, 104.5, 101.5, 101.75), (101.75, 102, 100.75, 101)]  # then back inside, accepted
    cands = ev(spec)
    states = {(c.family, c.direction): c.state for c in cands}
    assert states[(SetupFamily.PRICE_DISCOVERY_CONTINUATION, Direction.UP)] is CandidateState.CANDIDATE
    assert states[(SetupFamily.RETURN_TO_VALUE, Direction.DOWN)] is CandidateState.CANDIDATE
    assert ev([IN, IN, IN]) == ()  # zero candidates is a normal outcome


def test_quality_qualified_evidence_never_yields_a_pristine_candidate():
    c = one(ev(PDC_UP, quality="QUALITY_QUALIFIED"), SetupFamily.PRICE_DISCOVERY_CONTINUATION)
    assert st(c) == [S, S, S, S] and c.state is CandidateState.QUALITY_QUALIFIED and c.quality == "QUALITY_QUALIFIED"


def test_static_reference_context_respects_availability():
    statics = [("PRIOR_HIGH", "/prior_day/context/profile_high", D("103.5"), None),
               ("IB_HIGH", "/tpo/profile/initial_balance/high", D(105), T0 + timedelta(hours=1)),
               ("PRIOR_LOW", "/prior_day/context/profile_low", None, None)]
    b = one(ev(PDC_UP, statics=statics), SetupFamily.PRICE_DISCOVERY_CONTINUATION).breakout
    refs = {r.reference: r for r in b.references}
    assert refs["PRIOR_HIGH"].availability == "AVAILABLE" and refs["PRIOR_HIGH"].close_side is Side.BELOW
    assert refs["IB_HIGH"].availability == "NOT_YET_AVAILABLE"  # the IB is not known at the 08:45 trigger
    assert refs["PRIOR_LOW"].availability == "NOT_AVAILABLE"
    assert (b.nearest_opposing_reference, b.nearest_opposing_distance_points) == ("PRIOR_HIGH", D("0.5"))


def test_source_model_keeps_source_and_laboratory_apart():
    by = {c.concept: c for c in SOURCE_MODEL}
    assert by["VWAP anchor"].source_status is SourceStatus.SOURCE_SUPPORTED and "17:00" in by["VWAP anchor"].source_says
    assert by["VWAP value area"].policy_id == "DRYSDALE_VALUE_AREA_V1"
    for concept in ("breakout", "acceptance", "backtest / retest", "rejection", "first sign of strength / weakness",
                    "return to value", "VWAP bounce", "trend"):
        assert by[concept].source_status is SourceStatus.SOURCE_DISCRETIONARY and LAB in by[concept].laboratory
    assert "does not specify two bars" in by["acceptance"].laboratory
    assert by["chart interval"].source_status is SourceStatus.SOURCE_PRACTICE
    assert by["profile value area"].policy_id is None
    assert "LAB_ACCEPTANCE_DISTANCE_V1" not in dry.POLICIES and len(set(dry.POLICIES)) == len(dry.POLICIES)
    assert {"DRYSDALE_VALUE_AREA_V1", "LAB_BREAKOUT_TRIGGER_V1", "LAB_ACCEPTANCE_TIME_V1", "LAB_RETEST_V1",
            "LAB_REJECTION_V1", "LAB_DIRECTIONAL_CONFIRMATION_V1", "LAB_RETURN_TO_VALUE_V1", "LAB_VWAP_TEST_V1",
            "LAB_TREND_CONTEXT_V1", "DRYSDALE_SETUP_CANDIDATES_V1"} <= set(dry.POLICIES)


def test_no_trade_vocabulary_in_the_typed_model():
    names = {f for cls in (dry.DrysdaleSetupCandidate, dry.DrysdaleSetupCondition, dry.TestEvent,
                           dry.DrysdaleBreakoutEvidence) for f in cls.__dataclass_fields__}
    assert not names & {"entry", "stop", "target", "size", "position", "buy", "sell", "long", "short"}
    assert "entry" not in canonical_json_of(ev(PDC_UP)).lower()


def canonical_json_of(cands) -> str:
    from dicks_laboratory import market_study_state as mss
    return mss._dumps(mss.encode(cands))


# --- replay fixtures ----------------------------------------------------------------------------------

PROV = AnalysisProvenance("a" * 40, False)
CUR, PRIOR, ct = fx_mod.CUR, fx_mod.PRIOR, fx_mod.ct


def _m(hh, mm, ss=0):
    return (hh - 8) * 3600 + (mm - 30) * 60 + ss


OVERNIGHT = [(-55800 + 300 * i + 10, (99, 100, 101, 100)[i % 4], 0) for i in range(186)]  # 17:00 .. 08:30 CT
RTH = {0: (100, 100.5, 100), 1: (100, 102, 103), 2: (103, 104, 104.5), 3: (104.5, 100.5, 103.5),
       4: (103.5, 104.5, 106), 5: (106, 105, 105.5)}
LATE = (_m(8, 54, 50), 103, 420)  # in the 08:50 bar (the confirmation bar); received 09:01:50
ROWS = OVERNIGHT + [(300 * b + 60 * k + 30, p, 0) for b, ps in RTH.items() for k, p in enumerate(ps)] + [LATE]


@pytest.fixture(scope="module")
def prior(tmp_path_factory):
    return fx_mod._db(tmp_path_factory.mktemp("dr-prior"), PRIOR,
                      [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                      name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))


def _session(tmp_path, prior, rows=ROWS, name="cur", **kw):
    kw.setdefault("gaps", False)
    kw.setdefault("rejected", False)
    db = fx_mod._db(tmp_path, CUR, rows, name=name, stopped_ct=(16, 30), **kw)
    s = ReplaySession(MarketReplay.load(db, PROV, prior))
    s.db = db
    return s


def _pdc(a):
    return [c for c in a.candidates if c.family is SetupFamily.PRICE_DISCOVERY_CONTINUATION
            and c.first_event_utc >= ct(CUR, 8, 30)]


def test_globex_anchor_bands_equal_the_snapshot_globex_vwap(tmp_path, prior):
    s = _session(tmp_path, prior)
    a = analyze(s, "09:00")
    snap = s.snapshot("09:00")
    globex = next(v for v in snap.vwap if v.anchor_kind.value == "SESSION_OPEN")
    cash = next(v for v in snap.vwap if v.anchor_kind.value == "US_CASH_OPEN")
    assert a.bands.vwap == globex.study.vwap != cash.study.vwap  # Drysdale uses the Globex VWAP, not the cash VWAP
    assert a.bands.anchor_utc == ct(CUR, 17, 0) - timedelta(days=1)  # Sunday 17:00 CT for a Monday trading date
    assert a.bands.upper_1sd == a.bands.vwap + a.bands.sigma and a.bands.lower_2sd == a.bands.vwap - 2 * a.bands.sigma
    assert a.bands.included_trade_count == 186 + 18 and a.bands.value_area_policy == "DRYSDALE_VALUE_AREA_V1"
    assert a.bars[0].start_utc == a.bands.anchor_utc and all(b.end_utc <= ct(CUR, 9, 0) for b in a.bars)
    pa = build_price_action_facts(s.replay.current, snap)
    assert a.bars[-1].atr == pa.atr.value  # ATR_5M_V1 over the same full-session bars
    full = _session(tmp_path, prior, rows=ROWS + [(1, 100, 0)], name="full-day")  # an 08:30:01 trade
    assert analyze(full, "16:20").bands.maturity.value == "WINDOW_COMPLETE"


def test_time_is_attributed_to_the_bar_in_which_it_elapses(tmp_path, prior):
    # every bar has a trade (17:00:10, 17:05:10, ...) and the clock is on a bar boundary. The first trade is AT every
    # band (one price, sigma 0), so its time (to 17:05:10) is AT time; from bar 2 on no trade is AT +2 sigma.
    a = analyze(_session(tmp_path, prior), "09:00")
    later = a.bars[2:]
    total = sum((b.levels[3].seconds_above + b.levels[3].seconds_below for b in later), timedelta(0))
    assert not any(b.levels[3].traded_at for b in later) and total == ct(CUR, 9, 0) - later[0].start_utc
    assert all(b.levels[3].seconds_above + b.levels[3].seconds_below == timedelta(minutes=5) for b in later)


def test_replay_candidate_and_late_print_revision(tmp_path, prior):
    s = _session(tmp_path, prior)
    before, after = analyze(s, "09:01"), analyze(s, "09:03")
    (c0,), (c1,) = _pdc(before), _pdc(after)
    assert c0.state is CandidateState.CANDIDATE and c0.completed_at_utc == ct(CUR, 8, 55)
    confirm = before.bars[c0.conditions[3].bar_index]
    assert confirm.close == D(106) and after.bars[confirm.index].close == D(103)  # the late print is now known
    assert st(c1) == [S, S, S, N] and c1.state is CandidateState.DEVELOPING and c1.can_still_complete
    assert canonical_analysis_json(before) != canonical_analysis_json(after)


def test_later_evidence_cannot_change_earlier_analysis(tmp_path, prior):
    s = _session(tmp_path, prior)
    early = canonical_analysis_json(analyze(s, "08:50"))
    mutated = tmp_path / "dr-mutated.sqlite3"
    shutil.copyfile(s.db, mutated)
    con = sqlite3.connect(mutated)
    assert con.execute("UPDATE trade_observations SET price = '90' WHERE price = '105'").rowcount == 1  # 08:56
    con.commit()
    con.close()
    m = ReplaySession(MarketReplay.load(mutated, PROV, prior))
    assert canonical_analysis_json(analyze(m, "08:50")) == early
    assert canonical_analysis_json(analyze(m, "09:01")) != canonical_analysis_json(analyze(s, "09:01"))


def test_cache_hit_resume_and_refusal(tmp_path, prior):
    s = _session(tmp_path, prior)
    a = analyze(s, "08:40")
    assert analyze(s, "08:40") is a and s.drysdale_cache.stats["hits"] == 1
    resumed = analyze(s, "09:00")  # nothing newly known before 08:40: resumes from the 08:40 pass
    assert s.drysdale_cache.stats["resumed"] == 1
    fresh = ReplaySession(MarketReplay.load(s.db, PROV, prior))  # same dataset, no cache
    assert canonical_analysis_json(resumed) == canonical_analysis_json(analyze(fresh, "09:00"))
    revised = analyze(s, "09:03")  # the late print (market time 08:54:50) became known after the 09:00 checkpoint
    assert s.drysdale_cache.stats["full"] == 2  # refused: recomputed from the anchor
    assert canonical_analysis_json(revised) == canonical_analysis_json(analyze(fresh, "09:03"))


def test_deterministic_and_not_available_before_the_anchor(tmp_path, prior):
    s = _session(tmp_path, prior)
    a = analyze(s, "09:00")
    j = canonical_analysis_json(a)
    assert json.loads(j)["drysdale_sha256"] == drysdale_sha256(a) and "e-" not in j.split('"bands"')[1][:40]
    assert json.loads(j)["policies"][:2] == ["VWAP_BANDS_GLOBEX_V1", "DRYSDALE_VALUE_AREA_V1"]
    s2 = _session(tmp_path, prior, rows=[(_m(8, 31), 100, 0)], name="late-start")
    early = analyze(s2, ct(CUR, 16, 30) - timedelta(days=1))  # Sunday 16:30 CT: before the Globex anchor
    assert early.state is CandidateState.NOT_AVAILABLE and early.bars == () and early.candidates == ()


GAPPY = ROWS + [(1, 100, 0), (_m(10, 14), 101, 0), (_m(10, 16), 101, 0)]


def test_quality_propagates_to_every_candidate(tmp_path, prior):
    rows = GAPPY
    s = _session(tmp_path, prior, rows=rows, name="gappy", gaps=True)  # KNOWN_GAP 10:15:00-10:15:30
    assert analyze(s, "10:00").status == "AVAILABLE"
    late = analyze(s, "10:20")
    assert late.status == "QUALITY_QUALIFIED" and any("KNOWN_GAP" in r for r in late.reasons)
    assert all(c.state is not CandidateState.CANDIDATE and c.quality == "QUALITY_QUALIFIED" for c in late.candidates)
    assert any(c.state is CandidateState.QUALITY_QUALIFIED for c in late.candidates)  # the 08:55 PDC (conservative)
    assert late.state is CandidateState.QUALITY_QUALIFIED


def test_render_is_instructional(tmp_path, prior):
    s = _session(tmp_path, prior)
    text = dry.render_analysis(analyze(s, "09:01"))
    assert "SETUP 1 - PRICE DISCOVERY CONTINUATION" in text and "[satisfied]" in text
    assert "Drysdale source criteria (SOURCE SAYS" in text and "LABORATORY V1 TRAINING PROXY" in text
    assert "+/-2 sigma reached: YES" in text and "not the Laboratory 70% profile value area" in text
    for word in ("buy", "sell", "long ", "short ", "target", "stop "):
        assert word not in text.lower().replace("no trade, entry, stop, target", "")


# --- tutor ---------------------------------------------------------------------------------------------

def test_drysdale_lesson_is_grounded_and_teaches_two_voices(tmp_path, prior):
    from dicks_laboratory.tutor_ai import (
        DRYSDALE_SYSTEM_PROMPT_VERSION,
        SYSTEM_PROMPT_VERSION,
        FakeTutorModel,
        GuardCode,
        TutorRunStatus,
        answer_to_model_json,
        build_request,
        run_record,
        run_tutor,
    )
    from dicks_laboratory.tutor_evidence import (
        LessonStage,
        QuestionKind,
        SourceRole,
        build_tutor_lesson,
        drysdale_lesson,
        example_lesson,
        resolve_pointer,
        validate_answer_grounding,
    )
    s = _session(tmp_path, prior)
    lesson = build_tutor_lesson(s, drysdale_lesson(s, "09:01", question=2))
    dr = next(e for e in lesson.context.snapshots if e.role is SourceRole.DRYSDALE)
    doc = lesson.document(dr.snapshot_sha256)
    for item in dr.items:
        v = resolve_pointer(doc, item.ref.pointer)
        assert item.value == (json.dumps(v, sort_keys=True, separators=(",", ":")) if isinstance(v, dict | list) else v)
    key = lesson.answer_key
    assert key.support.value == "SUPPORTED" and key.summary == "CANDIDATE"
    assert {c.claim_id for c in key.rubric.common_incorrect_claims} >= {"ACCEPTED_AS_MARKET_FACT", "TRADE_SIGNAL",
                                                                          "CASH_VWAP_VALUE_AREA"}
    assert validate_answer_grounding(key.reference_answer, lesson).valid
    assert build_request(lesson, LessonStage.QUESTION).system_prompt_version == DRYSDALE_SYSTEM_PROMPT_VERSION
    lab = build_tutor_lesson(s, example_lesson(s, QuestionKind.PRICE_VS_CASH_VWAP, "09:01"))
    assert build_request(lab, LessonStage.QUESTION).system_prompt_version == SYSTEM_PROMPT_VERSION  # unchanged

    base = json.loads(answer_to_model_json(key.reference_answer, lesson))
    ok = run_tutor(lesson, LessonStage.QUESTION, FakeTutorModel([json.dumps(base)]), allow_repair=False)
    assert ok.status is TutorRunStatus.GROUNDED, ok.issues
    assert run_record(ok)["system_prompt_version"] == DRYSDALE_SYSTEM_PROMPT_VERSION
    acc = next(i for i in dr.items if i.label.startswith("PRICE_DISCOVERY_CONTINUATION UP")
               and "LAB_ACCEPTANCE_TIME_V1" in i.label)
    ref = {"source": "DRYSDALE", "pointer": acc.ref.pointer}

    def run(claim):
        answer = dict(base)
        answer["claims"] = base["claims"] + [claim]
        return run_tutor(lesson, LessonStage.QUESTION, FakeTutorModel([json.dumps(answer)]), allow_repair=False)

    lab_voice = {"statement": "Laboratory V1 acceptance (LAB_ACCEPTANCE_TIME_V1) is satisfied.",
                 "category": "LABORATORY_POLICY_RESULT", "evidence_refs": [ref],
                 "asserted": [{"ref": ref, "value": "SATISFIED"}], "curriculum_source_id": None}
    assert run(lab_voice).status is TutorRunStatus.GROUNDED
    wrong_value = {**lab_voice, "asserted": [{"ref": ref, "value": "NOT_SATISFIED"}]}
    assert run(wrong_value).status is TutorRunStatus.GROUNDING_FAILED  # the evidence decides, not the wording
    unlabeled = {**lab_voice, "statement": "Acceptance is satisfied."}
    r = run(unlabeled)
    assert r.status is TutorRunStatus.GROUNDING_FAILED and GuardCode.UNDEFINED_POLICY_CLAIM in {i.code for i in r.issues}
    as_fact = {**lab_voice, "statement": "The market has accepted the new value.", "category": "DERIVED_FACT",
               "asserted": []}
    assert run(as_fact).status is TutorRunStatus.GROUNDING_FAILED
    reading = {**as_fact, "category": "AI_INTERPRETATION"}
    assert run(reading).status is TutorRunStatus.GROUNDED  # framed as an interpretation, still cited
    source = {"statement": "Drysdale would consider volume expansion relevant breakout context.",
              "category": "CURRICULUM_RULE", "evidence_refs": [], "asserted": [],
              "curriculum_source_id": "DRYSDALE_VWAP_WAVE_SYSTEM_BOOK"}
    assert run(source).status is TutorRunStatus.GROUNDED
    advice = {**lab_voice, "statement": "Laboratory V1 says go long here at the retest."}
    assert GuardCode.TRADE_ADVICE in {i.code for i in run(advice).issues}


def test_drysdale_quality_warning_reaches_the_tutor(tmp_path, prior):
    from dicks_laboratory.tutor_evidence import build_tutor_lesson, drysdale_lesson
    s = _session(tmp_path, prior, rows=GAPPY, name="gappy-tutor", gaps=True)
    lesson = build_tutor_lesson(s, drysdale_lesson(s, "10:20"))
    assert "DRYSDALE:drysdale" in [w.warning_id for w in lesson.context.quality_warnings]
    assert "DRYSDALE:drysdale" in lesson.answer_key.reference_answer.quality_warnings


# --- CLI smoke ------------------------------------------------------------------------------------------

def _cli(script, *args):
    import subprocess
    return subprocess.run([sys.executable, f"scripts/{script}", *map(str, args)], cwd=fx_mod.REPO, env=fx_mod._ENV,
                          capture_output=True, text=True)


def test_drysdale_cli_smoke(tmp_path, prior):
    s = _session(tmp_path, prior)
    before = s.db.read_bytes()
    r = _cli("dicks_lab_drysdale_setups.py", s.db, "--prior-db", prior, "--at", "09:01", "--analysis-commit", "a" * 40)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("DRYSDALE VWAP WAVE - LABORATORY V1 TRAINING CANDIDATES  2026-10-05")
    assert "SETUP 4 - VWAP BOUNCE" in r.stdout and "Result: CANDIDATE" in r.stdout
    j = _cli("dicks_lab_drysdale_setups.py", s.db, "--prior-db", prior, "--at", "09:01", "--json",
             "--analysis-commit", "a" * 40)
    assert j.returncode == 0 and json.loads(j.stdout)["schema"] == "DRYSDALE_SETUP_ANALYSIS_V1"
    t = _cli("dicks_lab_tutor_lesson.py", s.db, "--prior-db", prior, "--lesson", "drysdale", "--at", "09:01",
             "--question", "3", "--instructor", "--analysis-commit", "a" * 40)
    assert t.returncode == 0, t.stderr
    assert "Which Laboratory V1 proxy conditions are satisfied?" in t.stdout and "ANSWER KEY  SUPPORTED: CANDIDATE" in t.stdout
    bad = _cli("dicks_lab_tutor_lesson.py", s.db, "--lesson", "drysdale", "--at", "09:01", "--question", "10",
               "--analysis-commit", "a" * 40)
    assert bad.returncode != 0
    assert s.db.read_bytes() == before
