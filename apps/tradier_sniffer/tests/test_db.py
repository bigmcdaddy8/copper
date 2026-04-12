import sqlite3

import pytest

from tradier_sniffer.db import (
    append_event,
    get_open_trades,
    get_order,
    get_orders_for_trade,
    get_poll_state,
    get_recent_events,
    get_trade,
    init_db,
    insert_trade,
    insert_trade_order_map,
    next_trade_sequence,
    set_poll_state,
    update_trade_status,
    upsert_order,
)
from tradier_sniffer.models import (
    EventLog,
    EventType,
    Order,
    OrderLeg,
    OrderStatus,
    Trade,
    TradeOrderMap,
    TradeStatus,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def _make_order(**kwargs) -> Order:
    defaults = dict(
        order_id="O001",
        account_id="ACC1",
        symbol="SPX",
        class_="option",
        order_type="limit",
        side="sell_to_open",
        quantity=1,
        status=OrderStatus.open,
        duration="day",
        created_at="2024-01-15T14:00:00Z",
    )
    defaults.update(kwargs)
    return Order(**defaults)


def _make_trade(**kwargs) -> Trade:
    defaults = dict(
        trade_id="TRDS_00001_NPUT",
        trade_type="NPUT",
        underlying="SPX",
        opened_at="2024-01-15T14:00:00Z",
    )
    defaults.update(kwargs)
    return Trade(**defaults)


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_init_creates_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"trades", "orders", "trade_order_map", "event_log", "poll_state"} <= names


def test_init_is_idempotent():
    c = init_db(":memory:")
    init_db(":memory:")  # second call on a fresh in-memory db — should not raise
    c.close()


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def test_upsert_order_insert(conn):
    order = _make_order(limit_price=1.50)
    upsert_order(conn, order)
    result = get_order(conn, "O001")
    assert result is not None
    assert result.order_id == "O001"
    assert result.limit_price == 1.50
    assert result.status == OrderStatus.open


def test_upsert_order_update(conn):
    upsert_order(conn, _make_order())
    upsert_order(conn, _make_order(status=OrderStatus.filled, fill_price=1.48, fill_quantity=1))
    result = get_order(conn, "O001")
    assert result.status == OrderStatus.filled
    assert result.fill_price == 1.48


def test_upsert_order_multileg_legs(conn):
    legs = [
        OrderLeg("SPX240119P04500000", "sell_to_open", 1),
        OrderLeg("SPX240119P04400000", "buy_to_open", 1),
    ]
    order = _make_order(order_id="O002", class_="multileg", legs=legs)
    upsert_order(conn, order)
    result = get_order(conn, "O002")
    assert len(result.legs) == 2
    assert result.legs[0].option_symbol == "SPX240119P04500000"
    assert result.legs[1].side == "buy_to_open"


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def test_insert_trade(conn):
    insert_trade(conn, _make_trade())
    result = get_trade(conn, "TRDS_00001_NPUT")
    assert result is not None
    assert result.trade_id == "TRDS_00001_NPUT"
    assert result.status == TradeStatus.open
    assert result.closed_at is None


def test_insert_trade_duplicate_raises(conn):
    insert_trade(conn, _make_trade())
    with pytest.raises(sqlite3.IntegrityError):
        insert_trade(conn, _make_trade())


def test_update_trade_status_closed(conn):
    insert_trade(conn, _make_trade())
    update_trade_status(conn, "TRDS_00001_NPUT", TradeStatus.closed, "2024-01-15T16:00:00Z")
    result = get_trade(conn, "TRDS_00001_NPUT")
    assert result.status == TradeStatus.closed
    assert result.closed_at == "2024-01-15T16:00:00Z"


def test_get_open_trades(conn):
    insert_trade(conn, _make_trade(trade_id="TRDS_00001_NPUT"))
    insert_trade(conn, _make_trade(trade_id="TRDS_00002_PCS"))
    insert_trade(conn, _make_trade(trade_id="TRDS_00003_SIC"))
    update_trade_status(conn, "TRDS_00003_SIC", TradeStatus.closed, "2024-01-15T16:00:00Z")
    open_trades = get_open_trades(conn)
    assert len(open_trades) == 2
    ids = {t.trade_id for t in open_trades}
    assert "TRDS_00003_SIC" not in ids


# ---------------------------------------------------------------------------
# Trade–Order mapping
# ---------------------------------------------------------------------------


def test_insert_trade_order_map(conn):
    insert_trade(conn, _make_trade())
    upsert_order(conn, _make_order())
    mapping = TradeOrderMap("TRDS_00001_NPUT", "O001", "entry", "2024-01-15T14:00:00Z")
    insert_trade_order_map(conn, mapping)
    orders = get_orders_for_trade(conn, "TRDS_00001_NPUT")
    assert len(orders) == 1
    assert orders[0].order_id == "O001"


def test_insert_trade_order_map_duplicate_ignored(conn):
    insert_trade(conn, _make_trade())
    upsert_order(conn, _make_order())
    mapping = TradeOrderMap("TRDS_00001_NPUT", "O001", "entry", "2024-01-15T14:00:00Z")
    insert_trade_order_map(conn, mapping)
    insert_trade_order_map(conn, mapping)  # should not raise
    orders = get_orders_for_trade(conn, "TRDS_00001_NPUT")
    assert len(orders) == 1


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


def test_append_event_returns_id(conn):
    evt = EventLog(timestamp="2024-01-15T14:00:00Z", event_type=EventType.new_order, order_id="O001")
    event_id = append_event(conn, evt)
    assert isinstance(event_id, int)
    assert event_id >= 1


def test_get_recent_events(conn):
    for i, et in enumerate([EventType.new_order, EventType.filled, EventType.closed]):
        append_event(conn, EventLog(timestamp=f"2024-01-15T14:0{i}:00Z", event_type=et))
    events = get_recent_events(conn, limit=2)
    assert len(events) == 2
    assert events[0].event_type == EventType.closed   # newest first


# ---------------------------------------------------------------------------
# Poll state
# ---------------------------------------------------------------------------


def test_get_poll_state_initial(conn):
    state = get_poll_state(conn)
    assert state["last_poll_at"] == ""
    assert state["trade_sequence"] == "0"


def test_set_poll_state(conn):
    set_poll_state(conn, "last_poll_at", "2024-01-15T14:30:00Z")
    state = get_poll_state(conn)
    assert state["last_poll_at"] == "2024-01-15T14:30:00Z"


def test_next_trade_sequence(conn):
    assert next_trade_sequence(conn) == 1
    assert next_trade_sequence(conn) == 2
    assert next_trade_sequence(conn) == 3
