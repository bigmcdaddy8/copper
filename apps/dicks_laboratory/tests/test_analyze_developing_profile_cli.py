import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.live_capture import capture_es_timesales_dataset

_SCRIPT = "scripts/dicks_lab_analyze_developing_profile.py"
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


def _build(tmp_path, events=None, name="cli.sqlite3"):
    if events is None:
        events = (
            _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
            _event(_MONDAY_OPEN + timedelta(minutes=6), 2, price=7694.25),
            _event(_MONDAY_OPEN + timedelta(minutes=12), 3, price=7694.50),
        )
    result = capture_es_timesales_dataset(tmp_path / name, _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


# A. Default interval = 5m
def test_default_interval_is_five_minutes(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "Slice interval:\n  5 minutes" in result.stdout


# B / C / D. Explicit 1m / 5m / 15m
def test_explicit_one_minute_interval(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--interval", "1m")
    assert result.returncode == 0, result.stderr
    assert "1 minute" in result.stdout


def test_explicit_five_minute_interval(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--interval", "5m")
    assert result.returncode == 0, result.stderr
    assert "5 minutes" in result.stdout


def test_explicit_fifteen_minute_interval(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--interval", "15m")
    assert result.returncode == 0, result.stderr
    assert "15 minutes" in result.stdout


# E. Invalid interval rejected
def test_invalid_interval_rejected(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--interval", "10m")
    assert result.returncode != 0
    assert "invalid" in result.stderr.lower() or "invalid" in result.stdout.lower()


# F. Session-open path
def test_session_open_runs_without_network_credentials(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "Developing Profile Timeline" in result.stdout


# G. Custom-anchor path
def test_custom_anchor_path(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "2026-08-23T22:02:00Z")
    assert result.returncode == 0, result.stderr
    assert "Custom UTC anchor" in result.stdout


# H. Cash-open no-result path
def test_cash_open_no_result(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "cash-open")
    assert result.returncode == 1
    assert "No developing profile timeline can be computed." in result.stdout
    assert "Time" not in result.stdout.split("Coverage:")[1].split("No retained trades")[0]


# I / J. Coverage and unobserved pre-capture interval shown
def test_coverage_and_pre_capture_interval_shown(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, _ = _build(tmp_path, events=(_event(first_trade, 1),))
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "DATASET_BEGINS_AFTER_ANCHOR" in result.stdout
    assert "Unobserved pre-capture interval:" in result.stdout


# K. No fake pre-capture rows shown
def test_no_fake_precapture_rows(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, _ = _build(tmp_path, events=(_event(first_trade, 1),))
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    table_section = result.stdout.split("Time")[1].split("Each row is cumulative")[0]
    assert "17:05" not in table_section
    assert "18:15" not in table_section


# L / M / N / O / P / Q. Timeline table headers and columns
def test_timeline_table_headers_and_columns(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "Time" in result.stdout and "New" in result.stdout and "Cum" in result.stdout
    assert "Volume" in result.stdout and "VWAP" in result.stdout
    assert "POC" in result.stdout and "VAL" in result.stdout and "VAH" in result.stdout


# R. Terminal row marked
def test_terminal_row_marked(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "*" in result.stdout


# S. Last retained trade footnote shown
def test_last_retained_trade_footnote_shown(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "terminal analytical cutoff; last retained trade was" in result.stdout


# T. Retrospective effective-tape caveat shown
def test_retrospective_caveat_shown(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "Retrospectively reconstructed" in result.stdout


# U. Cumulative-not-rolling statement shown
def test_cumulative_not_rolling_statement_shown(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    assert "This is not a rolling-window profile." in result.stdout


# V. Analytical no-result exit code
def test_no_result_exit_code_is_one(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "cash-open")
    assert result.returncode == 1


# W. Read-only DB behavior
def test_read_only_database_mtime_unchanged(tmp_path):
    path, _ = _build(tmp_path)
    mtime_before = path.stat().st_mtime_ns
    _run(str(path), "--anchor", "session-open")
    assert path.stat().st_mtime_ns == mtime_before


# X. No network credentials required (env already scrubbed by _run)
def test_no_network_credentials_required(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--interval", "1m")
    assert result.returncode == 0, result.stderr


def test_naive_custom_anchor_is_rejected(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "2026-08-24T14:15:00")
    assert result.returncode != 0
    assert "timezone-aware" in result.stderr.lower() or "timezone-aware" in result.stdout.lower()


def test_missing_database_path_fails_clearly():
    result = _run("no_such_file.sqlite3", "--anchor", "session-open")
    assert result.returncode == 2
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_canonical_source_option(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--source", "canonical")
    assert result.returncode == 0, result.stderr
    assert "Canonical NEW-only" in result.stdout
    assert "Retrospectively reconstructed" not in result.stdout


def test_invalid_source_rejected(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--source", "bogus")
    assert result.returncode != 0
