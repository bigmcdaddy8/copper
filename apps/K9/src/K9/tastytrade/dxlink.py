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


@dataclass
class DxLinkSnapshot:
    """Latest quote and Greek values observed for one streamer symbol."""

    symbol: str
    updated_at: datetime | None = None
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
            snapshot.updated_at = _event_time(event["eventTime"])
            if event_type == "Quote":
                snapshot.bid = _number(event["bidPrice"])
                snapshot.ask = _number(event["askPrice"])
            elif event_type == "Greeks":
                snapshot.volatility = _number(event["volatility"])
                snapshot.delta = _number(event["delta"])
                snapshot.gamma = _number(event["gamma"])
                snapshot.theta = _number(event["theta"])
                snapshot.rho = _number(event["rho"])
                snapshot.vega = _number(event["vega"])
            elif event_type == "Trade":
                snapshot.last_price = _optional_number(event["price"])
            else:
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


def _event_time(value: object) -> datetime:
    try:
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    except (TypeError, ValueError, OSError) as exc:
        raise DxLinkError(f"DXLink event contained an invalid event time: {value!r}.") from exc


def _has_scout_fields(snapshot: DxLinkSnapshot) -> bool:
    return snapshot.last_price is not None and snapshot.open_interest is not None