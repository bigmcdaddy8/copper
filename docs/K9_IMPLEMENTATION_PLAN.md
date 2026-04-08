# K9 High-Level Implementation Plan

## Context

K9 is the second major application in the Copper project. Where `trade_hunter` generates
*ranked candidate lists* for a human to review, K9 is an *automated executor* — it reads
a JSON trade spec, validates market conditions, and places a live (or sandbox) multi-leg
options order via the Tradier API. It is designed for 0DTE, defined-risk strategies on
cash-settled indices (SPX, XSP, NDX, RUT).

The MVP is intentionally constrained: single contract, no adjustments, no stop-loss, hold to
expiration or TP, one position per underlying at a time.

---

## Architecture Decisions (confirmed with user)

| Decision | Choice |
|---|---|
| Tradier client | Duplicated in K9 (`apps/K9/src/K9/tradier/client.py`) — same pattern as trade_hunter, adds order/account methods |
| CLI commands | `enter` only for MVP |
| Trade spec location | `apps/K9/trade_specs/` (version-controlled) |
| Story tracking | Separate `docs/K9_STORY_BOARD.md`, stories in `docs/stories/K9/` |

---

## App Directory Structure

```
apps/K9/
├── src/K9/
│   ├── __init__.py
│   ├── __main__.py           # Delegates to cli:app
│   ├── cli.py                # Typer: K9 enter --trade-spec <name>
│   ├── config.py             # TradeSpec dataclass (loaded from JSON)
│   │
│   ├── tradier/
│   │   ├── __init__.py
│   │   ├── client.py         # TradierClient — read + account + order methods
│   │   └── selector.py       # Delta-based strike selection (IC / PCS / CCS)
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── runner.py         # 15-step execution orchestration
│   │   ├── constructor.py    # Build multi-leg trade from selected strikes
│   │   ├── validator.py      # Pre-trade checks (credit, combo spread, risk)
│   │   └── order.py          # Place order, poll fill, cancel, place TP
│   │
│   └── output/
│       ├── __init__.py
│       └── run_log.py        # Per-execution structured log file
│
├── trade_specs/
│   └── spx_ic_20d_w5_tp34_0900.json   # Example/starter spec
│
├── tests/
│   └── test_smoke.py         # (grows per story)
│
└── pyproject.toml
```

---

## Environment Variables

| Variable | Required | Purpose |
|---|---|---|
| `TRADIER_API_KEY` | Yes (production) | Live brokerage API token |
| `TRADIER_SANDBOX_API_KEY` | Yes (sandbox) | Paper-trading API token |
| `TRADIER_ACCOUNT_ID` | Yes | Brokerage account ID (required for orders/positions) |

The `environment` field in the trade spec (`"sandbox"` / `"production"`) controls which key and
base URL is used at runtime.

---

## Story Map

### Phase 0 — Project Foundation
| Story | Title |
|---|---|
| K9-0000 | App Scaffold |

### Phase 1 — CLI & Trade Spec Loading
| Story | Title |
|---|---|
| K9-0010 | `enter` Command Scaffold + TradeSpec JSON Loading |

### Phase 2 — Tradier API Client
| Story | Title |
|---|---|
| K9-0020 | Tradier Read Client (chain, expirations, last price) |
| K9-0030 | Account & Order Methods (balances, positions, place, status, cancel) |

### Phase 3 — Trade Construction
| Story | Title |
|---|---|
| K9-0040 | Delta-Based Strike Selection (IC, PCS, CCS + wing sizing) |
| K9-0050 | Trade Constructor & Pre-Trade Validator |

### Phase 4 — Execution Engine
| Story | Title |
|---|---|
| K9-0060 | Entry Execution (place limit @ mid, poll fill, timeout + cancel) |
| K9-0070 | Take Profit Order Placement |

### Phase 5 — Output
| Story | Title |
|---|---|
| K9-0080 | Run Log (per-execution log file) |

### Phase 6 — Integration & Polish
| Story | Title |
|---|---|
| K9-0090 | End-to-End Integration + Guard Rails |
| K9-0100 | README & Example Trade Specs |

Total: **11 stories** across 7 phases.

---

## Key Module Details

### `config.py` — TradeSpec
Loaded from a JSON file at `apps/K9/trade_specs/<name>.json`. Represented as a dataclass
(not Pydantic — consistent with trade_hunter). Validated manually on load.

Fields mirror the spec schema in `K9_PROGRAM_INTENT.md`.

### `tradier/client.py` — TradierClient
Follows trade_hunter's adaptive rate-limit pattern.

**Read methods (same as trade_hunter):**
- `get_option_expirations(symbol)` → `list[str]`
- `get_last_price(symbol)` → `float`
- `get_option_chain(symbol, expiration)` → `list[dict]`

**New methods for K9:**
- `get_account_balances()` → `dict`
- `get_positions()` → `list[dict]`
- `place_combo_order(account_id, legs, price, duration)` → `str` (order ID)
- `get_order_status(account_id, order_id)` → `dict`
- `cancel_order(account_id, order_id)` → `bool`

### `tradier/selector.py` — Strike Selection
Delta-based, no IV-based selection in MVP.

- `select_0dte_expiration(expirations)` → `str` (today's expiration)
- `select_short_put(chain, target_delta)` → `dict`
- `select_short_call(chain, target_delta)` → `dict`
- `select_long_put(chain, short_strike, wing_size)` → `dict`
- `select_long_call(chain, short_strike, wing_size)` → `dict`

### `engine/runner.py` — Execution Flow
15-step linear sequence (not a data pipeline like trade_hunter):

```
1.  Load trade spec from JSON
2.  Validate spec schema
3.  Verify spec is enabled
4.  Verify account minimum (get_account_balances)
5.  Check existing positions (one per underlying)
6.  Pull option expirations — select 0DTE expiration
7.  Pull option chain
8.  Select strikes (delta-based)
9.  Construct multi-leg trade
10. Validate trade (min credit, combo bid/ask width, max risk)
11. Submit limit order at mid price
12. Poll order status up to max_fill_time_seconds
13. On fill → place GTC take-profit order
14. On timeout → cancel order
15. Write run log
```

### `engine/validator.py` — Pre-Trade Checks
- `check_minimum_credit(net_credit, minimum)` — net credit across all 4 legs
- `check_combo_spread(legs)` — sum of all leg bid/ask spreads ≤ max_combo_bid_ask_width
- `check_max_risk(max_loss, max_allowed)` — max_loss = (wing_size × 100) - net_credit × 100

### `output/run_log.py`
Mirrors trade_hunter's `run_log.py` pattern. Logs:
- Trade spec name + environment
- Timestamp
- Selected strikes + expiration
- Net credit at entry attempt
- Order ID + fill status
- TP order placement (or cancellation reason)

---

## Patterns Reused from trade_hunter

| Pattern | Source |
|---|---|
| Typer + Rich CLI structure | `apps/trade_hunter/src/trade_hunter/cli.py` |
| `@dataclass` config | `apps/trade_hunter/src/trade_hunter/config.py` |
| Adaptive rate-limit throttling | `apps/trade_hunter/src/trade_hunter/tradier/client.py` |
| Run log accumulator | `apps/trade_hunter/src/trade_hunter/output/run_log.py` |
| `subprocess.run` smoke tests | `apps/trade_hunter/tests/test_smoke.py` |
| `python-dotenv` env loading | `apps/trade_hunter/src/trade_hunter/cli.py` |

---

## Dependencies (`pyproject.toml`)

```toml
dependencies = [
  "typer>=0.12",
  "rich>=13",
  "python-dotenv>=1.0",
  "httpx>=0.27",
]
```

No pandas or openpyxl — K9 processes single trades, not tabular datasets.

---

## Verification (end-to-end)

```bash
uv run pytest apps/K9              # all tests pass
uv run ruff check apps/K9
uv run ruff format --check apps/K9
uv run K9 enter --help             # exits 0, shows all options
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_0900  # sandbox run
```

---

## Notes / Open Questions

1. **TP order type**: GTC limit order where limit = net_credit × (1 - take_profit_percent/100) — confirm
2. **Cron integration**: Scripts (`scripts/K9_enter.sh`) are out of scope for stories but can be
   added as a backlog item after integration story
3. **TRADIER_ACCOUNT_ID**: needs to be added to `.env.example` and documented
