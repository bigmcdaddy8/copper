"""Unit tests for engine.py — all I/O is mocked or uses in-memory SQLite."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from tradier_sniffer.db import (
    get_order,
    get_poll_state,
    init_db,
    upsert_order,
)
from tradier_sniffer.engine import _raw_to_order, detect_events, poll
from tradier_sniffer.models import EventType, Order, OrderStatus


# ---------------------------------------------------------------------------
# Fixtures & helpers
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


def _no_known(order_id: str) -> Order | None:
    return None


def _known_open(order_id: str) -> Order | None:
    return _make_order(order_id=order_id, status=OrderStatus.open)


# ---------------------------------------------------------------------------
# detect_events — pure function tests (no DB / HTTP)
# ---------------------------------------------------------------------------


def test_detect_events_new_order():
    fresh = [_make_order()]
    events = detect_events(fresh, _no_known)
    assert len(events) == 1
    assert events[0][1] == EventType.new_order


def test_detect_events_no_change():
    fresh = [_make_order(status=OrderStatus.open)]
    events = detect_events(fresh, _known_open)
    assert events == []


def test_detect_events_status_filled():
    fresh = [_make_order(status=OrderStatus.filled)]
    events = detect_events(fresh, _known_open)
    assert len(events) == 1
    assert events[0][1] == EventType.filled


def test_detect_events_status_canceled():
    fresh = [_make_order(status=OrderStatus.canceled)]
    events = detect_events(fresh, _known_open)
    assert len(events) == 1
    assert events[0][1] == EventType.canceled


def test_detect_events_status_rejected():
    fresh = [_make_order(status=OrderStatus.rejected)]
    events = detect_events(fresh, _known_open)
    assert len(events) == 1
    assert events[0][1] == EventType.canceled


def test_detect_events_status_expired():
    fresh = [_make_order(status=OrderStatus.expired)]
    events = detect_events(fresh, _known_open)
    assert len(events) == 1
    assert events[0][1] == EventType.canceled


# ---------------------------------------------------------------------------
# poll() — integration with in-memory DB
# ---------------------------------------------------------------------------


def _make_client(raw_orders: list[dict]) -> MagicMock:
    client = MagicMock()
    client.get_orders.return_value = raw_orders
    return client


_SAMPLE_RAW = {
    "id": "O001",
    "symbol": "SPX",
    "class": "option",
    "type": "limit",
    "side": "sell_to_open",
    "quantity": 1,
    "status": "open",
    "duration": "day",
    "price": 1.50,
    "create_date": "2024-01-15T14:00:00Z",
}


def test_poll_persists_new_order(conn):
    client = _make_client([_SAMPLE_RAW])
    events = poll(conn, client, "ACC1")
    assert len(events) == 1
    assert events[0].event_type == EventType.new_order
    order = get_order(conn, "O001")
    assert order is not None
    assert order.symbol == "SPX"


def test_poll_persists_fill_event(conn):
    # Seed DB with open order
    upsert_order(conn, _make_order(order_id="O001", status=OrderStatus.open))

    filled_raw = {**_SAMPLE_RAW, "status": "filled", "avg_fill_price": 1.48, "exec_quantity": 1}
    client = _make_client([filled_raw])
    events = poll(conn, client, "ACC1")

    assert len(events) == 1
    assert events[0].event_type == EventType.filled
    order = get_order(conn, "O001")
    assert order.fill_price == 1.48


def test_poll_updates_last_poll_at(conn):
    client = _make_client([])
    poll(conn, client, "ACC1")
    state = get_poll_state(conn)
    assert state["last_poll_at"] != ""


# ---------------------------------------------------------------------------
# _raw_to_order — defensive conversion
# ---------------------------------------------------------------------------


def test_raw_to_order_missing_fields():
    raw = {"id": "O999", "symbol": "SPX"}
    order = _raw_to_order(raw, "ACC1")
    assert order.order_id == "O999"
    assert order.limit_price is None
    assert order.fill_price is None
    assert order.legs == []
    assert order.status == OrderStatus.pending
