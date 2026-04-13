# K9 — Automated 0DTE Options Trade Entry

K9 is a CLI tool that executes 0DTE options trades (Iron Condors, Put Credit Spreads, Call Credit Spreads) against the SPX index via the Broker Interface Contract (BIC).

## Quick Start

```bash
# Run a holodeck (simulated) trade entry
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_0900

# Run against the Tradier sandbox (requires .env with TRADIER_SANDBOX_TOKEN)
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_sandbox
```

## Trade Specs

Trade specs are JSON files in `apps/K9/trade_specs/`. Each spec fully describes one trade strategy.

| Spec | Type | Environment | Description |
|---|---|---|---|
| `spx_ic_20d_w5_tp34_0900` | Iron Condor | holodeck | 20Δ shorts, $5 wings, 34% TP |
| `spx_pcs_20d_w5_tp50_0930` | Put Credit Spread | holodeck | 20Δ short put, $5 wing, 50% TP |
| `spx_ic_20d_w5_tp34_sandbox` | Iron Condor | sandbox | Same as above; Tradier sandbox (disabled by default) |

### Spec Fields

```json
{
  "enabled": true,
  "environment": "holodeck",        // holodeck | sandbox | production
  "underlying": "SPX",
  "trade_type": "IRON_CONDOR",      // IRON_CONDOR | PUT_CREDIT_SPREAD | CALL_CREDIT_SPREAD
  "wing_size": 5,                   // points between short and long strikes
  "short_strike_selection": {
    "method": "DELTA",
    "value": 20                     // whole-number delta (20 = ~0.20Δ)
  },
  "position_size": {
    "mode": "fixed_contracts",
    "contracts": 1
  },
  "account_minimum": 5000,          // skip if account equity below this
  "max_risk_per_trade": 500,        // skip if max loss exceeds this
  "minimum_net_credit": 0.30,       // skip if mid price below this
  "max_combo_bid_ask_width": 0.50,  // skip if spread too wide
  "entry": {
    "order_type": "LIMIT",
    "limit_price_strategy": "MID",
    "max_fill_time_seconds": 120
  },
  "exit": {
    "take_profit_percent": 34,
    "expiration_day_exit_mode": "HOLD_TO_EXPIRATION"
  },
  "constraints": {
    "max_entries_per_day": 1,
    "one_position_per_underlying": true
  },
  "allowed_entry_after": "09:00",   // CT — skip if before this time
  "allowed_entry_before": "14:30"   // CT — skip if after this time
}
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
| `sandbox` | TradierBroker | Requires `TRADIER_SANDBOX_TOKEN` in `.env` |
| `production` | TradierBroker | Requires `TRADIER_PRODUCTION_TOKEN` and `TRADIER_ACCOUNT_ID` in `.env` |

## Development

```bash
# Run tests
uv run pytest apps/K9 -q

# Lint
uv run ruff check apps/K9
```
