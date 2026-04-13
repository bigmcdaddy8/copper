"""Tests for TradierBroker (K9-0020 / K9-0030).

Uses respx to mock httpx calls — no live network required.
"""
from __future__ import annotations

import pytest
import respx
import httpx
from datetime import date, datetime
from K9.tradier.broker import TradierBroker, _SANDBOX_BASE

FAKE_KEY = "test-api-key"
FAKE_ACCT = "test-account-id"


@pytest.fixture
def broker():
    return TradierBroker(api_key=FAKE_KEY, account_id=FAKE_ACCT, sandbox=True)


# ------------------------------------------------------------------ #
# get_current_time                                                    #
# ------------------------------------------------------------------ #

def test_get_current_time_returns_aware_datetime(broker):
    t = broker.get_current_time()
    assert isinstance(t, datetime)
    assert t.tzinfo is not None


# ------------------------------------------------------------------ #
# get_underlying_quote                                                #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_underlying_quote(broker):
    respx.get(f"{_SANDBOX_BASE}/markets/quotes").mock(
        return_value=httpx.Response(
            200,
            json={
                "quotes": {
                    "quote": {
                        "symbol": "SPX",
                        "last": 5820.50,
                        "bid": 5820.00,
                        "ask": 5821.00,
                    }
                }
            },
        )
    )
    quote = broker.get_underlying_quote("SPX")
    assert quote.symbol == "SPX"
    assert quote.last == 5820.50
    assert quote.bid < quote.last < quote.ask


# ------------------------------------------------------------------ #
# get_option_chain                                                    #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_option_chain_returns_contracts(broker):
    expiry = date(2026, 1, 5)
    respx.get(f"{_SANDBOX_BASE}/markets/options/chains").mock(
        return_value=httpx.Response(
            200,
            json={
                "options": {
                    "option": [
                        {
                            "strike": 5800.0,
                            "option_type": "put",
                            "bid": 1.20,
                            "ask": 1.35,
                            "greeks": {"delta": -0.20},
                        },
                        {
                            "strike": 5840.0,
                            "option_type": "call",
                            "bid": 0.95,
                            "ask": 1.10,
                            "greeks": {"delta": 0.18},
                        },
                    ]
                }
            },
        )
    )
    chain = broker.get_option_chain("SPX", expiry)
    assert chain.symbol == "SPX"
    assert chain.expiration == expiry
    assert len(chain.options) == 2
    puts = [o for o in chain.options if o.option_type == "PUT"]
    assert puts[0].delta == -0.20


@respx.mock
def test_get_option_chain_null_returns_empty(broker):
    expiry = date(2026, 1, 5)
    respx.get(f"{_SANDBOX_BASE}/markets/options/chains").mock(
        return_value=httpx.Response(200, json={"options": None})
    )
    chain = broker.get_option_chain("SPX", expiry)
    assert chain.options == []


@respx.mock
def test_get_option_chain_missing_greeks(broker):
    expiry = date(2026, 1, 5)
    respx.get(f"{_SANDBOX_BASE}/markets/options/chains").mock(
        return_value=httpx.Response(
            200,
            json={
                "options": {
                    "option": {
                        "strike": 5800.0,
                        "option_type": "put",
                        "bid": 1.20,
                        "ask": 1.35,
                        "greeks": None,
                    }
                }
            },
        )
    )
    chain = broker.get_option_chain("SPX", expiry)
    assert len(chain.options) == 1
    assert chain.options[0].delta == 0.0  # defaults to 0.0 when greeks is None


# ------------------------------------------------------------------ #
# get_account                                                         #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_account(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/balances").mock(
        return_value=httpx.Response(
            200,
            json={
                "balances": {
                    "total_equity": 50000.0,
                    "cash": {"cash_available": 40000.0},
                    "option_buying_power": 35000.0,
                }
            },
        )
    )
    acct = broker.get_account()
    assert acct.account_id == FAKE_ACCT
    assert acct.net_liquidation == 50000.0
    assert acct.buying_power == 35000.0


# ------------------------------------------------------------------ #
# get_positions                                                       #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_positions_empty(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/positions").mock(
        return_value=httpx.Response(200, json={"positions": None})
    )
    assert broker.get_positions() == []


@respx.mock
def test_get_positions_single_item(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/positions").mock(
        return_value=httpx.Response(
            200,
            json={
                "positions": {
                    "position": {
                        "symbol": "SPX260105P05800000",
                        "quantity": -1,
                        "cost_basis": -120.0,
                    }
                }
            },
        )
    )
    positions = broker.get_positions()
    assert len(positions) == 1
    assert positions[0].symbol == "SPX260105P05800000"
    assert positions[0].quantity == -1


# ------------------------------------------------------------------ #
# get_order                                                           #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_order_filled(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "order": {
                    "id": 42,
                    "status": "filled",
                    "avg_fill_price": 1.25,
                    "remaining_quantity": 0,
                }
            },
        )
    )
    order = broker.get_order("42")
    assert order.status == "FILLED"
    assert order.filled_price == 1.25


@respx.mock
def test_get_order_open(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders/99").mock(
        return_value=httpx.Response(
            200,
            json={
                "order": {
                    "id": 99,
                    "status": "open",
                    "avg_fill_price": None,
                    "remaining_quantity": 1,
                }
            },
        )
    )
    order = broker.get_order("99")
    assert order.status == "OPEN"
    assert order.filled_price is None


# ------------------------------------------------------------------ #
# cancel_order                                                        #
# ------------------------------------------------------------------ #

@respx.mock
def test_cancel_order(broker):
    respx.delete(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders/77").mock(
        return_value=httpx.Response(
            200, json={"order": {"id": 77, "status": "canceled"}}
        )
    )
    broker.cancel_order("77")  # should not raise
