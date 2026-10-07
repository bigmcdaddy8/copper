"""0X-A smoke tests: the read-only roll-check CLI and the preflight roll gate.
Offline only (saved metadata / fake client); never a quote token."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

_REPO = Path(__file__).resolve().parents[3]
_ROLL_SCRIPT = "scripts/dicks_lab_roll_check.py"


def _row(symbol, streamer, expiration, active=False, next_active=False, root="ES", mult="50.0"):
    return {"symbol": symbol, "product-code": root, "streamer-symbol": streamer, "exchange": "CME",
            "expiration-date": expiration, "stops-trading-at": f"{expiration}T14:30:00.000+00:00",
            "active-month": active, "next-active-month": next_active, "is-tradeable": True,
            "is-closing-only": False, "tick-size": "0.25", "notional-multiplier": mult,
            "future-product": {"listed-months": ["H", "M", "U", "Z"]}}


_FUTURES = [
    _row("/ESZ6", "/ESZ26:XCME", "2026-12-18", active=True),
    _row("/ESH7", "/ESH27:XCME", "2027-03-19", next_active=True),
    _row("/MESZ6", "/MESZ26:XCME", "2026-12-18", active=True, root="MES", mult="5.0"),
]


def _run(tmp_path, *args):
    meta = tmp_path / "futures.json"
    meta.write_text(json.dumps(_FUTURES))
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
    return subprocess.run([sys.executable, _ROLL_SCRIPT, *args, "--metadata-json", str(meta)],
                          cwd=_REPO, env=env, capture_output=True, text=True)


def test_roll_check_help():
    r = subprocess.run([sys.executable, _ROLL_SCRIPT, "--help"], cwd=_REPO, capture_output=True, text=True)
    assert r.returncode == 0 and "check" in r.stdout and "chain" in r.stdout


def test_roll_check_current(tmp_path):
    r = _run(tmp_path, "check", "--trading-date", "2026-10-07")
    assert r.returncode == 0, r.stderr
    for text in ("Product: ES", "/ESZ6", "FUTURE:CME:ES:2026-12", "expires 2026-12-18",
                 "customary roll 2026-12-14", "active-month       /ESZ6", "next-active-month  /ESH7",
                 "CURRENT (OK)", "Recommended production action:\n  NONE"):
        assert text in r.stdout


def test_roll_check_approaching_and_draft_record(tmp_path):
    draft = tmp_path / "roll.json"
    r = _run(tmp_path, "check", "--trading-date", "2026-12-01", "--roll-record-draft", str(draft))
    assert r.returncode == 0, r.stderr
    assert "ROLL_APPROACHING (WARN)" in r.stdout and "/ESZ6 -> /ESH7" in r.stdout
    rec = json.loads(draft.read_text())
    assert rec["new_contract"]["broker_symbol"] == "/ESH7" and rec["decision"]["approved_by"] is None


def test_roll_check_stale_exits_nonzero(tmp_path):
    r = _run(tmp_path, "check", "--trading-date", "2026-12-18")
    assert r.returncode == 1
    assert "PIN_STALE (FAIL)" in r.stdout


def test_chain_lists_contracts(tmp_path):
    r = _run(tmp_path, "chain", "MES")
    assert r.returncode == 0, r.stderr
    assert "/MESZ6" in r.stdout and "FUTURE:CME:MES:2026-12" in r.stdout and "micro of ES" in r.stdout


# --- preflight roll gate (script wiring, fake client) -------------------------------

_spec = importlib.util.spec_from_file_location("dicks_lab_preflight", _REPO / "scripts" / "dicks_lab_preflight.py")
_pre = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _pre
_spec.loader.exec_module(_pre)


class _FakeClient:
    calls = 0

    def __init__(self, _settings):
        pass

    def list_futures(self):
        type(self).calls += 1
        return _FUTURES

    def get_api_quote_token(self):  # pragma: no cover - must not run
        raise AssertionError("preflight requested a DXLink quote token")


@pytest.fixture
def preflight(monkeypatch):
    monkeypatch.setattr(_pre, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(_pre.TastytradeSettings, "from_environment", classmethod(lambda cls, _e: object()))
    monkeypatch.setattr(_pre, "TastytradeClient", _FakeClient)
    _FakeClient.calls = 0

    def run(trading_date: date):
        monkeypatch.setattr(_pre, "upcoming_trading_date", lambda _now: trading_date)
        return CliRunner().invoke(_pre.app, [])
    return run


@pytest.mark.parametrize("td,state", [(date(2026, 10, 7), "CURRENT"), (date(2026, 11, 29), "CURRENT"),
                                      (date(2026, 11, 30), "ROLL_APPROACHING"), (date(2026, 12, 11), "ROLL_APPROACHING")])
def test_preflight_passes_when_roll_is_current_or_approaching(preflight, td, state):
    r = preflight(td)
    assert r.exit_code == 0, r.output
    assert f"roll_state={state}" in r.output and "PREFLIGHT_RESULT=PASS" in r.output
    assert "quote_token_requested=false" in r.output
    assert _FakeClient.calls == 1  # the roll check reuses the single metadata response


def test_preflight_fails_closed_on_stale_pin(preflight):
    r = preflight(date(2026, 12, 18))
    assert r.exit_code == 1
    assert "roll_state=PIN_STALE roll_severity=FAIL" in r.output and "PREFLIGHT_RESULT=FAIL" in r.output


@pytest.mark.parametrize("td,state", [(date(2026, 12, 14), "ROLL_DUE"), (date(2026, 12, 16), "ROLL_DUE"),
                                      (date(2026, 12, 18), "PIN_STALE")])
def test_preflight_fails_closed_on_roll_due_and_expiration(preflight, td, state):
    r = preflight(td)
    assert r.exit_code == 1
    assert f"roll_state={state} roll_severity=FAIL" in r.output and "PREFLIGHT_RESULT=FAIL" in r.output
    assert "quote_token_requested=false" in r.output


def test_approaching_preflight_prints_warning_lines(preflight):
    r = preflight(date(2026, 11, 30))
    assert "roll_severity=WARN" in r.output and "roll_reason=customary roll 2026-12-14" in r.output
    assert "roll_recommended_action=HUMAN: REVIEW AND PREPARE ROLL: /ESZ6 -> /ESH7" in r.output


# --- 0X-B: the real Sunday 2026-12-13 16:42 CT preflight (real clock -> trading date) ----

class _Sunday1642(datetime):
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 12, 13, 22, 42, tzinfo=timezone.utc).astimezone(tz)


# Broker metadata as it is expected to look that Sunday (the broker roll offset
# has advanced active-month to /ESH7); /ESZ6 is still listed and tradeable.
_DEC13_FUTURES = [
    _row("/ESZ6", "/ESZ26:XCME", "2026-12-18"),
    _row("/ESH7", "/ESH27:XCME", "2027-03-19", active=True),
    _row("/ESM7", "/ESM27:XCME", "2027-06-17", next_active=True),
]


@pytest.fixture
def sunday_preflight(monkeypatch):
    monkeypatch.setattr(_pre, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(_pre.TastytradeSettings, "from_environment", classmethod(lambda cls, _e: object()))
    monkeypatch.setattr(_pre, "datetime", _Sunday1642)

    class _Client(_FakeClient):
        def list_futures(self):
            return _DEC13_FUTURES
    monkeypatch.setattr(_pre, "TastytradeClient", _Client)

    def run(pin, streamer):
        monkeypatch.setattr(_pre, "_SYMBOL", pin)
        monkeypatch.setattr(_pre, "_EXPECTED_STREAMER", streamer)
        return CliRunner().invoke(_pre.app, [])
    return run


def test_sunday_dec13_preflight_refuses_z6_pin(sunday_preflight):
    r = sunday_preflight("/ESZ6", "/ESZ26:XCME")
    assert r.exit_code == 1
    assert "roll_trading_date=2026-12-14" in r.output
    assert "roll_state=ROLL_DUE roll_severity=FAIL" in r.output
    assert "ROLL REQUIRED BEFORE PRODUCTION CAPTURE" in r.output
    assert "PREFLIGHT_RESULT=FAIL" in r.output


def test_sunday_dec13_preflight_passes_after_explicit_h7_repin(sunday_preflight):
    r = sunday_preflight("/ESH7", "/ESH27:XCME")
    assert r.exit_code == 0, r.output
    assert "roll_trading_date=2026-12-14" in r.output
    assert "roll_state=CURRENT roll_severity=OK" in r.output
    assert "PREFLIGHT_RESULT=PASS" in r.output


def test_assessment_cli_and_preflight_never_change_the_production_pin(tmp_path, preflight):
    from dicks_laboratory import production_symbol
    src = _REPO / "apps" / "dicks_laboratory" / "src" / "dicks_laboratory" / "production_symbol.py"
    unit = _REPO / "deploy" / "dicks_laboratory" / "systemd" / "dicks-lab-es-session.service"
    before = (production_symbol.PINNED_ES_SYMBOL, src.read_bytes(), unit.read_bytes(), _pre._SYMBOL)
    preflight(date(2026, 12, 14))
    preflight(date(2026, 12, 18))
    _run(tmp_path, "check", "--trading-date", "2026-12-14")
    assert (production_symbol.PINNED_ES_SYMBOL, src.read_bytes(), unit.read_bytes(), _pre._SYMBOL) == before
    assert before[0] == "/ESZ6"


def test_roll_check_cli_exit_reflects_production_readiness(tmp_path):
    assert _run(tmp_path, "check", "--trading-date", "2026-10-07").returncode == 0
    approaching = _run(tmp_path, "check", "--trading-date", "2026-11-30")
    assert approaching.returncode == 0 and "PASS + WARNING" in approaching.stdout
    due = _run(tmp_path, "check", "--trading-date", "2026-12-14")
    assert due.returncode == 1
    assert "ROLL_DUE (FAIL)" in due.stdout and "ROLL REQUIRED BEFORE PRODUCTION CAPTURE" in due.stdout
    assert "Production readiness (preflight policy):\n  FAIL" in due.stdout
