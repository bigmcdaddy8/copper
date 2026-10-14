"""0AC-A1: the prepared chart timeline is the Laboratory's own as-of output, cutoff by cutoff."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

import test_replay as fx_mod  # on sys.path via conftest (shared Laboratory fixture)
from dicks_laboratory import drysdale as dry
from dicks_laboratory.replay_player import ReplaySession
from tutor_poc import timeline

CUR, ct = fx_mod.CUR, fx_mod.ct


def _pos(tl, hh, mm):
    t = ct(CUR, hh, mm)
    return next(p for p in tl.positions if p.cutoff_utc == t)


def test_grid_covers_the_globex_session_in_5_minute_steps():
    g = timeline.replay_grid(CUR)
    assert g[0] == ct(CUR - timedelta(days=1), 17, 5) and g[-1] == ct(CUR, 16, 0)
    assert len(g) == 276 and all(b - a == timedelta(minutes=5) for a, b in zip(g, g[1:]))


def test_no_bar_or_band_value_after_any_cutoff(fx_timeline):
    for p in fx_timeline.positions:
        assert all(b.end_utc <= p.cutoff_utc for b in p.bars)


def test_positions_equal_the_laboratory_drysdale_bars(lab_fx, fx_timeline):
    cur, prior = lab_fx
    session = ReplaySession.load(cur, fx_mod.PROV, prior)
    for hh, mm in ((8, 0), (9, 55), (10, 0), (10, 5), (10, 10), (12, 0), (16, 0)):
        lab = dry.analyze(session, f"{hh:02d}:{mm:02d}").bars
        mine = _pos(fx_timeline, hh, mm).bars
        assert [(b.start_utc, b.open, b.high, b.low, b.close, b.volume, b.vwap, b.sigma) for b in lab] == \
            [(b.start_utc, b.open, b.high, b.low, b.close, b.volume, b.vwap, b.sigma) for b in mine]
        assert [tuple(t.level_at_close for t in b.levels[1:]) for b in lab] == \
            [(b.upper_1sd, b.lower_1sd, b.upper_2sd, b.lower_2sd) for b in mine]


def test_knowledge_time_revision_is_preserved(fx_timeline):
    """09:55 bar: the 130 print is canceled at 10:05:20 and the 101 print corrected to 125 at 10:05:10.

    Neither revision is applied backward: at 10:00 and 10:05 the bar still shows 130; at 10:10 it shows 125.
    """
    def bar_0955(hh, mm):
        return next(b for b in _pos(fx_timeline, hh, mm).bars if b.start_utc == ct(CUR, 9, 55))

    assert bar_0955(10, 0).high == bar_0955(10, 5).high == D("130")
    assert bar_0955(10, 10).high == D("125")


def test_cache_round_trip(tmp_path, fx_timeline):
    path = tmp_path / "tl.json.gz"
    timeline.save_timeline(fx_timeline, path)
    assert timeline.load_timeline(path) == fx_timeline
