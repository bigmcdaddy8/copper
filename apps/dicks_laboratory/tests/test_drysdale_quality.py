"""0AB-C: Drysdale candidate quality scope, validation eligibility and the V4 tutor (DRYSDALE_CANDIDATE_QUALITY_V1).

Deterministic replay fixtures (the 0AB-B ones). Frozen DRYSDALE_V1 is read, never changed: its candidates inherit
the analysis status; the additive layer says which reason touches which evidence of each candidate.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from dicks_laboratory import drysdale_quality as dq
from dicks_laboratory.drysdale import CandidateState, SetupFamily, analyze
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.quality import DatasetQualityEvent
from dicks_laboratory.quality import DatasetQualityEvidenceType as Q
from dicks_laboratory.replay import MarketReplay
from dicks_laboratory.replay_player import ReplaySession
from dicks_laboratory.store import LaboratoryStore

sys.path.insert(0, str(Path(__file__).parent))
import test_drysdale as dr  # noqa: E402  (shared 0AB-B fixtures; that file stays frozen)

PROV = AnalysisProvenance("a" * 40, False)
CUR, ct = dr.CUR, dr.ct
NOLATE = dr.ROWS[:-1] + [(1, 100, 0)]  # the 08:55 PDC candidate stays complete; an 08:30:01 trade
ANCHOR = ct(CUR, 17, 0) - timedelta(days=1)
LATE_START = timedelta(microseconds=363)  # as observed on 2026-09-30 (capture began 0.000363 s after 17:00 CT)
REPO = Path(__file__).resolve().parents[3]
E, R = dq.Eligibility, dq.ReasonCode


@pytest.fixture(scope="module")
def prior(tmp_path_factory):
    return dr.fx_mod._db(tmp_path_factory.mktemp("dq-prior"), dr.PRIOR,
                         [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                         name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))


def _session(tmp_path, prior, name, rows=NOLATE, gaps=False, start_after=None, events=()):
    s = dr._session(tmp_path, prior, rows=rows, name=name, gaps=gaps)
    did = s.replay.current.dataset_id
    if start_after is not None:
        con = sqlite3.connect(s.db)
        con.execute("UPDATE datasets SET capture_started_at = ?", ((ANCHOR + start_after).isoformat(),))
        con.commit()
        con.close()
    if events:
        store = LaboratoryStore(s.db)
        store.save_quality_events(tuple(e(did) for e in events))
        store.close()
    if start_after is not None or events:
        s = ReplaySession(MarketReplay.load(s.db, PROV, prior))
    return s


def gap(start, end):
    return lambda did: DatasetQualityEvent(uuid4(), did, Q.KNOWN_GAP, "disconnect_to_reconnect",
                                           interval_start=start, interval_end=end)


def disconnect(at):
    return lambda did: DatasetQualityEvent(uuid4(), did, Q.SOURCE_DISCONNECTED, "source_disconnected", observed_at=at)


def audit(s, at):
    a = analyze(s, at)
    return a, dq.audit(a, s.snapshot(at))


def pdc(x):
    (c,) = [c for c in x.candidates if c.family is SetupFamily.PRICE_DISCOVERY_CONTINUATION
            and c.eligibility is not E.NOT_A_CANDIDATE]
    return c


def codes(c):
    return [(r.code, r.scope, r.materiality) for r in c.reasons]


def test_clean_boundary_and_no_event_is_eligible_unqualified(tmp_path, prior):
    a, x = audit(_session(tmp_path, prior, "clean"), "09:01")
    c = pdc(x)
    assert a.status == "AVAILABLE" and c.state is CandidateState.CANDIDATE and c.reasons == ()
    assert (x.boundary_status, c.eligibility, c.local_evidence_complete) == (dq.BoundaryStatus.PROVEN,
                                                                             E.ELIGIBLE_UNQUALIFIED, True)
    assert c.evidence_window_end_utc == c.completed_at_utc == ct(CUR, 8, 55)
    assert ANCHOR < c.evidence_window_start_utc <= c.first_event_utc - timedelta(minutes=5)
    assert dq.counts(x) == {"total_candidates": 1, "ELIGIBLE_UNQUALIFIED": 1, "ELIGIBLE_QUALITY_QUALIFIED": 0,
                            "NOT_ELIGIBLE": 0}


def test_boundary_only_qualification_is_provenance_not_impairment(tmp_path, prior):
    a, x = audit(_session(tmp_path, prior, "boundary", start_after=LATE_START), "09:01")
    c = pdc(x)
    assert a.status == "QUALITY_QUALIFIED" and c.state is CandidateState.QUALITY_QUALIFIED  # frozen V1, unchanged
    assert x.boundary_status is dq.BoundaryStatus.NOT_PROVEN and x.capture_started_at == ANCHOR + LATE_START
    assert codes(c) == [(R.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR, dq.Scope.SESSION_BOUNDARY, dq.Materiality.PROVENANCE)]
    assert c.reasons[0].duration == LATE_START and "not proven" in c.reasons[0].detail
    assert (c.gaps_overlapping_window, c.local_evidence_complete) == (0, True)
    assert c.eligibility is E.ELIGIBLE_QUALITY_QUALIFIED  # not excluded merely for a scoped boundary qualification
    assert [code for _, code in x.explained] == ["CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR"] * len(x.explained)


def test_known_gap_in_the_setup_window_is_not_eligible(tmp_path, prior):
    a, x = audit(dr._session(tmp_path, prior, rows=dr.GAPPY, name="gappy", gaps=True), "10:20")
    (c,) = [c for c in x.candidates if c.eligibility is not E.NOT_A_CANDIDATE]
    assert c.family is SetupFamily.RETURN_TO_VALUE and c.state is CandidateState.QUALITY_QUALIFIED
    assert c.evidence_window_start_utc < ct(CUR, 10, 15) < c.evidence_window_end_utc
    assert codes(c)[0] == (R.KNOWN_GAP, dq.Scope.SETUP_EVIDENCE_WINDOW, dq.Materiality.LOCAL_EVIDENCE)
    assert (c.gaps_overlapping_window, c.local_evidence_complete, c.eligibility) == (1, False, E.NOT_ELIGIBLE)
    assert "KNOWN_GAP/SETUP_EVIDENCE_WINDOW/LOCAL_EVIDENCE" in c.eligibility_basis
    assert dq.counts(x)["NOT_ELIGIBLE"] == 1 and dq.counts(x)["total_candidates"] == 1


def test_gap_outside_the_window_but_upstream_of_the_bands_is_qualified(tmp_path, prior):
    s = _session(tmp_path, prior, "upstream", events=(gap(ct(CUR, 2, 0), ct(CUR, 2, 0, 30)),))
    a, x = audit(s, "09:01")
    c = pdc(x)
    assert c.state is CandidateState.QUALITY_QUALIFIED
    assert codes(c) == [(R.KNOWN_GAP, dq.Scope.GLOBEX_VWAP, dq.Materiality.UPSTREAM_REFERENCE)]
    assert (c.gaps_overlapping_window, c.gaps_upstream, c.local_evidence_complete) == (0, 1, True)
    assert c.eligibility is E.ELIGIBLE_QUALITY_QUALIFIED  # the bands the window reads accumulated over the gap


def test_gap_after_the_candidate_is_not_a_dependency(tmp_path, prior):
    a, x = audit(_session(tmp_path, prior, "after", gaps=True), "10:20")  # KNOWN_GAP 10:15:00-10:15:30
    c = pdc(x)
    assert a.status == "QUALITY_QUALIFIED" and c.candidate_quality == "QUALITY_QUALIFIED"  # inherited (frozen V1)
    assert codes(c) == [(R.KNOWN_GAP, dq.Scope.GLOBEX_VWAP, dq.Materiality.NOT_A_DEPENDENCY)]
    assert (c.gaps_after_candidate, c.eligibility) == (1, E.ELIGIBLE_UNQUALIFIED)


def test_stale_price_active_interruption(tmp_path, prior):
    later = _session(tmp_path, prior, "stale-later", events=(disconnect(ct(CUR, 9, 10)),))
    a, x = audit(later, "09:20")
    snap = later.snapshot("09:20")
    assert snap.dataset_quality.active_interruption is not None and a.status == "QUALITY_QUALIFIED"
    c = pdc(x)
    assert codes(c) == [(R.ACTIVE_INTERRUPTION, dq.Scope.CURRENT_STATE, dq.Materiality.NOT_A_DEPENDENCY)]
    assert c.eligibility is E.ELIGIBLE_UNQUALIFIED  # the last price may be stale; the 08:55 candidate's bars are not
    inside = _session(tmp_path, prior, "stale-inside", events=(disconnect(ct(CUR, 8, 52)),))
    _, y = audit(inside, "09:01")
    (d,) = [d for d in y.candidates if d.eligibility is not E.NOT_A_CANDIDATE]
    assert codes(d)[0] == (R.ACTIVE_INTERRUPTION, dq.Scope.SETUP_EVIDENCE_WINDOW, dq.Materiality.LOCAL_EVIDENCE)
    assert d.eligibility is E.NOT_ELIGIBLE


def test_multiple_reasons_are_each_scoped(tmp_path, prior):
    s = _session(tmp_path, prior, "multi", start_after=LATE_START, events=(gap(ct(CUR, 2, 0), ct(CUR, 2, 0, 30)),))
    a, x = audit(s, "09:01")
    c = pdc(x)
    assert codes(c) == [(R.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR, dq.Scope.SESSION_BOUNDARY, dq.Materiality.PROVENANCE),
                        (R.KNOWN_GAP, dq.Scope.GLOBEX_VWAP, dq.Materiality.UPSTREAM_REFERENCE)]
    assert c.eligibility is E.ELIGIBLE_QUALITY_QUALIFIED and len(c.eligibility_basis) == 2
    assert {code for _, code in x.explained} == {"CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR", "KNOWN_GAP"}


def test_dependency_proof_and_unexplained_reasons(tmp_path, prior):
    s = _session(tmp_path, prior, "proof", start_after=LATE_START)
    a, x = audit(s, "09:01")
    steps = {p.step: p for p in x.propagation}
    vw = steps["Globex VWAP (snapshot SESSION_OPEN)"]
    assert vw.quality_output == steps["VWAP_BANDS_GLOBEX_V1 / DRYSDALE_VALUE_AREA_V1"].quality_output == a.status
    assert steps["DRYSDALE_SETUP_CANDIDATES_V1 candidate"].quality_output == a.status
    assert all(c.quality == a.status for c in a.candidates)  # every candidate inherits the analysis status
    payload = json.loads(json.dumps(dq.audit_payload(x)))
    assert payload["schema"] == "DRYSDALE_CANDIDATE_QUALITY_V1" and len(payload["propagation"]) == 6
    assert dq.audit_sha256(x) == dq.audit_sha256(dq.audit(a, s.snapshot("09:01")))
    assert dq.classify_reason("something new upstream") is R.UNEXPLAINED_UPSTREAM_REASON
    assert dq.classify_reason("lifecycle OPEN (not FINALIZED)") is R.LIFECYCLE_NOT_FINALIZED
    assert dq.classify_reason("OVERNIGHT window not captured through the clock") is \
        R.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR
    with pytest.raises(ValueError):
        dq.audit(a, s.snapshot("09:00"))  # one cutoff for both


# --- tutor (TUTOR_SYSTEM_PROMPT_V4_DRYSDALE_QUALITY) ---------------------------------------------------------

def _tutor():
    from dicks_laboratory import tutor_ai as ta
    from dicks_laboratory import tutor_evidence as te
    return ta, te


def test_v4_lesson_cites_scope_and_v3_stays_registered(tmp_path, prior):
    ta, te = _tutor()
    s = dr._session(tmp_path, prior, rows=dr.GAPPY, name="gappy-v4", gaps=True)
    v3 = te.build_tutor_lesson(s, te.drysdale_lesson(s, "10:20"))
    v4 = te.build_tutor_lesson(s, te.drysdale_lesson(s, "10:20", question=9, quality_scope=True))
    assert ta.build_request(v3, te.LessonStage.QUESTION).system_prompt_version == "TUTOR_SYSTEM_PROMPT_V3_DRYSDALE"
    assert ta.build_request(v4, te.LessonStage.QUESTION).system_prompt_version == ta.DRYSDALE_QUALITY_SYSTEM_PROMPT_VERSION
    assert te.SourceRole.DRYSDALE_QUALITY not in {e.role for e in v3.context.snapshots}
    assert v4.definition.question == te.DRYSDALE_QUALITY_QUESTIONS[9] and v4.definition.lesson_id.endswith("-QSCOPE")
    # V3 is reproducible: its prompt hash is the one recorded by the 0AB-B real-data run records
    rec = json.loads((REPO / "docs/dicks_laboratory/evidence/0AB-B/2026-10-01_lesson_1000_run_record.json").read_text())
    assert hashlib.sha256(ta.PROMPTS["TUTOR_SYSTEM_PROMPT_V3_DRYSDALE"].encode()).hexdigest() == \
        rec["system_prompt_sha256"]
    assert ta.DRYSDALE_QUALITY_SYSTEM_PROMPT.startswith(ta.DRYSDALE_SYSTEM_PROMPT[:-len("Return only the structured answer.")])
    q = next(e for e in v4.context.snapshots if e.role is te.SourceRole.DRYSDALE_QUALITY)
    doc = v4.document(q.snapshot_sha256)
    for item in q.items:
        v = te.resolve_pointer(doc, item.ref.pointer)
        assert item.value == (json.dumps(v, sort_keys=True, separators=(",", ":")) if isinstance(v, dict | list) else v)
    labels = {i.label for i in q.items}
    assert any("known gaps overlapping the candidate evidence window" in x for x in labels)
    assert any(o.observation_id.startswith("QS_RETURN_TO_VALUE_DOWN_REASON") for o in v4.answer_key.observations)
    assert "QUALIFIED_MEANS_UNRELIABLE" in {c.claim_id for c in v4.answer_key.rubric.common_incorrect_claims}
    assert te.validate_answer_grounding(v4.answer_key.reference_answer, v4).valid


def test_tutor_explanation_preserves_quality_scope(tmp_path, prior):
    ta, te = _tutor()
    s = dr._session(tmp_path, prior, rows=dr.GAPPY, name="gappy-guard", gaps=True)
    lesson = te.build_tutor_lesson(s, te.drysdale_lesson(s, "10:20", question=9, quality_scope=True))
    q = next(e for e in lesson.context.snapshots if e.role is te.SourceRole.DRYSDALE_QUALITY)
    base = json.loads(ta.answer_to_model_json(lesson.answer_key.reference_answer, lesson))
    ok = ta.run_tutor(lesson, te.LessonStage.QUESTION, ta.FakeTutorModel([json.dumps(base)]), allow_repair=False)
    assert ok.status is ta.TutorRunStatus.GROUNDED, ok.issues
    assert ta.run_record(ok)["system_prompt_version"] == ta.DRYSDALE_QUALITY_SYSTEM_PROMPT_VERSION

    def item(label_part):
        return next(i for i in q.items if label_part in i.label)

    def run(claim, text=None):
        answer = dict(base)
        answer["claims"] = base["claims"] + [claim]
        if text:
            answer["answer_text"] = text
        return ta.run_tutor(lesson, te.LessonStage.QUESTION, ta.FakeTutorModel([json.dumps(answer)]),
                            allow_repair=False)

    def claim(statement, it, value, category="QUALITY_WARNING"):
        ref = {"source": "DRYSDALE_QUALITY", "pointer": it.ref.pointer}
        return {"statement": statement, "category": category, "evidence_refs": [ref],
                "asserted": [{"ref": ref, "value": value}], "curriculum_source_id": None}

    rtv_mat = item("RETURN_TO_VALUE DOWN (RTV-DOWN-20261005T1515Z) quality reason 1 materiality")
    local = claim("The RETURN_TO_VALUE DOWN candidate's own evidence window overlaps a KNOWN_GAP, so its local "
                  "evidence is impaired.", rtv_mat, "LOCAL_EVIDENCE")
    assert run(local).status is ta.TutorRunStatus.GROUNDED
    rtv_el = item("RETURN_TO_VALUE DOWN (RTV-DOWN-20261005T1515Z) validation eligibility")
    assert run(claim("Laboratory V1 eligibility: NOT_ELIGIBLE, the candidate evidence is unusable for validation.",
                     rtv_el, "NOT_ELIGIBLE", "LABORATORY_POLICY_RESULT")).status is ta.TutorRunStatus.GROUNDED
    pdc_mat = item("PRICE_DISCOVERY_CONTINUATION UP (PDC-UP-20261005T1340Z) quality reason 1 materiality")
    misstated = claim("The PRICE_DISCOVERY_CONTINUATION UP instance is unreliable because it is quality-qualified.",
                      pdc_mat, "NOT_A_DEPENDENCY")
    r = run(misstated)
    assert r.status is ta.TutorRunStatus.GROUNDING_FAILED
    assert ta.GuardCode.QUALITY_SCOPE_MISSTATED in {i.code for i in r.issues}
    wrong_value = claim("The gap overlaps the PRICE_DISCOVERY_CONTINUATION UP evidence window.", pdc_mat,
                        "LOCAL_EVIDENCE")
    assert run(wrong_value).status is ta.TutorRunStatus.GROUNDING_FAILED  # the evidence decides, not the wording
    # the answer text may say "unusable" only when some claim asserts NOT_ELIGIBLE / LOCAL_EVIDENCE (here: the RTV one)
    assert run(claim("The gap is after this instance.", pdc_mat, "NOT_A_DEPENDENCY"),
               text="The RETURN_TO_VALUE DOWN candidate is unusable for validation.").status is \
        ta.TutorRunStatus.GROUNDED


def test_boundary_only_tutor_claim(tmp_path, prior):
    ta, te = _tutor()
    s = _session(tmp_path, prior, "boundary-tutor", start_after=LATE_START)
    lesson = te.build_tutor_lesson(s, te.drysdale_lesson(s, "09:01", question=9, quality_scope=True))
    q = next(e for e in lesson.context.snapshots if e.role is te.SourceRole.DRYSDALE_QUALITY)
    b = next(i for i in q.items if i.ref.pointer == "/boundary_status")
    assert b.value == "NOT_PROVEN"
    base = json.loads(ta.answer_to_model_json(lesson.answer_key.reference_answer, lesson))
    ref = {"source": "DRYSDALE_QUALITY", "pointer": b.ref.pointer}
    gaps = next(i for i in q.items if "known gaps overlapping" in i.label and "PDC-UP" in i.label)
    gref = {"source": "DRYSDALE_QUALITY", "pointer": gaps.ref.pointer}
    base["claims"] += [
        {"statement": "The candidate is quality-qualified because exact 17:00 CT Globex-boundary completeness cannot "
                      "be proven.", "category": "QUALITY_WARNING", "evidence_refs": [ref],
         "asserted": [{"ref": ref, "value": "NOT_PROVEN"}], "curriculum_source_id": None},
        {"statement": "No known gap overlaps the setup evidence window.", "category": "QUALITY_WARNING",
         "evidence_refs": [gref], "asserted": [{"ref": gref, "value": 0}], "curriculum_source_id": None}]
    ok = ta.run_tutor(lesson, te.LessonStage.QUESTION, ta.FakeTutorModel([json.dumps(base)]), allow_repair=False)
    assert ok.status is ta.TutorRunStatus.GROUNDED, ok.issues
    base["claims"].append({"statement": "The boundary qualification makes this setup invalid.",
                           "category": "QUALITY_WARNING", "evidence_refs": [ref],
                           "asserted": [{"ref": ref, "value": "NOT_PROVEN"}], "curriculum_source_id": None})
    bad = ta.run_tutor(lesson, te.LessonStage.QUESTION, ta.FakeTutorModel([json.dumps(base)]), allow_repair=False)
    assert ta.GuardCode.QUALITY_SCOPE_MISSTATED in {i.code for i in bad.issues}
    base["claims"].pop()
    base["answer_text"] = "The candidate is unreliable."  # nothing here asserts LOCAL_EVIDENCE or NOT_ELIGIBLE
    text = ta.run_tutor(lesson, te.LessonStage.QUESTION, ta.FakeTutorModel([json.dumps(base)]), allow_repair=False)
    assert [i.where for i in text.issues if i.code is ta.GuardCode.QUALITY_SCOPE_MISSTATED] == ["answer_text"]


# --- freeze integrity -------------------------------------------------------------------------------------

MARKET_RULE_FILES = ("apps/dicks_laboratory/src/dicks_laboratory/drysdale.py",
                     "docs/dicks_laboratory/DRYSDALE_VWAP_TRAINING_CANDIDATES.md",
                     "apps/dicks_laboratory/tests/test_drysdale.py",
                     "apps/dicks_laboratory/src/dicks_laboratory/price_action.py")


def test_drysdale_v1_market_rule_freeze_hashes_unchanged():
    text = (REPO / "docs/dicks_laboratory/evidence/0AB-B/FREEZE.md").read_text()
    frozen = dict((p, h) for h, p in re.findall(r"^([0-9a-f]{64})  (\S+)$", text, re.MULTILINE))
    for path in MARKET_RULE_FILES:
        assert hashlib.sha256((REPO / path).read_bytes()).hexdigest() == frozen[path], path


# --- CLI smoke ------------------------------------------------------------------------------------------

def test_quality_scope_lesson_cli_smoke(tmp_path, prior):
    s = dr._session(tmp_path, prior, rows=dr.GAPPY, name="gappy-cli", gaps=True)
    before = s.db.read_bytes()
    r = dr._cli("dicks_lab_tutor_lesson.py", s.db, "--prior-db", prior, "--lesson", "drysdale", "--at", "10:20",
                "--question", "10", "--quality-scope", "--instructor", "--analysis-commit", "a" * 40)
    assert r.returncode == 0, r.stderr
    assert "DRYSDALE_VALIDATION_ELIGIBILITY_V1" in r.stdout and "LOCAL_EVIDENCE" in r.stdout
    assert dr._cli("dicks_lab_tutor_lesson.py", s.db, "--lesson", "drysdale", "--at", "10:20", "--question", "11",
                   "--quality-scope", "--analysis-commit", "a" * 40).returncode != 0
    assert s.db.read_bytes() == before
