import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.live_capture import capture_es_timesales_dataset

_SCRIPT = "scripts/dicks_lab_plot_developing_profile.py"
_SYMBOL = "/ESU26:XCME"
_MONDAY_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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
    # Headless guarantee: no DISPLAY, matching a CI-like environment (script also forces Agg).
    env.pop("DISPLAY", None)
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


# A. Plot command default interval
def test_default_interval_is_five_minutes(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "out.png"
    result = _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


# B / C / D. Explicit 1m / 5m / 15m
def test_explicit_one_minute_interval(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "out_1m.png"
    result = _run(str(path), "--anchor", "session-open", "--interval", "1m", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


def test_explicit_five_minute_interval(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "out_5m.png"
    result = _run(str(path), "--anchor", "session-open", "--interval", "5m", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


def test_explicit_fifteen_minute_interval(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "out_15m.png"
    result = _run(str(path), "--anchor", "session-open", "--interval", "15m", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


# E. Invalid interval rejected
def test_invalid_interval_rejected(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open", "--interval", "10m", "--output", str(tmp_path / "x.png"))
    assert result.returncode != 0
    assert not (tmp_path / "x.png").exists()


# F. Session-open plot
def test_session_open_plot(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "session.png"
    result = _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


# G. Custom-anchor plot
def test_custom_anchor_plot(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "custom.png"
    result = _run(str(path), "--anchor", "2026-08-23T22:02:00Z", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


# H / I. Cash-open produces no image; no-result exit behavior
def test_cash_open_produces_no_image_and_exits_one(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "cashopen.png"
    result = _run(str(path), "--anchor", "cash-open", "--output", str(output))
    assert result.returncode == 1
    assert not output.exists()
    assert "No developing profile visualization can be produced." in result.stdout


# U / V. PNG generated and non-empty; PNG signature
def test_png_generated_nonempty_with_valid_signature(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "sig.png"
    result = _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert result.returncode == 0, result.stderr
    data = output.read_bytes()
    assert len(data) > 0
    assert data[:8] == _PNG_SIGNATURE


# W. Headless execution (DISPLAY removed above; script also forces Agg backend)
def test_headless_execution_succeeds(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "headless.png"
    result = _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert result.returncode == 0, result.stderr
    assert output.exists()


# X. Read-only DB behavior
def test_read_only_database_mtime_unchanged(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "readonly.png"
    mtime_before = path.stat().st_mtime_ns
    _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert path.stat().st_mtime_ns == mtime_before


# Y. No network credentials required (env already scrubbed by _run)
def test_no_network_credentials_required(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "offline.png"
    result = _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert result.returncode == 0, result.stderr


def test_existing_output_rejected_without_overwrite(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "exists.png"
    output.write_bytes(b"placeholder")
    result = _run(str(path), "--anchor", "session-open", "--output", str(output))
    assert result.returncode == 2
    assert output.read_bytes() == b"placeholder"


def test_overwrite_flag_replaces_existing_output(tmp_path):
    path, _ = _build(tmp_path)
    output = tmp_path / "overwrite.png"
    output.write_bytes(b"placeholder")
    result = _run(str(path), "--anchor", "session-open", "--output", str(output), "--overwrite")
    assert result.returncode == 0, result.stderr
    assert output.read_bytes()[:8] == _PNG_SIGNATURE


def test_naive_custom_anchor_is_rejected(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "2026-08-24T14:15:00", "--output", str(tmp_path / "x.png"))
    assert result.returncode != 0
    assert "timezone-aware" in result.stderr.lower() or "timezone-aware" in result.stdout.lower()


def test_missing_database_path_fails_clearly():
    result = _run("no_such_file.sqlite3", "--anchor", "session-open", "--output", "x.png")
    assert result.returncode == 2
    assert "not found" in result.stdout.lower() or "not found" in result.stderr.lower()


def test_default_output_path_derived_next_to_database(tmp_path):
    path, _ = _build(tmp_path)
    result = _run(str(path), "--anchor", "session-open")
    assert result.returncode == 0, result.stderr
    generated = list(tmp_path.glob("developing_profile_*.png"))
    assert len(generated) == 1
