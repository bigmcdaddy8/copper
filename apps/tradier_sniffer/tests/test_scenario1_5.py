"""Unit tests for scenario 1.5 — reprice-and-reenter logic."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradier_sniffer.demo import scenario1_5


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ENTRY_RESULT = {
    "order_id": "O001",
    "credit": 1.50,
    "expiry": "2024-01-19",
    "legs": {
        "short_put":  {"symbol": "SPX240119P04450000", "strike": 4450.0},
        "long_put":   {"symbol": "SPX240119P04440000", "strike": 4440.0},
        "short_call": {"symbol": "SPX240119C04550000", "strike": 4550.0},
        "long_call":  {"symbol": "SPX240119C04560000", "strike": 4560.0},
    },
}


def _make_client(order_status: str = "open") -> MagicMock:
    client = MagicMock()
    client.get_orders.return_value = [{"id": "O001", "status": order_status}]
    client.cancel_order.return_value = {"order": {"id": "O001", "status": "ok"}}
    client.place_multileg_order.return_value = {"order": {"id": "O002", "status": "ok"}}
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@patch("tradier_sniffer.demo.scenario1_5.time.sleep")
@patch("tradier_sniffer.demo.scenario1_5.scenario1.run", return_value=_ENTRY_RESULT)
def test_reprices_when_order_open(mock_run, mock_sleep):
    client = _make_client(order_status="open")
    result = scenario1_5.run(client, "ACC1", wait_seconds=5)
    assert result["repriced"] is True
    client.cancel_order.assert_called_once_with("ACC1", "O001")
    client.place_multileg_order.assert_called_once()
    assert result["order_id"] == "O002"


@patch("tradier_sniffer.demo.scenario1_5.time.sleep")
@patch("tradier_sniffer.demo.scenario1_5.scenario1.run", return_value=_ENTRY_RESULT)
def test_no_reprice_when_filled(mock_run, mock_sleep):
    client = _make_client(order_status="filled")
    result = scenario1_5.run(client, "ACC1", wait_seconds=5)
    assert result["repriced"] is False
    client.cancel_order.assert_not_called()


@patch("tradier_sniffer.demo.scenario1_5.time.sleep")
@patch("tradier_sniffer.demo.scenario1_5.scenario1.run", return_value=_ENTRY_RESULT)
def test_new_credit_reduced_by_tick(mock_run, mock_sleep):
    client = _make_client(order_status="open")
    result = scenario1_5.run(client, "ACC1", wait_seconds=1, tick_reduction=0.05)
    assert result["new_credit"] == pytest.approx(1.45)


@patch("tradier_sniffer.demo.scenario1_5.time.sleep")
@patch(
    "tradier_sniffer.demo.scenario1_5.scenario1.run",
    return_value={**_ENTRY_RESULT, "credit": 0.05},
)
def test_new_credit_floor_at_minimum(mock_run, mock_sleep):
    client = _make_client(order_status="open")
    result = scenario1_5.run(client, "ACC1", wait_seconds=1, tick_reduction=0.05)
    assert result["new_credit"] == pytest.approx(0.05)  # floored, not 0.00
