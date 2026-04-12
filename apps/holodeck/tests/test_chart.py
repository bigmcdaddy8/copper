"""Tests for `holodeck chart-bars` CLI command (HD-0110)."""
from __future__ import annotations
import subprocess
import sys
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from bic.models import OHLCVBar
from holodeck.broker import HolodeckBroker
from holodeck.config import HolodeckConfig
from holodeck.market_data import generate_spx_minutes


TZ = "America/Chicago"


@pytest.fixture
def csv_path(tmp_path):
    path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, path)
    return path


@pytest.fixture
def full_broker(csv_path):
    config = HolodeckConfig(
        starting_datetime=datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ)),
        ending_datetime=datetime(2026, 1, 30, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    return HolodeckBroker(config)


def test_chart_bars_imports():
    """Smoke test: plotext and holodeck chart modules are importable."""
    import plotext  # noqa: F401
    from holodeck.broker import HolodeckBroker  # noqa: F401
    from bic.models import OHLCVBar  # noqa: F401


def test_chart_bars_1d_count(full_broker):
    """1D resolution over 5 trading days returns 5 bars."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 8, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1d")
    # Jan 2, 5, 6, 7, 8 = 5 trading days
    assert len(bars) == 5
    assert all(isinstance(b, OHLCVBar) for b in bars)


def test_chart_bars_1w_full_month(full_broker):
    """1W resolution over full January returns ≤5 weekly bars."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 30, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1w")
    assert 1 <= len(bars) <= 5


def test_chart_bars_30m_count(full_broker):
    """30m resolution over one trading day (331 minutes CST) returns 12 bars."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "30m")
    assert len(bars) == 12
    assert all(isinstance(b, OHLCVBar) for b in bars)


def test_chart_bars_5m_count(full_broker):
    """5m resolution over one trading day (331 minutes CST) returns 67 bars."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "5m")
    assert len(bars) == 67
    assert all(isinstance(b, OHLCVBar) for b in bars)


def test_chart_bars_1M_count(full_broker):
    """1M resolution over full January returns exactly 1 bar."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 30, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1M")
    assert len(bars) == 1
    assert all(isinstance(b, OHLCVBar) for b in bars)


def test_chart_bars_cli_exits_zero(csv_path):
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "chart-bars",
            "--symbol", "SPX",
            "--start", "2026-01-02",
            "--end", "2026-01-08",
            "--resolution", "1d",
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"


def test_chart_bars_cli_dark_mode(csv_path):
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "chart-bars",
            "--symbol", "SPX",
            "--start", "2026-01-02",
            "--end", "2026-01-08",
            "--resolution", "1d",
            "--dark",
            "--data", csv_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"stderr: {result.stderr}\nstdout: {result.stdout}"


def test_chart_bars_gap_1d(full_broker):
    """1d gap insertion adds Sat + Sun flat bars between Fri and Mon."""
    from holodeck.cli import _insert_gap_bars

    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))   # Fri
    end   = datetime(2026, 1, 5, 15, 0, tzinfo=ZoneInfo(TZ))   # Mon
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1d")
    assert len(bars) == 2  # Fri + Mon
    with_gaps = _insert_gap_bars(bars, "1d")
    assert len(with_gaps) == 4  # Fri + Sat(gap) + Sun(gap) + Mon
    for g in with_gaps[1:3]:
        assert g.open == g.high == g.low == g.close == bars[0].close


def test_chart_bars_gap_intraday(full_broker):
    """30m gap insertion adds one gap bar between two different trading days."""
    from holodeck.cli import _insert_gap_bars

    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))   # day 1
    end   = datetime(2026, 1, 5, 15, 0, tzinfo=ZoneInfo(TZ))   # day 2
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "30m")
    bars_before = len(bars)
    with_gaps = _insert_gap_bars(bars, "30m")
    # Fri and Mon are separated by a weekend gap (Fri close → Mon open overnight+weekend = 1 gap bar)
    assert len(with_gaps) == bars_before + 1

