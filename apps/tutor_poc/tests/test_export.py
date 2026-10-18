"""0AC-A3E Export Session: the in-memory Tutor session as a ZIP evaluation artifact (zero cost, no network)."""
# ruff: noqa: F811  (pytest fixtures imported from test_real_provider are injected by name)
from __future__ import annotations

import csv
import dataclasses
import hashlib
import io
import itertools
import json
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest
from dicks_laboratory.tutor_ai import ProviderTimeout
from fastapi.testclient import TestClient
from test_real_provider import (  # noqa: F401  (fixtures: doc0900, good, registry, no_network)
    CUR,
    MODEL,
    SECRET,
    HALLUCINATIONS,
    ScriptedClient,
    _response,
    _sdk,
    answer,
    claim,
    ct,
    doc0900,
    good,
    good_hint,
    load_setups,
    no_network,
    post,
    registry,
    reply,
)

from tutor_poc import export
from tutor_poc.api import create_app
from tutor_poc.conversation import TurnRecord
from tutor_poc.dev_sessions import SealedDateError
from tutor_poc.providers import AnthropicModelClient, FakeProvider, GroundedProvider, Usage
from tutor_poc.snapshot import position_index

FILES = ["session.md", "session.json", "turns.csv", "evidence.jsonl", "market_context.csv", "manifest.json"]
T0 = datetime(2026, 10, 17, 15, 0, 0, tzinfo=UTC)
HUMAN_1 = 'Looks like maybe ~4pts\nnot sure, "below" VWAP?'
HUMAN_2 = "closed abv the +1sd i think,, maybe 2 pts"
SESSION = "page-export-1"


class Clock:
    """Wall-clock stand-in: every call is 3 seconds after the previous one."""

    def __init__(self):
        self.ticks = (T0 + timedelta(seconds=3 * k) for k in itertools.count())

    def __call__(self):
        return next(self.ticks)


def app_client(fx_timeline, registry, provider):
    def load(s):
        assert s.trading_date == CUR
        return fx_timeline

    return TestClient(create_app(registry, load, web_dist=None, provider=provider, clock=Clock(),
                                 load_setups=load_setups))


def do_export(c, at, session=SESSION, d=CUR, status=200):
    r = c.post(f"/api/sessions/{d}/tutor/export", json={"session_id": session, "replay_cutoff_utc": at.isoformat()})
    assert r.status_code == status, r.text
    return r


def unzip(r):
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return {n: z.read(n).decode("utf-8") for n in z.namelist()}


def rows(text):
    return list(csv.DictReader(io.StringIO(text)))


def evidence_lines(m):
    return [json.loads(x) for x in m["evidence.jsonl"].splitlines()]


def answer_at(hh, mm):
    at = f"{hh:02d}:{mm:02d}"
    return answer(f"We are at the {at} replay position. What stands out?", [
        claim("The replay cutoff.", "DERIVED_FACT", ["/replay/cutoff_ct"], [("/replay/cutoff_ct", at)])])


# --- scripted sessions ----------------------------------------------------------------------------

@pytest.fixture
def fake_session(fx_timeline, registry, no_network):
    """09:00 question · Human reply · Hint · +5m · Human reply · Explain (the A3E smoke flow)."""
    c = app_client(fx_timeline, registry, FakeProvider())
    s9, s95 = ct(CUR, 9, 0), ct(CUR, 9, 5)
    shown = [post(c, "question", at=s9, turn=0, session=SESSION)]
    shown.append(post(c, "message", at=s9, turn=1, text=HUMAN_1, stage=shown[-1]["stage"], session=SESSION))
    shown.append(post(c, "hint", at=s9, turn=2, stage=shown[-1]["stage"], session=SESSION))
    shown.append(post(c, "message", at=s95, turn=3, text=HUMAN_2, stage=shown[-1]["stage"], session=SESSION))
    shown.append(post(c, "explain", at=s95, turn=4, stage=shown[-1]["stage"], session=SESSION))
    return c, shown


@pytest.fixture
def real_session(fx_timeline, registry, doc0900, good, good_hint, no_network):
    """Grounded / failed after a repair / repaired / grounded at 09:05 / provider timeout, with scripted usage."""
    bad = HALLUCINATIONS["prose"](doc0900["latest_bar"])
    client = ScriptedClient(reply(good, Usage(1000, 200, 3000, 0), latency=2.0),
                            reply(bad, Usage(900, 300, 3000, 0)), reply(bad, Usage(950, 310, 3000, 0)),
                            reply(bad, Usage(800, 150, 3000, 0)), reply(good_hint, Usage(820, 160, 3000, 0)),
                            reply(answer_at(9, 5), Usage(700, 120, 3000, 0)), ProviderTimeout("slow"))
    c = app_client(fx_timeline, registry, GroundedProvider(client, "low"))
    s9, s95 = ct(CUR, 9, 0), ct(CUR, 9, 5)
    shown = [post(c, "question", at=s9, turn=0, session=SESSION),
             post(c, "message", at=s9, turn=1, text=HUMAN_1, session=SESSION),
             post(c, "hint", at=s9, turn=2, session=SESSION),
             post(c, "question", at=s95, turn=3, session=SESSION),
             post(c, "hint", at=s95, turn=4, session=SESSION)]
    return c, shown, client


# --- session.md -----------------------------------------------------------------------------------

def test_markdown_preserves_exact_texts_labels_cutoffs(fake_session):
    c, shown = fake_session
    md = unzip(do_export(c, ct(CUR, 9, 5)))["session.md"]
    assert md.startswith("# Dick's Laboratory Tutor Session\n")
    assert HUMAN_1 in md and HUMAN_2 in md  # exactly as typed: no spelling or wording cleanup
    for r in shown:
        assert r["text"] in md
    order = [md.index(x) for x in ("## Replay 09:00 CT", "### Tutor — Question", "### Human", "### Tutor — Hint",
                                   "## Replay 09:05 CT", "### Tutor — Explain")]
    assert order == sorted(order)
    assert md.count("## Replay ") == 2 and "provider: fake (scripted, no model call) · cost $0" in md


def test_markdown_carries_real_diagnostics_grounding_and_failures(real_session):
    c, shown, _ = real_session
    md = unzip(do_export(c, ct(CUR, 9, 5)))["session.md"]
    assert "Model: claude-opus-5-5" in md and "Prompt version: TUTOR_POC_SYSTEM_V2_DRYSDALE" in md
    assert "Grounding:\n- 1 observed fact\n- 2 derived facts\n- 1 interpretation" in md
    assert "- turn cost: $0.0086 · session cost after turn: $0.0086" in md
    assert "### Tutor — Reply (not shown: GROUNDING_FAILED)" in md
    assert "Error shown to the Human: Tutor response could not be grounded" in md
    assert "### Tutor — Hint (not shown: PROVIDER_TIMEOUT)" in md
    assert "- model calls: 2 · repairs: 1" in md
    assert "9999" not in md  # the rejected answer is never exported
    assert "Total turns: 5 (3 accepted, 2 failed)" in md


# --- session.json ---------------------------------------------------------------------------------

def test_json_is_versioned_with_metadata_ordering_and_positions(real_session):
    c, shown, _ = real_session
    j = json.loads(unzip(do_export(c, ct(CUR, 9, 5)))["session.json"])
    assert j["schema_version"] == "TUTOR_SESSION_EXPORT_V2"
    s = j["session"]
    assert (s["instrument"], s["trading_date"], s["provider"], s["model"], s["effort"]) == (
        "/ES", CUR.isoformat(), "anthropic", MODEL, "low")
    assert s["prompt_version"] == "TUTOR_POC_SYSTEM_V2_DRYSDALE" and s["pricing_version"]
    assert s["wall_clock"]["started_at_utc"] == T0.isoformat()  # the first turn's request time
    assert s["replay"]["first_turn_cutoff_ct"] == "09:00" and s["replay"]["export_cutoff_ct"] == "09:05"
    assert s["totals"] == shown[-1]["diagnostics"]["session"]  # the values the UI showed, not recomputed
    assert [t["turn_id"] for t in j["turns"]] == [f"turn-000{k}" for k in range(1, 6)]
    assert [t["client_turn"] for t in j["turns"]] == [0, 1, 2, 3, 4]
    assert [(m["role"], m["kind"]) for m in j["messages"]] == [
        ("tutor", "question"), ("human", "human"), ("tutor", "hint"), ("tutor", "question")]
    assert j["messages"][1]["text"] == HUMAN_1
    assert [(p["replay_cutoff_ct"], p["turn_ids"], p["export_position"]) for p in j["replay_positions"]] == [
        ("09:00", ["turn-0001", "turn-0002", "turn-0003"], False), ("09:05", ["turn-0004", "turn-0005"], True)]
    assert j["turns"][2]["repair_attempted"] and j["turns"][2]["final_accepted"]
    assert j["turns"][1]["failure_category"] == "GROUNDING_FAILED" and not j["turns"][1]["final_accepted"]


def test_export_is_deterministic_for_the_same_session(real_session, fx_timeline):
    c, _, _ = real_session
    a, b = unzip(do_export(c, ct(CUR, 9, 5))), unzip(do_export(c, ct(CUR, 9, 5)))
    for name in ("turns.csv", "evidence.jsonl", "market_context.csv"):
        assert a[name] == b[name]
    strip = lambda t: "\n".join(x for x in t.splitlines() if "xported" not in x and "created_at" not in x)  # noqa: E731
    assert strip(a["session.md"]) == strip(b["session.md"]) and strip(a["session.json"]) == strip(b["session.json"])


# --- turns.csv ------------------------------------------------------------------------------------

def test_turns_csv_columns_quoting_and_values(real_session):
    c, shown, _ = real_session
    m = unzip(do_export(c, ct(CUR, 9, 5)))
    rs = rows(m["turns.csv"])
    assert list(rs[0]) == list(export.TURN_COLUMNS) and len(rs) == 5
    assert rs[1]["human_text"] == HUMAN_1  # multiline text with quotes and commas round-trips
    assert rs[0]["text"] == shown[0]["text"] and rs[1]["text"] == ""
    assert (rs[0]["input_tokens"], rs[0]["output_tokens"], rs[0]["cached_tokens"], rs[0]["cache_write_tokens"]) == (
        "1000", "200", "3000", "0")
    assert rs[0]["turn_cost_usd"] == "0.008600" and rs[0]["model_latency_ms"] == "2000.0"
    assert rs[-1]["session_cost_usd_after_turn"] == shown[-1]["diagnostics"]["session"]["cost_usd"]
    assert (rs[1]["status"], rs[1]["final_accepted"], rs[1]["failure_category"], rs[1]["repair_attempts"]) == (
        "GROUNDING_FAILED", "False", "GROUNDING_FAILED", "1")
    assert (rs[2]["status"], rs[2]["final_accepted"], rs[2]["repair_attempts"]) == ("GROUNDED", "True", "1")
    assert rs[4]["status"] == "PROVIDER_TIMEOUT" and rs[4]["input_tokens"] == "" and rs[4]["error"]
    assert rs[0]["prompt_sha"] == shown[0]["diagnostics"]["prompt_sha256"]
    assert int(rs[2]["request_bytes"]) == sum(shown[2]["diagnostics"]["request_bytes"])
    assert (rs[0]["observed_facts"], rs[0]["derived_facts"], rs[0]["interpretations"]) == ("1", "2", "1")


# --- evidence.jsonl -------------------------------------------------------------------------------

def test_evidence_is_the_exact_object_each_model_call_received(real_session):
    c, _, client = real_session
    ev = evidence_lines(unzip(do_export(c, ct(CUR, 9, 5))))
    assert [e["turn_id"] for e in ev] == [f"turn-000{k}" for k in range(1, 6)]  # one per Tutor turn, failures too
    assert [e["replay_cutoff_ct"] for e in ev] == ["09:00", "09:00", "09:00", "09:05", "09:05"]
    sent = [q["user"]["evidence"] for q in client.requests]  # 7 calls: turns 2 and 3 have two attempts each
    assert [e["evidence"] for e in ev] == [sent[0], sent[1], sent[3], sent[5], sent[6]]
    assert sent[1] == sent[2] and sent[3] == sent[4]  # a repair uses the same evidence
    for e in ev:
        assert e["evidence_schema_version"] == "TUTOR_POC_MODEL_EVIDENCE_V2"
        assert e["evidence"]["replay_cutoff_ct"] == e["replay_cutoff_ct"]
        assert e["evidence_sha256"] == hashlib.sha256(export.canonical_json(e["evidence"]).encode()).hexdigest()
    assert ev[1]["grounding_result"]["attempts"][0]["issues"][0]["code"] == "UNGROUNDED_NUMBER"
    assert "9999" not in json.dumps(ev)  # issue codes only, never the rejected text or its details
    assert ev[2]["grounding_result"]["final_accepted"] and ev[2]["grounding_result"]["repair_attempts"] == 1


def test_earlier_turns_never_contain_later_evidence(real_session):
    c, _, _ = real_session
    ev = evidence_lines(unzip(do_export(c, ct(CUR, 9, 5))))
    for e in ev:
        bars = e["evidence"]["LESSON_TIME"]["bars"]
        ends = [row[bars["columns"].index("end_ct")] for row in bars["rows"]]
        assert ends and max(ends) <= e["replay_cutoff_ct"]
        assert all(m["replay_cutoff_ct"] <= e["replay_cutoff_ct"] for m in e["conversation_context"]["messages"])
    assert ev[0]["evidence"] != ev[3]["evidence"]


def test_fake_turn_evidence_is_the_show_evidence_object(fake_session):
    c, _ = fake_session
    ev = evidence_lines(unzip(do_export(c, ct(CUR, 9, 5))))
    assert len(ev) == 5
    for e in ev:
        shown = c.get(f"/api/sessions/{CUR}/tutor/evidence", params={"cutoff": e["replay_cutoff_utc"]}).json()
        assert e["evidence"] == shown and e["evidence_schema_version"] == "TUTOR_POC_EVIDENCE_V1"
        assert e["conversation_context"]["sent_to_model"] is False


# --- market_context.csv ---------------------------------------------------------------------------

def test_market_context_is_completed_bars_of_the_visited_window(real_session, fx_timeline):
    c, _, _ = real_session
    rs = rows(unzip(do_export(c, ct(CUR, 9, 5)))["market_context.csv"])
    assert list(rs[0]) == list(export.MARKET_COLUMNS)  # bars only: no tick / trade columns
    assert rs and all(r["bar_end_ct"] <= "09:05" for r in rs)
    p = fx_timeline.positions[position_index(fx_timeline, ct(CUR, 9, 5))]
    bars = {b.start_utc.isoformat(): b for b in p.bars}
    for r in rs:
        b = bars[r["bar_start_utc"]]  # Laboratory values of the chart position, not recomputed
        assert (r["close"], r["vwap"], r["plus_1_sigma"]) == (f"{b.close:.2f}", export._level(b.vwap),
                                                              export._level(b.upper_1sd))
    seen = {r["bar_start_ct"]: r["tutor_evidence"] for r in rs}
    assert "latest" in seen.values() and "recent" in seen.values()


def test_market_context_stops_at_the_latest_visited_cutoff(fx_timeline, registry, no_network):
    c = app_client(fx_timeline, registry, FakeProvider())
    post(c, "question", at=ct(CUR, 9, 5), session=SESSION)
    r = do_export(c, ct(CUR, 9, 0))  # the Human stepped back before exporting
    assert r.headers["content-disposition"] == f'attachment; filename="tutor_session_{CUR}_0905-0900.zip"'
    rs = rows(unzip(r)["market_context.csv"])
    later = [b for b in fx_timeline.positions[-1].bars if b.end_utc > ct(CUR, 9, 5)]
    assert later and rs and max(x["bar_end_ct"] for x in rs) <= "09:05"


# --- manifest -------------------------------------------------------------------------------------

def test_manifest_lists_files_flags_and_correct_hashes(fake_session):
    c, _ = fake_session
    r = do_export(c, ct(CUR, 9, 5))
    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert z.namelist() == FILES
    man = json.loads(z.read("manifest.json"))
    assert [f["name"] for f in man["files"]] == FILES
    assert man["export_schema_version"] == "TUTOR_SESSION_EXPORT_V2"
    assert man["campaign_data_included"] is False and man["contains_secrets"] is False
    for f in man["files"][:-1]:
        data = z.read(f["name"])
        assert f["sha256"] == hashlib.sha256(data).hexdigest() and f["bytes"] == len(data)
    assert (man["turns"], man["evidence_records"]) == (5, 5) and man["market_bars"] > 0
    assert man["review_prompt"] == "docs/dicks_laboratory/TUTOR_SESSION_REVIEW_PROMPT.md"


# --- security -------------------------------------------------------------------------------------

def test_no_secret_reaches_the_export(fx_timeline, registry, good, monkeypatch, no_network):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    monkeypatch.setenv("TUTOR_POC_TEST_TOKEN", "tok-0123456789abcdef-test")
    sdk, _ = _sdk(_response(json.dumps(good)))
    c = app_client(fx_timeline, registry, GroundedProvider(AnthropicModelClient(MODEL, "low", SECRET, sdk_client=sdk)))
    post(c, "question", session=SESSION)
    leaked = f"my key is {SECRET} and Authorization: Bearer sk-ant-api03-abcdefghijklmnopqrstuv tok-0123456789abcdef-test"
    post(c, "message", turn=1, text=leaked, session=SESSION)
    r = do_export(c, ct(CUR, 9, 0))
    blob = r.content + b"".join(zipfile.ZipFile(io.BytesIO(r.content)).read(n) for n in FILES)
    for bad in (SECRET, "sk-ant", "Authorization", "Bearer", "tok-0123456789abcdef-test", "ANTHROPIC_API_KEY",
                "anthropic.env", "/home/"):
        assert bad.encode() not in blob
    assert json.loads(unzip(r)["manifest.json"])["redactions"] >= 3


def test_sanitize_and_secret_values():
    env = {"ANTHROPIC_API_KEY": SECRET, "PATH": "/usr/bin:/bin:/usr/local/bin", "SHORT_KEY": "abc"}
    assert export.secret_values(env) == (SECRET,)
    text, n = export.sanitize(f"a {SECRET} b x-api-key: zzz /home/someone/x", (SECRET,), "/home/someone")
    assert text == "a [REDACTED] b [REDACTED] ~/x" and n == 3
    assert export.find_secrets(text, (SECRET,)) == []


# --- campaign protection --------------------------------------------------------------------------

def test_export_cannot_open_a_campaign_date(fx_timeline, registry, no_network):
    c = app_client(fx_timeline, registry, FakeProvider())
    post(c, "question", session=SESSION)
    for d in (date(2026, 10, 12), date(2026, 10, 20), date(2026, 11, 6)):
        r = do_export(c, ct(d, 9, 0), d=d, status=404)
        assert r.headers["content-type"].startswith("application/json")
    sealed = dataclasses.replace(fx_timeline, trading_date=date(2026, 10, 20))
    rec = TurnRecord(1, 0, T0, T0, date(2026, 10, 20), ct(CUR, 9, 0), "question", "question", "QUESTION", "QUESTION",
                     None, "x", "FAKE", None, None, {}, None)
    with pytest.raises(SealedDateError):
        export.build_export([rec], sealed, 0, {}, T0)


# --- export is read-only --------------------------------------------------------------------------

def test_empty_or_unknown_session_has_nothing_to_export(fx_timeline, registry, no_network):
    c = app_client(fx_timeline, registry, FakeProvider())
    r = do_export(c, ct(CUR, 9, 0), session="page-never-used", status=409)
    assert r.json()["detail"] == "Nothing to export yet: this session has no Tutor turns."
    assert post(c, "question", session="page-never-used")["diagnostics"]["session"]["turns"] == 1


def test_export_calls_no_model_and_changes_nothing(real_session):
    c, shown, client = real_session
    calls = len(client.requests)
    first = unzip(do_export(c, ct(CUR, 9, 5)))
    assert len(client.requests) == calls  # no model call
    client.replies.append(reply(answer_at(9, 5), Usage(10, 10, 0, 0)))
    nxt = post(c, "question", at=ct(CUR, 9, 5), turn=5, session=SESSION)
    assert nxt["diagnostics"]["session"]["turns"] == shown[-1]["diagnostics"]["session"]["turns"] + 1
    assert [m["role"] for m in client.requests[-1]["user"]["conversation"]] == ["tutor", "student", "tutor", "tutor"]
    again = unzip(do_export(c, ct(CUR, 9, 5)))
    assert rows(again["turns.csv"])[:5] == rows(first["turns.csv"]) and len(rows(again["turns.csv"])) == 6


def test_market_context_flags_bars_revised_after_completion(fx_timeline, registry, no_network):
    c = app_client(fx_timeline, registry, FakeProvider())
    first = fx_timeline.positions[0].cutoff_utc
    last = fx_timeline.positions[-1].cutoff_utc
    post(c, "question", at=first, session=SESSION)
    rs = rows(unzip(do_export(c, last))["market_context.csv"])
    by_cutoff = {p.cutoff_utc: p for p in fx_timeline.positions}
    flagged = 0
    for r in rs:
        b = next(x for x in by_cutoff[last].bars if x.start_utc.isoformat() == r["bar_start_utc"])
        b0 = next(x for x in by_cutoff[b.end_utc].bars if x.start_utc == b.start_utc)  # as the bar completed
        assert r["revised_after_completion"] == str(b0 != b) and r["close_at_completion"] == f"{b0.close:.2f}"
        assert r["values_as_of_ct"] == export._ct(last)
        flagged += b0 != b
    assert flagged, "the synthetic late print must revise at least one bar"
