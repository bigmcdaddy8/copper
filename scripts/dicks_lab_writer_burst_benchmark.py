"""0W-5A/0W-5B deterministic writer/persistence benchmark (offline, read-only source).

Replays the authentic raw TimeAndSale stream of one FINALIZED dataset, in
`source_order`, through the real `DurableWriter` + `LaboratoryStore` into a
disposable database. The source is opened `mode=ro` and never modified; no
network access.

Modes
  lifecycle  prefill (start .. --burst-start) -> burst window at full speed
             (always backlogged, as during the live drain) -> quiet pause
             (post-burst checkpoint opportunity) -> tail (rest of the day) ->
             finalization. Measures whole-lifecycle device I/O per component.
  paced      prefill (start .. --window-start) at full speed -> the window
             replayed at its real arrival times (burst minute optionally
             scaled with distinct synthetic trades) -> finalization. With
             --emulate-iops the writer thread is held after every commit /
             checkpoint / collapse until a serial disk of that IOPS (and
             --emulate-mbps) would have completed the measured device writes,
             so queue peak and persist lag reflect that disk.

Prefill/tail are submitted in chunks with idle pauses so a WAL-mode writer's
own quiet-time checkpoint policy runs during them, as it would in quiet flow.

I/O is attributed per operation from /proc/diskstats around each commit,
checkpoint and collapse (only the writer thread writes to disk during those
windows); Azure-style IOPS units = max(writes, bytes / 256 KiB).
"""
from __future__ import annotations

import bisect
import json
import math
import os
import resource
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

import typer

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.durable_writer import CaptureBackpressureError, DurableWriter, WriterFlushPolicy
from dicks_laboratory.long_running_capture import compute_sha256
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore

app = typer.Typer(add_completion=False)

_AZURE_IO_BYTES = 256 * 1024

_SOURCE_SQL = """
SELECT p.source_order, p.received_at, p.event_symbol, t.event_timestamp, p.event_classification,
       p.source_index, p.source_sequence, p.source_trade_id, p.event_flags, p.exchange_code,
       t.price, t.size, p.bid_price, p.ask_price, p.exchange_sale_conditions, p.trade_through_exempt,
       p.aggressor_side, p.spread_leg, p.extended_trading_hours, p.valid_tick
  FROM observation_source_provenance p JOIN trade_observations t USING(observation_id)
 WHERE p.source_order BETWEEN ? AND ?
UNION ALL
SELECT source_order, received_at, event_symbol, event_time, event_classification,
       source_index, source_sequence, source_trade_id, event_flags, exchange_code,
       price, size, bid_price, ask_price, exchange_sale_conditions, trade_through_exempt,
       aggressor_side, spread_leg, extended_trading_hours, valid_tick
  FROM rejected_dxlink_timesale_source_records WHERE source_order BETWEEN ? AND ?
UNION ALL
SELECT source_order, received_at, event_symbol, event_time, event_classification,
       source_index, source_sequence, source_trade_id, event_flags, exchange_code,
       price, size, bid_price, ask_price, exchange_sale_conditions, trade_through_exempt,
       aggressor_side, spread_leg, extended_trading_hours, valid_tick
  FROM deferred_dxlink_timesale_events WHERE source_order BETWEEN ? AND ?
ORDER BY 1
"""


def _ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def _epoch_ms(text: str | None) -> int | None:
    return None if text is None else int(round(_ts(text).timestamp() * 1000))


def _num(text: str | None) -> float | None:
    return None if text is None else float(text)


def _flag(value: object) -> bool | None:
    return None if value is None else bool(value)


def _source_events(source: sqlite3.Connection, first: int, last: int, chunk: int = 50_000):
    """Yield (source_order, DxLinkSourceEvent) rebuilt from durable source fields."""
    lo = first
    while lo <= last:
        hi = min(last, lo + chunk - 1)
        for row in source.execute(_SOURCE_SQL, (lo, hi) * 3):
            (order, received_at, symbol, event_time, classification, index, sequence, trade_id, flags,
             exchange, price, size, bid, ask, conditions, tte, aggressor, spread, eth, valid) = row
            yield order, DxLinkSourceEvent(
                "TimeAndSale",
                symbol,
                {
                    "eventSymbol": symbol,
                    "time": _epoch_ms(event_time),
                    "type": classification,
                    "index": index,
                    "sequence": sequence,
                    "tradeId": trade_id,
                    "eventFlags": flags,
                    "exchangeCode": exchange,
                    "price": _num(price),
                    "size": _num(size),
                    "bidPrice": _num(bid),
                    "askPrice": _num(ask),
                    "exchangeSaleConditions": conditions,
                    "tradeThroughExempt": tte,
                    "aggressorSide": aggressor,
                    "spreadLeg": _flag(spread),
                    "extendedTradingHours": _flag(eth),
                    "validTick": _flag(valid),
                },
                _ts(received_at),
            )
        lo = hi + 1


def _device_for(path: Path) -> str | None:
    """Whole block device under `path`, or None (e.g. tmpfs: no device counters)."""
    dev = os.stat(path).st_dev
    link = Path(f"/sys/dev/block/{os.major(dev)}:{os.minor(dev)}")
    if not link.exists():
        return None
    name = link.resolve().name
    parent = Path(f"/sys/class/block/{name}/..").resolve().name
    return parent if Path(f"/sys/block/{parent}").exists() else name


def _diskstats(device: str | None) -> dict | None:
    """Cumulative counters for one block device (None if unavailable)."""
    if device is None:
        return None
    for line in Path("/proc/diskstats").read_text().splitlines():
        parts = line.split()
        if parts[2] == device:
            return {
                "reads": int(parts[3]), "read_bytes": int(parts[5]) * 512,
                "writes": int(parts[7]), "write_bytes": int(parts[9]) * 512,
                "flushes": int(parts[18]) if len(parts) > 18 else 0,
            }
    return None


def _delta(before: dict | None, after: dict | None) -> dict:
    if before is None or after is None:
        return {"reads": 0, "read_bytes": 0, "writes": 0, "write_bytes": 0, "flushes": 0, "measured": False}
    out = {k: after[k] - before[k] for k in before}
    out["measured"] = True
    return out


def azure_units(writes: int, write_bytes: int) -> int:
    """Azure disk IOPS accounting: each I/O counts once per started 256 KiB."""
    return max(writes, math.ceil(write_bytes / _AZURE_IO_BYTES))


class EmulatedDisk:
    """A disk of `iops` Azure units/s and `mbps` MB/s shared by two streams.

    Foreground (writer commits) is FIFO-serial. While a background checkpoint
    holds the disk, the foreground gets only `1 - bg_share` of the bandwidth
    plus `contention_latency` seconds of queueing per commit, and the
    checkpoint itself is charged at only `bg_share` of the bandwidth for its
    whole duration (both pessimistic). `charge_*()` returns how long the caller
    must still wait for the I/O it just issued to complete."""

    def __init__(self, iops: float, mbps: float, bg_share: float = 0.5, contention_latency: float = 0.5) -> None:
        self.iops = iops
        self.bytes_per_second = mbps * 1_000_000
        self.bg_share = bg_share
        self.contention_latency = contention_latency
        self._fg_free = 0.0
        self._bg_until = 0.0
        self._lock = threading.Lock()
        self.busy_seconds = 0.0

    def _service(self, writes: int, write_bytes: int, share: float) -> float:
        return max(azure_units(writes, write_bytes) / (self.iops * share), write_bytes / (self.bytes_per_second * share))

    def charge(self, issued_at: float, writes: int, write_bytes: int, background: bool = False) -> float:
        with self._lock:
            if background:
                service = self._service(writes, write_bytes, self.bg_share)
                self._bg_until = max(self._bg_until, issued_at) + service
                done = self._bg_until
            else:
                contended = issued_at < self._bg_until
                service = self._service(writes, write_bytes, 1.0 - self.bg_share if contended else 1.0)
                service += self.contention_latency if contended else 0.0
                self._fg_free = max(self._fg_free, issued_at) + service
                done = self._fg_free
            self.busy_seconds += service
            return max(0.0, done - time.perf_counter())


class _BenchStore(LaboratoryStore):
    """Benchmark-only: attributes device I/O to each commit / checkpoint /
    collapse and optionally holds the calling thread for an emulated disk.
    Real execution of measured operations is serialized (measurement lock) so
    concurrent threads never mix their device writes; emulated waits overlap.
    Persistence itself is the unmodified production code."""

    def __init__(self, *args, device: str | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.device = device
        self.disk: EmulatedDisk | None = None
        self.ops: list[dict] = []
        self.phase = "setup"
        self._measure_lock = threading.Lock()

    def _account(self, kind: str, before: dict | None, started: float, extra: dict | None = None,
                 background: bool = False) -> None:
        d = _delta(before, _diskstats(self.device))
        elapsed = time.perf_counter() - started
        self._record(kind, d, started, elapsed, extra, background)

    def _record(self, kind, d, started, elapsed, extra, background) -> None:
        waited = 0.0
        if self.disk is not None and d["measured"]:
            waited = self.disk.charge(started, d["writes"], d["write_bytes"], background=background)
            if waited > 0:
                time.sleep(waited)
        self.ops.append({"phase": self.phase, "kind": kind, "t_start": started, "seconds": elapsed + waited, "emulated_wait": waited,
                         **{k: d[k] for k in ("writes", "write_bytes", "reads", "read_bytes", "flushes")},
                         **(extra or {})})

    @contextmanager
    def transaction(self):
        with self._measure_lock:
            before, started = _diskstats(self.device), time.perf_counter()
            with super().transaction():
                yield
            d = _delta(before, _diskstats(self.device))
            elapsed = time.perf_counter() - started
        self._record("commit", d, started, elapsed, None, False)

    def open_wal_checkpointer(self):
        inner, outer = super().open_wal_checkpointer(), self

        class Measured:
            def checkpoint_passive(self):
                wal = outer.wal_size_bytes()
                with outer._measure_lock:
                    before, started = _diskstats(outer.device), time.perf_counter()
                    result = inner.checkpoint_passive()
                    d = _delta(before, _diskstats(outer.device))
                    elapsed = time.perf_counter() - started
                outer._record("checkpoint", d, started, elapsed, {"wal_bytes_before": wal, "frames": result[2]}, True)
                return result

            def close(self):
                inner.close()

        return Measured()

    def measured(self, kind: str, fn):
        with self._measure_lock:
            before, started = _diskstats(self.device), time.perf_counter()
            value = fn()
            d = _delta(before, _diskstats(self.device))
            elapsed = time.perf_counter() - started
        self._record(kind, d, started, elapsed, None, False)
        return value


class _RecordingWriter(DurableWriter):
    """Benchmark-only subclass: records each committed batch size."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.batch_sizes: list[int] = []

    def _flush(self, batch) -> None:  # noqa: ANN001 -- private production type
        size = batch.event_count
        super()._flush(batch)
        if size:
            self.batch_sizes.append(size)


def _synthetic_copy(event: DxLinkSourceEvent, k: int) -> DxLinkSourceEvent:
    """A distinct accepted trade with the same shape/timing (scaled-burst cases only)."""
    fields = dict(event.fields)
    # Real DXLink indices are ~7.7e18 (near the int64 limit): 2**62 + k can
    # neither overflow int64 nor collide with real (or small test) indices.
    fields["index"] = (1 << 62) + k
    fields["sequence"] = (1 << 62) + k
    return DxLinkSourceEvent(event.event_type, event.streamer_symbol, fields, event.received_at)


def _wait_idle(writer: DurableWriter, settle: float) -> None:
    while writer.metrics.persisted_events < writer.metrics.submitted_events:
        time.sleep(0.01)
    time.sleep(settle)


def _phase_summary(name, store, writer, events, wall, cpu, input_seconds=None, extra=None) -> dict:
    ops = [o for o in store.ops if o["phase"] == name]
    commits = [o for o in ops if o["kind"] == "commit"]
    ckpts = [o for o in ops if o["kind"] == "checkpoint"]
    m = writer.metrics if writer else None
    sizes = sorted(writer.batch_sizes) if writer else []

    def tot(rows, key):
        return sum(r[key] for r in rows)

    cw, cb = tot(commits, "writes"), tot(commits, "write_bytes")
    aw, ab = tot(ops, "writes"), tot(ops, "write_bytes")

    def per(x):
        return round(x / events, 4) if events else None

    out = {
        "phase": name, "events": events, "wall_seconds": round(wall, 3), "cpu_seconds": round(cpu, 3),
        "input_events_per_second": round(events / input_seconds, 1) if input_seconds else None,
        "persist_events_per_second": round(events / wall, 1) if wall else None,
        "commit_count": len(commits),
        "commit_writes_per_event": per(cw), "commit_azure_units_per_event": per(azure_units(cw, cb)),
        "commit_bytes_per_event": per(cb),
        "all_writes_per_event": per(aw), "all_azure_units_per_event": per(azure_units(aw, ab)),
        "checkpoint_count": len(ckpts), "checkpoint_seconds_total": round(tot(ckpts, "seconds"), 3),
        "checkpoint_seconds_max": round(max((c["seconds"] for c in ckpts), default=0.0), 3),
        "checkpoint_writes": tot(ckpts, "writes"),
        "checkpoint_azure_units": azure_units(tot(ckpts, "writes"), tot(ckpts, "write_bytes")),
        "checkpoint_wal_bytes_max": max((c["wal_bytes_before"] for c in ckpts), default=0),
        "emulated_wait_seconds": round(tot(ops, "emulated_wait"), 3),
    }
    if m is not None:
        out.update({
            "submitted_events": m.submitted_events, "persisted_events": m.persisted_events,
            "accounting_difference": m.accounting_difference, "flush_count": m.flush_count,
            "batch_size_p50": sizes[len(sizes) // 2] if sizes else 0, "batch_size_max": m.batch_size_max,
            "queue_depth_max": m.queue_depth_max,
            "queue_limit_pct": round(100 * m.queue_depth_max / writer._policy.queue_maxsize, 1),  # noqa: SLF001
            "max_persist_lag_seconds": round(m.max_persist_lag_seconds, 3), "writer_overloaded": m.overloaded,
            "wal_bytes_max": m.wal_bytes_max,
        })
    out.update(extra or {})
    return out


@app.command()
def run(
    source_db: Path = typer.Argument(..., help="FINALIZED Dick's Laboratory dataset (opened read-only)."),
    scratch_dir: Path = typer.Option(..., "--scratch-dir", help="Directory for the disposable benchmark DB (real disk, not tmpfs)."),
    mode: str = typer.Option("lifecycle", "--mode", help="'lifecycle' or 'paced'."),
    journal_mode: str = typer.Option(WriterFlushPolicy().journal_mode, "--journal-mode", help="Writer policy: 'wal' or 'delete'."),
    burst_start: str = typer.Option("2026-09-30T19:58:00Z", "--burst-start", help="lifecycle: full-speed burst window start."),
    burst_end: str = typer.Option("2026-09-30T20:06:00Z", "--burst-end", help="lifecycle: burst window end / paced: window end."),
    window_start: str = typer.Option("2026-09-30T19:57:00Z", "--window-start", help="paced: replay window start."),
    scale: float = typer.Option(1.0, "--scale", help="paced: event-count multiplier inside the scale window."),
    scale_start: str = typer.Option("2026-09-30T19:59:00Z", "--scale-start"),
    scale_end: str = typer.Option("2026-09-30T20:01:00Z", "--scale-end"),
    emulate_iops: float = typer.Option(0.0, "--emulate-iops", help="paced: serial-disk emulation (0 = off)."),
    emulate_mbps: float = typer.Option(100.0, "--emulate-mbps"),
    emulate_bg_share: float = typer.Option(0.5, "--emulate-bg-share", help="Disk share of a background checkpoint under contention."),
    emulate_contention_latency: float = typer.Option(0.5, "--emulate-contention-latency", help="Extra seconds per commit while a checkpoint holds the disk."),
    max_events: int = typer.Option(WriterFlushPolicy().max_events, "--max-events"),
    checkpoint_quiet_seconds: float = typer.Option(WriterFlushPolicy().checkpoint_quiet_seconds, "--checkpoint-quiet-seconds"),
    checkpoint_min_wal_mib: float = typer.Option(WriterFlushPolicy().checkpoint_min_wal_bytes / 2**20, "--checkpoint-min-wal-mib"),
    checkpoint_force_wal_mib: float = typer.Option(WriterFlushPolicy().checkpoint_force_wal_bytes / 2**20, "--checkpoint-force-wal-mib"),
    prefill_chunk: int = typer.Option(20_000, "--prefill-chunk", help="Events per prefill/tail chunk before an idle pause."),
    prefill_limit: int | None = typer.Option(None, "--prefill-limit", help="Cap prefill events (smoke tests)."),
    burst_limit: int | None = typer.Option(None, "--burst-limit", help="Cap burst/window events (smoke tests)."),
    skip_tail: bool = typer.Option(False, "--skip-tail"),
    prefill_snapshot: Path | None = typer.Option(
        None, "--prefill-snapshot",
        help="Reuse (or create) a collapsed copy of the prefilled DB for this window start -- same index state, minutes faster.",
    ),
    cold_checks: bool = typer.Option(True, "--cold-checks/--no-cold-checks"),
    label: str = typer.Option("run", "--label"),
    output_json: Path | None = typer.Option(None, "--output-json"),
    keep_db: bool = typer.Option(False, "--keep-db"),
) -> None:
    if mode not in ("lifecycle", "paced"):
        raise typer.BadParameter("--mode must be 'lifecycle' or 'paced'")
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    source_dataset_id, trading_date, instrument_id, locator = source.execute(
        "SELECT dataset_id, trading_date, instrument_id, source_locator FROM datasets").fetchone()
    _, exchange, root, expiry = instrument_id.split(":")
    year, month = (int(part) for part in expiry.split("-"))
    instrument = InstrumentIdentity(InstrumentKind.FUTURE, exchange, root, year, month)
    symbol = locator.split(":", 1)[1].rsplit(":", 1)[0]
    last_order = source.execute(
        "SELECT MAX(source_order) FROM (SELECT source_order FROM observation_source_provenance "
        "UNION ALL SELECT source_order FROM normalization_rejections "
        "UNION ALL SELECT source_order FROM deferred_dxlink_timesale_events)").fetchone()[0]

    def first_order_at(moment: str) -> int:
        row = source.execute(
            "SELECT MIN(source_order) FROM observation_source_provenance WHERE received_at >= ?",
            (_ts(moment).isoformat(),)).fetchone()
        return int(row[0]) if row[0] is not None else last_order + 1

    win_first = first_order_at(burst_start if mode == "lifecycle" else window_start)
    win_last = first_order_at(burst_end) - 1
    prefill_last = win_first - 1 if prefill_limit is None else min(win_first - 1, prefill_limit)
    if burst_limit is not None:
        win_last = min(win_last, win_first + burst_limit - 1)
    tail_span = (win_last + 1, last_order) if (mode == "lifecycle" and not skip_tail) else None

    scratch_dir.mkdir(parents=True, exist_ok=True)
    work = scratch_dir / f"bench_{label}_{os.getpid()}"
    work.mkdir()
    db_path = work / "bench.sqlite3"
    device = _device_for(work)
    store = _BenchStore(db_path, check_same_thread=False, device=device)
    dataset_id = uuid5(UUID(source_dataset_id), f"0w5-benchmark:{label}")
    store.save_dataset(DatasetIdentity(
        dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label=f"0w5-bench-{label}",
        source_locator=locator, source_timezone="UTC epoch milliseconds", normalizer_version="bench",
        capture_started_at=_ts(window_start), origin=DatasetOrigin.AUTHENTIC_SOURCE))
    store.save_dataset_trading_context(dataset_id, datetime.fromisoformat(trading_date).date(), instrument)
    policy = WriterFlushPolicy(
        journal_mode=journal_mode, max_events=max_events, checkpoint_quiet_seconds=checkpoint_quiet_seconds,
        checkpoint_min_wal_bytes=int(checkpoint_min_wal_mib * 2**20),
        checkpoint_force_wal_bytes=int(checkpoint_force_wal_mib * 2**20))
    quiet_policy = replace(policy, checkpoint_quiet_seconds=min(policy.checkpoint_quiet_seconds, 0.2),
                           checkpoint_poll_seconds=min(policy.checkpoint_poll_seconds, 0.1))
    seen: set[int] = set()
    state = {"next_seq": 1, "next_order": 1, "synthetic": 0}
    phases: list[dict] = []

    def new_writer(pol: WriterFlushPolicy) -> _RecordingWriter:
        return _RecordingWriter(store, dataset_id, instrument, symbol,
                                start_dataset_sequence=state["next_seq"], seen_new_source_indices=seen, policy=pol)

    def cpu_now() -> float:
        r = resource.getrusage(resource.RUSAGE_SELF)
        return r.ru_utime + r.ru_stime

    def chunked_phase(name: str, first: int, last: int) -> None:
        """Full-speed chunks with idle pauses (quiet-flow checkpoint opportunities)."""
        if last < first:
            return
        store.phase = name
        writer = new_writer(quiet_policy)
        cpu0, t0 = cpu_now(), time.perf_counter()
        writer.start()
        count = 0
        for _order, event in _source_events(source, first, last):
            writer.submit_event(state["next_order"], event)
            state["next_order"] += 1
            count += 1
            if count % prefill_chunk == 0:
                _wait_idle(writer, quiet_policy.checkpoint_quiet_seconds + 0.3)
        _wait_idle(writer, quiet_policy.checkpoint_quiet_seconds + 0.3)
        writer.drain_and_stop()
        state["next_seq"] = store.count_trade_observations(dataset_id) + 1
        phases.append(_phase_summary(name, store, writer, count, time.perf_counter() - t0, cpu_now() - cpu0))
        typer.echo(json.dumps(phases[-1]))

    if prefill_snapshot is not None and prefill_snapshot.exists():
        store.close()
        shutil.copyfile(prefill_snapshot, db_path)
        store = _BenchStore(db_path, check_same_thread=False, device=device)
        (dataset_id,) = store.list_dataset_ids()  # the snapshot's own dataset
        state["next_order"] = prefill_last + 1
        state["next_seq"] = store.count_trade_observations(dataset_id) + 1
        seen.update(row[0] for row in store._connection.execute("SELECT source_index FROM observation_source_provenance"))  # noqa: SLF001
        if state["next_seq"] - 1 != source.execute(
                "SELECT COUNT(*) FROM observation_source_provenance WHERE source_order <= ?", (prefill_last,)).fetchone()[0]:
            raise typer.BadParameter("--prefill-snapshot does not match this source/window")
        phases.append({"phase": "prefill", "events": prefill_last, "from_snapshot": str(prefill_snapshot),
                       "submitted_events": prefill_last, "persisted_events": prefill_last})
    else:
        chunked_phase("prefill", 1, prefill_last)
        if prefill_snapshot is not None:
            store.collapse_to_single_file()
            shutil.copyfile(db_path, prefill_snapshot)

    # ---- the measured window ------------------------------------------------
    store.phase = "burst" if mode == "lifecycle" else "paced"
    writer = new_writer(policy)
    scale_window = (_ts(scale_start), _ts(scale_end))
    stream: list[DxLinkSourceEvent] = []
    carry = 0.0
    for _order, event in _source_events(source, win_first, win_last):
        stream.append(event)
        if mode == "paced" and scale != 1.0 and scale_window[0] <= event.received_at < scale_window[1] \
                and event.fields.get("type") == "NEW" and event.fields.get("validTick"):
            carry += scale - 1.0
            while carry >= 1.0:
                carry -= 1.0
                state["synthetic"] += 1
                stream.append(_synthetic_copy(event, state["synthetic"]))
    if mode == "paced" and emulate_iops > 0:
        store.disk = EmulatedDisk(emulate_iops, emulate_mbps, emulate_bg_share, emulate_contention_latency)
    cpu0, t0 = cpu_now(), time.perf_counter()
    samples: list[tuple[float, int, int]] = []
    sampling = threading.Event()

    def sampler() -> None:
        while not sampling.is_set():
            samples.append((round(time.perf_counter() - t0, 2), writer._queue.qsize(), store.wal_size_bytes()))  # noqa: SLF001
            time.sleep(0.25)

    sampler_thread = threading.Thread(target=sampler, daemon=True)
    writer.start()
    sampler_thread.start()
    first_arrival = stream[0].received_at if stream else None
    overloaded_at: int | None = None
    for position, event in enumerate(stream):
        if mode == "paced":
            delay = t0 + (event.received_at - first_arrival).total_seconds() - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
        try:
            writer.submit_event(state["next_order"], event)
        except CaptureBackpressureError:
            overloaded_at = position  # production: the dataset would end INTERRUPTED here
            break
        state["next_order"] += 1
    input_seconds = (time.perf_counter() - t0) if mode == "paced" else None
    _wait_idle(writer, policy.checkpoint_quiet_seconds + 1.5)  # post-burst quiet: checkpoint opportunity
    writer.drain_and_stop()
    sampling.set()
    sampler_thread.join()
    state["next_seq"] = store.count_trade_observations(dataset_id) + 1
    window_ops = [o for o in store.ops if o["phase"] == store.phase]
    timeline = {
        "queue_wal_samples": samples,
        "slow_ops": [
            {"kind": o["kind"], "t": round(o["t_start"] - t0, 2), "seconds": round(o["seconds"], 2),
             "azure_units": azure_units(o["writes"], o["write_bytes"]), "wal_bytes_before": o.get("wal_bytes_before")}
            for o in window_ops if o["kind"] != "commit" or o["seconds"] > 1.0
        ],
    }
    submitted_window = writer.metrics.submitted_events
    phases.append(_phase_summary(
        store.phase, store, writer, submitted_window, time.perf_counter() - t0, cpu_now() - cpu0, input_seconds=input_seconds,
        extra={"synthetic_events": state["synthetic"], "scale": scale, "emulated_iops": emulate_iops or None,
               "overloaded": overloaded_at is not None, "overloaded_at_stream_position": overloaded_at,
               "stream_events": len(stream),
               "emulated_disk_busy_seconds": round(store.disk.busy_seconds, 3) if store.disk else None,
               "emulated_bg_share": emulate_bg_share if store.disk else None,
               "emulated_contention_latency": emulate_contention_latency if store.disk else None}))
    typer.echo(json.dumps(phases[-1]))
    phases[-1]["timeline"] = timeline

    if tail_span is not None:
        chunked_phase("tail", tail_span[0], tail_span[1] if prefill_limit is None else win_last)

    # ---- finalization (each step measured; emulated disk still applies in paced mode) ----
    store.phase = "finalize"
    fin: dict = {"journal_mode_before": store.journal_mode(), "wal_bytes_before": store.wal_size_bytes()}
    t_fin = time.perf_counter()
    if fin["journal_mode_before"] == "wal":
        fin["final_checkpoint"] = list(store.measured(
            "final_checkpoint", lambda: store._connection.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()))  # noqa: SLF001
    store.measured("collapse", store.collapse_to_single_file)
    fin["sidecars_after_collapse"] = [p.name for p in store.sidecar_paths()]
    fin["journal_mode_after"] = store.journal_mode()
    t = time.perf_counter()
    fin["quick_check"] = store.quick_check()
    fin["quick_check_seconds_warm"] = round(time.perf_counter() - t, 3)
    t = time.perf_counter()
    fin["integrity_check"] = store._connection.execute("PRAGMA integrity_check").fetchone()[0]  # noqa: SLF001
    fin["integrity_check_seconds_warm"] = round(time.perf_counter() - t, 3)
    fin["finalization_core_seconds"] = round(time.perf_counter() - t_fin, 3)

    bench = store._connection  # noqa: SLF001 -- read-only verification queries
    replayed = [(1, prefill_last), (win_first, win_last)]
    if tail_span is not None and prefill_limit is None:
        replayed.append(tail_span)

    def source_counts(table: str) -> int:
        return sum(source.execute(f"SELECT COUNT(*) FROM {table} WHERE source_order BETWEEN ? AND ?", span).fetchone()[0]
                   for span in replayed if span[1] >= span[0])

    accounting = {
        "source_accepted": source_counts("observation_source_provenance"),
        "synthetic_accepted": state["synthetic"],
        "source_rejected": source_counts("normalization_rejections"),
        "source_deferred": source_counts("deferred_dxlink_timesale_events"),
        "bench_accepted": bench.execute("SELECT COUNT(*) FROM trade_observations").fetchone()[0],
        "bench_rejected": bench.execute("SELECT COUNT(*) FROM normalization_rejections").fetchone()[0],
        "bench_deferred": bench.execute("SELECT COUNT(*) FROM deferred_dxlink_timesale_events").fetchone()[0],
        "bench_dataset_sequence": list(bench.execute(
            "SELECT MIN(dataset_sequence), MAX(dataset_sequence), COUNT(DISTINCT dataset_sequence) FROM trade_observations").fetchone()),
        "bench_source_order": list(bench.execute(
            "SELECT MIN(o), MAX(o), COUNT(DISTINCT o) FROM (SELECT source_order o FROM observation_source_provenance "
            "UNION ALL SELECT source_order FROM normalization_rejections "
            "UNION ALL SELECT source_order FROM deferred_dxlink_timesale_events)").fetchone()),
        "submitted_total": sum(p.get("submitted_events", 0) for p in phases),
        "persisted_total": sum(p.get("persisted_events", 0) for p in phases),
        "bench_journal_mode": fin["journal_mode_after"],
        "bench_synchronous": bench.execute("PRAGMA synchronous").fetchone()[0],
        "bench_quick_check": fin["quick_check"],
        "bench_integrity_check": fin["integrity_check"],
    }
    if overloaded_at is None:
        expected = accounting["source_accepted"] + accounting["synthetic_accepted"]
        total = expected + accounting["source_rejected"] + accounting["source_deferred"]
        source_match = (
            accounting["bench_accepted"] == expected
            and accounting["bench_rejected"] == accounting["source_rejected"]
            and accounting["bench_deferred"] == accounting["source_deferred"]
        )
    else:
        # Overload stopped submission part-way: check exactness over what was submitted.
        expected = accounting["bench_accepted"]
        total = accounting["submitted_total"]
        source_match = expected + accounting["bench_rejected"] + accounting["bench_deferred"] == total
    accounting["overloaded"] = overloaded_at is not None
    accounting["exact"] = (
        source_match
        and accounting["bench_dataset_sequence"] == [1, expected, expected]
        and accounting["bench_source_order"] == [1, total, total]
        and accounting["submitted_total"] == accounting["persisted_total"] == total
        and fin["sidecars_after_collapse"] == [] and fin["journal_mode_after"] == "delete"
        and fin["quick_check"] == "ok" and fin["integrity_check"] == "ok"
    )
    store.disk = None
    store.close()
    leftovers = sorted(p.name for p in work.iterdir() if p.name != db_path.name)
    t = time.perf_counter()
    fin["checksum_sha256"] = compute_sha256(db_path)
    fin["checksum_seconds_warm"] = round(time.perf_counter() - t, 3)
    fin["checksum_stable"] = compute_sha256(db_path) == fin["checksum_sha256"]
    fin["sidecars_after_close"] = leftovers
    if cold_checks and hasattr(os, "posix_fadvise"):
        def evict() -> None:
            os.sync()
            with db_path.open("rb") as handle:
                os.posix_fadvise(handle.fileno(), 0, 0, os.POSIX_FADV_DONTNEED)

        evict()
        before, t = _diskstats(device), time.perf_counter()
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        conn.execute("PRAGMA quick_check").fetchone()
        conn.close()
        d = _delta(before, _diskstats(device))
        fin["quick_check_cold"] = {"seconds": round(time.perf_counter() - t, 3), "device_reads": d["reads"], "read_bytes": d["read_bytes"]}
        evict()
        before, t = _diskstats(device), time.perf_counter()
        compute_sha256(db_path)
        d = _delta(before, _diskstats(device))
        fin["checksum_cold"] = {"seconds": round(time.perf_counter() - t, 3), "device_reads": d["reads"], "read_bytes": d["read_bytes"]}
    fin_ops = [o for o in store.ops if o["phase"] == "finalize"]
    fin["finalize_ops"] = [{k: o[k] for k in ("kind", "seconds", "writes", "write_bytes", "reads")} for o in fin_ops]
    fin["finalize_azure_units"] = azure_units(sum(o["writes"] for o in fin_ops), sum(o["write_bytes"] for o in fin_ops))
    accounting["exact"] = accounting["exact"] and fin["checksum_stable"] and leftovers == []
    db_size = db_path.stat().st_size

    def units(kinds: tuple[str, ...] | None) -> int:
        rows = [o for o in store.ops if kinds is None or o["kind"] in kinds]
        return azure_units(sum(o["writes"] for o in rows), sum(o["write_bytes"] for o in rows))

    events_total = sum(p["events"] for p in phases)
    lifecycle_totals = {
        "events": events_total,
        "device_writes": sum(o["writes"] for o in store.ops),
        "bytes_written": sum(o["write_bytes"] for o in store.ops),
        "azure_units": units(None),
        "commit_azure_units": units(("commit",)),
        "checkpoint_azure_units": units(("checkpoint", "final_checkpoint", "collapse")),
        "azure_units_per_event": round(units(None) / events_total, 4) if events_total else None,
        "max_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
    }
    summary = {"finalization": fin, "accounting": accounting, "lifecycle_totals": lifecycle_totals,
               "db_size_bytes": db_size, "device": device}
    typer.echo(json.dumps(summary))
    report = {
        "label": label, "mode": mode, "source_db": str(source_db), "policy": policy.__dict__,
        "windows": {"burst_or_window": [burst_start if mode == "lifecycle" else window_start, burst_end],
                    "scale_window": [scale_start, scale_end]},
        "phases": phases, **summary, "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if output_json:
        output_json.write_text(json.dumps(report, indent=1, default=str))
    if not keep_db:
        shutil.rmtree(work)
    if not accounting["exact"]:
        raise typer.Exit(code=1)


def fifo_replay(arrivals: list[float], events_per_second: float, batch: int) -> tuple[int, float]:
    """Queue-depth peak and max persist lag for FIFO arrivals drained at a fixed rate,
    committing up to `batch` already-arrived events at a time."""
    if not arrivals:
        return 0, 0.0
    i, free, q_max, lag_max, n = 0, arrivals[0], 0, 0.0, len(arrivals)
    while i < n:
        start = max(free, arrivals[i])
        available = bisect.bisect_right(arrivals, start, lo=i)
        q_max = max(q_max, available - i)
        j = min(max(available, i + 1), i + batch)
        done = start + (j - i) / events_per_second
        lag_max = max(lag_max, done - arrivals[i])
        free, i = done, j
    return q_max, lag_max


def scaled_arrivals(arrivals: list[float], window: tuple[float, float], factor: float) -> list[float]:
    """Deterministically scale the event count inside `window` by `factor`
    (each in-window arrival is repeated floor/ceil(factor) times, evenly)."""
    out: list[float] = []
    carry = 0.0
    for t in arrivals:
        if window[0] <= t < window[1]:
            carry += factor
            copies = int(carry)
            carry -= copies
            out.extend([t] * copies)
        else:
            out.append(t)
    return out


@app.command("live-burst-replay")
def live_burst_replay(
    source_db: Path = typer.Argument(..., help="FINALIZED dataset whose real arrival times are replayed (read-only)."),
    window_start: str = typer.Option("2026-09-30T19:30:00Z", "--window-start"),
    window_end: str = typer.Option("2026-09-30T20:30:00Z", "--window-end"),
    burst_start: str = typer.Option("2026-09-30T19:59:00Z", "--burst-start"),
    burst_end: str = typer.Option("2026-09-30T20:01:00Z", "--burst-end"),
    rate: list[float] = typer.Option(..., "--rate", help="Sustained persistence rate(s), events/s."),
    scale: list[float] = typer.Option([1.0], "--scale", help="Burst-window event-count multiplier(s)."),
    batch: int = typer.Option(250, "--batch"),
    queue_maxsize: int = typer.Option(50_000, "--queue-maxsize"),
) -> None:
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    arrivals = [
        _ts(row[0]).timestamp()
        for row in source.execute(
            "SELECT received_at FROM observation_source_provenance WHERE received_at >= ? AND received_at < ? ORDER BY source_order",
            (_ts(window_start).isoformat(), _ts(window_end).isoformat()),
        )
    ]
    window = (_ts(burst_start).timestamp(), _ts(burst_end).timestamp())
    for factor in scale:
        scaled = scaled_arrivals(arrivals, window, factor)
        for mu in rate:
            q_max, lag = fifo_replay(scaled, mu, batch)
            typer.echo(json.dumps({
                "scale": factor, "events_in_window": len(scaled), "rate_events_per_second": mu,
                "queue_peak": q_max, "queue_peak_pct_of_limit": round(100 * q_max / queue_maxsize, 1),
                "max_persist_lag_seconds": round(lag, 1), "would_overload": q_max >= queue_maxsize,
            }))


if __name__ == "__main__":
    app()
