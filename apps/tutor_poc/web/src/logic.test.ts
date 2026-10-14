import { describe, expect, it } from "vitest";
import { parseSnapshot, type Snapshot } from "./api";
import { controlState } from "./replay";
import { DEFAULT_SETTINGS, overlayRenderModel, setOverlay } from "./settings";

const T0 = Date.parse("2026-09-30T14:00:00Z") / 1000; // 09:00 CT

function snap(extra: Partial<Snapshot> = {}, bars = 3): Snapshot {
  const candles = Array.from({ length: bars }, (_, i) => {
    const time = T0 - (bars - i) * 300;
    return { time, end_time: time + 300, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 };
  });
  const line = (id: string, group: string, v: number) => ({
    id, label: id, group, kind: "line" as const,
    points: candles.map((c) => ({ time: c.time, value: v })),
  });
  return {
    schema: "TUTOR_CHART_SNAPSHOT_V1",
    instrument: "/ES",
    trading_date: "2026-09-30",
    replay: {
      cutoff_utc: "2026-09-30T14:00:00+00:00", market_time_cutoff_utc: "", knowledge_time_cutoff_utc: "",
      index: 10, count: 276, at_start: false, at_end: false,
    },
    study: { vwap_anchor: "GLOBEX", band_policy: "VWAP_BANDS_GLOBEX_V1", anchor_utc: "", bar_interval: "5m" },
    candles,
    series: [line("vwap", "vwap", 100), line("upper_1sd", "sigma1", 102), line("lower_1sd", "sigma1", 98)],
    source: { dataset_id: "x", database_sha256: "y" },
    ...extra,
  };
}

describe("parseSnapshot", () => {
  it("accepts a server snapshot unchanged when nothing is past the cutoff", () => {
    const s = snap();
    expect(parseSnapshot(s).candles).toEqual(s.candles);
  });

  it("never renders candles or overlay points past the server-stated cutoff", () => {
    const s = snap();
    const future = { time: T0, end_time: T0 + 300, open: 9, high: 9, low: 9, close: 9, volume: 1 };
    s.candles.push(future);
    s.series[0].points.push({ time: T0, value: 999 });
    const p = parseSnapshot(s);
    expect(p.candles.some((c) => c.time === T0)).toBe(false);
    expect(p.series[0].points.some((x) => x.time === T0)).toBe(false);
  });

  it("rejects an unknown schema", () => {
    expect(() => parseSnapshot({ schema: "OTHER" })).toThrow();
  });
});

describe("overlay render model", () => {
  it("styles every server series by its group, without touching values", () => {
    const s = snap();
    const m = overlayRenderModel(s, DEFAULT_SETTINGS.presentation);
    expect(m.map((o) => o.id)).toEqual(["vwap", "upper_1sd", "lower_1sd"]);
    expect(m[1].style).toEqual(DEFAULT_SETTINGS.presentation.overlays.sigma1);
    expect(m[0].points).toBe(s.series[0].points);
  });

  it("applies visibility and color changes to the whole group only", () => {
    const changed = setOverlay(DEFAULT_SETTINGS, "sigma1", { visible: false, color: "#ffffff" });
    const m = overlayRenderModel(snap(), changed.presentation);
    expect(m.filter((o) => !o.style.visible).map((o) => o.id)).toEqual(["upper_1sd", "lower_1sd"]);
    expect(m[0].style.visible).toBe(true);
    expect(m[1].points).toEqual(overlayRenderModel(snap(), DEFAULT_SETTINGS.presentation)[1].points);
    expect(DEFAULT_SETTINGS.presentation.overlays.sigma1.visible).toBe(true); // immutable update
  });

  it("renders a future additional series with a neutral default (additive overlays)", () => {
    const s = snap();
    s.series.push({ id: "ib_high", label: "IB high", group: "ib", kind: "line", points: [] });
    const m = overlayRenderModel(s, DEFAULT_SETTINGS.presentation);
    expect(m[3].id).toBe("ib_high");
    expect(m[3].style.visible).toBe(true);
  });

  it("keeps the study anchor locked to GLOBEX", () => {
    expect(DEFAULT_SETTINGS.study).toEqual({ vwap_anchor: "GLOBEX", locked: true });
  });
});

describe("replay controls", () => {
  it("enables all steps at an ordinary position", () => {
    expect(controlState(snap(), false)).toEqual({ previous: true, next: true, plus5m: true });
  });

  it("disables Previous at the first position and Next/+5m at the last", () => {
    const first = snap({ replay: { ...snap().replay, at_start: true } });
    const last = snap({ replay: { ...snap().replay, at_end: true } });
    expect(controlState(first, false)).toEqual({ previous: false, next: true, plus5m: true });
    expect(controlState(last, false)).toEqual({ previous: true, next: false, plus5m: false });
  });

  it("disables everything while loading or before the first snapshot", () => {
    expect(controlState(snap(), true)).toEqual({ previous: false, next: false, plus5m: false });
    expect(controlState(null, false)).toEqual({ previous: false, next: false, plus5m: false });
  });
});
