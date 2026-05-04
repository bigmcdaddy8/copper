# K9 — Automated 0DTE Options Trade Entry

K9 is a CLI tool that executes 0DTE options trades (Iron Condors, Put Credit Spreads, Call Credit Spreads) against the SPX index via the Broker Interface Contract (BIC).

## Quick Start

> Fresh machine note: run `./setup.sh` once from the repo root before running `uv run ...` commands.

```bash
# Run a holodeck (simulated) trade entry
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_0900

# Validate broker/data readiness without placing orders
uv run K9 preflight --trade-spec spx_ic_20d_w5_tp34_0900

# Reconcile closures (TP fill / expiration) into captains_log
uv run K9 close --account TRDS

# Execute full selection/validation path without submitting orders
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_0900 --dry-run

# Run against the Tradier sandbox (requires .env with TRADIER_SANDBOX_TOKEN)
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_sandbox
```

## Trade Specs

Trade specs are YAML files in `apps/K9/trade_specs/`. JSON trade specs are not supported.

| Spec | Type | Environment | Description |
|---|---|---|---|
| `spx_ic_20d_w5_tp34_0900` | Iron Condor | holodeck | 20Δ shorts, $5 wings, 34% TP |
| `spx_pcs_20d_w5_tp50_0930` | Put Credit Spread | holodeck | 20Δ short put, $5 wing, 50% TP |
| `spx_ccs_20d_w5_tp50_0930` | Call Credit Spread | holodeck | 20Δ short call, $5 wing, 50% TP |
| `spx_ic_20d_w5_tp34_sandbox` | Iron Condor | sandbox | Same as above; Tradier sandbox (disabled by default) |
| `xsp_pcs_0dte_w2_none_0900_trds` | Put Credit Spread | sandbox | ~13Δ short put, $2 wing, no TP (expire flow) |

### Spec Fields

```yaml
schema_version: 2
enabled: true
environment: HD           # HD | TRDS | TRD (or holodeck/sandbox/production)
underlying: SPX
account_minimum: 5000
max_combo_bid_ask_width: 0.50
notes: "optional"

trade:
  option_strategy: SIC    # SIC | PCS | CCS

  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500

  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"

  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 5
    retry_price_decrement: 0.02
    entry_price: MIDPOINT
    min_credit_received: 0.30

  leg_selection:
    short_put:
      delta_preferred: -0.13
      delta_range:
        min: -0.25
        max: -0.15
    short_call:
      delta_range:
        min: 0.15
        max: 0.25
    long_put:
      wing_distance_points: 5.0
    long_call:
      wing_distance_points: 5.0

  exit_order:
    exit_type: TAKE_PROFIT   # or NONE
    order_type: LIMIT        # required for TAKE_PROFIT
    time_in_force: GTC       # required for TAKE_PROFIT
    exit_price:              # required for TAKE_PROFIT
      type: PERCENT_OF_INITIAL_CREDIT
      value: 34

### Entry Retry Behavior

- Attempt 1 uses midpoint LIMIT.
- K9 waits up to `max_fill_wait_time_seconds`.
- On timeout, K9 cancel-replaces with a lower credit by `retry_price_decrement`.
- K9 stops when `max_entry_attempts` is reached or the next retry would be below `min_credit_received`.

### Market-Open Guard

- K9 skips runs outside regular session and on weekends.
- Holiday/off-session broker rejections are normalized to SKIPPED outcomes.
```

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | FILLED or SKIPPED (normal outcomes) |
| 1 | CANCELED, REJECTED, or ERROR |

## Run Logs

Each execution writes a JSON log to `logs/K9/<spec>_<YYYYMMDD_HHMMSS>.json`. Override the log directory with `K9_LOG_DIR`.

## Brokers

| Environment | Broker | Notes |
|---|---|---|
| `holodeck` | HolodeckBroker | Deterministic synthetic data; no API keys required |
| `sandbox` | TradierBroker | Requires `TRADIER_SANDBOX_API_KEY` and prefers `TRADIER_SANDBOX_ACCOUNT_ID` (falls back to `TRADIER_ACCOUNT_ID`) |
| `production` | TradierBroker | Requires `TRADIER_API_KEY` and `TRADIER_ACCOUNT_ID` |

## Development

```bash
# Run tests
uv run pytest apps/K9 -q

# Lint
uv run ruff check apps/K9
```
