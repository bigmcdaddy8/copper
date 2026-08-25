"""Bounded DXLink Quote and Greeks collection for Tastytrade option symbols."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from websockets.sync.client import connect

_CHANNEL = 1
_QUOTE_FIELDS = (
    "eventType",
    "eventSymbol",
    "eventTime",
    "bidPrice",
    "askPrice",
    "bidSize",
    "askSize",
)
_GREEKS_FIELDS = (
    "eventType",
    "eventSymbol",
    "eventTime",
    "volatility",
    "delta",
    "gamma",
    "theta",
    "rho",
    "vega",
)
_TRADE_FIELDS = (
    "eventType",
    "eventSymbol",
    "eventTime",
    "price",
    "dayVolume",
    "size",
)
_SUMMARY_FIELDS = (
    "eventType",
    "eventSymbol",
    "eventTime",
    "openInterest",
    "dayOpenPrice",
    "dayHighPrice",
    "dayLowPrice",
    "prevDayClosePrice",
)
_SOURCE_EVENT_FIELDS: dict[str, tuple[str, ...]] = {
    "Trade": _TRADE_FIELDS,
    "Quote": _QUOTE_FIELDS,
    "TimeAndSale": (
        "eventType",
        "eventSymbol",
        "eventTime",
        "eventFlags",
        "index",
        "sequence",
        "time",
        "type",
        "tradeId",
        "exchangeCode",
        "price",
        "size",
        "bidPrice",
        "askPrice",
        "exchangeSaleConditions",
        "tradeThroughExempt",
        "aggressorSide",
        "spreadLeg",
        "extendedTradingHours",
        "validTick",
    ),
}


def scout_field_catalog() -> dict[str, object]:
    """Describe the DXLink event fields requested by the 0DTE put scout."""
    return {
        "events": {
            "Quote": list(_QUOTE_FIELDS),
            "Greeks": list(_GREEKS_FIELDS),
            "Trade": list(_TRADE_FIELDS),
            "Summary": list(_SUMMARY_FIELDS),
        },
        "report_columns": {
            "bid": "Quote.bidPrice",
            "ask": "Quote.askPrice",
            "delta": "Greeks.delta",
            "last_price": "Trade.price",
            "open_interest": "Summary.openInterest",
            "volatility": "Greeks.volatility",
        },
        "optional_columns": ["last_price", "open_interest"],
    }


class DxLinkError(RuntimeError):
    """Raised when a DXLink setup, authorization, or data frame is invalid."""


class _Socket(Protocol):
    def send(self, message: str) -> None: ...

    def recv(self, timeout: float | None = None) -> str: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class DxLinkSourceEvent:
    """One bounded, source-shaped DXLink event retained for semantic inspection."""

    event_type: str
    streamer_symbol: str
    fields: dict[str, object]
    received_at: datetime


@dataclass
class DxLinkSnapshot:
    """Latest quote and Greek values observed for one streamer symbol."""

    symbol: str
    quote_updated_at: datetime | None = None
    greeks_updated_at: datetime | None = None
    trade_updated_at: datetime | None = None
    summary_updated_at: datetime | None = None
    quote_received_at: datetime | None = None
    greeks_received_at: datetime | None = None
    trade_received_at: datetime | None = None
    summary_received_at: datetime | None = None
    bid: float | None = None
    ask: float | None = None
    last_price: float | None = None
    open_interest: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    rho: float | None = None
    vega: float | None = None
    volatility: float | None = None

    @property
    def is_complete(self) -> bool:
        return (
            self.bid is not None
            and self.ask is not None
            and self.delta is not None
            and self.gamma is not None
            and self.theta is not None
            and self.rho is not None
            and self.vega is not None
            and self.volatility is not None
        )


class DxLinkCollector:
    """Connect to DXLink and collect one Quote/Greeks snapshot per symbol."""

    def __init__(
        self,
        url: str,
        quote_token: str,
        socket_factory: Callable[[str], _Socket] = connect,
    ) -> None:
        self._url = url
        self._quote_token = quote_token
        self._socket_factory = socket_factory

    def collect(self, symbols: list[str], timeout_seconds: float = 5.0) -> dict[str, DxLinkSnapshot]:
        """Return Quote/Greeks snapshots and any available Trade/Summary values."""
        if not symbols:
            return {}

        socket = self._socket_factory(self._url)
        try:
            self._setup(socket, symbols)
            snapshots = {symbol: DxLinkSnapshot(symbol=symbol) for symbol in symbols}
            deadline = time.monotonic() + timeout_seconds
            optional_data_deadline: float | None = None
            while time.monotonic() < deadline:
                active_deadline = optional_data_deadline or deadline
                try:
                    frame = self._receive(
                        socket,
                        timeout=max(0.01, active_deadline - time.monotonic()),
                    )
                except DxLinkError:
                    if all(snapshot.is_complete for snapshot in snapshots.values()):
                        return snapshots
                    raise
                self._apply_frame(frame, snapshots)
                if not all(snapshot.is_complete for snapshot in snapshots.values()):
                    continue
                if all(_has_scout_fields(snapshot) for snapshot in snapshots.values()):
                    return snapshots
                if optional_data_deadline is None:
                    optional_data_deadline = min(deadline, time.monotonic() + 0.5)
                elif time.monotonic() >= optional_data_deadline:
                    return snapshots
            missing = [symbol for symbol, snapshot in snapshots.items() if not snapshot.is_complete]
            if not missing:
                return snapshots
            raise DxLinkError(f"DXLink did not return complete Quote/Greeks data for: {missing}")
        finally:
            socket.close()

    def _setup(self, socket: _Socket, symbols: list[str]) -> None:
        self._send(
            socket,
            {
                "type": "SETUP",
                "channel": 0,
                "version": "0.1-K9/1.0",
                "keepaliveTimeout": 60,
                "acceptKeepaliveTimeout": 60,
            },
        )
        self._expect_type(self._receive(socket), "SETUP")
        self._expect_auth_state(self._receive(socket), "UNAUTHORIZED")

        self._send(socket, {"type": "AUTH", "channel": 0, "token": self._quote_token})
        self._expect_auth_state(self._receive(socket), "AUTHORIZED")

        self._send(
            socket,
            {
                "type": "CHANNEL_REQUEST",
                "channel": _CHANNEL,
                "service": "FEED",
                "parameters": {"contract": "AUTO"},
            },
        )
        self._expect_type(self._receive(socket), "CHANNEL_OPENED")

        self._send(
            socket,
            {
                "type": "FEED_SETUP",
                "channel": _CHANNEL,
                "acceptAggregationPeriod": 0.1,
                "acceptDataFormat": "COMPACT",
                "acceptEventFields": {
                    "Quote": list(_QUOTE_FIELDS),
                    "Greeks": list(_GREEKS_FIELDS),
                    "Trade": list(_TRADE_FIELDS),
                    "Summary": list(_SUMMARY_FIELDS),
                },
            },
        )
        self._expect_type(self._receive(socket), "FEED_CONFIG")

        subscriptions = [
            {"type": event_type, "symbol": symbol}
            for symbol in symbols
            for event_type in ("Quote", "Greeks", "Trade", "Summary")
        ]
        self._send(
            socket,
            {"type": "FEED_SUBSCRIPTION", "channel": _CHANNEL, "reset": True, "add": subscriptions},
        )

    @staticmethod
    def _send(socket: _Socket, message: dict) -> None:
        socket.send(json.dumps(message))

    @staticmethod
    def _receive(socket: _Socket, timeout: float | None = None) -> dict:
        try:
            message = socket.recv(timeout=timeout)
        except TimeoutError as exc:
            raise DxLinkError("DXLink timed out while waiting for a response.") from exc
        except DxLinkError:
            raise
        except Exception as exc:
            raise DxLinkError(f"DXLink connection error while receiving: {exc}") from exc
        try:
            frame = json.loads(message)
        except json.JSONDecodeError as exc:
            raise DxLinkError("DXLink returned invalid JSON.") from exc
        if not isinstance(frame, dict):
            raise DxLinkError("DXLink returned a non-object JSON frame.")
        return frame

    @staticmethod
    def _expect_type(frame: dict, expected: str) -> None:
        if frame.get("type") != expected:
            raise DxLinkError(f"Expected DXLink {expected} frame, got {frame.get('type')!r}.")

    def _expect_auth_state(self, frame: dict, expected: str) -> None:
        self._expect_type(frame, "AUTH_STATE")
        if frame.get("state") != expected:
            raise DxLinkError(
                f"Expected DXLink authorization state {expected!r}, got {frame.get('state')!r}."
            )

    @staticmethod
    def _apply_frame(frame: dict, snapshots: dict[str, DxLinkSnapshot]) -> None:
        if frame.get("type") != "FEED_DATA":
            return
        data = frame.get("data")
        if not isinstance(data, list) or len(data) != 2:
            raise DxLinkError("DXLink FEED_DATA frame had an unsupported shape.")
        event_type, values = data
        if event_type == "Quote":
            DxLinkCollector._apply_events(values, _QUOTE_FIELDS, snapshots, event_type)
        elif event_type == "Greeks":
            DxLinkCollector._apply_events(values, _GREEKS_FIELDS, snapshots, event_type)
        elif event_type == "Trade":
            DxLinkCollector._apply_events(values, _TRADE_FIELDS, snapshots, event_type)
        elif event_type == "Summary":
            DxLinkCollector._apply_events(values, _SUMMARY_FIELDS, snapshots, event_type)

    @staticmethod
    def _apply_events(
        values: object,
        fields: tuple[str, ...],
        snapshots: dict[str, DxLinkSnapshot],
        event_type: str,
    ) -> None:
        if not isinstance(values, list) or len(values) % len(fields) != 0:
            raise DxLinkError(f"DXLink {event_type} data did not match the configured compact fields.")
        for start in range(0, len(values), len(fields)):
            event = dict(zip(fields, values[start : start + len(fields)], strict=True))
            symbol = event["eventSymbol"]
            if not isinstance(symbol, str) or symbol not in snapshots:
                continue
            snapshot = snapshots[symbol]
            event_time = _event_time_or_none(event["eventTime"])
            received_at = datetime.now(tz=timezone.utc)
            if event_type == "Quote":
                snapshot.quote_updated_at = event_time
                snapshot.quote_received_at = received_at
                snapshot.bid = _number(event["bidPrice"])
                snapshot.ask = _number(event["askPrice"])
            elif event_type == "Greeks":
                snapshot.greeks_updated_at = event_time
                snapshot.greeks_received_at = received_at
                snapshot.volatility = _number(event["volatility"])
                snapshot.delta = _number(event["delta"])
                snapshot.gamma = _number(event["gamma"])
                snapshot.theta = _number(event["theta"])
                snapshot.rho = _number(event["rho"])
                snapshot.vega = _number(event["vega"])
            elif event_type == "Trade":
                snapshot.trade_updated_at = event_time
                snapshot.trade_received_at = received_at
                snapshot.last_price = _optional_number(event["price"])
            else:
                snapshot.summary_updated_at = event_time
                snapshot.summary_received_at = received_at
                snapshot.open_interest = _optional_number(event["openInterest"])


def _number(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise DxLinkError(f"DXLink event contained a non-numeric value: {value!r}.") from exc
    if not math.isfinite(number):
        raise DxLinkError(f"DXLink event contained a non-finite value: {value!r}.")
    return number


def _optional_number(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _event_time_or_none(value: object) -> datetime | None:
    try:
        milliseconds = float(value)
    except (TypeError, ValueError, OSError) as exc:
        raise DxLinkError(f"DXLink event contained an invalid event time: {value!r}.") from exc
    if milliseconds <= 0:
        return None
    try:
        return datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc)
    except (ValueError, OSError) as exc:
        raise DxLinkError(f"DXLink event contained an invalid event time: {value!r}.") from exc


def _has_scout_fields(snapshot: DxLinkSnapshot) -> bool:
    return snapshot.last_price is not None and snapshot.open_interest is not None


class DxLinkSourceCollector:
    """Collect bounded raw DXLink events without normalizing them into market facts."""

    def __init__(
        self,
        url: str,
        quote_token: str,
        socket_factory: Callable[[str], _Socket] = connect,
    ) -> None:
        self._url = url
        self._quote_token = quote_token
        self._socket_factory = socket_factory

    def collect(
        self,
        streamer_symbol: str,
        event_types: tuple[str, ...],
        duration_seconds: float,
        max_events: int,
        on_event: Callable[[DxLinkSourceEvent], None] | None = None,
        on_connected: Callable[[], None] | None = None,
        retain_events: bool = True,
    ) -> tuple[DxLinkSourceEvent, ...]:
        """Return at most *max_events* raw source events within a bounded duration."""
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive.")
        if max_events < 1:
            raise ValueError("max_events must be positive.")
        if not event_types:
            raise ValueError("At least one event type is required.")

        socket = self._socket_factory(self._url)
        try:
            self._setup(socket, streamer_symbol, event_types)
            fields_by_type = self._read_feed_config(
                socket,
                {event_type: _SOURCE_EVENT_FIELDS[event_type] for event_type in event_types},
            )
            if on_connected is not None:
                on_connected()
            deadline = time.monotonic() + duration_seconds
            next_keepalive = time.monotonic() + 20.0
            events: list[DxLinkSourceEvent] = []
            event_count = 0
            while event_count < max_events and time.monotonic() < deadline:
                timeout = min(max(0.01, deadline - time.monotonic()), max(0.01, next_keepalive - time.monotonic()))
                try:
                    frame = DxLinkCollector._receive(socket, timeout=timeout)
                except DxLinkError as exc:
                    if "timed out" not in str(exc).lower():
                        raise
                    DxLinkCollector._send(socket, {"type": "KEEPALIVE", "channel": 0})
                    next_keepalive = time.monotonic() + 20.0
                    continue
                for event in self._source_events(frame, fields_by_type, streamer_symbol):
                    event_count += 1
                    if on_event is not None:
                        on_event(event)
                    if retain_events:
                        events.append(event)
                    if event_count >= max_events:
                        break
                if time.monotonic() >= next_keepalive:
                    DxLinkCollector._send(socket, {"type": "KEEPALIVE", "channel": 0})
                    next_keepalive = time.monotonic() + 20.0
            return tuple(events[:max_events])
        except DxLinkError as exc:
            if "timed out" in str(exc).lower():
                return tuple()
            raise
        finally:
            socket.close()

    def _setup(self, socket: _Socket, streamer_symbol: str, event_types: tuple[str, ...]) -> None:
        DxLinkCollector._send(
            socket,
            {
                "type": "SETUP",
                "channel": 0,
                "version": "0.1-DICKS_LAB/0.1",
                "keepaliveTimeout": 60,
                "acceptKeepaliveTimeout": 60,
            },
        )
        DxLinkCollector._expect_type(DxLinkCollector._receive(socket), "SETUP")
        self._expect_auth_state(DxLinkCollector._receive(socket), "UNAUTHORIZED")
        DxLinkCollector._send(socket, {"type": "AUTH", "channel": 0, "token": self._quote_token})
        self._expect_auth_state(DxLinkCollector._receive(socket), "AUTHORIZED")
        DxLinkCollector._send(
            socket,
            {"type": "CHANNEL_REQUEST", "channel": _CHANNEL, "service": "FEED", "parameters": {"contract": "AUTO"}},
        )
        DxLinkCollector._expect_type(DxLinkCollector._receive(socket), "CHANNEL_OPENED")
        fields = {event_type: list(_SOURCE_EVENT_FIELDS[event_type]) for event_type in event_types}
        DxLinkCollector._send(
            socket,
            {
                "type": "FEED_SETUP",
                "channel": _CHANNEL,
                "acceptAggregationPeriod": 0.0,
                "acceptDataFormat": "COMPACT",
                "acceptEventFields": fields,
            },
        )
        DxLinkCollector._send(
            socket,
            {
                "type": "FEED_SUBSCRIPTION",
                "channel": _CHANNEL,
                "reset": True,
                "add": [{"type": event_type, "symbol": streamer_symbol} for event_type in event_types],
            },
        )

    @staticmethod
    def _expect_auth_state(frame: dict, expected: str) -> None:
        DxLinkCollector._expect_type(frame, "AUTH_STATE")
        if frame.get("state") != expected:
            raise DxLinkError(
                f"Expected DXLink authorization state {expected!r}, got {frame.get('state')!r}."
            )

    @staticmethod
    def _read_feed_config(
        socket: _Socket,
        requested_fields: dict[str, tuple[str, ...]],
    ) -> dict[str, tuple[str, ...]]:
        while True:
            frame = DxLinkCollector._receive(socket)
            if frame.get("type") == "ERROR":
                raise DxLinkError(str(frame.get("message") or frame.get("error") or "DXLink error."))
            if frame.get("type") != "FEED_CONFIG":
                continue
            raw_fields = frame.get("eventFields") or frame.get("acceptEventFields")
            if not isinstance(raw_fields, dict):
                return requested_fields
            return {
                event_type: tuple(fields)
                for event_type, fields in raw_fields.items()
                if isinstance(event_type, str) and isinstance(fields, list) and all(isinstance(field, str) for field in fields)
            }

    @staticmethod
    def _source_events(
        frame: dict,
        fields_by_type: dict[str, tuple[str, ...]],
        streamer_symbol: str,
    ) -> list[DxLinkSourceEvent]:
        if frame.get("type") == "ERROR":
            raise DxLinkError(str(frame.get("message") or frame.get("error") or "DXLink error."))
        if frame.get("type") != "FEED_DATA":
            return []
        data = frame.get("data")
        if not isinstance(data, list) or len(data) != 2:
            raise DxLinkError("DXLink FEED_DATA frame had an unsupported shape.")
        event_type, values = data
        fields = fields_by_type.get(event_type) if isinstance(event_type, str) else None
        if fields is None or not isinstance(values, list) or len(values) % len(fields) != 0:
            raise DxLinkError("DXLink source event data did not match FEED_CONFIG fields.")
        result = []
        for start in range(0, len(values), len(fields)):
            raw = dict(zip(fields, values[start : start + len(fields)], strict=True))
            symbol = raw.get("eventSymbol")
            result.append(
                DxLinkSourceEvent(
                    event_type=event_type,
                    streamer_symbol=symbol if isinstance(symbol, str) else streamer_symbol,
                    fields=raw,
                    received_at=datetime.now(tz=timezone.utc),
                )
            )
        return result