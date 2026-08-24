from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.analysis import (
    AnchorCoverage,
    analyze_volume_profile_dataset,
    open_dataset_store,
    prepare_scoped_dataset,
)
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.developing_profile import (
    DEFAULT_SLICE_INTERVAL,
    DEVELOPING_PROFILE_SLICE_POLICY_ID,
    DEVELOPING_PROFILE_SLICE_POLICY_VERSION,
    SliceInterval,
    build_developing_profile_series,
    next_aligned_boundary_strictly_after,
)
from dicks_laboratory.live_capture import capture_es_timesales_dataset
from dicks_laboratory.sessions import AnchorKind, select_trades_from_anchor
from dicks_laboratory.value_area import DEFAULT_VALUE_AREA_FRACTION, compute_value_area
from dicks_laboratory.volume_profile import build_volume_at_price_profile, price_grid_for_instrument

_UTC = timezone.utc
_SYMBOL = "/ESU26:XCME"
_MONDAY_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=_UTC)  # trading date 2026-08-24


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


def _event(ts, index, classification="NEW", price=7694.00, size=1.0, **overrides):
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": classification,
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "price": price, "size": size, "validTick": True,
    }
    fields.update(overrides)
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


def _build_dataset(tmp_path, events, name="dataset.sqlite3"):
    result = capture_es_timesales_dataset(tmp_path / name, _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


# A. Slice-policy identity/version
def test_slice_policy_identity_and_version():
    assert DEVELOPING_PROFILE_SLICE_POLICY_ID == "DICKS_LAB_DEVELOPING_PROFILE_SLICE_POLICY"
    assert DEVELOPING_PROFILE_SLICE_POLICY_VERSION.startswith("V1_")
    assert DEFAULT_SLICE_INTERVAL is SliceInterval.FIVE_MINUTES


# B. Supported 1/5/15-minute intervals
def test_supported_intervals_have_correct_minutes():
    assert SliceInterval.ONE_MINUTE.minutes == 1
    assert SliceInterval.FIVE_MINUTES.minutes == 5
    assert SliceInterval.FIFTEEN_MINUTES.minutes == 15


# C. Unsupported interval rejected
def test_unsupported_interval_rejected():
    with pytest.raises(ValueError):
        SliceInterval("TEN_MINUTES")


# D / 47 / 48 / 49. Boundary alignment fixtures
def test_next_boundary_one_minute_alignment():
    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=_UTC)
    assert next_aligned_boundary_strictly_after(base + timedelta(seconds=30), SliceInterval.ONE_MINUTE) == base + timedelta(minutes=1)
    assert next_aligned_boundary_strictly_after(base + timedelta(minutes=1), SliceInterval.ONE_MINUTE) == base + timedelta(minutes=2)


def test_next_boundary_five_minute_alignment():
    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=_UTC)
    assert next_aligned_boundary_strictly_after(base + timedelta(minutes=1), SliceInterval.FIVE_MINUTES) == base + timedelta(minutes=5)
    assert next_aligned_boundary_strictly_after(
        base + timedelta(minutes=4, seconds=59, microseconds=999000), SliceInterval.FIVE_MINUTES
    ) == base + timedelta(minutes=5)
    assert next_aligned_boundary_strictly_after(base + timedelta(minutes=5), SliceInterval.FIVE_MINUTES) == base + timedelta(minutes=10)


def test_next_boundary_fifteen_minute_alignment():
    base = datetime(2026, 1, 1, 10, 0, 0, tzinfo=_UTC)
    assert next_aligned_boundary_strictly_after(base + timedelta(minutes=7), SliceInterval.FIFTEEN_MINUTES) == base + timedelta(minutes=15)
    assert next_aligned_boundary_strictly_after(base + timedelta(minutes=16), SliceInterval.FIFTEEN_MINUTES) == base + timedelta(minutes=30)
    assert next_aligned_boundary_strictly_after(base + timedelta(minutes=45), SliceInterval.FIFTEEN_MINUTES) == base + timedelta(hours=1)


# E / 50. Anchor before capture does not generate fake empty snapshots
def test_anchor_before_capture_produces_no_fake_empty_snapshots(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, dataset_id = _build_dataset(tmp_path, (_event(first_trade, 1),))
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    assert series.coverage is AnchorCoverage.DATASET_BEGINS_AFTER_ANCHOR
    assert len(series.snapshots) == 1
    assert series.snapshots[0].slice_end_utc == datetime(2026, 8, 23, 23, 20, 0, tzinfo=_UTC)
    assert series.snapshots[0].terminal_snapshot is True
    store.close()


# F / 51. Anchor exactly on boundary
def test_anchor_exactly_on_boundary_first_cutoff_is_next_boundary(tmp_path):
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=20)
    events = (
        _event(anchor_ts, 1, price=7694.00),
        _event(anchor_ts + timedelta(minutes=3), 2, price=7694.25),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert series.snapshots[0].slice_end_utc == anchor_ts + timedelta(minutes=5)
    store.close()


# G / H / I / 52. Trade exactly at regular cutoff excluded, included next; final-on-boundary retained
def test_trade_exactly_at_cutoff_excluded_then_included_next(tmp_path):
    anchor_ts = _MONDAY_OPEN
    boundary = anchor_ts + timedelta(minutes=5)
    events = (
        _event(anchor_ts + timedelta(minutes=1), 1, price=7694.00),
        _event(boundary, 2, price=7694.25),  # exactly on the first cutoff
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert len(series.snapshots) == 2
    assert series.snapshots[0].slice_end_utc == boundary
    assert series.snapshots[0].cumulative_trade_count == 1  # boundary trade excluded
    assert series.snapshots[1].slice_end_utc == boundary + timedelta(minutes=5)
    assert series.snapshots[1].terminal_snapshot is True
    assert series.snapshots[1].cumulative_trade_count == 2  # boundary trade now included
    store.close()


# J. Final partial interval
def test_final_partial_interval_terminal_cutoff_not_equal_to_last_trade(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    last_snapshot = series.snapshots[-1]
    assert last_snapshot.terminal_snapshot is True
    assert last_snapshot.last_included_trade_timestamp != last_snapshot.slice_end_utc
    store.close()


# K / L / 53. No-new-retained-trade slice; no gap inference
def test_no_new_retained_trade_slice_is_still_emitted(tmp_path):
    anchor_ts = _MONDAY_OPEN
    events = (
        _event(anchor_ts + timedelta(minutes=1), 1, price=7694.00),
        _event(anchor_ts + timedelta(minutes=12), 2, price=7694.25),  # nothing retained in [22:05, 22:10)
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert [s.slice_end_utc for s in series.snapshots] == [
        anchor_ts + timedelta(minutes=5), anchor_ts + timedelta(minutes=10), anchor_ts + timedelta(minutes=15),
    ]
    middle = series.snapshots[1]
    assert middle.new_trade_count == 0
    assert middle.new_volume == Decimal("0")
    assert middle.cumulative_trade_count == series.snapshots[0].cumulative_trade_count
    store.close()


# M / N / O / P / Q / R / S / T / U. Full engine-equivalence + invariants at every snapshot
def test_every_snapshot_matches_accepted_engines_and_invariants(tmp_path):
    anchor_ts = _MONDAY_OPEN
    events = (
        _event(anchor_ts + timedelta(minutes=1), 1, price=7694.00, size=2.0),
        _event(anchor_ts + timedelta(minutes=2), 2, price=7694.25, size=3.0),
        _event(anchor_ts + timedelta(minutes=6), 3, price=7694.50, size=1.0),
        _event(anchor_ts + timedelta(minutes=12), 4, price=7694.00, size=4.0),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )

    context = prepare_scoped_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, None, anchor_ts)
    selected = select_trades_from_anchor(context.scoped_effective, anchor_ts)
    grid = price_grid_for_instrument(context.instrument)

    previous_trade_count = 0
    previous_volume = Decimal("0")
    for snapshot in series.snapshots:
        prefix = tuple(t for t in selected if t.event_timestamp < snapshot.slice_end_utc)
        assert snapshot.cumulative_trade_count == len(prefix)
        assert snapshot.cumulative_trade_count >= previous_trade_count  # M

        vap = build_volume_at_price_profile(prefix, grid, VwapSourceMode.EFFECTIVE_TAPE)
        profile = vap.profile
        assert profile is not None
        assert snapshot.vwap == profile.selected_trades_vwap
        assert snapshot.profile_low == profile.lowest_price
        assert snapshot.profile_high == profile.highest_price
        assert snapshot.occupied_level_count == len(profile.levels)
        assert snapshot.poc_price == profile.point_of_control.price
        assert snapshot.poc_volume == profile.point_of_control.volume
        assert snapshot.poc_trade_count == profile.point_of_control.trade_count

        total_level_volume = sum((level.volume for level in profile.levels), Decimal("0"))
        assert total_level_volume == profile.total_volume == snapshot.cumulative_volume  # U
        assert snapshot.cumulative_volume >= previous_volume  # N
        previous_volume = snapshot.cumulative_volume
        previous_trade_count = snapshot.cumulative_trade_count

        value_area = compute_value_area(profile, DEFAULT_VALUE_AREA_FRACTION)
        assert snapshot.val == value_area.value_area_low.price
        assert snapshot.vah == value_area.value_area_high.price
        assert value_area.value_area_low.price <= value_area.point_of_control.price <= value_area.value_area_high.price  # S
        included_volume = sum((level.volume for level in value_area.included_levels), Decimal("0"))
        assert included_volume == value_area.included_volume  # T
        assert value_area.included_volume >= value_area.target_volume  # T
        assert snapshot.value_area_level_count == value_area.included_level_count
        assert snapshot.value_area_actual_fraction == value_area.included_fraction
    store.close()


# V / W. Intermediate POC migration and VAL/VAH evolution
def test_poc_and_value_area_migrate_across_snapshots(tmp_path):
    anchor_ts = _MONDAY_OPEN
    events = (
        _event(anchor_ts + timedelta(minutes=1), 1, price=7694.00, size=10.0),
        _event(anchor_ts + timedelta(minutes=6), 2, price=7695.00, size=20.0),
        _event(anchor_ts + timedelta(minutes=11), 3, price=7694.00, size=15.0),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert len(series.snapshots) == 3
    assert series.snapshots[0].poc_price == Decimal("7694.00")
    assert series.snapshots[1].poc_price == Decimal("7695.00")
    assert series.snapshots[2].poc_price == Decimal("7694.00")
    assert series.snapshots[2].terminal_snapshot is True
    # VAL/VAH move as the profile grows
    assert series.snapshots[0].val == series.snapshots[0].vah == Decimal("7694.00")
    assert series.snapshots[1].val != series.snapshots[1].vah or series.snapshots[1].vah != series.snapshots[0].vah
    store.close()


# X. POC tie policy reuse
def test_poc_tie_policy_reused_in_developing_series(tmp_path):
    anchor_ts = _MONDAY_OPEN
    events = (
        _event(anchor_ts + timedelta(minutes=1), 1, price=7694.00, size=1.0),
        _event(anchor_ts + timedelta(minutes=6), 2, price=7694.00, size=3.0),
        _event(anchor_ts + timedelta(minutes=7), 3, price=7694.50, size=4.0),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    terminal = series.snapshots[-1]
    assert terminal.terminal_snapshot is True
    assert terminal.poc_price == Decimal("7694.00")  # tied 4 vs 4; nearer-to-mean-then-lower-price policy
    store.close()


# Y. Value Area tie policy reuse
def test_value_area_tie_policy_reused_in_developing_series(tmp_path):
    anchor_ts = _MONDAY_OPEN
    prices_sizes = [
        ("99.50", "5"), ("99.75", "10"), ("100.00", "30"), ("100.25", "40"),
        ("100.50", "30"), ("100.75", "10"), ("101.00", "5"),
    ]
    events = tuple(
        _event(anchor_ts + timedelta(minutes=index), index, price=float(price), size=float(size))
        for index, (price, size) in enumerate(prices_sizes, start=1)
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    terminal = series.snapshots[-1]
    assert terminal.terminal_snapshot is True
    assert terminal.val == Decimal("100.00")
    assert terminal.vah == Decimal("100.50")
    assert terminal.value_area_level_count == 3
    store.close()


# Z / 57. Invalid tick anomaly propagation
def test_invalid_tick_trade_propagates_across_snapshots(tmp_path):
    anchor_ts = _MONDAY_OPEN
    events = (
        _event(anchor_ts + timedelta(minutes=1), 1, price=7694.10),  # off-grid
        _event(anchor_ts + timedelta(minutes=6), 2, price=7694.25),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert series.snapshots[0].invalid_tick_trade_count == 1
    assert series.snapshots[0].profile_low is None  # no on-grid trades yet
    assert series.snapshots[1].invalid_tick_trade_count == 1  # still present in the cumulative prefix
    assert series.snapshots[1].profile_low == Decimal("7694.25")
    store.close()


# AA. Anchor after dataset gives no snapshots
def test_anchor_after_dataset_end_gives_no_snapshots(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.US_CASH_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    assert series.coverage is AnchorCoverage.ANCHOR_AFTER_DATASET_END
    assert series.snapshots == ()
    store.close()


# AB. Custom anchor excludes earlier observations
def test_custom_anchor_excludes_earlier_observations(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=8), 2, price=7694.25),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=5)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert series.snapshots[-1].cumulative_trade_count == 1
    store.close()


# AC. Final snapshot equals static 0Q analysis
def test_final_snapshot_equals_static_0q_analysis(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=2.0),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 2, price=7694.25, size=3.0),
        _event(_MONDAY_OPEN + timedelta(minutes=12), 3, price=7694.50, size=1.0),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    static_result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    terminal = series.snapshots[-1]
    assert terminal.terminal_snapshot is True
    assert terminal.cumulative_trade_count == static_result.selected_trade_count
    assert terminal.cumulative_volume == static_result.selected_volume
    assert terminal.vwap == static_result.vwap
    assert terminal.profile_low == static_result.profile.lowest_price
    assert terminal.profile_high == static_result.profile.highest_price
    assert terminal.occupied_level_count == len(static_result.profile.levels)
    assert terminal.poc_price == static_result.profile.point_of_control.price
    assert terminal.poc_volume == static_result.profile.point_of_control.volume
    assert terminal.poc_trade_count == static_result.profile.point_of_control.trade_count
    assert terminal.val == static_result.value_area.value_area_low.price
    assert terminal.vah == static_result.value_area.value_area_high.price
    assert terminal.value_area_level_count == static_result.value_area.included_level_count
    store.close()


# AD. Canonical source-mode support
def test_canonical_source_mode_supported(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 2, price=7694.25),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES, source_mode=VwapSourceMode.CANONICAL_NEW_ONLY
    )
    assert series.source_mode is VwapSourceMode.CANONICAL_NEW_ONLY
    assert series.snapshots[-1].cumulative_trade_count == 2
    store.close()


# AE. Effective source-mode support
def test_effective_source_mode_supported(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 2, price=7694.25),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    assert series.source_mode is VwapSourceMode.EFFECTIVE_TAPE
    store.close()


# AF. Correction/cancel semantics explicitly tested
def test_canonical_and_effective_series_diverge_under_correction(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 11, price=7696.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, "CORRECTION", price=7700.00, size=1.0),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    effective_series = build_developing_profile_series(
        store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES, source_mode=VwapSourceMode.EFFECTIVE_TAPE
    )
    canonical_series = build_developing_profile_series(
        store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES, source_mode=VwapSourceMode.CANONICAL_NEW_ONLY
    )
    assert effective_series.applied_correction_count == 1
    assert effective_series.snapshots[-1].poc_price != canonical_series.snapshots[-1].poc_price
    store.close()


def test_canonical_and_effective_series_diverge_under_cancel(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 11, price=7696.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 11, "CANCEL"),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    effective_series = build_developing_profile_series(
        store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES, source_mode=VwapSourceMode.EFFECTIVE_TAPE
    )
    canonical_series = build_developing_profile_series(
        store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES, source_mode=VwapSourceMode.CANONICAL_NEW_ONLY
    )
    assert effective_series.applied_cancel_count == 1
    assert effective_series.snapshots[-1].cumulative_trade_count == 1
    assert canonical_series.snapshots[-1].cumulative_trade_count == 2
    store.close()


# AG. Deterministic repeated execution
def test_repeated_execution_is_deterministic(tmp_path):
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=2.0),
        _event(_MONDAY_OPEN + timedelta(minutes=6), 2, price=7694.25, size=3.0),
        _event(_MONDAY_OPEN + timedelta(minutes=12), 3, price=7694.50, size=1.0),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    first = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    second = build_developing_profile_series(store, dataset_id, AnchorKind.SESSION_OPEN, slice_interval=SliceInterval.FIVE_MINUTES)
    assert first == second
    store.close()


# 24. Trade exactly at anchor is included
def test_trade_exactly_at_anchor_included(tmp_path):
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=5)
    events = (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(anchor_ts, 2, price=7694.25),
    )
    path, dataset_id = _build_dataset(tmp_path, events)
    store = open_dataset_store(path)
    series = build_developing_profile_series(
        store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts, slice_interval=SliceInterval.FIVE_MINUTES
    )
    assert series.snapshots[-1].cumulative_trade_count == 1
    store.close()
