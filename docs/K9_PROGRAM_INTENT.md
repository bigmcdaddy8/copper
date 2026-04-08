# K9 Trade Entry MVP — Project Intent 

The 1st major program in the 'Copper' project is the 'trade_hunter' (i.e., @apps/trade_hunter) application. 'K9' (i.e., with a capital 'K') is the 2nd major program / application to be added to the 'Copper' project. This file describes the intent of the K9 program when the idea of it was originally conceived.

## Overview

K9  is an automated options trade entry system designed to execute predefined, rules-based 0DTE strategies using the Tradier API. The system is intentionally constrained for MVP to ensure simplicity, safety, and clean experimentation.

This document defines the **Minimum Viable Product (MVP)** design, focusing on:

* Deterministic behavior
* Limited scope
* Strong safeguards
* Clear separation of concerns

---

## Core Design Principles

1. **Configuration-driven strategies**

   * All trade logic defined in JSON files
   * No strategy logic hardcoded in application

2. **Separation of concerns**

   * Cron = scheduling
   * K9 = orchestration
   * JSON = strategy definition

3. **Safety-first execution**

   * Hard constraints before any order placement
   * Defensive checks to prevent duplicate or runaway trades

4. **MVP simplicity**

   * Single contract only
   * No adjustments
   * No stop losses
   * Hold to expiration

---

## System Components

### 1. Scheduler (Cron)

Responsible ONLY for invoking K9 at a specific time.

Example:

```
K9 enter --trade-spec spx_ic_20d_0900
```

No strategy logic exists in cron.

---

### 2. K9 Orchestrator

Primary execution engine.

Responsibilities:

* Load trade spec
* Validate configuration
* Verify trading conditions
* Retrieve market data
* Construct trade
* Apply filters
* Submit order
* Manage entry fill
* Log all activity

---

### 3. Trade Specification Files

Each trade spec exists as an individual JSON file.

Directory structure:

```
trade_specs/
  spx_ic_20d_0900.json
  xsp_ic_15d_0930.json
```

---

## Trade Specification Schema (MVP)

Example:

```json
{
  "enabled": true,
  "environment": "sandbox",

  "underlying": "SPX",
  "trade_type": "IRON_CONDOR",
  "wing_size": 5,

  "short_strike_selection": {
    "method": "DELTA",
    "value": 20
  },

  "position_size": {
    "mode": "fixed_contracts",
    "contracts": 1
  },

  "account_minimum": 1000,
  "max_risk_per_trade": 500,

  "minimum_net_credit": 0.30,
  "max_combo_bid_ask_width": 0.15,

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

  "notes": "SPX 0DTE IC, 20 delta shorts, $5 wings"
}
```

---

## Key Definitions

### Combo Bid/Ask Width

Defined as:

**Sum of all leg bid/ask spreads for the full multi-leg position.**

Used to ensure acceptable execution quality.

---

## Execution Flow (MVP)

1. Load trade spec
2. Validate schema
3. Verify spec is enabled
4. Check current time vs allowed execution window
5. Verify account minimum
6. Check existing positions

   * Only 1 position per underlying allowed
7. Pull option chain data
8. Select strikes (DELTA-based only for MVP)
9. Construct trade
10. Validate trade:

    * Minimum net credit
    * Combo bid/ask width
    * Max risk
11. Submit limit order at mid price
12. Wait up to max fill time
13. If filled:

    * Place take profit order
14. If not filled:

    * Cancel order
15. Log all results

---

## Constraints (MVP)

* 1 contract per trade (hardcoded)
* Only supported underlyings are: SPX, XSP, NDX and RUT (cash-settled indices)
* DELTA-based strike selection only
* No adjustments after entry
* No stop loss
* Hold to expiration if TP not hit
* One position per underlying at a time
* Only defined risk trades supported: Iron Condor, Put Credit Spread and Call Credit Spread

---

## Risk Controls

* Minimum account value required
* Max risk per trade enforced
* Minimum credit required
* Liquidity filter via combo spread
* Duplicate trade prevention

---

## Logging Requirements

Each run must log:

* Trade spec name
* Timestamp
* Selected strikes
* Credit at entry attempt
* Fill status
* Reason for rejection (if any)
* TP placement

---

## Naming Convention

Example:

```
spx_ic_20d_w5_tp34_0900
```

---

## Out of Scope (MVP)

* Support repricing on fill timeouts
* Multiple contracts
* Strategy optimization
* Indicator-based signals
* Dynamic position sizing
* Trade adjustments
* Stop-loss logic
* Multi-entry per day

---

## Future Extensions (Not in MVP)

* IV-based strike selection
* Time-of-day optimization
* Dynamic sizing
* Event filters
* Multi-strategy portfolio management

---

## Summary

The MVP version of K9 is designed to:

* Execute a single, controlled 0DTE strategy
* Use configuration-driven trade definitions
* Enforce strict safety and simplicity
* Provide a reliable platform for experimentation

This design prioritizes correctness and control over performance or optimization.
