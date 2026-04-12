"""Mock-based unit tests for TradierClient — no real network calls."""

import json
import time
from unittest.mock import patch

import httpx
import pytest

from tradier_sniffer.tradier_client import (
    ORDER_STATUSES,
    REJECTION_REASONS,
    TradierAPIError,
    TradierClient,
    _DEFAULT_DELAY,
    _MAX_DELAY,
    _MIN_DELAY,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROFILE_RESPONSE = {
    "profile": {
        "id": "testuser",
        "name": "Test User",
        "account": {"number": "VA12345678", "type": "margin"},
    }
}

_ORDERS_MULTI_RESPONSE = {
    "orders": {
        "order": [
            {"id": 1, "status": "open", "symbol": "SPY"},
            {"id": 2, "status": "filled", "symbol": "QQQ"},
        ]
    }
}

_ORDERS_SINGLE_RESPONSE = {
    "orders": {
        "order": {"id": 1, "status": "open", "symbol": "SPY"},
    }
}

_ORDERS_EMPTY_RESPONSE = {"orders": "null"}

_POSITIONS_MULTI_RESPONSE = {
    "positions": {
        "position": [
            {"id": 1, "symbol": "SPY", "quantity": 100},
            {"id": 2, "symbol": "QQQ", "quantity": -1},
        ]
    }
}

_POSITIONS_SINGLE_RESPONSE = {
    "positions": {
        "position": {"id": 1, "symbol": "SPY", "quantity": 100},
    }
}

_POSITIONS_EMPTY_RESPONSE = {"positions": "null"}

_BALANCES_RESPONSE = {
    "balances": {
        "total_equity": 10000.00,
        "total_cash": 5000.00,
        "option_buying_power": 4500.00,
        "day_trade_buying_power": 9000.00,
        "pending_orders_count": 0,
        "account_number": "VA12345678",
        "account_type": "margin",
        "option": {
            "short_value": 0.0,
            "long_value": 0.0,
        },
    }
}

_HISTORY_MULTI_RESPONSE = {
    "history": {
        "event": [
            {"date": "2026-01-01", "type": "trade", "description": "BTO SPY", "amount": -100.0},
            {"date": "2026-01-02", "type": "trade", "description": "STC SPY", "amount": 110.0},
        ]
    }
}

_HISTORY_SINGLE_RESPONSE = {
    "history": {
        "event": {"date": "2026-01-01", "type": "trade", "description": "BTO SPY", "amount": -100.0}
    }
}


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


def _client_with_transport(transport: httpx.MockTransport) -> TradierClient:
    client = TradierClient(api_key="test-key")
    client._compute_delay = lambda: 0.0  # suppress inter-request delay in tests
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
            content=json.dumps(_PROFILE_RESPONSE).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )

    client = _client_with_transport(httpx.MockTransport(handler))
    client.get_user_profile()

    assert len(captured) == 1
    assert captured[0].headers["Authorization"] == "Bearer test-key"
    assert captured[0].headers["Accept"] == "application/json"


# ---------------------------------------------------------------------------
# Sandbox base URL
# ---------------------------------------------------------------------------


def test_sandbox_base_url():
    client = TradierClient(api_key="k")
    assert "sandbox.tradier.com" in client._base_url


# ---------------------------------------------------------------------------
# get_user_profile
# ---------------------------------------------------------------------------


def test_get_user_profile_returns_dict():
    transport = _make_transport(200, _PROFILE_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_user_profile()
    assert result == _PROFILE_RESPONSE


# ---------------------------------------------------------------------------
# get_orders
# ---------------------------------------------------------------------------


def test_get_orders_returns_list_of_multiple():
    transport = _make_transport(200, _ORDERS_MULTI_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_orders("VA12345678")
    assert len(result) == 2
    assert result[0]["symbol"] == "SPY"
    assert result[1]["symbol"] == "QQQ"


def test_get_orders_normalises_single_order_to_list():
    transport = _make_transport(200, _ORDERS_SINGLE_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_orders("VA12345678")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_get_orders_returns_empty_list_when_no_orders():
    transport = _make_transport(200, {"orders": None})
    client = _client_with_transport(transport)
    result = client.get_orders("VA12345678")
    assert result == []


# ---------------------------------------------------------------------------
# get_positions
# ---------------------------------------------------------------------------


def test_get_positions_returns_list_of_multiple():
    transport = _make_transport(200, _POSITIONS_MULTI_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_positions("VA12345678")
    assert len(result) == 2
    assert result[0]["symbol"] == "SPY"
    assert result[1]["symbol"] == "QQQ"


def test_get_positions_normalises_single_position_to_list():
    transport = _make_transport(200, _POSITIONS_SINGLE_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_positions("VA12345678")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["id"] == 1


def test_get_positions_returns_empty_list_when_no_positions():
    transport = _make_transport(200, {"positions": None})
    client = _client_with_transport(transport)
    result = client.get_positions("VA12345678")
    assert result == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_non_2xx_raises_tradier_api_error():
    transport = _make_transport(429, {"fault": "rate limit exceeded"})
    client = _client_with_transport(transport)
    with pytest.raises(TradierAPIError) as exc_info:
        client.get_user_profile()
    assert exc_info.value.status_code == 429


def test_404_raises_tradier_api_error():
    transport = _make_transport(404, {"fault": "not found"})
    client = _client_with_transport(transport)
    with pytest.raises(TradierAPIError) as exc_info:
        client.get_orders("BADACCOUNT")
    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Hard rate-limit throttle (_throttle)
# ---------------------------------------------------------------------------


def test_rate_limit_throttle_triggered_when_available_low():
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
            content=json.dumps(_PROFILE_RESPONSE).encode(),
            headers={"content-type": "application/json", **rl_headers},
            request=request,
        )

    client = _client_with_transport(httpx.MockTransport(handler))
    client.get_user_profile()
    assert client._ratelimit_available == 3

    with patch("tradier_sniffer.tradier_client.time.sleep") as mock_sleep:
        client.get_user_profile()
        assert mock_sleep.called


def test_rate_limit_throttle_not_triggered_when_available_high():
    client = TradierClient(api_key="k")
    client._ratelimit_available = 100
    client._ratelimit_expiry = int((time.time() + 60) * 1000)

    with patch("tradier_sniffer.tradier_client.time.sleep") as mock_sleep:
        client._throttle()
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# Adaptive delay (_compute_delay)
# ---------------------------------------------------------------------------


def test_compute_delay_no_rate_limit_data():
    client = TradierClient(api_key="k")
    assert client._compute_delay() == pytest.approx(_DEFAULT_DELAY)


def test_compute_delay_stays_within_bounds():
    client = TradierClient(api_key="k")
    client._ratelimit_available = 300
    client._ratelimit_expiry = int((time.time() + 45) * 1000)
    delay = client._compute_delay()
    assert _MIN_DELAY <= delay <= _MAX_DELAY


def test_compute_delay_low_available_slower_than_high():
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
    client = TradierClient(api_key="k")
    client._ratelimit_available = 1000
    client._ratelimit_expiry = int((time.time() + 5) * 1000)
    assert client._compute_delay() >= _MIN_DELAY


def test_compute_delay_clamps_to_max():
    client = TradierClient(api_key="k")
    client._ratelimit_available = 1
    client._ratelimit_expiry = int((time.time() + 3600) * 1000)
    assert client._compute_delay() <= _MAX_DELAY


def test_compute_delay_no_expiry_uses_assumed_window():
    client = TradierClient(api_key="k")
    client._ratelimit_available = 300
    client._ratelimit_expiry = None
    delay = client._compute_delay()
    assert _MIN_DELAY <= delay <= _MAX_DELAY


# ---------------------------------------------------------------------------
# rate_limit_state and last_computed_delay properties
# ---------------------------------------------------------------------------


def test_rate_limit_state_initially_none():
    client = TradierClient(api_key="k")
    assert client.rate_limit_state == (None, None)


def test_rate_limit_state_after_update():
    client = TradierClient(api_key="k")
    client._ratelimit_available = 42
    client._ratelimit_expiry = 999000
    assert client.rate_limit_state == (42, 999000)


def test_last_computed_delay_initial_value():
    client = TradierClient(api_key="k")
    assert client.last_computed_delay == pytest.approx(_DEFAULT_DELAY)


# ---------------------------------------------------------------------------
# ORDER_STATUSES and REJECTION_REASONS completeness
# ---------------------------------------------------------------------------


def test_order_statuses_contains_required_keys():
    required = {"filled", "partially_filled", "open", "expired", "canceled", "pending", "rejected"}
    assert required.issubset(ORDER_STATUSES.keys())


def test_rejection_reasons_present():
    assert len(REJECTION_REASONS) > 0
    assert "invalid_price" in REJECTION_REASONS


# ---------------------------------------------------------------------------
# get_balances
# ---------------------------------------------------------------------------


def test_get_balances_returns_dict():
    transport = _make_transport(200, _BALANCES_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_balances("VA12345678")
    assert isinstance(result, dict)
    assert result["total_equity"] == pytest.approx(10000.00)
    assert result["option_buying_power"] == pytest.approx(4500.00)


def test_get_balances_returns_empty_dict_when_none():
    transport = _make_transport(200, {"balances": None})
    client = _client_with_transport(transport)
    result = client.get_balances("VA12345678")
    assert result == {}


# ---------------------------------------------------------------------------
# get_history
# ---------------------------------------------------------------------------


def test_get_history_returns_list_of_multiple():
    transport = _make_transport(200, _HISTORY_MULTI_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_history("VA12345678")
    assert len(result) == 2
    assert result[0]["type"] == "trade"


def test_get_history_normalises_single_event_to_list():
    transport = _make_transport(200, _HISTORY_SINGLE_RESPONSE)
    client = _client_with_transport(transport)
    result = client.get_history("VA12345678")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["description"] == "BTO SPY"


def test_get_history_returns_empty_list_when_no_history():
    transport = _make_transport(200, {"history": None})
    client = _client_with_transport(transport)
    result = client.get_history("VA12345678")
    assert result == []
