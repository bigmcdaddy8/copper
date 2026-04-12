"""Unit tests for reconcile.py — startup reconciliation logic."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tradier_sniffer.db import get_order, get_recent_events, get_poll_state, init_db, upsert_order
from tradier_sniffer.models import Order, OrderStatus
from tradier_sniffer.reconcile import reconcile


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
        option_symbol="SPX240119P04500000",
        created_at="2024-01-15T14:00:00Z",
    )
    defaults.update(kwargs)
    return Order(**defaults)


def _raw(order_id: str = "O001", status: str = "open", **kwargs) -> dict:
    base = {
        "id": order_id,
        "symbol": "SPX",
        "class": "option",
        "type": "limit",
        "side": "sell_to_open",
        "quantity": 1,
        "status": status,
        "duration": "day",
        "option_symbol": "SPX240119P04500000",
        "create_date": "2024-01-15T14:00:00Z",
    }
    base.update(kwargs)
    return base


def _client(raw_orders: list[dict]) -> MagicMock:
    c = MagicMock()
    c.get_orders.return_value = raw_orders
    return c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reconcile_no_changes(conn):
    upsert_order(conn, _make_order(status=OrderStatus.open))
    result = reconcile(conn, _client([_raw(status="open")]), "ACC1")
    assert result.replayed == 0
    assert result.checked == 1


def test_reconcile_detects_missed_fill(conn):
    upsert_order(conn, _make_order(status=OrderStatus.open))
    result = reconcile(conn, _client([_raw(status="filled", avg_fill_price=1.48, exec_quantity=1)]), "ACC1")
    assert result.replayed == 1
    order = get_order(conn, "O001")
    assert order.status == OrderStatus.filled
    assert order.fill_price == 1.48


def test_reconcile_detects_missed_cancel(conn):
    upsert_order(conn, _make_order(status=OrderStatus.open))
    result = reconcile(conn, _client([_raw(status="canceled")]), "ACC1")
    assert result.replayed == 1
    events = get_recent_events(conn, limit=10)
    assert any(e.event_type.value == "canceled" for e in events)


def test_reconcile_detects_new_order(conn):
    # O001 is not in DB at all
    result = reconcile(conn, _client([_raw(status="open")]), "ACC1")
    assert result.replayed == 1
    order = get_order(conn, "O001")
    assert order is not None


def test_reconcile_assigns_trade_on_fill(conn):
    upsert_order(conn, _make_order(status=OrderStatus.open))
    reconcile(conn, _client([_raw(status="filled", avg_fill_price=1.48, exec_quantity=1)]), "ACC1")
    from tradier_sniffer.db import get_open_trades
    trades = get_open_trades(conn)
    assert len(trades) == 1


def test_reconcile_marks_reconciled_in_details(conn):
    upsert_order(conn, _make_order(status=OrderStatus.open))
    reconcile(conn, _client([_raw(status="filled", avg_fill_price=1.48, exec_quantity=1)]), "ACC1")
    events = get_recent_events(conn, limit=5)
    fill_events = [e for e in events if e.event_type.value == "filled"]
    assert fill_events
    details = json.loads(fill_events[0].details)
    assert details.get("reconciled") is True


def test_reconcile_summary_string(conn):
    result = reconcile(conn, _client([_raw(status="open")]), "ACC1")
    assert result.summary
    assert "1" in result.summary  # checked count appears


def test_reconcile_updates_last_poll_at(conn):
    reconcile(conn, _client([]), "ACC1")
    state = get_poll_state(conn)
    assert state["last_poll_at"] != ""
