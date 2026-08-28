"""Phase 0V — resilient long-running DXLink TimeAndSale collection.

Extends the accepted bounded `capture_es_timesales_dataset` (`live_capture.py`,
left untouched and still usable for short bounded experiments) with the
serious-collection foundation Phase 0U's audit required: full source-field
parity for every disposition, bounded reconnect with explicit KNOWN_GAP
evidence, one dataset per exact instrument + futures trading date, durable
`source_order` continuity across restarts, and an explicit OPEN/FINALIZED/
INTERRUPTED dataset lifecycle.

Reconnect requires no change to the DXLink transport: `DxLinkSourceCollector.
collect()` already performs a full connect/auth/subscribe cycle on every call
(see `K9/tastytrade/dxlink.py`), so "reconnect" here is simply calling
`collect()` again for the remaining time budget after a caught `DxLinkError`.

Governing invariants (see docs/dicks_laboratory/LONG_HORIZON_DATA_REPLAY_
READINESS_AUDIT.md and RESILIENT_LONG_RUNNING_CAPTURE.md):
  reconnect != proof of gap recovery
  FINALIZED != complete market tape
  no retained events != proof of no market activity
  source_order != dataset_sequence
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4, uuid5
from zoneinfo import ZoneInfo

from K9.tastytrade.dxlink import DxLinkError
from dicks_laboratory.dataset_state import DatasetClosingSummary, DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import (
    RejectedDxLinkTimeAndSaleSourceRecord,
    normalize_dxlink_time_and_sales,
    source_records_from_events,
)
from dicks_laboratory.live_capture import SourceCollector
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.sessions import (
    ES_GLOBEX,
    FuturesSessionDefinition,
    SessionState,
    classify_es_session,
    session_coverage,
)
from dicks_laboratory.store import LaboratoryStore

_CT = ZoneInfo("America/Chicago")

_NORMALIZER_VERSION = "phase-0v-serious-collection-v1"


class LongHorizonCaptureError(RuntimeError):
    """A collection request could not proceed; the failure mode is explicit."""


@dataclass(frozen=True)
class InstrumentCaptureSpec:
    """What to collect: an exact contract, its streamer symbol, and session rule.

    Deliberately generic across instruments (not ES-specific architecture) --
    0V still only runs one instrument at a time; simultaneous multi-instrument
    capture is not implemented here (0U explicitly deferred that decision).
    """

    instrument: InstrumentIdentity
    streamer_symbol: str
    session_definition: FuturesSessionDefinition = ES_GLOBEX


@dataclass(frozen=True)
class ReconnectPolicy:
    """Deterministic bounded backoff. The last schedule entry repeats beyond its index."""

    backoff_schedule_seconds: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
    max_attempts: int = 5

    def __post_init__(self) -> None:
        if not self.backoff_schedule_seconds:
            raise ValueError("backoff_schedule_seconds must be non-empty.")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive.")

    def backoff_for_attempt(self, attempt: int) -> float:
        index = min(attempt - 1, len(self.backoff_schedule_seconds) - 1)
        return self.backoff_schedule_seconds[index]


DEFAULT_RECONNECT_POLICY = ReconnectPolicy()


@dataclass(frozen=True)
class LongHorizonCaptureResult:
    """Factual outcome of one supervised collection run; no completeness claim."""

    dataset_id: UUID
    database_path: Path
    instrument: InstrumentIdentity
    trading_date: date
    lifecycle_state: DatasetLifecycleState
    accepted_trade_count: int
    deferred_event_count: int
    rejected_record_count: int
    known_gap_count: int
    reconnect_count: int
    first_source_order: int | None
    last_source_order: int | None
    checksum_sha256: str | None
    manifest_path: Path | None


def resolve_current_trading_date(now: datetime, session_definition: FuturesSessionDefinition = ES_GLOBEX) -> date:
    """The exact accepted `sessions.py` trading date for `now`, or a clear error.

    Reuses `classify_es_session` rather than inventing a midnight-based day
    boundary. Raises if `now` falls in a closed/maintenance interval or
    outside the session entirely -- there is no valid trading date to assign
    a dataset to at that instant (0V does not implement an indefinite
    wait-for-session-open loop; see docs for this scope decision).
    """
    membership = classify_es_session(now, session_definition)
    if membership.state is not SessionState.IN_SESSION or membership.trading_date is None:
        raise LongHorizonCaptureError(
            f"Cannot open/continue a dataset: market is not in session at {now.isoformat()} "
            f"(state={membership.state.value}). Serious collection requires starting during an active session."
        )
    return membership.trading_date


def next_session_open_after(now: datetime, session_definition: FuturesSessionDefinition = ES_GLOBEX) -> datetime:
    """The next instant the session becomes IN_SESSION, strictly after `now`.

    Reuses `classify_es_session` as the single source of truth for weekday/
    weekend semantics rather than duplicating that logic -- probes candidate
    daily-open instants forward (bounded to one week) and returns the first
    one `classify_es_session` actually confirms is IN_SESSION.
    """
    local_now = now.astimezone(_CT)
    for day_offset in range(8):
        candidate_local = datetime.combine(
            local_now.date() + timedelta(days=day_offset), session_definition.open_time_local, tzinfo=_CT
        )
        candidate_utc = candidate_local.astimezone(timezone.utc)
        if candidate_utc <= now:
            continue
        if classify_es_session(candidate_utc, session_definition).state is SessionState.IN_SESSION:
            return candidate_utc
    raise LongHorizonCaptureError(f"Could not resolve the next session open within a week after {now.isoformat()}.")


def _session_close_for(trading_date: date, session_definition: FuturesSessionDefinition) -> datetime:
    """The accepted session-close instant for `trading_date` (0N `sessions.py`, unchanged)."""
    return session_coverage((), trading_date, session_definition).session_end_utc


def dataset_filename(instrument: InstrumentIdentity, trading_date: date, dataset_id: UUID) -> str:
    """Deterministic, human-readable filename. Never authoritative -- `dataset_id` is."""
    date_slug = trading_date.strftime("%Y%m%d")
    return f"{instrument.root.lower()}_{date_slug}_{str(dataset_id)[:8]}.sqlite3"


def resolve_collector_version() -> tuple[str, str]:
    """Resolve collector build identity once at startup; never invoked per-event.

    Returns (collector_version, collector_git_commit). Absence of Git metadata
    (e.g. a deployed package without a `.git` directory) must not fail capture
    -- falls back to the explicit string "UNKNOWN".
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5, check=True
        ).stdout.strip()
    except Exception:
        commit = "UNKNOWN"
    return _NORMALIZER_VERSION, (commit or "UNKNOWN")


def find_stale_open_datasets(
    data_dir: Path,
    instrument: InstrumentIdentity,
    current_trading_date: date,
) -> tuple[Path, ...]:
    """Locate other files for this instrument whose dataset is OPEN for a prior trading date.

    Read-only inspection only -- does not mutate any file. Callers decide
    whether/how to mark these INTERRUPTED (see `interrupt_stale_dataset`).
    """
    stale: list[Path] = []
    if not data_dir.is_dir():
        return ()
    for candidate in sorted(data_dir.glob(f"{instrument.root.lower()}_*.sqlite3")):
        try:
            store = LaboratoryStore(candidate, read_only=True)
        except Exception:
            continue
        try:
            for dataset_id in store.list_dataset_ids():
                try:
                    trading_date_value, dataset_instrument = store.load_dataset_trading_context(dataset_id)
                    state = store.load_dataset_lifecycle_state(dataset_id)
                except Exception:
                    continue
                if (
                    state is DatasetLifecycleState.OPEN
                    and dataset_instrument is not None
                    and dataset_instrument.canonical_id == instrument.canonical_id
                    and trading_date_value is not None
                    and trading_date_value != current_trading_date
                ):
                    stale.append(candidate)
        finally:
            store.close()
    return tuple(stale)


def interrupt_stale_dataset(database_path: Path, observed_at: datetime) -> None:
    """Mark every OPEN dataset in `database_path` INTERRUPTED with durable evidence.

    Used at startup for a previous trading date's leftover OPEN artifact
    (0U §28: do not resume a stale prior-day dataset; do not silently create
    a second dataset for the same instrument/date either -- close the old one
    explicitly first).
    """
    store = LaboratoryStore(database_path)
    try:
        for dataset_id in store.list_dataset_ids():
            state = store.load_dataset_lifecycle_state(dataset_id)
            if state is not DatasetLifecycleState.OPEN:
                continue
            store.save_quality_events((
                DatasetQualityEvent(
                    event_id=uuid5(dataset_id, f"lifecycle:STALE_INTERRUPTED:{observed_at.isoformat()}"),
                    dataset_id=dataset_id,
                    evidence_type=DatasetQualityEvidenceType.CAPTURE_STOPPED,
                    detail="stale_open_dataset_interrupted_at_startup",
                    observed_at=observed_at,
                ),
            ))
            store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.INTERRUPTED)
            _write_closing_summary(store, dataset_id, observed_at, collector_version=None, collector_git_commit=None)
    finally:
        store.close()


def run_long_horizon_capture(
    data_dir: Path,
    spec: InstrumentCaptureSpec,
    collector: SourceCollector,
    duration_seconds: float,
    max_events: int = 1_000_000,
    reconnect_policy: ReconnectPolicy = DEFAULT_RECONNECT_POLICY,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleeper: Callable[[float], None] = time.sleep,
    refresh_collector: Callable[[], SourceCollector] | None = None,
) -> LongHorizonCaptureResult:
    """Run one supervised, reconnect-capable, bounded collection run.

    `duration_seconds` bounds the *overall* Human deadline. Within that
    deadline, each trading-date session gets exactly ONE continuous
    `collect()` call spanning from connect through the earlier of the
    session's own close or the Human deadline -- a healthy connection is
    never intentionally torn down merely to check the clock (0V-A). Only a
    genuine `DxLinkError` triggers reconnect. A scheduled session close is
    an intentional clean stop (`CAPTURE_STOPPED` -> `FINALIZED`), never a
    `SOURCE_DISCONNECTED`/`KNOWN_GAP`. The scheduled maintenance interval
    between sessions is waited through (no dataset, no gap evidence); the
    next trading date's session then gets its own fresh `SOURCE_CONNECTED`,
    never a `SOURCE_RECONNECTED` of the prior dataset.

    `refresh_collector`, if given, is called to obtain a brand-new collector
    (e.g. carrying a freshly re-obtained provider quote token) before every
    reconnect attempt (0W-2A: `DxLinkSourceCollector` fixes its auth token at
    construction, so blindly retrying `collect()` on the *same* instance
    forever resends whatever token was valid at startup -- if that token has
    since expired, every retry fails identically). When omitted, the original
    collector instance is reused across retries exactly as before -- pure
    network hiccups where auth was never the issue still recover the same way.
    """
    collector_version, collector_git_commit = resolve_collector_version()
    overall_deadline = now() + timedelta(seconds=duration_seconds)
    current_time = now()
    last_result: LongHorizonCaptureResult | None = None

    while True:
        try:
            trading_date = resolve_current_trading_date(current_time, spec.session_definition)
        except LongHorizonCaptureError:
            if current_time >= overall_deadline:
                if last_result is not None:
                    return last_result
                raise LongHorizonCaptureError(
                    "The requested duration elapsed entirely within a scheduled closed "
                    "interval; no session ever opened, so no dataset was created."
                ) from None
            wait_until = min(next_session_open_after(current_time, spec.session_definition), overall_deadline)
            wait_seconds = (wait_until - current_time).total_seconds()
            if wait_seconds > 0:
                sleeper(wait_seconds)
            current_time = now()
            continue

        for stale_path in find_stale_open_datasets(data_dir, spec.instrument, trading_date):
            interrupt_stale_dataset(stale_path, current_time)

        session_close = _session_close_for(trading_date, spec.session_definition)
        segment_deadline = min(overall_deadline, session_close)

        result, stop = _run_one_trading_date_session(
            data_dir, spec, trading_date, current_time, segment_deadline, overall_deadline,
            collector, reconnect_policy, max_events, now, sleeper, collector_version, collector_git_commit,
            refresh_collector,
        )
        last_result = result
        current_time = now()
        if stop or current_time >= overall_deadline:
            return result
        # Otherwise: this trading date's session closed on schedule (FINALIZED)
        # with overall Human budget still remaining -> wait through maintenance
        # and continue to the next trading date at the top of this loop.


def _run_one_trading_date_session(
    data_dir: Path,
    spec: InstrumentCaptureSpec,
    trading_date: date,
    start_time: datetime,
    segment_deadline: datetime,
    overall_deadline: datetime,
    collector: SourceCollector,
    reconnect_policy: ReconnectPolicy,
    max_events: int,
    now: Callable[[], datetime],
    sleeper: Callable[[float], None],
    collector_version: str,
    collector_git_commit: str,
    refresh_collector: Callable[[], SourceCollector] | None = None,
) -> tuple[LongHorizonCaptureResult, bool]:
    """Run one dataset's continuous collection, bounded by `segment_deadline`
    (the earlier of this trading date's session close or the overall Human
    deadline). Returns `(result, stop)`; `stop=True` means the caller must
    not continue on to another trading date (deadline reached, INTERRUPTED,
    or an unexpected error)."""
    database_path, dataset_id, store, resumed = _open_or_resume_dataset(data_dir, spec, trading_date, start_time)
    source_order_counter = store.max_source_order_for_dataset(dataset_id) + 1
    accepted_count = len(store.load_trade_observations(dataset_id))
    seen_new_source_indices: set[int] = {
        p.source_index for p in store.load_dxlink_time_and_sale_provenance(dataset_id)
    }

    classifications: Counter[str] = Counter()
    reconnect_count = 0
    ever_connected = False
    disconnected_at: datetime | None = None
    total_events_seen = 0

    def on_connected() -> None:
        nonlocal ever_connected, disconnected_at
        moment = now()
        if not ever_connected:
            ever_connected = True
            store.save_quality_events((
                DatasetQualityEvent(
                    event_id=uuid5(dataset_id, f"lifecycle:SOURCE_CONNECTED:{moment.isoformat()}"),
                    dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.SOURCE_CONNECTED,
                    detail="source_connected", observed_at=moment,
                ),
            ))
        elif disconnected_at is not None:
            # Only a genuine prior disconnect makes this a real reconnect.
            store.save_quality_events((
                DatasetQualityEvent(
                    event_id=uuid5(dataset_id, f"lifecycle:SOURCE_RECONNECTED:{moment.isoformat()}"),
                    dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.SOURCE_RECONNECTED,
                    detail="source_reconnected", observed_at=moment,
                ),
            ))
            _close_known_gap(store, dataset_id, disconnected_at, moment)
            disconnected_at = None

    def on_event(event) -> None:
        nonlocal source_order_counter, accepted_count, total_events_seen
        total_events_seen += 1
        record = source_records_from_events((event,), start_source_order=source_order_counter)[0]
        classifications[record.event_classification or "UNKNOWN"] += 1

        # Duplicate handling across reconnect (0U §35): a provider MAY conceivably
        # redeliver an already-accepted NEW event after resubscribing. Detect this
        # conservatively via the same source identity dxFeed itself uses for
        # correction/cancel correlation (`index`) -- never via timestamp+price+size,
        # which would risk collapsing legitimately distinct trades. The duplicate's
        # own evidence is still retained (as a rejection), never silently dropped.
        if record.event_classification == "NEW":
            try:
                candidate_index = int(record.source_index)
            except (TypeError, ValueError):
                candidate_index = None
            if candidate_index is not None and candidate_index in seen_new_source_indices:
                rejection_id = uuid5(dataset_id, f"duplicate-rejection:{record.source_record_ref}")
                store.save_rejections((
                    NormalizationRejection(
                        rejection_id=rejection_id, dataset_id=dataset_id,
                        source_kind=RejectionSourceKind.DXLINK_TIME_AND_SALE,
                        source_record_ref=record.source_record_ref, source_order=source_order_counter,
                        reason="DUPLICATE_SOURCE_INDEX_ACROSS_RECONNECT",
                    ),
                ))
                store.save_rejected_dxlink_time_and_sale_source_records((
                    RejectedDxLinkTimeAndSaleSourceRecord(
                        rejection_id=rejection_id, dataset_id=dataset_id,
                        source_order=source_order_counter, source_record=record,
                    ),
                ))
                source_order_counter += 1
                return

        result = normalize_dxlink_time_and_sales(
            (record,), _dataset_identity_stub(dataset_id), spec.instrument, spec.streamer_symbol,
            start_source_order=source_order_counter, start_dataset_sequence=accepted_count + 1,
        )
        source_order_counter += 1
        if result.observations:
            accepted_count += len(result.observations)
            store.save_trade_observations(result.observations)
            store.save_dxlink_time_and_sale_provenance(result.provenance)
            seen_new_source_indices.update(p.source_index for p in result.provenance)
        if result.deferred:
            store.save_deferred_dxlink_time_and_sales(result.deferred)
        if result.rejected:
            store.save_rejections(result.rejected)
            store.save_rejected_dxlink_time_and_sale_source_records(result.rejected_source_records)

    target_state = DatasetLifecycleState.FINALIZED
    stop = False
    try:
        while True:
            remaining = (segment_deadline - now()).total_seconds()
            if remaining <= 0:
                break  # session close or Human deadline reached; connection was healthy throughout
            try:
                # ONE continuous connection for up to the full remaining span of
                # this trading date's session -- never sliced merely to poll the
                # clock. `collect()` only returns early via a genuine DxLinkError.
                collector.collect(
                    spec.streamer_symbol, ("TimeAndSale",), remaining, max(1, max_events - total_events_seen),
                    on_event=on_event, on_connected=on_connected, retain_events=False,
                )
                break  # remaining time (or max_events) genuinely elapsed: clean stop
            except DxLinkError as exc:
                disconnect_moment = now()
                disconnected_at = disconnect_moment
                reconnect_count += 1
                store.save_quality_events((
                    DatasetQualityEvent(
                        event_id=uuid5(dataset_id, f"lifecycle:SOURCE_DISCONNECTED:{disconnect_moment.isoformat()}"),
                        dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
                        detail=_sanitized_disconnect_detail(reconnect_count, exc), observed_at=disconnect_moment,
                    ),
                ))
                if reconnect_count > reconnect_policy.max_attempts:
                    target_state = DatasetLifecycleState.INTERRUPTED
                    stop = True
                    break
                backoff = reconnect_policy.backoff_for_attempt(reconnect_count)
                # Cap the retry wait at this session's own close/deadline: never
                # extend a disconnect-driven wait into the maintenance interval.
                retry_at = min(now() + timedelta(seconds=backoff), segment_deadline)
                wait_seconds = (retry_at - now()).total_seconds()
                if wait_seconds > 0:
                    sleeper(wait_seconds)
                if now() >= segment_deadline:
                    # Session closed (or deadline reached) while still disconnected,
                    # before a successful reconnect. Do not fabricate a reconnect for
                    # this now-closing dataset -- cap the gap at the boundary below.
                    break
                if refresh_collector is not None:
                    # Never retry authentication with whatever token was valid at
                    # startup (0W-2A root cause): a healthy connection is still never
                    # torn down proactively (0V-A), but a *genuine* reconnect always
                    # gets whatever fresh provider credential it needs.
                    collector = refresh_collector()
                continue
    except KeyboardInterrupt:
        target_state = DatasetLifecycleState.FINALIZED  # deliberate human stop: cleanly closed, not a failure
        stop = True
    except Exception:
        target_state = DatasetLifecycleState.INTERRUPTED
        close_moment = now()
        if disconnected_at is not None:
            _close_known_gap(store, dataset_id, disconnected_at, close_moment)
        _finalize(store, dataset_id, close_moment, classifications, collector_version, collector_git_commit, target_state)
        store.close()
        raise

    close_moment = now()
    if disconnected_at is not None:
        # A disconnect never successfully reconnected before this session ended
        # (session close or deadline reached while down). The unobserved interval
        # is capped at that boundary as explicit KNOWN_GAP evidence -- never
        # extended into maintenance, and never papered over with a fake reconnect.
        _close_known_gap(store, dataset_id, disconnected_at, close_moment)
    _finalize(store, dataset_id, close_moment, classifications, collector_version, collector_git_commit, target_state)
    result = _build_result(store, dataset_id, database_path, spec.instrument, trading_date, target_state)
    store.close()

    if target_state is DatasetLifecycleState.INTERRUPTED or close_moment >= overall_deadline:
        stop = True
    return result, stop


_FAILURE_STAGE_MARKERS: tuple[tuple[str, str], ...] = (
    ("AUTHORIZED", "DXLINK_AUTH"),
    ("SETUP", "DXLINK_SETUP"),
    ("CHANNEL_OPENED", "CHANNEL_REQUEST"),
    ("FEED_CONFIG", "FEED_SETUP"),
    ("timed out", "SOCKET_RECEIVE"),
    ("invalid json", "SOCKET_RECEIVE"),
    ("non-object json", "SOCKET_RECEIVE"),
    ("connection error while receiving", "SOCKET_RECEIVE"),
    ("unsupported shape", "FEED_DATA"),
)


def _classify_failure_stage(message: str) -> str:
    """Best-effort, evidence-only stage classification from a `DxLinkError`
    message (0W-2A observability requirement). `DxLinkError` messages never
    include the quote token or any credential -- see `K9/tastytrade/dxlink.py`
    -- so the raw message text is itself already safe to persist."""
    lowered = message.lower()
    for marker, stage in _FAILURE_STAGE_MARKERS:
        if marker.lower() in lowered:
            return stage
    return "OTHER"


def _sanitized_disconnect_detail(attempt: int, exc: DxLinkError) -> str:
    """Safe structured reconnect-failure detail: attempt number, best-effort
    stage, and the exception's own (secret-free) message -- never the socket,
    a header, or a token. See `_classify_failure_stage`."""
    reason = " ".join(str(exc).split())[:200]
    stage = _classify_failure_stage(reason)
    return f"source_disconnected; attempt={attempt}; stage={stage}; error={reason}"


def _close_known_gap(store: LaboratoryStore, dataset_id: UUID, disconnected_at: datetime, moment: datetime) -> None:
    """reconnect != proof of gap recovery: the disconnect interval is durably
    recorded as an unobserved KNOWN_GAP, never silently absorbed."""
    store.save_quality_events((
        DatasetQualityEvent(
            event_id=uuid5(dataset_id, f"lifecycle:KNOWN_GAP:{disconnected_at.isoformat()}:{moment.isoformat()}"),
            dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.KNOWN_GAP,
            detail="disconnect_to_reconnect_interval; no automatic recovery assumed",
            interval_start=disconnected_at, interval_end=moment,
        ),
    ))


def _open_or_resume_dataset(
    data_dir: Path,
    spec: InstrumentCaptureSpec,
    trading_date: date,
    observed_at: datetime,
) -> tuple[Path, UUID, LaboratoryStore, bool]:
    """Resume an existing OPEN dataset for this exact instrument+trading_date, or create one.

    Never silently creates a second dataset for the same instrument+date while
    a resumable OPEN one exists (0U §27). A same-instrument+date file whose
    dataset already closed (FINALIZED/INTERRUPTED) is a genuine conflict --
    raised clearly rather than silently overwritten or duplicated.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    for candidate in sorted(data_dir.glob(f"{spec.instrument.root.lower()}_*.sqlite3")):
        try:
            probe = LaboratoryStore(candidate, read_only=True)
        except Exception:
            continue
        try:
            for existing_id in probe.list_dataset_ids():
                existing_date, existing_instrument = probe.load_dataset_trading_context(existing_id)
                if (
                    existing_instrument is not None
                    and existing_instrument.canonical_id == spec.instrument.canonical_id
                    and existing_date == trading_date
                ):
                    state = probe.load_dataset_lifecycle_state(existing_id)
                    if state is DatasetLifecycleState.OPEN:
                        probe.close()
                        store = LaboratoryStore(candidate)
                        return candidate, existing_id, store, True
                    probe.close()
                    raise LongHorizonCaptureError(
                        f"A dataset for {spec.instrument.canonical_id} on {trading_date.isoformat()} "
                        f"already exists at {candidate} in state {state}. Refusing to overwrite or duplicate it."
                    )
        finally:
            if probe is not None:
                try:
                    probe.close()
                except Exception:
                    pass

    dataset_id = uuid4()
    filename = dataset_filename(spec.instrument, trading_date, dataset_id)
    database_path = data_dir / filename
    dataset = DatasetIdentity(
        dataset_id=dataset_id,
        kind=DatasetKind.HISTORICAL_IMPORT,
        label=f"long-horizon-{spec.instrument.root.lower()}-{trading_date.isoformat()}",
        source_locator=f"TASTYTRADE_DXLINK:{spec.streamer_symbol}:TimeAndSale",
        source_timezone="UTC epoch milliseconds",
        normalizer_version=_NORMALIZER_VERSION,
        capture_started_at=observed_at,
        origin=DatasetOrigin.AUTHENTIC_SOURCE,
    )
    store = LaboratoryStore(database_path)
    store.save_dataset(dataset)
    store.save_dataset_trading_context(dataset_id, trading_date, spec.instrument)
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.OPEN)
    store.save_quality_events((
        DatasetQualityEvent(
            event_id=uuid5(dataset_id, f"lifecycle:CAPTURE_STARTED:{observed_at.isoformat()}"),
            dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.CAPTURE_STARTED,
            detail="capture_started", observed_at=observed_at,
        ),
    ))
    return database_path, dataset_id, store, False


def _dataset_identity_stub(dataset_id: UUID) -> DatasetIdentity:
    """`normalize_dxlink_time_and_sales` only reads `.dataset_id` from this argument."""
    return DatasetIdentity(dataset_id=dataset_id, kind=DatasetKind.HISTORICAL_IMPORT, label="stub")


def _finalize(
    store: LaboratoryStore,
    dataset_id: UUID,
    closed_at: datetime,
    classifications: Counter,
    collector_version: str,
    collector_git_commit: str,
    target_state: DatasetLifecycleState,
) -> None:
    """Close a dataset intentionally, recording exactly the requested closure
    state -- never silently defaulting to FINALIZED regardless of intent
    (a prior version of this function did exactly that, masking the real
    lifecycle_state of an INTERRUPTED dataset in the database itself)."""
    store.save_quality_events((
        DatasetQualityEvent(
            event_id=uuid5(dataset_id, f"lifecycle:CAPTURE_STOPPED:{closed_at.isoformat()}"),
            dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.CAPTURE_STOPPED,
            detail="capture_stopped", observed_at=closed_at,
        ),
    ))
    store.update_dataset_capture_ended(dataset_id, closed_at)
    store.set_dataset_lifecycle_state(dataset_id, target_state)
    _write_closing_summary(store, dataset_id, closed_at, collector_version, collector_git_commit)


def _write_closing_summary(
    store: LaboratoryStore,
    dataset_id: UUID,
    closed_at: datetime,
    collector_version: str | None,
    collector_git_commit: str | None,
) -> None:
    if store.load_dataset_closing_summary(dataset_id) is not None:
        return  # already written once; a closing summary is a frozen snapshot, never rewritten
    trades = store.load_trade_observations(dataset_id)
    deferred = store.load_deferred_dxlink_time_and_sales(dataset_id)
    rejections = store.load_rejections(dataset_id)
    quality_events = store.load_quality_events(dataset_id)
    known_gaps = sum(1 for event in quality_events if event.evidence_type is DatasetQualityEvidenceType.KNOWN_GAP)
    suspected_gaps = sum(
        1 for event in quality_events if event.evidence_type is DatasetQualityEvidenceType.SUSPECTED_GAP
    )
    max_source_order = store.max_source_order_for_dataset(dataset_id)
    store.save_dataset_closing_summary(
        DatasetClosingSummary(
            dataset_id=dataset_id,
            accepted_trade_count=len(trades),
            deferred_event_count=len(deferred),
            rejected_record_count=len(rejections),
            known_gap_count=known_gaps,
            suspected_gap_count=suspected_gaps,
            first_source_order=1 if max_source_order else None,
            last_source_order=max_source_order or None,
            closed_at=closed_at,
            collector_version=collector_version,
            collector_git_commit=collector_git_commit,
        )
    )


def _build_result(
    store: LaboratoryStore,
    dataset_id: UUID,
    database_path: Path,
    instrument: InstrumentIdentity,
    trading_date: date,
    lifecycle_state: DatasetLifecycleState,
) -> LongHorizonCaptureResult:
    summary = store.load_dataset_closing_summary(dataset_id)
    quality_events = store.load_quality_events(dataset_id)
    reconnect_count = sum(
        1 for event in quality_events if event.evidence_type is DatasetQualityEvidenceType.SOURCE_RECONNECTED
    )
    checksum, manifest_path = None, None
    if database_path.exists():
        checksum = compute_sha256(database_path)
        manifest_path = write_manifest(database_path, dataset_id, instrument, trading_date, lifecycle_state, checksum, summary)
    return LongHorizonCaptureResult(
        dataset_id=dataset_id,
        database_path=database_path,
        instrument=instrument,
        trading_date=trading_date,
        lifecycle_state=lifecycle_state,
        accepted_trade_count=summary.accepted_trade_count if summary else 0,
        deferred_event_count=summary.deferred_event_count if summary else 0,
        rejected_record_count=summary.rejected_record_count if summary else 0,
        known_gap_count=summary.known_gap_count if summary else 0,
        reconnect_count=reconnect_count,
        first_source_order=summary.first_source_order if summary else None,
        last_source_order=summary.last_source_order if summary else None,
        checksum_sha256=checksum,
        manifest_path=manifest_path,
    )


def compute_sha256(path: Path) -> str:
    """Archival-integrity checksum of a closed SQLite file.

    This proves the file's bytes are unaltered since closure -- it is NOT a
    market-data completeness claim. A checksummed file may still contain
    known gaps or a partial session; "file intact" and "market tape complete"
    are unrelated facts.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(
    database_path: Path,
    dataset_id: UUID,
    instrument: InstrumentIdentity,
    trading_date: date,
    lifecycle_state: DatasetLifecycleState,
    checksum_sha256: str,
    summary: DatasetClosingSummary | None,
) -> Path:
    """Write a small sidecar manifest. Archival convenience only -- the SQLite
    database's own `datasets`/`dataset_closing_summaries` rows remain the
    single source of truth; this file must never become an independently
    editable second copy of that metadata."""
    manifest = {
        "dataset_id": str(dataset_id),
        "instrument": instrument.canonical_id,
        "trading_date": trading_date.isoformat(),
        "state": lifecycle_state.value,
        "sha256": checksum_sha256,
        "collector_git_commit": summary.collector_git_commit if summary else None,
        "closed_at": summary.closed_at.isoformat() if summary else None,
        "checksum_scope": "file integrity only; not a market-data completeness claim",
    }
    manifest_path = database_path.with_suffix(database_path.suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest_path


def verify_checksum(database_path: Path, expected_sha256: str) -> bool:
    return compute_sha256(database_path) == expected_sha256
