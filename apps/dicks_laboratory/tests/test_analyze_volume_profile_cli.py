import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.live_capture import capture_es_timesales_dataset

_SCRIPT = "scripts/dicks_lab_analyze_volume_profile.py"
_SYMBOL = "/ESU26:XCME"
_MONDAY_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)


class _Collector:
    def __init__(self, events):
        self.events = events

    def collect(self, _symbol, _types, _duration, max_events, on_event=None, on_connected=None, retain_events=True):
        if on_connected:
            on_connected()
        for event in self.events[:max_events]:
            if on_event:
                on_event(event)
        return self.events if retain_events else ()


def _event(ts, index, price=7694.00, size=1.0):
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": "NEW",
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "price": price, "size": size, "validTick": True,
    }
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


def _run(*args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    for key in list(env):
        if "TASTYTRADE" in key.upper():
            del env[key]
    return subprocess.run(
        [sys.executable, _SCRIPT, *args], capture_output=True, text=True, env=env,
    )


def test_missing_database_path_fails_clearly():
    result = _run("no_such_file.sqlite3", "--anchor", "session-open")
    assert result.returncode == 2
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_naive_custom_anchor_is_rejected(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "2026-08-24T14:15:00")
    assert result.returncode != 0
    assert "timezone-aware" in result.stderr.lower() or "timezone-aware" in result.stdout.lower()


def test_session_open_runs_without_network_credentials(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "Point of Control:" in result.stdout
    assert "Value Area:" in result.stdout
    assert "VWAP:" in result.stdout
    assert "Captured-data developing" in result.stdout


def test_cash_open_with_no_coverage_exits_nonzero_without_fake_values(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "cash-open")
    assert result.returncode == 1
    assert "No VWAP, Volume Profile, POC, or Value Area was calculated." in result.stdout


def test_custom_anchor_selects_subset_and_shows_top_levels(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "2026-08-23T22:02:00Z")
    assert result.returncode == 0, result.stderr
    assert "Top " in result.stdout
    assert "Point of Control:" in result.stdout


def test_top_levels_option_bounds_are_enforced(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--top-levels", "0")
    assert result.returncode != 0


def test_top_levels_option_limits_displayed_rows(tmp_path):
    path, _ = _build_many_levels(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--top-levels", "2")
    assert result.returncode == 0, result.stderr
    assert "Top 2 Volume Levels" in result.stdout


def test_read_only_database_mtime_unchanged(tmp_path):
    path, _ = _build(tmp_path)
    mtime_before = path.stat().st_mtime_ns
    _run(str(path), "--anchor", "session-open")
    assert path.stat().st_mtime_ns == mtime_before


def _build(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25),
    )
    result = capture_es_timesales_dataset(tmp_path / "cli.sqlite3", _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


def _build_many_levels(tmp_path):
    events = tuple(
        _event(_MONDAY_OPEN + timedelta(minutes=index), index, price=7694.00 + (index * 0.25))
        for index in range(1, 6)
    )
    result = capture_es_timesales_dataset(tmp_path / "cli_many.sqlite3", _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id
