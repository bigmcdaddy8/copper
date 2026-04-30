"""End-to-end integration tests for K9 using HolodeckBroker (K9-0090)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _base_spec() -> dict:
        return """
enabled: true
environment: holodeck
underlying: SPX
trade_type: IRON_CONDOR
wing_size: 5
short_strike_selection:
    method: DELTA
    value: 20
position_size:
    mode: fixed_contracts
    contracts: 1
account_minimum: 100
max_risk_per_trade: 1000
minimum_net_credit: 0.01
max_combo_bid_ask_width: 1000.0
entry:
    order_type: LIMIT
    limit_price_strategy: MID
    max_fill_time_seconds: 10
exit:
    take_profit_percent: 34
    expiration_day_exit_mode: HOLD_TO_EXPIRATION
constraints:
    max_entries_per_day: 10
    one_position_per_underlying: false
allowed_entry_after: "00:00"
allowed_entry_before: "23:59"
""".strip()


@pytest.fixture
def spec_file(tmp_path) -> Path:
    p = tmp_path / "test_ic.yaml"
    p.write_text(_base_spec())
    return p


def _run_enter(
    spec_file: Path,
    tmp_path: Path,
    dry_run: bool = False,
    extra_env: dict | None = None,
) -> subprocess.CompletedProcess:
    env = {**os.environ, "K9_LOG_DIR": str(tmp_path / "logs")}
    if extra_env:
        env.update(extra_env)
    cmd = [
        sys.executable, "-m", "K9",
        "enter",
        "--trade-spec", spec_file.stem,
        "--specs-dir", str(spec_file.parent),
    ]
    if dry_run:
        cmd.append("--dry-run")
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env=env,
    )


def _run_preflight(spec_file: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    env = {**os.environ, "K9_LOG_DIR": str(tmp_path / "logs")}
    return subprocess.run(
        [
            sys.executable, "-m", "K9",
            "preflight",
            "--trade-spec", spec_file.stem,
            "--specs-dir", str(spec_file.parent),
        ],
        capture_output=True,
        text=True,
        env=env,
    )


def test_enter_exits_zero_or_one(spec_file, tmp_path):
    """K9 enter exits 0 (FILLED/SKIPPED) or 1 (CANCELED/ERROR) — never other codes."""
    result = _run_enter(spec_file, tmp_path)
    assert result.returncode in (0, 1), (
        f"Unexpected exit code {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_enter_writes_log_file(spec_file, tmp_path):
    _run_enter(spec_file, tmp_path)
    log_files = list((tmp_path / "logs").glob("test_ic_*.json"))
    assert len(log_files) == 1


def test_enter_log_has_required_fields(spec_file, tmp_path):
    _run_enter(spec_file, tmp_path)
    log_files = list((tmp_path / "logs").glob("test_ic_*.json"))
    import json
    data = json.loads(log_files[0].read_text())
    for field in ("spec_name", "environment", "outcome", "started_at"):
        assert field in data, f"Missing field: {field}"
    assert data["environment"] == "holodeck"


def test_enter_disabled_spec_exits_zero(tmp_path):
    spec_file = tmp_path / "disabled.yaml"
    spec_file.write_text(
        _base_spec().replace("enabled: true", "enabled: false")
    )
    result = subprocess.run(
        [
            sys.executable, "-m", "K9",
            "enter",
            "--trade-spec", "disabled",
            "--specs-dir", str(tmp_path),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "disabled" in result.stdout.lower()


def test_enter_missing_spec_exits_one():
    result = subprocess.run(
        [sys.executable, "-m", "K9", "enter", "--trade-spec", "nonexistent_spec_xyz"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "not found" in result.stdout.lower()


def test_enter_writes_journal_record(spec_file, tmp_path):
    """K9 enter should write a TradeRecord to the captains_log journal."""
    db_path = tmp_path / "journal.db"
    _run_enter(spec_file, tmp_path, extra_env={"CL_DB_PATH": str(db_path)})

    from captains_log import Journal
    journal = Journal(db_path=db_path)
    trades = journal.list_trades()
    assert len(trades) == 1
    assert trades[0].spec_name == spec_file.stem
    assert trades[0].outcome in ("FILLED", "SKIPPED", "CANCELED", "REJECTED", "ERROR")


def test_enter_json_spec_rejected(spec_file, tmp_path):
    json_spec = tmp_path / "json_warn.json"
    json_spec.write_text(
        json.dumps(
            {
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
                "constraints": {"max_entries_per_day": 10, "one_position_per_underlying": False},
                "allowed_entry_after": "00:00",
                "allowed_entry_before": "23:59",
            }
        )
    )

    result = _run_enter(json_spec, tmp_path)
    assert result.returncode == 1
    assert "not found" in result.stdout.lower()


def test_enter_accepts_yaml_spec(tmp_path):
    spec_file = tmp_path / "yaml_ic.yaml"
    spec_file.write_text(
        """
enabled: true
environment: holodeck
underlying: SPX
trade_type: IRON_CONDOR
wing_size: 5
short_strike_selection:
  method: DELTA
  value: 20
position_size:
  mode: fixed_contracts
  contracts: 1
account_minimum: 100
max_risk_per_trade: 1000
minimum_net_credit: 0.01
max_combo_bid_ask_width: 1000.0
entry:
  order_type: LIMIT
  limit_price_strategy: MID
  max_fill_time_seconds: 10
exit:
  take_profit_percent: 34
  expiration_day_exit_mode: HOLD_TO_EXPIRATION
constraints:
  max_entries_per_day: 10
  one_position_per_underlying: false
allowed_entry_after: "00:00"
allowed_entry_before: "23:59"
""".strip()
    )

    result = _run_enter(spec_file, tmp_path)
    assert result.returncode in (0, 1)


def test_preflight_exits_zero_or_one(spec_file, tmp_path):
    result = _run_preflight(spec_file, tmp_path)
    assert result.returncode in (0, 1), (
        f"Unexpected exit code {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_preflight_writes_log_with_preflight_flag(spec_file, tmp_path):
    _run_preflight(spec_file, tmp_path)
    log_files = list((tmp_path / "logs").glob("test_ic_*.json"))
    assert len(log_files) == 1
    data = json.loads(log_files[0].read_text())
    assert data["preflight"] is True
    assert data["dry_run"] is False


def test_enter_dry_run_sets_log_flag(spec_file, tmp_path):
    result = _run_enter(spec_file, tmp_path, dry_run=True)
    assert result.returncode in (0, 1)

    log_files = list((tmp_path / "logs").glob("test_ic_*.json"))
    assert len(log_files) == 1
    data = json.loads(log_files[0].read_text())
    assert data["dry_run"] is True
    assert data["preflight"] is False


def test_enter_error_output_is_actionable(spec_file, tmp_path):
    result = _run_enter(spec_file, tmp_path)
    if "Outcome: ERROR" in result.stdout:
        assert "Market data unavailable" in result.stdout
        assert "Error category:" in result.stdout


