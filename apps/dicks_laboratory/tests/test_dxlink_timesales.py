from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.audit import audit_dataset
from dicks_laboratory.dxlink_timesales import normalize_dxlink_time_and_sales, source_records_from_events
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.vwap import calculate_vwap

_DATASET = DatasetIdentity(
    UUID("c5d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"), DatasetKind.HISTORICAL_IMPORT,
    "dxlink-es-test", origin=DatasetOrigin.AUTHENTIC_SOURCE,
)
_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)
_SYMBOL = "/ESU26:XCME"


def _event(index: int, sequence: int, **overrides: object) -> DxLinkSourceEvent:
    fields: dict[str, object] = {
        "eventSymbol": _SYMBOL, "time": 1_787_523_190_101, "type": "NEW",
        "index": index, "sequence": sequence, "tradeId": 272163,
        "eventFlags": 0, "exchangeCode": "G", "price": 7684.25,
        "size": 1.0, "validTick": True,
    }
    fields.update(overrides)
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, datetime(2026, 8, 23, 22, 13, 10, tzinfo=timezone.utc))


def test_new_events_same_time_and_trade_id_remain_distinct_and_persist(tmp_path):
    records = source_records_from_events((_event(10, 1), _event(11, 2)))
    result = normalize_dxlink_time_and_sales(records, _DATASET, _INSTRUMENT, _SYMBOL)

    assert [trade.dataset_sequence for trade in result.observations] == [1, 2]
    assert result.observations[0].event_timestamp == result.observations[1].event_timestamp
    assert result.observations[0].price == Decimal("7684.25")
    assert result.provenance[0].source_index == 10
    assert result.provenance[1].source_sequence == 2

    database = tmp_path / "live.db"
    store = LaboratoryStore(database)
    store.save_dataset(_DATASET)
    store.save_trade_observations(result.observations)
    store.save_dxlink_time_and_sale_provenance(result.provenance)
    store.close()
    reopened = LaboratoryStore(database)
    loaded = reopened.load_trade_observations(_DATASET.dataset_id)
    provenance = reopened.load_dxlink_time_and_sale_provenance(_DATASET.dataset_id)
    audit = audit_dataset(reopened, _DATASET.dataset_id)

    assert loaded == result.observations
    assert provenance == result.provenance
    assert audit.accepted_trade_count == 2
    assert calculate_vwap(loaded) == Decimal("7684.25")
    reopened.close()


def test_new_acceptance_rejection_and_deferred_policy():
    events = (
        _event(10, 1),
        _event(11, 2, type="CORRECTION"),
        _event(12, 3, type="CANCEL"),
        _event(13, 4, validTick=False),
        _event(14, 5, price="NaN"),
        _event(15, 6, size=0),
        _event(16, 7, eventSymbol="/MESU26:XCME"),
    )
    result = normalize_dxlink_time_and_sales(source_records_from_events(events), _DATASET, _INSTRUMENT, _SYMBOL)

    assert len(result.accepted) == 1
    assert [item.reason for item in result.deferred] == ["DXLINK_CORRECTION", "DXLINK_CANCEL"]
    assert [item.reason for item in result.rejected] == [
        "INVALID_DXLINK_TICK", "INVALID_DXLINK_PRICE", "INVALID_DXLINK_SIZE", "UNEXPECTED_DXLINK_STREAMER_SYMBOL",
    ]


def test_deferred_correction_and_cancel_survive_close_reopen_and_audit(tmp_path):
    events = (_event(10, 1), _event(11, 2, type="CORRECTION"), _event(12, 3, type="CANCEL"))
    result = normalize_dxlink_time_and_sales(source_records_from_events(events), _DATASET, _INSTRUMENT, _SYMBOL)
    database = tmp_path / "deferred.db"
    store = LaboratoryStore(database)
    store.save_dataset(_DATASET)
    store.save_trade_observations(result.observations)
    store.save_dxlink_time_and_sale_provenance(result.provenance)
    store.save_deferred_dxlink_time_and_sales(result.deferred)
    store.close()

    reopened = LaboratoryStore(database)
    trades = reopened.load_trade_observations(_DATASET.dataset_id)
    deferred = reopened.load_deferred_dxlink_time_and_sales(_DATASET.dataset_id)
    audit = audit_dataset(reopened, _DATASET.dataset_id)

    assert trades == result.observations
    assert [event.deferred_event_id for event in deferred] == [
        event.deferred_event_id for event in result.deferred
    ]
    assert [event.dataset_id for event in deferred] == [_DATASET.dataset_id, _DATASET.dataset_id]
    assert [event.source_order for event in deferred] == [2, 3]
    assert [event.source_record.source_record_ref for event in deferred] == ["event:2", "event:3"]
    assert [event.source_record.event_classification for event in deferred] == ["CORRECTION", "CANCEL"]
    assert [event.source_record.source_index for event in deferred] == [11, 12]
    assert [event.source_record.source_sequence for event in deferred] == [2, 3]
    assert [event.source_record.source_trade_id for event in deferred] == [272163, 272163]
    assert all(event.source_record.event_flags == 0 for event in deferred)
    assert all(event.source_record.event_time.tzinfo is timezone.utc for event in deferred)
    assert all(event.source_record.price == Decimal("7684.25") for event in deferred)
    assert all(event.source_record.size == Decimal("1.0") for event in deferred)
    assert all(event.source_record.received_at.tzinfo is timezone.utc for event in deferred)
    assert audit.deferred_timesale_count == 2
    assert audit.deferred_timesale_counts_by_classification == (("CANCEL", 1), ("CORRECTION", 1))
    assert calculate_vwap(trades) == Decimal("7684.25")
    reopened.close()