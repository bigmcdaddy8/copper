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
  CONDITION_MARK,
  INITIAL_TUTOR,
  canExport,
  conversationRows,
  cutoffSecondsOf,
  evidenceColumns,
  kindLabel,
  evidenceFor,
  exportSession,
  fetchConfig,
  fetchEvidence,
  fetchLessons,
  guidedAskAt,
  messageText,
  newSessionId,
  postTurn,
  turnBody,
  tutorReducer,
  type Evidence,
  type LessonView,
  type TutorAction,
  type TutorMessage,
  type TutorState,
} from "./tutor";

const ct = (iso: string) => `${formatCt(cutoffSecondsOf(iso))} CT`;

interface Props {
  date: string | null;
  cutoff: string | null; // the replay position currently on the chart (the Tutor context)
  style?: CSSProperties; // pane width from the divider
  onSeek?: (cutoff: string) => void; // move the chart (a guided lesson starts at its own cutoff)
  onLessonChange?: (lesson: LessonView | null) => void;
}

/** Container: owns the conversation and talks to the server. */
export function TutorPane({ date, cutoff, style, onSeek, onLessonChange }: Props) {
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
  const [exportStatus, setExportStatus] = useState<ExportStatus>(null);
  const [lessons, setLessons] = useState<LessonView[]>([]);
  const lastAsked = useRef<string | null>(null); // guided mode: the replay position the Tutor last asked about
  const seeking = useRef<string | null>(null); // guided mode: the lesson start the chart is moving to

  useEffect(() => {
    if (!date) return;
    let live = true;
    fetchLessons(date)
      .then((l) => live && setLessons(l))
      .catch(() => live && setLessons([]));
    return () => {
      live = false;
    };
  }, [date]);

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
      const body = turnBody(s, action, cutoff, sessionId.current, text);
      dispatch({ type: "request", action, trading_date: date, replay_cutoff_utc: cutoff, text });
      postTurn(date, body)
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

  // Guided lesson (A4): the Tutor speaks at every replay position the Human moves to, connecting it to the lesson.
  useEffect(() => {
    if (!guidedAskAt(state, cutoff, lastAsked.current, seeking.current)) return;
    if (request("question")) {
      lastAsked.current = cutoff;
      seeking.current = null;
    }
  }, [state, cutoff, request]);

  useEffect(() => onLessonChange?.(state.mode === "guided" ? state.lesson : null), [state.mode, state.lesson, onLessonChange]);

  const startLesson = (l: LessonView) => {
    if (stateRef.current.pending) return;
    lastAsked.current = null;
    seeking.current = l.start_cutoff_utc;
    dispatch({ type: "mode", mode: "guided", lesson: l });
    if (cutoff !== l.start_cutoff_utc) onSeek?.(l.start_cutoff_utc);
  };
  const endLesson = () => {
    seeking.current = null;
    dispatch({ type: "mode", mode: "free", lesson: null });
  };

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

  // Export Session: the server's record of this page's session, downloaded as a ZIP. No Tutor turn, no state change.
  const onExport = () => {
    if (!date || !cutoff || !canExport(stateRef.current)) return;
    setExportStatus({ busy: true, text: "Exporting…" });
    exportSession(date, sessionId.current, cutoff)
      .then(({ filename, blob }) => {
        saveFile(blob, filename);
        setExportStatus({ busy: false, text: `Exported ${filename}` });
      })
      .catch((e) => setExportStatus({ busy: false, text: String(e instanceof Error ? e.message : e), error: true }));
  };

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
      onExport={onExport}
      exportStatus={exportStatus}
      lessons={lessons}
      onStartLesson={startLesson}
      onEndLesson={endLesson}
    />
  );
}

export type ExportStatus = { busy: boolean; text: string; error?: boolean } | null;

function saveFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
      {g.referenced_setups?.length ? <div className="grounding-setups">Setups cited: {g.referenced_setups.join(", ")}</div> : null}
      {g.missing_conditions?.length ? (
        <div className="grounding-setups">Missing conditions cited: {g.missing_conditions.join(", ")}</div>
      ) : null}
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
  onExport?: () => void;
  exportStatus?: ExportStatus;
  lessons?: LessonView[];
  onStartLesson?: (l: LessonView) => void;
  onEndLesson?: () => void;
}

/** The guided-lesson bar: mode, neutral title (the setup only after the reveal), phase and the semantics lock. */
function LessonBar({ lesson, onEnd, busy }: { lesson: LessonView; onEnd?: () => void; busy: boolean }) {
  const lock = Object.entries(lesson.locked_semantics).map(([k, v]) => `${k === "vwap_anchor" ? "VWAP anchor" : k} ${v}`);
  return (
    <div className="lesson-bar" role="status">
      <span className="lesson-mode">Guided Lesson</span>
      <span className="lesson-title" title={lesson.lesson_id}>{lesson.title}</span>
      {lesson.phase_label && <span className="lesson-phase">{lesson.phase_label}</span>}
      <span className="lesson-lock" title="Study semantics locked by this lesson">🔒 {lock.join(" · ")} (locked by lesson)</span>
      <button className="link" onClick={onEnd} disabled={busy || !onEnd}>End lesson</button>
    </div>
  );
}

/** The frozen setup analysis at the cutoff (Show Evidence): state, stage and condition marks per instance. */
function SetupTable({ ev }: { ev: Evidence }) {
  if (!ev.setups) return null;
  return (
    <div className="evidence-setups">
      <div className="evidence-col-title">
        Drysdale setups (Laboratory V1){ev.setup_analysis ? ` · analysis ${ev.setup_analysis.state} · ${ev.setup_analysis.quality_status}` : ""}
      </div>
      {ev.setups.length ? (
        <table>
          <tbody>
            {ev.setups.map((x) => (
              <tr key={`${x.family}-${x.direction}`} className={`setup-state-${x.state}`}>
                <td>{x.family} {x.direction}</td>
                <td>{x.state}</td>
                <td>{x.stage}</td>
                <td title={x.conditions.map((c) => `${c.order} ${c.policy_id}: ${c.status}`).join("\n")}>
                  {x.conditions.map((c) => CONDITION_MARK[c.status] ?? "?").join(" ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="hint">No setup instance in this session so far.</div>
      )}
    </div>
  );
}

/** The bars the Tutor sees, each with its own as-of bands (Show Evidence). */
function RecentBars({ ev }: { ev: Evidence }) {
  if (!ev.recent_bars?.length) return null;
  return (
    <table className="evidence-bars">
      <thead>
        <tr><th>Bar</th><th>Close</th><th>−2σ</th><th>−1σ</th><th>VWAP</th><th>+1σ</th><th>+2σ</th></tr>
      </thead>
      <tbody>
        {ev.recent_bars.map((b) => (
          <tr key={b.start_utc}>
            <td>{formatCt(b.start_utc)}</td>
            <td>{b.close.toFixed(2)}</td>
            <td>{b.lower_2sd.toFixed(2)}</td>
            <td>{b.lower_1sd.toFixed(2)}</td>
            <td>{b.vwap.toFixed(2)}</td>
            <td>{b.upper_1sd.toFixed(2)}</td>
            <td>{b.upper_2sd.toFixed(2)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
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
        {state.mode === "free" && (p.lessons?.length ?? 0) > 0 && (
          <button className="link start-lesson" disabled={busy || !p.onStartLesson}
            onClick={() => p.lessons && p.onStartLesson?.(p.lessons[0])}
            title={`Start a guided Drysdale lesson: ${p.lessons?.[0].title ?? ""}`}>
            Start Guided Lesson
          </button>
        )}
        <button className="link export" disabled={!canExport(state) || !!p.exportStatus?.busy || !p.onExport}
          onClick={p.onExport}
          title={state.turns.length ? "Download this session (transcript, turns, evidence, market context) as a ZIP"
            : "Nothing to export yet"}>
          Export Session
        </button>
      </div>
      {p.exportStatus && (
        <div className={`export-status${p.exportStatus.error ? " error" : ""}`} role="status">{p.exportStatus.text}</div>
      )}
      {state.mode === "guided" && state.lesson && <LessonBar lesson={state.lesson} onEnd={p.onEndLesson} busy={state.pending !== null} />}
      <div className="tutor-context">
        Tutor context: replay {cutoff ? ct(cutoff) : "—"} · {state.mode === "guided" ? "guided lesson" : "free chat"}
      </div>

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
              <RecentBars ev={p.evidence} />
              <SetupTable ev={p.evidence} />
              <div className="hint">From the Laboratory replay snapshot feeding the chart and the frozen setup analysis (as of the cutoff).</div>
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
