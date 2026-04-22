"""Tests for reader aggregation helpers."""
from __future__ import annotations

import pytest
from captains_log.journal import Journal
from captains_log.models import TradeRecord

from encyclopedia_galactica.reader import Reader, group_by_month, group_by_year, pnl_stats


def _record(entered_at: str, realized_pnl: float | None = None, **kwargs) -> TradeRecord:
    defaults = dict(
        spec_name="spx_ic",
        environment="holodeck",
        account="HD",
        underlying="SPX",
        trade_type="IRON_CONDOR",
        expiration="2026-01-05",
        short_put_strike=5800.0,
        long_put_strike=5795.0,
        short_call_strike=5840.0,
        long_call_strike=5845.0,
        outcome="FILLED",
        reason="",
        errors=[],
        entry_order_id="HD-001",
        entry_filled_price=1.10,
        net_credit=1.10,
        tp_order_id="HD-002",
        tp_limit_price=0.75,
        tp_status="FILLED",
        realized_pnl=realized_pnl,
    )
    defaults.update(kwargs)
    t = TradeRecord(**defaults)
    t.entered_at = entered_at
    return t


@pytest.fixture
def reader(tmp_path):
    j = Journal(account="HD", db_path=tmp_path / "HD.db")
    t1 = _record("2026-01-05T10:00:00+00:00", realized_pnl=50.0)
    t2 = _record("2026-01-10T10:00:00+00:00", realized_pnl=-20.0)
    t3 = _record("2026-02-03T10:00:00+00:00", realized_pnl=80.0)
    j.record(t1)
    j.record(t2)
    j.record(t3)
    return Reader(account="HD", db_path=tmp_path / "HD.db")


def test_filled_trades(reader):
    trades = reader.filled_trades()
    assert len(trades) == 3


def test_group_by_month(reader):
    trades = reader.filled_trades()
    groups = group_by_month(trades)
    assert set(groups.keys()) == {"2026-01", "2026-02"}
    assert len(groups["2026-01"]) == 2
    assert len(groups["2026-02"]) == 1


def test_group_by_year(reader):
    trades = reader.filled_trades()
    groups = group_by_year(trades)
    assert list(groups.keys()) == ["2026"]
    assert len(groups["2026"]) == 3


def test_pnl_stats_basic(reader):
    trades = reader.filled_trades()
    s = pnl_stats(trades)
    assert s["count"] == 3
    assert s["pnl_count"] == 3
    assert s["total"] == pytest.approx(110.0)
    assert s["best"] == pytest.approx(80.0)
    assert s["worst"] == pytest.approx(-20.0)
    assert s["avg"] == pytest.approx(110.0 / 3)


def test_pnl_stats_empty():
    s = pnl_stats([])
    assert s["total"] is None
    assert s["pnl_count"] == 0
