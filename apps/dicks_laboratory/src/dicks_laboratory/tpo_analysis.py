"""Read-only TPO / Market Profile analysis over one durable Laboratory dataset (0Y-A).

SOURCE DATA -> NORMALIZED TRADE OBSERVATIONS -> DERIVED TPO PROFILE. Reuses the
accepted trading-date scoping and effective-tape reconstruction
(`prepare_scoped_dataset`), so TPO and Volume Profile are computed over one
identical retained tape. Dataset quality is reported alongside the profile and
never altered or "filled": a TPO profile never implies the tape was complete.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID
from zoneinfo import ZoneInfo

from dicks_laboratory.analysis import prepare_scoped_dataset
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.models import InstrumentIdentity
from dicks_laboratory.quality import DatasetQualityEvidenceType, summarize_dataset_quality
from dicks_laboratory.sessions import AnchorKind, select_trades_from_anchor
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_profile import (
    DEFAULT_PERIOD_MINUTES,
    US_CASH_PROFILE,
    StudyWindow,
    TpoProfile,
    build_period_slots,
    build_tpo_profile,
)
from dicks_laboratory.value_area import ValueAreaResult, compute_value_area
from dicks_laboratory.volume_profile import VolumeAtPriceProfile, build_volume_at_price_profile, price_grid_for_instrument

_CT = ZoneInfo("America/Chicago")


class QualityStatus(StrEnum):
    COMPLETE = "COMPLETE / NO KNOWN GAPS"
    INCOMPLETE = "INCOMPLETE"  # at least one KNOWN_GAP
    SUSPECTED = "QUALIFIED / SUSPECTED GAPS"  # no KNOWN_GAP, at least one SUSPECTED_GAP


@dataclass(frozen=True)
class TpoDatasetQuality:
    """Recorded quality evidence, restated beside the profile; never a fitness verdict."""

    status: QualityStatus
    known_gap_count: int
    suspected_gap_count: int
    known_gap_duration: timedelta
    gaps_overlapping_study_window: int
    lifecycle_state: str | None  # None = untracked (pre-0V dataset)
    capture_started_at: datetime | None
    capture_ended_at: datetime | None
    study_window_captured: bool | None  # None = capture interval not recorded


@dataclass(frozen=True)
class TpoAnalysisResult:
    dataset_id: UUID
    instrument: InstrumentIdentity
    trading_date: date
    window: StudyWindow
    window_start_utc: datetime
    window_end_utc: datetime
    period_minutes: int
    source_mode: VwapSourceMode
    applied_correction_count: int
    applied_cancel_count: int
    quality: TpoDatasetQuality
    profile: TpoProfile | None
    volume_profile: VolumeAtPriceProfile | None  # same trades, same window
    volume_value_area: ValueAreaResult | None


def analyze_tpo_dataset(
    store: LaboratoryStore,
    dataset_id: UUID,
    trading_date: date | None = None,
    period_minutes: int = DEFAULT_PERIOD_MINUTES,
    window: StudyWindow = US_CASH_PROFILE,
) -> TpoAnalysisResult:
    """TPO profile of the effective tape inside the study window, plus quality and a volume comparison."""
    context = prepare_scoped_dataset(store, dataset_id, AnchorKind.SESSION_OPEN, trading_date, None)
    resolved = context.resolved_trading_date
    build_period_slots(resolved, period_minutes, window)  # validate before any work
    start_utc, end_utc = window.bounds_utc(resolved)
    selected = select_trades_from_anchor(context.scoped_effective, start_utc, end_utc)

    grid = price_grid_for_instrument(context.instrument)
    profile = build_tpo_profile(selected, grid, resolved, period_minutes, window)
    volume = build_volume_at_price_profile(selected, grid, VwapSourceMode.EFFECTIVE_TAPE).profile

    return TpoAnalysisResult(
        dataset_id=dataset_id,
        instrument=context.instrument,
        trading_date=resolved,
        window=window,
        window_start_utc=start_utc,
        window_end_utc=end_utc,
        period_minutes=period_minutes,
        source_mode=VwapSourceMode.EFFECTIVE_TAPE,
        applied_correction_count=context.tape.applied_correction_count,
        applied_cancel_count=context.tape.applied_cancel_count,
        quality=_dataset_quality(store, dataset_id, start_utc, end_utc),
        profile=profile,
        volume_profile=volume,
        volume_value_area=compute_value_area(volume) if volume else None,
    )


def _dataset_quality(store: LaboratoryStore, dataset_id: UUID, start: datetime, end: datetime) -> TpoDatasetQuality:
    dataset = store.load_dataset(dataset_id)
    events = store.load_quality_events(dataset_id)
    summary = summarize_dataset_quality(events)
    gap_types = {DatasetQualityEvidenceType.KNOWN_GAP, DatasetQualityEvidenceType.SUSPECTED_GAP}
    overlapping = sum(
        1 for e in events if e.evidence_type in gap_types and e.interval_start < end and e.interval_end > start
    )
    if summary.known_gap_count:
        status = QualityStatus.INCOMPLETE
    elif summary.suspected_gap_count:
        status = QualityStatus.SUSPECTED
    else:
        status = QualityStatus.COMPLETE
    started, ended = dataset.capture_started_at, dataset.capture_ended_at
    lifecycle = store.load_dataset_lifecycle_state(dataset_id)
    return TpoDatasetQuality(
        status=status,
        known_gap_count=summary.known_gap_count,
        suspected_gap_count=summary.suspected_gap_count,
        known_gap_duration=summary.known_gap_duration,
        gaps_overlapping_study_window=overlapping,
        lifecycle_state=lifecycle.value if lifecycle else None,
        capture_started_at=started,
        capture_ended_at=ended,
        study_window_captured=None if started is None or ended is None else (started <= start and ended >= end),
    )


# --- text rendering -------------------------------------------------------------

def _ct(ts: datetime) -> str:
    return ts.astimezone(_CT).strftime("%H:%M")


def _utc(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ticks(points: Decimal, increment: Decimal) -> str:
    return f"{points} ({int(points / increment)} ticks)"


def render_quality(quality: TpoDatasetQuality) -> list[str]:
    lines = ["QUALITY:", f"  {quality.status.value}"]
    if quality.status is not QualityStatus.COMPLETE:
        lines += [f"  KNOWN_GAP={quality.known_gap_count}", f"  SUSPECTED_GAP={quality.suspected_gap_count}"]
        if quality.known_gap_count:
            lines.append(f"  Known-gap duration: {quality.known_gap_duration.total_seconds():.3f}s")
        lines.append(f"  Gaps overlapping study window: {quality.gaps_overlapping_study_window}")
        lines.append("  The source tape is NOT complete; the profile is computed from retained trades only")
        lines.append("  and no gap is filled.")
    lines.append(f"  Lifecycle: {quality.lifecycle_state or 'UNTRACKED (pre-0V)'}")
    if quality.study_window_captured is None:
        lines.append("  Study window captured: UNKNOWN (capture interval not recorded)")
    elif quality.study_window_captured:
        lines.append("  Study window captured: YES")
    else:
        lines.append(f"  Study window captured: NO -- STUDY WINDOW NOT FULLY CAPTURED "
                     f"(capture {_utc(quality.capture_started_at)} .. {_utc(quality.capture_ended_at)})")
    return lines


def render_matrix(profile: TpoProfile) -> list[str]:
    """Prices descending; letters chronological; marks for POC/VAH/VAL/IBH/IBL; '|' = in value area."""
    va, ib = profile.value_area, profile.initial_balance
    width = max(len(str(level.price)) for level in profile.levels)
    lines = [f"  {'Price':>{width}}  TPO  {'Marks':<19}  Periods"]
    for level in reversed(profile.levels):
        marks = [tag for tag, hit in (
            ("POC", level.price == profile.poc),
            ("VAH", level.price == va.high),
            ("VAL", level.price == va.low),
            ("IBH", ib is not None and level.price == ib.high),
            ("IBL", ib is not None and level.price == ib.low),
        ) if hit]
        in_va = "|" if va.low <= level.price <= va.high else " "
        lines.append(f"  {str(level.price):>{width}}  {level.tpo_count:>3}  {in_va} {' '.join(marks):<17}  {level.periods}")
    return lines


def render_tpo_report(result: TpoAnalysisResult, show_matrix: bool = True, compare_volume: bool = False) -> str:
    profile = result.profile
    lines = ["Dick's Laboratory -- TPO / Market Profile", ""]
    lines += [f"Dataset:        {result.dataset_id}",
              f"Instrument:     {result.instrument.canonical_id}",
              f"Trading date:   {result.trading_date.isoformat()}", ""]
    lines += [f"Profile window: {result.window.window_id} ({result.window.policy_version})",
              f"                {_ct(result.window_start_utc)}-{_ct(result.window_end_utc)} "
              f"{result.window.timezone_name}, [start, end)",
              f"                UTC {_utc(result.window_start_utc)} .. {_utc(result.window_end_utc)}",
              "                Laboratory cash-study window; not the CME Globex session.",
              f"Period size:    {result.period_minutes} minutes",
              f"Source tape:    {result.source_mode.value} "
              f"(corrections {result.applied_correction_count}, cancels {result.applied_cancel_count})", ""]
    lines += render_quality(result.quality)
    lines.append("")
    if profile is None:
        lines += ["No retained trades fall inside the study window.",
                  "No TPO profile, POC, Value Area or Initial Balance was calculated."]
        return "\n".join(lines)

    va, ib, inc = profile.value_area, profile.initial_balance, profile.price_increment
    lines += [f"Price increment: {inc} ({profile.price_grid_policy_id})",
              f"Eligible trades: {profile.selected_trade_count:,}"
              + (f"  (off-grid excluded: {profile.invalid_tick_trade_count})" if profile.invalid_tick_trade_count else ""),
              ""]
    lines += [f"Profile high:   {profile.profile_high}",
              f"Profile low:    {profile.profile_low}",
              f"Profile range:  {_ticks(profile.profile_range, inc)}", ""]
    if ib is None:
        lines += ["Initial Balance: not available (no trades in the first 60 minutes)", ""]
    else:
        lines += [f"IB high:        {ib.high}   (periods {ib.period_labels})",
                  f"IB low:         {ib.low}",
                  f"IB range:       {_ticks(ib.range, inc)}",
                  f"Range extension above IB: {_ticks(ib.extension_above, inc)}"
                  + (f", first in period {ib.first_extension_above_period}" if ib.first_extension_above_period else ""),
                  f"Range extension below IB: {_ticks(ib.extension_below, inc)}"
                  + (f", first in period {ib.first_extension_below_period}" if ib.first_extension_below_period else ""),
                  ""]
    lines += [f"TPO POC:        {profile.poc}   ({profile.poc_policy_version})",
              f"TPO VAL:        {va.low}",
              f"TPO VAH:        {va.high}",
              f"Value-area %:   {va.included_tpos}/{profile.total_tpo_count} TPOs = "
              f"{(va.included_fraction * 100).quantize(Decimal('0.01'))}% "
              f"(target {format((va.target_fraction * 100).normalize(), 'f')}%; {va.policy_version})",
              f"Total TPOs:     {profile.total_tpo_count}",
              f"Periods present: {profile.periods_present} "
              f"({len(profile.periods_present)} of {len(profile.periods)})", ""]
    lines.append("Periods (Chicago):")
    for p in profile.periods:
        high, low = (str(p.high), str(p.low)) if p.trade_count else ("--", "--")
        lines.append(f"  {p.label}  {_ct(p.start_utc)}-{_ct(p.end_utc)}  high {high:>10}  low {low:>10}  "
                     f"trades {p.trade_count:,}")
    lines.append("")
    if compare_volume and result.volume_profile is not None and result.volume_value_area is not None:
        vp, vva = result.volume_profile, result.volume_value_area
        lines += ["Market Profile vs Volume Profile (same effective tape, same window):",
                  f"  {'':4} {'TPO':>10}  {'Volume':>10}",
                  f"  {'POC':4} {str(profile.poc):>10}  {str(vp.point_of_control.price):>10}",
                  f"  {'VAL':4} {str(va.low):>10}  {str(vva.value_area_low.price):>10}",
                  f"  {'VAH':4} {str(va.high):>10}  {str(vva.value_area_high.price):>10}",
                  "  TPO: time/opportunity distribution (distinct periods per price).",
                  f"  Volume: contract-volume distribution ({vp.total_volume} contracts; "
                  f"{vva.value_area_policy_version}).",
                  ""]
    if show_matrix:
        lines.append("TPO matrix ('|' = inside value area):")
        lines += render_matrix(profile)
        lines.append("")
    lines += ["Boundary: derived facts only -- no interpretation, day type or signal.",
              "Ordinary CME schedule only; holiday/early-close overrides not modeled."]
    return "\n".join(lines)
