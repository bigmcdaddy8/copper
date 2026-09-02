from __future__ import annotations

import json

import pytest

from K9.tastytrade.dxlink import DxLinkCollector, DxLinkError


class FakeSocket:
    def __init__(self, frames: list[dict]) -> None:
        self._frames = iter(frames)
        self.sent: list[dict] = []
        self.closed = False

    def send(self, message: str) -> None:
        self.sent.append(json.loads(message))

    def recv(self, timeout: float | None = None) -> str:
        del timeout
        try:
            return json.dumps(next(self._frames))
        except StopIteration as exc:
            raise TimeoutError from exc

    def close(self) -> None:
        self.closed = True


def _setup_frames() -> list[dict]:
    return [
        {"type": "SETUP"},
        {"type": "AUTH_STATE", "state": "UNAUTHORIZED"},
        {"type": "AUTH_STATE", "state": "AUTHORIZED"},
        {"type": "CHANNEL_OPENED"},
        {"type": "FEED_CONFIG"},
    ]


def test_collects_quote_and_greeks_with_documented_setup_sequence():
    symbol = ".XSP260730P600"
    socket = FakeSocket(
        _setup_frames()
        + [
            {
                "type": "FEED_DATA",
                "data": ["Quote", ["Quote", symbol, 1_753_890_000_000, 1.2, 1.3, 10, 12]],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Greeks",
                    ["Greeks", symbol, 1_753_890_000_000, 0.18, -0.2, 0.01, -0.03, -0.01, 0.04],
                ],
            },
            {
                "type": "FEED_DATA",
                "data": ["Trade", ["Trade", symbol, 1_753_890_000_000, 1.25, 42, 1]],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Summary",
                    ["Summary", symbol, 1_753_890_000_000, 1234, 1.1, 1.5, 0.9, 1.0],
                ],
            },
        ]
    )
    collector = DxLinkCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    snapshots = collector.collect([symbol])

    assert socket.closed
    assert snapshots[symbol].bid == 1.2
    assert snapshots[symbol].ask == 1.3
    assert snapshots[symbol].last_price == 1.25
    assert snapshots[symbol].open_interest == 1234
    assert snapshots[symbol].delta == -0.2
    assert snapshots[symbol].quote_updated_at == snapshots[symbol].greeks_updated_at
    assert snapshots[symbol].trade_updated_at == snapshots[symbol].summary_updated_at
    assert snapshots[symbol].quote_received_at is not None
    assert snapshots[symbol].greeks_received_at is not None
    assert snapshots[symbol].is_complete
    assert [message["type"] for message in socket.sent] == [
        "SETUP",
        "AUTH",
        "CHANNEL_REQUEST",
        "FEED_SETUP",
        "FEED_SUBSCRIPTION",
    ]
    assert socket.sent[-1]["add"] == [
        {"type": "Quote", "symbol": symbol},
        {"type": "Greeks", "symbol": symbol},
        {"type": "Trade", "symbol": symbol},
        {"type": "Summary", "symbol": symbol},
    ]


def test_collect_rejects_unauthorized_dxlink_connection():
    socket = FakeSocket(
        [
            {"type": "SETUP"},
            {"type": "AUTH_STATE", "state": "UNAUTHORIZED"},
            {"type": "AUTH_STATE", "state": "DENIED"},
        ]
    )
    collector = DxLinkCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    with pytest.raises(DxLinkError, match="authorization state 'AUTHORIZED'"):
        collector.collect(["XSP"])

    assert socket.closed


def test_collect_quotes_requires_only_a_quote_snapshot():
    symbol = ".XSP"
    socket = FakeSocket(
        _setup_frames()
        + [
            {
                "type": "FEED_DATA",
                "data": ["Quote", ["Quote", symbol, 1_753_890_000_000, 600.0, 600.2, 10, 12]],
            }
        ]
    )
    collector = DxLinkCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    snapshot = collector.collect_quotes([symbol])[symbol]

    assert snapshot.bid == 600.0
    assert snapshot.ask == 600.2
    assert snapshot.quote_received_at is not None
    assert socket.sent[-1]["add"] == [{"type": "Quote", "symbol": symbol}]


def test_collect_treats_unavailable_trade_and_summary_fields_as_optional():
    symbol = ".XSP260730P600"
    socket = FakeSocket(
        _setup_frames()
        + [
            {
                "type": "FEED_DATA",
                "data": ["Quote", ["Quote", symbol, 1_753_890_000_000, 1.2, 1.3, 10, 12]],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Greeks",
                    ["Greeks", symbol, 1_753_890_000_000, 0.18, -0.2, 0.01, -0.03, -0.01, 0.04],
                ],
            },
            {
                "type": "FEED_DATA",
                "data": ["Trade", ["Trade", symbol, 1_753_890_000_000, "NaN", 42, 1]],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Summary",
                    ["Summary", symbol, 1_753_890_000_000, "NaN", 1.1, 1.5, 0.9, 1.0],
                ],
            },
        ]
    )
    collector = DxLinkCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    snapshots = collector.collect([symbol], timeout_seconds=0.01)

    assert snapshots[symbol].is_complete
    assert snapshots[symbol].last_price is None
    assert snapshots[symbol].open_interest is None


def test_collect_preserves_fresh_quote_and_greeks_timestamps_when_summary_is_old():
    symbol = ".XSP260730P600"
    fresh_time = 1_753_890_000_000
    old_time = fresh_time - 86_400_000
    socket = FakeSocket(
        _setup_frames()
        + [
            {
                "type": "FEED_DATA",
                "data": ["Quote", ["Quote", symbol, fresh_time, 1.2, 1.3, 10, 12]],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Greeks",
                    ["Greeks", symbol, fresh_time, 0.18, -0.2, 0.01, -0.03, -0.01, 0.04],
                ],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Summary",
                    ["Summary", symbol, old_time, 1234, 1.1, 1.5, 0.9, 1.0],
                ],
            },
        ]
    )
    collector = DxLinkCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    snapshot = collector.collect([symbol], timeout_seconds=0.01)[symbol]

    assert snapshot.quote_updated_at is not None
    assert snapshot.greeks_updated_at == snapshot.quote_updated_at
    assert snapshot.summary_updated_at is not None
    assert snapshot.summary_updated_at < snapshot.quote_updated_at


def test_collect_treats_zero_event_time_as_unavailable_but_records_receipt_time():
    symbol = ".XSP260730P600"
    socket = FakeSocket(
        _setup_frames()
        + [
            {
                "type": "FEED_DATA",
                "data": ["Quote", ["Quote", symbol, 0, 1.2, 1.3, 10, 12]],
            },
            {
                "type": "FEED_DATA",
                "data": [
                    "Greeks",
                    ["Greeks", symbol, 0, 0.18, -0.2, 0.01, -0.03, -0.01, 0.04],
                ],
            },
        ]
    )
    collector = DxLinkCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    snapshot = collector.collect([symbol], timeout_seconds=0.01)[symbol]

    assert snapshot.quote_updated_at is None
    assert snapshot.greeks_updated_at is None
    assert snapshot.quote_received_at is not None
    assert snapshot.greeks_received_at is not None