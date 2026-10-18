// 0AC-A3E Export Session in the browser: the control, the download call, empty sessions (no network).
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TutorView } from "./TutorPane";
import { INITIAL_TUTOR, canExport, exportSession, filenameFrom, tutorReducer, type TutorState } from "./tutor";

const D = "2026-09-30";
const AT = "2026-09-30T14:05:00+00:00";
const NAME = "tutor_session_2026-09-30_0900-0905.zip";

function answered(): TutorState {
  const s = tutorReducer(INITIAL_TUTOR, { type: "request", action: "question", trading_date: D, replay_cutoff_utc: AT });
  return tutorReducer(s, { type: "reply", response: { turn_id: "t0", turn: 0, role: "tutor", action: "question",
    text: "Look at the latest candle.", stage: "QUESTION", trading_date: D, replay_cutoff_utc: AT, provider: "fake",
    status: "FAKE", diagnostics: { provider: "fake", model: null, served_model: null, effort: null, prompt_version: null,
      pricing_version: null, status: "FAKE", attempts: 0, repair_attempts: 0, usage: null, evidence_bytes: null,
      latency_ms: {}, turn_cost_usd: "0.000000", fallback_used: false, session: { turns: 1, model_calls: 0,
        input_tokens: 0, output_tokens: 0, cached_input_tokens: 0, cache_write_input_tokens: 0, total_input_tokens: 0,
        cost_usd: "0.000000", unpriced_calls: 0 } } } });
}

function view(state: TutorState, extra: Partial<Parameters<typeof TutorView>[0]> = {}) {
  const noop = () => {};
  return renderToStaticMarkup(
    <TutorView state={state} cutoff={AT} draft="" evidenceOpen={false} evidence={null} evidenceError={null}
      onDraft={noop} onSend={noop} onAction={noop} onToggleEvidence={noop} onExport={noop} {...extra} />,
  );
}

const exportButton = (html: string) => html.match(/<button[^>]*class="link export"[^>]*>Export Session<\/button>/)?.[0] ?? "";

describe("Export Session control", () => {
  it("is in the Tutor header and disabled with a clear title while there is nothing to export", () => {
    const b = exportButton(view(INITIAL_TUTOR));
    expect(b).toContain('disabled=""');
    expect(b).toContain('title="Nothing to export yet"');
    expect(canExport(INITIAL_TUTOR)).toBe(false);
  });

  it("is enabled once a turn was answered, and disabled while a turn is pending", () => {
    const s = answered();
    expect(canExport(s)).toBe(true);
    expect(exportButton(view(s))).not.toContain("disabled");
    const pending = tutorReducer(s, { type: "request", action: "hint", trading_date: D, replay_cutoff_utc: AT });
    expect(exportButton(view(pending))).toContain('disabled=""');
  });

  it("shows the export outcome", () => {
    expect(view(answered(), { exportStatus: { busy: false, text: `Exported ${NAME}` } })).toContain(`Exported ${NAME}`);
    const err = view(answered(), { exportStatus: { busy: false, text: "Nothing to export yet: x", error: true } });
    expect(err).toContain('class="export-status error"');
  });
});

describe("exportSession", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("POSTs only to the export endpoint and returns the ZIP with the server's filename", async () => {
    const calls: { url: string; init: RequestInit }[] = [];
    vi.stubGlobal("fetch", async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return new Response(new Uint8Array([0x50, 0x4b, 3, 4]), { status: 200, headers: {
        "Content-Type": "application/zip", "Content-Disposition": `attachment; filename="${NAME}"` } });
    });
    const before = answered();
    const snapshot = JSON.stringify(before);
    const out = await exportSession(D, "page-1234abcd", AT);
    expect(out.filename).toBe(NAME);
    expect(out.blob.size).toBe(4);
    expect(calls.map((c) => c.url)).toEqual([`/api/sessions/${D}/tutor/export`]); // no Tutor turn, no replay call
    expect(calls[0].init.method).toBe("POST");
    expect(JSON.parse(String(calls[0].init.body))).toEqual({ session_id: "page-1234abcd", replay_cutoff_utc: AT });
    expect(JSON.stringify(before)).toBe(snapshot); // the conversation state is untouched
  });

  it("an empty session reports the server's message instead of saving a file", async () => {
    vi.stubGlobal("fetch", async () => new Response(JSON.stringify({ detail: "Nothing to export yet: this session has no Tutor turns." }),
      { status: 409, headers: { "Content-Type": "application/json" } }));
    await expect(exportSession(D, "page-1234abcd", AT)).rejects.toThrow("Nothing to export yet: this session has no Tutor turns.");
  });

  it("reads the filename from Content-Disposition", () => {
    expect(filenameFrom(`attachment; filename="${NAME}"`)).toBe(NAME);
    expect(filenameFrom(null)).toBeNull();
  });
});
