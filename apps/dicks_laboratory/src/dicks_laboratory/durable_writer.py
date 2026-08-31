"""Phase 0W-2B -- bounded ordered ingestion + a single durable SQLite writer.

Attempt 2 (see docs/dicks_laboratory/FULL_SESSION_MULTIDAY_SOAK_REPORT.md)
proved that doing synchronous per-event SQLite persistence *on the DXLink
feed-reader thread* lets a real market burst (1,690 accepted trades in one
second) fall ~30 s behind and starve the websocket keepalive, which the
provider then tears down.

This module moves persistence off that thread:

    DXLink reader / parser        (feed thread: assigns source_order, enqueues)
            |
    bounded ordered handoff       (queue.Queue, finite maxsize)
            |
    single persistence writer     (one dedicated thread: normalize + batch)
            |
    SQLite                        (one transaction per batch, not per event)

Design choices and why this is the *smallest* safe change:

  * `DxLinkSourceCollector.collect()` already invokes an `on_event` callback per
    event on its receive loop -- we only change what that callback does (an
    O(1) bounded `put`), not the collector transport itself.
  * `source_order` is assigned by the feed thread at the canonical ingestion
    point and travels with each item, so ordering derives from ingestion order,
    never from writer completion order. A single writer thread draining a FIFO
    queue preserves that order without any sort/merge.
  * The queue is bounded. If the writer cannot keep up for longer than a grace
    window, `submit_event` raises `CaptureBackpressureError` -- an explicit,
    truthful overload, never a silent drop and never unbounded RAM.
  * Lifecycle markers (connected / disconnected) travel through the same queue,
    so `SOURCE_RECONNECTED` / `KNOWN_GAP` / `SOURCE_DISCONNECTED` are persisted
    in the correct relationship to the trades around them.

Buffered != durable: an event sitting in the queue or an un-flushed batch is
NOT durable. Only `drain_and_stop()` (clean stop / session close / recoverable
disconnect handling) guarantees everything accepted so far is committed.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid5

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.dxlink_timesales import (
    RejectedDxLinkTimeAndSaleSourceRecord,
    normalize_dxlink_time_and_sales,
    source_records_from_events,
)
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.store import LaboratoryStore


class CaptureBackpressureError(RuntimeError):
    """The durable writer could not keep up with ingestion within the grace
    window and the bounded queue stayed full. Capture completeness can no
    longer be assured -- the run must terminate INTERRUPTED with truthful
    evidence rather than drop events or grow memory without bound."""


class CaptureWriterError(RuntimeError):
    """The durable writer thread failed while persisting. The original cause is
    chained; the run must terminate INTERRUPTED."""


@dataclass(frozen=True)
class WriterFlushPolicy:
    """Explicit bounded batch policy (0W-2B §17).

    `max_events` / `max_interval_seconds`: flush after N events OR T seconds,
    whichever comes first -- bounds both SQLite transaction overhead and the
    window of un-durable in-memory events.

    `queue_maxsize`: hard bound on in-memory ingestion backlog (0W-2B §13).
    `overload_grace_seconds`: how long `submit_event` will wait for the writer
    to free a slot before declaring `CaptureBackpressureError`.
    """

    max_events: int = 250
    max_interval_seconds: float = 0.1
    queue_maxsize: int = 50_000
    overload_grace_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.max_events < 1:
            raise ValueError("max_events must be positive.")
        if self.max_interval_seconds <= 0:
            raise ValueError("max_interval_seconds must be positive.")
        if self.queue_maxsize < 1:
            raise ValueError("queue_maxsize must be positive.")
        if self.overload_grace_seconds < 0:
            raise ValueError("overload_grace_seconds must be non-negative.")


@dataclass
class WriterMetrics:
    """Operational (not canonical) throughput evidence for post-run diagnosis
    (0W-2B §22). Answers: did persistence keep up?"""

    submitted_events: int = 0
    persisted_events: int = 0
    accepted: int = 0
    rejected: int = 0
    deferred: int = 0
    duplicates: int = 0
    flush_count: int = 0
    batch_size_max: int = 0
    queue_depth_max: int = 0
    max_persist_lag_seconds: float = 0.0
    overloaded: bool = False

    def as_detail_suffix(self) -> str:
        return (
            f"writer_flushes={self.flush_count}; "
            f"writer_batch_max={self.batch_size_max}; "
            f"writer_queue_depth_max={self.queue_depth_max}; "
            f"writer_max_persist_lag_s={self.max_persist_lag_seconds:.3f}; "
            f"writer_persisted_events={self.persisted_events}; "
            f"writer_overloaded={str(self.overloaded).lower()}"
        )


@dataclass
class _Batch:
    observations: list = field(default_factory=list)
    provenance: list = field(default_factory=list)
    rejections: list = field(default_factory=list)
    rejected_source_records: list = field(default_factory=list)
    deferred: list = field(default_factory=list)
    event_count: int = 0
    earliest_enqueued_monotonic: float | None = None

    def is_empty(self) -> bool:
        return self.event_count == 0

    def clear(self) -> None:
        self.observations.clear()
        self.provenance.clear()
        self.rejections.clear()
        self.rejected_source_records.clear()
        self.deferred.clear()
        self.event_count = 0
        self.earliest_enqueued_monotonic = None


# Queue item kinds.
_EVENT = "event"
_CONNECTED = "connected"
_DISCONNECTED = "disconnected"
_STOP = "stop"


class DurableWriter:
    """Owns the persistence side of one trading-date capture segment.

    The `LaboratoryStore` passed in is used ONLY by this writer's thread for the
    lifetime of the run (between `start()` and `drain_and_stop()` returning).
    The caller must not touch it during that window.
    """

    def __init__(
        self,
        store: LaboratoryStore,
        dataset_id: UUID,
        instrument: InstrumentIdentity,
        streamer_symbol: str,
        *,
        start_dataset_sequence: int,
        seen_new_source_indices: set[int],
        policy: WriterFlushPolicy = WriterFlushPolicy(),
        monotonic: "callable" = time.monotonic,
    ) -> None:
        self._store = store
        self._dataset_id = dataset_id
        self._instrument = instrument
        self._streamer_symbol = streamer_symbol
        self._dataset_sequence = start_dataset_sequence
        self._seen_new_source_indices = seen_new_source_indices
        self._policy = policy
        self._monotonic = monotonic

        self._queue: queue.Queue = queue.Queue(maxsize=policy.queue_maxsize)
        self._thread = threading.Thread(target=self._run, name="dicks-durable-writer", daemon=True)
        self._failure: BaseException | None = None
        self._started = False
        self._stopped = False
        self._stop_event = threading.Event()

        self._classifications: Counter[str] = Counter()
        self._metrics = WriterMetrics()

        # Lifecycle state, owned by the writer thread once running.
        self._ever_connected = False
        self._pending_disconnect_at: datetime | None = None
        self._last_disconnect_at: datetime | None = None

    # ---- feed-thread facing API -------------------------------------------------

    def start(self) -> None:
        if self._started:
            raise RuntimeError("DurableWriter already started.")
        self._started = True
        self._thread.start()

    def submit_event(self, source_order: int, event: DxLinkSourceEvent) -> None:
        """Hand one raw source event (already assigned its canonical
        `source_order`) to the writer. O(1) on the feed thread.

        Blocks at most `overload_grace_seconds` if the bounded queue is full,
        then raises `CaptureBackpressureError`. Raises `CaptureWriterError`
        immediately if the writer thread has already failed.
        """
        self._raise_if_writer_failed()
        self._metrics.submitted_events += 1
        item = (_EVENT, self._monotonic(), source_order, event)
        try:
            self._queue.put(item, timeout=self._policy.overload_grace_seconds)
        except queue.Full:
            self._metrics.overloaded = True
            raise CaptureBackpressureError(
                "Durable writer fell behind ingestion: the bounded queue "
                f"(maxsize={self._policy.queue_maxsize}) stayed full for "
                f"{self._policy.overload_grace_seconds:.0f}s at source_order="
                f"{source_order}. Capture completeness can no longer be assured."
            ) from None
        depth = self._queue.qsize()
        if depth > self._metrics.queue_depth_max:
            self._metrics.queue_depth_max = depth

    def submit_connected(self, moment: datetime) -> None:
        """Record a (re)connection. First one becomes SOURCE_CONNECTED; a later
        one after a disconnect becomes SOURCE_RECONNECTED + closes the KNOWN_GAP.
        Ordered through the queue so it lands after the trades that preceded it.
        """
        self._put_marker((_CONNECTED, self._monotonic(), moment))

    def submit_disconnected(self, attempt: int, detail: str, moment: datetime) -> None:
        """Record a SOURCE_DISCONNECTED with an already-sanitized detail string,
        ordered after the trades received before the drop."""
        self._put_marker((_DISCONNECTED, self._monotonic(), attempt, detail, moment))

    def _put_marker(self, item: tuple) -> None:
        self._raise_if_writer_failed()
        try:
            self._queue.put(item, timeout=self._policy.overload_grace_seconds)
        except queue.Full:
            self._metrics.overloaded = True
            raise CaptureBackpressureError(
                "Durable writer fell behind ingestion: a lifecycle marker could "
                f"not be enqueued within {self._policy.overload_grace_seconds:.0f}s "
                f"(queue maxsize={self._policy.queue_maxsize})."
            ) from None

    def drain_and_stop(self) -> WriterMetrics:
        """Flush every accepted item, stop the writer thread, and return metrics.

        Raises `CaptureWriterError` if the writer thread failed at any point
        (the partial batch in flight at failure is rolled back by
        `LaboratoryStore.transaction()`; everything committed before it stays).
        """
        if not self._started:
            return self._metrics
        if not self._stopped:
            self._stopped = True
            self._stop_event.set()
            try:
                self._queue.put((_STOP, self._monotonic()), timeout=1.0)
            except queue.Full:
                pass  # writer checks _stop_event on its next idle tick regardless
            self._thread.join()
        if self._failure is not None:
            raise CaptureWriterError(
                "The durable writer thread failed while persisting capture data."
            ) from self._failure
        return self._metrics

    # ---- read-only accessors --------------------------------------------------

    @property
    def metrics(self) -> WriterMetrics:
        return self._metrics

    @property
    def classifications(self) -> Counter[str]:
        return self._classifications

    @property
    def accepted_count(self) -> int:
        return self._metrics.accepted

    @property
    def pending_disconnect_at(self) -> datetime | None:
        """A disconnect that had not reconnected when the writer stopped -- the
        caller uses this to cap a terminal KNOWN_GAP at the session boundary."""
        return self._pending_disconnect_at

    @property
    def ever_connected(self) -> bool:
        return self._ever_connected

    # ---- writer thread ------------------------------------------------------------

    def _run(self) -> None:
        batch = _Batch()
        last_flush = self._monotonic()
        try:
            while True:
                timeout = max(0.0, last_flush + self._policy.max_interval_seconds - self._monotonic())
                try:
                    item = self._queue.get(timeout=timeout)
                except queue.Empty:
                    if not batch.is_empty():
                        self._flush(batch)
                    last_flush = self._monotonic()
                    if self._stop_event.is_set():
                        return
                    continue

                kind = item[0]
                if kind == _EVENT:
                    _, enqueued_monotonic, source_order, event = item
                    if batch.earliest_enqueued_monotonic is None:
                        batch.earliest_enqueued_monotonic = enqueued_monotonic
                    self._stage_event(batch, source_order, event)
                    if batch.event_count >= self._policy.max_events:
                        self._flush(batch)
                        last_flush = self._monotonic()
                elif kind == _CONNECTED:
                    # Order the lifecycle marker after everything received before it.
                    if not batch.is_empty():
                        self._flush(batch)
                        last_flush = self._monotonic()
                    self._write_connected(item[2])
                elif kind == _DISCONNECTED:
                    if not batch.is_empty():
                        self._flush(batch)
                        last_flush = self._monotonic()
                    self._write_disconnected(item[2], item[3], item[4])
                elif kind == _STOP:
                    if not batch.is_empty():
                        self._flush(batch)
                    return
        except BaseException as exc:  # noqa: BLE001 -- surfaced verbatim via drain_and_stop()
            self._failure = exc
            # Drain remaining queue items without persisting so feed-thread
            # `put()` calls cannot block forever on a dead writer.
            self._drain_queue_nonblocking()

    def _drain_queue_nonblocking(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def _stage_event(self, batch: _Batch, source_order: int, event: DxLinkSourceEvent) -> None:
        records = source_records_from_events((event,), start_source_order=source_order)
        if not records:
            # Not a TimeAndSale event (the subscription only asks for those, so
            # this is defensive): the ordinal is still consumed, nothing persisted.
            batch.event_count += 1
            return
        record = records[0]
        self._classifications[record.event_classification or "UNKNOWN"] += 1

        if record.event_classification == "NEW":
            try:
                candidate_index: int | None = int(record.source_index)
            except (TypeError, ValueError):
                candidate_index = None
            if candidate_index is not None and candidate_index in self._seen_new_source_indices:
                rejection_id = uuid5(self._dataset_id, f"duplicate-rejection:{record.source_record_ref}")
                batch.rejections.append(
                    NormalizationRejection(
                        rejection_id=rejection_id,
                        dataset_id=self._dataset_id,
                        source_kind=RejectionSourceKind.DXLINK_TIME_AND_SALE,
                        source_record_ref=record.source_record_ref,
                        source_order=source_order,
                        reason="DUPLICATE_SOURCE_INDEX_ACROSS_RECONNECT",
                    )
                )
                batch.rejected_source_records.append(
                    RejectedDxLinkTimeAndSaleSourceRecord(
                        rejection_id=rejection_id,
                        dataset_id=self._dataset_id,
                        source_order=source_order,
                        source_record=record,
                    )
                )
                batch.event_count += 1
                self._metrics.duplicates += 1
                return

        result = normalize_dxlink_time_and_sales(
            (record,),
            _dataset_identity_stub(self._dataset_id),
            self._instrument,
            self._streamer_symbol,
            start_source_order=source_order,
            start_dataset_sequence=self._dataset_sequence,
        )
        if result.observations:
            self._dataset_sequence += len(result.observations)
            batch.observations.extend(result.observations)
            batch.provenance.extend(result.provenance)
            for provenance in result.provenance:
                self._seen_new_source_indices.add(provenance.source_index)
            self._metrics.accepted += len(result.observations)
        if result.deferred:
            batch.deferred.extend(result.deferred)
            self._metrics.deferred += len(result.deferred)
        if result.rejected:
            batch.rejections.extend(result.rejected)
            batch.rejected_source_records.extend(result.rejected_source_records)
            self._metrics.rejected += len(result.rejected)
        batch.event_count += 1

    def _flush(self, batch: _Batch) -> None:
        if batch.is_empty():
            return
        with self._store.transaction():
            if batch.observations:
                self._store.save_trade_observations(tuple(batch.observations))
                self._store.save_dxlink_time_and_sale_provenance(tuple(batch.provenance))
            if batch.deferred:
                self._store.save_deferred_dxlink_time_and_sales(tuple(batch.deferred))
            if batch.rejections:
                self._store.save_rejections(tuple(batch.rejections))
                self._store.save_rejected_dxlink_time_and_sale_source_records(
                    tuple(batch.rejected_source_records)
                )
        self._metrics.flush_count += 1
        self._metrics.persisted_events += batch.event_count
        if batch.event_count > self._metrics.batch_size_max:
            self._metrics.batch_size_max = batch.event_count
        if batch.earliest_enqueued_monotonic is not None:
            lag = self._monotonic() - batch.earliest_enqueued_monotonic
            if lag > self._metrics.max_persist_lag_seconds:
                self._metrics.max_persist_lag_seconds = lag
        batch.clear()

    def _write_connected(self, moment: datetime) -> None:
        if not self._ever_connected:
            self._ever_connected = True
            self._store.save_quality_events(
                (
                    DatasetQualityEvent(
                        event_id=uuid5(self._dataset_id, f"lifecycle:SOURCE_CONNECTED:{moment.isoformat()}"),
                        dataset_id=self._dataset_id,
                        evidence_type=DatasetQualityEvidenceType.SOURCE_CONNECTED,
                        detail="source_connected",
                        observed_at=moment,
                    ),
                )
            )
            return
        if self._pending_disconnect_at is not None:
            self._store.save_quality_events(
                (
                    DatasetQualityEvent(
                        event_id=uuid5(self._dataset_id, f"lifecycle:SOURCE_RECONNECTED:{moment.isoformat()}"),
                        dataset_id=self._dataset_id,
                        evidence_type=DatasetQualityEvidenceType.SOURCE_RECONNECTED,
                        detail="source_reconnected",
                        observed_at=moment,
                    ),
                )
            )
            _save_known_gap(self._store, self._dataset_id, self._pending_disconnect_at, moment)
            self._pending_disconnect_at = None

    def _write_disconnected(self, attempt: int, detail: str, moment: datetime) -> None:
        self._store.save_quality_events(
            (
                DatasetQualityEvent(
                    event_id=uuid5(self._dataset_id, f"lifecycle:SOURCE_DISCONNECTED:{moment.isoformat()}"),
                    dataset_id=self._dataset_id,
                    evidence_type=DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
                    detail=detail,
                    observed_at=moment,
                ),
            )
        )
        self._pending_disconnect_at = moment
        self._last_disconnect_at = moment

    def _raise_if_writer_failed(self) -> None:
        if self._failure is not None:
            raise CaptureWriterError(
                "The durable writer thread has failed; no further events can be accepted."
            ) from self._failure


def _dataset_identity_stub(dataset_id: UUID) -> DatasetIdentity:
    """`normalize_dxlink_time_and_sales` only reads `.dataset_id` from this."""
    return DatasetIdentity(dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label="stub")


def _save_known_gap(
    store: LaboratoryStore, dataset_id: UUID, disconnected_at: datetime, moment: datetime
) -> None:
    store.save_quality_events(
        (
            DatasetQualityEvent(
                event_id=uuid5(
                    dataset_id, f"lifecycle:KNOWN_GAP:{disconnected_at.isoformat()}:{moment.isoformat()}"
                ),
                dataset_id=dataset_id,
                evidence_type=DatasetQualityEvidenceType.KNOWN_GAP,
                detail="disconnect_to_reconnect_interval; no automatic recovery assumed",
                interval_start=disconnected_at,
                interval_end=moment,
            ),
        )
    )
