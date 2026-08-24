import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.live_capture import capture_es_timesales_dataset

_SCRIPT = "scripts/dicks_lab_analyze_vwap.py"
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


def _event(ts, index, price=100.0):
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": "NEW",
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "price": price, "size": 1.0, "validTick": True,
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
    assert "VWAP:" in result.stdout
    assert "Captured-data developing" in result.stdout


def test_cash_open_with_no_coverage_exits_nonzero_without_fake_vwap(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "cash-open")
    assert result.returncode == 1
    assert "No VWAP was calculated." in result.stdout


def _build(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=102),
    )
    result = capture_es_timesales_dataset(tmp_path / "cli.sqlite3", _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id
