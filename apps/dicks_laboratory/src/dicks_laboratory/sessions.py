"""Ordinary CME equity-index session and Laboratory cash-window policies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from enum import StrEnum
from zoneinfo import ZoneInfo

from dicks_laboratory.models import TradeObservation

_CT = ZoneInfo("America/Chicago")


class SessionState(StrEnum):
    IN_SESSION = "IN_SESSION"
    CLOSED_INTERVAL = "CLOSED_INTERVAL"
    OUTSIDE_SESSION = "OUTSIDE_SESSION"


class AnchorKind(StrEnum):
    SESSION_OPEN = "SESSION_OPEN"
    US_CASH_OPEN = "US_CASH_OPEN"
    CUSTOM_TIMESTAMP = "CUSTOM_TIMESTAMP"


@dataclass(frozen=True)
class FuturesSessionDefinition:
    session_id: str
    policy_version: str
    timezone_name: str
    open_time_local: time
    close_time_local: time
    maintenance_start_local: time
    maintenance_end_local: time
    limitation: str


@dataclass(frozen=True)
class SessionMembership:
    session_definition_id: str
    policy_version: str
    event_timestamp: datetime
    trading_date: date | None
    session_start_utc: datetime | None
    session_end_utc: datetime | None
    state: SessionState


@dataclass(frozen=True)
class VwapAnchor:
    kind: AnchorKind
    policy_id: str
    policy_version: str
    anchor_timestamp_utc: datetime


@dataclass(frozen=True)
class SessionCoverageWindow:
    session_start_utc: datetime
    session_end_utc: datetime
    dataset_first_event_utc: datetime | None
    dataset_last_event_utc: datetime | None
    dataset_begins_after_session_start: bool
    dataset_ends_before_session_end: bool


ES_GLOBEX = FuturesSessionDefinition(
    session_id="CME_EQUITY_INDEX_GLOBEX",
    policy_version="CME_EQUITY_INDEX_STANDARD_V1",
    timezone_name="America/Chicago",
    open_time_local=time(17, 0),
    close_time_local=time(16, 0),
    maintenance_start_local=time(16, 0),
    maintenance_end_local=time(17, 0),
    limitation="Ordinary CME schedule only; holiday and early-close overrides are not modeled.",
)
US_CASH_SESSION_ID = "US_CASH_SESSION"
US_CASH_SESSION_VERSION = "US_CASH_SESSION_V1"
_CASH_OPEN = time(8, 30)
_CASH_CLOSE = time(15, 0)


def classify_es_session(event_timestamp: datetime, definition: FuturesSessionDefinition = ES_GLOBEX) -> SessionMembership:
    """Classify a UTC event under the ordinary CME equity-index session rule."""
    _require_utc(event_timestamp)
    local = event_timestamp.astimezone(_CT)
    local_date = local.date()
    local_time = local.timetz().replace(tzinfo=None)
    weekday = local.weekday()
    if weekday == 5 or (weekday == 6 and local_time < definition.open_time_local):
        return _outside(definition, event_timestamp)
    if weekday == 4 and local_time >= definition.close_time_local:
        return _outside(definition, event_timestamp)
    if local_time >= definition.maintenance_start_local and local_time < definition.maintenance_end_local:
        return _closed_interval(definition, event_timestamp)
    trading_date = local_date + timedelta(days=1) if local_time >= definition.open_time_local else local_date
    return _membership(definition, event_timestamp, trading_date, SessionState.IN_SESSION)


def resolve_anchor(kind: AnchorKind, trading_date: date | None = None, custom_timestamp: datetime | None = None) -> VwapAnchor:
    """Resolve a versioned analytical anchor to an explicit UTC instant."""
    if kind is AnchorKind.CUSTOM_TIMESTAMP:
        if custom_timestamp is None:
            raise ValueError("CUSTOM_TIMESTAMP anchor requires custom_timestamp.")
        _require_utc(custom_timestamp)
        return VwapAnchor(kind, "CUSTOM_TIMESTAMP", "CUSTOM_TIMESTAMP_V1", custom_timestamp)
    if trading_date is None:
        raise ValueError("Session and cash anchors require trading_date.")
    if kind is AnchorKind.SESSION_OPEN:
        local = datetime.combine(trading_date - timedelta(days=1), ES_GLOBEX.open_time_local, tzinfo=_CT)
        return VwapAnchor(kind, ES_GLOBEX.session_id, ES_GLOBEX.policy_version, local.astimezone(timezone.utc))
    if kind is AnchorKind.US_CASH_OPEN:
        local = datetime.combine(trading_date, _CASH_OPEN, tzinfo=_CT)
        return VwapAnchor(kind, US_CASH_SESSION_ID, US_CASH_SESSION_VERSION, local.astimezone(timezone.utc))
    raise ValueError(f"Unsupported anchor kind: {kind}")


def select_session_trades(
    trades: tuple[TradeObservation, ...],
    trading_date: date,
    definition: FuturesSessionDefinition = ES_GLOBEX,
) -> tuple[TradeObservation, ...]:
    """Select retained canonical trades currently active in the named session."""
    return tuple(trade for trade in trades if classify_es_session(trade.event_timestamp, definition).trading_date == trading_date and classify_es_session(trade.event_timestamp, definition).state is SessionState.IN_SESSION)


def select_trades_from_anchor(
    trades: tuple[TradeObservation, ...],
    anchor_timestamp_utc: datetime,
    end_timestamp_utc: datetime | None = None,
) -> tuple[TradeObservation, ...]:
    """Select retained trades in the half-open interval [anchor, end)."""
    _require_utc(anchor_timestamp_utc)
    if end_timestamp_utc is not None:
        _require_utc(end_timestamp_utc)
    return tuple(
        trade for trade in trades
        if trade.event_timestamp >= anchor_timestamp_utc and (end_timestamp_utc is None or trade.event_timestamp < end_timestamp_utc)
    )


def session_coverage(
    trades: tuple[TradeObservation, ...],
    trading_date: date,
    definition: FuturesSessionDefinition = ES_GLOBEX,
) -> SessionCoverageWindow:
    start = resolve_anchor(AnchorKind.SESSION_OPEN, trading_date).anchor_timestamp_utc
    end_local = datetime.combine(trading_date, definition.close_time_local, tzinfo=_CT)
    end = end_local.astimezone(timezone.utc)
    first = trades[0].event_timestamp if trades else None
    last = trades[-1].event_timestamp if trades else None
    return SessionCoverageWindow(start, end, first, last, first is not None and first > start, last is not None and last < end)


def cash_session_bounds(trading_date: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(trading_date, _CASH_OPEN, tzinfo=_CT).astimezone(timezone.utc),
        datetime.combine(trading_date, _CASH_CLOSE, tzinfo=_CT).astimezone(timezone.utc),
    )


def _membership(definition: FuturesSessionDefinition, event_timestamp: datetime, trading_date: date, state: SessionState) -> SessionMembership:
    start = resolve_anchor(AnchorKind.SESSION_OPEN, trading_date).anchor_timestamp_utc
    end = datetime.combine(trading_date, definition.close_time_local, tzinfo=_CT).astimezone(timezone.utc)
    return SessionMembership(definition.session_id, definition.policy_version, event_timestamp, trading_date, start, end, state)


def _outside(definition: FuturesSessionDefinition, event_timestamp: datetime) -> SessionMembership:
    return SessionMembership(definition.session_id, definition.policy_version, event_timestamp, None, None, None, SessionState.OUTSIDE_SESSION)


def _closed_interval(definition: FuturesSessionDefinition, event_timestamp: datetime) -> SessionMembership:
    return SessionMembership(definition.session_id, definition.policy_version, event_timestamp, None, None, None, SessionState.CLOSED_INTERVAL)


def _require_utc(timestamp: datetime) -> None:
    if timestamp.tzinfo is not timezone.utc:
        raise ValueError("Session policy requires timezone-aware UTC timestamps.")