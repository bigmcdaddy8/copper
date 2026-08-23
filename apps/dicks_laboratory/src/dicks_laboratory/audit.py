"""Read-only factual inspection of one durable Laboratory dataset."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from dicks_laboratory.models import DatasetIdentity
from dicks_laboratory.dxlink_timesales import DeferredDxLinkTimeAndSale
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType, summarize_dataset_quality
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.store import LaboratoryStore


@dataclass(frozen=True)
class GapAuditDetail:
    event_id: UUID
    evidence_type: DatasetQualityEvidenceType
    interval_start: datetime
    interval_end: datetime
    duration: timedelta
    supporting_event_ids: tuple[UUID, ...]


@dataclass(frozen=True)
class LifecycleAuditDetail:
    event_id: UUID
    evidence_type: DatasetQualityEvidenceType
    observed_at: datetime
    source_record_ref: str | None
    detail: str


@dataclass(frozen=True)
class RejectionAuditDetail:
    rejection_id: UUID
    source_kind: RejectionSourceKind
    source_record_ref: str
    source_order: int
    reason: str
    detail: str | None


@dataclass(frozen=True)
class DeferredTimeAndSaleAuditDetail:
    deferred_event_id: UUID
    event_classification: str
    source_record_ref: str
    source_time: datetime | None
    source_index: int | None
    source_sequence: int | None
    source_trade_id: int | None
    price: object
    size: object
    valid_tick: object
    received_at: datetime


@dataclass(frozen=True)
class DatasetAudit:
    """Immutable factual read model; it deliberately contains no fitness verdict."""

    dataset: DatasetIdentity
    accepted_trade_count: int
    first_trade_event_timestamp: datetime | None
    last_trade_event_timestamp: datetime | None
    first_dataset_sequence: int | None
    last_dataset_sequence: int | None
    instrument_ids: tuple[str, ...]
    rejected_record_count: int
    rejection_counts_by_source_kind: tuple[tuple[RejectionSourceKind, int], ...]
    rejection_counts_by_reason: tuple[tuple[str, int], ...]
    lifecycle_counts: tuple[tuple[DatasetQualityEvidenceType, int], ...]
    known_gap_count: int
    suspected_gap_count: int
    known_gap_duration: timedelta
    gaps: tuple[GapAuditDetail, ...]
    lifecycle_evidence: tuple[LifecycleAuditDetail, ...]
    rejections: tuple[RejectionAuditDetail, ...]
    deferred_timesale_count: int
    deferred_timesale_counts_by_classification: tuple[tuple[str, int], ...]
    deferred_timesales: tuple[DeferredTimeAndSaleAuditDetail, ...]


def audit_dataset(store: LaboratoryStore, dataset_id: UUID) -> DatasetAudit:
    """Build a deterministic audit from existing durable domain facts."""
    dataset = store.load_dataset(dataset_id)
    trades = store.load_trade_observations(dataset_id)
    events = store.load_quality_events(dataset_id)
    rejections = store.load_rejections(dataset_id)
    deferred = store.load_deferred_dxlink_time_and_sales(dataset_id)
    summary = summarize_dataset_quality(events, rejections)

    trade_timestamps = tuple(trade.event_timestamp for trade in trades)
    instruments = tuple(sorted({trade.instrument.canonical_id for trade in trades}))
    gaps = tuple(
        GapAuditDetail(
            event_id=event.event_id,
            evidence_type=event.evidence_type,
            interval_start=event.interval_start,
            interval_end=event.interval_end,
            duration=event.interval_duration,
            supporting_event_ids=event.supporting_event_ids,
        )
        for event in sorted(
            (event for event in events if event.interval_start is not None),
            key=lambda event: (event.interval_start, event.event_id),
        )
    )
    lifecycle = tuple(
        LifecycleAuditDetail(
            event_id=event.event_id,
            evidence_type=event.evidence_type,
            observed_at=event.observed_at,
            source_record_ref=event.source_record_ref,
            detail=event.detail,
        )
        for event in sorted(
            (event for event in events if event.observed_at is not None),
            key=lambda event: (event.observed_at, event.event_id),
        )
    )
    return DatasetAudit(
        dataset=dataset,
        accepted_trade_count=len(trades),
        first_trade_event_timestamp=trade_timestamps[0] if trades else None,
        last_trade_event_timestamp=trade_timestamps[-1] if trades else None,
        first_dataset_sequence=trades[0].dataset_sequence if trades else None,
        last_dataset_sequence=trades[-1].dataset_sequence if trades else None,
        instrument_ids=instruments,
        rejected_record_count=len(rejections),
        rejection_counts_by_source_kind=_count_by_source_kind(rejections),
        rejection_counts_by_reason=_count_by_reason(rejections),
        lifecycle_counts=_count_lifecycle(events),
        known_gap_count=summary.known_gap_count,
        suspected_gap_count=summary.suspected_gap_count,
        known_gap_duration=summary.known_gap_duration,
        gaps=gaps,
        lifecycle_evidence=lifecycle,
        rejections=tuple(
            RejectionAuditDetail(
                rejection_id=rejection.rejection_id,
                source_kind=rejection.source_kind,
                source_record_ref=rejection.source_record_ref,
                source_order=rejection.source_order,
                reason=rejection.reason,
                detail=rejection.detail,
            )
            for rejection in rejections
        ),
        deferred_timesale_count=len(deferred),
        deferred_timesale_counts_by_classification=_count_deferred_by_classification(deferred),
        deferred_timesales=tuple(
            DeferredTimeAndSaleAuditDetail(
                deferred_event_id=event.deferred_event_id,
                event_classification=event.source_record.event_classification or "UNKNOWN",
                source_record_ref=event.source_record.source_record_ref,
                source_time=_source_time(event),
                source_index=_as_int(event.source_record.source_index),
                source_sequence=_as_int(event.source_record.source_sequence),
                source_trade_id=_as_int(event.source_record.source_trade_id),
                price=event.source_record.price,
                size=event.source_record.size,
                valid_tick=event.source_record.valid_tick,
                received_at=event.source_record.received_at,
            )
            for event in deferred
        ),
    )


def _count_by_source_kind(
    rejections: tuple[NormalizationRejection, ...],
) -> tuple[tuple[RejectionSourceKind, int], ...]:
    counts: dict[RejectionSourceKind, int] = {}
    for rejection in rejections:
        counts[rejection.source_kind] = counts.get(rejection.source_kind, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: item[0].value))


def _count_by_reason(
    rejections: tuple[NormalizationRejection, ...],
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for rejection in rejections:
        counts[rejection.reason] = counts.get(rejection.reason, 0) + 1
    return tuple(sorted(counts.items()))


def _count_lifecycle(
    events: tuple[DatasetQualityEvent, ...],
) -> tuple[tuple[DatasetQualityEvidenceType, int], ...]:
    counts: dict[DatasetQualityEvidenceType, int] = {}
    for event in events:
        if event.observed_at is not None:
            counts[event.evidence_type] = counts.get(event.evidence_type, 0) + 1
    return tuple(sorted(counts.items(), key=lambda item: item[0].value))


def _count_deferred_by_classification(
    events: tuple[DeferredDxLinkTimeAndSale, ...],
) -> tuple[tuple[str, int], ...]:
    counts: dict[str, int] = {}
    for event in events:
        classification = event.source_record.event_classification or "UNKNOWN"
        counts[classification] = counts.get(classification, 0) + 1
    return tuple(sorted(counts.items()))


def _source_time(event: DeferredDxLinkTimeAndSale) -> datetime | None:
    value = event.source_record.event_time
    return value if isinstance(value, datetime) else None


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None