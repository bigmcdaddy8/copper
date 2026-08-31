"""Phase 0W-2B -- bounded ordered ingestion + durable writer coverage.

Grounded in the real Attempt-2 burst (see FULL_SESSION_MULTIDAY_SOAK_REPORT.md):
peak 1,690 accepted trades/second, ~5,047/minute. These prove the persistence
architecture absorbs a materially larger burst without unbounded memory, event
loss, source_order corruption, or deadlock -- and that a genuinely slower writer
enters an explicit bounded-overload failure instead of any of those.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.durable_writer import (
    CaptureBackpressureError,
    CaptureWriterError,
    DurableWriter,
    WriterFlushPolicy,
)
from dicks_laboratory.models import (
    DatasetIdentity,
    DatasetKind,
    DatasetOrigin,
    InstrumentIdentity,
    InstrumentKind,
)
from dicks_laboratory.store import LaboratoryStore

_UTC = timezone.utc
_SYMBOL = "/ESU26:XCME"
_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)
_T0 = datetime(2026, 8, 31, 22, 0, 0, tzinfo=_UTC)


def _make_store(tmp_path) -> tuple[LaboratoryStore, UUID]:
    store = LaboratoryStore(tmp_path / "es.sqlite3", check_same_thread=False)
    dataset_id = uuid4()
    store.save_dataset(
        DatasetIdentity(
            dataset_id=dataset_id,
            kind=DatasetKind.HISTORICAL_IMPORT,
            label="0w2b-writer-test",
            source_locator="test",
            source_timezone="UTC epoch milliseconds",
            normalizer_version="test",
            capture_started_at=_T0,
            origin=DatasetOrigin.AUTHENTIC_SOURCE,
        )
    )
    store.save_dataset_trading_context(dataset_id, _T0.date(), _INSTRUMENT)
    return store, dataset_id


def _event(i: int, classification: str = "NEW", index: int | None = None) -> DxLinkSourceEvent:
    idx = i if index is None else index
    return DxLinkSourceEvent(
        "TimeAndSale",
        _SYMBOL,
        {
            "eventSymbol": _SYMBOL,
            "time": int((_T0 + timedelta(milliseconds=i)).timestamp() * 1000),
            "type": classification,
            "index": idx,
            "sequence": idx,
            "tradeId": idx,
            "eventFlags": 0,
            "exchangeCode": "Q",
            "price": 7694.00 + (i % 7) * 0.25,
            "size": 1.0,
            "bidPrice": 7693.75,
            "askPrice": 7694.25,
            "exchangeSaleConditions": "@",
            "tradeThroughExempt": "0",
            "aggressorSide": "BUY",
            "spreadLeg": False,
            "extendedTradingHours": False,
            "validTick": True,
        },
        _T0 + timedelta(milliseconds=i),
    )


def _new_writer(store, dataset_id, **policy_kwargs) -> DurableWriter:
    return DurableWriter(
        store,
        dataset_id,
        _INSTRUMENT,
        _SYMBOL,
        start_dataset_sequence=1,
        seen_new_source_indices=set(),
        policy=WriterFlushPolicy(**policy_kwargs) if policy_kwargs else WriterFlushPolicy(),
    )


def _provenance_source_orders(store, dataset_id) -> list[int]:
    rows = store._connection.execute(  # noqa: SLF001 -- test introspection
        """
        SELECT p.source_order
        FROM observation_source_provenance p
        JOIN trade_observations o ON o.observation_id = p.observation_id
        WHERE o.dataset_id = ?
        ORDER BY o.dataset_sequence
        """,
        (str(dataset_id),),
    ).fetchall()
    return [r["source_order"] for r in rows]


# --------------------------------------------------------------------------- #
# §15/§16 -- ordering derives from ingestion order, never completion order    #
# --------------------------------------------------------------------------- #
def test_source_order_is_strictly_monotonic_and_matches_ingestion_order(tmp_path):
    store, dataset_id = _make_store(tmp_path)
    writer = _new_writer(store, dataset_id, max_events=17)
    writer.start()
    writer.submit_connected(_T0)
    for i in range(1, 501):
        writer.submit_event(i, _event(i))
    writer.drain_and_stop()

    orders = _provenance_source_orders(store, dataset_id)
    assert orders == list(range(1, 501))  # contiguous, strictly increasing, ingestion order
    seqs = [
        r["dataset_sequence"]
        for r in store._connection.execute(  # noqa: SLF001
            "SELECT dataset_sequence FROM trade_observations WHERE dataset_id = ? ORDER BY dataset_sequence",
            (str(dataset_id),),
        )
    ]
    assert seqs == list(range(1, 501))  # dataset_sequence stays 1..N, distinct from source_order semantics
    store.close()


# --------------------------------------------------------------------------- #
# §25 -- synthetic burst: >= 2,000 events "within one second"                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("burst", [2_000, 4_000])
def test_absorbs_burst_larger_than_attempt2_without_loss_or_corruption(tmp_path, burst):
    store, dataset_id = _make_store(tmp_path)
    writer = _new_writer(store, dataset_id, max_events=250, max_interval_seconds=0.05, queue_maxsize=100_000)
    writer.start()
    writer.submit_connected(_T0)

    start = time.monotonic()
    for i in range(1, burst + 1):
        writer.submit_event(i, _event(i))
    submit_elapsed = time.monotonic() - start

    writer.drain_and_stop()

    orders = _provenance_source_orders(store, dataset_id)
    assert orders == list(range(1, burst + 1))  # no loss, no reorder, no duplication
    assert writer.metrics.accepted == burst
    assert writer.metrics.persisted_events == burst
    assert writer.metrics.flush_count >= 1
    assert writer.metrics.queue_depth_max <= 100_000  # bounded memory held
    assert not writer.metrics.overloaded
    # The feed thread's per-event hand-off cost is what matters for keepalive
    # responsiveness: enqueuing the whole burst must be far quicker than the
    # ~24 s the Attempt-2 synchronous path took to drain 1,690 events.
    assert submit_elapsed < 5.0
    store.close()


# --------------------------------------------------------------------------- #
# §26 -- sustained rate materially above the Attempt-2 average, many flushes  #
# --------------------------------------------------------------------------- #
def test_sustained_throughput_exercises_many_flush_cycles(tmp_path):
    store, dataset_id = _make_store(tmp_path)
    writer = _new_writer(store, dataset_id, max_events=100, max_interval_seconds=0.02)
    writer.start()
    writer.submit_connected(_T0)

    total = 3_000
    start = time.monotonic()
    for i in range(1, total + 1):
        writer.submit_event(i, _event(i))
        if i % 200 == 0:
            time.sleep(0.005)  # pace it: bursts separated by short gaps
    writer.drain_and_stop()
    elapsed = time.monotonic() - start

    assert _provenance_source_orders(store, dataset_id) == list(range(1, total + 1))
    assert writer.metrics.flush_count > 5  # multiple batch/flush cycles genuinely exercised
    assert writer.metrics.persisted_events == total
    assert elapsed < 20.0  # capacity characterization, not a benchmark contest
    store.close()


# --------------------------------------------------------------------------- #
# §20/§21 -- rejections and deferred (CORRECTION/CANCEL) still fully accounted #
# under batched/async persistence; every ordinal consumed exactly once        #
# --------------------------------------------------------------------------- #
def test_rejections_and_deferred_preserve_ordinal_accounting(tmp_path):
    store, dataset_id = _make_store(tmp_path)
    writer = _new_writer(store, dataset_id, max_events=3)
    writer.start()
    writer.submit_connected(_T0)
    # 1 NEW, 2 CORRECTION (deferred), 3 NEW, 4 invalid tick (rejected), 5 CANCEL (deferred), 6 NEW
    writer.submit_event(1, _event(1, "NEW"))
    writer.submit_event(2, _event(2, "CORRECTION"))
    writer.submit_event(3, _event(3, "NEW"))
    bad = _event(4, "NEW")
    bad.fields["validTick"] = False
    writer.submit_event(4, bad)
    writer.submit_event(5, _event(5, "CANCEL"))
    writer.submit_event(6, _event(6, "NEW"))
    writer.drain_and_stop()

    accepted_orders = _provenance_source_orders(store, dataset_id)
    assert accepted_orders == [1, 3, 6]
    deferred = store.load_deferred_dxlink_time_and_sales(dataset_id)
    assert sorted(d.source_order for d in deferred) == [2, 5]
    rejections = store.load_rejections(dataset_id)
    assert [r.source_order for r in rejections] == [4]
    # Every source_order 1..6 consumed exactly once across the three dispositions.
    all_orders = sorted(accepted_orders + [d.source_order for d in deferred] + [r.source_order for r in rejections])
    assert all_orders == [1, 2, 3, 4, 5, 6]
    assert writer.metrics.accepted == 3
    assert writer.metrics.deferred == 2
    assert writer.metrics.rejected == 1
    store.close()


def test_duplicate_source_index_across_reconnect_is_rejected_not_dropped(tmp_path):
    store, dataset_id = _make_store(tmp_path)
    writer = _new_writer(store, dataset_id, max_events=2)
    writer.start()
    writer.submit_connected(_T0)
    writer.submit_event(1, _event(1, "NEW", index=9001))
    writer.submit_disconnected(1, "source_disconnected; attempt=1; episode=1; stage=X; error=y", _T0 + timedelta(seconds=1))
    writer.submit_connected(_T0 + timedelta(seconds=2))
    writer.submit_event(2, _event(2, "NEW", index=9001))  # redelivered same dxFeed index
    writer.submit_event(3, _event(3, "NEW", index=9002))
    writer.drain_and_stop()

    assert _provenance_source_orders(store, dataset_id) == [1, 3]
    rejections = store.load_rejections(dataset_id)
    assert [(r.source_order, r.reason) for r in rejections] == [(2, "DUPLICATE_SOURCE_INDEX_ACROSS_RECONNECT")]
    assert writer.metrics.duplicates == 1
    store.close()


# --------------------------------------------------------------------------- #
# §13/§14/§27 -- a genuinely slower writer enters an explicit bounded overload #
# instead of dropping data, growing RAM without bound, or deadlocking          #
# --------------------------------------------------------------------------- #
class _GatedStore(LaboratoryStore):
    """Persistence that blocks until the test explicitly releases it, so the
    writer provably cannot keep up and the bounded queue provably saturates."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.release = __import__("threading").Event()

    def save_trade_observations(self, trades):  # type: ignore[override]
        self.release.wait(timeout=30)
        super().save_trade_observations(trades)


def test_backpressure_saturation_raises_explicitly_without_loss_or_unbounded_growth(tmp_path):
    store = _GatedStore(tmp_path / "es.sqlite3", check_same_thread=False)
    dataset_id = uuid4()
    store.save_dataset(
        DatasetIdentity(
            dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label="gated",
            source_locator="t", source_timezone="UTC epoch milliseconds", normalizer_version="t",
            capture_started_at=_T0, origin=DatasetOrigin.AUTHENTIC_SOURCE,
        )
    )
    store.save_dataset_trading_context(dataset_id, _T0.date(), _INSTRUMENT)

    writer = DurableWriter(
        store, dataset_id, _INSTRUMENT, _SYMBOL,
        start_dataset_sequence=1, seen_new_source_indices=set(),
        policy=WriterFlushPolicy(max_events=1, queue_maxsize=8, overload_grace_seconds=0.3),
    )
    writer.start()
    writer.submit_connected(_T0)

    submitted_ok = 0
    with pytest.raises(CaptureBackpressureError):
        for i in range(1, 5_000):
            writer.submit_event(i, _event(i))
            submitted_ok += 1
            assert writer._queue.qsize() <= 8  # noqa: SLF001 -- bounded, never grows past maxsize

    # Explicit failure, no unbounded growth, no deadlock. Now let persistence
    # proceed and confirm nothing that was accepted got dropped -- what landed
    # is a contiguous prefix with no holes.
    store.release.set()
    writer.drain_and_stop()
    orders = _provenance_source_orders(store, dataset_id)
    assert orders == list(range(1, len(orders) + 1))
    assert len(orders) <= submitted_ok + 8
    assert writer.metrics.overloaded is True
    store.close()


def test_buffered_events_are_not_durable_until_drain(tmp_path):
    store, dataset_id = _make_store(tmp_path)
    # Big batch window: events sit un-flushed in the writer until drain.
    writer = _new_writer(store, dataset_id, max_events=100_000, max_interval_seconds=3600)
    writer.start()
    writer.submit_connected(_T0)
    for i in range(1, 51):
        writer.submit_event(i, _event(i))
    time.sleep(0.05)
    # Nothing committed yet -- buffered != durable.
    assert store.load_trade_observations(dataset_id) == ()
    writer.drain_and_stop()
    assert len(store.load_trade_observations(dataset_id)) == 50
    store.close()


# --------------------------------------------------------------------------- #
# writer-thread failure surfaces as CaptureWriterError, never a silent hang   #
# --------------------------------------------------------------------------- #
class _BrokenStore(LaboratoryStore):
    def save_trade_observations(self, trades):  # type: ignore[override]
        raise RuntimeError("disk on fire")


def test_writer_thread_failure_surfaces_on_drain(tmp_path):
    store = _BrokenStore(tmp_path / "es.sqlite3", check_same_thread=False)
    dataset_id = uuid4()
    store.save_dataset(
        DatasetIdentity(
            dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label="broken",
            source_locator="t", source_timezone="UTC epoch milliseconds", normalizer_version="t",
            capture_started_at=_T0, origin=DatasetOrigin.AUTHENTIC_SOURCE,
        )
    )
    store.save_dataset_trading_context(dataset_id, _T0.date(), _INSTRUMENT)
    writer = _new_writer(store, dataset_id, max_events=1)
    writer.start()
    writer.submit_connected(_T0)
    # The writer thread will raise on the first flush; give it a moment, then
    # every further interaction must fail fast rather than hang.
    for i in range(1, 200):
        try:
            writer.submit_event(i, _event(i))
        except CaptureWriterError:
            break
        time.sleep(0.001)
    with pytest.raises(CaptureWriterError):
        writer.drain_and_stop()
    store.close()


def _rss_mb() -> float:
    import os

    for line in open(f"/proc/{os.getpid()}/status"):
        if line.startswith("VmRSS"):
            return int(line.split()[1]) / 1024
    return 0.0


# --------------------------------------------------------------------------- #
# §32/§33 -- memory/backlog is BOUNDED (not "throw hardware at it"): under a  #
# sustained producer that outruns the writer, the queue pins at its hard cap  #
# and RSS plateaus rather than tracking events-sent.                          #
# --------------------------------------------------------------------------- #
def test_memory_and_queue_stay_bounded_under_sustained_overload(tmp_path):
    import gc

    store, dataset_id = _make_store(tmp_path)
    cap = 8_000
    writer = _new_writer(store, dataset_id, max_events=250, max_interval_seconds=0.05, queue_maxsize=cap)
    writer.start()
    writer.submit_connected(_T0)

    gc.collect()
    base = _rss_mb()
    total = 60_000
    mid = None
    for i in range(1, total + 1):
        writer.submit_event(i, _event(i))
        if i == total // 2:
            gc.collect()
            mid = _rss_mb()
            assert writer._queue.qsize() <= cap  # noqa: SLF001
    gc.collect()
    pre_drain = _rss_mb()
    writer.drain_and_stop()

    assert writer.metrics.queue_depth_max <= cap  # hard bound never exceeded
    assert _provenance_source_orders(store, dataset_id) == list(range(1, total + 1))  # nothing lost
    # RSS plateaus: growth is ~one queue's worth of events, and does not keep
    # climbing with the number sent (mid ~= pre_drain, well under a loose ceiling).
    assert pre_drain - base < 250  # MB: generous ceiling; a leak would blow past this
    assert pre_drain - (mid or base) < 60  # MB: flat between the halfway point and the end
    store.close()


def test_writer_join_is_bounded_even_if_stop_marker_cannot_enqueue(tmp_path):
    store, dataset_id = _make_store(tmp_path)
    writer = _new_writer(store, dataset_id, max_events=10, queue_maxsize=4)
    writer.start()
    writer.submit_connected(_T0)
    for i in range(1, 40):
        writer.submit_event(i, _event(i))
    started = time.monotonic()
    writer.drain_and_stop()  # must not hang
    assert time.monotonic() - started < 10.0
    assert _provenance_source_orders(store, dataset_id) == list(range(1, 40))
    store.close()
