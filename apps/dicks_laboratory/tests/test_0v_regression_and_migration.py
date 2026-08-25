"""Phase 0V regression suite: proves the real accepted 0L dataset's analytics
are unchanged after the 0V schema widening, and proves old-schema databases
remain readable without fabricating any newly-introduced field.

This is deliberately separate from `test_long_running_capture.py` (which
covers the new serious-collector orchestration) -- this file only proves
backward compatibility and non-regression of everything that came before 0V.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from K9.tastytrade.dxlink import DxLinkSourceEvent
from dicks_laboratory.analysis import analyze_volume_profile_dataset, open_dataset_store, resolve_dataset_id
from dicks_laboratory.dxlink_timesales import DxLinkTimeAndSaleProvenance
from dicks_laboratory.effective_tape import reconstruct_effective_tape
from dicks_laboratory.live_capture import capture_es_timesales_dataset
from dicks_laboratory.sessions import AnchorKind
from dicks_laboratory.store import LaboratoryStore

_REAL_DATASET = Path("apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3")
_SYMBOL = "/ESU26:XCME"
_UTC = timezone.utc


# Z. Real 0L regression -- exact accepted 0Q/0R/0S/0T values must not move.
@pytest.mark.skipif(not _REAL_DATASET.exists(), reason="Real 0L runtime dataset not present in this environment.")
def test_real_0l_dataset_analytics_unchanged_after_0v_schema_widening():
    mtime_before = _REAL_DATASET.stat().st_mtime_ns
    size_before = _REAL_DATASET.stat().st_size

    store = open_dataset_store(_REAL_DATASET)
    dataset_id = resolve_dataset_id(store, None)
    result = analyze_volume_profile_dataset(store, dataset_id, AnchorKind.SESSION_OPEN)
    store.close()

    assert _REAL_DATASET.stat().st_mtime_ns == mtime_before  # read-only: file genuinely untouched
    assert _REAL_DATASET.stat().st_size == size_before

    assert result.selected_trade_count == 1182
    assert result.selected_volume == Decimal("1426.0")
    assert result.vwap == Decimal("7693.867286115007012622720898")
    assert result.profile.lowest_price == Decimal("7690.75")
    assert result.profile.highest_price == Decimal("7697.00")
    assert len(result.profile.levels) == 26
    assert result.profile.point_of_control.price == Decimal("7695.00")
    assert result.profile.point_of_control.volume == Decimal("273.0")
    assert result.value_area.value_area_low.price == Decimal("7692.25")
    assert result.value_area.value_area_high.price == Decimal("7696.75")
    assert result.value_area.included_level_count == 19


# Y. Old-database migration: absent 0V columns load as None, never fabricated;
# a writable copy migrates additively without destroying existing rows.
@pytest.mark.skipif(not _REAL_DATASET.exists(), reason="Real 0L runtime dataset not present in this environment.")
def test_old_database_optional_fields_load_as_none_read_only(tmp_path):
    store = LaboratoryStore(_REAL_DATASET, read_only=True)
    dataset_id = store.list_dataset_ids()[0]
    provenance = store.load_dxlink_time_and_sale_provenance(dataset_id)
    assert len(provenance) == 1182
    for item in provenance:
        assert isinstance(item, DxLinkTimeAndSaleProvenance)
        # These fields did not exist when this dataset was captured -- they
        # must load as None (unavailable), never as fabricated zeros/False.
        assert item.bid_price is None
        assert item.ask_price is None
        assert item.aggressor_side is None
        assert item.exchange_code is None
        assert item.event_flags is None
        assert item.spread_leg is None
        assert item.extended_trading_hours is None
        assert item.valid_tick is None
    trading_date, instrument = store.load_dataset_trading_context(dataset_id)
    assert trading_date is None  # not tracked at capture time
    assert instrument is None
    assert store.load_dataset_lifecycle_state(dataset_id) is None  # untracked, not fabricated OPEN
    store.close()


def test_writable_migration_preserves_existing_rows_exactly(tmp_path):
    """Simulates opening an old-schema-shaped database for writing: existing
    canonical rows must survive additive migration byte-for-byte in value."""
    import shutil

    if not _REAL_DATASET.exists():
        pytest.skip("Real 0L runtime dataset not present in this environment.")
    copy_path = tmp_path / "migrated_copy.sqlite3"
    shutil.copy2(_REAL_DATASET, copy_path)

    before_store = LaboratoryStore(copy_path, read_only=True)
    dataset_id = before_store.list_dataset_ids()[0]
    trades_before = before_store.load_trade_observations(dataset_id)
    before_store.close()

    # Opening read-write triggers `_apply_additive_migrations()`.
    after_store = LaboratoryStore(copy_path)
    trades_after = after_store.load_trade_observations(dataset_id)
    assert trades_after == trades_before
    # New optional provenance columns now exist but are None for pre-existing rows.
    provenance = after_store.load_dxlink_time_and_sale_provenance(dataset_id)
    assert len(provenance) == len(trades_before)
    assert all(p.bid_price is None for p in provenance)
    after_store.close()


# AA. Effective-tape regression: new provenance fields must not alter lifecycle semantics.
def test_effective_tape_correction_and_cancel_semantics_unchanged(tmp_path):
    dataset_started = datetime(2026, 8, 23, 22, 0, tzinfo=_UTC)

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

    def _event(ts, index, classification="NEW", price=100.0, size=1.0):
        fields = {
            "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": classification,
            "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
            "price": price, "size": size, "validTick": True,
        }
        return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)

    events = (
        _event(dataset_started + timedelta(minutes=1), 10, price=100),
        _event(dataset_started + timedelta(minutes=2), 11, price=102),
        _event(dataset_started + timedelta(minutes=1), 10, "CORRECTION", price=104),
        _event(dataset_started + timedelta(minutes=3), 12, price=105),
        _event(dataset_started + timedelta(minutes=3), 12, "CANCEL"),
    )
    result = capture_es_timesales_dataset(tmp_path / "tape.sqlite3", _Collector(events), 60, 1000)
    store = LaboratoryStore(result.database_path, read_only=True)
    dataset_id = store.list_dataset_ids()[0]
    trades = store.load_trade_observations(dataset_id)
    provenance = store.load_dxlink_time_and_sale_provenance(dataset_id)
    deferred = store.load_deferred_dxlink_time_and_sales(dataset_id)
    tape = reconstruct_effective_tape(trades, provenance, deferred)
    store.close()

    assert len(trades) == 3  # two NEW + one NEW that gets canceled, all durably retained
    effective_prices = sorted(t.price for t in tape.effective_trades)
    assert effective_prices == [Decimal("102"), Decimal("104")]  # corrected 100->104; 105 canceled
    assert tape.applied_correction_count == 1
    assert tape.applied_cancel_count == 1
    # New provenance fields exist and are populated for this synthetic capture (all fields supplied).
    assert all(p.event_classification == "NEW" for p in provenance)
