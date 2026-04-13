# K9 High-Level Implementation Plan

## Context

K9 is the second major application in the Copper project. Where `trade_hunter` generates
*ranked candidate lists* for a human to review, K9 is an *automated executor* — it reads
a JSON trade spec, validates market conditions, and places a multi-leg options order through
the **Broker Interface Contract (BIC)**. Development and testing use `HolodeckBroker`;
sandbox and live trading use `TradierBroker`. It is designed for 0DTE, defined-risk
strategies on cash-settled indices (SPX, XSP, NDX, RUT).

The MVP is intentionally constrained: single contract, no adjustments, no stop-loss, hold to
expiration or TP, one position per underlying at a time.

---

## Architecture Decisions (confirmed with user)

| Decision | Choice |
|---|---|
| Broker abstraction | K9 engine uses `Broker` ABC from `apps/bic/` — never calls any broker API directly |
| Tradier implementation | `TradierBroker` in `apps/K9/src/K9/tradier/broker.py` implements BIC `Broker` ABC |
| Development/test broker | `HolodeckBroker` from `apps/holodeck/` — local, deterministic, no network required |
| Broker selection | `environment` field in trade spec (`"holodeck"` / `"sandbox"` / `"production"`) |
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
│   ├── broker_factory.py     # Instantiate HolodeckBroker or TradierBroker from trade spec
│   │
│   ├── tradier/
│   │   ├── __init__.py
│   │   ├── broker.py         # TradierBroker — implements BIC Broker ABC (sandbox + production)
│   │   └── selector.py       # Delta-based strike selection (IC / PCS / CCS)
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── runner.py         # 16-step execution orchestration (uses Broker interface)
│   │   ├── constructor.py    # Build multi-leg trade from selected strikes
│   │   ├── validator.py      # Pre-trade checks (credit, combo spread, risk)
│   │   └── order.py          # Place order, poll fill, cancel, place TP (via Broker ABC)
│   │
│   └── output/
│       ├── __init__.py
│       └── run_log.py        # Per-execution structured log file
│
├── trade_specs/
│   └── spx_ic_20d_w5_tp34_0900.json   # Example/starter spec (environment: "holodeck")
│
├── tests/
│   └── test_smoke.py         # (grows per story)
│
└── pyproject.toml
```

---

## Environment Variables

These are only required when `TradierBroker` is in use (`environment: "sandbox"` or
`"production"`).  Running against Holodeck requires no API keys.

| Variable | Required for | Purpose |
|---|---|---|
| `TRADIER_API_KEY` | production | Live brokerage API token |
| `TRADIER_SANDBOX_API_KEY` | sandbox | Paper-trading API token |
| `TRADIER_ACCOUNT_ID` | sandbox + production | Brokerage account ID |

The `environment` field in the trade spec (`"holodeck"` / `"sandbox"` / `"production"`)
controls which `Broker` implementation is instantiated by `broker_factory.py`.

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

### Phase 2 — TradierBroker (BIC Implementation)
| Story | Title |
|---|---|
| K9-0020 | TradierBroker — Market Data Methods (quote, chain, expirations) |
| K9-0030 | TradierBroker — Account & Order Methods (balances, positions, place, status, cancel) |

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

Fields mirror the spec schema in `K9_PROGRAM_INTENT.md`.  The `environment` field
(`"holodeck"` / `"sandbox"` / `"production"`) is read by `broker_factory.py`.

### `broker_factory.py` — Broker Factory
Single function `create_broker(spec: TradeSpec) -> Broker` that returns the appropriate
`Broker` implementation based on `spec.environment`:

- `"holodeck"` → `HolodeckBroker(config)` from `apps/holodeck/`
- `"sandbox"` → `TradierBroker(api_key=TRADIER_SANDBOX_API_KEY, sandbox=True)`
- `"production"` → `TradierBroker(api_key=TRADIER_API_KEY, sandbox=False)`

The runner receives a `Broker` instance and has no further knowledge of which
implementation is in use.

### `tradier/broker.py` — TradierBroker
Implements the BIC `Broker` ABC. Wraps the Tradier REST API for both sandbox and
production environments. Follows trade_hunter's adaptive rate-limit pattern.

**BIC methods implemented:**
- `get_current_time()` → real wall-clock time (CT)
- `get_account()` → `AccountSnapshot` (from Tradier balances endpoint)
- `get_positions()` → `list[Position]`
- `get_open_orders()` → `list[Order]`
- `get_underlying_quote(symbol)` → `Quote`
- `get_option_chain(symbol, expiration)` → `OptionChain`
- `place_order(order)` → `OrderResponse`
- `get_order(order_id)` → `Order`
- `cancel_order(order_id)` → `None`

### `tradier/selector.py` — Strike Selection
Delta-based, no IV-based selection in MVP.  Operates on BIC `OptionChain` /
`OptionContract` objects (not raw Tradier dicts).

- `select_0dte_expiration(expirations)` → `date` (today's expiration)
- `select_short_put(chain, target_delta)` → `OptionContract`
- `select_short_call(chain, target_delta)` → `OptionContract`
- `select_long_put(chain, short_strike, wing_size)` → `OptionContract`
- `select_long_call(chain, short_strike, wing_size)` → `OptionContract`

### `engine/runner.py` — Execution Flow
16-step linear sequence (not a data pipeline like trade_hunter).  All broker calls
go through the `Broker` ABC — the runner never imports `TradierBroker` or
`HolodeckBroker` directly.

```
1.  Load trade spec from JSON
2.  Validate spec schema
3.  Verify spec is enabled
4.  Instantiate Broker via broker_factory.create_broker(spec)
5.  Verify current time vs allowed window — broker.get_current_time()
6.  Verify account minimum — broker.get_account()
7.  Check existing positions — broker.get_positions()
8.  Pull underlying quote — broker.get_underlying_quote(symbol)
9.  Pull option chain — broker.get_option_chain(symbol, expiration)
10. Select strikes (delta-based, using selector.py)
11. Construct multi-leg OrderRequest
12. Validate trade (min credit, combo bid/ask width, max risk)
13. Submit limit order — broker.place_order(order)
14. Poll order status — broker.get_order(order_id) loop ≤ max_fill_time_seconds
15. On fill → place GTC take-profit order — broker.place_order(tp_order)
16. On timeout → cancel — broker.cancel_order(order_id)
17. Write run log
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
| Adaptive rate-limit throttling | `apps/trade_hunter/src/trade_hunter/tradier/client.py` (internal to `TradierBroker`) |
| Run log accumulator | `apps/trade_hunter/src/trade_hunter/output/run_log.py` |
| `subprocess.run` smoke tests | `apps/trade_hunter/tests/test_smoke.py` |
| `python-dotenv` env loading | `apps/trade_hunter/src/trade_hunter/cli.py` |

**Key difference from trade_hunter:** trade_hunter calls Tradier endpoints directly.
K9's engine calls `Broker` ABC methods only — Tradier-specific code is isolated inside
`TradierBroker`, and Holodeck is the default development target.

---

## Dependencies (`pyproject.toml`)

```toml
dependencies = [
  "typer>=0.12",
  "rich>=13",
  "python-dotenv>=1.0",
  "httpx>=0.27",
  "bic",
]
```

`bic` is the shared Broker Interface Contract package (`apps/bic/`), referenced via
`[tool.uv.sources] bic = { workspace = true }`.

`holodeck` is a dev/test dependency (used only when `environment = "holodeck"`);
it can be added under `[dependency-groups] dev` or pulled in through the workspace.

No pandas or openpyxl — K9 processes single trades, not tabular datasets.

---

## Verification (end-to-end)

```bash
uv run pytest apps/K9              # all tests pass
uv run ruff check apps/K9
uv run ruff format --check apps/K9
uv run K9 enter --help             # exits 0, shows all options

# Development run — no API keys required (uses HolodeckBroker)
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_0900  # environment: "holodeck"

# Sandbox run — requires TRADIER_SANDBOX_API_KEY + TRADIER_ACCOUNT_ID in .env
# (trade spec must have environment: "sandbox")
uv run K9 enter --trade-spec spx_ic_20d_w5_tp34_0900_sandbox
```

---

## Notes / Open Questions

1. **TP order type**: GTC limit order where limit = net_credit × (1 - take_profit_percent/100) — confirm
2. **Cron integration**: Scripts (`scripts/K9_enter.sh`) are out of scope for stories but can be
   added as a backlog item after integration story
3. **TRADIER_ACCOUNT_ID**: needs to be added to `.env.example` and documented
4. **Holodeck HolodeckConfig for K9**: When `environment = "holodeck"`, `broker_factory.py`
   needs to decide `starting_datetime` / `ending_datetime` / `data_path`.  For integration
   tests, reasonable defaults are today's date at market open/close with the standard
   `data/holodeck/spx_2026_01_minutes.csv` path.
5. **Patterns from trade_hunter vs BIC**: `TradierBroker` replaces `TradierClient` for all
   market data and order operations.  `selector.py` takes BIC `OptionChain` objects rather
   than raw Tradier dicts — this is the key interface change from trade_hunter's pattern.
