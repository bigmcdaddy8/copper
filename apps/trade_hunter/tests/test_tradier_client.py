"""Mock-based unit tests for TradierClient — no real network calls."""

import json
import time
from unittest.mock import patch

import httpx
import pytest

from trade_hunter.tradier.client import (
    TradierAPIError,
    TradierClient,
    _DEFAULT_DELAY,
    _MAX_DELAY,
    _MIN_DELAY,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXPIRATIONS_RESPONSE = {
    "expirations": {
        "date": ["2025-01-17", "2025-02-21", "2025-03-21"],
    }
}

_SINGLE_EXPIRATION_RESPONSE = {
    "expirations": {
        "date": "2025-01-17",
    }
}

_EMPTY_EXPIRATIONS_RESPONSE = {"expirations": None}

_CHAIN_RESPONSE = {
    "options": {
        "option": [
            {
                "strike": 450.0,
                "option_type": "put",
                "bid": 1.10,
                "ask": 1.20,
                "open_interest": 500,
                "last": 1.15,
                "greeks": {
                    "delta": -0.20,
                    "gamma": 0.01,
                    "theta": -0.05,
                    "vega": 0.10,
                },
            },
            {
                "strike": 460.0,
                "option_type": "call",
                "bid": 0.90,
                "ask": 1.00,
                "open_interest": 300,
                "last": 0.95,
                "greeks": {
                    "delta": 0.22,
                    "gamma": 0.01,
                    "theta": -0.04,
                    "vega": 0.09,
                },
            },
        ]
    }
}

_EMPTY_CHAIN_RESPONSE = {"options": None}


def _make_transport(
    status_code: int, body: dict, headers: dict | None = None
) -> httpx.MockTransport:
    response_headers = {"content-type": "application/json"}
    if headers:
        response_headers.update(headers)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            status_code=status_code,
            content=json.dumps(body).encode(),
            headers=response_headers,
            request=request,
        )

    return httpx.MockTransport(handler)


def _client_with_transport(transport: httpx.MockTransport, sandbox: bool = False) -> TradierClient:
    client = TradierClient(api_key="test-key", sandbox=sandbox)
    # Suppress inter-request delay so unit tests run at full speed.
    client._compute_delay = lambda: 0.0
    client._client = httpx.Client(
        base_url=client._base_url,
        headers={
            "Authorization": "Bearer test-key",
            "Accept": "application/json",
        },
        transport=transport,
    )
    return client


# ---------------------------------------------------------------------------
# Auth header
# ---------------------------------------------------------------------------


def test_auth_header_injected():
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            content=json.dumps(_EXPIRATIONS_RESPONSE).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    client = _client_with_transport(httpx.MockTransport(handler))
    client.get_option_expirations("SPY")

    assert len(captured) == 1
    assert captured[0].headers["Authorization"] == "Bearer test-key"
    assert captured[0].headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# Base URL selection
# ---------------------------------------------------------------------------


def test_production_base_url():
    client = TradierClient(api_key="k", sandbox=False)
    assert "api.tradier.com" in client._base_url


def test_sandbox_base_url():
    client = TradierClient(api_key="k", sandbox=True)
    assert "sandbox.tradier.com" in client._base_url


# ---------------------------------------------------------------------------
# get_option_expirations
# ---------------------------------------------------------------------------


def test_get_option_expirations_parses_response():
    transport = _make_transport(200, _EXPIRATIONS_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_option_expirations("SPY")
    assert result == ["2025-01-17", "2025-02-21", "2025-03-21"]


def test_get_option_expirations_single_date_as_string():
    """Tradier occasionally returns a single date as a bare string, not a list."""
    transport = _make_transport(200, _SINGLE_EXPIRATION_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_option_expirations("SPY")
    assert result == ["2025-01-17"]


def test_get_option_expirations_empty():
    transport = _make_transport(200, _EMPTY_EXPIRATIONS_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_option_expirations("NOPE")
    assert result == []


# ---------------------------------------------------------------------------
# get_option_chain
# ---------------------------------------------------------------------------


def test_get_option_chain_parses_response():
    transport = _make_transport(200, _CHAIN_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_option_chain("SPY", "2025-01-17")
    assert len(result) == 2
    assert result[0]["option_type"] == "put"
    assert result[1]["option_type"] == "call"


def test_get_option_chain_empty():
    transport = _make_transport(200, _EMPTY_CHAIN_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_option_chain("NOPE", "2025-01-17")
    assert result == []


# ---------------------------------------------------------------------------
# get_last_price
# ---------------------------------------------------------------------------

_QUOTES_RESPONSE = {
    "quotes": {
        "quote": {
            "symbol": "SPY",
            "last": 594.21,
        }
    }
}


def test_get_last_price_parses_response():
    transport = _make_transport(200, _QUOTES_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_last_price("SPY")
    assert result == pytest.approx(594.21)


def test_get_last_price_non_2xx_raises():
    transport = _make_transport(404, {"fault": "symbol not found"})
    client = _client_with_transport(transport)
    with pytest.raises(TradierAPIError) as exc_info:
        client.get_last_price("NOPE")
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_non_2xx_raises_tradier_api_error():
    transport = _make_transport(429, {"fault": "rate limit exceeded"})
    client = _client_with_transport(transport)
    with pytest.raises(TradierAPIError) as exc_info:
        client.get_option_expirations("SPY")
    assert exc_info.value.status_code == 429


# ---------------------------------------------------------------------------
# Hard rate-limit throttle (_throttle)
# ---------------------------------------------------------------------------


def test_rate_limit_throttle():
    """After a response with X-Ratelimit-Available: 3, sleep is called before next request."""
    future_expiry_ms = int((time.time() + 100) * 1000)
    rl_headers = {
        "X-Ratelimit-Available": "3",
        "X-Ratelimit-Expiry": str(future_expiry_ms),
    }

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            content=json.dumps(_EXPIRATIONS_RESPONSE).encode(),
            headers={"content-type": "application/json", **rl_headers},
            request=request,
        )

    client = _client_with_transport(httpx.MockTransport(handler))

    # First call — stores rate-limit state
    client.get_option_expirations("SPY")
    assert client._ratelimit_available == 3

    # Second call — should trigger throttle sleep
    with patch("trade_hunter.tradier.client.time.sleep") as mock_sleep:
        client.get_option_expirations("SPY")
        assert mock_sleep.called


def test_hard_throttle_not_triggered_when_available_high():
    """When X-Ratelimit-Available > 5, _throttle does not sleep to wait for reset."""
    client = TradierClient(api_key="k")
    client._ratelimit_available = 100
    client._ratelimit_expiry = int((time.time() + 60) * 1000)

    with patch("trade_hunter.tradier.client.time.sleep") as mock_sleep:
        client._throttle()
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Adaptive delay (_compute_delay)
# ---------------------------------------------------------------------------


def test_compute_delay_no_rate_limit_data():
    """Returns DEFAULT_DELAY before any headers have been received."""
    client = TradierClient(api_key="k")
    assert client._compute_delay() == pytest.approx(_DEFAULT_DELAY)


def test_compute_delay_normal_window():
    """Delay is within bounds given typical mid-window conditions."""
    client = TradierClient(api_key="k")
    client._ratelimit_available = 300
    client._ratelimit_expiry = int((time.time() + 45) * 1000)
    delay = client._compute_delay()
    assert _MIN_DELAY <= delay <= _MAX_DELAY


def test_compute_delay_low_available_slower_than_high():
    """Lower available headroom produces a longer delay than high headroom."""
    client = TradierClient(api_key="k")
    expiry_ms = int((time.time() + 45) * 1000)

    client._ratelimit_available = 8
    client._ratelimit_expiry = expiry_ms
    delay_low = client._compute_delay()

    client._ratelimit_available = 300
    client._ratelimit_expiry = expiry_ms
    delay_high = client._compute_delay()

    assert delay_low > delay_high


def test_compute_delay_clamps_to_min():
    """Delay never falls below MIN_DELAY even with abundant headroom."""
    client = TradierClient(api_key="k")
    client._ratelimit_available = 1000
    client._ratelimit_expiry = int((time.time() + 5) * 1000)
    assert client._compute_delay() >= _MIN_DELAY


def test_compute_delay_clamps_to_max():
    """Delay never exceeds MAX_DELAY even when very few calls remain."""
    client = TradierClient(api_key="k")
    client._ratelimit_available = 1
    client._ratelimit_expiry = int((time.time() + 3600) * 1000)
    assert client._compute_delay() <= _MAX_DELAY


def test_compute_delay_no_expiry_uses_assumed_window():
    """When expiry header is absent, a 60-second window is assumed."""
    client = TradierClient(api_key="k")
    client._ratelimit_available = 300
    client._ratelimit_expiry = None  # no expiry header
    delay = client._compute_delay()
    assert _MIN_DELAY <= delay <= _MAX_DELAY


# ---------------------------------------------------------------------------
# rate_limit_state property
# ---------------------------------------------------------------------------


def test_rate_limit_state_initially_none():
    client = TradierClient(api_key="k")
    assert client.rate_limit_state == (None, None)


def test_rate_limit_state_after_update():
    client = TradierClient(api_key="k")
    client._ratelimit_available = 42
    client._ratelimit_expiry = 999000
    assert client.rate_limit_state == (42, 999000)


# ---------------------------------------------------------------------------
# last_computed_delay property
# ---------------------------------------------------------------------------


def test_last_computed_delay_initial_value():
    """Starts at DEFAULT_DELAY before any API calls."""
    client = TradierClient(api_key="k")
    assert client.last_computed_delay == pytest.approx(_DEFAULT_DELAY)


def test_last_computed_delay_updates_after_call():
    """last_computed_delay reflects the result of the most recent _compute_delay call."""
    transport = _make_transport(
        200,
        _EXPIRATIONS_RESPONSE,
        headers={
            "X-Ratelimit-Available": "200",
            "X-Ratelimit-Expiry": str(int((time.time() + 45) * 1000)),
        },
    )
    client = _client_with_transport(transport)
    client.get_option_expirations("SPY")
    # After the call, last_computed_delay should reflect real header data
    assert _MIN_DELAY <= client.last_computed_delay <= _MAX_DELAY
