// Tutor interaction state (0AC-A2). The server decides the Tutor's text and the lesson stage; this module
// keeps the in-session conversation and makes sure every message keeps the replay position it was
// produced at. A reply is accepted only for the pending turn and only if it names the same cutoff the
// request carried, so an old reply is never relabeled as current.

export const STAGES = ["QUESTION", "HINT", "ANSWER", "POST_REVEAL"] as const;
export type Stage = (typeof STAGES)[number];
export type TutorAction = "question" | "message" | "hint" | "explain";

export interface TurnResponse {
  turn_id: string;
  turn: number;
  role: "tutor";
  action: TutorAction;
  text: string;
  stage: Stage;
  trading_date: string;
  replay_cutoff_utc: string;
  provider: string;
}

export interface EvidenceItem {
  key: string;
  label: string;
  value: number;
}

export interface Evidence {
  schema: "TUTOR_POC_EVIDENCE_V1";
  trading_date: string;
  replay_cutoff_utc: string;
  provenance: Record<string, string>;
  latest_bar: { start_utc: number; end_utc: number } | null;
  items: EvidenceItem[];
}

// What a message is for, kept per message (the stage badge only shows the current lesson stage).
export type MessageKind = "question" | "reply" | "hint" | "explain" | "human";
const KIND_OF_ACTION: Record<TutorAction, MessageKind> = {
  question: "question", message: "reply", hint: "hint", explain: "explain",
};
const KIND_LABEL: Partial<Record<MessageKind, string>> = { hint: "Hint", explain: "Explain" };

/** The visible label for a message kind, or null for kinds that need none. */
export function kindLabel(kind: MessageKind): string | null {
  return KIND_LABEL[kind] ?? null;
}

export interface TutorMessage {
  id: string;
  role: "tutor" | "human";
  kind: MessageKind;
  text: string;
  stage: Stage;
  trading_date: string;
  replay_cutoff_utc: string;
}

export interface PendingTurn {
  turn: number;
  action: TutorAction;
  trading_date: string;
  replay_cutoff_utc: string;
}

export interface TutorState {
  messages: TutorMessage[];
  stage: Stage;
  nextTurn: number;
  pending: PendingTurn | null;
  error: string | null;
}

export const INITIAL_TUTOR: TutorState = { messages: [], stage: "QUESTION", nextTurn: 0, pending: null, error: null };

export type TutorEvent =
  | { type: "request"; action: TutorAction; trading_date: string; replay_cutoff_utc: string; text?: string }
  | { type: "reply"; response: TurnResponse }
  | { type: "fail"; turn: number; error: string };

/** The text to send, or null when the message must be rejected (empty / whitespace only). */
export function messageText(draft: string): string | null {
  const t = draft.trim();
  return t ? t : null;
}

export function tutorReducer(state: TutorState, ev: TutorEvent): TutorState {
  switch (ev.type) {
    case "request": {
      if (state.pending) return state;
      const turn = state.nextTurn;
      const pending = { turn, action: ev.action, trading_date: ev.trading_date, replay_cutoff_utc: ev.replay_cutoff_utc };
      const messages =
        ev.action === "message"
          ? [...state.messages, { id: `h${turn}`, role: "human" as const, kind: "human" as const, text: ev.text ?? "", stage: state.stage,
              trading_date: ev.trading_date, replay_cutoff_utc: ev.replay_cutoff_utc }]
          : state.messages;
      return { ...state, messages, nextTurn: turn + 1, pending, error: null };
    }
    case "reply": {
      const r = ev.response;
      const p = state.pending;
      if (!p || r.turn !== p.turn) return state; // not the reply we are waiting for
      if (r.replay_cutoff_utc !== p.replay_cutoff_utc || r.trading_date !== p.trading_date || !STAGES.includes(r.stage)) {
        return { ...state, pending: null, error: "Tutor reply did not match the replay position it was asked about" };
      }
      const msg: TutorMessage = { id: r.turn_id, role: "tutor", kind: KIND_OF_ACTION[p.action], text: r.text, stage: r.stage,
        trading_date: r.trading_date, replay_cutoff_utc: r.replay_cutoff_utc };
      return { ...state, messages: [...state.messages, msg], stage: r.stage, pending: null };
    }
    case "fail":
      if (!state.pending || state.pending.turn !== ev.turn) return state;
      return { ...state, pending: null, error: ev.error };
  }
}

/** Conversation rows with a divider wherever the replay position changes between messages. */
export type Row = { kind: "message"; message: TutorMessage } | { kind: "divider"; replay_cutoff_utc: string; key: string };

export function conversationRows(messages: TutorMessage[]): Row[] {
  const rows: Row[] = [];
  let at: string | null = null;
  for (const m of messages) {
    if (at !== null && m.replay_cutoff_utc !== at) {
      rows.push({ kind: "divider", replay_cutoff_utc: m.replay_cutoff_utc, key: `d-${m.id}` });
    }
    at = m.replay_cutoff_utc;
    rows.push({ kind: "message", message: m });
  }
  return rows;
}

/** Evidence is shown only for the replay position it was fetched for. */
export function evidenceFor(evidence: Evidence | null, replay_cutoff_utc: string | null): Evidence | null {
  return evidence && evidence.replay_cutoff_utc === replay_cutoff_utc ? evidence : null;
}

// Display grouping only: the server's values, never recomputed. Bands top to bottom, as on the chart.
const EVIDENCE_COLUMNS = [
  { title: "Latest bar", keys: ["open", "high", "low", "close"] },
  { title: "VWAP bands", keys: ["upper_2sd", "upper_1sd", "vwap", "lower_1sd", "lower_2sd"] },
];

export function evidenceColumns(ev: Evidence): { title: string; items: EvidenceItem[] }[] {
  const byKey = new Map(ev.items.map((i) => [i.key, i]));
  return EVIDENCE_COLUMNS.map((c) => ({
    title: c.title,
    items: c.keys.flatMap((k) => byKey.get(k) ?? []),
  }));
}

export function cutoffSecondsOf(iso: string): number {
  return Math.floor(Date.parse(iso) / 1000);
}

// --- API ------------------------------------------------------------------------------------------

async function json(r: Response): Promise<unknown> {
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export async function postTurn(
  date: string,
  body: { action: TutorAction; replay_cutoff_utc: string; stage: Stage; turn: number; text?: string },
): Promise<TurnResponse> {
  const r = await fetch(`/api/sessions/${date}/tutor/turn`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return (await json(r)) as TurnResponse;
}

export async function fetchEvidence(date: string, replay_cutoff_utc: string): Promise<Evidence> {
  const q = new URLSearchParams({ cutoff: replay_cutoff_utc });
  return (await json(await fetch(`/api/sessions/${date}/tutor/evidence?${q}`))) as Evidence;
}
