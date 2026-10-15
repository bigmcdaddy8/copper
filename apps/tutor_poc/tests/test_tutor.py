"""0AC-A2 Tutor interaction shell: fake provider, stage transitions, evidence from the authorized snapshot."""
from __future__ import annotations

import socket
from datetime import date

import pytest
import test_replay as fx_mod  # on sys.path via conftest (shared Laboratory fixture)
from dicks_laboratory.tutor_evidence import LessonStage
from fastapi.testclient import TestClient

from tutor_poc.api import create_app
from tutor_poc.dev_sessions import DevSession
from tutor_poc.snapshot import build_snapshot, position_index
from tutor_poc.tutor import FakeTutorProvider, TutorAction, next_stage, snapshot_evidence

CUR, ct = fx_mod.CUR, fx_mod.ct
STAGES = {s.value for s in LessonStage}


@pytest.fixture(scope="module")
def client(fx_timeline):
    registry = (DevSession(CUR, "synthetic.sqlite3", fx_timeline.database_sha256, True),
                DevSession(date(2026, 9, 29), "unused.sqlite3", "0" * 64, False),
                DevSession(date(2026, 10, 12), "campaign.sqlite3", "0" * 64, True))  # wrongly registered, still sealed

    def load(s):
        assert s.trading_date == CUR
        return fx_timeline

    return TestClient(create_app(registry, load, web_dist=None))


def _turn(client, action, at=None, stage="QUESTION", turn=0, text=None, d=CUR, status=200):
    body = {"action": action, "replay_cutoff_utc": (at or ct(CUR, 9, 0)).isoformat(), "stage": stage, "turn": turn}
    if text is not None:
        body["text"] = text
    r = client.post(f"/api/sessions/{d}/tutor/turn", json=body)
    assert r.status_code == status, r.text
    return r.json()


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("the fake Tutor must not open a network connection")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def test_fake_provider_needs_no_network_or_credentials(client, no_network):
    for action, text in (("question", None), ("message", "price is above VWAP"), ("hint", None), ("explain", None)):
        r = _turn(client, action, text=text)
        assert r["text"] and r["provider"] == "FAKE_DETERMINISTIC_V1"


def test_deterministic_input_gives_deterministic_output(client):
    a = _turn(client, "message", turn=3, text="Closing near the upper band")
    b = _turn(client, "message", turn=3, text="Closing near the upper band")
    assert a == b
    assert _turn(client, "message", turn=4, text="x")["text"] != a["text"]  # scripted variety by turn, still fixed


@pytest.mark.parametrize("d", ["2026-10-12", "2026-11-06", "2026-10-20", "2026-09-29", "2026-09-01", "nope"])
def test_tutor_only_operates_on_enabled_development_dates(client, d):
    assert _turn(client, "question", d=d, status=404)
    assert client.get(f"/api/sessions/{d}/tutor/evidence", params={"cutoff": ct(CUR, 9, 0).isoformat()}).status_code == 404


def test_campaign_date_cutoff_is_rejected_on_an_enabled_session(client):
    # a campaign-day cutoff is not a position of the enabled session
    _turn(client, "question", at=ct(date(2026, 10, 13), 9, 0), status=422)
    assert client.get(f"/api/sessions/{CUR}/tutor/evidence",
                      params={"cutoff": ct(date(2026, 10, 13), 9, 0).isoformat()}).status_code == 422


@pytest.mark.parametrize("hh,mm", [(9, 0), (9, 15), (12, 0)])
def test_response_preserves_the_request_cutoff_and_stamps(client, hh, mm):
    at = ct(CUR, hh, mm)
    r = _turn(client, "message", at=at, turn=7, text="hello")
    assert r["replay_cutoff_utc"] == at.isoformat() and r["trading_date"] == CUR.isoformat()
    assert r["turn"] == 7 and r["turn_id"] == "t7" and r["role"] == "tutor" and r["stage"] in STAGES


def test_off_grid_cutoff_is_rejected(client):
    _turn(client, "hint", at=ct(CUR, 9, 1), status=422)
    _turn(client, "hint", at=ct(CUR, 16, 5), status=422)


@pytest.mark.parametrize("stage,action,expected", [
    ("QUESTION", "question", "QUESTION"), ("ANSWER", "question", "QUESTION"),
    ("QUESTION", "message", "QUESTION"), ("HINT", "message", "HINT"), ("ANSWER", "message", "ANSWER"),
    ("QUESTION", "hint", "HINT"), ("HINT", "hint", "HINT"), ("ANSWER", "hint", "ANSWER"),
    ("QUESTION", "explain", "ANSWER"), ("HINT", "explain", "ANSWER"), ("ANSWER", "explain", "ANSWER"),
])
def test_stage_transitions_use_the_laboratory_vocabulary(client, stage, action, expected):
    text = "x" if action == "message" else None
    assert _turn(client, action, stage=stage, text=text)["stage"] == expected


def test_post_reveal_is_never_entered_in_a2():
    for stage in LessonStage:
        for action in TutorAction:
            nxt = next_stage(stage, action)
            assert nxt is not LessonStage.POST_REVEAL or stage is LessonStage.POST_REVEAL


def test_hint_and_explain_produce_tutor_messages(client):
    hint = _turn(client, "hint")
    assert hint["stage"] == "HINT" and "VWAP" in hint["text"] and "08:55–09:00 CT" in hint["text"]
    ex = _turn(client, "explain")
    assert ex["stage"] == "ANSWER" and "observation from interpretation" in ex["text"]


def test_explain_values_come_from_the_snapshot(client, fx_timeline):
    at = ct(CUR, 12, 0)
    snap = build_snapshot(fx_timeline, position_index(fx_timeline, at))
    close = snap["candles"][-1]["close"]
    vwap = next(x for x in snap["series"] if x["id"] == "vwap")["points"][-1]["value"]
    text = _turn(client, "explain", at=at)["text"]
    assert f"Close {close:.2f}" in text and f"VWAP {vwap:.2f}" in text


@pytest.mark.parametrize("text", ["", "   \n ", None])
def test_empty_message_is_rejected(client, text):
    _turn(client, "message", text=text, status=422)


def test_non_message_actions_take_no_text(client):
    _turn(client, "hint", text="sneaky", status=422)


@pytest.mark.parametrize("extra", [{"database": "/home/x/es_20261013.sqlite3"}, {"path": "../../secure"},
                                   {"trading_date": "2026-10-13"}, {"dataset_id": "abc"}])
def test_no_dataset_path_or_date_can_be_supplied_in_the_body(client, extra):
    body = {"action": "hint", "replay_cutoff_utc": ct(CUR, 9, 0).isoformat(), "turn": 0} | extra
    assert client.post(f"/api/sessions/{CUR}/tutor/turn", json=body).status_code == 422


def test_evidence_route_ignores_unknown_parameters(client, fx_timeline):
    at = ct(CUR, 9, 0).isoformat()
    plain = client.get(f"/api/sessions/{CUR}/tutor/evidence", params={"cutoff": at}).json()
    probed = client.get(f"/api/sessions/{CUR}/tutor/evidence",
                        params={"cutoff": at, "database": "/etc/passwd", "date": "2026-10-13"}).json()
    assert plain == probed and plain["provenance"]["database_sha256"] == fx_timeline.database_sha256


def test_unknown_stage_or_action_is_rejected(client):
    _turn(client, "hint", stage="DECISION", status=422)
    _turn(client, "recommend", status=422)


@pytest.mark.parametrize("hh,mm", [(8, 0), (9, 0), (10, 5), (12, 0), (16, 0)])
def test_evidence_is_the_latest_bar_of_the_authorized_snapshot(client, fx_timeline, hh, mm):
    at = ct(CUR, hh, mm)
    ev = client.get(f"/api/sessions/{CUR}/tutor/evidence", params={"cutoff": at.isoformat()}).json()
    snap = build_snapshot(fx_timeline, position_index(fx_timeline, at))
    c = snap["candles"][-1]
    series = {x["id"]: x["points"][-1] for x in snap["series"]}
    assert ev["replay_cutoff_utc"] == at.isoformat() == snap["replay"]["cutoff_utc"]
    assert ev["latest_bar"] == {"start_utc": c["time"], "end_utc": c["end_time"]}
    assert ev["latest_bar"]["end_utc"] <= int(at.timestamp())  # nothing after the cutoff
    assert all(p["time"] == c["time"] for p in series.values())
    values = {i["key"]: i["value"] for i in ev["items"]}
    assert values == {"open": c["open"], "high": c["high"], "low": c["low"], "close": c["close"]} | {
        k: p["value"] for k, p in series.items()}
    assert ev["provenance"]["evidence_temporality"] == "AS_OF"
    assert ev["provenance"]["snapshot_schema"] == "TUTOR_CHART_SNAPSHOT_V1"


def test_evidence_carries_no_candidate_or_setup_labels(client):
    ev = client.get(f"/api/sessions/{CUR}/tutor/evidence", params={"cutoff": ct(CUR, 12, 0).isoformat()}).json()
    assert [i["key"] for i in ev["items"]] == ["open", "high", "low", "close", "vwap", "upper_1sd", "lower_1sd",
                                               "upper_2sd", "lower_2sd"]
    assert "drysdale" not in str(ev).lower() and "candidate" not in str(ev).lower()


def test_evidence_before_any_complete_bar_is_empty(fx_timeline):
    i = next(i for i, p in enumerate(fx_timeline.positions) if not p.bars)
    ev = snapshot_evidence(fx_timeline, i)
    assert ev["latest_bar"] is None and ev["items"] == []
    text = FakeTutorProvider().reply(TutorAction.EXPLAIN, LessonStage.ANSWER, 0, None, ev)
    assert "At this replay position" not in text  # no values invented when there are none
