"""Tutor session export (0AC-A3E): the current in-memory Tutor session as one ZIP evaluation artifact.

    TutorSession.turn_log (TurnRecord per answered turn, written when the turn was answered)
        + the chart timeline (Laboratory bars, for market_context.csv)
        -> session.md          chronological transcript for a Human or a reviewing LLM
           session.json        the whole session, typed and versioned (evidence by reference)
           turns.csv           one row per Tutor turn: status, usage, cost, latency, grounding counts, text
           evidence.jsonl      per turn: the exact evidence object the provider was given, and its grounding
           market_context.csv  completed 5-minute bars of the visited replay window (server values)
           manifest.json       files, sha256 / bytes of each, versions, flags

Nothing here calls a model, changes a session, or recomputes an earlier turn: every per-turn value is the one
recorded at that turn. Every member is scanned for secret values and secret-shaped strings before the ZIP is
written; matches are redacted and counted in the manifest.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import zipfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from dicks_laboratory.tutor_evidence import RECENT_BARS, canonical_json

from tutor_poc.conversation import TurnRecord
from tutor_poc.dev_sessions import INSTRUMENT, SealedDateError, is_sealed
from tutor_poc.evidence import _level, _price, close_region, close_vs_vwap
from tutor_poc.providers import TurnContext, TurnResult, _history, _usd, usage_dict
from tutor_poc.timeline import STEP, ChartTimeline

EXPORT_SCHEMA = "TUTOR_SESSION_EXPORT_V2"  # A4 (additive): mode, guided lesson, setup state per turn
EVIDENCE_RECORD_SCHEMA = "TUTOR_SESSION_EVIDENCE_RECORD_V2"
MARKET_CONTEXT_SCHEMA = "TUTOR_SESSION_MARKET_CONTEXT_V1"
REVIEW_PROMPT = "docs/dicks_laboratory/TUTOR_SESSION_REVIEW_PROMPT.md"
CT = ZoneInfo("America/Chicago")
_ACCEPTED = ("FAKE", "GROUNDED")
_PROVIDER_ERRORS = ("PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE")

FILES = (
    ("session.md", "Chronological transcript for a Human or a reviewing LLM: messages, grounding, diagnostics"),
    ("session.json", "The whole session, machine-readable: metadata, totals, replay positions, messages, turns"),
    ("turns.csv", "One row per Tutor turn: status, usage, cost, latency, grounding counts, exact texts"),
    ("evidence.jsonl", "One record per Tutor turn: the exact evidence object the provider was given, and grounding"),
    ("market_context.csv", "Completed 5-minute bars of the visited replay window (Laboratory values, no ticks)"),
    ("manifest.json", "This export: versions, flags, and sha256 / bytes of every other member"),
)

TURN_COLUMNS = (
    "turn_id", "client_turn", "requested_at_utc", "answered_at_utc", "trading_date", "replay_cutoff_ct",
    "replay_cutoff_utc", "role", "action", "message_kind", "lesson_stage_before", "lesson_stage", "mode", "lesson_id",
    "lesson_phase", "lesson_revealed", "studied_setup", "status",
    "final_accepted", "failure_category", "error", "attempts", "repair_attempts", "provider", "model", "served_model",
    "effort", "prompt_version", "prompt_sha", "pricing_version", "input_tokens", "output_tokens", "cached_tokens",
    "cache_write_tokens", "total_input_tokens", "evidence_bytes", "request_bytes", "evidence_latency_ms",
    "model_latency_ms", "validation_latency_ms", "total_latency_ms", "fallback_used", "turn_cost_usd",
    "session_cost_usd_after_turn", "observed_facts", "derived_facts", "interpretations", "unsupported_claims",
    "checked_refs", "setup_analysis_state", "valid_setups_at_cutoff", "referenced_setups", "missing_conditions",
    "human_text", "text",
)

# Values are the Laboratory's bars as known at `values_as_of_ct` (the latest visited replay cutoff), the same
# values the chart draws there. As-of semantics: a late print can revise a bar after it completed, so
# `revised_after_completion` flags bars whose values changed since the cutoff at which they completed, with the
# close / VWAP known then (what a Tutor turn at that cutoff saw; evidence.jsonl has every turn's exact values).
# Band columns are each bar's levels at its close; from A4 the Tutor evidence gives every window bar its own bands
# (A3 gave them for the latest bar only), and `tutor_evidence` says how each bar appeared to the Tutor (latest /
# recent / not at all).
MARKET_COLUMNS = (
    "bar_start_ct", "bar_end_ct", "bar_start_utc", "bar_end_utc", "open", "high", "low", "close", "volume", "vwap",
    "plus_1_sigma", "minus_1_sigma", "plus_2_sigma", "minus_2_sigma", "close_vs_vwap", "close_minus_vwap",
    "band_region", "values_as_of_ct", "revised_after_completion", "close_at_completion", "vwap_at_completion",
    "tutor_evidence",
)


class NothingToExport(ValueError):
    """The session has no Tutor turns for this trading date."""


# --- turn records (built when a turn is answered) ---------------------------------------------------

def attempt_records(r: TurnResult) -> tuple[dict, ...]:
    """Per model call metadata for export. Never the response text or validator details (they can echo a
    rejected answer); provider failures keep their short transport description."""
    out = []
    for a in r.attempts:
        codes = []
        for issue in a.issues:  # "<code> at <where>: <detail>"
            code, _, rest = issue.partition(" at ")
            codes.append({"code": code, "where": rest.partition(": ")[0]})
        out.append({"repair_attempt": a.repair_attempt, "status": a.status.value, "issues": codes,
                    "provider_error": a.detail if a.status.value in _PROVIDER_ERRORS else None,
                    "request_bytes": a.request_bytes,
                    "latency_ms": round(a.reply.latency_s * 1000, 1) if a.reply else None,
                    "served_model": a.reply.served_model if a.reply else None,
                    "stop_reason": a.reply.stop_reason if a.reply else None,
                    "request_id": a.reply.request_id if a.reply else None,
                    "fallback_used": a.reply.fallback_used if a.reply else False,
                    "usage": usage_dict(a.reply.usage) if a.reply else None, "cost_usd": _usd(a.cost_usd)})
    return tuple(out)


def context_records(ctx: TurnContext) -> tuple[dict, ...]:
    """The conversation messages available to the provider at this turn (cutoff-filtered), without their text."""
    return tuple({"role": m["role"], "kind": m["kind"], "replay_cutoff_ct": m["replay_cutoff_ct"],
                  "chars": len(m["text"])} for m in _history(ctx))


# --- helpers ------------------------------------------------------------------------------------------

def _ct(t: datetime) -> str:
    return t.astimezone(CT).strftime("%H:%M")


def _iso(t: datetime | None) -> str | None:
    return None if t is None else t.isoformat()


def turn_id(r: TurnRecord) -> str:
    return f"turn-{r.seq:04d}"


def _accepted(r: TurnRecord) -> bool:
    return r.status in _ACCEPTED and r.tutor_text is not None


def _counts(g: dict | None) -> dict:
    cats = [c["category"] for c in (g or {}).get("claims", [])]
    return {"observed_facts": cats.count("OBSERVED_FACT"), "derived_facts": cats.count("DERIVED_FACT"),
            "interpretations": cats.count("AI_INTERPRETATION"),
            "unsupported_claims": len((g or {}).get("unsupported", [])), "checked_refs": (g or {}).get("checked_refs")}


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _usd_text(v: str | None) -> str:
    return "unpriced" if v is None else f"${Decimal(v):.4f}"


def _ms(v) -> str:
    return "n/a" if v is None else f"{v / 1000:.1f} s"


def _tok(v) -> str:
    return "n/a" if v is None else f"{v:,}"


def _evidence_sha(ev: dict | None) -> str | None:
    return None if ev is None else hashlib.sha256(canonical_json(ev).encode("utf-8")).hexdigest()


def _bars_seen(ev: dict | None) -> dict[str, str]:
    """{bar start HH:MM CT: 'latest' | 'recent'} for the bars an evidence object contains."""
    if not ev:
        return {}
    if ev.get("schema") == "TUTOR_POC_MODEL_EVIDENCE_V2":
        rows = ev["LESSON_TIME"]["bars"]["rows"]
        col = ev["LESSON_TIME"]["bars"]["columns"].index("start_ct")
        return {r[col]: "latest" if r[0] == "/latest_bar" else "recent" for r in rows}
    if "items" in ev and ev.get("schema") == "TUTOR_POC_MODEL_EVIDENCE_V1":
        seen = {}
        for it in ev["items"]:
            if it["pointer"] == "/latest_bar/start_ct":
                seen[it["value"]] = "latest"
            elif it["pointer"].startswith("/recent_bars/") and it["pointer"].endswith("/start_ct"):
                seen.setdefault(it["value"], "recent")
        return seen
    if ev.get("latest_bar"):  # A2 snapshot evidence (fake provider): the latest bar (and, from A4, recent bars)
        seen = {datetime.fromtimestamp(b["start_utc"], CT).strftime("%H:%M"): "recent" for b in ev.get("recent_bars", ())}
        return seen | {datetime.fromtimestamp(ev["latest_bar"]["start_utc"], CT).strftime("%H:%M"): "latest"}
    return {}


def setup_summary(ev: dict | None) -> list[dict]:
    """Per family x direction at the turn's cutoff, from the turn's own evidence: state, satisfied / missing."""
    if not ev:
        return []
    if ev.get("schema") == "TUTOR_POC_MODEL_EVIDENCE_V2":
        d = ev["DRYSDALE"]
        cols, ccols = d["setups"]["columns"], d["conditions"]["columns"]
        conds: dict[str, list[dict]] = {}
        for row in d["conditions"]["rows"]:
            c = dict(zip(ccols, row, strict=True))
            conds.setdefault(c["pointer"].rsplit("/conditions/", 1)[0], []).append(c)
        rows = []
        for row in d["setups"]["rows"]:
            r = dict(zip(cols, row, strict=True))
            r["conditions"] = conds.get(r["pointer"], [])
            rows.append(r)
    else:  # A2 snapshot evidence (fake provider)
        rows = [r | {"instance_exists": True} for r in ev.get("setups", ())]
    out = []
    for r in rows:
        if not r.get("instance_exists"):
            continue
        out.append({"family": r["family"], "direction": r["direction"], "instance_id": r["instance_id"],
                    "state": r["state"], "stage": r["stage"],
                    "satisfied": [c["policy_id"] for c in r["conditions"] if c["status"] == "SATISFIED"],
                    "missing": [f"{c['policy_id']}:{c['status']}" for c in r["conditions"] if c["status"] != "SATISFIED"]})
    return out


def _valid(ev: dict | None) -> list[str]:
    return [f"{x['family']} {x['direction']}" for x in setup_summary(ev) if x["state"] in ("CANDIDATE",
                                                                                          "QUALITY_QUALIFIED")]


def _analysis_state(ev: dict | None) -> str | None:
    if not ev:
        return None
    if ev.get("schema") == "TUTOR_POC_MODEL_EVIDENCE_V2":
        return next((i[1] for i in ev["DRYSDALE"]["items"] if i[0] == "/analysis/state"), None)
    return (ev.get("setup_analysis") or {}).get("state")


def _lesson_cols(r: TurnRecord) -> dict:
    g = r.lesson or {}
    s = g.get("setup")
    return {"mode": r.mode, "lesson_id": g.get("lesson_id"), "lesson_phase": g.get("phase"),
            "lesson_revealed": g.get("revealed") if g else None,
            "studied_setup": f"{s['family']} {s['direction']} {s['instance_id']}" if s else None}


def _csv(columns: Iterable[str], rows: Iterable[Mapping]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(columns), lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writeheader()
    for row in rows:
        w.writerow({k: "" if row.get(k) is None else row[k] for k in columns})
    return buf.getvalue()


def _json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False, default=str) + "\n"


# --- secrets --------------------------------------------------------------------------------------

_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH", re.I)
_SECRET_SHAPES = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\b(authorization|x-api-key|api[_-]?key)\s*[:=]\s*(bearer\s+)?\S+"),  # A4: the token too
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
)
REDACTED = "[REDACTED]"


def secret_values(env: Mapping[str, str]) -> tuple[str, ...]:
    """Values of secret-named environment variables (12+ characters), longest first."""
    vals = {v for k, v in env.items() if _SECRET_NAME.search(k) and v and len(v) >= 12}
    return tuple(sorted(vals, key=len, reverse=True))


def sanitize(text: str, secrets: tuple[str, ...], home: str | None) -> tuple[str, int]:
    """(text with secret values, secret-shaped strings and the home directory removed, number of redactions)."""
    n = 0
    for v in secrets:
        n += text.count(v)
        text = text.replace(v, REDACTED)
    for rx in _SECRET_SHAPES:
        text, k = rx.subn(REDACTED, text)
        n += k
    if home and len(home) > 1 and home in text:
        n += text.count(home)
        text = text.replace(home, "~")
    return text, n


def find_secrets(text: str, secrets: tuple[str, ...]) -> list[str]:
    """What still looks secret in `text` (names of the checks, never the values)."""
    found = [f"env value #{i}" for i, v in enumerate(secrets) if v in text]
    found += [rx.pattern for rx in _SECRET_SHAPES if rx.search(text)]
    return found


# --- the export -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class SessionExport:
    filename: str
    data: bytes  # the ZIP
    members: dict[str, str]  # name -> text (after sanitization), for inspection and tests
    manifest: dict


def filename_for(trading_date: str, first_cutoff: datetime, export_cutoff: datetime) -> str:
    """tutor_session_<date>_<first Tutor turn's replay HHMM CT>-<export replay HHMM CT>.zip"""
    hhmm = lambda t: t.astimezone(CT).strftime("%H%M")  # noqa: E731
    return f"tutor_session_{trading_date}_{hhmm(first_cutoff)}-{hhmm(export_cutoff)}.zip"


def build_export(records: Iterable[TurnRecord], tl: ChartTimeline, export_index: int, config: dict,
                 created_at: datetime, dropped_turns: int = 0, env: Mapping[str, str] | None = None,
                 home: str | None = None) -> SessionExport:
    if is_sealed(tl.trading_date):
        raise SealedDateError(f"{tl.trading_date} is inside the sealed prospective campaign")
    recs = sorted((r for r in records if r.trading_date == tl.trading_date), key=lambda r: r.seq)
    if not recs:
        raise NothingToExport("this session has no Tutor turns to export")
    env = os.environ if env is None else env
    home = str(Path.home()) if home is None else home
    export_cutoff = tl.positions[export_index].cutoff_utc
    first_cutoff = recs[0].replay_cutoff_utc
    scope_cutoff = max([export_cutoff] + [r.replay_cutoff_utc for r in recs])
    d = tl.trading_date.isoformat()

    turns = [_turn_json(r) for r in recs]
    messages = _messages(recs)
    positions = _positions(recs, export_cutoff)
    totals = recs[-1].diagnostics.get("session")
    accepted = sum(1 for r in recs if _accepted(r))
    meta = {
        "instrument": INSTRUMENT, "trading_date": d,
        "wall_clock": {"started_at_utc": _iso(recs[0].requested_at), "last_turn_at_utc": _iso(recs[-1].answered_at),
                       "exported_at_utc": _iso(created_at)},
        "replay": {"first_turn_cutoff_ct": _ct(first_cutoff), "first_turn_cutoff_utc": _iso(first_cutoff),
                   "latest_turn_cutoff_ct": _ct(max(r.replay_cutoff_utc for r in recs)),
                   "export_cutoff_ct": _ct(export_cutoff), "export_cutoff_utc": _iso(export_cutoff),
                   "market_context_through_ct": _ct(scope_cutoff)},
        "provider": config.get("provider"), "provider_id": config.get("provider_id"), "model": config.get("model"),
        "effort": config.get("effort"), "prompt_version": config.get("prompt_version"),
        "pricing_version": config.get("pricing_version"),
        "turn_count": len(recs), "accepted_turns": accepted, "failed_turns": len(recs) - accepted,
        "dropped_turns": dropped_turns, "totals": totals,
        "persistence": "in memory only: a page reload or a server restart starts a new session",
        "modes": sorted({r.mode for r in recs}),
        "lessons": sorted({r.lesson["lesson_id"] for r in recs if r.lesson}),
    }
    evidence_lines = [_evidence_record(r) for r in recs]
    market_rows = _market_rows(tl, recs, scope_cutoff)

    members = {
        "session.md": _markdown(meta, recs),
        "session.json": _json({"schema_version": EXPORT_SCHEMA, "session": meta, "replay_positions": positions,
                               "messages": messages, "turns": turns}),
        "turns.csv": _csv(TURN_COLUMNS, (_turn_row(r) for r in recs)),
        "evidence.jsonl": "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in evidence_lines),
        "market_context.csv": _csv(MARKET_COLUMNS, market_rows),
    }
    secrets = secret_values(env)
    redactions = 0
    for name in list(members):
        members[name], n = sanitize(members[name], secrets, home)
        redactions += n
    manifest = {
        "export_schema_version": EXPORT_SCHEMA, "evidence_record_schema": EVIDENCE_RECORD_SCHEMA,
        "market_context_schema": MARKET_CONTEXT_SCHEMA, "created_at_utc": _iso(created_at), "instrument": INSTRUMENT,
        "trading_date": d, "session_start_cutoff_ct": _ct(first_cutoff), "session_end_cutoff_ct": _ct(export_cutoff),
        "filename_policy": "first Tutor turn's replay cutoff - replay cutoff at export (Chicago time)",
        "provider": meta["provider"], "model": meta["model"], "prompt_version": meta["prompt_version"],
        "pricing_version": meta["pricing_version"], "turns": len(recs), "evidence_records": len(evidence_lines),
        "market_bars": len(market_rows), "dropped_turns": dropped_turns, "modes": meta["modes"],
        "lessons": meta["lessons"],
        "campaign_data_included": False, "contains_secrets": False, "redactions": redactions,
        "review_prompt": REVIEW_PROMPT,
        "files": [{"name": n, "purpose": p} | ({"sha256": hashlib.sha256(members[n].encode()).hexdigest(),
                                                "bytes": len(members[n].encode())} if n in members else {})
                  for n, p in FILES],
    }
    members["manifest.json"] = _json(manifest)
    leftovers = {name: find_secrets(text, secrets) for name, text in members.items()}
    if any(leftovers.values()):
        raise RuntimeError(f"export refused: secret-like content remains in {sorted(k for k, v in leftovers.items() if v)}")
    return SessionExport(filename_for(d, first_cutoff, export_cutoff), _zip(members, created_at), members, manifest)


def _zip(members: dict[str, str], created_at: datetime) -> bytes:
    buf = io.BytesIO()
    stamp = created_at.astimezone(CT).timetuple()[:6]
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, _ in FILES:
            info = zipfile.ZipInfo(name, stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            z.writestr(info, members[name].encode("utf-8"))
    return buf.getvalue()


# --- members --------------------------------------------------------------------------------------

def _messages(recs: list[TurnRecord]) -> list[dict]:
    """The conversation as the Human saw it: their messages and every accepted Tutor message, in order."""
    out = []
    for r in recs:
        base = {"turn_id": turn_id(r), "trading_date": r.trading_date.isoformat(),
                "replay_cutoff_ct": _ct(r.replay_cutoff_utc), "replay_cutoff_utc": _iso(r.replay_cutoff_utc)}
        if r.human_text is not None:
            out.append({"message_id": f"{turn_id(r)}-human", "role": "human", "kind": "human", "text": r.human_text,
                        "lesson_stage": r.stage_before, "at_utc": _iso(r.requested_at)} | base)
        if _accepted(r):
            out.append({"message_id": f"{turn_id(r)}-tutor", "role": "tutor", "kind": r.kind, "text": r.tutor_text,
                        "lesson_stage": r.stage_after, "status": r.status, "at_utc": _iso(r.answered_at)} | base)
    return out


def _positions(recs: list[TurnRecord], export_cutoff: datetime) -> list[dict]:
    """Replay positions in first-visit order: every Tutor turn's cutoff, then the chart's position at export."""
    order: dict[datetime, list[str]] = {}
    for r in recs:
        order.setdefault(r.replay_cutoff_utc, []).append(turn_id(r))
    order.setdefault(export_cutoff, [])
    return [{"replay_cutoff_ct": _ct(t), "replay_cutoff_utc": _iso(t), "turn_ids": ids,
             "export_position": t == export_cutoff} for t, ids in order.items()]


def _turn_json(r: TurnRecord) -> dict:
    d = r.diagnostics
    return {"turn_id": turn_id(r), "client_turn": r.client_turn, "requested_at_utc": _iso(r.requested_at),
            "answered_at_utc": _iso(r.answered_at), "trading_date": r.trading_date.isoformat(),
            "replay_cutoff_ct": _ct(r.replay_cutoff_utc), "replay_cutoff_utc": _iso(r.replay_cutoff_utc),
            "action": r.action, "message_kind": r.kind, "lesson_stage_before": r.stage_before,
            "lesson_stage": r.stage_after, "mode": r.mode, "lesson": r.lesson, "status": r.status,
            "final_accepted": _accepted(r),
            "repair_attempted": d.get("repair_attempts", 0) > 0, "repair_attempts": d.get("repair_attempts", 0),
            "failure_category": None if _accepted(r) else r.status, "error_shown": r.error,
            "message_ids": ([f"{turn_id(r)}-human"] if r.human_text is not None else [])
            + ([f"{turn_id(r)}-tutor"] if _accepted(r) else []),
            "grounding_counts": _counts(r.grounding) if r.grounding else None, "grounding": r.grounding,
            "diagnostics": d, "attempts": list(r.attempts), "setup_summary": setup_summary(r.evidence),
            "evidence_ref": {"file": "evidence.jsonl", "turn_id": turn_id(r), "evidence_sha256": _evidence_sha(r.evidence)}}


def _turn_row(r: TurnRecord) -> dict:
    d = r.diagnostics
    u = d.get("usage") or {}
    lat = d.get("latency_ms") or {}
    req = d.get("request_bytes") or []
    g = _counts(r.grounding) if r.grounding else {}
    return {"turn_id": turn_id(r), "client_turn": r.client_turn, "requested_at_utc": _iso(r.requested_at),
            "answered_at_utc": _iso(r.answered_at), "trading_date": r.trading_date.isoformat(),
            "replay_cutoff_ct": _ct(r.replay_cutoff_utc), "replay_cutoff_utc": _iso(r.replay_cutoff_utc),
            "role": "tutor", "action": r.action, "message_kind": r.kind, "lesson_stage_before": r.stage_before,
            "lesson_stage": r.stage_after, **_lesson_cols(r), "status": r.status, "final_accepted": _accepted(r),
            "failure_category": None if _accepted(r) else r.status, "error": r.error,
            "attempts": d.get("attempts"), "repair_attempts": d.get("repair_attempts"), "provider": d.get("provider"),
            "model": d.get("model"), "served_model": d.get("served_model"), "effort": d.get("effort"),
            "prompt_version": d.get("prompt_version"), "prompt_sha": d.get("prompt_sha256"),
            "pricing_version": d.get("pricing_version"), "input_tokens": u.get("input_tokens"),
            "output_tokens": u.get("output_tokens"), "cached_tokens": u.get("cached_input_tokens"),
            "cache_write_tokens": u.get("cache_write_input_tokens"), "total_input_tokens": u.get("total_input_tokens"),
            "evidence_bytes": d.get("evidence_bytes"), "request_bytes": sum(req) if req else None,
            "evidence_latency_ms": lat.get("evidence"), "model_latency_ms": lat.get("model"),
            "validation_latency_ms": lat.get("validation"), "total_latency_ms": lat.get("total"),
            "fallback_used": d.get("fallback_used"), "turn_cost_usd": d.get("turn_cost_usd"),
            "session_cost_usd_after_turn": (d.get("session") or {}).get("cost_usd"), **g,
            "setup_analysis_state": _analysis_state(r.evidence), "valid_setups_at_cutoff": "; ".join(_valid(r.evidence)),
            "referenced_setups": "; ".join((r.grounding or {}).get("referenced_setups", [])),
            "missing_conditions": "; ".join((r.grounding or {}).get("missing_conditions", [])),
            "human_text": r.human_text, "text": r.tutor_text}


def _evidence_record(r: TurnRecord) -> dict:
    return {"schema": EVIDENCE_RECORD_SCHEMA, "turn_id": turn_id(r), "client_turn": r.client_turn,
            "trading_date": r.trading_date.isoformat(), "replay_cutoff_ct": _ct(r.replay_cutoff_utc),
            "replay_cutoff_utc": _iso(r.replay_cutoff_utc), "action": r.action, "mode": r.mode, "lesson": r.lesson,
            "provider": r.diagnostics.get("provider"),
            "evidence_schema_version": (r.evidence or {}).get("schema"), "evidence_sha256": _evidence_sha(r.evidence),
            "evidence": r.evidence, "setup_summary": setup_summary(r.evidence),
            "conversation_context": {"sent_to_model": r.status != "FAKE",
                                     "messages": list(r.context)},
            "grounding_result": {"status": r.status, "final_accepted": _accepted(r),
                                 "repair_attempts": r.diagnostics.get("repair_attempts", 0),
                                 "counts": _counts(r.grounding) if r.grounding else None, "accepted": r.grounding,
                                 "attempts": [{"repair_attempt": a["repair_attempt"], "status": a["status"],
                                               "issues": a["issues"]} for a in r.attempts]}}


def _market_rows(tl: ChartTimeline, recs: list[TurnRecord], scope_cutoff: datetime) -> list[dict]:
    """Completed bars from the evidence window before the first turn through the latest visited cutoff, read
    from the chart position at that cutoff (every bar ends at or before it)."""
    seen: dict[str, str] = {}
    for r in recs:
        for start, role in _bars_seen(r.evidence).items():
            if seen.get(start) != "latest":
                seen[start] = role
    by_cutoff = {q.cutoff_utc: q for q in tl.positions}
    p = by_cutoff[scope_cutoff]
    first = min(r.replay_cutoff_utc for r in recs) - STEP * RECENT_BARS
    rows = []
    for b in p.bars:
        if b.end_utc > p.cutoff_utc or b.start_utc < first:
            continue
        start = _ct(b.start_utc)
        done = by_cutoff.get(b.end_utc)  # the position at which this bar first appeared complete
        b0 = next((x for x in done.bars if x.start_utc == b.start_utc), None) if done else None
        rows.append({"bar_start_ct": start, "bar_end_ct": _ct(b.end_utc), "bar_start_utc": _iso(b.start_utc),
                     "bar_end_utc": _iso(b.end_utc), "open": _price(b.open), "high": _price(b.high),
                     "low": _price(b.low), "close": _price(b.close), "volume": f"{b.volume.normalize():f}",
                     "vwap": _level(b.vwap), "plus_1_sigma": _level(b.upper_1sd), "minus_1_sigma": _level(b.lower_1sd),
                     "plus_2_sigma": _level(b.upper_2sd), "minus_2_sigma": _level(b.lower_2sd),
                     "close_vs_vwap": close_vs_vwap(b), "close_minus_vwap": _level(b.close - b.vwap),
                     "band_region": close_region(b), "values_as_of_ct": _ct(p.cutoff_utc),
                     "revised_after_completion": None if b0 is None else b0 != b,
                     "close_at_completion": None if b0 is None else _price(b0.close),
                     "vwap_at_completion": None if b0 is None else _level(b0.vwap),
                     "tutor_evidence": seen.get(start, "")})
    return rows


_HEAD = {"question": "Question", "reply": "Reply", "hint": "Hint", "explain": "Explain"}


def _markdown(meta: dict, recs: list[TurnRecord]) -> str:
    t = meta["totals"] or {}
    w, rp = meta["wall_clock"], meta["replay"]
    lines = [
        "# Dick's Laboratory Tutor Session", "",
        f"Instrument: {meta['instrument']}  ",
        f"Trading date: {meta['trading_date']}  ",
        f"Session start (wall clock, UTC): {w['started_at_utc']}  ",
        f"Last turn (wall clock, UTC): {w['last_turn_at_utc']}  ",
        f"Exported (wall clock, UTC): {w['exported_at_utc']}  ",
        f"Replay window (historical, CT): first Tutor turn {rp['first_turn_cutoff_ct']} · latest Tutor turn "
        f"{rp['latest_turn_cutoff_ct']} · chart at export {rp['export_cutoff_ct']}  ",
        f"Provider: {meta['provider']}  ",
        f"Model: {meta['model'] or 'none (scripted fake Tutor)'}  ",
        f"Effort: {meta['effort'] or 'n/a'}  ",
        f"Prompt version: {meta['prompt_version'] or 'n/a'}  ",
        f"Pricing version: {meta['pricing_version'] or 'n/a'}  ",
        f"Modes: {', '.join(meta['modes'])}" + (f" · guided lessons: {', '.join(meta['lessons'])}" if meta["lessons"]
                                                else "") + "  ",
        f"Total turns: {meta['turn_count']} ({meta['accepted_turns']} accepted, {meta['failed_turns']} failed)  ",
        f"Model calls: {t.get('model_calls', 0)}  ",
        f"Total cost: {_usd_text(t.get('cost_usd'))}"
        + (f" ({t['unpriced_calls']} unpriced calls)" if t.get("unpriced_calls") else "") + "  ",
        f"Total input tokens: {_tok(t.get('total_input_tokens'))} (uncached {_tok(t.get('input_tokens'))}, cached "
        f"{_tok(t.get('cached_input_tokens'))}, cache write {_tok(t.get('cache_write_input_tokens'))})  ",
        f"Total output tokens: {_tok(t.get('output_tokens'))}", "",
        "Wall-clock times are when a turn happened. \"Replay\" times are the historical chart position (Chicago "
        "time) the Tutor was given; it only had evidence known at that cutoff. Texts are exactly as shown in the app.",
    ]
    if meta["dropped_turns"]:
        lines += ["", f"Note: the {meta['dropped_turns']} oldest turns were no longer in memory and are not included."]
    at = None
    for r in recs:
        if r.replay_cutoff_utc != at:
            at = r.replay_cutoff_utc
            lines += ["", "---", "", f"## Replay {_ct(at)} CT"]
        if r.human_text is not None:
            lines += ["", "### Human", "", r.human_text]
        head = _HEAD.get(r.kind, r.kind)
        if _accepted(r):
            lines += ["", f"### Tutor — {head}", "", r.tutor_text]
        else:
            lines += ["", f"### Tutor — {head} (not shown: {r.status})", "", f"Error shown to the Human: {r.error}"]
        lines += ["", f"Turn {turn_id(r)} · stage {r.stage_before} → {r.stage_after} · status {r.status} · "
                      f"wall clock {_iso(r.answered_at)}"]
        if r.lesson:
            g = r.lesson
            lines.append(f"Guided lesson {g['lesson_id']} · {g['title']} · phase {g['phase']}"
                         + (" · revealed" if g.get("revealed") else ""))
        valid = _valid(r.evidence)
        lines.append(f"Setup analysis at this cutoff: {_analysis_state(r.evidence) or 'n/a'} · valid setups: "
                     f"{', '.join(valid) if valid else 'none'}")
        if r.grounding:
            c = _counts(r.grounding)
            lines += ["", "Grounding:", f"- {_plural(c['observed_facts'], 'observed fact')}",
                      f"- {_plural(c['derived_facts'], 'derived fact')}",
                      f"- {_plural(c['interpretations'], 'interpretation')}"]
            if c["unsupported_claims"]:
                lines.append(f"- {_plural(c['unsupported_claims'], 'claim')} marked not in evidence")
            if r.grounding.get("referenced_setups"):
                lines.append(f"- setups cited: {', '.join(r.grounding['referenced_setups'])}")
            if r.grounding.get("missing_conditions"):
                lines.append(f"- missing conditions cited: {', '.join(r.grounding['missing_conditions'])}")
        lines += ["", "Diagnostics:", *_diag_lines(r)]
    return "\n".join(lines) + "\n"


def _diag_lines(r: TurnRecord) -> list[str]:
    d = r.diagnostics
    if r.status == "FAKE":
        return ["- provider: fake (scripted, no model call) · cost $0"]
    u = d.get("usage") or {}
    lat = d.get("latency_ms") or {}
    req = d.get("request_bytes") or []
    return [f"- latency: model {_ms(lat.get('model'))}, total {_ms(lat.get('total'))}",
            f"- input tokens: {_tok(u.get('total_input_tokens'))} (uncached {_tok(u.get('input_tokens'))}, cached "
            f"{_tok(u.get('cached_input_tokens'))}, cache write {_tok(u.get('cache_write_input_tokens'))})",
            f"- output tokens: {_tok(u.get('output_tokens'))}",
            f"- model calls: {d.get('attempts')} · repairs: {d.get('repair_attempts')}",
            f"- evidence bytes: {_tok(d.get('evidence_bytes'))} · request bytes: {_tok(sum(req)) if req else 'n/a'}",
            f"- served model: {d.get('served_model') or 'n/a'}" + (" (fallback)" if d.get("fallback_used") else ""),
            f"- turn cost: {_usd_text(d.get('turn_cost_usd'))} · session cost after turn: "
            f"{_usd_text((d.get('session') or {}).get('cost_usd'))}"]

