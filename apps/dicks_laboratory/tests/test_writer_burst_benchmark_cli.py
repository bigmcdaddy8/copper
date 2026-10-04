"""Smoke tests for the 0W-5A offline writer burst benchmark (scripts/dicks_lab_writer_burst_benchmark.py)."""
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.durable_writer import DurableWriter
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore

_SCRIPT = "scripts/dicks_lab_writer_burst_benchmark.py"
_SYMBOL = "/ESZ26:XCME"
_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12)
_T0 = datetime(2026, 9, 29, 22, 0, tzinfo=timezone.utc)


def _event(i: int, classification: str = "NEW", valid: bool = True) -> DxLinkSourceEvent:
    moment = _T0 + timedelta(seconds=i)
    return DxLinkSourceEvent(
        "TimeAndSale",
        _SYMBOL,
        {
            "eventSymbol": _SYMBOL, "time": int(moment.timestamp() * 1000), "type": classification,
            "index": i, "sequence": i, "tradeId": i, "eventFlags": 0, "exchangeCode": "Q",
            "price": 7700.0 + (i % 4) * 0.25, "size": 1.0, "bidPrice": 7699.75, "askPrice": 7700.25,
            "exchangeSaleConditions": "@", "tradeThroughExempt": "0", "aggressorSide": "BUY",
            "spreadLeg": False, "extendedTradingHours": False, "validTick": valid,
        },
        moment,
    )


def _build_source(tmp_path: Path, count: int = 600) -> Path:
    path = tmp_path / "source.sqlite3"
    store = LaboratoryStore(path, check_same_thread=False)
    dataset_id = uuid4()
    store.save_dataset(
        DatasetIdentity(
            dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label="fixture",
            source_locator=f"TASTYTRADE_DXLINK:{_SYMBOL}:TimeAndSale", source_timezone="UTC epoch milliseconds",
            normalizer_version="t", capture_started_at=_T0, origin=DatasetOrigin.AUTHENTIC_SOURCE,
        )
    )
    store.save_dataset_trading_context(dataset_id, (_T0 + timedelta(days=1)).date(), _INSTRUMENT)
    writer = DurableWriter(store, dataset_id, _INSTRUMENT, _SYMBOL, start_dataset_sequence=1, seen_new_source_indices=set())
    writer.start()
    for i in range(1, count + 1):
        if i == 100:
            event = _event(i, valid=False)  # INVALID_DXLINK_TICK rejection
        elif i == 400:
            event = _event(i, classification="CANCEL")  # deferred
        else:
            event = _event(i)
        writer.submit_event(i, event)
    writer.drain_and_stop()
    store.close()
    return path


def _run(*args: str) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
    return subprocess.run([sys.executable, _SCRIPT, *args], capture_output=True, text=True, env=env)


def _iso(seconds: int) -> str:
    return (_T0 + timedelta(seconds=seconds)).isoformat().replace("+00:00", "Z")


def test_benchmark_replays_real_writer_with_exact_accounting_and_leaves_source_untouched(tmp_path):
    source = _build_source(tmp_path)
    before = source.read_bytes()
    report = tmp_path / "report.json"
    result = _run(
        "run", str(source), "--scratch-dir", str(tmp_path / "scratch"),
        "--burst-start", _iso(300), "--burst-end", _iso(500), "--label", "smoke", "--output-json", str(report),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(report.read_text())
    assert [phase["phase"] for phase in data["phases"]] == ["prefill", "burst"]
    assert data["phases"][0]["events"] == 299 and data["phases"][1]["events"] == 200
    accounting = data["accounting"]
    assert accounting["exact"] is True
    assert (accounting["bench_accepted"], accounting["bench_rejected"], accounting["bench_deferred"]) == (497, 1, 1)
    assert accounting["bench_journal_mode"] == "delete" and accounting["bench_quick_check"] == "ok"
    assert source.read_bytes() == before
    assert not list((tmp_path / "scratch").iterdir())  # disposable DB removed


def test_live_burst_replay_reports_queue_peak_and_lag(tmp_path):
    source = _build_source(tmp_path, count=50)
    result = _run(
        "live-burst-replay", str(source), "--window-start", _iso(0), "--window-end", _iso(100),
        "--burst-start", _iso(10), "--burst-end", _iso(20), "--rate", "0.5", "--rate", "1000", "--scale", "2",
    )
    assert result.returncode == 0, result.stderr
    rows = [json.loads(line) for line in result.stdout.splitlines()]
    slow, fast = rows
    assert slow["events_in_window"] == fast["events_in_window"] == 60  # 10 in-window events doubled
    assert slow["queue_peak"] > fast["queue_peak"] and slow["max_persist_lag_seconds"] > fast["max_persist_lag_seconds"]


def test_fifo_model_reproduces_simple_backlog_arithmetic():
    spec = importlib.util.spec_from_file_location("dicks_lab_writer_burst_benchmark", _SCRIPT)
    bench = importlib.util.module_from_spec(spec)
    sys.modules["dicks_lab_writer_burst_benchmark"] = bench
    spec.loader.exec_module(bench)
    arrivals = [0.0] * 100  # 100 events at once, drained at 10/s in batches of 10
    queue_peak, lag = bench.fifo_replay(arrivals, 10.0, 10)
    assert queue_peak == 100 and abs(lag - 10.0) < 1e-9
    assert bench.scaled_arrivals([0.0, 1.0, 5.0], (0.5, 2.0), 1.5) == [0.0, 1.0, 5.0]
    assert bench.scaled_arrivals([1.0, 1.1], (0.5, 2.0), 1.5) == [1.0, 1.1, 1.1]
