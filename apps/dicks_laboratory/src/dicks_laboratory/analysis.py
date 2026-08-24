"""Read-only, offline anchored-VWAP analysis over a durable Laboratory dataset.

Orchestrates the accepted 0M session/anchor primitives and the 0K6 effective-tape
reconstruction into one human-facing analytical result. Computes no new VWAP formula
and performs no network I/O; it only reads what is already durable in SQLite.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID

from dicks_laboratory.anchored_vwap import AnchoredVwapResult, VwapSourceMode, calculate_anchored_vwap
from dicks_laboratory.effective_tape import EffectiveTapeResult, reconstruct_effective_tape
from dicks_laboratory.models import InstrumentIdentity, TradeObservation
from dicks_laboratory.sessions import (
    AnchorKind,
    SessionCoverageWindow,
    SessionState,
    VwapAnchor,
    classify_es_session,
    resolve_anchor,
    select_session_trades,
    select_trades_from_anchor,
    session_coverage,
)
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.value_area import DEFAULT_VALUE_AREA_FRACTION, ValueAreaResult, compute_value_area
from dicks_laboratory.volume_profile import (
    VolumeAtPriceProfile,
    build_volume_at_price_profile,
    price_grid_for_instrument,
)


class LaboratoryAnalysisError(ValueError):
    """A dataset or request could not be analyzed; the failure mode is explicit."""


class AmbiguousDatasetError(LaboratoryAnalysisError):
    def __init__(self, dataset_ids: tuple[UUID, ...]) -> None:
        self.dataset_ids = dataset_ids
        listed = ", ".join(str(item) for item in dataset_ids)
        super().__init__(f"Database contains multiple datasets: {listed}. Specify --dataset-id.")


class AmbiguousTradingDateError(LaboratoryAnalysisError):
    def __init__(self, trading_dates: tuple[date, ...]) -> None:
        self.trading_dates = trading_dates
        listed = ", ".join(item.isoformat() for item in trading_dates)
        super().__init__(f"Dataset contains trades from multiple trading dates: {listed}. Specify --trading-date.")


class AnchorCoverage(StrEnum):
    ANCHOR_COVERED = "ANCHOR_COVERED"
    DATASET_BEGINS_AFTER_ANCHOR = "DATASET_BEGINS_AFTER_ANCHOR"
    ANCHOR_AFTER_DATASET_END = "ANCHOR_AFTER_DATASET_END"


@dataclass(frozen=True)
class VwapAnalysisResult:
    """Immutable factual report; deliberately carries no score or recommendation."""

    dataset_id: UUID
    instrument: InstrumentIdentity
    trading_date: date | None

    session_definition_id: str | None
    session_policy_version: str | None

    anchor_kind: AnchorKind
    anchor_timestamp_utc: datetime

    dataset_first_trade_timestamp: datetime
    dataset_last_trade_timestamp: datetime

    coverage: AnchorCoverage
    dataset_begins_after_anchor: bool
    unobserved_pre_capture_interval: timedelta | None

    session_end_utc: datetime | None
    dataset_ends_before_session_end: bool | None

    first_included_trade_timestamp: datetime | None
    last_included_trade_timestamp: datetime | None

    canonical_included_trade_count: int
    canonical_included_volume: Decimal | None
    canonical_vwap: Decimal | None

    effective_included_trade_count: int
    effective_included_volume: Decimal | None
    effective_vwap: Decimal | None

    applied_correction_count: int
    applied_cancel_count: int
    reconstruction_anomaly_count: int
    reconstruction_anomaly_counts_by_reason: tuple[tuple[str, int], ...]


def open_dataset_store(database_path: Path) -> LaboratoryStore:
    """Open an existing Laboratory SQLite database strictly read-only."""
    path = Path(database_path)
    if not path.is_file():
        raise LaboratoryAnalysisError(f"Dataset database not found: {path}")
    try:
        store = LaboratoryStore(path, read_only=True)
        store.list_dataset_ids()
    except sqlite3.DatabaseError as exc:
        raise LaboratoryAnalysisError(f"File is not a readable Laboratory SQLite database: {path}") from exc
    return store


def resolve_dataset_id(store: LaboratoryStore, requested: UUID | None) -> UUID:
    """Infer the single dataset in a database, or require explicit selection."""
    dataset_ids = store.list_dataset_ids()
    if not dataset_ids:
        raise LaboratoryAnalysisError("Database contains no Laboratory dataset.")
    if requested is not None:
        if requested not in dataset_ids:
            raise LaboratoryAnalysisError(f"Dataset {requested} was not found in this database.")
        return requested
    if len(dataset_ids) > 1:
        raise AmbiguousDatasetError(dataset_ids)
    return dataset_ids[0]


def determine_dataset_trading_dates(trades: tuple[TradeObservation, ...]) -> tuple[date, ...]:
    """Distinct ordinary-schedule trading dates actually present in retained trades."""
    dates = {
        membership.trading_date
        for membership in (classify_es_session(trade.event_timestamp) for trade in trades)
        if membership.state is SessionState.IN_SESSION and membership.trading_date is not None
    }
    return tuple(sorted(dates))


def _resolve_required_trading_date(trades: tuple[TradeObservation, ...], requested: date | None) -> date:
    if requested is not None:
        return requested
    trading_dates = determine_dataset_trading_dates(trades)
    if not trading_dates:
        raise LaboratoryAnalysisError("No session-active retained trades were found; cannot determine a trading date.")
    if len(trading_dates) > 1:
        raise AmbiguousTradingDateError(trading_dates)
    return trading_dates[0]


def _best_effort_trading_date(trades: tuple[TradeObservation, ...], requested: date | None) -> date | None:
    if requested is not None:
        return requested
    trading_dates = determine_dataset_trading_dates(trades)
    return trading_dates[0] if len(trading_dates) == 1 else None


@dataclass(frozen=True)
class ScopedDatasetContext:
    """Shared trading-date/anchor/session-scoping glue reused by every analysis service.

    Centralizes the one accepted way to resolve a trading date and session-scope
    canonical/effective trades so VWAP and Volume Profile analyses can never diverge
    on which trades were selected for a given anchor.
    """

    instrument: InstrumentIdentity
    resolved_trading_date: date | None
    anchor: VwapAnchor
    dataset_first: datetime
    dataset_last: datetime
    scoped_canonical: tuple[TradeObservation, ...]
    scoped_effective: tuple
    coverage_window: SessionCoverageWindow | None
    tape: EffectiveTapeResult
    coverage: AnchorCoverage
    anomaly_counts_by_reason: tuple[tuple[str, int], ...]


def prepare_scoped_dataset(
    store: LaboratoryStore,
    dataset_id: UUID,
    anchor_kind: AnchorKind,
    trading_date: date | None,
    custom_timestamp: datetime | None,
) -> ScopedDatasetContext:
    try:
        store.load_dataset(dataset_id)
    except KeyError as exc:
        raise LaboratoryAnalysisError(str(exc)) from exc

    canonical_trades = store.load_trade_observations(dataset_id)
    if not canonical_trades:
        raise LaboratoryAnalysisError("Dataset has no canonical NEW trade observations to analyze.")

    instrument_ids = {trade.instrument.canonical_id for trade in canonical_trades}
    if len(instrument_ids) > 1:
        raise LaboratoryAnalysisError(f"Dataset spans multiple instruments; unsupported: {sorted(instrument_ids)}")
    instrument = canonical_trades[0].instrument

    provenance = store.load_dxlink_time_and_sale_provenance(dataset_id)
    deferred = store.load_deferred_dxlink_time_and_sales(dataset_id)
    tape = reconstruct_effective_tape(canonical_trades, provenance, deferred)

    if anchor_kind is AnchorKind.CUSTOM_TIMESTAMP:
        resolved_trading_date = _best_effort_trading_date(canonical_trades, trading_date)
    else:
        resolved_trading_date = _resolve_required_trading_date(canonical_trades, trading_date)

    anchor = resolve_anchor(anchor_kind, resolved_trading_date, custom_timestamp)

    dataset_first = min(trade.event_timestamp for trade in canonical_trades)
    dataset_last = max(trade.event_timestamp for trade in canonical_trades)

    scoped_canonical = (
        select_session_trades(canonical_trades, resolved_trading_date) if resolved_trading_date else canonical_trades
    )
    scoped_effective = (
        tuple(
            trade for trade in tape.effective_trades
            if classify_es_session(trade.event_timestamp).trading_date == resolved_trading_date
            and classify_es_session(trade.event_timestamp).state is SessionState.IN_SESSION
        )
        if resolved_trading_date
        else tape.effective_trades
    )

    coverage_window = session_coverage(scoped_canonical, resolved_trading_date) if (
        resolved_trading_date and anchor_kind is AnchorKind.SESSION_OPEN
    ) else None

    if anchor.anchor_timestamp_utc > dataset_last:
        coverage = AnchorCoverage.ANCHOR_AFTER_DATASET_END
    elif anchor.anchor_timestamp_utc < dataset_first:
        coverage = AnchorCoverage.DATASET_BEGINS_AFTER_ANCHOR
    else:
        coverage = AnchorCoverage.ANCHOR_COVERED

    anomaly_counts: dict[str, int] = {}
    for anomaly in tape.anomalies:
        anomaly_counts[anomaly.reason] = anomaly_counts.get(anomaly.reason, 0) + 1

    return ScopedDatasetContext(
        instrument=instrument,
        resolved_trading_date=resolved_trading_date,
        anchor=anchor,
        dataset_first=dataset_first,
        dataset_last=dataset_last,
        scoped_canonical=scoped_canonical,
        scoped_effective=scoped_effective,
        coverage_window=coverage_window,
        tape=tape,
        coverage=coverage,
        anomaly_counts_by_reason=tuple(sorted(anomaly_counts.items())),
    )


def analyze_anchored_vwap_dataset(
    store: LaboratoryStore,
    dataset_id: UUID,
    anchor_kind: AnchorKind,
    trading_date: date | None = None,
    custom_timestamp: datetime | None = None,
) -> VwapAnalysisResult:
    """Compute one anchored canonical + effective VWAP report from retained trades only."""
    context = prepare_scoped_dataset(store, dataset_id, anchor_kind, trading_date, custom_timestamp)
    anchor = context.anchor

    canonical_result = _safe_anchored_vwap(
        context.scoped_canonical, anchor, VwapSourceMode.CANONICAL_NEW_ONLY, context.resolved_trading_date
    )
    effective_result = _safe_anchored_vwap(
        context.scoped_effective, anchor, VwapSourceMode.EFFECTIVE_TAPE, context.resolved_trading_date
    )

    unobserved_interval = (
        context.dataset_first - anchor.anchor_timestamp_utc if context.dataset_first > anchor.anchor_timestamp_utc else None
    )
    reference = canonical_result or effective_result

    return VwapAnalysisResult(
        dataset_id=dataset_id,
        instrument=context.instrument,
        trading_date=context.resolved_trading_date,
        session_definition_id=anchor.policy_id if anchor_kind is not AnchorKind.CUSTOM_TIMESTAMP else None,
        session_policy_version=anchor.policy_version if anchor_kind is not AnchorKind.CUSTOM_TIMESTAMP else None,
        anchor_kind=anchor_kind,
        anchor_timestamp_utc=anchor.anchor_timestamp_utc,
        dataset_first_trade_timestamp=context.dataset_first,
        dataset_last_trade_timestamp=context.dataset_last,
        coverage=context.coverage,
        dataset_begins_after_anchor=context.dataset_first > anchor.anchor_timestamp_utc,
        unobserved_pre_capture_interval=unobserved_interval,
        session_end_utc=context.coverage_window.session_end_utc if context.coverage_window else None,
        dataset_ends_before_session_end=(
            context.coverage_window.dataset_ends_before_session_end if context.coverage_window else None
        ),
        first_included_trade_timestamp=reference.first_included_trade_timestamp if reference else None,
        last_included_trade_timestamp=reference.last_included_trade_timestamp if reference else None,
        canonical_included_trade_count=canonical_result.included_trade_count if canonical_result else 0,
        canonical_included_volume=canonical_result.included_volume if canonical_result else None,
        canonical_vwap=canonical_result.vwap if canonical_result else None,
        effective_included_trade_count=effective_result.included_trade_count if effective_result else 0,
        effective_included_volume=effective_result.included_volume if effective_result else None,
        effective_vwap=effective_result.vwap if effective_result else None,
        applied_correction_count=context.tape.applied_correction_count,
        applied_cancel_count=context.tape.applied_cancel_count,
        reconstruction_anomaly_count=len(context.tape.anomalies),
        reconstruction_anomaly_counts_by_reason=context.anomaly_counts_by_reason,
    )


def _safe_anchored_vwap(
    trades: tuple,
    anchor: VwapAnchor,
    source_mode: VwapSourceMode,
    trading_date: date | None,
) -> AnchoredVwapResult | None:
    try:
        return calculate_anchored_vwap(trades, anchor, source_mode, str(trading_date) if trading_date else None)
    except ValueError:
        return None


@dataclass(frozen=True)
class VolumeProfileAnalysisResult:
    """Immutable factual Volume Profile report; carries no score or recommendation.

    The primary (headline) profile is always EFFECTIVE_TAPE, since corrections and
    cancels have already been reconstructed there. A concise canonical NEW-only
    comparison is retained so the two are never silently mixed (0Q section 25).
    """

    dataset_id: UUID
    instrument: InstrumentIdentity
    trading_date: date | None

    session_definition_id: str | None
    session_policy_version: str | None

    anchor_kind: AnchorKind
    anchor_timestamp_utc: datetime

    dataset_first_trade_timestamp: datetime
    dataset_last_trade_timestamp: datetime

    coverage: AnchorCoverage
    dataset_begins_after_anchor: bool
    unobserved_pre_capture_interval: timedelta | None

    session_end_utc: datetime | None
    dataset_ends_before_session_end: bool | None

    first_included_trade_timestamp: datetime | None
    last_included_trade_timestamp: datetime | None

    source_mode: VwapSourceMode

    selected_trade_count: int
    selected_volume: Decimal | None
    vwap: Decimal | None

    tick_size: Decimal | None
    price_grid_policy_id: str | None
    price_grid_policy_version: str | None

    profile: VolumeAtPriceProfile | None
    value_area: ValueAreaResult | None

    invalid_tick_trade_count: int

    applied_correction_count: int
    applied_cancel_count: int
    reconstruction_anomaly_count: int
    reconstruction_anomaly_counts_by_reason: tuple[tuple[str, int], ...]

    canonical_selected_trade_count: int
    canonical_selected_volume: Decimal | None
    canonical_vwap: Decimal | None
    canonical_profile: VolumeAtPriceProfile | None
    canonical_value_area: ValueAreaResult | None

    @property
    def differs_from_canonical(self) -> bool | None:
        """None when either side has no profile to compare; otherwise a strict comparison."""
        if self.profile is None or self.canonical_profile is None:
            return None
        return (
            self.profile.point_of_control.price != self.canonical_profile.point_of_control.price
            or self.profile.total_volume != self.canonical_profile.total_volume
            or self.profile.levels != self.canonical_profile.levels
        )


def analyze_volume_profile_dataset(
    store: LaboratoryStore,
    dataset_id: UUID,
    anchor_kind: AnchorKind,
    trading_date: date | None = None,
    custom_timestamp: datetime | None = None,
    target_value_area_fraction: Decimal = DEFAULT_VALUE_AREA_FRACTION,
) -> VolumeProfileAnalysisResult:
    """Combine 0N anchor/coverage selection with 0O Volume-at-Price/POC and 0P Value Area.

    Reuses the exact same selected-trade population as `analyze_anchored_vwap_dataset`
    (via the shared `prepare_scoped_dataset` context) so VWAP, POC, VAL, and VAH are
    always reported over one identical retained-trade set.
    """
    context = prepare_scoped_dataset(store, dataset_id, anchor_kind, trading_date, custom_timestamp)
    anchor = context.anchor

    selected_effective = select_trades_from_anchor(context.scoped_effective, anchor.anchor_timestamp_utc)
    selected_canonical = select_trades_from_anchor(context.scoped_canonical, anchor.anchor_timestamp_utc)

    grid = price_grid_for_instrument(context.instrument)

    effective_vap = build_volume_at_price_profile(selected_effective, grid, VwapSourceMode.EFFECTIVE_TAPE)
    canonical_vap = build_volume_at_price_profile(selected_canonical, grid, VwapSourceMode.CANONICAL_NEW_ONLY)

    effective_value_area = (
        compute_value_area(effective_vap.profile, target_value_area_fraction) if effective_vap.profile else None
    )
    canonical_value_area = (
        compute_value_area(canonical_vap.profile, target_value_area_fraction) if canonical_vap.profile else None
    )

    unobserved_interval = (
        context.dataset_first - anchor.anchor_timestamp_utc if context.dataset_first > anchor.anchor_timestamp_utc else None
    )

    first_included = selected_effective[0].event_timestamp if selected_effective else None
    last_included = selected_effective[-1].event_timestamp if selected_effective else None

    return VolumeProfileAnalysisResult(
        dataset_id=dataset_id,
        instrument=context.instrument,
        trading_date=context.resolved_trading_date,
        session_definition_id=anchor.policy_id if anchor_kind is not AnchorKind.CUSTOM_TIMESTAMP else None,
        session_policy_version=anchor.policy_version if anchor_kind is not AnchorKind.CUSTOM_TIMESTAMP else None,
        anchor_kind=anchor_kind,
        anchor_timestamp_utc=anchor.anchor_timestamp_utc,
        dataset_first_trade_timestamp=context.dataset_first,
        dataset_last_trade_timestamp=context.dataset_last,
        coverage=context.coverage,
        dataset_begins_after_anchor=context.dataset_first > anchor.anchor_timestamp_utc,
        unobserved_pre_capture_interval=unobserved_interval,
        session_end_utc=context.coverage_window.session_end_utc if context.coverage_window else None,
        dataset_ends_before_session_end=(
            context.coverage_window.dataset_ends_before_session_end if context.coverage_window else None
        ),
        first_included_trade_timestamp=first_included,
        last_included_trade_timestamp=last_included,
        source_mode=VwapSourceMode.EFFECTIVE_TAPE,
        selected_trade_count=len(selected_effective),
        selected_volume=effective_vap.profile.total_volume if effective_vap.profile else None,
        vwap=effective_vap.profile.selected_trades_vwap if effective_vap.profile else None,
        tick_size=grid.tick_size,
        price_grid_policy_id=grid.policy_id,
        price_grid_policy_version=grid.policy_version,
        profile=effective_vap.profile,
        value_area=effective_value_area,
        invalid_tick_trade_count=len(effective_vap.invalid_tick_trades),
        applied_correction_count=context.tape.applied_correction_count,
        applied_cancel_count=context.tape.applied_cancel_count,
        reconstruction_anomaly_count=len(context.tape.anomalies),
        reconstruction_anomaly_counts_by_reason=context.anomaly_counts_by_reason,
        canonical_selected_trade_count=len(selected_canonical),
        canonical_selected_volume=canonical_vap.profile.total_volume if canonical_vap.profile else None,
        canonical_vwap=canonical_vap.profile.selected_trades_vwap if canonical_vap.profile else None,
        canonical_profile=canonical_vap.profile,
        canonical_value_area=canonical_value_area,
    )
