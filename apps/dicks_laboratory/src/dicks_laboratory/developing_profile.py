"""Deterministic cumulative VWAP / Volume-at-Price / POC / Value Area time series.

Extends the accepted 0Q single anchored Volume Profile analysis into an ordered
sequence of cumulative snapshots at wall-clock-aligned checkpoints. Every
snapshot recomputes the accepted 0N (selection/coverage), 0O (Volume-at-Price /
POC), and 0P (Value Area) engines over a cumulative retained-trade prefix; this
module introduces no new VWAP, POC, or Value Area algorithm of its own.

DEVELOPING means cumulative from the requested anchor forward, observed at
regular checkpoints -- never a rolling/moving window. See module docs at
`docs/dicks_laboratory/DEVELOPING_PROFILE_SERIES.md` for the full policy write-up.

Effective-tape historical semantics (see 0R design checkpoint): the accepted
0K6 `reconstruct_effective_tape` produces only the *final* reconstructed
effective state; it does not preserve enough information to answer "what would
the effective trade state have been as of an earlier moment, before a later
correction/cancel arrived." Consequently the EFFECTIVE_TAPE developing series
here is a *retrospectively reconstructed effective-tape series*: each snapshot
reflects the final accepted lifecycle interpretation of source events, sliced
by each effective trade's own (possibly corrected) `event_timestamp`. It is
NOT a model of what the feed had told us by that wall-clock instant. This
module does not attempt point-in-time feed-knowledge reconstruction.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from dicks_laboratory.analysis import AnchorCoverage, prepare_scoped_dataset
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.models import InstrumentIdentity
from dicks_laboratory.sessions import AnchorKind, select_trades_from_anchor
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.value_area import DEFAULT_VALUE_AREA_FRACTION, compute_value_area
from dicks_laboratory.volume_profile import build_volume_at_price_profile, price_grid_for_instrument

# There is no exchange or universal vendor standard for how to checkpoint a
# developing Volume Profile time series. This is an explicit, versioned
# Dick's Laboratory policy choice.
DEVELOPING_PROFILE_SLICE_POLICY_ID = "DICKS_LAB_DEVELOPING_PROFILE_SLICE_POLICY"
DEVELOPING_PROFILE_SLICE_POLICY_VERSION = "V1_WALL_CLOCK_ALIGNED_HALF_OPEN_CUMULATIVE_NO_PRECAPTURE_TERMINAL_INCLUSIVE"


class SliceInterval(StrEnum):
    """Supported developing-profile checkpoint intervals (0R: 1/5/15 minutes only)."""

    ONE_MINUTE = "ONE_MINUTE"
    FIVE_MINUTES = "FIVE_MINUTES"
    FIFTEEN_MINUTES = "FIFTEEN_MINUTES"

    @property
    def minutes(self) -> int:
        return _SLICE_INTERVAL_MINUTES[self]


_SLICE_INTERVAL_MINUTES: dict[SliceInterval, int] = {
    SliceInterval.ONE_MINUTE: 1,
    SliceInterval.FIVE_MINUTES: 5,
    SliceInterval.FIFTEEN_MINUTES: 15,
}

DEFAULT_SLICE_INTERVAL = SliceInterval.FIVE_MINUTES


def next_aligned_boundary_strictly_after(timestamp: datetime, interval: SliceInterval) -> datetime:
    """Smallest wall-clock-aligned boundary strictly greater than `timestamp`.

    Alignment is on UTC minute boundaries where `minute % interval.minutes == 0`.
    Because America/Chicago differs from UTC by a whole number of hours (never a
    fractional minute offset), this UTC alignment corresponds to the same clock
    minutes in America/Chicago for every 0R-supported interval (1/5/15 minutes).
    """
    minutes = interval.minutes
    floor = timestamp.replace(second=0, microsecond=0)
    aligned_minute = (floor.minute // minutes) * minutes
    candidate = floor.replace(minute=aligned_minute)
    while candidate <= timestamp:
        candidate += timedelta(minutes=minutes)
    return candidate


@dataclass(frozen=True)
class DevelopingProfileSnapshot:
    """One immutable cumulative checkpoint; carries no interpretation or score."""

    snapshot_index: int
    slice_end_utc: datetime
    terminal_snapshot: bool

    first_included_trade_timestamp: datetime | None
    last_included_trade_timestamp: datetime | None

    new_trade_count: int
    new_volume: Decimal | None

    cumulative_trade_count: int
    cumulative_volume: Decimal | None

    vwap: Decimal | None

    profile_low: Decimal | None
    profile_high: Decimal | None
    occupied_level_count: int

    poc_price: Decimal | None
    poc_volume: Decimal | None
    poc_trade_count: int

    value_area_target_fraction: Decimal | None
    value_area_actual_fraction: Decimal | None
    val: Decimal | None
    vah: Decimal | None
    value_area_level_count: int

    invalid_tick_trade_count: int


@dataclass(frozen=True)
class DevelopingProfileSeries:
    """Immutable ordered developing-profile result; deliberately carries no score."""

    dataset_id: UUID
    instrument: InstrumentIdentity
    trading_date: date | None

    anchor_kind: AnchorKind
    anchor_timestamp_utc: datetime

    coverage: AnchorCoverage
    dataset_first_trade_timestamp: datetime
    dataset_last_trade_timestamp: datetime
    dataset_begins_after_anchor: bool
    unobserved_pre_capture_interval: timedelta | None
    session_end_utc: datetime | None
    dataset_ends_before_session_end: bool | None

    source_mode: VwapSourceMode

    slice_policy_id: str
    slice_policy_version: str
    slice_interval: SliceInterval
    target_value_area_fraction: Decimal

    applied_correction_count: int
    applied_cancel_count: int
    reconstruction_anomaly_count: int
    reconstruction_anomaly_counts_by_reason: tuple[tuple[str, int], ...]

    snapshots: tuple[DevelopingProfileSnapshot, ...]


def build_developing_profile_series(
    store: LaboratoryStore,
    dataset_id: UUID,
    anchor_kind: AnchorKind,
    trading_date: date | None = None,
    custom_timestamp: datetime | None = None,
    slice_interval: SliceInterval = DEFAULT_SLICE_INTERVAL,
    source_mode: VwapSourceMode = VwapSourceMode.EFFECTIVE_TAPE,
    target_value_area_fraction: Decimal = DEFAULT_VALUE_AREA_FRACTION,
) -> DevelopingProfileSeries:
    """Build a deterministic cumulative developing series over one anchored selection.

    Reuses the exact same anchor/coverage/session scoping as the 0Q static analysis
    (via `prepare_scoped_dataset`), then reapplies the accepted Volume-at-Price/POC
    (0O) and Value Area (0P) engines to successive cumulative retained-trade
    prefixes. Produces zero snapshots (never fabricated empty ones) when the
    requested anchor has no retained observations at or after it.
    """
    context = prepare_scoped_dataset(store, dataset_id, anchor_kind, trading_date, custom_timestamp)
    anchor = context.anchor

    scoped = context.scoped_effective if source_mode is VwapSourceMode.EFFECTIVE_TAPE else context.scoped_canonical
    selected = select_trades_from_anchor(scoped, anchor.anchor_timestamp_utc)

    unobserved_interval = (
        context.dataset_first - anchor.anchor_timestamp_utc if context.dataset_first > anchor.anchor_timestamp_utc else None
    )

    snapshots: tuple[DevelopingProfileSnapshot, ...] = ()
    if selected:
        grid = price_grid_for_instrument(context.instrument)
        snapshots = _build_snapshots(selected, grid, source_mode, slice_interval, target_value_area_fraction)

    return DevelopingProfileSeries(
        dataset_id=dataset_id,
        instrument=context.instrument,
        trading_date=context.resolved_trading_date,
        anchor_kind=anchor_kind,
        anchor_timestamp_utc=anchor.anchor_timestamp_utc,
        coverage=context.coverage,
        dataset_first_trade_timestamp=context.dataset_first,
        dataset_last_trade_timestamp=context.dataset_last,
        dataset_begins_after_anchor=context.dataset_first > anchor.anchor_timestamp_utc,
        unobserved_pre_capture_interval=unobserved_interval,
        session_end_utc=context.coverage_window.session_end_utc if context.coverage_window else None,
        dataset_ends_before_session_end=(
            context.coverage_window.dataset_ends_before_session_end if context.coverage_window else None
        ),
        source_mode=source_mode,
        slice_policy_id=DEVELOPING_PROFILE_SLICE_POLICY_ID,
        slice_policy_version=DEVELOPING_PROFILE_SLICE_POLICY_VERSION,
        slice_interval=slice_interval,
        target_value_area_fraction=target_value_area_fraction,
        applied_correction_count=context.tape.applied_correction_count,
        applied_cancel_count=context.tape.applied_cancel_count,
        reconstruction_anomaly_count=len(context.tape.anomalies),
        reconstruction_anomaly_counts_by_reason=context.anomaly_counts_by_reason,
        snapshots=snapshots,
    )


def _build_snapshots(
    selected: tuple,
    grid,
    source_mode: VwapSourceMode,
    slice_interval: SliceInterval,
    target_value_area_fraction: Decimal,
) -> tuple[DevelopingProfileSnapshot, ...]:
    first_trade_ts = selected[0].event_timestamp
    last_trade_ts = selected[-1].event_timestamp
    first_cutoff = next_aligned_boundary_strictly_after(first_trade_ts, slice_interval)
    terminal_cutoff = next_aligned_boundary_strictly_after(last_trade_ts, slice_interval)

    cutoffs = [first_cutoff]
    while cutoffs[-1] < terminal_cutoff:
        cutoffs.append(cutoffs[-1] + timedelta(minutes=slice_interval.minutes))

    snapshots = []
    previous_trade_count = 0
    previous_volume: Decimal | None = None
    for index, cutoff in enumerate(cutoffs):
        prefix = tuple(trade for trade in selected if trade.event_timestamp < cutoff)
        vap = build_volume_at_price_profile(prefix, grid, source_mode)
        profile = vap.profile
        value_area = compute_value_area(profile, target_value_area_fraction) if profile is not None else None

        cumulative_trade_count = len(prefix)
        cumulative_volume = profile.total_volume if profile is not None else None
        new_trade_count = cumulative_trade_count - previous_trade_count
        new_volume = (
            cumulative_volume - previous_volume if cumulative_volume is not None and previous_volume is not None else None
        )

        snapshots.append(
            DevelopingProfileSnapshot(
                snapshot_index=index,
                slice_end_utc=cutoff,
                terminal_snapshot=index == len(cutoffs) - 1,
                first_included_trade_timestamp=prefix[0].event_timestamp if prefix else None,
                last_included_trade_timestamp=prefix[-1].event_timestamp if prefix else None,
                new_trade_count=new_trade_count,
                new_volume=new_volume,
                cumulative_trade_count=cumulative_trade_count,
                cumulative_volume=cumulative_volume,
                vwap=profile.selected_trades_vwap if profile is not None else None,
                profile_low=profile.lowest_price if profile is not None else None,
                profile_high=profile.highest_price if profile is not None else None,
                occupied_level_count=len(profile.levels) if profile is not None else 0,
                poc_price=profile.point_of_control.price if profile is not None else None,
                poc_volume=profile.point_of_control.volume if profile is not None else None,
                poc_trade_count=profile.point_of_control.trade_count if profile is not None else 0,
                value_area_target_fraction=value_area.target_fraction if value_area is not None else None,
                value_area_actual_fraction=value_area.included_fraction if value_area is not None else None,
                val=value_area.value_area_low.price if value_area is not None else None,
                vah=value_area.value_area_high.price if value_area is not None else None,
                value_area_level_count=value_area.included_level_count if value_area is not None else 0,
                invalid_tick_trade_count=len(vap.invalid_tick_trades),
            )
        )
        previous_trade_count = cumulative_trade_count
        if cumulative_volume is not None:
            previous_volume = cumulative_volume

    return tuple(snapshots)
