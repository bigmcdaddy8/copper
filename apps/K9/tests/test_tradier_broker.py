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


@respx.mock
def test_get_underlying_quote_null_last_uses_midpoint(broker):
    respx.get(f"{_SANDBOX_BASE}/markets/quotes").mock(
        return_value=httpx.Response(
            200,
            json={
                "quotes": {
                    "quote": {
                        "symbol": "XSP",
                        "last": None,
                        "bid": 581.10,
                        "ask": 581.30,
                    }
                }
            },
        )
    )
    quote = broker.get_underlying_quote("XSP")
    assert quote.symbol == "XSP"
    assert quote.bid == 581.10
    assert quote.ask == 581.30
    assert quote.last == pytest.approx(581.20)


@respx.mock
def test_get_underlying_quote_missing_all_prices_raises_value_error(broker):
    respx.get(f"{_SANDBOX_BASE}/markets/quotes").mock(
        return_value=httpx.Response(
            200,
            json={
                "quotes": {
                    "quote": {
                        "symbol": "XSP",
                        "last": None,
                        "bid": None,
                        "ask": None,
                    }
                }
            },
        )
    )
    with pytest.raises(ValueError, match="missing required numeric fields"):
        broker.get_underlying_quote("XSP")


@respx.mock
def test_get_underlying_quote_http_error_includes_fault_detail(broker):
    respx.get(f"{_SANDBOX_BASE}/markets/quotes").mock(
        return_value=httpx.Response(
            400,
            json={"fault": {"faultstring": "account is not approved for this symbol"}},
        )
    )
    with pytest.raises(httpx.HTTPStatusError, match="Tradier response: account is not approved"):
        broker.get_underlying_quote("XSP")


@respx.mock
def test_get_underlying_quote_retries_read_timeout(broker):
    calls = {"n": 0}

    def flaky_quote(request: httpx.Request, **_):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(
            200,
            json={
                "quotes": {
                    "quote": {
                        "symbol": "XSP",
                        "last": 581.2,
                        "bid": 581.1,
                        "ask": 581.3,
                    }
                }
            },
        )

    respx.get(f"{_SANDBOX_BASE}/markets/quotes").mock(side_effect=flaky_quote)
    quote = broker.get_underlying_quote("XSP")
    assert quote.last == 581.2
    assert calls["n"] == 2


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


@respx.mock
def test_get_account_flat_cash_shape(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/balances").mock(
        return_value=httpx.Response(
            200,
            json={
                "balances": {
                    "total_equity": 50000.0,
                    "cash_available": 40000.0,
                    "option_buying_power": 35000.0,
                }
            },
        )
    )
    acct = broker.get_account()
    assert acct.account_id == FAKE_ACCT
    assert acct.net_liquidation == 50000.0
    assert acct.available_funds == 40000.0
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


# ------------------------------------------------------------------ #
# Extended status mapping                                             #
# ------------------------------------------------------------------ #

_STATUS_CASES = [
    ("partially_filled",          "PARTIALLY_FILLED"),
    ("pending",                   "PENDING"),
    ("pending_cancel",            "PENDING_CANCEL"),
    ("rejected",                  "REJECTED"),
    ("expired",                   "EXPIRED"),
    ("partially_filled_canceled", "CANCELED"),
]


@pytest.mark.parametrize("raw_status,expected_bic", _STATUS_CASES)
@respx.mock
def test_get_order_status_mapping(broker, raw_status, expected_bic):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders/55").mock(
        return_value=httpx.Response(
            200,
            json={"order": {"id": 55, "status": raw_status, "remaining_quantity": 0}},
        )
    )
    order = broker.get_order("55")
    assert order.status == expected_bic
    assert order.raw_status == raw_status


# ------------------------------------------------------------------ #
# Rejection reason propagation                                        #
# ------------------------------------------------------------------ #

@respx.mock
def test_place_order_rejected_with_reason(broker):
    from bic.models import OrderLeg
    from datetime import date
    legs = [
        OrderLeg("SELL", "PUT",  5700.0, date(2026, 5, 3)),
        OrderLeg("BUY",  "PUT",  5650.0, date(2026, 5, 3)),
    ]
    respx.post(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "order": {
                    "status": "error",
                    "reason_description": "insufficient_buying_power",
                }
            },
        )
    )
    from bic.models import OrderRequest
    req = OrderRequest("SPX", "PUT_CREDIT_SPREAD", legs=legs, limit_price=0.50)
    resp = broker.place_order(req)
    assert resp.status == "REJECTED"
    assert resp.rejection_reason == "insufficient_buying_power"
    assert resp.rejection_text == "insufficient_buying_power"


@respx.mock
def test_place_order_rejected_unknown_reason(broker):
    from bic.models import OrderLeg, OrderRequest
    from datetime import date
    legs = [OrderLeg("SELL", "PUT", 5700.0, date(2026, 5, 3))]
    respx.post(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(
        return_value=httpx.Response(
            200,
            json={"order": {"status": "error", "reason_description": ""}},
        )
    )
    req = OrderRequest("SPX", "NPUT", legs=legs, limit_price=1.00)
    resp = broker.place_order(req)
    assert resp.status == "REJECTED"
    assert resp.rejection_reason == "unknown"
    assert resp.rejection_text is None


# ------------------------------------------------------------------ #
# Tag round-trip                                                      #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_order_returns_tag(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders/88").mock(
        return_value=httpx.Response(
            200,
            json={
                "order": {
                    "id": 88,
                    "status": "open",
                    "tag": "TRD-0001",
                    "remaining_quantity": 1,
                }
            },
        )
    )
    order = broker.get_order("88")
    assert order.tag == "TRD-0001"


@respx.mock
def test_place_order_sends_tag_and_gtc(broker):
    from bic.models import OrderLeg, OrderRequest
    from datetime import date
    legs = [
        OrderLeg("BUY", "PUT", 5700.0, date(2026, 5, 3)),
        OrderLeg("BUY", "PUT", 5650.0, date(2026, 5, 3)),
    ]
    captured: list[httpx.Request] = []

    def capture(request: httpx.Request, **_):
        captured.append(request)
        return httpx.Response(200, json={"order": {"status": "ok", "id": 1234}})

    respx.post(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(side_effect=capture)

    req = OrderRequest("SPX", "PUT_CREDIT_SPREAD_TP",
                       legs=legs, limit_price=0.20, duration="gtc", tag="TRD-0001")
    resp = broker.place_order(req)
    assert resp.status == "ACCEPTED"
    body = captured[0].content.decode()
    assert "type=debit" in body
    assert "duration=gtc" in body
    assert "tag=TRD-0001" in body


@respx.mock
def test_place_order_sends_credit_type_for_credit_strategy(broker):
    from bic.models import OrderLeg, OrderRequest
    from datetime import date
    legs = [
        OrderLeg("SELL", "PUT", 5700.0, date(2026, 5, 3)),
        OrderLeg("BUY", "PUT", 5650.0, date(2026, 5, 3)),
    ]
    captured: list[httpx.Request] = []

    def capture(request: httpx.Request, **_):
        captured.append(request)
        return httpx.Response(200, json={"order": {"status": "ok", "id": 1235}})

    respx.post(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(side_effect=capture)

    req = OrderRequest("SPX", "PUT_CREDIT_SPREAD", legs=legs, limit_price=0.40)
    resp = broker.place_order(req)
    assert resp.status == "ACCEPTED"
    body = captured[0].content.decode()
    assert "type=credit" in body


# ------------------------------------------------------------------ #
# Form encoding: bracket keys must not be percent-encoded            #
# ------------------------------------------------------------------ #

@respx.mock
def test_place_multileg_form_encoding_preserves_brackets(broker):
    from bic.models import OrderLeg, OrderRequest
    from datetime import date
    legs = [
        OrderLeg("SELL", "PUT",  5700.0, date(2026, 5, 3)),
        OrderLeg("BUY",  "PUT",  5650.0, date(2026, 5, 3)),
        OrderLeg("SELL", "CALL", 5900.0, date(2026, 5, 3)),
        OrderLeg("BUY",  "CALL", 5950.0, date(2026, 5, 3)),
    ]
    captured: list[httpx.Request] = []

    def capture(request: httpx.Request, **_):
        captured.append(request)
        return httpx.Response(200, json={"order": {"status": "ok", "id": 999}})

    respx.post(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(side_effect=capture)

    req = OrderRequest("SPX", "IRON_CONDOR", legs=legs, limit_price=1.00)
    broker.place_order(req)

    body = captured[0].content.decode()
    # Literal brackets must appear in the body; percent-encoded %5B/%5D would break Tradier
    assert "option_symbol[0]=" in body
    assert "option_symbol[1]=" in body
    assert "option_symbol[2]=" in body
    assert "option_symbol[3]=" in body
    assert "SPX260503P05700000" in body
    assert "SPX260503P05650000" in body
    assert "%5B" not in body
    assert "%5D" not in body


# ------------------------------------------------------------------ #
# get_orders (reconciliation)                                        #
# ------------------------------------------------------------------ #

@respx.mock
def test_get_orders_all(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "orders": {
                    "order": [
                        {"id": 1, "status": "open",   "remaining_quantity": 1},
                        {"id": 2, "status": "filled", "avg_fill_price": 1.50, "remaining_quantity": 0},
                        {"id": 3, "status": "canceled","remaining_quantity": 0},
                    ]
                }
            },
        )
    )
    orders = broker.get_orders()
    assert len(orders) == 3
    statuses = {o.status for o in orders}
    assert "OPEN" in statuses
    assert "FILLED" in statuses
    assert "CANCELED" in statuses


@respx.mock
def test_get_orders_filtered(broker):
    respx.get(f"{_SANDBOX_BASE}/accounts/{FAKE_ACCT}/orders").mock(
        return_value=httpx.Response(
            200,
            json={
                "orders": {
                    "order": [
                        {"id": 1, "status": "open",    "remaining_quantity": 1},
                        {"id": 2, "status": "filled",  "avg_fill_price": 1.50, "remaining_quantity": 0},
                        {"id": 3, "status": "pending", "remaining_quantity": 1},
                    ]
                }
            },
        )
    )
    orders = broker.get_orders(statuses=["OPEN", "PENDING"])
    assert len(orders) == 2
    assert all(o.status in ("OPEN", "PENDING") for o in orders)
