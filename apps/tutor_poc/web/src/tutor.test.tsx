import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TutorView } from "./TutorPane";
import {
  INITIAL_TUTOR,
  conversationRows,
  evidenceColumns,
  evidenceFor,
  kindLabel,
  messageText,
  tutorReducer,
  type Evidence,
  type TurnResponse,
  type TutorAction,
  type TutorState,
} from "./tutor";

const D = "2026-09-30";
const AT_0900 = "2026-09-30T14:00:00+00:00";
const AT_0915 = "2026-09-30T14:15:00+00:00";

function reply(state: TutorState, over: Partial<TurnResponse> = {}): TurnResponse {
  const p = state.pending!;
  return { turn_id: `t${p.turn}`, turn: p.turn, role: "tutor", action: p.action, text: `reply ${p.turn}`,
    stage: "QUESTION", trading_date: p.trading_date, replay_cutoff_utc: p.replay_cutoff_utc,
    provider: "FAKE_DETERMINISTIC_V1", ...over };
}

function ask(state: TutorState, action: TutorAction, at = AT_0900, text?: string) {
  return tutorReducer(state, { type: "request", action, trading_date: D, replay_cutoff_utc: at, text });
}

function roundTrip(state: TutorState, action: TutorAction, at = AT_0900, text?: string, over: Partial<TurnResponse> = {}) {
  const s = ask(state, action, at, text);
  return tutorReducer(s, { type: "reply", response: reply(s, over) });
}

function view(state: TutorState, extra: Partial<Parameters<typeof TutorView>[0]> = {}) {
  const noop = () => {};
  return renderToStaticMarkup(
    <TutorView state={state} cutoff={AT_0900} draft="" evidenceOpen={false} evidence={null} evidenceError={null}
      onDraft={noop} onSend={noop} onAction={noop} onToggleEvidence={noop} {...extra} />,
  );
}

describe("message text", () => {
  it("rejects empty and whitespace-only messages", () => {
    expect(messageText("")).toBeNull();
    expect(messageText("  \n\t ")).toBeNull();
    expect(messageText("  above VWAP \n")).toBe("above VWAP");
  });
});

describe("tutorReducer", () => {
  it("sending a message appends the Human message at once and marks the turn pending", () => {
    const s = ask(INITIAL_TUTOR, "message", AT_0900, "price is above VWAP");
    expect(s.messages).toEqual([{ id: "h0", role: "human", kind: "human", text: "price is above VWAP", stage: "QUESTION",
      trading_date: D, replay_cutoff_utc: AT_0900 }]);
    expect(s.pending).toMatchObject({ turn: 0, action: "message", replay_cutoff_utc: AT_0900 });
    expect(s.nextTurn).toBe(1);
  });

  it("the Tutor reply is appended and its stage becomes the lesson stage", () => {
    const s = roundTrip(INITIAL_TUTOR, "hint", AT_0900, undefined, { stage: "HINT", text: "Start with…" });
    expect(s.pending).toBeNull();
    expect(s.stage).toBe("HINT");
    expect(s.messages.at(-1)).toMatchObject({ role: "tutor", text: "Start with…", stage: "HINT" });
  });

  it("hint and explain produce Tutor messages only (no Human bubble)", () => {
    let s = roundTrip(INITIAL_TUTOR, "hint", AT_0900, undefined, { stage: "HINT" });
    s = roundTrip(s, "explain", AT_0900, undefined, { stage: "ANSWER" });
    expect(s.messages.map((m) => m.role)).toEqual(["tutor", "tutor"]);
    expect(s.stage).toBe("ANSWER");
  });

  it("ignores a second request while one is pending", () => {
    const s = ask(INITIAL_TUTOR, "message", AT_0900, "one");
    expect(ask(s, "hint")).toBe(s);
  });

  it("keeps each message's own replay position when the replay moves", () => {
    let s = roundTrip(INITIAL_TUTOR, "question", AT_0900);
    s = roundTrip(s, "message", AT_0915, "now below VWAP");
    expect(s.messages.map((m) => [m.role, m.replay_cutoff_utc])).toEqual([
      ["tutor", AT_0900], ["human", AT_0915], ["tutor", AT_0915]]);
  });

  it("a reply that arrives after the replay moved stays stamped with the cutoff it was asked at", () => {
    const s = ask(INITIAL_TUTOR, "message", AT_0900, "q at 09:00");
    // the chart is at 09:15 by now; the reducer does not know or care: the reply keeps 09:00
    const after = tutorReducer(s, { type: "reply", response: reply(s) });
    expect(after.messages.at(-1)!.replay_cutoff_utc).toBe(AT_0900);
    expect(view(after, { cutoff: AT_0915 })).toContain("msg-other-context");
  });

  it("rejects a reply that names a different cutoff than the request", () => {
    const s = ask(INITIAL_TUTOR, "message", AT_0900, "q");
    const after = tutorReducer(s, { type: "reply", response: reply(s, { replay_cutoff_utc: AT_0915 }) });
    expect(after.messages).toHaveLength(1); // only the Human message
    expect(after.pending).toBeNull();
    expect(after.error).toMatch(/replay position/);
  });

  it("drops a reply for a turn that is not pending", () => {
    const s = ask(INITIAL_TUTOR, "message", AT_0900, "q");
    const stale = tutorReducer(s, { type: "reply", response: reply(s, { turn: 99, turn_id: "t99" }) });
    expect(stale).toBe(s);
  });

  it("a failed request clears pending and shows the error", () => {
    const s = ask(INITIAL_TUTOR, "hint");
    const f = tutorReducer(s, { type: "fail", turn: 0, error: "500: boom" });
    expect(f.pending).toBeNull();
    expect(f.error).toBe("500: boom");
  });
});

describe("conversation rows", () => {
  it("inserts a divider where the replay position changes", () => {
    let s = roundTrip(INITIAL_TUTOR, "question", AT_0900);
    s = roundTrip(s, "message", AT_0900, "a");
    s = roundTrip(s, "message", AT_0915, "b");
    const kinds = conversationRows(s.messages).map((r) => r.kind);
    expect(kinds).toEqual(["message", "message", "message", "divider", "message", "message"]);
  });
});

describe("evidence", () => {
  const ev: Evidence = {
    schema: "TUTOR_POC_EVIDENCE_V1", trading_date: D, replay_cutoff_utc: AT_0900, provenance: {},
    latest_bar: { start_utc: Date.parse("2026-09-30T13:55:00Z") / 1000, end_utc: Date.parse(AT_0900) / 1000 },
    items: [{ key: "close", label: "Close", value: 6712.25 }, { key: "vwap", label: "VWAP", value: 6705.5 }],
  };

  it("groups the server's items for display without changing values", () => {
    const cols = evidenceColumns(ev);
    expect(cols.map((c) => c.title)).toEqual(["Latest bar", "VWAP bands"]);
    expect(cols.flatMap((c) => c.items)).toEqual([ev.items[0], ev.items[1]]);
  });

  it("is shown only for the replay position it was fetched for", () => {
    expect(evidenceFor(ev, AT_0900)).toBe(ev);
    expect(evidenceFor(ev, AT_0915)).toBeNull();
  });

  it("renders a compact panel labeled with its replay position", () => {
    const html = view(INITIAL_TUTOR, { evidenceOpen: true, evidence: ev });
    expect(html).toContain("Evidence at replay 09:00 CT");
    expect(html).toContain("bar 08:55–09:00");
    expect(html).toContain("6712.25");
    expect(html).toContain("Hide Evidence");
    expect(view(INITIAL_TUTOR)).not.toContain("Evidence at replay");
  });
});

describe("TutorView", () => {
  it("shows the stage, the Tutor context and distinguishes Human from Tutor messages", () => {
    let s = roundTrip(INITIAL_TUTOR, "question", AT_0900, undefined, { text: "Look at the latest candle." });
    s = roundTrip(s, "message", AT_0900, "above VWAP", { stage: "QUESTION" });
    const html = view(s);
    expect(html).toContain('data-stage="QUESTION"');
    expect(html).toContain("Tutor context: replay 09:00 CT");
    expect(html).toContain("msg msg-tutor");
    expect(html).toContain("msg msg-human");
    expect(html).toContain("above VWAP");
    expect(html).toContain("simulated");
  });

  it("the context line follows the chart cutoff without rewriting earlier messages", () => {
    const s = roundTrip(INITIAL_TUTOR, "question", AT_0900);
    const html = view(s, { cutoff: AT_0915 });
    expect(html).toContain("Tutor context: replay 09:15 CT");
    expect(html).toContain("Tutor · 09:00 CT");
  });

  it("disables the Tutor controls while a reply is pending", () => {
    const pending = ask(INITIAL_TUTOR, "hint");
    const html = view(pending, { draft: "typed" });
    expect(html).toContain("Tutor is replying");
    for (const label of ["Hint", "Explain", "New question", "Send"]) {
      expect(html).toMatch(new RegExp(`<button[^>]*disabled=""[^>]*>${label}</button>`));
    }
  });

  it("Send is disabled for an empty draft and enabled for text", () => {
    expect(view(INITIAL_TUTOR, { draft: "   " })).toMatch(/<button class="send" disabled="">Send/);
    expect(view(INITIAL_TUTOR, { draft: "hi" })).toMatch(/<button class="send">Send/);
  });

  it("stage badge reflects HINT and ANSWER", () => {
    expect(view({ ...INITIAL_TUTOR, stage: "HINT" })).toContain('data-stage="HINT">HINT');
    expect(view({ ...INITIAL_TUTOR, stage: "ANSWER" })).toContain('data-stage="ANSWER">ANSWER');
  });
});

describe("message kind (A2P)", () => {
  it("each Tutor message keeps the kind of the action that produced it", () => {
    let s = roundTrip(INITIAL_TUTOR, "question");
    s = roundTrip(s, "message", AT_0900, "above VWAP");
    s = roundTrip(s, "hint", AT_0900, undefined, { stage: "HINT" });
    s = roundTrip(s, "explain", AT_0900, undefined, { stage: "ANSWER" });
    s = roundTrip(s, "message", AT_0900, "ok", { stage: "ANSWER" });
    expect(s.messages.map((m) => m.kind)).toEqual(["question", "human", "reply", "hint", "explain", "human", "reply"]);
    expect(s.stage).toBe("ANSWER"); // the lesson stage is separate and unchanged in meaning
  });

  it("Hint and Explain replies are visibly labeled; other messages are not", () => {
    let s = roundTrip(INITIAL_TUTOR, "question", AT_0900, undefined, { text: "Q-TEXT" });
    s = roundTrip(s, "message", AT_0900, "H-TEXT", { text: "R-TEXT" });
    s = roundTrip(s, "hint", AT_0900, undefined, { stage: "HINT", text: "HINT-TEXT" });
    s = roundTrip(s, "explain", AT_0900, undefined, { stage: "ANSWER", text: "EXPLAIN-TEXT" });
    const html = view(s);
    expect(html).toContain('<strong class="msg-label">Hint: </strong>HINT-TEXT');
    expect(html).toContain('<strong class="msg-label">Explain: </strong>EXPLAIN-TEXT');
    expect(html.match(/msg-label/g)).toHaveLength(2);
    for (const t of ["Q-TEXT", "H-TEXT", "R-TEXT"]) expect(html).toMatch(new RegExp(`<div class="msg-text">${t}</div>`));
    expect(kindLabel("reply")).toBeNull();
    expect(kindLabel("question")).toBeNull();
    expect(kindLabel("human")).toBeNull();
  });

  it("a Hint given at an earlier replay position is still labeled after the replay moves", () => {
    const s = roundTrip(INITIAL_TUTOR, "hint", AT_0900, undefined, { stage: "HINT", text: "nudge" });
    const html = view(s, { cutoff: AT_0915 });
    expect(html).toContain("msg-kind-hint msg-other-context");
    expect(html).toContain("Hint: </strong>nudge");
  });
});
