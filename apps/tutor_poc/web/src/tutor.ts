// Tutor interaction state (0AC-A2). The server decides the Tutor's text and the lesson stage; this module
// keeps the in-session conversation and makes sure every message keeps the replay position it was
// produced at. A reply is accepted only for the pending turn and only if it names the same cutoff the
// request carried, so an old reply is never relabeled as current.
//
// 0AC-A3: a reply may be a failure (the real model's answer could not be grounded, the provider timed out, ...).
// It then carries no text: the browser shows the server's short error and never any rejected answer.

import type { ProviderConfig, TurnDiagnostics, TurnRecord } from "./diagnostics";

export const STAGES = ["QUESTION", "HINT", "ANSWER", "POST_REVEAL"] as const;
export type Stage = (typeof STAGES)[number];
export type TutorAction = "question" | "message" | "hint" | "explain";

export interface TurnResponse {
  turn_id: string;
  turn: number;
  role: "tutor";
  action: TutorAction;
  text: string | null; // null when the turn failed
  stage: Stage;
  trading_date: string;
  replay_cutoff_utc: string;
  provider: string;
  status?: string; // FAKE | GROUNDED | GROUNDING_FAILED | INVALID_STRUCTURED_OUTPUT | PROVIDER_TIMEOUT | PROVIDER_UNAVAILABLE
  error?: string | null;
  grounding?: Grounding | null;
  diagnostics?: TurnDiagnostics;
}

/** What the validator accepted: each claim's category and the evidence it cites (server-built). */
export interface Grounding {
  checked_refs: number;
  interpretations: number;
  claims: { category: string; statement: string; cites: { pointer: string; label: string; value: string | number | boolean | null }[] }[];
  unsupported: { support: string; statement: string; missing: string[] }[];
}

const ACCEPTED = new Set(["FAKE", "GROUNDED"]);

/** A reply is shown only when the server accepted it and it has text. */
export function isAccepted(r: TurnResponse): boolean {
  return (r.status === undefined || ACCEPTED.has(r.status)) && typeof r.text === "string" && r.text.length > 0;
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
  grounding?: Grounding | null;
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
  turns: TurnRecord[]; // diagnostics of every answered turn, accepted or not
}

export const INITIAL_TUTOR: TutorState = { messages: [], stage: "QUESTION", nextTurn: 0, pending: null, error: null, turns: [] };

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
      const turns = r.diagnostics
        ? [...state.turns, { turn: r.turn, action: p.action, replay_cutoff_utc: r.replay_cutoff_utc, diagnostics: r.diagnostics }]
        : state.turns;
      if (!isAccepted(r)) {
        return { ...state, turns, pending: null, error: r.error || "The Tutor could not answer. Please try again." };
      }
      const msg: TutorMessage = { id: r.turn_id, role: "tutor", kind: KIND_OF_ACTION[p.action], text: r.text ?? "", stage: r.stage,
        trading_date: r.trading_date, replay_cutoff_utc: r.replay_cutoff_utc, grounding: r.grounding ?? null };
      return { ...state, messages: [...state.messages, msg], stage: r.stage, pending: null, turns };
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

// The server bounds a real turn (two model attempts, each with one transport retry and its own timeout);
// this is the browser's own ceiling so the pane can never wait forever.
export const TURN_TIMEOUT_MS = 300_000;

/** One random id per page: the server keeps that page's conversation context and usage totals in memory. */
export function newSessionId(): string {
  const c = globalThis.crypto;
  if (c?.randomUUID) return c.randomUUID();
  return `page-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export async function postTurn(
  date: string,
  body: { action: TutorAction; replay_cutoff_utc: string; stage: Stage; turn: number; text?: string; session_id?: string },
  timeoutMs: number = TURN_TIMEOUT_MS,
): Promise<TurnResponse> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(`/api/sessions/${date}/tutor/turn`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    });
    return (await json(r)) as TurnResponse;
  } catch (e) {
    if (ctrl.signal.aborted) throw new Error("The Tutor took too long to answer. Please try again.");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

export async function fetchConfig(): Promise<ProviderConfig> {
  return (await json(await fetch("/api/tutor/config"))) as ProviderConfig;
}

export async function fetchEvidence(date: string, replay_cutoff_utc: string): Promise<Evidence> {
  const q = new URLSearchParams({ cutoff: replay_cutoff_utc });
  return (await json(await fetch(`/api/sessions/${date}/tutor/evidence?${q}`))) as Evidence;
}
