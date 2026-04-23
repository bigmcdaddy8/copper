"""Tests for TradeRecord model (CL-0010)."""
from __future__ import annotations

import pytest
from captains_log.models import TradeRecord, build_legacy_trade_num, TRADE_TYPE_LEGACY_CODES


def _filled_record(**kwargs) -> TradeRecord:
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
    return TradeRecord(**defaults)


def test_trade_record_defaults():
    t = _filled_record()
    assert t.trade_id, "trade_id should be auto-populated"
    assert "T" in t.entered_at or "+" in t.entered_at, "entered_at should be ISO UTC"
    assert t.tp_fill_price is None
    assert t.realized_pnl is None
    assert t.account == "TRD"


def test_trade_record_filled_fields():
    t = _filled_record(tp_fill_price=0.75, realized_pnl=35.0)
    assert t.entry_filled_price == 1.10
    assert t.net_credit == 1.10
    assert t.short_put_strike == 5800.0
    assert t.long_put_strike == 5795.0
    assert t.short_call_strike == 5840.0
    assert t.long_call_strike == 5845.0
    assert t.tp_fill_price == 0.75
    assert t.realized_pnl == 35.0


def test_trade_record_skipped_fields():
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
    assert t.entry_filled_price is None
    assert t.net_credit is None
    assert t.tp_status == "UNKNOWN"


def test_trade_id_unique():
    a = _filled_record()
    b = _filled_record()
    assert a.trade_id != b.trade_id


def test_errors_is_list():
    t = _filled_record()
    assert isinstance(t.errors, list)
    assert len(t.errors) == 0


# ── build_legacy_trade_num ────────────────────────────────────────────────────

def test_build_legacy_trade_num_format():
    assert build_legacy_trade_num("TRD", 1, "PUT_CREDIT_SPREAD") == "TRD_00001_PCS"


def test_build_legacy_trade_num_zero_padding():
    assert build_legacy_trade_num("TRDS", 42, "IRON_CONDOR") == "TRDS_00042_SIC"


def test_build_legacy_trade_num_large_seq():
    assert build_legacy_trade_num("HD", 99999, "CALL_CREDIT_SPREAD") == "HD_99999_CCS"


def test_build_legacy_trade_num_unknown_type_raises():
    with pytest.raises(ValueError, match="No legacy code"):
        build_legacy_trade_num("TRD", 1, "UNKNOWN_TYPE")


def test_all_known_trade_types_have_codes():
    for trade_type in ("IRON_CONDOR", "PUT_CREDIT_SPREAD", "CALL_CREDIT_SPREAD",
                       "NAKED_SHORT_PUT", "NAKED_SHORT_CALL"):
        assert trade_type in TRADE_TYPE_LEGACY_CODES


def test_legacy_trade_num_defaults_to_none():
    t = _filled_record()
    assert t.legacy_trade_num is None
