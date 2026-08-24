import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.analysis import (
    AmbiguousDatasetError,
    AmbiguousTradingDateError,
    AnchorCoverage,
    LaboratoryAnalysisError,
    analyze_anchored_vwap_dataset,
    determine_dataset_trading_dates,
    open_dataset_store,
    resolve_dataset_id,
)
from dicks_laboratory.live_capture import capture_es_timesales_dataset
from dicks_laboratory.sessions import AnchorKind
from dicks_laboratory.store import LaboratoryStore

_SYMBOL = "/ESU26:XCME"
_MONDAY_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=timezone.utc)  # trading date 2026-08-24
_TUESDAY_OPEN = datetime(2026, 8, 24, 22, 0, tzinfo=timezone.utc)  # trading date 2026-08-25


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
        "price": 100.0, "size": 1.0, "validTick": True,
    }
    fields.update(overrides)
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


def _build_dataset(tmp_path, events, name="dataset.sqlite3"):
    result = capture_es_timesales_dataset(tmp_path / name, _Collector(events), 60, 1000)
    return result.database_path, result.dataset_id


def test_dataset_path_not_found(tmp_path):
    with pytest.raises(LaboratoryAnalysisError):
        open_dataset_store(tmp_path / "missing.sqlite3")


def test_unreadable_non_sqlite_file_is_rejected(tmp_path):
    path = tmp_path / "garbage.sqlite3"
    path.write_bytes(b"not a real sqlite database at all")
    with pytest.raises(LaboratoryAnalysisError):
        open_dataset_store(path)


def test_empty_laboratory_schema_with_no_dataset(tmp_path):
    path = tmp_path / "empty.sqlite3"
    LaboratoryStore(path).close()
    store = open_dataset_store(path)
    with pytest.raises(LaboratoryAnalysisError):
        resolve_dataset_id(store, None)
    store.close()


def test_ambiguous_dataset_requires_explicit_selection(tmp_path):
    path, dataset_a = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    _, dataset_b = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=2), 2),), name="dataset.sqlite3")
    store = open_dataset_store(path)
    with pytest.raises(AmbiguousDatasetError):
        resolve_dataset_id(store, None)
    assert resolve_dataset_id(store, dataset_a) == dataset_a
    assert resolve_dataset_id(store, dataset_b) == dataset_b
    store.close()


def test_single_trading_date_auto_selection(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=102),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.trading_date == date(2026, 8, 24)
    store.close()


def test_multiple_trading_dates_require_explicit_selection(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1),
        _event(_TUESDAY_OPEN + timedelta(minutes=1), 2),
    ))
    store = open_dataset_store(path)
    trades = store.load_trade_observations(dataset_id)
    assert determine_dataset_trading_dates(trades) == (date(2026, 8, 24), date(2026, 8, 25))
    with pytest.raises(AmbiguousTradingDateError):
        analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN, trading_date=date(2026, 8, 25))
    assert result.trading_date == date(2026, 8, 25)
    store.close()


def test_session_open_anchor_resolution(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.anchor_timestamp_utc == _MONDAY_OPEN
    assert result.session_definition_id == "CME_EQUITY_INDEX_GLOBEX"
    store.close()


def test_cash_open_anchor_resolution(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.US_CASH_OPEN)
    assert result.anchor_timestamp_utc == datetime(2026, 8, 24, 13, 30, tzinfo=timezone.utc)
    assert result.session_definition_id == "US_CASH_SESSION"
    store.close()


def test_custom_utc_anchor_accepted(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=1)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts)
    assert result.anchor_timestamp_utc == anchor_ts
    assert result.session_definition_id is None
    store.close()


def test_anchor_before_first_retained_trade_is_not_shifted(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, dataset_id = _build_dataset(tmp_path, (_event(first_trade, 1),))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.anchor_timestamp_utc == _MONDAY_OPEN
    assert result.dataset_first_trade_timestamp == first_trade
    assert result.coverage is AnchorCoverage.DATASET_BEGINS_AFTER_ANCHOR
    assert result.dataset_begins_after_anchor is True
    store.close()


def test_missing_pre_capture_interval_calculation(tmp_path):
    first_trade = _MONDAY_OPEN + timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    path, dataset_id = _build_dataset(tmp_path, (_event(first_trade, 1),))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.unobserved_pre_capture_interval == timedelta(hours=1, minutes=16, seconds=3, milliseconds=749)
    store.close()


def test_anchor_inside_dataset_selects_subset(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=5), 2, price=102),
        _event(_MONDAY_OPEN + timedelta(minutes=10), 3, price=104),
    ))
    store = open_dataset_store(path)
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=5)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts)
    assert result.first_included_trade_timestamp == anchor_ts
    assert result.canonical_included_trade_count == 2
    assert result.coverage is AnchorCoverage.ANCHOR_COVERED
    store.close()


def test_trade_exactly_on_anchor_is_included(tmp_path):
    anchor_ts = _MONDAY_OPEN + timedelta(minutes=5)
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1),
        _event(anchor_ts, 2),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.CUSTOM_TIMESTAMP, custom_timestamp=anchor_ts)
    assert result.canonical_included_trade_count == 1
    assert result.first_included_trade_timestamp == anchor_ts
    store.close()


def test_anchor_after_last_retained_trade_produces_no_vwap(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.US_CASH_OPEN)
    assert result.coverage is AnchorCoverage.ANCHOR_AFTER_DATASET_END
    assert result.canonical_vwap is None
    assert result.effective_vwap is None
    assert result.canonical_included_trade_count == 0
    store.close()


def test_session_end_coverage_reported(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.session_end_utc == datetime(2026, 8, 24, 21, 0, tzinfo=timezone.utc)
    assert result.dataset_ends_before_session_end is True
    store.close()


def test_canonical_new_only_result(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 2, price=102),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.canonical_included_trade_count == 2
    assert result.canonical_vwap == Decimal("101")
    store.close()


def test_correction_aware_effective_result_differs_from_canonical(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 11, price=102),
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, "CORRECTION", price=104),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.applied_correction_count == 1
    assert result.canonical_vwap == Decimal("101")
    assert result.effective_vwap == Decimal("103")
    store.close()


def test_cancel_aware_effective_result_differs_from_canonical(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 11, price=102),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 11, "CANCEL"),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.applied_cancel_count == 1
    assert result.canonical_vwap == Decimal("101")
    assert result.effective_vwap == Decimal("100")
    assert result.effective_included_trade_count == 1
    store.close()


def test_reconstruction_anomaly_surfaced(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 10, price=100),
        _event(_MONDAY_OPEN + timedelta(minutes=2), 99, "CORRECTION", price=104),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert result.reconstruction_anomaly_count == 1
    assert result.reconstruction_anomaly_counts_by_reason == (("TARGET_SOURCE_EVENT_NOT_FOUND", 1),)
    store.close()


def test_exact_decimal_values_preserved(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (
        _event(_MONDAY_OPEN + timedelta(minutes=1), 1, price="7693.867286115007012622720898", size=1),
    ))
    store = open_dataset_store(path)
    result = analyze_anchored_vwap_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    assert isinstance(result.canonical_vwap, Decimal)
    assert result.canonical_vwap == Decimal("7693.867286115007012622720898")
    store.close()


def test_read_only_store_rejects_writes(tmp_path):
    path, dataset_id = _build_dataset(tmp_path, (_event(_MONDAY_OPEN + timedelta(minutes=1), 1),))
    store = LaboratoryStore(path, read_only=True)
    with pytest.raises(sqlite3.OperationalError):
        store._connection.execute("DELETE FROM trade_observations")
    store.close()


def test_analysis_does_not_import_network_client_modules():
    import dicks_laboratory.analysis as analysis_module
    with open(analysis_module.__file__) as handle:
        text = handle.read().lower()
    assert "tastytrade" not in text
    assert "import k9" not in text
