from datetime import datetime, timedelta, timezone
from decimal import Decimal

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.analysis import open_dataset_store
from dicks_laboratory.developing_profile import SliceInterval, build_developing_profile_series
from dicks_laboratory.developing_profile_plot_data import build_developing_profile_plot_data
from dicks_laboratory.live_capture import capture_es_timesales_dataset
from dicks_laboratory.sessions import AnchorKind

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
    result = capture_es_timesales_dataset(tmp_path / "plotdata.sqlite3", _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


# J. Plot-data timestamps equal DevelopingProfileSeries snapshots
def test_plot_data_timestamps_equal_series_snapshots(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    assert len(plot_data.points) == len(series.snapshots)
    for point, snapshot in zip(plot_data.points, series.snapshots):
        assert point.slice_end_utc == snapshot.slice_end_utc
        assert point.terminal_snapshot == snapshot.terminal_snapshot
    store.close()


# K / L / M / N. Exact Decimal values before any rendering conversion
def test_plot_data_vwap_poc_val_vah_are_exact_decimal(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    for point, snapshot in zip(plot_data.points, series.snapshots):
        assert point.vwap == snapshot.vwap
        assert isinstance(point.vwap, Decimal)
        assert point.poc_price == snapshot.poc_price
        assert isinstance(point.poc_price, Decimal)
        assert point.val == snapshot.val
        assert isinstance(point.val, Decimal)
        assert point.vah == snapshot.vah
        assert isinstance(point.vah, Decimal)
    store.close()


# O. Terminal snapshot marked
def test_exactly_one_terminal_point(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    terminal_points = [p for p in plot_data.points if p.terminal_snapshot]
    assert len(terminal_points) == 1
    assert terminal_points[0] is plot_data.points[-1]
    store.close()


# P. Terminal last-retained timestamp exposed
def test_terminal_last_included_trade_timestamp_exposed(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    assert plot_data.points[-1].last_included_trade_timestamp is not None
    assert plot_data.points[-1].last_included_trade_timestamp == series.snapshots[-1].last_included_trade_timestamp
    store.close()


# Q. Coverage context exposed
def test_coverage_context_exposed(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    result = capture_es_timesales_dataset(tmp_path / "cov.sqlite3", _Collector((_event(first_trade, 1),)), 60, 1000)
    store = open_dataset_store(result.database_path)
    series = build_developing_profile_series(store, result.dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    assert plot_data.coverage == series.coverage
    assert plot_data.dataset_begins_after_anchor is True
    assert plot_data.unobserved_pre_capture_interval == series.unobserved_pre_capture_interval
    store.close()


# T. Decimal-to-rendering conversion isolated -- no float type anywhere in plot data
def test_plot_data_contains_no_float_values(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    for point in plot_data.points:
        for value in (point.vwap, point.poc_price, point.val, point.vah, point.cumulative_volume):
            assert value is None or isinstance(value, Decimal)
    store.close()


# Z. 1m/5m/15m terminal equality at the plot-data adapter boundary
def test_terminal_point_identical_across_intervals(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    terminals = {}
    for interval in (SliceInterval.ONE_MINUTE, SliceInterval.FIVE_MINUTES, SliceInterval.FIFTEEN_MINUTES):
        series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=interval)
        plot_data = build_developing_profile_plot_data(series)
        terminals[interval] = plot_data.points[-1]
    reference = terminals[SliceInterval.ONE_MINUTE]
    for interval, point in terminals.items():
        assert point.vwap == reference.vwap, interval
        assert point.poc_price == reference.poc_price, interval
        assert point.val == reference.val, interval
        assert point.vah == reference.vah, interval
        assert point.cumulative_trade_count == reference.cumulative_trade_count, interval
    store.close()


def test_no_snapshots_produces_empty_points(tmp_path):
    path, dataset_id = _build(tmp_path)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.US_CASH_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    plot_data = build_developing_profile_plot_data(series)
    assert plot_data.points == ()
    store.close()
