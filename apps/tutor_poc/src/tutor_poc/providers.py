"""Tutor providers (0AC-A3): one seam, a deterministic fake and one grounded real-model provider.

    TutorModelProvider.respond(TurnContext) -> TurnResult
        FakeProvider       the accepted A2 scripted Tutor (no model, no network, no credentials, cost 0)
        GroundedProvider   evidence -> model -> grounding validation -> at most one repair -> answer or typed failure
            ModelClient    transport only (AnthropicModelClient: the Anthropic Messages API through the official SDK)

The grounded provider owns the Laboratory semantics (what evidence is authorized, how answers are
validated, when to repair); a ModelClient only turns (system, user, schema) into text plus usage. A later
phase changes the evidence or the lesson behind the same seam without touching the transport.
"""
from __future__ import annotations

import copy
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from dicks_laboratory.tutor_ai import (
    ANSWER_JSON_SCHEMA,
    MAX_REPAIR_ATTEMPTS,
    ProviderTimeout,
    ProviderUnavailable,
    TutorRunStatus,
)
from dicks_laboratory.tutor_evidence import LessonStage, canonical_json

from tutor_poc import grounding
from tutor_poc.evidence import ROLE, ChartLesson, chart_lesson, model_evidence
from tutor_poc.pricing import UnsupportedModel, estimate_cost, pricing_for
from tutor_poc.prompt import PROMPT_VERSION, PROMPTS, TASKS, prompt_sha256
from tutor_poc.timeline import ChartTimeline
from tutor_poc.tutor import PROVIDER_ID as FAKE_PROVIDER_ID
from tutor_poc.tutor import FakeTutorProvider, TutorAction, format_ct, snapshot_evidence

REQUEST_SCHEMA = "TUTOR_POC_MODEL_REQUEST_V1"
CONTEXT_MESSAGES = 8  # recent conversation messages sent to the model (at or before the current cutoff)
CONTEXT_MESSAGE_CHARS = 1200
DEFAULT_MODEL = "claude-opus-5-5"
DEFAULT_EFFORT = "low"
EFFORTS = ("low", "medium", "high", "xhigh", "max")
ACTION_NAMES = {TutorAction.QUESTION: "QUESTION", TutorAction.MESSAGE: "MESSAGE", TutorAction.HINT: "HINT",
                TutorAction.EXPLAIN: "EXPLAIN"}

# The Human-facing message for each failure. Nothing internal (prompts, provider bodies, traces) reaches the browser.
FAILURE_MESSAGES = {
    TutorRunStatus.GROUNDING_FAILED: "Tutor response could not be grounded in the replay evidence. Please try again.",
    TutorRunStatus.INVALID_STRUCTURED_OUTPUT: "Tutor response could not be read. Please try again.",
    TutorRunStatus.PROVIDER_TIMEOUT: "The AI provider did not answer in time. Please try again.",
    TutorRunStatus.PROVIDER_UNAVAILABLE: "The AI provider is unavailable right now. Please try again.",
}


class ProviderConfigError(ValueError):
    """The configured provider cannot run (unknown provider / model / effort, missing credentials)."""


# --- turn types -----------------------------------------------------------------------------------

@dataclass(frozen=True)
class HistoryMessage:
    role: str  # "student" | "tutor"
    kind: str  # question / reply / hint / explain / human
    replay_cutoff_utc: datetime
    text: str


@dataclass(frozen=True)
class TurnContext:
    action: TutorAction
    stage: LessonStage  # the stage after this action (server-decided)
    turn: int
    text: str | None  # the Human's message (MESSAGE only)
    timeline: ChartTimeline
    index: int  # replay position
    history: tuple[HistoryMessage, ...] = ()  # already filtered to this date and cutoffs <= the current one


@dataclass(frozen=True)
class Usage:
    """Provider-reported token counts; None = the provider did not report it (never estimated)."""

    input_tokens: int | None  # uncached input
    output_tokens: int | None
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None


@dataclass(frozen=True)
class ModelReply:
    text: str
    served_model: str
    latency_s: float
    usage: Usage
    raw_usage: dict | None = None  # the provider's usage object as returned
    stop_reason: str | None = None
    request_id: str | None = None
    fallback_used: bool = False


@dataclass(frozen=True)
class Attempt:
    repair_attempt: int
    status: TutorRunStatus
    request_bytes: int
    reply: ModelReply | None
    issues: tuple[str, ...] = ()
    detail: str | None = None
    cost_usd: Decimal | None = None
    validation_s: float = 0.0


@dataclass(frozen=True)
class TurnResult:
    status: str  # "FAKE" or a TutorRunStatus value
    text: str | None  # shown only when accepted
    provider: str
    model: str | None = None
    effort: str | None = None
    prompt_version: str | None = None
    pricing_version: str | None = None
    evidence_bytes: int | None = None
    attempts: tuple[Attempt, ...] = ()
    grounding: dict | None = None
    timings_ms: dict = field(default_factory=dict)

    @property
    def accepted(self) -> bool:
        return self.status in ("FAKE", TutorRunStatus.GROUNDED.value)

    @property
    def error_message(self) -> str | None:
        return None if self.accepted else FAILURE_MESSAGES.get(TutorRunStatus(self.status), FAILURE_MESSAGES[
            TutorRunStatus.PROVIDER_UNAVAILABLE])

    def usage_total(self) -> Usage | None:
        replies = [a.reply for a in self.attempts if a.reply is not None]
        if not replies:
            return None

        def total(name):
            vals = [getattr(r.usage, name) for r in replies]
            return None if any(v is None for v in vals) else sum(vals)

        return Usage(total("input_tokens"), total("output_tokens"), total("cache_read_input_tokens"),
                     total("cache_creation_input_tokens"))

    def cost_usd(self) -> Decimal | None:
        if self.status == "FAKE":
            return Decimal(0)
        costs = [a.cost_usd for a in self.attempts if a.reply is not None]
        return None if not costs or any(c is None for c in costs) else sum(costs, Decimal(0))


class TutorModelProvider(Protocol):
    provider_id: str

    def respond(self, ctx: TurnContext) -> TurnResult: ...

    def public_config(self) -> dict: ...


# --- fake ------------------------------------------------------------------------------------------

class FakeProvider:
    """The accepted A2 scripted Tutor behind the A3 seam. Zero cost, no network, no credentials."""

    provider_id = "fake"

    def __init__(self, scripted: FakeTutorProvider | None = None) -> None:
        self.scripted = scripted or FakeTutorProvider()

    def respond(self, ctx: TurnContext) -> TurnResult:
        evidence = snapshot_evidence(ctx.timeline, ctx.index)
        text = self.scripted.reply(ctx.action, ctx.stage, ctx.turn, ctx.text, evidence)
        return TurnResult("FAKE", text, FAKE_PROVIDER_ID)  # no model metrics: same inputs, same response

    def public_config(self) -> dict:
        return {"mode": "fake", "provider": "fake", "provider_id": FAKE_PROVIDER_ID, "model": None, "effort": None,
                "prompt_version": None, "pricing_version": None}


# --- real ------------------------------------------------------------------------------------------

def _anyof(node):
    """The frozen ANSWER_JSON_SCHEMA with JSON type unions written as anyOf (same shape, same keys)."""
    if isinstance(node, dict):
        out = {k: _anyof(v) for k, v in node.items()}
        if isinstance(out.get("type"), list):
            out = {k: v for k, v in out.items() if k != "type"} | {"anyOf": [{"type": t} for t in node["type"]]}
        return out
    if isinstance(node, list):
        return [_anyof(v) for v in node]
    return node


def answer_schema() -> dict:
    """What the model must return: exactly the frozen TutorAnswer model shape, citing only this POC's source."""
    schema = copy.deepcopy(ANSWER_JSON_SCHEMA)
    roles = [ROLE.value]
    claim = schema["properties"]["claims"]["items"]["properties"]
    claim["evidence_refs"]["items"]["properties"]["source"]["enum"] = roles
    claim["asserted"]["items"]["properties"]["ref"]["properties"]["source"]["enum"] = roles
    schema["properties"]["unsupported_claims"]["items"]["properties"]["evidence_refs"]["items"]["properties"][
        "source"]["enum"] = roles
    return _anyof(schema)


ANSWER_SCHEMA_WIRE = answer_schema()


class ModelClient(Protocol):
    provider: str
    model: str

    def parameters(self) -> dict: ...

    def complete(self, system: str, user: str, schema: dict) -> ModelReply: ...


def _history(ctx: TurnContext) -> list[dict]:
    cutoff = ctx.timeline.positions[ctx.index].cutoff_utc
    kept = [m for m in ctx.history if m.replay_cutoff_utc <= cutoff][-CONTEXT_MESSAGES:]  # defensive re-check
    return [{"role": m.role, "kind": m.kind, "replay_cutoff_ct": format_ct(int(m.replay_cutoff_utc.timestamp())),
             "text": m.text[:CONTEXT_MESSAGE_CHARS]} for m in kept]


def build_user_message(ctx: TurnContext, cl: ChartLesson, repair: dict | None = None) -> tuple[str, int]:
    """(canonical JSON user message, evidence section bytes)."""
    evidence = model_evidence(cl)
    body = {"schema": REQUEST_SCHEMA, "task": TASKS[ctx.action.value], "action": ACTION_NAMES[ctx.action],
            "stage": ctx.stage.value, "evidence": evidence, "conversation": _history(ctx),
            "student_message": ctx.text}
    if repair is not None:
        body["repair"] = repair
    return canonical_json(body), len(canonical_json(evidence).encode("utf-8"))


class GroundedProvider:
    """Real-model Tutor: the model interprets authorized evidence; the validator decides what is shown."""

    provider_id = "anthropic"

    def __init__(self, client: ModelClient, effort: str | None = None) -> None:
        self.client = client
        self.effort = effort
        self.pricing = pricing_for(client.provider, client.model)

    def public_config(self) -> dict:
        return {"mode": "real", "provider": self.client.provider, "provider_id": self.client.provider,
                "model": self.client.model, "effort": self.effort, "prompt_version": PROMPT_VERSION,
                "pricing_version": self.pricing.pricing_version}

    def _cost(self, reply: ModelReply) -> Decimal | None:
        u = reply.usage
        if reply.fallback_used or reply.served_model != self.client.model or u.input_tokens is None \
                or u.output_tokens is None:
            return None  # priced only for the configured model; raw usage is still recorded
        return estimate_cost(self.pricing, u.input_tokens, u.output_tokens, u.cache_read_input_tokens or 0,
                             u.cache_creation_input_tokens or 0)

    def respond(self, ctx: TurnContext) -> TurnResult:
        t0 = time.perf_counter()
        cutoff = ctx.timeline.positions[ctx.index].cutoff_utc
        cl = chart_lesson(ctx.timeline, ctx.index, f"TUTOR_POC_A3:{ctx.timeline.trading_date}:{cutoff.isoformat()}")
        system = PROMPTS[PROMPT_VERSION]
        user, evidence_bytes = build_user_message(ctx, cl)
        t_evidence = time.perf_counter() - t0
        attempts: list[Attempt] = []
        repair = None
        accepted = None
        for n in range(1 + MAX_REPAIR_ATTEMPTS):
            if repair is not None:
                user, _ = build_user_message(ctx, cl, repair)
            size = len(user.encode("utf-8"))
            try:
                reply = self.client.complete(system, user, ANSWER_SCHEMA_WIRE)
            except ProviderTimeout as exc:
                attempts.append(Attempt(n, TutorRunStatus.PROVIDER_TIMEOUT, size, None, detail=str(exc)))
                break
            except ProviderUnavailable as exc:
                attempts.append(Attempt(n, TutorRunStatus.PROVIDER_UNAVAILABLE, size, None, detail=str(exc)))
                break
            v0 = time.perf_counter()
            status, answer, report, issues, detail = grounding.evaluate(reply.text, cl, ctx.stage, ctx.text)
            if detail is None and reply.stop_reason not in (None, "end_turn"):
                detail = f"stop_reason={reply.stop_reason}"
            issue_text = tuple(f"{i.code} at {i.where}: {i.detail}" for i in issues)
            attempts.append(Attempt(n, status, size, reply, issue_text, detail, self._cost(reply),
                                    time.perf_counter() - v0))
            if status is TutorRunStatus.GROUNDED:
                accepted = (answer, report)
                break
            repair = {"instruction": "Your previous answer failed deterministic validation. Return a corrected "
                                     "structured answer using only the same evidence.",
                      "previous_answer": reply.text, "validation_errors": list(issue_text) or [detail]}
        last = attempts[-1]
        status = last.status
        text = summary = None
        if accepted is not None:
            text = accepted[0].answer_text
            summary = grounding.grounding_summary(accepted[0], accepted[1], cl)
        model_s = sum(a.reply.latency_s for a in attempts if a.reply is not None)
        timings = {"evidence": round(t_evidence * 1000, 1), "model": round(model_s * 1000, 1),
                   "validation": round(sum(a.validation_s for a in attempts) * 1000, 1),
                   "total": round((time.perf_counter() - t0) * 1000, 1)}
        return TurnResult(status.value, text, self.client.provider, self.client.model, self.effort, PROMPT_VERSION,
                          self.pricing.pricing_version, evidence_bytes, tuple(attempts), summary, timings)


# --- Anthropic transport ---------------------------------------------------------------------------

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicModelClient:
    """Claude through the Anthropic Messages API (official `anthropic` SDK, direct HTTPS).

    Structured output: output_config.format json_schema (the frozen 0AA-B adapter's forced tool use and
    temperature 0 are rejected by claude-opus-5-5). The fixed system prompt is a cache breakpoint, so its
    tokens are billed as cache reads on later turns. Server-side refusal fallback ("default") is on; a turn
    served by a fallback model keeps its raw usage but gets no cost estimate. Transport: one SDK retry
    (connection errors, 408/409/429/5xx), a per-attempt timeout. The key is passed to the SDK client only.
    """

    provider = "anthropic"

    def __init__(self, model: str, effort: str, api_key: str, timeout_s: float = 60.0, max_retries: int = 1,
                 max_tokens: int = 16000, sdk_client=None) -> None:
        import anthropic

        self.model, self.effort, self.timeout_s, self.max_retries, self.max_tokens = (
            model, effort, timeout_s, max_retries, max_tokens)
        self._sdk = anthropic
        self._client = sdk_client or anthropic.Anthropic(api_key=api_key, timeout=timeout_s, max_retries=max_retries)

    def parameters(self) -> dict:
        return {"model": self.model, "effort": self.effort, "max_tokens": self.max_tokens, "timeout_s": self.timeout_s,
                "max_retries": self.max_retries, "structured_output": "output_config.format json_schema",
                "fallbacks": "default"}

    def request(self, system: str, user: str, schema: dict) -> dict:
        return {"model": self.model, "max_tokens": self.max_tokens,
                "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                "messages": [{"role": "user", "content": user}],
                "output_config": {"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
                "betas": [FALLBACK_BETA], "fallbacks": "default"}

    def complete(self, system: str, user: str, schema: dict) -> ModelReply:
        a = self._sdk
        start = time.monotonic()
        try:
            resp = self._client.beta.messages.create(**self.request(system, user, schema))
        except a.APITimeoutError as exc:
            raise ProviderTimeout(f"no answer within {self.timeout_s} s") from exc
        except a.APIStatusError as exc:  # never include the provider's body
            raise ProviderUnavailable(f"HTTP {exc.status_code} {type(exc).__name__}") from exc
        except a.APIConnectionError as exc:
            raise ProviderUnavailable(type(exc).__name__) from exc
        latency = time.monotonic() - start
        text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
        u = resp.usage
        fallback = any(getattr(b, "type", None) == "fallback" for b in resp.content) or any(
            getattr(i, "type", None) == "fallback_message" for i in (getattr(u, "iterations", None) or []))
        raw = u.model_dump(mode="json", exclude_none=True) if hasattr(u, "model_dump") else None
        return ModelReply(text, resp.model, latency,
                          Usage(u.input_tokens, u.output_tokens, getattr(u, "cache_read_input_tokens", None),
                                getattr(u, "cache_creation_input_tokens", None)),
                          raw, resp.stop_reason, getattr(resp, "_request_id", None), fallback)


# --- configuration ---------------------------------------------------------------------------------

def provider_from_env(env: Mapping[str, str] | None = None) -> TutorModelProvider:
    """TUTOR_PROVIDER=fake (default) | anthropic;  TUTOR_MODEL (default claude-opus-5-5);  TUTOR_EFFORT (default low);
    ANTHROPIC_API_KEY (anthropic only, read here and handed to the SDK client; never logged or returned)."""
    env = os.environ if env is None else env
    name = (env.get("TUTOR_PROVIDER") or "fake").strip().lower()
    if name == "fake":
        return FakeProvider()
    if name != "anthropic":
        raise ProviderConfigError(f"unknown TUTOR_PROVIDER {name!r}: use 'fake' or 'anthropic'")
    model = (env.get("TUTOR_MODEL") or DEFAULT_MODEL).strip()
    try:
        pricing_for("anthropic", model)
    except UnsupportedModel as exc:
        raise ProviderConfigError(str(exc)) from exc
    effort = (env.get("TUTOR_EFFORT") or DEFAULT_EFFORT).strip().lower()
    if effort not in EFFORTS:
        raise ProviderConfigError(f"unknown TUTOR_EFFORT {effort!r}: use one of {', '.join(EFFORTS)}")
    key = env.get("ANTHROPIC_API_KEY")
    if not key:
        raise ProviderConfigError("TUTOR_PROVIDER=anthropic needs ANTHROPIC_API_KEY in the server environment")
    return GroundedProvider(AnthropicModelClient(model, effort, key), effort)


# --- records ---------------------------------------------------------------------------------------

def usage_dict(u: Usage | None) -> dict | None:
    if u is None:
        return None
    total = None if u.input_tokens is None else (
        u.input_tokens + (u.cache_read_input_tokens or 0) + (u.cache_creation_input_tokens or 0))
    return {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
            "cached_input_tokens": u.cache_read_input_tokens, "cache_write_input_tokens": u.cache_creation_input_tokens,
            "total_input_tokens": total}


def _usd(d: Decimal | None) -> str | None:
    return None if d is None else f"{d:.6f}"


def turn_diagnostics(r: TurnResult) -> dict:
    """Per-turn diagnostics for the browser (no prompt text, no provider bodies, no credentials)."""
    return {"provider": r.provider, "model": r.model, "served_model": next(
                (a.reply.served_model for a in reversed(r.attempts) if a.reply), None),
            "effort": r.effort, "prompt_version": r.prompt_version,
            "prompt_sha256": prompt_sha256(r.prompt_version) if r.prompt_version else None,
            "pricing_version": r.pricing_version, "status": r.status, "attempts": len(r.attempts),
            "repair_attempts": sum(1 for a in r.attempts if a.repair_attempt), "usage": usage_dict(r.usage_total()),
            "raw_usage": [a.reply.raw_usage for a in r.attempts if a.reply is not None],
            "evidence_bytes": r.evidence_bytes, "request_bytes": [a.request_bytes for a in r.attempts],
            "latency_ms": r.timings_ms, "turn_cost_usd": _usd(r.cost_usd()),
            "fallback_used": any(a.reply.fallback_used for a in r.attempts if a.reply)}


def run_record(r: TurnResult, ctx: TurnContext) -> dict:
    """Server-side development record (JSONL): adds raw model texts and validator issues; no prompt, no key."""
    return {"schema": "TUTOR_POC_RUN_RECORD_V1", "trading_date": ctx.timeline.trading_date.isoformat(),
            "replay_cutoff_utc": ctx.timeline.positions[ctx.index].cutoff_utc.isoformat(), "turn": ctx.turn,
            "action": ctx.action.value, "stage": ctx.stage.value, **turn_diagnostics(r),
            "attempt_records": [{"repair_attempt": a.repair_attempt, "status": a.status.value,
                                 "issues": list(a.issues), "detail": a.detail, "request_bytes": a.request_bytes,
                                 "latency_s": round(a.reply.latency_s, 3) if a.reply else None,
                                 "request_id": a.reply.request_id if a.reply else None,
                                 "stop_reason": a.reply.stop_reason if a.reply else None,
                                 "response_text": a.reply.text if a.reply else None,
                                 "cost_usd": _usd(a.cost_usd)} for a in r.attempts]}


def dumps(record: dict) -> str:
    return json.dumps(record, sort_keys=True, default=str)
