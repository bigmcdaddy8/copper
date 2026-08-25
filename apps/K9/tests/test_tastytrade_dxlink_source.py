from datetime import timezone

import pytest

from K9.tastytrade.dxlink import DxLinkCollector, DxLinkError, DxLinkSourceCollector


def test_source_events_preserve_configured_fields_and_add_utc_receipt_time():
    frame = {
        "type": "FEED_DATA",
        "data": [
            "TimeAndSale",
            [
                "TimeAndSale", "BTC/USD:CXTALP", 0, 0, 42, 7, 1_777_777_777_000,
                "NEW", 12345, "X", 65_000.25, 0.01, 64_999.0, 65_001.0,
                None, "\u0000", "BUY", False, False, True,
            ],
        ],
    }
    fields = {
        "TimeAndSale": (
            "eventType", "eventSymbol", "eventTime", "eventFlags", "index", "sequence", "time", "type",
            "tradeId", "exchangeCode", "price", "size", "bidPrice", "askPrice",
            "exchangeSaleConditions", "tradeThroughExempt", "aggressorSide", "spreadLeg",
            "extendedTradingHours", "validTick",
        )
    }

    events = DxLinkSourceCollector._source_events(frame, fields, "BTC/USD:CXTALP")

    assert len(events) == 1
    assert events[0].event_type == "TimeAndSale"
    assert events[0].streamer_symbol == "BTC/USD:CXTALP"
    assert events[0].fields["price"] == 65_000.25
    assert events[0].fields["size"] == 0.01
    assert events[0].fields["eventFlags"] == 0
    assert events[0].fields["index"] == 42
    assert events[0].fields["sequence"] == 7
    assert events[0].fields["type"] == "NEW"
    assert events[0].fields["tradeId"] == 12345
    assert events[0].received_at.tzinfo is timezone.utc


def test_source_collector_keepalive_is_bounded_when_no_events_arrive():
    class Socket:
        def __init__(self):
            self.sent = []
            self.frames = iter(
                [
                    '{"type":"SETUP"}',
                    '{"type":"AUTH_STATE","state":"UNAUTHORIZED"}',
                    '{"type":"AUTH_STATE","state":"AUTHORIZED"}',
                    '{"type":"CHANNEL_OPENED"}',
                    '{"type":"FEED_CONFIG"}',
                ]
            )

        def send(self, message):
            self.sent.append(message)

        def recv(self, timeout=None):
            try:
                return next(self.frames)
            except StopIteration:
                raise TimeoutError()

        def close(self):
            pass

    socket = Socket()
    collector = DxLinkSourceCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    assert collector.collect("BTC/USD:CXTALP", ("Trade",), duration_seconds=0.01, max_events=1) == ()


def test_receive_wraps_arbitrary_connection_errors_as_dxlink_error():
    """A dropped connection (e.g. websockets' ConnectionClosed) must surface as
    DxLinkError so orchestration-layer reconnect logic can reliably detect it,
    rather than propagating an arbitrary transport-specific exception."""

    class _ConnectionDropped(Exception):
        pass

    class Socket:
        def recv(self, timeout=None):
            raise _ConnectionDropped("connection closed by peer")

        def send(self, message):
            pass

        def close(self):
            pass

    with pytest.raises(DxLinkError, match="connection error"):
        DxLinkCollector._receive(Socket())