from decimal import Decimal
from pathlib import Path
from uuid import UUID

from dicks_laboratory.capture_lifecycle import (
    CaptureLifecycleImportPolicy,
    CaptureLifecycleSourceRecord,
    CaptureLossPolicy,
    normalize_capture_lifecycle,
)
from dicks_laboratory.fixture import SYNTHETIC_ES_DATASET, synthetic_es_trades
from dicks_laboratory.historical_csv import HistoricalCsvImportPolicy, HistoricalTradeSourceRecord, normalize_historical_trades
from dicks_laboratory.quality import summarize_dataset_quality
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.vwap import calculate_vwap


def _rejections() -> tuple[NormalizationRejection, ...]:
    policy = HistoricalCsvImportPolicy(
        source_timezone="America/Chicago",
        source_locator="inline",
        dataset=SYNTHETIC_ES_DATASET,
    )
    historical = normalize_historical_trades(
        (
            HistoricalTradeSourceRecord("row:8", "08/21/2026 09:47:37", "ESU26", "bad", "1"),
            HistoricalTradeSourceRecord("row:9", "08/21/2026 09:47:38", "ESZ26", "6432.25", "1"),
        ),
        policy,
    )
    lifecycle = normalize_capture_lifecycle(
        (
            CaptureLifecycleSourceRecord("row:10", "08/21/2026 09:47:39", "flapping", "unknown"),
        ),
        CaptureLifecycleImportPolicy(
            source_timezone="America/Chicago",
            source_locator="inline",
            dataset=SYNTHETIC_ES_DATASET,
            loss_policy=CaptureLossPolicy.DISCONNECT_DOES_NOT_IMPLY_DATA_LOSS,
        ),
    )
    return (
        NormalizationRejection(
            rejection_id=UUID("a5d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
            dataset_id=SYNTHETIC_ES_DATASET.dataset_id,
            source_kind=RejectionSourceKind.HISTORICAL_TRADE,
            source_record_ref=historical.rejected[0].source_record_ref,
            source_order=8,
            reason=historical.rejected[0].reason,
            detail="Price text could not be parsed as Decimal.",
        ),
        NormalizationRejection(
            rejection_id=UUID("a5d7d1e4-3c38-4c16-9e04-e6f7c8a7c002"),
            dataset_id=SYNTHETIC_ES_DATASET.dataset_id,
            source_kind=RejectionSourceKind.HISTORICAL_TRADE,
            source_record_ref=historical.rejected[1].source_record_ref,
            source_order=9,
            reason=historical.rejected[1].reason,
        ),
        NormalizationRejection(
            rejection_id=UUID("a5d7d1e4-3c38-4c16-9e04-e6f7c8a7c003"),
            dataset_id=SYNTHETIC_ES_DATASET.dataset_id,
            source_kind=RejectionSourceKind.CAPTURE_LIFECYCLE,
            source_record_ref=lifecycle.rejected[0].source_record_ref,
            source_order=10,
            reason=lifecycle.rejected[0].reason,
        ),
    )


def test_rejections_round_trip_after_database_reopen_with_source_provenance(tmp_path):
    db_path = Path(tmp_path) / "laboratory.db"
    store = LaboratoryStore(db_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)
    store.save_trade_observations(synthetic_es_trades())
    rejections = _rejections()
    store.save_rejections(rejections)
    store.close()

    reopened = LaboratoryStore(db_path)
    loaded = reopened.load_rejections(SYNTHETIC_ES_DATASET.dataset_id)

    assert loaded == rejections
    assert [rejection.source_order for rejection in loaded] == [8, 9, 10]
    assert [rejection.reason for rejection in loaded] == [
        "MALFORMED_PRICE",
        "UNSUPPORTED_SOURCE_CONTRACT",
        "UNSUPPORTED_LIFECYCLE_EVENT",
    ]
    assert loaded[0].detail == "Price text could not be parsed as Decimal."
    assert calculate_vwap(reopened.load_trade_observations(SYNTHETIC_ES_DATASET.dataset_id)) == Decimal(
        "6432.166666666666666666666667"
    )
    reopened.close()


def test_rejection_summary_and_accepted_accounting_remain_separate(tmp_path):
    store = LaboratoryStore(Path(tmp_path) / "laboratory.db")
    trades = synthetic_es_trades()
    rejections = _rejections()
    store.save_dataset(SYNTHETIC_ES_DATASET)
    store.save_trade_observations(trades)
    store.save_rejections(rejections)

    loaded_trades = store.load_trade_observations(SYNTHETIC_ES_DATASET.dataset_id)
    loaded_rejections = store.load_rejections(SYNTHETIC_ES_DATASET.dataset_id)

    assert len(loaded_trades) == 6
    assert len(loaded_rejections) == 3
    assert summarize_dataset_quality((), loaded_rejections) == summarize_dataset_quality((), rejections)
    assert summarize_dataset_quality((), loaded_rejections).known_gap_count == 0
    store.close()


def test_schema_initialization_adds_rejection_table_to_existing_store(tmp_path):
    db_path = Path(tmp_path) / "laboratory.db"
    store = LaboratoryStore(db_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)
    store.save_trade_observations(synthetic_es_trades())
    store._connection.execute("DROP TABLE normalization_rejections")
    store._connection.commit()
    store.close()

    reopened = LaboratoryStore(db_path)
    reopened.save_rejections((_rejections()[0],))

    assert reopened.load_trade_observations(SYNTHETIC_ES_DATASET.dataset_id) == synthetic_es_trades()
    assert reopened.load_rejections(SYNTHETIC_ES_DATASET.dataset_id) == (_rejections()[0],)
    reopened.close()


def test_rejection_is_not_a_trade_observation_or_vwap_input():
    rejections = _rejections()
    accepted_trades = synthetic_es_trades()

    assert calculate_vwap(accepted_trades) == Decimal("6432.166666666666666666666667")
    assert all(not hasattr(rejection, "dataset_sequence") for rejection in rejections)