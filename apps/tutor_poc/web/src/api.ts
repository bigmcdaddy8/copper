// Typed client for the local Tutor POC API. The server is the source of market truth: this module
// only parses what it is given, and drops anything later than the server-stated cutoff (a render
// guard, not the correctness boundary — the server never ships future bars).

export const BAR_SECONDS = 300;

export interface Candle {
  time: number; // bar start, UTC seconds
  end_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SeriesPoint {
  time: number;
  value: number;
}

export interface OverlaySeries {
  id: string;
  label: string;
  group: string; // presentation group (one setting for both ±1σ lines, etc.)
  kind: "line";
  points: SeriesPoint[];
}

export interface Snapshot {
  schema: "TUTOR_CHART_SNAPSHOT_V1";
  instrument: string;
  trading_date: string;
  replay: {
    cutoff_utc: string;
    market_time_cutoff_utc: string;
    knowledge_time_cutoff_utc: string;
    index: number;
    count: number;
    at_start: boolean;
    at_end: boolean;
  };
  study: { vwap_anchor: string; band_policy: string; anchor_utc: string; bar_interval: string };
  candles: Candle[];
  series: OverlaySeries[];
  source: { dataset_id: string; database_sha256: string };
}

export interface SessionList {
  instrument: string;
  sessions: { trading_date: string; enabled: boolean }[];
  default: string | null;
}

export type ReplayAction = "previous" | "next" | "plus5m";

export function cutoffSeconds(s: Snapshot): number {
  return Math.floor(Date.parse(s.replay.cutoff_utc) / 1000);
}

export function parseSnapshot(raw: unknown): Snapshot {
  const s = raw as Snapshot;
  if (!s || s.schema !== "TUTOR_CHART_SNAPSHOT_V1") throw new Error("unexpected snapshot schema");
  if (!Array.isArray(s.candles) || !Array.isArray(s.series)) throw new Error("malformed snapshot");
  if (Number.isNaN(Date.parse(s.replay?.cutoff_utc))) throw new Error("snapshot has no cutoff");
  const cutoff = cutoffSeconds(s);
  const known = (t: number) => t + BAR_SECONDS <= cutoff;
  return {
    ...s,
    candles: s.candles.filter((c) => c.end_time <= cutoff),
    series: s.series.map((x) => ({ ...x, points: x.points.filter((p) => known(p.time)) })),
  };
}

async function getJson(url: string): Promise<unknown> {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status}: ${await r.text()}`);
  return r.json();
}

export async function fetchSessions(): Promise<SessionList> {
  return (await getJson("/api/sessions")) as SessionList;
}

export async function fetchSnapshot(
  date: string,
  opts: { cutoff?: string; action?: ReplayAction; vwapAnchor: string },
): Promise<Snapshot> {
  const q = new URLSearchParams({ vwap_anchor: opts.vwapAnchor });
  if (opts.cutoff) q.set("cutoff", opts.cutoff);
  if (opts.action) q.set("action", opts.action);
  return parseSnapshot(await getJson(`/api/sessions/${date}/snapshot?${q}`));
}
