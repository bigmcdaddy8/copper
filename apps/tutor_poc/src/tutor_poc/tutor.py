"""Tutor interaction shell (0AC-A2): stage transitions, snapshot evidence, and a deterministic fake provider.

No model, no network, no credentials. The provider is fake; the market facts are not: every value in
`snapshot_evidence` is read from `build_snapshot` for the same replay position that feeds the chart.

Stages reuse the Laboratory vocabulary (`tutor_evidence.LessonStage`) and its monotonic order
(STAGE_ORDER / TUTOR_REVEAL_V1): a lesson never moves back to an earlier stage, and a new question
starts a new lesson at QUESTION. POST_REVEAL releases hidden future evidence in TUTOR_REVEAL_V1, which
A2 never has, so A2 never enters it.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Protocol
from zoneinfo import ZoneInfo

from dicks_laboratory.tutor_evidence import AS_OF, RECENT_BARS, STAGE_ORDER, LessonStage

from tutor_poc.snapshot import SNAPSHOT_SCHEMA, build_snapshot
from tutor_poc.timeline import ChartTimeline

EVIDENCE_SCHEMA = "TUTOR_POC_EVIDENCE_V1"
PROVIDER_ID = "FAKE_DETERMINISTIC_V1"
CT = ZoneInfo("America/Chicago")


class TutorAction(StrEnum):
    QUESTION = "question"  # opening / new question at the current replay position
    MESSAGE = "message"  # the Human's free-text reply
    HINT = "hint"
    EXPLAIN = "explain"


# The stage each action moves to at least; MESSAGE keeps the current stage.
_FLOOR = {TutorAction.HINT: LessonStage.HINT, TutorAction.EXPLAIN: LessonStage.ANSWER}


def next_stage(stage: LessonStage, action: TutorAction) -> LessonStage:
    if action is TutorAction.QUESTION:
        return LessonStage.QUESTION
    floor = _FLOOR.get(action)
    if floor is None:
        return stage
    return max(stage, floor, key=STAGE_ORDER.index)


# Evidence fields, in display order: (snapshot candle field or series id, label).
_CANDLE_FIELDS = (("open", "Open"), ("high", "High"), ("low", "Low"), ("close", "Close"))
_SERIES_FIELDS = (("vwap", "VWAP"), ("upper_1sd", "+1σ"), ("lower_1sd", "−1σ"), ("upper_2sd", "+2σ"),
                  ("lower_2sd", "−2σ"))


def _setups(setup: dict | None) -> list[dict]:
    """A4: the frozen setup analysis at the same cutoff (latest instance per family x direction), for display."""
    if setup is None:
        return []
    return [{"family": c["family"], "direction": c["direction"], "instance_id": c["candidate_id"], "state": c["state"],
             "stage": c["stage"], "conditions": [{"order": k["order"], "policy_id": k["policy_id"], "status": k["status"]}
                                                 for k in c["conditions"]]} for c in setup["latest"]]


def snapshot_evidence(tl: ChartTimeline, index: int, setup: dict | None = None) -> dict:
    """The latest completed bar of the chart snapshot at `index`, with its provenance; from A4 also the recent bars
    with their own bands and the frozen setup state at the same cutoff. Nothing later."""
    s = build_snapshot(tl, index)
    ev = {"schema": EVIDENCE_SCHEMA, "trading_date": s["trading_date"], "replay_cutoff_utc": s["replay"]["cutoff_utc"],
          "provenance": {"snapshot_schema": SNAPSHOT_SCHEMA, "evidence_temporality": AS_OF,
                         "band_policy": s["study"]["band_policy"], "vwap_anchor": s["study"]["vwap_anchor"],
                         **s["source"]},
          "latest_bar": None, "items": [], "recent_bars": [], "setups": _setups(setup),
          "setup_analysis": None if setup is None else {"state": setup["state"], "quality_status": setup["status"]}}
    if not s["candles"]:
        return ev
    series = {x["id"]: x["points"] for x in s["series"]}
    ev["recent_bars"] = [{"start_utc": c["time"], "end_utc": c["end_time"], "close": c["close"],
                          **{k: series[k][i]["value"] for k, _ in _SERIES_FIELDS}}
                         for i, c in list(enumerate(s["candles"]))[-RECENT_BARS:]]
    c = s["candles"][-1]
    last = {x["id"]: x["points"][-1]["value"] for x in s["series"]}
    ev["latest_bar"] = {"start_utc": c["time"], "end_utc": c["end_time"]}
    ev["items"] = ([{"key": k, "label": label, "value": c[k]} for k, label in _CANDLE_FIELDS]
                   + [{"key": k, "label": label, "value": last[k]} for k, label in _SERIES_FIELDS])
    return ev


class TutorProvider(Protocol):
    """A2 scripted-text interface. A3 wraps it in providers.FakeProvider (the TutorModelProvider seam)."""

    def reply(self, action: TutorAction, stage: LessonStage, turn: int, text: str | None, evidence: dict) -> str: ...


def format_ct(utc_seconds: int) -> str:
    return datetime.fromtimestamp(utc_seconds, CT).strftime("%H:%M")


def _bar_phrase(evidence: dict) -> str:
    b = evidence["latest_bar"]
    return f"the {format_ct(b['start_utc'])}–{format_ct(b['end_utc'])} CT candle" if b else "the latest completed candle"


def _values_line(evidence: dict) -> str:
    v = {i["key"]: i["value"] for i in evidence["items"]}
    return (f"Close {v['close']:.2f} · VWAP {v['vwap']:.2f} · +1σ {v['upper_1sd']:.2f} / −1σ {v['lower_1sd']:.2f} · "
            f"+2σ {v['upper_2sd']:.2f} / −2σ {v['lower_2sd']:.2f}")


_ACKS = ("Okay — keep that observation in mind.", "Noted.", "Got it.")
_FOLLOW_UPS = (
    "Now compare the latest close with VWAP and the nearest deviation boundary. What on the chart supports your reading?",
    "What would you look at next to check that interpretation?",
    "Is anything on the chart arguing against that? What would change your mind?",
)
_AFTER_ANSWER = (
    "Step the replay forward when you're ready and watch whether that picture holds.",
    "What would you expect to see over the next few candles if your reading is right?",
)


class FakeTutorProvider:
    """Scripted wording and progression. Same inputs, same text. It does not evaluate the Human's answer."""

    def reply(self, action: TutorAction, stage: LessonStage, turn: int, text: str | None, evidence: dict) -> str:
        if action is TutorAction.QUESTION:
            return (f"Look at {_bar_phrase(evidence)}, the latest completed one.\n\n"
                    "Where is price relative to VWAP and the Level 1 / Level 2 deviation regions? What stands out to you?")
        if action is TutorAction.HINT:
            return (f"Start with {_bar_phrase(evidence)}. Compare its close with VWAP, then check whether it sits "
                    "inside Level 1 (between −1σ and +1σ), in Level 2 (between ±1σ and ±2σ), or beyond ±2σ.")
        if action is TutorAction.EXPLAIN:
            values = f"\n\nAt this replay position: {_values_line(evidence)}." if evidence["items"] else ""
            return ("For this exercise, separate observation from interpretation. First pin down the facts: the latest "
                    f"close, VWAP, and which deviation region holds the close.{values}\n\n"
                    "Place the close among those levels yourself. In a later phase the grounded Tutor will use these "
                    "facts to discuss setup conditions.")
        follow = _AFTER_ANSWER if stage is LessonStage.ANSWER else _FOLLOW_UPS
        return f"{_ACKS[turn % len(_ACKS)]} {follow[turn % len(follow)]}"
