"""0Y-E: hand-verified DAY_STRUCTURE_STRENGTH_V1 facts beside the frozen DAY_TYPE_V1 label.

Same fixture convention as test_tpo_day_structure.py: every period's range
(A..M, 30-minute cash periods; IB = A+B) is listed in a comment and the expected
values were worked by hand. ES grid 0.25: 1 point = 4 ticks.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import FrozenInstanceError, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from dicks_laboratory import tpo_day_structure
from dicks_laboratory.tpo_day_strength import (
    DAY_STRUCTURE_STRENGTH_V1,
    DAY_TYPE_V1,
    DominantExtension,
    StrengthScope,
    build_day_structure_strength,
    max_consecutive_periods,
    strength_to_json,
)
from dicks_laboratory.tpo_day_structure import (
    ClassificationOutcome,
    DayType,
    Direction,
    DirectionalState,
    classification_quality,
    classify_day_type,
    build_day_structure_facts,
    study_window_terminal,
)
from dicks_laboratory.tpo_analysis import render_day_strength
from dicks_laboratory.tpo_profile import build_tpo_profile
from dicks_laboratory.tpo_structure import build_profile_structure
from dicks_laboratory.volume_profile import ES_PRICE_GRID

D = Decimal
INC = D("0.25")
TD = date(2026, 10, 6)
OPEN = datetime(2026, 10, 6, 13, 30, tzinfo=timezone.utc)
CLEAN = classification_quality(True, 0, "FINALIZED")
_REPO = Path(__file__).resolve().parents[3]
_EVIDENCE = _REPO / "docs/dicks_laboratory/evidence"
# sha256 of the accepted 0Y-C classifier module (fbbb095); DAY_TYPE_V1 is frozen.
_V1_CLASSIFIER_SHA256 = "8d745aab0e6b6bba3f6a2092e4e679e89a97a0629509d715522d5600e4cfef88"


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


def _strength(ranges, close=None, quality=CLEAN):
    trades = _trades(ranges, close)
    profile = build_tpo_profile(trades, ES_PRICE_GRID, TD)
    facts = build_day_structure_facts(profile, build_profile_structure(profile),
                                      study_window_terminal(trades, profile, ES_PRICE_GRID))
    day = classify_day_type(facts, quality)
    return day, build_day_structure_strength(day, INC)


IB = [(100, 110)] * 2  # IB 100-110 = 40 ticks


# --- extension asymmetry --------------------------------------------------------------------

def test_up_dominant_both_sides():
    # C 99-108 (4 ticks below); D 105-113; E 110-115 (20 ticks above); F..M 112-114; close 114 -> range 99-115
    day, s = _strength(IB + [(99, 108), (105, 113), (110, 115)] + [(112, 114)] * 8, close=114)
    assert (day.primary, s.directional_state, s.dominant_extension) == (
        DayType.NEUTRAL_DAY, DirectionalState.BOTH_SIDES, DominantExtension.UP)
    assert (s.extension_above_ticks, s.extension_below_ticks, s.ib_range_ticks) == (20, 4, 40)
    assert (s.extension_above_points, s.extension_below_points) == (D(5), D(1))
    assert (s.extension_above_per_ib, s.extension_below_per_ib) == (D("0.5"), D("0.1"))
    assert (s.dominant_extension_ticks, s.counter_extension_ticks) == (20, 4)
    assert (s.dominant_per_ib, s.counter_per_ib, s.counter_to_dominant) == (D("0.5"), D("0.1"), D("0.2"))
    assert s.dominant_share_of_total == D(20) / D(24)
    assert (s.new_high_periods, s.new_low_periods, s.max_consecutive_new_high_periods) == ("DE", "C", 2)
    assert s.terminal_percentile == D("0.9375")


def test_down_dominant_both_sides():
    # C 102-111 (4 ticks above); D 97-105; E 95-100 (20 ticks below); F..M 96-98; close 96 -> range 95-111
    day, s = _strength(IB + [(102, 111), (97, 105), (95, 100)] + [(96, 98)] * 8, close=96)
    assert (day.primary, s.dominant_extension) == (DayType.NEUTRAL_DAY, DominantExtension.DOWN)
    assert (s.dominant_extension_ticks, s.counter_extension_ticks, s.counter_to_dominant) == (20, 4, D("0.2"))
    assert (s.new_low_period_count, s.max_consecutive_new_low_periods) == (2, 2)
    assert (s.terminal_percentile, s.terminal_from_low_ticks, s.terminal_from_low_per_range) == (
        D("0.0625"), 4, D("0.0625"))


def test_equal_bilateral_extension_is_tie():
    # C 98-104; D 106-112; E..M 103-107 -> 8 ticks each side
    _, s = _strength(IB + [(98, 104), (106, 112)] + [(103, 107)] * 9)
    assert (s.dominant_extension, s.dominant_extension_ticks, s.counter_extension_ticks) == (DominantExtension.TIE, 8, 8)
    assert (s.counter_to_dominant, s.dominant_share_of_total) == (D(1), D("0.5"))


def test_one_sided_extension_has_zero_counter_not_undefined():
    # C 97-105; D..M 98-104; close 99 -> 12 ticks below only
    day, s = _strength(IB + [(97, 105)] + [(98, 104)] * 10, close=99)
    assert (day.primary, day.direction) == (DayType.NORMAL_VARIATION_DAY, Direction.DOWN)
    assert (s.dominant_extension, s.dominant_extension_ticks, s.counter_extension_ticks) == (DominantExtension.DOWN, 12, 0)
    assert (s.counter_per_ib, s.counter_to_dominant, s.dominant_share_of_total) == (D(0), D(0), D(1))
    assert (s.day_type, s.day_type_direction) == (DayType.NORMAL_VARIATION_DAY, Direction.DOWN)


def test_no_extension_leaves_dominant_ratios_undefined():
    # C..M 102-108 inside the IB; close 108
    day, s = _strength(IB + [(102, 108)] * 11, close=108)
    assert (day.primary, s.dominant_extension) == (DayType.NORMAL_DAY, DominantExtension.NONE)
    assert (s.dominant_extension_ticks, s.counter_extension_ticks, s.dominant_per_ib) == (0, 0, D(0))
    assert (s.counter_to_dominant, s.dominant_share_of_total) == (None, None)
    assert (s.new_high_period_count, s.new_low_period_count, s.first_extension_direction) == (0, 0, None)


def test_zero_ib_range_is_raw_facts_only_with_undefined_ib_ratios():
    # A,B 100 only; C..M 100-102 -> 8 ticks above a zero-width IB
    day, s = _strength([(100, 100)] * 2 + [(100, 102)] * 11)
    assert day.outcome is ClassificationOutcome.NOT_CLASSIFIED
    assert (s.ib_range_ticks, s.extension_above_ticks, s.dominant_extension) == (0, 8, DominantExtension.UP)
    assert (s.extension_above_per_ib, s.dominant_per_ib, s.counter_per_ib) == (None, None, None)
    assert s.counter_to_dominant == D(0)  # 0 / 8 is defined; only the IB denominators are zero
    assert s.scope is StrengthScope.RAW_FACTS_ONLY
    assert "IB range = 0: IB-relative policies undefined" in s.scope_reasons


def test_no_initial_balance_has_no_extension_facts():
    _, s = _strength([(None, None)] * 2 + [(100, 102)] * 11)
    assert (s.extension_above_ticks, s.dominant_extension, s.counter_to_dominant) == (None, None, None)
    assert s.scope is StrengthScope.RAW_FACTS_ONLY
    assert "Initial Balance:          not available" in "\n".join(render_day_strength(s))


# --- terminal location ----------------------------------------------------------------------

@pytest.mark.parametrize(("close", "pct", "from_high", "from_low"), [
    (110, D(1), 0, 40), (100, D(0), 40, 0), (105, D("0.5"), 20, 20)])
def test_terminal_location(close, pct, from_high, from_low):
    _, s = _strength(IB + [(102, 108)] * 11, close=close)
    assert (s.terminal_price, s.terminal_percentile) == (D(close), pct)
    assert (s.terminal_from_high_ticks, s.terminal_from_low_ticks) == (from_high, from_low)
    assert (s.terminal_from_high_per_range, s.terminal_from_low_per_range) == (D(from_high) / 40, D(from_low) / 40)


def test_zero_profile_range_terminal_ratios_undefined():
    _, s = _strength([(100, 100)] * 13, close=100)
    assert (s.terminal_percentile, s.terminal_from_high_per_range, s.terminal_from_low_per_range) == (None, None, None)
    assert (s.terminal_from_high_ticks, s.terminal_from_low_ticks) == (0, 0)


# --- directional persistence ----------------------------------------------------------------

def test_consecutive_new_high_periods():
    # A 100-104, B 101-105; C 104-108, D 107-111, E 110-114, F 113-117 (new highs CDEF);
    # G 112-116; H 116-119 (new high); I..M 115-118; close 118
    _, s = _strength([(100, 104), (101, 105), (104, 108), (107, 111), (110, 114), (113, 117), (112, 116),
                      (116, 119)] + [(115, 118)] * 5, close=118)
    assert (s.new_high_periods, s.new_high_period_count, s.max_consecutive_new_high_periods) == ("CDEFH", 5, 4)
    assert (s.new_low_period_count, s.max_consecutive_new_low_periods, s.counter_to_dominant) == (0, 0, D(0))
    assert s.longest_higher_low_run == 6  # A..F


def test_consecutive_new_low_periods():
    # mirror: B 115-119; C 111-115, D 108-112, E 105-109 (new lows CDE); F 106-110; G 102-106 (new low)
    _, s = _strength([(116, 120), (115, 119), (111, 115), (108, 112), (105, 109), (106, 110), (102, 106)]
                     + [(103, 107)] * 6, close=103)
    assert (s.new_low_periods, s.max_consecutive_new_low_periods, s.longest_lower_high_run) == ("CDEG", 3, 5)


def test_max_consecutive_periods_helper():
    assert [max_consecutive_periods(x) for x in ("", "C", "CEG", "DEFH", "HFED", "KLM")] == [0, 1, 1, 3, 3, 3]


# --- quality ----------------------------------------------------------------------------------

def test_quality_qualified_scope_keeps_reasons():
    _, s = _strength(IB + [(102, 108)] * 11, quality=classification_quality(True, 2, "FINALIZED"))
    assert s.scope is StrengthScope.QUALITY_QUALIFIED and s.day_type is DayType.NORMAL_DAY
    assert s.scope_reasons == ("gap evidence (KNOWN/SUSPECTED) overlaps the study window: 2",)
    assert "*** STRENGTH FACTS ARE QUALITY-QUALIFIED ***" in "\n".join(render_day_strength(s))


def test_not_classified_partial_window_is_never_a_full_day_assessment():
    ranges = [(100, 104), (101, 105), (104, 108), (107, 111), (110, 114), (113, 117)] + [(115, 118)] * 5
    day, s = _strength(ranges + [(None, None)] * 2, quality=classification_quality(False, 0, "FINALIZED"))
    assert (s.day_type_outcome, s.day_type, s.scope) == (
        ClassificationOutcome.NOT_CLASSIFIED, None, StrengthScope.RAW_FACTS_ONLY)
    assert s.scope_reasons == day.not_classified_reasons
    assert "STUDY WINDOW NOT FULLY CAPTURED" in s.scope_reasons and "period(s) with no retained trades: LM" in s.scope_reasons
    assert s.new_high_periods == "CDEFG"  # raw facts still exposed
    text = "\n".join(render_day_strength(s))
    assert "*** RAW FACTS ONLY -- NOT A FULL-DAY STRENGTH ASSESSMENT ***" in text
    assert "V1 day type:              NOT_CLASSIFIED" in text


def test_full_clean_day_scope():
    _, s = _strength(IB + [(102, 108)] * 11, close=108)
    assert (s.scope, s.scope_reasons) == (StrengthScope.FULL_STUDY_WINDOW, ())


# --- policy versioning ------------------------------------------------------------------------

def test_policy_ids_are_explicit_and_v1_classifier_is_frozen():
    day, s = _strength(IB + [(102, 108)] * 11, close=108)
    assert (s.policy_id, s.day_type_policy) == (DAY_STRUCTURE_STRENGTH_V1, DAY_TYPE_V1)
    assert (day.policy_id, day.policy_version) == ("DICKS_LAB_DAY_TYPE_POLICY", "V1_DIRECTIONAL_STATE_X_IB_SHARE")
    assert (day.normal_min_ib_share, day.normal_variation_min_ib_share, day.trend_min_new_extreme_periods) == (
        D("0.85"), D("0.50"), 2)
    source = Path(tpo_day_structure.__file__).read_bytes()
    assert hashlib.sha256(source).hexdigest() == _V1_CLASSIFIER_SHA256, (
        "DAY_TYPE_V1 is frozen: a policy change needs a new policy ID beside V1, not an edit of V1")


def test_unknown_day_type_policy_is_refused():
    day, _ = _strength(IB + [(102, 108)] * 11)
    with pytest.raises(ValueError, match="unknown day-type policy"):
        build_day_structure_strength(replace(day, policy_version="V2_SOMETHING"), INC)


def test_strength_never_alters_the_classification():
    day, s = _strength(IB + [(99, 108), (105, 113), (110, 115)] + [(112, 114)] * 8, close=114)
    before = replace(day)
    build_day_structure_strength(day, INC)
    assert day == before and day.primary is DayType.NEUTRAL_DAY
    with pytest.raises(FrozenInstanceError):
        s.counter_to_dominant = D(0)  # type: ignore[misc]


# --- output ---------------------------------------------------------------------------------

def test_render_is_numeric_and_carries_both_policy_ids():
    _, s = _strength(IB + [(99, 108), (105, 113), (110, 115)] + [(112, 114)] * 8, close=114)
    text = "\n".join(render_day_strength(s))
    for needle in ("DAY STRUCTURE STRENGTH:", "V1 day type:              NEUTRAL_DAY", "Dominant extension:       UP",
                   "Counter / dominant:       0.2000", "Terminal percentile:      0.9375",
                   "    DAY_TYPE_V1\n    DAY_STRUCTURE_STRENGTH_V1"):
        assert needle in text, needle
    lowered = text.lower().replace("not a trading conclusion", "")
    for word in ("bullish", "bearish", "strong", "weak", "likely", "continuation", "buyer", "seller", "score ="):
        assert word not in lowered, word


def test_json_is_deterministic_and_exact():
    _, s = _strength(IB + [(99, 108), (105, 113), (110, 115)] + [(112, 114)] * 8, close=114)
    line = strength_to_json(s)
    data = json.loads(line)
    assert line == strength_to_json(s)
    assert (data["counter_to_dominant"], data["dominant_extension"], data["policy_id"]) == (
        "0.2", "UP", DAY_STRUCTURE_STRENGTH_V1)


# --- frozen 0Y-D evidence: 2026-09-30 ------------------------------------------------------

def test_sep30_strength_matches_frozen_0yd_record():
    frozen = [json.loads(x) for x in (_EVIDENCE / "0Y-D/blind_run/records.jsonl").read_text().splitlines()]
    derived = [json.loads(x) for x in (_EVIDENCE / "0Y-E/strength_run/strength_records.jsonl").read_text().splitlines()]
    record = next(r for r in frozen if r["trading_date"] == "2026-09-30")
    s = next(d for d in derived if d["dataset_id"] == record["dataset_id"])["strength"]
    assert (record["day_type"], record["directional_state"]) == ("NEUTRAL_DAY", "BOTH_SIDES")
    assert (s["day_type"], s["day_type_policy"], s["scope"]) == ("NEUTRAL_DAY", DAY_TYPE_V1, "FULL_STUDY_WINDOW")
    assert (s["extension_above_ticks"], s["extension_below_ticks"]) == (
        record["ext_above_ticks"], record["ext_below_ticks"]) == (10, 155)
    assert (s["dominant_extension"], s["dominant_extension_ticks"], s["counter_extension_ticks"]) == ("DOWN", 155, 10)
    assert D(s["counter_to_dominant"]) == D(10) / D(155)
    assert (s["terminal_percentile"], s["new_high_periods"], s["new_low_periods"]) == (
        record["terminal_pct"], record["new_high_periods"], record["new_low_periods"])
    assert D(s["terminal_percentile"]).quantize(D("0.0001")) == D("0.0515")
