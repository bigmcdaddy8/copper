from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from dicks_laboratory.capture_lifecycle import (
    CaptureLifecycleImportPolicy,
    CaptureLifecycleSourceRecord,
    CaptureLossPolicy,
    derive_gap_conclusions,
    load_capture_lifecycle_csv,
    normalize_capture_lifecycle,
)
from dicks_laboratory.fixture import ES_SEP_2026
from dicks_laboratory.models import DatasetIdentity, DatasetKind, TradeObservation
from dicks_laboratory.quality import DatasetQualityEvidenceType, summarize_dataset_quality
from dicks_laboratory.vwap import calculate_vwap

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "capture_lifecycle.csv"
_DATASET = DatasetIdentity(
    dataset_id=UUID("85d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
    kind=DatasetKind.HISTORICAL_IMPORT,
    label="phase-0f-capture-lifecycle",
    source_locator="tests/fixtures/capture_lifecycle.csv",
    source_timezone="America/Chicago",
    normalizer_version="phase-0f-capture-lifecycle-v1",
    capture_started_at=datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc),
    capture_ended_at=datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc),
)


def _policy(loss_policy: CaptureLossPolicy) -> CaptureLifecycleImportPolicy:
    return CaptureLifecycleImportPolicy(
        source_timezone="America/Chicago",
        source_locator="tests/fixtures/capture_lifecycle.csv",
        dataset=_DATASET,
        loss_policy=loss_policy,
    )


def test_lifecycle_fixture_normalizes_in_source_row_order_with_utc_timestamps():
    records = load_capture_lifecycle_csv(_FIXTURE_PATH)
    result = normalize_capture_lifecycle(records, _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS))

    assert [record.source_record_ref for record in records] == ["row:2", "row:3", "row:4", "row:5"]
    assert result.rejected == ()
    assert [event.source_record_ref for event in result.accepted] == ["row:2", "row:3", "row:4", "row:5"]
    assert [event.evidence_type for event in result.accepted] == [
        DatasetQualityEvidenceType.SOURCE_CONNECTED,
        DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
        DatasetQualityEvidenceType.SOURCE_RECONNECTED,
        DatasetQualityEvidenceType.CAPTURE_STOPPED,
    ]
    assert result.accepted[1].observed_at == datetime(2026, 8, 21, 14, 42, 13, tzinfo=timezone.utc)
    assert result.accepted[1].detail == "connection_lost"


def test_loss_policy_derives_known_gap_without_removing_lifecycle_evidence():
    lifecycle = normalize_capture_lifecycle(
        load_capture_lifecycle_csv(_FIXTURE_PATH),
        _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS),
    )
    conclusions = derive_gap_conclusions(
        lifecycle.accepted,
        _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS),
    )

    assert [event.evidence_type for event in lifecycle.accepted] == [
        DatasetQualityEvidenceType.SOURCE_CONNECTED,
        DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
        DatasetQualityEvidenceType.SOURCE_RECONNECTED,
        DatasetQualityEvidenceType.CAPTURE_STOPPED,
    ]
    assert conclusions[0].evidence_type is DatasetQualityEvidenceType.KNOWN_GAP
    assert conclusions[0].interval_start == datetime(2026, 8, 21, 14, 42, 13, tzinfo=timezone.utc)
    assert conclusions[0].interval_end == datetime(2026, 8, 21, 14, 43, 2, tzinfo=timezone.utc)
    assert conclusions[0].supporting_event_ids == (
        lifecycle.accepted[1].event_id,
        lifecycle.accepted[2].event_id,
    )
    summary = summarize_dataset_quality(lifecycle.accepted + conclusions)
    assert summary.known_gap_count == 1
    assert summary.known_gap_duration == timedelta(seconds=49)


def test_same_lifecycle_facts_do_not_imply_gap_under_non_loss_policy():
    policy = _policy(CaptureLossPolicy.DISCONNECT_DOES_NOT_IMPLY_DATA_LOSS)
    lifecycle = normalize_capture_lifecycle(load_capture_lifecycle_csv(_FIXTURE_PATH), policy)

    conclusions = derive_gap_conclusions(lifecycle.accepted, policy)

    assert conclusions == ()
    assert summarize_dataset_quality(lifecycle.accepted).known_gap_count == 0


def test_lifecycle_evidence_traces_to_source_record():
    records = load_capture_lifecycle_csv(_FIXTURE_PATH)
    result = normalize_capture_lifecycle(records, _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS))
    disconnected = result.accepted[1]

    source_record = next(record for record in records if record.source_record_ref == disconnected.source_record_ref)

    assert source_record.raw_event == "disconnected"
    assert source_record.raw_reason == "connection_lost"


def test_unsupported_lifecycle_event_is_rejected_without_guessing():
    record = CaptureLifecycleSourceRecord(
        source_record_ref="row:6",
        raw_timestamp="08/21/2026 10:01:00",
        raw_event="flapping",
        raw_reason="unknown",
    )

    result = normalize_capture_lifecycle((record,), _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS))

    assert result.accepted == ()
    assert result.rejected[0].source_record_ref == "row:6"
    assert result.rejected[0].reason == "UNSUPPORTED_LIFECYCLE_EVENT"


def test_capture_stop_does_not_create_an_unbounded_gap():
    lifecycle = normalize_capture_lifecycle(
        load_capture_lifecycle_csv(_FIXTURE_PATH),
        _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS),
    )

    conclusions = derive_gap_conclusions(lifecycle.accepted, _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS))

    assert lifecycle.accepted[-1].evidence_type is DatasetQualityEvidenceType.CAPTURE_STOPPED
    assert len(conclusions) == 1


def test_lifecycle_evidence_does_not_mutate_trades_or_vwap():
    trades = (
        TradeObservation(
            observation_id=UUID("85d7d1e4-3c38-4c16-9e04-e6f7c8a7c101"),
            dataset_id=_DATASET.dataset_id,
            dataset_sequence=1,
            instrument=ES_SEP_2026,
            event_timestamp=datetime(2026, 8, 21, 14, 42, 13, tzinfo=timezone.utc),
            price=Decimal("6432.00"),
            size=Decimal("2"),
        ),
        TradeObservation(
            observation_id=UUID("85d7d1e4-3c38-4c16-9e04-e6f7c8a7c102"),
            dataset_id=_DATASET.dataset_id,
            dataset_sequence=2,
            instrument=ES_SEP_2026,
            event_timestamp=datetime(2026, 8, 21, 14, 43, 2, tzinfo=timezone.utc),
            price=Decimal("6432.50"),
            size=Decimal("2"),
        ),
    )
    lifecycle = normalize_capture_lifecycle(
        load_capture_lifecycle_csv(_FIXTURE_PATH),
        _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS),
    )

    assert derive_gap_conclusions(lifecycle.accepted, _policy(CaptureLossPolicy.DISCONNECT_IMPLIES_DATA_LOSS))
    assert calculate_vwap(trades) == Decimal("6432.25")
    with pytest.raises(FrozenInstanceError):
        trades[0].price = Decimal("1")  # type: ignore[misc]