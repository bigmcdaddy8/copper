"""Mock transport tests for order-placement and option-chain client methods."""

import json

import httpx
import pytest

from tradier_sniffer.tradier_client import TradierAPIError, TradierClient


# ---------------------------------------------------------------------------
# Helpers (mirrors pattern from test_client.py)
# ---------------------------------------------------------------------------


def _make_transport(status_code: int, body: dict, headers: dict | None = None) -> httpx.MockTransport:
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
    client._compute_delay = lambda: 0.0
    client._client = httpx.Client(
        base_url=client._base_url,
        headers={"Authorization": "Bearer test-key", "Accept": "application/json"},
        transport=transport,
    )
    return client


# ---------------------------------------------------------------------------
# place_multileg_order
# ---------------------------------------------------------------------------

_ORDER_OK = {"order": {"id": 12345, "status": "ok", "partner_id": 0}}


def test_place_multileg_order_returns_order_dict():
    client = _client_with_transport(_make_transport(200, _ORDER_OK))
    legs = [
        {"option_symbol": "SPX240119P04500000", "side": "sell_to_open", "quantity": 1},
        {"option_symbol": "SPX240119P04400000", "side": "buy_to_open",  "quantity": 1},
        {"option_symbol": "SPX240119C04600000", "side": "sell_to_open", "quantity": 1},
        {"option_symbol": "SPX240119C04700000", "side": "buy_to_open",  "quantity": 1},
    ]
    result = client.place_multileg_order("ACC1", legs, 1.50)
    assert result["order"]["id"] == 12345
    assert result["order"]["status"] == "ok"


def test_place_multileg_raises_on_4xx():
    client = _client_with_transport(_make_transport(400, {"fault": {"faultstring": "Bad request"}}))
    with pytest.raises(TradierAPIError) as exc_info:
        client.place_multileg_order("ACC1", [], 1.00)
    assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# cancel_order
# ---------------------------------------------------------------------------


def test_cancel_order_returns_dict():
    client = _client_with_transport(_make_transport(200, _ORDER_OK))
    result = client.cancel_order("ACC1", "12345")
    assert result["order"]["id"] == 12345


# ---------------------------------------------------------------------------
# get_option_expirations
# ---------------------------------------------------------------------------

_EXPIRATIONS_RESPONSE = {
    "expirations": {
        "date": ["2024-01-26", "2024-01-19", "2024-02-16"]
    }
}


def test_get_option_expirations_returns_sorted_list():
    client = _client_with_transport(_make_transport(200, _EXPIRATIONS_RESPONSE))
    result = client.get_option_expirations("SPX")
    assert result == ["2024-01-19", "2024-01-26", "2024-02-16"]


# ---------------------------------------------------------------------------
# get_option_chain
# ---------------------------------------------------------------------------

_CHAIN_SINGLE = {
    "options": {
        "option": {
            "symbol": "SPX240119P04500000",
            "strike": 4500.0,
            "option_type": "put",
            "bid": 1.20,
            "ask": 1.30,
            "greeks": {"delta": -0.21},
        }
    }
}


def test_get_option_chain_normalises_single():
    client = _client_with_transport(_make_transport(200, _CHAIN_SINGLE))
    result = client.get_option_chain("SPX", "2024-01-19")
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["strike"] == 4500.0
