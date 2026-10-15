import { useCallback, useEffect, useReducer, useRef, useState, type KeyboardEvent } from "react";
import { formatCt } from "./replay";
import {
  INITIAL_TUTOR,
  conversationRows,
  cutoffSecondsOf,
  evidenceColumns,
  evidenceFor,
  fetchEvidence,
  messageText,
  postTurn,
  tutorReducer,
  type Evidence,
  type TutorAction,
  type TutorState,
} from "./tutor";

const ct = (iso: string) => `${formatCt(cutoffSecondsOf(iso))} CT`;

interface Props {
  date: string | null;
  cutoff: string | null; // the replay position currently on the chart (the Tutor context)
}

/** Container: owns the conversation and talks to the server. */
export function TutorPane({ date, cutoff }: Props) {
  const [state, dispatch] = useReducer(tutorReducer, INITIAL_TUTOR);
  const [draft, setDraft] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const asked = useRef(false);
  const inflight = useRef(false); // set before the reducer re-renders, so a double click sends once

  // Returns synchronously whether the request was started; the reply arrives through the reducer.
  const request = useCallback(
    (action: TutorAction, text?: string): boolean => {
      const s = stateRef.current;
      if (!date || !cutoff || s.pending || inflight.current) return false;
      inflight.current = true;
      const turn = s.nextTurn;
      dispatch({ type: "request", action, trading_date: date, replay_cutoff_utc: cutoff, text });
      postTurn(date, { action, replay_cutoff_utc: cutoff, stage: s.stage, turn, text })
        .then((response) => dispatch({ type: "reply", response }))
        .catch((e) => dispatch({ type: "fail", turn, error: String(e) }))
        .finally(() => {
          inflight.current = false;
        });
      return true;
    },
    [date, cutoff],
  );

  // Opening question once the first replay position is known.
  useEffect(() => {
    if (!asked.current && date && cutoff) {
      asked.current = true;
      request("question");
    }
  }, [date, cutoff, request]);

  useEffect(() => {
    if (!evidenceOpen || !date || !cutoff) return;
    let live = true;
    setEvidenceError(null);
    fetchEvidence(date, cutoff)
      .then((ev) => live && setEvidence(ev))
      .catch((e) => live && setEvidenceError(String(e)));
    return () => {
      live = false;
    };
  }, [evidenceOpen, date, cutoff]);

  const send = () => {
    const text = messageText(draft);
    if (text === null) return;
    if (request("message", text)) setDraft("");
  };

  return (
    <TutorView
      state={state}
      cutoff={cutoff}
      draft={draft}
      evidenceOpen={evidenceOpen}
      evidence={evidenceFor(evidence, cutoff)}
      evidenceError={evidenceError}
      onDraft={setDraft}
      onSend={send}
      onAction={(a) => request(a)}
      onToggleEvidence={() => setEvidenceOpen((v) => !v)}
    />
  );
}

interface ViewProps {
  state: TutorState;
  cutoff: string | null;
  draft: string;
  evidenceOpen: boolean;
  evidence: Evidence | null;
  evidenceError: string | null;
  onDraft: (v: string) => void;
  onSend: () => void;
  onAction: (a: TutorAction) => void;
  onToggleEvidence: () => void;
}

/** Presentation only (rendered in tests without a browser). */
export function TutorView(p: ViewProps) {
  const { state, cutoff } = p;
  const busy = state.pending !== null || cutoff === null;
  const canSend = !busy && messageText(p.draft) !== null;
  const logRef = useRef<HTMLDivElement>(null);

  // Keep the newest message in view.
  useEffect(() => {
    const el = logRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [state.messages.length, state.pending, p.evidenceOpen, p.evidence]);

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (canSend) p.onSend();
    }
  };

  return (
    <aside className="tutor-pane">
      <div className="tutor-head">
        <h2>AI Tutor</h2>
        <span className="tutor-sim" title="Scripted responses for interaction testing; no AI model is called">
          simulated
        </span>
        <span className="stage-badge" data-stage={state.stage}>
          {state.stage}
        </span>
      </div>
      <div className="tutor-context">Tutor context: replay {cutoff ? ct(cutoff) : "—"}</div>

      <div className="tutor-log" ref={logRef} aria-live="polite">
        {conversationRows(state.messages).map((row) =>
          row.kind === "divider" ? (
            <div key={row.key} className="tutor-divider">
              replay {ct(row.replay_cutoff_utc)}
            </div>
          ) : (
            <div
              key={row.message.id}
              className={`msg msg-${row.message.role}${row.message.replay_cutoff_utc !== cutoff ? " msg-other-context" : ""}`}
            >
              <div className="msg-meta">
                {row.message.role === "tutor" ? "Tutor" : "You"} · {ct(row.message.replay_cutoff_utc)}
              </div>
              <div className="msg-text">{row.message.text}</div>
            </div>
          ),
        )}
        {state.pending && <div className="msg msg-tutor msg-pending">Tutor is replying…</div>}
      </div>

      {p.evidenceOpen && (
        <div className="evidence">
          {p.evidence ? (
            <>
              <div className="evidence-head">
                Evidence at replay {ct(p.evidence.replay_cutoff_utc)}
                {p.evidence.latest_bar &&
                  ` · bar ${formatCt(p.evidence.latest_bar.start_utc)}–${formatCt(p.evidence.latest_bar.end_utc)}`}
              </div>
              {p.evidence.items.length ? (
                <div className="evidence-cols">
                  {evidenceColumns(p.evidence).map((col) => (
                    <dl key={col.title} className="evidence-col">
                      <div className="evidence-col-title">{col.title}</div>
                      {col.items.map((i) => (
                        <div key={i.key}>
                          <dt>{i.label}</dt>
                          <dd>{i.value.toFixed(2)}</dd>
                        </div>
                      ))}
                    </dl>
                  ))}
                </div>
              ) : (
                <div className="hint">No completed bar at this replay position.</div>
              )}
              <div className="hint">From the Laboratory replay snapshot feeding the chart (as of the cutoff).</div>
            </>
          ) : p.evidenceError ? (
            <div className="error">{p.evidenceError}</div>
          ) : (
            <div className="hint">Loading evidence…</div>
          )}
        </div>
      )}

      {state.error && <div className="error tutor-error">{state.error}</div>}

      <div className="tutor-actions">
        <button disabled={busy} onClick={() => p.onAction("hint")} title="A short nudge; does not give the answer">
          Hint
        </button>
        <button disabled={busy} onClick={() => p.onAction("explain")} title="Walk through how to read this position">
          Explain
        </button>
        <button onClick={p.onToggleEvidence} aria-expanded={p.evidenceOpen} disabled={cutoff === null}>
          {p.evidenceOpen ? "Hide Evidence" : "Show Evidence"}
        </button>
        <button className="link" disabled={busy} onClick={() => p.onAction("question")}
          title="Start a new question at the current replay position">
          New question
        </button>
      </div>
      <div className="tutor-input">
        <textarea
          value={p.draft}
          onChange={(e) => p.onDraft(e.target.value)}
          onKeyDown={onKey}
          rows={3}
          placeholder="Type your answer… (Enter to send, Shift+Enter for a new line)"
          aria-label="Your message to the Tutor"
        />
        <button className="send" disabled={!canSend} onClick={p.onSend}>
          Send
        </button>
      </div>
    </aside>
  );
}
