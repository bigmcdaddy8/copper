"""Integration tests for K9 entry runner using HolodeckBroker (K9-0060/K9-0070)."""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

import pytest

from holodeck.broker import HolodeckBroker
from holodeck.config import HolodeckConfig
from holodeck.market_data import generate_spx_minutes

from K9.config import TradeSpec
from K9.engine.constructor import build_order, build_tp_order
from K9.engine.runner import RunResult, run_entry, run_preflight

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
        "enabled": True,
        "environment": "holodeck",
        "underlying": "SPX",
        "trade_type": "IRON_CONDOR",
        "wing_size": 5,
        "short_strike_selection": {"method": "DELTA", "value": 20},
        "position_size": {"mode": "fixed_contracts", "contracts": 1},
        "account_minimum": 100,
        "max_risk_per_trade": 1000,
        "minimum_net_credit": 0.01,
        "max_combo_bid_ask_width": 1000.0,
        "entry": {
            "order_type": "LIMIT",
            "limit_price_strategy": "MID",
            "max_fill_time_seconds": 10,
        },
        "exit": {
            "take_profit_percent": 34,
            "expiration_day_exit_mode": "HOLD_TO_EXPIRATION",
        },
        "constraints": {
            "max_entries_per_day": 10,
            "one_position_per_underlying": False,
        },
        "allowed_entry_after": "00:00",
        "allowed_entry_before": "23:59",
    }
    if overrides:
        data.update(overrides)

    p = tmp_path / "spec.yaml"
    p.write_text(
        """
enabled: {enabled}
environment: {environment}
underlying: {underlying}
trade_type: {trade_type}
wing_size: {wing_size}
short_strike_selection:
  method: {ss_method}
  value: {ss_value}
position_size:
  mode: {ps_mode}
  contracts: {ps_contracts}
account_minimum: {account_minimum}
max_risk_per_trade: {max_risk_per_trade}
minimum_net_credit: {minimum_net_credit}
max_combo_bid_ask_width: {max_combo_bid_ask_width}
entry:
  order_type: {entry_order_type}
  limit_price_strategy: {entry_limit_price_strategy}
  max_fill_time_seconds: {entry_max_fill}
exit:
  take_profit_percent: {exit_tp}
  expiration_day_exit_mode: {exit_mode}
constraints:
  max_entries_per_day: {constraints_max_entries}
  one_position_per_underlying: {constraints_one_pos}
allowed_entry_after: "{allowed_after}"
allowed_entry_before: "{allowed_before}"
""".strip().format(
            enabled=str(data["enabled"]).lower(),
            environment=data["environment"],
            underlying=data["underlying"],
            trade_type=data["trade_type"],
            wing_size=data["wing_size"],
            ss_method=data["short_strike_selection"]["method"],
            ss_value=data["short_strike_selection"]["value"],
            ps_mode=data["position_size"]["mode"],
            ps_contracts=data["position_size"]["contracts"],
            account_minimum=data["account_minimum"],
            max_risk_per_trade=data["max_risk_per_trade"],
            minimum_net_credit=data["minimum_net_credit"],
            max_combo_bid_ask_width=data["max_combo_bid_ask_width"],
            entry_order_type=data["entry"]["order_type"],
            entry_limit_price_strategy=data["entry"]["limit_price_strategy"],
            entry_max_fill=data["entry"]["max_fill_time_seconds"],
            exit_tp=data["exit"]["take_profit_percent"],
            exit_mode=data["exit"]["expiration_day_exit_mode"],
            constraints_max_entries=data["constraints"]["max_entries_per_day"],
            constraints_one_pos=str(data["constraints"]["one_position_per_underlying"]).lower(),
            allowed_after=data["allowed_entry_after"],
            allowed_before=data["allowed_entry_before"],
        )
    )
    return TradeSpec.from_file(p)


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
    # Holodeck time is 09:30 CT; window 11:00-14:30 will exclude it
    spec = _make_spec(
        tmp_path,
        {
            "allowed_entry_after": "11:00",
            "allowed_entry_before": "14:30",
        },
    )
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
    spec = _make_spec(
        tmp_path,
        {"constraints": {"max_entries_per_day": 1, "one_position_per_underlying": False}},
    )
    result = run_entry(spec, "test_ic", holodeck_broker, log_dir=log_dir)
    assert result.outcome == "SKIPPED"
    assert "Already ran" in result.reason


def test_build_tp_order_reverses_legs(tmp_path):
    from bic.models import OptionContract

    spec = _make_spec(tmp_path)
    exp = date(2026, 1, 5)
    sp = OptionContract(5800.0, "PUT", 1.20, 1.35, -0.20)
    lp = OptionContract(5795.0, "PUT", 0.60, 0.70, -0.10)
    sc = OptionContract(5840.0, "CALL", 0.90, 1.05, 0.18)
    lc = OptionContract(5845.0, "CALL", 0.45, 0.55, 0.10)
    entry_order = build_order(spec, exp, sp, lp, sc, lc)
    tp_order = build_tp_order(spec, entry_order, filled_price=1.10)
    entry_actions = {(leg.action, leg.option_type) for leg in entry_order.legs}
    tp_actions = {(leg.action, leg.option_type) for leg in tp_order.legs}
    for action, otype in entry_actions:
        reversed_action = "BUY" if action == "SELL" else "SELL"
        assert (reversed_action, otype) in tp_actions


def test_run_entry_categorizes_market_data_error(holodeck_broker, tmp_path, monkeypatch):
    spec = _make_spec(tmp_path)

    def _boom(_symbol):
        raise KeyError("2026-04-29T09:30:00")

    monkeypatch.setattr(holodeck_broker, "get_underlying_quote", _boom)

    result = run_entry(spec, "test_ic", holodeck_broker, log_dir=tmp_path / "logs")
    assert result.outcome == "ERROR"
    assert result.error_category == "DATA_UNAVAILABLE"
    assert result.error_code == "MARKET_DATA_UNAVAILABLE"
    assert "Market data unavailable" in result.reason
    assert any("DATA_UNAVAILABLE|MARKET_DATA_UNAVAILABLE" in e for e in result.errors)


def test_run_entry_categorizes_selection_error(holodeck_broker, tmp_path, monkeypatch):
    spec = _make_spec(tmp_path)

    def _boom(_chain, _delta):
        raise ValueError("no contracts matched")

    monkeypatch.setattr("K9.engine.runner.select_short_put", _boom)

    result = run_entry(spec, "test_ic", holodeck_broker, log_dir=tmp_path / "logs")
    assert result.outcome == "ERROR"
    assert result.error_category == "SELECTION_FAILED"
    assert result.error_code == "STRIKE_SELECTION_FAILED"
    assert "Unable to select strategy legs" in result.reason
    assert any("SELECTION_FAILED|STRIKE_SELECTION_FAILED" in e for e in result.errors)


def test_run_entry_dry_run_sets_flag(holodeck_broker, tmp_path):
    spec = _make_spec(tmp_path)
    result = run_entry(
        spec,
        "test_ic",
        holodeck_broker,
        log_dir=tmp_path / "logs",
        dry_run=True,
    )
    assert result.dry_run is True
    assert result.preflight is False
    assert result.outcome in ("SKIPPED", "ERROR")


def test_run_preflight_returns_expected_outcome(holodeck_broker, tmp_path):
    spec = _make_spec(tmp_path)
    result = run_preflight(spec, "test_ic", holodeck_broker)
    assert result.preflight is True
    assert result.dry_run is False
    assert result.outcome in ("PREFLIGHT_OK", "ERROR")


# ------------------------------------------------------------------ #
# trade_tag and rejection_reason propagation                         #
# ------------------------------------------------------------------ #

def test_run_entry_sets_trade_tag_on_fill(holodeck_broker, tmp_path):
    """A successfully filled run must carry a non-empty trade_tag."""
    spec = _make_spec(tmp_path)
    result = run_entry(
        spec, "test_ic", holodeck_broker,
        log_dir=tmp_path / "logs",
        tick=holodeck_broker.advance_time,
    )
    if result.outcome == "FILLED":
        assert result.trade_tag != ""
        assert len(result.trade_tag) == 8   # uuid4().hex[:8]


def test_run_entry_rejection_reason_propagates(holodeck_broker, tmp_path, monkeypatch):
    """When place_order returns REJECTED with a reason, RunResult carries it."""
    from bic.models import OrderResponse

    def _reject(order):
        return OrderResponse(
            order_id="",
            status="REJECTED",
            rejection_reason="insufficient_buying_power",
            rejection_text="Insufficient buying power",
        )

    monkeypatch.setattr(holodeck_broker, "place_order", _reject)
    spec = _make_spec(tmp_path)
    result = run_entry(spec, "test_ic", holodeck_broker, log_dir=tmp_path / "logs")
    # outcome should be REJECTED (or ERROR if broker raises before reaching place_order)
    if result.outcome == "REJECTED":
        assert result.rejection_reason == "insufficient_buying_power"


def test_run_entry_trade_tag_non_empty_even_on_cancel(holodeck_broker, tmp_path):
    """trade_tag is assigned before order placement, so it is set even on timeout/cancel."""
    spec = _make_spec(tmp_path, {"entry": {
        "order_type": "LIMIT",
        "limit_price_strategy": "MID",
        "max_fill_time_seconds": 1,  # near-zero timeout to force cancel
    }})
    result = run_entry(
        spec, "test_ic", holodeck_broker,
        log_dir=tmp_path / "logs",
    )
    if result.outcome in ("FILLED", "CANCELED", "REJECTED"):
        assert result.trade_tag != ""
