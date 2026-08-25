from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from K9.tastytrade.dxlink import DxLinkError, DxLinkSourceEvent
from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.long_running_capture import (
    InstrumentCaptureSpec,
    LongHorizonCaptureError,
    ReconnectPolicy,
    _session_close_for,
    compute_sha256,
    dataset_filename,
    find_stale_open_datasets,
    next_session_open_after,
    resolve_current_trading_date,
    run_long_horizon_capture,
    verify_checksum,
)
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore

_UTC = timezone.utc
_SYMBOL = "/ESU26:XCME"
_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)
_SPEC = InstrumentCaptureSpec(instrument=_INSTRUMENT, streamer_symbol=_SYMBOL)

# 2026-08-24 is a Monday trading date; session opens 2026-08-23 22:00 UTC (17:00 CT Sunday).
_SESSION_OPEN = datetime(2026, 8, 23, 22, 0, tzinfo=_UTC)


def _event(ts: datetime, index: int, classification: str = "NEW", price: float = 7694.00, size: float = 1.0):
    fields = {
        "eventSymbol": _SYMBOL, "time": int(ts.timestamp() * 1000), "type": classification,
        "index": index, "sequence": index, "tradeId": index, "eventFlags": 0,
        "exchangeCode": "Q", "price": price, "size": size, "bidPrice": price - 0.25, "askPrice": price + 0.25,
        "exchangeSaleConditions": "@", "tradeThroughExempt": "0", "aggressorSide": "BUY",
        "spreadLeg": False, "extendedTradingHours": False, "validTick": True,
    }
    return DxLinkSourceEvent("TimeAndSale", _SYMBOL, fields, ts)


@dataclass
class _Segment:
    events: tuple
    raises: bool = False


class ScriptedFakeCollector:
    """Deterministic fake collector: each `collect()` call consumes one scripted
    segment (deliver events, then either return cleanly or raise DxLinkError),
    simulating exactly one connect/subscribe attempt per call -- matching how
    the real `DxLinkSourceCollector.collect()` behaves per invocation.

    A clean (non-raising) return advances the shared fake clock by the full
    requested `duration_seconds` -- exactly matching the real collector's
    contract of blocking for the requested span before returning normally.
    Without this, a fake clean return would look instantaneous to the
    supervisor, which (correctly, post-0V-A) treats a clean return as proof
    that the requested time genuinely elapsed."""

    def __init__(self, segments: tuple[_Segment, ...], clock: "_FakeClock | None" = None):
        self._segments = list(segments)
        self.call_count = 0
        self._clock = clock

    def collect(self, streamer_symbol, event_types, duration_seconds, max_events, on_event=None, on_connected=None, retain_events=True):
        self.call_count += 1
        if on_connected is not None:
            on_connected()
        if not self._segments:
            if self._clock is not None:
                self._clock.sleep(duration_seconds)
            return ()
        segment = self._segments.pop(0)
        for event in segment.events:
            if on_event is not None:
                on_event(event)
        if segment.raises:
            raise DxLinkError("simulated disconnect")
        if self._clock is not None:
            self._clock.sleep(duration_seconds)
        return ()


class _FakeClock:
    """Deterministic clock: each call to `now()` advances by a fixed step,
    and `sleep()` advances it by the requested duration -- no real wall-clock
    delay in tests."""

    def __init__(self, start: datetime, step: timedelta = timedelta(seconds=0.01)):
        self._current = start
        self._step = step
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        value = self._current
        self._current += self._step
        return value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self._current += timedelta(seconds=seconds)


# D. First cutoff / trading-date resolution
def test_resolve_current_trading_date_matches_session_model():
    assert resolve_current_trading_date(_SESSION_OPEN) == __import__("datetime").date(2026, 8, 24)


def test_resolve_current_trading_date_rejects_maintenance_interval():
    maintenance = datetime(2026, 8, 24, 21, 30, tzinfo=_UTC)  # 16:30 CT, closed interval
    with pytest.raises(LongHorizonCaptureError):
        resolve_current_trading_date(maintenance)


def test_dataset_filename_is_deterministic_and_readable():
    from uuid import UUID
    name = dataset_filename(_INSTRUMENT, __import__("datetime").date(2026, 8, 25), UUID("4b12c9aa-0000-0000-0000-000000000000"))
    assert name == "es_20260825_4b12c9aa.sqlite3"


# 60. Clean reconnect scenario
def test_clean_reconnect_scenario_produces_known_gap_and_finalized(tmp_path):
    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    collector = ScriptedFakeCollector((
        _Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=1), 1), _event(_SESSION_OPEN + timedelta(minutes=2), 2)), raises=True),
        _Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=3), 3),), raises=False),
    ), clock=clock)
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep,
    )
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    assert result.accepted_trade_count == 3
    assert result.known_gap_count == 1
    assert result.reconnect_count == 1
    assert result.checksum_sha256 is not None
    assert verify_checksum(result.database_path, result.checksum_sha256)

    store = LaboratoryStore(result.database_path, read_only=True)
    events = store.load_quality_events(result.dataset_id)
    evidence_types = [e.evidence_type.value for e in events]
    assert "SOURCE_CONNECTED" in evidence_types
    assert "SOURCE_DISCONNECTED" in evidence_types
    assert "SOURCE_RECONNECTED" in evidence_types
    assert "KNOWN_GAP" in evidence_types
    assert "CAPTURE_STOPPED" in evidence_types
    store.close()


# 61. Reconnect exhaustion scenario
def test_reconnect_exhaustion_marks_dataset_interrupted(tmp_path):
    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    segments = tuple(_Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=1), 1),), raises=True) for _ in range(5))
    collector = ScriptedFakeCollector(segments, clock=clock)
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=600,
        reconnect_policy=ReconnectPolicy(backoff_schedule_seconds=(0.01,), max_attempts=2),
        now=clock.now, sleeper=clock.sleep,
    )
    assert result.lifecycle_state is DatasetLifecycleState.INTERRUPTED
    store = LaboratoryStore(result.database_path, read_only=True)
    events = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    # Exhaustion means the FINAL attempt after the last permitted reconnect also
    # failed -- transient successful reconnects before that point are expected
    # and correctly recorded; what matters is the terminal state is INTERRUPTED,
    # never silently retried forever, and never marked FINALIZED.
    assert events.count("SOURCE_DISCONNECTED") > 2  # more disconnects than max_attempts permitted
    assert "CAPTURE_STOPPED" in events
    assert result.accepted_trade_count >= 1  # partial evidence preserved
    store.close()


# 62. Restart / resume scenario (deterministic store-level simulation, per
# instruction: "Do not require an actual OS crash test if deterministic
# store-level simulation proves it" -- a process crash is simulated by
# directly opening a dataset and leaving it OPEN, exactly as a real crash
# would, then resuming it in a fresh `run_long_horizon_capture` call).
def test_restart_resume_after_manual_open_dataset_continues_source_order(tmp_path):
    from dicks_laboratory.long_running_capture import _open_or_resume_dataset

    first_moment = _SESSION_OPEN + timedelta(minutes=1)
    database_path, dataset_id, store, resumed = _open_or_resume_dataset(
        tmp_path, _SPEC, __import__("datetime").date(2026, 8, 24), first_moment
    )
    assert resumed is False
    store.close()

    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=5))
    collector = ScriptedFakeCollector((
        _Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=5), 1),), raises=False),
    ), clock=clock)
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep)
    assert result.dataset_id == dataset_id  # same logical dataset resumed, not a second one
    assert result.accepted_trade_count == 1
    assert result.first_source_order == 1


# 28 / 99. Previous-day stale OPEN dataset handling
def test_stale_previous_day_open_dataset_is_interrupted_not_resumed(tmp_path):
    from dicks_laboratory.long_running_capture import _open_or_resume_dataset

    previous_day = __import__("datetime").date(2026, 8, 23)
    stale_path, stale_id, stale_store, _ = _open_or_resume_dataset(
        tmp_path, _SPEC, previous_day, _SESSION_OPEN - timedelta(hours=1)
    )
    stale_store.close()

    assert find_stale_open_datasets(tmp_path, _INSTRUMENT, __import__("datetime").date(2026, 8, 24)) == (stale_path,)

    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    collector = ScriptedFakeCollector((_Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=1), 1),), raises=False),), clock=clock)
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep)

    assert result.dataset_id != stale_id  # a new dataset was opened for the current date
    stale_store = LaboratoryStore(stale_path, read_only=True)
    assert stale_store.load_dataset_lifecycle_state(stale_id) is DatasetLifecycleState.INTERRUPTED
    stale_store.close()


# 100. Segmentation tests
def test_same_instrument_same_date_resumes_same_dataset(tmp_path):
    from dicks_laboratory.long_running_capture import _open_or_resume_dataset

    trading_date = __import__("datetime").date(2026, 8, 24)
    path_a, id_a, store_a, _ = _open_or_resume_dataset(tmp_path, _SPEC, trading_date, _SESSION_OPEN)
    store_a.close()
    path_b, id_b, store_b, resumed_b = _open_or_resume_dataset(tmp_path, _SPEC, trading_date, _SESSION_OPEN)
    store_b.close()
    assert path_a == path_b
    assert id_a == id_b
    assert resumed_b is True


def test_same_instrument_new_trading_date_opens_new_dataset(tmp_path):
    from dicks_laboratory.long_running_capture import _open_or_resume_dataset

    date_a = __import__("datetime").date(2026, 8, 24)
    date_b = __import__("datetime").date(2026, 8, 25)
    path_a, id_a, store_a, _ = _open_or_resume_dataset(tmp_path, _SPEC, date_a, _SESSION_OPEN)
    store_a.close()
    path_b, id_b, store_b, resumed_b = _open_or_resume_dataset(tmp_path, _SPEC, date_b, _SESSION_OPEN)
    store_b.close()
    assert path_a != path_b
    assert id_a != id_b
    assert resumed_b is False


def test_different_instrument_same_date_opens_different_dataset(tmp_path):
    from dicks_laboratory.long_running_capture import _open_or_resume_dataset

    trading_date = __import__("datetime").date(2026, 8, 24)
    other_spec = InstrumentCaptureSpec(
        instrument=InstrumentIdentity(InstrumentKind.FUTURE, "CME", "NQ", 2026, 9),
        streamer_symbol="/NQU26:XCME",
    )
    path_a, id_a, store_a, _ = _open_or_resume_dataset(tmp_path, _SPEC, trading_date, _SESSION_OPEN)
    store_a.close()
    path_b, id_b, store_b, _ = _open_or_resume_dataset(tmp_path, other_spec, trading_date, _SESSION_OPEN)
    store_b.close()
    assert path_a != path_b
    assert id_a != id_b


def test_finalized_dataset_for_same_instrument_date_conflicts(tmp_path):
    from dicks_laboratory.long_running_capture import _open_or_resume_dataset

    trading_date = __import__("datetime").date(2026, 8, 24)
    path, dataset_id, store, _ = _open_or_resume_dataset(tmp_path, _SPEC, trading_date, _SESSION_OPEN)
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.FINALIZED)
    store.close()
    with pytest.raises(LongHorizonCaptureError):
        _open_or_resume_dataset(tmp_path, _SPEC, trading_date, _SESSION_OPEN)


# 65. Duplicate replay across reconnect
def test_duplicate_source_event_across_reconnect_is_not_duplicated(tmp_path):
    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    duplicate_event = _event(_SESSION_OPEN + timedelta(minutes=1), 42)
    collector = ScriptedFakeCollector((
        _Segment(events=(duplicate_event,), raises=True),
        _Segment(events=(duplicate_event, _event(_SESSION_OPEN + timedelta(minutes=2), 43)), raises=False),
    ), clock=clock)
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep)
    assert result.accepted_trade_count == 2  # index 42 accepted once, 43 accepted once
    store = LaboratoryStore(result.database_path, read_only=True)
    rejections = store.load_rejections(result.dataset_id)
    assert any(r.reason == "DUPLICATE_SOURCE_INDEX_ACROSS_RECONNECT" for r in rejections)
    store.close()


def test_distinct_trades_sharing_time_price_size_are_not_collapsed(tmp_path):
    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    same_moment = _SESSION_OPEN + timedelta(minutes=1)
    collector = ScriptedFakeCollector((
        _Segment(events=(_event(same_moment, 100, price=7694.00), _event(same_moment, 101, price=7694.00)), raises=False),
    ), clock=clock)
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep)
    assert result.accepted_trade_count == 2


# Checksum
def test_checksum_verification_fails_after_file_altered(tmp_path):
    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    collector = ScriptedFakeCollector((_Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=1), 1),), raises=False),), clock=clock)
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep)
    assert result.manifest_path is not None
    assert result.manifest_path.exists()

    tampered = tmp_path / "tampered.sqlite3"
    tampered.write_bytes(result.database_path.read_bytes() + b"\x00")
    assert not verify_checksum(tampered, result.checksum_sha256)
    assert compute_sha256(tampered) != result.checksum_sha256


# 64. Maintenance-interval boundary behavior (not KNOWN_GAP; scheduled closed interval)
def test_maintenance_interval_is_not_in_session_but_is_not_a_gap():
    from datetime import date as _date

    before_close = datetime(2026, 8, 24, 20, 59, tzinfo=_UTC)  # 15:59 CT Monday
    at_close = datetime(2026, 8, 24, 21, 0, tzinfo=_UTC)  # 16:00 CT Monday
    mid_maintenance = datetime(2026, 8, 24, 21, 30, tzinfo=_UTC)  # 16:30 CT Monday
    reopen = datetime(2026, 8, 24, 22, 0, tzinfo=_UTC)  # 17:00 CT Monday -> new trading date

    assert resolve_current_trading_date(before_close) == _date(2026, 8, 24)
    with pytest.raises(LongHorizonCaptureError):
        resolve_current_trading_date(at_close)
    with pytest.raises(LongHorizonCaptureError):
        resolve_current_trading_date(mid_maintenance)
    assert resolve_current_trading_date(reopen) == _date(2026, 8, 25)


# 63. Trading-date rotation scenario (live, via the reconnect loop's own rotation check)
def test_trading_date_rotation_finalizes_old_dataset_and_opens_new_one(tmp_path):
    session_a_trade = _SESSION_OPEN + timedelta(minutes=1)  # trading date 2026-08-24
    session_b_open = _SESSION_OPEN + timedelta(days=1)  # next session open, trading date 2026-08-25
    session_b_trade = session_b_open + timedelta(minutes=1)

    class _JumpingClock:
        """Advances normally until a scripted jump point, then leaps straight
        past the session close/reopen boundary -- simulating the collector
        remaining alive across a trading-date rotation without waiting for
        real wall-clock time to pass in the test."""

        def __init__(self):
            self._current = session_a_trade
            self._collect_calls = 0

        def now(self):
            value = self._current
            self._current += timedelta(seconds=0.01)
            return value

        def sleep(self, seconds):
            self._current += timedelta(seconds=seconds)

        def after_first_collect(self):
            self._current = session_b_open

    clock = _JumpingClock()

    class _RotatingCollector:
        def __init__(self):
            self.call_count = 0

        def collect(self, streamer_symbol, event_types, duration_seconds, max_events, on_event=None, on_connected=None, retain_events=True):
            self.call_count += 1
            if on_connected is not None:
                on_connected()
            if self.call_count == 1:
                on_event(_event(session_a_trade, 1))
                clock.after_first_collect()
                return ()  # explicit jump simulates "rest of session A elapsed"; no extra clock.sleep needed here
            if self.call_count == 2:
                on_event(_event(session_b_trade, 2))
                clock.sleep(duration_seconds)  # clean return: the requested remaining span genuinely elapsed
                return ()
            clock.sleep(duration_seconds)
            return ()

    collector = _RotatingCollector()
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=3600 * 24, now=clock.now, sleeper=clock.sleep,
    )
    # The final result reflects dataset B (the rotated-to dataset); dataset A
    # must have been finalized separately with only its own trading date's row.
    from datetime import date as _date
    assert result.trading_date == _date(2026, 8, 25)
    assert result.accepted_trade_count == 1

    # dataset A has a different id; locate it by globbing.
    candidates = [p for p in tmp_path.glob("es_20260824_*.sqlite3")]
    assert len(candidates) == 1
    store_a = LaboratoryStore(candidates[0], read_only=True)
    dataset_a_id = store_a.list_dataset_ids()[0]
    assert store_a.load_dataset_lifecycle_state(dataset_a_id) is DatasetLifecycleState.FINALIZED
    trades_a = store_a.load_trade_observations(dataset_a_id)
    assert len(trades_a) == 1
    assert trades_a[0].event_timestamp == session_a_trade
    store_a.close()

    store_b = LaboratoryStore(result.database_path, read_only=True)
    trades_b = store_b.load_trade_observations(result.dataset_id)
    assert len(trades_b) == 1
    assert trades_b[0].event_timestamp == session_b_trade
    store_b.close()


# =====================================================================
# Phase 0V-A — Continuous Session Capture / Maintenance Boundary Correction
# =====================================================================

# Primary acceptance test (0V-A #13): a healthy 2-hour session, substantially
# longer than the old (removed) 300s poll interval, must produce exactly ONE
# source connection -- no periodic teardown/reconnect merely to check the clock.
def test_healthy_long_session_does_not_reconnect_periodically(tmp_path):
    from datetime import date as _date

    start = _SESSION_OPEN + timedelta(minutes=1)
    clock = _FakeClock(start)
    collector = ScriptedFakeCollector(
        (_Segment(events=(_event(start, 1), _event(start + timedelta(hours=1), 2)), raises=False),),
        clock=clock,
    )
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=7200, now=clock.now, sleeper=clock.sleep,
    )
    assert collector.call_count == 1  # exactly one connect/auth/subscribe for the whole 2-hour span
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    assert result.trading_date == _date(2026, 8, 24)
    assert result.accepted_trade_count == 2
    assert result.known_gap_count == 0
    assert result.reconnect_count == 0

    store = LaboratoryStore(result.database_path, read_only=True)
    events = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    assert events.count("SOURCE_CONNECTED") == 1
    assert events.count("SOURCE_DISCONNECTED") == 0
    assert events.count("SOURCE_RECONNECTED") == 0
    assert events.count("KNOWN_GAP") == 0
    store.close()


# 0V-A #14: scheduled session close is an intentional clean stop, never a
# disconnect/reconnect/gap.
def test_session_close_is_a_clean_stop_not_a_disconnect(tmp_path):
    start = _SESSION_OPEN + timedelta(minutes=1)
    trading_date = resolve_current_trading_date(start)
    session_close = _session_close_for(trading_date, _SPEC.session_definition)
    duration_seconds = (session_close - start).total_seconds()

    clock = _FakeClock(start)
    collector = ScriptedFakeCollector(
        (_Segment(events=(_event(start, 1),), raises=False),), clock=clock,
    )
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=duration_seconds, now=clock.now, sleeper=clock.sleep,
    )
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    store = LaboratoryStore(result.database_path, read_only=True)
    events = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    assert "CAPTURE_STOPPED" in events
    assert events.count("SOURCE_DISCONNECTED") == 0
    assert events.count("SOURCE_RECONNECTED") == 0
    assert events.count("KNOWN_GAP") == 0
    store.close()


# 0V-A #15: the collector process remains alive through the scheduled
# maintenance interval; no active dataset, no KNOWN_GAP, fresh SOURCE_CONNECTED
# at the next session open.
def test_maintenance_wait_produces_no_gap_and_fresh_connect_at_reopen(tmp_path):
    from datetime import date as _date

    trading_date_d = resolve_current_trading_date(_SESSION_OPEN + timedelta(minutes=1))
    session_close_d = _session_close_for(trading_date_d, _SPEC.session_definition)  # 16:00 CT Monday

    clock = _FakeClock(session_close_d)  # start exactly at close: already CLOSED_INTERVAL
    next_open = next_session_open_after(session_close_d, _SPEC.session_definition)
    post_open_trade = next_open + timedelta(minutes=1)
    collector = ScriptedFakeCollector(
        (_Segment(events=(_event(post_open_trade, 1),), raises=False),), clock=clock,
    )
    duration_seconds = (next_open - session_close_d).total_seconds() + 60  # a little past reopen
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=duration_seconds, now=clock.now, sleeper=clock.sleep,
    )
    assert result.trading_date == _date(2026, 8, 25)  # rolled to the next trading date
    assert any(s > 3000 for s in clock.sleeps)  # genuinely waited (~1 hour), not a busy-loop
    store = LaboratoryStore(result.database_path, read_only=True)
    events = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    assert events.count("SOURCE_CONNECTED") == 1
    assert events.count("KNOWN_GAP") == 0  # maintenance interval is not a capture gap
    store.close()
    # No dataset was ever opened for the maintenance window itself.
    assert list(tmp_path.glob("es_20260824_*.sqlite3")) == []


# 0V-A #16: starting the collector mid-maintenance must not crash/fail --
# it waits logically until the next session open.
def test_start_during_maintenance_waits_then_opens_correct_dataset(tmp_path):
    from datetime import date as _date

    trading_date_d = resolve_current_trading_date(_SESSION_OPEN + timedelta(minutes=1))
    session_close_d = _session_close_for(trading_date_d, _SPEC.session_definition)
    mid_maintenance = session_close_d + timedelta(minutes=30)  # 16:30 CT

    clock = _FakeClock(mid_maintenance)
    next_open = next_session_open_after(mid_maintenance, _SPEC.session_definition)
    post_open_trade = next_open + timedelta(minutes=1)
    collector = ScriptedFakeCollector(
        (_Segment(events=(_event(post_open_trade, 1),), raises=False),), clock=clock,
    )
    duration_seconds = (next_open - mid_maintenance).total_seconds() + 60
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=duration_seconds, now=clock.now, sleeper=clock.sleep,
    )
    assert result.trading_date == _date(2026, 8, 25)
    assert collector.call_count == 1
    store = LaboratoryStore(result.database_path, read_only=True)
    events = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    assert events.count("SOURCE_CONNECTED") == 1
    store.close()


# 0V-A #17: actual reconnect (unchanged accepted behavior) -- exact counts.
def test_actual_reconnect_produces_exact_lifecycle_counts(tmp_path):
    clock = _FakeClock(_SESSION_OPEN + timedelta(minutes=1))
    collector = ScriptedFakeCollector((
        _Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=1), 1),), raises=True),
        _Segment(events=(_event(_SESSION_OPEN + timedelta(minutes=3), 2),), raises=False),
    ), clock=clock)
    result = run_long_horizon_capture(tmp_path, _SPEC, collector, duration_seconds=60, now=clock.now, sleeper=clock.sleep)
    store = LaboratoryStore(result.database_path, read_only=True)
    events = [e.evidence_type.value for e in store.load_quality_events(result.dataset_id)]
    assert events.count("SOURCE_CONNECTED") == 1
    assert events.count("SOURCE_DISCONNECTED") == 1
    assert events.count("SOURCE_RECONNECTED") == 1
    assert events.count("KNOWN_GAP") == 1
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED
    store.close()


# 0V-A #18: a disconnect that never successfully reconnects before session
# close must cap the gap at the boundary, never fake a reconnect, and the
# next trading date's dataset must open independently with SOURCE_CONNECTED.
def test_disconnect_crossing_session_close_caps_gap_and_next_day_is_independent(tmp_path):
    trading_date_d = resolve_current_trading_date(_SESSION_OPEN + timedelta(minutes=1))
    session_close_d = _session_close_for(trading_date_d, _SPEC.session_definition)
    start = session_close_d - timedelta(seconds=10)  # 15:59:50 CT

    clock = _FakeClock(start)
    collector = ScriptedFakeCollector(
        (_Segment(events=(_event(start, 1),), raises=True),), clock=clock,
    )
    duration_seconds = (session_close_d - start).total_seconds()
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=duration_seconds,
        reconnect_policy=ReconnectPolicy(backoff_schedule_seconds=(30.0,), max_attempts=5),
        now=clock.now, sleeper=clock.sleep,
    )
    assert result.lifecycle_state is DatasetLifecycleState.FINALIZED  # closed on schedule, not a failure
    store = LaboratoryStore(result.database_path, read_only=True)
    events = store.load_quality_events(result.dataset_id)
    evidence_types = [e.evidence_type.value for e in events]
    assert evidence_types.count("SOURCE_RECONNECTED") == 0  # never fake a reconnect for the closing dataset
    gaps = [e for e in events if e.evidence_type.value == "KNOWN_GAP"]
    assert len(gaps) == 1
    # Capped at the session-close boundary (within the fake clock's own small
    # step resolution) -- never extended into the 16:00-17:00 maintenance hour.
    assert abs((gaps[0].interval_end - session_close_d).total_seconds()) < 1.0
    store.close()

    # The next trading date's dataset opens completely independently.
    next_open = next_session_open_after(session_close_d, _SPEC.session_definition)
    clock2 = _FakeClock(next_open)
    collector2 = ScriptedFakeCollector(
        (_Segment(events=(_event(next_open + timedelta(minutes=1), 1),), raises=False),), clock=clock2,
    )
    result2 = run_long_horizon_capture(tmp_path, _SPEC, collector2, duration_seconds=60, now=clock2.now, sleeper=clock2.sleep)
    assert result2.dataset_id != result.dataset_id
    store2 = LaboratoryStore(result2.database_path, read_only=True)
    events2 = [e.evidence_type.value for e in store2.load_quality_events(result2.dataset_id)]
    assert events2.count("SOURCE_CONNECTED") == 1
    assert events2.count("SOURCE_RECONNECTED") == 0
    store2.close()


# 0V-A #19: full transition -- continuous capture on D, scheduled close,
# genuine wait through maintenance, continuous capture on D+1 -- no artificial
# gap spanning the maintenance interval.
def test_trading_date_rotation_across_real_maintenance_wait(tmp_path):
    from datetime import date as _date

    start = _SESSION_OPEN + timedelta(minutes=1)
    trading_date_d = resolve_current_trading_date(start)
    session_close_d = _session_close_for(trading_date_d, _SPEC.session_definition)
    next_open = next_session_open_after(session_close_d, _SPEC.session_definition)

    clock = _FakeClock(start)

    class _TwoSessionCollector:
        def __init__(self):
            self.call_count = 0

        def collect(self, streamer_symbol, event_types, duration_seconds, max_events, on_event=None, on_connected=None, retain_events=True):
            self.call_count += 1
            if on_connected is not None:
                on_connected()
            if self.call_count == 1:
                on_event(_event(start, 1))
            elif self.call_count == 2:
                on_event(_event(next_open + timedelta(minutes=1), 2))
            clock.sleep(duration_seconds)
            return ()

    collector = _TwoSessionCollector()
    duration_seconds = (next_open - start).total_seconds() + 60
    result = run_long_horizon_capture(
        tmp_path, _SPEC, collector, duration_seconds=duration_seconds, now=clock.now, sleeper=clock.sleep,
    )
    assert result.trading_date == _date(2026, 8, 25)
    assert collector.call_count == 2  # one continuous connection per trading date, not per poll interval

    candidates_d = list(tmp_path.glob("es_20260824_*.sqlite3"))
    assert len(candidates_d) == 1
    store_d = LaboratoryStore(candidates_d[0], read_only=True)
    dataset_d_id = store_d.list_dataset_ids()[0]
    assert store_d.load_dataset_lifecycle_state(dataset_d_id) is DatasetLifecycleState.FINALIZED
    events_d = [e.evidence_type.value for e in store_d.load_quality_events(dataset_d_id)]
    assert events_d.count("KNOWN_GAP") == 0  # no artificial gap from the scheduled close/maintenance
    store_d.close()

    store_d1 = LaboratoryStore(result.database_path, read_only=True)
    events_d1 = [e.evidence_type.value for e in store_d1.load_quality_events(result.dataset_id)]
    assert events_d1.count("SOURCE_CONNECTED") == 1
    assert events_d1.count("SOURCE_RECONNECTED") == 0
    assert events_d1.count("KNOWN_GAP") == 0
    store_d1.close()
