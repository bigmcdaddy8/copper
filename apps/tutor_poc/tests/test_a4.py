"""0AC-A4 Guided Drysdale lesson and setup-aware evidence: zero-cost tests (scripted model, no network, no tokens).

Fixtures: the frozen Drysdale replay fixture (dicks_laboratory/tests/test_drysdale.ROWS) on the synthetic date:
a PRICE_DISCOVERY_CONTINUATION UP instance triggers with the bar ending 08:40, is accepted at 08:45, retests at
08:50 and is confirmed by the bar ending 08:55 (CANDIDATE at 08:55 and 09:00). A late print inside the 08:50-08:55
bar (received 09:01:50) revises that bar from 09:05 on and turns the instance back into DEVELOPING.
Numbers refer to the A4 test list.
"""
# ruff: noqa: F811  (pytest fixtures imported from test_real_provider are injected by name)
from __future__ import annotations

import dataclasses
import io
import json
import re
import zipfile
from datetime import UTC, date
from decimal import ROUND_HALF_EVEN, Decimal

import pytest
import test_drysdale as dr_mod
import test_replay as fx_mod
from conftest import A4_GRID
from dicks_laboratory import drysdale as dry
from dicks_laboratory.price_action import Direction
from dicks_laboratory.replay import MarketReplay, ReplayCutoff
from dicks_laboratory.replay_player import ReplaySession
from dicks_laboratory.tutor_ai import DRYSDALE_VOCABULARY
from dicks_laboratory.tutor_evidence import DRYSDALE_MODULE, LessonStage
from fastapi.testclient import TestClient
from test_real_provider import (  # noqa: F401
    SECRET,
    ScriptedClient,
    answer,
    claim,
    dclaim,
    no_network,
    reply,
)

from tutor_poc import export, grounding, setups
from tutor_poc.api import create_app
from tutor_poc.catalog import CATALOG, CATALOG_VERSION, DIRECTIONS, FAMILIES, TITLES, catalog_text
from tutor_poc.dev_sessions import DevSession
from tutor_poc.evidence import DRYSDALE_WARNING, chart_lesson, evidence_document, model_evidence, setup_document
from tutor_poc.lesson import L1, LESSONS, LOCKED_SEMANTICS, GuidedLesson, _phases, verify
from tutor_poc.prompt import PROMPT_VERSION, PROMPTS
from tutor_poc.providers import FakeProvider, GroundedProvider, TurnContext
from tutor_poc.setup_guards import RESIDUAL_VOCABULARY, SetupGuardCode
from tutor_poc.snapshot import position_index
from tutor_poc.tutor import TutorAction

CUR, ct = fx_mod.CUR, fx_mod.ct
PDC = "PRICE_DISCOVERY_CONTINUATION"
PDC_ID = "PDC-UP-20261005T1340Z"
FIX = GuidedLesson(
    "FIXTURE_GUIDED_L1", CUR, "Fixture lesson · the opening drive", f"{PDC} UP · {PDC_ID}",
    _phases("08:35", "08:40", "08:55", "09:00"), PDC, "UP", PDC_ID,
    (("08:40", "condition 1 LAB_BREAKOUT_TRIGGER_V1"), ("08:45", "condition 2 LAB_ACCEPTANCE_TIME_V1"),
     ("08:50", "condition 3 LAB_RETEST_V1"), ("08:55", "condition 4 LAB_DIRECTIONAL_CONFIRMATION_V1")))
SESSION = "page-a4-0001"


def at(hh, mm):
    return ct(CUR, hh, mm)


def lesson_at(tl, st, hh, mm):
    i = position_index(tl, at(hh, mm))
    return chart_lesson(tl, i, "a4", st.at(at(hh, mm)))


def doc_at(tl, st, hh, mm):
    return evidence_document(tl, position_index(tl, at(hh, mm)), st.at(at(hh, mm)))


def check(cl, doc, stage=LessonStage.QUESTION, action=None, student=None):
    status, _, _, issues, detail = grounding.evaluate(json.dumps(doc), cl, stage, student, action)
    return status.value, {i.code for i in issues}, issues


def row(cl, family, direction):
    return next(i for i, r in enumerate(cl.setup_document["setups"]) if (r["family"], r["direction"]) == (family,
                                                                                                         direction))


@pytest.fixture(scope="module")
def registry():
    return (DevSession(CUR, "synthetic.sqlite3", "0" * 64, True),
            DevSession(date(2026, 10, 12), "campaign.sqlite3", "0" * 64, True))  # wrongly registered, still sealed


def client_for(dr_timeline, dr_setups, registry, provider, lessons=None):
    return TestClient(create_app(registry, lambda s: dr_timeline, web_dist=None, provider=provider,
                                 load_setups=lambda s: dr_setups, lessons={CUR: (FIX,)} if lessons is None else lessons))


def turn(c, action, hh, mm, n, stage="QUESTION", text=None, mode="guided", lesson="FIXTURE_GUIDED_L1", status=200,
         d=CUR):
    body = {"action": action, "replay_cutoff_utc": at(hh, mm).isoformat(), "stage": stage, "turn": n,
            "session_id": SESSION, "mode": mode}
    if mode == "guided":
        body["lesson_id"] = lesson
    if text is not None:
        body["text"] = text
    r = c.post(f"/api/sessions/{d}/tutor/turn", json=body)
    assert r.status_code == status, r.text
    return r.json()


# --- 1-4 historical band evidence ----------------------------------------------------------------------

def q(v: Decimal) -> str:
    return str(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))


def test_01_every_window_bar_has_its_own_as_of_vwap_and_bands(dr_timeline, dr_setups):
    doc = doc_at(dr_timeline, dr_setups, 9, 0)
    bars = {b.start_utc.astimezone(fx_mod.CT).strftime("%H:%M"): b
            for b in dr_timeline.positions[position_index(dr_timeline, at(9, 0))].bars}
    rows = doc["recent_bars"] + [doc["latest_bar"]]
    assert len(rows) == 6
    for r in rows:
        b = bars[r["start_ct"]]
        assert (r["vwap"], r["upper_1sd"], r["lower_1sd"], r["upper_2sd"], r["lower_2sd"]) == (
            q(b.vwap), q(b.upper_1sd), q(b.lower_1sd), q(b.upper_2sd), q(b.lower_2sd))
    assert len({r["upper_1sd"] for r in rows}) > 1  # each bar's own level, not the latest one repeated


def test_02_band_relations_use_each_bars_own_values(dr_timeline, dr_setups):
    for hh, mm in ((8, 30), (8, 50), (9, 0)):
        doc = doc_at(dr_timeline, dr_setups, hh, mm)
        bars = {b.start_utc.astimezone(fx_mod.CT).strftime("%H:%M"): b
                for b in dr_timeline.positions[position_index(dr_timeline, at(hh, mm))].bars}
        for r in doc["recent_bars"] + [doc["latest_bar"]]:
            b = bars[r["start_ct"]]
            side = lambda x, y: "ABOVE" if x > y else "BELOW" if x < y else "AT"  # noqa: E731
            assert r["close_vs_upper_1sd"] == side(b.close, b.upper_1sd)
            assert r["close_vs_lower_2sd"] == side(b.close, b.lower_2sd)
            # the frozen DRYSDALE_VALUE_AREA_V1 position agrees with the bar's own +/-1 sigma relations
            assert (r["value_position"] == "ABOVE_VALUE") == (r["close_vs_upper_1sd"] == "ABOVE")
            assert (r["value_position"] == "BELOW_VALUE") == (r["close_vs_lower_1sd"] == "BELOW")


def test_03_04_late_revision_never_leaks_hindsight(dr_timeline, dr_setups):
    """The 7767.25 -> 7767.50 case in miniature: 08:50 bar close 106.00 at 09:00, 103.00 once the late print is known."""
    later = doc_at(dr_timeline, dr_setups, 9, 5)  # built first: order must not matter
    early = doc_at(dr_timeline, dr_setups, 9, 0)
    e, lt = early["recent_bars"][-1], later["recent_bars"][-1]
    assert e["start_ct"] == lt["start_ct"] == "08:50"
    assert (e["close"], e["revised_since_completion"]) == ("106.00", False)  # as known at 09:00
    assert (lt["close"], lt["revised_since_completion"]) == ("103.00", True)  # as known at 09:05, flagged
    assert early["replay"]["values_as_of_ct"] == "09:00" and later["replay"]["revised_bars_in_window"] == 2
    assert early == doc_at(dr_timeline, dr_setups, 9, 0)  # deterministic
    s0, s1 = setup_document(dr_setups.at(at(9, 0))), setup_document(dr_setups.at(at(9, 5)))
    assert s0["setups"][0]["state"] == "CANDIDATE" and s1["setups"][0]["state"] == "DEVELOPING"


# --- 5-8 recent structure ------------------------------------------------------------------------------

def test_05_06_close_high_low_sequences(dr_timeline, dr_setups):
    doc = doc_at(dr_timeline, dr_setups, 9, 0)
    rows = doc["recent_bars"] + [doc["latest_bar"]]
    closes = [Decimal(r["close"]) for r in rows]
    for prev, cur, r in zip(closes, closes[1:], rows[1:], strict=False):
        assert r["close_vs_prev_close"] == ("HIGHER" if cur > prev else "LOWER" if cur < prev else "EQUAL")
    highs, lows = [Decimal(r["high"]) for r in rows], [Decimal(r["low"]) for r in rows]
    assert [r["high_vs_prev_high"] for r in rows[1:]] == [
        "HIGHER" if b > a else "LOWER" if b < a else "EQUAL" for a, b in zip(highs, highs[1:], strict=False)]
    assert [r["low_vs_prev_low"] for r in rows[1:]] == [
        "HIGHER" if b > a else "LOWER" if b < a else "EQUAL" for a, b in zip(lows, lows[1:], strict=False)]
    s = doc["sequence"]
    assert (s["consecutive_lower_closes"], s["consecutive_higher_lows"], s["closes_above_upper_2sd"]) == (1, 2, 5)


def test_07_vwap_slope_is_the_frozen_per_bar_fact(dr_timeline, dr_setups):
    doc = doc_at(dr_timeline, dr_setups, 8, 50)
    frozen = [b["vwap_slope"] for b in dr_setups.at(at(8, 50))["bars"]]  # LAB_VWAP_SLOPE_V1 from the frozen bars
    rows = doc["recent_bars"] + [doc["latest_bar"]]
    assert [r["vwap_slope"] for r in rows] == frozen
    assert doc["sequence"]["vwap_rising_bars"] == sum(r["vwap_slope"] == "RISING" for r in rows) == 5
    assert doc["sequence"]["vwap_change_over_window"] == q(Decimal(rows[-1]["vwap"]) - Decimal(rows[0]["vwap"]))


CLOSED_VOCABULARY = {"ABOVE", "BELOW", "AT", "HIGHER", "LOWER", "EQUAL", "RISING", "FALLING", "FLAT", "ABOVE_VALUE",
                     "INSIDE_VALUE", "BELOW_VALUE", "ABOVE_PLUS_2_SIGMA", "BELOW_MINUS_2_SIGMA",
                     "LEVEL_2_UPPER (between +1σ and +2σ)", "LEVEL_1 (between -1σ and +1σ)",
                     "LEVEL_2_LOWER (between -2σ and -1σ)"}


def test_08_no_new_indicator_semantics(dr_timeline, dr_setups):
    doc = doc_at(dr_timeline, dr_setups, 9, 0)
    for r in doc["recent_bars"] + [doc["latest_bar"]]:
        for k, v in r.items():
            if isinstance(v, str) and not re.fullmatch(r"-?\d+\.\d{2}|\d{2}:\d{2}", v):
                assert v in CLOSED_VOCABULARY, (k, v)
    words = json.dumps(doc).lower()
    for label in ("trend", "bullish", "bearish", "strong", "weak", "momentum", "signal"):
        assert label not in words  # sequences are comparisons and counts, never a label


# --- 9-12 setup vocabulary -----------------------------------------------------------------------------

M = lambda spec: [(200 - r[0], 200 - r[2], 200 - r[1], 200 - r[3]) + tuple(r[4:5]) + tuple(  # noqa: E731
    200 - x for x in r[5:6]) for r in spec]
SPECS = {(PDC, "UP"): dr_mod.PDC_UP, (PDC, "DOWN"): M(dr_mod.PDC_UP),
         ("FADE_VALUE_AREA_EXTREME", "DOWN"): dr_mod.FADE_UP,
         ("FADE_VALUE_AREA_EXTREME", "UP"): [dr_mod.IN, dr_mod.IN, (100, 100, 97.5, 99), (99, 101, 98.75, 100.5)],
         ("RETURN_TO_VALUE", "DOWN"): dr_mod.RTV_DOWN, ("RETURN_TO_VALUE", "UP"): M(dr_mod.RTV_DOWN),
         ("VWAP_BOUNCE", "UP"): dr_mod.BOUNCE_UP, ("VWAP_BOUNCE", "DOWN"): M(dr_mod.BOUNCE_UP)}


def test_09_10_catalog_conditions_equal_the_frozen_candidates_for_all_eight_variants():
    assert len(SPECS) == 8
    for (family, direction), spec in SPECS.items():
        c = next(x for x in dr_mod.ev(spec) if (x.family.value, x.direction.value) == (family, direction))
        cat = CATALOG["families"][family]["directions"][direction]["conditions"]
        assert [(k.order, k.policy_id, k.laboratory_rule) for k in c.conditions] == [
            (x["order"], x["policy_id"], x["rule"]) for x in cat], (family, direction)
        assert list(c.source_criteria) == CATALOG["families"][family]["source_criteria"]


def test_11_12_names_are_the_frozen_names_and_nothing_is_invented():
    assert [f.value for f in FAMILIES] == [f.value for f in dry.SetupFamily] == list(CATALOG["families"])
    assert [d.value for d in DIRECTIONS] == [d.value for d in Direction] == ["UP", "DOWN"]
    assert [TITLES[f] for f in FAMILIES] == [t.title for t in DRYSDALE_MODULE.topics]
    assert {f: v["candidate_policy"] for f, v in CATALOG["families"].items()} == {
        f.value: p for f, p in dry.CANDIDATE_POLICY.items()}
    assert CATALOG["states"] == [s.value for s in dry.CandidateState]
    assert "APPROACHING" not in json.dumps(CATALOG) and "APPROACHING" not in PROMPTS[PROMPT_VERSION]
    assert catalog_text() in PROMPTS[PROMPT_VERSION] and CATALOG_VERSION in PROMPTS[PROMPT_VERSION]


def test_setup_rows_cover_the_eight_variants_from_the_frozen_analysis(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 9, 0)
    rows = cl.setup_document["setups"]
    assert [(r["family"], r["direction"]) for r in rows] == [(f.value, d.value) for f in FAMILIES for d in DIRECTIONS]
    p = dr_setups.at(at(9, 0))
    for r in rows:
        c = next((x for x in p["latest"] if (x["family"], x["direction"]) == (r["family"], r["direction"])), None)
        assert r["instance_exists"] is (c is not None)
        if c:
            assert (r["instance_id"], r["state"], r["stage"]) == (c["candidate_id"], c["state"], c["stage"])
            assert [k["status"] for k in r["conditions"]] == [k["status"] for k in c["conditions"]]


def test_setup_projection_is_the_frozen_analysis(dr_fx):
    s = ReplaySession(MarketReplay.load(dr_fx[0], dr_mod.PROV, dr_fx[1]))
    a = dry.analyze(s, cutoff=ReplayCutoff.at(at(8, 55)))
    p = setups.project(a)
    assert p["drysdale_sha256"] == dry.drysdale_sha256(a) and p["state"] == a.state.value
    latest = dry.latest_by_family(a)
    assert {(c["family"], c["direction"]): c["state"] for c in p["latest"]} == {
        (f.value, d.value): c.state.value for (f, d), c in latest.items()}


# --- 13-16 setup grounding -----------------------------------------------------------------------------

def valid_claim(cl, state):
    i = row(cl, PDC, "UP")
    return dclaim(f"Laboratory V1 {PDC} UP state (PRICE_DISCOVERY_CONTINUATION_CANDIDATE_V1).", "CANDIDATE",
                  [f"/setups/{i}/state"], [(f"/setups/{i}/state", state)])


def test_13_a_valid_deterministic_state_can_be_stated(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 55)
    a = answer("The PRICE_DISCOVERY_CONTINUATION UP setup is now a Laboratory V1 candidate: all its conditions are "
               "satisfied.", [valid_claim(cl, "CANDIDATE")])
    assert check(cl, a)[0] == "GROUNDED"


def test_14_invalid_setup_condition_and_band_assertions_are_rejected(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)  # PDC UP: DEVELOPING, WAITING_FOR_CONFIRMATION
    status, codes, _ = check(cl, answer("The PRICE_DISCOVERY_CONTINUATION UP setup is valid.",
                                        [valid_claim(cl, "DEVELOPING")]))
    assert status == "GROUNDING_FAILED" and SetupGuardCode.SETUP_STATE_CONTRADICTED in codes
    status, codes, _ = check(cl, answer("The PDC UP is valid now.", [valid_claim(cl, "CANDIDATE")]))
    assert "VALUE_MISMATCH" in codes  # asserting the wrong state value fails the frozen validator too
    i = row(cl, "FADE_VALUE_AREA_EXTREME", "DOWN")  # its LAB_REJECTION_V1 is NOT_SATISFIED
    a = answer("Rejection has occurred at the upper band.",
               [dclaim("Laboratory V1 LAB_REJECTION_V1 status for FADE DOWN.", "LABORATORY_POLICY_RESULT",
                       [f"/setups/{i}/conditions/2/status"], [(f"/setups/{i}/conditions/2/status", "NOT_SATISFIED")])])
    assert SetupGuardCode.CONDITION_NOT_GROUNDED in check(cl, a)[1]
    a = answer("Acceptance has occurred.", [claim("Close vs VWAP.", "DERIVED_FACT", ["/latest_bar/close_vs_vwap"])])
    assert SetupGuardCode.CONDITION_NOT_GROUNDED in check(cl, a)[1]
    # 08:20-08:25 closed below its -1 sigma, not above +2 sigma
    a = answer("The 08:20 bar closed above +2 sigma.", [claim("Its close.", "OBSERVED_FACT", ["/recent_bars/0/close"])])
    assert SetupGuardCode.BAND_RELATION_CONTRADICTED in check(cl, a)[1]
    a = answer("The prior bar closed below -1 sigma.", [claim("Its close.", "OBSERVED_FACT", ["/recent_bars/4/close"])])
    assert SetupGuardCode.BAND_RELATION_CONTRADICTED in check(cl, a)[1]
    ok = answer("The 08:20 bar closed below -1 sigma and the latest bar closed above +2 sigma.",
                [claim("Their closes.", "OBSERVED_FACT", ["/recent_bars/0/close", "/latest_bar/close"])])
    assert check(cl, ok)[0] == "GROUNDED"
    # live-smoke regression: a negated count is not an assertion; a bar outside the window is not checked by bars
    for text in ("All 6 closes in the window were above the VWAP and none closed above +1 sigma.",
                 "The bar ending 08:10 closed above +1 sigma."):
        assert SetupGuardCode.BAND_RELATION_CONTRADICTED not in check(cl, answer(text, [claim(
            "Closes.", "DERIVED_FACT", ["/sequence/closes_above_vwap"])]))[1], text


def test_15_missing_condition_claims_are_grounded(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    i = row(cl, PDC, "UP")
    p = f"/setups/{i}/conditions/3/status"
    a = answer("The PDC UP is not valid yet: Laboratory V1 LAB_DIRECTIONAL_CONFIRMATION_V1 is still pending. Why "
               "isn't it complete?", [dclaim("Laboratory V1 LAB_DIRECTIONAL_CONFIRMATION_V1 for PDC UP is PENDING.",
                                             "LABORATORY_POLICY_RESULT", [p], [(p, "PENDING")])])
    status, _, _ = check(cl, a)
    assert status == "GROUNDED"
    _, ans, rep, _, _ = grounding.evaluate(json.dumps(a), cl, LessonStage.QUESTION)
    g = grounding.grounding_summary(ans, rep, cl)
    assert g["referenced_setups"] == [f"{PDC} UP"]
    assert g["missing_conditions"] == [f"{PDC} UP LAB_DIRECTIONAL_CONFIRMATION_V1 PENDING"]
    wrong = answer("Confirmation is missing.", [dclaim("Laboratory V1 LAB_DIRECTIONAL_CONFIRMATION_V1.",
                                                       "LABORATORY_POLICY_RESULT", [p], [(p, "SATISFIED")])])
    assert "VALUE_MISMATCH" in check(cl, wrong)[1]


def test_16_ai_interpretation_is_allowed_without_mutating_state(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    i = row(cl, PDC, "UP")
    a = answer("I would describe the last bars as increasingly bullish, so the PDC UP is worth watching; it is still "
               "DEVELOPING.", [
                   claim("I would read the closes above +2 sigma as increasingly bullish.", "AI_INTERPRETATION",
                         ["/sequence/closes_above_upper_2sd", "/latest_bar/close_vs_upper_2sd"]),
                   dclaim("Laboratory V1 PDC UP state.", "CANDIDATE", [f"/setups/{i}/state"],
                          [(f"/setups/{i}/state", "DEVELOPING")])])
    assert check(cl, a)[0] == "GROUNDED"
    as_fact = answer("The bars are bullish.", [claim("The bars are bullish.", "DERIVED_FACT", ["/sequence/vwap_rising_bars"])])
    assert check(cl, as_fact)[0] == "GROUNDING_FAILED"
    bare = answer("This is bullish.", [claim("Close vs VWAP.", "DERIVED_FACT", ["/latest_bar/close_vs_vwap"])])
    assert check(cl, bare)[0] == "GROUNDING_FAILED"
    other = answer("A bullish read with high probability.", [claim("I read it as bullish.", "AI_INTERPRETATION",
                                                                   ["/latest_bar/close_vs_vwap"])])
    assert check(cl, other)[0] == "GROUNDING_FAILED"  # every other frozen vocabulary word stays refused
    assert RESIDUAL_VOCABULARY.pattern == DRYSDALE_VOCABULARY.pattern.replace("bullish|bearish|", "")


# --- 17-19 conditional future reasoning ----------------------------------------------------------------

def test_17_18_conditional_pathways_pass_and_known_futures_fail(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    cites = [claim("Close vs VWAP.", "DERIVED_FACT", ["/latest_bar/close_vs_vwap"])]
    ok = answer("If a later bar closes above its open and above the retest bar high, the PDC UP conditions would be "
                "met. If instead price closes back inside value, the RETURN_TO_VALUE pathway could become relevant.",
                cites)
    assert check(cl, ok)[0] == "GROUNDED"
    for text in ("The next bar will break out.", "Price will bounce from here.", "A reversal is coming.",
                 "We know this will reverse.", "The setup is going to complete."):
        assert SetupGuardCode.FUTURE_STATED_AS_KNOWN in check(cl, answer(text, cites))[1], text


def test_19_no_future_candidate_state_before_it_exists(dr_fx, dr_timeline, dr_setups):
    early = setups.build_setup_timeline(dr_fx[0], dr_fx[1], [t for t in A4_GRID if t <= at(8, 50)])
    assert early.at(at(8, 50)) == dr_setups.at(at(8, 50))  # identical without any later cutoff ever computed
    ev = model_evidence(lesson_at(dr_timeline, dr_setups, 8, 50))
    state = ev["DRYSDALE"]["setups"]["columns"].index("state")
    assert all(r[state] != "CANDIDATE" for r in ev["DRYSDALE"]["setups"]["rows"])  # it completes at 08:55
    assert ev["DRYSDALE"]["completed_today"]["rows"] == []
    end = ev["LESSON_TIME"]["bars"]["columns"].index("end_ct")
    assert max(r[end] for r in ev["LESSON_TIME"]["bars"]["rows"]) == "08:50"


# --- 20-24 teaching behavior ---------------------------------------------------------------------------

def test_20_approximate_answers_are_accepted(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    a = answer("Yes, about 3 points above VWAP is close enough here: what matters is that the close is above +2 sigma. "
               "What does that location say about the setups?",
               [claim("Close minus VWAP.", "DERIVED_FACT", ["/latest_bar/close_minus_vwap"],
                      [("/latest_bar/close_minus_vwap", "3.38")])])
    assert check(cl, a, student="its maybe ~3pts above vwap")[0] == "GROUNDED"
    assert "Accept approximate answers" in PROMPTS[PROMPT_VERSION]


def test_21_deterministic_arithmetic_is_not_quizzed(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    cites = [claim("Close minus VWAP.", "DERIVED_FACT", ["/latest_bar/close_minus_vwap"])]
    for text in ("What is 103.50 - 100.12?", "How many points is the close above VWAP?",
                 "Can you calculate the distance to +2 sigma?", "By how much did it close above +1 sigma?"):
        assert SetupGuardCode.ARITHMETIC_QUIZ in check(cl, answer(text, cites))[1], text
    meaning = answer("The close is 3.38 points above VWAP and above +2 sigma. What does that location tell you about "
                     "which setup possibilities deserve attention?", cites)
    assert check(cl, meaning)[0] == "GROUNDED"
    assert "Do not turn deterministic arithmetic into a quiz" in PROMPTS[PROMPT_VERSION]


def test_22_guided_replay_progression_carries_the_prior_lesson_state(dr_timeline, dr_setups, registry, no_network):
    hint = answer("Look at what the newest bar did relative to the band it just broke.",
                  [claim("Close vs +1 sigma.", "DERIVED_FACT", ["/latest_bar/close_vs_upper_1sd"])])
    client = ScriptedClient(reply(hint), reply(hint), reply(hint))
    c = client_for(dr_timeline, dr_setups, registry, GroundedProvider(client))
    turn(c, "question", 8, 35, 0)
    turn(c, "message", 8, 35, 1, text="Price is in Level 1, the overnight was quiet")
    turn(c, "question", 8, 40, 2)
    user = client.requests[2]["user"]
    assert user["mode"] == "guided" and user["lesson"]["phase"]["phase"] == "DEVELOPMENT"
    assert user["lesson"]["phase"]["at_phase_start"] is True and user["lesson"]["reveal"] is None
    assert user["replay_change"] == {"from_ct": "08:35", "to_ct": "08:40", "direction": "FORWARD",
                                     "bars_completed_since": 1}
    assert "Price is in Level 1, the overnight was quiet" in json.dumps(user["conversation"])
    assert client.requests[0]["user"]["lesson"]["phase"]["phase"] == "BEFORE_SETUP"
    assert client.requests[0]["user"]["replay_change"] is None


def test_23_hint_guides_without_laying_out_the_answer(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    cites = [claim("The close and +2 sigma.", "DERIVED_FACT", ["/latest_bar/close", "/latest_bar/upper_2sd"])]
    bad = answer("The close is 103.50 and +2 sigma is 102.04. Which is larger?", cites)
    assert SetupGuardCode.HINT_GIVES_ANSWER in check(cl, bad, LessonStage.HINT, "hint")[1]
    good = answer("Check whether the latest close stayed inside upper Level 2 or established itself beyond +2 sigma, "
                  "then compare that with the bars before it.", cites)
    assert check(cl, good, LessonStage.HINT, "hint")[0] == "GROUNDED"


def test_24_explain_links_fact_interpretation_and_setup(dr_timeline, dr_setups):
    cl = lesson_at(dr_timeline, dr_setups, 8, 50)
    i = row(cl, PDC, "UP")
    facts = [claim("Close vs +1 sigma.", "DERIVED_FACT", ["/latest_bar/close_vs_upper_1sd"])]
    narration = answer("The close is above +1 sigma.", facts)
    assert SetupGuardCode.EXPLAIN_NOT_LINKED in check(cl, narration, LessonStage.ANSWER, "explain")[1]
    linked = answer("The close is above +1 sigma; I read that as price holding outside value, which is why the "
                    "PDC UP matters here: it still waits for its confirmation bar.",
                    facts + [claim("Holding outside value.", "AI_INTERPRETATION", ["/latest_bar/close_vs_upper_1sd"]),
                             dclaim("Laboratory V1 PDC UP stage.", "LABORATORY_POLICY_RESULT", [f"/setups/{i}/stage"],
                                    [(f"/setups/{i}/stage", "WAITING_FOR_CONFIRMATION")])])
    assert check(cl, linked, LessonStage.ANSWER, "explain")[0] == "GROUNDED"


# --- entry / risk boundary -----------------------------------------------------------------------------

def test_entry_is_discussed_only_after_validity_and_risk_is_refused(dr_timeline, dr_setups):
    early, done = lesson_at(dr_timeline, dr_setups, 8, 50), lesson_at(dr_timeline, dr_setups, 8, 55)
    text = "Under this training framework, the completing bar marks the PDC UP potential entry location."
    assert SetupGuardCode.ENTRY_BEFORE_VALIDITY in check(early, answer(text, [valid_claim(early, "DEVELOPING")]))[1]
    assert check(done, answer(text + " What would make you hesitate?", [valid_claim(done, "CANDIDATE")]))[0] == "GROUNDED"
    for risky in ("Risk 1% of your account here.", "Trade 2 contracts.", "Put your stop-loss below the bar.",
                  "Size your position for a $500 daily loss."):
        _, codes, _ = check(done, answer(risky, [valid_claim(done, "CANDIDATE")]))
        assert codes & {SetupGuardCode.RISK_MANAGEMENT, "TRADE_ADVICE"}, risky


# --- 25-30 guided lesson -------------------------------------------------------------------------------

def test_25_lesson_verifies_and_starts_before_the_reveal(dr_setups, dr_timeline, registry):
    assert verify(FIX, dr_setups) == []
    assert FIX.start < FIX.reveal_at and FIX.public()["title"] == "Fixture lesson · the opening drive"
    assert "setup" not in FIX.public(at(8, 50)) and FIX.public(at(9, 0))["setup"]["instance_id"] == PDC_ID
    pre = json.dumps(FIX.block(at(8, 55)))
    assert PDC_ID not in pre and PDC not in pre and "PDC" not in pre  # outcome-neutral before the reveal
    c = client_for(dr_timeline, dr_setups, registry, FakeProvider())
    listed = c.get(f"/api/sessions/{CUR}/lessons").json()["lessons"]
    assert [x["lesson_id"] for x in listed] == ["FIXTURE_GUIDED_L1"] and PDC_ID not in json.dumps(listed)
    assert listed[0]["start_cutoff_utc"] == at(8, 35).astimezone(UTC).isoformat()


def test_lesson_verification_catches_authoring_errors(dr_setups):
    wrong_time = GuidedLesson(FIX.lesson_id, CUR, FIX.title, FIX.revealed_title, FIX.phases, PDC, "UP", PDC_ID,
                              (("08:45", "condition 1 LAB_BREAKOUT_TRIGGER_V1"),))
    assert any("condition 1" in p for p in verify(wrong_time, dr_setups))
    wrong_setup = GuidedLesson(FIX.lesson_id, CUR, FIX.title, FIX.revealed_title, FIX.phases, PDC, "DOWN", PDC_ID, ())
    assert verify(wrong_setup, dr_setups)
    early_reveal = GuidedLesson(FIX.lesson_id, CUR, FIX.title, FIX.revealed_title, _phases("08:35", "08:40", "08:45",
                                                                                        "08:50"), PDC, "UP", PDC_ID, ())
    assert any("not a completed" in p for p in verify(early_reveal, dr_setups))
    leaky = dataclasses.replace(FIX, phases=(dataclasses.replace(FIX.phases[0], instructions=f"Watch {PDC_ID}."),)
                                + FIX.phases[1:])
    assert any("names the studied setup" in p for p in verify(leaky, dr_setups))


def test_26_29_30_complete_guided_lesson_reaches_post_reveal_only_at_the_reveal(dr_timeline, dr_setups, registry):
    c = client_for(dr_timeline, dr_setups, registry, FakeProvider())
    seen, n, stage = [], 0, "QUESTION"
    for hh, mm in ((8, 35), (8, 40), (8, 45), (8, 50), (8, 55), (9, 0)):
        r = turn(c, "question", hh, mm, n, stage)
        n += 1
        h = turn(c, "hint", hh, mm, n, r["stage"])
        n += 1
        seen.append((f"{hh:02d}:{mm:02d}", r["lesson"]["phase"], r["stage"], h["stage"], r["lesson"]["revealed"]))
        stage = h["stage"]
    assert seen == [("08:35", "BEFORE_SETUP", "QUESTION", "HINT", False), ("08:40", "DEVELOPMENT", "QUESTION", "HINT", False),
                    ("08:45", "DEVELOPMENT", "QUESTION", "HINT", False), ("08:50", "DEVELOPMENT", "QUESTION", "HINT", False),
                    ("08:55", "DECISION", "QUESTION", "HINT", False), ("09:00", "POST_REVEAL", "POST_REVEAL", "POST_REVEAL", True)]
    last = turn(c, "explain", 9, 0, n, "POST_REVEAL")
    assert last["stage"] == "POST_REVEAL" and last["lesson"]["setup"] == {"family": PDC, "direction": "UP",
                                                                         "instance_id": PDC_ID}
    assert "Fixture lesson" in turn(c, "question", 8, 35, n + 1)["text"]


def test_27_lesson_semantics_lock_globex(dr_timeline, dr_setups, registry):
    assert dict(FIX.locked) == dict(L1.locked) == LOCKED_SEMANTICS == {"vwap_anchor": "GLOBEX"}
    assert FIX.block(at(8, 40))["locked_semantics"] == {"vwap_anchor": "GLOBEX"}
    assert doc_at(dr_timeline, dr_setups, 8, 40)["study"]["vwap_anchor"] == "GLOBEX"
    c = client_for(dr_timeline, dr_setups, registry, FakeProvider())
    r = c.post(f"/api/sessions/{CUR}/tutor/turn", json={"action": "question", "replay_cutoff_utc": at(8, 40).isoformat(),
                                                         "turn": 0, "mode": "guided", "lesson_id": FIX.lesson_id,
                                                         "vwap_anchor": "US_CASH_OPEN"})
    assert r.status_code == 422  # no study-semantic setting can be sent with a turn
    assert c.get(f"/api/sessions/{CUR}/lessons").json()["lessons"][0]["locked_semantics"] == {"vwap_anchor": "GLOBEX"}


def test_28_29_stage_transitions_and_no_early_post_reveal(dr_timeline, dr_setups, registry):
    c = client_for(dr_timeline, dr_setups, registry, FakeProvider())
    assert turn(c, "hint", 8, 55, 0, "POST_REVEAL")["stage"] == "ANSWER"  # a client cannot claim the reveal early
    assert turn(c, "explain", 8, 55, 1, "QUESTION")["stage"] == "ANSWER"
    assert turn(c, "question", 9, 5, 2, mode="free", lesson=None)["stage"] == "QUESTION"  # free chat never reveals
    assert turn(c, "hint", 9, 5, 3, "POST_REVEAL", mode="free")["stage"] == "ANSWER"
    r = c.post(f"/api/sessions/{CUR}/tutor/turn", json={"action": "question", "replay_cutoff_utc": at(8, 40).isoformat(),
                                                         "turn": 5, "mode": "free", "lesson_id": FIX.lesson_id})
    assert r.status_code == 422
    turn(c, "question", 8, 40, 6, lesson="NO_SUCH_LESSON", status=404)


# --- 31-34 free chat -----------------------------------------------------------------------------------

def test_31_34_free_chat_uses_setup_evidence_and_stays_conditional(dr_timeline, dr_setups, registry, no_network):
    def at850():
        return lesson_at(dr_timeline, dr_setups, 8, 50)

    cl = at850()
    up, down = row(cl, PDC, "UP"), row(cl, PDC, "DOWN")
    plausible = answer("I would concentrate on the PDC UP: three of its four Laboratory V1 conditions are satisfied. The "
                       "DOWN variants lack the structure: closes are above VWAP.", [
                           claim("Closes above VWAP make the DOWN side not currently plausible.", "AI_INTERPRETATION",
                                 ["/sequence/closes_above_vwap"]),
                           dclaim("Laboratory V1 PDC UP stage.", "LABORATORY_POLICY_RESULT", [f"/setups/{up}/stage"],
                                  [(f"/setups/{up}/stage", "WAITING_FOR_CONFIRMATION")])])
    why_not = answer("It is not valid yet because Laboratory V1 LAB_DIRECTIONAL_CONFIRMATION_V1 is PENDING.", [
        dclaim("Laboratory V1 LAB_DIRECTIONAL_CONFIRMATION_V1.", "LABORATORY_POLICY_RESULT",
               [f"/setups/{up}/conditions/3/status"], [(f"/setups/{up}/conditions/3/status", "PENDING")])])
    next_ = answer("If the next complete bar closes above its open and above the retest bar high, the PDC UP conditions "
                   "would all be met; the PDC DOWN cannot complete (Laboratory V1 can still complete: false).", [
                       dclaim("Laboratory V1 PDC DOWN can still complete.", "LABORATORY_POLICY_RESULT",
                              [f"/setups/{down}/can_still_complete"], [(f"/setups/{down}/can_still_complete", False)])])
    predict = answer("The next bar will confirm the PDC UP.", [claim("Close.", "OBSERVED_FACT", ["/latest_bar/close"])])
    client = ScriptedClient(reply(plausible), reply(why_not), reply(next_), reply(predict), reply(predict))
    c = client_for(dr_timeline, dr_setups, registry, GroundedProvider(client))
    out = [turn(c, "message", 8, 50, k, text=t, mode="free", lesson=None)
           for k, t in enumerate(("Which Drysdale setups are plausible right now?", "Why is it not valid yet?",
                                  "What would have to happen next?", "Will it work?"))]
    assert [o["status"] for o in out] == ["GROUNDED", "GROUNDED", "GROUNDED", "GROUNDING_FAILED"]
    u = client.requests[0]["user"]
    assert u["mode"] == "free" and u["lesson"] is None and u["evidence"]["DRYSDALE"]["setups"]["rows"]
    assert out[1]["grounding"]["missing_conditions"] == [f"{PDC} UP LAB_DIRECTIONAL_CONFIRMATION_V1 PENDING"]
    assert CATALOG_VERSION in client.requests[0]["system"] and "DRYSDALE" in json.dumps(client.requests[0]["schema"])


# --- 35-38 export / campaign ---------------------------------------------------------------------------

def test_35_36_guided_export_carries_lesson_context_without_early_reveal(dr_timeline, dr_setups, registry):
    c = client_for(dr_timeline, dr_setups, registry, FakeProvider())
    n = 0
    for hh, mm in ((8, 35), (8, 50), (8, 55), (9, 0)):
        turn(c, "question", hh, mm, n)
        n += 1
    turn(c, "message", 9, 0, n, "POST_REVEAL", text="the retest bar mattered most")
    r = c.post(f"/api/sessions/{CUR}/tutor/export", json={"session_id": SESSION, "replay_cutoff_utc": at(9, 0).isoformat()})
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    m = {k: z.read(k).decode() for k in z.namelist()}
    rows = list(export.csv.DictReader(io.StringIO(m["turns.csv"])))
    assert [(x["mode"], x["lesson_id"], x["lesson_phase"], x["lesson_revealed"]) for x in rows] == [
        ("guided", "FIXTURE_GUIDED_L1", ph, rv) for ph, rv in (("BEFORE_SETUP", "False"), ("DEVELOPMENT", "False"),
                                                               ("DECISION", "False"), ("POST_REVEAL", "True"),
                                                               ("POST_REVEAL", "True"))]
    assert [x["studied_setup"] for x in rows] == ["", "", "", f"{PDC} UP {PDC_ID}", f"{PDC} UP {PDC_ID}"]
    assert rows[2]["valid_setups_at_cutoff"] == f"{PDC} UP" and rows[1]["valid_setups_at_cutoff"] == ""
    ev = [json.loads(x) for x in m["evidence.jsonl"].splitlines()]
    for e in ev[:3]:  # before the reveal: no studied setup anywhere in the record's lesson block
        assert "setup" not in e["lesson"] and PDC_ID not in json.dumps(e["lesson"])
    def pdc(e):
        return next(x for x in e["setup_summary"] if (x["family"], x["direction"]) == (PDC, "UP"))

    assert pdc(ev[1])["state"] == "DEVELOPING" and pdc(ev[2])["state"] == "CANDIDATE"
    assert pdc(ev[1])["missing"] == ["LAB_DIRECTIONAL_CONFIRMATION_V1:PENDING"]
    s = json.loads(m["session.json"])
    assert s["session"]["modes"] == ["guided"] and s["session"]["lessons"] == ["FIXTURE_GUIDED_L1"]
    assert "Guided lesson FIXTURE_GUIDED_L1" in m["session.md"] and "valid setups: none" in m["session.md"]
    assert json.loads(m["manifest.json"])["export_schema_version"] == "TUTOR_SESSION_EXPORT_V2"


def test_37_secret_protection_still_applies_to_guided_sessions(dr_timeline, dr_setups, registry, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    c = client_for(dr_timeline, dr_setups, registry, FakeProvider())
    turn(c, "question", 8, 50, 0)
    turn(c, "message", 8, 50, 1, text=f"my key is {SECRET} and Authorization: Bearer abcdefghijklmnop1234")
    r = c.post(f"/api/sessions/{CUR}/tutor/export", json={"session_id": SESSION, "replay_cutoff_utc": at(8, 50).isoformat()})
    body = zipfile.ZipFile(io.BytesIO(r.content))
    text = "".join(body.read(k).decode() for k in body.namelist())
    assert SECRET not in text and "abcdefghijklmnop1234" not in text and "/home/" not in text


def test_38_campaign_dates_stay_refused(dr_timeline, dr_setups, registry):
    sealed = date(2026, 10, 20)
    lessons = {CUR: (FIX,), sealed: (GuidedLesson("SEALED_LESSON", sealed, "x", "y", FIX.phases, PDC, "UP", PDC_ID, ()),)}
    client = ScriptedClient()
    c = client_for(dr_timeline, dr_setups, registry, GroundedProvider(client), lessons)
    for d in (date(2026, 10, 12), sealed, date(2026, 11, 6)):
        assert c.get(f"/api/sessions/{d}/lessons").status_code == 404
        turn(c, "question", 9, 0, 0, lesson="SEALED_LESSON", d=d, status=404)
    assert client.requests == []


# --- the real lesson definition (static; the real data check runs at serve time and in the handoff) -----

def test_real_lesson_definition_is_well_formed():
    assert L1.trading_date == date(2026, 9, 30) and LESSONS[date(2026, 9, 30)] == (L1,)
    assert (L1.family, L1.direction, L1.instance_id) == ("VWAP_BOUNCE", "UP", "BOUNCE-UP-20260930T1350Z")
    assert [p.phase for p in L1.phases] == ["BEFORE_SETUP", "DEVELOPMENT", "DECISION", "POST_REVEAL"]
    assert [p.at_ct for p in L1.phases] == ["08:30", "08:35", "08:55", "09:00"]
    for p in L1.phases[:-1]:
        text = f"{L1.title} {p.label} {p.instructions} {p.fake_text}".lower()
        assert "bounce" not in text and "1350z" not in text and "vwap_bounce" not in text
    assert {c.split()[1] for _, c in L1.progression if c.startswith("condition")} == {"1", "2", "3", "4", "5"}


def test_prompt_and_turn_wiring(dr_timeline, dr_setups):
    i = position_index(dr_timeline, at(8, 55))
    cl = chart_lesson(dr_timeline, i, "a4", dr_setups.at(at(8, 55)))
    assert cl.lesson.definition.curriculum_module_id == DRYSDALE_MODULE.module_id  # frozen Drysdale guards apply
    assert [w.warning_id for w in cl.lesson.context.quality_warnings] == []  # the fixture analysis is AVAILABLE
    assert DRYSDALE_WARNING == "DRYSDALE:drysdale"
    ctx = TurnContext(TutorAction.QUESTION, LessonStage.QUESTION, 0, None, dr_timeline, i, (), dr_setups.at(at(8, 55)),
                      FIX)
    assert ctx.mode == "guided" and ctx.cutoff == at(8, 55)
