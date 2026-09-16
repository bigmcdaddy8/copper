"""0W-4A: deterministic proof that the recurring launch-gate marker cannot
authorize a trading date it was not written for.

Exercises the real `dicks_lab_gate_marker.sh` (write/check) used by
dicks-lab-preflight-gate.service and dicks-lab-launch-gate.service, against a
throwaway marker file -- no systemd, no network, no market data, no quote
token."""
from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

_SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "deploy"
    / "dicks_laboratory"
    / "scripts"
    / "dicks_lab_gate_marker.sh"
)
_CT = ZoneInfo("America/Chicago")


def _today_ct() -> str:
    return dt.datetime.now(_CT).strftime("%Y-%m-%d")


def _yesterday_ct() -> str:
    return (dt.datetime.now(_CT) - dt.timedelta(days=1)).strftime("%Y-%m-%d")


def _write(marker: Path) -> None:
    subprocess.run([str(_SCRIPT), "write", str(marker)], check=True)


def _check(marker: Path) -> int:
    return subprocess.run([str(_SCRIPT), "check", str(marker)]).returncode


def test_todays_marker_authorizes_todays_launch(tmp_path):
    """A: recurring successful preflight -- today's marker authorizes today."""
    marker = tmp_path / "preflight-ok"
    _write(marker)
    assert marker.read_text().strip() == _today_ct()
    assert _check(marker) == 0


def test_stale_previous_day_marker_is_rejected(tmp_path):
    """B: stale marker -- yesterday's marker cannot authorize today's launch."""
    marker = tmp_path / "preflight-ok"
    marker.write_text(_yesterday_ct() + "\n")
    assert _check(marker) != 0


def test_missing_marker_is_rejected(tmp_path):
    """C: failed daily preflight -- no marker means no launch."""
    marker = tmp_path / "preflight-ok"
    assert not marker.exists()
    assert _check(marker) != 0


def test_day_n_plus_1_recovers_after_day_n_failure(tmp_path):
    """D: Day N preflight fails (no marker written); Day N+1 preflight
    succeeds and its fresh marker authorizes Day N+1's launch normally."""
    marker = tmp_path / "preflight-ok"
    # Day N: preflight failed, ExecStartPost never ran -- simulated as "no
    # marker on disk", exactly what the real oneshot service leaves behind.
    assert _check(marker) != 0
    # Day N+1: preflight succeeds and (re)writes the marker for *that* day.
    _write(marker)
    assert _check(marker) == 0


def test_rewriting_marker_each_day_prevents_cross_day_reuse(tmp_path):
    """A stale marker from an earlier day, still sitting on disk when a new
    day's preflight-gate run overwrites it, is fully replaced -- no residual
    old-date content survives a real write."""
    marker = tmp_path / "preflight-ok"
    marker.write_text(_yesterday_ct() + "\n")
    _write(marker)
    assert marker.read_text().strip() == _today_ct()
    assert _check(marker) == 0


@pytest.mark.parametrize("bad_content", ["", "not-a-date", "2020-01-01\nextra"])
def test_malformed_marker_content_is_rejected(tmp_path, bad_content):
    marker = tmp_path / "preflight-ok"
    marker.write_text(bad_content)
    assert _check(marker) != 0


def test_runtime_max_sec_cannot_overlap_next_launch_window():
    """F: the collector's RuntimeMaxSec backstop plus its graceful-stop
    timeout must fully elapse before the *next* trading date's 16:55
    launch-gate fires, so a single OnCalendar schedule can never overlap two
    trading dates' processes."""
    launch_hour_seconds = 16 * 3600 + 55 * 60  # 16:55 in seconds-since-midnight
    runtime_max_sec = 84300  # dicks-lab-es-session.service RuntimeMaxSec=
    timeout_stop_sec = 180  # dicks-lab-es-session.service TimeoutStopSec=
    latest_forced_exit = launch_hour_seconds + runtime_max_sec + timeout_stop_sec
    next_launch = launch_hour_seconds + 24 * 3600
    safety_margin_seconds = next_launch - latest_forced_exit
    assert safety_margin_seconds > 0
    # Matches the ~16:20 SIGINT / ~16:23 SIGKILL / 16:55 next-launch figures
    # documented in dicks-lab-es-session.service's own header.
    assert safety_margin_seconds == pytest.approx(1920, abs=1)
