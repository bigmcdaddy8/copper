"""Small SQLite persistence proof for canonical Dick's Laboratory facts."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from dicks_laboratory.models import (
    DatasetIdentity,
    DatasetKind,
    DatasetOrigin,
    InstrumentIdentity,
    InstrumentKind,
    TradeAction,
    TradeObservation,
)
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.dxlink_timesales import (
    DeferredDxLinkTimeAndSale,
    DxLinkTimeAndSaleProvenance,
    DxLinkTimeAndSaleSourceRecord,
)

_DDL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS datasets (
    dataset_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    origin TEXT NOT NULL,
    label TEXT NOT NULL,
    source_locator TEXT,
    source_timezone TEXT,
    normalizer_version TEXT,
    capture_started_at TEXT,
    capture_ended_at TEXT,
    parent_dataset_id TEXT REFERENCES datasets(dataset_id),
    transformation_policy TEXT,
    transformation_version TEXT,
    random_seed INTEGER
);

CREATE TABLE IF NOT EXISTS instruments (
    canonical_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    exchange TEXT NOT NULL,
    root TEXT NOT NULL,
    expiration_year INTEGER NOT NULL,
    expiration_month INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS trade_observations (
    observation_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    dataset_sequence INTEGER NOT NULL,
    instrument_id TEXT NOT NULL REFERENCES instruments(canonical_id),
    event_timestamp TEXT NOT NULL,
    price TEXT NOT NULL,
    size TEXT NOT NULL,
    trade_action TEXT NOT NULL,
    UNIQUE(dataset_id, dataset_sequence)
);

CREATE TABLE IF NOT EXISTS dataset_quality_events (
    event_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    evidence_type TEXT NOT NULL,
    detail TEXT NOT NULL,
    observed_at TEXT,
    interval_start TEXT,
    interval_end TEXT,
    source_record_ref TEXT
);

CREATE TABLE IF NOT EXISTS quality_event_links (
    event_id TEXT NOT NULL REFERENCES dataset_quality_events(event_id),
    supporting_event_id TEXT NOT NULL REFERENCES dataset_quality_events(event_id),
    link_sequence INTEGER NOT NULL,
    PRIMARY KEY (event_id, link_sequence)
);

CREATE TABLE IF NOT EXISTS normalization_rejections (
    rejection_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_kind TEXT NOT NULL,
    source_record_ref TEXT NOT NULL,
    source_order INTEGER NOT NULL,
    reason TEXT NOT NULL,
    detail TEXT
);

CREATE TABLE IF NOT EXISTS observation_source_provenance (
    observation_id TEXT PRIMARY KEY REFERENCES trade_observations(observation_id),
    source_kind TEXT NOT NULL,
    source_record_ref TEXT NOT NULL,
    source_index INTEGER NOT NULL,
    source_sequence INTEGER NOT NULL,
    source_trade_id INTEGER,
    received_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deferred_dxlink_timesale_events (
    deferred_event_id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_order INTEGER NOT NULL,
    source_record_ref TEXT NOT NULL,
    reason TEXT NOT NULL,
    event_symbol TEXT,
    event_time TEXT,
    event_classification TEXT NOT NULL,
    source_index INTEGER NOT NULL,
    source_sequence INTEGER NOT NULL,
    source_trade_id INTEGER,
    event_flags INTEGER,
    exchange_code TEXT,
    price TEXT,
    size TEXT,
    bid_price TEXT,
    ask_price TEXT,
    exchange_sale_conditions TEXT,
    trade_through_exempt TEXT,
    aggressor_side TEXT,
    spread_leg INTEGER,
    extended_trading_hours INTEGER,
    valid_tick INTEGER,
    received_at TEXT NOT NULL
);
"""


class LaboratoryStore:
    """Owns a small SQLite schema and canonical object serialization for Phase 0G."""

    def __init__(self, db_path: Path) -> None:
        self._connection = sqlite3.connect(db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.executescript(_DDL)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def save_dataset(self, dataset: DatasetIdentity) -> None:
        self._connection.execute(
            """
            INSERT INTO datasets (
                dataset_id, kind, origin, label, source_locator, source_timezone,
                normalizer_version, capture_started_at, capture_ended_at, parent_dataset_id,
                transformation_policy, transformation_version, random_seed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(dataset.dataset_id),
                dataset.kind.value,
                dataset.origin.value,
                dataset.label,
                dataset.source_locator,
                dataset.source_timezone,
                dataset.normalizer_version,
                _timestamp_text(dataset.capture_started_at),
                _timestamp_text(dataset.capture_ended_at),
                str(dataset.parent_dataset_id) if dataset.parent_dataset_id else None,
                dataset.transformation_policy,
                dataset.transformation_version,
                dataset.random_seed,
            ),
        )
        self._connection.commit()

    def save_trade_observations(self, trades: tuple[TradeObservation, ...]) -> None:
        for trade in trades:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO instruments (
                    canonical_id, kind, exchange, root, expiration_year, expiration_month
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    trade.instrument.canonical_id,
                    trade.instrument.kind.value,
                    trade.instrument.exchange,
                    trade.instrument.root,
                    trade.instrument.expiration_year,
                    trade.instrument.expiration_month,
                ),
            )
            self._connection.execute(
                """
                INSERT INTO trade_observations (
                    observation_id, dataset_id, dataset_sequence, instrument_id,
                    event_timestamp, price, size, trade_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(trade.observation_id),
                    str(trade.dataset_id),
                    trade.dataset_sequence,
                    trade.instrument.canonical_id,
                    _timestamp_text(trade.event_timestamp),
                    str(trade.price),
                    str(trade.size),
                    trade.trade_action.value,
                ),
            )
        self._connection.commit()

    def save_quality_events(self, events: tuple[DatasetQualityEvent, ...]) -> None:
        for event in events:
            self._connection.execute(
                """
                INSERT INTO dataset_quality_events (
                    event_id, dataset_id, evidence_type, detail, observed_at,
                    interval_start, interval_end, source_record_ref
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.event_id),
                    str(event.dataset_id),
                    event.evidence_type.value,
                    event.detail,
                    _timestamp_text(event.observed_at),
                    _timestamp_text(event.interval_start),
                    _timestamp_text(event.interval_end),
                    event.source_record_ref,
                ),
            )
            for sequence, supporting_event_id in enumerate(event.supporting_event_ids, start=1):
                self._connection.execute(
                    """
                    INSERT INTO quality_event_links (event_id, supporting_event_id, link_sequence)
                    VALUES (?, ?, ?)
                    """,
                    (str(event.event_id), str(supporting_event_id), sequence),
                )
        self._connection.commit()

    def save_rejections(self, rejections: tuple[NormalizationRejection, ...]) -> None:
        for rejection in rejections:
            self._connection.execute(
                """
                INSERT INTO normalization_rejections (
                    rejection_id, dataset_id, source_kind, source_record_ref,
                    source_order, reason, detail
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(rejection.rejection_id),
                    str(rejection.dataset_id),
                    rejection.source_kind.value,
                    rejection.source_record_ref,
                    rejection.source_order,
                    rejection.reason,
                    rejection.detail,
                ),
            )
        self._connection.commit()

    def save_dxlink_time_and_sale_provenance(
        self,
        provenance: tuple[DxLinkTimeAndSaleProvenance, ...],
    ) -> None:
        for item in provenance:
            self._connection.execute(
                """
                INSERT INTO observation_source_provenance (
                    observation_id, source_kind, source_record_ref, source_index,
                    source_sequence, source_trade_id, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.observation_id),
                    "DXLINK_TIME_AND_SALE",
                    item.source_record_ref,
                    item.source_index,
                    item.source_sequence,
                    item.source_trade_id,
                    _timestamp_text(item.received_at),
                ),
            )
        self._connection.commit()

    def save_deferred_dxlink_time_and_sales(
        self,
        events: tuple[DeferredDxLinkTimeAndSale, ...],
    ) -> None:
        for event in events:
            record = event.source_record
            self._connection.execute(
                """
                INSERT INTO deferred_dxlink_timesale_events (
                    deferred_event_id, dataset_id, source_order, source_record_ref, reason,
                    event_symbol, event_time, event_classification, source_index, source_sequence,
                    source_trade_id, event_flags, exchange_code, price, size, bid_price, ask_price,
                    exchange_sale_conditions, trade_through_exempt, aggressor_side, spread_leg,
                    extended_trading_hours, valid_tick, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(event.deferred_event_id), str(event.dataset_id), event.source_order,
                    record.source_record_ref, event.reason, record.event_symbol,
                    _timestamp_text(_dxlink_event_time(record.event_time)), record.event_classification,
                    _int_or_none(record.source_index), _int_or_none(record.source_sequence),
                    _int_or_none(record.source_trade_id), _int_or_none(record.event_flags),
                    _string_or_none(record.exchange_code), _decimal_text(record.price), _decimal_text(record.size),
                    _decimal_text(record.bid_price), _decimal_text(record.ask_price),
                    _string_or_none(record.exchange_sale_conditions), _string_or_none(record.trade_through_exempt),
                    _string_or_none(record.aggressor_side), _bool_or_none(record.spread_leg),
                    _bool_or_none(record.extended_trading_hours), _bool_or_none(record.valid_tick),
                    _timestamp_text(record.received_at),
                ),
            )
        self._connection.commit()

    def load_dataset(self, dataset_id: UUID) -> DatasetIdentity:
        row = self._connection.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?", (str(dataset_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"Dataset not found: {dataset_id}")
        return DatasetIdentity(
            dataset_id=UUID(row["dataset_id"]),
            kind=DatasetKind(row["kind"]),
            origin=DatasetOrigin(row["origin"]),
            label=row["label"],
            source_locator=row["source_locator"],
            source_timezone=row["source_timezone"],
            normalizer_version=row["normalizer_version"],
            capture_started_at=_timestamp_from_text(row["capture_started_at"]),
            capture_ended_at=_timestamp_from_text(row["capture_ended_at"]),
            parent_dataset_id=UUID(row["parent_dataset_id"]) if row["parent_dataset_id"] else None,
            transformation_policy=row["transformation_policy"],
            transformation_version=row["transformation_version"],
            random_seed=row["random_seed"],
        )

    def load_trade_observations(self, dataset_id: UUID) -> tuple[TradeObservation, ...]:
        rows = self._connection.execute(
            """
            SELECT o.*, i.kind AS instrument_kind, i.exchange, i.root,
                   i.expiration_year, i.expiration_month
            FROM trade_observations AS o
            JOIN instruments AS i ON i.canonical_id = o.instrument_id
            WHERE o.dataset_id = ?
            ORDER BY o.dataset_sequence
            """,
            (str(dataset_id),),
        ).fetchall()
        return tuple(
            TradeObservation(
                observation_id=UUID(row["observation_id"]),
                dataset_id=UUID(row["dataset_id"]),
                dataset_sequence=row["dataset_sequence"],
                instrument=InstrumentIdentity(
                    kind=InstrumentKind(row["instrument_kind"]),
                    exchange=row["exchange"],
                    root=row["root"],
                    expiration_year=row["expiration_year"],
                    expiration_month=row["expiration_month"],
                ),
                event_timestamp=_timestamp_from_text(row["event_timestamp"]),
                price=Decimal(row["price"]),
                size=Decimal(row["size"]),
                trade_action=TradeAction(row["trade_action"]),
            )
            for row in rows
        )

    def load_quality_events(self, dataset_id: UUID) -> tuple[DatasetQualityEvent, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM dataset_quality_events
            WHERE dataset_id = ?
            ORDER BY event_id
            """,
            (str(dataset_id),),
        ).fetchall()
        events = []
        for row in rows:
            links = self._connection.execute(
                """
                SELECT supporting_event_id FROM quality_event_links
                WHERE event_id = ?
                ORDER BY link_sequence
                """,
                (row["event_id"],),
            ).fetchall()
            events.append(
                DatasetQualityEvent(
                    event_id=UUID(row["event_id"]),
                    dataset_id=UUID(row["dataset_id"]),
                    evidence_type=DatasetQualityEvidenceType(row["evidence_type"]),
                    detail=row["detail"],
                    observed_at=_timestamp_from_text(row["observed_at"]),
                    interval_start=_timestamp_from_text(row["interval_start"]),
                    interval_end=_timestamp_from_text(row["interval_end"]),
                    source_record_ref=row["source_record_ref"],
                    supporting_event_ids=tuple(UUID(link["supporting_event_id"]) for link in links),
                )
            )
        return tuple(events)

    def load_rejections(self, dataset_id: UUID) -> tuple[NormalizationRejection, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM normalization_rejections
            WHERE dataset_id = ?
            ORDER BY source_order, rejection_id
            """,
            (str(dataset_id),),
        ).fetchall()
        return tuple(
            NormalizationRejection(
                rejection_id=UUID(row["rejection_id"]),
                dataset_id=UUID(row["dataset_id"]),
                source_kind=RejectionSourceKind(row["source_kind"]),
                source_record_ref=row["source_record_ref"],
                source_order=row["source_order"],
                reason=row["reason"],
                detail=row["detail"],
            )
            for row in rows
        )

    def load_dxlink_time_and_sale_provenance(
        self,
        dataset_id: UUID,
    ) -> tuple[DxLinkTimeAndSaleProvenance, ...]:
        rows = self._connection.execute(
            """
            SELECT p.* FROM observation_source_provenance AS p
            JOIN trade_observations AS o ON o.observation_id = p.observation_id
            WHERE o.dataset_id = ? AND p.source_kind = 'DXLINK_TIME_AND_SALE'
            ORDER BY o.dataset_sequence
            """,
            (str(dataset_id),),
        ).fetchall()
        return tuple(
            DxLinkTimeAndSaleProvenance(
                observation_id=UUID(row["observation_id"]),
                source_record_ref=row["source_record_ref"],
                source_index=row["source_index"],
                source_sequence=row["source_sequence"],
                source_trade_id=row["source_trade_id"],
                received_at=_timestamp_from_text(row["received_at"]),
            )
            for row in rows
        )

    def load_deferred_dxlink_time_and_sales(
        self,
        dataset_id: UUID,
    ) -> tuple[DeferredDxLinkTimeAndSale, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM deferred_dxlink_timesale_events
            WHERE dataset_id = ?
            ORDER BY event_time, source_index, deferred_event_id
            """,
            (str(dataset_id),),
        ).fetchall()
        return tuple(
            DeferredDxLinkTimeAndSale(
                deferred_event_id=UUID(row["deferred_event_id"]),
                dataset_id=UUID(row["dataset_id"]),
                source_order=row["source_order"],
                source_record=DxLinkTimeAndSaleSourceRecord(
                    source_record_ref=row["source_record_ref"],
                    event_symbol=row["event_symbol"],
                    event_time=_timestamp_from_text(row["event_time"]),
                    event_classification=row["event_classification"],
                    source_index=row["source_index"],
                    source_sequence=row["source_sequence"],
                    source_trade_id=row["source_trade_id"],
                    event_flags=row["event_flags"],
                    exchange_code=row["exchange_code"],
                    price=_decimal_from_text(row["price"]),
                    size=_decimal_from_text(row["size"]),
                    bid_price=_decimal_from_text(row["bid_price"]),
                    ask_price=_decimal_from_text(row["ask_price"]),
                    exchange_sale_conditions=row["exchange_sale_conditions"],
                    trade_through_exempt=row["trade_through_exempt"],
                    aggressor_side=row["aggressor_side"],
                    spread_leg=_bool_from_int(row["spread_leg"]),
                    extended_trading_hours=_bool_from_int(row["extended_trading_hours"]),
                    valid_tick=_bool_from_int(row["valid_tick"]),
                    received_at=_timestamp_from_text(row["received_at"]),
                ),
                reason=row["reason"],
            )
            for row in rows
        )


def _timestamp_text(timestamp: datetime | None) -> str | None:
    if timestamp is None:
        return None
    if timestamp.tzinfo is not timezone.utc:
        raise ValueError("Persisted timestamps must use timezone.utc.")
    return timestamp.isoformat()


def _timestamp_from_text(timestamp: str | None) -> datetime | None:
    if timestamp is None:
        return None
    value = datetime.fromisoformat(timestamp)
    if value.tzinfo is not timezone.utc:
        raise ValueError("Stored timestamp must use timezone.utc.")
    return value


def _dxlink_event_time(value: object) -> datetime | None:
    try:
        milliseconds = int(value)
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(milliseconds / 1000, tz=timezone.utc) if milliseconds > 0 else None


def _int_or_none(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _string_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _decimal_text(value: object) -> str | None:
    if value is None:
        return None
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return str(decimal) if decimal.is_finite() else None


def _decimal_from_text(value: str | None) -> Decimal | None:
    return Decimal(value) if value is not None else None


def _bool_or_none(value: object) -> int | None:
    return int(value) if isinstance(value, bool) else None


def _bool_from_int(value: int | None) -> bool | None:
    return bool(value) if value is not None else None