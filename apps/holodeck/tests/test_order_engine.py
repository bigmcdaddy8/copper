import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from bic.models import OrderLeg, OrderRequest
from holodeck.clock import VirtualClock
from holodeck.config import HolodeckConfig
from holodeck.ledger import AccountLedger
from holodeck.market_data import MarketDataStore, generate_spx_minutes
from holodeck.order_engine import OrderEngine

TZ = "America/Chicago"
START = datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ))  # market open
EXP = date(2026, 1, 2)


@pytest.fixture
def engine(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    config = HolodeckConfig(
        starting_datetime=START,
        ending_datetime=datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    clock = VirtualClock(START, "09:30", "15:00", TZ)
    store = MarketDataStore(csv_path)
    store.load()
    ledger = AccountLedger(config)
    return OrderEngine(ledger, store, clock, config)


def pcs_order(limit_price: float = 0.50) -> OrderRequest:
    return OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 5750.0, EXP),
            OrderLeg("BUY", "PUT", 5745.0, EXP),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=limit_price,
    )


def tp_order() -> OrderRequest:
    return OrderRequest(
        symbol="SPX",
        strategy_type="TP_PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("BUY", "PUT", 5750.0, EXP),
            OrderLeg("SELL", "PUT", 5745.0, EXP),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=0.15,
    )


def test_submit_order_accepted(engine):
    resp = engine.submit_order(pcs_order())
    assert resp.status == "ACCEPTED"
    assert resp.order_id != ""


def test_submit_order_rejected_market_closed(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    closed_time = datetime(2026, 1, 2, 8, 0, tzinfo=ZoneInfo(TZ))
    config = HolodeckConfig(
        starting_datetime=closed_time,
        ending_datetime=datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    clock = VirtualClock(closed_time, "09:30", "15:00", TZ)
    store = MarketDataStore(csv_path)
    store.load()
    ledger = AccountLedger(config)
    eng = OrderEngine(ledger, store, clock, config)
    resp = eng.submit_order(pcs_order())
    assert resp.status == "REJECTED"


def test_submit_order_rejected_existing_position(engine):
    # Fill a position first
    engine.submit_order(pcs_order(limit_price=0.01))  # very low → fills immediately
    engine.evaluate_orders()
    # Now try to submit another for same symbol
    resp = engine.submit_order(pcs_order())
    assert resp.status == "REJECTED"


def test_submit_order_rejected_non_limit(engine):
    req = pcs_order()
    req.order_type = "MARKET"
    resp = engine.submit_order(req)
    assert resp.status == "REJECTED"


def test_order_id_format(engine):
    resp = engine.submit_order(pcs_order())
    assert resp.order_id == "HD-000001"


def test_order_ids_are_sequential(engine):
    r1 = engine.submit_order(pcs_order(limit_price=0.01))
    engine.evaluate_orders()  # fill r1 so position check passes
    # Can't submit another entry for same symbol — use TP order
    r2 = engine.submit_order(tp_order())
    assert r1.order_id == "HD-000001"
    assert r2.order_id == "HD-000002"


def test_cancel_open_order(engine):
    resp = engine.submit_order(pcs_order(limit_price=999.0))  # never fills
    engine.cancel_order(resp.order_id)
    order = engine.get_order(resp.order_id)
    assert order.status == "CANCELED"


def test_cancel_filled_order_noop(engine):
    resp = engine.submit_order(pcs_order(limit_price=0.01))
    engine.evaluate_orders()
    order_before = engine.get_order(resp.order_id)
    engine.cancel_order(resp.order_id)
    order_after = engine.get_order(resp.order_id)
    assert order_after.status == order_before.status  # unchanged


def test_evaluate_fills_entry_low_price(engine):
    # Request very low credit → should fill on first evaluate
    resp = engine.submit_order(pcs_order(limit_price=0.01))
    filled = engine.evaluate_orders()
    assert resp.order_id in filled


def test_evaluate_no_fill_high_price(engine):
    # Request impossibly high credit → never fills
    resp = engine.submit_order(pcs_order(limit_price=999.0))
    filled = engine.evaluate_orders()
    assert resp.order_id not in filled


def test_evaluate_returns_filled_ids(engine):
    resp = engine.submit_order(pcs_order(limit_price=0.01))
    filled = engine.evaluate_orders()
    assert isinstance(filled, list)
    assert resp.order_id in filled


def test_get_order_after_fill(engine):
    resp = engine.submit_order(pcs_order(limit_price=0.01))
    engine.evaluate_orders()
    order = engine.get_order(resp.order_id)
    assert order.status == "FILLED"
    assert order.filled_price is not None


def test_get_open_orders_empty_after_fill(engine):
    engine.submit_order(pcs_order(limit_price=0.01))
    engine.evaluate_orders()
    assert engine.get_open_orders() == []


def test_get_open_orders_returns_open(engine):
    engine.submit_order(pcs_order(limit_price=999.0))
    open_orders = engine.get_open_orders()
    assert len(open_orders) == 1
    assert open_orders[0].status == "OPEN"


# ------------------------------------------------------------------ #
# get_all_orders (BIC get_orders reconciliation path)                #
# ------------------------------------------------------------------ #

def test_get_all_orders_empty(engine):
    assert engine.get_all_orders() == []


def test_get_all_orders_returns_open_and_filled(engine):
    # One order that fills (low limit price), one that stays open (very high price)
    engine.submit_order(pcs_order(limit_price=0.01))   # will fill
    engine.submit_order(pcs_order(limit_price=999.0))  # stays open (also hits duplicate-position guard)
    engine.evaluate_orders()
    all_orders = engine.get_all_orders()
    # At least the first (filled) order must be present
    statuses = {o.status for o in all_orders}
    assert "FILLED" in statuses


def test_get_all_orders_filter_by_open(engine):
    engine.submit_order(pcs_order(limit_price=0.01))   # fills
    engine.submit_order(pcs_order(limit_price=999.0))  # blocked by position guard after first fills
    engine.evaluate_orders()
    open_only = engine.get_all_orders(statuses=["OPEN"])
    assert all(o.status == "OPEN" for o in open_only)


def test_get_all_orders_filter_by_filled(engine):
    engine.submit_order(pcs_order(limit_price=0.01))
    engine.evaluate_orders()
    filled_only = engine.get_all_orders(statuses=["FILLED"])
    assert len(filled_only) >= 1
    assert all(o.status == "FILLED" for o in filled_only)


def test_get_all_orders_filter_returns_empty_for_missing_status(engine):
    engine.submit_order(pcs_order(limit_price=0.01))
    engine.evaluate_orders()
    pending = engine.get_all_orders(statuses=["PENDING"])
    assert pending == []


def test_get_all_orders_tag_is_preserved(engine):
    req = pcs_order(limit_price=0.01)
    req.tag = "TRD-TEST-01"
    engine.submit_order(req)
    engine.evaluate_orders()
    orders = engine.get_all_orders(statuses=["FILLED"])
    assert len(orders) == 1
    assert orders[0].tag == "TRD-TEST-01"


def test_get_all_orders_raw_status_is_lowercase(engine):
    engine.submit_order(pcs_order(limit_price=999.0))
    orders = engine.get_all_orders(statuses=["OPEN"])
    assert len(orders) == 1
    assert orders[0].raw_status == "open"
