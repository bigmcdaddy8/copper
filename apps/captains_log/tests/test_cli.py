"""Tests for captains_log query CLI (CL-0040)."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


def _insert_filled(
    db_path: Path,
    spec_name: str = "spx_ic_test",
    entered_at: str | None = None,
) -> TradeRecord:
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
    if entered_at is not None:
        t.entered_at = entered_at
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
    assert "FILLED" in result.stdout


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


def test_list_date_today_token(tmp_path):
    db = tmp_path / "trades.db"
    _insert_filled(db, spec_name="today_spec")
    result = _run_cli(["list", "--date", "today"], db)
    assert result.returncode == 0
    assert "FILLED" in result.stdout


def test_list_invalid_date_exits_nonzero(tmp_path):
    db = tmp_path / "trades.db"
    _insert_filled(db)
    result = _run_cli(["list", "--date", "not-a-date"], db)
    assert result.returncode != 0


def test_list_date_tomorrow_token(tmp_path):
    db = tmp_path / "trades.db"
    tomorrow = (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()
    _insert_filled(db, spec_name="tomorrow_spec", entered_at=f"{tomorrow}T12:00:00+00:00")
    result = _run_cli(["list", "--date", "tomorrow", "--spec", "tomorrow_spec"], db)
    assert result.returncode == 0
    assert "1 record(s)" in result.stdout


def test_list_from_to_range_filters_records(tmp_path):
    db = tmp_path / "trades.db"
    _insert_filled(db, spec_name="older_spec", entered_at="2026-05-01T12:00:00+00:00")
    _insert_filled(db, spec_name="in_range_spec", entered_at="2026-05-03T12:00:00+00:00")
    _insert_filled(db, spec_name="newer_spec", entered_at="2026-05-05T12:00:00+00:00")

    result = _run_cli(
        ["list", "--from", "2026-05-02", "--to", "2026-05-04", "--spec", "in_range_spec"],
        db,
    )
    assert result.returncode == 0
    assert "1 record(s)" in result.stdout

    outside = _run_cli(
        ["list", "--from", "2026-05-02", "--to", "2026-05-04", "--spec", "older_spec"],
        db,
    )
    assert outside.returncode == 0
    assert "No trades found." in outside.stdout


def test_list_date_conflicts_with_range_options(tmp_path):
    db = tmp_path / "trades.db"
    _insert_filled(db)
    result = _run_cli(["list", "--date", "today", "--from", "2026-05-01"], db)
    assert result.returncode != 0


def test_list_invalid_range_order_exits_nonzero(tmp_path):
    db = tmp_path / "trades.db"
    _insert_filled(db)
    result = _run_cli(["list", "--from", "2026-05-05", "--to", "2026-05-01"], db)
    assert result.returncode != 0
