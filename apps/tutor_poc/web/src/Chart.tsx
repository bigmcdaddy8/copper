import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type MouseEventParams,
  type Time,
  type UTCTimestamp,
} from "lightweight-charts";
import { cutoffSeconds, type Snapshot } from "./api";
import { overlayRenderModel, type LineStyleName, type PresentationSettings } from "./settings";
import { formatCt, formatCtDay } from "./replay";
import { RegionFill, ReplayCutoff } from "./primitives";
import { regionBands } from "./regions";
import { tickPriceFormatter } from "./instrument";

const LINE_STYLE: Record<LineStyleName, LineStyle> = {
  solid: LineStyle.Solid,
  dashed: LineStyle.Dashed,
  dotted: LineStyle.Dotted,
};

const asTime = (t: number) => t as UTCTimestamp;
const fmt = (v: number | undefined) => (v === undefined ? "—" : v.toFixed(2));

interface Props {
  snapshot: Snapshot;
  presentation: PresentationSettings;
}

interface Legend {
  time: number;
  ohlc?: { open: number; high: number; low: number; close: number };
  values: { label: string; color: string; value?: number }[];
}

export function Chart({ snapshot, presentation }: Props) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const overlaysRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const regionsRef = useRef(new RegionFill());
  const cutoffRef = useRef(new ReplayCutoff());
  const fittedFor = useRef<string | null>(null);
  const gridFor = useRef<string | null>(null);
  const [legend, setLegend] = useState<Legend | null>(null);

  // Create the chart once.
  useEffect(() => {
    const chart = createChart(host.current!, {
      autoSize: true,
      layout: { background: { color: "#131722" }, textColor: "#c7cbd4", fontSize: 12 },
      grid: { vertLines: { color: "#1f2430" }, horzLines: { color: "#1f2430" } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: "#2a2f3a" },
      timeScale: {
        borderColor: "#2a2f3a",
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 8,
        tickMarkFormatter: (t: Time) => formatCt(t as number),
      },
      localization: { timeFormatter: (t: Time) => `${formatCtDay(t as number)} ${formatCt(t as number)} CT` },
    });
    chartRef.current = chart;
    candlesRef.current = chart.addSeries(CandlestickSeries, {
      borderVisible: false,
      priceLineVisible: false,
    });
    candlesRef.current.attachPrimitive(regionsRef.current);
    candlesRef.current.attachPrimitive(cutoffRef.current);
    return () => {
      chart.remove();
      chartRef.current = null;
      candlesRef.current = null;
      overlaysRef.current.clear();
    };
  }, []);

  // Data: replace series contents with the server snapshot (only what the server sent).
  useEffect(() => {
    const chart = chartRef.current!;
    // Tradable-price labels (axis, crosshair) on the instrument's tick grid. Formatting only: the
    // candle and analytical values below are set exactly as served.
    const grid = snapshot.price_grid;
    const gridKey = `${grid.symbol}:${grid.tick_size}:${grid.price_precision}`;
    if (gridFor.current !== gridKey) {
      candlesRef.current!.applyOptions({
        priceFormat: { type: "price", precision: grid.price_precision, minMove: grid.tick_size },
      });
      chart.applyOptions({ localization: { priceFormatter: tickPriceFormatter(grid) } });
      gridFor.current = gridKey;
    }
    candlesRef.current!.setData(
      snapshot.candles.map((c) => ({ time: asTime(c.time), open: c.open, high: c.high, low: c.low, close: c.close })),
    );
    const model = snapshot.series;
    const seen = new Set<string>();
    for (const o of model) {
      seen.add(o.id);
      let s = overlaysRef.current.get(o.id);
      if (!s) {
        s = chart.addSeries(LineSeries, { priceLineVisible: false, lastValueVisible: false, title: "" });
        overlaysRef.current.set(o.id, s);
      }
      s.setData(o.points.map((p) => ({ time: asTime(p.time), value: p.value })));
    }
    for (const [id, s] of overlaysRef.current) {
      if (!seen.has(id)) {
        chart.removeSeries(s);
        overlaysRef.current.delete(id);
      }
    }
    const last = snapshot.candles[snapshot.candles.length - 1];
    cutoffRef.current.set(last ? last.time : null, `replay ${formatCt(cutoffSeconds(snapshot))}`);
    if (fittedFor.current !== snapshot.trading_date) {
      chart.timeScale().fitContent();
      fittedFor.current = snapshot.trading_date;
    }
    // Styling is applied by the presentation effect below (it also runs on every snapshot).
  }, [snapshot]);

  // Presentation: colors / visibility / line styles. Never touches data.
  useEffect(() => {
    candlesRef.current!.applyOptions({
      upColor: presentation.candles.up,
      downColor: presentation.candles.down,
      wickUpColor: presentation.candles.up,
      wickDownColor: presentation.candles.down,
    });
    for (const o of overlayRenderModel(snapshot, presentation)) {
      overlaysRef.current.get(o.id)?.applyOptions({
        visible: o.style.visible,
        color: o.style.color,
        lineWidth: o.style.lineWidth,
        lineStyle: LINE_STYLE[o.style.lineStyle],
      });
    }
    regionsRef.current.set(regionBands(snapshot, presentation));
  }, [presentation, snapshot]);

  // Legend: values under the crosshair, or the last bar.
  useEffect(() => {
    const chart = chartRef.current!;
    const model = overlayRenderModel(snapshot, presentation).filter((o) => o.style.visible);
    const last = snapshot.candles[snapshot.candles.length - 1];
    const at = (time: number): Legend => {
      const c = snapshot.candles.find((x) => x.time === time);
      return {
        time,
        ohlc: c,
        values: model.map((o) => ({
          label: o.label,
          color: o.style.color,
          value: o.points.find((p) => p.time === time)?.value,
        })),
      };
    };
    setLegend(last ? at(last.time) : null);
    const onMove = (p: MouseEventParams) => {
      if (p.time === undefined) setLegend(last ? at(last.time) : null);
      else setLegend(at(p.time as number));
    };
    chart.subscribeCrosshairMove(onMove);
    return () => chart.unsubscribeCrosshairMove(onMove);
  }, [snapshot, presentation]);

  return (
    <div className="chart-wrap">
      <div className="chart-host" ref={host} />
      {legend && (
        <div className="legend">
          <span className="legend-time">
            {formatCtDay(legend.time)} {formatCt(legend.time)} CT
          </span>
          {legend.ohlc && (
            <span>
              O {fmt(legend.ohlc.open)} H {fmt(legend.ohlc.high)} L {fmt(legend.ohlc.low)} C {fmt(legend.ohlc.close)}
            </span>
          )}
          {legend.values.map((v) => (
            <span key={v.label} style={{ color: v.color }}>
              {v.label} {fmt(v.value)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
