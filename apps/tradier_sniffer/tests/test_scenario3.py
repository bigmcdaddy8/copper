"""Unit tests for scenario 3 — entry + GTC TP."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tradier_sniffer.demo import scenario3

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


def _make_client() -> MagicMock:
    client = MagicMock()
    client.place_multileg_order.return_value = {"order": {"id": "TP001", "status": "ok"}}
    return client


@patch("tradier_sniffer.demo.scenario3.scenario1.run", return_value=_ENTRY_RESULT)
def test_scenario3_places_tp_order(mock_run):
    client = _make_client()
    result = scenario3.run(client, "ACC1")
    assert result["tp_order_id"] == "TP001"
    assert result["entry_order_id"] == "O001"
    # place_multileg_order called twice: once for entry (via scenario1 mock), once for TP
    client.place_multileg_order.assert_called_once()  # only the TP call (entry is mocked)


@patch("tradier_sniffer.demo.scenario3.scenario1.run", return_value=_ENTRY_RESULT)
def test_scenario3_tp_price_at_50pct(mock_run):
    client = _make_client()
    result = scenario3.run(client, "ACC1", tp_pct=0.50)
    assert result["tp_price"] == pytest.approx(1.00)


@patch("tradier_sniffer.demo.scenario3.scenario1.run", return_value=_ENTRY_RESULT)
def test_scenario3_tp_price_at_custom_pct(mock_run):
    client = _make_client()
    result = scenario3.run(client, "ACC1", tp_pct=0.25)
    assert result["tp_price"] == pytest.approx(0.50)
