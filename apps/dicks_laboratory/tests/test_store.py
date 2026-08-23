import sqlite3
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from dicks_laboratory.capture_lifecycle import (
    CaptureLifecycleImportPolicy,
    CaptureLossPolicy,
    derive_gap_conclusions,
    load_capture_lifecycle_csv,
    normalize_capture_lifecycle,
)
from dicks_laboratory.fixture import SYNTHETIC_ES_DATASET, synthetic_es_trades
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin
from dicks_laboratory.quality import summarize_dataset_quality
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.vwap import calculate_vwap

_CAPTURE_DATASET = DatasetIdentity(
    dataset_id=UUID("95d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
    kind=DatasetKind.HISTORICAL_IMPORT,
    label="phase-0g-capture-round-trip",
    source_locator="tests/fixtures/capture_lifecycle.csv",
    source_timezone="America/Chicago",
    normalizer_version="phase-0f-capture-lifecycle-v1",
    capture_started_at=datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc),
    capture_ended_at=datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc),
)


def _capture_events():
    fixture_path = Path(__file__).parent / "fixtures" / "capture_lifecycle.csv"
    policy = CaptureLifecycleImportPolicy(
        source_timezone="America/Chicago",
        source_locator="tests/fixtures/capture_lifecycle.csv",
        dataset=_CAPTURE_DATASET,
        loss_policy=CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS,
    )
    lifecycle = normalize_capture_lifecycle(load_capture_lifecycle_csv(fixture_path), policy)
    return lifecycle.accepted + derive_gap_conclusions(lifecycle.accepted, policy)


def test_schema_initialization_is_idempotent_and_data_survives_reopen(tmp_path):
    db_path = tmp_path / "laboratory.db"
    store = LaboratoryStore(db_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)
    store.save_trade_observations(synthetic_es_trades())
    store.close()

    reopened = LaboratoryStore(db_path)
    assert reopened.load_dataset(SYNTHETIC_ES_DATASET.dataset_id) == SYNTHETIC_ES_DATASET
    assert reopened.load_trade_observations(SYNTHETIC_ES_DATASET.dataset_id) == synthetic_es_trades()
    reopened.close()


def test_trade_round_trip_preserves_decimal_utc_identity_and_sequence_order(tmp_path):
    store = LaboratoryStore(tmp_path / "laboratory.db")
    store.save_dataset(SYNTHETIC_ES_DATASET)
    store.save_trade_observations(synthetic_es_trades())

    loaded = store.load_trade_observations(SYNTHETIC_ES_DATASET.dataset_id)

    assert [trade.dataset_sequence for trade in loaded] == [1, 2, 3, 4, 5, 6]
    assert loaded[0].observation_id == synthetic_es_trades()[0].observation_id
    assert loaded[0].instrument.canonical_id == "FUTURE:CME:ES:2026-09"
    assert loaded[0].event_timestamp.tzinfo is timezone.utc
    assert loaded[0].price == Decimal("6432.00")
    assert loaded[0].size == Decimal("2")
    assert calculate_vwap(loaded) == Decimal("6432.166666666666666666666667")
    store.close()


def test_quality_events_and_evidence_links_round_trip_with_summary(tmp_path):
    store = LaboratoryStore(tmp_path / "laboratory.db")
    store.save_dataset(_CAPTURE_DATASET)
    events = _capture_events()
    store.save_quality_events(events)

    loaded = store.load_quality_events(_CAPTURE_DATASET.dataset_id)

    original_gap = next(event for event in events if event.interval_start is not None)
    loaded_gap = next(event for event in loaded if event.interval_start is not None)
    assert loaded_gap.event_id == original_gap.event_id
    assert loaded_gap.supporting_event_ids == original_gap.supporting_event_ids
    assert loaded_gap.interval_start == original_gap.interval_start
    assert loaded_gap.interval_end == original_gap.interval_end
    assert next(event for event in loaded if event.source_record_ref == "row:3").detail == "connection_lost"
    assert summarize_dataset_quality(loaded) == summarize_dataset_quality(events)
    store.close()


def test_dataset_lineage_round_trip(tmp_path):
    store = LaboratoryStore(tmp_path / "laboratory.db")
    parent = DatasetIdentity(
        dataset_id=UUID("95d7d1e4-3c38-4c16-9e04-e6f7c8a7c010"),
        kind=DatasetKind.HISTORICAL_IMPORT,
        label="authentic-parent",
    )
    child = DatasetIdentity(
        dataset_id=UUID("95d7d1e4-3c38-4c16-9e04-e6f7c8a7c011"),
        kind=DatasetKind.SYNTHETIC,
        label="future-gap-fill-child",
        origin=DatasetOrigin.DERIVED_SYNTHETIC,
        parent_dataset_id=parent.dataset_id,
        transformation_policy="gap-fill-v1",
        transformation_version="1.0",
        random_seed=12345,
    )
    store.save_dataset(parent)
    store.save_dataset(child)

    assert store.load_dataset(child.dataset_id) == child
    store.close()


def test_unique_dataset_sequence_integrity_constraint_is_enforced(tmp_path):
    store = LaboratoryStore(tmp_path / "laboratory.db")
    store.save_dataset(SYNTHETIC_ES_DATASET)
    first, second, *_ = synthetic_es_trades()
    store.save_trade_observations((first,))
    duplicate_sequence = replace(second, dataset_sequence=first.dataset_sequence)

    with pytest.raises(sqlite3.IntegrityError):
        store.save_trade_observations((duplicate_sequence,))
    store.close()