"""Deterministic Market Profile day-structure facts and day-type CANDIDATES (0Y-C).

A derived layer over the accepted `TpoProfile` (0Y-A) and `ProfileStructure`
(0Y-B); it never alters either. Three kinds of output, kept apart:

  DERIVED FACT        `DayStructureFacts`: ranges, ratios, IB extension,
                      directional state, value/POC location, terminal price.
  LABORATORY POLICY   `classify_day_type`: versioned candidate rules, each a
                      list of named conditions with the observed value.
  (no interpretation) no bias, no initiative/responsive, no setup or signal.

Every ratio with a zero denominator is None ("undefined"), never 0 or infinity.
See docs/dicks_laboratory/TPO_MARKET_PROFILE_0YA.md §22-§31.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.tpo_profile import PERIOD_LABELS, TpoProfile
from dicks_laboratory.tpo_structure import ExtremeStructure, OneTpoZone, ProfileStructure
from dicks_laboratory.volume_profile import PriceGrid

# --- Laboratory day-type policy (survey: TPO_MARKET_PROFILE_0YA.md §22, §26) --------
DAY_TYPE_POLICY_ID = "DICKS_LAB_DAY_TYPE_POLICY"
DAY_TYPE_POLICY_VERSION = "V1_DIRECTIONAL_STATE_X_IB_SHARE"
# IB share = IB range / profile range. 0.85 and 0.50 are the published defaults of
# the only mechanical classifier found (Linn Software DayTypes RTX); 0.50 is also
# the "range roughly double the IB" boundary in the descriptive references.
NORMAL_MIN_IB_SHARE = Decimal("0.85")
NORMAL_VARIATION_MIN_IB_SHARE = Decimal("0.50")
# "Persistent new highs/lows through multiple periods": the minimal literal
# reading of "multiple" -- at least two post-IB periods each set a new extreme.
TREND_MIN_NEW_EXTREME_PERIODS = 2


class DirectionalState(StrEnum):
    NO_EXTENSION = "NO_EXTENSION"
    UP_ONLY = "UP_ONLY"
    DOWN_ONLY = "DOWN_ONLY"
    BOTH_SIDES = "BOTH_SIDES"


class ExtensionDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    BOTH_IN_SAME_PERIOD = "BOTH_IN_SAME_PERIOD"


class Direction(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class DayType(StrEnum):
    NORMAL_DAY = "NORMAL_DAY"
    NORMAL_VARIATION_DAY = "NORMAL_VARIATION_DAY"
    TREND_DAY = "TREND_DAY"
    NEUTRAL_DAY = "NEUTRAL_DAY"


class CandidateResult(StrEnum):
    YES = "YES"  # every evaluated condition satisfied
    NO = "NO"


class ClassificationOutcome(StrEnum):
    CANDIDATE = "CANDIDATE"  # exactly one policy matched
    AMBIGUOUS = "AMBIGUOUS"  # more than one matched; no winner is forced
    UNCLASSIFIED = "UNCLASSIFIED"  # evaluated, no adopted policy matched
    NOT_CLASSIFIED = "NOT_CLASSIFIED"  # not evaluated: coverage or profile insufficient


class QualityGrade(StrEnum):
    UNQUALIFIED = "UNQUALIFIED"
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # evaluated, but evidence of missing trades in the window
    NOT_CLASSIFIABLE = "NOT_CLASSIFIABLE"  # full study window not observed


@dataclass(frozen=True)
class ClassificationQuality:
    grade: QualityGrade
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class TerminalPrice:
    """Study-window terminal price: the last eligible trade before the window end.

    Not the CME settlement and not the Globex session close.
    """

    price: Decimal
    timestamp_utc: datetime
    period_label: str
    percentile_in_range: Decimal | None  # (price - low) / range; None when range == 0
    distance_from_high: Decimal
    distance_from_low: Decimal


@dataclass(frozen=True)
class DayStructureFacts:
    profile_high: Decimal
    profile_low: Decimal
    profile_range: Decimal
    profile_range_ticks: int
    profile_midpoint: Decimal
    ib_high: Decimal | None  # None: no Initial Balance
    ib_low: Decimal | None
    ib_range: Decimal | None
    ib_range_ticks: int | None
    ib_midpoint: Decimal | None
    ib_share_of_range: Decimal | None  # IB range / profile range
    range_multiple_of_ib: Decimal | None  # profile range / IB range
    extension_above: Decimal | None
    extension_below: Decimal | None
    extension_above_ticks: int | None
    extension_below_ticks: int | None
    extension_above_multiple_of_ib: Decimal | None
    extension_below_multiple_of_ib: Decimal | None
    directional_state: DirectionalState | None
    first_extension_direction: ExtensionDirection | None  # first post-IB period beyond the IB
    last_extension_direction: ExtensionDirection | None  # last period to set a new post-IB extreme
    periods_extending_above_ib: str  # post-IB periods whose high > IB high
    periods_extending_below_ib: str
    new_post_ib_high_periods: str  # each beat every earlier high, IB high included
    new_post_ib_low_periods: str
    poc: Decimal
    value_area_low: Decimal
    value_area_high: Decimal
    value_area_midpoint: Decimal
    poc_percentile: Decimal | None  # location within profile range, 0 = low, 1 = high
    value_area_midpoint_percentile: Decimal | None
    ib_midpoint_percentile: Decimal | None
    periods_at_profile_high: str
    periods_at_profile_low: str
    first_period_at_profile_high: str
    first_period_at_profile_low: str
    longest_higher_low_run: int  # consecutive traded periods, each low > prior low
    longest_lower_high_run: int  # consecutive traded periods, each high < prior high
    periods_without_trades: str
    upper_extreme: ExtremeStructure
    lower_extreme: ExtremeStructure
    interior_one_tpo_zones: tuple[OneTpoZone, ...]
    terminal: TerminalPrice | None


@dataclass(frozen=True)
class Condition:
    name: str
    rule: str
    observed: str
    satisfied: bool | None  # None = not evaluated (dependency outside the same-day profile)


@dataclass(frozen=True)
class DayTypeCandidate:
    day_type: DayType
    result: CandidateResult
    direction: Direction | None
    conditions: tuple[Condition, ...]

    @property
    def satisfied(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if c.satisfied is True)

    @property
    def failed(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if c.satisfied is False)

    @property
    def not_evaluated(self) -> tuple[Condition, ...]:
        return tuple(c for c in self.conditions if c.satisfied is None)


@dataclass(frozen=True)
class DeferredDayType:
    name: str
    reason: str


@dataclass(frozen=True)
class DayTypeClassification:
    policy_id: str
    policy_version: str
    normal_min_ib_share: Decimal
    normal_variation_min_ib_share: Decimal
    trend_min_new_extreme_periods: int
    quality: ClassificationQuality
    outcome: ClassificationOutcome
    primary: DayType | None  # set only for CANDIDATE
    direction: Direction | None
    candidates: tuple[DayTypeCandidate, ...]  # every evaluated policy; () when NOT_CLASSIFIED
    not_classified_reasons: tuple[str, ...]
    deferred: tuple[DeferredDayType, ...]
    facts: DayStructureFacts

    @property
    def matched(self) -> tuple[DayTypeCandidate, ...]:
        return tuple(c for c in self.candidates if c.result is CandidateResult.YES)


DEFERRED_DAY_TYPES = (
    DeferredDayType("NON_TREND_DAY",
                    "'narrow IB' / 'narrow range' are absolute or historical judgements; the same-day profile "
                    "cannot separate it from NORMAL_DAY (requires historical context)"),
    DeferredDayType("NEUTRAL_EXTREME / NEUTRAL_CENTER",
                    "close 'near an extreme' / 'in the middle' is undefined; terminal-price facts are reported"),
    DeferredDayType("DOUBLE_DISTRIBUTION_TREND_DAY",
                    "requires deterministic distribution segmentation (0Y-D candidate)"),
)


# --- facts -------------------------------------------------------------------------

def study_window_terminal(trades, profile: TpoProfile, grid: PriceGrid) -> TerminalPrice | None:
    """Last eligible (in-window, on-grid) trade; equal timestamps resolve to the later tape position."""
    last = None
    for position, trade in enumerate(trades):
        ts = trade.event_timestamp
        tick = grid.tick_index(trade.price) if profile.start_utc <= ts < profile.end_utc else None
        if tick is not None and (last is None or (ts, position) >= (last[0], last[1])):
            last = (ts, position, grid.price_at(tick))  # grid scale, like every profile price
    if last is None:
        return None
    ts, _, price = last
    label = next(p.label for p in profile.periods if p.start_utc <= ts < p.end_utc)
    return TerminalPrice(
        price=price,
        timestamp_utc=ts,
        period_label=label,
        percentile_in_range=_pct(price, profile),
        distance_from_high=profile.profile_high - price,
        distance_from_low=price - profile.profile_low,
    )


def _pct(price: Decimal, profile: TpoProfile) -> Decimal | None:
    return None if profile.profile_range == 0 else (price - profile.profile_low) / profile.profile_range


def build_day_structure_facts(
    profile: TpoProfile, structure: ProfileStructure, terminal: TerminalPrice | None
) -> DayStructureFacts:
    ib, va, inc = profile.initial_balance, profile.value_area, profile.price_increment
    va_mid = (va.low + va.high) / 2
    high_letters = structure.upper.letters_at_extreme
    low_letters = structure.lower.letters_at_extreme
    base = dict(
        profile_high=profile.profile_high,
        profile_low=profile.profile_low,
        profile_range=profile.profile_range,
        profile_range_ticks=int(profile.profile_range / inc),
        profile_midpoint=(profile.profile_high + profile.profile_low) / 2,
        poc=profile.poc,
        value_area_low=va.low,
        value_area_high=va.high,
        value_area_midpoint=va_mid,
        poc_percentile=_pct(profile.poc, profile),
        value_area_midpoint_percentile=_pct(va_mid, profile),
        periods_at_profile_high=high_letters,
        periods_at_profile_low=low_letters,
        first_period_at_profile_high=high_letters[0],
        first_period_at_profile_low=low_letters[0],
        longest_higher_low_run=_longest_run(profile, lambda prev, cur: cur.low > prev.low),
        longest_lower_high_run=_longest_run(profile, lambda prev, cur: cur.high < prev.high),
        periods_without_trades="".join(p.label for p in profile.periods if not p.trade_count),
        upper_extreme=structure.upper,
        lower_extreme=structure.lower,
        interior_one_tpo_zones=structure.interior_zones,
        terminal=terminal,
    )
    if ib is None:
        return DayStructureFacts(
            ib_high=None, ib_low=None, ib_range=None, ib_range_ticks=None, ib_midpoint=None,
            ib_share_of_range=None, range_multiple_of_ib=None, extension_above=None, extension_below=None,
            extension_above_ticks=None, extension_below_ticks=None, extension_above_multiple_of_ib=None,
            extension_below_multiple_of_ib=None, directional_state=None, first_extension_direction=None,
            last_extension_direction=None, periods_extending_above_ib="", periods_extending_below_ib="",
            new_post_ib_high_periods="", new_post_ib_low_periods="", ib_midpoint_percentile=None, **base)

    ibx = structure.ib_extension
    up, down = ib.extension_above > 0, ib.extension_below > 0
    state = (DirectionalState.BOTH_SIDES if up and down else DirectionalState.UP_ONLY if up
             else DirectionalState.DOWN_ONLY if down else DirectionalState.NO_EXTENSION)
    above = "".join(p.label for p in structure.periods if p.extended_ib_high)
    below = "".join(p.label for p in structure.periods if p.extended_ib_low)
    ib_mid = (ib.high + ib.low) / 2
    zero_ib = ib.range == 0
    return DayStructureFacts(
        ib_high=ib.high,
        ib_low=ib.low,
        ib_range=ib.range,
        ib_range_ticks=int(ib.range / inc),
        ib_midpoint=ib_mid,
        ib_share_of_range=None if profile.profile_range == 0 else ib.range / profile.profile_range,
        range_multiple_of_ib=None if zero_ib else profile.profile_range / ib.range,
        extension_above=ib.extension_above,
        extension_below=ib.extension_below,
        extension_above_ticks=int(ib.extension_above / inc),
        extension_below_ticks=int(ib.extension_below / inc),
        extension_above_multiple_of_ib=ibx.extension_above_fraction_of_ib,
        extension_below_multiple_of_ib=ibx.extension_below_fraction_of_ib,
        directional_state=state,
        first_extension_direction=_first_direction(structure),
        last_extension_direction=_last_direction(ibx.periods_new_post_ib_high, ibx.periods_new_post_ib_low),
        periods_extending_above_ib=above,
        periods_extending_below_ib=below,
        new_post_ib_high_periods=ibx.periods_new_post_ib_high,
        new_post_ib_low_periods=ibx.periods_new_post_ib_low,
        ib_midpoint_percentile=_pct(ib_mid, profile),
        **base,
    )


def _direction_of(up: bool, down: bool) -> ExtensionDirection | None:
    if up and down:
        return ExtensionDirection.BOTH_IN_SAME_PERIOD
    return ExtensionDirection.UP if up else ExtensionDirection.DOWN if down else None


def _first_direction(structure: ProfileStructure) -> ExtensionDirection | None:
    for p in structure.periods:
        direction = _direction_of(bool(p.extended_ib_high), bool(p.extended_ib_low))
        if direction is not None:
            return direction
    return None


def _last_direction(new_highs: str, new_lows: str) -> ExtensionDirection | None:
    letters = set(new_highs) | set(new_lows)
    if not letters:
        return None
    last = max(letters, key=PERIOD_LABELS.index)
    return _direction_of(last in new_highs, last in new_lows)


def _longest_run(profile: TpoProfile, step_holds) -> int:
    best = run = 0
    prev = None
    for p in profile.periods:
        if not p.trade_count:
            prev, run = None, 0
            continue
        run = run + 1 if prev is not None and step_holds(prev, p) else 1
        best = max(best, run)
        prev = p
    return best


# --- quality -------------------------------------------------------------------------

def classification_quality(
    study_window_captured: bool | None, gaps_overlapping_study_window: int, lifecycle_state: str | None
) -> ClassificationQuality:
    """V1 severity policy: an unobserved window blocks naming; gap evidence inside it qualifies it."""
    if study_window_captured is False:
        return ClassificationQuality(QualityGrade.NOT_CLASSIFIABLE, ("STUDY WINDOW NOT FULLY CAPTURED",))
    if study_window_captured is None:
        return ClassificationQuality(QualityGrade.NOT_CLASSIFIABLE,
                                     ("capture interval not recorded; study-window coverage unverified",))
    reasons = []
    if gaps_overlapping_study_window:
        reasons.append(f"gap evidence (KNOWN/SUSPECTED) overlaps the study window: {gaps_overlapping_study_window}")
    if lifecycle_state != "FINALIZED":
        reasons.append(f"lifecycle {lifecycle_state or 'UNTRACKED'} (not FINALIZED)")
    return ClassificationQuality(QualityGrade.QUALITY_QUALIFIED if reasons else QualityGrade.UNQUALIFIED,
                                 tuple(reasons))


# --- classification --------------------------------------------------------------------

def classify_day_type(facts: DayStructureFacts, quality: ClassificationQuality) -> DayTypeClassification:
    blockers = list(quality.reasons) if quality.grade is QualityGrade.NOT_CLASSIFIABLE else []
    if facts.ib_range is None:
        blockers.append("no Initial Balance (no trades in the first 60 minutes)")
    elif facts.ib_range == 0:
        blockers.append("IB range = 0: IB-relative policies undefined")
    if facts.profile_range == 0:
        blockers.append("profile range = 0")
    if facts.periods_without_trades:
        blockers.append(f"period(s) with no retained trades: {facts.periods_without_trades}")

    candidates: tuple[DayTypeCandidate, ...] = ()
    if blockers:
        outcome, primary, direction = ClassificationOutcome.NOT_CLASSIFIED, None, None
    else:
        candidates = (_normal(facts), _normal_variation(facts), _trend(facts), _neutral(facts))
        outcome, primary, direction = resolve_candidates(candidates)
    return DayTypeClassification(
        policy_id=DAY_TYPE_POLICY_ID,
        policy_version=DAY_TYPE_POLICY_VERSION,
        normal_min_ib_share=NORMAL_MIN_IB_SHARE,
        normal_variation_min_ib_share=NORMAL_VARIATION_MIN_IB_SHARE,
        trend_min_new_extreme_periods=TREND_MIN_NEW_EXTREME_PERIODS,
        quality=quality,
        outcome=outcome,
        primary=primary,
        direction=direction,
        candidates=candidates,
        not_classified_reasons=tuple(blockers),
        deferred=DEFERRED_DAY_TYPES,
        facts=facts,
    )


def resolve_candidates(
    candidates: tuple[DayTypeCandidate, ...],
) -> tuple[ClassificationOutcome, DayType | None, Direction | None]:
    """Exactly one match -> CANDIDATE; several -> AMBIGUOUS (no winner forced); none -> UNCLASSIFIED."""
    matched = [c for c in candidates if c.result is CandidateResult.YES]
    if len(matched) == 1:
        return ClassificationOutcome.CANDIDATE, matched[0].day_type, matched[0].direction
    if matched:
        return ClassificationOutcome.AMBIGUOUS, None, None
    return ClassificationOutcome.UNCLASSIFIED, None, None


def _candidate(day_type: DayType, direction: Direction | None, *conditions: Condition) -> DayTypeCandidate:
    ok = all(c.satisfied is not False for c in conditions)
    return DayTypeCandidate(day_type, CandidateResult.YES if ok else CandidateResult.NO,
                            direction if ok else None, conditions)


def _share(facts: DayStructureFacts) -> str:
    return f"IB share = {facts.ib_range} / {facts.profile_range} = {_fmt(facts.ib_share_of_range)}"


def _fmt(value: Decimal | None) -> str:
    return "undefined" if value is None else str(value.quantize(Decimal("0.0001")))


def _one_sided(facts: DayStructureFacts) -> Direction | None:
    return {DirectionalState.UP_ONLY: Direction.UP, DirectionalState.DOWN_ONLY: Direction.DOWN}.get(
        facts.directional_state)


def _state_condition(facts: DayStructureFacts, rule: str, allowed: set[DirectionalState]) -> Condition:
    return Condition("directional_state", rule, facts.directional_state.value, facts.directional_state in allowed)


def _normal(facts: DayStructureFacts) -> DayTypeCandidate:
    return _candidate(
        DayType.NORMAL_DAY, None,
        _state_condition(facts, "not BOTH_SIDES (IB contains the session, or a one-sided extension)",
                         {DirectionalState.NO_EXTENSION, DirectionalState.UP_ONLY, DirectionalState.DOWN_ONLY}),
        Condition("ib_share_wide", f"IB share >= {NORMAL_MIN_IB_SHARE}", _share(facts),
                  facts.ib_share_of_range >= NORMAL_MIN_IB_SHARE),
        Condition("ib_wide_vs_history", "IB wide versus recent sessions (separates NON_TREND_DAY)",
                  "requires historical context; not evaluated in V1", None),
    )


def _normal_variation(facts: DayStructureFacts) -> DayTypeCandidate:
    share = facts.ib_share_of_range
    return _candidate(
        DayType.NORMAL_VARIATION_DAY, _one_sided(facts),
        _state_condition(facts, "UP_ONLY or DOWN_ONLY", {DirectionalState.UP_ONLY, DirectionalState.DOWN_ONLY}),
        Condition("ib_share_band",
                  f"{NORMAL_VARIATION_MIN_IB_SHARE} <= IB share < {NORMAL_MIN_IB_SHARE} "
                  f"(range up to 2x IB)", _share(facts),
                  NORMAL_VARIATION_MIN_IB_SHARE <= share < NORMAL_MIN_IB_SHARE),
    )


def _trend(facts: DayStructureFacts) -> DayTypeCandidate:
    direction = _one_sided(facts)
    new_extremes = (facts.new_post_ib_high_periods if direction is Direction.UP
                    else facts.new_post_ib_low_periods if direction is Direction.DOWN else "")
    terminal = facts.terminal
    if terminal is None or direction is None:
        term_ok, term_obs = False, ("no terminal price" if terminal is None else
                                    f"terminal {terminal.price}; no single extension direction")
    else:
        term_ok = (terminal.price > facts.profile_midpoint if direction is Direction.UP
                   else terminal.price < facts.profile_midpoint)
        term_obs = f"terminal {terminal.price} vs midpoint {facts.profile_midpoint}"
    return _candidate(
        DayType.TREND_DAY, direction,
        _state_condition(facts, "UP_ONLY or DOWN_ONLY (no counter-extension)",
                         {DirectionalState.UP_ONLY, DirectionalState.DOWN_ONLY}),
        Condition("ib_share_narrow", f"IB share < {NORMAL_VARIATION_MIN_IB_SHARE} (range more than 2x IB)",
                  _share(facts), facts.ib_share_of_range < NORMAL_VARIATION_MIN_IB_SHARE),
        Condition("persistent_new_extremes",
                  f">= {TREND_MIN_NEW_EXTREME_PERIODS} post-IB periods set a new extreme in the extension direction",
                  "no single extension direction" if direction is None
                  else f"new extreme periods: {new_extremes or 'none'} ({len(new_extremes)})",
                  len(new_extremes) >= TREND_MIN_NEW_EXTREME_PERIODS),
        Condition("terminal_on_extension_side",
                  "study-window terminal price strictly beyond the profile midpoint on the extension side",
                  term_obs, term_ok),
    )


def _neutral(facts: DayStructureFacts) -> DayTypeCandidate:
    return _candidate(
        DayType.NEUTRAL_DAY, None,
        Condition("both_sides_extension", "extension above IB >= 1 tick AND extension below IB >= 1 tick",
                  f"above {facts.extension_above_ticks} ticks, below {facts.extension_below_ticks} ticks",
                  facts.directional_state is DirectionalState.BOTH_SIDES),
    )
