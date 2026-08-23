"""Dataset-level quality evidence that never changes authentic observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from uuid import UUID

from dicks_laboratory.historical_csv import RejectedSourceRecord


class DatasetQualityEvidenceType(StrEnum):
    CAPTURE_STARTED = "CAPTURE_STARTED"
    SOURCE_CONNECTED = "SOURCE_CONNECTED"
    SOURCE_DISCONNECTED = "SOURCE_DISCONNECTED"
    SOURCE_RECONNECTED = "SOURCE_RECONNECTED"
    CAPTURE_STOPPED = "CAPTURE_STOPPED"
    KNOWN_GAP = "KNOWN_GAP"
    SUSPECTED_GAP = "SUSPECTED_GAP"


@dataclass(frozen=True)
class DatasetQualityEvent:
    """One explicit point or interval of evidence about a dataset's completeness."""

    event_id: UUID
    dataset_id: UUID
    evidence_type: DatasetQualityEvidenceType
    detail: str
    observed_at: datetime | None = None
    interval_start: datetime | None = None
    interval_end: datetime | None = None
    source_record_ref: str | None = None
    supporting_event_ids: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        if not self.detail.strip():
            raise ValueError("Quality evidence detail is required.")
        timestamps = (self.observed_at, self.interval_start, self.interval_end)
        if any(timestamp is not None and timestamp.tzinfo is not timezone.utc for timestamp in timestamps):
            raise ValueError("Quality timestamps must use timezone.utc.")
        is_interval = self.interval_start is not None or self.interval_end is not None
        if self.evidence_type in {
            DatasetQualityEvidenceType.KNOWN_GAP,
            DatasetQualityEvidenceType.SUSPECTED_GAP,
        }:
            if self.observed_at is not None or not is_interval:
                raise ValueError("Gap evidence requires only a timestamp interval.")
            if self.interval_start is None or self.interval_end is None:
                raise ValueError("Gap evidence requires interval start and end.")
            if self.interval_end <= self.interval_start:
                raise ValueError("Gap interval must have positive duration.")
        elif self.observed_at is None or is_interval:
            raise ValueError("Point evidence requires only an observed timestamp.")

    @property
    def interval_duration(self) -> timedelta:
        if self.interval_start is None or self.interval_end is None:
            return timedelta()
        return self.interval_end - self.interval_start


@dataclass(frozen=True)
class DatasetQualitySummary:
    """Mechanical counts and durations; never an analytical-fitness judgment."""

    known_gap_count: int
    suspected_gap_count: int
    rejected_record_count: int
    known_gap_duration: timedelta


def summarize_dataset_quality(
    events: tuple[DatasetQualityEvent, ...],
    rejected_records: tuple[RejectedSourceRecord, ...] = (),
) -> DatasetQualitySummary:
    """Summarize explicit evidence without inferring gaps from observation timing."""
    known_gaps = tuple(
        event
        for event in events
        if event.evidence_type is DatasetQualityEvidenceType.KNOWN_GAP
    )
    suspected_gap_count = sum(
        event.evidence_type is DatasetQualityEvidenceType.SUSPECTED_GAP for event in events
    )
    return DatasetQualitySummary(
        known_gap_count=len(known_gaps),
        suspected_gap_count=suspected_gap_count,
        rejected_record_count=len(rejected_records),
        known_gap_duration=sum((event.interval_duration for event in known_gaps), timedelta()),
    )