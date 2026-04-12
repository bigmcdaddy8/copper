"""Tests for `holodeck live-bars` and LiveLoop infrastructure (HD-0130)."""
from __future__ import annotations
import subprocess
import sys
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from holodeck.clock import VirtualClock
from holodeck.live_loop import LiveLoop, SPEED_MINUTES
from holodeck.market_data import generate_spx_minutes

TZ = "America/Chicago"


@pytest.fixture
def csv_path(tmp_path):
    path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, path)
    return path


def test_live_loop_speed_map():
    """SPEED_MINUTES covers all expected keys."""
    assert set(SPEED_MINUTES) == {"1m", "5m", "15m", "30m", "1h", "1d"}


def test_live_loop_advances_clock():
    """LiveLoop yields virtual times advancing by the step interval."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    clock = VirtualClock(start, "09:30", "15:00", TZ)
    data_end = datetime(2026, 1, 2, 9, 40, tzinfo=ZoneInfo(TZ))
    loop = LiveLoop(clock, speed="5m", data_end=data_end, tick_seconds=0)
    ticks = list(loop)
    assert len(ticks) == 3
    assert ticks[0] == start
    assert ticks[1] == datetime(2026, 1, 2, 9, 35, tzinfo=ZoneInfo(TZ))
    assert ticks[2] == datetime(2026, 1, 2, 9, 40, tzinfo=ZoneInfo(TZ))


def test_live_loop_exhausts_at_data_end():
    """LiveLoop yields exactly one tick when start == data_end."""
    start  = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
    end    = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
    clock  = VirtualClock(start, "09:30", "15:00", TZ)
    loop   = LiveLoop(clock, speed="1h", data_end=end, tick_seconds=0)
    ticks  = list(loop)
    assert len(ticks) == 1


def test_live_bars_cli_smoke(csv_path):
    """live-bars exits 0 after data exhausted at end of a single day."""
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "live-bars",
            "--symbol", "SPX",
            "--start", "2026-01-30",
            "--end",   "2026-01-30",
            "--resolution", "1d",
            "--speed", "1d",
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"
