from __future__ import annotations

import json

import httpx
import pytest
import respx

from K9.tastytrade.client import TastytradeAPIError, TastytradeClient
from K9.tastytrade.settings import TastytradeSettings


@pytest.fixture
def client() -> TastytradeClient:
    settings = TastytradeSettings(
        app_name="k9-diagnostic",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        account_number="5WT00001",
        environment="tastytrade_production",
        base_url="https://api.tastyworks.com",
    )
    return TastytradeClient(settings)


@respx.mock
def test_named_read_method_refreshes_oauth_token_and_sends_required_headers(client):
    token_route = respx.post("https://api.tastyworks.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "first-token"})
    )
    account_route = respx.get("https://api.tastyworks.com/customers/me/accounts").mock(
        return_value=httpx.Response(200, json={"data": {"items": []}})
    )

    payload = client.list_accounts()

    assert payload == []
    assert token_route.called
    assert account_route.called
    assert token_route.calls[0].request.headers["User-Agent"] == "k9-diagnostic/1.0"
    assert token_route.calls[0].request.content == (
        b"grant_type=refresh_token&refresh_token=refresh-token&client_secret=client-secret"
    )
    assert account_route.calls[0].request.headers["Authorization"] == "Bearer first-token"


@respx.mock
def test_named_read_method_refreshes_once_after_expired_bearer_token(client):
    token_route = respx.post("https://api.tastyworks.com/oauth/token").mock(
        side_effect=[
            httpx.Response(200, json={"access_token": "expired-token"}),
            httpx.Response(200, json={"access_token": "fresh-token"}),
        ]
    )
    account_route = respx.get("https://api.tastyworks.com/customers/me/accounts").mock(
        side_effect=[
            httpx.Response(401, json={"error": {"code": "unauthorized"}}),
            httpx.Response(200, json={"data": {"items": []}}),
        ]
    )

    client.list_accounts()

    assert token_route.call_count == 2
    assert account_route.call_count == 2
    assert account_route.calls[1].request.headers["Authorization"] == "Bearer fresh-token"


@respx.mock
def test_named_read_method_raises_redacted_api_error(client):
    respx.post("https://api.tastyworks.com/oauth/token").mock(
        return_value=httpx.Response(401, json={"error": {"message": "grant rejected"}})
    )

    with pytest.raises(TastytradeAPIError, match="grant rejected"):
        client.list_accounts()


@respx.mock
def test_named_read_methods_use_configured_account_and_documented_query_params(client):
    respx.post("https://api.tastyworks.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token"})
    )
    balances_route = respx.get("https://api.tastyworks.com/accounts/5WT00001/balances").mock(
        return_value=httpx.Response(200, json={"data": {"net-liquidating-value": "1000"}})
    )
    orders_route = respx.get("https://api.tastyworks.com/accounts/5WT00001/orders").mock(
        return_value=httpx.Response(200, json={"data": {"items": []}})
    )
    transactions_route = respx.get("https://api.tastyworks.com/accounts/5WT00001/transactions").mock(
        return_value=httpx.Response(200, json={"data": {"items": []}})
    )

    assert client.get_balances()["net-liquidating-value"] == "1000"
    assert client.search_orders("2026-07-30", "2026-07-30") == []
    assert client.get_trade_transactions("2026-07-30", "2026-07-30") == []

    assert balances_route.called
    assert dict(orders_route.calls[0].request.url.params) == {
        "start-date": "2026-07-30",
        "end-date": "2026-07-30",
        "per-page": "100",
    }
    assert dict(transactions_route.calls[0].request.url.params) == {
        "start-date": "2026-07-30",
        "end-date": "2026-07-30",
        "type": "Trade",
        "per-page": "250",
    }


@respx.mock
def test_chain_quote_and_dxlink_token_methods_parse_data_items(client):
    respx.post("https://api.tastyworks.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token"})
    )
    respx.get("https://api.tastyworks.com/option-chains/XSP/nested").mock(
        return_value=httpx.Response(200, json={"data": {"items": [{"underlying-symbol": "XSP"}]}})
    )
    quotes_route = respx.get("https://api.tastyworks.com/market-data/by-type").mock(
        return_value=httpx.Response(200, json={"data": {"items": [{"symbol": "XSP"}]}})
    )
    respx.get("https://api.tastyworks.com/api-quote-tokens").mock(
        return_value=httpx.Response(200, json={"data": {"token": "quote-token", "dxlink-url": "wss://dx"}})
    )

    assert client.get_nested_option_chain("XSP") == [{"underlying-symbol": "XSP"}]
    assert client.get_quotes("index", ["XSP"]) == [{"symbol": "XSP"}]
    assert client.get_api_quote_token()["dxlink-url"] == "wss://dx"
    assert dict(quotes_route.calls[0].request.url.params) == {"index": "XSP"}


def test_get_quotes_rejects_unknown_instrument_type(client):
    with pytest.raises(ValueError, match="Unsupported Tastytrade quote instrument type"):
        client.get_quotes("option", ["XSP"])


@respx.mock
def test_instrument_list_methods_return_streamer_symbol_items(client):
    respx.post("https://api.tastyworks.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token"})
    )
    respx.get("https://api.tastyworks.com/instruments/cryptocurrencies").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"items": [{"symbol": "BTC/USD", "streamer-symbol": "BTC/USD:CXTALP"}]}},
        )
    )
    respx.get("https://api.tastyworks.com/instruments/futures").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"items": [{"symbol": "/ESU6", "streamer-symbol": "/ESU26:XCME"}]}},
        )
    )

    assert client.list_cryptocurrencies()[0]["streamer-symbol"] == "BTC/USD:CXTALP"
    assert client.list_futures()[0]["streamer-symbol"] == "/ESU26:XCME"


@respx.mock
def test_order_mutation_methods_use_documented_account_endpoints(client):
    respx.post("https://api.tastyworks.com/oauth/token").mock(
        return_value=httpx.Response(200, json={"access_token": "token"})
    )
    dry_run_route = respx.post(
        "https://api.tastyworks.com/accounts/5WT00001/orders/dry-run"
    ).mock(return_value=httpx.Response(200, json={"data": {"warnings": []}}))
    submit_route = respx.post("https://api.tastyworks.com/accounts/5WT00001/orders").mock(
        return_value=httpx.Response(201, json={"data": {"order": {"id": 42}}})
    )
    cancel_route = respx.delete("https://api.tastyworks.com/accounts/5WT00001/orders/42").mock(
        return_value=httpx.Response(200, json={"data": {"id": 42, "status": "Cancel Requested"}})
    )
    order = {
        "time-in-force": "Day",
        "order-type": "Limit",
        "price": "0.05",
        "price-effect": "Credit",
        "legs": [],
    }

    assert client.dry_run_order(order) == {"warnings": []}
    assert client.submit_order(order) == {"order": {"id": 42}}
    assert client.cancel_order("42") == {"id": 42, "status": "Cancel Requested"}
    assert json.loads(dry_run_route.calls[0].request.content) == order
    assert submit_route.calls[0].request.headers["Authorization"] == "Bearer token"
    assert cancel_route.called