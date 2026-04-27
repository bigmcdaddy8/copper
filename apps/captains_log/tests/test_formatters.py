"""Tests for shared Daily Notes formatter helpers."""
from __future__ import annotations

from captains_log.formatters import (
    format_daily_notes_header,
    format_entry_line,
    format_exit_line,
    format_gtc_line,
)
from captains_log.models import TradeRecord


def _trade() -> TradeRecord:
    t = TradeRecord(
        spec_name="spx_ic_test",
        environment="holodeck",
        account="HD",
        underlying="SPX",
        trade_type="IRON_CONDOR",
        expiration="2026-01-05",
        short_put_strike=7000.0,
        long_put_strike=6995.0,
        short_call_strike=7050.0,
        long_call_strike=7055.0,
        outcome="FILLED",
        reason="",
        errors=[],
        entry_order_id="HD-0001",
        entry_filled_price=1.50,
        net_credit=1.50,
        tp_order_id="HD-0002",
        tp_limit_price=0.75,
        tp_status="PLACED",
        bpr=500.0,
        credit_received=150.0,
        credit_fees=0.50,
        quantity=1,
        entry_dte=0,
        entry_underlying_last=7025.08,
        long_put_delta=-0.15,
        short_put_delta=-0.20,
        short_call_delta=0.20,
        long_call_delta=0.15,
    )
    t.entered_at = "2026-01-05T09:30:00+00:00"
    t.legacy_trade_num = "HD_00001_SIC"
    return t


def test_format_daily_notes_header_active():
    t = _trade()
    assert format_daily_notes_header(t) == "SPX(HD_00001_SIC): ACTIVE"


def test_format_daily_notes_header_closed():
    t = _trade()
    t.closed_at = "2026-01-05T15:00:00+00:00"
    assert format_daily_notes_header(t) == "SPX(HD_00001_SIC): CLOSED"


def test_format_entry_line_sic():
    t = _trade()
    line = format_entry_line(t)
    assert "01/05/2026: ENTRY #1 SOLD 1x SIC(6995/7000/7050/7055)" in line
    assert "DTE:0d BPR($500)" in line
    assert "-.15d/-.20d/.20d/.15d" in line
    assert "$7025.08 @1.50 - $0.50" in line


def test_format_gtc_line():
    t = _trade()
    line = format_gtc_line(t, tp_percent=50)
    assert line == "01/05/2026: GTC Quantity:1 TP:50%@-0.75 PP:$75.00 CB:$150.00"


def test_format_exit_line():
    line = format_exit_line(
        reason="GTC",
        occurred_at="2026-01-05T15:00:00+00:00",
        exit_price=0.75,
        fees=0.50,
    )
    assert line == "01/05/2026: GTC CLOSED TRADE @0.75 - $0.50"