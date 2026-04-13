"""Integration tests for K9 entry runner using HolodeckBroker (K9-0060/K9-0070)."""
from __future__ import annotations

import json
import pytest
from datetime import datetime, date
from zoneinfo import ZoneInfo

from holodeck.broker import HolodeckBroker
from holodeck.config import HolodeckConfig
from holodeck.market_data import generate_spx_minutes

from K9.config import TradeSpec
from K9.engine.constructor import build_tp_order, build_order
from K9.engine.runner import RunResult, run_entry

TZ = "America/Chicago"


@pytest.fixture
def csv_path(tmp_path):
    path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, path)
    return path


@pytest.fixture
def holodeck_broker(csv_path):
    config = HolodeckConfig(
        starting_datetime=datetime(2026, 1, 5, 9, 30, tzinfo=ZoneInfo(TZ)),
        ending_datetime=datetime(2026, 1, 5, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    return HolodeckBroker(config)


def _make_spec(tmp_path, overrides: dict | None = None) -> TradeSpec:
    data = {
        "enabled": True, "environment": "holodeck",
        "underlying": "SPX", "trade_type": "IRON_CONDOR", "wing_size": 5,
        "short_strike_selection": {"method": "DELTA", "value": 20},
        "position_size": {"mode": "fixed_contracts", "contracts": 1},
        "account_minimum": 100,        # low so Holodeck account passes
        "max_risk_per_trade": 1000,
        "minimum_net_credit": 0.01,    # low so stylized prices pass
        "max_combo_bid_ask_width": 1000.0,  # wide so stylized spreads pass
        "entry": {"order_type": "LIMIT", "limit_price_strategy": "MID", "max_fill_time_seconds": 10},
        "exit": {"take_profit_percent": 34, "expiration_day_exit_mode": "HOLD_TO_EXPIRATION"},
        "constraints": {"max_entries_per_day": 10, "one_position_per_underlying": False},
        "allowed_entry_after": "00:00",
        "allowed_entry_before": "23:59",
    }
    if overrides:
        data.update(overrides)
    p = tmp_path / "spec.json"
    p.write_text(json.dumps(data))
    return TradeSpec.from_json(p)


def test_run_entry_returns_run_result(holodeck_broker, tmp_path):
    spec = _make_spec(tmp_path)
    result = run_entry(spec, "test_ic", holodeck_broker, log_dir=tmp_path / "logs")
    assert isinstance(result, RunResult)
    assert result.outcome in ("FILLED", "CANCELED", "SKIPPED", "ERROR")


def test_run_entry_skips_on_low_account(holodeck_broker, tmp_path):
    spec = _make_spec(tmp_path, {"account_minimum": 9_999_999.0})
    result = run_entry(spec, "test_skip", holodeck_broker, log_dir=tmp_path / "logs")
    assert result.outcome == "SKIPPED"
    assert "minimum" in result.reason.lower()


def test_run_entry_skips_outside_time_window(holodeck_broker, tmp_path):
    # Holodeck time is 09:30 CT; window 11:00–14:30 will exclude it
    spec = _make_spec(tmp_path, {
        "allowed_entry_after": "11:00",
        "allowed_entry_before": "14:30",
    })
    result = run_entry(spec, "test_window", holodeck_broker, log_dir=tmp_path / "logs")
    assert result.outcome == "SKIPPED"
    assert "outside entry window" in result.reason


def test_run_entry_sets_expiration(holodeck_broker, tmp_path):
    spec = _make_spec(tmp_path)
    result = run_entry(spec, "test_exp", holodeck_broker, log_dir=tmp_path / "logs")
    if result.outcome != "ERROR":
        assert result.expiration == "2026-01-05"


def test_run_entry_skips_max_entries_per_day(holodeck_broker, tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    # Pre-create a fake log file for today
    today_str = "20260105"
    (log_dir / f"test_ic_{today_str}_090000.json").write_text("{}")
    spec = _make_spec(tmp_path, {"constraints": {"max_entries_per_day": 1, "one_position_per_underlying": False}})
    result = run_entry(spec, "test_ic", holodeck_broker, log_dir=log_dir)
    assert result.outcome == "SKIPPED"
    assert "Already ran" in result.reason


def test_build_tp_order_reverses_legs(tmp_path):
    from bic.models import OptionContract
    spec = _make_spec(tmp_path)
    EXP = date(2026, 1, 5)
    SP = OptionContract(5800.0, "PUT",  1.20, 1.35, -0.20)
    LP = OptionContract(5795.0, "PUT",  0.60, 0.70, -0.10)
    SC = OptionContract(5840.0, "CALL", 0.90, 1.05,  0.18)
    LC = OptionContract(5845.0, "CALL", 0.45, 0.55,  0.10)
    entry_order = build_order(spec, EXP, SP, LP, SC, LC)
    tp_order = build_tp_order(spec, entry_order, filled_price=1.10)
    entry_actions = {(leg.action, leg.option_type) for leg in entry_order.legs}
    tp_actions = {(leg.action, leg.option_type) for leg in tp_order.legs}
    for action, otype in entry_actions:
        reversed_action = "BUY" if action == "SELL" else "SELL"
        assert (reversed_action, otype) in tp_actions
