// Two small lightweight-charts series primitives, drawn on the chart canvas (presentation only):
//   RegionFill    fills between already-authorized server ±σ points (regions.ts)
//   ReplayCutoff  a thin line at the right edge of the last complete bar, with a time-axis label

import type {
  IChartApi,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesApi,
  ISeriesPrimitive,
  ISeriesPrimitiveAxisView,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { RegionBand } from "./regions";

abstract class Base implements ISeriesPrimitive<Time> {
  protected chart: IChartApi | null = null;
  protected series: ISeriesApi<SeriesType> | null = null;
  private requestUpdate: (() => void) | null = null;

  attached(p: SeriesAttachedParameter<Time>) {
    this.chart = p.chart as IChartApi;
    this.series = p.series;
    this.requestUpdate = p.requestUpdate;
  }

  detached() {
    this.chart = this.series = this.requestUpdate = null;
  }

  protected changed() {
    this.requestUpdate?.();
  }
}

export class RegionFill extends Base {
  private bands: RegionBand[] = [];

  set(bands: RegionBand[]) {
    this.bands = bands;
    this.changed();
  }

  paneViews(): IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = {
      draw: () => {},
      drawBackground: (target: CanvasRenderingTarget2D) => {
        const chart = this.chart;
        const series = this.series;
        if (!chart || !series) return;
        const ts = chart.timeScale();
        target.useMediaCoordinateSpace(({ context: ctx }) => {
          for (const band of this.bands) {
            const pts = band.points
              .map((p) => ({
                x: ts.timeToCoordinate(p.time as Time),
                lo: series.priceToCoordinate(p.lower),
                hi: series.priceToCoordinate(p.upper),
              }))
              .filter((p) => p.x !== null && p.lo !== null && p.hi !== null) as { x: number; lo: number; hi: number }[];
            if (pts.length < 2) continue;
            ctx.beginPath();
            pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.hi) : ctx.moveTo(p.x, p.hi)));
            for (let i = pts.length - 1; i >= 0; i--) ctx.lineTo(pts[i].x, pts[i].lo);
            ctx.closePath();
            ctx.fillStyle = band.fill;
            ctx.fill();
          }
        });
      },
    };
    return [{ zOrder: () => "bottom", renderer: () => renderer }];
  }
}

const CUTOFF_COLOR = "rgba(245, 166, 35, 0.45)";

export class ReplayCutoff extends Base {
  private lastBar: number | null = null; // start time of the last complete bar (UTC seconds)
  private label = "";

  set(lastBar: number | null, label: string) {
    this.lastBar = lastBar;
    this.label = label;
    this.changed();
  }

  /** The right edge of the last complete bar = the replay cutoff. */
  private x(): number | null {
    if (!this.chart || this.lastBar === null) return null;
    const ts = this.chart.timeScale();
    const center = ts.timeToCoordinate(this.lastBar as Time);
    return center === null ? null : center + ts.options().barSpacing / 2;
  }

  paneViews(): IPrimitivePaneView[] {
    const renderer: IPrimitivePaneRenderer = {
      draw: () => {},
      drawBackground: (target: CanvasRenderingTarget2D) => {
        const x = this.x();
        if (x === null) return;
        target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
          ctx.save();
          ctx.strokeStyle = CUTOFF_COLOR;
          ctx.lineWidth = 1;
          ctx.setLineDash([4, 4]);
          ctx.beginPath();
          ctx.moveTo(Math.round(x) + 0.5, 0);
          ctx.lineTo(Math.round(x) + 0.5, mediaSize.height);
          ctx.stroke();
          ctx.restore();
        });
      },
    };
    return [{ zOrder: () => "bottom", renderer: () => renderer }];
  }

  timeAxisViews(): ISeriesPrimitiveAxisView[] {
    if (this.x() === null) return [];
    return [
      {
        coordinate: () => this.x() ?? -1,
        text: () => this.label,
        textColor: () => "#131722",
        backColor: () => "#c8901f",
        visible: () => true,
        tickVisible: () => true,
      },
    ];
  }
}
