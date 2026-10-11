"""Drysdale VWAP Wave Laboratory V1 training candidates (0AB-B): DRYSDALE_SETUP_ANALYSIS_V1.

Educational structure recognition only. No trade, entry, stop, target or sizing is produced here.

Source hierarchy: (1) the Human's notes from Chris Drysdale's book *VWAP Wave System*; (2) the
*VWAP Wave Core Setup Guide*; (3) accepted Laboratory evidence; (4) explicit Laboratory V1 proxies
where the source stays discretionary. Every mechanical rule below that is ours is a

    LABORATORY V1 OPERATIONALIZATION   (never "DRYSDALE DEFINITION")

Source-supported conventions (the Human's book notes):
    Drysdale VWAP              anchored at the Globex session start, 17:00 America/Chicago
    DRYSDALE_VALUE_AREA_V1     Globex VWAP +/- 1 sigma (the dynamic VWAP value area, inclusive)
    +/- 2 sigma                outer / extreme context (strong trend, price discovery or exhaustion)
These are not the Laboratory 70% volume / TPO value area and not the playbook's 68% profile value.

VWAP_BANDS_GLOBEX_V1 (additive; VWAP_BANDS_V1 stays the cash-anchored policy, unchanged)
    VWAP_BANDS_V1 arithmetic (volume-weighted population sigma, exact integer comparisons, bands change
    only on trades) over the session-scoped as-of EFFECTIVE_TAPE from the SESSION_OPEN anchor (17:00 CT
    prior evening) to the market cutoff; window end 16:00 CT. The VWAP equals the snapshot's
    SESSION_OPEN (Globex) VWAP.

Evaluation scale (Laboratory choice aligned with the source's day-trading practice; the source does
not mandate it): COMPLETE BARS_5M_V1 bars of the Globex session (non-empty; consecutive = consecutive
non-empty bars). A bar's close is compared with the bands as of the bar's last trade (that trade
included). "Trades at / through" a moving level uses the exact side of each trade vs the level as of
that trade. A complete bar may still be revised by a later-received record (COMPLETE, not FINAL).

LABORATORY V1 OPERATIONALIZATIONS
    LAB_VWAP_SLOPE_V1             bar VWAP minus the previous completed bar's VWAP (Decimal);
                                  RISING > 0, FLAT == 0 exactly, FALLING < 0 (no tolerance)
    LAB_VOLUME_CONTEXT_V1         bar volume vs the previous bar and vs the mean / median of up to 12
                                  preceding completed bars; ratios only (no strong / weak label)
    LAB_BREAKOUT_TRIGGER_V1       UP: a complete bar closes strictly above +1 sigma while the previous
                                  complete bar did not (or it is the first bar); DOWN mirror. Only a
                                  trigger: DrysdaleBreakoutEvidence always accompanies it.
    LAB_ACCEPTANCE_TIME_V1        outside: two consecutive complete closes strictly beyond the same
                                  +/-1 sigma boundary; inside: two consecutive complete closes inside the
                                  inclusive -1..+1 sigma region. THE SOURCE DOES NOT SPECIFY TWO BARS:
                                  a Laboratory training proxy. Distance acceptance: no Laboratory rule.
    LAB_RETEST_V1                 outward: after the acceptance bar of the same outside episode, a bar
                                  trades at or through the broken boundary and closes outside (strictly);
                                  return-to-value: after the return bar, a bar of the same inside episode
                                  trades at or through the boundary and closes inside. No proximity rule.
    LAB_REJECTION_V1              a complete bar trades at or through a level and closes strictly back on
                                  the originating side
    LAB_DIRECTIONAL_CONFIRMATION_V1  the first subsequent complete bar (the next one) closes above its own
                                  open and strictly above the previous bar's high (UP); DOWN mirror
    LAB_RETURN_TO_VALUE_V1        the first complete close inside value after an outside episode
    LAB_VWAP_TEST_V1              a complete bar trades at or through the Globex VWAP (from the side of
                                  the trend context). No proximity rule.
    LAB_TREND_CONTEXT_V1          UP at a bar: LAB_VWAP_SLOPE_V1 RISING and the close strictly above the
                                  Globex VWAP; DOWN mirror
    DRYSDALE_SETUP_CANDIDATES_V1  the four family rules (see _price_discovery, _fade, _return, _bounce)

A candidate is the outcome of these proxies, not Drysdale's judgment and not a trade signal.
"""
from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum
from math import isqrt
from zoneinfo import ZoneInfo

from dicks_laboratory import market_study_state as mss
from dicks_laboratory.market_study_state import ComponentStatus
from dicks_laboratory.price_action import (
    ATR_POLICY,
    BAR_POLICY,
    BarDirection,
    BandZone,
    Direction,
    Side,
    _zone,
    atr_series,
)
from dicks_laboratory.replay import MarketStudySnapshot, Maturity, PreparedReplay, ReplayCutoff, snapshot_sha256
from dicks_laboratory.sessions import AnchorKind, resolve_anchor
from dicks_laboratory.volume_profile import price_grid_for_instrument

SCHEMA = "DRYSDALE_SETUP_ANALYSIS_V1"
HASH_FIELD = "drysdale_sha256"
SOURCE_MODEL_VERSION = "DRYSDALE_SOURCE_MODEL_V1"
GLOBEX_BAND_POLICY = "VWAP_BANDS_GLOBEX_V1"
VALUE_AREA_POLICY = "DRYSDALE_VALUE_AREA_V1"
SLOPE_POLICY = "LAB_VWAP_SLOPE_V1"
VOLUME_POLICY = "LAB_VOLUME_CONTEXT_V1"
BREAKOUT_POLICY = "LAB_BREAKOUT_TRIGGER_V1"
ACCEPTANCE_POLICY = "LAB_ACCEPTANCE_TIME_V1"
RETEST_POLICY = "LAB_RETEST_V1"
REJECTION_POLICY = "LAB_REJECTION_V1"
CONFIRMATION_POLICY = "LAB_DIRECTIONAL_CONFIRMATION_V1"
RETURN_POLICY = "LAB_RETURN_TO_VALUE_V1"
VWAP_TEST_POLICY = "LAB_VWAP_TEST_V1"
TREND_POLICY = "LAB_TREND_CONTEXT_V1"
CANDIDATES_POLICY = "DRYSDALE_SETUP_CANDIDATES_V1"
POLICIES = (GLOBEX_BAND_POLICY, VALUE_AREA_POLICY, BAR_POLICY, ATR_POLICY, SLOPE_POLICY, VOLUME_POLICY,
            BREAKOUT_POLICY, ACCEPTANCE_POLICY, RETEST_POLICY, REJECTION_POLICY, CONFIRMATION_POLICY,
            RETURN_POLICY, VWAP_TEST_POLICY, TREND_POLICY, CANDIDATES_POLICY)
LAB = "LABORATORY V1 OPERATIONALIZATION"
VOLUME_BASELINE_BARS = 12
RECENT_BARS = 6
DISTANCE_ACCEPTANCE = "SOURCE CONCEPT PRESENT; MECHANICAL THRESHOLD NOT SPECIFIED"
NOT_AVAILABLE_CONFIRMATIONS = ("CORRELATED_MARKET_NQ", "MARKET_INTERNALS", "ORDER_FLOW_AGGRESSION", "NEWS_CATALYST")
_BAR_US = 300_000_000
_Q = 10 ** 6  # sigma fixed-point digits for distances (as REFERENCE_PATH_V1)
_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
_US = timedelta(microseconds=1)
_POINTS = Decimal("0.000001")
_CT = ZoneInfo("America/Chicago")
_CASH_OPEN, _CASH_CLOSE = time(8, 30), time(15, 0)  # US_CASH_SESSION_V1 (time-of-day context only)


# --- vocabularies --------------------------------------------------------------------------------------

class Level(StrEnum):
    GLOBEX_VWAP = "GLOBEX_VWAP"
    UPPER_1SD = "UPPER_1SD"
    LOWER_1SD = "LOWER_1SD"
    UPPER_2SD = "UPPER_2SD"
    LOWER_2SD = "LOWER_2SD"


_LEVELS = ((Level.GLOBEX_VWAP, 0), (Level.UPPER_1SD, 1), (Level.LOWER_1SD, -1), (Level.UPPER_2SD, 2),
           (Level.LOWER_2SD, -2))
_LI = {lv: i for i, (lv, _) in enumerate(_LEVELS)}
_SIDE = {1: Side.ABOVE, 0: Side.AT, -1: Side.BELOW}


class ValuePosition(StrEnum):
    """Close vs DRYSDALE_VALUE_AREA_V1 (inside is inclusive of both boundaries)."""

    ABOVE_VALUE = "ABOVE_VALUE"
    INSIDE_VALUE = "INSIDE_VALUE"
    BELOW_VALUE = "BELOW_VALUE"


class Slope(StrEnum):
    RISING = "RISING"
    FLAT = "FLAT"  # exactly unchanged
    FALLING = "FALLING"


class ConditionStatus(StrEnum):
    SATISFIED = "SATISFIED"
    NOT_SATISFIED = "NOT_SATISFIED"  # evaluated and not met (an earlier attempt, or the window ended)
    PENDING = "PENDING"  # not met yet; the structure can still meet it
    NOT_AVAILABLE = "NOT_AVAILABLE"


class CandidateState(StrEnum):
    NOT_AVAILABLE = "NOT_AVAILABLE"
    DEVELOPING = "DEVELOPING"
    CANDIDATE = "CANDIDATE"  # every Laboratory V1 condition satisfied on AVAILABLE evidence
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # every condition satisfied, but the evidence is qualified


class SetupFamily(StrEnum):
    PRICE_DISCOVERY_CONTINUATION = "PRICE_DISCOVERY_CONTINUATION"
    FADE_VALUE_AREA_EXTREME = "FADE_VALUE_AREA_EXTREME"
    RETURN_TO_VALUE = "RETURN_TO_VALUE"
    VWAP_BOUNCE = "VWAP_BOUNCE"


class Stage(StrEnum):
    BREAKOUT_TRIGGERED = "BREAKOUT_TRIGGERED"
    ACCEPTED_OUTSIDE = "ACCEPTED_OUTSIDE"
    RETEST_OBSERVED = "RETEST_OBSERVED"
    BOUNDARY_TESTED = "BOUNDARY_TESTED"
    REJECTION_OBSERVED = "REJECTION_OBSERVED"
    RETURNED_TO_VALUE = "RETURNED_TO_VALUE"
    VWAP_TESTED = "VWAP_TESTED"
    WAITING_FOR_CONFIRMATION = "WAITING_FOR_CONFIRMATION"
    CONDITIONS_SATISFIED = "CONDITIONS_SATISFIED"


CANDIDATE_POLICY = {
    SetupFamily.PRICE_DISCOVERY_CONTINUATION: "PRICE_DISCOVERY_CONTINUATION_CANDIDATE_V1",
    SetupFamily.FADE_VALUE_AREA_EXTREME: "FADE_VALUE_AREA_EXTREME_CANDIDATE_V1",
    SetupFamily.RETURN_TO_VALUE: "RETURN_TO_VALUE_CANDIDATE_V1",
    SetupFamily.VWAP_BOUNCE: "VWAP_BOUNCE_CANDIDATE_V1",
}
_SHORT = {SetupFamily.PRICE_DISCOVERY_CONTINUATION: "PDC", SetupFamily.FADE_VALUE_AREA_EXTREME: "FADE",
          SetupFamily.RETURN_TO_VALUE: "RTV", SetupFamily.VWAP_BOUNCE: "BOUNCE"}


# --- source model (what the source says vs what the Laboratory operationalizes) -------------------------

class SourceStatus(StrEnum):
    SOURCE_SUPPORTED = "SOURCE_SUPPORTED"  # the Human's book notes state it; adopted as the V1 teaching convention
    SOURCE_DISCRETIONARY = "SOURCE_DISCRETIONARY"  # the source names the concept without a mechanical rule
    SOURCE_PRACTICE = "SOURCE_PRACTICE"  # what the source generally uses, not a mandate
    NOT_IN_LABORATORY = "NOT_IN_LABORATORY"  # the source names it; no deterministic Laboratory source exists


@dataclass(frozen=True)
class DrysdaleConcept:
    concept: str
    source_status: SourceStatus
    source_says: str  # paraphrase of the source / the Human's book notes (no third-party text is copied)
    laboratory: str  # the Laboratory policy or fact, with its label
    policy_id: str | None


SOURCE_MODEL = (
    DrysdaleConcept("VWAP anchor", SourceStatus.SOURCE_SUPPORTED, "intraday VWAP anchored at the futures Globex "
                    "session start (17:00 America/Chicago)", f"{GLOBEX_BAND_POLICY} anchor SESSION_OPEN; the cash "
                    "08:30 VWAP is not Drysdale's VWAP", GLOBEX_BAND_POLICY),
    DrysdaleConcept("VWAP value area", SourceStatus.SOURCE_SUPPORTED, "VWAP +/-1 sigma is the normal back-and-forth, "
                    "dynamic value area", f"{VALUE_AREA_POLICY}: Globex VWAP +/-1 sigma, inclusive (V1 teaching "
                    "convention)", VALUE_AREA_POLICY),
    DrysdaleConcept("outer / extreme region", SourceStatus.SOURCE_SUPPORTED, "+/-2 sigma: strong trend / price "
                    "discovery or exhaustion context", "+/-2 sigma reach, excursion and time: context facts only",
                    GLOBEX_BAND_POLICY),
    DrysdaleConcept("profile value area", SourceStatus.NOT_IN_LABORATORY, "not a Drysdale VWAP concept",
                    "Laboratory 70% volume / TPO value and the playbook's 68% profile value are separate concepts; "
                    "never converted", None),
    DrysdaleConcept("chart interval", SourceStatus.SOURCE_PRACTICE, "generally 5-minute charts for day trading, "
                    "higher timeframes for swing trading; no single mandated timeframe",
                    f"{LAB}: complete {BAR_POLICY} bars", BAR_POLICY),
    DrysdaleConcept("breakout", SourceStatus.SOURCE_DISCRETIONARY, "multi-factor: a clear prior range / value "
                    "boundary, movement beyond +/-1 sigma, often extension toward +/-2 sigma, volume expansion, VWAP "
                    "slope, limited nearby opposing reference, time of day, correlated markets / internals",
                    f"{LAB}: {BREAKOUT_POLICY} trigger + DrysdaleBreakoutEvidence (dimensions reported "
                    "independently)", BREAKOUT_POLICY),
    DrysdaleConcept("acceptance", SourceStatus.SOURCE_DISCRETIONARY, "shown by time or distance outside / inside "
                    "value; no number given", f"{LAB}: {ACCEPTANCE_POLICY} (two consecutive complete 5m closes; the "
                    f"source does not specify two bars). Distance acceptance: {DISTANCE_ACCEPTANCE}",
                    ACCEPTANCE_POLICY),
    DrysdaleConcept("backtest / retest", SourceStatus.SOURCE_DISCRETIONARY, "a pullback that tests the band again; "
                    "it may retest more than once; no mechanical definition", f"{LAB}: {RETEST_POLICY} (trade at or "
                    "through the same boundary, close back outside / inside; no proximity rule)", RETEST_POLICY),
    DrysdaleConcept("rejection", SourceStatus.SOURCE_DISCRETIONARY, "touch / approach the band, wick or excursion, "
                    "return; contrasted with acceleration through the band", f"{LAB}: {REJECTION_POLICY} (trade at "
                    "or through, close strictly back on the originating side)", REJECTION_POLICY),
    DrysdaleConcept("acceleration", SourceStatus.SOURCE_DISCRETIONARY, "movement that continues through the band "
                    "instead of returning", "facts only (cross, next bar beyond, volume change, distance added); no "
                    "label", None),
    DrysdaleConcept("first sign of strength / weakness", SourceStatus.SOURCE_DISCRETIONARY, "contextual: higher-"
                    "timeframe trend, absence of major divergence, pullback volume, ability to move away from VWAP, "
                    "failure / success of repeated bounce attempts", f"{LAB}: {CONFIRMATION_POLICY} (next bar closes "
                    "beyond its open and the previous bar's extreme)", CONFIRMATION_POLICY),
    DrysdaleConcept("return to value", SourceStatus.SOURCE_DISCRETIONARY, "price comes back inside the VWAP value "
                    "area after being outside; a backtest may or may not occur", f"{LAB}: {RETURN_POLICY} (one "
                    f"complete close inside), then {ACCEPTANCE_POLICY} inside", RETURN_POLICY),
    DrysdaleConcept("VWAP bounce", SourceStatus.SOURCE_DISCRETIONARY, "trend resumption after a pullback to VWAP in "
                    "an already trending market; trend definition, test tolerance and confirmation are discretionary",
                    f"{LAB}: {VWAP_TEST_POLICY} + {TREND_POLICY} + {CONFIRMATION_POLICY}", VWAP_TEST_POLICY),
    DrysdaleConcept("trend", SourceStatus.SOURCE_DISCRETIONARY, "an already trending market (no classifier given)",
                    f"{LAB}: {TREND_POLICY} (VWAP rising and close above it; mirror); not a trend classifier",
                    TREND_POLICY),
    DrysdaleConcept("volume expansion", SourceStatus.SOURCE_DISCRETIONARY, "volume participation matters; no "
                    "threshold", f"{VOLUME_POLICY}: volumes and ratios only, no strong / weak label", VOLUME_POLICY),
    DrysdaleConcept("VWAP slope", SourceStatus.SOURCE_DISCRETIONARY, "slope in the breakout / trend direction "
                    "matters", f"{SLOPE_POLICY}: Decimal delta, RISING / FLAT (exactly unchanged) / FALLING",
                    SLOPE_POLICY),
    DrysdaleConcept("volatility", SourceStatus.SOURCE_DISCRETIONARY, "higher-volatility days can be preferable (no "
                    "threshold)", f"{ATR_POLICY}: context only; no high / low volatility label", ATR_POLICY),
    DrysdaleConcept("correlated markets, internals, order flow, news", SourceStatus.NOT_IN_LABORATORY,
                    "confirmation where available", "NOT_AVAILABLE (no deterministic Laboratory source)", None),
)

SOURCE_CRITERIA = {
    SetupFamily.PRICE_DISCOVERY_CONTINUATION: (
        "break from prior value / range out of the VWAP value area",
        "acceptance outside VWAP value (time or distance)",
        "backtest pullback of the VWAP deviation band (it may retest again)",
        "first sign of strength (weakness) after the backtest",
        "supporting context: volume expansion, extension toward +/-2 sigma, VWAP slope, nearby opposing references, "
        "time of day, correlated markets"),
    SetupFamily.FADE_VALUE_AREA_EXTREME: (
        "price accepted inside the VWAP value area",
        "a test of the value-area extreme (the +/-1 sigma band)",
        "first sign of weakness / rejection on the test of the band area",
        "rotation back toward the interior; acceleration through the band is not a rejection"),
    SetupFamily.RETURN_TO_VALUE: (
        "price was accepted outside value",
        "price returns inside the VWAP value area",
        "acceptance back inside value (time or distance)",
        "a backtest of the band may or may not occur"),
    SetupFamily.VWAP_BOUNCE: (
        "an already trending market",
        "a pullback to the VWAP",
        "trend resumption: first sign of strength (weakness) away from the VWAP",
        "higher-volatility days can be preferable (no threshold)"),
}


# --- results -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class LevelTouch:
    """One bar vs one moving level (trade level: each trade vs the level as of that trade)."""

    level: Level
    level_at_close: Decimal
    close_side: Side
    traded_above: bool  # some trade strictly above
    traded_at: bool
    traded_below: bool
    max_above_points: Decimal  # max(price - level) over the bar's trades; negative: never above
    max_below_points: Decimal  # max(level - price)
    seconds_above: timedelta  # time elapsed in this bar with the last trade strictly above
    seconds_below: timedelta
    volume_above: Decimal
    volume_below: Decimal
    crosses: int  # strict side changes at trades in this bar (continuing from the previous trade)


@dataclass(frozen=True)
class GlobexBar:
    """A COMPLETE BARS_5M_V1 bar of the Globex session with its VWAP_BANDS_GLOBEX_V1 facts."""

    index: int
    start_utc: datetime
    end_utc: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    direction: BarDirection
    trade_count: int
    volume: Decimal
    vwap: Decimal  # as of the bar's last trade
    sigma: Decimal
    value_position: ValuePosition
    close_zone_1sd: BandZone
    close_zone_2sd: BandZone
    vwap_delta: Decimal | None  # LAB_VWAP_SLOPE_V1
    vwap_slope: Slope | None
    atr: Decimal | None  # ATR_5M_V1 through this bar
    levels: tuple[LevelTouch, ...]  # GLOBEX_VWAP, UPPER_1SD, LOWER_1SD, UPPER_2SD, LOWER_2SD


@dataclass(frozen=True)
class GlobexBands:
    policy_id: str
    anchor: str
    anchor_utc: datetime
    window_end_utc: datetime
    maturity: Maturity
    included_trade_count: int
    included_volume: Decimal | None
    vwap: Decimal | None  # equals the snapshot's SESSION_OPEN (Globex) VWAP
    sigma: Decimal | None
    zero_width: bool | None
    upper_1sd: Decimal | None
    lower_1sd: Decimal | None
    upper_2sd: Decimal | None
    lower_2sd: Decimal | None
    value_area_policy: str
    last_price: Decimal | None
    last_price_value_position: ValuePosition | None
    last_price_zone_2sd: BandZone | None


@dataclass(frozen=True)
class VolumeContext:
    policy_id: str
    bar_end_utc: datetime
    bar_volume: Decimal
    prior_bar_volume: Decimal | None
    baseline_bars: int  # preceding completed bars used (up to 12)
    baseline_mean: Decimal | None
    baseline_median: Decimal | None
    ratio_to_prior: Decimal | None
    ratio_to_mean: Decimal | None
    ratio_to_median: Decimal | None


@dataclass(frozen=True)
class ReferenceContext:
    reference: str
    source: str  # pointer into the accompanying snapshot
    level: Decimal | None
    availability: str
    close_side: Side | None
    traded_through_in_bar: bool | None  # bar low <= level <= bar high
    close_distance_points: Decimal | None  # close - level


@dataclass(frozen=True)
class AcceptanceEvidence:
    policy_id: str
    region: str  # OUTSIDE_ABOVE / OUTSIDE_BELOW / INSIDE
    reference: str  # UPPER_1SD / LOWER_1SD / VALUE_AREA (+/-1 sigma)
    first_bar_end_utc: datetime
    last_bar_end_utc: datetime  # the latest complete bar of the episode so far
    completed_closes: int  # consecutive complete closes in the region (the episode so far)
    lab_acceptance_time_v1: bool
    accepted_at_utc: datetime | None
    episode_ended_at_utc: datetime | None  # end of the first bar closing outside the region (None: ongoing)
    seconds_beyond: timedelta | None  # outside episodes: time strictly beyond the boundary within the episode bars
    volume_beyond: Decimal | None
    max_distance_beyond_points: Decimal | None
    last_close_distance_points: Decimal | None  # last close beyond the boundary (outside) or None
    last_close_distance_sigma: Decimal | None
    last_close_distance_atr: Decimal | None
    boundary_crosses: int  # trade-level crosses of the boundary (both boundaries for INSIDE) in the episode bars
    vwap_delta_at_last: Decimal | None
    vwap_slope_at_last: Slope | None
    distance_acceptance: str = DISTANCE_ACCEPTANCE


@dataclass(frozen=True)
class DrysdaleBreakoutEvidence:
    """Breakout dimensions, reported independently. None is required by V1 beyond the trigger."""

    direction: Direction
    boundary: Level
    trigger_policy: str
    trigger_bar_index: int
    trigger_bar_end_utc: datetime
    distance_beyond_points: Decimal  # trigger close beyond the boundary (as of its close)
    distance_beyond_ticks: Decimal
    distance_beyond_sigma: Decimal | None
    distance_beyond_atr: Decimal | None
    max_excursion_beyond_points: Decimal  # over the outside episode so far (trade level)
    seconds_beyond: timedelta  # over the outside episode so far
    completed_closes_beyond: int
    reached_2sd: bool  # some trade at or beyond the same-side 2 sigma band during the episode so far
    first_2sd_reach_bar_end_utc: datetime | None
    volume: VolumeContext
    vwap_delta: Decimal | None
    vwap_slope: Slope | None
    slope_in_breakout_direction: bool | None
    prior_inside_closes: int  # consecutive complete closes inside value immediately before the trigger
    prior_inside_lab_accepted: bool
    session_high_before: Decimal | None  # Globex session so far, before the trigger bar
    session_low_before: Decimal | None
    new_session_extreme: bool | None
    references: tuple[ReferenceContext, ...]
    nearest_opposing_reference: str | None  # nearest available reference beyond the close in the direction
    nearest_opposing_distance_points: Decimal | None
    bar_end_ct: str
    in_us_cash_session: bool
    returned_inside: bool
    returned_at_utc: datetime | None
    time_to_return: timedelta | None
    not_available: tuple[str, ...]


@dataclass(frozen=True)
class TestEvent:
    """A bar that traded at / through a level, with its proxy result and the next bar's facts."""

    kind: str  # RETEST / BOUNDARY_TEST / RETURN_RETEST / VWAP_TEST
    bar_index: int
    bar_end_utc: datetime
    level: Level
    traded_through: bool  # some trade strictly beyond the level from the originating side
    excursion_points: Decimal  # wick / distance through (negative: touched only... never negative when touched)
    seconds_through: timedelta
    bar_volume: Decimal
    volume_through: Decimal
    close_side: Side
    proxy_policy: str
    proxy_satisfied: bool
    trend_context: ConditionStatus | None  # VWAP_TEST only: LAB_TREND_CONTEXT_V1 at the previous bar
    confirmation: ConditionStatus  # LAB_DIRECTIONAL_CONFIRMATION_V1 at the next bar
    next_bar_end_utc: datetime | None
    next_close_beyond: bool | None  # acceleration facts (the next complete bar)
    next_volume_change: Decimal | None
    next_excursion_added_points: Decimal | None
    next_distance_back_points: Decimal | None  # next bar's max distance on the originating side


@dataclass(frozen=True)
class DrysdaleSetupCondition:
    order: int
    policy_id: str
    source_criterion: str  # SOURCE SAYS (paraphrase)
    laboratory_rule: str  # LABORATORY V1 TRAINING PROXY
    status: ConditionStatus
    bar_index: int | None
    satisfied_at_utc: datetime | None  # end of the complete bar that satisfied it
    evidence_pointer: str | None  # into this document


@dataclass(frozen=True)
class DrysdaleSetupCandidate:
    candidate_id: str
    family: SetupFamily
    candidate_policy: str
    direction: Direction
    state: CandidateState
    quality: str
    stage: Stage
    can_still_complete: bool  # some required condition is PENDING
    first_event_utc: datetime  # end of the bar that created the instance
    completed_at_utc: datetime | None  # end of the bar that satisfied the last condition
    source_criteria: tuple[str, ...]
    conditions: tuple[DrysdaleSetupCondition, ...]
    events: tuple[TestEvent, ...]
    breakout: DrysdaleBreakoutEvidence | None
    acceptance: tuple[AcceptanceEvidence, ...]
    supporting: tuple[tuple[str, object], ...]  # family-specific context facts (name, value)
    policy_versions: tuple[str, ...]


@dataclass(frozen=True)
class DrysdaleContextEvidence:
    """Facts at the last complete bar. Supporting evidence; no classification."""

    last_bar_end_utc: datetime
    value_position: ValuePosition
    vwap_delta: Decimal | None
    vwap_slope: Slope | None
    trend_context: Direction | None  # LAB_TREND_CONTEXT_V1 at the last complete bar (None: neither)
    higher_high: bool | None
    higher_low: bool | None
    lower_high: bool | None
    lower_low: bool | None
    consecutive_higher_highs_and_lows: int
    consecutive_lower_highs_and_lows: int
    recent_up_closes: int  # of the last 6 complete bars
    recent_down_closes: int
    current_episode: AcceptanceEvidence
    session_seconds_above_1sd: timedelta
    session_seconds_below_1sd: timedelta
    session_bars_reaching_2sd: int
    atr: Decimal | None
    atr_12_bars_earlier: Decimal | None
    atr_change: Decimal | None
    volume: VolumeContext
    not_available: tuple[str, ...]


@dataclass(frozen=True)
class DrysdaleSetupAnalysis:
    schema: str
    dataset_id: object
    trading_date: object
    cutoff: ReplayCutoff
    clock_utc: datetime
    snapshot_sha256: str  # the MARKET_STUDY_SNAPSHOT_V1 these facts accompany (static references, quality)
    source_model: str
    policies: tuple[str, ...]
    status: str  # the Globex VWAP component status (quality propagation)
    reasons: tuple[str, ...]
    state: CandidateState  # NOT_AVAILABLE, DEVELOPING (no candidate yet), CANDIDATE or QUALITY_QUALIFIED
    bands: GlobexBands
    developing_bar_start_utc: datetime | None
    bars: tuple[GlobexBar, ...]  # complete bars only
    context: DrysdaleContextEvidence | None
    candidates: tuple[DrysdaleSetupCandidate, ...]


# --- arithmetic ----------------------------------------------------------------------------------------

def _scale_of(values) -> int:
    e = min((v.as_tuple().exponent for v in values), default=0)
    return 10 ** max(0, -e)


def _dec(num: int, den: int) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = 28, ROUND_HALF_EVEN
        return Decimal(num) / Decimal(den)


def _pts(num: int, den: int) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = 40, ROUND_HALF_EVEN
        return (Decimal(num) / Decimal(den)).quantize(_POINTS)


def _div(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    if a is None or b is None or b == 0:
        return None
    with localcontext() as c:
        c.prec, c.rounding = 28, ROUND_HALF_EVEN
        return a / b


def _sub(a: Decimal, b: Decimal) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = 28, ROUND_HALF_EVEN
        return a - b


def _cmp(a: int, b: int) -> int:
    return (a > b) - (a < b)


def _sides(D: int, var: int, DD: int) -> tuple[int, int, int, int, int]:
    """Exact side (+1 ABOVE, 0 AT, -1 BELOW) of a price vs VWAP, +1, -1, +2, -2 sigma."""
    if D > 0:
        return 1, _cmp(DD, var), 1, _cmp(DD, 4 * var), 1
    if D < 0:
        return -1, -1, -_cmp(DD, var), -1, -_cmp(DD, 4 * var)
    if var == 0:
        return 0, 0, 0, 0, 0
    return 0, -1, 1, -1, 1


# --- the single pass (resumable) -----------------------------------------------------------------------

class _Pass:
    """Incremental VWAP_BANDS_GLOBEX_V1 / BARS_5M_V1 accumulation over trades in event-time order."""

    def __init__(self, anchor_us: int, ps: int, vs: int) -> None:
        self.anchor_us, self.ps, self.vs = anchor_us, ps, vs
        self.S0 = self.S1 = self.S2 = 0
        self.n = 0
        self.bars: dict[int, dict] = {}
        self.order: list[int] = []
        self.last_us: int | None = None
        self.last_P: int | None = None
        self.prev = (0, 0, 0, 0, 0)
        self.strict: list[int | None] = [None] * 5
        self.through_us: int | None = None  # market cutoff the pass has consumed up to (exclusive)

    def feed(self, prices: list[int], sizes: list[int], times: list[int]) -> None:
        bars, Q = self.bars, _Q
        S0, S1, S2 = self.S0, self.S1, self.S2
        cur_start = cur_end = -1
        bar = None
        for P, V, us in zip(prices, sizes, times):
            if not cur_start <= us < cur_end:
                cur_start = us - us % _BAR_US
                cur_end = cur_start + _BAR_US
                bar = bars.get(cur_start)
                if bar is None:
                    bar = bars[cur_start] = {
                        "o": P, "h": P, "l": P, "c": P, "n": 0, "v": 0, "st": None,
                        "ab": [False] * 5, "at": [False] * 5, "be": [False] * 5,
                        "mx": [None] * 5, "mn": [None] * 5, "sa": [0] * 5, "sb": [0] * 5,
                        "va": [0] * 5, "vb": [0] * 5, "cr": [0] * 5}
                    self.order.append(cur_start)
            if self.last_us is not None:  # the state since the previous trade, split across bars (this one exists)
                self._spend(self.last_us, us, self.prev, bars)
            if P > bar["h"]:
                bar["h"] = P
            if P < bar["l"]:
                bar["l"] = P
            bar["c"] = P
            bar["n"] += 1
            bar["v"] += V
            S0 += V
            S1 += V * P
            S2 += V * P * P
            D = P * S0 - S1
            var = S2 * S0 - S1 * S1
            sides = _sides(D, var, D * D)
            sig = isqrt(var * Q * Q)
            DQ = D * Q
            ab, at, be, mx, mn, va, vb, cr, strict = (bar["ab"], bar["at"], bar["be"], bar["mx"], bar["mn"], bar["va"],
                                                       bar["vb"], bar["cr"], self.strict)
            for i, k in ((0, 0), (1, 1), (2, -1), (3, 2), (4, -2)):
                s = sides[i]
                d = (DQ - k * sig) // S0
                if mx[i] is None or d > mx[i]:
                    mx[i] = d
                if mn[i] is None or d < mn[i]:
                    mn[i] = d
                if s > 0:
                    ab[i] = True
                    va[i] += V
                elif s < 0:
                    be[i] = True
                    vb[i] += V
                else:
                    at[i] = True
                if s:
                    if strict[i] is not None and s != strict[i]:
                        cr[i] += 1
                    strict[i] = s
            bar["st"] = (S0, S1, S2, P)
            self.prev = sides
            self.last_us = us
            self.last_P = P
            self.n += 1
        self.S0, self.S1, self.S2 = S0, S1, S2

    @staticmethod
    def _spend(t0: int, t1: int, sides, bars) -> None:
        while t0 < t1:
            b = t0 - t0 % _BAR_US
            end = min(b + _BAR_US, t1)
            bar = bars.get(b)
            if bar is not None:
                dt = end - t0
                for i in range(5):
                    if sides[i] > 0:
                        bar["sa"][i] += dt
                    elif sides[i] < 0:
                        bar["sb"][i] += dt
            t0 = end


def _us(ts: datetime) -> int:
    return (ts - _EPOCH) // _US


def _utc(us: int) -> datetime:
    return _EPOCH + timedelta(microseconds=us)


@dataclass
class _Checkpoint:
    cutoff: ReplayCutoff
    acc: _Pass


def _prices(trades, ps, vs):
    return ([int(t.price * ps) for t in trades], [int(t.size * vs) for t in trades],
            [_us(t.event_timestamp) for t in trades])


def _sorted(trades):
    return sorted(trades, key=lambda t: (t.event_timestamp, t.originating_source_index))


def run_pass(trades, anchor_utc: datetime, cutoff: ReplayCutoff, resume: _Checkpoint | None = None) -> _Pass:
    """The accumulated pass at `cutoff` over the as-of scoped tape `trades`.

    With `resume` (a checkpoint whose trades with market time < its market cutoff are known to be identical
    in `trades`), only trades at or after that cutoff are fed to a copy of the checkpoint.
    """
    if resume is not None:
        start = resume.cutoff.market_time_cutoff_utc
        rest = _sorted(t for t in trades if t.event_timestamp >= start)
        acc = resume.acc
        if _scale_of(t.price for t in rest) <= acc.ps and _scale_of(t.size for t in rest) <= acc.vs:
            acc = copy.deepcopy(acc)
            acc.feed(*_prices(rest, acc.ps, acc.vs))
            acc.through_us = _us(cutoff.market_time_cutoff_utc)
            return acc
    ordered = _sorted(trades)
    acc = _Pass(_us(anchor_utc), _scale_of(t.price for t in ordered), _scale_of(t.size for t in ordered))
    acc.feed(*_prices(ordered, acc.ps, acc.vs))
    acc.through_us = _us(cutoff.market_time_cutoff_utc)
    return acc


# --- bars from the pass --------------------------------------------------------------------------------

def _bars(acc: _Pass, clock: datetime, window_end: datetime) -> tuple[tuple[GlobexBar, ...], datetime | None]:
    clock_us = _us(clock)
    through = min(clock_us, _us(window_end))
    bars = acc.bars
    extra: dict[int, dict] = {}
    if acc.last_us is not None and through > acc.last_us:  # the open interval up to the clock (not stored)
        view = {b: {"sa": [0] * 5, "sb": [0] * 5} for b in bars}
        _Pass._spend(acc.last_us, through, acc.prev, view)
        extra = view
    ps, vs = acc.ps, acc.vs
    complete = [b for b in acc.order if b + _BAR_US <= clock_us]
    developing = next((b for b in acc.order if b + _BAR_US > clock_us), None)
    atrs = atr_series([(bars[b]["h"], bars[b]["l"], bars[b]["c"]) for b in complete], ps)
    out: list[GlobexBar] = []
    prev_vwap = None
    for idx, b in enumerate(complete):
        x = bars[b]
        S0, S1, S2, P = x["st"]
        D, var = P * S0 - S1, S2 * S0 - S1 * S1
        vwap = _dec(S1, S0 * ps)
        with localcontext() as c:
            c.prec, c.rounding = 28, ROUND_HALF_EVEN
            sigma = (Decimal(var) / Decimal(S0 * S0 * ps * ps)).sqrt()
        sides = _sides(D, var, D * D)
        z1, z2 = _zone(D, var, 1), _zone(D, var, 2)
        pos = (ValuePosition.ABOVE_VALUE if sides[1] > 0 else ValuePosition.BELOW_VALUE if sides[2] < 0
               else ValuePosition.INSIDE_VALUE)
        delta = None if prev_vwap is None else _sub(vwap, prev_vwap)
        slope = None if delta is None else Slope.RISING if delta > 0 else Slope.FALLING if delta < 0 else Slope.FLAT
        prev_vwap = vwap
        levels = []
        for i, (lv, k) in enumerate(_LEVELS):
            with localcontext() as c:
                c.prec, c.rounding = 28, ROUND_HALF_EVEN
                level = vwap + k * sigma
            e = extra.get(b)
            sa = x["sa"][i] + (e["sa"][i] if e else 0)
            sb = x["sb"][i] + (e["sb"][i] if e else 0)
            levels.append(LevelTouch(lv, level, _SIDE[sides[i]], x["ab"][i], x["at"][i], x["be"][i],
                                     _pts(x["mx"][i], _Q * ps), _pts(-x["mn"][i], _Q * ps),
                                     timedelta(microseconds=sa), timedelta(microseconds=sb),
                                     _dec(x["va"][i], vs), _dec(x["vb"][i], vs), x["cr"][i]))
        o, h, lo, cl = x["o"], x["h"], x["l"], x["c"]
        out.append(GlobexBar(
            idx, _utc(b), _utc(b + _BAR_US), _dec(o, ps), _dec(h, ps), _dec(lo, ps), _dec(cl, ps),
            BarDirection.UP if cl > o else BarDirection.DOWN if cl < o else BarDirection.FLAT, x["n"],
            _dec(x["v"], vs), vwap, sigma, pos, z1, z2, delta, slope, atrs[idx], tuple(levels)))
    return tuple(out), (_utc(developing) if developing is not None else None)


# --- policy helpers ------------------------------------------------------------------------------------

def _lv(bar: GlobexBar, level: Level) -> LevelTouch:
    return bar.levels[_LI[level]]


def _outside(direction: Direction) -> ValuePosition:
    return ValuePosition.ABOVE_VALUE if direction is Direction.UP else ValuePosition.BELOW_VALUE


def _boundary(direction: Direction) -> Level:
    return Level.UPPER_1SD if direction is Direction.UP else Level.LOWER_1SD


def _outer(direction: Direction) -> Level:
    return Level.UPPER_2SD if direction is Direction.UP else Level.LOWER_2SD


def _opposite(direction: Direction) -> Direction:
    return Direction.DOWN if direction is Direction.UP else Direction.UP


def _runs(bars, pred) -> list[tuple[int, int]]:
    out, s = [], None
    for i, b in enumerate(bars):
        if pred(b):
            s = i if s is None else s
        elif s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(bars) - 1))
    return out


def _confirmation(bars, j: int, direction: Direction) -> ConditionStatus:
    """LAB_DIRECTIONAL_CONFIRMATION_V1 at the bar after j."""
    if j + 1 >= len(bars):
        return ConditionStatus.PENDING
    b, p = bars[j + 1], bars[j]
    ok = (b.close > b.open and b.close > p.high) if direction is Direction.UP else (b.close < b.open and b.close < p.low)
    return ConditionStatus.SATISFIED if ok else ConditionStatus.NOT_SATISFIED


def _touched_from(t: LevelTouch, from_side: Side) -> bool:
    """Traded at or through the level, coming from `from_side`."""
    return t.traded_at or (t.traded_below if from_side is Side.ABOVE else t.traded_above)


def _event(bars, j: int, kind: str, level: Level, from_side: Side, proxy_policy: str, proxy_ok: bool,
           direction: Direction, trend: ConditionStatus | None = None) -> TestEvent:
    b, t = bars[j], _lv(bars[j], level)
    through = t.traded_below if from_side is Side.ABOVE else t.traded_above
    exc = t.max_below_points if from_side is Side.ABOVE else t.max_above_points
    secs = t.seconds_below if from_side is Side.ABOVE else t.seconds_above
    vol = t.volume_below if from_side is Side.ABOVE else t.volume_above
    nxt = bars[j + 1] if j + 1 < len(bars) else None
    nt = _lv(nxt, level) if nxt else None
    far = Side.BELOW if from_side is Side.ABOVE else Side.ABOVE
    return TestEvent(
        kind, j, b.end_utc, level, through, exc, secs, b.volume, vol, t.close_side, proxy_policy, proxy_ok, trend,
        _confirmation(bars, j, direction), nxt.end_utc if nxt else None,
        (nt.close_side is far) if nt else None, _sub(nxt.volume, b.volume) if nxt else None,
        _sub(nt.max_below_points if far is Side.BELOW else nt.max_above_points, exc) if nt else None,
        (nt.max_above_points if from_side is Side.ABOVE else nt.max_below_points) if nt else None)


def _volume(bars, j: int) -> VolumeContext:
    b = bars[j]
    prior = bars[j - 1].volume if j > 0 else None
    window = [x.volume for x in bars[max(0, j - VOLUME_BASELINE_BARS):j]]
    mean = median = None
    if window:
        with localcontext() as c:
            c.prec, c.rounding = 28, ROUND_HALF_EVEN
            mean = sum(window, Decimal(0)) / len(window)
            s = sorted(window)
            m = len(s) // 2
            median = s[m] if len(s) % 2 else (s[m - 1] + s[m]) / 2
    return VolumeContext(VOLUME_POLICY, b.end_utc, b.volume, prior, len(window), mean, median, _div(b.volume, prior),
                         _div(b.volume, mean), _div(b.volume, median))


def _acceptance(bars, s: int, e: int, region: ValuePosition, n: int) -> AcceptanceEvidence:
    """LAB_ACCEPTANCE_TIME_V1 evidence for the episode bars[s..e] (closes in `region`)."""
    last = bars[e]
    ended = bars[e + 1].end_utc if e + 1 < n else None
    accepted = e >= s + 1
    if region is ValuePosition.INSIDE_VALUE:
        crosses = sum(_lv(b, Level.UPPER_1SD).crosses + _lv(b, Level.LOWER_1SD).crosses for b in bars[s:e + 1])
        return AcceptanceEvidence(ACCEPTANCE_POLICY, "INSIDE", "VALUE_AREA", bars[s].end_utc, last.end_utc, e - s + 1,
                                  accepted, bars[s + 1].end_utc if accepted else None, ended, None, None, None, None,
                                  None, None, crosses, last.vwap_delta, last.vwap_slope)
    up = region is ValuePosition.ABOVE_VALUE
    lv = Level.UPPER_1SD if up else Level.LOWER_1SD
    ts = [_lv(b, lv) for b in bars[s:e + 1]]
    secs = sum((t.seconds_above if up else t.seconds_below for t in ts), timedelta(0))
    vol = sum((t.volume_above if up else t.volume_below for t in ts), Decimal(0))
    maxd = max(t.max_above_points if up else t.max_below_points for t in ts)
    lt = ts[-1]
    dist = _sub(last.close, lt.level_at_close) if up else _sub(lt.level_at_close, last.close)
    return AcceptanceEvidence(ACCEPTANCE_POLICY, "OUTSIDE_ABOVE" if up else "OUTSIDE_BELOW", lv.value,
                              bars[s].end_utc, last.end_utc, e - s + 1, accepted,
                              bars[s + 1].end_utc if accepted else None, ended, secs, vol, maxd, dist,
                              _div(dist, last.sigma), _div(dist, last.atr), sum(t.crosses for t in ts),
                              last.vwap_delta, last.vwap_slope)


_STATIC = (("PRIOR_HIGH", "/prior_day/context/profile_high"), ("PRIOR_LOW", "/prior_day/context/profile_low"),
           ("OVERNIGHT_HIGH", "/overnight/session/high"), ("OVERNIGHT_LOW", "/overnight/session/low"),
           ("IB_HIGH", "/tpo/profile/initial_balance/high"), ("IB_LOW", "/tpo/profile/initial_balance/low"))


def _statics(snapshot: MarketStudySnapshot) -> list[tuple[str, str, Decimal | None, datetime | None]]:
    """(name, pointer, level, known-from market time) of the static references in the snapshot."""
    doc = mss.encode(snapshot)
    pc = doc["prior_day"]["context"] or {}
    on = doc["overnight"]["session"] or {}
    ib_done = snapshot.tpo.initial_balance_maturity is Maturity.WINDOW_COMPLETE
    ib = (doc["tpo"]["profile"] or {}).get("initial_balance") or {} if ib_done else {}
    on_end = next((m.matures_at_utc for m in snapshot.maturity if m.component == "overnight"), None)
    ib_end = next((m.matures_at_utc for m in snapshot.maturity if m.component == "initial_balance"), None)
    vals = {"PRIOR_HIGH": (pc.get("profile_high"), None), "PRIOR_LOW": (pc.get("profile_low"), None),
            "OVERNIGHT_HIGH": (on.get("high"), on_end), "OVERNIGHT_LOW": (on.get("low"), on_end),
            "IB_HIGH": (ib.get("high"), ib_end), "IB_LOW": (ib.get("low"), ib_end)}
    return [(n, p, None if vals[n][0] is None else Decimal(vals[n][0]), vals[n][1]) for n, p in _STATIC]


def _breakout(bars, s: int, e: int, direction: Direction, statics, tick: Decimal) -> DrysdaleBreakoutEvidence:
    n = len(bars)
    b = bars[s]
    bl, ol = _boundary(direction), _outer(direction)
    up = direction is Direction.UP
    t = _lv(b, bl)
    dist = _sub(b.close, t.level_at_close) if up else _sub(t.level_at_close, b.close)
    ep = bars[s:e + 1]
    ts = [_lv(x, bl) for x in ep]
    reach = next((x for x in ep if _lv(x, ol).traded_at or (_lv(x, ol).traded_above if up else
                                                           _lv(x, ol).traded_below)), None)
    k = s - 1
    while k >= 0 and bars[k].value_position is ValuePosition.INSIDE_VALUE:
        k -= 1
    prior_inside = s - 1 - k
    hi = max((x.high for x in bars[:s]), default=None)
    lo = min((x.low for x in bars[:s]), default=None)
    refs, nearest = [], None
    for name, src, level, known_from in statics:
        avail = level is not None and (known_from is None or b.end_utc >= known_from)
        if not avail:
            refs.append(ReferenceContext(name, src, None, "NOT_AVAILABLE" if level is None else "NOT_YET_AVAILABLE",
                                         None, None, None))
            continue
        side = Side.ABOVE if b.close > level else Side.BELOW if b.close < level else Side.AT
        d = _sub(b.close, level)
        refs.append(ReferenceContext(name, src, level, "AVAILABLE", side, b.low <= level <= b.high, d))
        ahead = level > b.close if up else level < b.close
        if ahead and (nearest is None or abs(d) < nearest[1]):
            nearest = (name, abs(d))
    local = b.end_utc.astimezone(_CT)
    ended = bars[e + 1].end_utc if e + 1 < n else None
    return DrysdaleBreakoutEvidence(
        direction, bl, BREAKOUT_POLICY, s, b.end_utc, dist, _div(dist, tick), _div(dist, b.sigma), _div(dist, b.atr),
        max(x.max_above_points if up else x.max_below_points for x in ts),
        sum((x.seconds_above if up else x.seconds_below for x in ts), timedelta(0)), e - s + 1, reach is not None,
        reach.end_utc if reach else None, _volume(bars, s), b.vwap_delta, b.vwap_slope,
        None if b.vwap_slope is None else b.vwap_slope is (Slope.RISING if up else Slope.FALLING),
        prior_inside, prior_inside >= 2, hi, lo, None if hi is None else (b.high > hi if up else b.low < lo),
        tuple(refs), nearest[0] if nearest else None, nearest[1] if nearest else None, local.strftime("%H:%M"),
        _CASH_OPEN <= bars[s].start_utc.astimezone(_CT).time() < _CASH_CLOSE, ended is not None, ended,
        (ended - b.end_utc) if ended else None, NOT_AVAILABLE_CONFIRMATIONS)


_P, _S, _N = ConditionStatus.PENDING, ConditionStatus.SATISFIED, ConditionStatus.NOT_SATISFIED


def _cond(order, policy, source, rule, status, bars, j=None) -> DrysdaleSetupCondition:
    ok = status is _S and j is not None
    return DrysdaleSetupCondition(order, policy, source, rule, status, j if ok else None,
                                  bars[j].end_utc if ok else None, f"/bars/{j}" if ok else None)


def _decisive(statuses: list[tuple[ConditionStatus, ...]]) -> int:
    """Index of the first attempt whose conditions are all satisfied, else of the latest attempt among those
    that progressed furthest (most leading SATISFIED conditions)."""
    def progress(st):
        k = 0
        while k < len(st) and st[k] is _S:
            k += 1
        return k

    for i, st in enumerate(statuses):
        if progress(st) == len(st):
            return i
    best = max(progress(st) for st in statuses)
    return max(i for i, st in enumerate(statuses) if progress(st) == best)


def _after(status: ConditionStatus, prerequisite_met: bool, open_: bool) -> ConditionStatus:
    """A condition evaluated only after its prerequisite: otherwise PENDING while the structure is open."""
    if prerequisite_met:
        return status
    return _P if open_ else _N


def _finish(family, direction, first_bar, conditions, events, quality, open_, stage, bars, breakout=None,
            acceptance=(), supporting=()) -> DrysdaleSetupCandidate:
    done = all(c.status is _S for c in conditions)
    state = (CandidateState.DEVELOPING if not done else CandidateState.CANDIDATE if quality == "AVAILABLE"
             else CandidateState.QUALITY_QUALIFIED)
    first = bars[first_bar]
    return DrysdaleSetupCandidate(
        f"{_SHORT[family]}-{direction.value}-{first.end_utc:%Y%m%dT%H%MZ}", family, CANDIDATE_POLICY[family],
        direction, state, quality, Stage.CONDITIONS_SATISFIED if done else stage, (not done) and open_,
        first.end_utc, max(c.satisfied_at_utc for c in conditions) if done else None, SOURCE_CRITERIA[family],
        tuple(conditions), tuple(events), breakout, tuple(acceptance), tuple(supporting),
        (CANDIDATES_POLICY, CANDIDATE_POLICY[family]))


def _word(direction: Direction, up: str, down: str) -> str:
    return up if direction is Direction.UP else down


def _closest(bars, js, level: Level, from_side: Side) -> Decimal | None:
    """Smallest distance from the originating side to the level over bars `js` (<= 0: touched / through).
    Reported separately: under V1 an approach without a touch is no retest (no proximity rule)."""
    d = [-(_lv(bars[j], level).max_below_points if from_side is Side.ABOVE else _lv(bars[j], level).max_above_points)
         for j in js]
    return min(d) if d else None


# --- the four families (DRYSDALE_SETUP_CANDIDATES_V1) ----------------------------------------------------

def _price_discovery(bars, quality, statics, tick) -> list[DrysdaleSetupCandidate]:
    """PRICE_DISCOVERY_CONTINUATION_CANDIDATE_V1, per outside episode (a maximal run of complete closes strictly
    beyond the same +/-1 sigma boundary):
      1 LAB_BREAKOUT_TRIGGER_V1     the run's first bar
      2 LAB_ACCEPTANCE_TIME_V1      the run's second bar (outside)
      3 LAB_RETEST_V1               a later bar of the run trades at / through the broken boundary (being in the
                                    run, it closes back outside)
      4 LAB_DIRECTIONAL_CONFIRMATION_V1  in the breakout direction, at the bar after that retest
    The first retest whose next bar confirms decides; a failed confirmation is reported and a later retest of the
    same episode may still complete the structure. DrysdaleBreakoutEvidence always accompanies the trigger."""
    n, out = len(bars), []
    src = SOURCE_CRITERIA[SetupFamily.PRICE_DISCOVERY_CONTINUATION]
    for direction in (Direction.UP, Direction.DOWN):
        side, bl = _word(direction, Side.ABOVE, Side.BELOW), _boundary(direction)
        for s, e in _runs(bars, lambda b, d=direction: b.value_position is _outside(d)):
            ongoing = e == n - 1
            accepted = e >= s + 1
            events = [_event(bars, j, "RETEST", bl, side, RETEST_POLICY, True, direction)
                      for j in range(s + 2, e + 1) if _touched_from(_lv(bars[j], bl), side)]
            if events:
                i = _decisive([(x.confirmation,) for x in events])
                rj, conf = events[i].bar_index, events[i].confirmation
                ret = _S
                stage = Stage.WAITING_FOR_CONFIRMATION if conf is _P else Stage.RETEST_OBSERVED
            else:
                rj, ret, conf = None, (_P if ongoing else _N), (_P if ongoing else _N)
                stage = Stage.ACCEPTED_OUTSIDE if accepted else Stage.BREAKOUT_TRIGGERED
            conditions = [
                _cond(1, BREAKOUT_POLICY, src[0], f"a complete 5m bar closes strictly {_word(direction, 'above +', 'below -')}"
                      "1 sigma (Globex VWAP bands)", _S, bars, s),
                _cond(2, ACCEPTANCE_POLICY, src[1], "two consecutive complete 5m closes strictly beyond the same "
                      "1 sigma boundary", _S if accepted else (_P if ongoing else _N), bars, s + 1),
                _cond(3, RETEST_POLICY, src[2], "a later bar of the outside episode trades at or through the broken "
                      "boundary and closes back outside", ret, bars, rj),
                _cond(4, CONFIRMATION_POLICY, src[3], f"the next complete bar closes {_word(direction, 'above', 'below')} "
                      f"its open and {_word(direction, 'above the retest bar high', 'below the retest bar low')}",
                      conf, bars, None if rj is None else rj + 1),
            ]
            out.append(_finish(SetupFamily.PRICE_DISCOVERY_CONTINUATION, direction, s, conditions, events, quality,
                               ongoing or conf is _P, stage, bars, _breakout(bars, s, e, direction, statics, tick),
                               (_acceptance(bars, s, e, _outside(direction), n),),
                               (("closest_approach_after_acceptance_points", _closest(bars, range(s + 2, e + 1), bl,
                                                                                       side)),)))
    return out


def _fade(bars, quality) -> list[DrysdaleSetupCandidate]:
    """FADE_VALUE_AREA_EXTREME_CANDIDATE_V1, per inside episode with LAB_ACCEPTANCE_TIME_V1 inside, and per
    boundary tested after the acceptance bar (an instance exists once that boundary is tested):
      1 LAB_ACCEPTANCE_TIME_V1      inside (the episode's second bar)
      2 boundary test               a later bar (of the episode, or the bar ending it) trades at / through
                                    +1 sigma (-1 sigma)
      3 LAB_REJECTION_V1            that bar closes strictly back below +1 sigma (above -1 sigma)
      4 LAB_DIRECTIONAL_CONFIRMATION_V1  toward the interior (DOWN at the upper band, UP at the lower band) at
                                    the next bar
    No touch / proximity entry rule exists. A test that closes beyond the boundary is reported with its
    acceleration facts."""
    n, out = len(bars), []
    src = SOURCE_CRITERIA[SetupFamily.FADE_VALUE_AREA_EXTREME]
    for s, e in _runs(bars, lambda b: b.value_position is ValuePosition.INSIDE_VALUE):
        if e < s + 1:
            continue
        ongoing = e == n - 1
        last = min(e + 1, n - 1)
        for bl, direction in ((Level.UPPER_1SD, Direction.DOWN), (Level.LOWER_1SD, Direction.UP)):
            origin = Side.BELOW if bl is Level.UPPER_1SD else Side.ABOVE
            events = [_event(bars, j, "BOUNDARY_TEST", bl, origin, REJECTION_POLICY,
                             _lv(bars[j], bl).close_side is origin, direction)
                      for j in range(s + 2, last + 1) if _touched_from(_lv(bars[j], bl), origin)]
            if not events:
                continue
            statuses = [(_S if x.proxy_satisfied else _N, x.confirmation) for x in events]
            i = _decisive(statuses)
            ev, (rej, conf) = events[i], statuses[i]
            open_ = ongoing or conf is _P
            conf = _after(conf, rej is _S, open_)
            stage = (Stage.BOUNDARY_TESTED if rej is not _S else
                     Stage.WAITING_FOR_CONFIRMATION if conf is _P else Stage.REJECTION_OBSERVED)
            conditions = [
                _cond(1, ACCEPTANCE_POLICY, src[0], "two consecutive complete 5m closes inside the inclusive "
                      "-1..+1 sigma value region", _S, bars, s + 1),
                _cond(2, VALUE_AREA_POLICY, src[1], f"a later complete bar trades at or through "
                      f"{'+' if bl is Level.UPPER_1SD else '-'}1 sigma", _S, bars, ev.bar_index),
                _cond(3, REJECTION_POLICY, src[2], "that bar closes strictly back inside the boundary", rej, bars,
                      ev.bar_index),
                _cond(4, CONFIRMATION_POLICY, src[3], f"the next complete bar closes {_word(direction, 'above', 'below')} "
                      f"its open and {_word(direction, 'above the test bar high', 'below the test bar low')}",
                      conf, bars, ev.bar_index + 1),
            ]
            out.append(_finish(SetupFamily.FADE_VALUE_AREA_EXTREME, direction, events[0].bar_index, conditions,
                               events, quality, open_, stage, bars,
                               acceptance=(_acceptance(bars, s, e, ValuePosition.INSIDE_VALUE, n),)))
    return out


def _return(bars, quality) -> list[DrysdaleSetupCandidate]:
    """RETURN_TO_VALUE_CANDIDATE_V1, per outside episode with LAB_ACCEPTANCE_TIME_V1 outside whose next complete
    bar closes inside value (an instance exists from that return):
      1 LAB_ACCEPTANCE_TIME_V1      outside
      2 LAB_RETURN_TO_VALUE_V1      the first close back inside (one close)
      3 LAB_ACCEPTANCE_TIME_V1      inside: the return close and the next close both inside
    No backtest is required (the source allows none). A LAB_RETEST_V1 of the same boundary later in the inside
    episode is reported as RETURN_TO_VALUE_RETEST_PRESENT."""
    n, out = len(bars), []
    src = SOURCE_CRITERIA[SetupFamily.RETURN_TO_VALUE]
    for from_dir in (Direction.UP, Direction.DOWN):
        direction, bl = _opposite(from_dir), _boundary(from_dir)
        origin = _word(from_dir, Side.BELOW, Side.ABOVE)  # the inside of the boundary
        for s, e in _runs(bars, lambda b, d=from_dir: b.value_position is _outside(d)):
            r = e + 1
            if e < s + 1 or r >= n or bars[r].value_position is not ValuePosition.INSIDE_VALUE:
                continue
            e2 = r
            while e2 + 1 < n and bars[e2 + 1].value_position is ValuePosition.INSIDE_VALUE:
                e2 += 1
            inside = _S if e2 >= r + 1 else (_P if r == n - 1 else _N)
            events = [_event(bars, j, "RETURN_RETEST", bl, origin, RETEST_POLICY, True, direction)
                      for j in range(r + 1, e2 + 1) if _touched_from(_lv(bars[j], bl), origin)]
            conditions = [
                _cond(1, ACCEPTANCE_POLICY, src[0], "two consecutive complete 5m closes strictly beyond the same "
                      "1 sigma boundary", _S, bars, s + 1),
                _cond(2, RETURN_POLICY, src[1], "after that outside episode, a complete bar closes back inside the "
                      "inclusive -1..+1 sigma region", _S, bars, r),
                _cond(3, ACCEPTANCE_POLICY, src[2], "two consecutive complete 5m closes inside value (the return "
                      "close and the next)", inside, bars, r + 1),
            ]
            out.append(_finish(SetupFamily.RETURN_TO_VALUE, direction, r, conditions, events, quality, inside is _P,
                               Stage.RETURNED_TO_VALUE, bars,
                               acceptance=(_acceptance(bars, s, e, _outside(from_dir), n),
                                           _acceptance(bars, r, e2, ValuePosition.INSIDE_VALUE, n)),
                               supporting=(("RETURN_TO_VALUE_RETEST_PRESENT", bool(events)),
                                           ("retest_required", False),
                                           ("closest_approach_after_return_points",
                                            _closest(bars, range(r + 1, e2 + 1), bl, origin)))))
    return out


def _bounce(bars, quality) -> list[DrysdaleSetupCandidate]:
    """VWAP_BOUNCE_CANDIDATE_V1 (conservative), per outside episode on the bounce side (its last bar a) and the
    complete bars after it up to and including the next outside close (an instance exists once the VWAP is
    tested in that window):
      1 prior outside               bar a closed strictly beyond +1 sigma (UP) / -1 sigma (DOWN)
      2 LAB_RETURN_TO_VALUE_V1      a later close inside value, at or before the test bar
      3 LAB_TREND_CONTEXT_V1        in the bounce direction at the bar before the test (required)
      4 LAB_VWAP_TEST_V1            the test bar trades at or through the Globex VWAP from the trend side
      5 LAB_DIRECTIONAL_CONFIRMATION_V1  away from the VWAP (UP / DOWN) at the next bar
    The first test meeting 2-5 decides, else the furthest-progressed latest test is reported. ATR is context
    only."""
    n, out = len(bars), []
    src = SOURCE_CRITERIA[SetupFamily.VWAP_BOUNCE]
    for direction in (Direction.UP, Direction.DOWN):
        side = _word(direction, Side.ABOVE, Side.BELOW)
        slope = _word(direction, Slope.RISING, Slope.FALLING)
        for _, a in _runs(bars, lambda b, d=direction: b.value_position is _outside(d)):
            end = next((i for i in range(a + 1, n) if bars[i].value_position is not ValuePosition.INSIDE_VALUE), None)
            events, statuses, returns = [], [], []
            for j in range(a + 1, (end if end is not None else n - 1) + 1):
                if not _touched_from(_lv(bars[j], Level.GLOBEX_VWAP), side):
                    continue
                inside = next((i for i in range(a + 1, j + 1)
                               if bars[i].value_position is ValuePosition.INSIDE_VALUE), None)
                p = bars[j - 1]
                trend = _S if p.vwap_slope is slope and _lv(p, Level.GLOBEX_VWAP).close_side is side else _N
                ev = _event(bars, j, "VWAP_TEST", Level.GLOBEX_VWAP, side, VWAP_TEST_POLICY, True, direction, trend)
                events.append(ev)
                statuses.append((_S if inside is not None else _N, trend, ev.confirmation))
                returns.append(inside)
            if not events:
                continue
            i = _decisive(statuses)
            ev, (ret, trend, conf), inside = events[i], statuses[i], returns[i]
            open_ = end is None or conf is _P
            conf = _after(conf, ret is _S and trend is _S, open_)
            stage = Stage.WAITING_FOR_CONFIRMATION if conf is _P and ret is _S and trend is _S else Stage.VWAP_TESTED
            conditions = [
                _cond(1, VALUE_AREA_POLICY, src[0], f"an earlier complete close strictly "
                      f"{_word(direction, 'above +', 'below -')}1 sigma", _S, bars, a),
                _cond(2, RETURN_POLICY, src[1], "then a complete close back inside value (at or before the test)",
                      ret, bars, inside),
                _cond(3, TREND_POLICY, src[0], f"at the bar before the test: Globex VWAP {slope.value} vs the "
                      f"previous bar and the close strictly {side.value} the VWAP", trend, bars, ev.bar_index - 1),
                _cond(4, VWAP_TEST_POLICY, src[1], "a complete bar trades at or through the Globex VWAP", _S, bars,
                      ev.bar_index),
                _cond(5, CONFIRMATION_POLICY, src[2], f"the next complete bar closes {_word(direction, 'above', 'below')} "
                      f"its open and {_word(direction, 'above the test bar high', 'below the test bar low')}",
                      conf, bars, ev.bar_index + 1),
            ]
            out.append(_finish(SetupFamily.VWAP_BOUNCE, direction, events[0].bar_index, conditions, events, quality,
                               open_, stage, bars, supporting=(("trend_context_required", True),)))
    return out


# --- context and the builder -----------------------------------------------------------------------------

def _context(bars) -> DrysdaleContextEvidence:
    n = len(bars)
    last = bars[-1]
    prev = bars[-2] if n > 1 else None
    tv = _lv(last, Level.GLOBEX_VWAP).close_side
    trend = (Direction.UP if last.vwap_slope is Slope.RISING and tv is Side.ABOVE else
             Direction.DOWN if last.vwap_slope is Slope.FALLING and tv is Side.BELOW else None)

    def streak(f):
        c = 0
        for i in range(n - 1, 0, -1):
            if not f(bars[i], bars[i - 1]):
                break
            c += 1
        return c

    s = n - 1
    while s > 0 and bars[s - 1].value_position is last.value_position:
        s -= 1
    recent = bars[-RECENT_BARS:]
    a12 = bars[-1 - VOLUME_BASELINE_BARS].atr if n > VOLUME_BASELINE_BARS else None
    return DrysdaleContextEvidence(
        last.end_utc, last.value_position, last.vwap_delta, last.vwap_slope, trend,
        None if prev is None else last.high > prev.high, None if prev is None else last.low > prev.low,
        None if prev is None else last.high < prev.high, None if prev is None else last.low < prev.low,
        streak(lambda b, p: b.high > p.high and b.low > p.low), streak(lambda b, p: b.high < p.high and b.low < p.low),
        sum(1 for b in recent if b.direction is BarDirection.UP), sum(1 for b in recent if b.direction is BarDirection.DOWN),
        _acceptance(bars, s, n - 1, last.value_position, n),
        sum((_lv(b, Level.UPPER_1SD).seconds_above for b in bars), timedelta(0)),
        sum((_lv(b, Level.LOWER_1SD).seconds_below for b in bars), timedelta(0)),
        sum(1 for b in bars if any(_touched_from(_lv(b, lv), sd) for lv, sd in
                                   ((Level.UPPER_2SD, Side.BELOW), (Level.LOWER_2SD, Side.ABOVE)))),
        last.atr, a12, None if last.atr is None or a12 is None else _sub(last.atr, a12), _volume(bars, n - 1),
        NOT_AVAILABLE_CONFIRMATIONS)


def evaluate(bars: tuple[GlobexBar, ...], quality: str, statics, tick: Decimal) -> tuple[DrysdaleSetupCandidate, ...]:
    """DRYSDALE_SETUP_CANDIDATES_V1 over complete bars. Pure; families may overlap; no precedence."""
    if not bars:
        return ()
    found = (_price_discovery(bars, quality, statics, tick) + _fade(bars, quality) + _return(bars, quality)
             + _bounce(bars, quality))
    return tuple(sorted(found, key=lambda c: (c.first_event_utc, c.family.value, c.direction.value)))


def build_drysdale_analysis(prep: PreparedReplay, snapshot: MarketStudySnapshot, trades: tuple | None = None,
                            checkpoint: _Checkpoint | None = None, keep: list | None = None) -> DrysdaleSetupAnalysis:
    """DRYSDALE_SETUP_ANALYSIS_V1 at the snapshot's cutoff.

    `trades`: the as-of scoped tape at that cutoff (recomputed when omitted). `checkpoint`: a pass at an
    earlier cutoff whose earlier trades are identical (see DrysdaleCache). `keep`, if given, receives the
    new checkpoint.
    """
    from dicks_laboratory.replay import as_of_evidence
    cutoff, clock = snapshot.cutoff, snapshot.cutoff.clock
    if trades is None:
        trades = as_of_evidence(prep, cutoff).scoped
    anchor = resolve_anchor(AnchorKind.SESSION_OPEN, prep.trading_date).anchor_timestamp_utc
    window_end = next(m.matures_at_utc for m in snapshot.maturity if m.component == "vwap SESSION_OPEN")
    acc = run_pass(trades, anchor, cutoff, checkpoint)
    if keep is not None:
        keep.append(_Checkpoint(cutoff, acc))
    bars, developing = _bars(acc, clock, window_end)
    vw = next(v for v in snapshot.vwap if v.anchor_kind is AnchorKind.SESSION_OPEN)
    status, reasons = vw.status.value, tuple(vw.reasons) + tuple(snapshot.dataset_quality.reasons)
    maturity = (Maturity.NOT_YET_AVAILABLE if clock <= anchor else
                Maturity.WINDOW_COMPLETE if clock >= window_end else Maturity.DEVELOPING)
    if acc.S0:
        S0, S1, S2, ps = acc.S0, acc.S1, acc.S2, acc.ps
        vwap = _dec(S1, S0 * ps)
        with localcontext() as c:
            c.prec, c.rounding = 28, ROUND_HALF_EVEN
            sigma = (Decimal(S2 * S0 - S1 * S1) / Decimal(S0 * S0 * ps * ps)).sqrt()
            u1, l1, u2, l2 = vwap + sigma, vwap - sigma, vwap + 2 * sigma, vwap - 2 * sigma
        D, var = acc.last_P * S0 - S1, S2 * S0 - S1 * S1
        sd = _sides(D, var, D * D)
        band = GlobexBands(GLOBEX_BAND_POLICY, "SESSION_OPEN 17:00 America/Chicago (Globex)", anchor, window_end,
                           maturity, acc.n, _dec(S0, acc.vs), vwap, sigma, var == 0, u1, l1, u2, l2, VALUE_AREA_POLICY,
                           _dec(acc.last_P, ps),
                           ValuePosition.ABOVE_VALUE if sd[1] > 0 else ValuePosition.BELOW_VALUE if sd[2] < 0
                           else ValuePosition.INSIDE_VALUE, _zone(D, var, 2))
    else:
        band = GlobexBands(GLOBEX_BAND_POLICY, "SESSION_OPEN 17:00 America/Chicago (Globex)", anchor, window_end,
                           maturity, 0, None, None, None, None, None, None, None, None, VALUE_AREA_POLICY, None, None,
                           None)
    available = band.vwap is not None and status != ComponentStatus.NOT_AVAILABLE.value
    tick = price_grid_for_instrument(prep.instrument).tick_size
    candidates = evaluate(bars, status, _statics(snapshot), tick) if available else ()
    if not available:
        state = CandidateState.NOT_AVAILABLE
    elif any(c.state is CandidateState.CANDIDATE for c in candidates):
        state = CandidateState.CANDIDATE
    elif any(c.state is CandidateState.QUALITY_QUALIFIED for c in candidates):
        state = CandidateState.QUALITY_QUALIFIED
    else:
        state = CandidateState.DEVELOPING
    return DrysdaleSetupAnalysis(SCHEMA, prep.dataset_id, prep.trading_date, cutoff, clock, snapshot_sha256(snapshot),
                                 SOURCE_MODEL_VERSION, POLICIES, status, reasons, state, band, developing,
                                 bars if available else (), _context(bars) if available and bars else None,
                                 candidates)


# --- reuse on a prepared session ---------------------------------------------------------------------------

class DrysdaleCache:
    """Per-ReplaySession reuse (0AB-B performance): results per cutoff, and one resumable pass checkpoint.

    A checkpoint at cutoff C1 is reused for C2 only when C2's market and knowledge cutoffs are both at or after
    C1's and no record newly known between them has a market time before C1's market cutoff and none is a
    correction or cancel (then every trade before C1 is the same in both as-of tapes). Otherwise the pass is
    recomputed from the anchor. Results are keyed by the full ReplayCutoff.
    """

    def __init__(self, size: int = 8) -> None:
        self.results: dict[ReplayCutoff, DrysdaleSetupAnalysis] = {}
        self.checkpoint: _Checkpoint | None = None
        self.size = size
        self.stats = {"hits": 0, "misses": 0, "resumed": 0, "full": 0}

    def usable(self, session, cutoff: ReplayCutoff) -> _Checkpoint | None:
        c = self.checkpoint
        if c is None:
            return None
        a, b = c.cutoff, cutoff
        if not (a.market_time_cutoff_utc <= b.market_time_cutoff_utc and
                a.knowledge_time_cutoff_utc <= b.knowledge_time_cutoff_utc and
                (a.knowledge_source_order_cutoff is None) == (b.knowledge_source_order_cutoff is None)):
            return None
        if a.knowledge_source_order_cutoff is not None and a.knowledge_source_order_cutoff > b.knowledge_source_order_cutoff:
            return None
        nk = session.newly_known(a, b)
        return c if nk.with_market_time_before_earlier_market_cutoff == 0 and not nk.corrections and \
            not nk.cancels else None


def analyze(session, at=None, *, cutoff: ReplayCutoff | None = None, trades=None) -> DrysdaleSetupAnalysis:
    """DRYSDALE_SETUP_ANALYSIS_V1 for a ReplaySession time, reusing the session's DrysdaleCache."""
    cache = getattr(session, "drysdale_cache", None)
    if cache is None:
        cache = session.drysdale_cache = DrysdaleCache()
    snap = session.snapshot(at, cutoff=cutoff)
    key = snap.cutoff
    if key in cache.results:
        cache.stats["hits"] += 1
        return cache.results[key]
    cache.stats["misses"] += 1
    ck = cache.usable(session, key)
    cache.stats["resumed" if ck else "full"] += 1
    keep: list = []
    result = build_drysdale_analysis(session.replay.current, snap, trades, ck, keep)
    if len(cache.results) >= cache.size:
        cache.results.pop(next(iter(cache.results)))
    cache.results[key] = result
    if cache.checkpoint is None or keep[0].cutoff.market_time_cutoff_utc >= cache.checkpoint.cutoff.market_time_cutoff_utc:
        cache.checkpoint = keep[0]
    return result


# --- serialization and text ----------------------------------------------------------------------------

def analysis_payload(a: DrysdaleSetupAnalysis) -> dict:
    return mss.encode(a)


def drysdale_sha256(a: DrysdaleSetupAnalysis) -> str:
    return hashlib.sha256(mss._dumps(analysis_payload(a)).encode("ascii")).hexdigest()


def canonical_analysis_json(a: DrysdaleSetupAnalysis) -> str:
    payload = analysis_payload(a)
    payload[HASH_FIELD] = drysdale_sha256(a)
    return mss._dumps(payload)


_TITLES = {SetupFamily.PRICE_DISCOVERY_CONTINUATION: "SETUP 1 - PRICE DISCOVERY CONTINUATION",
           SetupFamily.FADE_VALUE_AREA_EXTREME: "SETUP 2 - FADE VALUE AREA EXTREMES",
           SetupFamily.RETURN_TO_VALUE: "SETUP 3 - RETURN TO VALUE",
           SetupFamily.VWAP_BOUNCE: "SETUP 4 - VWAP BOUNCE"}
_MARK = {ConditionStatus.SATISFIED: "[satisfied]", ConditionStatus.NOT_SATISFIED: "[not satisfied]",
         ConditionStatus.PENDING: "[pending]", ConditionStatus.NOT_AVAILABLE: "[not available]"}


def _ct(ts: datetime | None) -> str:
    return "--" if ts is None else ts.astimezone(_CT).strftime("%H:%M")


def latest_by_family(a: DrysdaleSetupAnalysis) -> dict[tuple[SetupFamily, Direction], DrysdaleSetupCandidate]:
    out = {}
    for c in a.candidates:
        out[(c.family, c.direction)] = c
    return out


def render_analysis(a: DrysdaleSetupAnalysis) -> str:
    """Instructional text: source criteria, Laboratory V1 conditions, context. Not advice."""
    b = a.bands
    lines = [f"DRYSDALE VWAP WAVE - LABORATORY V1 TRAINING CANDIDATES  {a.trading_date}  as of "
             f"{a.clock_utc.astimezone(_CT):%Y-%m-%d %H:%M:%S %Z}",
             f"  Globex VWAP (anchor 17:00 CT): {b.vwap if b.vwap is not None else '--'}  sigma "
             f"{b.sigma if b.sigma is not None else '--'}  [{b.maturity.value}; {a.status}]",
             f"  Drysdale VWAP value area (DRYSDALE_VALUE_AREA_V1, +/-1 sigma): {b.lower_1sd} - {b.upper_1sd};  "
             f"outer +/-2 sigma context: {b.lower_2sd} - {b.upper_2sd}",
             "  (not the Laboratory 70% profile value area, not the playbook 68% profile value)",
             f"  complete 5m bars: {len(a.bars)}; analysis state {a.state.value}"]
    if a.reasons and a.status != "AVAILABLE":
        lines.append(f"  QUALITY: {a.status} - {'; '.join(a.reasons)}")
    latest = latest_by_family(a)
    for family in SetupFamily:
        lines += ["", _TITLES[family]]
        mine = [c for c in a.candidates if c.family is family]
        lines.append("  Drysdale source criteria (SOURCE SAYS; discretionary unless noted):")
        lines += [f"  - {s}" for s in SOURCE_CRITERIA[family]]
        if not mine:
            lines.append("  Laboratory V1: no instance in this session so far.")
            continue
        counts = {}
        for c in mine:
            counts[c.state.value] = counts.get(c.state.value, 0) + 1
        lines.append(f"  instances this session: {len(mine)} ({', '.join(f'{k} {v}' for k, v in sorted(counts.items()))})")
        for d in Direction:
            c = latest.get((family, d))
            if c is None:
                continue
            lines.append(f"  latest {d.value} instance {c.candidate_id} (from {_ct(c.first_event_utc)} CT)  "
                         f"stage {c.stage.value}")
            lines.append("  Laboratory V1 (LABORATORY V1 TRAINING PROXY):")
            for k in c.conditions:
                at = f" at {_ct(k.satisfied_at_utc)}" if k.satisfied_at_utc else ""
                lines.append(f"    {_MARK[k.status]:<16} {k.policy_id}: {k.laboratory_rule}{at}")
            if c.breakout is not None:
                x = c.breakout
                lines.append("  Context (DrysdaleBreakoutEvidence):")
                lines.append(f"    +/-2 sigma reached: {'YES' if x.reached_2sd else 'NO'};  VWAP slope: "
                             f"{x.vwap_slope.value if x.vwap_slope else '--'} ({x.vwap_delta});  breakout-bar volume "
                             f"ratio vs mean of {x.volume.baseline_bars}: {_r(x.volume.ratio_to_mean)}")
                lines.append(f"    distance beyond 1 sigma at the trigger close: {x.distance_beyond_points} pts "
                             f"({_r(x.distance_beyond_sigma)} sigma, {_r(x.distance_beyond_atr)} ATR);  max excursion "
                             f"{x.max_excursion_beyond_points} pts;  time beyond {int(x.seconds_beyond.total_seconds())} s;  "
                             f"closes beyond {x.completed_closes_beyond}")
                lines.append(f"    time of day {x.bar_end_ct} CT (cash session: {x.in_us_cash_session});  nearest "
                             f"opposing reference {x.nearest_opposing_reference or '--'} "
                             f"{x.nearest_opposing_distance_points or ''};  returned inside: {x.returned_inside}")
                lines.append(f"    not available: {', '.join(x.not_available)}")
            for ev in c.events[-3:]:
                lines.append(f"    event {ev.kind} {_ct(ev.bar_end_utc)} vs {ev.level.value}: through {ev.traded_through} "
                             f"excursion {ev.excursion_points} pts, close {ev.close_side.value}, proxy "
                             f"{'satisfied' if ev.proxy_satisfied else 'not satisfied'}, next-bar confirmation "
                             f"{ev.confirmation.value}" + (f", trend context {ev.trend_context.value}"
                                                           if ev.trend_context else ""))
            for name, value in c.supporting:
                lines.append(f"    {name}: {value}")
            lines.append(f"  Result: {c.state.value}" + (f" ({a.status})" if c.state is CandidateState.QUALITY_QUALIFIED
                                                         else ""))
    if a.context is not None:
        x = a.context
        lines += ["", "CONTEXT AT THE LAST COMPLETE BAR (facts)",
                  f"  {_ct(x.last_bar_end_utc)} CT: {x.value_position.value}; VWAP slope "
                  f"{x.vwap_slope.value if x.vwap_slope else '--'} ({x.vwap_delta}); {TREND_POLICY} "
                  f"{x.trend_context.value if x.trend_context else 'neither'}",
                  f"  current episode: {x.current_episode.completed_closes} closes ({x.current_episode.region}); "
                  f"{ACCEPTANCE_POLICY}: {'YES' if x.current_episode.lab_acceptance_time_v1 else 'NO'}",
                  f"  ATR_5M_V1 {x.atr} (12 bars earlier {x.atr_12_bars_earlier}); volume ratio vs mean "
                  f"{_r(x.volume.ratio_to_mean)}"]
    lines += ["", "Educational structure only: no trade, entry, stop, target or sizing. Laboratory V1 proxies are "
              "ours, not Drysdale's definitions."]
    return "\n".join(lines) + "\n"


def _r(x: Decimal | None) -> str:
    return "--" if x is None else f"{x:.2f}"
