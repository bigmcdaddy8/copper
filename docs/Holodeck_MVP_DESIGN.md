# Holodeck — MVP Design Specification

## Purpose

Holodeck is the MVP broker simulation implementation of the Broker Interface Contract. Its purpose is to provide a **fast, deterministic, local development and testing environment** for K9 without depending on Tradier sandbox hours, network calls, or live market conditions.

Holodeck is **not** intended to be a realistic backtesting engine in MVP. It is a **simulation broker for development mechanics**.

Its goals are:
- Enable rapid iteration
- Support repeatable tests
- Emulate enough broker behavior for K9 MVP
- Provide virtual time
- Support synthetic option chains and order lifecycle handling

---

## MVP Design Principles

1. **Mechanics over realism**
   - Support execution flow, not perfect market microstructure

2. **Deterministic behavior**
   - Given the same seed and config, Holodeck should produce the same results

3. **Simple, inspectable models**
   - Prefer explicit formulas and rules over opaque randomness

4. **Discrete time first**
   - Step-based virtual time is easier to debug than continuously flowing time

5. **Minimal surface area**
   - Only implement what K9 MVP requires

---

## Responsibilities

Holodeck must provide:
- Current virtual time
- Simulated account state
- Simulated open positions
- Simulated orders
- Synthetic underlying quotes
- Synthetic option chains
- Deterministic order fill / no-fill handling
- Expiration resolution

Holodeck is not responsible for:
- True brokerage realism
- Tick-level replay
- Full Greeks modeling
- Exchange-style order matching
- Portfolio analytics

---

## High-Level Architecture

Holodeck should be composed of a few small internal components.

### 1. VirtualClock
Owns simulated current time.

Responsibilities:
- Start at configured datetime
- Advance time in discrete steps
- Know market session boundaries

### 2. MarketDataStore
Provides synthetic underlying and option data.

Responsibilities:
- Load or generate SPX minute bars
- Return current underlying quote for virtual time
- Generate synthetic option chains for a given expiration/time

### 3. AccountLedger
Tracks simulated account state.

Responsibilities:
- Net liquidation
- Available funds / buying power
- Open positions
- Realized P/L
- Open orders

### 4. OrderEngine
Handles order placement, status, and fills.

Responsibilities:
- Accept or reject orders
- Store open orders
- Reevaluate orders when time advances
- Fill or cancel orders based on configured rules

### 5. ExpirationEngine
Resolves positions at expiration.

Responsibilities:
- Determine final option value at expiration
- Close expiring positions
- Update account balances
- Write final trade outcomes back into state

---

## Virtual Time Model

## MVP Choice: Discrete Step-Based Time

Holodeck should use **step-based virtual time** rather than continuously accelerated time.

### Why step-based time?
- Easier to debug
- Easier to reproduce
- Easier to unit test
- Avoids race conditions
- Good fit for minute-based market simulation

### Recommended behavior
- Virtual time begins at a configured timestamp, such as `2026-01-02 09:30:00 America/Chicago`
- Time advances only when explicitly requested
- Each advance typically moves time by **1 minute**

### Suggested interface
Internally, Holodeck should support operations such as:
- `advance_time(minutes=1)`
- `advance_to_next_market_minute()`
- `advance_to(timestamp)`

K9 itself does not need to know how time is advanced. A test harness or simulation runner may control it.

### Optional later enhancement
A continuous accelerated-clock mode may be added later for demos, but it should not be part of MVP.

---

## Market Session Rules

For MVP, Holodeck should model a simplified regular market session.

### Proposed assumptions
- Session dates are business days only
- Market open: `08:30 America/Chicago`
- Market close: `15:00 America/Chicago`
- SPX 0DTE expiration handled at end of session

### Simplifications
- Ignore holidays initially, or model them with a static calendar file
- No after-hours trading
- No intraday halts

---

## Synthetic Underlying Data Model

## Primary Underlying for MVP
- SPX only

Later this can be extended to XSP, NDX, IWM, etc.

## Data Granularity
- 1-minute bars or snapshots

## Time Range
- January 2026 synthetic data, generated once and reused

## Required fields per minute
Each minute record should include at least:
- timestamp
- last price
- bid
- ask

### Recommendation
Use:
- `last` = synthetic underlying price
- `bid` = `last - 0.05`
- `ask` = `last + 0.05`

This is crude but sufficient for MVP.

---

## Underlying Path Generation

## Goal
Generate believable but synthetic SPX intraday paths for development purposes.

## Recommended model
Use a **piecewise bounded random walk with drift toward the daily close**, rather than a pure sine wave.

### Inputs
For each trading day:
- known or user-specified daily open
- known or user-specified daily close
- random seed
- intraday volatility factor

### Suggested generation approach
1. Set minute 0 to open price
2. Set final minute to close price
3. Generate intermediate prices using:
   - small random increments
   - occasional volatility regime changes
   - gentle gravitation toward final close as the day progresses
4. Clamp unrealistic jumps
5. Round final prices to sensible precision

### Why this model?
- More varied than a sine wave
- Still deterministic with a fixed seed
- Easier to explain and implement
- Good enough for strategy mechanics testing

## Storage strategy
Synthetic data should be **generated once and stored** for reuse.

Recommended output format:
- CSV for easy inspection, or
- SQLite for structured query access

For MVP, CSV is likely enough.

---

## Synthetic Option Chain Model

## Goal
Produce a deterministic option chain that is internally consistent enough for K9 to:
- identify short strikes by delta
- compute credit and combo spread
- place entry orders
- simulate TP / expiration outcomes

## Core requirements
- Strikes divisible by 5
- Option prices divisible by 0.05
- Calls and puts generated around current underlying
- Includes short strikes and wing strikes needed by K9

## Recommended strike range
For each minute and expiration, generate strikes:
- from underlying minus 150 points
- to underlying plus 150 points
- in 5-point increments

This can be narrowed later if needed.

---

## Option Pricing Model

For MVP, pricing should be **simple, deterministic, and monotonic**, not financially perfect.

### Recommended approach
Use a lightweight synthetic pricing function influenced by:
- underlying price
- strike distance from underlying
- time remaining to expiration
- synthetic IV level
- option type (call/put)

### Desired properties
- Closer-to-money options cost more than farther OTM options
- As time passes, extrinsic value decays
- As underlying approaches a strike, that option becomes more expensive
- Put and call prices behave symmetrically enough for condors/spreads

### Possible implementation approach
Use a simplified pricing recipe such as:

`option_price = intrinsic_value + extrinsic_value`

Where:
- `intrinsic_value = max(0, underlying - strike)` for calls
- `intrinsic_value = max(0, strike - underlying)` for puts
- `extrinsic_value` is derived from:
  - time to expiration
  - moneyness distance
  - synthetic IV factor

Then round final prices to nearest 0.05.

This is sufficient for MVP even if it is not true Black-Scholes.

---

## Delta Model

K9 MVP depends on delta-based strike selection.

Holodeck therefore needs a synthetic delta model that is consistent with the chain.

### MVP requirement
Each option contract should include a delta estimate.

### Recommended approach
Use a deterministic synthetic delta approximation based on moneyness:
- deep ITM call approaches `+1.00`
- deep OTM call approaches `0.00`
- deep ITM put approaches `-1.00`
- deep OTM put approaches `0.00`

For example, delta can be approximated from standardized strike distance from underlying and then rounded to 0.01.

### Key requirement
The chain must include at least one put near `-0.20` delta and one call near `+0.20` delta for normal conditions.

This matters more than perfect finance math.

---

## IV Model

Holodeck may include a synthetic IV or IVx factor used by the option pricing recipe.

### MVP behavior
- A per-day IV base value may be generated once
- Small intraday IV variation may be added
- IV does not need to match real-world VIX behavior

### Recommendation
Keep IV simple and deterministic:
- daily base IV from a bounded random range
- optional mild intraday drift

This keeps option prices dynamic without making the model complicated.

---

## Account Simulation Model

Holodeck must emulate enough account behavior to support K9 risk checks and trade state management.

## MVP account fields
- account_id
- net_liquidation
- available_funds
- buying_power
- open_positions
- open_orders
- realized_pnl

## Initial account setup
Configuration should allow:
- starting account value
- starting buying power
- empty or preloaded positions

### Recommendation
For MVP:
- default account starts flat
- no open positions
- buying power approximated simply

---

## Buying Power / Risk Model

K9 MVP uses defined-risk 0DTE spreads and condors.

### MVP simplification
Buying power reduction can be approximated as:

`max_loss_per_trade * quantity`

For example:
- Iron condor with $5 wings and $1.00 net credit
- Approx max loss = `(5.00 - 1.00) * 100 = $400`

That amount reduces available funds / buying power when the trade opens.

When the trade closes or expires, buying power is released.

This is simple and sufficient for MVP.

---

## Order Model

## Supported order types in MVP
- LIMIT only

## Supported strategy types in MVP
- Iron Condor
- Put Credit Spread
- Call Credit Spread

## Order lifecycle states
- ACCEPTED
- OPEN
- FILLED
- CANCELED
- REJECTED

K9 should place an entry order, poll for status, and cancel if max fill time expires.

---

## Fill Logic

## Goal
Provide deterministic and understandable fill behavior for development.

## Entry fill model (MVP)
Since K9 MVP will enter at **bid** prices for credit trades, Holodeck needs clear rules for when a limit order fills.

### Recommended rule
A credit order fills if:
- order credit requested is less than or equal to the synthetic current market bid for the full combo

Otherwise:
- order remains OPEN
- it may fill later if market conditions improve
- if timeout expires, K9 cancels it

## Combo bid/ask definition
For MVP, combo bid/ask should be computed from the legs as follows:
- combo bid = sum of sell-leg bids minus sum of buy-leg asks
- combo ask = sum of sell-leg asks minus sum of buy-leg bids

This is a reasonable synthetic approximation.

## Repricing
Not needed in K9 MVP if your current entry rule is fixed at bid and timeout.

---

## TP Fill Logic

When K9 places a take-profit order after entry, Holodeck should evaluate it using similarly simple rules.

### Recommended rule
A debit buy-to-close TP order fills if:
- requested debit is greater than or equal to the synthetic combo ask-to-close threshold appropriate for the current minute

A simpler approximation may also be used:
- recompute current combo mark from legs
- fill if requested TP debit is executable at current simulated prices

The important thing is internal consistency.

---

## Timeout Handling

Holodeck does not own timeout policy; K9 does.

However, Holodeck must support the behavior K9 needs:
- order remains OPEN across virtual time steps
- K9 polls status
- K9 cancels after timeout threshold

---

## Position Model

Once an order is FILLED, Holodeck should create a position record sufficient for later tracking.

### Position should include
- underlying symbol
- strategy type
- quantity
- legs
- entry credit
- entry time
- expiration date
- status

This can be stored as a strategy-level position even if internally legs are also tracked.

---

## Expiration Handling

## Goal
Resolve open 0DTE positions at end of session.

### Recommended rule
At market close:
1. Identify all positions expiring that day
2. Calculate each option’s intrinsic value based on final underlying price
3. Compute final spread / condor value
4. Realize final P/L
5. Close the position
6. Release buying power

### Notes
- Ignore settlement quirks and special exercise mechanics in MVP
- Focus on simple cash-settled outcome logic

This is sufficient for SPX-style products in a synthetic environment.

---

## Persistence Strategy

Holodeck should persist generated market data so it can be reused.

### Recommended persisted artifacts
- synthetic underlying minute data
- optional synthetic daily IV data
- optional generated account snapshots during tests

### Recommendation
Store market data separately from transient order/account state.

For example:
- `data/holodeck/spx_2026_01_minutes.csv`
- runtime account/order state lives in memory unless tests choose to persist it

---

## Configuration Inputs

Holodeck should be configurable via a simple config object or JSON/YAML file.

## Suggested configuration fields
- starting_datetime
- ending_datetime
- timezone
- random_seed
- starting_account_value
- starting_buying_power
- underlying_symbol
- default_price_tick
- default_strike_increment
- session_open_time
- session_close_time

---

## Recommended Testing Scenarios

Holodeck should support fast, repeatable testing of K9 behavior.

### Core scenarios
1. Trade enters immediately at bid
2. Trade never fills and is canceled after timeout
3. Trade fills, TP later fills
4. Trade fills, TP never fills, trade expires profitable
5. Trade fills, TP never fills, trade expires at max loss
6. Account minimum fails and no order is placed
7. Existing same-underlying position blocks new trade

These are more important than market realism for MVP.

---

## MVP Scope Boundaries

Holodeck MVP should NOT attempt to provide:
- historical realism
- statistically valid backtests
- streaming quotes
- partial fills
- advanced slippage models
- realistic volatility surfaces
- multi-broker support inside Holodeck itself
- web server / REST emulation

Holodeck should remain a **local Python broker implementation** behind the Broker Interface Contract.

---

## Suggested Internal Build Order

1. Build VirtualClock
2. Build synthetic SPX minute data generator
3. Build underlying quote retrieval
4. Build synthetic option chain generator
5. Build basic account ledger
6. Build limit order acceptance / open / fill / cancel logic
7. Build expiration engine
8. Add deterministic test scenarios

---

## Summary

Holodeck MVP is a simulation broker designed to support K9 development rapidly and safely.

It should be:
- deterministic
- local
- simple
- inspectable
- good enough for execution mechanics

It should not try to be:
- a perfect backtester
- a fake exchange
- a full Tradier clone

Its job is to let K9, and later captains_log and encyclopedia_galactica, be built and tested quickly before promotion to sandbox and production.
