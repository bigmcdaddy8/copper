from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from dicks_laboratory.fixture import ES_SEP_2026
from dicks_laboratory.historical_csv import RejectedSourceRecord
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, TradeObservation
from dicks_laboratory.quality import (
    DatasetQualityEvidenceType,
    DatasetQualityEvent,
    summarize_dataset_quality,
)
from dicks_laboratory.vwap import calculate_vwap

_DATASET_ID = UUID("75d7d1e4-3c38-4c16-9e04-e6f7c8a7c001")
_START = datetime(2026, 8, 21, 14, 42, 13, tzinfo=timezone.utc)
_END = datetime(2026, 8, 21, 14, 43, 2, tzinfo=timezone.utc)


def _quality_event(
    evidence_type: DatasetQualityEvidenceType,
    **overrides: object,
) -> DatasetQualityEvent:
    values: dict[str, object] = {
        "event_id": UUID("75d7d1e4-3c38-4c16-9e04-e6f7c8a7c101"),
        "dataset_id": _DATASET_ID,
        "evidence_type": evidence_type,
        "detail": "synthetic test evidence",
    }
    if evidence_type in {
        DatasetQualityEvidenceType.KNOWN_GAP,
        DatasetQualityEvidenceType.SUSPECTED_GAP,
    }:
        values.update({"interval_start": _START, "interval_end": _END})
    else:
        values["observed_at"] = _START
    values.update(overrides)
    return DatasetQualityEvent(**values)  # type: ignore[arg-type]


def _trade(sequence: int, event_timestamp: datetime) -> TradeObservation:
    return TradeObservation(
        observation_id=UUID(f"75d7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
        dataset_id=_DATASET_ID,
        dataset_sequence=sequence,
        instrument=ES_SEP_2026,
        event_timestamp=event_timestamp,
        price=Decimal("6432.25"),
        size=Decimal("1"),
    )


def test_known_gap_is_dataset_evidence_and_does_not_mutate_authentic_trades():
    trades = (_trade(1, _START), _trade(2, _END))
    disconnected = _quality_event(DatasetQualityEvidenceType.SOURCE_DISCONNECTED)
    gap = _quality_event(DatasetQualityEvidenceType.KNOWN_GAP)
    reconnected = _quality_event(
        DatasetQualityEvidenceType.SOURCE_RECONNECTED,
        observed_at=_END,
    )

    summary = summarize_dataset_quality((disconnected, gap, reconnected))

    assert trades[0].event_timestamp == _START
    assert disconnected.observed_at == _START
    assert reconnected.observed_at == _END
    assert summary.known_gap_count == 1
    assert summary.known_gap_duration == timedelta(seconds=49)
    with pytest.raises(FrozenInstanceError):
        trades[0].price = Decimal("1")  # type: ignore[misc]


def test_suspected_gap_remains_distinct_from_known_gap():
    suspected = _quality_event(DatasetQualityEvidenceType.SUSPECTED_GAP)

    summary = summarize_dataset_quality((suspected,))

    assert summary.known_gap_count == 0
    assert summary.suspected_gap_count == 1


def test_quiet_interval_does_not_create_quality_evidence():
    trades = (
        _trade(1, datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc)),
        _trade(2, datetime(2026, 8, 21, 14, 35, tzinfo=timezone.utc)),
    )

    summary = summarize_dataset_quality(())

    assert [trade.dataset_sequence for trade in trades] == [1, 2]
    assert summary.known_gap_count == 0
    assert summary.suspected_gap_count == 0


def test_quality_summary_counts_normalization_rejections_without_duplicating_events():
    rejected = (RejectedSourceRecord("row:8", "MALFORMED_PRICE"),)

    summary = summarize_dataset_quality((), rejected)

    assert summary.rejected_record_count == 1


@pytest.mark.parametrize(
    "start,end",
    [
        (_END, _START),
        (_START, _START),
    ],
)
def test_gap_intervals_must_be_nonempty_and_forward(start, end):
    with pytest.raises(ValueError, match="Gap interval"):
        _quality_event(DatasetQualityEvidenceType.KNOWN_GAP, interval_start=start, interval_end=end)


def test_quality_timestamps_require_utc():
    with pytest.raises(ValueError, match="timezone.utc"):
        _quality_event(
            DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
            observed_at=datetime(2026, 8, 21, 9, 42, tzinfo=timezone(timedelta(hours=-5))),
        )


def test_authentic_and_synthetic_dataset_lineage_are_explicit():
    authentic = DatasetIdentity(
        dataset_id=_DATASET_ID,
        kind=DatasetKind.HISTORICAL_IMPORT,
        label="authentic-source",
        capture_started_at=datetime(2026, 8, 21, 14, 30, tzinfo=timezone.utc),
        capture_ended_at=datetime(2026, 8, 21, 15, 0, tzinfo=timezone.utc),
    )
    synthetic = DatasetIdentity(
        dataset_id=UUID("75d7d1e4-3c38-4c16-9e04-e6f7c8a7c002"),
        kind=DatasetKind.SYNTHETIC,
        label="hypothetical-gap-fill",
        origin=DatasetOrigin.DERIVED_SYNTHETIC,
        parent_dataset_id=authentic.dataset_id,
        transformation_policy="gap-fill-v1",
        transformation_version="1.0",
        random_seed=12345,
    )

    assert authentic.origin is DatasetOrigin.AUTHENTIC_SOURCE
    assert synthetic.origin is DatasetOrigin.DERIVED_SYNTHETIC
    assert synthetic.parent_dataset_id == authentic.dataset_id
    assert synthetic.random_seed == 12345


def test_vwap_remains_computable_when_independent_known_gap_evidence_exists():
    trades = (_trade(1, _START), _trade(2, _END))
    gap = _quality_event(DatasetQualityEvidenceType.KNOWN_GAP)

    assert summarize_dataset_quality((gap,)).known_gap_count == 1
    assert calculate_vwap(trades) == Decimal("6432.25")