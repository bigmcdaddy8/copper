import { useCallback, useEffect, useReducer, useRef, useState, type CSSProperties, type KeyboardEvent } from "react";
import { formatCt } from "./replay";
import {
  formatKb,
  formatSeconds,
  formatTokens,
  formatUsd,
  summaryLine,
  type ProviderConfig,
  type TurnRecord,
} from "./diagnostics";
import {
  INITIAL_TUTOR,
  conversationRows,
  cutoffSecondsOf,
  evidenceColumns,
  kindLabel,
  evidenceFor,
  fetchConfig,
  fetchEvidence,
  messageText,
  newSessionId,
  postTurn,
  tutorReducer,
  type Evidence,
  type TutorAction,
  type TutorMessage,
  type TutorState,
} from "./tutor";

const ct = (iso: string) => `${formatCt(cutoffSecondsOf(iso))} CT`;

interface Props {
  date: string | null;
  cutoff: string | null; // the replay position currently on the chart (the Tutor context)
  style?: CSSProperties; // pane width from the divider
}

/** Container: owns the conversation and talks to the server. */
export function TutorPane({ date, cutoff, style }: Props) {
  const [state, dispatch] = useReducer(tutorReducer, INITIAL_TUTOR);
  const [draft, setDraft] = useState("");
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [evidenceError, setEvidenceError] = useState<string | null>(null);
  const stateRef = useRef(state);
  stateRef.current = state;
  const asked = useRef(false);
  const inflight = useRef(false); // set before the reducer re-renders, so a double click sends once
  const sessionId = useRef(newSessionId()); // this page's conversation; a reload starts a new one
  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [elapsedS, setElapsedS] = useState(0);

  useEffect(() => {
    fetchConfig()
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  // Seconds since the pending request started (real-model replies take a while).
  useEffect(() => {
    if (!state.pending) return;
    const t0 = Date.now();
    setElapsedS(0);
    const id = setInterval(() => setElapsedS(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => clearInterval(id);
  }, [state.pending]);

  // Returns synchronously whether the request was started; the reply arrives through the reducer.
  const request = useCallback(
    (action: TutorAction, text?: string): boolean => {
      const s = stateRef.current;
      if (!date || !cutoff || s.pending || inflight.current) return false;
      inflight.current = true;
      const turn = s.nextTurn;
      dispatch({ type: "request", action, trading_date: date, replay_cutoff_utc: cutoff, text });
      postTurn(date, { action, replay_cutoff_utc: cutoff, stage: s.stage, turn, text, session_id: sessionId.current })
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
      style={style}
      state={state}
      cutoff={cutoff}
      config={config}
      elapsedS={elapsedS}
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

function Message({ message: m, current }: { message: TutorMessage; current: boolean }) {
  const label = kindLabel(m.kind);
  return (
    <div className={`msg msg-${m.role} msg-kind-${m.kind}${current ? "" : " msg-other-context"}`}>
      <div className="msg-meta">
        {m.role === "tutor" ? "Tutor" : "You"} · {ct(m.replay_cutoff_utc)}
      </div>
      <div className="msg-text">
        {label && <strong className="msg-label">{label}: </strong>}
        {m.text}
      </div>
      {m.grounding && <GroundingDetails grounding={m.grounding} />}
    </div>
  );
}

/** The validator-accepted support for a real-model answer: facts vs interpretation, with the cited evidence. */
function GroundingDetails({ grounding: g }: { grounding: NonNullable<TutorMessage["grounding"]> }) {
  const facts = g.claims.length - g.interpretations;
  return (
    <details className="grounding">
      <summary>
        Grounded · {facts} fact{facts === 1 ? "" : "s"} · {g.interpretations} interpretation
        {g.interpretations === 1 ? "" : "s"}
        {g.unsupported.length ? ` · ${g.unsupported.length} not in evidence` : ""}
      </summary>
      <ul>
        {g.claims.map((c, i) => (
          <li key={i}>
            <span className={`cat cat-${c.category}`}>{c.category === "AI_INTERPRETATION" ? "interpretation" : c.category}</span>{" "}
            {c.statement}
            {c.cites.length > 0 && (
              <span className="cites"> — {c.cites.map((x) => `${x.label}${x.value === null ? "" : ` = ${x.value}`}`).join("; ")}</span>
            )}
          </li>
        ))}
        {g.unsupported.map((u, i) => (
          <li key={`u${i}`}>
            <span className="cat cat-unsupported">{u.support}</span> {u.statement}
          </li>
        ))}
      </ul>
    </details>
  );
}

/** Development diagnostics for real-model turns: one summary line, details on demand. */
function Diagnostics({ config, turns }: { config: ProviderConfig | null; turns: TurnRecord[] }) {
  const last = turns.length ? turns[turns.length - 1].diagnostics : null;
  const line = summaryLine(config, last);
  if (!config || config.mode === "fake") {
    return <div className="ai-diag ai-diag-fake">{line}</div>;
  }
  const s = last?.session;
  return (
    <details className="ai-diag">
      <summary>{line}</summary>
      <div className="ai-diag-body">
        <div>
          Provider {config.provider} · model {config.model} · effort {config.effort} · prompt {config.prompt_version} ·
          pricing {config.pricing_version}
        </div>
        {s && (
          <div>
            Session: {s.turns} turns · {s.model_calls} model calls · input {formatTokens(s.total_input_tokens)} (cached{" "}
            {formatTokens(s.cached_input_tokens)}, cache write {formatTokens(s.cache_write_input_tokens)}) · output{" "}
            {formatTokens(s.output_tokens)} · cost {formatUsd(s.cost_usd)}
            {s.unpriced_calls ? ` · ${s.unpriced_calls} unpriced` : ""} (resets on page reload)
          </div>
        )}
        <table>
          <thead>
            <tr>
              <th>Turn</th><th>Status</th><th>Model</th><th>Total</th><th>Input</th><th>Cached</th><th>Output</th>
              <th>Evidence</th><th>Repairs</th><th>Cost</th>
            </tr>
          </thead>
          <tbody>
            {turns.slice(-12).map((t) => {
              const d = t.diagnostics;
              return (
                <tr key={t.turn} className={d.status === "GROUNDED" ? "" : "diag-fail"}>
                  <td>{t.action} {ct(t.replay_cutoff_utc)}</td>
                  <td>{d.status}</td>
                  <td>{formatSeconds(d.latency_ms.model)}</td>
                  <td>{formatSeconds(d.latency_ms.total)}</td>
                  <td>{formatTokens(d.usage?.input_tokens)}</td>
                  <td>{formatTokens(d.usage?.cached_input_tokens)}</td>
                  <td>{formatTokens(d.usage?.output_tokens)}</td>
                  <td>{formatKb(d.evidence_bytes)}</td>
                  <td>{d.repair_attempts}</td>
                  <td>{formatUsd(d.turn_cost_usd)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </details>
  );
}

interface ViewProps {
  style?: CSSProperties;
  state: TutorState;
  cutoff: string | null;
  config?: ProviderConfig | null;
  elapsedS?: number;
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
    <aside className="tutor-pane" style={p.style}>
      <div className="tutor-head">
        <h2>AI Tutor</h2>
        {p.config?.mode === "real" ? (
          <span className="tutor-real" title="Real AI model; every answer is checked against the replay evidence">
            {p.config.model}
          </span>
        ) : (
          <span className="tutor-sim" title="Scripted responses for interaction testing; no AI model is called">
            simulated
          </span>
        )}
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
            <Message key={row.message.id} message={row.message} current={row.message.replay_cutoff_utc === cutoff} />
          ),
        )}
        {state.pending && (
          <div className="msg msg-tutor msg-pending">
            Tutor is replying
            {state.pending.replay_cutoff_utc !== cutoff ? ` about replay ${ct(state.pending.replay_cutoff_utc)}` : ""}…{" "}
            {p.config?.mode === "real" && p.elapsedS ? `${p.elapsedS} s` : ""}
          </div>
        )}
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
      <Diagnostics config={p.config ?? null} turns={state.turns} />
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
