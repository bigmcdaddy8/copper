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
from dicks_laboratory.durable_writer import (
    CaptureBackpressureError,
    CaptureWriterError,
    DurableWriter,
    WriterFlushPolicy,
    WriterMetrics,
)
from dicks_laboratory.live_capture import SourceCollector
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
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
    """Deterministic bounded backoff plus two independent safety bounds.

    `max_attempts` bounds *consecutive* failed reconnect attempts within ONE
    outage episode. A successful reconnect (the source genuinely came back and
    `on_connected` fired) closes that episode and restores the full budget --
    so a later, unrelated disconnect after a long healthy stretch gets a fresh
    `max_attempts` tries, never a budget already spent hours earlier (0W-2B
    §2: this is the retry-semantics defect Attempt 2 exposed, where four
    disconnects spread across ~90 minutes each incremented one session-wide
    counter toward exhaustion).

    `max_disconnect_episodes` is the separate anti-flapping circuit breaker:
    it bounds how many distinct outage episodes one trading-date session may
    absorb before it is declared INTERRUPTED, so a connection that keeps
    dropping seconds after every reconnect still terminates (rather than
    looping forever on a perpetually-reset per-episode budget). It is set
    generously -- a handful of spread-out real blips in a full session is
    normal and must not trip it.
    """

    backoff_schedule_seconds: tuple[float, ...] = (1.0, 2.0, 5.0, 10.0, 30.0)
    max_attempts: int = 5
    max_disconnect_episodes: int = 50

    def __post_init__(self) -> None:
        if not self.backoff_schedule_seconds:
            raise ValueError("backoff_schedule_seconds must be non-empty.")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive.")
        if self.max_disconnect_episodes < 1:
            raise ValueError("max_disconnect_episodes must be positive.")

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
    # 0W-2B operational (non-canonical) throughput evidence -- "did persistence
    # keep up?". Defaulted so every existing construction/read path is unchanged.
    writer_flush_count: int = 0
    writer_batch_size_max: int = 0
    writer_queue_depth_max: int = 0
    writer_max_persist_lag_seconds: float = 0.0
    writer_persisted_events: int = 0
    writer_overloaded: bool = False
    # Set only when the SQLite artifact closed cleanly but its sidecar
    # manifest/checksum could not be written (0W-2B §10) -- never rewrites
    # lifecycle_state, never hides a collector failure.
    manifest_error: str | None = None


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
    on_reconnect_attempt: Callable[[int], None] | None = None,
    writer_flush_policy: WriterFlushPolicy = WriterFlushPolicy(),
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
            refresh_collector, on_reconnect_attempt, writer_flush_policy,
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
    on_reconnect_attempt: Callable[[int], None] | None = None,
    writer_flush_policy: WriterFlushPolicy = WriterFlushPolicy(),
) -> tuple[LongHorizonCaptureResult, bool]:
    """Run one dataset's continuous collection, bounded by `segment_deadline`
    (the earlier of this trading date's session close or the overall Human
    deadline). Returns `(result, stop)`; `stop=True` means the caller must
    not continue on to another trading date (deadline reached, INTERRUPTED,
    or an unexpected error).

    0W-2B: raw source events are handed to a `DurableWriter` (bounded queue +
    one dedicated writer thread doing batched SQLite transactions) so the
    feed-reader thread never blocks on synchronous per-event persistence.
    `source_order` is still assigned here, on the feed thread, at the canonical
    ingestion point -- ordering derives from ingestion order, never from writer
    completion order. Every termination path -- clean stop, session close,
    retry exhaustion, backpressure overload, unexpected exception -- lands in
    one common finalization block that always drains the writer, records
    complete disconnect/gap evidence where knowable, finalizes the dataset,
    and writes the manifest/checksum sidecar before re-raising any fatal error.
    """
    database_path, dataset_id, store, resumed = _open_or_resume_dataset(
        data_dir, spec, trading_date, start_time, check_same_thread=False
    )
    source_order_counter = store.max_source_order_for_dataset(dataset_id) + 1
    accepted_count = store.count_trade_observations(dataset_id)
    seen_new_source_indices: set[int] = {
        p.source_index for p in store.load_dxlink_time_and_sale_provenance(dataset_id)
    }

    writer = DurableWriter(
        store,
        dataset_id,
        spec.instrument,
        spec.streamer_symbol,
        start_dataset_sequence=accepted_count + 1,
        seen_new_source_indices=seen_new_source_indices,
        policy=writer_flush_policy,
    )

    # Two independent bounds (0W-2B §2). `consecutive_reconnect_failures` counts
    # failed reconnect attempts *within the current outage episode* and is reset
    # the moment the source genuinely comes back (`on_connected` fires) -- so a
    # disconnect after a long healthy stretch gets a full fresh budget, never a
    # session-wide tally spent hours earlier. `disconnect_episode_count` is the
    # separate anti-flap circuit breaker over the whole trading-date session.
    consecutive_reconnect_failures = 0
    disconnect_episode_count = 0
    total_events_seen = 0
    disconnected_in_loop_at: datetime | None = None
    last_progress_at: datetime | None = None

    def on_connected() -> None:
        nonlocal disconnected_in_loop_at, last_progress_at, consecutive_reconnect_failures
        moment = now()
        last_progress_at = moment
        writer.submit_connected(moment)
        disconnected_in_loop_at = None
        # The source is back: this outage episode is closed. A later, unrelated
        # disconnect starts over with the full `max_attempts` budget. (Pathological
        # connect-then-immediately-drop flapping is bounded separately by
        # `max_disconnect_episodes`, so this reset cannot spin forever.)
        consecutive_reconnect_failures = 0

    def on_event(event) -> None:
        nonlocal source_order_counter, total_events_seen, last_progress_at
        # Assign the canonical ingestion ordinal, then hand off (O(1)). The
        # ordinal is only consumed once the writer has accepted the item, so a
        # backpressure failure leaves `source_order` a clean contiguous prefix.
        writer.submit_event(source_order_counter, event)
        source_order_counter += 1
        total_events_seen += 1
        # "We were still receiving as of this instant" -- on the SAME clock as
        # `now()`, so a terminal synthetic KNOWN_GAP always has a defensible,
        # non-negative interval (0W-2B §8). Cheap: one `now()` per event, feed
        # thread only, no lock, no I/O.
        last_progress_at = now()

    target_state = DatasetLifecycleState.FINALIZED
    stop = False
    terminal_exc: BaseException | None = None
    stopped_reason: str | None = None

    writer.start()
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
                disconnected_in_loop_at = disconnect_moment
                if consecutive_reconnect_failures == 0:
                    disconnect_episode_count += 1  # first failure of a new outage episode
                consecutive_reconnect_failures += 1
                writer.submit_disconnected(
                    consecutive_reconnect_failures,
                    _sanitized_disconnect_detail(
                        consecutive_reconnect_failures, disconnect_episode_count, exc
                    ),
                    disconnect_moment,
                )
                if consecutive_reconnect_failures > reconnect_policy.max_attempts:
                    target_state = DatasetLifecycleState.INTERRUPTED
                    stopped_reason = (
                        "reconnect_retry_budget_exhausted; "
                        f"consecutive_failures={consecutive_reconnect_failures}; "
                        f"episode={disconnect_episode_count}"
                    )
                    stop = True
                    break
                if disconnect_episode_count > reconnect_policy.max_disconnect_episodes:
                    target_state = DatasetLifecycleState.INTERRUPTED
                    stopped_reason = (
                        "disconnect_episode_circuit_breaker; "
                        f"episodes={disconnect_episode_count}"
                    )
                    stop = True
                    break
                backoff = reconnect_policy.backoff_for_attempt(consecutive_reconnect_failures)
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
                    if on_reconnect_attempt is not None:
                        on_reconnect_attempt(consecutive_reconnect_failures)
                    collector = refresh_collector()
                continue
    except KeyboardInterrupt:
        target_state = DatasetLifecycleState.FINALIZED  # deliberate human stop: cleanly closed, not a failure
        stopped_reason = "keyboard_interrupt_clean_stop"
        stop = True
    except CaptureBackpressureError as exc:
        # Controlled overload (0W-2B §13/§27): the bounded queue stayed full past
        # the grace window. No silent drop, no unbounded RAM -- terminate
        # INTERRUPTED and let the truthful evidence below say completeness is
        # no longer assured.
        target_state = DatasetLifecycleState.INTERRUPTED
        stopped_reason = (
            f"writer_backpressure_overload; last_assigned_source_order={source_order_counter - 1}"
        )
        stop = True
        terminal_exc = exc
    except BaseException as exc:  # noqa: BLE001 -- re-raised verbatim after a truthful finalize
        target_state = DatasetLifecycleState.INTERRUPTED
        stopped_reason = f"terminal_exception:{type(exc).__name__}"
        stop = True
        terminal_exc = exc

    # ------------------------------------------------------------------ #
    # Common finalization -- EVERY path above lands here (0W-2B §8, §9). #
    # ------------------------------------------------------------------ #
    close_moment = now()

    try:
        writer_metrics = writer.drain_and_stop()
    except CaptureWriterError as exc:
        writer_metrics = writer.metrics
        target_state = DatasetLifecycleState.INTERRUPTED
        stop = True
        if terminal_exc is None:
            terminal_exc = exc
            stopped_reason = stopped_reason or f"terminal_exception:{type(exc).__name__}"

    # A disconnect recorded in the reconnect loop that never reconnected before
    # the session ended (session close / deadline while down).
    unresolved_disconnect_at = writer.pending_disconnect_at or disconnected_in_loop_at

    # A terminal connection loss that ended the run OUTSIDE the reconnect loop
    # (a raw exception that slipped past `except DxLinkError`) still owes a
    # SOURCE_DISCONNECTED + KNOWN_GAP. Best-defensible gap start = last known
    # progress instant; never a fabricated earlier time (0W-2B §8).
    if (
        unresolved_disconnect_at is None
        and terminal_exc is not None
        and not isinstance(terminal_exc, (CaptureBackpressureError, CaptureWriterError))
        and _looks_like_connection_loss(terminal_exc)
    ):
        gap_start = min(last_progress_at or close_moment, close_moment)
        store.save_quality_events((
            DatasetQualityEvent(
                event_id=uuid5(dataset_id, f"lifecycle:SOURCE_DISCONNECTED:{gap_start.isoformat()}:terminal"),
                dataset_id=dataset_id,
                evidence_type=DatasetQualityEvidenceType.SOURCE_DISCONNECTED,
                detail=_terminal_disconnect_detail(terminal_exc),
                observed_at=gap_start,
            ),
        ))
        unresolved_disconnect_at = gap_start

    # Only a strictly-positive interval is a defensible KNOWN_GAP (the quality
    # model enforces this too). A disconnect at the very close instant -- or with
    # no observed progress to anchor the start -- gets its SOURCE_DISCONNECTED
    # recorded above without a zero-width gap fabricated after it.
    if unresolved_disconnect_at is not None and unresolved_disconnect_at < close_moment:
        _close_known_gap(store, dataset_id, unresolved_disconnect_at, close_moment)

    stopped_detail = "capture_stopped"
    if stopped_reason:
        stopped_detail += f"; reason={stopped_reason}"
    stopped_detail += f"; {writer_metrics.as_detail_suffix()}"

    _finalize(
        store, dataset_id, close_moment, writer.classifications,
        collector_version, collector_git_commit, target_state, stopped_detail=stopped_detail,
    )

    manifest_error: str | None = None
    try:
        result = _build_result(
            store, dataset_id, database_path, spec.instrument, trading_date, target_state,
            writer_metrics=writer_metrics,
        )
    except Exception as exc:  # noqa: BLE001 -- the sidecar is convenience only (0W-2B §10)
        manifest_error = f"{type(exc).__name__}: {exc}"
        result = _build_result(
            store, dataset_id, database_path, spec.instrument, trading_date, target_state,
            writer_metrics=writer_metrics, skip_manifest=True, manifest_error=manifest_error,
        )

    store.close()

    if terminal_exc is not None:
        # Preserve the original failure for process-exit / result semantics --
        # the dataset is already truthfully INTERRUPTED with complete evidence
        # and (where possible) a manifest.
        raise terminal_exc

    if target_state is DatasetLifecycleState.INTERRUPTED or close_moment >= overall_deadline:
        stop = True
    return result, stop


_CONNECTION_LOSS_MARKERS: tuple[str, ...] = (
    "connectionclosed",
    "connection closed",
    "connection reset",
    "broken pipe",
    "keepalive ping timeout",
    "connection error while receiving",
    "connection error while sending",
    "timed out",
)


def _looks_like_connection_loss(exc: BaseException) -> bool:
    """True when a terminal exception is a lost source connection (so it still
    owes SOURCE_DISCONNECTED + KNOWN_GAP evidence), not a local defect."""
    if isinstance(exc, DxLinkError):
        return True
    text = f"{type(exc).__name__}: {exc}".lower()
    return any(marker in text for marker in _CONNECTION_LOSS_MARKERS)


def _terminal_disconnect_detail(exc: BaseException) -> str:
    """Sanitized SOURCE_DISCONNECTED detail for a connection loss that ended the
    run outside the numbered reconnect attempts (0W-2B §8). Same secret-free
    shape as `_sanitized_disconnect_detail`, with `attempt=terminal`."""
    reason = " ".join(str(exc).split())[:200] or type(exc).__name__
    stage = _classify_failure_stage(reason)
    return f"source_disconnected; attempt=terminal; stage={stage}; error={reason}"


_FAILURE_STAGE_MARKERS: tuple[tuple[str, str], ...] = (
    ("AUTHORIZED", "DXLINK_AUTH"),
    ("SETUP", "DXLINK_SETUP"),
    ("CHANNEL_OPENED", "CHANNEL_REQUEST"),
    ("FEED_CONFIG", "FEED_SETUP"),
    ("timed out", "SOCKET_RECEIVE"),
    ("invalid json", "SOCKET_RECEIVE"),
    ("non-object json", "SOCKET_RECEIVE"),
    ("connection error while receiving", "SOCKET_RECEIVE"),
    ("connection error while sending", "SOCKET_SEND"),
    ("keepalive ping timeout", "SOCKET_KEEPALIVE"),
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


def _sanitized_disconnect_detail(attempt: int, episode: int, exc: DxLinkError) -> str:
    """Safe structured reconnect-failure detail: the within-episode attempt
    number (resets to 1 for each new outage -- 0W-2B §2), the session-wide
    outage-episode number, a best-effort stage, and the exception's own
    (secret-free) message -- never the socket, a header, or a token."""
    reason = " ".join(str(exc).split())[:200]
    stage = _classify_failure_stage(reason)
    return (
        f"source_disconnected; attempt={attempt}; episode={episode}; "
        f"stage={stage}; error={reason}"
    )


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
    check_same_thread: bool = True,
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
                        store = LaboratoryStore(candidate, check_same_thread=check_same_thread)
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
    store = LaboratoryStore(database_path, check_same_thread=check_same_thread)
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
    stopped_detail: str = "capture_stopped",
) -> None:
    """Close a dataset intentionally, recording exactly the requested closure
    state -- never silently defaulting to FINALIZED regardless of intent
    (a prior version of this function did exactly that, masking the real
    lifecycle_state of an INTERRUPTED dataset in the database itself).

    `stopped_detail` carries the sanitized closure reason plus operational
    writer metrics (0W-2B §22) so a future soak can answer "did persistence
    keep up?" from the dataset alone."""
    store.save_quality_events((
        DatasetQualityEvent(
            event_id=uuid5(dataset_id, f"lifecycle:CAPTURE_STOPPED:{closed_at.isoformat()}"),
            dataset_id=dataset_id, evidence_type=DatasetQualityEvidenceType.CAPTURE_STOPPED,
            detail=stopped_detail, observed_at=closed_at,
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
    accepted_trade_count = store.count_trade_observations(dataset_id)
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
            accepted_trade_count=accepted_trade_count,
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
    writer_metrics: WriterMetrics | None = None,
    skip_manifest: bool = False,
    manifest_error: str | None = None,
) -> LongHorizonCaptureResult:
    summary = store.load_dataset_closing_summary(dataset_id)
    quality_events = store.load_quality_events(dataset_id)
    reconnect_count = sum(
        1 for event in quality_events if event.evidence_type is DatasetQualityEvidenceType.SOURCE_RECONNECTED
    )
    metrics = writer_metrics or WriterMetrics()
    checksum, manifest_path = None, None
    # The SHA-256 + manifest sidecar is now written for EVERY cleanly-closed
    # artifact -- FINALIZED, retry-exhaustion INTERRUPTED, or crash-finalized
    # INTERRUPTED (0W-2B §9). `skip_manifest` is only ever set on the fallback
    # path after the sidecar write itself failed (0W-2B §10) -- the dataset
    # state and the original error are never rewritten to make one appear.
    if database_path.exists() and not skip_manifest:
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
        writer_flush_count=metrics.flush_count,
        writer_batch_size_max=metrics.batch_size_max,
        writer_queue_depth_max=metrics.queue_depth_max,
        writer_max_persist_lag_seconds=metrics.max_persist_lag_seconds,
        writer_persisted_events=metrics.persisted_events,
        writer_overloaded=metrics.overloaded,
        manifest_error=manifest_error,
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
