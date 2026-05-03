from datetime import date, datetime
from bic.models import (
    AccountSnapshot, OHLCVBar, Order, OrderLeg, OrderRequest, OrderResponse,
    OptionChain, OptionContract, Position, Quote,
    ORDER_STATUS_OPEN, ORDER_STATUS_PENDING, ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIALLY_FILLED, ORDER_STATUS_CANCELED, ORDER_STATUS_REJECTED,
    ORDER_STATUS_EXPIRED, ORDER_STATUS_PENDING_CANCEL,
    ORDER_ACTIVE_STATUSES, ORDER_FILL_STATUSES, ORDER_DONE_STATUSES,
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
    assert req.duration == "day"
    assert req.tag is None


def test_order_request_with_tag_and_gtc():
    req = OrderRequest("SPX", "IRON_CONDOR_TP", duration="gtc", tag="TRD-0001")
    assert req.duration == "gtc"
    assert req.tag == "TRD-0001"


def test_order_response_accepted():
    r = OrderResponse("HD-000001", "ACCEPTED")
    assert r.status == "ACCEPTED"
    assert r.rejection_reason is None
    assert r.rejection_text is None


def test_order_response_rejected_with_reason():
    r = OrderResponse("", "REJECTED",
                      rejection_reason="insufficient_buying_power",
                      rejection_text="Account buying power too low")
    assert r.status == "REJECTED"
    assert r.rejection_reason == "insufficient_buying_power"
    assert r.rejection_text == "Account buying power too low"


def test_order_filled_price_default_none():
    o = Order("HD-000001", ORDER_STATUS_OPEN)
    assert o.filled_price is None
    assert o.status == ORDER_STATUS_OPEN
    assert o.tag is None
    assert o.raw_status is None


def test_order_with_tag_and_raw_status():
    o = Order("42", ORDER_STATUS_FILLED,
              filled_price=1.25, tag="TRD-0001", raw_status="filled")
    assert o.tag == "TRD-0001"
    assert o.raw_status == "filled"


def test_order_status_constants_are_strings():
    assert ORDER_STATUS_OPEN == "OPEN"
    assert ORDER_STATUS_PENDING == "PENDING"
    assert ORDER_STATUS_FILLED == "FILLED"
    assert ORDER_STATUS_PARTIALLY_FILLED == "PARTIALLY_FILLED"
    assert ORDER_STATUS_CANCELED == "CANCELED"
    assert ORDER_STATUS_REJECTED == "REJECTED"
    assert ORDER_STATUS_EXPIRED == "EXPIRED"
    assert ORDER_STATUS_PENDING_CANCEL == "PENDING_CANCEL"


def test_order_status_set_membership():
    assert ORDER_STATUS_OPEN in ORDER_ACTIVE_STATUSES
    assert ORDER_STATUS_PENDING in ORDER_ACTIVE_STATUSES
    assert ORDER_STATUS_PENDING_CANCEL in ORDER_ACTIVE_STATUSES
    assert ORDER_STATUS_FILLED in ORDER_FILL_STATUSES
    assert ORDER_STATUS_PARTIALLY_FILLED in ORDER_FILL_STATUSES
    assert ORDER_STATUS_CANCELED in ORDER_DONE_STATUSES
    assert ORDER_STATUS_REJECTED in ORDER_DONE_STATUSES
    assert ORDER_STATUS_EXPIRED in ORDER_DONE_STATUSES
    # No overlap between active, fill, and done
    assert not (ORDER_ACTIVE_STATUSES & ORDER_FILL_STATUSES)
    assert not (ORDER_ACTIVE_STATUSES & ORDER_DONE_STATUSES)
    assert not (ORDER_FILL_STATUSES & ORDER_DONE_STATUSES)


def test_ohlcv_bar():
    ts = datetime(2026, 1, 2, 9, 30)
    bar = OHLCVBar("SPX", ts, open=5820.0, high=5850.0, low=5810.0, close=5842.0)
    assert bar.symbol == "SPX"
    assert bar.high >= bar.low
    assert bar.volume == 0  # default
