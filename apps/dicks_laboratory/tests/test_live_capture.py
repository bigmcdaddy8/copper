from datetime import datetime, timezone
import pytest

from K9.tastytrade.dxlink import DxLinkError, DxLinkSourceEvent
from dicks_laboratory.live_capture import capture_es_timesales_dataset


def _event(index: int, classification: str = "NEW", **overrides: object) -> DxLinkSourceEvent:
    fields: dict[str, object] = {
        "eventSymbol": "/ESU26:XCME", "time": 1_787_523_190_000 + index,
        "type": classification, "index": index, "sequence": index,
        "tradeId": 99, "eventFlags": 0, "price": 7684.25, "size": 1.0,
        "validTick": True,
    }
    fields.update(overrides)
    return DxLinkSourceEvent("TimeAndSale", "/ESU26:XCME", fields, datetime(2026, 8, 23, 22, 13, 10, tzinfo=timezone.utc))


class Collector:
    def __init__(self, events: tuple[DxLinkSourceEvent, ...], error: Exception | None = None):
        self.events = events
        self.error = error

    def collect(self, _symbol, _types, _duration, max_events, on_event=None, on_connected=None, retain_events=True):
        if on_connected:
            on_connected()
        for event in self.events[:max_events]:
            if on_event:
                on_event(event)
        if self.error:
            raise self.error
        return self.events if retain_events else ()


@pytest.mark.parametrize("duration", [0, -1, 1801])
def test_capture_bounds_are_enforced(tmp_path, duration):
    with pytest.raises(ValueError):
        capture_es_timesales_dataset(tmp_path / "capture.sqlite3", Collector(()), duration, 100)


def test_capture_persists_lifecycle_new_deferred_rejection_and_reopens(tmp_path):
    result = capture_es_timesales_dataset(
        tmp_path / "capture.sqlite3",
        Collector((_event(1), _event(2, "CORRECTION"), _event(3, "CANCEL"), _event(4, validTick=False))),
        60,
        100,
    )

    assert result.database_path.exists()
    assert result.source_event_count == 4
    assert result.accepted_trade_count == 1
    assert result.deferred_event_count == 2
    assert result.rejection_count == 1
    assert result.audit.lifecycle_counts[0][0].value == "CAPTURE_STARTED"
    assert any(kind.value == "SOURCE_CONNECTED" for kind, _count in result.audit.lifecycle_counts)
    assert any(kind.value == "CAPTURE_STOPPED" for kind, _count in result.audit.lifecycle_counts)
    assert result.audit.known_gap_count == 0
    assert result.canonical_vwap is not None
    assert len(result.effective_tape.effective_trades) == 1


def test_interrupted_capture_retains_partial_authentic_facts_without_gap_claim(tmp_path):
    result = capture_es_timesales_dataset(
        tmp_path / "interrupted.sqlite3",
        Collector((_event(1),), DxLinkError("simulated disconnect")),
        60,
        100,
    )

    assert result.accepted_trade_count == 1
    assert any(kind.value == "SOURCE_DISCONNECTED" for kind, _count in result.audit.lifecycle_counts)
    assert result.audit.known_gap_count == 0
    assert result.audit.suspected_gap_count == 0