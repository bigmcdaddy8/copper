"""Shared synthetic fixture: the Laboratory's 0Z-B replay dataset (dicks_laboratory/tests/test_replay.py).

Synthetic rows only (late print, correction, cancel, future market timestamp). No real corpus file is read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAB_TESTS = Path(__file__).resolve().parents[2] / "dicks_laboratory" / "tests"
sys.path.insert(0, str(LAB_TESTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # A3E tests reuse the A3 scripted helpers
import test_replay as fx_mod  # noqa: E402

from tutor_poc import timeline  # noqa: E402


@pytest.fixture(scope="session")
def lab_fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tutor_fx")
    cur = fx_mod._db(tmp, fx_mod.CUR, fx_mod.OVERNIGHT + fx_mod._base_day() + fx_mod.SPECIAL, name="cur",
                     deferred=(fx_mod.CORRECTION, fx_mod.CANCEL))
    prior = fx_mod._db(tmp, fx_mod.PRIOR, [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                       name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))
    return cur, prior


@pytest.fixture(scope="session")
def fx_timeline(lab_fx):
    return timeline.build_timeline(lab_fx[0])


# --- A4: the frozen Drysdale replay fixture (test_drysdale.ROWS) ------------------------------------------
# A PRICE_DISCOVERY_CONTINUATION UP candidate completes with the 08:50-08:55 bar; a late print in that bar
# (received 09:01:50) turns it back into DEVELOPING from the 09:05 cutoff on.
import test_drysdale as dr_mod  # noqa: E402

from tutor_poc import setups  # noqa: E402

A4_GRID = tuple(fx_mod.ct(fx_mod.CUR, 8, 0) + timeline.STEP * k for k in range(18))  # 08:00 .. 09:25 CT (the frozen
# synthetic fixture has no trade in the first 30 s after 08:30: tpo_opening_path raises from 09:30, 0AB-B policy §10)


@pytest.fixture(scope="session")
def dr_fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tutor_dr")
    prior = fx_mod._db(tmp, fx_mod.PRIOR, [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                       name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))
    cur = fx_mod._db(tmp, fx_mod.CUR, dr_mod.ROWS, name="cur", stopped_ct=(16, 30), gaps=False, rejected=False)
    return cur, prior


@pytest.fixture(scope="session")
def dr_timeline(dr_fx):
    return timeline.build_timeline(dr_fx[0])


@pytest.fixture(scope="session")
def dr_setups(dr_fx):
    return setups.build_setup_timeline(dr_fx[0], dr_fx[1], A4_GRID)


@pytest.fixture(scope="session")
def fx_setups(lab_fx):
    return setups.build_setup_timeline(lab_fx[0], lab_fx[1])  # the whole replay grid (a small dataset)


from _fx_state import FX  # noqa: E402  (the A3 / A3E helpers read the fixture setup timeline from here)


@pytest.fixture(scope="session", autouse=True)
def _fx_setups_for_helpers(fx_setups):
    FX["setups"] = fx_setups
