// 0AC-A3: real-model replies, failures, grounding disclosure and diagnostics in the browser (no network).
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { formatKb, formatSeconds, formatTokens, formatUsd, summaryLine, type ProviderConfig, type TurnDiagnostics } from "./diagnostics";
import { TutorView } from "./TutorPane";
import {
  INITIAL_TUTOR,
  isAccepted,
  newSessionId,
  postTurn,
  tutorReducer,
  type Grounding,
  type TurnResponse,
  type TutorAction,
  type TutorState,
} from "./tutor";

const D = "2026-09-30";
const AT_0900 = "2026-09-30T14:00:00+00:00";
const AT_0905 = "2026-09-30T14:05:00+00:00";
const REAL: ProviderConfig = { mode: "real", provider: "anthropic", model: "claude-opus-5-5", effort: "low",
  prompt_version: "TUTOR_POC_SYSTEM_V1", pricing_version: "ANTHROPIC_LIST_2026-10-17" };
const FAKE: ProviderConfig = { mode: "fake", provider: "fake", model: null, effort: null, prompt_version: null,
  pricing_version: null };

function diag(over: Partial<TurnDiagnostics> = {}): TurnDiagnostics {
  return { provider: "anthropic", model: "claude-opus-5-5", served_model: "claude-opus-5-5", effort: "low",
    prompt_version: "TUTOR_POC_SYSTEM_V1", pricing_version: "ANTHROPIC_LIST_2026-10-17", status: "GROUNDED", attempts: 1,
    repair_attempts: 0, usage: { input_tokens: 1000, output_tokens: 180, cached_input_tokens: 3000,
      cache_write_input_tokens: 0, total_input_tokens: 4000 }, evidence_bytes: 8602,
    latency_ms: { evidence: 2, model: 2800, validation: 3, total: 2810 }, turn_cost_usd: "0.008200",
    fallback_used: false, session: { turns: 1, model_calls: 1, input_tokens: 1000, output_tokens: 180,
      cached_input_tokens: 3000, cache_write_input_tokens: 0, total_input_tokens: 4000, cost_usd: "0.008200",
      unpriced_calls: 0 }, ...over };
}

const GROUNDING: Grounding = { checked_refs: 3, interpretations: 1, unsupported: [],
  claims: [{ category: "OBSERVED_FACT", statement: "The close.", cites: [{ pointer: "/latest_bar/close", label: "latest completed bar close", value: "7751.25" }] },
    { category: "AI_INTERPRETATION", statement: "Near VWAP.", cites: [] }] };

function ask(state: TutorState, action: TutorAction, at = AT_0900, text?: string) {
  return tutorReducer(state, { type: "request", action, trading_date: D, replay_cutoff_utc: at, text });
}

function answer(state: TutorState, over: Partial<TurnResponse> = {}): TutorState {
  const p = state.pending!;
  const r: TurnResponse = { turn_id: `t${p.turn}`, turn: p.turn, role: "tutor", action: p.action, text: "Close is below VWAP.",
    stage: "QUESTION", trading_date: p.trading_date, replay_cutoff_utc: p.replay_cutoff_utc, provider: "anthropic",
    status: "GROUNDED", error: null, grounding: GROUNDING, diagnostics: diag(), ...over };
  return tutorReducer(state, { type: "reply", response: r });
}

const FAILED = { status: "GROUNDING_FAILED", text: null, grounding: null,
  error: "Tutor response could not be grounded in the replay evidence. Please try again." };

function view(state: TutorState, extra: Partial<Parameters<typeof TutorView>[0]> = {}) {
  const noop = () => {};
  return renderToStaticMarkup(
    <TutorView state={state} cutoff={AT_0900} config={REAL} draft="" evidenceOpen={false} evidence={null}
      evidenceError={null} onDraft={noop} onSend={noop} onAction={noop} onToggleEvidence={noop} {...extra} />,
  );
}

describe("real-model replies in the reducer", () => {
  it("a grounded reply becomes a Tutor message with its grounding and diagnostics", () => {
    const s = answer(ask(INITIAL_TUTOR, "question"));
    expect(s.messages).toHaveLength(1);
    expect(s.messages[0]).toMatchObject({ role: "tutor", text: "Close is below VWAP.", grounding: GROUNDING });
    expect(s.turns).toHaveLength(1);
    expect(s.turns[0]).toMatchObject({ turn: 0, action: "question", replay_cutoff_utc: AT_0900 });
    expect(s.error).toBeNull();
  });

  it("a failed turn shows only the server's short error, never a rejected answer, and keeps the stage", () => {
    const hinted = answer(ask(INITIAL_TUTOR, "hint"), { stage: "HINT" });
    const s = answer(ask(hinted, "explain"), { ...FAILED, stage: "HINT", diagnostics: diag({ status: "GROUNDING_FAILED", repair_attempts: 1 }) });
    expect(s.messages).toHaveLength(1);
    expect(s.error).toBe(FAILED.error);
    expect(s.stage).toBe("HINT");
    expect(s.pending).toBeNull();
    expect(s.turns.map((t) => t.diagnostics.status)).toEqual(["GROUNDED", "GROUNDING_FAILED"]); // cost of failures is kept
  });

  it("text on a failed status is never displayed", () => {
    const s = answer(ask(INITIAL_TUTOR, "question"), { status: "GROUNDING_FAILED", text: "The VWAP is 9999.00", error: "x" });
    expect(s.messages).toHaveLength(0);
    expect(JSON.stringify(s.messages)).not.toContain("9999");
  });

  it("isAccepted: FAKE and GROUNDED with text only", () => {
    const base = { turn_id: "t0", turn: 0, role: "tutor" as const, action: "question" as const, stage: "QUESTION" as const,
      trading_date: D, replay_cutoff_utc: AT_0900, provider: "x" };
    expect(isAccepted({ ...base, text: "a", status: "FAKE" })).toBe(true);
    expect(isAccepted({ ...base, text: "a", status: "GROUNDED" })).toBe(true);
    expect(isAccepted({ ...base, text: "a" })).toBe(true); // A2 replies carry no status
    expect(isAccepted({ ...base, text: null, status: "GROUNDED" })).toBe(false);
    for (const status of ["GROUNDING_FAILED", "INVALID_STRUCTURED_OUTPUT", "PROVIDER_TIMEOUT", "PROVIDER_UNAVAILABLE"]) {
      expect(isAccepted({ ...base, text: "a", status })).toBe(false);
    }
  });

  it("a real reply that arrives after the replay moved keeps its original cutoff", () => {
    const pending = ask(INITIAL_TUTOR, "message", AT_0900, "what now?");
    // the chart moves to 09:05 while waiting; the reply still answers the 09:00 request
    const s = answer(pending);
    expect(s.messages.map((m) => m.replay_cutoff_utc)).toEqual([AT_0900, AT_0900]);
    const html = view(s, { cutoff: AT_0905 });
    expect(html).toContain("msg-other-context");
  });

  it("a reply naming a different cutoff than its request is refused", () => {
    const pending = ask(INITIAL_TUTOR, "question", AT_0900);
    const s = answer(pending, { replay_cutoff_utc: AT_0905 });
    expect(s.messages).toHaveLength(0);
    expect(s.error).toMatch(/did not match/);
  });
});

describe("TutorView with a real provider", () => {
  it("shows the model instead of 'simulated' and a one-line diagnostics summary", () => {
    const s = answer(ask(INITIAL_TUTOR, "question"));
    const html = view(s);
    expect(html).toContain("claude-opus-5-5");
    expect(html).not.toContain(">simulated<");
    expect(html).toContain("AI 2.8 s · in 4,000 · out 180 · turn $0.0082 · session $0.0082");
    expect(html).toContain("TUTOR_POC_SYSTEM_V1");
  });

  it("labels facts and interpretations in a collapsed grounding disclosure", () => {
    const html = view(answer(ask(INITIAL_TUTOR, "question")));
    expect(html).toMatch(/<details class="grounding">/);
    expect(html).toContain("Grounded · 1 fact · 1 interpretation");
    expect(html).toContain("latest completed bar close = 7751.25");
  });

  it("pending shows elapsed seconds and, after the replay moves, which cutoff it answers", () => {
    const pending = ask(INITIAL_TUTOR, "question", AT_0900);
    expect(view(pending, { elapsedS: 4 })).toContain("Tutor is replying… 4 s");
    expect(view(pending, { elapsedS: 4, cutoff: AT_0905 })).toContain("Tutor is replying about replay 09:00 CT… 4 s");
    expect(view(pending, { elapsedS: 4 })).toMatch(/<button disabled="">Hint<\/button>|disabled=""[^>]*>Hint/);
  });

  it("renders a failed turn as an error line with its diagnostics row", () => {
    const s = answer(ask(INITIAL_TUTOR, "question"), { ...FAILED, diagnostics: diag({ status: "GROUNDING_FAILED", turn_cost_usd: "0.017200" }) });
    const html = view(s);
    expect(html).toContain(FAILED.error);
    expect(html).toContain("diag-fail");
    expect(html).toContain("$0.0172");
  });

  it("fake mode states provider fake and zero cost", () => {
    const html = view(INITIAL_TUTOR, { config: FAKE });
    expect(html).toContain("Provider: fake · cost $0");
    expect(html).toContain(">simulated<");
  });
});

describe("diagnostics formatting", () => {
  it("formats server values and marks missing ones", () => {
    expect(formatTokens(12345)).toBe("12,345");
    expect(formatTokens(null)).toBe("n/a");
    expect(formatSeconds(2800)).toBe("2.8 s");
    expect(formatKb(8602)).toBe("8.4 KB");
    expect(formatUsd("0.008600")).toBe("$0.0086");
    expect(formatUsd(null)).toBe("unpriced");
  });

  it("summary line", () => {
    expect(summaryLine(FAKE, null)).toBe("Provider: fake · cost $0");
    expect(summaryLine(REAL, null)).toBe("AI: claude-opus-5-5 · no turns yet");
  });
});

describe("transport", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("each page gets its own session id", () => {
    expect(newSessionId()).not.toBe(newSessionId());
  });

  it("sends the session id and gives up with a clear error after the browser timeout", async () => {
    const bodies: string[] = [];
    vi.stubGlobal("fetch", (_url: string, init: RequestInit) => {
      bodies.push(String(init.body));
      return new Promise((_resolve, reject) => {
        init.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
      });
    });
    await expect(postTurn(D, { action: "question", replay_cutoff_utc: AT_0900, stage: "QUESTION", turn: 0, session_id: "page-x" }, 10))
      .rejects.toThrow("The Tutor took too long to answer. Please try again.");
    expect(JSON.parse(bodies[0]).session_id).toBe("page-x");
  });
});
