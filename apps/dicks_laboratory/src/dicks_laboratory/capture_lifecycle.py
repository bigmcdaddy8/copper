"""Minimal capture lifecycle normalization for Phase 0F."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from uuid import uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dicks_laboratory.historical_csv import RejectedSourceRecord
from dicks_laboratory.models import DatasetIdentity
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType

_TIME_FORMAT = "%m/%d/%Y %H:%M:%S"


class CaptureLossPolicy(StrEnum):
    DISCONNECT_IMPLIES_DATA_LOSS = "DISCONNECT_IMPLIES_DATA_LOSS"
    DISCONNECT_DOES_NOT_IMPLY_DATA_LOSS = "DISCONNECT_DOES_NOT_IMPLY_DATA_LOSS"


@dataclass(frozen=True)
class CaptureLifecycleSourceRecord:
    """One source-native capture lifecycle row before canonical normalization."""

    source_record_ref: str
    raw_timestamp: str
    raw_event: str
    raw_reason: str


@dataclass(frozen=True)
class CaptureLifecycleImportPolicy:
    """Declared interpretation for one known capture-lifecycle CSV shape."""

    source_timezone: str | None
    source_locator: str
    dataset: DatasetIdentity
    loss_policy: CaptureLossPolicy


@dataclass(frozen=True)
class CaptureLifecycleNormalizationResult:
    """Normalized lifecycle facts and explicit source-record rejections."""

    accepted: tuple[DatasetQualityEvent, ...]
    rejected: tuple[RejectedSourceRecord, ...]


def load_capture_lifecycle_csv(path: Path) -> tuple[CaptureLifecycleSourceRecord, ...]:
    """Load source-native lifecycle rows using physical CSV line numbers."""
    with path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        return tuple(
            CaptureLifecycleSourceRecord(
                source_record_ref=f"row:{physical_line_number}",
                raw_timestamp=row["time"],
                raw_event=row["event"],
                raw_reason=row["reason"],
            )
            for physical_line_number, row in enumerate(reader, start=2)
        )


def normalize_capture_lifecycle(
    records: tuple[CaptureLifecycleSourceRecord, ...],
    policy: CaptureLifecycleImportPolicy,
) -> CaptureLifecycleNormalizationResult:
    """Normalize lifecycle facts without deciding whether a disconnect lost data."""
    source_timezone = _source_timezone(policy.source_timezone)
    if isinstance(source_timezone, str):
        return CaptureLifecycleNormalizationResult(
            accepted=(),
            rejected=tuple(RejectedSourceRecord(record.source_record_ref, source_timezone) for record in records),
        )

    accepted: list[DatasetQualityEvent] = []
    rejected: list[RejectedSourceRecord] = []
    for record in records:
        try:
            evidence_type = _evidence_type(record.raw_event)
            observed_at = _parse_timestamp(record.raw_timestamp, source_timezone)
        except ValueError as exc:
            rejected.append(RejectedSourceRecord(record.source_record_ref, str(exc)))
            continue
        accepted.append(
            DatasetQualityEvent(
                event_id=uuid5(policy.dataset.dataset_id, record.source_record_ref),
                dataset_id=policy.dataset.dataset_id,
                evidence_type=evidence_type,
                detail=record.raw_reason,
                observed_at=observed_at,
                source_record_ref=record.source_record_ref,
            )
        )
    return CaptureLifecycleNormalizationResult(tuple(accepted), tuple(rejected))


def derive_gap_conclusions(
    lifecycle_events: tuple[DatasetQualityEvent, ...],
    policy: CaptureLifecycleImportPolicy,
) -> tuple[DatasetQualityEvent, ...]:
    """Derive finite known gaps only where declared capture semantics permit it."""
    if policy.loss_policy is CaptureLossPolicy.DISCONNECT_DOES_NOT_IMPLY_DATA_LOSS:
        return ()

    conclusions: list[DatasetQualityEvent] = []
    disconnected: DatasetQualityEvent | None = None
    for event in lifecycle_events:
        if event.evidence_type is DatasetQualityEvidenceType.SOURCE_DISCONNECTED:
            disconnected = event
        elif (
            event.evidence_type is DatasetQualityEvidenceType.SOURCE_RECONNECTED
            and disconnected is not None
            and disconnected.observed_at is not None
            and event.observed_at is not None
        ):
            conclusions.append(
                DatasetQualityEvent(
                    event_id=uuid5(
                        policy.dataset.dataset_id,
                        f"known-gap:{disconnected.source_record_ref}:{event.source_record_ref}",
                    ),
                    dataset_id=policy.dataset.dataset_id,
                    evidence_type=DatasetQualityEvidenceType.KNOWN_GAP,
                    detail="Derived from explicit disconnect/reconnect semantics.",
                    interval_start=disconnected.observed_at,
                    interval_end=event.observed_at,
                    supporting_event_ids=(disconnected.event_id, event.event_id),
                )
            )
            disconnected = None
    return tuple(conclusions)


def _source_timezone(source_timezone: str | None) -> ZoneInfo | str:
    if not source_timezone:
        return "SOURCE_TIMEZONE_NOT_DECLARED"
    try:
        return ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return "SOURCE_TIMEZONE_INVALID"


def _evidence_type(raw_event: str) -> DatasetQualityEvidenceType:
    mapping = {
        "connected": DatasetQualityEvidenceType.SOURCE_CONNECTED,
        "disconnected": DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
        "reconnected": DatasetQualityEvidenceType.SOURCE_RECONNECTED,
        "stopped": DatasetQualityEvidenceType.CAPTURE_STOPPED,
    }
    try:
        return mapping[raw_event]
    except KeyError as exc:
        raise ValueError("UNSUPPORTED_LIFECYCLE_EVENT") from exc


def _parse_timestamp(raw_timestamp: str, source_timezone: ZoneInfo) -> datetime:
    try:
        source_local = datetime.strptime(raw_timestamp, _TIME_FORMAT).replace(tzinfo=source_timezone)
    except ValueError as exc:
        raise ValueError("MALFORMED_TIMESTAMP") from exc
    return source_local.astimezone(timezone.utc)