from datetime import date, datetime
from bic.models import (
    AccountSnapshot, OHLCVBar, Order, OrderLeg, OrderRequest, OrderResponse,
    OptionChain, OptionContract, Position, Quote,
)


def test_account_snapshot():
    s = AccountSnapshot("acct-1", 100_000.0, 80_000.0, 50_000.0)
    assert s.account_id == "acct-1"
    assert s.buying_power == 50_000.0


def test_position():
    p = Position("SPX", 1, 2.50, "OPTION")
    assert p.position_type == "OPTION"


def test_quote():
    q = Quote("SPX", 5800.0, 5799.95, 5800.05)
    assert q.bid < q.last < q.ask


def test_option_contract_put():
    c = OptionContract(5750.0, "PUT", 1.20, 1.30, -0.20)
    assert c.option_type == "PUT"
    assert c.delta == -0.20


def test_option_chain_defaults_empty():
    chain = OptionChain("SPX", date(2026, 1, 2))
    assert chain.options == []


def test_order_leg_sell():
    leg = OrderLeg("SELL", "PUT", 5750.0, date(2026, 1, 2))
    assert leg.action == "SELL"


def test_order_request_defaults():
    req = OrderRequest("SPX", "IRON_CONDOR")
    assert req.legs == []
    assert req.order_type == "LIMIT"
    assert req.quantity == 1


def test_order_response():
    r = OrderResponse("HD-000001", "ACCEPTED")
    assert r.status == "ACCEPTED"


def test_order_filled_price_default_none():
    o = Order("HD-000001", "OPEN")
    assert o.filled_price is None
    assert o.status == "OPEN"


def test_ohlcv_bar():
    ts = datetime(2026, 1, 2, 9, 30)
    bar = OHLCVBar("SPX", ts, open=5820.0, high=5850.0, low=5810.0, close=5842.0)
    assert bar.symbol == "SPX"
    assert bar.high >= bar.low
    assert bar.volume == 0  # default
