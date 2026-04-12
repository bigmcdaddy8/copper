# tradier_sniffer

A CLI POC that validates the Tradier sandbox API for automated trading. Uses a polling loop, SQLite state, and demo sub-commands to prove each MVP scenario end-to-end.

---

## Prerequisites

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)
- A Tradier sandbox account ([sandbox.tradier.com](https://sandbox.tradier.com))

---

## Setup

```bash
# From the repo root
uv sync --all-groups --all-packages

# Create your credentials file
cp apps/tradier_sniffer/.env.example apps/tradier_sniffer/.env
# Edit .env and fill in your sandbox API key and account ID
```

### Environment variables (`.env`)

| Variable | Description |
|---|---|
| `TRADIER_SANDBOX_API_KEY` | Bearer token from your Tradier sandbox app |
| `TRADIER_SANDBOX_ACCOUNT_ID` | Sandbox account number (e.g. `VA12345678`) |

---

## Commands

### Account discovery

```bash
tradier_sniffer discover
```

Calls the sandbox account endpoints and prints a structured summary of available balance fields, history, and user profile. Use this to verify credentials and check for API data gaps.

---

### Polling loop

```bash
tradier_sniffer poll [--interval SECONDS]
```

Runs startup reconciliation (detects missed fills/cancels since last run), then enters a polling loop. Default interval: 10 s. Stop with Ctrl-C.

---

### Status

```bash
tradier_sniffer status
```

Prints a Rich table of all open trades and the 20 most recent event log entries from the local DB.

---

### Reset

```bash
tradier_sniffer reset --confirm
```

Clears all rows from the local DB (trades, orders, events, poll state). The `--confirm` flag is required. The `.db` file itself is not deleted.

---

## Demo Scenarios

All demo commands place orders and return immediately. Run `tradier_sniffer poll` in a separate terminal to track fills.

### Scenario 1 — SPX 0DTE SIC Entry

```bash
tradier_sniffer demo scenario1
```

Fetches the 0DTE SPX option chain, finds the nearest 20-delta short strikes, builds a 4-leg Short Iron Condor with $10 wings, calculates the Day Limit credit, and places the order.

**Requires:** market hours (9:30 AM – 4:00 PM ET) for option greeks.

---

### Scenario 1.5 — Reprice and Re-enter

```bash
tradier_sniffer demo scenario1_5 [--wait SECONDS] [--tick FLOAT]
```

Places the SIC entry, waits `--wait` seconds (default 30), cancels if still open, and re-places at `credit − tick` (default $0.05 reduction). Exits after the new order is placed.

---

### Scenario 2 — Multi-leg Grouping Verification

```bash
tradier_sniffer demo scenario2
```

Read-only. Queries the local DB and prints all open trades with their linked order IDs. Use after a fill is detected by the poll loop to confirm the 4-leg SIC grouped under a single Trade #.

---

### Scenario 3 — TP Offline

```bash
tradier_sniffer demo scenario3 [--tp-pct FLOAT]
```

Places the SIC entry + a GTC BTC order at `--tp-pct` of the entry credit (default 50%). Exit the poll loop (Ctrl-C), wait for the TP to trigger in the sandbox, then restart — `reconcile()` on startup detects the closure.

---

### Scenario 4 — Adjustment

```bash
tradier_sniffer demo scenario4
```

Places the SIC entry, polls until it fills (up to 60 s), then places a 2-leg adjustment rolling the short put spread 10 points lower. The adjustment order is linked to the same Trade # as the entry.

---

### Edge Cases

```bash
# Print all four observation checklists (no API calls)
tradier_sniffer demo edge_cases

# Run a specific test
tradier_sniffer demo edge_cases --run nickel_pricing
tradier_sniffer demo edge_cases --run expiry_timing
tradier_sniffer demo edge_cases --run after_hours_gtc
tradier_sniffer demo edge_cases --run after_hours_quotes
```

| Test | When to run |
|---|---|
| `nickel_pricing` | During market hours |
| `expiry_timing` | After 4:00 PM ET on a day with an open 0DTE position |
| `after_hours_gtc` | After 4:05 PM ET with an open position |
| `after_hours_quotes` | After 4:05 PM ET |

---

## Demo Workflow

```
# Terminal 1 — polling loop
tradier_sniffer poll

# Terminal 2 — place and observe
tradier_sniffer demo scenario1      # place SIC entry
tradier_sniffer status              # check after fill detected
tradier_sniffer demo scenario3      # place SIC + GTC TP, then Ctrl-C Terminal 1
# ...wait for sandbox TP trigger...
tradier_sniffer poll                # restart — reconcile detects the closure
tradier_sniffer status              # confirm trade closed
```

---

## Cron Setup

For automated daily observations:

```bash
cd apps/tradier_sniffer
bash scripts/cron_setup.sh
```

This prints the recommended `crontab -e` entries and warns if your system timezone is not US Eastern Time.

---

## Architecture

| File | Purpose |
|---|---|
| `cli.py` | Typer entry point; all sub-commands |
| `config.py` | `SnifferConfig` dataclass |
| `models.py` | All dataclasses and enums |
| `db.py` | SQLite schema, CRUD, sequence counter |
| `engine.py` | Polling loop, event detection, `_raw_to_order` |
| `assign.py` | Trade # assignment, `infer_trade_type` |
| `reconcile.py` | Startup reconciliation |
| `options.py` | Pure option-chain helpers (delta strike, SIC legs, OCC symbols) |
| `tradier_client.py` | `httpx`-based Tradier sandbox API client |
| `demo/scenario1.py` | SIC entry |
| `demo/scenario1_5.py` | Reprice and re-enter |
| `demo/scenario2.py` | Multi-leg grouping verification |
| `demo/scenario3.py` | Entry + GTC TP |
| `demo/scenario4.py` | Entry + adjustment |
| `demo/edge_cases.py` | Edge case runners and checklists |
| `scripts/` | Cron shell scripts for daily automation |

---

## Development

```bash
# Run all tests
uv run pytest apps/tradier_sniffer

# Lint
uv run ruff check apps/tradier_sniffer
```
