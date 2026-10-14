// Minimal settings architecture (AI_TUTOR_UX_POC_PLAN.md, "Minimal Settings Architecture").
//
// PRESENTATION settings change how evidence looks; they never change values or what is requested.
// STUDY-SEMANTIC settings change what the server computes; they are sent to the server and never
// calculated here. A guided lesson may lock them; in A1 the VWAP anchor is locked to GLOBEX.

import type { OverlaySeries, Snapshot } from "./api";

export type LineStyleName = "solid" | "dashed" | "dotted";

export interface OverlayPresentation {
  visible: boolean;
  color: string;
  lineWidth: 1 | 2 | 3;
  lineStyle: LineStyleName;
}

export interface RegionPresentation {
  visible: boolean;
  color: string;
  opacity: number; // 0..100 %
}

export interface PresentationSettings {
  candles: { up: string; down: string };
  overlays: Record<string, OverlayPresentation>; // keyed by overlay group
  regions: Record<string, RegionPresentation>; // keyed by region level (see regions.ts)
}

export interface StudySettings {
  vwap_anchor: "GLOBEX";
  locked: boolean; // A1: true (the Globex anchor is the source-aligned Drysdale semantic)
}

export interface ChartSettings {
  presentation: PresentationSettings;
  study: StudySettings;
}

export const OVERLAY_GROUPS: { group: string; label: string }[] = [
  { group: "vwap", label: "Globex VWAP" },
  { group: "sigma1", label: "±1σ" },
  { group: "sigma2", label: "±2σ" },
];

const SIGMA1_COLOR = "#4a90e2";
const SIGMA2_COLOR = "#9b7fd4";

export const DEFAULT_SETTINGS: ChartSettings = {
  presentation: {
    candles: { up: "#26a69a", down: "#ef5350" },
    overlays: {
      vwap: { visible: true, color: "#f5a623", lineWidth: 2, lineStyle: "solid" },
      sigma1: { visible: true, color: SIGMA1_COLOR, lineWidth: 1, lineStyle: "solid" },
      sigma2: { visible: true, color: SIGMA2_COLOR, lineWidth: 1, lineStyle: "dashed" },
    },
    // Fill colors default to the matching line colors at 30% opacity.
    regions: {
      level1: { visible: true, color: SIGMA1_COLOR, opacity: 30 },
      level2: { visible: true, color: SIGMA2_COLOR, opacity: 30 },
    },
  },
  study: { vwap_anchor: "GLOBEX", locked: true },
};

// Overlays without a presentation entry (a future reference series) still render, with a neutral default.
const FALLBACK: OverlayPresentation = { visible: true, color: "#9aa0a6", lineWidth: 1, lineStyle: "solid" };

export interface OverlayRender {
  id: string;
  label: string;
  style: OverlayPresentation;
  points: OverlaySeries["points"];
}

/** The chart's render model: one entry per server series, styled by presentation settings only. */
export function overlayRenderModel(snapshot: Snapshot, presentation: PresentationSettings): OverlayRender[] {
  return snapshot.series.map((s) => ({
    id: s.id,
    label: s.label,
    style: presentation.overlays[s.group] ?? FALLBACK,
    points: s.points,
  }));
}

export function setOverlay(
  settings: ChartSettings,
  group: string,
  change: Partial<OverlayPresentation>,
): ChartSettings {
  const current = settings.presentation.overlays[group] ?? FALLBACK;
  return {
    ...settings,
    presentation: {
      ...settings.presentation,
      overlays: { ...settings.presentation.overlays, [group]: { ...current, ...change } },
    },
  };
}

export function setRegion(settings: ChartSettings, level: string, change: Partial<RegionPresentation>): ChartSettings {
  const current = settings.presentation.regions[level];
  return {
    ...settings,
    presentation: {
      ...settings.presentation,
      regions: { ...settings.presentation.regions, [level]: { ...current, ...change } },
    },
  };
}
