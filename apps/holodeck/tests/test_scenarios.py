import subprocess
import sys
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from holodeck.broker import HolodeckBroker
from holodeck.config import HolodeckConfig
from holodeck.market_data import generate_spx_minutes
from holodeck.scenarios.spx_0dte import (
    scenario_immediate_fill,
    scenario_no_fill_timeout,
    scenario_entry_then_tp,
    scenario_entry_expire_profit,
    scenario_entry_expire_loss,
    scenario_account_minimum_block,
    scenario_existing_position_block,
)

TZ = "America/Chicago"
START = datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ))


@pytest.fixture
def broker(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    config = HolodeckConfig(
        starting_datetime=START,
        ending_datetime=datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ)),
        data_path=csv_path,
    )
    return HolodeckBroker(config)


def fresh_broker(broker):
    """Reset broker to initial state for each scenario."""
    broker.reset()
    return broker


def test_scenario_immediate_fill(broker):
    result = scenario_immediate_fill(fresh_broker(broker))
    assert result["filled"] is True


def test_scenario_no_fill_timeout(broker):
    result = scenario_no_fill_timeout(fresh_broker(broker))
    assert result["fill_blocked"] is True
    assert result["canceled"] is True


def test_scenario_entry_then_tp(broker):
    result = scenario_entry_then_tp(fresh_broker(broker))
    assert result["entry_filled"] is True
    assert result["tp_filled"] is True


def test_scenario_entry_expire_profit(broker):
    result = scenario_entry_expire_profit(fresh_broker(broker))
    assert result["entry_filled"] is True
    assert result["position_closed"] is True
    assert result["pnl_positive"] is True


def test_scenario_entry_expire_loss(broker):
    result = scenario_entry_expire_loss(fresh_broker(broker))
    assert result["entry_filled"] is True
    assert result["position_closed"] is True
    assert result["max_loss_realized"] is True


def test_scenario_account_minimum_block(broker):
    result = scenario_account_minimum_block(fresh_broker(broker))
    assert result["order_blocked"] is True


def test_scenario_existing_position_block(broker):
    result = scenario_existing_position_block(fresh_broker(broker))
    assert result["first_order_filled"] is True
    assert result["second_order_rejected"] is True


def test_run_scenario_cli_immediate_fill(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    result = subprocess.run(
        [
            sys.executable, "-m", "holodeck",
            "run-scenario",
            "--name", "immediate-fill",
            "--output", csv_path,
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "passed" in result.stdout.lower() or "filled" in result.stdout.lower()
