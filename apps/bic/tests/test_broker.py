import pytest
import inspect
from datetime import date, datetime
from bic.broker import Broker
from bic.models import (
    AccountSnapshot, OHLCVBar, OptionChain, Order, OrderRequest,
    OrderResponse, Position, Quote,
)


class StubBroker(Broker):
    def get_current_time(self) -> datetime:
        return datetime(2026, 1, 2, 9, 30)

    def get_account(self) -> AccountSnapshot:
        return AccountSnapshot("stub", 0.0, 0.0, 0.0)

    def get_positions(self) -> list[Position]:
        return []

    def get_open_orders(self) -> list[Order]:
        return []

    def get_underlying_quote(self, symbol: str) -> Quote:
        return Quote(symbol, 5800.0, 5799.95, 5800.05)

    def get_option_chain(self, symbol: str, expiration: date) -> OptionChain:
        return OptionChain(symbol, expiration)

    def place_order(self, order: OrderRequest) -> OrderResponse:
        return OrderResponse("stub-001", "ACCEPTED")

    def cancel_order(self, order_id: str) -> None:
        pass

    def get_order(self, order_id: str) -> Order:
        return Order(order_id, "OPEN")

    def get_ohlcv_bars(
        self, symbol: str, start: datetime, end: datetime, resolution: str
    ) -> list[OHLCVBar]:
        return []


def test_stub_broker_instantiates():
    broker = StubBroker()
    assert broker is not None


def test_broker_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        Broker()


def test_all_abstract_methods_present():
    expected = {
        "get_current_time", "get_account", "get_positions", "get_open_orders",
        "get_underlying_quote", "get_option_chain", "get_ohlcv_bars",
        "place_order", "cancel_order", "get_order",
    }
    abstract_methods = {
        name for name, method in inspect.getmembers(Broker, predicate=inspect.isfunction)
        if getattr(method, "__isabstractmethod__", False)
    }
    assert expected == abstract_methods


def test_stub_broker_is_subclass():
    assert issubclass(StubBroker, Broker)


def test_stub_broker_isinstance():
    assert isinstance(StubBroker(), Broker)


def test_stub_broker_get_current_time():
    b = StubBroker()
    t = b.get_current_time()
    assert isinstance(t, datetime)


def test_stub_broker_get_account():
    b = StubBroker()
    snap = b.get_account()
    assert isinstance(snap, AccountSnapshot)


def test_stub_broker_place_order():
    b = StubBroker()
    req = OrderRequest("SPX", "IRON_CONDOR")
    resp = b.place_order(req)
    assert resp.status in ("ACCEPTED", "REJECTED")


def test_stub_broker_get_ohlcv_bars():
    b = StubBroker()
    bars = b.get_ohlcv_bars("SPX", datetime(2026, 1, 2), datetime(2026, 1, 5), "1d")
    assert isinstance(bars, list)
