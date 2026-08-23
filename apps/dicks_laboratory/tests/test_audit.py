from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

from dicks_laboratory.audit import audit_dataset
from dicks_laboratory.capture_lifecycle import (
    CaptureLifecycleImportPolicy,
    CaptureLossPolicy,
    derive_gap_conclusions,
    load_capture_lifecycle_csv,
    normalize_capture_lifecycle,
)
from dicks_laboratory.fixture import synthetic_es_trades
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin
from dicks_laboratory.quality import DatasetQualityEvidenceType
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.store import LaboratoryStore

_DATASET = DatasetIdentity(
    dataset_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
    kind=DatasetKind.HISTORICAL_IMPORT,
    label="phase-0i-authentic-audit",
    source_locator="tests/fixtures/capture_lifecycle.csv",
    source_timezone="America/Chicago",
    normalizer_version="phase-0i-audit-v1",
    capture_started_at=datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc),
    capture_ended_at=datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc),
)


def _populate(store: LaboratoryStore) -> None:
    fixture = Path(__file__).parent / "fixtures" / "capture_lifecycle.csv"
    policy = CaptureLifecycleImportPolicy(
        source_timezone="America/Chicago",
        source_locator="tests/fixtures/capture_lifecycle.csv",
        dataset=_DATASET,
        loss_policy=CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS,
    )
    lifecycle = normalize_capture_lifecycle(load_capture_lifecycle_csv(fixture), policy)
    events = lifecycle.accepted + derive_gap_conclusions(lifecycle.accepted, policy)
    rejections = (
        NormalizationRejection(
            rejection_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c010"),
            dataset_id=_DATASET.dataset_id,
            source_kind=RejectionSourceKind.HISTORICAL_TRADE,
            source_record_ref="row:8",
            source_order=8,
            reason="MALFORMED_PRICE",
        ),
        NormalizationRejection(
            rejection_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c011"),
            dataset_id=_DATASET.dataset_id,
            source_kind=RejectionSourceKind.HISTORICAL_TRADE,
            source_record_ref="row:9",
            source_order=9,
            reason="UNSUPPORTED_SOURCE_CONTRACT",
        ),
        NormalizationRejection(
            rejection_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c012"),
            dataset_id=_DATASET.dataset_id,
            source_kind=RejectionSourceKind.CAPTURE_LIFECYCLE,
            source_record_ref="row:10",
            source_order=10,
            reason="UNSUPPORTED_LIFECYCLE_EVENT",
        ),
    )
    trades = tuple(
        trade.__class__(
            observation_id=trade.observation_id,
            dataset_id=_DATASET.dataset_id,
            dataset_sequence=trade.dataset_sequence,
            instrument=trade.instrument,
            event_timestamp=trade.event_timestamp,
            price=trade.price,
            size=trade.size,
            trade_action=trade.trade_action,
        )
        for trade in synthetic_es_trades()
    )
    store.save_dataset(_DATASET)
    store.save_trade_observations(trades)
    store.save_quality_events(events)
    store.save_rejections(rejections)


def test_audit_is_built_from_reloaded_durable_facts(tmp_path):
    db_path = Path(tmp_path) / "laboratory.db"
    store = LaboratoryStore(db_path)
    _populate(store)
    store.close()

    reopened = LaboratoryStore(db_path)
    audit = audit_dataset(reopened, _DATASET.dataset_id)

    assert audit.dataset == _DATASET
    assert audit.accepted_trade_count == 6
    assert audit.first_trade_event_timestamp == datetime(2026, 8, 21, 14, 47, 32, tzinfo=timezone.utc)
    assert audit.last_trade_event_timestamp == datetime(2026, 8, 21, 14, 47, 36, tzinfo=timezone.utc)
    assert (audit.first_dataset_sequence, audit.last_dataset_sequence) == (1, 6)
    assert audit.instrument_ids == ("FUTURE:CME:ES:2026-09",)
    assert audit.rejected_record_count == 3
    assert audit.rejection_counts_by_source_kind == (
        (RejectionSourceKind.CAPTURE_LIFECYCLE, 1),
        (RejectionSourceKind.HISTORICAL_TRADE, 2),
    )
    assert audit.rejection_counts_by_reason == (
        ("MALFORMED_PRICE", 1),
        ("UNSUPPORTED_LIFECYCLE_EVENT", 1),
        ("UNSUPPORTED_SOURCE_CONTRACT", 1),
    )
    assert audit.lifecycle_counts == (
        (DatasetQualityEvidenceType.CAPTURE_STOPPED, 1),
        (DatasetQualityEvidenceType.SOURCE_CONNECTED, 1),
        (DatasetQualityEvidenceType.SOURCE_DISCONNECTED, 1),
        (DatasetQualityEvidenceType.SOURCE_RECONNECTED, 1),
    )
    assert (audit.known_gap_count, audit.suspected_gap_count) == (1, 0)
    assert audit.known_gap_duration == timedelta(seconds=49)
    assert audit.gaps[0].supporting_event_ids == (
        audit.lifecycle_evidence[1].event_id,
        audit.lifecycle_evidence[2].event_id,
    )
    assert [detail.source_order for detail in audit.rejections] == [8, 9, 10]
    reopened.close()


def test_authentic_origin_is_independent_of_completeness_evidence(tmp_path):
    store = LaboratoryStore(Path(tmp_path) / "laboratory.db")
    _populate(store)

    audit = audit_dataset(store, _DATASET.dataset_id)

    assert audit.dataset.origin is DatasetOrigin.AUTHENTIC_SOURCE
    assert audit.known_gap_count == 1
    assert audit.rejected_record_count == 3
    assert not hasattr(audit, "trust_score")
    assert not hasattr(audit, "fitness")
    store.close()


def test_derived_synthetic_lineage_is_visible_in_audit(tmp_path):
    store = LaboratoryStore(Path(tmp_path) / "laboratory.db")
    parent = DatasetIdentity(
        dataset_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c020"),
        kind=DatasetKind.HISTORICAL_IMPORT,
        label="authentic-parent",
    )
    child = DatasetIdentity(
        dataset_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c021"),
        kind=DatasetKind.SYNTHETIC,
        label="derived-child",
        origin=DatasetOrigin.DERIVED_SYNTHETIC,
        parent_dataset_id=parent.dataset_id,
        transformation_policy="gap-fill-v1",
        transformation_version="1.0",
        random_seed=12345,
    )
    store.save_dataset(parent)
    store.save_dataset(child)

    audit = audit_dataset(store, child.dataset_id)

    assert audit.dataset == child
    assert audit.accepted_trade_count == 0
    assert audit.dataset.parent_dataset_id == parent.dataset_id
    assert audit.dataset.transformation_policy == "gap-fill-v1"
    assert audit.dataset.random_seed == 12345
    store.close()


def test_empty_dataset_differs_from_missing_dataset(tmp_path):
    store = LaboratoryStore(Path(tmp_path) / "laboratory.db")
    empty = DatasetIdentity(
        dataset_id=UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c030"),
        kind=DatasetKind.HISTORICAL_IMPORT,
        label="empty",
    )
    store.save_dataset(empty)

    audit = audit_dataset(store, empty.dataset_id)

    assert audit.accepted_trade_count == 0
    assert audit.rejected_record_count == 0
    assert audit.first_trade_event_timestamp is None
    assert audit.last_trade_event_timestamp is None
    assert audit.known_gap_count == 0
    with pytest.raises(KeyError, match="Dataset not found"):
        audit_dataset(store, UUID("b5d7d1e4-3c38-4c16-9e04-e6f7c8a7c031"))
    store.close()