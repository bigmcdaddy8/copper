"""0Z-A: MARKET_STUDY_STATE_V1 -- composition, canonical serialization, hashing and missing-data semantics.

Fixture days follow the 0Y-H fixtures: cash rows are (seconds after 08:30:00 CT, price), one contract
each. Current trading date Mon 2026-10-05; its prior trading date is Fri 2026-10-02.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID, uuid5

import pytest

from dicks_laboratory.analysis import analyze_anchored_vwap_dataset
from dicks_laboratory.dataset_state import DatasetClosingSummary, DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import DxLinkTimeAndSaleProvenance
from dicks_laboratory.market_study_state import (
    EVIDENCE_CLASSIFICATION,
    HASH_FIELD,
    MARKET_STUDY_STATE_SCHEMA,
    NOT_RECORDED,
    REPLAY_READINESS,
    AnalysisProvenance,
    ComponentStatus,
    EvidenceKind,
    ReplayReadiness,
    StateTemporality,
    build_market_study_state,
    canonical_payload_json,
    canonical_state_json,
    check_references,
    encode,
    load_study_inputs,
    market_study_state_sha256,
    render_summary,
    resolve_pointer,
    verify_state_json,
)
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.sessions import AnchorKind
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_analysis import opening_type_classification
from dicks_laboratory.tpo_opening import ContextOutcome, cash_open_utc
from dicks_laboratory.tpo_opening_type import CandidateResult, OpeningTypeName
from dicks_laboratory.tpo_opening_type_record import OPENING_TYPE_V1_SOURCE_SHA256
from dicks_laboratory.tpo_overnight import overnight_window_utc

D = Decimal
CUR, PRIOR = date(2026, 10, 5), date(2026, 10, 2)
REPO = Path(__file__).resolve().parents[3]
PROV = AnalysisProvenance("a" * 40, False)
_NS = UUID("0e5a0000-0000-4000-8000-0000000000fa")
_ENV = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
# Canonical hash of the `_golden` fixture state. Any change to an accepted analytic's output, to the
# state schema or to the canonical encoding changes it: that is a MARKET_STUDY_STATE_V2 question.
GOLDEN_SHA256 = "c1555fc8861a2c45e53f6dfd9b291dbb78098f5889484db1073d461c65e18e69"


def _full_day(low, high):
    return [(1800 * i + m, p) for i in range(13) for m, p in ((5, low), (6, high))]


CUR_ROWS = [(-3600, 101), (0, 102), (10, 103), (100, 110), (200, 103), (400, 101.5), (1700, 101.75)] + \
    _full_day(99, 103)[2:]


def _db(tmp_path, td, rows, *, month=12, summary="full", gaps=(), lifecycle=DatasetLifecycleState.FINALIZED,
        started="window", ended=None, name=None):
    dataset_id = uuid5(_NS, f"{td}-{month}-{name}")
    es = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, month)
    o = cash_open_utc(td)
    trades = tuple(TradeObservation(uuid5(dataset_id, str(i)), dataset_id, i + 1, es, o + timedelta(seconds=s),
                                    D(str(p)), D(1)) for i, (s, p) in enumerate(rows))
    path = tmp_path / f"mss-{name or td}.sqlite3"
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(
        dataset_id, DatasetKind.HISTORICAL_IMPORT, f"mss-{td}",
        source_locator=f"TASTYTRADE_DXLINK:/ES{'Z' if month == 12 else 'U'}26:XCME:TimeAndSale",
        normalizer_version="phase-0v-serious-collection-v1",
        capture_started_at=overnight_window_utc(td)[0] if started == "window" else started,
        capture_ended_at=ended if ended is not None else o + timedelta(hours=7)))
    store.save_dataset_trading_context(dataset_id, td, es)
    store.save_trade_observations(trades)
    store.save_dxlink_time_and_sale_provenance(tuple(
        DxLinkTimeAndSaleProvenance(t.observation_id, f"evt:{t.dataset_sequence}", t.dataset_sequence,
                                    t.dataset_sequence, t.dataset_sequence, t.dataset_sequence, t.event_timestamp,
                                    event_classification="NEW") for t in trades))
    store.save_quality_events(tuple(
        DatasetQualityEvent(uuid5(dataset_id, f"gap{i}"), dataset_id, kind, "test gap", interval_start=s,
                            interval_end=e) for i, (kind, s, e) in enumerate(gaps)))
    if summary is not None:
        full = summary == "full"
        store.save_dataset_closing_summary(DatasetClosingSummary(
            dataset_id, len(trades), 0, 0, sum(1 for g in gaps if g[0] is DatasetQualityEvidenceType.KNOWN_GAP), 0,
            1, len(trades), o + timedelta(hours=7), "phase-0v-serious-collection-v1", "c" * 40,
            submitted_events=len(trades) if full else None, persisted_events=len(trades) if full else None))
    store.set_dataset_lifecycle_state(dataset_id, lifecycle)
    store.close()
    return path


def _pair(tmp_path, prior_month=12):
    return (_db(tmp_path, PRIOR, _full_day(90, 110), month=prior_month, name=f"prior{prior_month}"),
            _db(tmp_path, CUR, CUR_ROWS, name="cur"))


def _state(cur_path, prior_path=None, provenance=PROV):
    prior = load_study_inputs(prior_path) if prior_path is not None else None
    return build_market_study_state(load_study_inputs(cur_path), prior, provenance)


@pytest.fixture(scope="module")
def pair(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pair")
    prior_path, cur_path = _pair(tmp)
    prior, cur = load_study_inputs(prior_path), load_study_inputs(cur_path)
    return prior_path, cur_path, prior, cur, build_market_study_state(cur, prior, PROV)


# --- identity, composition -----------------------------------------------------------------------

def test_schema_and_final_temporality(pair):
    s = pair[4]
    assert s.schema == MARKET_STUDY_STATE_SCHEMA == "MARKET_STUDY_STATE_V1"
    assert s.state_temporality is StateTemporality.FINAL_STUDY_STATE
    assert "NOT what was knowable at any intraday instant" in s.temporality_note
    doc = json.loads(canonical_state_json(s))
    assert doc["schema"] == "MARKET_STUDY_STATE_V1" and doc["state_temporality"] == "FINAL_STUDY_STATE"
    assert not any("generated" in k for k in doc)  # no wall-clock field in the canonical state


def test_state_assembles_the_accepted_objects_without_a_second_calculation(pair):
    _, _, prior, cur, s = pair
    r = cur.result
    assert s.tpo.profile is r.profile and s.tpo_structure.structure is r.structure
    assert s.day_type.classification is r.day_structure and s.day_strength.strength is r.day_strength
    assert s.overnight.session is r.overnight
    assert s.opening_type.classification == opening_type_classification(r, (prior.result,))
    assert s.cash_opening.path_facts is s.opening_type.classification.facts
    assert s.cash_opening.facts is s.cash_opening.path_facts.opening
    assert s.prior_day.context is s.cash_opening.facts.prior
    assert s.overnight.context is s.cash_opening.path_facts.overnight
    vp = r.volume_profile
    assert (s.volume_profile.poc, s.volume_profile.total_volume, s.volume_profile.window_vwap) == (
        vp.point_of_control.price, vp.total_volume, vp.selected_trades_vwap)
    assert s.volume_profile.distribution == tuple((lv.price, lv.volume) for lv in vp.levels)


def test_vwap_studies_equal_the_accepted_anchored_vwap_analysis(pair):
    _, cur_path, _, _, s = pair
    store = LaboratoryStore(cur_path, read_only=True)
    try:
        for study in s.vwap.studies:
            accepted = analyze_anchored_vwap_dataset(store, s.current_dataset.dataset_id, study.anchor_kind)
            assert (study.vwap, study.included_trade_count, study.included_volume) == (
                accepted.effective_vwap, accepted.effective_included_trade_count, accepted.effective_included_volume)
            assert study.anchor_utc == accepted.anchor_timestamp_utc and study.coverage == accepted.coverage
    finally:
        store.close()
    assert [v.anchor_kind for v in s.vwap.studies] == [AnchorKind.SESSION_OPEN, AnchorKind.US_CASH_OPEN]
    # capture ends 15:30 CT, before the 16:00 CT session end: qualified, still computed
    assert s.vwap.status is ComponentStatus.QUALITY_QUALIFIED
    assert all("before the session end" in v.reasons[0] for v in s.vwap.studies)


def test_dataset_identity_and_collector_vs_analysis_provenance(pair):
    s = pair[4]
    d = s.current_dataset
    assert (d.trading_date, d.recorded_trading_date, d.instrument_id) == (CUR, CUR, "FUTURE:CME:ES:2026-12")
    assert (d.source_system, d.streamer_symbol, d.source_event_type) == ("TASTYTRADE_DXLINK", "/ESZ26:XCME",
                                                                         "TimeAndSale")
    assert d.collector_git_commit == "c" * 40 and s.provenance.analysis_git_commit == "a" * 40
    assert (d.accepted_trade_count, d.submitted_events, d.persisted_events, d.accounting_difference) == (
        len(CUR_ROWS), len(CUR_ROWS), len(CUR_ROWS), 0)
    assert d.retained_trade_count == len(CUR_ROWS) and d.database_sha256 == hashlib.sha256(
        pair[1].read_bytes()).hexdigest()


def test_contract_identity_comes_from_the_dataset_not_the_broker(pair):
    c = pair[4].contract
    assert (c.root, c.exchange, c.contract_year, c.contract_month, c.month_code) == ("ES", "CME", 2026, 12, "Z")
    assert c.tick_size == D("0.25") and c.tick_size_source == "CME_ES_TICK_GRID CME_ES_TICK_GRID_V1"
    assert c.streamer_symbol == "/ESZ26:XCME"
    assert (c.broker_symbol, c.broker_symbol_status, c.multiplier, c.multiplier_status) == (
        None, NOT_RECORDED, None, NOT_RECORDED)


def test_prior_day_context_and_both_dataset_identities(pair):
    _, _, prior, _, s = pair
    p = s.prior_day
    assert p.status is ComponentStatus.AVAILABLE and p.outcome is ContextOutcome.AVAILABLE
    assert p.prior_dataset_supplied and p.source == prior.source and p.source.database_sha256
    assert (p.context.prior_dataset_id, p.context.profile_high, p.context.profile_low) == (
        str(prior.source.dataset_id), D("110.00"), D("90.00"))
    assert p.context.strength is not None and p.context.day_type_outcome is not None


def test_opening_type_section_is_a_candidate_set_with_policy_hash(pair):
    o = pair[4].opening_type
    assert o.policy_id == "OPENING_TYPE_V1" and o.policy_frozen_sha256 == OPENING_TYPE_V1_SOURCE_SHA256
    assert o.policy_source_matches_freeze
    assert [(m.type, m.direction) for m in o.matched] == [("OPEN_AUCTION_IN_RANGE", None), ("OPEN_TEST_DRIVE", "DOWN")]
    assert o.deferred == (("OPEN_REJECTION_REVERSE",
                           o.classification.candidate(OpeningTypeName.OPEN_REJECTION_REVERSE).reasons[0]),)
    assert o.deferred[0][1].startswith("REFERENCE_DEFINITION_CONFLICT")
    assert not hasattr(o, "primary") and not hasattr(o.classification, "primary")


# --- canonical serialization and hashing ---------------------------------------------------------

def test_build_twice_is_byte_identical_and_hash_excludes_itself(tmp_path):
    prior_path, cur_path = _pair(tmp_path)
    before = (prior_path.read_bytes(), cur_path.read_bytes())
    a, b = _state(cur_path, prior_path), _state(cur_path, prior_path)
    ja, jb = canonical_state_json(a), canonical_state_json(b)
    assert ja == jb and market_study_state_sha256(a) == market_study_state_sha256(b)
    doc = json.loads(ja)
    assert doc[HASH_FIELD] == market_study_state_sha256(a) == hashlib.sha256(
        canonical_payload_json(a).encode()).hexdigest()
    assert HASH_FIELD not in canonical_payload_json(a)
    assert verify_state_json(ja)
    assert not verify_state_json(ja.replace('"schema":"MARKET_STUDY_STATE_V1"', '"schema":"MARKET_STUDY_STATE_V2"'))
    assert (prior_path.read_bytes(), cur_path.read_bytes()) == before  # read-only
    assert not list(tmp_path.glob("*-wal")) and not list(tmp_path.glob("*-journal"))


def test_canonical_layout_is_sorted_compact_ascii(pair):
    text = canonical_state_json(pair[4])
    assert text.startswith('{"cash_opening":') and ", " not in text[:200] and text.isascii()
    doc = json.loads(text)
    assert list(doc) == sorted(doc)
    assert json.dumps(doc, sort_keys=True, separators=(",", ":")) == text


class _Color(StrEnum):
    RED = "RED"


def test_value_encoding_is_stable():
    ts = datetime(2026, 10, 5, 13, 30, 0, 123, tzinfo=timezone.utc)
    assert encode(D("102.00")) == "102.00" and encode(D("1E+2")) == "100" and encode(D("0.10")) == "0.10"
    assert encode(D("-0.25")) == "-0.25"
    assert encode(ts) == "2026-10-05T13:30:00.000123Z"
    assert encode(ts.astimezone(timezone(timedelta(hours=-5)))) == "2026-10-05T13:30:00.000123Z"
    assert encode(timedelta(seconds=60)) == "60.000000" and encode(timedelta(microseconds=-1)) == "-0.000001"
    assert encode(timedelta(seconds=91, microseconds=300000)) == "91.300000"
    assert encode(date(2026, 10, 5)) == "2026-10-05" and encode(_Color.RED) == "RED"
    assert encode((None, 0, True)) == [None, 0, True]
    with pytest.raises(TypeError):
        encode(1.5)
    with pytest.raises(TypeError):
        encode(datetime(2026, 10, 5))
    with pytest.raises(TypeError):
        encode(D("NaN"))


def test_hash_changes_on_any_semantic_change(pair):
    s = pair[4]
    base = market_study_state_sha256(s)
    variants = [
        dataclasses.replace(s, provenance=AnalysisProvenance("b" * 40, False)),
        dataclasses.replace(s, provenance=AnalysisProvenance("a" * 40, True)),
        dataclasses.replace(s, current_dataset=dataclasses.replace(s.current_dataset, submitted_events=None)),
        dataclasses.replace(s, volume_profile=dataclasses.replace(s.volume_profile, poc=D("103.25"))),
        dataclasses.replace(s, volume_profile=dataclasses.replace(s.volume_profile, poc=D("103.0"))),  # 103.0 != 103.00
        dataclasses.replace(s, tpo=dataclasses.replace(s.tpo, status=ComponentStatus.QUALITY_QUALIFIED)),
        dataclasses.replace(s, opening_type=dataclasses.replace(s.opening_type, matched=s.opening_type.matched[:1])),
    ]
    hashes = {market_study_state_sha256(v) for v in variants}
    assert base not in hashes and len(hashes) == len(variants)


def test_golden_hash(tmp_path):
    prior_path, cur_path = _pair(tmp_path)
    cur, prior = load_study_inputs(cur_path), load_study_inputs(prior_path)
    # the SQLite file bytes are not part of the fixture contract; everything else is
    cur = dataclasses.replace(cur, source=dataclasses.replace(cur.source, database_sha256="1" * 64))
    prior = dataclasses.replace(prior, source=dataclasses.replace(prior.source, database_sha256="2" * 64))
    assert market_study_state_sha256(build_market_study_state(cur, prior, PROV)) == GOLDEN_SHA256


def test_duplicates_are_references_and_tape_paths_are_omitted(pair):
    doc = json.loads(canonical_state_json(pair[4]))
    assert doc["cash_opening"]["facts"]["prior"] == {"$ref": "/prior_day/context"}
    assert doc["cash_opening"]["path_facts"]["opening"] == {"$ref": "/cash_opening/facts"}
    assert doc["cash_opening"]["path_facts"]["overnight"] == {"$ref": "/overnight/context"}
    assert doc["overnight"]["context"]["session"] == {"$ref": "/overnight/session"}
    assert doc["opening_type"]["classification"]["facts"] == {"$ref": "/cash_opening/path_facts"}
    assert doc["cash_opening"]["facts"]["session"]["path"]["$omitted"].startswith("TAPE_PATH")
    assert doc["overnight"]["session"]["path"]["$omitted"].startswith("TAPE_PATH")
    for ref in ("/prior_day/context", "/cash_opening/facts", "/overnight/context", "/overnight/session",
                "/cash_opening/path_facts"):
        assert resolve_pointer(doc, ref) and isinstance(resolve_pointer(doc, ref)[0], dict)
    assert len(canonical_state_json(pair[4])) < 200_000  # an evidence state, not a tape dump


def test_reference_must_be_the_serialized_object(pair):
    s = pair[4]
    other = dataclasses.replace(s.prior_day.context, reasons=("different",))
    with pytest.raises(ValueError, match="/prior_day/context"):
        check_references(dataclasses.replace(s, prior_day=dataclasses.replace(s.prior_day, context=other)))


def test_state_is_immutable(pair):
    s = pair[4]
    with pytest.raises(FrozenInstanceError):
        s.schema = "MARKET_STUDY_STATE_V2"
    with pytest.raises(FrozenInstanceError):
        s.tpo.status = ComponentStatus.NOT_AVAILABLE
    assert isinstance(s.quality_matrix, tuple) and isinstance(s.vwap.studies, tuple)


# --- evidence, policy, replay contract -----------------------------------------------------------

def test_evidence_classification_is_explicit_and_resolves(pair):
    doc = json.loads(canonical_state_json(pair[4]))
    for entry in EVIDENCE_CLASSIFICATION:
        assert resolve_pointer(doc, entry.pointer), entry.pointer
    kinds = {e.pointer: e.kind for e in EVIDENCE_CLASSIFICATION}
    assert kinds["/tpo_structure/structure/upper/excess_candidate"] is EvidenceKind.CANDIDATE
    assert kinds["/opening_type/deferred"] is EvidenceKind.DEFERRED
    assert kinds["/day_type/classification/facts"] is EvidenceKind.DERIVED_FACT
    assert kinds["/overnight/session/quality"] is EvidenceKind.QUALITY_QUALIFICATION
    assert doc["evidence_classification"][0] == {"kind": "IDENTITY", "pointer": "/provenance"}
    results = {c["result"] for c in doc["opening_type"]["classification"]["candidates"]}
    assert results <= {r.value for r in CandidateResult} and "DEFERRED" in results
    assert doc["tpo_structure"]["structure"]["upper"]["excess_candidate"] in ("YES", "NO", "NOT_CLASSIFIED")


def test_policy_registry_uses_the_codebase_identifiers(pair):
    reg = {e.component: e for e in pair[4].policy_registry}
    assert len(reg) == len(pair[4].policy_registry)
    assert reg["MARKET_STUDY_STATE"].policy_id == "MARKET_STUDY_STATE_V1"
    assert (reg["PRICE_GRID"].policy_id, reg["PRICE_GRID"].policy_version) == ("CME_ES_TICK_GRID",
                                                                               "CME_ES_TICK_GRID_V1")
    assert reg["TPO_POC"].policy_id == "DICKS_LAB_TPO_POC_POLICY"
    assert reg["TPO_VALUE_AREA"].policy_version == "V1_TWO_ROW_GREATER_SUM_TIE_ABOVE"
    assert reg["DAY_TYPE_V1"].policy_version == "V1_DIRECTIONAL_STATE_X_IB_SHARE"
    for pid in ("DAY_STRUCTURE_STRENGTH_V1", "OPENING_AUCTION_FACTS_V1", "OVERNIGHT_CONTEXT_V1",
                "OPENING_PATH_FACTS_V1"):
        assert reg[pid].policy_id == pid
    assert reg["OPENING_TYPE_V1"].frozen_source_sha256 == OPENING_TYPE_V1_SOURCE_SHA256
    assert "matches the freeze" in reg["OPENING_TYPE_V1"].note
    assert reg["VWAP"].policy_id is None  # none exists; none is invented
    assert pair[4].tpo.profile.poc_policy_id == reg["TPO_POC"].policy_id


def test_replay_readiness_inventory():
    by_name = {name: readiness for name, readiness, _ in REPLAY_READINESS}
    assert by_name["day_type DAY_TYPE_V1"] is ReplayReadiness.FINAL_DAY_ONLY
    assert by_name["study-window terminal price"] is ReplayReadiness.FINAL_DAY_ONLY
    assert by_name["prior_day context"] is ReplayReadiness.REPLAY_READY
    assert by_name["opening_type OPENING_TYPE_V1"] is ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION
    covered = " ".join(by_name)
    for section in ("dataset_quality", "vwap", "volume_profile", "tpo", "tpo_structure", "day_type", "day_strength",
                    "prior_day", "overnight", "opening_type", "contract", "quality_matrix"):
        assert section in covered, section


def test_quality_matrix_is_component_specific(pair):
    m = {q.component: q for q in pair[4].quality_matrix}
    assert list(m) == ["dataset", "contract", "vwap", "volume_profile", "cash_tpo", "tpo_structure", "day_type",
                       "day_strength", "prior_context", "overnight", "cash_opening", "opening_type"]
    assert m["vwap"].status is ComponentStatus.QUALITY_QUALIFIED and m["cash_tpo"].status is ComponentStatus.AVAILABLE
    assert m["opening_type"].domain_status == "CLASSIFIED"
    assert not any(hasattr(pair[4], name) for name in ("overall_quality", "score", "quality"))


# --- missing / unavailable semantics -------------------------------------------------------------

def test_contract_transition_makes_prior_context_unavailable(tmp_path):
    prior_path, cur_path = _pair(tmp_path, prior_month=9)
    s = _state(cur_path, prior_path)
    p = s.prior_day
    assert p.outcome is ContextOutcome.CONTRACT_CHANGED and p.status is ComponentStatus.NOT_AVAILABLE
    assert p.source.instrument_id == "FUTURE:CME:ES:2026-09" and p.context.prior_contract == "FUTURE:CME:ES:2026-09"
    assert p.context.profile_high is None and p.context.poc is None  # no cross-contract price
    f = s.cash_opening.facts
    assert f.range_location is None and f.gap_points is None
    assert not [i for i in f.reference_interactions if i.reference.startswith("PRIOR")]
    c = s.opening_type.classification
    assert c.candidate(OpeningTypeName.OPEN_AUCTION_IN_RANGE).result is CandidateResult.NOT_CLASSIFIED
    assert "CONTRACT_CHANGED" in render_summary(s)


def test_no_prior_supplied_is_explicit(tmp_path):
    _, cur_path = _pair(tmp_path)
    s = _state(cur_path)
    p = s.prior_day
    assert (p.status, p.outcome, p.prior_dataset_supplied, p.source) == (
        ComponentStatus.NOT_AVAILABLE, ContextOutcome.NO_PRIOR_PROFILE, False, None)
    assert p.reasons[0] == "no prior dataset was supplied to the builder"
    assert json.loads(canonical_state_json(s))["prior_day"]["source"] is None


def test_missing_historical_closing_fields_are_null_not_zero(tmp_path):
    legacy = _db(tmp_path, CUR, CUR_ROWS, summary="legacy", name="legacy")
    none = _db(tmp_path, CUR, CUR_ROWS, summary=None, name="none")
    d = json.loads(canonical_state_json(_state(legacy)))["current_dataset"]
    assert d["accepted_trade_count"] == len(CUR_ROWS) and d["collector_git_commit"] == "c" * 40
    assert (d["submitted_events"], d["persisted_events"], d["accounting_difference"]) == (None, None, None)
    n = json.loads(canonical_state_json(_state(none)))["current_dataset"]
    assert n["closing_summary_recorded"] is False
    assert all(n[k] is None for k in ("accepted_trade_count", "rejected_record_count", "deferred_event_count",
                                      "submitted_events", "collector_git_commit", "collector_version"))
    assert n["applied_correction_count"] == 0 and n["retained_trade_count"] == len(CUR_ROWS)


def test_partial_quality_dataset_stays_constructible(tmp_path):
    o = cash_open_utc(CUR)
    gap = (DatasetQualityEvidenceType.KNOWN_GAP, o + timedelta(seconds=300), o + timedelta(seconds=302))
    path = _db(tmp_path, CUR, CUR_ROWS[:20], gaps=(gap,), lifecycle=DatasetLifecycleState.INTERRUPTED,
               ended=o + timedelta(hours=3), name="partial")
    s = _state(path)
    q = s.dataset_quality
    assert q.status is ComponentStatus.QUALITY_QUALIFIED and q.lifecycle_qualification.startswith("lifecycle INTERRUPTED")
    w = {x.window: x for x in q.windows}
    assert (w["CASH_PROFILE"].fully_captured, w["OPENING"].fully_captured, w["OVERNIGHT"].fully_captured) == (
        False, True, True)
    assert (w["OPENING"].known_gaps_overlapping, w["OVERNIGHT"].known_gaps_overlapping) == (1, 0)
    assert s.tpo.status is ComponentStatus.QUALITY_QUALIFIED
    assert s.day_type.status is ComponentStatus.NOT_AVAILABLE and s.day_type.outcome.value == "NOT_CLASSIFIED"
    assert s.cash_opening.status is ComponentStatus.QUALITY_QUALIFIED
    assert verify_state_json(canonical_state_json(s))
    statuses = {q.component: q.status for q in s.quality_matrix}
    assert statuses["day_type"] is ComponentStatus.NOT_AVAILABLE and statuses["cash_tpo"] is not statuses["day_type"]


def test_no_cash_profile_state_is_still_built(tmp_path):
    path = _db(tmp_path, CUR, [(-7200, 100), (-3600, 101)], name="overnight-only")
    s = _state(path)
    for section in (s.volume_profile, s.tpo, s.tpo_structure, s.day_type, s.day_strength, s.overnight,
                    s.cash_opening, s.opening_type):
        assert section.status is ComponentStatus.NOT_AVAILABLE and section.reasons
    assert s.opening_type.deferred == (("OPEN_REJECTION_REVERSE", "REFERENCE_DEFINITION_CONFLICT"),)
    doc = json.loads(canonical_state_json(s))
    assert doc["tpo"]["profile"] is None and doc["volume_profile"]["poc"] is None
    assert doc["volume_profile"]["distribution"] == []
    assert s.vwap.studies[0].vwap is not None and s.vwap.studies[1].status is ComponentStatus.NOT_AVAILABLE


def test_globex_open_not_claimed_keeps_first_observed_trade(tmp_path):
    late = overnight_window_utc(CUR)[0] + timedelta(milliseconds=1)
    s = _state(_db(tmp_path, CUR, CUR_ROWS, started=late, name="late"))
    o = s.overnight
    assert (o.globex_open_claimed, o.globex_open_boundary_proven, o.first_observed_overnight_trade_is_globex_open) == (
        False, False, False)
    assert o.session.first_price == D("101") and o.session.globex_open_price is None
    assert o.status is ComponentStatus.QUALITY_QUALIFIED


# --- human summary and CLI -----------------------------------------------------------------------

DOMAINS = ("MARKET STUDY STATE", "DATASET / QUALITY", "CONTRACT", "VWAP", "VOLUME PROFILE", "TPO / INITIAL BALANCE",
           "PROFILE STRUCTURE", "DAY TYPE CANDIDATE", "DAY STRENGTH", "PRIOR DAY", "OVERNIGHT", "CASH OPENING",
           "OPENING-TYPE CANDIDATES", "QUALITY MATRIX", "POLICY VERSIONS", "STATE HASH")
FORBIDDEN = ("bullish", "bearish", "buy", "sell", "setup", "entry", "target", "probability", "confidence",
             "fade", "continuation", "initiative", "responsive")


def test_summary_is_organized_by_evidence_domain(pair):
    text = render_summary(pair[4])
    positions = [text.index(d if i == 0 else "\n" + d) for i, d in enumerate(DOMAINS)]
    assert positions == sorted(positions)
    lowered = text.lower()
    assert not [w for w in FORBIDDEN if w in lowered]
    assert "RECOMMENDATION" not in text and "no primary type" in text
    assert market_study_state_sha256(pair[4]) in text


def _run(*args):
    return subprocess.run([sys.executable, "scripts/dicks_lab_market_study_state.py", *map(str, args)], cwd=REPO,
                          env=_ENV, capture_output=True, text=True)


def test_cli_json_summary_and_read_only_smoke(tmp_path):
    prior_path, cur_path = _pair(tmp_path)
    before = (prior_path.read_bytes(), cur_path.read_bytes())
    out = tmp_path / "state.json"
    r = _run(cur_path, "--prior-database", prior_path, "--json", "--analysis-commit", "a" * 40, "--json-out", out)
    assert r.returncode == 0, r.stderr
    document = r.stdout.rstrip("\n")
    assert verify_state_json(document) and out.read_text() == document
    assert json.loads(document)["provenance"] == {"analysis_git_commit": "a" * 40, "analysis_worktree_modified": None}
    again = _run(cur_path, "--prior-database", prior_path, "--json", "--analysis-commit", "a" * 40)
    assert again.stdout == r.stdout
    summary = _run(cur_path, "--prior-database", prior_path, "--analysis-commit", "a" * 40)
    assert summary.returncode == 0 and summary.stdout.startswith("MARKET STUDY STATE")
    assert json.loads(document)[HASH_FIELD] in summary.stdout
    both = _run(cur_path, "--json", "--summary", "--analysis-commit", "a" * 40)
    assert both.returncode != 0
    resolved = _run(cur_path, "--json")
    assert resolved.returncode == 0 and len(json.loads(resolved.stdout)["provenance"]["analysis_git_commit"]) == 40
    assert (prior_path.read_bytes(), cur_path.read_bytes()) == before
