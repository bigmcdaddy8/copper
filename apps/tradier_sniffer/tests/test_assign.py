"""Unit tests for assign.py — trade # assignment logic."""

from __future__ import annotations

import pytest

from tradier_sniffer.assign import assign_trade, build_trade_id, infer_trade_type
from tradier_sniffer.db import get_orders_for_trade, init_db, upsert_order
from tradier_sniffer.models import Order, OrderLeg, OrderStatus, TradeType


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def _opt_order(
    order_id: str = "O001",
    symbol: str = "SPX",
    side: str = "sell_to_open",
    option_symbol: str = "SPX240119P04500000",
    legs: list | None = None,
    tag: str | None = None,
    created_at: str = "2024-01-15T14:00:00Z",
) -> Order:
    return Order(
        order_id=order_id,
        account_id="ACC1",
        symbol=symbol,
        class_="option" if not legs else "multileg",
        order_type="limit",
        side=side,
        quantity=1,
        status=OrderStatus.filled,
        duration="day",
        option_symbol=option_symbol if not legs else None,
        legs=legs or [],
        tag=tag,
        created_at=created_at,
    )


def _put_leg(sym: str, side: str = "sell_to_open") -> OrderLeg:
    return OrderLeg(option_symbol=sym, side=side, quantity=1)


def _call_leg(sym: str, side: str = "sell_to_open") -> OrderLeg:
    return OrderLeg(option_symbol=sym, side=side, quantity=1)


# ---------------------------------------------------------------------------
# build_trade_id
# ---------------------------------------------------------------------------


def test_build_trade_id():
    assert build_trade_id(1, TradeType.NPUT) == "TRDS_00001_NPUT"


def test_build_trade_id_large_seq():
    assert build_trade_id(99999, TradeType.NPUT) == "TRDS_99999_NPUT"
    assert build_trade_id(100000, TradeType.SIC) == "TRDS_100000_SIC"  # no truncation


# ---------------------------------------------------------------------------
# infer_trade_type
# ---------------------------------------------------------------------------


def test_infer_trade_type_nput():
    order = _opt_order(side="sell_to_open", option_symbol="SPX240119P04500000")
    assert infer_trade_type(order) == TradeType.NPUT


def test_infer_trade_type_ncall():
    order = _opt_order(side="sell_to_open", option_symbol="SPX240119C04500000")
    assert infer_trade_type(order) == TradeType.NCALL


def test_infer_trade_type_stock():
    order = Order(
        order_id="O001", account_id="ACC1", symbol="AAPL",
        class_="equity", order_type="limit", side="buy_to_open",
        quantity=100, status=OrderStatus.filled, duration="day",
    )
    assert infer_trade_type(order) == TradeType.STOCK


def test_infer_trade_type_pcs():
    legs = [
        _put_leg("SPX240119P04500000", "sell_to_open"),
        _put_leg("SPX240119P04400000", "buy_to_open"),
    ]
    order = _opt_order(legs=legs)
    assert infer_trade_type(order) == TradeType.PCS


def test_infer_trade_type_ccs():
    legs = [
        _call_leg("SPX240119C04600000", "sell_to_open"),
        _call_leg("SPX240119C04700000", "buy_to_open"),
    ]
    order = _opt_order(legs=legs)
    assert infer_trade_type(order) == TradeType.CCS


def test_infer_trade_type_sic():
    legs = [
        _put_leg("SPX240119P04500000", "sell_to_open"),
        _put_leg("SPX240119P04400000", "buy_to_open"),
        _call_leg("SPX240119C04600000", "sell_to_open"),
        _call_leg("SPX240119C04700000", "buy_to_open"),
    ]
    order = _opt_order(legs=legs)
    assert infer_trade_type(order) == TradeType.SIC


# ---------------------------------------------------------------------------
# assign_trade
# ---------------------------------------------------------------------------


def test_assign_trade_creates_new(conn):
    order = _opt_order()
    upsert_order(conn, order)
    trade = assign_trade(conn, order)
    assert trade.trade_id.startswith("TRDS_")
    assert trade.trade_id.endswith("_NPUT")
    orders = get_orders_for_trade(conn, trade.trade_id)
    assert any(o.order_id == "O001" for o in orders)


def test_assign_trade_returns_same_for_tag_match(conn):
    # First order creates the trade
    o1 = _opt_order(order_id="O001", tag="NPUT")
    upsert_order(conn, o1)
    trade1 = assign_trade(conn, o1)

    # Second order with same tag finds the same trade
    o2 = _opt_order(order_id="O002", tag="NPUT")
    upsert_order(conn, o2)
    trade2 = assign_trade(conn, o2, role="tp")

    assert trade1.trade_id == trade2.trade_id


def test_assign_trade_returns_same_for_proximity(conn):
    # Same symbol, created_at within 5 seconds
    o1 = _opt_order(order_id="O001", created_at="2024-01-15T14:00:00Z")
    upsert_order(conn, o1)
    trade1 = assign_trade(conn, o1)

    o2 = _opt_order(order_id="O002", created_at="2024-01-15T14:00:03Z")
    upsert_order(conn, o2)
    trade2 = assign_trade(conn, o2)

    assert trade1.trade_id == trade2.trade_id


def test_assign_trade_new_when_proximity_expired(conn):
    o1 = _opt_order(order_id="O001", created_at="2024-01-15T14:00:00Z")
    upsert_order(conn, o1)
    trade1 = assign_trade(conn, o1)

    o2 = _opt_order(order_id="O002", created_at="2024-01-15T14:00:10Z")
    upsert_order(conn, o2)
    trade2 = assign_trade(conn, o2)

    assert trade1.trade_id != trade2.trade_id


def test_assign_trade_duplicate_map_ignored(conn):
    order = _opt_order()
    upsert_order(conn, order)
    trade1 = assign_trade(conn, order)
    trade2 = assign_trade(conn, order)  # second call — should not raise or duplicate

    assert trade1.trade_id == trade2.trade_id
    orders = get_orders_for_trade(conn, trade1.trade_id)
    assert len(orders) == 1  # only one mapping entry
