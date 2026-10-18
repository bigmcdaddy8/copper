"""0AC-A3 grounded real-model Tutor, tested without a model: scripted replies, a stub SDK, no network, no tokens."""
from __future__ import annotations

import hashlib
import json
import socket
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
import test_replay as fx_mod  # on sys.path via conftest (shared Laboratory fixture)
from _fx_state import FX
from dicks_laboratory.tutor_ai import ANSWER_JSON_SCHEMA, ProviderTimeout, ProviderUnavailable
from dicks_laboratory.tutor_evidence import LessonStage
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from tutor_poc import grounding
from tutor_poc.api import create_app
from tutor_poc.cli import app as cli_app
from tutor_poc.conversation import TutorSession
from tutor_poc.dev_sessions import DevSession
from tutor_poc.evidence import chart_lesson, evidence_document
from tutor_poc.pricing import PRICING, estimate_cost, pricing_for
from tutor_poc.prompt import PROMPT_VERSION, PROMPTS, prompt_sha256
from tutor_poc.providers import (
    ANSWER_SCHEMA_WIRE,
    AnthropicModelClient,
    FakeProvider,
    GroundedProvider,
    ModelReply,
    ProviderConfigError,
    TurnContext,
    Usage,
    provider_from_env,
)
from tutor_poc.snapshot import position_index
from tutor_poc.tutor import TutorAction

CUR, ct = fx_mod.CUR, fx_mod.ct
REPO = Path(__file__).resolve().parents[3]
SECRET = "FAKE-TEST-KEY-not-a-real-credential-0123456789"
MODEL = "claude-opus-5-5"

# The TUTOR_POC_SYSTEM_V1 text is pinned: editing it requires a new PROMPT_VERSION.
PINNED_PROMPTS = {"TUTOR_POC_SYSTEM_V1": "800e8675f2be7972cb6be8b812fe6e312f54d9ca325ce8f6596bc71f4d0e2fbc",
                  "TUTOR_POC_SYSTEM_V2_DRYSDALE": "2cb428de775984eca56b44072fafa499c2ce5a428d789a3bfc698e3bcd3e896c"}


# --- scripted transport ---------------------------------------------------------------------------

class ScriptedClient:
    """A ModelClient that returns queued replies (or raises queued errors) and records every request."""

    provider, model = "anthropic", MODEL

    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []

    def parameters(self):
        return {}

    def complete(self, system, user, schema):
        self.requests.append({"system": system, "user": json.loads(user), "schema": schema})
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def reply(doc, usage=Usage(1000, 200, 3000, 0), served=MODEL, latency=1.5, stop="end_turn"):
    text = doc if isinstance(doc, str) else json.dumps(doc)
    return ModelReply(text, served, latency, usage, {"input_tokens": usage.input_tokens,
                                                     "output_tokens": usage.output_tokens}, stop, "req_test")


def ref(pointer):
    return {"source": "LESSON_TIME", "pointer": pointer}


def claim(statement, category, pointers, asserted=()):
    return {"statement": statement, "category": category, "evidence_refs": [ref(p) for p in pointers],
            "asserted": [{"ref": ref(p), "value": v} for p, v in asserted], "curriculum_source_id": None}


def answer(text, claims=(), unsupported=(), uncertainties=()):
    return {"answer_text": text, "claims": list(claims), "uncertainties": list(uncertainties), "quality_warnings": [],
            "unsupported_claims": list(unsupported)}


def setup_at(tl, i):
    return FX["setups"].at(tl.positions[i].cutoff_utc)


def load_setups(s):
    return FX["setups"]


def lesson_at(tl, hh, mm, lesson_id="x"):
    i = position_index(tl, ct(CUR, hh, mm))
    return chart_lesson(tl, i, lesson_id, setup_at(tl, i))


@pytest.fixture(scope="module")
def doc0900(fx_timeline):
    i = position_index(fx_timeline, ct(CUR, 9, 0))
    return evidence_document(fx_timeline, i, setup_at(fx_timeline, i))


@pytest.fixture(scope="module")
def good(doc0900):
    b = doc0900["latest_bar"]
    return answer(
        f"The latest candle closed at {b['close']}, {b['close_vs_vwap'].lower()} VWAP at {b['vwap']}. "
        "What do you notice about where it sits between the bands?",
        [claim("The latest completed bar closed at the stated price.", "OBSERVED_FACT", ["/latest_bar/close"],
               [("/latest_bar/close", b["close"])]),
         claim("Globex VWAP at that bar's close.", "DERIVED_FACT", ["/latest_bar/vwap"], [("/latest_bar/vwap", b["vwap"])]),
         claim("The close is on this side of VWAP.", "DERIVED_FACT", ["/latest_bar/close_vs_vwap"],
               [("/latest_bar/close_vs_vwap", b["close_vs_vwap"])]),
         claim("Sitting near VWAP may mean neither side has pushed far yet.", "AI_INTERPRETATION",
               ["/latest_bar/close", "/latest_bar/vwap"])])


def dref(pointer):
    return {"source": "DRYSDALE", "pointer": pointer}


def dclaim(statement, category, pointers, asserted=()):
    return {"statement": statement, "category": category, "evidence_refs": [dref(p) for p in pointers],
            "asserted": [{"ref": dref(p), "value": v} for p, v in asserted], "curriculum_source_id": None}


@pytest.fixture(scope="module")
def good_hint(doc0900):
    """A4 hint shape: where to look, no numbers laid out side by side."""
    b = doc0900["latest_bar"]
    return answer("Look at where the latest close sits against its own +1 sigma band, then compare that with the bars "
                  "before it.", [claim("The latest close is on this side of VWAP.", "DERIVED_FACT",
                                       ["/latest_bar/close_vs_vwap"], [("/latest_bar/close_vs_vwap", b["close_vs_vwap"])])])


@pytest.fixture(scope="module")
def good_explain(doc0900):
    """A4 explain shape: fact -> interpretation -> setup relevance (cites the setup analysis)."""
    b = doc0900["latest_bar"]
    return answer(f"The latest candle closed {b['close_vs_vwap'].lower()} VWAP. That location matters because each "
                  "Drysdale setup starts from where price sits against the bands; no setup is complete here yet.",
                  [claim("The close vs VWAP.", "DERIVED_FACT", ["/latest_bar/close_vs_vwap"],
                         [("/latest_bar/close_vs_vwap", b["close_vs_vwap"])]),
                   claim("Price near VWAP leaves several setup families open.", "AI_INTERPRETATION",
                         ["/latest_bar/close_vs_vwap"]),
                   dclaim("The Laboratory V1 setup analysis state (DRYSDALE_SETUP_CANDIDATES_V1).", "CANDIDATE",
                          ["/analysis/state"], [("/analysis/state", "DEVELOPING")])])


@pytest.fixture(scope="module")
def registry(fx_timeline):
    return (DevSession(CUR, "synthetic.sqlite3", fx_timeline.database_sha256, True),
            DevSession(date(2026, 10, 12), "campaign.sqlite3", "0" * 64, True))  # wrongly registered, still sealed


def make_client(fx_timeline, registry, provider, run_log=None):
    def load(s):
        assert s.trading_date == CUR
        return fx_timeline

    return TestClient(create_app(registry, load, web_dist=None, provider=provider, run_log=run_log,
                                 load_setups=load_setups))


def post(client, action, at=None, stage="QUESTION", turn=0, text=None, session="page-0001", d=CUR, status=200):
    body = {"action": action, "replay_cutoff_utc": (at or ct(CUR, 9, 0)).isoformat(), "stage": stage, "turn": turn,
            "session_id": session}
    if text is not None:
        body["text"] = text
    r = client.post(f"/api/sessions/{d}/tutor/turn", json=body)
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("no network in zero-cost tests")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)


# --- provider / configuration ---------------------------------------------------------------------

def test_fake_provider_is_the_default_and_needs_no_credentials(no_network):
    p = provider_from_env({})
    assert isinstance(p, FakeProvider) and p.public_config()["mode"] == "fake"


def test_fake_turn_reports_provider_fake_and_zero_cost(fx_timeline, registry, no_network):
    r = post(make_client(fx_timeline, registry, FakeProvider()), "question")
    assert r["status"] == "FAKE" and r["text"] and r["error"] is None
    assert r["diagnostics"]["turn_cost_usd"] == "0.000000" and r["diagnostics"]["usage"] is None
    assert r["diagnostics"]["model"] is None and r["diagnostics"]["session"]["cost_usd"] == "0.000000"


def test_real_provider_config_never_reaches_the_browser(fx_timeline, registry, doc0900, good, no_network):
    p = provider_from_env({"TUTOR_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": SECRET})
    p.client = ScriptedClient(reply(good))
    c = make_client(fx_timeline, registry, p)
    cfg = c.get("/api/tutor/config").json()
    assert cfg == {"mode": "real", "provider": "anthropic", "provider_id": "anthropic", "model": MODEL,
                   "effort": "low", "prompt_version": PROMPT_VERSION, "pricing_version": PRICING[0].pricing_version}
    r = c.post(f"/api/sessions/{CUR}/tutor/turn", json={"action": "question", "replay_cutoff_utc": ct(CUR, 9, 0).isoformat(),
                                                         "stage": "QUESTION", "turn": 0})
    for body in (json.dumps(cfg), r.text):
        assert SECRET not in body and "sk-ant" not in body and "api_key" not in body.lower()
    assert PROMPTS[PROMPT_VERSION][:60] not in r.text  # the prompt text is not sent to the browser either


def test_missing_credentials_fail_clearly():
    with pytest.raises(ProviderConfigError, match="ANTHROPIC_API_KEY"):
        provider_from_env({"TUTOR_PROVIDER": "anthropic"})


def test_serve_refuses_to_start_without_credentials(monkeypatch):
    monkeypatch.setenv("TUTOR_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = CliRunner().invoke(cli_app, ["serve"])
    assert r.exit_code == 2 and "ANTHROPIC_API_KEY" in r.output


@pytest.mark.parametrize("env, match", [
    ({"TUTOR_PROVIDER": "openai"}, "unknown TUTOR_PROVIDER"),
    ({"TUTOR_PROVIDER": "anthropic", "TUTOR_MODEL": "claude-made-up-9", "ANTHROPIC_API_KEY": SECRET}, "no pricing"),
    ({"TUTOR_PROVIDER": "anthropic", "TUTOR_EFFORT": "turbo", "ANTHROPIC_API_KEY": SECRET}, "unknown TUTOR_EFFORT"),
])
def test_unsupported_configuration_fails_clearly(env, match):
    with pytest.raises(ProviderConfigError, match=match):
        provider_from_env(env)


def test_live_smoke_is_opt_in(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = CliRunner().invoke(cli_app, ["live-smoke"])
    assert r.exit_code == 2 and "--yes" in r.output


# --- the request: only authorized, as-of evidence ------------------------------------------------

def _ctx(tl, hh, mm, action=TutorAction.QUESTION, stage=LessonStage.QUESTION, text=None, history=()):
    i = position_index(tl, ct(CUR, hh, mm))
    return TurnContext(action, stage, 0, text, tl, i, history, setup_at(tl, i))


def test_request_carries_only_the_current_cutoff_evidence(fx_timeline, good):
    client = ScriptedClient(reply(good))
    GroundedProvider(client).respond(_ctx(fx_timeline, 9, 0))
    user = client.requests[0]["user"]
    assert user["evidence"]["replay_cutoff_ct"] == "09:00" and user["evidence"]["trading_date"] == CUR.isoformat()
    cl = lesson_at(fx_timeline, 9, 0)
    ev = user["evidence"]
    shown = [(r[0], r[1]) for src in ("LESSON_TIME", "DRYSDALE") for r in ev[src]["items"]]
    shown += [(f"{row[0]}/{col}", v) for t in (ev["LESSON_TIME"]["bars"], ev["DRYSDALE"]["setups"],
                                               ev["DRYSDALE"]["conditions"], ev["DRYSDALE"]["completed_today"])
              for row in t["rows"] for col, v in zip(t["columns"][1:], row[1:], strict=True)]
    items = {i.ref.pointer: i.value for i in cl.lesson.context.items()}
    assert shown and all(items[p] == v for p, v in shown)  # every value shown is an authorized item, exactly
    assert {p for p in items if not p.startswith("/catalog/")} == {p for p, _ in shown}  # the catalog: system prompt
    raw = json.dumps(user)
    for forbidden in (fx_timeline.dataset_id, fx_timeline.database_sha256, ".sqlite3", "/home/", cl.sha256):
        assert forbidden not in raw


def test_future_bars_are_absent_from_the_payload(fx_timeline):
    early = position_index(fx_timeline, ct(CUR, 9, 0))
    doc = evidence_document(fx_timeline, early, setup_at(fx_timeline, early))
    cutoff = fx_timeline.positions[early].cutoff_utc
    later = [b for p in fx_timeline.positions[early + 1:] for b in p.bars if b.end_utc > cutoff]
    assert later, "the fixture must have bars after the cutoff"
    times = {b["start_ct"] for b in doc["recent_bars"]} | {doc["latest_bar"]["start_ct"]}
    assert all(b.start_utc.astimezone(fx_mod.CT).strftime("%H:%M") not in times for b in later)
    assert all(b.end_utc <= cutoff for b in fx_timeline.positions[early].bars)


def test_conversation_from_a_later_cutoff_is_never_sent(fx_timeline, good):
    s = TutorSession()
    from tutor_poc.providers import TurnResult

    s.record(CUR, ct(CUR, 10, 0), "what about 10:00?", "reply", TurnResult("GROUNDED", "LATER FACT 123.45", "anthropic"))
    s.record(CUR, ct(CUR, 8, 30), "earlier question", "reply", TurnResult("GROUNDED", "earlier answer", "anthropic"))
    history = s.context(CUR, ct(CUR, 9, 0))
    client = ScriptedClient(reply(good))
    GroundedProvider(client).respond(_ctx(fx_timeline, 9, 0, history=history))
    sent = json.dumps(client.requests[0]["user"]["conversation"])
    assert "earlier answer" in sent and "LATER FACT" not in sent and "10:00" not in sent


def test_conversation_context_is_bounded(fx_timeline):
    s = TutorSession()
    from tutor_poc.providers import CONTEXT_MESSAGES, TurnResult

    for n in range(30):
        s.record(CUR, ct(CUR, 8, 0), f"q{n}", "reply", TurnResult("GROUNDED", f"a{n}", "anthropic"))
    assert len(s.context(CUR, ct(CUR, 9, 0))) == CONTEXT_MESSAGES


# --- grounding / repair ----------------------------------------------------------------------------

def test_answer_schema_is_the_frozen_tutor_answer_shape():
    assert set(ANSWER_SCHEMA_WIRE["required"]) == set(ANSWER_JSON_SCHEMA["required"])
    assert "type" not in json.dumps(ANSWER_SCHEMA_WIRE).replace('"type": "', "")  # no type unions left


def test_valid_grounded_answer_is_accepted(fx_timeline, registry, good):
    c = make_client(fx_timeline, registry, GroundedProvider(ScriptedClient(reply(good))))
    r = post(c, "question")
    assert r["status"] == "GROUNDED" and r["text"] == good["answer_text"] and r["error"] is None
    g = r["grounding"]
    assert g["interpretations"] == 1 and [x["category"] for x in g["claims"]] == [
        "OBSERVED_FACT", "DERIVED_FACT", "DERIVED_FACT", "AI_INTERPRETATION"]
    assert g["claims"][0]["cites"][0]["label"] == "latest completed bar close"


HALLUCINATIONS = {
    "asserted": lambda b: answer("VWAP is right there.", [claim("The current VWAP.", "DERIVED_FACT",
                                                                 ["/latest_bar/vwap"], [("/latest_bar/vwap", "9999.00")])]),
    "prose": lambda b: answer("The current VWAP is 9999.00.", [claim("VWAP.", "DERIVED_FACT", ["/latest_bar/vwap"])]),
    "invented_pointer": lambda b: answer("Look at the session high.",
                                         [claim("Session high.", "OBSERVED_FACT", ["/session/high"],
                                                [("/session/high", "120.00")])]),
    "future_time": lambda b: answer("Watch the 10:30 candle.", [claim("Bar.", "DERIVED_FACT", ["/latest_bar/start_ct"])]),
    "interpretation_as_fact": lambda b: answer("Buyers are in control.",
                                               [claim("Buyers are in control.", "OBSERVED_FACT", ["/latest_bar/vwap"])]),
    "trade_advice": lambda b: answer("You could buy here.", [claim("Close.", "OBSERVED_FACT", ["/latest_bar/close"])]),
    "undefined_policy": lambda b: answer("Price shows acceptance above VWAP.",
                                         [claim("Acceptance above VWAP.", "AI_INTERPRETATION", ["/latest_bar/vwap"])]),
}


@pytest.mark.parametrize("name", sorted(HALLUCINATIONS))
def test_fabricated_or_unsafe_answers_fail_grounding(fx_timeline, doc0900, name):
    cl = lesson_at(fx_timeline, 9, 0)
    status, _, _, issues, _ = grounding.evaluate(json.dumps(HALLUCINATIONS[name](doc0900["latest_bar"])), cl,
                                                 LessonStage.QUESTION)
    assert status.value == "GROUNDING_FAILED" and issues


def test_rounded_evidence_values_and_evidence_times_are_accepted(fx_timeline, doc0900):
    cl = lesson_at(fx_timeline, 9, 0)
    b = doc0900["latest_bar"]
    rounded = str(Decimal(b["vwap"]).quantize(Decimal("0.1")))
    a = answer(f"The {b['start_ct']} candle closed below VWAP near {rounded}.",
               [claim("VWAP.", "DERIVED_FACT", ["/latest_bar/vwap"], [("/latest_bar/vwap", b["vwap"])])])
    assert grounding.evaluate(json.dumps(a), cl, LessonStage.QUESTION)[0].value == "GROUNDED"


def test_the_hallucinated_vwap_triggers_one_repair_and_is_never_shown(fx_timeline, registry, doc0900):
    bad = HALLUCINATIONS["prose"](doc0900["latest_bar"])
    client = ScriptedClient(reply(bad), reply(bad))
    c = make_client(fx_timeline, registry, GroundedProvider(client))
    r = post(c, "question")
    assert len(client.requests) == 2  # the first answer, then exactly one repair; no loop
    repair = client.requests[1]["user"]["repair"]
    assert any("UNGROUNDED_NUMBER" in e and "9999.00" in e for e in repair["validation_errors"])
    assert repair["previous_answer"] == json.dumps(bad)
    assert r["status"] == "GROUNDING_FAILED" and r["text"] is None
    assert r["error"] == "Tutor response could not be grounded in the replay evidence. Please try again."
    assert "9999" not in json.dumps({k: v for k, v in r.items() if k != "diagnostics"})
    assert r["diagnostics"]["repair_attempts"] == 1 and r["diagnostics"]["attempts"] == 2
    assert r["stage"] == "QUESTION"


def test_a_successful_repair_is_accepted(fx_timeline, registry, doc0900, good):
    client = ScriptedClient(reply(HALLUCINATIONS["asserted"](doc0900["latest_bar"])), reply(good))
    r = post(make_client(fx_timeline, registry, GroundedProvider(client)), "question")
    assert r["status"] == "GROUNDED" and r["text"] == good["answer_text"]
    assert r["diagnostics"]["repair_attempts"] == 1
    assert any("VALUE_MISMATCH" in e for e in client.requests[1]["user"]["repair"]["validation_errors"])


def test_malformed_output_is_not_shown(fx_timeline, registry):
    client = ScriptedClient(reply("not json"), reply('{"answer_text": "hi"}'))
    r = post(make_client(fx_timeline, registry, GroundedProvider(client)), "question")
    assert r["status"] == "INVALID_STRUCTURED_OUTPUT" and r["text"] is None and r["error"]


@pytest.mark.parametrize("exc, status", [(ProviderTimeout("slow"), "PROVIDER_TIMEOUT"),
                                         (ProviderUnavailable("HTTP 500"), "PROVIDER_UNAVAILABLE")])
def test_provider_failures_are_graceful_and_not_retried_as_repairs(fx_timeline, registry, exc, status):
    client = ScriptedClient(exc)
    c = make_client(fx_timeline, registry, GroundedProvider(client))
    r = post(c, "question")
    assert r["status"] == status and r["text"] is None and r["error"] and len(client.requests) == 1
    assert "HTTP 500" not in r["error"] and "Traceback" not in json.dumps(r)
    assert c.get("/api/sessions").status_code == 200  # still usable


# --- usage / cost ----------------------------------------------------------------------------------

def test_cost_uses_the_versioned_pricing():
    p = pricing_for("anthropic", MODEL)
    assert (p.input_per_mtok, p.output_per_mtok, p.cache_read_per_mtok, p.cache_write_per_mtok) == (
        Decimal("4"), Decimal("20"), Decimal("0.20"), Decimal("5"))
    # 1000 * $4 + 200 * $20 + 3000 * $0.20 + 400 * $5, per million tokens
    assert estimate_cost(p, 1000, 200, 3000, 400) == Decimal("0.0106")


def test_turn_diagnostics_and_session_totals(fx_timeline, registry, good, good_hint):
    client = ScriptedClient(reply(good, Usage(1000, 200, 3000, 0), latency=2.0),
                            reply(good_hint, Usage(500, 100, 0, 2000), latency=1.0))
    c = make_client(fx_timeline, registry, GroundedProvider(client, "low"))
    d1 = post(c, "question")["diagnostics"]
    assert d1["provider"] == "anthropic" and d1["model"] == MODEL and d1["served_model"] == MODEL
    assert d1["prompt_version"] == PROMPT_VERSION and d1["prompt_sha256"] == prompt_sha256()
    assert d1["pricing_version"] == PRICING[0].pricing_version and d1["effort"] == "low"
    assert d1["usage"] == {"input_tokens": 1000, "output_tokens": 200, "cached_input_tokens": 3000,
                           "cache_write_input_tokens": 0, "total_input_tokens": 4000}
    assert d1["latency_ms"]["model"] == 2000.0 and d1["latency_ms"]["total"] >= 0 and "evidence" in d1["latency_ms"]
    assert d1["repair_attempts"] == 0 and d1["evidence_bytes"] > 1000
    assert d1["request_bytes"][0] > d1["evidence_bytes"]  # payload bytes are not the whole request
    assert d1["turn_cost_usd"] == "0.008600" and d1["raw_usage"] == [{"input_tokens": 1000, "output_tokens": 200}]
    d2 = post(c, "hint", stage="QUESTION", turn=1)["diagnostics"]
    assert d2["turn_cost_usd"] == "0.014000"  # 500*4 + 100*20 + 2000*5
    s = d2["session"]
    assert (s["turns"], s["model_calls"], s["input_tokens"], s["output_tokens"], s["cached_input_tokens"],
            s["cache_write_input_tokens"], s["cost_usd"]) == (2, 2, 1500, 300, 3000, 2000, "0.022600")


def test_failed_turns_still_count_their_cost(fx_timeline, registry, doc0900):
    bad = HALLUCINATIONS["prose"](doc0900["latest_bar"])
    c = make_client(fx_timeline, registry, GroundedProvider(ScriptedClient(reply(bad), reply(bad))))
    s = post(c, "question")["diagnostics"]["session"]
    assert s["model_calls"] == 2 and s["cost_usd"] == "0.017200"


def test_raw_usage_is_kept_when_a_turn_cannot_be_priced(fx_timeline, registry, good):
    client = ScriptedClient(reply(good, Usage(10, 20, None, None), served="claude-opus-4-8"))
    d = post(make_client(fx_timeline, registry, GroundedProvider(client)), "question")["diagnostics"]
    assert d["turn_cost_usd"] is None and d["usage"]["input_tokens"] == 10 and d["usage"]["cached_input_tokens"] is None
    assert d["session"]["unpriced_calls"] == 1 and d["served_model"] == "claude-opus-4-8"


def test_session_totals_are_per_page_session(fx_timeline, registry, good):
    c = make_client(fx_timeline, registry, GroundedProvider(ScriptedClient(reply(good), reply(good))))
    post(c, "question", session="page-aaaa")
    assert post(c, "question", session="page-bbbb")["diagnostics"]["session"]["turns"] == 1


def test_run_log_records_attempts_without_secrets(fx_timeline, registry, doc0900, good, tmp_path):
    log = tmp_path / "runs.jsonl"
    p = GroundedProvider(ScriptedClient(reply(HALLUCINATIONS["prose"](doc0900["latest_bar"])), reply(good)))
    post(make_client(fx_timeline, registry, p, run_log=log), "question")
    rec = json.loads(log.read_text().splitlines()[0])
    assert rec["status"] == "GROUNDED" and len(rec["attempt_records"]) == 2
    assert rec["attempt_records"][0]["issues"] and "9999.00" in rec["attempt_records"][0]["response_text"]
    assert PROMPTS[PROMPT_VERSION] not in log.read_text()


# --- replay synchronization ----------------------------------------------------------------------

@pytest.mark.parametrize("hh, mm", [(9, 0), (9, 30)])
def test_reply_is_bound_to_the_request_cutoff(fx_timeline, registry, hh, mm):
    at = f"{hh:02d}:{mm:02d}"
    client = ScriptedClient(reply(answer("Let's look at this position.", [
        claim("The replay cutoff.", "DERIVED_FACT", ["/replay/cutoff_ct"], [("/replay/cutoff_ct", at)])])))
    r = post(make_client(fx_timeline, registry, GroundedProvider(client)), "question", at=ct(CUR, hh, mm))
    assert r["replay_cutoff_utc"] == ct(CUR, hh, mm).isoformat()
    assert client.requests[0]["user"]["evidence"]["replay_cutoff_ct"] == at and r["status"] == "GROUNDED"


# --- Tutor UX through the real provider ---------------------------------------------------------

def test_message_hint_and_explain_use_the_real_provider(fx_timeline, registry, good, good_hint, good_explain):
    client = ScriptedClient(reply(good), reply(good_hint), reply(good_explain))
    c = make_client(fx_timeline, registry, GroundedProvider(client))
    m = post(c, "message", text="It closed below VWAP", turn=1)
    h = post(c, "hint", stage=m["stage"], turn=2)
    e = post(c, "explain", stage=h["stage"], turn=3)
    assert [(q["user"]["action"], q["user"]["stage"]) for q in client.requests] == [
        ("MESSAGE", "QUESTION"), ("HINT", "HINT"), ("EXPLAIN", "ANSWER")]
    assert client.requests[0]["user"]["student_message"] == "It closed below VWAP"
    assert [x["stage"] for x in (m, h, e)] == ["QUESTION", "HINT", "ANSWER"]
    assert [x["role"] for x in client.requests[2]["user"]["conversation"]] == ["student", "tutor", "tutor"]


def test_show_evidence_stays_deterministic_and_model_free(fx_timeline, registry):
    client = ScriptedClient()
    c = make_client(fx_timeline, registry, GroundedProvider(client))
    fake = make_client(fx_timeline, registry, FakeProvider())
    q = {"cutoff": ct(CUR, 9, 0).isoformat()}
    a = c.get(f"/api/sessions/{CUR}/tutor/evidence", params=q).json()
    assert a == fake.get(f"/api/sessions/{CUR}/tutor/evidence", params=q).json() and a["schema"] == "TUTOR_POC_EVIDENCE_V1"
    assert client.requests == []


def test_campaign_dates_are_refused_before_any_model_call(fx_timeline, registry):
    client = ScriptedClient()
    c = make_client(fx_timeline, registry, GroundedProvider(client))
    post(c, "question", at=ct(date(2026, 10, 12), 9, 0), d=date(2026, 10, 12), status=404)
    assert client.requests == []


# --- the Anthropic transport (stub SDK object; nothing leaves the process) -----------------------

class StubMessages:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def create(self, **kw):
        self.calls.append(kw)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _sdk(outcome):
    m = StubMessages(outcome)
    return SimpleNamespace(beta=SimpleNamespace(messages=m)), m


def _response(text, model=MODEL, content_extra=()):
    usage = SimpleNamespace(input_tokens=1200, output_tokens=150, cache_read_input_tokens=2600,
                            cache_creation_input_tokens=0, iterations=None,
                            model_dump=lambda **k: {"input_tokens": 1200, "output_tokens": 150,
                                                    "cache_read_input_tokens": 2600, "cache_creation_input_tokens": 0})
    return SimpleNamespace(content=[*content_extra, SimpleNamespace(type="text", text=text)], model=model,
                           stop_reason="end_turn", usage=usage, _request_id="req_stub")


def test_anthropic_request_shape(no_network):
    sdk, m = _sdk(_response("{}"))
    c = AnthropicModelClient(MODEL, "low", SECRET, sdk_client=sdk)
    c.complete("SYSTEM", "USER", ANSWER_SCHEMA_WIRE)
    kw = m.calls[0]
    assert kw["model"] == MODEL and kw["messages"] == [{"role": "user", "content": "USER"}]
    assert kw["system"] == [{"type": "text", "text": "SYSTEM", "cache_control": {"type": "ephemeral"}}]
    assert kw["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": ANSWER_SCHEMA_WIRE}}
    assert "temperature" not in kw and "tool_choice" not in kw and "thinking" not in kw  # rejected by this model
    assert kw["fallbacks"] == "default" and kw["betas"] == ["server-side-fallback-2026-07-01"]
    assert SECRET not in json.dumps(kw, default=str)


def test_anthropic_usage_is_parsed_from_the_provider(no_network):
    sdk, _ = _sdk(_response('{"a": 1}'))
    r = AnthropicModelClient(MODEL, "low", SECRET, sdk_client=sdk).complete("S", "U", {})
    assert r.text == '{"a": 1}' and r.served_model == MODEL and r.request_id == "req_stub" and not r.fallback_used
    assert r.usage == Usage(1200, 150, 2600, 0) and r.raw_usage["cache_read_input_tokens"] == 2600


def test_anthropic_fallback_is_detected(no_network):
    sdk, _ = _sdk(_response("{}", "claude-opus-4-8", (SimpleNamespace(type="fallback"),)))
    assert AnthropicModelClient(MODEL, "low", SECRET, sdk_client=sdk).complete("S", "U", {}).fallback_used


_REQ = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize("exc, expected", [
    (anthropic.APITimeoutError(request=_REQ), ProviderTimeout),
    (anthropic.InternalServerError("boom secret body", response=httpx2.Response(500, request=_REQ), body=None),
     ProviderUnavailable),
    (anthropic.AuthenticationError("bad key", response=httpx2.Response(401, request=_REQ), body=None),
     ProviderUnavailable),
    (anthropic.APIConnectionError(request=_REQ), ProviderUnavailable),
])
def test_anthropic_errors_map_to_typed_failures_without_bodies(exc, expected, no_network):
    sdk, _ = _sdk(exc)
    with pytest.raises(expected) as info:
        AnthropicModelClient(MODEL, "low", SECRET, sdk_client=sdk).complete("S", "U", {})
    assert "secret body" not in str(info.value) and SECRET not in str(info.value)


# --- versioning and the frozen boundary ---------------------------------------------------------

def test_prompt_versions_are_pinned():
    assert {v: prompt_sha256(v) for v in PROMPTS} == PINNED_PROMPTS


def test_frozen_tutor_modules_are_unchanged():
    """A3 reuses the 0AB-C-frozen tutor layer by import only (docs/dicks_laboratory/evidence/0AB-C/FREEZE_ADDENDUM.md)."""
    lab = REPO / "apps/dicks_laboratory/src/dicks_laboratory"
    assert hashlib.sha256((lab / "tutor_ai.py").read_bytes()).hexdigest() == \
        "f9a702286e3126c07808f77d3a588056f661b87ad999fdc50504237f1e97f1c9"
    assert hashlib.sha256((lab / "tutor_evidence.py").read_bytes()).hexdigest() == \
        "318853db3bb8aadb7dc51075315f4afad7c18eb7977bd2472acdd74624c8e8b0"
