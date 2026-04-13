"""Tests for TradeSpec loading and validation (K9-0010)."""
from __future__ import annotations

import json
import pytest
from pathlib import Path
from K9.config import TradeSpec


@pytest.fixture
def valid_spec_path(tmp_path) -> Path:
    data = {
        "enabled": True,
        "environment": "holodeck",
        "underlying": "SPX",
        "trade_type": "IRON_CONDOR",
        "wing_size": 5,
        "short_strike_selection": {"method": "DELTA", "value": 20},
        "position_size": {"mode": "fixed_contracts", "contracts": 1},
        "account_minimum": 5000,
        "max_risk_per_trade": 500,
        "minimum_net_credit": 0.30,
        "max_combo_bid_ask_width": 0.50,
        "entry": {
            "order_type": "LIMIT",
            "limit_price_strategy": "MID",
            "max_fill_time_seconds": 120,
        },
        "exit": {
            "take_profit_percent": 34,
            "expiration_day_exit_mode": "HOLD_TO_EXPIRATION",
        },
        "constraints": {
            "max_entries_per_day": 1,
            "one_position_per_underlying": True,
        },
        "notes": "test spec",
    }
    path = tmp_path / "test_spec.json"
    path.write_text(json.dumps(data))
    return path


def test_load_valid_spec(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    assert spec.underlying == "SPX"
    assert spec.trade_type == "IRON_CONDOR"
    assert spec.environment == "holodeck"
    assert spec.wing_size == 5
    assert spec.entry.max_fill_time_seconds == 120
    assert spec.exit.take_profit_percent == 34
    assert spec.constraints.one_position_per_underlying is True


def test_validate_passes_for_valid_spec(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    spec.validate()  # should not raise


def test_validate_rejects_invalid_underlying(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    spec.underlying = "AAPL"
    with pytest.raises(ValueError, match="Invalid underlying"):
        spec.validate()


def test_validate_rejects_invalid_environment(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    spec.environment = "paper"
    with pytest.raises(ValueError, match="Invalid environment"):
        spec.validate()


def test_validate_rejects_multi_contract(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    spec.position_size.contracts = 5
    with pytest.raises(ValueError, match="1 contract"):
        spec.validate()


def test_validate_rejects_non_delta_selection(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    spec.short_strike_selection.method = "IV_RANK"
    with pytest.raises(ValueError, match="DELTA"):
        spec.validate()


def test_default_entry_window(valid_spec_path):
    spec = TradeSpec.from_json(valid_spec_path)
    assert spec.allowed_entry_after == "09:25"
    assert spec.allowed_entry_before == "14:30"
