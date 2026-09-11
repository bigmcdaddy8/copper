"""0W-2E deploy-validation check: the tracked production systemd unit must
explicitly pin the intended --max-events safety fuse (and the other
Attempt-4-accepted invariants) rather than relying on the collector CLI's
own default. Attempt 4's failure was exactly this: the unit omitted
--max-events, silently inheriting the CLI's 1,000,000 default, which a full
ES trading date exceeds (FULL_SESSION_MULTIDAY_SOAK_REPORT.md §LB).

This test reads the real deployed-from-git unit file directly -- it must
fail if a future edit ever drops or changes these values without deliberate
review, never a copy or a hand-maintained duplicate of the command line.
"""
from __future__ import annotations

from pathlib import Path

_UNIT_PATH = (
    Path(__file__).resolve().parents[3]
    / "deploy" / "dicks_laboratory" / "systemd" / "dicks-lab-es-session.service"
)


def _exec_start_line() -> str:
    text = _UNIT_PATH.read_text()
    (line,) = (line for line in text.splitlines() if line.startswith("ExecStart="))
    return line


def test_production_unit_file_exists():
    assert _UNIT_PATH.is_file(), f"expected the tracked production unit at {_UNIT_PATH}"


def test_production_unit_pins_explicit_max_events():
    # 0W-2E: never rely on the collector's own --max-events default in
    # production -- the unit must say so explicitly.
    assert "--max-events 5000000" in _exec_start_line()


def test_production_unit_pins_expected_duration_and_data_dir():
    line = _exec_start_line()
    assert "--duration 83700" in line
    assert "--data-dir /srv/dicks_laboratory/data/sessions" in line
    assert "scripts/dicks_lab_collect_es.py" in line


def test_production_unit_never_auto_restarts_a_fatal_exit():
    # 0W-2 Attempt-4 lesson: a fatal collector exit must stay failed -- no
    # late catch-up relaunch that would masquerade as a complete session.
    text = _UNIT_PATH.read_text()
    assert "Restart=no" in text
