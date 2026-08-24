# Phase 0T — Developing Profile Visualization

`scripts/dicks_lab_plot_developing_profile.py` renders a static, headless PNG
of the accepted 0R `DevelopingProfileSeries` (already shown textually by the
0S CLI). It introduces no new analytics: every plotted value is drawn
directly from `DevelopingProfileSnapshot` fields via a pure conversion
adapter, `dicks_laboratory.developing_profile_plot_data`.

## Plotting dependency

No plotting library existed in the repo (the only prior charting dependency,
`plotext`, is a terminal-only ASCII renderer used by `holodeck` and cannot
produce a real PNG). `matplotlib>=3.9` was added to
`apps/dicks_laboratory/pyproject.toml` as the smallest reasonable dependency
for deterministic, headless static image output. The script forces the
non-interactive `Agg` backend (`matplotlib.use("Agg")`) before any pyplot
import, so it never requires a display server.

After adding the dependency, sync the workspace with:

```bash
uv sync --all-packages
```

(plain `uv sync` at the repo root only resolves the root project's own empty
dependency list and can appear to drop workspace-member packages from the
shared venv; `--all-packages` is the correct command for this uv workspace.)

## Usage

```bash
uv run python scripts/dicks_lab_plot_developing_profile.py \
  apps/dicks_laboratory/data/<dataset>.sqlite3 \
  --anchor session-open \
  --interval 5m \
  --output <path>.png
```

- `--anchor`: same contract as 0S — `session-open`, `cash-open`, or an
  explicit aware UTC timestamp.
- `--interval`: `1m`, `5m` (default), or `15m`. Any other value is rejected.
- `--source`: `effective` (default) or `canonical`.
- `--output`: optional. If omitted, a descriptive filename
  (`developing_profile_<trading-date>_<interval>.png`) is written next to the
  input database.
- `--overwrite`: required to replace an existing output file; otherwise the
  command refuses to overwrite silently (exit code 2).

## Session-open example (real 0L dataset)

```bash
uv run python scripts/dicks_lab_plot_developing_profile.py \
  apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 \
  --anchor session-open --interval 5m --overwrite
```

Produces a 1500×900 PNG with four checkpoints (`18:20`, `18:25`, `18:30`,
`18:35*`), matching the accepted 0S table exactly — terminal VWAP
`7693.867286115007012622720898`, POC `7695.00`, VAL `7692.25`, VAH
`7696.75`.

## Custom-anchor example

```bash
uv run python scripts/dicks_lab_plot_developing_profile.py \
  apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 \
  --anchor 2026-08-23T23:20:00Z --interval 5m --overwrite
```

Three checkpoints (`18:25`, `18:30`, `18:35*`); terminal state (939 trades,
VWAP `7694.466404886561954624781850`) matches the accepted 0S custom-anchor
result exactly.

## Cash-open no-result

```bash
uv run python scripts/dicks_lab_plot_developing_profile.py \
  apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 \
  --anchor cash-open --interval 5m
```

The real capture ends before the cash-session anchor
(`ANCHOR_AFTER_DATASET_END`). No image is created — the command prints a
clear no-result message and exits with code `1`.

## 1-minute and 15-minute intervals

Both are fully supported. For the real session-open dataset, `1m` produces
16 checkpoints and `15m` produces 2; the **terminal point is identical**
across `1m`, `5m`, and `15m` (proven at both the plot-data-adapter and CLI
level) — the interval only changes which intermediate wall-clock moments are
plotted, never the final analytical state.

## The four plotted measures

- **VWAP** — a normal connected line with round markers. The line segment
  between two checkpoints is a visual aid only; it does not represent a
  newly computed or interpolated intermediate market observation.
- **POC** — the highest-volume price level in the cumulative profile at each
  checkpoint (`DICKS_LAB_POC_TIE_POLICY`, 0O), drawn as a post-step line
  (constant from one checkpoint until the next) since it is a discrete
  derived quantity, not a continuously interpolated one.
- **VAL / VAH** — the accepted 0P Value Area low/high bounds, also drawn as
  post-step lines for the same reason.

No trading interpretation (bullish/bearish/trend/etc.) is added anywhere.

## Terminal cutoff marker

The terminal checkpoint is marked with an open diamond and a vertical dashed
guide line, distinct from the ordinary round/square checkpoint markers. The
figure footer explicitly states the terminal cutoff is a checkpoint boundary
and names the actual last retained trade timestamp — the marker never
implies retained observations exist through the cutoff itself.

## Coverage and retrospective-tape notes

The figure footer always shows the anchor and coverage classification, and
(when applicable) the unobserved pre-capture interval and the
`DATASET_BEGINS_AFTER_ANCHOR` first-retained-trade timestamp. For the
default `effective` source, the footer states once that the effective
timeline is retrospectively reconstructed from the final accepted
`NEW`/`CORRECTION`/`CANCEL` lifecycle state — never a model of what the feed
had told us by each historical instant. The `canonical` source omits this
caveat (it needs no such qualification). "Cumulative from requested anchor;
not a rolling window" is likewise stated once, not per checkpoint.

## Decimal / rendering boundary

`developing_profile.py` and `developing_profile_plot_data.py` never import
matplotlib and never convert to `float`. All `Decimal` values (VWAP, POC,
VAL, VAH, volume) are carried through exactly by the plot-data adapter;
`float()` conversion happens only inside `_render_figure` in the plotting
script, immediately before handing coordinates to matplotlib.

## Y-axis

The price axis autoscales to the plotted range with matplotlib's default
padding — it is **not** forced to a zero baseline. For ES prices around
7690–7700, a zero baseline would make the actual developing movement
unreadable; this is a price-detail plot, not a zero-based magnitude chart.

## Output location and overwrite

Generated PNGs are runtime artifacts. The default output path sits next to
the input database (e.g. `apps/dicks_laboratory/data/`, already excluded by
`.gitignore`'s `data/` rule) and is never written into a tracked source
directory. An existing output file is never silently overwritten; `savefig`
writes to a `.tmp` sibling file first and atomically renames it into place,
so a failed render never leaves a corrupt or truncated PNG at the requested
path.

## Guarantees

- **Headless**: the script forces the `Agg` backend before importing
  `pyplot`; no display server is required (proven with `DISPLAY` unset in
  tests).
- **Read-only**: uses the same `LaboratoryStore(read_only=True)` path as
  every other Dick's Laboratory analysis command; database mtime is
  unchanged after plotting (tested).
- **Offline**: no network access, no Tastytrade credentials, no `.env`
  dependency (tested with those environment variables scrubbed).

## Human smoke-test checklist

1. The four series (VWAP, POC, VAL, VAH) are visually distinguishable.
2. The time axis reads naturally in America/Chicago time.
3. The VWAP trajectory matches the values in the 0S table.
4. POC step changes match the 0S table exactly.
5. VAL/VAH bounds are legible at each checkpoint.
6. The terminal checkpoint is visibly and unambiguously marked.
7. Coverage / retrospective-tape notes are visible in the footer without
   overwhelming the chart.
8. The plot is readable at normal desktop viewing size (1500×900 default).

## Analytical limitations

- Retained observations only — a plotted line never implies a complete
  session's tape.
- No candles/OHLC, no volume histogram, no TPO/Market Profile, no delta —
  deferred to a later phase if ever pursued.
- No interactive UI — static PNG artifact only.
- No trading interpretation of any kind.
