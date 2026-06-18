# K9 Trade Spec Criteria Reference v1

This document is a focused reference for trade entry and exit criteria in K9 trade spec JSON files.

Scope:
- Current supported criteria: what K9 currently accepts and enforces.
- Future planned criteria: criteria discussed in planning docs but not yet implemented.

Primary source of truth for implemented schema and validation:
- apps/K9/src/K9/config.py
- apps/K9/src/K9/engine/validator.py
- apps/K9/src/K9/engine/constructor.py

## 1. Current Supported JSON Criteria

### 1.1 Top-Level Fields

| Field | Type | Required | Supported Values / Behavior |
|---|---|---|---|
| enabled | bool | Yes | true or false. If false, K9 exits normally without entering. |
| environment | string | Yes | holodeck, sandbox, production |
| underlying | string | Yes | SPX, XSP, NDX, RUT |
| trade_type | string | Yes | IRON_CONDOR, PUT_CREDIT_SPREAD, CALL_CREDIT_SPREAD |
| wing_size | int | Yes | Must be > 0 |
| short_strike_selection | object | Yes | method/value pair. See section 1.2 |
| position_size | object | Yes | mode/contracts pair. See section 1.3 |
| account_minimum | number | Yes | Account equity must be >= this value |
| max_risk_per_trade | number | Yes | Trade max loss must be <= this value |
| minimum_net_credit | number | Yes | Must be > 0 and met by entry order mid credit |
| max_combo_bid_ask_width | number | Yes | Combo spread width must be <= this value |
| entry | object | Yes | Entry criteria. See section 1.4 |
| exit | object | Yes | Exit criteria. See section 1.5 |
| constraints | object | Yes | Position/entry limits. See section 1.6 |
| allowed_entry_after | string (HH:MM) | No | Defaults to 09:25 (CT) |
| allowed_entry_before | string (HH:MM) | No | Defaults to 14:30 (CT) |
| notes | string | No | Informational only |

### 1.2 short_strike_selection

| Field | Type | Required | Supported Values / Behavior |
|---|---|---|---|
| method | string | Yes | DELTA only (MVP) |
| value | number | Yes | Delta target (for example 20 means about 0.20 delta) |

### 1.3 position_size

| Field | Type | Required | Supported Values / Behavior |
|---|---|---|---|
| mode | string | Yes | fixed_contracts expected in specs |
| contracts | int | Yes | 1 only (MVP hard limit) |

### 1.4 entry

| Field | Type | Required | Supported Values / Behavior |
|---|---|---|---|
| order_type | string | Yes | LIMIT |
| limit_price_strategy | string | Yes | MID |
| max_fill_time_seconds | int | Yes | Maximum poll/wait window before cancel |

### 1.5 exit

| Field | Type | Required | Supported Values / Behavior |
|---|---|---|---|
| take_profit_percent | number | Yes | Used to create TP buy-to-close limit order |
| expiration_day_exit_mode | string | Yes | HOLD_TO_EXPIRATION |

### 1.6 constraints

| Field | Type | Required | Supported Values / Behavior |
|---|---|---|---|
| max_entries_per_day | int | Yes | Daily cap enforced from K9 run logs |
| one_position_per_underlying | bool | Yes | Prevents opening another position on same underlying |

## 2. Current Runtime Checks Related to Criteria

K9 validates or enforces the following from the trade spec:

- Schema and value checks:
  - underlying, trade_type, environment are validated against allowed sets.
  - short_strike_selection.method must be DELTA.
  - position_size.contracts must be 1.
  - wing_size and minimum_net_credit must be positive.

- Entry-time checks:
  - Current CT time must be within allowed_entry_after and allowed_entry_before.
  - Account equity must meet account_minimum.
  - one_position_per_underlying and max_entries_per_day constraints are enforced.

- Pre-trade checks:
  - Entry net credit must meet minimum_net_credit.
  - Combo bid/ask width must be <= max_combo_bid_ask_width.
  - Max risk must be <= max_risk_per_trade.

- Exit behavior:
  - If entry fills, K9 places a TP order using take_profit_percent.
  - If TP does not fill, exit behavior is HOLD_TO_EXPIRATION.

## 3. Future Planned Criteria Support (Not Yet Implemented)

The following are documented as future extensions or currently out of MVP scope in planning docs, but are not implemented as supported JSON criteria today.

### 3.1 Strategy/Signal Criteria

- IV-based strike selection
- Time-of-day optimization criteria (beyond fixed window)
- Event filters
- Indicator-based entry signals

### 3.2 Position/Risk Criteria

- Dynamic sizing
- Multiple contracts
- Dynamic position sizing logic
- Multi-strategy portfolio management criteria

### 3.3 Order/Lifecycle Criteria

- Repricing on fill timeouts
- Stop-loss logic
- Trade adjustments after entry
- Multi-entry per day beyond current static cap behavior

## 4. Notes on JSON Compatibility

To avoid runtime validation failures, keep trade specs within section 1 constraints.

When future criteria are implemented, update this document together with:
- apps/K9/src/K9/config.py
- apps/K9/src/K9/engine/validator.py
- apps/K9/src/K9/engine/runner.py
- apps/K9/README.md

## 5. Related Docs

- docs/K9_PROGRAM_INTENT.md
- docs/K9_IMPLEMENTATION_PLAN.md
- apps/K9/README.md
