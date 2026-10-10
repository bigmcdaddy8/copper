"""MARKET_STUDY_SNAPSHOT_V1: deterministic as-of market study snapshots from a recorded dataset (0Z-B).

MARKET-TIME CUTOFF != FEED-KNOWLEDGE CUTOFF.

- A source record (accepted NEW trade, deferred CORRECTION / CANCEL, rejected record) is
  KNOWN at a cutoff iff `received_at < knowledge_time_cutoff_utc` (strict) and, when a
  source-order cursor is set, `source_order <= knowledge_source_order_cutoff`.
- The accepted effective-tape reconstruction (0K6) then applies only the KNOWN records,
  in source order. A correction or cancel received later is never applied backward.
- A known effective trade enters market analytics iff `event_timestamp <
  market_time_cutoff_utc` (strict; every study window is half-open [start, end)).
  A record with a future market timestamp is known but excluded.
- Lifecycle point evidence is known iff `observed_at < knowledge cutoff`. A KNOWN /
  SUSPECTED gap interval is known iff `interval_end < knowledge cutoff` (the collector
  writes it at reconnect or close). An unresolved SOURCE_DISCONNECTED is an ACTIVE
  INTERRUPTION [disconnect, knowledge cutoff).
- Maturity uses the effective clock `min(market cutoff, knowledge cutoff)`.

Every snapshot runs the accepted derivation (`derive_tpo_analysis`, the accepted opening /
overnight / OPENING_TYPE_V1 builders) over that as-of view, then exposes each component
only at its maturity. Final-study components (TPO structure, DAY_TYPE_V1,
DAY_STRUCTURE_STRENGTH_V1, terminal price) are NOT_YET_DETERMINED before 15:00 CT;
OPENING_TYPE_V1 before 09:30 CT. MARKET_STUDY_STATE_V1 is not changed.

Read-only: the database is opened read-only once (`prepare_replay`); snapshots are pure.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from dicks_laboratory import market_study_state as mss
from dicks_laboratory.analysis import (
    AnchorCoverage,
    LaboratoryAnalysisError,
    determine_dataset_trading_dates,
    open_dataset_store,
    resolve_dataset_id,
)
from dicks_laboratory.anchored_vwap import VwapSourceMode, calculate_anchored_vwap
from dicks_laboratory.dataset_state import DatasetClosingSummary
from dicks_laboratory.effective_tape import EffectiveTapeResult, _source_timestamp, reconstruct_effective_tape
from dicks_laboratory.market_study_state import (
    AnalysisProvenance,
    ComponentStatus,
    ContractSection,
    DatasetSource,
    DayStrengthSection,
    DayTypeSection,
    GapInterval,
    OpeningTypeSection,
    PolicyEntry,
    PriorDaySection,
    StudyInputs,
    TpoStructureSection,
    VolumeProfileSection,
    VwapStudy,
)
from dicks_laboratory.models import DatasetIdentity, InstrumentIdentity, TradeObservation
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.sessions import AnchorKind, SessionState, classify_es_session, resolve_anchor, session_coverage
from dicks_laboratory.tpo_analysis import (
    QualityStatus,
    TpoAnalysisResult,
    build_prior_context,
    dataset_quality_from_evidence,
    derive_tpo_analysis,
    opening_type_classification,
)
from dicks_laboratory.tpo_opening import (
    CASH_OPEN_MAX_DELAY,
    OPENING_WINDOW_MINUTES,
    CashOpen,
    OpeningAuctionFacts,
    OpeningWindowFacts,
    RangeLocation,
    Side,
    ValueLocation,
    _locate,
    _path,
    _ticks,
    _window,
    cash_open_utc,
)
from dicks_laboratory.tpo_opening_path import OpeningPathFacts
from dicks_laboratory.tpo_overnight import (
    OvernightContext,
    OvernightSession,
    build_overnight_session,
    overnight_window_utc,
)
from dicks_laboratory.tpo_profile import INITIAL_BALANCE_MINUTES, US_CASH_PROFILE, TpoProfile
from dicks_laboratory.volume_profile import price_grid_for_instrument

SNAPSHOT_SCHEMA = "MARKET_STUDY_SNAPSHOT_V1"  # a breaking semantic change is MARKET_STUDY_SNAPSHOT_V2
SNAPSHOT_HASH_FIELD = "market_study_snapshot_sha256"
TEMPORALITY_NOTE = ("AS_OF evidence: only source records received before the knowledge cutoff, and only market "
                    "activity before the market cutoff. Later evidence, final metadata and final-study labels are "
                    "absent or NOT_YET_DETERMINED.")
CUTOFF_SEMANTICS = (
    "KNOWLEDGE: a source record is known iff received_at < knowledge_time_cutoff_utc and, when set, "
    "source_order <= knowledge_source_order_cutoff",
    "CORRECTION/CANCEL: applied only when itself known, in source_order, by the accepted effective-tape "
    "reconstruction; never backward",
    "MARKET: a known effective trade is included iff event_timestamp < market_time_cutoff_utc; windows are "
    "half-open [start, end)",
    "LIFECYCLE: point evidence is known iff observed_at < knowledge cutoff; a gap interval is known iff "
    "interval_end < knowledge cutoff; an unresolved disconnect is an ACTIVE_INTERRUPTION up to the knowledge cutoff",
    "MATURITY: judged at the effective clock min(market cutoff, knowledge cutoff)",
)


class SnapshotTemporality(StrEnum):
    AS_OF = "AS_OF"


class Maturity(StrEnum):
    NOT_YET_AVAILABLE = "NOT_YET_AVAILABLE"  # its window / anchor has not begun at the effective clock
    DEVELOPING = "DEVELOPING"  # its window is in progress: values cover [start, clock)
    WINDOW_COMPLETE = "WINDOW_COMPLETE"  # its market window ended before the clock (late receipts may still revise)
    NOT_YET_DETERMINED = "NOT_YET_DETERMINED"  # a final-study component before its window completes
    NOT_AVAILABLE = "NOT_AVAILABLE"  # its window passed without the evidence it needs


class CaptureStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    STOPPED = "STOPPED"
    UNRECORDED = "UNRECORDED"  # legacy dataset: no capture start recorded


class ConnectionState(StrEnum):
    NOT_CONNECTED = "NOT_CONNECTED"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"  # an active interruption at the cutoff
    STOPPED = "STOPPED"
    UNRECORDED = "UNRECORDED"


class Visibility(StrEnum):
    VISIBLE = "VISIBLE"
    VISIBLE_CORRECTED = "VISIBLE_CORRECTED"
    NOT_YET_RECEIVED = "NOT_YET_RECEIVED"
    BEYOND_SOURCE_ORDER_CUTOFF = "BEYOND_SOURCE_ORDER_CUTOFF"
    MARKET_TIME_AT_OR_AFTER_CUTOFF = "MARKET_TIME_AT_OR_AFTER_CUTOFF"
    CANCELED_AS_OF = "CANCELED_AS_OF"
    OUTSIDE_TRADING_DATE_SESSION = "OUTSIDE_TRADING_DATE_SESSION"
    APPLIED = "APPLIED"  # a known correction / cancel the reconstruction applied
    ANOMALY = "ANOMALY"  # a known correction / cancel the reconstruction could not apply
    NOT_DUPLICATED = "NOT_DUPLICATED"  # a known NEW record dropped by the reconstruction (duplicate index)


# --- cutoff ------------------------------------------------------------------------------------

def _utc(ts: datetime, name: str) -> datetime:
    if ts.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")
    return ts.astimezone(timezone.utc)


@dataclass(frozen=True)
class ReplayCutoff:
    """Two separate semantic clocks (plus an optional source-order cursor). Canonical in UTC."""

    market_time_cutoff_utc: datetime
    knowledge_time_cutoff_utc: datetime
    knowledge_source_order_cutoff: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "market_time_cutoff_utc", _utc(self.market_time_cutoff_utc, "market cutoff"))
        object.__setattr__(self, "knowledge_time_cutoff_utc",
                           _utc(self.knowledge_time_cutoff_utc, "knowledge cutoff"))

    @classmethod
    def at(cls, instant: datetime, source_order: int | None = None) -> ReplayCutoff:
        """Ordinary historical replay: both clocks at the same wall-clock instant."""
        return cls(instant, instant, source_order)

    @property
    def clock(self) -> datetime:
        """Effective maturity clock: nothing received after the knowledge cutoff can be used."""
        return min(self.market_time_cutoff_utc, self.knowledge_time_cutoff_utc)

    def knows(self, received_at: datetime | None, source_order: int) -> bool:
        if received_at is None or received_at >= self.knowledge_time_cutoff_utc:
            return False
        return self.knowledge_source_order_cutoff is None or source_order <= self.knowledge_source_order_cutoff

    def in_market(self, ts: datetime) -> bool:
        return ts < self.market_time_cutoff_utc


# --- prepared evidence (loaded once) -------------------------------------------------------------

@dataclass(frozen=True)
class PreparedReplay:
    """Everything durable about one dataset, loaded once read-only. Snapshots filter it; never mutate it."""

    dataset: DatasetIdentity
    trading_date: date
    recorded_trading_date: date | None
    instrument: InstrumentIdentity
    canonical_trades: tuple[TradeObservation, ...]
    provenance: tuple  # DxLinkTimeAndSaleProvenance, source order
    deferred: tuple  # DeferredDxLinkTimeAndSale
    rejected: tuple[tuple[int, datetime | None], ...]  # (source_order, received_at or None)
    quality_events: tuple[DatasetQualityEvent, ...]
    stored_lifecycle_state: str | None
    closing_summary: DatasetClosingSummary | None
    in_scope_ids: frozenset  # NEW observation ids inside the trading-date session (original timestamps)
    database_sha256: str  # replay-input identity; NOT part of any snapshot (final-file property)

    @property
    def dataset_id(self) -> UUID:
        return self.dataset.dataset_id


def prepare_replay(database: Path, dataset_id: UUID | None = None) -> PreparedReplay:
    store = open_dataset_store(database)
    try:
        resolved = resolve_dataset_id(store, dataset_id)
        dataset = store.load_dataset(resolved)
        recorded_date, recorded_instrument = store.load_dataset_trading_context(resolved)
        lifecycle = store.load_dataset_lifecycle_state(resolved)
        summary = store.load_dataset_closing_summary(resolved)
        trades = store.load_trade_observations(resolved)
        provenance = store.load_dxlink_time_and_sale_provenance(resolved)
        deferred = store.load_deferred_dxlink_time_and_sales(resolved)
        rejected_records = {r.rejection_id: r for r in store.load_rejected_dxlink_time_and_sale_source_records(resolved)}
        rejections = store.load_rejections(resolved)
        events = store.load_quality_events(resolved)
    finally:
        store.close()
    if not trades:
        raise LaboratoryAnalysisError("Dataset has no canonical NEW trade observations to replay.")
    instruments = {t.instrument.canonical_id for t in trades}
    if len(instruments) > 1:
        raise LaboratoryAnalysisError(f"Dataset spans multiple instruments; unsupported: {sorted(instruments)}")
    dates = determine_dataset_trading_dates(trades)
    trading_date = recorded_date or (dates[0] if len(dates) == 1 else None)
    if trading_date is None:
        raise LaboratoryAnalysisError(f"Cannot determine one trading date: {dates}")
    in_scope = frozenset(t.observation_id for t in trades if _in_session(t.event_timestamp, trading_date))
    rejected = tuple(sorted(
        (r.source_order, rejected_records[r.rejection_id].source_record.received_at
         if r.rejection_id in rejected_records else None) for r in rejections))
    return PreparedReplay(
        dataset=dataset, trading_date=trading_date, recorded_trading_date=recorded_date,
        instrument=recorded_instrument or trades[0].instrument, canonical_trades=trades,
        provenance=tuple(sorted(provenance, key=lambda p: (p.source_order, p.source_index))),
        deferred=tuple(sorted(deferred, key=lambda d: d.source_order)), rejected=rejected,
        quality_events=events, stored_lifecycle_state=lifecycle.value if lifecycle else None,
        closing_summary=summary, in_scope_ids=in_scope, database_sha256=mss.file_sha256(database))


def _in_session(ts: datetime, trading_date: date) -> bool:
    membership = classify_es_session(ts)
    return membership.state is SessionState.IN_SESSION and membership.trading_date == trading_date


# --- as-of evidence ------------------------------------------------------------------------------

@dataclass(frozen=True)
class AsOfEvidence:
    """The view of the dataset a Laboratory had at the cutoff (internal; not serialized)."""

    cutoff: ReplayCutoff
    tape: EffectiveTapeResult  # reconstruction over KNOWN records only
    scoped: tuple  # known effective trades in the trading-date session with market time < cutoff
    known_canonical_first: datetime | None
    known_canonical_last: datetime | None
    point_events: tuple[DatasetQualityEvent, ...]
    gap_events: tuple[DatasetQualityEvent, ...]  # known intervals + an active interruption, if any
    active_interruption: GapInterval | None
    capture_status: CaptureStatus
    capture_started_at: datetime | None
    capture_ended_at: datetime | None  # only once the stop is known
    capture_through: datetime | None  # end bound handed to accepted quality rules
    lifecycle_as_of: str
    lifecycle_for_rules: str | None
    connection: ConnectionState
    known_provenance: int
    known_deferred: tuple
    known_rejected: int
    rejected_time_unrecorded: int
    future_market_known: int  # known records whose market time is at/after the market cutoff


def as_of_evidence(prep: PreparedReplay, cutoff: ReplayCutoff) -> AsOfEvidence:
    k = cutoff.knowledge_time_cutoff_utc
    prov = tuple(p for p in prep.provenance if cutoff.knows(p.received_at, p.source_order))
    deferred = tuple(d for d in prep.deferred if cutoff.knows(d.source_record.received_at, d.source_order))
    tape = reconstruct_effective_tape(prep.canonical_trades, prov, deferred)
    scoped = tuple(t for t in tape.effective_trades if cutoff.in_market(t.event_timestamp) and (
        t.original_observation_id in prep.in_scope_ids if t.correction_count == 0
        else _in_session(t.event_timestamp, prep.trading_date)))
    by_id = {t.observation_id: t for t in prep.canonical_trades}
    known_times = [by_id[p.observation_id].event_timestamp for p in prov if p.observation_id in by_id]
    in_market = [ts for ts in known_times if cutoff.in_market(ts)]

    points = tuple(sorted((e for e in prep.quality_events if e.observed_at is not None and e.observed_at < k),
                          key=lambda e: (e.observed_at, e.event_id)))
    gap_types = {DatasetQualityEvidenceType.KNOWN_GAP, DatasetQualityEvidenceType.SUSPECTED_GAP}
    gaps = [e for e in prep.quality_events if e.evidence_type in gap_types and e.interval_end < k]
    connection, disconnected_at = ConnectionState.UNRECORDED, None
    for e in points:
        t = e.evidence_type
        if t in (DatasetQualityEvidenceType.SOURCE_CONNECTED, DatasetQualityEvidenceType.SOURCE_RECONNECTED):
            connection, disconnected_at = ConnectionState.CONNECTED, None
        elif t is DatasetQualityEvidenceType.SOURCE_DISCONNECTED:
            connection, disconnected_at = ConnectionState.DISCONNECTED, e.observed_at
        elif t is DatasetQualityEvidenceType.CAPTURE_STOPPED:
            connection, disconnected_at = ConnectionState.STOPPED, None
        elif t is DatasetQualityEvidenceType.CAPTURE_STARTED and connection is ConnectionState.UNRECORDED:
            connection = ConnectionState.NOT_CONNECTED
    active = None
    if disconnected_at is not None and disconnected_at < k and not any(
            g.interval_start == disconnected_at for g in gaps):
        active = GapInterval("ACTIVE_INTERRUPTION", disconnected_at, k)
        gaps.append(DatasetQualityEvent(
            UUID(int=0), prep.dataset_id, DatasetQualityEvidenceType.KNOWN_GAP,
            "ACTIVE_INTERRUPTION as of the knowledge cutoff", interval_start=disconnected_at, interval_end=k))

    d = prep.dataset
    started = d.capture_started_at if d.capture_started_at is not None and d.capture_started_at < k else None
    stop_known = any(e.evidence_type is DatasetQualityEvidenceType.CAPTURE_STOPPED for e in points) or (
        d.capture_ended_at is not None and d.capture_ended_at < k)
    if d.capture_started_at is None:
        status, lifecycle = CaptureStatus.UNRECORDED, prep.stored_lifecycle_state or "UNTRACKED"
        lifecycle_rules, ended, through = prep.stored_lifecycle_state, d.capture_ended_at, d.capture_ended_at
    elif started is None:
        status, lifecycle, lifecycle_rules, ended, through = CaptureStatus.NOT_STARTED, "NOT_STARTED", "OPEN", None, None
    elif stop_known:
        status, lifecycle = CaptureStatus.STOPPED, prep.stored_lifecycle_state or "UNTRACKED"
        lifecycle_rules, ended, through = prep.stored_lifecycle_state, d.capture_ended_at, d.capture_ended_at
    else:
        status, lifecycle, lifecycle_rules = CaptureStatus.RUNNING, "OPEN_AS_OF", "OPEN"
        ended = None
        through = None if d.capture_ended_at is None else min(k, d.capture_ended_at)
    rejected_known = sum(1 for order, received in prep.rejected if cutoff.knows(received, order))
    return AsOfEvidence(
        cutoff=cutoff, tape=tape, scoped=scoped,
        known_canonical_first=min(in_market, default=None), known_canonical_last=max(in_market, default=None),
        point_events=points, gap_events=tuple(sorted(gaps, key=lambda e: (e.interval_start, e.interval_end))),
        active_interruption=active, capture_status=status, capture_started_at=started, capture_ended_at=ended,
        capture_through=through, lifecycle_as_of=lifecycle, lifecycle_for_rules=lifecycle_rules,
        connection=connection, known_provenance=len(prov), known_deferred=deferred, known_rejected=rejected_known,
        rejected_time_unrecorded=sum(1 for _, received in prep.rejected if received is None),
        future_market_known=len(known_times) - len(in_market))


def as_of_result(prep: PreparedReplay, ev: AsOfEvidence) -> TpoAnalysisResult:
    """The accepted derivation over the as-of tape and as-of quality evidence."""
    start, end = US_CASH_PROFILE.bounds_utc(prep.trading_date)
    quality = dataset_quality_from_evidence(ev.point_events + ev.gap_events, ev.capture_started_at,
                                            ev.capture_through, ev.lifecycle_for_rules, start, end)
    return derive_tpo_analysis(prep.dataset_id, prep.instrument, prep.trading_date, ev.scoped, quality,
                               ev.tape.applied_correction_count, ev.tape.applied_cancel_count)


# --- snapshot sections ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AsOfCounts:
    source_records_known: int
    accepted_known: int
    rejected_known: int
    rejected_knowledge_time_unrecorded: int
    deferred_known: int
    corrections_known: int
    cancels_known: int
    corrections_applied: int
    cancels_applied: int
    reconstruction_anomalies: int
    effective_trades_in_session_before_market_cutoff: int
    known_records_with_market_time_at_or_after_cutoff: int


@dataclass(frozen=True)
class DatasetAsOf:
    dataset_id: UUID
    trading_date: date
    recorded_trading_date: date | None
    instrument_id: str
    kind: str
    origin: str
    label: str
    source_locator: str | None
    source_system: str | None
    streamer_symbol: str | None
    normalizer_version: str | None
    collector_version: str | None  # collector code identity (constant over the capture)
    collector_git_commit: str | None
    capture_status: CaptureStatus
    capture_started_at: datetime | None
    capture_ended_at: datetime | None  # null until the stop is known
    lifecycle_as_of: str  # NOT_STARTED / OPEN_AS_OF / the stored final state once the stop is known
    connection_as_of: ConnectionState
    lifecycle_evidence_known: tuple[tuple[str, datetime], ...]
    counts: AsOfCounts
    closing_summary_maturity: Maturity
    closing_summary: DatasetClosingSummary | None
    closing_accounting_difference: int | None


@dataclass(frozen=True)
class WindowCoverageAsOf:
    window: str
    start_utc: datetime
    end_utc: datetime
    maturity: Maturity
    captured_through_clock: bool | None  # capture started by the window start and still covering [start, clock)
    known_gaps_overlapping: int
    suspected_gaps_overlapping: int


@dataclass(frozen=True)
class QualityAsOf:
    status: ComponentStatus
    reasons: tuple[str, ...]
    completeness: QualityStatus
    known_gap_count: int
    suspected_gap_count: int
    known_gap_duration: timedelta
    gaps: tuple[GapInterval, ...]  # intervals known by the knowledge cutoff
    active_interruption: GapInterval | None
    windows: tuple[WindowCoverageAsOf, ...]


@dataclass(frozen=True)
class MaturityEntry:
    component: str
    maturity: Maturity
    matures_at_utc: datetime | None  # market instant at which the component's window completes


@dataclass(frozen=True)
class SnapshotVwap:
    anchor_kind: AnchorKind
    anchor_utc: datetime
    maturity: Maturity
    status: ComponentStatus
    reasons: tuple[str, ...]
    study: VwapStudy | None  # the accepted study over trades in [anchor, market cutoff)


@dataclass(frozen=True)
class TpoAsOfSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    window_id: str
    window_policy_version: str
    period_minutes: int
    periods_reached: str  # letters of periods begun before the clock; no future period exists
    current_period: str | None  # the period containing the clock (partially developed), if any
    initial_balance_maturity: Maturity
    profile: TpoProfile | None  # value area / POC DEVELOPING until 15:00 CT


@dataclass(frozen=True)
class PricesAsOf:
    last_known_price: Decimal | None  # last known effective trading-date-session trade before the cutoff
    last_known_utc: datetime | None
    study_window_terminal_maturity: Maturity
    study_window_terminal_price: Decimal | None  # only when the 15:00 CT window is complete


@dataclass(frozen=True)
class OvernightDeveloping:
    first_observed_price: Decimal | None
    first_observed_utc: datetime | None
    high: Decimal | None
    low: Decimal | None
    range_ticks: int | None
    time_of_high_utc: datetime | None
    time_of_low_utc: datetime | None
    last_price: Decimal | None
    last_utc: datetime | None


@dataclass(frozen=True)
class OvernightAsOfSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    globex_open_claimed: bool
    globex_open_boundary_proven: bool
    first_observed_overnight_trade_is_globex_open: bool
    developing: OvernightDeveloping | None  # while [17:00, 08:30) is in progress
    session: OvernightSession | None  # accepted object, once the window is complete
    context: OvernightContext | None  # once the window is complete and the cash open is known


@dataclass(frozen=True)
class OpeningWindowAsOf:
    minutes: int
    end_utc: datetime
    maturity: Maturity
    facts: OpeningWindowFacts | None  # only when the window is complete


@dataclass(frozen=True)
class CashOpeningAsOfSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    cash_open_maturity: Maturity
    cash_open: CashOpen | None
    range_location: RangeLocation | None
    value_location: ValueLocation | None
    gap_points: Decimal | None
    gap_ticks: int | None
    gap_direction: Side | None
    windows: tuple[OpeningWindowAsOf, ...]
    facts: OpeningAuctionFacts | None  # full OPENING_AUCTION_FACTS_V1 once 09:30 CT is reached
    path_facts: OpeningPathFacts | None  # OPENING_PATH_FACTS_V1 once 09:30 CT is reached
    fields_developing_until_study_window_end: tuple[str, ...]  # JSON pointers still DEVELOPING before 15:00 CT


@dataclass(frozen=True)
class SnapshotQualityEntry:
    component: str
    maturity: Maturity
    status: ComponentStatus
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class MarketStudySnapshot:
    """MARKET_STUDY_SNAPSHOT_V1 payload. Its hash is attached only at serialization."""

    schema: str
    state_temporality: SnapshotTemporality
    temporality_note: str
    cutoff: ReplayCutoff
    cutoff_semantics: tuple[str, ...]
    provenance: AnalysisProvenance
    current_dataset: DatasetAsOf
    contract: ContractSection
    dataset_quality: QualityAsOf
    maturity: tuple[MaturityEntry, ...]
    vwap: tuple[SnapshotVwap, ...]
    volume_profile: VolumeProfileSection
    tpo: TpoAsOfSection
    tpo_structure: TpoStructureSection
    day_type: DayTypeSection
    day_strength: DayStrengthSection
    prices: PricesAsOf
    prior_day: PriorDaySection
    overnight: OvernightAsOfSection
    cash_opening: CashOpeningAsOfSection
    opening_type: OpeningTypeSection
    policy_registry: tuple[PolicyEntry, ...]
    quality_matrix: tuple[SnapshotQualityEntry, ...]


# Fields of OPENING_AUCTION_FACTS_V1 / OPENING_PATH_FACTS_V1 / OPENING_TYPE_V1 that read the cash profile or
# path after 09:30 CT. Between 09:30 and 15:00 CT they are DEVELOPING values over [08:30, clock).
OPENING_FIELDS_DEVELOPING_UNTIL_STUDY_WINDOW_END = (
    "/cash_opening/facts/session/quality/gaps_later_in_study_window",
    "/cash_opening/facts/session/quality/study_window_truncated",
    "/cash_opening/facts/session/early_tpo/a_only_rows_full_day",
    "/cash_opening/facts/session/early_tpo/a_only_rows_at_day_high",
    "/cash_opening/facts/session/early_tpo/a_only_rows_at_day_low",
    "/cash_opening/facts/session/one_timeframing",
    "/cash_opening/facts/value_zone/first_entry_utc",
    "/cash_opening/facts/value_zone/first_exit_above_utc",
    "/cash_opening/facts/value_zone/first_exit_below_utc",
    "/cash_opening/facts/value_zone/first_return_utc",
    "/cash_opening/facts/value_zone/time_to_return",
    "/cash_opening/facts/range_zone/first_entry_utc",
    "/cash_opening/facts/range_zone/first_exit_above_utc",
    "/cash_opening/facts/range_zone/first_exit_below_utc",
    "/cash_opening/facts/range_zone/first_return_utc",
    "/cash_opening/facts/range_zone/time_to_return",
    "/opening_type/classification/strength/opening_higher_low_run",
    "/opening_type/classification/strength/opening_lower_high_run",
)


# --- builder -------------------------------------------------------------------------------------

def _window_maturity(start: datetime, end: datetime, clock: datetime) -> Maturity:
    if clock <= start:
        return Maturity.NOT_YET_AVAILABLE
    return Maturity.WINDOW_COMPLETE if clock >= end else Maturity.DEVELOPING


def _developing_status(ev: AsOfEvidence, start: datetime, clock: datetime) -> tuple[ComponentStatus, tuple[str, ...]]:
    """Quality of a partial window [start, clock): gaps known by the cutoff and the capture start only."""
    reasons = []
    if ev.capture_status is CaptureStatus.UNRECORDED:
        reasons.append("capture interval not recorded; coverage unverified")
    elif ev.capture_started_at is not None and ev.capture_started_at > start:
        reasons.append(f"capture began {ev.capture_started_at - start} after the window start")
    for kind in ("KNOWN_GAP", "SUSPECTED_GAP"):
        n = sum(1 for g in ev.gap_events if g.evidence_type.value == kind and g.interval_start < clock
                and g.interval_end > start)
        if n:
            reasons.append(f"{kind} overlaps [window start, clock): {n}"
                           + (" (includes the ACTIVE_INTERRUPTION)" if ev.active_interruption is not None and
                              kind == "KNOWN_GAP" and ev.active_interruption.start_utc < clock else ""))
    if ev.capture_status is CaptureStatus.STOPPED and ev.lifecycle_as_of != "FINALIZED":
        reasons.append(f"lifecycle {ev.lifecycle_as_of} (not FINALIZED)")
    return (ComponentStatus.QUALITY_QUALIFIED if reasons else ComponentStatus.AVAILABLE), tuple(reasons)


def _nyd(why: str) -> tuple[ComponentStatus, tuple[str, ...]]:
    return ComponentStatus.NOT_AVAILABLE, (f"NOT_YET_DETERMINED: {why}",)


def build_snapshot(
    prep: PreparedReplay,
    prior: StudyInputs | None,
    cutoff: ReplayCutoff,
    provenance: AnalysisProvenance,
    closures: frozenset[date] = frozenset(),
) -> MarketStudySnapshot:
    """Pure: the as-of view of `prep` at `cutoff`, exposed by component maturity."""
    ev = as_of_evidence(prep, cutoff)
    r = as_of_result(prep, ev)
    td, clock = prep.trading_date, cutoff.clock
    grid = price_grid_for_instrument(prep.instrument)
    session_open = resolve_anchor(AnchorKind.SESSION_OPEN, td).anchor_timestamp_utc
    cash_open = cash_open_utc(td)
    cash_end = r.window_end_utc
    ib_end = cash_open + timedelta(minutes=INITIAL_BALANCE_MINUTES)
    session_end = session_coverage((), td).session_end_utc
    on_start, on_end = overnight_window_utc(td)
    final_study = clock >= cash_end

    prior_known = prior is not None and _prior_known(prior.source, cutoff, session_open)
    candidates = (prior.result,) if prior_known else ()
    classification = opening_type_classification(r, candidates, closures)
    path_facts = classification.facts if classification else None
    opening_facts = path_facts.opening if path_facts else None
    prior_ctx = opening_facts.prior if opening_facts else build_prior_context(r, candidates, closures)

    cash_m = _window_maturity(cash_open, cash_end, clock)
    maturity = (
        MaturityEntry("closing_summary", _closing_maturity(prep, ev, cutoff), None),
        MaturityEntry("vwap SESSION_OPEN", _window_maturity(session_open, session_end, clock), session_end),
        MaturityEntry("vwap US_CASH_OPEN", _window_maturity(cash_open, session_end, clock), session_end),
        MaturityEntry("overnight", _window_maturity(on_start, on_end, clock), on_end),
        MaturityEntry("cash_open", Maturity.NOT_YET_AVAILABLE, cash_open + CASH_OPEN_MAX_DELAY),  # replaced below
        MaturityEntry("opening_facts", _final_at(cash_open, ib_end, clock), ib_end),
        MaturityEntry("opening_type", _final_at(cash_open, ib_end, clock), ib_end),
        MaturityEntry("volume_profile", cash_m, cash_end),
        MaturityEntry("tpo", cash_m, cash_end),
        MaturityEntry("initial_balance", _window_maturity(cash_open, ib_end, clock), ib_end),
        MaturityEntry("tpo_structure", _final_at(cash_open, cash_end, clock), cash_end),
        MaturityEntry("day_type", _final_at(cash_open, cash_end, clock), cash_end),
        MaturityEntry("day_strength", _final_at(cash_open, cash_end, clock), cash_end),
        MaturityEntry("study_window_terminal", _final_at(cash_open, cash_end, clock), cash_end),
    )
    cash_opening = _cash_opening(ev, r, clock, cash_open, ib_end, final_study, opening_facts, path_facts,
                                 prior_ctx, grid)
    maturity = tuple(dataclasses.replace(m, maturity=cash_opening.cash_open_maturity) if m.component == "cash_open"
                     else m for m in maturity)
    m = {e.component: e.maturity for e in maturity}

    snapshot = MarketStudySnapshot(
        schema=SNAPSHOT_SCHEMA,
        state_temporality=SnapshotTemporality.AS_OF,
        temporality_note=TEMPORALITY_NOTE,
        cutoff=cutoff,
        cutoff_semantics=CUTOFF_SEMANTICS,
        provenance=provenance,
        current_dataset=_dataset_as_of(prep, ev, cutoff, m["closing_summary"]),
        contract=mss._contract(r, SimpleNamespace(streamer_symbol=_streamer(prep)), grid),
        dataset_quality=_quality_as_of(prep, ev, r, clock, cash_open, cash_end, ib_end, on_start, on_end),
        maturity=maturity,
        vwap=tuple(_vwap(prep, ev, r, kind, clock, session_end) for kind in (AnchorKind.SESSION_OPEN,
                                                                             AnchorKind.US_CASH_OPEN)),
        volume_profile=_gate_profile(mss._volume_profile(r), m["volume_profile"], ev, cash_open, clock),
        tpo=_tpo(r, m["tpo"], m["initial_balance"], ev, cash_open, clock),
        tpo_structure=(mss._tpo_structure(r) if final_study else
                       TpoStructureSection(*_nyd("final-study structure; evaluated at 15:00 CT"), None)),
        day_type=(mss._day_type(r) if final_study else
                  DayTypeSection(*_nyd("DAY_TYPE_V1 is evaluated at 15:00 CT"), None, None)),
        day_strength=(mss._day_strength(r) if final_study else
                      DayStrengthSection(*_nyd("DAY_STRUCTURE_STRENGTH_V1 is evaluated at 15:00 CT"), None, None)),
        prices=_prices(ev, r, final_study),
        prior_day=_prior_day(prior, prior_known, prior_ctx),
        overnight=_overnight(prep, ev, r, clock, on_start, on_end, m["overnight"], path_facts, grid),
        cash_opening=cash_opening,
        opening_type=(mss._opening_type(classification) if clock >= ib_end else
                      dataclasses.replace(mss._opening_type(None),
                                          reasons=("NOT_YET_DETERMINED: OPENING_TYPE_V1 is evaluated at 09:30 CT",))),
        policy_registry=mss.policy_registry((grid.policy_id, grid.policy_version)) + (
            PolicyEntry("MARKET_STUDY_SNAPSHOT", SNAPSHOT_SCHEMA, SNAPSHOT_SCHEMA),),
        quality_matrix=(),
    )
    return dataclasses.replace(snapshot, quality_matrix=_quality_matrix(snapshot))


def _final_at(start: datetime, end: datetime, clock: datetime) -> Maturity:
    if clock <= start:
        return Maturity.NOT_YET_AVAILABLE
    return Maturity.WINDOW_COMPLETE if clock >= end else Maturity.NOT_YET_DETERMINED


def _closing_maturity(prep: PreparedReplay, ev: AsOfEvidence, cutoff: ReplayCutoff) -> Maturity:
    s = prep.closing_summary
    if s is not None and s.closed_at < cutoff.knowledge_time_cutoff_utc:
        return Maturity.WINDOW_COMPLETE
    if s is None and ev.capture_status in (CaptureStatus.STOPPED, CaptureStatus.UNRECORDED):
        return Maturity.NOT_AVAILABLE  # the capture is over and no closing summary was ever written
    return Maturity.NOT_YET_DETERMINED


def _prior_known(source: DatasetSource, cutoff: ReplayCutoff, session_open: datetime) -> bool:
    """The prior dataset is legitimate knowledge once it had closed (its own recorded close)."""
    closed = source.capture_ended_at or source.closing_summary_closed_at
    return (closed < cutoff.knowledge_time_cutoff_utc) if closed is not None else (
        cutoff.knowledge_time_cutoff_utc > session_open)


def _streamer(prep: PreparedReplay) -> str | None:
    match = mss._LOCATOR.match(prep.dataset.source_locator or "")
    return match.group(2) if match else None


def _dataset_as_of(prep: PreparedReplay, ev: AsOfEvidence, cutoff: ReplayCutoff, closing: Maturity) -> DatasetAsOf:
    d, s = prep.dataset, prep.closing_summary
    match = mss._LOCATOR.match(d.source_locator or "")
    known_classes = [x.source_record.event_classification for x in ev.known_deferred]
    shown = s if closing is Maturity.WINDOW_COMPLETE else None
    return DatasetAsOf(
        dataset_id=d.dataset_id, trading_date=prep.trading_date, recorded_trading_date=prep.recorded_trading_date,
        instrument_id=prep.instrument.canonical_id, kind=d.kind.value, origin=d.origin.value, label=d.label,
        source_locator=d.source_locator, source_system=match.group(1) if match else None,
        streamer_symbol=match.group(2) if match else None, normalizer_version=d.normalizer_version,
        collector_version=s.collector_version if s else None, collector_git_commit=s.collector_git_commit if s else None,
        capture_status=ev.capture_status, capture_started_at=ev.capture_started_at,
        capture_ended_at=ev.capture_ended_at, lifecycle_as_of=ev.lifecycle_as_of, connection_as_of=ev.connection,
        lifecycle_evidence_known=tuple((e.evidence_type.value, e.observed_at) for e in ev.point_events),
        counts=AsOfCounts(
            source_records_known=ev.known_provenance + len(ev.known_deferred) + ev.known_rejected,
            accepted_known=ev.known_provenance, rejected_known=ev.known_rejected,
            rejected_knowledge_time_unrecorded=ev.rejected_time_unrecorded, deferred_known=len(ev.known_deferred),
            corrections_known=known_classes.count("CORRECTION"), cancels_known=known_classes.count("CANCEL"),
            corrections_applied=ev.tape.applied_correction_count, cancels_applied=ev.tape.applied_cancel_count,
            reconstruction_anomalies=len(ev.tape.anomalies),
            effective_trades_in_session_before_market_cutoff=len(ev.scoped),
            known_records_with_market_time_at_or_after_cutoff=ev.future_market_known),
        closing_summary_maturity=closing, closing_summary=shown,
        closing_accounting_difference=shown.accounting_difference if shown else None)


def _quality_as_of(prep, ev: AsOfEvidence, r: TpoAnalysisResult, clock, cash_open, cash_end, ib_end, on_start,
                   on_end) -> QualityAsOf:
    q = r.quality
    windows = []
    for name, start, end in (("CASH_PROFILE", cash_open, cash_end), ("OPENING", cash_open, ib_end),
                             ("OVERNIGHT", on_start, on_end)):
        mat = _window_maturity(start, end, clock)
        upto = min(end, clock)
        if mat is Maturity.NOT_YET_AVAILABLE:
            captured = None
        elif ev.capture_status is CaptureStatus.UNRECORDED:
            captured = None
        else:
            captured = ev.capture_started_at is not None and ev.capture_started_at <= start and (
                ev.capture_ended_at is None or ev.capture_ended_at >= upto)
        known = sum(1 for g in ev.gap_events if g.evidence_type.value == "KNOWN_GAP" and g.interval_start < upto
                    and g.interval_end > start) if mat is not Maturity.NOT_YET_AVAILABLE else 0
        suspected = sum(1 for g in ev.gap_events if g.evidence_type.value == "SUSPECTED_GAP"
                        and g.interval_start < upto and g.interval_end > start) if mat is not Maturity.NOT_YET_AVAILABLE else 0
        windows.append(WindowCoverageAsOf(name, start, end, mat, captured, known, suspected))
    reasons = []
    if q.known_gap_count:
        reasons.append(f"KNOWN_GAP evidence known: {q.known_gap_count}")
    if q.suspected_gap_count:
        reasons.append(f"SUSPECTED_GAP evidence known: {q.suspected_gap_count}")
    if ev.active_interruption is not None:
        reasons.append(f"ACTIVE_INTERRUPTION since {mss.encode(ev.active_interruption.start_utc)}")
    for w in windows:
        if w.captured_through_clock is False:
            reasons.append(f"{w.window} window not captured through the clock")
    if ev.capture_status is CaptureStatus.STOPPED and ev.lifecycle_as_of != "FINALIZED":
        reasons.append(f"lifecycle {ev.lifecycle_as_of} (not FINALIZED)")
    if ev.capture_status is CaptureStatus.NOT_STARTED:
        reasons.append("capture not started at the knowledge cutoff")
    return QualityAsOf(
        status=ComponentStatus.QUALITY_QUALIFIED if reasons else ComponentStatus.AVAILABLE, reasons=tuple(reasons),
        completeness=q.status, known_gap_count=q.known_gap_count, suspected_gap_count=q.suspected_gap_count,
        known_gap_duration=q.known_gap_duration,
        gaps=tuple(GapInterval(g.evidence_type.value, g.interval_start, g.interval_end) for g in ev.gap_events
                   if g.event_id != UUID(int=0)),
        active_interruption=ev.active_interruption, windows=tuple(windows))


def _vwap(prep, ev: AsOfEvidence, r: TpoAnalysisResult, kind: AnchorKind, clock, session_end) -> SnapshotVwap:
    anchor = resolve_anchor(kind, prep.trading_date)
    mat = _window_maturity(anchor.anchor_timestamp_utc, session_end, clock)
    if mat is Maturity.NOT_YET_AVAILABLE:
        return SnapshotVwap(kind, anchor.anchor_timestamp_utc, mat, ComponentStatus.NOT_AVAILABLE,
                            ("NOT_YET_AVAILABLE: the anchor has not occurred",), None)
    if mat is Maturity.WINDOW_COMPLETE:  # the accepted 0Z-A study over the as-of view (converges to the final)
        ctx = SimpleNamespace(dataset_first=ev.known_canonical_first, dataset_last=ev.known_canonical_last,
                              scoped_effective=ev.scoped)
        if ev.known_canonical_first is None:
            return SnapshotVwap(kind, anchor.anchor_timestamp_utc, mat, ComponentStatus.NOT_AVAILABLE,
                                ("no known trade",), None)
        study = mss._vwap_study(ctx, kind, r)
        return SnapshotVwap(kind, anchor.anchor_timestamp_utc, mat, study.status, study.reasons, study)
    try:
        v = calculate_anchored_vwap(ev.scoped, anchor, VwapSourceMode.EFFECTIVE_TAPE, str(prep.trading_date))
    except ValueError:
        v = None
    if v is None:
        return SnapshotVwap(kind, anchor.anchor_timestamp_utc, mat, ComponentStatus.NOT_AVAILABLE,
                            ("no known trade at or after the anchor before the cutoff",), None)
    status, reasons = _developing_status(ev, anchor.anchor_timestamp_utc, clock)
    first = ev.known_canonical_first
    coverage = (AnchorCoverage.DATASET_BEGINS_AFTER_ANCHOR if first is not None and anchor.anchor_timestamp_utc < first
                else AnchorCoverage.ANCHOR_COVERED)
    study = VwapStudy(
        anchor_kind=kind, anchor_policy_id=anchor.policy_id, anchor_policy_version=anchor.policy_version,
        anchor_utc=anchor.anchor_timestamp_utc,
        end_semantics="[anchor, market cutoff): retained effective-tape trades known by the knowledge cutoff",
        session_end_utc=session_end, source_mode=VwapSourceMode.EFFECTIVE_TAPE, status=status, reasons=reasons,
        coverage=coverage, vwap=v.vwap, included_trade_count=v.included_trade_count, included_volume=v.included_volume,
        first_included_utc=v.first_included_trade_timestamp, last_included_utc=v.last_included_trade_timestamp)
    return SnapshotVwap(kind, anchor.anchor_timestamp_utc, mat, status, reasons, study)


def _gate_profile(section: VolumeProfileSection, mat: Maturity, ev, start, clock) -> VolumeProfileSection:
    if mat is Maturity.NOT_YET_AVAILABLE:
        return dataclasses.replace(section, status=ComponentStatus.NOT_AVAILABLE,
                                   reasons=("NOT_YET_AVAILABLE: the cash study window has not begun",))
    if mat is Maturity.DEVELOPING and section.poc is not None:
        status, reasons = _developing_status(ev, start, clock)
        return dataclasses.replace(section, status=status, reasons=reasons)
    return section


def _tpo(r: TpoAnalysisResult, mat: Maturity, ib_mat: Maturity, ev, start, clock) -> TpoAsOfSection:
    base = mss._tpo(r)
    p = r.profile
    if mat is Maturity.NOT_YET_AVAILABLE:
        return TpoAsOfSection(ComponentStatus.NOT_AVAILABLE, ("NOT_YET_AVAILABLE: the cash study window has not begun",),
                              base.window_id, base.window_policy_version, base.period_minutes, "", None, ib_mat, None)
    status, reasons = base.status, base.reasons
    current = None
    if p is not None:
        reached = tuple(x for x in p.periods if x.start_utc < clock)
        current = next((x.label for x in reached if x.end_utc > clock), None)
        p = dataclasses.replace(p, periods=reached)
        if mat is Maturity.DEVELOPING:
            status, reasons = _developing_status(ev, start, clock)
    return TpoAsOfSection(status, reasons, base.window_id, base.window_policy_version, base.period_minutes,
                          "".join(x.label for x in p.periods) if p else "", current, ib_mat, p)


def _prices(ev: AsOfEvidence, r: TpoAnalysisResult, final_study: bool) -> PricesAsOf:
    last = ev.scoped[-1] if ev.scoped else None
    terminal = None
    if final_study and r.day_structure is not None and r.day_structure.facts.terminal is not None:
        terminal = r.day_structure.facts.terminal.price
    return PricesAsOf(last.price if last else None, last.event_timestamp if last else None,
                      Maturity.WINDOW_COMPLETE if final_study else Maturity.NOT_YET_DETERMINED, terminal)


def _prior_day(prior: StudyInputs | None, known: bool, ctx) -> PriorDaySection:
    if prior is not None and not known:
        return PriorDaySection(ComponentStatus.NOT_AVAILABLE,
                               ("NOT_YET_AVAILABLE: the prior dataset had not closed by the knowledge cutoff",),
                               None, True, None, None)
    return mss._prior_day(prior, ctx)


def _overnight(prep, ev, r: TpoAnalysisResult, clock, on_start, on_end, mat: Maturity, path_facts, grid
               ) -> OvernightAsOfSection:
    if mat is Maturity.NOT_YET_AVAILABLE:
        return OvernightAsOfSection(ComponentStatus.NOT_AVAILABLE, ("NOT_YET_AVAILABLE: 17:00 CT not reached",),
                                    False, False, False, None, None, None)
    q = r.quality
    session = r.overnight or build_overnight_session(
        tuple(t for t in ev.scoped if on_start <= t.event_timestamp < on_end), grid, prep.trading_date,
        prep.instrument.canonical_id, q.capture_started_at, q.capture_ended_at, q.gap_intervals, q.lifecycle_state)
    claimed = session.globex_open_price is not None
    proven = session.globex_open_boundary_proven
    if mat is Maturity.WINDOW_COMPLETE:
        ctx = path_facts.overnight if path_facts is not None else None
        base = mss._overnight(session, ctx)
        return OvernightAsOfSection(base.status, base.reasons, claimed, proven, claimed and proven, None, session, ctx)
    status, reasons = _developing_status(ev, on_start, clock)
    if not session.available:
        status, reasons = ComponentStatus.NOT_AVAILABLE, ("no known overnight trade before the cutoff",) + reasons
    elif not claimed:
        reasons = reasons + (f"Globex open NOT CLAIMED: {session.globex_open_unavailable_reason}",)
    dev = OvernightDeveloping(session.first_price, session.first_utc, session.high, session.low, session.range_ticks,
                              session.time_of_high_utc, session.time_of_low_utc, session.terminal_price,
                              session.terminal_utc)
    return OvernightAsOfSection(status, reasons, claimed, proven, claimed and proven, dev, None, None)


def _cash_opening(ev, r: TpoAnalysisResult, clock, cash_open, ib_end, final_study, facts, path_facts, prior,
                  grid) -> CashOpeningAsOfSection:
    session = r.opening
    co = session.cash_open if session is not None else None
    if co is not None and co.price is not None:
        co_mat = Maturity.WINDOW_COMPLETE
    elif clock < cash_open + CASH_OPEN_MAX_DELAY:
        co_mat, co = Maturity.NOT_YET_AVAILABLE, None
    else:
        co_mat = Maturity.NOT_AVAILABLE
    mature = clock >= ib_end
    # The accepted rule: opening facts are NOT_AVAILABLE when capture began after 08:30 CT or (as known) ended
    # before 09:30 CT. Before 09:30 the end is judged only from a known stop.
    blocked = []
    if ev.capture_started_at is None or ev.capture_started_at > cash_open:
        blocked.append("opening window [08:30, 09:30) CT not fully captured (capture start)")
    if ev.capture_ended_at is not None and ev.capture_ended_at < min(ib_end, clock):
        blocked.append("opening window [08:30, 09:30) CT not fully captured (capture stopped)")
    windows = []
    if mature and session is not None:
        complete = {w.minutes: w for w in session.windows}
    else:
        cash = tuple(t for t in ev.scoped if cash_open <= t.event_timestamp < r.window_end_utc)
        points = _path(cash, grid, cash_open, r.window_end_utc) if co_mat is Maturity.WINDOW_COMPLETE else ()
        complete = {m: _window(points, cash_open, m) for m in OPENING_WINDOW_MINUTES
                    if points and not blocked and clock >= cash_open + timedelta(minutes=m)}
    for minutes in OPENING_WINDOW_MINUTES:
        end = cash_open + timedelta(minutes=minutes)
        if clock <= cash_open:
            windows.append(OpeningWindowAsOf(minutes, end, Maturity.NOT_YET_AVAILABLE, None))
        elif clock < end:
            windows.append(OpeningWindowAsOf(minutes, end, Maturity.NOT_YET_DETERMINED, None))
        elif minutes in complete:
            windows.append(OpeningWindowAsOf(minutes, end, Maturity.WINDOW_COMPLETE, complete[minutes]))
        else:
            windows.append(OpeningWindowAsOf(minutes, end, Maturity.NOT_AVAILABLE, None))
    rl = vl = gp = gt = gd = None
    if co_mat is Maturity.WINDOW_COMPLETE and prior.usable:  # the accepted location / gap formulas
        o = co.price
        rl = _locate(o, prior.profile_low, prior.profile_high, RangeLocation)
        vl = _locate(o, prior.value_area_low, prior.value_area_high, ValueLocation)
        gp = o - prior.terminal_price
        gt = _ticks(grid.tick_size)(gp)
        gd = Side.UP if gp > 0 else Side.DOWN if gp < 0 else Side.NONE
    if co_mat is Maturity.NOT_YET_AVAILABLE:
        status, reasons = ComponentStatus.NOT_AVAILABLE, ("NOT_YET_AVAILABLE: no cash open print yet",)
    elif co_mat is Maturity.NOT_AVAILABLE:
        status = ComponentStatus.NOT_AVAILABLE
        reasons = (co.unavailable_reason,) if co is not None and co.unavailable_reason else (
            f"no on-grid cash print within {CASH_OPEN_MAX_DELAY} of 08:30 CT",)
    elif mature:
        base = mss._cash_opening(session, facts, path_facts)
        status, reasons = base.status, base.reasons
    elif blocked:
        status, reasons = ComponentStatus.NOT_AVAILABLE, tuple(blocked)
    else:
        status, reasons = _developing_status(ev, cash_open, clock)
    show = mature and co_mat is Maturity.WINDOW_COMPLETE
    return CashOpeningAsOfSection(
        status=status, reasons=reasons, cash_open_maturity=co_mat,
        cash_open=co if co_mat is Maturity.WINDOW_COMPLETE else None,
        range_location=rl, value_location=vl, gap_points=gp, gap_ticks=gt, gap_direction=gd, windows=tuple(windows),
        facts=facts if show else None, path_facts=path_facts if show else None,
        fields_developing_until_study_window_end=(OPENING_FIELDS_DEVELOPING_UNTIL_STUDY_WINDOW_END
                                                  if show and not final_study and facts is not None else ()))


def _quality_matrix(s: MarketStudySnapshot) -> tuple[SnapshotQualityEntry, ...]:
    m = {e.component: e.maturity for e in s.maturity}
    vwap_m = m["vwap SESSION_OPEN"]
    return tuple(SnapshotQualityEntry(name, mat, section.status, section.reasons) for name, mat, section in (
        ("dataset", Maturity.DEVELOPING if s.current_dataset.capture_status is CaptureStatus.RUNNING
         else Maturity.WINDOW_COMPLETE, s.dataset_quality),
        ("contract", Maturity.WINDOW_COMPLETE, s.contract),
        ("vwap SESSION_OPEN", vwap_m, s.vwap[0]),
        ("vwap US_CASH_OPEN", m["vwap US_CASH_OPEN"], s.vwap[1]),
        ("volume_profile", m["volume_profile"], s.volume_profile),
        ("cash_tpo", m["tpo"], s.tpo),
        ("tpo_structure", m["tpo_structure"], s.tpo_structure),
        ("day_type", m["day_type"], s.day_type),
        ("day_strength", m["day_strength"], s.day_strength),
        ("prior_context", Maturity.WINDOW_COMPLETE if s.prior_day.context is not None else Maturity.NOT_YET_AVAILABLE,
         s.prior_day),
        ("overnight", m["overnight"], s.overnight),
        ("cash_opening", m["opening_facts"], s.cash_opening),
        ("opening_type", m["opening_type"], s.opening_type),
    ))


# --- canonical serialization ---------------------------------------------------------------------

def check_snapshot_references(s: MarketStudySnapshot) -> None:
    """Every $ref resolves to the very object serialized at its pointer (layout shared with 0Z-A)."""
    targets = {"/prior_day/context": s.prior_day.context, "/overnight/session": s.overnight.session,
               "/overnight/context": s.overnight.context, "/cash_opening/facts": s.cash_opening.facts,
               "/cash_opening/path_facts": s.cash_opening.path_facts}
    pairs = []
    if s.cash_opening.facts is not None:
        pairs.append((s.cash_opening.facts.prior, "/prior_day/context"))
    if s.overnight.context is not None:
        pairs += [(s.overnight.context.session, "/overnight/session"), (s.overnight.context.prior, "/prior_day/context")]
    if s.cash_opening.path_facts is not None:
        pairs += [(s.cash_opening.path_facts.opening, "/cash_opening/facts"),
                  (s.cash_opening.path_facts.overnight, "/overnight/context")]
    if s.opening_type.classification is not None:
        pairs.append((s.opening_type.classification.facts, "/cash_opening/path_facts"))
    for value, pointer in pairs:
        if value is not None and value is not targets[pointer]:
            raise ValueError(f"$ref {pointer} does not resolve to the serialized object")


def snapshot_payload(s: MarketStudySnapshot) -> dict:
    check_snapshot_references(s)
    return mss.encode(s)


def snapshot_sha256(s: MarketStudySnapshot) -> str:
    """SHA-256 of the canonical payload JSON (which never contains the hash field)."""
    return hashlib.sha256(mss._dumps(snapshot_payload(s)).encode("ascii")).hexdigest()


def canonical_snapshot_json(s: MarketStudySnapshot) -> str:
    payload = snapshot_payload(s)
    payload[SNAPSHOT_HASH_FIELD] = hashlib.sha256(mss._dumps(payload).encode("ascii")).hexdigest()
    return mss._dumps(payload)


def verify_snapshot_json(text: str) -> bool:
    document = json.loads(text)
    claimed = document.pop(SNAPSHOT_HASH_FIELD, None)
    return claimed == hashlib.sha256(mss._dumps(document).encode("ascii")).hexdigest() and mss._dumps(
        {**document, SNAPSHOT_HASH_FIELD: claimed}) == text


@dataclass(frozen=True)
class SnapshotIdentity:
    dataset_id: UUID
    schema: str
    market_time_cutoff_utc: datetime
    knowledge_time_cutoff_utc: datetime
    knowledge_source_order_cutoff: int | None
    analysis_git_commit: str
    snapshot_sha256: str


def snapshot_identity(s: MarketStudySnapshot) -> SnapshotIdentity:
    c = s.cutoff
    return SnapshotIdentity(s.current_dataset.dataset_id, s.schema, c.market_time_cutoff_utc,
                            c.knowledge_time_cutoff_utc, c.knowledge_source_order_cutoff,
                            s.provenance.analysis_git_commit, snapshot_sha256(s))


# --- diagnostics (replay audit; reads the full record, never part of a snapshot) -------------------

@dataclass(frozen=True)
class RecordVisibility:
    record: str  # NEW / CORRECTION / CANCEL
    source_order: int
    source_index: int
    market_timestamp_utc: datetime | None
    received_at_utc: datetime
    receipt_lag: timedelta | None
    visibility: Visibility
    reason: str


def record_visibility(prep: PreparedReplay, cutoff: ReplayCutoff, source_orders=None, late_print_limit: int = 10,
                      ) -> tuple[RecordVisibility, ...]:
    """Why each selected source record is or is not in the snapshot at `cutoff`.

    Default selection: every CORRECTION / CANCEL, their target NEW records, and up to
    `late_print_limit` late prints relative to the cutoff (market time before the market cutoff, received
    at/after the knowledge cutoff; largest lag first), topped up with the day's largest receipt lags.
    This audit uses hindsight by design.
    """
    ev = as_of_evidence(prep, cutoff)
    by_id = {t.observation_id: t for t in prep.canonical_trades}
    effective = {t.originating_source_index: t for t in ev.tape.effective_trades}
    scoped_idx = {t.originating_source_index for t in ev.scoped}
    anomalies = {a.source_record_ref: a.reason for a in ev.tape.anomalies}
    known_deferred_refs = {d.source_record.source_record_ref for d in ev.known_deferred}
    known_cancel_idx = {d.source_record.source_index for d in ev.known_deferred
                        if d.source_record.event_classification == "CANCEL"
                        and d.source_record.source_record_ref not in anomalies}
    target_idx = {d.source_record.source_index for d in prep.deferred}
    if source_orders is None:
        def lag(p):
            return p.received_at - by_id[p.observation_id].event_timestamp, p.source_order

        straddling = sorted((p for p in prep.provenance if cutoff.in_market(by_id[p.observation_id].event_timestamp)
                             and p.received_at >= cutoff.knowledge_time_cutoff_utc), key=lag, reverse=True)
        late = straddling[:late_print_limit]
        if len(late) < late_print_limit:
            taken = {p.source_order for p in late}
            late += [p for p in sorted(prep.provenance, key=lag, reverse=True)
                     if p.source_order not in taken][:late_print_limit - len(late)]
        chosen = {p.source_order for p in late} | {p.source_order for p in prep.provenance
                                                   if p.source_index in target_idx} | {d.source_order
                                                                                        for d in prep.deferred}
    else:
        chosen = set(source_orders)
    out = []
    for p in prep.provenance:
        if p.source_order not in chosen:
            continue
        trade = by_id.get(p.observation_id)
        mts = trade.event_timestamp if trade else None
        lag = p.received_at - mts if mts else None
        if p.received_at >= cutoff.knowledge_time_cutoff_utc:
            vis, why = Visibility.NOT_YET_RECEIVED, "received at/after the knowledge cutoff"
        elif not cutoff.knows(p.received_at, p.source_order):
            vis, why = Visibility.BEYOND_SOURCE_ORDER_CUTOFF, "source_order beyond the cursor"
        elif p.source_index in known_cancel_idx and p.source_index not in effective:
            vis, why = Visibility.CANCELED_AS_OF, "a known CANCEL removed it from the effective tape"
        elif p.source_index not in effective:
            vis, why = Visibility.NOT_DUPLICATED, "dropped by the reconstruction"
        elif not cutoff.in_market(effective[p.source_index].event_timestamp):
            vis, why = Visibility.MARKET_TIME_AT_OR_AFTER_CUTOFF, "known, but its market time is not before the cutoff"
        elif p.source_index not in scoped_idx:
            vis, why = Visibility.OUTSIDE_TRADING_DATE_SESSION, "outside the trading-date session"
        elif effective[p.source_index].correction_count:
            vis, why = Visibility.VISIBLE_CORRECTED, (f"visible with {effective[p.source_index].correction_count} known "
                                                      f"correction(s) applied")
        else:
            vis, why = Visibility.VISIBLE, "known and before the market cutoff"
        out.append(RecordVisibility("NEW", p.source_order, p.source_index, mts, p.received_at, lag, vis, why))
    for d in prep.deferred:
        if d.source_order not in chosen:
            continue
        sr = d.source_record
        mts = _source_timestamp(sr.event_time)
        if sr.received_at >= cutoff.knowledge_time_cutoff_utc:
            vis, why = Visibility.NOT_YET_RECEIVED, "received at/after the knowledge cutoff"
        elif not cutoff.knows(sr.received_at, d.source_order):
            vis, why = Visibility.BEYOND_SOURCE_ORDER_CUTOFF, "source_order beyond the cursor"
        elif sr.source_record_ref in anomalies:
            vis, why = Visibility.ANOMALY, anomalies[sr.source_record_ref]
        elif sr.source_record_ref in known_deferred_refs:
            vis, why = Visibility.APPLIED, f"applied to source_index {sr.source_index}"
        else:
            vis, why = Visibility.NOT_YET_RECEIVED, "not known"
        out.append(RecordVisibility(sr.event_classification or "UNKNOWN", d.source_order, sr.source_index, mts,
                                    sr.received_at, sr.received_at - mts if mts else None, vis, why))
    return tuple(sorted(out, key=lambda x: x.source_order))


# --- programmatic replay API ---------------------------------------------------------------------

class MarketReplay:
    """`replay.snapshot(at=T)`: the evidence a Laboratory could have known at T. Prepared once; read-only."""

    def __init__(self, current: PreparedReplay, prior: StudyInputs | None, provenance: AnalysisProvenance,
                 closures: frozenset[date] = frozenset()) -> None:
        self.current, self.prior, self.provenance, self.closures = current, prior, provenance, closures

    @classmethod
    def load(cls, database: Path, provenance: AnalysisProvenance, prior_database: Path | None = None,
             closures: frozenset[date] = frozenset(), dataset_id: UUID | None = None) -> MarketReplay:
        prior = mss.load_study_inputs(prior_database) if prior_database is not None else None
        return cls(prepare_replay(database, dataset_id), prior, provenance, closures)

    def snapshot(self, at: datetime | None = None, *, cutoff: ReplayCutoff | None = None) -> MarketStudySnapshot:
        if (at is None) == (cutoff is None):
            raise ValueError("pass exactly one of `at` or `cutoff`")
        return build_snapshot(self.current, self.prior, cutoff or ReplayCutoff.at(at), self.provenance, self.closures)

    def snapshots(self, times) -> tuple[MarketStudySnapshot, ...]:
        return tuple(self.snapshot(at=t) for t in times)

    def source_order_steps(self, market_time_cutoff: datetime, knowledge_time_cutoff: datetime, orders):
        """Event-by-event diagnostic stepping: one snapshot per source-order cursor."""
        return tuple(self.snapshot(cutoff=ReplayCutoff(market_time_cutoff, knowledge_time_cutoff, n)) for n in orders)

    def visibility(self, cutoff: ReplayCutoff, source_orders=None, late_print_limit: int = 10):
        return record_visibility(self.current, cutoff, source_orders, late_print_limit)


# --- human summary -------------------------------------------------------------------------------

def _v(value) -> str:
    return mss._v(value)


def render_snapshot_summary(s: MarketStudySnapshot, sha: str | None = None) -> str:
    """Evidence by domain at the cutoff; maturity first. No recommendation section."""
    from zoneinfo import ZoneInfo
    ct = ZoneInfo("America/Chicago")
    c, d = s.cutoff, s.current_dataset
    lines = ["MARKET STUDY SNAPSHOT (AS OF)",
             f"  Schema: {s.schema}   Temporality: {s.state_temporality.value}",
             f"  Market cutoff:    {_v(c.market_time_cutoff_utc)}  ({c.market_time_cutoff_utc.astimezone(ct):%Y-%m-%d %H:%M:%S %Z})",
             f"  Knowledge cutoff: {_v(c.knowledge_time_cutoff_utc)}  ({c.knowledge_time_cutoff_utc.astimezone(ct):%Y-%m-%d %H:%M:%S %Z})"
             + (f"  source_order <= {c.knowledge_source_order_cutoff}" if c.knowledge_source_order_cutoff else ""),
             f"  {s.temporality_note}",
             f"  Analysis commit: {s.provenance.analysis_git_commit}", "",
             "DATASET AS OF",
             f"  {d.dataset_id}  trading date {d.trading_date}  {d.instrument_id}",
             f"  capture {d.capture_status.value}  lifecycle {d.lifecycle_as_of}  connection {d.connection_as_of.value}  "
             f"closing summary {d.closing_summary_maturity.value}",
             f"  known: records {d.counts.source_records_known}  accepted {d.counts.accepted_known}  rejected "
             f"{d.counts.rejected_known}  deferred {d.counts.deferred_known} (corrections {d.counts.corrections_known}, "
             f"cancels {d.counts.cancels_known}; applied {d.counts.corrections_applied}/{d.counts.cancels_applied})",
             f"  known with market time >= cutoff (excluded): {d.counts.known_records_with_market_time_at_or_after_cutoff}",
             f"QUALITY AS OF  [{s.dataset_quality.status.value}]"]
    lines += [f"  ! {x}" for x in s.dataset_quality.reasons]
    lines += ["", "MATURITY"]
    lines += [f"  {e.component:<22} {e.maturity.value}" for e in s.maturity]
    lines += ["", "VWAP"]
    for v in s.vwap:
        lines.append(f"  {v.anchor_kind.value:<13} {v.maturity.value:<17} "
                     + (f"VWAP {_v(v.study.vwap)}  trades {v.study.included_trade_count}" if v.study else "--")
                     + f"  [{v.status.value}]")
    vp = s.volume_profile
    lines += ["", f"VOLUME PROFILE  [{vp.status.value}]",
              f"  POC {_v(vp.poc)}  VAL {_v(vp.value_area_low)}  VAH {_v(vp.value_area_high)}  high "
              f"{_v(vp.profile_high)}  low {_v(vp.profile_low)}  volume {_v(vp.total_volume)}"]
    t = s.tpo
    lines += ["", f"TPO  [{t.status.value}]  periods reached {t.periods_reached or '--'}  current "
              f"{t.current_period or '--'}  IB {t.initial_balance_maturity.value}"]
    if t.profile is not None:
        ib = t.profile.initial_balance
        lines.append(f"  POC {t.profile.poc}  VAL {t.profile.value_area.low}  VAH {t.profile.value_area.high}  high "
                     f"{t.profile.profile_high}  low {t.profile.profile_low}"
                     + (f"  IB {ib.low}-{ib.high}" if ib else ""))
    lines += ["", "FINAL-STUDY COMPONENTS",
              f"  structure {s.tpo_structure.reasons[0] if s.tpo_structure.structure is None else 'available'}",
              "  DAY_TYPE_V1 " + (s.day_type.reasons[0] if s.day_type.classification is None else
                                   f"{s.day_type.outcome.value} {s.day_type.classification.primary.value if s.day_type.classification.primary else ''}"),
              f"  terminal {s.prices.study_window_terminal_maturity.value} {_v(s.prices.study_window_terminal_price)}"
              f"   last known price {_v(s.prices.last_known_price)} at {_v(s.prices.last_known_utc)}"]
    o = s.overnight
    lines += ["", f"OVERNIGHT  [{o.status.value}]  Globex open claimed {'yes' if o.globex_open_claimed else 'no'}"]
    if o.developing is not None:
        x = o.developing
        lines.append(f"  developing: high {_v(x.high)}  low {_v(x.low)}  range {_v(x.range_ticks)} ticks  last "
                     f"{_v(x.last_price)}")
    if o.session is not None and o.session.available:
        lines.append(f"  ONH {o.session.high}  ONL {o.session.low}  last {o.session.terminal_price}")
    co = s.cash_opening
    lines += ["", f"CASH OPENING  [{co.status.value}]  cash open {co.cash_open_maturity.value} "
              f"{_v(co.cash_open.price) if co.cash_open else ''}  vs prior range {_v(co.range_location)}"]
    lines += [f"  {w.minutes:>2} min {w.maturity.value}" + (f": high {w.facts.high} low {w.facts.low} crosses "
                                                            f"{w.facts.open_cross_count}" if w.facts else "")
              for w in co.windows]
    ot = s.opening_type
    lines += ["", f"OPENING-TYPE CANDIDATES  [{ot.status.value}]"]
    lines += [f"  CANDIDATE {x.type}" + (f" {x.direction}" if x.direction else "") for x in ot.matched] or [
        f"  {ot.reasons[0] if ot.reasons else 'no matched candidate'}"]
    pd = s.prior_day
    lines += ["", f"PRIOR DAY  [{pd.status.value}]  {pd.outcome.value if pd.outcome else '--'}"]
    lines += ["", f"SNAPSHOT HASH  {sha or snapshot_sha256(s)}",
              "As-of evidence only: no recommendation; candidate labels are Laboratory policy outputs."]
    return "\n".join(lines) + "\n"
