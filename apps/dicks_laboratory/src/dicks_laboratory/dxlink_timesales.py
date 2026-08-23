"""Strict source-to-canonical normalization for bounded DXLink TimeAndSale captures."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid5

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.models import DatasetIdentity, InstrumentIdentity, TradeObservation
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind


@dataclass(frozen=True)
class DxLinkTimeAndSaleSourceRecord:
    """Source-shaped DXLink TimeAndSale evidence before canonical trade acceptance."""

    source_record_ref: str
    event_symbol: str | None
    event_time: object
    event_classification: str | None
    source_index: object
    source_sequence: object
    source_trade_id: object
    event_flags: object
    exchange_code: object
    price: object
    size: object
    bid_price: object
    ask_price: object
    exchange_sale_conditions: object
    trade_through_exempt: object
    aggressor_side: object
    spread_leg: object
    extended_trading_hours: object
    valid_tick: object
    received_at: datetime


@dataclass(frozen=True)
class DxLinkTimeAndSaleProvenance:
    """Durable source provenance for one accepted canonical TimeAndSale trade."""

    observation_id: UUID
    source_record_ref: str
    source_order: int
    source_index: int
    source_sequence: int
    source_trade_id: int | None
    received_at: datetime


@dataclass(frozen=True)
class AcceptedDxLinkTimeAndSaleNormalization:
    observation: TradeObservation
    source_record: DxLinkTimeAndSaleSourceRecord
    provenance: DxLinkTimeAndSaleProvenance


@dataclass(frozen=True)
class DeferredDxLinkTimeAndSale:
    """A correction/cancel source fact intentionally excluded from canonical trade state."""

    deferred_event_id: UUID
    dataset_id: UUID
    source_order: int
    source_record: DxLinkTimeAndSaleSourceRecord
    reason: str


@dataclass(frozen=True)
class DxLinkTimeAndSaleNormalizationResult:
    accepted: tuple[AcceptedDxLinkTimeAndSaleNormalization, ...]
    rejected: tuple[NormalizationRejection, ...]
    deferred: tuple[DeferredDxLinkTimeAndSale, ...]

    @property
    def observations(self) -> tuple[TradeObservation, ...]:
        return tuple(item.observation for item in self.accepted)

    @property
    def provenance(self) -> tuple[DxLinkTimeAndSaleProvenance, ...]:
        return tuple(item.provenance for item in self.accepted)


def source_records_from_events(
    events: tuple[DxLinkSourceEvent, ...],
    start_source_order: int = 1,
) -> tuple[DxLinkTimeAndSaleSourceRecord, ...]:
    """Assign bounded-capture-local references without deduplicating source events."""
    records = []
    for source_order, event in enumerate(events, start=start_source_order):
        if event.event_type != "TimeAndSale":
            continue
        fields = event.fields
        records.append(
            DxLinkTimeAndSaleSourceRecord(
                source_record_ref=f"event:{source_order}",
                event_symbol=_string_or_none(fields.get("eventSymbol")),
                event_time=fields.get("time"),
                event_classification=_string_or_none(fields.get("type")),
                source_index=fields.get("index"),
                source_sequence=fields.get("sequence"),
                source_trade_id=fields.get("tradeId"),
                event_flags=fields.get("eventFlags"),
                exchange_code=fields.get("exchangeCode"),
                price=fields.get("price"),
                size=fields.get("size"),
                bid_price=fields.get("bidPrice"),
                ask_price=fields.get("askPrice"),
                exchange_sale_conditions=fields.get("exchangeSaleConditions"),
                trade_through_exempt=fields.get("tradeThroughExempt"),
                aggressor_side=fields.get("aggressorSide"),
                spread_leg=fields.get("spreadLeg"),
                extended_trading_hours=fields.get("extendedTradingHours"),
                valid_tick=fields.get("validTick"),
                received_at=event.received_at,
            )
        )
    return tuple(records)


def normalize_dxlink_time_and_sales(
    records: tuple[DxLinkTimeAndSaleSourceRecord, ...],
    dataset: DatasetIdentity,
    instrument: InstrumentIdentity,
    expected_streamer_symbol: str,
    start_source_order: int = 1,
    start_dataset_sequence: int = 1,
) -> DxLinkTimeAndSaleNormalizationResult:
    """Accept only explicit NEW/valid/positive TimeAndSale source events."""
    accepted: list[AcceptedDxLinkTimeAndSaleNormalization] = []
    rejected: list[NormalizationRejection] = []
    deferred: list[DeferredDxLinkTimeAndSale] = []
    for source_order, record in enumerate(records, start=start_source_order):
        if record.event_classification in {"CORRECTION", "CANCEL"}:
            deferred.append(
                DeferredDxLinkTimeAndSale(
                    deferred_event_id=uuid5(dataset.dataset_id, f"deferred:{record.source_record_ref}"),
                    dataset_id=dataset.dataset_id,
                    source_order=source_order,
                    source_record=record,
                    reason=f"DXLINK_{record.event_classification}",
                )
            )
            continue
        reason = _rejection_reason(record, expected_streamer_symbol)
        if reason is not None:
            rejected.append(
                NormalizationRejection(
                    rejection_id=uuid5(dataset.dataset_id, f"rejection:{record.source_record_ref}"),
                    dataset_id=dataset.dataset_id,
                    source_kind=RejectionSourceKind.DXLINK_TIME_AND_SALE,
                    source_record_ref=record.source_record_ref,
                    source_order=source_order,
                    reason=reason,
                )
            )
            continue
        event_timestamp = _timestamp_from_milliseconds(record.event_time)
        price = _positive_decimal(record.price)
        size = _positive_decimal(record.size)
        source_index = int(record.source_index)
        source_sequence = int(record.source_sequence)
        source_trade_id = _optional_int(record.source_trade_id)
        observation = TradeObservation(
            observation_id=uuid5(dataset.dataset_id, f"observation:{record.source_record_ref}"),
            dataset_id=dataset.dataset_id,
            dataset_sequence=start_dataset_sequence + len(accepted),
            instrument=instrument,
            event_timestamp=event_timestamp,
            price=price,
            size=size,
        )
        provenance = DxLinkTimeAndSaleProvenance(
            observation_id=observation.observation_id,
            source_record_ref=record.source_record_ref,
            source_order=source_order,
            source_index=source_index,
            source_sequence=source_sequence,
            source_trade_id=source_trade_id,
            received_at=record.received_at,
        )
        accepted.append(AcceptedDxLinkTimeAndSaleNormalization(observation, record, provenance))
    return DxLinkTimeAndSaleNormalizationResult(tuple(accepted), tuple(rejected), tuple(deferred))


def _rejection_reason(record: DxLinkTimeAndSaleSourceRecord, expected_streamer_symbol: str) -> str | None:
    if record.event_symbol != expected_streamer_symbol:
        return "UNEXPECTED_DXLINK_STREAMER_SYMBOL"
    if record.event_classification != "NEW":
        return "UNSUPPORTED_DXLINK_EVENT_CLASSIFICATION"
    if record.valid_tick is not True:
        return "INVALID_DXLINK_TICK"
    if not _positive_milliseconds(record.event_time):
        return "INVALID_DXLINK_EVENT_TIME"
    if _positive_decimal_or_none(record.price) is None:
        return "INVALID_DXLINK_PRICE"
    if _positive_decimal_or_none(record.size) is None:
        return "INVALID_DXLINK_SIZE"
    if _nonnegative_int_or_none(record.source_index) is None:
        return "INVALID_DXLINK_INDEX"
    if _nonnegative_int_or_none(record.source_sequence) is None:
        return "INVALID_DXLINK_SEQUENCE"
    if record.received_at.tzinfo is not timezone.utc:
        return "INVALID_DXLINK_RECEIPT_TIME"
    return None


def _timestamp_from_milliseconds(value: object) -> datetime:
    milliseconds = int(value)
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc)


def _positive_milliseconds(value: object) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _positive_decimal(value: object) -> Decimal:
    result = _positive_decimal_or_none(value)
    if result is None:
        raise ValueError("DXLink value was not a positive finite Decimal.")
    return result


def _positive_decimal_or_none(value: object) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return result if result.is_finite() and result > 0 else None


def _nonnegative_int_or_none(value: object) -> int | None:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result >= 0 else None


def _optional_int(value: object) -> int | None:
    return _nonnegative_int_or_none(value)


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None