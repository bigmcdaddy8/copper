from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.dxlink_timesales import normalize_dxlink_time_and_sales, source_records_from_events
from dicks_laboratory.effective_tape import reconstruct_effective_tape
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.vwap import calculate_vwap

_DATASET = DatasetIdentity(UUID("d5d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"), DatasetKind.HISTORICAL_IMPORT, "tape", origin=DatasetOrigin.AUTHENTIC_SOURCE)
_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)
_SYMBOL = "/ESU26:XCME"


def _event(index: int, sequence: int, event_type: str = "NEW", price: object = 7684.25, size: object = 1) -> DxLinkSourceEvent:
    return DxLinkSourceEvent(
        "TimeAndSale", _SYMBOL,
        {"eventSymbol": _SYMBOL, "time": 1_787_523_190_000 + index, "type": event_type,
         "index": index, "sequence": sequence, "tradeId": 99, "eventFlags": 0,
         "price": price, "size": size, "validTick": True},
        datetime(2026, 8, 23, 22, 13, 10, tzinfo=timezone.utc),
    )


def _result(events: tuple[DxLinkSourceEvent, ...]):
    return normalize_dxlink_time_and_sales(source_records_from_events(events), _DATASET, _INSTRUMENT, _SYMBOL)


def test_new_events_form_effective_tape_without_mutating_canonical_trades():
    result = _result((_event(10, 1), _event(11, 2)))
    tape = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)

    assert len(tape.effective_trades) == 2
    assert tape.effective_trades[0].price == Decimal("7684.25")
    assert result.observations[0].price == Decimal("7684.25")
    assert tape.anomalies == ()


def test_correction_replaces_effective_state_by_exact_source_index():
    result = _result((_event(10, 1, "NEW", 7684.25), _event(10, 1, "CORRECTION", 7684.50, 2)))
    tape = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)

    assert len(tape.effective_trades) == 1
    assert tape.effective_trades[0].price == Decimal("7684.5")
    assert tape.effective_trades[0].size == Decimal("2")
    assert tape.effective_trades[0].correction_count == 1
    assert tape.applied_correction_count == 1
    assert result.observations[0].price == Decimal("7684.25")


def test_latest_of_multiple_same_index_corrections_is_effective_for_vwap():
    result = _result((
        _event(10, 1, "NEW", 100),
        _event(11, 2, "NEW", 102),
        _event(10, 1, "CORRECTION", 104, 1),
        _event(10, 1, "CORRECTION", 106, 1),
    ))
    tape = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)
    effective_vwap = sum((trade.price * trade.size for trade in tape.effective_trades), Decimal("0")) / sum((trade.size for trade in tape.effective_trades), Decimal("0"))

    assert tape.applied_correction_count == 2
    assert tape.effective_trades[0].price == Decimal("106")
    assert calculate_vwap(result.observations) == Decimal("101")
    assert effective_vwap == Decimal("104")


def test_cancel_removes_exact_index_from_effective_tape_and_changes_vwap():
    result = _result((_event(10, 1, "NEW", 100), _event(11, 2, "NEW", 102), _event(11, 2, "CANCEL")))
    tape = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)

    new_only_vwap = calculate_vwap(result.observations)
    effective_vwap = sum((trade.price * trade.size for trade in tape.effective_trades), Decimal("0")) / sum((trade.size for trade in tape.effective_trades), Decimal("0"))
    assert new_only_vwap == Decimal("101")
    assert effective_vwap == Decimal("100")
    assert tape.applied_cancel_count == 1


def test_correction_then_cancel_leaves_no_effective_trade():
    result = _result((_event(10, 1), _event(10, 1, "CORRECTION", 7685, 2), _event(10, 1, "CANCEL")))
    tape = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)

    assert tape.effective_trades == ()
    assert tape.applied_correction_count == 1
    assert tape.applied_cancel_count == 1


def test_same_time_distinct_indexes_remain_distinct_and_missing_target_is_anomaly():
    first = _event(10, 1)
    second = _event(11, 2)
    second.fields["time"] = first.fields["time"]
    result = _result((first, second, _event(99, 3, "CORRECTION", 7685, 1)))
    tape = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)

    assert len(tape.effective_trades) == 2
    assert [anomaly.reason for anomaly in tape.anomalies] == ["TARGET_SOURCE_EVENT_NOT_FOUND"]


def test_missing_cancel_and_correction_after_cancel_are_explicit_anomalies():
    missing_cancel = _result((_event(99, 1, "CANCEL"),))
    canceled_then_corrected = _result((_event(10, 1), _event(10, 1, "CANCEL"), _event(10, 1, "CORRECTION", 7685, 1)))

    missing_tape = reconstruct_effective_tape(missing_cancel.observations, missing_cancel.provenance, missing_cancel.deferred)
    canceled_tape = reconstruct_effective_tape(canceled_then_corrected.observations, canceled_then_corrected.provenance, canceled_then_corrected.deferred)

    assert [anomaly.reason for anomaly in missing_tape.anomalies] == ["TARGET_SOURCE_EVENT_NOT_FOUND"]
    assert [anomaly.reason for anomaly in canceled_tape.anomalies] == ["CORRECTION_AFTER_CANCEL"]


def test_reconstruction_is_identical_after_sqlite_close_reopen(tmp_path):
    result = _result((_event(10, 1), _event(10, 1, "CORRECTION", 7685, 2), _event(11, 2), _event(11, 2, "CANCEL")))
    before = reconstruct_effective_tape(result.observations, result.provenance, result.deferred)
    database = tmp_path / "reconstruct.db"
    store = LaboratoryStore(database)
    store.save_dataset(_DATASET)
    store.save_trade_observations(result.observations)
    store.save_dxlink_time_and_sale_provenance(result.provenance)
    store.save_deferred_dxlink_time_and_sales(result.deferred)
    store.close()
    reopened = LaboratoryStore(database)
    after = reconstruct_effective_tape(
        reopened.load_trade_observations(_DATASET.dataset_id),
        reopened.load_dxlink_time_and_sale_provenance(_DATASET.dataset_id),
        reopened.load_deferred_dxlink_time_and_sales(_DATASET.dataset_id),
    )

    assert after == before
    reopened.close()