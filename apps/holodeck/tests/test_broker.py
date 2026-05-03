import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from bic.broker import Broker
from bic.models import OHLCVBar, OrderLeg, OrderRequest
from holodeck.broker import HolodeckBroker
from holodeck.config import HolodeckConfig
from holodeck.market_data import generate_spx_minutes

TZ = "America/Chicago"
START = datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ))
EXP = date(2026, 1, 2)


@pytest.fixture
def broker(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    config = HolodeckConfig(
        starting_datetime=START,
        ending_datetime=datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    return HolodeckBroker(config)


def pcs_order(limit_price: float = 0.10) -> OrderRequest:
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


def tp_order(limit_price: float = 0.50) -> OrderRequest:
    return OrderRequest(
        symbol="SPX",
        strategy_type="TP_PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("BUY", "PUT", 5750.0, EXP),
            OrderLeg("SELL", "PUT", 5745.0, EXP),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=limit_price,
    )


def test_broker_is_bic_broker(broker):
    assert isinstance(broker, Broker)


def test_broker_instantiates(broker):
    assert broker is not None


def test_get_current_time(broker):
    assert broker.get_current_time() == START


def test_get_account_initial(broker):
    snap = broker.get_account()
    assert snap.net_liquidation == 100_000.0
    assert snap.buying_power == 50_000.0


def test_get_positions_empty(broker):
    assert broker.get_positions() == []


def test_get_underlying_quote_spx(broker):
    quote = broker.get_underlying_quote("SPX")
    assert quote.symbol == "SPX"
    assert quote.last > 0
    assert quote.bid < quote.last < quote.ask


def test_get_underlying_quote_invalid_symbol_raises(broker):
    with pytest.raises(ValueError):
        broker.get_underlying_quote("AAPL")


def test_get_option_chain(broker):
    chain = broker.get_option_chain("SPX", EXP)
    assert chain.symbol == "SPX"
    assert len(chain.options) == 122


def test_place_order_accepted(broker):
    resp = broker.place_order(pcs_order())
    assert resp.status == "ACCEPTED"


def test_advance_time_returns_list(broker):
    filled = broker.advance_time()
    assert isinstance(filled, list)


def test_order_fills_after_advance(broker):
    resp = broker.place_order(pcs_order(limit_price=0.01))
    filled = broker.advance_time()
    assert resp.order_id in filled


def test_cancel_order(broker):
    resp = broker.place_order(pcs_order(limit_price=999.0))
    broker.cancel_order(resp.order_id)
    order = broker.get_order(resp.order_id)
    assert order.status == "CANCELED"


def test_full_lifecycle_entry_and_tp(broker):
    """Place IC entry → fill → place TP → TP fills."""
    # Step 1: Entry order with low credit requirement
    entry_resp = broker.place_order(pcs_order(limit_price=0.01))
    assert entry_resp.status == "ACCEPTED"

    # Step 2: Advance until entry fills (max 60 steps)
    entry_filled = False
    for _ in range(60):
        filled = broker.advance_time()
        if entry_resp.order_id in filled:
            entry_filled = True
            break
    assert entry_filled, "Entry order did not fill within 60 steps"

    # Step 3: Place TP order with high debit limit (easily fills)
    tp_resp = broker.place_order(tp_order(limit_price=999.0))
    assert tp_resp.status == "ACCEPTED"

    # Step 4: Advance until TP fills (max 60 steps)
    tp_filled = False
    for _ in range(60):
        filled = broker.advance_time()
        if tp_resp.order_id in filled:
            tp_filled = True
            break
    assert tp_filled, "TP order did not fill within 60 steps"

    # Final state: no open positions, buying power restored
    assert broker.get_positions() == []


def test_full_lifecycle_expiration(broker):
    """Place entry → fill → advance to close → position expires OTM."""
    entry_resp = broker.place_order(pcs_order(limit_price=0.01))
    assert entry_resp.status == "ACCEPTED"

    # Fill entry
    entry_filled = False
    for _ in range(60):
        filled = broker.advance_time()
        if entry_resp.order_id in filled:
            entry_filled = True
            break
    assert entry_filled

    # Advance to close (triggers expiration)
    broker.advance_to_close()

    # Position should be closed by expiration engine
    assert broker.get_positions() == []


def test_reset_reinitializes(broker):
    broker.place_order(pcs_order(limit_price=0.01))
    broker.advance_time()
    broker.reset()
    assert broker.get_positions() == []
    assert broker.get_current_time() == START


# ------------------------------------------------------------------ #
# get_orders — BIC reconciliation path                               #
# ------------------------------------------------------------------ #

def test_get_orders_empty_initially(broker):
    assert broker.get_orders() == []


def test_get_orders_returns_all_statuses(broker):
    """Place two orders: one fills, one stays open (blocked by position guard)."""
    entry_resp = broker.place_order(pcs_order(limit_price=0.01))
    assert entry_resp.status == "ACCEPTED"

    # Fill the entry
    for _ in range(60):
        filled = broker.advance_time()
        if entry_resp.order_id in filled:
            break

    # After fill, the filled order is visible via get_orders()
    all_orders = broker.get_orders()
    assert len(all_orders) >= 1
    statuses = {o.status for o in all_orders}
    assert "FILLED" in statuses


def test_get_orders_filter_open_only(broker):
    """Open orders appear in get_orders(statuses=['OPEN'])."""
    broker.place_order(pcs_order(limit_price=999.0))  # stays open
    open_orders = broker.get_orders(statuses=["OPEN"])
    assert len(open_orders) == 1
    assert open_orders[0].status == "OPEN"


def test_get_orders_filter_excludes_other_statuses(broker):
    """get_orders(['OPEN']) does not return FILLED orders."""
    entry_resp = broker.place_order(pcs_order(limit_price=0.01))
    for _ in range(60):
        filled = broker.advance_time()
        if entry_resp.order_id in filled:
            break
    open_only = broker.get_orders(statuses=["OPEN"])
    assert all(o.status == "OPEN" for o in open_only)


def test_get_orders_tag_survives_fill(broker):
    """A tag set on submission is present in get_orders() after the order fills."""
    req = pcs_order(limit_price=0.01)
    req.tag = "TRD-INTEG-01"
    entry_resp = broker.place_order(req)
    assert entry_resp.status == "ACCEPTED"

    for _ in range(60):
        filled = broker.advance_time()
        if entry_resp.order_id in filled:
            break

    filled_orders = broker.get_orders(statuses=["FILLED"])
    assert len(filled_orders) == 1
    assert filled_orders[0].tag == "TRD-INTEG-01"


def test_get_orders_reconciliation_lifecycle(broker):
    """Full lifecycle integration: entry → fill → TP → get_orders shows both orders."""
    # Entry
    entry_req = pcs_order(limit_price=0.01)
    entry_req.tag = "TRD-RECON-01"
    entry_resp = broker.place_order(entry_req)
    for _ in range(60):
        if entry_resp.order_id in broker.advance_time():
            break

    # TP placement
    tp_req = tp_order(limit_price=999.0)
    tp_req.tag = "TRD-RECON-01"
    tp_resp = broker.place_order(tp_req)
    for _ in range(60):
        if tp_resp.order_id in broker.advance_time():
            break

    # Both orders should be visible; both should carry the same tag
    all_orders = broker.get_orders()
    assert len(all_orders) == 2
    assert all(o.tag == "TRD-RECON-01" for o in all_orders)

    # After both fill, get_orders(["OPEN"]) returns nothing
    open_orders = broker.get_orders(statuses=["OPEN"])
    assert open_orders == []

    # get_orders(["FILLED"]) returns both
    filled_orders = broker.get_orders(statuses=["FILLED"])
    assert len(filled_orders) == 2


# ---------------------------------------------------------------------------
# get_ohlcv_bars tests
# ---------------------------------------------------------------------------

@pytest.fixture
def full_broker(tmp_path):
    """Broker spanning full January 2026 for OHLCV tests."""
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    config = HolodeckConfig(
        starting_datetime=datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ)),
        ending_datetime=datetime(2026, 1, 30, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    return HolodeckBroker(config)


def test_ohlcv_1m_passthrough(full_broker):
    """1-minute resolution returns one bar per minute bar in range."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1m")
    # 09:30 to 10:00 inclusive = 31 minutes
    assert len(bars) == 31
    assert all(isinstance(b, OHLCVBar) for b in bars)
    assert all(b.high >= b.low for b in bars)


def test_ohlcv_1h_bar_count(full_broker):
    """1-hour resolution on a single trading day gives 6 hourly bars (09:xx–14:xx)."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1h")
    # Hours present: 9, 10, 11, 12, 13, 14 (15:00 falls in hour 15, alone)
    assert len(bars) == 7   # hours 9–15 (15:00 is its own 1-bar hour)
    assert bars[0].timestamp.hour == 9
    assert bars[-1].timestamp.hour == 15


def test_ohlcv_1d_bar_count(full_broker):
    """1-day resolution on first 5 trading days gives 5 bars."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 8, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1d")
    # Jan 2, 5, 6, 7, 8 = 5 trading days
    assert len(bars) == 5
    assert all(b.high >= b.open for b in bars)
    assert all(b.low <= b.open for b in bars)


def test_ohlcv_1w_bar_count_full_month(full_broker):
    """1-week resolution on full January returns ≤5 weekly bars."""
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 30, 15, 0, tzinfo=ZoneInfo(TZ))
    bars = full_broker.get_ohlcv_bars("SPX", start, end, "1w")
    assert 1 <= len(bars) <= 5


def test_ohlcv_invalid_resolution_raises(full_broker):
    start = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
    end = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
    with pytest.raises(ValueError, match="Unknown resolution"):
        full_broker.get_ohlcv_bars("SPX", start, end, "2d")
