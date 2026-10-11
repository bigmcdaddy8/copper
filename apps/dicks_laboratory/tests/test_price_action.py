"""0AB-A: VWAP bands and price-action evidence primitives (PRICE_ACTION_FACTS_V1).

Synthetic replay datasets are built with the 0Z-B fixture helpers (test_replay._db): rows are
(seconds after 08:30 CT, price, receipt delay in seconds); every trade has size 1. The prior day
(fixture PRIOR) has high 110, low 90.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.price_action import (
    BandZone,
    Side,
    _band_side,
    _zone,
    build_price_action_facts,
    canonical_facts_json,
    price_action_sha256,
)
from dicks_laboratory.replay import MarketReplay, Maturity
from dicks_laboratory.replay_player import ReplaySession

sys.path.insert(0, str(Path(__file__).parent))
import test_replay as fx_mod  # noqa: E402  (shared 0Z-B fixtures)

CUR, PRIOR, ct = fx_mod.CUR, fx_mod.PRIOR, fx_mod.ct
PROV = AnalysisProvenance("a" * 40, False)


@pytest.fixture(scope="module")
def prior(tmp_path_factory):
    return fx_mod._db(tmp_path_factory.mktemp("pa-prior"), PRIOR,
                      [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                      name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))


def _session(tmp_path, prior, rows, name="cur", **kw):
    kw.setdefault("gaps", False)
    kw.setdefault("rejected", False)
    db = fx_mod._db(tmp_path, CUR, rows, name=name, stopped_ct=kw.pop("stopped_ct", (16, 30)), **kw)
    s = ReplaySession(MarketReplay.load(db, PROV, prior))
    s.db = db
    return s


def _facts(s, at):
    return build_price_action_facts(s.replay.current, s.snapshot(at))


def _ref(f, name):
    return next(r for r in f.references if r.reference == name)


def _m(hh, mm, ss=0):  # seconds after 08:30
    return (hh - 8) * 3600 + (mm - 30) * 60 + ss


# --- band math ---------------------------------------------------------------------------------------

def test_band_math_matches_the_definition_and_the_accepted_vwap(tmp_path, prior):
    s = _session(tmp_path, prior, [(_m(8, 30, 10), 100, 0), (_m(8, 31), 102, 0), (_m(8, 32), 104, 0)])
    f = _facts(s, "08:33")
    b = f.bands
    assert b.vwap == D(102) and b.included_trade_count == 3 and b.included_volume == D(3)
    cash = next(v for v in s.snapshot("08:33").vwap if v.anchor_kind.value == "US_CASH_OPEN")
    assert b.vwap == cash.study.vwap  # same population, same arithmetic
    assert b.sigma == (D(8) / D(3)).sqrt()  # population variance (4 + 0 + 4) / 3
    assert b.bands[0].upper == b.vwap + b.sigma and b.bands[1].lower == b.vwap - 2 * b.sigma
    assert dict(b.last_price_zones) == {1: BandZone.ABOVE_UPPER_BAND, 2: BandZone.BETWEEN_VWAP_AND_UPPER_BAND}
    assert b.maturity is Maturity.DEVELOPING and not b.zero_width


def test_zero_width_and_not_yet_available(tmp_path, prior):
    s = _session(tmp_path, prior, [(-3600, 100, 0), (_m(8, 31), 101, 0)])
    early = _facts(s, "08:00")
    assert early.bands.maturity is Maturity.NOT_YET_AVAILABLE and early.bands.vwap is None
    assert early.bands.bands == () and _ref(early, "CASH_VWAP").maturity is Maturity.NOT_YET_AVAILABLE
    one = _facts(s, "08:32")
    assert one.bands.sigma == 0 and one.bands.zero_width and one.bands.bands[0].upper == D(101)
    assert dict(one.bands.last_price_zones) == {1: BandZone.AT_VWAP, 2: BandZone.AT_VWAP}


def test_exact_zone_and_side_comparisons():
    # D = P*S0 - S1 and var = S2*S0 - S1^2 are scaled by S0; D^2 vs k^2 var decides exactly
    assert _zone(3, 9, 1) is BandZone.AT_UPPER_BAND and _zone(-3, 9, 1) is BandZone.AT_LOWER_BAND
    assert _zone(4, 9, 1) is BandZone.ABOVE_UPPER_BAND and _zone(2, 9, 1) is BandZone.BETWEEN_VWAP_AND_UPPER_BAND
    assert _zone(5, 9, 2) is BandZone.BETWEEN_VWAP_AND_UPPER_BAND and _zone(0, 9, 1) is BandZone.AT_VWAP
    assert _zone(-7, 9, 2) is BandZone.BELOW_LOWER_BAND
    assert _band_side(3, 9, 1) is Side.AT and _band_side(-3, 9, -1) is Side.AT and _band_side(2, 9, 1) is Side.BELOW
    assert _band_side(-4, 9, -1) is Side.BELOW and _band_side(-2, 9, -1) is Side.ABOVE and _band_side(0, 0, 1) is Side.AT


# --- crossings, episodes, time ------------------------------------------------------------------------

PATH = [(_m(8, 30, 1), 105, 0), (_m(8, 31), 110, 0), (_m(8, 32), 111, 0), (_m(8, 33), 110, 0),
        (_m(8, 34), 112, 0), (_m(8, 36), 109, 0), (_m(8, 41), 111, 0)]


def test_static_reference_touch_cross_episode_and_return(tmp_path, prior):
    s = _session(tmp_path, prior, PATH)
    r = _ref(_facts(s, "08:45"), "PRIOR_HIGH")  # level 110
    assert r.level_at_clock == D(110) and r.initial_side is Side.BELOW and r.side_at_clock is Side.ABOVE
    assert r.first_touch_utc == ct(CUR, 8, 31)  # the trade AT 110
    assert (r.first_cross.utc, r.first_cross.direction.value, r.first_cross.price) == (ct(CUR, 8, 32), "UP", D(111))
    assert r.cross_count == 3 and r.episode_count == 3 and r.last_cross.utc == ct(CUR, 8, 41)
    assert r.seconds_since_last_cross == timedelta(minutes=4)
    e = r.first_episode
    assert (e.direction.value, e.start_utc, e.max_excursion_points, e.max_excursion_utc) == (
        "UP", ct(CUR, 8, 32), D("2.000000"), ct(CUR, 8, 34))
    assert e.touched_again_utc == ct(CUR, 8, 33) and e.excursion_after_touch_points == D("2.000000")
    assert e.returned_utc == ct(CUR, 8, 36) and e.seconds_to_return == timedelta(minutes=4)
    assert e.seconds_beyond == timedelta(minutes=3)  # 08:32-08:33 and 08:34-08:36 (08:33-08:34 is AT)
    assert e.volume_beyond == D(2) and e.excursion_after_return_points == D("1.000000")
    assert e.closest_approach_after_peak_points is None  # nothing traded between the peak and the return
    assert r.seconds_above + r.seconds_at + r.seconds_below == timedelta(minutes=15) - timedelta(seconds=1)
    assert r.latest_episode.start_utc == ct(CUR, 8, 41) and r.latest_episode.returned_utc is None


def test_closes_beyond_are_counted_per_completed_bar(tmp_path, prior):
    s = _session(tmp_path, prior, PATH)
    r = _ref(_facts(s, "08:45"), "PRIOR_HIGH")
    # bars: 08:30-35 closes 112 (beyond), 08:35-40 closes 109, 08:40-45 closes 111 (beyond, a new episode)
    assert r.first_close_beyond_utc == ct(CUR, 8, 35)
    assert (r.first_episode.bars_closing_beyond, r.first_episode.first_close_beyond_utc) == (1, ct(CUR, 8, 35))
    assert r.latest_episode.bars_closing_beyond == 1 and r.latest_episode.max_consecutive_closes_beyond == 1
    assert _ref(_facts(s, "08:44"), "PRIOR_HIGH").latest_episode.bars_closing_beyond == 0  # bar not complete


def test_vwap_crossings_and_band_occupancy(tmp_path, prior):
    s = _session(tmp_path, prior, PATH)
    f = _facts(s, "08:45")
    v = _ref(f, "CASH_VWAP")
    assert v.initial_side is Side.AT and v.first_touch_utc == ct(CUR, 8, 30, 1) and v.cross_count >= 2
    for o in f.occupancy:
        assert sum((x for _, x in o.seconds), timedelta(0)) == o.observed == timedelta(minutes=15) - timedelta(seconds=1)
        assert o.outside_total == o.outside_above + o.outside_below
        assert o.window == timedelta(minutes=15)


def test_ib_reference_waits_for_the_ib(tmp_path, prior):
    s = _session(tmp_path, prior, PATH + [(_m(9, 35), 120, 0)])
    assert _ref(_facts(s, "09:00"), "IB_HIGH").maturity is Maturity.NOT_YET_AVAILABLE
    ib = _ref(_facts(s, "09:40"), "IB_HIGH")
    assert ib.level_at_clock == D(112) and ib.initial_side is Side.BELOW  # the last trade before 09:30 (111)
    assert (ib.first_cross.direction.value, ib.first_cross.utc) == ("UP", ct(CUR, 9, 35))


# --- bars ----------------------------------------------------------------------------------------------

def test_five_minute_ohlc_and_relations(tmp_path, prior):
    rows = [(_m(8, 30, 1), 100, 0), (_m(8, 31), 103, 0), (_m(8, 32), 99, 0), (_m(8, 34), 101, 0),  # 100/103/99/101
            (_m(8, 35, 5), 101, 0), (_m(8, 37), 102, 0), (_m(8, 39), 100, 0),  # inside bar
            (_m(8, 40, 5), 100, 0), (_m(8, 42), 104, 0), (_m(8, 43), 98, 0), (_m(8, 44), 104, 0)]  # outside
    s = _session(tmp_path, prior, rows)
    bars = _facts(s, "08:47").rth_bars
    a, b, c = bars
    assert (a.open, a.high, a.low, a.close, a.range, a.body, a.upper_wick, a.lower_wick) == (
        D(100), D(103), D(99), D(101), D(4), D(1), D(2), D(1))
    assert a.direction.value == "UP" and a.trade_count == 4 and a.volume == D(4) and a.higher_high is None
    assert b.inside_bar and not b.outside_bar and b.lower_high and b.higher_low and b.direction.value == "DOWN"
    assert c.outside_bar and not c.inside_bar and c.higher_high and c.lower_low and c.close_above_prior_high
    assert c.maturity is Maturity.WINDOW_COMPLETE and c.close_vs_vwap is Side.ABOVE
    developing = _facts(s, "08:44").rth_bars[-1]
    assert developing.maturity is Maturity.DEVELOPING and developing.close == D(98)


def test_late_print_revises_a_completed_bar_only_once_known(tmp_path, prior):
    rows = [(_m(8, 30, 1), 100, 0), (_m(8, 31), 101, 0), (_m(8, 32), 108, 540), (_m(8, 36), 101, 0)]  # 108 @ 08:41
    s = _session(tmp_path, prior, rows)
    before, after = _facts(s, "08:40").rth_bars[0], _facts(s, "08:42").rth_bars[0]
    assert before.maturity is after.maturity is Maturity.WINDOW_COMPLETE  # COMPLETE, not FINAL
    assert (before.high, after.high) == (D(101), D(108))


def test_atr_warm_up_seed_and_wilder(tmp_path, prior):
    rows = []
    for j in range(16):  # bar j: low 100+j, high 100+j+(j%3+1); open low, close high
        base = _m(8, 30) + 300 * j
        rows += [(base + 1, 100 + j, 0), (base + 2, 100 + j + (j % 3 + 1), 0)]
    s = _session(tmp_path, prior, rows)
    assert _facts(s, "09:30").atr.maturity is Maturity.NOT_YET_AVAILABLE  # 12 completed bars
    trs, prev = [], None
    for j in range(16):
        lo, hi = D(100 + j), D(100 + j + (j % 3 + 1))
        trs.append(hi - lo if prev is None else max(hi - lo, abs(hi - prev), abs(lo - prev)))
        prev = hi
    seed = sum(trs[:13], D(0)) / 13
    f = _facts(s, "09:35")
    assert f.atr.value == seed and f.atr.completed_bars_used == 13 and f.atr.maturity is Maturity.DEVELOPING
    w = (seed * 12 + trs[13]) / 13
    assert _facts(s, "09:40").atr.value == w and _facts(s, "09:40").rth_bars[13].atr_after == w


# --- replay correctness, quality, serialization ----------------------------------------------------------

def test_later_evidence_cannot_change_earlier_facts(tmp_path, prior):
    s = _session(tmp_path, prior, PATH + [(_m(8, 50), 115, 0), (_m(8, 52), 108, 0)])
    base_early, base_late = canonical_facts_json(_facts(s, "08:45")), canonical_facts_json(_facts(s, "08:55"))
    mutated = tmp_path / "pa-mutated.sqlite3"
    shutil.copyfile(s.db, mutated)
    con = sqlite3.connect(mutated)
    assert con.execute("UPDATE trade_observations SET price = '130' WHERE price = '115'").rowcount == 1
    con.commit()
    con.close()
    m = ReplaySession(MarketReplay.load(mutated, PROV, prior))
    assert canonical_facts_json(build_price_action_facts(m.replay.current, m.snapshot("08:45"))) == base_early
    late = build_price_action_facts(m.replay.current, m.snapshot("08:55"))
    assert canonical_facts_json(late) != base_late and late.rth_bars[-1].high == D(130)


def test_quality_propagates(tmp_path, prior):
    s = _session(tmp_path, prior, fx_mod._base_day(), name="gappy", gaps=True)  # KNOWN_GAP 10:15:00-10:15:30
    assert _facts(s, "10:00").status == "AVAILABLE"
    late = _facts(s, "10:20")
    assert late.status == "QUALITY_QUALIFIED" and any("KNOWN_GAP" in r for r in late.reasons)


def test_canonical_and_deterministic(tmp_path, prior):
    s = _session(tmp_path, prior, PATH)
    a, b = _facts(s, "08:45"), build_price_action_facts(s.replay.current, s.replay.snapshot(at=ct(CUR, 8, 45)))
    ja = canonical_facts_json(a)
    assert ja == canonical_facts_json(b) and json.loads(ja)["price_action_sha256"] == price_action_sha256(a)
    assert "generated" not in ja and "e-" not in ja.split('"bands"')[1][:50]
    assert json.loads(ja)["policies"] == ["VWAP_BANDS_V1", "BARS_5M_V1", "ATR_5M_V1", "REFERENCE_PATH_V1"]


def test_complete_after_the_vwap_window(tmp_path, prior):
    s = _session(tmp_path, prior, PATH)
    f = _facts(s, "16:10")
    assert f.bands.maturity is Maturity.WINDOW_COMPLETE and _ref(f, "CASH_VWAP").maturity is Maturity.WINDOW_COMPLETE


# --- tutor evidence integration -----------------------------------------------------------------------------

def _lesson(s, at, extra=()):
    import dataclasses

    from dicks_laboratory.tutor_evidence import EvidenceDomain, QuestionKind, build_tutor_lesson, example_lesson
    d = example_lesson(s, QuestionKind.PRICE_VS_CASH_VWAP, at)
    if extra:
        d = dataclasses.replace(d, allowed_domains=d.allowed_domains + tuple(EvidenceDomain(x) for x in extra))
    return build_tutor_lesson(s, d)


def test_tutor_context_cites_price_action_facts(tmp_path, prior):
    from dicks_laboratory.tutor_ai import FakeTutorModel, TutorRunStatus, answer_to_model_json, run_tutor
    from dicks_laboratory.tutor_evidence import LessonStage, SourceRole, resolve_pointer, validate_answer_grounding
    s = _session(tmp_path, prior, PATH)
    plain = _lesson(s, "08:45")
    assert [e.role for e in plain.context.snapshots] == [SourceRole.LESSON_TIME]  # unchanged unless requested
    lesson = _lesson(s, "08:45", ("VWAP_BANDS", "REFERENCE_PATHS", "PRICE_ACTION_BARS", "VOLATILITY"))
    pa = next(e for e in lesson.context.snapshots if e.role is SourceRole.PRICE_ACTION)
    facts = _facts(s, "08:45")
    assert pa.snapshot_sha256 == price_action_sha256(facts) and pa.replay_market_time == ct(CUR, 8, 45)
    doc = lesson.document(pa.snapshot_sha256)
    for item in pa.items:
        v = resolve_pointer(doc, item.ref.pointer)
        assert item.value == (json.dumps(v, sort_keys=True, separators=(",", ":")) if isinstance(v, dict | list) else v)
    labels = {i.label: i.value for i in pa.items}
    assert labels["PRIOR_HIGH cross count"] == 3 and labels["ATR_5M_V1 maturity"] == "NOT_YET_AVAILABLE"
    assert labels["PRIOR_HIGH latest episode direction"] == "UP"
    assert validate_answer_grounding(lesson.answer_key.reference_answer, lesson).valid
    answer = json.loads(answer_to_model_json(lesson.answer_key.reference_answer, lesson))
    answer["claims"].append({"statement": "Price crossed the prior high 3 times.", "category": "DERIVED_FACT",
                             "evidence_refs": [{"source": "PRICE_ACTION", "pointer": next(
                                 i.ref.pointer for i in pa.items if i.label == "PRIOR_HIGH cross count")}],
                             "asserted": [], "curriculum_source_id": None})
    answer["claims"].append({"statement": "Price is above the +1 sigma VWAP band.", "category": "DERIVED_FACT",
                             "evidence_refs": [{"source": "PRICE_ACTION", "pointer": "/bands/last_price_zones/0/1"}],
                             "asserted": [], "curriculum_source_id": None})
    result = run_tutor(lesson, LessonStage.QUESTION, FakeTutorModel([json.dumps(answer)]), allow_repair=False)
    assert result.status is TutorRunStatus.GROUNDED, result.issues
    accepted = dict(answer)
    accepted["claims"] = answer["claims"] + [{**answer["claims"][-1], "statement": "Price is accepting above the band."}]
    assert run_tutor(lesson, LessonStage.QUESTION, FakeTutorModel([json.dumps(accepted)]), allow_repair=False).status is \
        TutorRunStatus.GROUNDING_FAILED  # measured dimensions exist; the acceptance label still does not


def test_price_action_quality_warning_reaches_the_tutor(tmp_path, prior):
    s = _session(tmp_path, prior, fx_mod._base_day(), name="gappy-tutor", gaps=True)
    lesson = _lesson(s, "10:20", ("VWAP_BANDS",))
    assert "PRICE_ACTION:price_action" in [w.warning_id for w in lesson.context.quality_warnings]
    assert "PRICE_ACTION:price_action" in lesson.answer_key.reference_answer.quality_warnings
