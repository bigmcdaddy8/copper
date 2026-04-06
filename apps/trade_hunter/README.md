# trade_hunter

`trade_hunter` generates ranked BULL-ish and BEAR-ish option-selling candidates. It reads
three manually downloaded input files plus live options data from the Tradier API, scores each
candidate using a weighted quality formula, and writes a sorted Excel workbook.

---

## Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) — workspace dependency manager
- A [Tradier](https://tradier.com/) account with a production or sandbox API key

---

## Installation

From the workspace root (`copper/`):

```bash
uv sync
```

---

## Configuration

### Required environment variable

| Variable | Description |
|---|---|
| `TRADIER_API_KEY` | Production Tradier API key |

### Optional environment variables

| Variable | Description | Default |
|---|---|---|
| `TRADIER_SANDBOX_API_KEY` | Sandbox API key — used when `--sandbox` flag is set or `TRADIER_ENV=sandbox` | — |
| `TRADIER_ENV` | Set to `sandbox` to use the Tradier sandbox environment | `production` |

### `.env` file

Credentials may be stored in a `.env` file at the workspace root. It is loaded automatically
at runtime via python-dotenv. Use `.env.example` (included in the repo) as a template:

```bash
cp .env.example .env
# Edit .env and fill in your API key(s)
```

> `.env` is git-ignored — never commit it.

---

## Input files

Three files are required on each run. Supply them explicitly via CLI options, or let
`trade_hunter` auto-discover the newest matching file in the configured directories.

### 1. TastyTrade CSV

Downloaded manually from TastyTrade into `downloads/`.

**Auto-discovery glob:** `tastytrade_watchlist_m8investments_Russell 1000_*.csv`  
When multiple matches exist the file with the highest lexicographic date suffix is used.

Required columns:

| Column | Use |
|---|---|
| `Symbol` | Ticker identifier |
| `Sector` | Raw sector name — normalized to standard sectors internally |
| `IV Idx` | Implied volatility index |
| `IV Rank` | IV rank (0–100 scale) |
| `IV %tile` | IV percentile (0–100 scale) |
| `Liquidity` | Star-encoded liquidity rating (★/☆ Unicode symbols) |
| `Earnings At` | Primary earnings date (optional — a fallback is used if absent or null) |

Optional columns passed through if present: `Name`, `Last`

### 2. SeekingAlpha BULL-ish Excel

Downloaded manually from a SeekingAlpha screen into `downloads/`.

**Auto-discovery glob:** `Copper_BULLish *.xlsx`

### 3. SeekingAlpha BEAR-ish Excel

**Auto-discovery glob:** `Copper_BEARish *.xlsx`

Both SeekingAlpha files require these columns:

| Column | Use |
|---|---|
| `Symbol` | Ticker identifier |
| `Quant Rating` | SeekingAlpha quant score (1.0–5.0) |
| `Growth` | Growth grade (A+…F) |
| `Momentum` | Momentum grade (A+…F) |

Optional column: `Upcoming Announce Date` (fallback earnings date if `Earnings At` is absent)

### 4. Active trades journal (`journal.xlsx`)

**Default location:** `worksheets/journal.xlsx`

Must contain a worksheet named `daJournal` with a `Symbol` column. Every row is treated as an
active trade; tickers present here are excluded from candidate scoring to avoid doubling up.
Duplicate symbols are deduplicated automatically.

---

## Default directory paths

The defaults are configured for Todd's trading data directory. Override with the CLI options
shown below.

| Option | Default path |
|---|---|
| `--downloads-dir` | `/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/downloads` |
| `--worksheets-dir` | `/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/worksheets` |
| `--output-dir` | *(required — no default)* |

---

## Usage

```bash
# Minimal — uses default download/worksheet dirs and auto-discovers input files
uv run trade_hunter run --output-dir /path/to/output

# All input files supplied explicitly
uv run trade_hunter run \
  --output-dir /path/to/output \
  --tastytrade-file /path/to/tastytrade.csv \
  --bull-file /path/to/bull.xlsx \
  --bear-file /path/to/bear.xlsx \
  --journal-file /path/to/journal.xlsx

# Use Tradier sandbox environment
uv run trade_hunter run --output-dir /path/to/output --sandbox

# Override hard-filter thresholds
uv run trade_hunter run \
  --output-dir /path/to/output \
  --min-open-interest 15 \
  --min-bid 0.75 \
  --max-spread-pct 0.10

# Full help
uv run trade_hunter run --help
```

### All CLI options

| Option | Type | Default | Description |
|---|---|---|---|
| `--output-dir` | `PATH` | *(required)* | Directory where output files are written |
| `--downloads-dir` | `PATH` | see above | Directory to search for auto-discovered input files |
| `--worksheets-dir` | `PATH` | see above | Directory containing `journal.xlsx` |
| `--tastytrade-file` | `PATH` | auto-discover | TastyTrade CSV — bypasses auto-discovery when set |
| `--bull-file` | `PATH` | auto-discover | SeekingAlpha BULL-ish Excel |
| `--bear-file` | `PATH` | auto-discover | SeekingAlpha BEAR-ish Excel |
| `--journal-file` | `PATH` | `worksheets-dir/journal.xlsx` | Active trades journal |
| `--min-open-interest` | `INT` | `8` | Minimum open interest hard filter |
| `--min-bid` | `FLOAT` | `0.55` | Minimum option bid hard filter |
| `--max-spread-pct` | `FLOAT` | `0.13` | Maximum spread % hard filter — `(ask−bid)/mid` |
| `--min-dte` | `INT` | `30` | Minimum days-to-expiration for expiration selection |
| `--max-dte` | `INT` | `60` | Maximum days-to-expiration for expiration selection |
| `--sandbox` | flag | off | Use Tradier sandbox environment and `TRADIER_SANDBOX_API_KEY` |

---

## Output

Both output files are written to `--output-dir`.

### `trade_signals.xlsx`

Two worksheets — `BULL-ish` and `BEAR-ish` — each sorted descending by Trade Score.

Each sheet contains 23 columns:

| Column | Format |
|---|---|
| Ticker | Text |
| Sector Bucket | Text |
| Sector | Text |
| Option Type | Text (`Put` / `Call`) |
| Expiration Date | Date `MM/DD/YYYY` |
| Earnings Date | Date `MM/DD/YYYY` |
| DTE | Integer |
| Price | `#.##` |
| Strike | `#` |
| Bid | `#.##` |
| Ask | `#.##` |
| Spread% | `#.#%` |
| Delta | `[-]0.##` |
| Open Interest | `#` |
| Trade Score | `#.##` (0.00–5.00) |
| Quant Rating | `#.##` |
| Liquidity | Text (`0 stars`–`4 stars`) |
| Growth | Text (grade A+…F) |
| Momentum | Text (grade A+…F) |
| IVx | `#.#%` |
| IVR | `#.##` |
| IVP | `#.#%` |
| BPR | Currency `$#` |

### `run_log_YYYYMMDD_HHMMSS.txt`

Plain-text per-run log. Includes:

- Timestamp header
- All warnings: tickers skipped (API error, no qualifying option, open trade exclusion, not in
  universe), unknown sectors, schema issues
- Summary counts: loaded, enriched, filtered, and scored candidates for each side

---

## Development

```bash
# Run all tests (from workspace root)
uv run pytest

# Lint
uv run ruff check .

# Format check
uv run ruff format --check .

# Auto-format
uv run ruff format .
```
