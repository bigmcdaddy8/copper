from datetime import timezone

from K9.tastytrade.dxlink import DxLinkSourceCollector


def test_source_events_preserve_configured_fields_and_add_utc_receipt_time():
    frame = {
        "type": "FEED_DATA",
        "data": [
            "TimeAndSale",
            ["TimeAndSale", "BTC/USD:CXTALP", 1_777_777_777_000, 65_000.25, 0.01, 42, 1_777_777_777_000],
        ],
    }
    fields = {
        "TimeAndSale": (
            "eventType", "eventSymbol", "eventTime", "price", "size", "index", "time"
        )
    }

    events = DxLinkSourceCollector._source_events(frame, fields, "BTC/USD:CXTALP")

    assert len(events) == 1
    assert events[0].event_type == "TimeAndSale"
    assert events[0].streamer_symbol == "BTC/USD:CXTALP"
    assert events[0].fields["price"] == 65_000.25
    assert events[0].fields["size"] == 0.01
    assert events[0].fields["index"] == 42
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