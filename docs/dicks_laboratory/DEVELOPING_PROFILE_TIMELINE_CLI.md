# Phase 0S — Human-Facing Developing Profile Timeline

`scripts/dicks_lab_analyze_developing_profile.py` is a read-only, offline CLI
that renders the accepted 0R `DevelopingProfileSeries` as a compact human
timeline. It computes nothing new: every table row is a direct view of one
`DevelopingProfileSnapshot` produced by `build_developing_profile_series`.

## Usage

```bash
uv run python scripts/dicks_lab_analyze_developing_profile.py \
  apps/dicks_laboratory/data/<dataset>.sqlite3 \
  --anchor session-open \
  --interval 5m
```

- `--anchor`: `session-open`, `cash-open`, or an explicit aware UTC timestamp
  (e.g. `2026-08-23T23:20:00Z`).
- `--interval`: `1m`, `5m` (default), or `15m` — the only checkpoint intervals
  0R supports. Any other value is rejected with a clear usage error, never
  silently coerced.
- `--source`: `effective` (default) or `canonical`.
- `--trading-date` / `--dataset-id`: only needed to resolve genuine ambiguity
  (multiple trading dates or datasets in one database).

## Session-open example (real 0L dataset)

```bash
uv run python scripts/dicks_lab_analyze_developing_profile.py \
  apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 \
  --anchor session-open --interval 5m
```

```text
Time       New     Cum      Volume        VWAP       POC       VAL       VAH
18:20      243     243       280.0   7691.4152   7691.00   7690.75   7691.75
18:25      189     432       488.0   7691.6829   7692.00   7691.25   7692.25
18:30      446     878      1071.0   7693.2157   7695.00   7692.00   7695.00
18:35*     304    1182      1426.0   7693.8673   7695.00   7692.25   7696.75
* terminal analytical cutoff; last retained trade was 18:31:01.281 CT
```

Terminal exact VWAP: `7693.867286115007012622720898` — exactly matches the
accepted static 0Q analysis for the same dataset and anchor.

## Custom-anchor example

```bash
uv run python scripts/dicks_lab_analyze_developing_profile.py \
  apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 \
  --anchor 2026-08-23T23:20:00Z --interval 5m
```

Produces a shorter 3-row series (`18:25`, `18:30`, `18:35*`), terminal trade
count `939`, terminal exact VWAP `7694.466404886561954624781850` — exactly
matching the accepted static 0Q custom-anchor result.

## Cash-open no-result example

```bash
uv run python scripts/dicks_lab_analyze_developing_profile.py \
  apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 \
  --anchor cash-open --interval 5m
```

The real capture ends before the US cash-session anchor
(`ANCHOR_AFTER_DATASET_END`). No table is printed — no zero-valued rows, no
fabricated VWAP/POC/VAL/VAH — and the process exits with code `1`.

## 1-minute and 15-minute intervals

Both are fully supported and produce more/fewer intermediate checkpoints
(16 and 2 rows respectively for the real session-open dataset), but the
**terminal row is identical** across `1m`, `5m`, and `15m` — the checkpoint
interval only changes which intermediate wall-clock moments are shown, never
the final retained analytical state.

## Terminal marker

A `*` after a time (e.g. `18:35*`) marks the terminal snapshot, with a
footnote naming the actual last retained trade timestamp. The terminal
cutoff is the next aligned wall-clock boundary after the last retained trade
— it does **not** imply capture continued through that boundary.

## Cumulative, not rolling

Every row is cumulative from the requested anchor through that row's cutoff.
A `5m` row is never "the last five minutes." The report states this
explicitly beneath the table.

## Retrospective effective-tape caveat

For the default `effective` source, the report states once (header and
footer) that the timeline is retrospectively reconstructed from the final
accepted `NEW`/`CORRECTION`/`CANCEL` lifecycle state — it is not a model of
what the feed had told us by each historical instant. See
`docs/dicks_laboratory/DEVELOPING_PROFILE_SERIES.md` for the full 0R design
rationale. The `canonical` source has no such caveat (it is built directly
from immutable `NEW` observations) and the CLI omits the caveat text for it.

## Coverage shown before the timeline

`DATASET_BEGINS_AFTER_ANCHOR`, first/last retained trade (UTC and America/
Chicago), the unobserved pre-capture interval, and whether the dataset ends
before session close are all printed **before** the table, together with an
explicit statement that the unobserved interval must not be read as zero
market activity.

## No-new-trade rows

A row with `New = 0` is still printed — it is never omitted, relabeled
"quiet," or treated as proof of no market activity.

## Analytical limitations

- Retained observations only; absence of new rows does not prove absence of
  market trades.
- Ordinary CME schedule only; holiday/early-close overrides not modeled.
- No rolling/moving windows — every row is cumulative from the anchor.
- The effective timeline is a retrospective reconstruction, not point-in-time
  feed knowledge.
- No trading interpretation, no charting, no CSV/JSON export, no persistence
  — presentation only, over the exact 0R analytical result.
