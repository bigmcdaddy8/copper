"""0W-2D: the pre-arm credential preflight must verify OAuth/REST/futures/symbol
resolution WITHOUT requesting a DXLink quote token (obtaining it early burns
its ~24h lifetime -- the 0W-2 Attempt-3 KNOWN_GAP root cause, 0W-2C)."""
from dicks_laboratory.preflight import run_credential_preflight

_SYMBOL = "/ESU6"
_STREAMER = "/ESU26:XCME"

_GOOD_FUTURES = [
    {"symbol": "/CLZ6", "streamer-symbol": "/CLZ26:XNYM"},
    {"symbol": _SYMBOL, "streamer-symbol": _STREAMER},
]


class _Client:
    """Minimal fake. `get_api_quote_token` explodes -- the preflight must never
    touch it."""

    def __init__(self, futures):
        self._futures = futures
        self.list_futures_calls = 0

    def list_futures(self):
        self.list_futures_calls += 1
        if isinstance(self._futures, Exception):
            raise self._futures
        return self._futures

    def get_api_quote_token(self):  # pragma: no cover - must not run
        raise AssertionError("preflight requested a DXLink quote token (0W-2D violation)")


def test_preflight_does_not_request_quote_token():
    client = _Client(_GOOD_FUTURES)
    result = run_credential_preflight(client, _SYMBOL, _STREAMER)
    assert result.ok
    assert client.list_futures_calls == 1  # one authenticated GET covers OAuth+REST+futures


def test_preflight_pass_on_resolved_symbol():
    result = run_credential_preflight(_Client(_GOOD_FUTURES), _SYMBOL, _STREAMER)
    assert result.rest_reachable
    assert result.futures_endpoint_usable
    assert result.futures_count == 2
    assert result.symbol_resolves
    assert result.streamer_symbol_matches
    assert result.ok


def test_preflight_fail_on_wrong_streamer_symbol():
    futures = [{"symbol": _SYMBOL, "streamer-symbol": "/ESZ26:XCME"}]
    result = run_credential_preflight(_Client(futures), _SYMBOL, _STREAMER)
    assert result.symbol_resolves
    assert not result.streamer_symbol_matches
    assert not result.ok


def test_preflight_fail_on_missing_symbol():
    result = run_credential_preflight(_Client([{"symbol": "/NQU6"}]), _SYMBOL, _STREAMER)
    assert result.rest_reachable
    assert not result.symbol_resolves
    assert not result.ok


def test_preflight_fail_on_rest_error():
    result = run_credential_preflight(_Client(RuntimeError("401")), _SYMBOL, _STREAMER)
    assert not result.rest_reachable
    assert not result.futures_endpoint_usable
    assert not result.ok


def test_preflight_script_module_never_calls_quote_token():
    """The tracked script wires the safe library function, not `get_api_quote_token`."""
    import pathlib

    src = (pathlib.Path(__file__).resolve().parents[3] / "scripts" / "dicks_lab_preflight.py").read_text()
    assert "get_api_quote_token" not in src
    assert "run_credential_preflight" in src
