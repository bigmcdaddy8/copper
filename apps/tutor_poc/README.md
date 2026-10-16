# tutor_poc — AI Tutor UX POC (0AC-A1 chart + replay, 0AC-A2 Tutor interaction shell, A2P polish)

Canonical plan: [`docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md`](../../docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md).

A local browser app on robby: `/ES` 5-minute candles, Globex VWAP and ±1σ / ±2σ bands, a replay
cutoff you move with Previous / Next / +5m, and a Tutor pane driven by a deterministic fake provider.
No AI model is called and no credentials are needed (A2 tests interaction mechanics, not answer quality).

## Run

```bash
scripts/tutor_poc.sh            # builds the web app if needed, then serves
# open http://localhost:8765
```

The first run on a machine prepares the approved session once (about 30 minutes for 2026-09-30, ~4 GB RAM)
into `~/.cache/copper/tutor_poc/`. Later starts load that cache in a few seconds. To prepare it ahead of time:
`uv run tutor_poc prepare`.

If `uv run tutor_poc` is not found, install the workspace apps with `uv sync --all-packages` (a plain
`uv sync` at the repo root only syncs the root project and removes the other apps' packages).

Frontend development: `uv run tutor_poc serve` in one terminal, `cd apps/tutor_poc/web && npm run dev` in
another (Vite proxies `/api` to port 8765).

## Layout

| Path | What |
|---|---|
| `src/tutor_poc/dev_sessions.py` | Approved development dates; the 2026-10-12..2026-11-06 campaign is refused |
| `src/tutor_poc/timeline.py` | Prepares the as-of chart timeline with the Laboratory pipeline; local cache |
| `src/tutor_poc/snapshot.py` | Replay stepping (clamped) and the `TUTOR_CHART_SNAPSHOT_V1` payload |
| `src/tutor_poc/api.py` | FastAPI: `/api/sessions`, `/api/sessions/{date}/replay`, `/api/sessions/{date}/snapshot`, `/api/sessions/{date}/tutor/turn`, `/api/sessions/{date}/tutor/evidence` |
| `src/tutor_poc/tutor.py` | A2: stage transitions, snapshot evidence, `FakeTutorProvider` (the seam A3 replaces) |
| `src/tutor_poc/cli.py` | Typer CLI: `prepare`, `serve` |
| `web/` | React + TypeScript + Vite; chart: TradingView lightweight-charts 5.1.0 |

## Market truth stays in the Laboratory

The browser never computes bars, VWAP or bands. For every 5-minute cutoff T on the session grid
(17:05 CT the prior evening through 16:00 CT), `timeline.py` runs the accepted pipeline:
`prepare_replay` → `ReplayCutoff.at(T)` → `as_of_evidence` (the effective tape known at T) →
`drysdale.run_pass` / `_bars` (VWAP_BANDS_GLOBEX_V1, BARS_5M_V1), resuming the pass under the 0AB-B
`DrysdaleCache.usable` rule. Each position holds only the complete bars the Laboratory knew at T, so
late prints, corrections and cancels behave exactly as in the Laboratory. The snapshot endpoint
returns one position: future bars are never sent to the browser.

## Settings

```text
presentation (browser only; never changes values or requests)
  candles:  up / down color
  overlays: per group (vwap, sigma1, sigma2): visible, color, lineWidth, lineStyle
  regions:  level1 (-1σ → +1σ), level2 (±1σ → ±2σ): visible, color, opacity (default: line color, 30%)

study-semantic (sent to the server; computed there)
  vwap_anchor = GLOBEX   (locked in A1; the server rejects anything else)
```

Overlays arrive as named series (`id`, `label`, `group`, `points`); the chart renders whatever series
the server sends, so a later reference or indicator is an additional series, not a chart rewrite.
Tradable-price labels follow the Laboratory's `/ES` tick grid (`volume_profile.ES_PRICE_GRID`,
`CME_ES_TICK_GRID_V1`), sent in the snapshot as `price_grid` (`symbol`, `tick_size` 0.25, `price_precision` 2).
The price axis and the crosshair label show the nearest valid tick (an exact half tick rounds up:
7780.125 → 7780.25); the crosshair itself still moves freely. This is formatting only: candle values and
the analytical VWAP / σ levels are sent and plotted unrounded, and the legend and evidence panel keep
showing them to two decimals.

Region fills and the replay-cutoff marker are lightweight-charts series primitives (`web/src/primitives.ts`)
that only pair points the server already sent; the regions never overlap, so opacities do not stack.

## Tutor interaction shell (A2)

```text
POST /api/sessions/{date}/tutor/turn       {action, replay_cutoff_utc, stage, turn, text?}
     -> {turn_id, turn, role: "tutor", action, text, stage, trading_date, replay_cutoff_utc, provider}
GET  /api/sessions/{date}/tutor/evidence?cutoff=...
```

`action` is `question` (opening / New question), `message` (the Human's text, required non-empty), `hint`
or `explain`. The request body is closed (unknown fields are refused); the date is the same approved,
enabled session the chart uses, and the cutoff must be one of its replay positions, so the Tutor API is
no route to another dataset or the sealed campaign.

The provider is fake; the market facts are not. `FakeTutorProvider` returns scripted text (same inputs,
same text; it never evaluates the Human's answer). Any value it or the evidence panel shows is read from
`build_snapshot` at the request's cutoff, the same snapshot that feeds the chart.

Stages reuse the Laboratory vocabulary (`tutor_evidence.LessonStage`) and its monotonic order:

```text
question  -> QUESTION      (starts a new lesson at the current replay position)
message   -> unchanged
hint      -> HINT          (a later stage is kept: ANSWER stays ANSWER)
explain   -> ANSWER
POST_REVEAL is not used: in TUTOR_REVEAL_V1 it releases hidden future evidence, which A2 never has.
```

Every message keeps the trading date, replay cutoff and stage it was produced at. The reply echoes the
request's cutoff and turn; the browser accepts a reply only for the pending turn and the same cutoff, so
a reply that arrives after the replay moved stays labeled with its original time. Moving the replay
changes the Tutor context line but keeps the conversation (a divider marks the change).

Show Evidence opens a compact panel for the current replay position: the latest completed bar's
open / high / low / close and its VWAP, ±1σ, ±2σ, with the cutoff and bar time. No candidate or setup
labels. Chart highlighting is A5.

The conversation lives in the page only: a reload starts a new one. Replies are plain HTTP (no streaming).

Each message also keeps its kind (`question`, `reply`, `hint`, `explain`, `human`, from the action that
produced it), separate from the lesson stage. Hint and Explain replies are labeled `Hint:` / `Explain:`
with a colored edge, so they stay identifiable when scrolling back.

The divider between the chart and the Tutor pane can be dragged (double-click resets). The accepted
width `clamp(240px, 26%, 400px)` is the Tutor minimum; the chart keeps at least 480 px. Resizing is
browser-only (the chart autosizes; no request is made) and the width is remembered in `localStorage`.

## Future (0AC-A5, not implemented): Tutor chart annotations

The Human wants Tutor actions (Hint, Explain, Show Evidence) to be able to place temporary annotations
on the chart: an arrow at a candle, a circle / highlight around a candle or region, a marker on VWAP / ±σ,
an emphasized area. Intended shape:

```text
Tutor action -> structured annotation intent -> frontend chart rendering -> temporary annotation
             -> cleared or superseded when the replay advances
```

The model must never emit drawing code. It returns a constrained, structured annotation request that refers
to deterministic evidence (identifiers, bar times, prices from the authorized snapshot), and the frontend
renders it. The schema is to be designed in A5.

## Branding and chart attribution (A2P2)

The header shows the company logo (`docs/company_logo.png`, imported by the web build and cropped to the
lettering with CSS; the file itself is unchanged). The chart's built-in TradingView logo link is turned off
with the library's own option `layout.attributionLogo: false` (`web/src/Chart.tsx`).

Lightweight Charts is Apache-2.0; its README requires the attribution notice from its `NOTICE` file and a
link to https://www.tradingview.com/ on a page available to users. The npm package does not ship `NOTICE`,
so the text is taken verbatim from `NOTICE` in tradingview/lightweight-charts at tag `v5.1.0` (the installed
version) and shown in the status bar footer (`web/src/Branding.tsx`):

```text
Charts: TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc. https://www.tradingview.com/
```

(The URL is a link; "(с)" is reproduced as published, with a Cyrillic "с".) Re-check `NOTICE` when the
chart library is upgraded.

## Development dates

Only already-inspected dates are approved: 2026-09-29, 2026-09-30, 2026-10-01, 2026-10-02. A1/A2 enable
2026-09-30. Each dataset is checked against its recorded sha256 when it is prepared.

## Tests

```bash
uv run pytest apps/tutor_poc/tests -q          # backend (synthetic Laboratory fixture, no corpus file)
cd apps/tutor_poc/web && npm test              # frontend logic + Tutor view render (vitest)
```
