# Tradier API FAQ

The answers to the following questions will be obtained during the development and implementation of the 'tradier_sniffer' program.

**Question**: When a multi-leg option trade is entered (not yet filled) how do we know if / when it gets filled ?
  - Is the API order placed synchronously - so that we don't get a response until it is filled or times out ?
  - Is the API order placed asynchronously - can we poll the brokerage or is there call back functionality ?
  - Can we place a time limit on the fill ?
  - Can we implement a retry loop that brings our required entry price down a few pennies and tries again ?

**Story:** TS-0040 (async fill detection via polling), TS-0080 (Scenario 1.5 — reprice retry loop)

---

**Question**: How can we associate the various options orders (multiple legs) with a 'Trade #' so that if they get closed - either manually by 'Mr. Dick Weasel' using the desktop application to close the trade or by hitting a GTC BTC order.
  - Does the brokerage have a reference # for each specific order that we can use to map orders to trades ?
  - Does the brokerage support a tagging capability where we can add a tag to an order to indicate which trade it belongs to ?
  - We will want to associate filled orders and pending orders with a trade ?
    - For example we place a Day STO Limit order - it is pending, we reboot the local computer running our automated trade program, during the down time the trade 'fills' on the brokerage side, we bring our trading system up and it knows (according to its' local database) that we have a pending entry order. How can it figure out that the order 'filled' and it needs to update its' status and all related data for the trade with the 'filled' data ?

**Story:** TS-0050 (order-to-trade mapping via Tradier grouping/tag field), TS-0060 (startup reconciliation detects pending→filled transitions after downtime)

---

**Question**: Is there a list of error reasons for a order being 'cancelled' or 'rejected' ?

**Answer:** Tradier exposes order status via the `status` field on order objects. Known statuses: `filled`, `partially_filled`, `open`, `expired` (Day order past session end or GTC past expiry), `canceled` (user or broker action), `pending` (received, not yet routed), `pending_cancel` (cancellation submitted), `rejected` (refused by broker or exchange), `partially_filled_canceled` (partial fill then canceled). Rejection reasons may appear in a `reason_description` field; known broker-level reasons include: insufficient buying power, invalid price (e.g., penny limit on nickel-only option), invalid quantity, market closed (order type not accepted outside RTH), and duplicate order. These are documented in `apps/tradier_sniffer/src/tradier_sniffer/tradier_client.py` as `ORDER_STATUSES` and `REJECTION_REASONS` dicts.

**Story:** TS-0010 (document known cancellation/rejection codes from Tradier API docs in client module)

---

**Question**: Some options trade on nickel pricing (i.e., they only trade on 0.05 boundaries such as 1.05, 1.10 etc.)
  - What happens when we place an Day STO Limit order with a penny based entry price (1.08) on a nickel only option ?

**Story:** TS-0095 (edge case sandbox test — place penny-priced limit on nickel option, observe broker response)

---

**Question**: Does the 'Tradier' brokerage support price improvement (i.e., the fill price is better than the Day STO Limit price) ?
  - Does the broker return the 'filled' price ?

**Story:** TS-0070 (Scenario 1 — observe fill price vs limit price in demo run and document finding)

---

**Question**: In the world of 0DTE trades on cash-settled options letting an option expire is very common. 
  - When does the option expire order status become visible in the order history for the brokerage (e.g., 5 minutes after market close, 5:00 PM, ???)

**Story:** TS-0095 (edge case sandbox test — poll for expiration status near market close; record timestamp delta)

---

**Question**: If we have a trade that involves Stock, such as a 'CCALL' and we receive a dividend payment what will that 'look' like to the automated trade program from an API perspective ?

**Story:** Deferred — out of MVP scope; requires a live account with a dividend-paying stock position. Revisit post-MVP.

---

**Question**: How is the maintenance BPR of a trade (with multiple legs) determined ?

**Answer:** The sandbox balances response includes a `margin` sub-object with fields `maintenance_call`, `fed_call`, `option_buying_power`, and `stock_buying_power`. The `margin.maintenance_call` field reflects the maintenance margin requirement currently in effect. For individual positions, the `current_requirement` top-level field appears to represent total margin requirement across all positions. **Gap:** a per-trade or per-leg maintenance BPR breakdown is not directly surfaced — the API aggregates margin at the account level. Actual per-leg BPR will need to be calculated locally using position cost basis and standard margin rules, or observed empirically by opening and inspecting positions in TS-0080/TS-0090 demos.

**Story:** TS-0015 (API discovery — inspect positions/orders response fields for BPR data)

---

**Question**: When adjusting a trade (e.g., rolling the Call side option down towards the Puts in a 'SIC' trade) can all of the adjustment orders (e.g., BTC a Call Spread, and then STO a Call Spread with lower strike prices) be placed into a single Day Limit order ?

**Story:** TS-0090 (Scenario 4 — BTC+STO adjustment demo; validates whether grouping into one order is supported)

---

**Question**: Can a TP trade be placed / adjusted after hours so that it in essence takes effect during the next trading session ?

**Story:** TS-0095 (edge case sandbox test — attempt to place/modify GTC order after market close; document behavior)

---

**Question**: Can after hours / extended hours pricing information be retrieved for Stocks ?

**Story:** TS-0095 (edge case sandbox test — call quotes endpoint after hours on a stock; document response)

---

**Question**: What exchange routing options are available ? Can a person just select a generic 'BEST' ?

**Answer:** Tradier's order submission API accepts a `duration` field (e.g., `day`, `gtc`, `pre`, `post`) but does not expose an explicit exchange routing parameter for options orders. Tradier routes orders internally through its smart order routing system — there is no `route` field to specify an exchange. The broker's documentation indicates orders are routed to the best available exchange automatically. For options, NBBO smart routing is the default and only option. No manual exchange selection (e.g., CBOE, PHLX) is available via the API.

**Story:** TS-0015 (API discovery — review Tradier order submission fields for routing options)

---

**Question**: What necessary account information is available via the 'Tradier API' ?
  - A list of needed data points include: Net Liquidity, Cash Balance, PDT Count, Option Buying Power, Beta-weighted delta, Total Theta, account transactions (e.g., withdraws and deposits)

**Answer:** Confirmed available via `GET /accounts/{id}/balances` (sandbox observation):
  - **Net Liquidity / Total Equity**: `total_equity` = 100000.00 ✓
  - **Cash Balance**: `total_cash` = 100000.00 ✓
  - **Option Buying Power**: `margin.option_buying_power` = 100000.00 ✓ (nested under `margin` sub-object, not at top level)
  - **Pending Orders Count**: `pending_orders_count` = 0 ✓
  - **PDT Count**: **Gap** — no `day_trade_count`, `pdt_count`, or similar field found in balances response. Tradier does not expose PDT trade count via the balances endpoint; this is a known limitation.
  - **Beta-weighted delta**: **Gap** — not available via API; this is a portfolio-level calculated metric that must be computed locally from individual position deltas weighted by beta.
  - **Total Theta**: **Gap** — not available via API; must be computed locally by summing per-position theta values from the options chain.
  - **Account transactions** (withdrawals/deposits): `GET /accounts/{id}/history` returns transaction history; sandbox account returned empty but endpoint is confirmed available.

**Story:** TS-0015 (API discovery — call `GET /accounts/{id}/balances` and `GET /accounts/{id}/history`; document available fields vs needed fields)

---

**Question**: Is there a flag available when a trade is closed that indicates that the broker is going to count that trade as a 'PDT' ?

**Answer:** **Gap** — No PDT flag was found in the balances, orders, or positions response payloads. Tradier does not surface a `is_pdt`, `day_trade`, or similar per-trade flag in the API. The sandbox account balance has no `day_trade_count` field. PDT tracking will need to be handled locally by the automated trader (e.g., counting same-day open+close pairs on the same symbol). Confirmed by inspection of `GET /accounts/{id}/balances` and Tradier API documentation.

**Story:** TS-0015 (API discovery — inspect closed order/trade response for PDT-related fields)

---

**Question**: What security is available to lock down my API access ?
  - OAuth password ? Any additional ssh or two-factor authentication or IP white-listing available ?
  - Can a strong authentication mechanism be put in place and still be compatible with a automated trader program ?

**Answer:** Tradier supports two authentication mechanisms: (1) **Long-lived API tokens** — a static Bearer token issued per application, stored as a secret, used in every request header. This is the mechanism used by `tradier_sniffer`. No interactive login required; fully compatible with automated/headless programs. (2) **OAuth 2.0** — three-legged flow requiring browser-based user authorization; produces short-lived access tokens + refresh tokens. OAuth is intended for multi-user applications and requires interactive login at least once. **IP whitelisting** is not available via the standard Tradier API. **2FA / SSH** do not apply to API token auth — 2FA is a Tradier web console setting and does not affect API key usage. **Recommendation for automated trading**: use the long-lived API token stored in a `.env` file (never committed). Rotate the key if compromised via the Tradier developer dashboard.

**Story:** TS-0015 (API discovery — review Tradier API docs for auth options; document compatibility with automated access)

---

**Question**: Are there any account level restrictions that can be put in place - max trade size - max BPR - max number of trades ?

**Answer:** **Gap** — Tradier does not expose account-level risk controls (max trade size, max BPR, max number of open trades) via the API. The broker enforces standard margin requirements and buying power limits, but there is no API endpoint to configure custom per-account guardrails. Any such restrictions (e.g., max position size, max concurrent trades) must be enforced by the automated trading program itself in application logic, not delegated to the broker.

**Story:** TS-0015 (API discovery — review Tradier account settings and API docs for risk controls)

---

**Question**: The automated trading system does not need a constant flow of real time pricing data to make its' entry decisions.
  - Entry signals will be hard-coded (e.g, daily 0DTE trades on SPX on the 20 delta with $10 wings and a 20% TP)
  - Other trade signals will come from sources outside of the automated trading system. The details of this interface will be designed later, for now suffice to say streaming price data is not needed by the automated trading system.
    - Do we have any need to stream any data ?
    - Are trades entered into synchronously or asynchronously or something else ?

**Story:** Plan decision — streaming explicitly excluded from scope. Order synchronicity validated in TS-0040 (polling loop implementation reveals async/sync behavior).
