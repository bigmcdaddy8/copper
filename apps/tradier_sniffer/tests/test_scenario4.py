"""Unit tests for scenario 4 — entry + adjustment."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradier_sniffer.db import get_open_trades, init_db
from tradier_sniffer.demo import scenario4

_ENTRY_RESULT = {
    "order_id": "O001",
    "credit": 2.00,
    "expiry": "2024-01-19",
    "legs": {
        "short_put":  {"symbol": "SPX240119P04450000", "strike": 4450.0},
        "long_put":   {"symbol": "SPX240119P04440000", "strike": 4440.0},
        "short_call": {"symbol": "SPX240119C04550000", "strike": 4550.0},
        "long_call":  {"symbol": "SPX240119C04560000", "strike": 4560.0},
    },
}

_FILLED_RAW = {
    "id": "O001",
    "symbol": "SPX",
    "class": "multileg",
    "type": "limit",
    "side": "",
    "quantity": 1,
    "status": "filled",
    "duration": "day",
    "avg_fill_price": 2.00,
    "exec_quantity": 1,
    "option_symbol": None,
    "create_date": "2024-01-19T10:00:00Z",
}

_CHAIN = [
    {"symbol": "SPX240119P04450000", "option_type": "put", "strike": 4450.0, "bid": 1.20, "ask": 1.30, "greeks": None},
    {"symbol": "SPX240119P04440000", "option_type": "put", "strike": 4440.0, "bid": 0.30, "ask": 0.40, "greeks": None},
    {"symbol": "SPX240119P04440000", "option_type": "put", "strike": 4440.0, "bid": 0.80, "ask": 0.90, "greeks": None},
    {"symbol": "SPX240119P04430000", "option_type": "put", "strike": 4430.0, "bid": 0.60, "ask": 0.70, "greeks": None},
]


@pytest.fixture
def conn():
    c = init_db(":memory:")
    yield c
    c.close()


def _make_client(order_status: str = "filled") -> MagicMock:
    client = MagicMock()
    client.get_orders.return_value = [{**_FILLED_RAW, "id": "O001", "status": order_status}]
    client.place_multileg_order.return_value = {"order": {"id": "ADJ001", "status": "ok"}}
    client.get_option_chain.return_value = _CHAIN
    return client


@patch("tradier_sniffer.demo.scenario4.time.sleep")
@patch("tradier_sniffer.demo.scenario4.scenario1.run", return_value=_ENTRY_RESULT)
def test_scenario4_links_adjustment_to_trade(mock_run, mock_sleep, conn):
    client = _make_client(order_status="filled")
    result = scenario4.run(client, conn, "ACC1", max_wait_seconds=10)
    assert result["status"] == "adjustment_placed"
    assert result["trade_id"].startswith("TRDS_")
    assert result["adjustment_order_id"] == "ADJ001"
    # Both entry and adjustment are under the same trade
    trades = get_open_trades(conn)
    assert len(trades) == 1


@patch("tradier_sniffer.demo.scenario4.time.sleep")
@patch("tradier_sniffer.demo.scenario4.scenario1.run", return_value=_ENTRY_RESULT)
def test_scenario4_returns_entry_unfilled_when_no_fill(mock_run, mock_sleep, conn):
    client = _make_client(order_status="open")
    result = scenario4.run(client, conn, "ACC1", max_wait_seconds=5)
    assert result["status"] == "entry_unfilled"
    assert "order_id" in result
