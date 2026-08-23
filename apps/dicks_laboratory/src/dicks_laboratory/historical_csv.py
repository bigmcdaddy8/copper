"""Minimal historical CSV source-record normalization for Phase 0D."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dicks_laboratory.fixture import ES_SEP_2026
from dicks_laboratory.models import DatasetIdentity, TradeObservation

_TIME_FORMAT = "%m/%d/%Y %H:%M:%S"
_NORMALIZER_VERSION = "phase-0d-csv-v1"


class _NormalizationError(ValueError):
    pass


@dataclass(frozen=True)
class HistoricalTradeSourceRecord:
    """One CSV data row before it becomes a canonical market observation."""

    source_record_ref: str
    raw_timestamp: str
    raw_contract: str
    raw_price: str
    raw_quantity: str


@dataclass(frozen=True)
class HistoricalCsvImportPolicy:
    """Declared interpretation for one known historical CSV source shape."""

    source_timezone: str | None
    source_locator: str
    dataset: DatasetIdentity


@dataclass(frozen=True)
class AcceptedTradeNormalization:
    """A canonical observation and the source row that produced it."""

    observation: TradeObservation
    source_record_ref: str


@dataclass(frozen=True)
class RejectedSourceRecord:
    """A source row that could not be normalized without guessing."""

    source_record_ref: str
    reason: str


@dataclass(frozen=True)
class NormalizationResult:
    """The explicit accepted/rejected boundary for one source import."""

    accepted: tuple[AcceptedTradeNormalization, ...]
    rejected: tuple[RejectedSourceRecord, ...]

    @property
    def observations(self) -> tuple[TradeObservation, ...]:
        return tuple(item.observation for item in self.accepted)


def load_historical_trade_csv(path: Path) -> tuple[HistoricalTradeSourceRecord, ...]:
    """Load source-native rows using physical CSV line numbers, including the header."""
    with path.open(newline="", encoding="utf-8") as source_file:
        reader = csv.DictReader(source_file)
        return tuple(
            HistoricalTradeSourceRecord(
                source_record_ref=f"row:{physical_line_number}",
                raw_timestamp=row["time"],
                raw_contract=row["contract"],
                raw_price=row["last"],
                raw_quantity=row["qty"],
            )
            for physical_line_number, row in enumerate(reader, start=2)
        )


def normalize_historical_trades(
    records: tuple[HistoricalTradeSourceRecord, ...],
    policy: HistoricalCsvImportPolicy,
) -> NormalizationResult:
    """Normalize known source rows without guessing unknown time or instrument semantics."""
    timezone_result = _source_timezone(policy.source_timezone)
    if isinstance(timezone_result, RejectedSourceRecord):
        return NormalizationResult(
            accepted=(),
            rejected=tuple(
                RejectedSourceRecord(record.source_record_ref, timezone_result.reason)
                for record in records
            ),
        )

    accepted: list[AcceptedTradeNormalization] = []
    rejected: list[RejectedSourceRecord] = []
    for dataset_sequence, record in enumerate(records, start=1):
        try:
            observation = TradeObservation(
                observation_id=uuid5(policy.dataset.dataset_id, record.source_record_ref),
                dataset_id=policy.dataset.dataset_id,
                dataset_sequence=dataset_sequence,
                instrument=_instrument_for_alias(record.raw_contract),
                event_timestamp=_parse_timestamp(record.raw_timestamp, timezone_result),
                price=_parse_decimal(record.raw_price, "MALFORMED_PRICE"),
                size=_parse_decimal(record.raw_quantity, "MALFORMED_QUANTITY"),
            )
        except _NormalizationError as exc:
            rejected.append(RejectedSourceRecord(record.source_record_ref, str(exc)))
            continue
        except ValueError:
            rejected.append(RejectedSourceRecord(record.source_record_ref, "INVALID_TRADE"))
            continue
        accepted.append(AcceptedTradeNormalization(observation, record.source_record_ref))
    return NormalizationResult(tuple(accepted), tuple(rejected))


def _source_timezone(source_timezone: str | None) -> ZoneInfo | RejectedSourceRecord:
    if not source_timezone:
        return RejectedSourceRecord("", "SOURCE_TIMEZONE_NOT_DECLARED")
    try:
        return ZoneInfo(source_timezone)
    except ZoneInfoNotFoundError:
        return RejectedSourceRecord("", "SOURCE_TIMEZONE_INVALID")


def _instrument_for_alias(raw_contract: str):
    if raw_contract != "ESU26":
        raise _NormalizationError("UNSUPPORTED_SOURCE_CONTRACT")
    return ES_SEP_2026


def _parse_timestamp(raw_timestamp: str, source_timezone: ZoneInfo) -> datetime:
    try:
        source_local = datetime.strptime(raw_timestamp, _TIME_FORMAT).replace(tzinfo=source_timezone)
    except ValueError as exc:
        raise _NormalizationError("MALFORMED_TIMESTAMP") from exc
    return source_local.astimezone(timezone.utc)


def _parse_decimal(raw_value: str, reason: str) -> Decimal:
    try:
        value = Decimal(raw_value)
    except InvalidOperation as exc:
        raise _NormalizationError(reason) from exc
    if not value.is_finite():
        raise _NormalizationError(reason)
    return value