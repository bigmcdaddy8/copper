# K9 Functional Specification — Trade Spec Schema

This document is the authoritative reference for the **K9 trade specification** (`.yaml`) file format. Each trade spec file fully defines one automated options strategy that K9 can execute. As new functionality is added to K9, the supported fields and allowed values documented here are expanded accordingly.

---
## Background Information - Anatomy of an Options Trade

A typical options trade has several distinct stages and the transitions between these stages will be described in this section. The 'K9' Automated Trading System (ATS) focuses on collecting options premium strategies, so that will be our focus here. The 'K9' ATS must take into account the brokerage interactions (i.e., send orders, adjust orders, close orders, and monitor orders) and keep the 'K9' ATS tracking/logging in sync with the brokerage status.

Events that the 'K9' ATS must capture and monitor are defined in this table:

| Description | Brokerage Action | 'K9' Trading System Action |
|---|---|---|
| trade entry orders pending | broker logs STO/BTO pending orders have been entered | must detect that pending entry orders have been entered and update 'K9' tracking/logging data; invoke any pre-fill logic (i.e., set timers) |
| trade entry failed | Trade Order Reject | log failure reason and determine if retry is needed |
| trade entry timed out | N/A | a 'K9' timer detects that trade has not filled in configured time; 'K9' must cancel the unfilled entry order and wait for broker cancellation confirmation before retrying or giving up |
| entry order cancellation confirmed | broker confirms entry order has been cancelled | 'K9' records cancellation; if `max_entry_attempts` not exceeded AND the next retry price still meets `min_credit_received` AND the entry time window (`allowed_entry_before`) has not expired, submit a new entry order with adjusted price; otherwise mark trade as abandoned for the day |
| trade entry filled | pending entry orders are now 'filled' | must detect the fill event and update 'K9' tracking/logging data and invoke any post-fill logic (i.e., enter 'take profit' pending orders) |
| take-profit exit order submitted | broker acknowledges a new pending GTC close order | 'K9' records the broker-assigned exit order ID and links it to the originating trade entry |
| take-profit exit order cancelled unexpectedly | broker cancels the GTC close order without a fill (e.g., broker rejection, corporate action) | 'K9' must detect the orphaned position, alert, and either resubmit the exit order or flag the trade for manual review |
| active options expire worthless (OTM at expiration) | broker logs expired options (may appear 0–3 days later) | must detect that options expired worthless and reconcile them to the originating trade; update trade status to closed at max profit |
| active options cash-settle with intrinsic value (ITM at expiration) | broker logs cash settlement debit/credit | must detect the cash-settlement event, reconcile to the originating trade, compute final P&L including settlement amount, and update trade status accordingly |
| active options closed by 'GTC LIMIT take profit order' | broker logs that previously entered pending 'take profit' orders have filled | must detect that BTC/STC orders have been filled and update 'K9' tracking/logging data |
| user manually closes an open position (emergency exit) | trader places close orders directly via broker UI or another tool; broker logs the fill outside of K9 control | must detect that the position no longer exists in account positions (or that close orders filled without K9 initiating them); immediately cancel any outstanding GTC exit orders associated with that trade to prevent them from re-opening the position; mark trade as manually closed in tracking/logging and alert |
| trade has completed | N/A — brokerage only monitors orders, not 'K9' trades | 'K9' ATS is responsible for correlating brokerage orders to a 'K9' trade and updating tracking/logging as needed |

### Additional 'K9' Capabilities

* *Order Mapping*: Trades can be comprised of multiple legs and there can be multiple trades in the same underlying, all of which requires that 'K9' ATS be able to associate broker orders through the various transition states to 'K9' ATS trades. The Tradier API provides the following mechanisms to support this:
  * **Tradier order ID**: Every order placement response includes an integer `id` field. K9 stores this as the authoritative broker-side handle for looking up or cancelling an order via `GET /v1/accounts/{account_id}/orders/{order_id}`.
  * **Multileg order class**: Credit spreads (PCS, CCS) and iron condors (SIC) are submitted as a single `class: multileg` request. Tradier returns **one order ID** for the entire spread — K9 does not need to track individual leg-level IDs.
  * **`tag` field (user-defined label)**: The Place Order request accepts an optional `tag: string` parameter that K9 can populate with its own internal trade identifier (e.g. `k9_xsp_pcs_20260619_001`). Tags are returned when querying orders with `includeTags=true`, enabling K9 to correlate broker orders back to K9 trades during reconciliation without relying solely on the Tradier order ID.
  * **OTOCO advanced orders**: For strategies that use a `TAKE_PROFIT` exit, Tradier's One-Triggers-One-Cancels-Other (OTOCO) advanced order type allows K9 to submit the spread entry and the GTC take-profit close order in a single API call. If the entry fills, Tradier automatically activates the exit order at the exchange level. This is a candidate simplification for K9's post-fill state machine (eliminating the separate "submit exit order" step), and should be evaluated during implementation.
* *Expired Options*: When an option expires it may not appear in the brokerage order history for a period of time (0–3 days). The 'K9' ATS needs to be able to handle orders (and therefore trades) that may take a period of time to reach their final status.

## Trade Spec Overview

Trade spec files are YAML documents stored under `apps/K9/trade_specs/`. K9 loads a spec at runtime via the `--trade-spec` CLI argument. A spec contains:

1. **File-level metadata** — versioning, environment targeting, and the underlying instrument.
2. **Entry constraints** — safety rails that prevent runaway or duplicate trades.
3. **Entry criteria** — conditions that must be met before an order is placed.
4. **Entry order** — how the opening order is constructed and submitted.
5. **Leg selection** — how option strikes are chosen for each leg.
6. **Exit order** — how (or whether) K9 manages the position after entry.

---

## File-Level Fields

| Field | Type | Required | Description |
|---|---|---|---|
| `schema_version` | integer | yes | Schema version number. Current supported version: `2`. |
| `enabled` | boolean | yes | When `false`, K9 refuses to execute this spec. Provides a safe on/off switch without deleting the file. |
| `environment` | string | yes | Target broker environment. See [Environments](#environments). |
| `underlying` | string | yes | The ticker symbol of the underlying instrument (e.g., `XSP`, `SPX`, `QQQ`). |
| `notes` | string | no | Free-text description of the strategy. Not used programmatically. |

### Environments

| Value | Description |
|---|---|
| `HD` | Holodeck — local simulation broker. Used for development and backtesting. |
| `TRDS` | Tradier Sandbox — paper trading against the Tradier sandbox API. |
| `TRD` | Tradier Production — live trading against a real brokerage account. |

---

## `trade` Block

All strategy configuration lives inside the top-level `trade:` key.

### `option_strategy`

Identifies the multi-leg options structure K9 will trade.

| Value | Legs | Description |
|---|---|---|
| `PCS` | 2 (put credit spread) | Short put + long put at a lower strike. Bullish/neutral bias. |
| `CCS` | 2 (call credit spread) | Short call + long call at a higher strike. Bearish/neutral bias. |
| `SIC` | 4 (short iron condor) | Short put spread + short call spread. Neutral bias. |

---

## `entry_constraints` Block

Hard limits evaluated before any order is sent. If any constraint is violated, K9 aborts the entry attempt for that run.

| Field | Type | Required | Description |
|---|---|---|---|
| `allow_multiple_trades` | boolean | yes | When `false`, K9 will not enter if an open position already exists for this spec. |
| `quantity` | integer | yes | Number of contracts (spreads) to trade per entry. |
| `max_entries_per_day` | integer | yes | Maximum number of filled entries allowed in a single calendar day for this spec. |
| `max_risk_dollars` | float | yes | Maximum dollar risk per trade. K9 will not enter if the computed max loss exceeds this value. For a credit spread, max risk = (wing distance × 100 × quantity) − credit received. |

---

## `entry_criteria` Block

Conditions that must be true at the time K9 evaluates whether to place an order.

| Field | Type | Required | Description |
|---|---|---|---|
| `type` | string | yes | The type of entry rule. Currently only `time_window` is supported. |

### `type: time_window`

Entry is only attempted within a defined clock window (Chicago / Central time).

| Field | Type | Required | Description |
|---|---|---|---|
| `allowed_entry_after` | string (`"HH:MM"`) | yes | Earliest time of day at which an entry order may be submitted. |
| `allowed_entry_before` | string (`"HH:MM"`) | yes | Latest time of day at which a new entry order may be submitted. Orders already in flight are not cancelled when this time passes. |

---

## `entry_order` Block

Defines how the opening order ticket is constructed and managed.

| Field | Type | Required | Description |
|---|---|---|---|
| `order_type` | string | yes | Order type for the entry ticket. Currently only `LIMIT` is supported. |
| `time_in_force` | string | yes | Order duration. `DAY` cancels any unfilled order at market close. |
| `max_fill_wait_time_seconds` | integer | yes | How long (in seconds) K9 waits for the order to fill before cancelling and optionally retrying. |
| `max_entry_attempts` | integer | yes | Maximum number of fill attempts (original submission + retries) before giving up for the day. |
| `retry_price_decrement` | float | yes | Amount (in dollars) to reduce the limit price on each retry. Set to `0.0` to disable price-walking. |
| `entry_price` | string | yes | Starting limit price formula. See [Entry Price Expressions](#entry-price-expressions). |
| `min_credit_received` | float | yes | Minimum net credit (in dollars per share, i.e., per-contract value ÷ 100) required to place the order. K9 will not enter if the calculated credit is below this threshold. |

### Entry Price Expressions

| Expression | Description |
|---|---|
| `MIDPOINT` | Use the natural bid/ask midpoint of the spread. |
| `MIDPOINT + N` | Use midpoint plus a fixed dollar offset `N` (raises the limit, making the order more aggressive to fill). |
| `MIDPOINT - N` | Use midpoint minus a fixed dollar offset `N`. |

---

## `leg_selection` Block

Defines how K9 chooses strikes for each option leg. The keys present depend on `option_strategy`.

### Common per-leg fields

| Field | Type | Required | Description |
|---|---|---|---|
| `delta_preferred` | float | no | Ideal target delta. K9 selects the strike whose delta is closest to this value within the allowed range. If omitted, K9 selects the strike whose delta falls closest to the center of `delta_range`. |
| `delta_range.min` | float | yes (short legs) | Minimum acceptable delta (inclusive). For puts, values are negative. |
| `delta_range.max` | float | yes (short legs) | Maximum acceptable delta (inclusive). |
| `wing_distance_points` | float | yes (long legs) | Distance in index points between the short leg and the corresponding long (protective) leg. |

### Legs by Strategy

#### `PCS` — Put Credit Spread

| Key | Role |
|---|---|
| `short_put` | The short (sold) put; delta selection applies. |
| `long_put` | The long (bought) put; placed `wing_distance_points` below the short put. |

#### `CCS` — Call Credit Spread

| Key | Role |
|---|---|
| `short_call` | The short (sold) call; delta selection applies. |
| `long_call` | The long (bought) call; placed `wing_distance_points` above the short call. |

#### `SIC` — Short Iron Condor

| Key | Role |
|---|---|
| `short_put` | Short put; delta selection applies (negative values). |
| `long_put` | Protective put; placed `wing_distance_points` below `short_put`. |
| `short_call` | Short call; delta selection applies (positive values). |
| `long_call` | Protective call; placed `wing_distance_points` above `short_call`. |

---

## `exit_order` Block

Defines how (or whether) K9 manages an exit after a successful entry fill.

| Field | Type | Required | Description |
|---|---|---|---|
| `exit_type` | string | yes | The exit management mode. See [Exit Types](#exit-types). |

### Exit Types

#### `NONE`

K9 takes no automated exit action. The position is held to expiration and managed externally (or expires worthless).

No additional fields are required.

#### `TAKE_PROFIT`

K9 immediately submits a GTC limit order to close the position at a target credit.

| Field | Type | Required | Description |
|---|---|---|---|
| `order_type` | string | yes | Must be `LIMIT`. |
| `time_in_force` | string | yes | Must be `GTC` (Good Till Cancelled). |
| `exit_price.type` | string | yes | How the target price is calculated. Currently only `PERCENT_OF_INITIAL_CREDIT` is supported. |
| `exit_price.value` | float | yes | The percentage of the initial credit received to use as the closing debit target. For example, `50.0` means K9 attempts to buy the spread back at 50% of what was originally collected. |

---

## Planned / Future Extensions

The following features are not yet implemented but represent the intended direction for this schema.

### Short Iron Condor (SIC) — _currently supported; listed here for completeness_

Four-leg strategy (`short_put`, `long_put`, `short_call`, `long_call`) defined under `leg_selection`. Already implemented. See [SIC leg table](#sic--short-iron-condor) above.

### Call Credit Spread (CCS) — _currently supported; listed here for completeness_

Two-leg strategy (`short_call`, `long_call`) defined under `leg_selection`. Already implemented. See [CCS leg table](#ccs--call-credit-spread) above.

### Future: Additional `exit_type` values

| Planned Value | Description |
|---|---|
| `STOP_LOSS` | GTC limit order to close the spread if the position reaches a maximum loss threshold (expressed as a multiple of credit received or a fixed dollar amount). |
| `TRAILING_STOP` | Dynamic stop that adjusts as the position moves in the trader's favor. |

### Future: Additional `entry_criteria` types

| Planned Value | Description |
|---|---|
| `vix_range` | Only enter if VIX is within a defined min/max band at entry time. |
| `market_trend` | Only enter on days matching a specified directional bias (e.g., bullish, bearish, neutral based on prior close or overnight futures). |

### Future: Additional `entry_price` expressions

| Planned Value | Description |
|---|---|
| `ASK` | Use the natural ask of the spread (most aggressive buyer price). |
| `BID` | Use the natural bid of the spread (least aggressive; most favorable credit but lowest fill probability). |
