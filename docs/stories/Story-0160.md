# Story-0160 — README & Config Docs

**Status**: Completed  
**Phase**: 6 — Integration & Polish

---

## Goal

Write a complete, accurate `apps/trade_hunter/README.md` documenting everything a user needs
to configure and run `trade_hunter`: environment variables, input file formats, all CLI options,
and output. Update the root `README.md` with a brief `trade_hunter` overview section that links
to the app README.

No code changes are made in this story.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/README.md` | New — complete trade_hunter user guide |
| `README.md` | Update — add a `trade_hunter` section after the Project Structure section |

---

## `apps/trade_hunter/README.md` — required sections

### 1. Overview

One-paragraph description of what `trade_hunter` does: reads three input files plus the Tradier
API, scores BULL-ish and BEAR-ish option-selling candidates, and writes a ranked Excel workbook.

### 2. Prerequisites

- Python 3.13+
- `uv` (workspace dependency manager)
- A Tradier account with an API key (production or sandbox)

### 3. Installation

```bash
# From the workspace root
uv sync
```

### 4. Configuration

#### Required environment variable

| Variable | Description |
|---|---|
| `TRADIER_API_KEY` | Production Tradier API key |

#### Optional environment variables

| Variable | Description | Default |
|---|---|---|
| `TRADIER_SANDBOX_API_KEY` | Sandbox API key (used when `--sandbox` or `TRADIER_ENV=sandbox`) | — |
| `TRADIER_ENV` | Set to `sandbox` to use the sandbox environment | `production` |

Credentials may be placed in a `.env` file at the workspace root (loaded automatically via
python-dotenv). A `.env.example` template is provided.

### 5. Input files

Three input files are required on each run. Each can be supplied explicitly via CLI option or
auto-discovered by glob from the appropriate directory.

#### TastyTrade CSV

Downloaded manually from TastyTrade into `downloads/`.

Auto-discovery glob: `tastytrade_watchlist_m8investments_Russell 1000_*.csv`
(newest match selected when multiple files are present)

Required columns:

| Column | Use |
|---|---|
| `Symbol` | Ticker identifier |
| `Sector` | Raw sector name (normalized internally) |
| `IV Idx` | Implied volatility index |
| `IV Rank` | IV rank (0–100 scale) |
| `IV %tile` | IV percentile (0–100 scale) |
| `Liquidity` | Star-encoded liquidity rating (★–☆ symbols) |
| `Earnings At` | Primary earnings date (optional — fallback used if absent) |

Optional columns (passed through if present): `Name`, `Last`

#### SeekingAlpha BULL-ish Excel

Downloaded manually from a SeekingAlpha screen into `downloads/`.

Auto-discovery glob: `Copper_BULLish *.xlsx`

#### SeekingAlpha BEAR-ish Excel

Auto-discovery glob: `Copper_BEARish *.xlsx`

Both SeekingAlpha files require these columns:

| Column | Use |
|---|---|
| `Symbol` | Ticker identifier |
| `Quant Rating` | SeekingAlpha quant score (1.0–5.0) |
| `Growth` | Growth grade (A+…F) |
| `Momentum` | Momentum grade (A+…F) |

Optional column: `Upcoming Announce Date` (fallback earnings date)

#### Active trades journal (`journal.xlsx`)

Located at `worksheets/journal.xlsx` by default. Must contain a worksheet named `daJournal`
with a `Symbol` column. All rows are treated as active trades; tickers present here are
excluded from candidate scoring.

### 6. Default file paths

Configured for Todd's trading data directory. Override with CLI options as needed.

| Path | Default |
|---|---|
| `--downloads-dir` | `/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/downloads` |
| `--worksheets-dir` | `/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/worksheets` |
| `--output-dir` | *(required — no default)* |

### 7. Usage

```bash
# Minimal — uses default download/worksheet dirs, auto-discovers input files
uv run trade_hunter run --output-dir /path/to/output

# All input files explicit
uv run trade_hunter run \
  --output-dir /path/to/output \
  --tastytrade-file /path/to/tastytrade.csv \
  --bull-file /path/to/bull.xlsx \
  --bear-file /path/to/bear.xlsx \
  --journal-file /path/to/journal.xlsx

# Sandbox environment
uv run trade_hunter run --output-dir /path/to/output --sandbox
```

#### All CLI options

| Option | Type | Default | Description |
|---|---|---|---|
| `--output-dir` | PATH | *(required)* | Directory where output files are written |
| `--downloads-dir` | PATH | see above | Directory to search for downloaded input files |
| `--worksheets-dir` | PATH | see above | Directory containing `journal.xlsx` |
| `--tastytrade-file` | PATH | auto-discover | TastyTrade CSV (bypasses discovery if set) |
| `--bull-file` | PATH | auto-discover | SeekingAlpha BULL-ish Excel |
| `--bear-file` | PATH | auto-discover | SeekingAlpha BEAR-ish Excel |
| `--journal-file` | PATH | auto-discover | Active trades journal |
| `--min-open-interest` | INT | `8` | Minimum open interest hard filter |
| `--min-bid` | FLOAT | `0.55` | Minimum option bid hard filter |
| `--max-spread-pct` | FLOAT | `0.13` | Maximum spread % hard filter |
| `--min-dte` | INT | `30` | Minimum days-to-expiration |
| `--max-dte` | INT | `60` | Maximum days-to-expiration |
| `--sandbox` | FLAG | off | Use Tradier sandbox environment |

### 8. Output

All output is written to `--output-dir`.

#### `trade_signals.xlsx`

Two worksheets — `BULL-ish` and `BEAR-ish` — each sorted descending by Trade Score, with 23
columns:

`Ticker`, `Sector Bucket`, `Sector`, `Option Type`, `Expiration Date`, `Earnings Date`,
`DTE`, `Price`, `Strike`, `Bid`, `Ask`, `Spread%`, `Delta`, `Open Interest`, `Trade Score`,
`Quant Rating`, `Liquidity`, `Growth`, `Momentum`, `IVx`, `IVR`, `IVP`, `BPR`

#### `run_log_YYYYMMDD_HHMMSS.txt`

Per-run log capturing all warnings (tickers skipped, API errors, unknown sectors, etc.) and a
summary table of loaded/enriched/filtered/scored counts.

### 9. Development

```bash
# Run all tests
uv run pytest

# Lint and format check
uv run ruff check .
uv run ruff format --check .

# Auto-format
uv run ruff format .
```

---

## Root `README.md` update

Add a `## trade_hunter` section immediately after the `## Project Structure` section. Keep it
short (4–6 lines) and link to `apps/trade_hunter/README.md` for full documentation:

```markdown
## trade_hunter

`trade_hunter` generates ranked BULL-ish and BEAR-ish option-selling candidates from
TastyTrade and SeekingAlpha input files combined with live Tradier options data.
Output is a scored and sorted Excel workbook (`trade_signals.xlsx`).

See **[apps/trade_hunter/README.md](apps/trade_hunter/README.md)** for setup,
configuration, input file formats, and all CLI options.
```

---

## Acceptance Criteria

1. `apps/trade_hunter/README.md` exists and covers all nine sections listed above.
2. All CLI options in the README match `uv run trade_hunter run --help` exactly (names,
   types, defaults).
3. Both auto-discovery globs (`TASTYTRADE_GLOB`, `BULL_GLOB`, `BEAR_GLOB`) are documented.
4. The `.env.example` file is mentioned as the credential template.
5. Root `README.md` has a `trade_hunter` section linking to the app README.
6. `uv run pytest` still passes (no code changes, so this is a sanity check).

---

## Verification Steps

```bash
uv run pytest
# Manual review: uv run trade_hunter run --help matches table in README
```
