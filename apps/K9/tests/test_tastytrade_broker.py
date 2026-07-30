from __future__ import annotations

from datetime import date

import pytest

from bic.models import ORDER_STATUS_FILLED, ORDER_STATUS_OPEN, OrderRequest
from K9.tastytrade.broker import TastytradeBroker, TradingDisabledError
from K9.tastytrade.dxlink import DxLinkSnapshot
from K9.tastytrade.settings import TastytradeSettings


class FakeClient:
    def get_balances(self):
        return {
            "net-liquidating-value": "10000.50",
            "cash-available-to-withdraw": "5000.25",
            "derivative-buying-power": "4000.00",
        }

    def get_positions(self):
        return [
            {
                "symbol": "XSP   260730P00600000",
                "quantity": "1",
                "quantity-direction": "Short",
                "average-open-price": "1.25",
                "instrument-type": "Equity Option",
            }
        ]

    def search_orders(self, start_date, end_date):
        del start_date, end_date
        return [
            {"id": 1, "status": "Live", "remaining-quantity": "1", "source": "K9:prod:abc"},
            {"id": 2, "status": "Filled", "remaining-quantity": "0", "price": "1.10"},
        ]

    def get_order(self, order_id):
        return {"id": order_id, "status": "Filled", "remaining-quantity": "0", "price": "1.10"}

    def get_quotes(self, instrument_type, symbols):
        assert instrument_type == "index"
        assert symbols == ["XSP"]
        return [{"symbol": "XSP", "bid": "600.0", "ask": "600.2", "last": "600.1"}]

    def get_nested_option_chain(self, underlying):
        assert underlying == "XSP"
        return [
            {
                "expirations": [
                    {
                        "expiration-date": "2026-07-30",
                        "strikes": [
                            {
                                "strike-price": "600.0",
                                "call": "XSP   260730C00600000",
                                "call-streamer-symbol": ".XSP260730C600",
                                "put": "XSP   260730P00600000",
                                "put-streamer-symbol": ".XSP260730P600",
                            }
                        ],
                    }
                ]
            }
        ]

    def get_api_quote_token(self):
        return {"token": "quote-token", "dxlink-url": "wss://dxlink.example"}

    def get_balance_snapshots(self):
        return [{"snapshot-date": "2026-07-29", "net-liquidating-value": "9999.50"}]


class FakeCollector:
    def __init__(self, url, token):
        assert url == "wss://dxlink.example"
        assert token == "quote-token"

    def collect(self, symbols):
        return {
            symbol: DxLinkSnapshot(
                symbol=symbol,
                bid=1.0,
                ask=1.1,
                delta=-0.2 if symbol.endswith("P600") else 0.2,
                gamma=0.01,
                theta=-0.02,
                rho=-0.01,
                vega=0.03,
                volatility=0.18,
            )
            for symbol in symbols
        }


@pytest.fixture
def broker() -> TastytradeBroker:
    settings = TastytradeSettings(
        app_name="k9-diagnostic",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        account_number="5WT00001",
        environment="tastytrade_production",
        base_url="https://api.tastyworks.com",
    )
    return TastytradeBroker(settings, client=FakeClient(), dxlink_collector_factory=FakeCollector)


def test_read_methods_map_balances_positions_and_orders(broker):
    account = broker.get_account()
    positions = broker.get_positions()
    open_orders = broker.get_open_orders()
    filled_order = broker.get_order("2")

    assert account.net_liquidation == 10000.50
    assert account.buying_power == 4000.00
    assert positions[0].quantity == -1
    assert positions[0].position_type == "EQUITY OPTION"
    assert open_orders[0].status == ORDER_STATUS_OPEN
    assert open_orders[0].tag == "K9:prod:abc"
    assert filled_order.status == ORDER_STATUS_FILLED
    assert filled_order.filled_price == 1.10


def test_option_chain_retains_tastytrade_symbols_and_dxlink_greeks(broker):
    chain = broker.get_option_chain("XSP", date(2026, 7, 30))

    assert len(chain.options) == 2
    put = next(contract for contract in chain.options if contract.option_type == "PUT")
    assert put.broker_symbol == "XSP   260730P00600000"
    assert put.streamer_symbol == ".XSP260730P600"
    assert put.bid == 1.0
    assert put.delta == -0.2


def test_mutating_methods_are_blocked_before_network_access(broker):
    with pytest.raises(TradingDisabledError, match="order placement is disabled"):
        broker.place_order(OrderRequest(symbol="XSP", strategy_type="PUT_CREDIT_SPREAD"))
    with pytest.raises(TradingDisabledError, match="order cancellation is disabled"):
        broker.cancel_order("123")


def test_underlying_quote_and_balance_history_map_read_data(broker):
    quote = broker.get_underlying_quote("XSP")
    balances = broker.get_historical_balances()

    assert quote.last == 600.1
    assert quote.bid < quote.ask
    assert balances[0].date == "2026-07-29"
    assert balances[0].value == 9999.50