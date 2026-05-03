from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from typer.testing import CliRunner

from bic.models import Order, ORDER_STATUS_FILLED, Position
from captains_log import Journal, TradeRecord
from K9.cli import app


runner = CliRunner()


@dataclass
class _FakeBroker:
    order: Order
    positions: list[Position] = field(default_factory=list)

    def get_order(self, _order_id: str) -> Order:
        return self.order

    def get_positions(self) -> list[Position]:
        return self.positions


def _make_filled_trade(*, tp_order_id: str = "", tp_limit_price: float | None = None) -> TradeRecord:
    return TradeRecord(
        spec_name="xsp_pcs_0dte_w2_none_0900_trds",
        environment="sandbox",
        account="TRDS",
        underlying="XSP",
        trade_type="PUT_CREDIT_SPREAD",
        expiration="2026-01-05",
        short_put_strike=580.0,
        long_put_strike=578.0,
        short_call_strike=None,
        long_call_strike=None,
        outcome="FILLED",
        reason="",
        entry_order_id="entry-1",
        entry_filled_price=1.00,
        net_credit=1.00,
        tp_order_id=tp_order_id,
        tp_limit_price=tp_limit_price,
        tp_status="PLACED" if tp_order_id else "NONE",
        quantity=1,
        credit_received=100.0,
    )


def test_close_dry_run_leaves_trade_unmodified(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))

    journal = Journal(account="TRDS")
    trade = _make_filled_trade(tp_order_id="")
    journal.record(trade)

    monkeypatch.setattr(
        "K9.cli._create_broker_for_account",
        lambda account: _FakeBroker(
            Order(order_id="unused", status=ORDER_STATUS_FILLED, filled_price=0.25)
        ),
    )

    result = runner.invoke(app, ["close", "--account", "TRDS", "--dry-run"])
    assert result.exit_code == 0

    saved = journal.get_trade(trade.trade_id)
    assert saved is not None
    assert saved.closed_at is None
    assert saved.exit_reason is None


def test_close_updates_tp_fill_and_writes_exit_event(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))

    journal = Journal(account="TRDS")
    trade = _make_filled_trade(tp_order_id="tp-1", tp_limit_price=0.30)
    journal.record(trade)

    monkeypatch.setattr(
        "K9.cli._create_broker_for_account",
        lambda account: _FakeBroker(
            Order(order_id="tp-1", status=ORDER_STATUS_FILLED, filled_price=0.30)
        ),
    )

    result = runner.invoke(app, ["close", "--account", "TRDS"])
    assert result.exit_code == 0

    saved = journal.get_trade(trade.trade_id)
    assert saved is not None
    assert saved.closed_at is not None
    assert saved.exit_reason == "GTC"
    assert saved.tp_fill_price == 0.30
    assert saved.realized_pnl == 70.0

    events = journal.list_events(trade.trade_id)
    assert any(e.event_type == "EXIT" for e in events)


def test_close_marks_stale_none_exit_trade_orphan(tmp_path, monkeypatch):
    db_path = tmp_path / "trades.db"
    monkeypatch.setenv("CL_DB_PATH", str(db_path))

    journal = Journal(account="TRDS")
    trade = _make_filled_trade(tp_order_id="")
    trade.entered_at = "2026-01-05T15:30:00+00:00"
    journal.record(trade)

    monkeypatch.setattr(
        "K9.cli._create_broker_for_account",
        lambda account: _FakeBroker(
            Order(order_id="unused", status=ORDER_STATUS_FILLED, filled_price=0.25),
            positions=[],
        ),
    )
    monkeypatch.setattr(
        "K9.cli.datetime",
        type(
            "_DT",
            (),
            {
                "now": staticmethod(
                    lambda tz=None: datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc)
                ),
                "fromisoformat": staticmethod(datetime.fromisoformat),
            },
        ),
    )

    result = runner.invoke(app, ["close", "--account", "TRDS"])
    assert result.exit_code == 2

    saved = journal.get_trade(trade.trade_id)
    assert saved is not None
    assert saved.closed_at is None
    assert saved.tp_status == "ORPHAN"
    assert "ORPHAN" in (saved.reason or "")

    events = journal.list_events(trade.trade_id)
    assert any(e.event_type == "ADJ" and "ORPHAN" in e.line_text for e in events)
