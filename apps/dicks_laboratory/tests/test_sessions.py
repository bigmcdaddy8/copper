from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from dicks_laboratory.anchored_vwap import VwapSourceMode, calculate_anchored_vwap
from dicks_laboratory.effective_tape import EffectiveTrade
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.sessions import AnchorKind, ES_GLOBEX, SessionState, cash_session_bounds, classify_es_session, resolve_anchor, select_session_trades, select_trades_from_anchor, session_coverage

UTC = timezone.utc
CT = ZoneInfo("America/Chicago")
INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)


def _trade(timestamp: datetime, price: str, sequence: int) -> TradeObservation:
    from uuid import UUID
    return TradeObservation(UUID(f"e5d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"), UUID("e5d7d1e4-3c38-4c16-9e04-e6f7c8a7c999"), sequence, INSTRUMENT, timestamp, Decimal(price), Decimal("1"))


def test_definition_identity_and_ordinary_schedule_limitation():
    assert ES_GLOBEX.session_id == "CME_EQUITY_INDEX_GLOBEX"
    assert ES_GLOBEX.policy_version == "CME_EQUITY_INDEX_STANDARD_V1"
    assert "holiday" in ES_GLOBEX.limitation.lower()


def test_sunday_evening_and_monday_daytime_share_following_trading_date():
    sunday_open = datetime(2026, 8, 23, 22, 0, tzinfo=UTC)
    monday_day = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
    assert classify_es_session(sunday_open).trading_date == date(2026, 8, 24)
    assert classify_es_session(monday_day).trading_date == date(2026, 8, 24)
    assert classify_es_session(sunday_open).state is SessionState.IN_SESSION


def test_maintenance_weekend_and_session_boundaries_are_explicit():
    before_break = classify_es_session(datetime(2026, 8, 24, 20, 59, 59, 999000, tzinfo=UTC))
    break_start = classify_es_session(datetime(2026, 8, 24, 21, 0, tzinfo=UTC))
    middle_break = classify_es_session(datetime(2026, 8, 24, 21, 30, tzinfo=UTC))
    break_end = classify_es_session(datetime(2026, 8, 24, 21, 59, 59, 999000, tzinfo=UTC))
    next_open = classify_es_session(datetime(2026, 8, 24, 22, 0, tzinfo=UTC))
    assert before_break.state is SessionState.IN_SESSION
    assert before_break.trading_date == date(2026, 8, 24)
    for membership in (break_start, middle_break, break_end):
        assert membership.state is SessionState.CLOSED_INTERVAL
        assert membership.trading_date is None
        assert membership.session_start_utc is None
        assert membership.session_end_utc is None
    assert next_open.state is SessionState.IN_SESSION
    assert next_open.trading_date == date(2026, 8, 25)
    assert classify_es_session(datetime(2026, 8, 22, 18, 0, tzinfo=UTC)).state is SessionState.OUTSIDE_SESSION
    assert classify_es_session(datetime(2026, 8, 21, 21, 0, tzinfo=UTC)).state is SessionState.OUTSIDE_SESSION


def test_dst_anchor_resolution_for_summer_and_winter():
    summer = resolve_anchor(AnchorKind.SESSION_OPEN, date(2026, 8, 24))
    winter = resolve_anchor(AnchorKind.SESSION_OPEN, date(2026, 1, 5))
    cash_summer = resolve_anchor(AnchorKind.US_CASH_OPEN, date(2026, 8, 24))
    cash_winter = resolve_anchor(AnchorKind.US_CASH_OPEN, date(2026, 1, 5))
    assert summer.anchor_timestamp_utc == datetime(2026, 8, 23, 22, 0, tzinfo=UTC)
    assert winter.anchor_timestamp_utc == datetime(2026, 1, 4, 23, 0, tzinfo=UTC)
    assert cash_summer.anchor_timestamp_utc == datetime(2026, 8, 24, 13, 30, tzinfo=UTC)
    assert cash_winter.anchor_timestamp_utc == datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    assert cash_session_bounds(date(2026, 8, 24))[1] == datetime(2026, 8, 24, 20, 0, tzinfo=UTC)


def test_anchor_selector_uses_half_open_boundary_and_never_shifts_anchor():
    anchor = resolve_anchor(AnchorKind.SESSION_OPEN, date(2026, 8, 24))
    trades = (_trade(datetime(2026, 8, 23, 22, 1, tzinfo=UTC), "100", 1), _trade(datetime(2026, 8, 23, 22, 2, tzinfo=UTC), "102", 2))
    selected = select_trades_from_anchor(trades, anchor.anchor_timestamp_utc, datetime(2026, 8, 23, 22, 2, tzinfo=UTC))
    coverage = session_coverage(trades, date(2026, 8, 24))
    result = calculate_anchored_vwap(trades, anchor, VwapSourceMode.CANONICAL_NEW_ONLY, "2026-08-24", coverage)
    assert selected == (trades[0],)
    assert select_session_trades(trades, date(2026, 8, 24)) == trades
    assert coverage.dataset_begins_after_session_start is True
    assert coverage.dataset_ends_before_session_end is True
    assert result.first_included_trade_timestamp == datetime(2026, 8, 23, 22, 1, tzinfo=UTC)
    assert result.vwap == Decimal("101")


def test_custom_anchor_requires_utc_and_calculates_exact_vwap():
    anchor = resolve_anchor(AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=datetime(2026, 8, 24, 14, 0, tzinfo=UTC))
    trades = (_trade(datetime(2026, 8, 24, 13, 59, tzinfo=UTC), "100", 1), _trade(datetime(2026, 8, 24, 14, 0, tzinfo=UTC), "102", 2))
    result = calculate_anchored_vwap(trades, anchor, VwapSourceMode.CANONICAL_NEW_ONLY)
    assert result.included_trade_count == 1
    assert result.vwap == Decimal("102")
    with pytest.raises(ValueError):
        resolve_anchor(AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=datetime(2026, 8, 24, 14, 0, tzinfo=CT))


def test_effective_tape_anchor_vwap_keeps_source_mode_explicit():
    anchor = resolve_anchor(AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=datetime(2026, 8, 24, 14, 0, tzinfo=UTC))
    effective = (
        EffectiveTrade(
            UUID("f5d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
            UUID("f5d7d1e4-3c38-4c16-9e04-e6f7c8a7c101"),
            INSTRUMENT,
            datetime(2026, 8, 24, 14, 0, tzinfo=UTC),
            Decimal("104"),
            Decimal("1"),
            1,
            1,
            1,
        ),
        EffectiveTrade(
            UUID("f5d7d1e4-3c38-4c16-9e04-e6f7c8a7c002"),
            UUID("f5d7d1e4-3c38-4c16-9e04-e6f7c8a7c102"),
            INSTRUMENT,
            datetime(2026, 8, 24, 14, 1, tzinfo=UTC),
            Decimal("102"),
            Decimal("1"),
            2,
            2,
        ),
    )
    result = calculate_anchored_vwap(effective, anchor, VwapSourceMode.EFFECTIVE_TAPE)
    assert result.source_mode is VwapSourceMode.EFFECTIVE_TAPE
    assert result.vwap == Decimal("103")