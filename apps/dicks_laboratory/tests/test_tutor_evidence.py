"""0AA-A: AI tutor evidence and lesson foundation (no AI model).

Uses the 0Z-B fixture day (test_replay): late print 09:55 received 10:05; correction / cancel
received 10:05:10 / 10:05:20; disconnect 10:15:00-10:15:30 (KNOWN_GAP); capture stop 15:30 CT.
"""
from __future__ import annotations

import dataclasses
import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.replay import MarketReplay, snapshot_sha256
from dicks_laboratory.replay_player import ReplaySession, relations
from dicks_laboratory.tutor_evidence import (
    AS_OF,
    CURRICULUM_MODULES,
    CURRICULUM_SOURCES,
    DRYSDALE_MODULE,
    LABORATORY_PROFILE_70,
    PAYLOAD_HASH_FIELD,
    PLAYBOOK_NINJATRADER_68,
    AssertedValue,
    Availability,
    ClaimCategory,
    CurriculumNotReady,
    DependencyStatus,
    EvidenceDomain,
    EvidenceRef,
    EvidenceSupport,
    GroundingIssueCode,
    LessonMode,
    LessonStage,
    ModuleReadiness,
    QuestionKind,
    TutorClaim,
    UnsupportedClaim,
    ValueAreaConventionError,
    build_tutor_lesson,
    canonical_json,
    example_lesson,
    instructor_view,
    render_view,
    require_executable,
    resolve_pointer,
    rubric_ref_coverage,
    snapshot_document,
    student_view,
    validate_answer_grounding,
    verify_payload,
)

sys.path.insert(0, str(Path(__file__).parent))
import test_replay as fx_mod  # noqa: E402  (shared 0Z-B fixtures)

CUR, PRIOR, ct = fx_mod.CUR, fx_mod.PRIOR, fx_mod.ct
PROV = AnalysisProvenance("a" * 40, False)
REPO = Path(__file__).resolve().parents[3]
Q = QuestionKind
FORBIDDEN = ("bullish", "bearish", "buy", "sell", "setup", "entry", "target", "probability", "confidence",
             "recommend", "signal", "initiative", "responsive")


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("tutor")
    prior = fx_mod._db(tmp, PRIOR, [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                       name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))
    cur = fx_mod._db(tmp, CUR, fx_mod.OVERNIGHT + fx_mod._base_day() + fx_mod.SPECIAL, name="cur",
                     deferred=(fx_mod.CORRECTION, fx_mod.CANCEL))
    s = ReplaySession(MarketReplay.load(cur, PROV, prior))
    s.paths = (prior, cur, tmp)
    return s


def _lesson(session, kind, at, compare_from=None, reveal_at=None):
    return build_tutor_lesson(session, example_lesson(session, kind, at, compare_from, reveal_at))


def _ref(lesson, pointer, role="LESSON_TIME"):
    snap = next(s for s in lesson.context.snapshots if s.role.value == role)
    return EvidenceRef(snap.snapshot_sha256, pointer)


def _codes(report):
    return {i.code for i in report.issues}


# --- temporality and anti-lookahead --------------------------------------------------------------

def test_context_is_as_of_the_lesson_time(session):
    lesson = _lesson(session, Q.PRICE_VS_CASH_VWAP, "09:45")
    c, snap = lesson.context, session.snapshot("09:45")
    assert c.evidence_temporality == AS_OF and c.snapshot_sha256 == snapshot_sha256(snap)
    assert c.replay_market_time == c.replay_knowledge_time == ct(CUR, 9, 45)
    doc = snapshot_document(snap)
    for item in c.items():  # every reference resolves to exactly the cited value in the authorized snapshot
        assert item.ref.source_sha256 == c.snapshot_sha256
        value = resolve_pointer(doc, item.ref.pointer)
        assert item.value == (json.dumps(value, sort_keys=True, separators=(",", ":")) if isinstance(
            value, dict | list) else value)
    assert {i.domain for i in c.items()} <= set(c.authorized_domains)
    stamps = [i.value for i in c.items() if isinstance(i.value, str) and i.value.endswith("Z") and "T" in i.value]
    assert stamps and all(s < "2026-10-05T14:45:00.000000Z" for s in stamps)


def _mutate_after_1000(src: Path, dst: Path) -> None:
    shutil.copyfile(src, dst)
    con = sqlite3.connect(dst)  # a trade at 14:00:05 CT changes price; nothing before 10:00 changes
    assert con.execute("UPDATE trade_observations SET price = '107' WHERE event_timestamp LIKE "
                       "'2026-10-05T19:00:05%'").rowcount == 1
    con.commit()
    con.close()


def test_later_evidence_cannot_change_an_earlier_lesson(session):
    prior, cur, tmp = session.paths
    mutated = tmp / "tutor-mutated.sqlite3"
    _mutate_after_1000(cur, mutated)
    other = ReplaySession(MarketReplay.load(mutated, PROV, prior))
    for kind, at, frm in ((Q.PRICE_VS_CASH_VWAP, "10:00", None), (Q.VALUE_MIGRATION, "10:00", "09:30"),
                          (Q.DATA_QUALITY, "10:00", None)):
        a, b = _lesson(session, kind, at, frm), _lesson(other, kind, at, frm)
        assert canonical_json(student_view(a)) == canonical_json(student_view(b))
        assert canonical_json(instructor_view(a)) == canonical_json(instructor_view(b))
    late = _lesson(session, Q.PRICE_VS_CASH_VWAP, "15:00")
    assert late.context.snapshot_sha256 != _lesson(other, Q.PRICE_VS_CASH_VWAP, "15:00").context.snapshot_sha256


def test_late_print_is_absent_before_receipt(session):
    def volume(at):
        lesson = _lesson(session, Q.VALUE_OCCUPANCY, at)
        return int(next(i for i in lesson.context.items() if i.ref.pointer == "/volume_profile/total_volume").value)

    # the 09:55 print is received at 10:05: a 10:04:59 lesson cannot contain it; no trade has market time in between
    assert volume("10:05:01") == volume("10:04:59") + 1


# --- student / instructor separation and reveal --------------------------------------------------

def test_student_payload_withholds_answer_and_future(session):
    lesson = _lesson(session, Q.PRICE_VS_CASH_VWAP, "09:45", reveal_at="10:15")
    future = lesson.future_outcome.evidence
    assert future.replay_market_time == ct(CUR, 10, 15)
    for stage in (LessonStage.QUESTION, LessonStage.HINT, LessonStage.ANSWER):
        text = canonical_json(student_view(lesson, stage))
        assert future.snapshot_sha256 not in text and "2026-10-05T15:15:00" not in text
        assert "future_outcome\":{" not in text and "FUTURE_OUTCOME" not in text
    q = student_view(lesson, LessonStage.QUESTION)
    text = canonical_json(q)
    assert q["withheld"] == ["hints", "answer_key", "future_outcome"]
    for hidden in ("answer_key\":", "reference_answer", "common_incorrect_claims", "rubric", "ACCEPTANCE",
                   lesson.definition.hints[0]):
        assert hidden not in text
    assert student_view(lesson, LessonStage.HINT)["withheld"] == ["answer_key", "future_outcome"]
    ans = student_view(lesson, LessonStage.ANSWER)
    assert ans["withheld"] == ["future_outcome"] and ans["answer_key"]["summary"] == "ABOVE"
    post = student_view(lesson, LessonStage.POST_REVEAL)
    assert post["withheld"] == [] and post["future_outcome"]["evidence"]["snapshot_sha256"] == future.snapshot_sha256
    inst = instructor_view(lesson)
    assert inst["answer_key"]["rubric"]["common_incorrect_claims"] and inst["future_outcome"]["summary"] == "BELOW"
    assert inst["lesson"]["hints"] == list(lesson.definition.hints)


def test_future_evidence_is_refused_until_post_reveal(session):
    lesson = _lesson(session, Q.PRICE_VS_CASH_VWAP, "09:45", reveal_at="10:15")
    fsha = lesson.future_outcome.evidence.snapshot_sha256
    ref = EvidenceRef(fsha, "/relations/last_price_vs_cash_vwap")
    answer = dataclasses.replace(lesson.answer_key.reference_answer, claims=(
        TutorClaim("Later the price is BELOW the cash VWAP.", ClaimCategory.DERIVED_FACT, (ref,)),))
    assert GroundingIssueCode.HIDDEN_FUTURE_EVIDENCE in _codes(validate_answer_grounding(answer, lesson))
    revealed = dataclasses.replace(answer, stage=LessonStage.POST_REVEAL)
    assert validate_answer_grounding(revealed, lesson).valid


# --- grounding -------------------------------------------------------------------------------------

def test_reference_answers_are_grounded(session):
    for kind, at, frm in ((Q.PRICE_VS_CASH_VWAP, "09:45", None), (Q.INITIAL_BALANCE_STATUS, "09:15", None),
                          (Q.EVIDENCE_CHANGES, "10:05:01", "10:04:59"), (Q.VALUE_MIGRATION, "10:00", "09:30"),
                          (Q.VALUE_OCCUPANCY, "10:00", None), (Q.NOT_YET_DETERMINED_ITEMS, "10:00", None),
                          (Q.DATA_QUALITY, "10:20", None)):
        lesson = _lesson(session, kind, at, frm)
        answer = lesson.answer_key.reference_answer
        report = validate_answer_grounding(answer, lesson)
        assert report.valid, (kind, report.issues)
        cited, missing = rubric_ref_coverage(answer, lesson)
        assert not missing and len(cited) == len(lesson.answer_key.rubric.required_evidence_refs)


def test_unknown_unauthorized_and_mismatched_references_fail(session):
    lesson = _lesson(session, Q.PRICE_VS_CASH_VWAP, "09:45")
    base = lesson.answer_key.reference_answer
    sha = lesson.context.snapshot_sha256

    def check(claim, code):
        report = validate_answer_grounding(dataclasses.replace(base, claims=(claim,)), lesson)
        assert code in _codes(report), report.issues

    check(TutorClaim("x", ClaimCategory.DERIVED_FACT, (EvidenceRef(sha, "/vwap/9/study/vwap"),)),
          GroundingIssueCode.UNKNOWN_EVIDENCE)
    check(TutorClaim("x", ClaimCategory.DERIVED_FACT, (EvidenceRef("0" * 64, "/prices/last_known_price"),)),
          GroundingIssueCode.UNKNOWN_EVIDENCE)
    check(TutorClaim("x", ClaimCategory.DERIVED_FACT, (EvidenceRef(sha, "/volume_profile/poc"),)),
          GroundingIssueCode.UNAUTHORIZED_EVIDENCE)  # exists, but VOLUME_PROFILE is not authorized here
    price = _ref(lesson, "/prices/last_known_price")
    check(TutorClaim("x", ClaimCategory.OBSERVED_FACT, (price,), (AssertedValue(price, "99"),)),
          GroundingIssueCode.VALUE_MISMATCH)
    check(TutorClaim("The cash VWAP is 1.", ClaimCategory.DERIVED_FACT, ()), GroundingIssueCode.UNGROUNDED_CLAIM)
    rel = _ref(lesson, "/relations/last_price_vs_cash_vwap")
    check(TutorClaim("Price appears to be accepting above VWAP.", ClaimCategory.OBSERVED_FACT, (rel,)),
          GroundingIssueCode.CATEGORY_NOT_SUPPORTED)  # an interpretation is not an observed fact
    check(TutorClaim("x", ClaimCategory.CURRICULUM_RULE, (), curriculum_source_id="DRYSDALE_VWAP_WAVE_CORE_SETUP_GUIDE"),
          GroundingIssueCode.CURRICULUM_SOURCE_INVALID)
    wrong = dataclasses.replace(base, snapshot_sha256=snapshot_sha256(session.snapshot("10:15")))
    assert GroundingIssueCode.WRONG_SNAPSHOT in _codes(validate_answer_grounding(wrong, lesson))


def test_interpretation_is_labeled_and_grounded(session):
    lesson = _lesson(session, Q.PRICE_VS_CASH_VWAP, "09:45")
    rel = _ref(lesson, "/relations/last_price_vs_cash_vwap")
    base = lesson.answer_key.reference_answer
    ok = dataclasses.replace(base, claims=base.claims + (
        TutorClaim("Price appears to be accepting above VWAP.", ClaimCategory.AI_INTERPRETATION, (rel,)),))
    report = validate_answer_grounding(ok, lesson)
    assert report.valid and report.interpretations == 1
    bare = dataclasses.replace(base, claims=(TutorClaim("Looks firm.", ClaimCategory.AI_INTERPRETATION, ()),))
    assert GroundingIssueCode.UNGROUNDED_CLAIM in _codes(validate_answer_grounding(bare, lesson))


def test_not_yet_available_evidence_cannot_support_a_claim(session):
    lesson = _lesson(session, Q.NOT_YET_DETERMINED_ITEMS, "10:00")
    base = lesson.answer_key.reference_answer
    snap = session.snapshot("10:00")
    i = [m.component for m in snap.maturity].index("day_type")
    maturity = _ref(lesson, f"/maturity/{i}/maturity")
    assert validate_answer_grounding(base, lesson).valid and maturity in {r for c in base.claims for r in c.evidence_refs}
    pending = build_tutor_lesson(session, dataclasses.replace(
        example_lesson(session, Q.NOT_YET_DETERMINED_ITEMS, "10:00"),
        allowed_domains=(EvidenceDomain.DATA_QUALITY, EvidenceDomain.MATURITY, EvidenceDomain.DAY_TYPE)))
    dt = next(i for i in pending.context.items() if i.label == "DAY_TYPE_V1 outcome")
    assert dt.value is None and dt.availability is Availability.NOT_YET_DETERMINED
    claim = TutorClaim("The day type is NEUTRAL_DAY.", ClaimCategory.LABORATORY_POLICY_RESULT, (dt.ref,))
    a = dataclasses.replace(pending.answer_key.reference_answer, claims=(claim,))
    assert GroundingIssueCode.EVIDENCE_NOT_AVAILABLE in _codes(validate_answer_grounding(a, pending))
    honest = dataclasses.replace(a, claims=(), unsupported_claims=(UnsupportedClaim(
        "The day type is not known yet.", EvidenceSupport.NOT_YET_DETERMINED, ("DAY_TYPE_V1 at 15:00 CT",),
        (dt.ref,)),))
    assert validate_answer_grounding(honest, pending).valid
    marked = dataclasses.replace(honest, unsupported_claims=(UnsupportedClaim("x", EvidenceSupport.SUPPORTED, ()),))
    assert GroundingIssueCode.UNSUPPORTED_MARKED_SUPPORTED in _codes(validate_answer_grounding(marked, pending))


def test_stale_last_price_is_not_presented_as_current(session):
    running = _lesson(session, Q.PRICE_VS_CASH_VWAP, "09:45")
    assert running.answer_key.observations[0].statement == "The last known price is 103 (traded at " \
        "2026-10-05T14:30:06.000000Z)."
    assert "PRICE_AT_LESSON_TIME" not in [c.claim_id for c in running.answer_key.rubric.common_incorrect_claims]
    stopped = _lesson(session, Q.PRICE_VS_CASH_VWAP, "16:00")  # the capture stopped at 15:30 CT
    claim = next(c for c in stopped.answer_key.rubric.common_incorrect_claims if c.claim_id == "PRICE_AT_LESSON_TIME")
    assert claim.support is EvidenceSupport.INSUFFICIENT_EVIDENCE and claim.why.startswith("capture is STOPPED")
    assert validate_answer_grounding(stopped.answer_key.reference_answer, stopped).valid


def test_insufficient_evidence_is_not_false(session):
    lesson = _lesson(session, Q.VALUE_OCCUPANCY, "10:00")
    key = lesson.answer_key
    assert key.support is EvidenceSupport.INSUFFICIENT_EVIDENCE and key.summary is None
    assert key.missing_dependencies == ("time outside value (NEEDS_IMPLEMENTATION)",)
    assert key.rubric.insufficient_evidence_is_correct
    assert [o.observation_id for o in key.observations] == ["CURRENT_RELATION"]  # what IS available is still taught
    u = key.reference_answer.unsupported_claims[0]
    assert u.support is EvidenceSupport.INSUFFICIENT_EVIDENCE
    early = _lesson(session, Q.PRICE_VS_CASH_VWAP, "08:00")
    assert early.answer_key.support is EvidenceSupport.NOT_YET_AVAILABLE and early.answer_key.summary is None


# --- quality ---------------------------------------------------------------------------------------

def test_quality_warnings_propagate_and_must_be_preserved(session):
    lesson = _lesson(session, Q.DATA_QUALITY, "10:20")  # after the 10:15 KNOWN_GAP became known
    ids = [w.warning_id for w in lesson.context.quality_warnings]
    assert "LESSON_TIME:dataset" in ids
    assert lesson.answer_key.summary == "QUALITY_QUALIFIED"
    assert "LESSON_TIME:dataset" in lesson.answer_key.rubric.quality_caveats
    assert [c.claim_id for c in lesson.answer_key.rubric.common_incorrect_claims] == ["PRISTINE"]
    dropped = dataclasses.replace(lesson.answer_key.reference_answer, quality_warnings=())
    assert GroundingIssueCode.QUALITY_WARNING_OMITTED in _codes(validate_answer_grounding(dropped, lesson))
    invented = dataclasses.replace(lesson.answer_key.reference_answer,
                                   quality_warnings=(*lesson.answer_key.reference_answer.quality_warnings, "X:y"))
    assert GroundingIssueCode.UNKNOWN_QUALITY_WARNING in _codes(validate_answer_grounding(invented, lesson))
    # the dataset warning reaches every lesson, even one not authorized for DATA_QUALITY
    narrow = build_tutor_lesson(session, dataclasses.replace(
        example_lesson(session, Q.PRICE_VS_CASH_VWAP, "10:20"),
        allowed_domains=(EvidenceDomain.PRICE, EvidenceDomain.VWAP)))
    assert "LESSON_TIME:dataset" in [w.warning_id for w in narrow.context.quality_warnings]
    assert not [i for i in narrow.context.items() if i.ref.pointer.startswith("/dataset_quality")]
    assert "QUALITY WARNINGS\n  LESSON_TIME:dataset: QUALITY_QUALIFIED" in render_view(student_view(narrow))


# --- maturity, changes -----------------------------------------------------------------------------

def test_initial_balance_lesson_knows_maturity(session):
    early, done = _lesson(session, Q.INITIAL_BALANCE_STATUS, "09:15"), _lesson(session, Q.INITIAL_BALANCE_STATUS,
                                                                             "09:30")
    assert early.answer_key.summary == "DEVELOPING"
    assert [c.claim_id for c in early.answer_key.rubric.common_incorrect_claims] == ["IB_COMPLETE"]
    assert done.answer_key.summary == "COMPLETE"
    assert done.answer_key.observations[1].statement == "The Initial Balance complete is 99.00 - 110.00."
    final = done.answer_key.rubric.common_incorrect_claims[0]
    assert final.claim_id == "IB_FINAL" and "later-received records" in final.why


def test_evidence_change_lesson(session):
    lesson = _lesson(session, Q.EVIDENCE_CHANGES, "10:05:01", "10:04:59")
    assert lesson.context.delta is not None and [s.role.value for s in lesson.context.snapshots] == [
        "COMPARE_FROM", "LESSON_TIME"]
    obs = {o.observation_id: o for o in lesson.answer_key.observations}
    assert obs["STATE_HASH"].value is True and obs["LATE_OBSERVATIONS"].value == 1
    assert "received up to 600.000000 s late" in obs["LATE_OBSERVATIONS"].statement
    assert "LATE_AS_NEW_ACTIVITY" in [c.claim_id for c in lesson.answer_key.rubric.common_incorrect_claims]
    delta = session.compare("10:04:59", "10:05:01")
    assert lesson.context.delta.delta_sha256 == lesson.context.delta.items[0].ref.source_sha256
    assert lesson.context.delta.from_snapshot_sha256 == delta.from_snapshot_sha256


# --- conventions and curriculum ----------------------------------------------------------------------

def test_value_area_conventions_stay_distinct(session):
    assert (LABORATORY_PROFILE_70.fraction, PLAYBOOK_NINJATRADER_68.fraction) == (
        LABORATORY_PROFILE_70.fraction.__class__("0.70"), PLAYBOOK_NINJATRADER_68.fraction.__class__("0.68"))
    assert LABORATORY_PROFILE_70.computed_by_laboratory and not PLAYBOOK_NINJATRADER_68.computed_by_laboratory
    lesson = _lesson(session, Q.VALUE_MIGRATION, "10:00", "09:30")
    conv = student_view(lesson)["context"]["value_area_convention"]
    assert (conv["convention_id"], conv["fraction"]) == ("LABORATORY_PROFILE_70", "0.70")
    with pytest.raises(ValueAreaConventionError):  # 68% is never applied to 70% Laboratory evidence
        build_tutor_lesson(session, dataclasses.replace(example_lesson(session, Q.VALUE_MIGRATION, "10:00", "09:30"),
                                                        value_area_convention_id="PLAYBOOK_NINJATRADER_68"))
    with pytest.raises(ValueAreaConventionError):  # a value-area lesson must state its convention
        dataclasses.replace(example_lesson(session, Q.VALUE_OCCUPANCY, "10:00"), value_area_convention_id=None)
    assert _lesson(session, Q.PRICE_VS_CASH_VWAP, "10:00").context.value_area_convention is None


def test_drysdale_is_registered_but_not_executable(session):
    assert DRYSDALE_MODULE in CURRICULUM_MODULES and not DRYSDALE_MODULE.executable
    assert DRYSDALE_MODULE.readiness is ModuleReadiness.NOT_READY_FOR_RULE_IMPLEMENTATION
    assert [t.title for t in DRYSDALE_MODULE.topics] == ["Price Discovery Continuation", "Fade Value Area Extremes",
                                                        "Return to Value", "VWAP Bounce"]
    by = {s: [d.dependency for d in DRYSDALE_MODULE.dependencies if d.status is s] for s in DependencyStatus}
    assert len(by[DependencyStatus.FACT_AVAILABLE_NOW]) == 13  # 0AB-A: bands, crossings, time outside, bars, ATR
    assert by[DependencyStatus.NEEDS_POLICY_DEFINITION] == ["VWAP value area (which band pair)", "breakout",
                                                            "acceptance", "backtest / retest", "first sign of strength",
                                                            "first sign of weakness", "rejection"]
    assert by[DependencyStatus.NEEDS_IMPLEMENTATION] == []
    source = next(s for s in CURRICULUM_SOURCES if s.source_id == DRYSDALE_MODULE.source_id)
    assert source.origin == "Chris Drysdale" and not source.redistributable_in_repository
    with pytest.raises(CurriculumNotReady, match="acceptance"):
        require_executable(DRYSDALE_MODULE.module_id)
    with pytest.raises(CurriculumNotReady):
        build_tutor_lesson(session, dataclasses.replace(example_lesson(session, Q.PRICE_VS_CASH_VWAP, "10:00"),
                                                        curriculum_module_id=DRYSDALE_MODULE.module_id))


def test_lesson_modes_are_educational_only():
    assert {m.value for m in LessonMode} == {"OBSERVE", "IDENTIFY", "COMPARE", "EXPLAIN_EVIDENCE"}


# --- serialization ---------------------------------------------------------------------------------

def test_payloads_are_canonical_deterministic_and_hashed(session):
    prior, cur, _ = session.paths
    fresh = ReplaySession(MarketReplay.load(cur, PROV, prior))
    for kind, at, frm, rv in ((Q.PRICE_VS_CASH_VWAP, "09:45", None, "10:15"), (Q.EVIDENCE_CHANGES, "10:05:01",
                                                                              "10:04:59", None)):
        a, b = _lesson(session, kind, at, frm, rv), _lesson(fresh, kind, at, frm, rv)
        assert a.definition_sha256 == b.definition_sha256
        for view in (lambda x: student_view(x), lambda x: student_view(x, LessonStage.POST_REVEAL), instructor_view):
            pa, pb = view(a), view(b)
            assert canonical_json(pa) == canonical_json(pb) and verify_payload(pa)
            assert pa[PAYLOAD_HASH_FIELD] == pb[PAYLOAD_HASH_FIELD]
    text = canonical_json(instructor_view(_lesson(session, Q.DATA_QUALITY, "10:20")))
    assert datetime.now(timezone.utc).isoformat()[:10] not in text and "generated" not in text
    tampered = student_view(a)
    tampered["stage"] = "ANSWER"
    assert not verify_payload(tampered)


def test_rendered_views_are_evidence_only(session):
    for kind, at, frm in ((Q.PRICE_VS_CASH_VWAP, "09:45", None), (Q.VALUE_MIGRATION, "10:00", "09:30"),
                          (Q.DATA_QUALITY, "10:20", None), (Q.VALUE_OCCUPANCY, "10:00", None)):
        lesson = _lesson(session, kind, at, frm)
        for text in (render_view(student_view(lesson)), render_view(instructor_view(lesson))):
            assert not [w for w in FORBIDDEN if w in text.lower()], kind
    assert relations(snapshot_document(session.snapshot("09:45")))  # the derived relation source


# --- CLI -------------------------------------------------------------------------------------------

def _run(*args):
    return subprocess.run([sys.executable, "scripts/dicks_lab_tutor_lesson.py", *map(str, args)], cwd=REPO,
                          env=fx_mod._ENV, capture_output=True, text=True)


def test_tutor_lesson_cli_smoke(session):
    prior, cur, _ = session.paths
    before = (prior.read_bytes(), cur.read_bytes())
    r = _run(cur, "--prior-db", prior, "--lesson", "vwap", "--at", "09:45", "--reveal-at", "10:15",
             "--analysis-commit", "a" * 40)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("LESSON LAB-PRICE_VS_CASH_VWAP-2026-10-05-094500") and "QUESTION  Where" in r.stdout
    assert "WITHHELD (not in this payload): hints, answer_key, future_outcome" in r.stdout
    assert "ANSWER KEY" not in r.stdout and "FUTURE OUTCOME" not in r.stdout
    i = _run(cur, "--prior-db", prior, "--lesson", "vwap", "--at", "09:45", "--reveal-at", "10:15", "--instructor",
             "--analysis-commit", "a" * 40)
    assert i.returncode == 0 and "ANSWER KEY  SUPPORTED: ABOVE" in i.stdout and "FUTURE OUTCOME" in i.stdout
    j = _run(cur, "--prior-db", prior, "--lesson", "changes", "--at", "10:05:01", "--from", "10:04:59", "--json",
             "--analysis-commit", "a" * 40)
    assert j.returncode == 0, j.stderr
    assert verify_payload(json.loads(j.stdout)) and json.loads(j.stdout)["stage"] == "QUESTION"
    bad = _run(cur, "--lesson", "changes", "--at", "10:05", "--analysis-commit", "a" * 40)
    assert bad.returncode != 0  # a comparison lesson needs --from
    assert (prior.read_bytes(), cur.read_bytes()) == before
