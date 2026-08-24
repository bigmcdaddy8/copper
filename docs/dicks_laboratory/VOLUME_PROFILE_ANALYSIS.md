# Phase 0Q — Human-Facing Volume Profile Analysis

`scripts/dicks_lab_analyze_volume_profile.py` is a read-only, offline CLI that
orchestrates the accepted analytical chain into one human-facing report:

```text
durable SQLite dataset -> read-only open -> trading-date selection
  -> session/custom anchor -> coverage inspection -> selected effective trades
  -> VWAP -> Volume at Price -> POC -> Value Area -> VAL/VAH -> report
```

It computes no new formulas. It orchestrates:

- **Anchor/coverage selection** (Phase 0N, `dicks_laboratory.sessions` /
  `dicks_laboratory.analysis`)
- **Volume-at-Price and POC** (Phase 0O, `dicks_laboratory.volume_profile`)
- **Value Area / VAL / VAH** (Phase 0P, `dicks_laboratory.value_area`)

The governing usability rule: **POC, VAH, and VAL are never shown without also
showing which retained trades and anchor produced them.**

## Usage

```bash
uv run python scripts/dicks_lab_analyze_volume_profile.py \
  apps/dicks_laboratory/data/<dataset>.sqlite3 \
  --anchor session-open
```

```bash
uv run python scripts/dicks_lab_analyze_volume_profile.py \
  apps/dicks_laboratory/data/<dataset>.sqlite3 \
  --anchor cash-open
```

```bash
uv run python scripts/dicks_lab_analyze_volume_profile.py \
  apps/dicks_laboratory/data/<dataset>.sqlite3 \
  --anchor 2026-08-23T23:20:00Z
```

Optional:

- `--trading-date YYYY-MM-DD` — required only when the dataset spans multiple
  trading dates.
- `--dataset-id <uuid>` — required only when the database holds multiple datasets.
- `--top-levels N` (1-100, default 10) — how many ranked volume levels to display.
  Presentation only; never changes POC or Value Area semantics.

The command is fully offline: it opens the SQLite database read-only, performs
no network I/O, and requires no Tastytrade credentials or `.env` file.

## Example outcomes (real 0L dataset, `es_20260823T231601Z_997555.sqlite3`)

**Session-open**: `DATASET_BEGINS_AFTER_ANCHOR`, 1,182 effective trades, 1,426.0
volume, VWAP `7693.867286115007012622720898`, POC `7695.00` (273.0 volume, 154
prints), VAL `7692.25`, VAH `7696.75`, 19 included levels — exit code 0.

**Cash-open**: `ANCHOR_AFTER_DATASET_END` (the cash-session anchor falls the day
after this capture window ends). No trades selected, no VWAP/POC/VAL/VAH
fabricated — exit code 1.

**Custom anchor `2026-08-23T23:20:00Z`**: `ANCHOR_COVERED`, anchor preserved
exactly, 939 selected trades (a genuine subset of the full 1,182), its own VWAP,
POC, and Value Area computed strictly over that subset.

## VWAP, POC, VAL, VAH are separate analytical concepts over one shared trade set

All four are computed from the same selected-trade population for a given
anchor:

- **VWAP** — exact volume-weighted average price.
- **POC** — the price level with the greatest traded volume
  (`DICKS_LAB_POC_TIE_POLICY`, Phase 0O).
- **VAL / VAH** — the low/high bound of the contiguous Value Area expansion
  around the POC (`DICKS_LAB_VALUE_AREA_POLICY`, Phase 0P).

They can disagree (e.g. VWAP need not equal POC) — that's expected; they answer
different questions about the same data.

## Source mode

The primary reported profile is always `EFFECTIVE_TAPE` (corrections/cancels
already reconstructed). A concise canonical NEW-only comparison is always
computed and reported as a single fact: whether it differs from the effective
tape. The two are never silently mixed into one profile.

## Policy provenance

- POC tie policy: `DICKS_LAB_POC_TIE_POLICY` / `V1_NEAREST_VOLUME_WEIGHTED_MEAN_THEN_LOWER_PRICE`
  (Phase 0O) — a Laboratory policy, not an exchange rule.
- Value Area policy: `DICKS_LAB_VALUE_AREA_POLICY` / `V1_SINGLE_ROW_GREATER_VOLUME_NEAREST_POC_TIE_ABOVE`
  (Phase 0P) — a Laboratory policy informed by, but not identical to, any single
  vendor's undisclosed algorithm. See `docs/dicks_laboratory/VALUE_AREA_MODEL.md`.
- Session/anchor rules follow the ordinary CME equity-index schedule only;
  holiday and early-close overrides are not modeled.

## Analytical limitations

- Reflects retained captured observations only — not necessarily a complete
  session profile. A dataset that begins after the requested anchor, or ends
  before session close, is labeled a "captured-data developing" profile, never
  a "complete session profile."
- Static, finite profile only — no developing (event-by-event) time series yet.
- No TPO/Market Profile (letters, initial balance, single prints, poor
  highs/lows, excess).
- No volume delta (bid/ask, buy/sell aggression).
- No charting; text report only.
- No persistence — VWAP/POC/VAL/VAH are recomputed on demand every run.
