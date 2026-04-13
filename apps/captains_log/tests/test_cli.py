"""Tests for captains_log query CLI (CL-0040)."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


from captains_log.journal import Journal
from captains_log.models import TradeRecord


def _run_cli(args: list[str], db_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "captains_log", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "CL_DB_PATH": str(db_path)},
    )


def _insert_filled(db_path: Path, spec_name: str = "spx_ic_test") -> TradeRecord:
    t = TradeRecord(
        spec_name=spec_name,
        environment="holodeck",
        underlying="SPX",
        trade_type="IRON_CONDOR",
        expiration="2026-01-05",
        short_put_strike=5800.0,
        long_put_strike=5795.0,
        short_call_strike=5840.0,
        long_call_strike=5845.0,
        outcome="FILLED",
        reason="",
        entry_order_id="HD-000042",
        entry_filled_price=1.10,
        net_credit=1.10,
        tp_order_id="HD-000043",
        tp_limit_price=0.75,
        tp_status="PLACED",
    )
    Journal(db_path=db_path).record(t)
    return t


def test_list_exits_zero_empty(tmp_path):
    db = tmp_path / "trades.db"
    result = _run_cli(["list"], db)
    assert result.returncode == 0


def test_list_shows_record(tmp_path):
    db = tmp_path / "trades.db"
    _insert_filled(db, spec_name="my_test_spec")
    result = _run_cli(["list"], db)
    assert result.returncode == 0
    assert "my_tes" in result.stdout  # Rich may truncate long spec names in table


def test_show_exits_zero(tmp_path):
    db = tmp_path / "trades.db"
    trade = _insert_filled(db)
    result = _run_cli(["show", trade.trade_id], db)
    assert result.returncode == 0
    assert "FILLED" in result.stdout


def test_show_missing_exits_one(tmp_path):
    db = tmp_path / "trades.db"
    result = _run_cli(["show", "nonexistent_trade_id_xyz"], db)
    assert result.returncode == 1
