"""Derived effective TimeAndSale tape reconstruction over immutable source history."""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID

from dicks_laboratory.dxlink_timesales import (
    DeferredDxLinkTimeAndSale,
    DxLinkTimeAndSaleProvenance,
)
from dicks_laboratory.models import InstrumentIdentity, TradeObservation


@dataclass(frozen=True)
class EffectiveTrade:
    """Derived analytical trade state; never a replacement for source history."""

    effective_trade_id: UUID
    original_observation_id: UUID
    instrument: InstrumentIdentity
    event_timestamp: datetime
    price: Decimal
    size: Decimal
    originating_source_index: int
    latest_source_index: int
    correction_count: int = 0


@dataclass(frozen=True)
class TapeReconstructionAnomaly:
    reason: str
    source_record_ref: str
    source_index: int | None


@dataclass(frozen=True)
class EffectiveTapeResult:
    effective_trades: tuple[EffectiveTrade, ...]
    applied_correction_count: int
    applied_cancel_count: int
    anomalies: tuple[TapeReconstructionAnomaly, ...]


@dataclass(frozen=True)
class _LifecycleItem:
    source_order: int
    source_index: int
    classification: str
    source_record_ref: str
    observation: TradeObservation | None = None
    provenance: DxLinkTimeAndSaleProvenance | None = None
    deferred: DeferredDxLinkTimeAndSale | None = None


def reconstruct_effective_tape(
    canonical_new_trades: tuple[TradeObservation, ...],
    new_provenance: tuple[DxLinkTimeAndSaleProvenance, ...],
    deferred_events: tuple[DeferredDxLinkTimeAndSale, ...],
) -> EffectiveTapeResult:
    """Apply documented same-index updates without mutating durable source facts."""
    trades_by_id = {trade.observation_id: trade for trade in canonical_new_trades}
    lifecycle = []
    for provenance in new_provenance:
        trade = trades_by_id.get(provenance.observation_id)
        if trade is None:
            continue
        lifecycle.append(
            _LifecycleItem(
                source_order=provenance.source_order,
                source_index=provenance.source_index,
                classification="NEW",
                source_record_ref=provenance.source_record_ref,
                observation=trade,
                provenance=provenance,
            )
        )
    for deferred in deferred_events:
        source_index = _as_int(deferred.source_record.source_index)
        if source_index is None:
            continue
        lifecycle.append(
            _LifecycleItem(
                source_order=deferred.source_order,
                source_index=source_index,
                classification=deferred.source_record.event_classification or "UNKNOWN",
                source_record_ref=deferred.source_record.source_record_ref,
                deferred=deferred,
            )
        )
    lifecycle.sort(key=lambda item: (item.source_order, item.source_index, item.source_record_ref))

    active: dict[int, EffectiveTrade] = {}
    canceled: set[int] = set()
    anomalies: list[TapeReconstructionAnomaly] = []
    corrections = 0
    cancels = 0
    for item in lifecycle:
        if item.classification == "NEW":
            if item.source_index in active or item.source_index in canceled:
                anomalies.append(TapeReconstructionAnomaly("DUPLICATE_SOURCE_INDEX", item.source_record_ref, item.source_index))
                continue
            trade = item.observation
            if trade is None:
                continue
            active[item.source_index] = EffectiveTrade(
                effective_trade_id=trade.observation_id,
                original_observation_id=trade.observation_id,
                instrument=trade.instrument,
                event_timestamp=trade.event_timestamp,
                price=trade.price,
                size=trade.size,
                originating_source_index=item.source_index,
                latest_source_index=item.source_index,
            )
            continue
        if item.classification == "CORRECTION":
            if item.source_index in canceled:
                anomalies.append(TapeReconstructionAnomaly("CORRECTION_AFTER_CANCEL", item.source_record_ref, item.source_index))
                continue
            target = active.get(item.source_index)
            if target is None:
                anomalies.append(TapeReconstructionAnomaly("TARGET_SOURCE_EVENT_NOT_FOUND", item.source_record_ref, item.source_index))
                continue
            deferred = item.deferred
            if deferred is None:
                continue
            price = _positive_decimal(deferred.source_record.price)
            size = _positive_decimal(deferred.source_record.size)
            timestamp = _source_timestamp(deferred.source_record.event_time)
            if price is None or size is None or timestamp is None:
                anomalies.append(TapeReconstructionAnomaly("INVALID_CORRECTION_STATE", item.source_record_ref, item.source_index))
                continue
            active[item.source_index] = replace(
                target,
                event_timestamp=timestamp,
                price=price,
                size=size,
                latest_source_index=item.source_index,
                correction_count=target.correction_count + 1,
            )
            corrections += 1
            continue
        if item.classification == "CANCEL":
            if item.source_index in canceled:
                anomalies.append(TapeReconstructionAnomaly("CANCEL_ALREADY_APPLIED", item.source_record_ref, item.source_index))
                continue
            if item.source_index not in active:
                anomalies.append(TapeReconstructionAnomaly("TARGET_SOURCE_EVENT_NOT_FOUND", item.source_record_ref, item.source_index))
                continue
            del active[item.source_index]
            canceled.add(item.source_index)
            cancels += 1
            continue
        anomalies.append(TapeReconstructionAnomaly("UNSUPPORTED_LIFECYCLE_ORDER", item.source_record_ref, item.source_index))
    return EffectiveTapeResult(
        effective_trades=tuple(sorted(active.values(), key=lambda trade: (trade.event_timestamp, trade.originating_source_index))),
        applied_correction_count=corrections,
        applied_cancel_count=cancels,
        anomalies=tuple(anomalies),
    )


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _positive_decimal(value: object) -> Decimal | None:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return decimal if decimal.is_finite() and decimal > 0 else None


def _source_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo is timezone.utc else None
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc) if milliseconds > 0 else None