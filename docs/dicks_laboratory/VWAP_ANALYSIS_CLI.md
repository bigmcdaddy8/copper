# Anchored VWAP Analysis CLI

`scripts/dicks_lab_analyze_vwap.py` is a read-only, offline instrument over durable
Laboratory SQLite datasets. It performs no network I/O and requires no Tastytrade
credentials. See [SESSION_AND_ANCHOR_MODEL.md](SESSION_AND_ANCHOR_MODEL.md) for the
underlying session/anchor semantics, which this tool does not redefine.

## Usage

```bash
uv run python scripts/dicks_lab_analyze_vwap.py <database.sqlite3> --anchor session-open
uv run python scripts/dicks_lab_analyze_vwap.py <database.sqlite3> --anchor cash-open
uv run python scripts/dicks_lab_analyze_vwap.py <database.sqlite3> --anchor 2026-08-24T14:15:00Z
```

Optional selectors:

- `--trading-date YYYY-MM-DD` — required only when the dataset spans multiple ordinary
  CME trading dates and the anchor is `session-open` or `cash-open`.
- `--dataset-id <uuid>` — required only when the database contains more than one
  Laboratory dataset.

A custom anchor must be an explicit, timezone-aware UTC timestamp (`Z` suffix or an
explicit offset). Naive or local timestamps are rejected rather than silently assumed
to be Chicago time.

## The key rule

**A requested anchor predating the dataset is never shifted to the first retained
trade.** If a dataset begins after the requested anchor, the report says so explicitly
and computes VWAP only from retained observations, labeled as a *developing* anchored
VWAP rather than a complete session VWAP. If the requested anchor is after the last
retained trade, no VWAP is produced at all.

## Exit codes

- `0` — a VWAP was calculated (developing or otherwise).
- `1` — a clean analytical no-result: no retained trades exist at or after the
  requested anchor (e.g. `cash-open` on a dataset that ends before Monday's open).
- `2` — a usage or dataset-validity error (bad path, bad anchor, ambiguous dataset or
  trading-date selection, unreadable database).

## Example: the 0L bounded live capture

Against `apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3` (a 15-minute
live `/ES` capture that starts about 1h16m after the CME session open):

```
$ uv run python scripts/dicks_lab_analyze_vwap.py \
    apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 --anchor session-open

Coverage:
  DATASET_BEGINS_AFTER_ANCHOR
  Dataset begins after requested anchor: YES
  Unobserved pre-capture interval: 1h 16m 3.749s
  ...
Canonical NEW-only:
  VWAP:   7693.867286115007012622720898
```

```
$ uv run python scripts/dicks_lab_analyze_vwap.py \
    apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3 --anchor cash-open

No retained trades exist at or after the requested anchor.
No VWAP was calculated.
```

(exits `1` — the capture ends Sunday night, long before Monday's 8:30 AM Chicago cash open.)

## Limitations

- Ordinary CME schedule only; holiday and early-close overrides are not modeled.
- Results describe retained observations only; they are not proof of the full market
  tape, and a "developing" label means the retained window does not span the full
  requested session.
- No volume profile, replay, charting, or AI interpretation. This tool computes and
  reports facts only.
