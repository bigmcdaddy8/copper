"""Small SQLite persistence proof for canonical Dick's Laboratory facts."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from typing import Iterator
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import UUID

from dicks_laboratory.dataset_state import DatasetClosingSummary, DatasetLifecycleState
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
    RejectedDxLinkTimeAndSaleSourceRecord,
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
    source_order INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS rejected_dxlink_timesale_source_records (
    rejection_id TEXT PRIMARY KEY REFERENCES normalization_rejections(rejection_id),
    dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
    source_order INTEGER NOT NULL,
    source_record_ref TEXT NOT NULL,
    event_symbol TEXT,
    event_time TEXT,
    event_classification TEXT,
    source_index INTEGER,
    source_sequence INTEGER,
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

CREATE TABLE IF NOT EXISTS dataset_closing_summaries (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(dataset_id),
    accepted_trade_count INTEGER NOT NULL,
    deferred_event_count INTEGER NOT NULL,
    rejected_record_count INTEGER NOT NULL,
    known_gap_count INTEGER NOT NULL,
    suspected_gap_count INTEGER NOT NULL,
    first_source_order INTEGER,
    last_source_order INTEGER,
    closed_at TEXT NOT NULL,
    collector_version TEXT,
    collector_git_commit TEXT
);
"""


class LaboratoryStore:
    """Owns a small SQLite schema and canonical object serialization for Phase 0G."""

    def __init__(self, db_path: Path, read_only: bool = False, check_same_thread: bool = True) -> None:
        # `check_same_thread=False` is used only by the 0W-2B durable-writer path,
        # where the connection is created on the capture thread, handed to exactly
        # one dedicated writer thread for the run, then reclaimed by the capture
        # thread after that writer has joined -- never touched by two threads at
        # once. It is not a licence for concurrent access.
        if read_only:
            if not Path(db_path).is_file():
                raise FileNotFoundError(f"Database not found: {db_path}")
            self._connection = sqlite3.connect(
                f"file:{db_path}?mode=ro", uri=True, check_same_thread=check_same_thread
            )
        else:
            self._connection = sqlite3.connect(db_path, check_same_thread=check_same_thread)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._in_transaction = False
        if not read_only:
            self._connection.executescript(_DDL)
            self._apply_additive_migrations()
            self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Batch many `save_*` calls into ONE SQLite transaction/commit.

        While active, the per-call `commit()` inside each `save_*` method is
        suppressed; a single `commit()` runs on clean exit, and `rollback()` on
        any exception. Not re-entrant. Introduced for 0W-2B: committing (and
        fsync-ing) per event on the feed-reader path is what let a real market
        burst starve the DXLink keepalive in Attempt 2.
        """
        if self._in_transaction:
            raise RuntimeError("LaboratoryStore.transaction() is not re-entrant.")
        self._in_transaction = True
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()
        finally:
            self._in_transaction = False

    def _maybe_commit(self) -> None:
        if not self._in_transaction:
            self._connection.commit()

    def list_dataset_ids(self) -> tuple[UUID, ...]:
        rows = self._connection.execute("SELECT dataset_id FROM datasets ORDER BY dataset_id").fetchall()
        return tuple(UUID(row["dataset_id"]) for row in rows)

    def _apply_additive_migrations(self) -> None:
        """Widen existing tables with nullable/defaulted columns only.

        Never destructive, never applied to a read-only connection (callers
        opening an old database read-only get exactly the columns that
        database was created with -- absent optional 0V fields load as None,
        never fabricated).
        """
        self._ensure_columns(
            "observation_source_provenance",
            {
                "source_order": "INTEGER NOT NULL DEFAULT 0",
                "event_symbol": "TEXT",
                "event_classification": "TEXT",
                "event_flags": "INTEGER",
                "exchange_code": "TEXT",
                "bid_price": "TEXT",
                "ask_price": "TEXT",
                "exchange_sale_conditions": "TEXT",
                "trade_through_exempt": "TEXT",
                "aggressor_side": "TEXT",
                "spread_leg": "INTEGER",
                "extended_trading_hours": "INTEGER",
                "valid_tick": "INTEGER",
            },
        )
        self._ensure_columns(
            "datasets",
            {
                "trading_date": "TEXT",
                "instrument_id": "TEXT",
                "lifecycle_state": "TEXT",
            },
        )

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {row["name"] for row in self._connection.execute(f"PRAGMA table_info({table})")}
        for name, column_type in columns.items():
            if name not in existing:
                self._connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {column_type}")

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
        self._maybe_commit()

    def update_dataset_capture_ended(self, dataset_id: UUID, capture_ended_at: datetime) -> None:
        self._connection.execute(
            "UPDATE datasets SET capture_ended_at = ? WHERE dataset_id = ?",
            (_timestamp_text(capture_ended_at), str(dataset_id)),
        )
        self._maybe_commit()

    def save_dataset_trading_context(
        self,
        dataset_id: UUID,
        trading_date: date,
        instrument: InstrumentIdentity,
    ) -> None:
        """Persist dataset-level trading_date + exact instrument identity (0V segmentation).

        Recorded even before any trade arrives -- a valid serious dataset may
        contain zero accepted trades and must still carry its own identity.
        """
        self._connection.execute(
            """
            INSERT OR IGNORE INTO instruments (
                canonical_id, kind, exchange, root, expiration_year, expiration_month
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                instrument.canonical_id, instrument.kind.value, instrument.exchange,
                instrument.root, instrument.expiration_year, instrument.expiration_month,
            ),
        )
        self._connection.execute(
            "UPDATE datasets SET trading_date = ?, instrument_id = ? WHERE dataset_id = ?",
            (trading_date.isoformat(), instrument.canonical_id, str(dataset_id)),
        )
        self._maybe_commit()

    def load_dataset_trading_context(self, dataset_id: UUID) -> tuple[date | None, InstrumentIdentity | None]:
        """Backward-compatible: an old database predating 0V lacks the
        `trading_date`/`instrument_id` columns entirely (never migrated in
        read-only mode). `SELECT d.*` naturally omits columns that don't
        exist in that file rather than erroring, unlike naming them
        explicitly -- so this must never reference them by name in SQL.
        """
        row = self._connection.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?", (str(dataset_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"Dataset not found: {dataset_id}")
        trading_date_text = _row_get(row, "trading_date")
        trading_date_value = date.fromisoformat(trading_date_text) if trading_date_text else None
        instrument_id = _row_get(row, "instrument_id")
        instrument = None
        if instrument_id is not None:
            instrument_row = self._connection.execute(
                "SELECT * FROM instruments WHERE canonical_id = ?", (instrument_id,)
            ).fetchone()
            if instrument_row is not None:
                instrument = InstrumentIdentity(
                    kind=InstrumentKind(instrument_row["kind"]),
                    exchange=instrument_row["exchange"],
                    root=instrument_row["root"],
                    expiration_year=instrument_row["expiration_year"],
                    expiration_month=instrument_row["expiration_month"],
                )
        return trading_date_value, instrument

    def set_dataset_lifecycle_state(self, dataset_id: UUID, state: DatasetLifecycleState) -> None:
        self._connection.execute(
            "UPDATE datasets SET lifecycle_state = ? WHERE dataset_id = ?",
            (state.value, str(dataset_id)),
        )
        self._maybe_commit()

    def load_dataset_lifecycle_state(self, dataset_id: UUID) -> DatasetLifecycleState | None:
        """None means untracked (legacy pre-0V dataset), never inferred as OPEN/FINALIZED/INTERRUPTED.

        Uses `SELECT *` rather than naming `lifecycle_state` explicitly: an
        old database predating 0V lacks that column entirely, and naming a
        nonexistent column in SQL raises `OperationalError` rather than
        simply omitting it the way `SELECT *` does.
        """
        row = self._connection.execute(
            "SELECT * FROM datasets WHERE dataset_id = ?", (str(dataset_id),)
        ).fetchone()
        if row is None:
            raise KeyError(f"Dataset not found: {dataset_id}")
        value = _row_get(row, "lifecycle_state")
        return DatasetLifecycleState(value) if value else None

    def max_source_order_for_dataset(self, dataset_id: UUID) -> int:
        """Highest durable `source_order` across every disposition for this dataset.

        Used to resume a crashed/restarted collector at `max + 1` -- `source_order`
        must never reset to 1 mid-dataset (0U §15 requirement).
        """
        row = self._connection.execute(
            """
            SELECT MAX(value) AS m FROM (
                SELECT MAX(p.source_order) AS value
                FROM observation_source_provenance AS p
                JOIN trade_observations AS o ON o.observation_id = p.observation_id
                WHERE o.dataset_id = ?
                UNION ALL
                SELECT MAX(source_order) FROM deferred_dxlink_timesale_events WHERE dataset_id = ?
                UNION ALL
                SELECT MAX(source_order) FROM rejected_dxlink_timesale_source_records WHERE dataset_id = ?
            )
            """,
            (str(dataset_id), str(dataset_id), str(dataset_id)),
        ).fetchone()
        return row["m"] if row is not None and row["m"] is not None else 0

    def save_dataset_closing_summary(self, summary: DatasetClosingSummary) -> None:
        self._connection.execute(
            """
            INSERT INTO dataset_closing_summaries (
                dataset_id, accepted_trade_count, deferred_event_count, rejected_record_count,
                known_gap_count, suspected_gap_count, first_source_order, last_source_order,
                closed_at, collector_version, collector_git_commit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(summary.dataset_id), summary.accepted_trade_count, summary.deferred_event_count,
                summary.rejected_record_count, summary.known_gap_count, summary.suspected_gap_count,
                summary.first_source_order, summary.last_source_order, _timestamp_text(summary.closed_at),
                summary.collector_version, summary.collector_git_commit,
            ),
        )
        self._maybe_commit()

    def load_dataset_closing_summary(self, dataset_id: UUID) -> DatasetClosingSummary | None:
        row = self._connection.execute(
            "SELECT * FROM dataset_closing_summaries WHERE dataset_id = ?", (str(dataset_id),)
        ).fetchone()
        if row is None:
            return None
        return DatasetClosingSummary(
            dataset_id=UUID(row["dataset_id"]),
            accepted_trade_count=row["accepted_trade_count"],
            deferred_event_count=row["deferred_event_count"],
            rejected_record_count=row["rejected_record_count"],
            known_gap_count=row["known_gap_count"],
            suspected_gap_count=row["suspected_gap_count"],
            first_source_order=row["first_source_order"],
            last_source_order=row["last_source_order"],
            closed_at=_timestamp_from_text(row["closed_at"]),
            collector_version=row["collector_version"],
            collector_git_commit=row["collector_git_commit"],
        )

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
        self._maybe_commit()

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
        self._maybe_commit()

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
        self._maybe_commit()

    def save_dxlink_time_and_sale_provenance(
        self,
        provenance: tuple[DxLinkTimeAndSaleProvenance, ...],
    ) -> None:
        for item in provenance:
            self._connection.execute(
                """
                INSERT INTO observation_source_provenance (
                    observation_id, source_kind, source_record_ref, source_order, source_index,
                    source_sequence, source_trade_id, received_at,
                    event_symbol, event_classification, event_flags, exchange_code,
                    bid_price, ask_price, exchange_sale_conditions, trade_through_exempt,
                    aggressor_side, spread_leg, extended_trading_hours, valid_tick
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.observation_id),
                    "DXLINK_TIME_AND_SALE",
                    item.source_record_ref,
                    item.source_order,
                    item.source_index,
                    item.source_sequence,
                    item.source_trade_id,
                    _timestamp_text(item.received_at),
                    item.event_symbol,
                    item.event_classification,
                    item.event_flags,
                    item.exchange_code,
                    _decimal_text(item.bid_price),
                    _decimal_text(item.ask_price),
                    item.exchange_sale_conditions,
                    item.trade_through_exempt,
                    item.aggressor_side,
                    _bool_or_none(item.spread_leg),
                    _bool_or_none(item.extended_trading_hours),
                    _bool_or_none(item.valid_tick),
                ),
            )
        self._maybe_commit()

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
        self._maybe_commit()

    def save_rejected_dxlink_time_and_sale_source_records(
        self,
        records: tuple[RejectedDxLinkTimeAndSaleSourceRecord, ...],
    ) -> None:
        """Persist full structured source evidence for rejected TimeAndSale records (0V).

        Mirrors `save_deferred_dxlink_time_and_sales`'s field-complete approach:
        a rejected record's source-shaped evidence must survive so a later
        reader can independently examine what was rejected and why, not only
        the reason string already durable in `normalization_rejections`.
        """
        for item in records:
            record = item.source_record
            self._connection.execute(
                """
                INSERT INTO rejected_dxlink_timesale_source_records (
                    rejection_id, dataset_id, source_order, source_record_ref,
                    event_symbol, event_time, event_classification, source_index, source_sequence,
                    source_trade_id, event_flags, exchange_code, price, size, bid_price, ask_price,
                    exchange_sale_conditions, trade_through_exempt, aggressor_side, spread_leg,
                    extended_trading_hours, valid_tick, received_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(item.rejection_id), str(item.dataset_id), item.source_order,
                    record.source_record_ref, record.event_symbol,
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
        self._maybe_commit()

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
                source_order=row["source_order"],
                source_index=row["source_index"],
                source_sequence=row["source_sequence"],
                source_trade_id=row["source_trade_id"],
                received_at=_timestamp_from_text(row["received_at"]),
                event_symbol=_row_get(row, "event_symbol"),
                event_classification=_row_get(row, "event_classification"),
                event_flags=_row_get(row, "event_flags"),
                exchange_code=_row_get(row, "exchange_code"),
                bid_price=_decimal_from_text(_row_get(row, "bid_price")),
                ask_price=_decimal_from_text(_row_get(row, "ask_price")),
                exchange_sale_conditions=_row_get(row, "exchange_sale_conditions"),
                trade_through_exempt=_row_get(row, "trade_through_exempt"),
                aggressor_side=_row_get(row, "aggressor_side"),
                spread_leg=_bool_from_int(_row_get(row, "spread_leg")),
                extended_trading_hours=_bool_from_int(_row_get(row, "extended_trading_hours")),
                valid_tick=_bool_from_int(_row_get(row, "valid_tick")),
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

    def load_rejected_dxlink_time_and_sale_source_records(
        self,
        dataset_id: UUID,
    ) -> tuple[RejectedDxLinkTimeAndSaleSourceRecord, ...]:
        rows = self._connection.execute(
            """
            SELECT * FROM rejected_dxlink_timesale_source_records
            WHERE dataset_id = ?
            ORDER BY source_order, rejection_id
            """,
            (str(dataset_id),),
        ).fetchall()
        return tuple(
            RejectedDxLinkTimeAndSaleSourceRecord(
                rejection_id=UUID(row["rejection_id"]),
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
            )
            for row in rows
        )


def _row_get(row: sqlite3.Row, key: str) -> object:
    """Read an optional column that may not exist in an older (pre-0V) database.

    A read-only connection never runs migrations, so an old file's tables
    genuinely lack these columns; `sqlite3.Row` raises IndexError/KeyError for
    an absent key rather than returning None, so this must check membership
    first. Absent means "not retained at capture time" -- never fabricated.
    """
    return row[key] if key in row.keys() else None


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