"""Tests for Journal SQLite persistence (CL-0020)."""
from __future__ import annotations

import pytest
from captains_log.journal import Journal
from captains_log.models import TradeRecord


def _filled(trade_id: str | None = None, **kwargs) -> TradeRecord:
    defaults = dict(
        spec_name="spx_ic_test",
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
        errors=[],
        entry_order_id="HD-000042",
        entry_filled_price=1.10,
        net_credit=1.10,
        tp_order_id="HD-000043",
        tp_limit_price=0.75,
        tp_status="PLACED",
    )
    defaults.update(kwargs)
    t = TradeRecord(**defaults)
    if trade_id:
        t.trade_id = trade_id
    return t


@pytest.fixture
def journal(tmp_path) -> Journal:
    return Journal(db_path=tmp_path / "test_trades.db")


def test_journal_creates_db_file(tmp_path):
    db = tmp_path / "trades.db"
    Journal(db_path=db)
    assert db.exists()


def test_record_filled_trade(journal):
    t = _filled()
    journal.record(t)
    fetched = journal.get_trade(t.trade_id)
    assert fetched is not None
    assert fetched.spec_name == "spx_ic_test"
    assert fetched.outcome == "FILLED"
    assert fetched.entry_filled_price == pytest.approx(1.10)
    assert fetched.short_put_strike == pytest.approx(5800.0)
    assert fetched.long_put_strike == pytest.approx(5795.0)
    assert fetched.short_call_strike == pytest.approx(5840.0)
    assert fetched.long_call_strike == pytest.approx(5845.0)
    assert fetched.tp_limit_price == pytest.approx(0.75)
    assert fetched.errors == []


def test_record_skipped_trade(journal):
    t = TradeRecord(
        spec_name="spx_ic_test",
        environment="holodeck",
        underlying="SPX",
        trade_type="IRON_CONDOR",
        expiration="",
        short_put_strike=None,
        long_put_strike=None,
        short_call_strike=None,
        long_call_strike=None,
        outcome="SKIPPED",
        reason="Account below minimum.",
    )
    journal.record(t)
    fetched = journal.get_trade(t.trade_id)
    assert fetched is not None
    assert fetched.outcome == "SKIPPED"
    assert fetched.short_put_strike is None
    assert fetched.entry_filled_price is None
    assert "minimum" in fetched.reason


def test_record_idempotent(journal):
    t = _filled()
    journal.record(t)
    journal.record(t)  # should not raise
    assert len(journal.list_trades()) == 1


def test_list_trades_all(journal):
    journal.record(_filled())
    journal.record(_filled())
    assert len(journal.list_trades()) == 2


def test_list_trades_by_date(journal):
    t1 = _filled()
    t1.entered_at = "2026-01-05T10:00:00+00:00"
    t2 = _filled()
    t2.entered_at = "2026-01-06T10:00:00+00:00"
    journal.record(t1)
    journal.record(t2)
    results = journal.list_trades(date="2026-01-05")
    assert len(results) == 1
    assert results[0].entered_at.startswith("2026-01-05")


def test_list_trades_by_outcome(journal):
    journal.record(_filled(outcome="FILLED"))
    journal.record(_filled(outcome="SKIPPED",
                           entry_order_id="", entry_filled_price=None,
                           net_credit=None, tp_order_id="",
                           tp_limit_price=None, tp_status="UNKNOWN"))
    filled = journal.list_trades(outcome="FILLED")
    assert all(t.outcome == "FILLED" for t in filled)
    assert len(filled) == 1


def test_account_stored_and_retrieved(journal):
    t = _filled(account="TRDS")
    journal.record(t)
    fetched = journal.get_trade(t.trade_id)
    assert fetched.account == "TRDS"


def test_list_trades_by_account(journal):
    journal.record(_filled(account="TRD"))
    journal.record(_filled(account="HD"))
    trd = journal.list_trades(account="TRD")
    assert len(trd) == 1
    assert trd[0].account == "TRD"
    hd = journal.list_trades(account="HD")
    assert len(hd) == 1
    assert hd[0].account == "HD"


def test_update_tp_fill(journal):
    t = _filled()
    journal.record(t)
    journal.update_tp_fill(t.trade_id, tp_fill_price=0.75, realized_pnl=35.0)
    fetched = journal.get_trade(t.trade_id)
    assert fetched.tp_fill_price == pytest.approx(0.75)
    assert fetched.realized_pnl == pytest.approx(35.0)
    assert fetched.tp_status == "FILLED"


def test_update_expiration(journal):
    t = _filled()
    journal.record(t)
    journal.update_expiration(t.trade_id, realized_pnl=110.0)
    fetched = journal.get_trade(t.trade_id)
    assert fetched.realized_pnl == pytest.approx(110.0)
    assert fetched.tp_status == "EXPIRED"
    assert fetched.tp_fill_price is None


# ── legacy_trade_num allocation ───────────────────────────────────────────────

def test_filled_trade_gets_legacy_trade_num(journal):
    t = _filled()
    journal.record(t)
    fetched = journal.get_trade(t.trade_id)
    assert fetched.legacy_trade_num is not None
    assert fetched.legacy_trade_num == "TRD_00001_SIC"


def test_unfilled_trade_has_no_legacy_trade_num(journal):
    t = _filled(entry_filled_price=None, outcome="SKIPPED",
                entry_order_id="", net_credit=None,
                tp_order_id="", tp_limit_price=None, tp_status="UNKNOWN")
    journal.record(t)
    fetched = journal.get_trade(t.trade_id)
    assert fetched.legacy_trade_num is None


def test_legacy_trade_nums_are_sequential(journal):
    t1 = _filled()
    t2 = _filled()
    journal.record(t1)
    journal.record(t2)
    f1 = journal.get_trade(t1.trade_id)
    f2 = journal.get_trade(t2.trade_id)
    assert f1.legacy_trade_num == "TRD_00001_SIC"
    assert f2.legacy_trade_num == "TRD_00002_SIC"


def test_record_idempotent_does_not_reallocate_sequence(journal):
    t = _filled()
    journal.record(t)
    journal.record(t)  # second call is a no-op
    assert len(journal.list_trades()) == 1
    fetched = journal.get_trade(t.trade_id)
    assert fetched.legacy_trade_num == "TRD_00001_SIC"
    # Sequence should only have been incremented once; next new trade gets 00002.
    t2 = _filled()
    journal.record(t2)
    assert journal.get_trade(t2.trade_id).legacy_trade_num == "TRD_00002_SIC"


def test_legacy_trade_num_reflects_account(tmp_path):
    journal_trds = Journal(db_path=tmp_path / "TRDS.db", account="TRDS")
    t = _filled(account="TRDS", trade_type="PUT_CREDIT_SPREAD")
    journal_trds.record(t)
    fetched = journal_trds.get_trade(t.trade_id)
    assert fetched.legacy_trade_num == "TRDS_00001_PCS"
