"""0Y-H: hand-built fixtures for the OPENING_TYPE_V1 candidate policy.

Cash rows are (seconds after 08:30:00 CT, price); the open print is at +0 s, so the grace
instant is +60 s and period A ends at +1800 s. Overnight rows are (seconds after 17:00 CT,
price). ES grid 0.25: 1 point = 4 ticks. Trading date Tue 2026-10-06 (CDT). Prior day (unless
stated): range 90-110, value 95-105, POC 100, terminal 99. Default overnight: ONL 100, ONH 106.
Every expected value was worked by hand.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid5

import pytest

from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import DxLinkTimeAndSaleProvenance
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, opening_type_classification, render_tpo_report
from dicks_laboratory.tpo_day_structure import QualityGrade, build_day_structure_facts, study_window_terminal
from dicks_laboratory.tpo_opening import (
    ContextOutcome,
    OpeningQualityGrade,
    PriorContext,
    RangeLocation,
    Side,
    build_cash_open_session,
    build_opening_auction_facts,
    cash_open_utc,
)
from dicks_laboratory.tpo_opening_path import build_opening_path_facts
from dicks_laboratory.tpo_opening_type import (
    OPENING_TYPE_GRACE,
    OPENING_TYPE_POLICY_ID,
    OPENING_TYPE_POLICY_VERSION,
    POLICY_CONSTANTS,
    CandidateResult,
    ClassificationStatus,
    ConditionStatus,
    OpeningTypeName,
    classify_opening_type,
    render_opening_types,
)
from dicks_laboratory.tpo_opening_type_record import (
    OPENING_TYPE_V1_POLICY_DOC,
    OPENING_TYPE_V1_POLICY_DOC_SHA256,
    OPENING_TYPE_V1_SOURCE_SHA256,
    Cohort,
    build_record,
    cohort_for,
    policy_source_sha256,
    render_audit,
)
from dicks_laboratory.tpo_overnight import (
    OvernightQualityGrade,
    build_overnight_context,
    build_overnight_session,
    overnight_window_utc,
)
from dicks_laboratory.tpo_profile import build_tpo_profile
from dicks_laboratory.tpo_structure import build_profile_structure
from dicks_laboratory.volume_profile import ES_PRICE_GRID

D = Decimal
TD = date(2026, 10, 6)
OPEN = cash_open_utc(TD)
ON_START = datetime(2026, 10, 5, 22, 0, tzinfo=timezone.utc)
ESZ6 = "FUTURE:CME:ES:2026-12"
REPO = Path(__file__).resolve().parents[3]
T = OpeningTypeName
DRIVE, OAIR, OAOR, OA, OTD, ORR = (T.OPEN_DRIVE, T.OPEN_AUCTION_IN_RANGE, T.OPEN_AUCTION_OUT_OF_RANGE, T.OPEN_AUCTION,
                                   T.OPEN_TEST_DRIVE, T.OPEN_REJECTION_REVERSE)


def _at(seconds):
    return OPEN + timedelta(seconds=seconds)


def _on(rows, started=ON_START):
    trades = tuple(SimpleNamespace(event_timestamp=ON_START + timedelta(seconds=s), price=D(str(p)), size=D(1))
                   for s, p in rows)
    return build_overnight_session(trades, ES_PRICE_GRID, TD, ESZ6, started, OPEN + timedelta(hours=8), (),
                                   "FINALIZED")


def _cash(rows, gaps=(), period_minutes=30):
    trades = tuple(SimpleNamespace(event_timestamp=_at(s), price=D(str(p))) for s, p in rows)
    profile = build_tpo_profile(trades, ES_PRICE_GRID, TD, period_minutes)
    facts = build_day_structure_facts(profile, build_profile_structure(profile),
                                      study_window_terminal(trades, profile, ES_PRICE_GRID))
    return build_cash_open_session(trades, profile, facts, ES_PRICE_GRID, ON_START - timedelta(minutes=1),
                                   OPEN + timedelta(hours=8), gaps, "FINALIZED")


def _prior(outcome=ContextOutcome.AVAILABLE, quality=QualityGrade.UNQUALIFIED, reasons=()):
    return PriorContext(outcome, reasons, date(2026, 10, 5), ESZ6, prior_trading_date=date(2026, 10, 5),
                        prior_dataset_id="prior", prior_contract=ESZ6, same_contract=True,
                        profile_high=D(110), profile_low=D(90), poc=D(100), value_area_high=D(105),
                        value_area_low=D(95), ib_high=D(104), ib_low=D(96), terminal_price=D(99),
                        quality_grade=quality)


def _classify(cash_rows, on_rows=((0, 100), (10, 106)), prior=None, on_started=ON_START, cash_gaps=(),
              overnight=True):
    opening = build_opening_auction_facts(_cash(cash_rows, cash_gaps), prior or _prior())
    ctx = (build_overnight_context(_on(on_rows, on_started), opening.session, opening.prior) if overnight else None)
    return classify_opening_type(build_opening_path_facts(opening, ctx))


def _statuses(cand):
    return [c.status for c in cand.conditions]


S, N, E = ConditionStatus.SATISFIED, ConditionStatus.NOT_SATISFIED, ConditionStatus.NOT_EVALUABLE


# --- policy identity -------------------------------------------------------------------------------

def test_policy_identity_and_constants():
    assert OPENING_TYPE_POLICY_ID == "OPENING_TYPE_V1"
    assert OPENING_TYPE_POLICY_VERSION == "V1_A_PERIOD_60S_GRACE_EXACT_REFERENCE_TEST_PRIOR_RANGE_ANCHOR"
    consts = dict(POLICY_CONSTANTS)
    assert (consts["grace_seconds"], consts["grace_anchor"], consts["horizon"], consts["horizon_minutes"]) == (
        "60", "CASH_OPEN_PRINT", "PERIOD_A", "30")
    assert (consts["reference_touch_policy"], consts["open_auction_location_anchor"]) == ("EXACT", "PRIOR_RANGE")
    assert consts["test_drive_references"] == ("PRIOR_HIGH,PRIOR_VAH,PRIOR_POC,PRIOR_VAL,PRIOR_LOW,OVERNIGHT_HIGH,"
                                               "OVERNIGHT_LOW")
    assert consts["in_range_locations"] == "INSIDE_PRIOR_RANGE,AT_PRIOR_HIGH,AT_PRIOR_LOW"
    assert consts["open_rejection_reverse"] == "DEFERRED:REFERENCE_DEFINITION_CONFLICT"
    assert OPENING_TYPE_GRACE == timedelta(seconds=60)


def test_policy_source_and_document_are_frozen():
    """OPENING_TYPE_V1 is frozen for prospective validation: any change needs OPENING_TYPE_V2."""
    assert OPENING_TYPE_V1_SOURCE_SHA256 != "PENDING_FREEZE"
    assert policy_source_sha256() == OPENING_TYPE_V1_SOURCE_SHA256
    doc = (REPO / OPENING_TYPE_V1_POLICY_DOC).read_bytes()
    assert hashlib.sha256(doc).hexdigest() == OPENING_TYPE_V1_POLICY_DOC_SHA256


# --- Open Drive ------------------------------------------------------------------------------------

def test_clean_open_drive_up_with_cross_before_grace():
    c = _classify([(0, 102), (0.2, 102.25), (0.5, 101.75), (30, 102.5), (120, 103), (1700, 104), (3600, 99)])
    assert c.status is ClassificationStatus.CLASSIFIED and c.reasons == ()
    d = c.candidate(DRIVE)
    assert (d.result, d.direction, d.quality, _statuses(d)) == (CandidateResult.CANDIDATE, Side.UP,
                                                                OpeningQualityGrade.UNQUALIFIED, [S, S, S])
    obs = d.evidence
    assert (obs.instant_utc, obs.price, obs.offset_ticks, obs.side, obs.held_side) == (_at(60), D("102.5"), 2, Side.UP,
                                                                                       Side.UP)
    assert (obs.open_cross_count, obs.first_below_after_utc, obs.max_up_ticks, obs.max_down_ticks) == (0, None, 8, 0)
    assert (obs.a_high, obs.a_low, obs.a_terminal_price, obs.a_terminal_side, obs.horizon_end_utc) == (
        D(104), D("101.75"), D(104), Side.UP, _at(1800))
    assert c.facts.scale(60).open_cross_count == 2  # the pre-grace crosses are still reported as facts
    assert c.matched_types == (DRIVE,)


def test_clean_open_drive_down():
    c = _classify([(0, 102), (10, 101.5), (90, 101), (1790, 100.5)])
    d = c.candidate(DRIVE)
    assert (d.result, d.direction) == (CandidateResult.CANDIDATE, Side.DOWN)
    assert (d.evidence.price, d.evidence.offset_ticks, d.evidence.a_terminal_offset_ticks) == (D("101.5"), -2, -6)
    assert c.matched_types == (DRIVE,)


def test_cross_after_grace_is_not_a_drive_and_post_grace_rotation_is_an_auction():
    c = _classify([(0, 102), (10, 102.5), (300, 101.5), (600, 102.5)])
    d = c.candidate(DRIVE)
    assert (d.result, d.direction, _statuses(d)) == (CandidateResult.NOT_CANDIDATE, None, [S, N, S])
    assert d.conditions[1].detail == ("first cross 13:35:00.000Z; 2 post-grace crosses, last 13:40:00.000Z")
    ir = c.candidate(OAIR)
    assert (ir.result, ir.direction, _statuses(ir), ir.quality) == (CandidateResult.CANDIDATE, None, [S, S, S],
                                                                    OpeningQualityGrade.UNQUALIFIED)
    assert (ir.evidence.open_cross_count, ir.evidence.first_open_cross_utc, ir.evidence.last_open_cross_utc) == (
        2, _at(300), _at(600))
    assert c.candidate(OAOR).result is CandidateResult.NOT_CANDIDATE
    assert _statuses(c.candidate(OAOR)) == [S, S, N]
    assert c.candidate(OA).result is CandidateResult.NOT_APPLICABLE
    assert c.matched_types == (OAIR,)


def test_at_open_at_grace_is_not_a_drive_and_no_candidate_matches():
    c = _classify([(0, 102), (10, 102.5), (50, 102), (200, 102.5), (1700, 103)])
    d = c.candidate(DRIVE)
    assert (d.result, _statuses(d)) == (CandidateResult.NOT_CANDIDATE, [N, E, E])
    assert d.conditions[0].detail == "price at 13:31:00.000Z = 102.00 (+0 ticks): exactly at the open"
    assert (d.evidence.side, d.evidence.held_side) == (Side.NONE, Side.UP)
    assert _statuses(c.candidate(OAIR)) == [N, N, S]
    assert c.candidate(OTD).result is CandidateResult.NOT_CANDIDATE
    assert c.status is ClassificationStatus.CLASSIFIED and c.matched == ()


def test_rotation_only_before_grace_is_not_an_open_auction():
    c = _classify([(0, 102), (5, 102.5), (10, 101.5), (20, 102.5), (30, 101.5), (40, 102.5), (300, 103), (1700, 103.5)])
    assert c.facts.scale(60).open_cross_count == 4
    ir = c.candidate(OAIR)
    assert (ir.result, _statuses(ir)) == (CandidateResult.NOT_CANDIDATE, [N, N, S])
    assert (ir.evidence.traded_below_after, ir.evidence.open_cross_count) == (False, 0)
    assert c.matched_types == (DRIVE,) and c.candidate(DRIVE).direction is Side.UP


# --- Open Auction in / out of range ------------------------------------------------------------------

def test_oaor_above_prior_range():
    c = _classify([(0, 112), (10, 112.5), (300, 111.5), (600, 112.5)])
    assert c.facts.opening.range_location is RangeLocation.ABOVE_PRIOR_RANGE
    assert c.candidate(OAOR).result is CandidateResult.CANDIDATE
    assert c.candidate(OAOR).conditions[2].detail == ("open 112.00 ABOVE_PRIOR_RANGE (prior range 90-110; open - high "
                                                      "8 ticks, open - low 88 ticks)")
    assert c.candidate(OAIR).result is CandidateResult.NOT_CANDIDATE
    assert c.matched_types == (OAOR,)


def test_oaor_below_prior_range():
    c = _classify([(0, 88), (10, 87.5), (300, 88.5), (600, 87.5)])
    assert c.facts.opening.range_location is RangeLocation.BELOW_PRIOR_RANGE
    assert c.matched_types == (OAOR,)


def test_open_at_prior_high_is_in_range():
    c = _classify([(0, 110), (10, 110.5), (300, 109.5), (600, 110.5)])
    assert c.facts.opening.range_location is RangeLocation.AT_PRIOR_HIGH
    assert c.matched_types == (OAIR,)
    # the prior high is at the open tick: it cannot be a Test Drive probe reference
    assert c.facts.encounter("PRIOR_HIGH").side_of_open is Side.NONE
    assert c.candidate(OTD).evidence.reference is None


# --- Open Test Drive ---------------------------------------------------------------------------------

VAH_TEST = [(0, 102), (10, 103), (100, 105), (200, 103), (400, 101.5), (1700, 101.75)]


def test_prior_vah_touch_then_open_cross_then_opposite_expansion_and_multiple_candidates():
    c = _classify(VAH_TEST)
    td = c.candidate(OTD)
    assert (td.result, td.direction, _statuses(td), td.quality) == (CandidateResult.CANDIDATE, Side.DOWN, [S, S, S, S],
                                                                    OpeningQualityGrade.UNQUALIFIED)
    ev = td.evidence
    assert (ev.reference, ev.reference_source, ev.reference_price, ev.reached_utc, ev.exact_touch_utc) == (
        "PRIOR_VAH", "PRIOR_DAY", D(105), _at(100), _at(100))
    assert (ev.reach_beyond_ticks, ev.probe_side, ev.open_to_reference_ticks, ev.open_to_reference_points) == (
        0, Side.UP, 12, D(3))
    assert (ev.open_cross_after_reach_utc, ev.reach_to_cross) == (_at(400), timedelta(seconds=300))
    assert (ev.opposite_excursion_after_cross_ticks, ev.opposite_excursion_after_cross_points) == (2, D("0.5"))
    assert (ev.a_terminal_offset_ticks, ev.a_terminal_side, ev.other_references_reached) == (-1, Side.DOWN, ())
    # a candidate SET: the post-grace rotation also matches OAIR; no precedence, no primary type
    assert c.matched_types == (OAIR, OTD)
    assert not hasattr(c, "primary_opening_type")
    d = c.candidate(DRIVE)
    assert _statuses(d) == [S, N, N]


def test_prior_low_touch_then_cross_up():
    c = _classify([(0, 92), (10, 91), (100, 90), (200, 91.5), (400, 92.5), (1700, 93)])
    td = c.candidate(OTD)
    assert (td.result, td.direction, td.evidence.reference, td.evidence.probe_side) == (
        CandidateResult.CANDIDATE, Side.UP, "PRIOR_LOW", Side.DOWN)
    assert (td.evidence.open_to_reference_ticks, td.evidence.reach_to_cross,
            td.evidence.opposite_excursion_after_cross_ticks) == (-8, timedelta(seconds=300), 4)


def test_onh_touch_then_cross_down():
    c = _classify([(0, 102), (10, 102.5), (100, 103), (200, 102.5), (400, 101.5), (1700, 101.75)],
                  on_rows=((0, 100), (10, 103)))
    td = c.candidate(OTD)
    assert (td.result, td.direction, td.evidence.reference, td.evidence.reference_source, td.quality) == (
        CandidateResult.CANDIDATE, Side.DOWN, "OVERNIGHT_HIGH", "OVERNIGHT", OpeningQualityGrade.UNQUALIFIED)


def test_onl_touch_then_cross_up():
    c = _classify([(0, 102), (10, 101.5), (100, 101), (200, 101.5), (400, 102.5), (1700, 102.25)],
                  on_rows=((0, 101), (10, 104)))
    td = c.candidate(OTD)
    assert (td.result, td.direction, td.evidence.reference, td.evidence.reached_utc) == (
        CandidateResult.CANDIDATE, Side.UP, "OVERNIGHT_LOW", _at(100))
    assert c.matched_types == (OAIR, OTD)


def test_reference_touch_without_open_cross():
    c = _classify([(0, 102), (10, 103), (100, 105), (200, 104), (1700, 103)])
    td = c.candidate(OTD)
    assert (td.result, _statuses(td)) == (CandidateResult.NOT_CANDIDATE, [S, S, N, E])
    assert td.conditions[2].detail == "no open cross before the end of A"
    assert c.matched_types == (DRIVE,)


def test_open_cross_before_reference_touch_does_not_count():
    c = _classify([(0, 102), (10, 101.5), (300, 103), (600, 105), (700, 104), (1700, 103.5), (2000, 101)])
    td = c.candidate(OTD)
    assert (td.result, _statuses(td), td.evidence.reference, td.evidence.reached_utc) == (
        CandidateResult.NOT_CANDIDATE, [S, S, N, E], "PRIOR_VAH", _at(600))
    assert td.conditions[2].detail == "no open cross before the end of A (first cross after A at 14:03:20.000Z)"


def test_near_reference_without_exact_touch_is_not_a_test():
    c = _classify([(0, 102), (10, 103), (100, 104.75), (200, 103), (400, 101.5), (1700, 101.75)])
    td = c.candidate(OTD)
    assert (td.result, _statuses(td)) == (CandidateResult.NOT_CANDIDATE, [N, E, E, E])
    assert (td.evidence.minimum_reference_distance_ticks, td.evidence.minimum_reference_distance_reference) == (
        1, "PRIOR_VAH")
    assert "PRIOR_VAH 1" in td.conditions[0].detail


def test_reference_touched_after_a_is_not_a_test():
    c = _classify([(0, 102), (10, 103), (1700, 104), (1900, 105), (2000, 101)])
    td = c.candidate(OTD)
    assert (td.result, td.conditions[0].status, td.evidence.reference) == (CandidateResult.NOT_CANDIDATE, N, None)


def test_first_reference_reached_is_the_probe_and_others_are_listed():
    # POC 100 (8 ticks below) is reached first, then ONL 99.5; the later cross up is after both
    c = _classify([(0, 102), (10, 101), (100, 100), (150, 99.5), (400, 102.5), (1700, 102.25)],
                  on_rows=((0, 99.5), (10, 104)))
    td = c.candidate(OTD)
    assert (td.result, td.direction, td.evidence.reference) == (CandidateResult.CANDIDATE, Side.UP, "PRIOR_POC")
    assert td.evidence.other_references_reached == (("OVERNIGHT_LOW", _at(150)),)


def test_test_drive_cross_before_grace_can_coexist_with_open_drive():
    c = _classify([(0, 102), (5, 102.5), (20, 101.5), (100, 101), (1700, 100.75)], on_rows=((0, 100), (10, 102.5)))
    td, d = c.candidate(OTD), c.candidate(DRIVE)
    assert (td.direction, td.evidence.reference, td.evidence.open_cross_after_reach_utc) == (Side.DOWN, "OVERNIGHT_HIGH",
                                                                                          _at(20))
    assert (d.direction, c.matched_types) == (Side.DOWN, (DRIVE, OTD))


# --- dependency-aware quality ------------------------------------------------------------------------

def test_overnight_reference_test_drive_is_quality_qualified_but_oair_is_not():
    late = ON_START + timedelta(seconds=0.0002)
    c = _classify([(0, 102), (10, 102.5), (100, 103), (200, 102.5), (400, 101.5), (1700, 101.75)],
                  on_rows=((1, 100), (10, 103)), on_started=late)
    assert c.quality.overnight is OvernightQualityGrade.QUALITY_QUALIFIED
    td, ir, d = c.candidate(OTD), c.candidate(OAIR), c.candidate(DRIVE)
    assert (td.result, td.quality) == (CandidateResult.CANDIDATE, OpeningQualityGrade.QUALITY_QUALIFIED)
    assert td.quality_reasons == ("overnight: capture began 0:00:00.000200 after 17:00 CT (overnight window starts "
                                  "late)",)
    assert (ir.result, ir.quality, ir.quality_reasons) == (CandidateResult.CANDIDATE, OpeningQualityGrade.UNQUALIFIED,
                                                           ())
    assert d.quality is OpeningQualityGrade.UNQUALIFIED


def test_prior_reference_test_drive_is_not_contaminated_by_qualified_overnight():
    c = _classify(VAH_TEST, on_started=ON_START + timedelta(seconds=0.0002))
    assert c.quality.overnight is OvernightQualityGrade.QUALITY_QUALIFIED
    td = c.candidate(OTD)
    assert (td.result, td.evidence.reference, td.quality, td.quality_reasons) == (
        CandidateResult.CANDIDATE, "PRIOR_VAH", OpeningQualityGrade.UNQUALIFIED, ())


def test_qualified_prior_day_qualifies_prior_dependent_candidates_only():
    prior = _prior(quality=QualityGrade.QUALITY_QUALIFIED, reasons=("prior quality-qualified: KNOWN_GAP 1",))
    c = _classify(VAH_TEST, prior=prior)
    for name in (OAIR, OTD):
        cand = c.candidate(name)
        assert (cand.result, cand.quality) == (CandidateResult.CANDIDATE, OpeningQualityGrade.QUALITY_QUALIFIED)
        assert cand.quality_reasons == ("prior day QUALITY_QUALIFIED: prior quality-qualified: KNOWN_GAP 1",)
    assert c.candidate(DRIVE).quality is OpeningQualityGrade.UNQUALIFIED


def test_qualified_current_open_qualifies_every_candidate():
    c = _classify(VAH_TEST, cash_gaps=(("KNOWN_GAP", _at(3000), _at(3100)),))
    assert c.quality.current_open is OpeningQualityGrade.QUALITY_QUALIFIED
    assert all(m.quality is OpeningQualityGrade.QUALITY_QUALIFIED for m in c.matched) and len(c.matched) == 2
    assert c.candidate(OTD).quality_reasons == ("current open: KNOWN_GAP overlaps the opening window: 1",)


# --- missing context ----------------------------------------------------------------------------------

def test_missing_prior_context_gives_generic_open_auction():
    c = _classify([(0, 102), (10, 102.5), (300, 101.5), (600, 102.5)], prior=_prior(ContextOutcome.NO_PRIOR_PROFILE))
    for name in (OAIR, OAOR):
        cand = c.candidate(name)
        assert (cand.result, _statuses(cand)) == (CandidateResult.NOT_CLASSIFIED, [S, S, E])
        assert cand.reasons == ("IN_RANGE / OUT_OF_RANGE: NOT_CLASSIFIED -- prior context NO_PRIOR_PROFILE; "
                                "no prior range",)
    oa = c.candidate(OA)
    assert (oa.result, _statuses(oa)) == (CandidateResult.CANDIDATE, [S, S, S])
    td = c.candidate(OTD)  # only the overnight references remain
    assert (td.result, td.evidence.minimum_reference_distance_reference) == (CandidateResult.NOT_CANDIDATE,
                                                                             "OVERNIGHT_LOW")
    assert c.matched_types == (OA,)
    assert c.strength.range_location is None


def test_no_reference_at_all_leaves_test_drive_not_classified():
    c = _classify([(0, 102), (10, 102.5), (300, 101.5), (600, 102.5)], prior=_prior(ContextOutcome.NO_PRIOR_PROFILE),
                  overnight=False)
    td = c.candidate(OTD)
    assert (td.result, td.reasons) == (CandidateResult.NOT_CLASSIFIED,
                                       ("no qualifying reference: prior context NO_PRIOR_PROFILE; overnight NOT_BUILT",))
    assert c.status is ClassificationStatus.CLASSIFIED and c.matched_types == (OA,)


def test_missing_opening_coverage_is_not_classified():
    c = _classify([(120, 102), (200, 103)])
    assert c.status is ClassificationStatus.NOT_CLASSIFIED and c.strength is None and c.matched == ()
    assert c.reasons[0].startswith("opening facts NOT_AVAILABLE: first eligible trade 0:02:00 after 08:30:00 CT")
    assert [x.result for x in c.candidates] == [CandidateResult.NOT_CLASSIFIED] * 5 + [CandidateResult.DEFERRED]
    assert "  OPENING TYPE: NOT_CLASSIFIED" in render_opening_types(c)


def test_period_a_must_be_thirty_minutes():
    trades_rows = [(0, 102), (10, 102.5), (300, 101.5)]
    opening = build_opening_auction_facts(_cash(trades_rows, period_minutes=15), _prior())
    c = classify_opening_type(build_opening_path_facts(opening, None))
    assert c.status is ClassificationStatus.NOT_CLASSIFIED
    assert c.reasons == ("period A is not 30 minutes (V1 is defined on 30-minute A)",)


def test_open_rejection_reverse_is_always_deferred():
    for c in (_classify(VAH_TEST), _classify([(120, 102)])):
        orr = c.candidate(ORR)
        assert (orr.result, orr.conditions, orr.direction) == (CandidateResult.DEFERRED, (), None)
        assert orr.reasons[0].startswith("REFERENCE_DEFINITION_CONFLICT")


# --- Globex boundary ---------------------------------------------------------------------------------

def test_globex_open_needs_a_recorded_on_time_capture_start():
    trades = (SimpleNamespace(event_timestamp=ON_START + timedelta(seconds=1), price=D(100), size=D(1)),)
    unknown = build_overnight_session(trades, ES_PRICE_GRID, TD, ESZ6, None, OPEN, (), "FINALIZED")
    assert (unknown.globex_open_price, unknown.first_price, unknown.globex_open_boundary_proven) == (None, D(100), False)
    assert unknown.globex_open_unavailable_reason == ("capture start not recorded; exact Globex-open boundary coverage "
                                                      "not proven")
    assert unknown.quality.grade is OvernightQualityGrade.QUALITY_QUALIFIED
    late = build_overnight_session(trades, ES_PRICE_GRID, TD, ESZ6, ON_START + timedelta(microseconds=180), OPEN, (),
                                   "FINALIZED")
    assert (late.globex_open_price, late.globex_open_boundary_proven, late.high) == (None, False, D(100))
    exact = build_overnight_session(trades, ES_PRICE_GRID, TD, ESZ6, ON_START, OPEN, (), "FINALIZED")
    assert (exact.globex_open_price, exact.globex_open_boundary_proven) == (D(100), True)


# --- output, immutability, records ---------------------------------------------------------------------

FORBIDDEN = ("bullish", "bearish", "fade", "buy", "sell", "continuation", "high confidence", "high-confidence",
             "probability", "setup", "strong", "weak", "primary_opening_type", "accepted", "rejected", "initiative",
             "responsive")


def test_render_explains_every_candidate_without_interpretation():
    text = "\n".join(render_opening_types(_classify(VAH_TEST)))
    for needle in ("OPENING-TYPE CANDIDATES:", "Policy: OPENING_TYPE_V1 (V1_A_PERIOD_60S_GRACE_EXACT_REFERENCE_TEST",
                   "Pre-registered Laboratory candidate policy, not an industry-standard mechanical definition.",
                   "Matched candidates: OPEN_AUCTION_IN_RANGE, OPEN_TEST_DRIVE DOWN   (2 matched; candidate set -- no "
                   "primary type)",
                   "[satisfied]     an exact qualifying reference is reached during A",
                   "[NOT satisfied] no later trade on the other side of the open through the end of A",
                   "Result: CANDIDATE DOWN   quality UNQUALIFIED", "Result: NOT_APPLICABLE",
                   "DEFERRED -- REFERENCE_DEFINITION_CONFLICT", "Continuous facts beside every candidate",
                   "A/B overlap", "open vs overnight: INSIDE_OVERNIGHT_RANGE"):
        assert needle in text, needle
    lowered = text.lower()
    for word in FORBIDDEN:
        assert word not in lowered, word


def test_classification_is_immutable():
    c = _classify(VAH_TEST)
    with pytest.raises(FrozenInstanceError):
        c.candidates = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        c.candidate(OTD).conditions[0].status = S  # type: ignore[misc]


def test_record_is_json_and_cohorts_are_explicit():
    c = _classify(VAH_TEST)
    rec = build_record(TD, "0e5a0000-0000-4000-8000-000000000001", ESZ6, "ab" * 32, c)
    text = json.dumps(rec, sort_keys=True)
    assert json.loads(text) == rec
    assert (rec["cohort"], rec["policy_id"], rec["policy_source_sha256"]) == ("DEVELOPMENT", "OPENING_TYPE_V1",
                                                                             OPENING_TYPE_V1_SOURCE_SHA256)
    assert rec["classification"]["candidates"][4]["evidence"]["reference"] == "PRIOR_VAH"
    assert "path" not in rec["opening_auction_facts"]["session"]
    assert rec["opening_auction_facts"]["session"]["cash_open"]["price"] == "102.00"
    assert set(rec["fact_source_sha256"]) == {"tpo_opening.py", "tpo_opening_path.py", "tpo_overnight.py"}
    assert cohort_for(date(2026, 10, 9), OPENING_TYPE_V1_SOURCE_SHA256) is Cohort.DEVELOPMENT
    assert cohort_for(date(2026, 10, 12), OPENING_TYPE_V1_SOURCE_SHA256) is Cohort.VALIDATION
    assert cohort_for(date(2026, 10, 12), "0" * 64) is Cohort.POLICY_MODIFIED
    audit = render_audit([rec], "t")
    assert "## Counts — DEVELOPMENT (NOT VALIDATION)" in audit
    assert "| 2026-10-06 | 0e5a0000 | DEVELOPMENT | UNQUALIFIED | AVAILABLE / UNQUALIFIED | AVAILABLE | " in audit
    assert "| no | YES | no | -- | YES DOWN | PRIOR_VAH | 2 | -- |" in audit
    assert "| overlap OPEN_AUCTION_IN_RANGE + OPEN_TEST_DRIVE | 1 |" in audit


# --- datasets and CLI ----------------------------------------------------------------------------------

_NS = UUID("0e5a0000-0000-4000-8000-0000000000f2")
_ENV = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}


def _db(tmp_path, td, rows):
    dataset_id = uuid5(_NS, str(td))
    es = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12)
    o = cash_open_utc(td)
    trades = tuple(TradeObservation(uuid5(dataset_id, str(i)), dataset_id, i + 1, es, o + timedelta(seconds=s),
                                    D(str(p)), D(1)) for i, (s, p) in enumerate(rows))
    path = tmp_path / f"ot-{td}.sqlite3"
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(dataset_id, DatasetKind.HISTORICAL_IMPORT, "opening-type-test",
                                       capture_started_at=overnight_window_utc(td)[0],
                                       capture_ended_at=o + timedelta(hours=7)))
    store.save_trade_observations(trades)
    store.save_dxlink_time_and_sale_provenance(tuple(
        DxLinkTimeAndSaleProvenance(t.observation_id, f"evt:{t.dataset_sequence}", t.dataset_sequence,
                                    t.dataset_sequence, t.dataset_sequence, t.dataset_sequence, t.event_timestamp,
                                    event_classification="NEW") for t in trades))
    store.save_quality_events(())
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.FINALIZED)
    store.close()
    return path


def _full_day(low, high):
    return [(1800 * i + m, p) for i in range(13) for m, p in ((5, low), (6, high))]


def _pair(tmp_path):
    prior = _db(tmp_path, date(2026, 10, 2), _full_day(90, 110))
    cur = _db(tmp_path, date(2026, 10, 5), [(-3600, 101), (0, 102), (10, 103), (100, 110), (200, 103), (400, 101.5),
                                            (1700, 101.75)] + _full_day(99, 103)[2:])
    return prior, cur


def test_dataset_classification_matches_direct_build(tmp_path):
    prior_path, cur_path = _pair(tmp_path)
    results = []
    for p in (prior_path, cur_path):
        store = LaboratoryStore(p, read_only=True)
        try:
            results.append(analyze_tpo_dataset(store, uuid5(_NS, p.stem[3:])))
        finally:
            store.close()
    c = opening_type_classification(results[1], results)
    assert c.facts.opening.prior.prior_trading_date == date(2026, 10, 2)
    ev = c.candidate(OTD).evidence
    assert (ev.reference, ev.reached_utc, [n for n, _ in ev.other_references_reached]) == (
        "PRIOR_HIGH", cash_open_utc(date(2026, 10, 5)) + timedelta(seconds=100), ["PRIOR_VAH"])
    text = render_tpo_report(results[1], opening_types=c)
    assert "OPENING-TYPE CANDIDATES:" in text
    assert "Boundary: derived facts and opening-type CANDIDATES (OPENING_TYPE_V1) -- no interpretation or signal." in text
    assert "OPENING-TYPE" not in render_tpo_report(results[1])


def test_profile_cli_opening_types_flag(tmp_path):
    prior, cur = _pair(tmp_path)

    def run(*args):
        r = subprocess.run([sys.executable, "scripts/dicks_lab_tpo_profile.py", str(cur), *args], cwd=REPO, env=_ENV,
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout

    base = run("--opening-facts", "--prior-database", str(prior))
    both = run("--opening-facts", "--opening-types", "--prior-database", str(prior))
    assert "OPENING-TYPE CANDIDATES" not in base and "OPENING-TYPE CANDIDATES:" in both
    head = base.split("\nTPO matrix", 1)[0]
    assert both.startswith(head)  # the accepted sections are unchanged
    assert "Matched candidates: OPEN_AUCTION_IN_RANGE, OPEN_TEST_DRIVE DOWN" in both


def test_study_script_records_and_summarize_smoke(tmp_path):
    prior, cur = _pair(tmp_path)
    before = [prior.read_bytes(), cur.read_bytes()]
    out = tmp_path / "out"
    r = subprocess.run([sys.executable, "scripts/dicks_lab_mp_opening_type_study.py", "record", str(out), str(prior),
                        str(cur)], cwd=REPO, env=_ENV, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    records = sorted((out / "records").iterdir())
    assert len(records) == 2 and len(list((out / "reports").iterdir())) == 2
    rec = json.loads(records[1].read_text())
    assert (rec["trading_date"], rec["cohort"], rec["database_sha256"]) == (
        "2026-10-05", "DEVELOPMENT", hashlib.sha256(before[1]).hexdigest())
    audit = (out / "opening_type_audit.md").read_text()
    assert "NOT VALIDATION" in audit and "| 2026-10-05 |" in audit
    assert [prior.read_bytes(), cur.read_bytes()] == before
    summary = tmp_path / "summary.md"
    r = subprocess.run([sys.executable, "scripts/dicks_lab_mp_opening_type_study.py", "summarize", str(summary),
                        str(out / "records")], cwd=REPO, env=_ENV, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "OPENING_TYPE_V1 record summary" in summary.read_text()
