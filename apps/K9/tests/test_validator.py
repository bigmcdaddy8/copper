"""Tests for pre-trade validator (K9-0050)."""
from __future__ import annotations

import json
import pytest
from bic.models import OptionContract, OrderRequest
from K9.config import TradeSpec
from K9.engine.validator import (
    check_combo_spread,
    check_max_risk,
    check_minimum_credit,
    validate_trade,
)


@pytest.fixture
def spec(tmp_path) -> TradeSpec:
    data = {
        "enabled": True, "environment": "holodeck",
        "underlying": "SPX", "trade_type": "IRON_CONDOR", "wing_size": 5,
        "short_strike_selection": {"method": "DELTA", "value": 20},
        "position_size": {"mode": "fixed_contracts", "contracts": 1},
        "account_minimum": 5000, "max_risk_per_trade": 400,
        "minimum_net_credit": 0.30, "max_combo_bid_ask_width": 0.50,
        "entry": {"order_type": "LIMIT", "limit_price_strategy": "MID", "max_fill_time_seconds": 120},
        "exit": {"take_profit_percent": 34, "expiration_day_exit_mode": "HOLD_TO_EXPIRATION"},
        "constraints": {"max_entries_per_day": 1, "one_position_per_underlying": True},
    }
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(data))
    return TradeSpec.from_json(p)


def test_check_minimum_credit_passes():
    assert check_minimum_credit(0.50, 0.30).passed is True


def test_check_minimum_credit_fails():
    result = check_minimum_credit(0.20, 0.30)
    assert result.passed is False
    assert "below minimum" in result.reason


def test_check_combo_spread_passes():
    assert check_combo_spread(0.40, 0.50).passed is True


def test_check_combo_spread_fails():
    result = check_combo_spread(0.60, 0.50)
    assert result.passed is False
    assert "exceeds maximum" in result.reason


def test_check_max_risk_passes():
    assert check_max_risk(380.0, 400.0).passed is True


def test_check_max_risk_fails():
    result = check_max_risk(450.0, 400.0)
    assert result.passed is False
    assert "exceeds limit" in result.reason


def test_validate_trade_all_pass(spec):
    sp = OptionContract(5800.0, "PUT",  1.20, 1.35, -0.20)
    lp = OptionContract(5795.0, "PUT",  0.60, 0.70, -0.10)
    sc = OptionContract(5840.0, "CALL", 0.90, 1.05,  0.18)
    lc = OptionContract(5845.0, "CALL", 0.45, 0.55,  0.10)
    order = OrderRequest("SPX", "IRON_CONDOR", limit_price=1.10)
    result = validate_trade(spec, order, sp, lp, sc, lc)
    assert result.passed is True


def test_validate_trade_fails_low_credit(spec):
    sp = OptionContract(5800.0, "PUT",  0.10, 0.12, -0.05)
    lp = OptionContract(5795.0, "PUT",  0.05, 0.07, -0.02)
    sc = OptionContract(5840.0, "CALL", 0.08, 0.10,  0.04)
    lc = OptionContract(5845.0, "CALL", 0.03, 0.05,  0.02)
    order = OrderRequest("SPX", "IRON_CONDOR", limit_price=0.10)
    result = validate_trade(spec, order, sp, lp, sc, lc)
    assert result.passed is False
    assert "below minimum" in result.reason


def test_validate_trade_short_circuits_on_first_failure(spec):
    # Credit fails — combo spread and max risk should never be checked
    order = OrderRequest("SPX", "IRON_CONDOR", limit_price=0.05)
    sp = OptionContract(5800.0, "PUT",  0.05, 0.06, -0.05)
    lp = OptionContract(5795.0, "PUT",  0.02, 0.03, -0.02)
    result = validate_trade(spec, order, sp, lp, None, None)
    assert result.passed is False
    assert "below minimum" in result.reason
