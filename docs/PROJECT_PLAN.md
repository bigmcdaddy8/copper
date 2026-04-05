# Plan: trade_hunter — Story-Based Development Roadmap

## Context

The `trade_hunter` CLI app generates ranked BULL-ish and BEAR-ish option-selling candidates from three
manually downloaded files (TastyTrade, SeekingAlpha x2) plus the Tradier API. The business rules are
fully specified in `docs/PROJECT_INTENT.md`. The repo scaffold exists (`apps/trade_hunter/`) but contains
only a "hello world" CLI. This plan lays out the phased story roadmap to implement the full pipeline.

**Configuration decisions:**
- Tradier API key: `TRADIER_API_KEY` environment variable (optionally from `.env` via python-dotenv)
- Filter thresholds: CLI options with defaults matching PROJECT_INTENT.md values
- Test strategy: synthetic fixtures (inline DataFrames + mocked HTTP) — no real files or API calls

---

## Proposed Module Structure

```
apps/trade_hunter/src/trade_hunter/
├── __init__.py
├── __main__.py
├── cli.py                  # Typer app + `run` command (thin layer)
├── config.py               # RunConfig dataclass populated from env + CLI args
├── models.py               # Domain dataclasses (Candidate, ActiveTrade, etc.)
├── loaders/
│   ├── __init__.py
│   ├── tastytrade.py       # TastyTrade CSV → DataFrame
│   ├── seekingalpha.py     # SeekingAlpha Excel → DataFrame
│   └── journal.py          # journal.xlsx / daJournal → symbol set
├── pipeline/
│   ├── __init__.py
│   ├── normalize.py        # Sector normalization + bucket mapping tables
│   ├── filters.py          # Hard filters (OI, bid, spread, monthly cycle)
│   └── scoring.py          # Quality tables + weighted Trade Score
├── tradier/
│   ├── __init__.py
│   ├── client.py           # httpx client with rate-limit header handling
│   └── selector.py         # Expiration selection + put/call strike selection
└── output/
    ├── __init__.py
    ├── workbook.py         # openpyxl BULL-ish/BEAR-ish workbook writer
    └── run_log.py          # Per-run log file writer
```

---

## Dependencies to Add (apps/trade_hunter)

```
pandas>=2.2
openpyxl>=3.1      # Excel read (journal) + write (output workbook)
httpx>=0.27        # Tradier API client
python-dotenv>=1.0 # .env support for TRADIER_API_KEY
```

---

## Story Roadmap

### Phase 0 — Project Foundation

| Story | Title | Scope |
|---|---|---|
| Story-0000 | Environment Validation | Confirm uv, pytest, ruff all work; smoke test passes |

---

### Phase 1 — CLI Skeleton & Configuration

| Story | Title | Scope |
|---|---|---|
| Story-0010 | `run` Command Scaffold | Replace hello-world with `run` command; accept all input file paths as required args; accept filter thresholds as CLI options with PROJECT_INTENT defaults; load `TRADIER_API_KEY` from env (fail loudly if missing); print "dry run" summary; smoke + unit tests |

---

### Phase 2 — Data Ingestion Layer

| Story | Title | Scope |
|---|---|---|
| Story-0020 | TastyTrade Loader & Universal Data Set | Load TastyTrade CSV; validate required columns; apply sector normalization table; assign sector buckets; produce Universal Data Set DataFrame; warn + skip on unknown sectors; unit tests with synthetic DataFrame |
| Story-0030 | SeekingAlpha Loaders | Load BULL-ish and BEAR-ish Excel files; validate required columns; parse grade columns (`A+`…`F`) as strings; unit tests with synthetic DataFrame |
| Story-0040 | Active Trades Loader | Load `journal.xlsx` worksheet `daJournal`; extract and deduplicate Symbol set; warn if symbol missing from Universal Data Set; unit tests |
| Story-0050 | Candidate Filtering & Universe Join | Remove open-trade tickers; remove tickers not in Universal Data Set (log warnings); join remaining candidates to Universal Data Set; unit tests covering each exclusion case |

---

### Phase 3 — Tradier API Integration

| Story | Title | Scope |
|---|---|---|
| Story-0060 | Tradier API Client | `httpx`-based client; auth header injection; respect rate-limit response headers; retry/throttle logic; mock-based unit tests (no real API calls) |
| Story-0070 | Expiration & Option Selection | Monthly cycle detection logic; nearest DTE 30–60 selection; put selection (delta ≤ −0.21, closest to −0.21) for BULL; call selection (delta ≥ 0.21, closest to 0.21) for BEAR; log + skip if no qualifying option; unit tests with synthetic option chain data |
| Story-0080 | Tradier Enrichment Pass | Iterate candidates; call client for each ticker; apply expiration + option selection; collect all required Tradier fields into enriched DataFrame; log API failures; unit tests with mocked responses |

---

### Phase 4 — Hard Filters & Scoring Engine

| Story | Title | Scope |
|---|---|---|
| Story-0090 | Hard Filters | Apply OI ≥ 8, bid ≥ 0.55, spread% ≤ 0.08, monthly cycle filters; log each failure with reason; thresholds read from `RunConfig` (CLI options); unit tests covering pass/fail cases for each filter |
| Story-0100 | Core Quality Metrics | IVR, IVP, Open Interest, Spread%, BPR quality table lookups; formulas match PROJECT_INTENT exactly; unit tests with boundary values for each table |
| Story-0110 | Diversity & SeekingAlpha Metrics | Cyclical Diversity, Sector Diversity (using deduplicated active ticker set); Quant Rating (with BEAR inversion); Growth (Growth bucket only, BEAR inversion); Momentum (BEAR inversion); Earnings Date (TastyTrade → SeekingAlpha → +70-day fallback); Bid quality; unit tests |
| Story-0120 | Trade Score Calculator | Weighted average formula; active-weight rule (Growth excluded when not applicable); output clamped to 0.00–5.00; unit tests with known inputs → expected score |

---

### Phase 5 — Output

| Story | Title | Scope |
|---|---|---|
| Story-0130 | Excel Workbook Output | Write `uploads/trade_signals.xlsx` with BULL-ish and BEAR-ish worksheets; all 23 columns with correct formats per PROJECT_INTENT; sorted descending by Trade Score; unit tests verifying sheet names, column headers, sort order |
| Story-0140 | Per-Run Log File | Write timestamped run log capturing all warning/skip/summary events accumulated during the pipeline; unit tests verifying log entries appear for each warning type |

---

### Phase 6 — Integration & Polish

| Story | Title | Scope |
|---|---|---|
| Story-0150 | End-to-End Integration Test | Wire the full pipeline with synthetic fixture files and mocked Tradier responses; assert output workbook structure and that at least one scored candidate appears; this is the primary regression guard |
| Story-0160 | README & Config Docs | Document `trade_hunter run` usage, required env vars, all CLI options, expected input file formats, and output location |

---

## Critical Files

| File | Role |
|---|---|
| `apps/trade_hunter/pyproject.toml` | Add pandas, openpyxl, httpx, python-dotenv |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Replace hello-world with `run` command (Story-0010) |
| `apps/trade_hunter/src/trade_hunter/config.py` | RunConfig dataclass (created Story-0010) |
| `apps/trade_hunter/src/trade_hunter/pipeline/normalize.py` | Sector + bucket lookup tables (Story-0020) |
| `apps/trade_hunter/src/trade_hunter/pipeline/scoring.py` | Quality tables + weighted average (Stories 0100–0120) |
| `apps/trade_hunter/src/trade_hunter/tradier/client.py` | API client (Story-0060) |
| `docs/STORY_BOARD.md` | Updated with all new story rows as each story is written |

---

## Verification Approach

Each story is verified via:
1. `uv run pytest` — all tests pass (existing + new)
2. `uv run ruff check .` — no lint errors
3. Smoke test: `uv run python -m trade_hunter --help` exits 0

Phase 6 (Story-0150) provides the end-to-end regression gate. Manual validation by the Vibe Engineer
using real data files + a live Tradier sandbox key is the final acceptance step before Story-0150 is
marked Completed.
