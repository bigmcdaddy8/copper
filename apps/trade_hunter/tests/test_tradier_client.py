"""Mock-based unit tests for TradierClient — no real network calls."""

import json
import time
from unittest.mock import patch

import httpx
import pytest

from trade_hunter.tradier.client import TradierAPIError, TradierClient

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
                "delta": -0.20,
                "bid": 1.10,
                "ask": 1.20,
                "open_interest": 500,
                "last": 1.15,
            },
            {
                "strike": 460.0,
                "option_type": "call",
                "delta": 0.22,
                "bid": 0.90,
                "ask": 1.00,
                "open_interest": 300,
                "last": 0.95,
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
    client = TradierClient(api_key="test-key", sandbox=sandbox, request_delay=0)
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
    client = TradierClient(api_key="k", sandbox=False, request_delay=0)
    assert "api.tradier.com" in client._base_url


def test_sandbox_base_url():
    client = TradierClient(api_key="k", sandbox=True, request_delay=0)
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
# Rate-limit throttle
# ---------------------------------------------------------------------------


def test_rate_limit_throttle():
    """After a response with X-Ratelimit-Available: 3, sleep is called before next request."""
    # Expiry ~100 seconds in the future so we can verify sleep is called
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
        # sleep must have been called at least once (for throttle)
        assert mock_sleep.called


def test_no_delay_when_available_high():
    """When X-Ratelimit-Available is high, rate-limit throttle sleep is NOT triggered."""
    rl_headers = {
        "X-Ratelimit-Available": "100",
        "X-Ratelimit-Expiry": "9999999999000",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=json.dumps(_EXPIRATIONS_RESPONSE).encode(),
            headers={"content-type": "application/json", **rl_headers},
            request=request,
        )

    client = _client_with_transport(httpx.MockTransport(handler))

    # First call — stores high availability
    client.get_option_expirations("SPY")
    assert client._ratelimit_available == 100

    # Second call — no rate-limit throttle sleep expected (request_delay=0 so no inter-request sleep)
    with patch("trade_hunter.tradier.client.time.sleep") as mock_sleep:
        client.get_option_expirations("SPY")
        mock_sleep.assert_not_called()
