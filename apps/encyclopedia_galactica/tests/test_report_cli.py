"""Functional CLI tests for reporting commands."""
from __future__ import annotations

import re

from typer.testing import CliRunner

from captains_log.formatters import (
    format_daily_notes_header,
    format_entry_line,
    format_exit_line,
    format_gtc_line,
)
from captains_log.journal import Journal
from captains_log.models import TradeLogEntry, TradeRecord
from encyclopedia_galactica.cli import app

runner = CliRunner()


def _record(seq: int, *, closed: bool, underlying: str = "SPX") -> TradeRecord:
    trade = TradeRecord(
        spec_name="spx_ic",
        environment="holodeck",
        account="TRD",
        underlying=underlying,
        trade_type="IRON_CONDOR",
        expiration="2026-01-05",
        short_put_strike=7000.0,
        long_put_strike=6995.0,
        short_call_strike=7050.0,
        long_call_strike=7055.0,
        outcome="FILLED",
        reason="",
        errors=[],
        entry_order_id=f"TRD-E-{seq}",
        entry_filled_price=1.50,
        net_credit=1.50,
        tp_order_id=f"TRD-TP-{seq}",
        tp_limit_price=0.75,
        tp_status="PLACED",
        bpr=500.0,
        credit_received=150.0,
        credit_fees=0.50,
        debit_paid=0.0,
        debit_fees=0.0,
        quantity=1,
        entry_dte=0,
        entry_underlying_last=7025.08,
        long_put_delta=-0.15,
        short_put_delta=-0.20,
        short_call_delta=0.20,
        long_call_delta=0.15,
    )
    trade.entered_at = f"2026-01-{seq:02d}T09:30:00+00:00"
    if closed:
        trade.closed_at = f"2026-01-{seq:02d}T15:00:00+00:00"
        trade.exit_reason = "GTC"
        trade.tp_status = "FILLED"
        trade.realized_pnl = 74.5
        trade.debit_paid = 75.0
        trade.debit_fees = 0.5
    return trade


def _seed_data(db_path) -> None:
    journal = Journal(account="TRD", db_path=db_path)

    t1 = _record(1, closed=True, underlying="SPX")
    journal.record(t1)
    journal.append_event(
        TradeLogEntry(
            trade_id=t1.trade_id,
            event_type="ENTRY",
            occurred_at=t1.entered_at,
            line_text=(
                "01/01/2026: ENTRY #1 SOLD 1x SIC(6995/7000/7050/7055) "
                "DTE:0d BPR($500) -.15d/-.20d/+0.20d/+0.15d $7025.08 @1.50 - $0.50"
            ),
            payload={"quantity": 1},
        )
    )
    journal.append_event(
        TradeLogEntry(
            trade_id=t1.trade_id,
            event_type="GTC",
            occurred_at=t1.entered_at,
            line_text="01/01/2026: GTC Quantity:1 TP:50%@-0.75 PP:$75.00 CB:$150.00",
            payload={"tp_percent": 50},
        )
    )
    journal.append_event(
        TradeLogEntry(
            trade_id=t1.trade_id,
            event_type="EXIT",
            occurred_at=t1.closed_at or t1.entered_at,
            line_text="01/01/2026: EXIT #1 GTC CLOSED TRADE @0.75 - $0.50",
            payload={"reason": "GTC"},
        )
    )

    t2 = _record(2, closed=False, underlying="NDX")
    journal.record(t2)


def test_trade_number_report_sorted_and_filtered(tmp_path, monkeypatch):
    db_path = tmp_path / "TRD.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))
    _seed_data(db_path)

    result = runner.invoke(app, ["report", "trade-number", "--account", "TRD"])
    assert result.exit_code == 0
    assert "Trade Number Report - TRD" in result.output
    assert "TRD_00002_SIC" in result.output
    assert "TRD_00001_SIC" in result.output
    assert result.output.index("TRD_00002_SIC") < result.output.index("TRD_00001_SIC")

    filtered = runner.invoke(
        app,
        ["report", "trade-number", "--account", "TRD", "--trade-number", "TRD_00001_SIC"],
    )
    assert filtered.exit_code == 0
    assert "TRD_00001_SIC" in filtered.output
    assert "TRD_00002_SIC" not in filtered.output


def test_daily_notes_report_header_and_lines(tmp_path, monkeypatch):
    db_path = tmp_path / "TRD.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))
    _seed_data(db_path)

    result = runner.invoke(app, ["report", "daily-notes", "--account", "TRD", "--underlying", "SPX"])
    assert result.exit_code == 0
    assert "SPX(TRD_00001_SIC): CLOSED" in result.output
    assert "ENTRY #1 SOLD 1x SIC" in result.output
    assert "GTC Quantity:1 TP:50%@-0.75" in result.output
    assert "EXIT #1 GTC CLOSED TRADE @0.75 - $0.50" in result.output
    assert "NDX(TRD_00002_SIC)" not in result.output


def test_trade_history_report_with_filters(tmp_path, monkeypatch):
    db_path = tmp_path / "TRD.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))
    _seed_data(db_path)

    result = runner.invoke(
        app,
        [
            "report",
            "trade-history",
            "--account",
            "TRD",
            "--status",
            "CLOSED",
            "--trade-number",
            "TRD_00001_SIC",
            "--entry-date",
            ">=01/01/2026",
            "--exit-date",
            "<=01/31/2026",
        ],
    )
    assert result.exit_code == 0
    assert "Trade History - TRD" in result.output
    assert "No trades found" not in result.output
    assert "Closed Trade Count" in result.output
    assert "Winning Trade Count" in result.output


def test_trade_history_invalid_date_filter(tmp_path, monkeypatch):
    db_path = tmp_path / "TRD.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))
    _seed_data(db_path)

    result = runner.invoke(
        app,
        ["report", "trade-history", "--account", "TRD", "--entry-date", "invalid"],
    )
    assert result.exit_code == 1
    assert "Invalid date expression" in result.output


def test_daily_notes_exact_formatter_output(tmp_path, monkeypatch):
    """End-to-end: events stored via shared formatters are rendered verbatim by the CLI."""
    db_path = tmp_path / "TRD.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))

    journal = Journal(account="TRD", db_path=db_path)
    trade = _record(5, closed=True, underlying="SPX")
    journal.record(trade)

    entry_line = format_entry_line(trade, occurred_at=trade.entered_at)
    gtc_line = format_gtc_line(trade, tp_percent=50, occurred_at=trade.entered_at)
    exit_line = format_exit_line(
        reason="GTC",
        occurred_at=trade.closed_at,
        exit_price=0.75,
        fees=0.50,
    )

    journal.append_event(
        TradeLogEntry(
            trade_id=trade.trade_id,
            event_type="ENTRY",
            occurred_at=trade.entered_at,
            line_text=entry_line,
            payload={"quantity": 1},
        )
    )
    journal.append_event(
        TradeLogEntry(
            trade_id=trade.trade_id,
            event_type="GTC",
            occurred_at=trade.entered_at,
            line_text=gtc_line,
            payload={"tp_percent": 50},
        )
    )
    journal.append_event(
        TradeLogEntry(
            trade_id=trade.trade_id,
            event_type="EXIT",
            occurred_at=trade.closed_at,
            line_text=exit_line,
            payload={"reason": "GTC"},
        )
    )

    result = runner.invoke(
        app,
        ["report", "daily-notes", "--account", "TRD", "--trade-number", trade.legacy_trade_num],
    )
    assert result.exit_code == 0

    # Rich may wrap long lines; normalise whitespace for comparison
    flat_output = " ".join(result.output.split())

    expected_header = format_daily_notes_header(trade)
    assert expected_header in flat_output
    # Assert each formatter-produced line appears verbatim (after whitespace normalisation)
    assert " ".join(entry_line.split()) in flat_output
    assert " ".join(gtc_line.split()) in flat_output
    assert " ".join(exit_line.split()) in flat_output
    assert re.search(
        r"\b\d{2}/\d{2}/\d{4}: EXIT #1 (GTC|MANUALLY|EXPIRED) CLOSED TRADE @\d+\.\d{2} - \$\d+\.\d{2}\b",
        flat_output,
    )


def test_weekly_flow_report_groups_conditions_and_non_standard(tmp_path, monkeypatch):
    db_path = tmp_path / "TRD.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))

    journal = Journal(account="TRD", db_path=db_path)

    def _pcs_trade(seq: int, entered: str, pnl: float | None, *, closed: bool = True) -> TradeRecord:
        trade = TradeRecord(
            spec_name="xsp_pcs_0dte_w1_none_0900_trds",
            environment="production",
            account="TRD",
            underlying="XSP",
            trade_type="PUT_CREDIT_SPREAD",
            expiration=entered[:10],
            short_put_strike=750.0,
            long_put_strike=748.0,
            short_call_strike=None,
            long_call_strike=None,
            outcome="FILLED",
            reason="",
            errors=[],
            entry_order_id=f"TRD-E-{seq}",
            entry_filled_price=-0.50,
            net_credit=0.50,
            tp_order_id="",
            tp_limit_price=None,
            tp_status="EXPIRED",
            realized_pnl=pnl,
            closed_at=(entered[:10] + "T16:00:00+00:00") if closed else None,
            exit_reason="EXPIRED" if closed else None,
            credit_received=50.0,
            quantity=1,
        )
        trade.entered_at = entered
        return trade

    # Above both strikes (max profit), standard flow.
    t1 = _pcs_trade(1, "2026-06-01T14:00:00+00:00", 50.0)
    journal.record(t1)
    journal.append_event(
        TradeLogEntry(
            trade_id=t1.trade_id,
            event_type="ADJ",
            occurred_at="2026-06-02T11:15:00+00:00",
            line_text="ORPHAN FLAGGED: test",
            payload={"reason": "ORPHAN"},
        )
    )
    journal.append_event(
        TradeLogEntry(
            trade_id=t1.trade_id,
            event_type="EXIT",
            occurred_at="2026-06-03T11:15:00+00:00",
            line_text="06/03/2026: EXIT #1 EXPIRED CLOSED TRADE @0.00 - $0.00",
            payload={"reason": "EXPIRED"},
        )
    )

    # Between strikes (partial), standard flow.
    t2 = _pcs_trade(2, "2026-06-02T14:00:00+00:00", -20.0)
    journal.record(t2)
    journal.append_event(
        TradeLogEntry(
            trade_id=t2.trade_id,
            event_type="ADJ",
            occurred_at="2026-06-03T11:15:00+00:00",
            line_text="ORPHAN FLAGGED: test",
            payload={"reason": "ORPHAN"},
        )
    )
    journal.append_event(
        TradeLogEntry(
            trade_id=t2.trade_id,
            event_type="EXIT",
            occurred_at="2026-06-04T11:15:00+00:00",
            line_text="06/04/2026: EXIT #1 EXPIRED CLOSED TRADE @0.00 - $0.00",
            payload={"reason": "EXPIRED"},
        )
    )

    # Below both strikes (max loss), non-standard flow (no ORPHAN).
    t3 = _pcs_trade(3, "2026-06-03T14:00:00+00:00", -150.0)
    journal.record(t3)
    journal.append_event(
        TradeLogEntry(
            trade_id=t3.trade_id,
            event_type="EXIT",
            occurred_at="2026-06-04T11:15:00+00:00",
            line_text="06/04/2026: EXIT #1 EXPIRED CLOSED TRADE @1.50 - $0.00",
            payload={"reason": "EXPIRED"},
        )
    )

    result = runner.invoke(
        app,
        [
            "report",
            "weekly-flow",
            "--account",
            "TRD",
            "--spec",
            "xsp_pcs_0dte_w1_none_0900_trds",
            "--from",
            "2026-06-01",
            "--to",
            "2026-06-05",
        ],
    )

    assert result.exit_code == 0
    assert "Weekly Flow Report" in result.output
    assert "Flow Pattern Counts" in result.output
    assert "Market Condition Buckets" in result.output
    assert "Non-Standard Flow Trades" in result.output
    assert "Above both strikes" in result.output
    assert "Between strikes" in result.output
    assert "Below both strikes" in result.output
    assert "ENTRY->ORPHAN->CLOSED" in result.output
    assert "ENTRY->CLOSED(EXPIRED)" in result.output