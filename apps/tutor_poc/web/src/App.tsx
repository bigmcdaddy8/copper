import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import { cutoffSeconds, fetchSessions, fetchSnapshot, type ReplayAction, type SessionList, type Snapshot } from "./api";
import { ChartAttribution, CompanyLogo } from "./Branding";
import { Chart } from "./Chart";
import { clampTutorWidth, loadTutorWidth, saveTutorWidth, tutorFlexBasis, tutorWidthAtPointer } from "./layout";
import { ACTIONS, controlState, formatCt, formatCtDay } from "./replay";
import { DEFAULT_SETTINGS, type ChartSettings } from "./settings";
import { SettingsPanel } from "./SettingsPanel";
import type { LessonView } from "./tutor";
import { TutorPane } from "./TutorPane";

export function App() {
  const [sessions, setSessions] = useState<SessionList | null>(null);
  const [date, setDate] = useState<string | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [settings, setSettings] = useState<ChartSettings>(DEFAULT_SETTINGS);
  const [showSettings, setShowSettings] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latencyMs, setLatencyMs] = useState<number | null>(null);
  const [tutorWidth, setTutorWidth] = useState<number | null>(loadTutorWidth); // null = accepted default
  const [lesson, setLesson] = useState<LessonView | null>(null); // the active guided lesson (A4)
  const panesRef = useRef<HTMLElement>(null);

  const load = useCallback(
    async (d: string, opts: { cutoff?: string; action?: ReplayAction } = {}) => {
      setLoading(true);
      setError(null);
      const t0 = performance.now();
      try {
        setSnapshot(await fetchSnapshot(d, { ...opts, vwapAnchor: settings.study.vwap_anchor }));
        setLatencyMs(Math.round(performance.now() - t0));
      } catch (e) {
        setError(String(e));
      } finally {
        setLoading(false);
      }
    },
    [settings.study.vwap_anchor],
  );

  useEffect(() => {
    fetchSessions()
      .then((s) => {
        setSessions(s);
        setDate(s.default);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (date) load(date);
  }, [date, load]);

  // Divider drag: presentation only; the chart autosizes, no data is reloaded.
  const onDividerMove = (e: PointerEvent<HTMLDivElement>) => {
    if (!e.currentTarget.hasPointerCapture(e.pointerId)) return;
    const r = panesRef.current!.getBoundingClientRect();
    setTutorWidth(clampTutorWidth(tutorWidthAtPointer(e.clientX, r.right), r.width));
  };
  const onDividerUp = (e: PointerEvent<HTMLDivElement>) => {
    e.currentTarget.releasePointerCapture(e.pointerId);
    document.body.classList.remove("resizing");
    saveTutorWidth(tutorWidth);
  };
  const resetWidth = () => {
    setTutorWidth(null);
    saveTutorWidth(null);
  };

  const controls = controlState(snapshot, loading);
  const cutoff = snapshot ? cutoffSeconds(snapshot) : null;

  return (
    <div className="app">
      <header className="topbar">
        <CompanyLogo />
        <span className="brand">Dick's Laboratory · Tutor POC</span>
        <span className="instrument">{sessions?.instrument ?? "/ES"}</span>
        <select value={date ?? ""} onChange={(e) => setDate(e.target.value)} aria-label="Development session">
          {sessions?.sessions.map((s) => (
            <option key={s.trading_date} value={s.trading_date} disabled={!s.enabled}>
              {s.trading_date}
              {s.enabled ? "" : " (not enabled in A1)"}
            </option>
          ))}
        </select>
        <span className="cutoff">
          Replay cutoff{" "}
          <strong>{cutoff !== null ? `${formatCtDay(cutoff)} ${formatCt(cutoff)} CT` : "—"}</strong>
        </span>
        <div className="controls">
          {ACTIONS.map((a) => (
            <button
              key={a.action}
              title={a.title}
              disabled={!controls[a.key]}
              onClick={() => date && snapshot && load(date, { cutoff: snapshot.replay.cutoff_utc, action: a.action })}
            >
              {a.label}
            </button>
          ))}
        </div>
        <button className="settings-toggle" onClick={() => setShowSettings((v) => !v)} aria-expanded={showSettings}>
          ⚙ Settings
        </button>
      </header>

      <main className="panes" ref={panesRef}>
        <section className="chart-pane">
          {snapshot ? <Chart snapshot={snapshot} presentation={settings.presentation} /> : <div className="empty">Loading…</div>}
          {showSettings && <SettingsPanel settings={settings} onChange={setSettings} />}
        </section>
        <div
          className="pane-divider"
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize Tutor pane"
          title="Drag to resize the Tutor pane · double-click to reset"
          onPointerDown={(e) => {
            e.currentTarget.setPointerCapture(e.pointerId);
            document.body.classList.add("resizing");
          }}
          onPointerMove={onDividerMove}
          onPointerUp={onDividerUp}
          onPointerCancel={onDividerUp}
          onDoubleClick={resetWidth}
        />
        <TutorPane
          date={date}
          cutoff={snapshot?.replay.cutoff_utc ?? null}
          style={tutorWidth === null ? undefined : { flexBasis: tutorFlexBasis(tutorWidth) }}
          onSeek={(c) => date && load(date, { cutoff: c })}
          onLessonChange={setLesson}
        />
      </main>

      <footer className="statusbar">
        <span>
          {snapshot ? `position ${snapshot.replay.index + 1}/${snapshot.replay.count}` : ""}
          {snapshot ? ` · ${snapshot.candles.length} complete 5m bars` : ""}
        </span>
        <span>
          VWAP anchor: {snapshot?.study.vwap_anchor ?? settings.study.vwap_anchor}{" "}
          {lesson ? "(locked by the guided lesson, server-computed)" : "(locked, server-computed)"}
        </span>
        <span>{latencyMs !== null ? `last load ${latencyMs} ms` : ""}</span>
        {loading && <span>loading…</span>}
        {error && <span className="error">{error}</span>}
        <ChartAttribution />
      </footer>
    </div>
  );
}
