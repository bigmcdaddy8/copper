// Replay control state. Positions and clamping are decided by the server; this only reflects them.

import type { ReplayAction, Snapshot } from "./api";

export interface ControlState {
  previous: boolean;
  next: boolean;
  plus5m: boolean;
}

export function controlState(snapshot: Snapshot | null, loading: boolean): ControlState {
  if (!snapshot || loading) return { previous: false, next: false, plus5m: false };
  const { at_start, at_end } = snapshot.replay;
  return { previous: !at_start, next: !at_end, plus5m: !at_end };
}

export const ACTIONS: { action: ReplayAction; label: string; key: keyof ControlState }[] = [
  { action: "previous", label: "◀ Previous", key: "previous" },
  { action: "next", label: "Next ▶", key: "next" },
  { action: "plus5m", label: "+5m", key: "plus5m" },
];

const CT_TIME = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Chicago",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});
const CT_DAY = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Chicago",
  weekday: "short",
  month: "short",
  day: "numeric",
});

export function formatCt(seconds: number): string {
  return CT_TIME.format(new Date(seconds * 1000));
}

export function formatCtDay(seconds: number): string {
  return CT_DAY.format(new Date(seconds * 1000));
}
