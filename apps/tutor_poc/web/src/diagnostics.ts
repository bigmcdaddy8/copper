// Real-model diagnostics (0AC-A3): types and formatting only. Every number is the server's (provider-reported
// usage, server-measured latency, cost from the server's versioned pricing); nothing is estimated here.

export interface TurnUsage {
  input_tokens: number | null; // uncached input
  output_tokens: number | null;
  cached_input_tokens: number | null;
  cache_write_input_tokens: number | null;
  total_input_tokens: number | null;
}

export interface SessionTotals {
  turns: number;
  model_calls: number;
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  cache_write_input_tokens: number;
  total_input_tokens: number;
  cost_usd: string;
  unpriced_calls: number;
}

export interface TurnDiagnostics {
  provider: string;
  model: string | null;
  served_model: string | null;
  effort: string | null;
  prompt_version: string | null;
  pricing_version: string | null;
  status: string;
  attempts: number;
  repair_attempts: number;
  usage: TurnUsage | null;
  evidence_bytes: number | null;
  latency_ms: { evidence?: number; model?: number; validation?: number; total?: number };
  turn_cost_usd: string | null;
  fallback_used: boolean;
  session: SessionTotals;
}

export interface ProviderConfig {
  mode: "fake" | "real";
  provider: string;
  model: string | null;
  effort: string | null;
  prompt_version: string | null;
  pricing_version: string | null;
}

/** A diagnostics row kept per Tutor turn (accepted or not), with the turn's context. */
export interface TurnRecord {
  turn: number;
  action: string;
  replay_cutoff_utc: string;
  diagnostics: TurnDiagnostics;
}

const NA = "n/a";

export function formatTokens(n: number | null | undefined): string {
  return n === null || n === undefined ? NA : n.toLocaleString("en-US");
}

export function formatSeconds(ms: number | null | undefined): string {
  return ms === null || ms === undefined ? NA : `${(ms / 1000).toFixed(1)} s`;
}

export function formatKb(bytes: number | null | undefined): string {
  return bytes === null || bytes === undefined ? NA : `${(bytes / 1024).toFixed(1)} KB`;
}

/** Dollars with four decimals (sub-cent turns stay readable); null means the turn could not be priced. */
export function formatUsd(usd: string | null | undefined): string {
  if (usd === null || usd === undefined) return "unpriced";
  return `$${Number(usd).toFixed(4)}`;
}

/** The one-line summary under the Tutor actions. */
export function summaryLine(config: ProviderConfig | null, last: TurnDiagnostics | null): string {
  if (!config || config.mode === "fake") return "Provider: fake · cost $0";
  if (!last) return `AI: ${config.model} · no turns yet`;
  const u = last.usage;
  return [
    `AI ${formatSeconds(last.latency_ms.model)}`,
    `in ${formatTokens(u?.total_input_tokens)}`,
    `out ${formatTokens(u?.output_tokens)}`,
    `turn ${formatUsd(last.turn_cost_usd)}`,
    `session ${formatUsd(last.session.cost_usd)}`,
  ].join(" · ");
}
