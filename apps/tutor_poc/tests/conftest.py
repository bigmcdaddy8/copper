"""Shared synthetic fixture: the Laboratory's 0Z-B replay dataset (dicks_laboratory/tests/test_replay.py).

Synthetic rows only (late print, correction, cancel, future market timestamp). No real corpus file is read.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

LAB_TESTS = Path(__file__).resolve().parents[2] / "dicks_laboratory" / "tests"
sys.path.insert(0, str(LAB_TESTS))
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
