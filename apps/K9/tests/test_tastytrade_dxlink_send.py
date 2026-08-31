"""Phase 0W-2B Defect A -- send-path connection failures must surface as
`DxLinkError`, symmetrically with `_receive`, so the orchestration-layer
reconnect loop detects them. Attempt 2 died because a `ConnectionClosedError`
raised from a KEEPALIVE *send* bypassed every `except DxLinkError`.
"""
from __future__ import annotations

import pytest
from websockets.exceptions import ConnectionClosedError

from K9.tastytrade.dxlink import DxLinkCollector, DxLinkError, DxLinkSourceCollector


def test_send_translates_connection_closed_to_dxlink_error():
    class Socket:
        def send(self, message):
            raise ConnectionClosedError(None, None)

    with pytest.raises(DxLinkError, match="connection error while sending"):
        DxLinkCollector._send(Socket(), {"type": "KEEPALIVE", "channel": 0})


def test_send_translates_oserror_to_dxlink_error():
    class Socket:
        def send(self, message):
            raise BrokenPipeError("[Errno 32] Broken pipe")

    with pytest.raises(DxLinkError, match="connection error while sending"):
        DxLinkCollector._send(Socket(), {"type": "KEEPALIVE", "channel": 0})


def test_send_does_not_disguise_a_serialization_error_as_a_disconnect():
    class Socket:
        def send(self, message):  # pragma: no cover - never reached
            raise AssertionError("send must not be called for an unserializable payload")

    with pytest.raises(TypeError):
        DxLinkCollector._send(Socket(), {"bad": object()})


def test_keepalive_send_failure_during_collect_surfaces_as_dxlink_error():
    """End-to-end at the collector level: a healthy connect/subscribe, then the
    periodic KEEPALIVE send hits a peer-closed socket -> `collect()` raises
    `DxLinkError` (the reconnect trigger), never a raw websockets exception."""

    class Socket:
        def __init__(self):
            self._setup_frames = iter(
                [
                    '{"type":"SETUP"}',
                    '{"type":"AUTH_STATE","state":"UNAUTHORIZED"}',
                    '{"type":"AUTH_STATE","state":"AUTHORIZED"}',
                    '{"type":"CHANNEL_OPENED"}',
                    '{"type":"FEED_CONFIG"}',
                ]
            )
            self.keepalive_attempts = 0

        def send(self, message):
            if '"KEEPALIVE"' in message:
                self.keepalive_attempts += 1
                raise ConnectionClosedError(None, None)

        def recv(self, timeout=None):
            frame = next(self._setup_frames, None)
            if frame is not None:
                return frame
            raise TimeoutError()  # drives the collect loop into its KEEPALIVE branch

        def close(self):
            pass

    socket = Socket()
    collector = DxLinkSourceCollector("wss://dxlink.example", "quote-token", lambda _url: socket)

    with pytest.raises(DxLinkError, match="connection error while sending"):
        collector.collect("/ESU26:XCME", ("TimeAndSale",), duration_seconds=1.0, max_events=10)
    assert socket.keepalive_attempts == 1
