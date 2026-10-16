import { describe, expect, it } from "vitest";
import { parseSnapshot, type Snapshot } from "./api";
import { quantizeToTick, tickPriceFormatter, type PriceGrid } from "./instrument";
import { CHART_MIN_PX, clampTutorWidth, minTutorWidth, tutorFlexBasis, tutorWidthAtPointer } from "./layout";

const ES: PriceGrid = { symbol: "/ES", tick_size: 0.25, price_precision: 2, policy: "CME_ES_TICK_GRID_V1" };

describe("/ES tick-size price labels", () => {
  const fmt = tickPriceFormatter(ES);

  it.each([
    [7780.0, "7780.00"],
    [7780.12, "7780.00"],
    [7780.13, "7780.25"],
    [7780.37, "7780.25"],
    [7780.38, "7780.50"],
    [7780.62, "7780.50"],
    [7780.63, "7780.75"],
    [7780.87, "7780.75"],
    [7780.88, "7781.00"],
    [7780.75, "7780.75"],
  ])("%d is labeled %s", (price, label) => {
    expect(fmt(price)).toBe(label);
  });

  it("an exact half tick rounds up; just below rounds down", () => {
    expect(fmt(7780.125)).toBe("7780.25");
    expect(fmt(7780.1249)).toBe("7780.00");
    expect(fmt(7780.375)).toBe("7780.50");
    expect(fmt(7780.3749)).toBe("7780.25");
  });

  it("every label ends in .00 / .25 / .50 / .75", () => {
    for (let p = 7700; p < 7702; p += 0.01) expect(fmt(p)).toMatch(/\.(00|25|50|75)$/);
  });

  it("quantization is a pure label function", () => {
    expect(quantizeToTick(7750.567052383102, 0.25)).toBe(7750.5);
  });

  it("parsing a snapshot leaves bar and analytical values unrounded", () => {
    const raw = {
      schema: "TUTOR_CHART_SNAPSHOT_V1", instrument: "/ES", price_grid: ES, trading_date: "2026-09-30",
      replay: { cutoff_utc: "2026-09-30T14:00:00+00:00", market_time_cutoff_utc: "", knowledge_time_cutoff_utc: "",
        index: 1, count: 2, at_start: false, at_end: false },
      study: { vwap_anchor: "GLOBEX", band_policy: "", anchor_utc: "", bar_interval: "5m" },
      candles: [{ time: 1790776500, end_time: 1790776800, open: 7761, high: 7767.75, low: 7758, close: 7767.25, volume: 1 }],
      series: [{ id: "vwap", label: "VWAP", group: "vwap", kind: "line", points: [{ time: 1790776500, value: 7750.567052383102 }] }],
      source: { dataset_id: "x", database_sha256: "y" },
    } as Snapshot;
    const s = parseSnapshot(structuredClone(raw));
    expect(s.series[0].points[0].value).toBe(7750.567052383102);
    expect(s.candles).toEqual(raw.candles);
    expect(s.price_grid).toEqual(ES);
  });

  it("a snapshot without a price grid is refused", () => {
    expect(() => parseSnapshot({ schema: "TUTOR_CHART_SNAPSHOT_V1", candles: [], series: [],
      replay: { cutoff_utc: "2026-09-30T14:00:00+00:00" } })).toThrow(/price grid/);
  });
});

describe("resizable Tutor pane", () => {
  it("default is the accepted width clamp(240px, 26%, 400px)", () => {
    expect(clampTutorWidth(null, 1600)).toBe(400);
    expect(clampTutorWidth(null, 1200)).toBe(312);
    expect(clampTutorWidth(null, 800)).toBe(240);
    expect(minTutorWidth(1600)).toBe(400);
  });

  it("widening the Tutor shrinks the chart by the same amount", () => {
    const w = clampTutorWidth(700, 1600);
    expect(w).toBe(700);
    expect(1600 - w).toBe(900);
  });

  it("cannot go narrower than the accepted width", () => {
    expect(clampTutorWidth(100, 1600)).toBe(400);
    expect(clampTutorWidth(300, 1600)).toBe(400);
  });

  it("leaves the chart its minimum width", () => {
    expect(clampTutorWidth(5000, 1600)).toBe(1600 - CHART_MIN_PX);
    expect(1600 - clampTutorWidth(5000, 1600)).toBe(CHART_MIN_PX);
  });

  it("on a very small window the Tutor minimum wins", () => {
    expect(clampTutorWidth(5000, 600)).toBe(240);
  });

  it("pointer position maps to width from the right edge", () => {
    expect(tutorWidthAtPointer(1000, 1600)).toBe(600);
  });

  it("CSS basis re-applies the same limits on window resize", () => {
    expect(tutorFlexBasis(700)).toBe("clamp(clamp(240px, 26%, 400px), 700px, calc(100% - 480px))");
  });
});
