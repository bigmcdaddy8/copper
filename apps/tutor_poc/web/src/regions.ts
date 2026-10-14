// VWAP deviation region fills (presentation only). Geometry comes from the server's ±σ series:
// no band value is computed here; the fill only pairs points the server already sent.
//
//   level2  +1σ → +2σ
//   level1  −1σ → +1σ
//   level2  −2σ → −1σ
// The regions never overlap, so opacities do not stack.

import type { SeriesPoint, Snapshot } from "./api";
import type { PresentationSettings } from "./settings";

export const REGION_LEVELS: { level: string; label: string }[] = [
  { level: "level1", label: "Level 1 region (−1σ → +1σ)" },
  { level: "level2", label: "Level 2 regions (±1σ → ±2σ)" },
];

const GEOMETRY: { level: string; lower: string; upper: string }[] = [
  { level: "level1", lower: "lower_1sd", upper: "upper_1sd" },
  { level: "level2", lower: "upper_1sd", upper: "upper_2sd" },
  { level: "level2", lower: "lower_2sd", upper: "lower_1sd" },
];

export interface BandPoint {
  time: number;
  lower: number;
  upper: number;
}

export interface RegionBand {
  level: string;
  fill: string; // css rgba
  points: BandPoint[];
}

export function rgba(hex: string, opacityPct: number): string {
  const n = parseInt(hex.replace("#", ""), 16);
  const a = Math.min(100, Math.max(0, opacityPct)) / 100;
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
}

/** Visible region bands, pairing the server's boundary points by bar time (only times present in both). */
export function regionBands(snapshot: Snapshot, presentation: PresentationSettings): RegionBand[] {
  const byId = new Map<string, SeriesPoint[]>(snapshot.series.map((s) => [s.id, s.points]));
  const out: RegionBand[] = [];
  for (const g of GEOMETRY) {
    const style = presentation.regions[g.level];
    const lower = byId.get(g.lower);
    const upper = byId.get(g.upper);
    if (!style?.visible || style.opacity <= 0 || !lower || !upper) continue;
    const up = new Map(upper.map((p) => [p.time, p.value]));
    const points = lower
      .filter((p) => up.has(p.time))
      .map((p) => ({ time: p.time, lower: p.value, upper: up.get(p.time)! }));
    out.push({ level: g.level, fill: rgba(style.color, style.opacity), points });
  }
  return out;
}
