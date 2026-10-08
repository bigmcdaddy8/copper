"""0Y-C: hand-verified day-structure facts and day-type candidates.

Each fixture lists every period's range (A..M, 30-minute cash periods; IB = A+B)
in a comment; IB share, extensions and the expected candidate were worked by
hand from those ranges before the code was run. Grid: ES 0.25, so 1 point = 4 ticks.
"""
from __future__ import annotations

import random
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from dicks_laboratory.tpo_day_structure import (
    NORMAL_MIN_IB_SHARE,
    NORMAL_VARIATION_MIN_IB_SHARE,
    TREND_MIN_NEW_EXTREME_PERIODS,
    CandidateResult,
    ClassificationOutcome,
    ClassificationQuality,
    Condition,
    DayType,
    DayTypeCandidate,
    Direction,
    DirectionalState,
    ExtensionDirection,
    QualityGrade,
    build_day_structure_facts,
    classification_quality,
    classify_day_type,
    resolve_candidates,
    study_window_terminal,
)
from dicks_laboratory.tpo_profile import build_tpo_profile
from dicks_laboratory.tpo_structure import build_profile_structure
from dicks_laboratory.volume_profile import ES_PRICE_GRID

D = Decimal
TD = date(2026, 10, 6)
OPEN = datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)
CLEAN = classification_quality(True, 0, "FINALIZED")
UP, DOWN = Direction.UP, Direction.DOWN
EXT_UP, EXT_DOWN, EXT_BOTH = ExtensionDirection.UP, ExtensionDirection.DOWN, ExtensionDirection.BOTH_IN_SAME_PERIOD


def _trades(ranges, close=None):
    """Period i trades its low at minute 1 and high at minute 2; `close` trades at M+29 min."""
    out = []
    for i, (low, high) in enumerate(ranges):
        if low is None:
            continue
        out += [SimpleNamespace(event_timestamp=OPEN + timedelta(minutes=i * 30 + 1), price=D(str(low))),
                SimpleNamespace(event_timestamp=OPEN + timedelta(minutes=i * 30 + 2), price=D(str(high)))]
    if close is not None:
        out.append(SimpleNamespace(event_timestamp=OPEN + timedelta(minutes=12 * 30 + 29), price=D(str(close))))
    return tuple(out)


def _day(ranges, close=None, quality=CLEAN):
    trades = _trades(ranges, close)
    profile = build_tpo_profile(trades, ES_PRICE_GRID, TD)
    structure = build_profile_structure(profile)
    facts = build_day_structure_facts(profile, structure, study_window_terminal(trades, profile, ES_PRICE_GRID))
    return facts, classify_day_type(facts, quality)


def _results(day):
    return {c.day_type: c.result for c in day.candidates}


def _cond(day, day_type, name):
    cand = next(c for c in day.candidates if c.day_type is day_type)
    return next(c for c in cand.conditions if c.name == name)


def test_policy_thresholds_are_explicit():
    assert (NORMAL_MIN_IB_SHARE, NORMAL_VARIATION_MIN_IB_SHARE, TREND_MIN_NEW_EXTREME_PERIODS) == (
        D("0.85"), D("0.50"), 2)


# --- facts + candidates ------------------------------------------------------------------

def test_no_ib_extension_is_normal_day_with_unevaluated_history_condition():
    # A,B 100-110 (IB 10); C..M 102-108; close 108
    f, day = _day([(100, 110)] * 2 + [(102, 108)] * 11, close=108)
    assert (f.ib_range, f.profile_range, f.ib_share_of_range, f.range_multiple_of_ib) == (D(10), D(10), D(1), D(1))
    assert (f.extension_above, f.extension_below, f.directional_state) == (D(0), D(0), DirectionalState.NO_EXTENSION)
    assert (f.first_extension_direction, f.last_extension_direction) == (None, None)
    assert (f.periods_extending_above_ib, f.new_post_ib_high_periods) == ("", "")
    assert (day.outcome, day.primary, day.direction) == (ClassificationOutcome.CANDIDATE, DayType.NORMAL_DAY, None)
    hist = _cond(day, DayType.NORMAL_DAY, "ib_wide_vs_history")
    assert hist.satisfied is None and "historical" in hist.observed
    assert _results(day) == {DayType.NORMAL_DAY: CandidateResult.YES, DayType.NORMAL_VARIATION_DAY: CandidateResult.NO,
                             DayType.TREND_DAY: CandidateResult.NO, DayType.NEUTRAL_DAY: CandidateResult.NO}


def test_small_up_only_extension_wide_ib_stays_normal():
    # A,B 100-110; C 105-111; D..M 103-109.  range 11, IB share 10/11 = 0.909 >= 0.85
    f, day = _day([(100, 110)] * 2 + [(105, 111)] + [(103, 109)] * 10)
    assert (f.directional_state, f.extension_above, f.extension_above_ticks) == (DirectionalState.UP_ONLY, D(1), 4)
    assert f.ib_share_of_range == D(10) / D(11) and f.extension_above_multiple_of_ib == D("0.1")
    assert (f.periods_extending_above_ib, f.new_post_ib_high_periods, f.first_extension_direction) == ("C", "C", EXT_UP)
    assert (day.primary, day.direction) == (DayType.NORMAL_DAY, None)
    assert _cond(day, DayType.NORMAL_VARIATION_DAY, "ib_share_band").satisfied is False


def test_wide_ib_low_extension_structure():
    # A,B 100-120 (IB 20); C..L 105-115; M 115-121.  range 21, share 20/21 = 0.952
    f, day = _day([(100, 120)] * 2 + [(105, 115)] * 10 + [(115, 121)], close=120)
    assert (f.ib_range_ticks, f.profile_range_ticks, f.periods_extending_above_ib) == (80, 84, "M")
    assert day.primary is DayType.NORMAL_DAY


def test_down_only_normal_variation_with_direction():
    # A 100-110, B 102-110 (IB 100-110); C 96-104; D 94-100; E..M 95-102.  range 16, share 0.625
    f, day = _day([(100, 110), (102, 110), (96, 104), (94, 100)] + [(95, 102)] * 9, close=97)
    assert (f.directional_state, f.extension_below, f.extension_below_ticks) == (DirectionalState.DOWN_ONLY, D(6), 24)
    assert (f.ib_share_of_range, f.range_multiple_of_ib, f.extension_below_multiple_of_ib) == (
        D("0.625"), D("1.6"), D("0.6"))
    assert (f.periods_extending_below_ib, f.new_post_ib_low_periods) == ("CDEFGHIJKLM", "CD")
    assert (f.first_extension_direction, f.last_extension_direction) == (EXT_DOWN, EXT_DOWN)
    assert (day.outcome, day.primary, day.direction) == (
        ClassificationOutcome.CANDIDATE, DayType.NORMAL_VARIATION_DAY, DOWN)
    assert "NORMAL_VARIATION_DAY" not in DOWN.value and "DOWN" not in day.primary.value  # direction kept separate


def test_both_side_extension_is_neutral_first_up_last_down():
    # A,B 100-110; C 111-112; D 95-101; E..M 100-105.  above 2, below 5, range 17
    f, day = _day([(100, 110)] * 2 + [(108, 112), (95, 101)] + [(100, 105)] * 9, close=103)
    assert (f.directional_state, f.extension_above, f.extension_below) == (DirectionalState.BOTH_SIDES, D(2), D(5))
    assert (f.first_extension_direction, f.last_extension_direction) == (EXT_UP, EXT_DOWN)
    assert (f.periods_extending_above_ib, f.periods_extending_below_ib) == ("C", "D")
    assert (day.primary, day.direction) == (DayType.NEUTRAL_DAY, None)
    assert _cond(day, DayType.NEUTRAL_DAY, "both_sides_extension").observed == "above 8 ticks, below 20 ticks"
    assert _cond(day, DayType.NORMAL_DAY, "directional_state").satisfied is False


def test_two_sided_extension_in_one_period_and_minimal_one_tick_each_side():
    # A,B 100-110; C 99.75-110.25 (one tick each side); D..M 101-109
    f, day = _day([(100, 110)] * 2 + [("99.75", "110.25")] + [(101, 109)] * 10)
    assert (f.extension_above_ticks, f.extension_below_ticks) == (1, 1)
    assert (f.first_extension_direction, f.last_extension_direction) == (EXT_BOTH, EXT_BOTH)
    assert day.primary is DayType.NEUTRAL_DAY  # V1: no material-extension threshold


def test_persistent_new_highs_trend_up_lists_every_condition():
    # A 100-104, B 101-105 (IB 100-105 = 5); C 104-108; D 107-111; E 110-114; F 113-117; G..M 115-118; close 117.5
    f, day = _day([(100, 104), (101, 105), (104, 108), (107, 111), (110, 114), (113, 117)] + [(115, 118)] * 7,
                  close="117.5")
    assert (f.profile_range, f.ib_share_of_range) == (D(18), D(5) / D(18))
    assert (f.new_post_ib_high_periods, f.periods_extending_above_ib) == ("CDEFG", "CDEFGHIJKLM")
    assert (f.longest_higher_low_run, f.first_period_at_profile_high, f.first_period_at_profile_low) == (7, "G", "A")
    assert (f.terminal.price, f.terminal.period_label, f.profile_midpoint) == (D("117.5"), "M", D(109))
    assert f.terminal.percentile_in_range == D("17.5") / D(18)
    assert (f.terminal.distance_from_high, f.terminal.distance_from_low) == (D("0.5"), D("17.5"))
    assert (day.outcome, day.primary, day.direction) == (ClassificationOutcome.CANDIDATE, DayType.TREND_DAY, UP)
    trend = next(c for c in day.candidates if c.day_type is DayType.TREND_DAY)
    assert [c.name for c in trend.satisfied] == [
        "directional_state", "ib_share_narrow", "persistent_new_extremes", "terminal_on_extension_side"]
    assert trend.failed == () and trend.not_evaluated == ()
    assert _cond(day, DayType.TREND_DAY, "persistent_new_extremes").observed == "new extreme periods: CDEFG (5)"


def test_persistent_new_lows_trend_down():
    # A 116-120, B 115-119 (IB 115-120); C 111-115; D 108-112; E 105-109; F 102-106; G..M 100-103; close 100.5
    f, day = _day([(116, 120), (115, 119), (111, 115), (108, 112), (105, 109), (102, 106)] + [(100, 103)] * 7,
                  close="100.5")
    assert (f.ib_share_of_range, f.new_post_ib_low_periods, f.longest_lower_high_run) == (D("0.25"), "CDEFG", 7)
    assert (day.primary, day.direction) == (DayType.TREND_DAY, DOWN)


def test_one_sided_extension_then_reversal_is_unclassified():
    # A 100-104, B 101-105; C 104-108; D 107-111; E 110-114; F 106-112; G 103-107; H..M 101-104; close 102
    f, day = _day([(100, 104), (101, 105), (104, 108), (107, 111), (110, 114), (106, 112), (103, 107)]
                  + [(101, 104)] * 6, close=102)
    assert (f.directional_state, f.new_post_ib_high_periods, f.ib_share_of_range) == (
        DirectionalState.UP_ONLY, "CDE", D(5) / D(14))
    assert (day.outcome, day.primary, day.direction, day.matched) == (ClassificationOutcome.UNCLASSIFIED, None, None, ())
    term = _cond(day, DayType.TREND_DAY, "terminal_on_extension_side")
    assert (term.satisfied, term.observed) == (False, "terminal 102.00 vs midpoint 107.00")
    assert _cond(day, DayType.NORMAL_VARIATION_DAY, "ib_share_band").satisfied is False


def test_ambiguous_structure_single_period_jump_is_unclassified_not_forced():
    # A 100-104, B 100-105; C 104-115 (one-period jump); D..M 106-113; close 112.  share 5/15
    f, day = _day([(100, 104), (100, 105), (104, 115)] + [(106, 113)] * 10, close=112)
    assert (f.new_post_ib_high_periods, f.extension_above) == ("C", D(10))
    assert day.outcome is ClassificationOutcome.UNCLASSIFIED
    trend = next(c for c in day.candidates if c.day_type is DayType.TREND_DAY)
    assert [c.name for c in trend.failed] == ["persistent_new_extremes"] and trend.direction is None


def test_narrow_ib_large_extension_fact():
    f, _ = _day([(100, 104), (101, 105), (104, 108), (107, 111), (110, 114), (113, 117)] + [(115, 118)] * 7)
    assert (f.ib_range_ticks, f.extension_above_ticks, f.extension_above_multiple_of_ib) == (20, 52, D("2.6"))


def test_ib_share_boundaries_are_inclusive_as_documented():
    # exactly 0.85: A,B 100-117 (IB 17); C 110-120; D..M 105-115 -> range 20
    _, normal = _day([(100, 117)] * 2 + [(110, 120)] + [(105, 115)] * 10)
    assert (normal.facts.ib_share_of_range, normal.primary) == (D("0.85"), DayType.NORMAL_DAY)
    # exactly 0.50: A,B 100-110; C 105-115; D 110-120; E..M 112-118; close 117 -> range 20
    _, nv = _day([(100, 110)] * 2 + [(105, 115), (110, 120)] + [(112, 118)] * 9, close=117)
    assert (nv.facts.ib_share_of_range, nv.primary, nv.direction) == (D("0.5"), DayType.NORMAL_VARIATION_DAY, UP)
    assert _cond(nv, DayType.TREND_DAY, "ib_share_narrow").satisfied is False


def test_location_facts_poc_value_ib_midpoint_percentiles():
    f, _ = _day([(100, 110)] * 2 + [(102, 108)] * 11, close=108)
    assert (f.poc, f.profile_midpoint, f.ib_midpoint) == (D(105), D(105), D(105))
    assert (f.poc_percentile, f.ib_midpoint_percentile, f.terminal.percentile_in_range) == (D("0.5"), D("0.5"), D("0.8"))
    assert f.value_area_midpoint == (f.value_area_low + f.value_area_high) / 2
    assert (f.periods_at_profile_high, f.upper_extreme.letters_at_extreme) == ("AB", "AB")
    assert f.interior_one_tpo_zones == ()


# --- zero denominators, missing data, quality -----------------------------------------------

def test_zero_ib_range_has_undefined_ratios_and_is_not_classified():
    # A,B 100.00 only; C..M 100-102
    f, day = _day([(100, 100)] * 2 + [(100, 102)] * 11)
    assert (f.ib_range, f.ib_share_of_range, f.range_multiple_of_ib, f.extension_above_multiple_of_ib) == (
        D(0), D(0), None, None)
    assert (day.outcome, day.candidates) == (ClassificationOutcome.NOT_CLASSIFIED, ())
    assert "IB range = 0: IB-relative policies undefined" in day.not_classified_reasons


def test_zero_profile_range_has_undefined_percentiles():
    f, day = _day([(100, 100)] * 13, close=100)
    assert (f.ib_share_of_range, f.poc_percentile, f.terminal.percentile_in_range) == (None, None, None)
    assert day.outcome is ClassificationOutcome.NOT_CLASSIFIED and "profile range = 0" in day.not_classified_reasons


def test_truncated_study_window_is_not_classified_but_facts_remain():
    # Trend-up fixture but the capture ended early (quality) and periods L, M are empty.
    ranges = [(100, 104), (101, 105), (104, 108), (107, 111), (110, 114), (113, 117)] + [(115, 118)] * 5
    f, day = _day(ranges + [(None, None)] * 2, quality=classification_quality(False, 0, "FINALIZED"))
    assert f.periods_without_trades == "LM" and f.new_post_ib_high_periods == "CDEFG" and f.terminal.period_label == "K"
    assert (day.outcome, day.primary, day.direction, day.candidates) == (
        ClassificationOutcome.NOT_CLASSIFIED, None, None, ())
    assert day.not_classified_reasons == ("STUDY WINDOW NOT FULLY CAPTURED", "period(s) with no retained trades: LM")
    assert day.facts is f


def test_missing_period_alone_blocks_classification():
    _, day = _day([(100, 110)] * 2 + [(102, 108)] * 5 + [(None, None)] + [(102, 108)] * 5)
    assert day.not_classified_reasons == ("period(s) with no retained trades: H",)


def test_quality_policy_grades():
    assert classification_quality(True, 0, "FINALIZED") == ClassificationQuality(QualityGrade.UNQUALIFIED, ())
    assert classification_quality(None, 0, "FINALIZED").grade is QualityGrade.NOT_CLASSIFIABLE
    gap = classification_quality(True, 1, "FINALIZED")
    assert (gap.grade, gap.reasons) == (
        QualityGrade.QUALITY_QUALIFIED, ("gap evidence (KNOWN/SUSPECTED) overlaps the study window: 1",))
    assert classification_quality(True, 0, "OPEN").reasons == ("lifecycle OPEN (not FINALIZED)",)


def test_quality_qualified_still_classifies_and_records_reasons():
    _, day = _day([(100, 110)] * 2 + [(102, 108)] * 11, quality=classification_quality(True, 2, "FINALIZED"))
    assert (day.outcome, day.primary, day.quality.grade) == (
        ClassificationOutcome.CANDIDATE, DayType.NORMAL_DAY, QualityGrade.QUALITY_QUALIFIED)


# --- terminal price -----------------------------------------------------------------------

def test_terminal_ignores_out_of_window_and_off_grid_and_breaks_timestamp_ties_by_tape_order():
    trades = _trades([(100, 110)] * 2)
    late = OPEN + timedelta(minutes=50)
    extra = (SimpleNamespace(event_timestamp=late, price=D("101.00")),
             SimpleNamespace(event_timestamp=late, price=D("102.00")),  # same timestamp, later in tape
             SimpleNamespace(event_timestamp=late + timedelta(minutes=1), price=D("103.10")),  # off grid
             SimpleNamespace(event_timestamp=OPEN + timedelta(hours=7), price=D("90")))  # 15:00 CT, outside
    profile = build_tpo_profile(trades + extra, ES_PRICE_GRID, TD)
    t = study_window_terminal(trades + extra, profile, ES_PRICE_GRID)
    assert (t.price, t.timestamp_utc, t.period_label) == (D("102.00"), late, "B")


# --- exclusivity and ambiguity ------------------------------------------------------------------

def test_v1_policies_are_mutually_exclusive_over_generated_days():
    rng = random.Random(0)
    outcomes = set()
    for _ in range(400):
        ranges = []
        for _ in range(13):
            low = rng.randint(80, 120)
            ranges.append((low, low + rng.randint(0, 12)))
        _, day = _day(ranges, close=rng.randint(ranges[-1][0], ranges[-1][1]))
        assert len(day.matched) <= 1
        assert day.outcome is not ClassificationOutcome.AMBIGUOUS
        outcomes.add((day.outcome, day.primary))
    # The generator reaches every adopted type and the UNCLASSIFIED outcome.
    assert {p for _, p in outcomes} >= set(DayType) | {None}


def test_resolver_reports_ambiguous_without_forcing_a_winner():
    yes = CandidateResult.YES
    a = DayTypeCandidate(DayType.NORMAL_DAY, yes, None, ())
    b = DayTypeCandidate(DayType.NEUTRAL_DAY, yes, None, ())
    no = replace(a, result=CandidateResult.NO)
    assert resolve_candidates((a, b)) == (ClassificationOutcome.AMBIGUOUS, None, None)
    assert resolve_candidates((no,)) == (ClassificationOutcome.UNCLASSIFIED, None, None)
    assert resolve_candidates((no, b)) == (ClassificationOutcome.CANDIDATE, DayType.NEUTRAL_DAY, None)


def test_results_are_immutable_and_inputs_unchanged():
    trades = _trades([(100, 110)] * 2 + [(102, 108)] * 11)
    profile = build_tpo_profile(trades, ES_PRICE_GRID, TD)
    structure = build_profile_structure(profile)
    before = (profile, structure)
    facts = build_day_structure_facts(profile, structure, study_window_terminal(trades, profile, ES_PRICE_GRID))
    day = classify_day_type(facts, CLEAN)
    assert (profile, structure) == before and build_profile_structure(profile) == structure
    with pytest.raises(FrozenInstanceError):
        day.outcome = ClassificationOutcome.AMBIGUOUS  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        Condition("x", "y", "z", True).satisfied = False  # type: ignore[misc]
    assert classify_day_type(facts, CLEAN) == day  # deterministic


def test_no_initial_balance_reports_facts_without_ib_and_is_not_classified():
    # A, B empty; C..M 100-105
    f, day = _day([(None, None)] * 2 + [(100, 105)] * 11, close=104)
    assert (f.ib_range, f.directional_state, f.ib_share_of_range, f.periods_extending_above_ib) == (None, None, None, "")
    assert (f.profile_range, f.terminal.price) == (D(5), D(104))
    assert day.not_classified_reasons == ("no Initial Balance (no trades in the first 60 minutes)",
                                          "period(s) with no retained trades: AB")
