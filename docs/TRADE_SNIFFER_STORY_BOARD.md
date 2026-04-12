# Trade Sniffer Story Board

Stories for the `tradier_sniffer` POC CLI app. See `docs/TRADE_SNIFFER_PLAN.md` for the full phased plan and `docs/TRADIER_FAQ.md` for the questions each story is expected to answer.

| Story | Phase | Title | FAQ Questions Addressed | Status |
|---|---|---|---|---|
| TS-0000 | 0 — Foundation | App Scaffold & Environment Validation | — | Done |
| TS-0010 | 1 — Client | Tradier Sandbox Client | Error codes for cancellation/rejection | Done |
| TS-0015 | 1 — Client | API Discovery & Account Data | Security/auth options; exchange routing; account-level restrictions; account data fields (net liq, cash, PDT count, option BP, theta); PDT flag on closed trades; maintenance BPR fields | Done |
| TS-0020 | 2 — Models | Internal Data Models | — | Done |
| TS-0030 | 2 — Persistence | SQLite Persistence Layer | — | Done |
| TS-0040 | 3 — Engine | Polling Loop & Event Detection | Multi-leg fill detection (async vs sync); can we poll; time limit on fill; order synchronicity | Done |
| TS-0050 | 3 — Engine | Trade # Assignment & Order Mapping | Tradier reference # and tagging capability for order-to-trade association | Done |
| TS-0060 | 4 — Reconciliation | Startup Reconciliation | Pending order that filled while offline — how do we detect it on restart | Done |
| TS-0070 | 5 — Demo | Demo CLI & Scenario 1 — Entry Fill | Price improvement visibility; does Tradier return the fill price | Done |
| TS-0080 | 5 — Demo | Scenario 1.5 (Repricing) & Scenario 2 (Multi-leg) | Retry loop that brings entry price down a few pennies | Done |
| TS-0090 | 5 — Demo | Scenario 3 (TP offline) & Scenario 4 (Adjustment) | Can all adjustment orders be placed in a single Day Limit order | Done |
| TS-0095 | 5 — Demo | Edge Case Sandbox Tests | Nickel pricing behavior; option expiration timing; after-hours GTC placement; after-hours/extended hours quotes for stocks | Done |
| TS-0100 | 6 — Polish | Status Command, Observability & README | — | Done |
