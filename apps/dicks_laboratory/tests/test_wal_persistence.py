"""0W-5B WAL-decoupled persistence: semantics, crash/recovery matrix, finalization.

Crashes are real process deaths (`os._exit` in a child interpreter running the
production DurableWriter/LaboratoryStore), not mocks: no close, no checkpoint,
no Python cleanup. Host power loss cannot be simulated here; it rests on
synchronous=FULL fsync-at-COMMIT semantics (asserted below) -- see
docs/dicks_laboratory/WAL_PERSISTENCE_0W5B.md.
"""
from __future__ import annotations

import json
import time
import sqlite3
import subprocess
import sys
import textwrap
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory import long_running_capture as lrc
from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.durable_writer import DurableWriter, WriterFlushPolicy
from dicks_laboratory.long_running_capture import (
    InstrumentCaptureSpec,
    _open_or_resume_dataset,
    compute_sha256,
    find_stale_open_datasets,
    interrupt_stale_dataset,
    run_long_horizon_capture,
    verify_checksum,
)
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore, WalCollapseError

_UTC = timezone.utc
_SYMBOL = "/ESZ26:XCME"
_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12)
_SPEC = InstrumentCaptureSpec(instrument=_INSTRUMENT, streamer_symbol=_SYMBOL)
_SESSION_OPEN = datetime(2026, 9, 29, 22, 0, tzinfo=_UTC)  # trading date 2026-09-30
_TRADING_DATE = date(2026, 9, 30)


def _event(ts: datetime, index: int) -> DxLinkSourceEvent:
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": "NEW",
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "exchangeCode": "Q", "price": 7700.0 + (index % 8) * 0.25, "size": 1.0,
        "bidPrice": 7699.75, "askPrice": 7700.25, "exchangeSaleConditions": "@",
        "tradeThroughExempt": "0", "aggressorSide": "BUY", "spreadLeg": False,
        "extendedTradingHours": False, "validTick": True,
    }
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


def _sidecars(db: Path) -> list[str]:
    return sorted(p.name for p in db.parent.iterdir() if p.name.startswith(db.name + "-"))


def _source_orders(db: Path, dataset_id: UUID) -> list[int]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT p.source_order FROM observation_source_provenance p "
            "JOIN trade_observations o USING(observation_id) WHERE o.dataset_id = ? ORDER BY o.dataset_sequence",
            (str(dataset_id),),
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


# Child process: opens a dataset exactly as production does, runs the real
# DurableWriter in WAL mode, then dies at a chosen point without any cleanup.
_CHILD = textwrap.dedent(
    """
    import json, os, sys, threading, time
    from datetime import date, datetime, timedelta, timezone
    from pathlib import Path
    from K9.tastytrade.dxlink import DxLinkSourceEvent
    from dicks_laboratory.durable_writer import DurableWriter, WriterFlushPolicy
    from dicks_laboratory.long_running_capture import InstrumentCaptureSpec, _open_or_resume_dataset
    from dicks_laboratory.models import InstrumentIdentity, InstrumentKind
    from dicks_laboratory.store import LaboratoryStore

    cfg = json.loads(sys.argv[1])
    sym = "/ESZ26:XCME"
    inst = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12)
    t0 = datetime(2026, 9, 29, 22, 0, tzinfo=timezone.utc)

    def ev(i):
        ts = t0 + timedelta(milliseconds=i)
        return DxLinkSourceEvent("TimeAndSale", sym, {
            "eventSymbol": sym, "time": int(ts.timestamp() * 1000), "type": "NEW", "index": i,
            "sequence": i, "tradeId": i, "eventFlags": 0, "exchangeCode": "Q", "price": 7700.0 + (i % 8) * 0.25,
            "size": 1.0, "bidPrice": 7699.75, "askPrice": 7700.25, "exchangeSaleConditions": "@",
            "tradeThroughExempt": "0", "aggressorSide": "BUY", "spreadLeg": False,
            "extendedTradingHours": False, "validTick": True}, ts)

    class Store(LaboratoryStore):
        gate_after = cfg.get("block_commit_after")  # block the trade commit once N rows are durable
        def save_trade_observations(self, trades):
            if self.gate_after is not None and self.count_rows() >= self.gate_after:
                Path(cfg["dir"], "in_flight").write_text(str(len(trades)))
                time.sleep(3600)
            super().save_trade_observations(trades)
        def count_rows(self):
            return self._connection.execute("SELECT COUNT(*) FROM trade_observations").fetchone()[0]
        def open_wal_checkpointer(self):
            inner = super().open_wal_checkpointer()
            class Wrapped:
                def checkpoint_passive(self_inner):
                    Path(cfg["dir"], "ckpt_started").write_text("1")
                    if cfg.get("die_in_checkpoint") is not None:
                        threading.Timer(cfg["die_in_checkpoint"], lambda: os._exit(9)).start()
                    return inner.checkpoint_passive()
                def close(self_inner):
                    inner.close()
            return Wrapped()

    spec = InstrumentCaptureSpec(instrument=inst, streamer_symbol=sym)
    path, dataset_id, store, _ = _open_or_resume_dataset(Path(cfg["dir"]), spec, date(2026, 9, 30), t0)
    store.close()
    store = Store(path, check_same_thread=False)
    policy = WriterFlushPolicy(journal_mode=cfg.get("journal_mode", "wal"), max_events=cfg.get("max_events", 20000),
                               checkpoint_min_wal_bytes=cfg.get("ckpt_min", 64 * 1024 * 1024),
                               checkpoint_force_wal_bytes=max(cfg.get("ckpt_min", 64 * 1024 * 1024), 1 << 30),
                               checkpoint_quiet_seconds=0.0, checkpoint_poll_seconds=0.02)
    w = DurableWriter(store, dataset_id, inst, sym, start_dataset_sequence=1, seen_new_source_indices=set(), policy=policy)
    w.start()
    w.submit_connected(t0)
    Path(cfg["dir"], "meta.json").write_text(json.dumps({"db": str(path), "dataset_id": str(dataset_id)}))
    n = cfg["events"]
    for i in range(1, n + 1):
        w.submit_event(i, ev(i))
        if cfg.get("pause_every") and i % cfg["pause_every"] == 0:
            time.sleep(0.25)   # let the writer go idle (idle-timer flush / checkpoint opportunity)
    deadline = time.time() + 60
    while w.metrics.persisted_events < cfg.get("wait_persisted", n) and time.time() < deadline:
        time.sleep(0.01)
    if cfg.get("wait_checkpoint"):
        while w.metrics.checkpoint_count < 1 and time.time() < deadline:
            time.sleep(0.01)
    Path(cfg["dir"], "persisted").write_text(str(w.metrics.persisted_events))
    os._exit(9)   # process death: no drain, no close, no checkpoint
    """
)


def _run_child(tmp_path: Path, **cfg) -> dict:
    cfg["dir"] = str(tmp_path)
    proc = subprocess.run([sys.executable, "-c", _CHILD, json.dumps(cfg)], capture_output=True, text=True, timeout=180)
    assert proc.returncode == 9, proc.stderr[-2000:]
    meta = json.loads((tmp_path / "meta.json").read_text())
    return {"db": Path(meta["db"]), "dataset_id": UUID(meta["dataset_id"])}


# --------------------------------------------------------------------------- #
# WAL semantics the design relies on                                           #
# --------------------------------------------------------------------------- #
def test_capture_mode_is_wal_full_no_autocheckpoint(tmp_path):
    store = LaboratoryStore(tmp_path / "x.sqlite3", check_same_thread=False)
    store.enter_wal_capture_mode()
    conn = store._connection  # noqa: SLF001
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL: WAL fsync'd at every COMMIT
    assert conn.execute("PRAGMA wal_autocheckpoint").fetchone()[0] == 0
    assert conn.execute("PRAGMA journal_size_limit").fetchone()[0] == 0
    store.collapse_to_single_file()
    assert store.journal_mode() == "delete" and store.sidecar_paths() == ()
    store.close()


def test_writer_runs_in_wal_and_open_dataset_is_readable_read_only(tmp_path):
    db = tmp_path / "x.sqlite3"
    path, dataset_id, store, _ = _open_or_resume_dataset(tmp_path, _SPEC, _TRADING_DATE, _SESSION_OPEN)
    store.close()
    store = LaboratoryStore(path, check_same_thread=False)
    writer = DurableWriter(store, dataset_id, _INSTRUMENT, _SYMBOL, start_dataset_sequence=1, seen_new_source_indices=set())
    writer.start()
    for i in range(1, 501):
        writer.submit_event(i, _event(_SESSION_OPEN + timedelta(milliseconds=i), i))
    metrics = writer.drain_and_stop()
    assert store.journal_mode() == "wal" and "-wal" in "".join(_sidecars(path))
    # G: read-only tooling (DatasetAudit's store path) sees every committed row of an OPEN WAL dataset
    reader = LaboratoryStore(path, read_only=True)
    assert reader.count_trade_observations(dataset_id) == 500
    assert reader.load_dataset_lifecycle_state(dataset_id) is DatasetLifecycleState.OPEN
    reader.close()
    assert metrics.submitted_events == metrics.persisted_events == 500
    store.close()
    del db


# --------------------------------------------------------------------------- #
# A. crash after committed WAL transactions, before any checkpoint            #
# --------------------------------------------------------------------------- #
def test_A_crash_after_commit_before_checkpoint_recovers_every_committed_event(tmp_path):
    out = _run_child(tmp_path, events=3000)
    db, dataset_id = out["db"], out["dataset_id"]
    assert int((tmp_path / "persisted").read_text()) == 3000
    assert any(name.endswith("-wal") for name in _sidecars(db))  # committed data lives only in the WAL
    assert _source_orders(db, dataset_id) == list(range(1, 3001))  # recovered (read-only open)
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


# --------------------------------------------------------------------------- #
# B. crash during a checkpoint                                                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("delay", [0.0, 0.002, 0.01, 0.05])
def test_B_crash_during_checkpoint_loses_nothing_and_stays_consistent(tmp_path, delay):
    out = _run_child(
        tmp_path, events=40_000, max_events=2000, ckpt_min=256 * 1024, pause_every=10_000,
        die_in_checkpoint=delay, wait_checkpoint=True,
    )
    db, dataset_id = out["db"], out["dataset_id"]
    assert (tmp_path / "ckpt_started").exists()  # the kill really happened during/after a checkpoint
    committed = int((tmp_path / "persisted").read_text()) if (tmp_path / "persisted").exists() else None
    orders = _source_orders(db, dataset_id)
    assert orders == list(range(1, len(orders) + 1))  # contiguous: no hole, no duplicate
    if committed is not None:
        assert len(orders) >= committed
    assert len(orders) >= 10_000  # at least the batches committed before the first checkpoint
    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    conn.close()


# --------------------------------------------------------------------------- #
# C. killed with an uncommitted batch in flight                               #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_C_uncommitted_batch_is_lost_but_never_claimed_and_committed_rows_recover(tmp_path, journal_mode):
    # 1,000 events commit; the next batch (whatever had queued) is blocked mid-commit, then the process dies.
    out = _run_child(
        tmp_path, events=6000, journal_mode=journal_mode, block_commit_after=1000,
        pause_every=1000, wait_persisted=1000,
    )
    db, dataset_id = out["db"], out["dataset_id"]
    in_flight = int((tmp_path / "in_flight").read_text())
    orders = _source_orders(db, dataset_id)
    assert orders == list(range(1, 1001))  # exactly the committed prefix; nothing from the in-flight batch
    assert 1 <= in_flight <= WriterFlushPolicy().max_events
    store = LaboratoryStore(db, read_only=True)
    assert store.load_dataset_lifecycle_state(dataset_id) is DatasetLifecycleState.OPEN  # no completion claim
    assert store.load_dataset_closing_summary(dataset_id) is None
    store.close()


# --------------------------------------------------------------------------- #
# D/F. normal close: drain, collapse, single file, accounting, checksum        #
# --------------------------------------------------------------------------- #
class _OneShotCollector:
    def __init__(self, events, before_return=None):
        self.events = events
        self.before_return = before_return

    def collect(self, streamer_symbol, event_types, duration_seconds, max_events, on_event=None, on_connected=None, retain_events=True):
        if on_connected:
            on_connected()
        for event in self.events:
            on_event(event)
        if self.before_return:
            self.before_return()
        self.clock.sleep(duration_seconds)
        return ()


class _Clock:
    def __init__(self, start):
        self.t = start

    def now(self):
        self.t += timedelta(milliseconds=5)
        return self.t

    def sleep(self, seconds):
        self.t += timedelta(seconds=seconds)


def _run_session(tmp_path, n=2000, before_return=None):
    clock = _Clock(_SESSION_OPEN + timedelta(seconds=1))
    collector = _OneShotCollector(
        tuple(_event(_SESSION_OPEN + timedelta(seconds=1, milliseconds=i), i) for i in range(1, n + 1)), before_return
    )
    collector.clock = clock
    return run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=120, now=clock.now, sleeper=clock.sleep)


def test_D_F_normal_close_is_single_file_exact_and_checksum_stable(tmp_path):
    result = _run_session(tmp_path, n=2500)
    db = result.database_path
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    assert _sidecars(db) == []  # no -wal, -shm or -journal
    assert result.writer_submitted_events == result.writer_persisted_events == 2500
    assert result.writer_accounting_difference == 0
    store = LaboratoryStore(db, read_only=True)
    summary = store.load_dataset_closing_summary(result.dataset_id)
    assert (summary.submitted_events, summary.persisted_events, summary.accounting_difference) == (2500, 2500, 0)
    assert store.journal_mode() == "delete"
    assert store._connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"  # noqa: SLF001
    stopped = [e for e in store.load_quality_events(result.dataset_id) if e.evidence_type.value == "CAPTURE_STOPPED"]
    assert len(stopped) == 1 and "writer_accounting_difference=0" in stopped[0].detail
    store.close()
    assert _source_orders(db, result.dataset_id) == list(range(1, 2501))
    manifest = json.loads(result.manifest_path.read_text())
    assert manifest["state"] == "FINALIZED" and manifest["accounting_difference"] == 0
    assert manifest["submitted_events"] == manifest["persisted_events"] == 2500
    assert verify_checksum(db, result.checksum_sha256)
    reopened = LaboratoryStore(db, read_only=True)  # a later read-only audit must not change the bytes
    reopened.count_trade_observations(result.dataset_id)
    reopened.close()
    assert compute_sha256(db) == result.checksum_sha256 and _sidecars(db) == []


# --------------------------------------------------------------------------- #
# G. finalization that cannot collapse is INTERRUPTED, never falsely FINALIZED #
# --------------------------------------------------------------------------- #
def test_G_reader_blocking_final_collapse_yields_interrupted_with_intact_data(tmp_path, monkeypatch):
    monkeypatch.setattr(lrc, "FINALIZATION_BUSY_TIMEOUT_SECONDS", 0.2)
    holder: dict = {}

    def hold_reader():  # e.g. a read-only audit left open across 16:00
        db = next(tmp_path.glob("es_*.sqlite3"))
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, isolation_level=None)
        conn.execute("BEGIN")
        conn.execute("SELECT COUNT(*) FROM trade_observations").fetchone()
        holder["conn"] = conn

    result = _run_session(tmp_path, n=1500, before_return=hold_reader)
    db = result.database_path
    assert result.lifecycle_state is DatasetLifecycleState.INTERRUPTED
    assert result.checksum_sha256 is None and result.manifest_path is None
    assert "wal_collapse" in (result.manifest_error or "")
    assert not db.with_name(db.name + ".manifest.json").exists()
    holder["conn"].execute("COMMIT")
    holder["conn"].close()
    store = LaboratoryStore(db, read_only=True)
    assert store.load_dataset_lifecycle_state(result.dataset_id) is DatasetLifecycleState.INTERRUPTED
    stopped = next(e for e in store.load_quality_events(result.dataset_id) if e.evidence_type.value == "CAPTURE_STOPPED")
    assert "finalization_failed=wal_collapse" in stopped.detail
    store.close()
    assert _source_orders(db, result.dataset_id) == list(range(1, 1501))  # nothing lost


def test_G_collapse_failure_injected_yields_interrupted(tmp_path, monkeypatch):
    def boom(self, busy_timeout_seconds=60.0):
        raise WalCollapseError("injected: final checkpoint incomplete")

    monkeypatch.setattr(LaboratoryStore, "collapse_to_single_file", boom)
    result = _run_session(tmp_path, n=300)
    assert result.lifecycle_state is DatasetLifecycleState.INTERRUPTED
    assert result.checksum_sha256 is None and result.manifest_path is None
    assert _source_orders(result.database_path, result.dataset_id) == list(range(1, 301))


# --------------------------------------------------------------------------- #
# H. recovery then lifecycle policy                                            #
# --------------------------------------------------------------------------- #
def test_H_crashed_wal_dataset_is_interrupted_and_collapsed_next_day(tmp_path):
    out = _run_child(tmp_path, events=2000)
    db, dataset_id = out["db"], out["dataset_id"]
    assert any(name.endswith("-wal") for name in _sidecars(db))
    stale = find_stale_open_datasets(tmp_path, _INSTRUMENT, date(2026, 10, 1))
    assert stale == (db,)
    interrupt_stale_dataset(db, datetime(2026, 9, 30, 22, 0, tzinfo=_UTC))
    assert _sidecars(db) == []  # recovered and folded into the single file
    store = LaboratoryStore(db, read_only=True)
    assert store.load_dataset_lifecycle_state(dataset_id) is DatasetLifecycleState.INTERRUPTED
    summary = store.load_dataset_closing_summary(dataset_id)
    assert summary.accepted_trade_count == 2000
    assert summary.submitted_events is None  # unknown after a crash: not fabricated
    assert store._connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"  # noqa: SLF001
    store.close()


def test_H_crashed_wal_dataset_resumes_same_day_and_finalizes_single_file(tmp_path):
    out = _run_child(tmp_path, events=1200)
    dataset_id = out["dataset_id"]
    clock = _Clock(_SESSION_OPEN + timedelta(minutes=10))
    collector = _OneShotCollector(
        tuple(_event(_SESSION_OPEN + timedelta(minutes=10, milliseconds=i), 5000 + i) for i in range(1, 301))
    )
    collector.clock = clock
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=120, now=clock.now, sleeper=clock.sleep)
    assert result.dataset_id == dataset_id  # resumed, not duplicated
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    assert _source_orders(result.database_path, dataset_id) == list(range(1, 1501))
    assert _sidecars(result.database_path) == []
    # the resumed segment's own handoff accounting is exact
    assert result.writer_submitted_events == result.writer_persisted_events == 300


# --------------------------------------------------------------------------- #
# checkpoint policy: yields to ingestion                                       #
# --------------------------------------------------------------------------- #
class _CountingStore(LaboratoryStore):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checkpoints = 0

    def open_wal_checkpointer(self):
        inner, outer = super().open_wal_checkpointer(), self

        class Counting:
            def checkpoint_passive(self):
                outer.checkpoints += 1
                return inner.checkpoint_passive()

            def close(self):
                inner.close()

        return Counting()


def _writer_run(tmp_path, n, burst=False, **policy):
    import time as _time

    path, dataset_id, store, _ = _open_or_resume_dataset(tmp_path, _SPEC, _TRADING_DATE, _SESSION_OPEN)
    store.close()
    store = _CountingStore(path, check_same_thread=False)
    writer = DurableWriter(
        store, dataset_id, _INSTRUMENT, _SYMBOL, start_dataset_sequence=1, seen_new_source_indices=set(),
        policy=WriterFlushPolicy(**{"checkpoint_poll_seconds": 0.05, **policy}),
    )
    writer.start()
    for i in range(1, n + 1):
        writer.submit_event(i, _event(_SESSION_OPEN + timedelta(milliseconds=i), i))
        if not burst and i % 200 == 0:
            _time.sleep(0.15)  # quiet flow: small batches, idle gaps
    _time.sleep(0.6)  # idle moments after the last batch
    metrics = writer.drain_and_stop()
    return store, metrics


def test_checkpoint_waits_while_ingestion_is_busy(tmp_path):
    # one burst (batches >= 500), WAL above the minimum, quiet window not yet elapsed -> no checkpoint
    store, metrics = _writer_run(
        tmp_path, 6000, burst=True, checkpoint_min_wal_bytes=64 * 1024, checkpoint_quiet_seconds=30.0,
    )
    assert metrics.batch_size_max >= 500 and metrics.wal_bytes_max >= 64 * 1024
    assert store.checkpoints == 0 and metrics.checkpoint_count == 0
    store.close()


def test_checkpoint_runs_when_quiet_and_restarts_the_wal(tmp_path):
    store, metrics = _writer_run(
        tmp_path, 2000, checkpoint_min_wal_bytes=64 * 1024, checkpoint_quiet_seconds=0.0,
        checkpoint_busy_events_per_second=1e9,
    )
    assert metrics.checkpoint_count >= 1 and metrics.checkpoint_frames > 0
    assert metrics.submitted_events == metrics.persisted_events == 2000
    store.close()
    # Without checkpoints the same input grows the WAL far larger: each completed
    # checkpoint lets the next commit restart (and truncate) the WAL.
    other = tmp_path / "no_ckpt"
    other.mkdir()
    store2, unbounded = _writer_run(other, 2000, checkpoint_min_wal_bytes=1 << 40, checkpoint_force_wal_bytes=1 << 40)
    assert unbounded.checkpoint_count == 0
    assert metrics.wal_bytes_max * 3 < unbounded.wal_bytes_max
    store2.close()


def test_checkpoint_force_bound_overrides_busy(tmp_path):
    store, metrics = _writer_run(
        tmp_path, 6000, burst=True, checkpoint_min_wal_bytes=64 * 1024,
        checkpoint_force_wal_bytes=128 * 1024, checkpoint_quiet_seconds=3600.0,
    )
    assert metrics.checkpoint_count >= 1
    store.close()


def test_delete_journal_mode_never_uses_wal(tmp_path):
    store, metrics = _writer_run(tmp_path, 1000, journal_mode="delete")
    assert store.journal_mode() == "delete" and store.wal_size_bytes() == 0 and metrics.checkpoint_count == 0
    store.close()


def test_pre_0w5b_closing_summary_loads_without_fabricated_accounting(tmp_path):
    result = _run_session(tmp_path, n=50)
    conn = sqlite3.connect(result.database_path)
    for column in ("submitted_events", "persisted_events", "accounting_difference"):
        conn.execute(f"ALTER TABLE dataset_closing_summaries DROP COLUMN {column}")  # a legacy file
    conn.commit()
    conn.close()
    store = LaboratoryStore(result.database_path, read_only=True)
    summary = store.load_dataset_closing_summary(result.dataset_id)
    assert summary.accepted_trade_count == 50
    assert summary.submitted_events is None and summary.persisted_events is None
    assert summary.accounting_difference is None
    store.close()


class _BlockingCheckpointerStore(LaboratoryStore):
    """Background checkpoint that holds until released (a slow disk), or fails."""

    def __init__(self, *args, fail: bool = False, **kwargs):
        import threading

        super().__init__(*args, **kwargs)
        self.entered = threading.Event()
        self.release = threading.Event()
        self.fail = fail

    def open_wal_checkpointer(self):
        outer = self

        class Blocking:
            def checkpoint_passive(self):
                outer.entered.set()
                if outer.fail:
                    raise sqlite3.OperationalError("disk I/O error")
                outer.release.wait(timeout=10)
                return (0, 0, 0)

            def close(self):
                pass

        return Blocking()


def _blocking_writer(tmp_path, **store_kwargs):
    path, dataset_id, store, _ = _open_or_resume_dataset(tmp_path, _SPEC, _TRADING_DATE, _SESSION_OPEN)
    store.close()
    store = _BlockingCheckpointerStore(path, check_same_thread=False, **store_kwargs)
    writer = DurableWriter(
        store, dataset_id, _INSTRUMENT, _SYMBOL, start_dataset_sequence=1, seen_new_source_indices=set(),
        policy=WriterFlushPolicy(checkpoint_min_wal_bytes=1, checkpoint_quiet_seconds=0.0, checkpoint_poll_seconds=0.02),
    )
    writer.start()
    writer.submit_event(1, _event(_SESSION_OPEN, 1))
    assert store.entered.wait(timeout=5)  # a background checkpoint is now in progress
    return path, dataset_id, store, writer


def test_writer_keeps_committing_while_a_checkpoint_runs(tmp_path):
    path, dataset_id, store, writer = _blocking_writer(tmp_path)
    for i in range(2, 5_002):  # a burst arrives while the checkpoint is stuck on the disk
        writer.submit_event(i, _event(_SESSION_OPEN + timedelta(milliseconds=i), i))
    deadline = time.monotonic() + 10
    while writer.metrics.persisted_events < 5_001 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert writer.metrics.persisted_events == 5_001  # all committed (durable) during the checkpoint
    assert not store.release.is_set()
    store.release.set()
    metrics = writer.drain_and_stop()
    assert metrics.submitted_events == metrics.persisted_events == 5_001
    assert _source_orders(path, dataset_id) == list(range(1, 5_002))
    store.close()


def test_drain_waits_for_the_in_flight_checkpoint_then_returns(tmp_path):
    import threading

    path, dataset_id, store, writer = _blocking_writer(tmp_path)
    threading.Timer(0.3, store.release.set).start()
    metrics = writer.drain_and_stop()
    assert store.release.is_set() and metrics.checkpoint_count >= 1
    assert metrics.submitted_events == metrics.persisted_events == 1
    store.close()


def test_checkpointer_failure_fails_the_drain_loudly_with_data_intact(tmp_path):
    from dicks_laboratory.durable_writer import CaptureWriterError

    path, dataset_id, store, writer = _blocking_writer(tmp_path, fail=True)
    for i in range(2, 102):
        writer.submit_event(i, _event(_SESSION_OPEN + timedelta(milliseconds=i), i))
    with pytest.raises(CaptureWriterError, match="checkpointer failed"):
        writer.drain_and_stop()
    assert _source_orders(path, dataset_id) == list(range(1, 102))
    store.close()


def test_real_background_checkpoints_concurrent_with_commits_are_exact_and_bound_the_wal(tmp_path):
    """Real SQLite, real files: background PASSIVE checkpoints racing live commits."""
    store, metrics = _writer_run(
        tmp_path, 30_000, burst=False, checkpoint_min_wal_bytes=128 * 1024,
        checkpoint_quiet_seconds=0.0, checkpoint_busy_events_per_second=1e9, max_events=500,
    )
    assert metrics.checkpoint_count >= 3
    assert metrics.submitted_events == metrics.persisted_events == 30_000
    assert store.count_trade_observations(store.list_dataset_ids()[0]) == 30_000
    assert store._connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"  # noqa: SLF001
    store.close()
