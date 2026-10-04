"""0W-5A deterministic writer/persistence burst benchmark (offline, read-only source).

Replays the authentic raw TimeAndSale stream of one FINALIZED dataset, in
`source_order`, through the real `DurableWriter` + `LaboratoryStore` into a
disposable database, and measures what persistence costs:

    prefill     source_order 1 .. (first event received at/after --burst-start)
                -> grows the indexes to their real pre-burst size
    burst       the --burst-start .. --burst-end window, submitted as fast as
                the bounded queue accepts (always backlogged, as during the
                live post-burst drain), measured on its own

The source dataset is opened `mode=ro` and never modified. No network access.

Device write operations are read from /proc/diskstats for the block device
holding the scratch database (a whole-device counter: run on an otherwise idle
host). `device writes / event` is the transferable number: on a disk with an
IOPS ceiling the sustained persistence rate is approximately
`ceiling / (device writes per event)`. `--live-burst-replay` then pushes the
real per-event arrival times of the source window (optionally scaled) through
a FIFO model at that rate to predict queue peak and persist lag.
"""
from __future__ import annotations

import bisect
import json
import os
import resource
import shutil
import sqlite3
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid5

import typer

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.durable_writer import DurableWriter, WriterFlushPolicy
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore

app = typer.Typer(add_completion=False)

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


def _diskstats(device: str | None) -> tuple[int, int, int] | None:
    """(writes completed, sectors written, flushes completed) for one block device."""
    if device is None:
        return None
    for line in Path("/proc/diskstats").read_text().splitlines():
        parts = line.split()
        if parts[2] == device:
            flushes = int(parts[18]) if len(parts) > 18 else 0
            return int(parts[7]), int(parts[9]), flushes
    return None


class _RecordingWriter(DurableWriter):
    """Benchmark-only subclass: records each committed batch size. Persistence
    itself is the unmodified production `_flush`."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.batch_sizes: list[int] = []

    def _flush(self, batch) -> None:  # noqa: ANN001 -- private production type
        size = batch.event_count
        super()._flush(batch)
        if size:
            self.batch_sizes.append(size)


@dataclass
class PhaseResult:
    phase: str
    events: int
    wall_seconds: float
    events_per_second: float
    cpu_seconds: float
    flush_count: int
    avg_events_per_flush: float
    batch_size_p50: int
    batch_size_max: int
    queue_depth_max: int
    max_persist_lag_seconds: float
    device_writes: int | None
    device_writes_per_event: float | None
    device_flushes: int | None
    sectors_written: int | None
    bytes_written_per_event: float | None
    predicted_events_per_second_at_603_iops: float | None


def _run_phase(phase, writer_factory, source, first, last, device, wal_final_checkpoint=True) -> tuple[PhaseResult, dict]:
    writer = writer_factory()
    os.sync()
    before = _diskstats(device)
    cpu0 = resource.getrusage(resource.RUSAGE_SELF)
    t0 = time.perf_counter()
    writer.start()
    count = 0
    for order, event in _source_events(source, first, last):
        writer.submit_event(order, event)
        count += 1
    metrics = writer.drain_and_stop()
    connection = writer._store._connection  # noqa: SLF001 -- count deferred WAL page writes inside the phase
    if wal_final_checkpoint and connection.execute("PRAGMA journal_mode").fetchone()[0] == "wal":
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    wall = time.perf_counter() - t0
    cpu1 = resource.getrusage(resource.RUSAGE_SELF)
    os.sync()
    after = _diskstats(device)
    sizes = sorted(writer.batch_sizes)
    if before is not None and after is not None and count:
        writes, sectors, flushes = (b - a for a, b in zip(before, after))
        per_event = writes / count
    else:
        writes = sectors = flushes = per_event = None
    result = PhaseResult(
        phase=phase,
        events=count,
        wall_seconds=round(wall, 3),
        events_per_second=round(count / wall, 1) if wall else 0.0,
        cpu_seconds=round((cpu1.ru_utime + cpu1.ru_stime) - (cpu0.ru_utime + cpu0.ru_stime), 3),
        flush_count=metrics.flush_count,
        avg_events_per_flush=round(metrics.persisted_events / metrics.flush_count, 2) if metrics.flush_count else 0.0,
        batch_size_p50=sizes[len(sizes) // 2] if sizes else 0,
        batch_size_max=metrics.batch_size_max,
        queue_depth_max=metrics.queue_depth_max,
        max_persist_lag_seconds=round(metrics.max_persist_lag_seconds, 3),
        device_writes=writes,
        device_writes_per_event=None if per_event is None else round(per_event, 4),
        device_flushes=flushes,
        sectors_written=sectors,
        bytes_written_per_event=None if sectors is None else round(sectors * 512 / count, 1),
        predicted_events_per_second_at_603_iops=round(603 / per_event, 1) if per_event else None,
    )
    histogram = Counter(_bucket(size) for size in sizes)
    return result, {"batch_size_histogram": dict(sorted(histogram.items(), key=lambda kv: _bucket_key(kv[0])))}


def _bucket(size: int) -> str:
    for edge in (1, 5, 10, 50, 100, 249):
        if size <= edge:
            return f"<={edge}"
    return f"={size}" if size in (250,) else ">=250" if size < 1000 else ">=1000"


def _bucket_key(label: str) -> int:
    return int("".join(ch for ch in label if ch.isdigit()))


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


@app.command()
def run(
    source_db: Path = typer.Argument(..., help="FINALIZED Dick's Laboratory dataset (opened read-only)."),
    scratch_dir: Path = typer.Option(..., "--scratch-dir", help="Directory for the disposable benchmark DB (real disk, not tmpfs)."),
    burst_start: str = typer.Option("2026-09-30T19:58:00Z", "--burst-start"),
    burst_end: str = typer.Option("2026-09-30T20:06:00Z", "--burst-end"),
    max_events: int = typer.Option(WriterFlushPolicy().max_events, "--max-events"),
    max_interval_seconds: float = typer.Option(WriterFlushPolicy().max_interval_seconds, "--max-interval-seconds"),
    queue_maxsize: int = typer.Option(WriterFlushPolicy().queue_maxsize, "--queue-maxsize"),
    prefill_limit: int | None = typer.Option(None, "--prefill-limit", help="Cap prefill events (smoke tests)."),
    burst_limit: int | None = typer.Option(None, "--burst-limit", help="Cap burst events (smoke tests)."),
    cache_size_kib: int | None = typer.Option(None, "--cache-size-kib", help="Experiment: PRAGMA cache_size=-N on the scratch DB."),
    journal_mode: str | None = typer.Option(None, "--journal-mode", help="Experiment: PRAGMA journal_mode on the scratch DB (e.g. wal)."),
    wal_autocheckpoint: int | None = typer.Option(None, "--wal-autocheckpoint", help="Experiment: PRAGMA wal_autocheckpoint (pages)."),
    wal_final_checkpoint: bool = typer.Option(
        True, "--wal-final-checkpoint/--no-wal-final-checkpoint",
        help="Experiment: count (default) or exclude deferred WAL checkpoint writes in each phase.",
    ),
    label: str = typer.Option("baseline", "--label"),
    output_json: Path | None = typer.Option(None, "--output-json"),
    keep_db: bool = typer.Option(False, "--keep-db"),
) -> None:
    source = sqlite3.connect(f"file:{source_db}?mode=ro", uri=True)
    dataset_row = source.execute("SELECT dataset_id, trading_date, instrument_id, source_locator FROM datasets").fetchone()
    source_dataset_id, trading_date, instrument_id, locator = dataset_row
    _, exchange, root, expiry = instrument_id.split(":")
    year, month = (int(part) for part in expiry.split("-"))
    instrument = InstrumentIdentity(InstrumentKind.FUTURE, exchange, root, year, month)
    symbol = locator.split(":", 1)[1].rsplit(":", 1)[0]

    def first_order_at(moment: str) -> int:
        row = source.execute(
            "SELECT MIN(source_order) FROM observation_source_provenance WHERE received_at >= ?",
            (_ts(moment).isoformat(),),
        ).fetchone()
        return int(row[0])

    last_order = source.execute(
        "SELECT MAX(source_order) FROM (SELECT source_order FROM observation_source_provenance "
        "UNION ALL SELECT source_order FROM normalization_rejections "
        "UNION ALL SELECT source_order FROM deferred_dxlink_timesale_events)"
    ).fetchone()[0]
    burst_first = first_order_at(burst_start)
    burst_last = first_order_at(burst_end) - 1
    prefill_last = burst_first - 1
    if prefill_limit is not None:
        prefill_last = min(prefill_last, prefill_limit)
    if burst_limit is not None:
        burst_last = min(burst_last, burst_first + burst_limit - 1)

    scratch_dir.mkdir(parents=True, exist_ok=True)
    work = scratch_dir / f"bench_{label}_{os.getpid()}"
    work.mkdir()
    db_path = work / "bench.sqlite3"
    device = _device_for(work)
    store = LaboratoryStore(db_path, check_same_thread=False)
    pragmas = {}
    connection = store._connection  # noqa: SLF001 -- benchmark-only experiment knobs
    if cache_size_kib is not None:
        connection.execute(f"PRAGMA cache_size=-{int(cache_size_kib)}")
    if journal_mode is not None:
        connection.execute(f"PRAGMA journal_mode={journal_mode}")
    if wal_autocheckpoint is not None:
        connection.execute(f"PRAGMA wal_autocheckpoint={int(wal_autocheckpoint)}")
    for name in ("journal_mode", "synchronous", "cache_size", "page_size", "wal_autocheckpoint"):
        pragmas[name] = connection.execute(f"PRAGMA {name}").fetchone()[0]
    typer.echo(json.dumps({"pragmas": pragmas}))
    dataset_id = uuid5(UUID(source_dataset_id), f"0w5a-benchmark:{label}")
    started = _ts(burst_start)
    store.save_dataset(
        DatasetIdentity(
            dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label=f"0w5a-bench-{label}",
            source_locator=locator, source_timezone="UTC epoch milliseconds", normalizer_version="bench",
            capture_started_at=started, origin=DatasetOrigin.AUTHENTIC_SOURCE,
        )
    )
    store.save_dataset_trading_context(dataset_id, datetime.fromisoformat(trading_date).date(), instrument)
    policy = WriterFlushPolicy(max_events=max_events, max_interval_seconds=max_interval_seconds, queue_maxsize=queue_maxsize)
    seen: set[int] = set()
    sequence = {"next": 1}

    def factory() -> _RecordingWriter:
        writer = _RecordingWriter(
            store, dataset_id, instrument, symbol,
            start_dataset_sequence=sequence["next"], seen_new_source_indices=seen, policy=policy,
        )
        return writer

    phases = []
    for phase, first, last in (("prefill", 1, prefill_last), ("burst", burst_first, burst_last)):
        if last < first:
            continue
        result, extra = _run_phase(phase, factory, source, first, last, device, wal_final_checkpoint)
        sequence["next"] = store.count_trade_observations(dataset_id) + 1
        phases.append({**asdict(result), **extra})
        typer.echo(json.dumps({**asdict(result), **extra}))

    # Exact accounting of what was replayed vs the source.
    replayed = [(1, prefill_last)] + ([(burst_first, burst_last)] if burst_last >= burst_first else [])
    def source_counts(table: str) -> int:
        return sum(
            source.execute(f"SELECT COUNT(*) FROM {table} WHERE source_order BETWEEN ? AND ?", span).fetchone()[0]
            for span in replayed
        )
    bench = store._connection  # noqa: SLF001 -- read-only verification queries
    accounting = {
        "source_accepted": source_counts("observation_source_provenance"),
        "source_rejected": source_counts("normalization_rejections"),
        "source_deferred": source_counts("deferred_dxlink_timesale_events"),
        "bench_accepted": bench.execute("SELECT COUNT(*) FROM trade_observations").fetchone()[0],
        "bench_rejected": bench.execute("SELECT COUNT(*) FROM normalization_rejections").fetchone()[0],
        "bench_deferred": bench.execute("SELECT COUNT(*) FROM deferred_dxlink_timesale_events").fetchone()[0],
        "bench_dataset_sequence": list(bench.execute(
            "SELECT MIN(dataset_sequence), MAX(dataset_sequence), COUNT(DISTINCT dataset_sequence) FROM trade_observations"
        ).fetchone()),
        "bench_source_order_distinct": bench.execute(
            "SELECT COUNT(DISTINCT source_order) FROM (SELECT source_order FROM observation_source_provenance "
            "UNION ALL SELECT source_order FROM normalization_rejections UNION ALL SELECT source_order FROM deferred_dxlink_timesale_events)"
        ).fetchone()[0],
        "bench_journal_mode": bench.execute("PRAGMA journal_mode").fetchone()[0],
        "bench_synchronous": bench.execute("PRAGMA synchronous").fetchone()[0],
        "bench_quick_check": bench.execute("PRAGMA quick_check").fetchone()[0],
    }
    accounting["exact"] = (
        accounting["source_accepted"] == accounting["bench_accepted"]
        and accounting["source_rejected"] == accounting["bench_rejected"]
        and accounting["source_deferred"] == accounting["bench_deferred"]
        and accounting["bench_dataset_sequence"][0] == 1
        and accounting["bench_dataset_sequence"][1] == accounting["bench_dataset_sequence"][2] == accounting["bench_accepted"]
    )
    store.close()
    db_size = db_path.stat().st_size
    typer.echo(json.dumps({"accounting": accounting, "db_size_bytes": db_size, "device": device}))

    report = {
        "label": label, "source_db": str(source_db), "policy": asdict(policy), "pragmas": pragmas,
        "burst_window": [burst_start, burst_end], "source_last_order": last_order,
        "phases": phases, "accounting": accounting, "db_size_bytes": db_size, "device": device,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if output_json:
        output_json.write_text(json.dumps(report, indent=1))
    if not keep_db:
        shutil.rmtree(work)
    if not accounting["exact"]:
        raise typer.Exit(code=1)


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
