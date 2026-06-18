# Plan: Map TRADIER_FAQ.md Questions to Trade Sniffer Stories

## Context

`TRADIER_FAQ.md` contains ~19 open questions about how the Tradier API behaves during automated trading. The `TRADE_SNIFFER_PLAN.md` defines stories TS-0000 through TS-0100 but does not explicitly assign FAQ questions to stories. The goal is to ensure every FAQ question is either answered by documentation research or demonstrated/validated via a specific story so no question falls through the cracks.

---

## FAQ → Story Mapping Analysis

### Already covered by existing stories

| FAQ Question | Story | Notes |
|---|---|---|
| Multi-leg fill detection — async/sync? Can we poll? | TS-0040 | Polling loop detects `pending→filled` transitions |
| Can we place a time limit on the fill? | TS-0040 | Day Limit order type handles this |
| Retry loop bringing price down a few pennies | TS-0080 (Scenario 1.5) | Demo: cancel + reprice cycle |
| Associate multi-leg orders to Trade # (Tradier tag/grouping field?) | TS-0050 | `assign_trade()` uses Tradier tag/grouping field |
| After downtime: pending order that filled while offline | TS-0060 | Startup reconciliation detects missed fills |
| Can adjustment orders be grouped into single Day Limit? | TS-0090 (Scenario 4) | Demo: BTC+STO adjustment mapping |
| Do we need streaming data? | Plan decision | Explicitly excluded from scope |

### Gaps — not covered by any existing story

| FAQ Question | Proposed Coverage | Story |
|---|---|---|
| Account information fields: net liq, cash, PDT count, option BP, beta-delta, theta, transactions | TS-0015 ✓ | `total_equity`, `total_cash`, `margin.option_buying_power` confirmed; `day_trader` boolean in `/v1/user/profile` confirmed; rolling PDT count, beta-delta, theta are gaps (local calc needed) |
| What security is available (OAuth, 2FA, IP whitelisting)? | TS-0015 ✓ | Long-lived API token recommended for automation; OAuth requires interactive login; no IP whitelisting |
| Exchange routing options — is BEST available? | TS-0015 ✓ | No exchange routing param — Tradier auto-routes via NBBO smart routing |
| Account-level restrictions (max trade size, max BPR, max trades)? | TS-0015 ✓ | Gap — no API controls; must be enforced in application logic |
| Is there a PDT flag on closed trade data? | TS-0015 ✓ | `day_trader` boolean confirmed in `/v1/user/profile` (account-level designation flag); no per-trade/per-close PDT flag in orders/positions |
| Maintenance BPR for multi-leg trade? | TS-0015 ✓ | `margin.maintenance_call` available at account level; per-leg BPR not surfaced — must be calculated locally |
| Error codes for cancellation/rejection? | TS-0010 ✓ | `ORDER_STATUSES` + `REJECTION_REASONS` dicts in `tradier_client.py`; `**Answer:**` added to `TRADIER_FAQ.md` |
| Nickel pricing: what happens when penny limit placed on nickel option? | New story TS-0095 | Sandbox test: place bad-priced order, observe rejection/behavior |
| Price improvement: does Tradier return better fill price? | TS-0070 (Scenario 1) | Observe fill price vs limit price in demo run; document finding |
| Option expiration timing: when does expired status appear? | New story TS-0095 | Sandbox test or Tradier docs research |
| After-hours TP placement: can GTC BTC be placed/adjusted after hours? | New story TS-0095 | Sandbox test |
| After-hours/extended hours pricing for stocks? | New story TS-0095 | Tradier docs research |
| Dividend payment: what does it look like via API for a CCALL? | Defer / document as out-of-MVP-scope | Note in FAQ |

---

## Proposed New Stories

### TS-0015 — API Discovery & Account Data
**Phase**: After TS-0010 (uses the client)  
**Goal**: Answer documentation-researchable questions by reading Tradier API docs and exercising account/user endpoints in sandbox.

Tasks:
- Read Tradier API docs and document answers for: security options, exchange routing, account-level restrictions, available account data fields, PDT flag, BPR fields
- Call `GET /user/profile`, `GET /accounts/{id}/balances`, `GET /accounts/{id}/history` in sandbox
- Add a `tradier_sniffer discover` CLI sub-command that prints a structured summary of available account data fields
- Document answers inline in `TRADIER_FAQ.md` (add **Answer:** lines to each applicable question)

### TS-0095 — Edge Case Sandbox Tests
**Phase**: After TS-0070 (uses working demo infrastructure)  
**Goal**: Answer questions that require live sandbox experiments.

Tasks:
- **Nickel pricing**: place a penny-priced limit order on a nickel-only option; observe and document broker response
- **Option expiration timing**: place 0DTE order near expiry; poll for expiration status; record timestamp delta
- **After-hours TP**: attempt to place/modify GTC order after market close; document behavior
- **After-hours pricing**: call quotes endpoint after hours on a stock; document response
- Add `tradier_sniffer demo edge_cases` CLI sub-command that runs each test sequentially and prints results
- Document answers inline in `TRADIER_FAQ.md`

---

## Changes Required

### 1. `docs/TRADE_SNIFFER_PLAN.md`
- Add TS-0015 row to Phase 1 table (after TS-0010)
- Add TS-0095 row to Phase 5 table (after TS-0090)
- Add both to the New Files Created table

### 2. `docs/TRADE_SNIFFER_STORY_BOARD.md`
- Add TS-0015 and TS-0095 rows with their FAQ coverage noted

### 3. `docs/TRADIER_FAQ.md`
- Add a `**Story:** TS-XXXX` line directly after each question block indicating which story will answer it
- This creates a visible traceability link as stories get implemented

### 4. New story files
- `docs/stories/trade_sniffer/TS-0015.md` — API Discovery & Account Data
- `docs/stories/trade_sniffer/TS-0095.md` — Edge Case Sandbox Tests

---

## FAQ Questions Explicitly Deferred (out of MVP scope)
- Dividend/CCALL API behavior — requires real account with dividend-paying stock position; note in FAQ as deferred
- Order synchronicity (async vs sync) — answered by TS-0040 observation during implementation

---

## Verification
1. Every FAQ question in `TRADIER_FAQ.md` has a `<!-- Story: ... -->` annotation
2. `TRADE_SNIFFER_PLAN.md` includes TS-0015 and TS-0095
3. `TRADE_SNIFFER_STORY_BOARD.md` lists all stories with FAQ coverage column
4. No FAQ question is left without either a story assignment or an explicit "deferred/out-of-scope" note

