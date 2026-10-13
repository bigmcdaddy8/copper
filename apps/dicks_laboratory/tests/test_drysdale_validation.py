"""0AB-D: Drysdale prospective validation machinery (DRYSDALE_PROSPECTIVE_VALIDATION_V1).

Synthetic records for the registered cohort rules (flags, minimums, classification, strata, quality accounting,
overlap, Human-review sample); the 0AB-B replay fixtures for the per-date record (sequence, semantics, knowledge
time, determinism, withdrawn candidates); a synthetic campaign-dated fixture for the access guard. No campaign data.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import random
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from dicks_laboratory import drysdale as dry
from dicks_laboratory import drysdale_validation as dv
from dicks_laboratory.drysdale import analyze
from dicks_laboratory.replay import MarketReplay
from dicks_laboratory.replay_player import ReplaySession

sys.path.insert(0, str(Path(__file__).parent))
import test_drysdale as dr  # noqa: E402  (0AB-B fixtures; frozen)
import test_drysdale_quality as tq  # noqa: E402  (0AB-C fixtures)

REPO = Path(__file__).resolve().parents[3]
C = dv.Classification
UTC = timezone.utc


# --- synthetic records -----------------------------------------------------------------------------------------

def cand(cid="PDC-UP-1", family="PRICE_DISCOVERY_CONTINUATION", direction="UP", td="2026-10-12", minutes=900,
         eligibility="ELIGIBLE_QUALITY_QUALIFIED", tags=("BOUNDARY_PROVENANCE",),
         combo="CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE", window=None, **kw):
    short = {f.value: dv.SHORT[f] for f in dv.FAMILIES}[family]
    done = dv.anchor_of(date.fromisoformat(td)) + timedelta(minutes=minutes)
    w = window or (done - timedelta(minutes=20), done)
    c = {"candidate_id": cid, "family": family, "short": short, "direction": direction, "trading_date": td,
         "completed_at_utc": done.isoformat(), "minutes_since_anchor": minutes,
         "stratum": dv.stratum(done, date.fromisoformat(td)).value, "condition_bars": [1, 2, 4, 5],
         "evidence_window_utc": [w[0].isoformat(), w[1].isoformat()], "eligibility": eligibility,
         "eligibility_at_first_known": eligibility, "quality_tags": list(tags), "reason_combination": combo,
         "knowledge": {"resolved": True, "receipt_delay_seconds": "0"}, "lookahead_violations": [],
         "sequence_violations": [], "semantic_violations": [], "family_facts": None}
    c.update(kw)
    return c


def rec(td, cands=(), status="ELIGIBLE", identical=True):
    return {"trading_date": td, "dataset_id": f"ds-{td}", "contract": "ES-2026-12", "date_status": status,
            "lifecycle_at_final_knowledge": "FINALIZED", "analysis_status": "QUALITY_QUALIFIED",
            "analysis_reason_codes": ["CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR"], "known_gaps": [],
            "active_interruption": False, "determinism": {"identical": identical}, "candidates": list(cands),
            "withdrawn_or_revised": [],
            "funnel": {f.value: {"instances": 0, "conditions": dv.N_CONDITIONS[f], "policies": [],
                                 "reached_at_least": [0] * dv.N_CONDITIONS[f],
                                 "satisfied_by_condition": [0] * dv.N_CONDITIONS[f], "first_unsatisfied": {}}
                       for f in dv.FAMILIES}}


DATES = [d.isoformat() for d in dv.COHORT_DATES]
FAM = [f.value for f in dv.FAMILIES]


def cohort(per_date: list[int], families=None, **kw):
    """Records for the first len(per_date) cohort dates with that many eligible candidates (families cycle)."""
    recs, k = [], 0
    for td, n in zip(DATES, per_date):
        cs = []
        for i in range(n):
            f = (families or FAM)[k % len(families or FAM)]
            k += 1
            cs.append(cand(f"{f[:3]}-{td}-{i}", family=f, td=td, minutes=60 + 30 * i,
                           window=(dv.anchor_of(date.fromisoformat(td)) + timedelta(minutes=60 * i),
                                   dv.anchor_of(date.fromisoformat(td)) + timedelta(minutes=60 * i + 10))))
        recs.append(rec(td, cs))
    return dv.cohort_summary(recs, **kw)


def test_zero_candidate_dates_and_scarcity_flag():
    s = cohort([0] * 7 + [3] * 5)  # 7 of 12 eligible dates with zero candidates: > 50%
    assert s["flags"]["CANDIDATE_SCARCITY_CHALLENGED"] and s["classification"] == C.PASS_WITH_CHALLENGES.value
    assert s["all_families"]["dates"] == {"zero": 7, "one": 0, "multiple": 5}
    assert s["dates"]["eligible"] == 12 and s["dates"]["excluded"]["2026-11-06"] == "NOT_CAPTURED"
    assert not cohort([0] * 6 + [3] * 6)["flags"]["CANDIDATE_SCARCITY_CHALLENGED"]  # exactly 50%: not > 50%


def test_high_density_flag():
    assert cohort([21] * 10)["flags"]["CANDIDATE_DENSITY_CHALLENGED"]  # median 21 > 20
    s = cohort([20] * 10)
    assert not s["flags"]["CANDIDATE_DENSITY_CHALLENGED"] and s["flags"]["_inputs"]["median_eligible_per_date"] == "20"
    assert s["classification"] == C.PASS.value


def test_family_dominance_flag_and_its_minimum():
    pdc = "PRICE_DISCOVERY_CONTINUATION"
    s = cohort([3] * 10, families=[pdc] * 6 + [FAM[1]])  # 30 eligible: PDC share > 80%
    assert s["flags"]["FAMILY_DOMINANCE_FOR_REVIEW"] and s["classification"] == C.PASS_WITH_CHALLENGES.value
    s = cohort([2] * 10, families=[pdc] * 4 + [FAM[1]])  # 20 eligible, PDC exactly 80%: not > 80%
    assert s["flags"]["FAMILY_DOMINANCE_FOR_REVIEW"] is False
    s = cohort([1] * 10 + [0] * 5, families=[pdc])  # 10 eligible < 20: not evaluated
    assert s["flags"]["FAMILY_DOMINANCE_FOR_REVIEW"] is None
    assert s["sample_rules"]["distribution_conclusions"] == "INCONCLUSIVE"


def test_minimum_cohort_and_candidate_rules():
    s = cohort([3] * 9)
    assert s["dates"]["eligible"] == 9 and s["classification"] == C.INCONCLUSIVE.value
    assert s["families"]["PRICE_DISCOVERY_CONTINUATION"]["eligible_candidates"] == 7  # still reported
    s = cohort([2] * 9 + [1])  # 10 dates, 19 candidates
    assert s["classification"] == C.PASS.value and s["sample_rules"]["distribution_conclusions"] == "INCONCLUSIVE"
    assert cohort([2] * 10)["sample_rules"]["distribution_conclusions"] == "INTERPRETABLE"


def test_per_family_sample_too_small_is_not_invalid():
    s = cohort([2] * 10, families=["PRICE_DISCOVERY_CONTINUATION"] * 4 + ["VWAP_BOUNCE"])  # 16 PDC, 4 BOUNCE
    assert s["sample_rules"]["family_sample_too_small"] == ["FADE_VALUE_AREA_EXTREME", "RETURN_TO_VALUE",
                                                            "VWAP_BOUNCE"]
    assert s["families"]["VWAP_BOUNCE"]["eligible_candidates"] == 4 and s["families"]["VWAP_BOUNCE"]["sample_too_small"]
    assert not s["families"]["PRICE_DISCOVERY_CONTINUATION"]["sample_too_small"]
    assert s["curriculum"]["families_too_sparse_for_lessons"] == s["sample_rules"]["family_sample_too_small"]
    assert s["classification"] == C.PASS.value  # sparsity never invalidates a family (PDC 80%: not > 80%)


def test_quality_accounting_overlapping_subcounts_and_exact_combinations():
    both = "CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/PROVENANCE+KNOWN_GAP/UPSTREAM_REFERENCE"
    cs = [cand("a"), cand("b", tags=("BOUNDARY_LOCAL_EVIDENCE",),
                          combo="CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR/LOCAL_EVIDENCE"),
          cand("c", tags=("BOUNDARY_PROVENANCE", "UPSTREAM_REFERENCE"), combo=both),
          cand("d", eligibility="NOT_ELIGIBLE", tags=(), combo="KNOWN_GAP/LOCAL_EVIDENCE"),
          cand("e", eligibility="ELIGIBLE_UNQUALIFIED", tags=(), combo="")]
    q = dv.quality_counts(cs)
    assert (q["total"], q["ELIGIBLE_UNQUALIFIED"], q["ELIGIBLE_QUALITY_QUALIFIED"], q["NOT_ELIGIBLE"]) == (5, 1, 3, 1)
    assert q["eligible_quality_qualified_subcounts"] == {"BOUNDARY_PROVENANCE": 2, "BOUNDARY_LOCAL_EVIDENCE": 1,
                                                         "UPSTREAM_REFERENCE": 1}  # c counted twice (overlap)
    assert sum(q["eligible_quality_qualified_combinations"].values()) == 3 and \
        q["eligible_quality_qualified_combinations"][both] == 1  # but once in the combinations
    assert q["not_eligible_combinations"] == {"KNOWN_GAP/LOCAL_EVIDENCE": 1} and q["coherent"]
    assert not dv.quality_counts(cs + [cand("x", combo="UNEXPLAINED_UPSTREAM_REASON/UNKNOWN",
                                            eligibility="NOT_ELIGIBLE")])["coherent"]


def test_strata_assignment_and_first_hour():
    td = date(2026, 10, 13)

    def at(hh, mm, day=td):
        return datetime.combine(day, datetime.min.time().replace(hour=hh, minute=mm), tzinfo=dv.CT).astimezone(UTC)

    eve = td - timedelta(days=1)
    assert dv.stratum(at(17, 5, eve), td) is dv.Stratum.FIRST_GLOBEX_HOUR
    assert dv.stratum(at(18, 0, eve), td) is dv.Stratum.FIRST_GLOBEX_HOUR  # reference <= 18:00
    assert dv.stratum(at(18, 5, eve), td) is dv.Stratum.LATER_OVERNIGHT
    assert dv.stratum(at(8, 30), td) is dv.Stratum.LATER_OVERNIGHT  # bar 08:25-08:30 lies inside [17:00, 08:30)
    assert dv.stratum(at(8, 35), td) is dv.Stratum.US_CASH_SESSION
    assert dv.stratum(at(15, 0), td) is dv.Stratum.US_CASH_SESSION
    assert dv.stratum(at(15, 5), td) is dv.Stratum.POST_CASH and dv.stratum(at(16, 0), td) is dv.Stratum.POST_CASH
    with pytest.raises(ValueError):
        dv.stratum(at(16, 5), td)
    dst = date(2026, 11, 2)  # Sunday 2026-11-01 17:00 CST anchor (DST ended that morning)
    assert dv.stratum(at(18, 0, date(2026, 11, 1)), dst) is dv.Stratum.FIRST_GLOBEX_HOUR
    assert dv.stratum(at(18, 5, date(2026, 11, 1)), dst) is dv.Stratum.LATER_OVERNIGHT
    s = cohort([1] * 10, families=["PRICE_DISCOVERY_CONTINUATION"])  # every candidate at anchor + 60 min
    assert s["first_hour"]["candidates"] == 10 and s["first_hour"]["quality"]["eligible_quality_qualified_subcounts"][
        "BOUNDARY_PROVENANCE"] == 10
    assert s["families"]["PRICE_DISCOVERY_CONTINUATION"]["by_stratum"]["FIRST_GLOBEX_HOUR"]["count"] == 10


def test_overlap_definitions_and_combinations():
    a0 = dv.anchor_of(date(2026, 10, 12))
    w = lambda m0, m1: (a0 + timedelta(minutes=m0), a0 + timedelta(minutes=m1))  # noqa: E731
    cs = [cand("p", window=w(0, 30), minutes=30),
          cand("r", family="RETURN_TO_VALUE", direction="DOWN", window=w(20, 40), minutes=40),
          cand("b", family="VWAP_BOUNCE", window=w(40, 50), minutes=50),  # touches r's end: no overlap
          cand("p2", window=w(25, 30), minutes=30)]
    o = dv.overlaps(cs)
    assert o["same_time_pairs"] == 1 and o["sequence_overlap_pairs"] == 3
    assert o["pair_combinations"] == {"PDC+PDC": 1, "PDC+RTV": 2} and o["family_overlap_pairs"] == 2
    assert o["directional_conflict_pairs"] == 2 and o["overlapping_ids"] == ["p", "p2", "r"]


def test_human_review_sample_is_deterministic_and_not_by_appearance():
    cs = [cand(f"PDC-{i}", td=DATES[i % 3], minutes=m) for i, m in enumerate([300, 100, 900, 500, 700])]
    cs.append(cand("RTV-0", family="RETURN_TO_VALUE", minutes=50))
    a = dv.human_review_sample(cs)
    shuffled = cs[:]
    random.Random(7).shuffle(shuffled)
    assert dv.human_review_sample(shuffled) == a
    # earliest by (date, completion, id), then the lower median of the rest by minutes since the anchor
    # rest by minutes: PDC-1 100, PDC-3 500, PDC-4 700, PDC-2 900 -> lower median PDC-3
    assert a["PRICE_DISCOVERY_CONTINUATION"] == [f"{DATES[0]}/PDC-0", f"{DATES[0]}/PDC-3"]
    assert a["RETURN_TO_VALUE"] == [f"{DATES[0]}/RTV-0"] and a["VWAP_BOUNCE"] == []  # fewer than two: all


def test_classification_fixtures():
    ok = dict(determinism_failures=0, lookahead_defects=0, knowledge_unresolved=0, sequence_or_semantic_violations=0,
              violating_candidates=0, attribution=None, harness_errors=0, quality_coherent=True, eligible_dates=12,
              flags={"CANDIDATE_DENSITY_CHALLENGED": False})
    assert dv.classify(**ok) == (C.PASS, [])
    assert dv.classify(**{**ok, "flags": {"CANDIDATE_SCARCITY_CHALLENGED": True}})[0] is C.PASS_WITH_CHALLENGES
    assert dv.classify(**{**ok, "eligible_dates": 9})[0] is C.INCONCLUSIVE
    assert dv.classify(**{**ok, "determinism_failures": 1})[0] is C.BLOCKED
    assert dv.classify(**{**ok, "lookahead_defects": 1, "eligible_dates": 3})[0] is C.BLOCKED  # before INCONCLUSIVE
    pending = {**ok, "sequence_or_semantic_violations": 2, "violating_candidates": 2}
    assert dv.classify(**pending) == (C.BLOCKED, ["2 sequence / semantic violation(s) pending investigation"])
    assert dv.classify(**{**pending, "attribution": dv.Attribution.FROZEN_RULE})[0] is C.FAIL
    assert dv.classify(**{**pending, "violating_candidates": 1, "attribution": dv.Attribution.FROZEN_RULE})[0] \
        is C.BLOCKED  # once is a defect to fix, not "repeatedly"
    assert dv.classify(**{**pending, "attribution": dv.Attribution.HARNESS})[0] is C.BLOCKED
    assert dv.classify(**{**ok, "quality_coherent": False})[0] is C.BLOCKED
    s = cohort([2] * 12)
    s_bad = dv.cohort_summary([rec(DATES[0], [cand(sequence_violations=["RETEST_AFTER_ACCEPTANCE"])])] +
                              [rec(td, [cand(f"x{td}", td=td)]) for td in DATES[1:12]])
    assert s["classification"] == C.PASS.value and s_bad["classification"] == C.BLOCKED.value
    assert dv.cohort_summary([rec(td, [cand(f"y{td}", td=td)], identical=td != DATES[0]) for td in DATES[:12]])[
        "classification"] == C.BLOCKED.value


def test_excluded_dates_keep_their_reason_and_are_not_dropped_silently():
    recs = [rec(td, [cand(f"z{td}", td=td)]) for td in DATES[:11]] + [rec(DATES[11], status="NOT_FINALIZED")]
    s = dv.cohort_summary(recs)
    assert s["dates"]["eligible"] == 11 and s["dates"]["captured"] == 12
    assert s["dates"]["excluded"][DATES[11]] == "NOT_FINALIZED" and len(s["dates"]["excluded"]) == 9
    assert dv.cohort_summary(recs + [rec("2026-10-17")])["unexpected_records"] == ["2026-10-17"]
    err = dv.error_record(date.fromisoformat(DATES[12]), "es.sqlite3", "IndexError: boom")
    s = dv.cohort_summary(recs + [err])  # a captured date that could not be evaluated is never dropped
    assert s["dates"]["captured"] == 13 and s["dates"]["excluded"][DATES[12]] == "HARNESS_ERROR"
    assert s["classification"] == C.BLOCKED.value and s["implementation"]["harness_errors"] == 1


# --- per-date record on the replay fixtures ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def prior(tmp_path_factory):
    return dr.fx_mod._db(tmp_path_factory.mktemp("dv-prior"), dr.PRIOR,
                         [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                         name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))


def _pdc(rec):
    (c,) = [c for c in rec["candidates"] if c["short"] == "PDC"]
    return c


def test_date_record_clean_candidate_sequence_semantics_and_knowledge(tmp_path, prior):
    s = tq._session(tmp_path, prior, "dv-clean", start_after=tq.LATE_START)
    r = dv.date_record(s)
    c = _pdc(r)
    assert r["date_status"] == "ELIGIBLE" and r["lifecycle_at_final_knowledge"] == "FINALIZED"
    assert r["determinism"]["identical"] and r["record_sha256"] == dv.record_sha256(r)
    assert (c["sequence_violations"], c["semantic_violations"], c["lookahead_violations"]) == ([], [], [])
    assert c["eligibility"] == "ELIGIBLE_QUALITY_QUALIFIED" and c["quality_tags"] == ["BOUNDARY_PROVENANCE"]
    assert c["completed_at_utc"] == "2026-10-05T13:55:00.000000Z" and c["stratum"] == "US_CASH_SESSION"
    k = c["knowledge"]
    assert (k["first_known_utc"], k["receipt_delay_seconds"], k["absent_before"]) == (c["completed_at_utc"], "0", True)
    assert c["family_facts"]["reach_2sd"] == "REACHED_AT_BREAKOUT_BAR" and c["context"]["time_of_day_ct"] == "08:55"
    fn = r["funnel"]["PRICE_DISCOVERY_CONTINUATION"]
    assert fn["reached_at_least"][0] == fn["instances"] and fn["reached_at_least"][3] == 1
    assert r["withdrawn_or_revised"] == []
    again = ReplaySession(MarketReplay.load(tmp_path / "rp-dv-clean.sqlite3", tq.PROV, prior))  # a fresh session
    assert dv.date_record(again) == r  # the whole record, byte for byte (canonical hashes included)


def test_receipt_delay_is_measured_from_what_was_knowable(tmp_path, prior):
    # the 08:52:30 print of 106 (the confirmation close) is received at 08:55:07: at 08:55:00 the confirmation bar
    # closes at 104.5 (not above the retest bar high 104.5), so the candidate is first known 1 us after the receipt
    rows = [r if r != (300 * 4 + 60 * 2 + 30, 106, 0) else (300 * 4 + 60 * 2 + 30, 106, 157) for r in tq.NOLATE]
    assert rows != tq.NOLATE
    s = tq._session(tmp_path, prior, "dv-delay", rows=rows)
    c = _pdc(dv.date_record(s, sweep=False))
    k = c["knowledge"]
    assert k["first_known_utc"] == "2026-10-05T13:55:07.000001Z" and k["receipt_delay_seconds"] == "7.000001"
    assert k["absent_before"] and k["absent_probe_utc"] == c["completed_at_utc"] and c["lookahead_violations"] == []


def test_withdrawn_candidate_known_earlier_is_reported(tmp_path, prior):
    s = dr._session(tmp_path, prior, rows=dr.ROWS + [(1, 100, 0)], name="dv-late")  # the 09:01:50 late print
    r = dv.date_record(s)
    assert [c for c in r["candidates"] if c["short"] == "PDC"] == []
    (w,) = r["withdrawn_or_revised"]
    assert (w["cutoff_ct"], w["candidate_id"], w["present_at_final_with_other_structure"]) == (
        "09:00", "PDC-UP-20261005T1340Z", False)


def test_sequence_and_semantic_violations_are_detected(tmp_path, prior):
    a = analyze(tq._session(tmp_path, prior, "dv-viol"), "16:00")
    (c,) = [c for c in a.candidates if c.state in dv.QUAL]
    assert dv.sequence_violations(c, a.bars) == [] and dv.semantic_violations(c, a.bars) == []
    k = sorted(c.conditions, key=lambda k: k.order)
    swapped = dataclasses.replace(c, conditions=(k[0], dataclasses.replace(k[1], bar_index=k[2].bar_index,
                                                                           satisfied_at_utc=k[2].satisfied_at_utc),
                                                 k[2], k[3]))
    assert "TRIGGER_BEFORE_ACCEPTANCE" in dv.sequence_violations(swapped, a.bars)
    j = k[3].bar_index
    bars = list(a.bars)
    bars[j] = dataclasses.replace(bars[j], close=bars[j].open)  # no longer a directional close
    assert dv.semantic_violations(c, tuple(bars)) == ["PDC_CONFIRMATION_NOT_DIRECTIONAL"]


# --- campaign data access guard -------------------------------------------------------------------------------

def _campaign_db(tmp_path):
    return dr.fx_mod._db(tmp_path, date(2026, 10, 13), tq.NOLATE, name="synthetic-campaign-date", gaps=False,
                         rejected=False, stopped_ct=(16, 30))


def _manifest(root: Path, files: dict[str, bytes]) -> str:
    lines = []
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        lines.append(f"{hashlib.sha256(data).hexdigest()}  {rel}")
    m = root / dv.FREEZE_MANIFEST
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text("# freeze\n\n```text\n" + "\n".join(lines) + "\n```\n")
    return hashlib.sha256(files[dv.PLAN]).hexdigest()


def test_guard_refuses_campaign_dates_until_the_plan_freeze_verifies(tmp_path, prior):
    assert dv.guarded(date(2026, 10, 12)) and dv.guarded(None) and not dv.guarded(date(2026, 10, 2))
    assert dv.guarded(date(2026, 10, 2), dv.anchor_of(date(2026, 10, 12)))  # a capture from the first cohort session
    db = _campaign_db(tmp_path)
    assert dv.dataset_identity(db)[0] == date(2026, 10, 13)
    root = tmp_path / "repo"
    with pytest.raises(dv.CampaignAccessDenied, match="no 0AB-D freeze manifest"):
        dv.require_access(root, db, None)
    plan = _manifest(root, {dv.PLAN: b"plan", dv.PREREGISTRATION: b"prereg", "x/drysdale.py": b"code"})
    with pytest.raises(dv.CampaignAccessDenied, match="need --frozen-plan"):
        dv.require_access(root, db, None)
    with pytest.raises(dv.CampaignAccessDenied, match="does not match"):
        dv.require_access(root, db, "0" * 64)
    assert dv.require_access(root, db, plan) is True
    (root / "x/drysdale.py").write_bytes(b"changed")
    with pytest.raises(dv.CampaignAccessDenied, match="frozen file changed: x/drysdale.py"):
        dv.require_access(root, db, plan)
    dev = tq._session(tmp_path, prior, "dv-dev").db  # 2026-10-05 fixture: not campaign data
    assert dv.require_access(tmp_path / "empty", dev, None) is False


def _cli(*args):
    return subprocess.run([sys.executable, "scripts/dicks_lab_drysdale_validation.py", *map(str, args)],
                          cwd=REPO, env=dr.fx_mod._ENV, capture_output=True, text=True, timeout=600)


def test_cli_smoke_date_cohort_and_guard(tmp_path, prior):
    db = tq._session(tmp_path, prior, "dv-cli").db
    out = tmp_path / "rec.json"
    r = _cli("date", db, "--prior-db", prior, "--out", out, "--analysis-commit", "a" * 40, "--no-sweep")
    assert r.returncode == 0, r.stderr
    rec_ = json.loads(out.read_text())
    assert rec_["trading_date"] == "2026-10-05" and rec_["campaign_guarded"] is False and \
        rec_["record_sha256"] == dv.record_sha256(rec_)
    r = _cli("cohort", out, "--date", "2026-10-05", "--json-out", tmp_path / "s.json", "--md-out", tmp_path / "s.md")
    assert r.returncode == 0, r.stderr
    assert "INCONCLUSIVE" in r.stdout  # one eligible date < 10
    assert "RESERVED FOR HUMAN REVIEW" in (tmp_path / "s.md").read_text()
    assert _cli("guard", db).returncode == 0
    camp = _campaign_db(tmp_path)
    for args in (("guard", camp), ("date", camp, "--out", tmp_path / "no.json")):
        r = _cli(*args)
        assert r.returncode == 3 and "unseen campaign data" in (r.stdout + r.stderr)
    assert not (tmp_path / "no.json").exists()


# --- freeze integrity -------------------------------------------------------------------------------------------

def test_frozen_policy_files_unchanged_and_the_validation_freeze_verifies():
    quality = {"apps/dicks_laboratory/src/dicks_laboratory/drysdale_quality.py":
               "1d54d63e808ca6bdc77dd2258e70e81b6600dbce37c8701cc9b7870258c7cc8d"}
    for rel, sha in quality.items():
        assert hashlib.sha256((REPO / rel).read_bytes()).hexdigest() == sha
    entries = dv.manifest_entries(REPO)
    if entries:  # once 0AB-D is frozen, every listed file must still verify (no silent post-freeze edit)
        assert dv.freeze_problems(REPO, entries[dv.PLAN]) == []


def test_no_trading_outcome_vocabulary_in_the_validation_record(tmp_path, prior):
    r = json.dumps(dv.date_record(tq._session(tmp_path, prior, "dv-vocab"), sweep=False)).lower()
    for word in ("pnl", "win_rate", "expectancy", "profit", "entry", "stop_price", "target", "position_size"):
        assert word not in r
    assert dry.SCHEMA == "DRYSDALE_SETUP_ANALYSIS_V1"
