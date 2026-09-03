"""0W-2D: quote-token lifetime observability + the connect-time guard in
`scripts/dicks_lab_collect_es.py`.

The DXLink quote token lives ~24h with its `expires-at` anchored to first
issuance (0W-2C). The collector now (a) parses the non-secret issued-at /
expires-at and (b) on the INITIAL launch refuses to open a canonical capture
the token cannot outlast (horizon + small margin).
"""
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "dicks_lab_collect_es.py"
_spec = importlib.util.spec_from_file_location("dicks_lab_collect_es", _SCRIPT_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

_NOW = datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)


# --- pure helpers -----------------------------------------------------------


def test_parse_api_timestamp_accepts_offset_and_z():
    a = _mod._parse_api_timestamp("2026-09-04T02:53:45.218+00:00")
    b = _mod._parse_api_timestamp("2026-09-04T02:53:45.218Z")
    assert a == b == datetime(2026, 9, 4, 2, 53, 45, 218000, tzinfo=timezone.utc)


def test_parse_api_timestamp_rejects_junk():
    assert _mod._parse_api_timestamp(None) is None
    assert _mod._parse_api_timestamp("") is None
    assert _mod._parse_api_timestamp("not-a-time") is None


def test_quote_token_lifetime_computes_remaining():
    token_data = {
        "issued-at": "2026-09-01T22:00:00+00:00",
        "expires-at": "2026-09-02T22:00:00+00:00",
    }
    issued, expires, remaining = _mod._quote_token_lifetime(token_data, now=_NOW)
    assert issued == datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)
    assert expires == datetime(2026, 9, 2, 22, 0, tzinfo=timezone.utc)
    assert remaining == pytest.approx(24 * 3600)


def test_quote_token_lifetime_missing_fields_is_none():
    issued, expires, remaining = _mod._quote_token_lifetime({}, now=_NOW)
    assert issued is None and expires is None and remaining is None


# --- guard via the CLI ----------------------------------------------------


class _Stop(Exception):
    """Sentinel: reached run_long_horizon_capture (guard passed)."""


def _wire(monkeypatch, expires_at: datetime):
    calls: list = []

    class _FakeClient:
        access_token_refresh_count = 0

        def __init__(self, *_a, **_k):
            pass

        def list_futures(self):
            return [{"symbol": "/ESU6", "streamer-symbol": "/ESU26:XCME"}]

        def get_api_quote_token(self):
            return {
                "token": "REDACTED-not-a-real-token",
                "dxlink-url": "wss://example.invalid/dxlink",
                "issued-at": (expires_at - timedelta(hours=24)).isoformat(),
                "expires-at": expires_at.isoformat(),
            }

    def _fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        raise _Stop()

    monkeypatch.setattr(_mod, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr(_mod.TastytradeSettings, "from_environment", classmethod(lambda cls, _e: object()))
    monkeypatch.setattr(_mod, "TastytradeClient", _FakeClient)
    monkeypatch.setattr(_mod, "run_long_horizon_capture", _fake_run)
    return calls


def test_guard_blocks_short_lifetime_token(monkeypatch):
    # token expires 1h from now; a 23h capture must be refused before opening.
    calls = _wire(monkeypatch, datetime.now(tz=timezone.utc) + timedelta(hours=1))
    result = CliRunner().invoke(_mod.app, ["--duration", "23h"])
    assert result.exit_code != 0
    assert "quote-token lifetime is insufficient" in result.output.lower() or (
        result.exception is not None and "insufficient" in str(result.exception).lower()
    )
    assert calls == []  # never reached the capture


def test_guard_allows_fresh_full_lifetime_token(monkeypatch):
    calls = _wire(monkeypatch, datetime.now(tz=timezone.utc) + timedelta(hours=25))
    result = CliRunner().invoke(_mod.app, ["--duration", "23h"])
    assert isinstance(result.exception, _Stop)  # guard passed, capture entered
    assert len(calls) == 1
