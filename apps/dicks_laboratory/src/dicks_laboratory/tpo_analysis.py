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
from dicks_laboratory.tpo_day_structure import (
    ClassificationOutcome,
    DayTypeClassification,
    QualityGrade,
    build_day_structure_facts,
    classification_quality,
    classify_day_type,
    study_window_terminal,
)
from dicks_laboratory.tpo_structure import CandidateStatus, ProfileStructure, ZoneLocation, build_profile_structure
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

    @property
    def structural_qualifications(self) -> tuple[str, ...]:
        """0Y-B: reasons an apparent one-TPO zone or flat extreme could be a data artifact."""
        reasons = []
        if self.gaps_overlapping_study_window:
            reasons.append(f"gap evidence (KNOWN/SUSPECTED) overlaps the study window: "
                           f"{self.gaps_overlapping_study_window}")
        if self.study_window_captured is False:
            reasons.append("STUDY WINDOW NOT FULLY CAPTURED")
        elif self.study_window_captured is None:
            reasons.append("capture interval not recorded; study-window coverage unverified")
        if self.lifecycle_state != "FINALIZED":
            reasons.append(f"lifecycle {self.lifecycle_state or 'UNTRACKED'} (not FINALIZED)")
        return tuple(reasons)


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
    structure: ProfileStructure | None = None  # 0Y-B derived structural facts
    day_structure: DayTypeClassification | None = None  # 0Y-C day-structure facts + day-type candidates


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
    quality = _dataset_quality(store, dataset_id, start_utc, end_utc)
    structure = build_profile_structure(profile) if profile else None
    day_structure = None
    if profile is not None:
        facts = build_day_structure_facts(profile, structure, study_window_terminal(selected, profile, grid))
        day_structure = classify_day_type(facts, classification_quality(
            quality.study_window_captured, quality.gaps_overlapping_study_window, quality.lifecycle_state))

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
        quality=quality,
        profile=profile,
        volume_profile=volume,
        volume_value_area=compute_value_area(volume) if volume else None,
        structure=structure,
        day_structure=day_structure,
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


def render_matrix(profile: TpoProfile, structure: ProfileStructure | None = None) -> list[str]:
    """Prices descending; letters chronological; marks for POC/VAH/VAL/IBH/IBL; '|' = in value area.

    With `structure` (0Y-B), a column tags tail rows (TAIL) and interior one-TPO rows (SP).
    """
    va, ib = profile.value_area, profile.initial_balance
    width = max(len(str(level.price)) for level in profile.levels)
    tags: dict = {}
    if structure is not None:
        for zone in structure.zones:
            tag = "SP" if zone.location is ZoneLocation.INTERIOR else "TAIL"
            tags.update({price: tag for price, _ in zone.level_periods})
    struct_head = f"{'Str':<4}  " if structure is not None else ""
    lines = [f"  {'Price':>{width}}  TPO  {'Marks':<19}  {struct_head}Periods"]
    for level in reversed(profile.levels):
        marks = [tag for tag, hit in (
            ("POC", level.price == profile.poc),
            ("VAH", level.price == va.high),
            ("VAL", level.price == va.low),
            ("IBH", ib is not None and level.price == ib.high),
            ("IBL", ib is not None and level.price == ib.low),
        ) if hit]
        in_va = "|" if va.low <= level.price <= va.high else " "
        struct = f"{tags.get(level.price, ''):<4}  " if structure is not None else ""
        lines.append(f"  {str(level.price):>{width}}  {level.tpo_count:>3}  {in_va} {' '.join(marks):<17}  "
                     f"{struct}{level.periods}")
    return lines


def render_tpo_report(
    result: TpoAnalysisResult,
    show_matrix: bool = True,
    compare_volume: bool = False,
    show_structure: bool = False,
    show_day_structure: bool = False,
) -> str:
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
    structure = result.structure if show_structure else None
    if structure is not None:
        lines += render_structure(structure, result.quality, inc)
    if show_day_structure and result.day_structure is not None:
        lines += render_day_structure(result.day_structure, inc)
    if show_matrix:
        if structure is not None:
            lines.append("TPO matrix ('|' = inside value area; TAIL = extreme one-TPO run; SP = interior one-TPO zone):")
        else:
            lines.append("TPO matrix ('|' = inside value area):")
        lines += render_matrix(profile, structure)
        lines.append("")
    boundary = ("derived facts and day-type CANDIDATES only -- no interpretation or signal."
                if show_day_structure and result.day_structure is not None
                else "derived facts only -- no interpretation, day type or signal.")
    lines += [f"Boundary: {boundary}",
              "Ordinary CME schedule only; holiday/early-close overrides not modeled."]
    return "\n".join(lines)


def _yn(value: bool | None) -> str:
    return "--" if value is None else ("yes" if value else "no")


def _opt(value: Decimal | None) -> str:
    return "--" if value is None else str(value)


def _ratio(value: Decimal | None) -> str:
    return "undefined (IB range = 0)" if value is None else f"{value.quantize(Decimal('0.0001'))} x IB range"


def render_structure(structure: ProfileStructure, quality: TpoDatasetQuality, inc: Decimal) -> list[str]:
    """0Y-B structure section: raw facts first, then the two CANDIDATE labels; no interpretation."""
    qualified = quality.structural_qualifications
    lines = [f"STRUCTURE ({structure.policy_id} {structure.policy_version}):"]
    if qualified:
        lines.append("  *** STRUCTURAL FEATURES ARE QUALITY-QUALIFIED ***")
        lines += [f"    - {reason}" for reason in qualified]
        lines.append("    An apparent one-TPO zone or flat extreme may be an artifact of missing trades.")
    lines.append(f"  One-TPO levels: {len(structure.one_tpo_levels)}")
    lines.append(f"  One-TPO zones (single-print candidates), high to low: {len(structure.zones)}")
    if structure.zones:
        lines.append(f"    {'high':>10}  {'low':>10}  rows  ticks  {'span':>6}  periods  {'location':<14}  "
                     f"{'vs IB':<14}  vs value area")
    for z in reversed(structure.zones):
        lines.append(f"    {str(z.high):>10}  {str(z.low):>10}  {z.level_count:>4}  {z.tick_count:>5}  "
                     f"{str(z.span_points):>6}  {z.periods:<7}  {z.location.value:<14}  {z.ib_relation.value:<14}  "
                     f"{z.value_relation.value}")
    suffix = " (quality-qualified)" if qualified else ""
    for ex, word in ((structure.upper, "HIGH"), (structure.lower, "LOW")):
        lines += [
            f"  {'Upper' if word == 'HIGH' else 'Lower'} extreme (PROFILE_{word}): {ex.price}",
            f"    letters at extreme: {ex.letters_at_extreme} ({ex.tpo_count_at_extreme} TPO"
            f"{'s' if ex.tpo_count_at_extreme != 1 else ''})",
            f"    tail: {ex.tail_level_count} rows / {ex.tail_tick_count} ticks / span {ex.tail_span_points} pts"
            + (f", to {ex.tail_inner_price}, periods {ex.tail_periods}, formed in final period: "
               f"{_yn(ex.tail_formed_in_final_period)}" if ex.tail_level_count else ""),
            f"    EXCESS_{word}_CANDIDATE: {ex.excess_candidate.value}"
            + (suffix if ex.excess_candidate is CandidateStatus.YES else "")
            + f"   (rule: tail >= {structure.excess_min_tail_levels} one-TPO rows)",
            f"    POOR_{word}_CANDIDATE:   {ex.poor_candidate.value}"
            + (suffix if ex.poor_candidate is CandidateStatus.YES else "")
            + f"   (rule: >= {structure.poor_extreme_min_tpos} TPOs at the exact extreme)",
        ]
    ibx = structure.ib_extension
    if ibx is None:
        lines.append("  IB extension detail: not available (no Initial Balance)")
    else:
        lines += [
            f"  IB extension detail (IB {ibx.ib_low}-{ibx.ib_high}, range {_ticks(ibx.ib_range, inc)}):",
            f"    max above IB: {_ticks(ibx.max_extension_above, inc)} = {_ratio(ibx.extension_above_fraction_of_ib)}; "
            f"new post-IB highs: {ibx.periods_new_post_ib_high or 'none'}",
            f"    max below IB: {_ticks(ibx.max_extension_below, inc)} = {_ratio(ibx.extension_below_fraction_of_ib)}; "
            f"new post-IB lows: {ibx.periods_new_post_ib_low or 'none'}",
        ]
    lines.append("  Period range facts ('--' = not applicable):")
    lines.append(f"    P  {'high':>10}  {'low':>10}  newHigh  newLow  extIBH  extIBL  {'hiExt':>6}  {'loExt':>6}")
    for p in structure.periods:
        lines.append(
            f"    {p.label}  {_opt(p.high):>10}  {_opt(p.low):>10}  {_yn(p.new_profile_high):<7}  "
            f"{_yn(p.new_profile_low):<6}  {_yn(p.extended_ib_high):<6}  {_yn(p.extended_ib_low):<6}  "
            f"{_opt(p.high_extension):>6}  {_opt(p.low_extension):>6}")
    lines += ["  Facts and CANDIDATE labels only: no excess/poor/single-print interpretation, day type or signal.", ""]
    return lines


def _p4(value: Decimal | None, undefined: str = "undefined") -> str:
    return undefined if value is None else str(value.quantize(Decimal("0.0001")))


def render_day_structure(day: DayTypeClassification, inc: Decimal) -> list[str]:
    """0Y-C: day-structure facts first, then every evaluated candidate with its conditions."""
    f = day.facts
    lines = ["DAY STRUCTURE FACTS:",
             f"  Profile: {f.profile_low}-{f.profile_high}, range {_ticks(f.profile_range, inc)}, "
             f"midpoint {f.profile_midpoint}"]
    if f.ib_range is None:
        lines.append("  Initial Balance: not available")
    else:
        lines += [
            f"  IB: {f.ib_low}-{f.ib_high}, range {_ticks(f.ib_range, inc)}, midpoint {f.ib_midpoint}",
            f"  IB share of range (IB/profile): {_p4(f.ib_share_of_range, 'undefined (profile range = 0)')}   "
            f"range multiple of IB (profile/IB): {_p4(f.range_multiple_of_ib, 'undefined (IB range = 0)')}",
            f"  Extension above IB: {_ticks(f.extension_above, inc)} = "
            f"{_p4(f.extension_above_multiple_of_ib, 'undefined')} x IB; "
            f"periods beyond IB high: {f.periods_extending_above_ib or 'none'} "
            f"({len(f.periods_extending_above_ib)}); new post-IB highs: {f.new_post_ib_high_periods or 'none'}",
            f"  Extension below IB: {_ticks(f.extension_below, inc)} = "
            f"{_p4(f.extension_below_multiple_of_ib, 'undefined')} x IB; "
            f"periods beyond IB low: {f.periods_extending_below_ib or 'none'} "
            f"({len(f.periods_extending_below_ib)}); new post-IB lows: {f.new_post_ib_low_periods or 'none'}",
            f"  Directional state: {f.directional_state.value}   first extension: "
            f"{f.first_extension_direction.value if f.first_extension_direction else 'none'}   last extension: "
            f"{f.last_extension_direction.value if f.last_extension_direction else 'none'}",
        ]
    lines += [
        f"  POC {f.poc} (at {_p4(f.poc_percentile)} of range)   VAL {f.value_area_low}   VAH {f.value_area_high}   "
        f"VA midpoint {f.value_area_midpoint} (at {_p4(f.value_area_midpoint_percentile)})"
        + ("" if f.ib_midpoint is None else f"   IB midpoint at {_p4(f.ib_midpoint_percentile)}"),
        f"  Profile high printed by {f.periods_at_profile_high} (first {f.first_period_at_profile_high}); "
        f"profile low printed by {f.periods_at_profile_low} (first {f.first_period_at_profile_low})",
        f"  Longest run of higher lows: {f.longest_higher_low_run} periods; "
        f"of lower highs: {f.longest_lower_high_run} periods",
        f"  Upper tail: {f.upper_extreme.tail_level_count} rows; lower tail: {f.lower_extreme.tail_level_count} rows; "
        f"interior one-TPO zones: {len(f.interior_one_tpo_zones)}",
        f"  Periods without trades: {f.periods_without_trades or 'none'}",
    ]
    t = f.terminal
    if t is None:
        lines.append("  Study-window terminal price: none")
    else:
        lines.append(f"  Study-window terminal price: {t.price} at {_utc(t.timestamp_utc)} (period {t.period_label}); "
                     f"at {_p4(t.percentile_in_range)} of range; {t.distance_from_high} below high, "
                     f"{t.distance_from_low} above low")
        lines.append("    (last eligible trade before the window end -- not the CME settlement or Globex close)")
    lines.append("")

    lines.append(f"DAY-TYPE CANDIDATES ({day.policy_id} {day.policy_version}):")
    lines.append(f"  Thresholds: NORMAL IB share >= {day.normal_min_ib_share}; NORMAL_VARIATION "
                 f"{day.normal_variation_min_ib_share} <= IB share < {day.normal_min_ib_share}; TREND IB share < "
                 f"{day.normal_variation_min_ib_share} and >= {day.trend_min_new_extreme_periods} new-extreme periods")
    q = day.quality
    if q.grade is QualityGrade.QUALITY_QUALIFIED:
        lines.append("  *** DAY-TYPE CLASSIFICATION IS QUALITY-QUALIFIED ***")
        lines += [f"    - {reason}" for reason in q.reasons]
    lines.append(f"  Quality: {q.grade.value}")
    if day.outcome is ClassificationOutcome.NOT_CLASSIFIED:
        lines.append("  Outcome: NOT_CLASSIFIED -- no named day type is claimed")
        lines += [f"    - {reason}" for reason in day.not_classified_reasons]
        lines.append("    Day-structure facts above are still reported.")
    else:
        if day.outcome is ClassificationOutcome.CANDIDATE:
            label = f"{day.primary.value}_CANDIDATE" + (f", direction {day.direction.value}" if day.direction else "")
            if q.grade is QualityGrade.QUALITY_QUALIFIED:
                label += " (quality-qualified)"
        elif day.outcome is ClassificationOutcome.AMBIGUOUS:
            label = "several policies matched: " + ", ".join(c.day_type.value for c in day.matched)
        else:
            label = "no adopted policy matched"
        lines.append(f"  Outcome: {day.outcome.value} -- {label}")
        for c in day.candidates:
            lines.append(f"  {c.day_type.value}_CANDIDATE: {c.result.value}"
                         + (f" (direction {c.direction.value})" if c.direction else ""))
            for cond in c.conditions:
                mark = {True: "satisfied    ", False: "NOT satisfied", None: "not evaluated"}[cond.satisfied]
                lines.append(f"    [{mark}] {cond.name}: {cond.rule} -- {cond.observed}")
    lines.append("  Deferred (not evaluated): " + "; ".join(f"{d.name} ({d.reason})" for d in day.deferred))
    lines += ["  CANDIDATE labels are Laboratory policy outputs, not market interpretation, bias or signal.", ""]
    return lines
