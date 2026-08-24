from datetime import datetime, timedelta, timezone
from decimal import Decimal

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.analysis import (
    AnchorCoverage,
    analyze_volume_profile_dataset,
    open_dataset_store,
)
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.live_capture import capture_es_timesales_dataset
from dicks_laboratory.sessions import AnchorKind
from dicks_laboratory.value_area import VALUE_AREA_POLICY_ID
from dicks_laboratory.volume_profile import POC_TIE_POLICY_ID

_SYMBOL = "/ESU26:XCME"
_MONDAY_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)  # trading date 2026-08-24


class _Collector:
    def __init__(self, events: tuple[DxLinkSourceEvent, ...]):
        self.events = events

    def collect(self, _symbol, _types, _duration, max_events, on_event=None, on_connected=None, retain_events=True):
        if on_connected:
            on_connected()
        for event in self.events[:max_events]:
            if on_event:
                on_event(event)
        return self.events if retain_events else ()


def _event(ts: datetime, index: int, classification: str = "NEW", **overrides: object) -> DxLinkSourceEvent:
    fields: dict[str, object] = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": classification,
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "price": 7694.00, "size": 1.0, "validTick": True,
    }
    fields.update(overrides)
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


def _build_dataset(tmp_path, events, name="dataset.sqlite3"):
    result = capture_es_timesales_dataset(tmp_path / name, _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


# A. session-open path
def test_session_open_path_produces_full_profile(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25),
        _event(_MONDAY_OPEN + timedelta(minutes=3), 3, price=7694.00),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.profile is not None
    assert result.selected_trade_count == 3
    store.close()


# B. cash-open no-result
def test_cash_open_no_result(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.US_CASH_OPEN)
    assert result.coverage is AnchorCoverage.ANCHOR_AFTER_DATASET_END
    assert result.profile is None
    assert result.value_area is None
    assert result.vwap is None
    assert result.selected_trade_count == 0
    store.close()


# C. custom anchor
def test_custom_anchor_path(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=5), 2, price=7694.25),
    ))
    store = open_dataset_store(path)
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=5)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts)
    assert result.selected_trade_count == 1
    store.close()


# D. requested anchor preserved exactly
def test_requested_anchor_preserved_exactly(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=1)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts)
    assert result.anchor_timestamp_utc == anchor_ts
    store.close()


# E. dataset begins after anchor
def test_dataset_begins_after_anchor_not_shifted(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, dataset_id = _build_dataset(tmp_path, (_event(first_trade, 1),))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.anchor_timestamp_utc == _MONDAY_OPEN
    assert result.coverage is AnchorCoverage.DATASET_BEGINS_AFTER_ANCHOR
    assert result.dataset_begins_after_anchor is True
    assert result.profile is not None
    store.close()


# F. unobserved pre-capture interval
def test_unobserved_pre_capture_interval(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, dataset_id = _build_dataset(tmp_path, (_event(first_trade, 1),))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.unobserved_pre_capture_interval == timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    store.close()


# G. dataset ends before session end
def test_dataset_ends_before_session_end(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.dataset_ends_before_session_end is True
    assert result.session_end_utc == datetime(2026, 8, 24, 21, 0, tzinfo=timezone.utc)
    store.close()


# H. selected trade count/volume
def test_selected_trade_count_and_volume(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=2.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25, size=3.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.selected_trade_count == 2
    assert result.selected_volume == Decimal("5")
    store.close()


# I. VWAP matches selected trades
def test_vwap_matches_selected_trades(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7696.00, size=1.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.vwap == Decimal("7695")
    store.close()


# J. Volume Profile matches selected trades / K. Volume conservation
def test_volume_profile_conserves_selected_volume(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=2.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25, size=3.0),
        _event(_MONDAY_OPEN + timedelta(minutes=3), 3, price=7694.25, size=1.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    total_level_volume = sum((level.volume for level in result.profile.levels), Decimal("0"))
    assert total_level_volume == result.profile.total_volume == Decimal("6")
    store.close()


# L / M. POC price/volume/trade_count
def test_poc_price_volume_trade_count(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25, size=5.0),
        _event(_MONDAY_OPEN + timedelta(minutes=3), 3, price=7694.25, size=5.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.profile.point_of_control.price == Decimal("7694.25")
    assert result.profile.point_of_control.volume == Decimal("10")
    assert result.profile.point_of_control.trade_count == 2
    assert result.profile.poc_policy_id == POC_TIE_POLICY_ID
    store.close()


# N / O / P. Value Area target, VAL/VAH, achieved fraction
def test_value_area_target_val_vah_and_fraction(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=5.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25, size=50.0),
        _event(_MONDAY_OPEN + timedelta(minutes=3), 3, price=7694.50, size=5.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    va = result.value_area
    assert va.target_fraction == Decimal("0.70")
    assert va.value_area_low.price <= va.point_of_control.price <= va.value_area_high.price
    assert va.included_volume >= va.target_volume
    assert va.included_volume == sum((level.volume for level in va.included_levels), Decimal("0"))
    assert va.value_area_policy_id == VALUE_AREA_POLICY_ID
    store.close()


# Q. top-N ranking determinism is verified at the CLI layer (rendering), profile levels are deterministic here
def test_profile_levels_are_deterministic_ascending_price_order(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.50, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=3), 3, price=7694.25, size=1.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    prices = [level.price for level in result.profile.levels]
    assert prices == sorted(prices)
    store.close()


# R. Canonical/effective equivalence when no lifecycle changes
def test_canonical_and_effective_agree_without_lifecycle_events(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25, size=1.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.differs_from_canonical is False
    assert result.canonical_vwap == result.vwap
    assert result.canonical_selected_trade_count == result.selected_trade_count
    store.close()


# S. Canonical/effective divergence under correction
def test_canonical_and_effective_diverge_under_correction(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 11, price=7696.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, "CORRECTION", price=7700.00, size=1.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.differs_from_canonical is True
    assert result.applied_correction_count == 1
    assert result.profile.point_of_control.price != result.canonical_profile.point_of_control.price
    store.close()


# T. Canonical/effective divergence under cancel
def test_canonical_and_effective_diverge_under_cancel(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=7694.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 11, price=7696.00, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 11, "CANCEL"),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.applied_cancel_count == 1
    assert result.selected_trade_count == 1
    assert result.canonical_selected_trade_count == 2
    assert result.differs_from_canonical is True
    store.close()


# U. Effective reconstruction anomaly surfaced
def test_reconstruction_anomaly_surfaced(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=7694.00),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 99, "CORRECTION", price=7700.00),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.reconstruction_anomaly_count == 1
    assert result.reconstruction_anomaly_counts_by_reason == (("TARGET_SOURCE_EVENT_NOT_FOUND", 1),)
    store.close()


# V. Invalid tick-grid trade surfaced
def test_invalid_tick_grid_trade_surfaced(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.10, size=1.0),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=7694.25, size=1.0),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.invalid_tick_trade_count == 1
    assert result.profile is not None
    store.close()


# W. Anchor after data produces no analytical values
def test_anchor_after_dataset_end_produces_no_values(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.US_CASH_OPEN)
    assert result.profile is None
    assert result.value_area is None
    assert result.vwap is None
    assert result.selected_volume is None
    store.close()


# X. Read-only DB mtime unchanged
def test_read_only_analysis_does_not_modify_database(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    mtime_before = path.stat().st_mtime_ns
    store = open_dataset_store(path)
    analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    store.close()
    assert path.stat().st_mtime_ns == mtime_before


# Y. Works without network credentials (module-level import guarantee)
def test_analysis_module_does_not_require_tastytrade_credentials():
    import dicks_laboratory.analysis as analysis_module
    with open(analysis_module.__file__) as handle:
        text = handle.read().lower()
    assert "tastytrade" not in text


def test_trade_exactly_on_anchor_is_included(tmp_path):
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=5)
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),
        _event(anchor_ts, 2, price=7694.25),
    ))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts)
    assert result.selected_trade_count == 1
    assert result.first_included_trade_timestamp == anchor_ts
    store.close()


def test_value_area_and_poc_use_accepted_source_mode_metadata(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=7694.00),))
    store = open_dataset_store(path)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.source_mode is VwapSourceMode.EFFECTIVE_TAPE
    assert result.profile.source_mode is VwapSourceMode.EFFECTIVE_TAPE
    assert result.value_area.source_mode is VwapSourceMode.EFFECTIVE_TAPE
    store.close()
