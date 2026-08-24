import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.analysis import open_dataset_store
from dicks_laboratory.developing_profile import SliceInterval, build_developing_profile_series
from dicks_laboratory.live_capture import capture_es_timesales_dataset
from dicks_laboratory.sessions import AnchorKind

_SCRIPT_PATH = Path(__file__).resolve().parents[3] / "scripts" / "dicks_lab_analyze_developing_profile.py"
_spec = importlib.util.spec_from_file_location("dicks_lab_analyze_developing_profile", _SCRIPT_PATH)
_module = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _module
_spec.loader.exec_module(_module)

_SYMBOL = "/ESU26:XCME"
_MONDAY_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)


class _Collector:
    def __init__(self, events):
        self.events = events

    def collect(self, _symbol, _types, _duration, max_events, on_event=None, on_connected=None, retain_events=True):
        if on_connected:
            on_connected()
        for event in self.events[:max_events]:
            if on_event:
                on_event(event)
        return self.events if retain_events else ()


def _event(ts, index, price=7694.00, size=1.0):
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": "NEW",
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "price": price, "size": size, "validTick": True,
    }
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


def _build(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=2.0),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 2, price=7694.25, size=3.0),
        _event(_MONDAY_OPEN + timedelta(minutes=12), 3, price=7694.50, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=18), 4, price=7694.00, size=4.0),
    )
    result = capture_es_timesales_dataset(tmp_path / "render.sqlite3", _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


# 43. Prove CLI rows correspond exactly to the underlying snapshots -- no separate calculation.
def test_rendered_table_rows_match_series_snapshots_exactly(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    table_lines = _module._render_table(series)
    data_rows = table_lines[1:-1]  # skip header and footnote line
    assert len(data_rows) == len(series.snapshots)
    for row, snapshot in zip(data_rows, series.snapshots):
        assert str(snapshot.new_trade_count) in row
        assert str(snapshot.cumulative_trade_count) in row
        assert str(snapshot.poc_price) in row
        assert str(snapshot.val) in row
        assert str(snapshot.vah) in row
        if snapshot.terminal_snapshot:
            assert "*" in row
    store.close()


def test_report_terminal_summary_matches_final_snapshot(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    report = _module._render_report(series)
    terminal = series.snapshots[-1]
    assert f"Trades: {terminal.cumulative_trade_count:,}" in report
    assert str(terminal.vwap) in report
    assert str(terminal.poc_price) in report
    assert str(terminal.val) in report
    assert str(terminal.vah) in report
    store.close()


# 25 / 44. Cross-interval terminal equality
def test_terminal_state_identical_across_intervals(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    terminals = {}
    for interval in (SliceInterval.ONE_MINUTE, SliceInterval.FIVE_MINUTES, SliceInterval.FIFTEEN_MINUTES):
        series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=interval)
        terminals[interval] = series.snapshots[-1]
    reference = terminals[SliceInterval.ONE_MINUTE]
    for interval, snapshot in terminals.items():
        assert snapshot.cumulative_trade_count == reference.cumulative_trade_count, interval
        assert snapshot.cumulative_volume == reference.cumulative_volume, interval
        assert snapshot.vwap == reference.vwap, interval
        assert snapshot.poc_price == reference.poc_price, interval
        assert snapshot.val == reference.val, interval
        assert snapshot.vah == reference.vah, interval
    store.close()


def test_intermediate_checkpoints_differ_across_intervals(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    five = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    fifteen = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIFTEEN_MINUTES)
    assert len(five.snapshots) != len(fifteen.snapshots) or [s.slice_end_utc for s in five.snapshots] != [
        s.slice_end_utc for s in fifteen.snapshots
    ]
    store.close()
