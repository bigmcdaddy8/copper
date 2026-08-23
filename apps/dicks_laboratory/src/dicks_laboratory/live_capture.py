"""Human-invoked, explicitly bounded durable DXLink TimeAndSale capture workflow."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable, Protocol
from uuid import UUID, uuid4, uuid5

from K9.tastytrade.dxlink import DxLinkError, DxLinkSourceEvent
from dicks_laboratory.audit import DatasetAudit, audit_dataset
from dicks_laboratory.dxlink_timesales import normalize_dxlink_time_and_sales, source_records_from_events
from dicks_laboratory.effective_tape import EffectiveTapeResult, reconstruct_effective_tape
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.vwap import calculate_vwap

_ES_DISPLAY_SYMBOL = "/ESU6"
_ES_STREAMER_SYMBOL = "/ESU26:XCME"
_ES_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)


class SourceCollector(Protocol):
    def collect(
        self,
        streamer_symbol: str,
        event_types: tuple[str, ...],
        duration_seconds: float,
        max_events: int,
        on_event: Callable[[DxLinkSourceEvent], None] | None = None,
        on_connected: Callable[[], None] | None = None,
        retain_events: bool = True,
    ) -> tuple[DxLinkSourceEvent, ...]: ...


@dataclass(frozen=True)
class LiveCaptureResult:
    dataset_id: UUID
    database_path: Path
    requested_duration_seconds: float
    capture_started_at: datetime
    capture_ended_at: datetime
    source_event_count: int
    classification_counts: tuple[tuple[str, int], ...]
    accepted_trade_count: int
    deferred_event_count: int
    rejection_count: int
    canonical_vwap: Decimal | None
    total_accepted_volume: Decimal
    effective_tape: EffectiveTapeResult
    audit: DatasetAudit


def capture_es_timesales_dataset(
    database_path: Path,
    collector: SourceCollector,
    requested_duration_seconds: float,
    max_events: int,
) -> LiveCaptureResult:
    """Capture one bounded authentic ES study dataset with per-event SQLite durability."""
    if not 0 < requested_duration_seconds <= 30 * 60:
        raise ValueError("requested_duration_seconds must be between 0 and 1800.")
    if not 0 < max_events <= 100_000:
        raise ValueError("max_events must be between 1 and 100000.")
    database_path.parent.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(tz=timezone.utc)
    dataset = DatasetIdentity(
        dataset_id=uuid4(),
        kind=DatasetKind.HISTORICAL_IMPORT,
        label=f"bounded-live-es-{started_at.strftime('%Y%m%dT%H%M%SZ')}",
        source_locator="TASTYTRADE_DXLINK:/ESU26:XCME:TimeAndSale",
        source_timezone="UTC epoch milliseconds",
        normalizer_version="phase-0l-live-capture-v1",
        capture_started_at=started_at,
        origin=DatasetOrigin.AUTHENTIC_SOURCE,
    )
    store = LaboratoryStore(database_path)
    store.save_dataset(dataset)
    _save_lifecycle(store, dataset.dataset_id, "CAPTURE_STARTED", started_at)
    ended_at = started_at
    source_count = 0
    classifications: Counter[str] = Counter()
    accepted_count = 0
    try:
        def on_connected() -> None:
            _save_lifecycle(store, dataset.dataset_id, "SOURCE_CONNECTED", datetime.now(tz=timezone.utc))

        def on_event(event: DxLinkSourceEvent) -> None:
            nonlocal source_count, accepted_count
            source_count += 1
            record = source_records_from_events((event,), start_source_order=source_count)[0]
            classifications[record.event_classification or "UNKNOWN"] += 1
            result = normalize_dxlink_time_and_sales(
                (record,),
                dataset,
                _ES_INSTRUMENT,
                _ES_STREAMER_SYMBOL,
                start_source_order=source_count,
                start_dataset_sequence=accepted_count + 1,
            )
            if result.observations:
                accepted_count += len(result.observations)
                store.save_trade_observations(result.observations)
                store.save_dxlink_time_and_sale_provenance(result.provenance)
            if result.deferred:
                store.save_deferred_dxlink_time_and_sales(result.deferred)
            if result.rejected:
                store.save_rejections(result.rejected)

        collector.collect(
            _ES_STREAMER_SYMBOL,
            ("TimeAndSale",),
            requested_duration_seconds,
            max_events,
            on_event=on_event,
            on_connected=on_connected,
            retain_events=False,
        )
        ended_at = datetime.now(tz=timezone.utc)
        _save_lifecycle(store, dataset.dataset_id, "CAPTURE_STOPPED", ended_at)
    except DxLinkError:
        ended_at = datetime.now(tz=timezone.utc)
        _save_lifecycle(store, dataset.dataset_id, "SOURCE_DISCONNECTED", ended_at)
    finally:
        store.update_dataset_capture_ended(dataset.dataset_id, ended_at)
        store.close()

    reopened = LaboratoryStore(database_path)
    trades = reopened.load_trade_observations(dataset.dataset_id)
    provenance = reopened.load_dxlink_time_and_sale_provenance(dataset.dataset_id)
    deferred = reopened.load_deferred_dxlink_time_and_sales(dataset.dataset_id)
    tape = reconstruct_effective_tape(trades, provenance, deferred)
    audit = audit_dataset(reopened, dataset.dataset_id)
    total_volume = sum((trade.size for trade in trades), Decimal("0"))
    result = LiveCaptureResult(
        dataset_id=dataset.dataset_id,
        database_path=database_path,
        requested_duration_seconds=requested_duration_seconds,
        capture_started_at=started_at,
        capture_ended_at=ended_at,
        source_event_count=source_count,
        classification_counts=tuple(sorted(classifications.items())),
        accepted_trade_count=len(trades),
        deferred_event_count=len(deferred),
        rejection_count=len(reopened.load_rejections(dataset.dataset_id)),
        canonical_vwap=calculate_vwap(trades) if trades else None,
        total_accepted_volume=total_volume,
        effective_tape=tape,
        audit=audit,
    )
    reopened.close()
    return result


def _save_lifecycle(store: LaboratoryStore, dataset_id: UUID, event_name: str, observed_at: datetime) -> None:
    evidence_type = DatasetQualityEvidenceType(event_name)
    event_id = uuid5(dataset_id, f"lifecycle:{event_name}:{observed_at.isoformat()}")
    store.save_quality_events((
        DatasetQualityEvent(
            event_id=event_id,
            dataset_id=dataset_id,
            evidence_type=evidence_type,
            detail=event_name.lower(),
            observed_at=observed_at,
        ),
    ))


def effective_vwap(tape: EffectiveTapeResult) -> Decimal | None:
    if not tape.effective_trades:
        return None
    volume = sum((trade.size for trade in tape.effective_trades), Decimal("0"))
    return sum((trade.price * trade.size for trade in tape.effective_trades), Decimal("0")) / volume