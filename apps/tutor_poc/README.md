# tutor_poc — AI Tutor UX POC (0AC-A1: chart + replay shell)

Canonical plan: [`docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md`](../../docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md).

A local browser app on robby: `/ES` 5-minute candles, Globex VWAP and ±1σ / ±2σ bands, a replay
cutoff you move with Previous / Next / +5m, and a placeholder Tutor pane. No AI in this phase.

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
| `src/tutor_poc/api.py` | FastAPI: `/api/sessions`, `/api/sessions/{date}/replay`, `/api/sessions/{date}/snapshot` |
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
Region fills and the replay-cutoff marker are lightweight-charts series primitives (`web/src/primitives.ts`)
that only pair points the server already sent; the regions never overlap, so opacities do not stack.

## Development dates

Only already-inspected dates are approved: 2026-09-29, 2026-09-30, 2026-10-01, 2026-10-02. A1 enables
2026-09-30. Each dataset is checked against its recorded sha256 when it is prepared.

## Tests

```bash
uv run pytest apps/tutor_poc/tests -q          # backend (synthetic Laboratory fixture, no corpus file)
cd apps/tutor_poc/web && npm test              # frontend pure logic (vitest)
```
