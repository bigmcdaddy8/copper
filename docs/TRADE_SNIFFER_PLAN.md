# Plan: `tradier_sniffer` — Iterative MVP Development

**`tradier_sniffer` is a new POC CLI app** under `apps/tradier_sniffer/` that validates the Tradier sandbox API can support automated trading and journaling. It uses a polling loop, SQLite state, and dedicated CLI demo sub-commands to prove each MVP scenario. Stories are tracked in `docs/TRADE_SNIFFER_STORY_BOARD.md` with files under `docs/stories/trade_sniffer/TS-XXXX.md`.

---

## Phase 0 — Foundation
| Story | Title |
|---|---|
| TS-0000 | App Scaffold & Environment Validation |

- Mirror `trade_hunter` structure under `apps/tradier_sniffer/`
- Entry point: `tradier_sniffer = "tradier_sniffer.cli:app"`
- Dependencies: `typer`, `rich`, `python-dotenv`, `httpx` (stdlib SQLite)
- Smoke test: `tradier_sniffer --help` exits 0; `uv sync`, `ruff check`, `pytest` all green

---

## Phase 1 — Tradier Sandbox Client
| Story | Title |
|---|---|
| TS-0010 | Tradier Sandbox Client |

- New `tradier_client.py` module — Bearer auth from `TRADIER_SANDBOX_API_KEY` env var (`.env` file, same pattern as trade_hunter)
- Endpoints: `GET /user/profile`, `GET /accounts/{id}/orders`, `GET /accounts/{id}/positions`
- Respects `X-Ratelimit-Available` headers (60 req/min sandbox limit)
- `config.py` — `SnifferConfig` dataclass (`api_key`, `account_id`, `poll_interval`)
- Tests: mock `httpx` responses

---

## Phase 2 — Data Models & Persistence
| Story | Title |
|---|---|
| TS-0020 | Internal Data Models |
| TS-0030 | SQLite Persistence Layer |

- **TS-0020** — `models.py`: `Order`, `Position`, `Trade`, `TradeOrderMap`, `EventLog` dataclasses
  - `Trade.trade_id` uses `TRDS_{#####}_{TTT}` format (e.g., `TRDS_00001_NPUT`)
  - `EventLog`: timestamp, event_type (`new_order` / `filled` / `closed` / `canceled`), order_id, trade_id, details
- **TS-0030** — `db.py`: SQLite tables (`trades`, `orders`, `trade_order_map`, `event_log`, `poll_state`); CRUD operations; default DB path `./tradier_sniffer.db`
- Tests: in-memory SQLite

---

## Phase 3 — Core Engine *(depends on Phases 1 & 2)*
| Story | Title |
|---|---|
| TS-0040 | Polling Loop & Event Detection |
| TS-0050 | Trade # Assignment & Order Mapping |

- **TS-0040** — `engine.py`: `poll()` fetches broker data, diffs against last known state, detects events (new order, filled, canceled, position closed), persists to `EventLog`; `tradier_sniffer poll` command with `--interval` flag
- **TS-0050** — `assign_trade()` logic: group multi-leg orders by Tradier grouping/tag field (falling back to symbol + timestamp proximity); infer TTT from leg count/type (SIC=4 legs, PCS=2-leg put spread, NPUT=1-leg put, etc.); sequential Trade # counter from DB

---

## Phase 4 — Reconciliation *(depends on Phase 3)*
| Story | Title |
|---|---|
| TS-0060 | Startup Reconciliation |

- On startup: reload DB state → fetch fresh broker data → detect missed events (orders not in local DB, status changes) → replay chronologically → log reconciliation summary
- Tests: simulate restart after GTC TP fired; verify closed trade is detected and Trade # updated

---

## Phase 5 — Demo Scenarios as CLI Commands *(parallel after Phase 4)*
| Story | Title |
|---|---|
| TS-0070 | Demo CLI & Scenario 1 — Entry Fill |
| TS-0080 | Scenario 1.5 (Repricing) & Scenario 2 (Multi-leg) |
| TS-0090 | Scenario 3 (TP offline) & Scenario 4 (Adjustment) |

- `tradier_sniffer demo scenario1` — place a Day STO Limit order in sandbox, poll until filled, print assigned Trade #
- `tradier_sniffer demo scenario1_5` — place order, client-timeout, cancel, reprice, re-enter
- `tradier_sniffer demo scenario2` — place a 2-leg PCS, verify grouped into one Trade #
- `tradier_sniffer demo scenario3` — place trade + GTC TP, stop polling (simulate offline), restart, verify reconciliation detects the TP closure
- `tradier_sniffer demo scenario4` — place trade, execute BTC+STO adjustment, verify associated to existing Trade #
- Each scenario lives under `src/tradier_sniffer/demo/scenarioX.py`

---

## Phase 6 — Polish & Docs *(depends on Phase 5)*
| Story | Title |
|---|---|
| TS-0100 | Status Command, Observability & README |

- `tradier_sniffer status` — Rich table of open trades + recent events from DB
- `tradier_sniffer reset --confirm` — clears local DB
- `apps/tradier_sniffer/README.md` — setup, env vars, all commands, demo scenarios

---

## New Files Created

| Path | Purpose |
|---|---|
| `apps/tradier_sniffer/pyproject.toml` | App definition, deps, entry point |
| `apps/tradier_sniffer/src/tradier_sniffer/{cli,config,models,db,engine,tradier_client}.py` | Core modules |
| `apps/tradier_sniffer/src/tradier_sniffer/demo/scenario{1,1_5,2,3,4}.py` | Scenario runners |
| `apps/tradier_sniffer/tests/test_{smoke,client,models,db,engine,reconciliation}.py` | Tests |
| `docs/TRADE_SNIFFER_STORY_BOARD.md` | Trade sniffer story board |
| `docs/stories/trade_sniffer/TS-0000.md` through `TS-0100.md` | Individual stories |

## Reference Patterns to Reuse
- `apps/trade_hunter/src/trade_hunter/tradier/client.py` — `httpx` + rate limit header pattern
- `apps/trade_hunter/src/trade_hunter/cli.py` — `load_dotenv()`, Typer sub-commands pattern
- `apps/trade_hunter/pyproject.toml` — workspace member pyproject structure

---

## Verification
1. `uv sync --all-groups --all-packages` — workspace resolves cleanly
2. `uv run pytest apps/tradier_sniffer` — all tests green
3. `uv run ruff check apps/tradier_sniffer` — zero lint errors
4. `tradier_sniffer --help` — all sub-commands listed
5. `tradier_sniffer demo scenario1` — executes against sandbox, prints Trade # assignment
6. `tradier_sniffer demo scenario3` — verifies reconciliation detects TP closure after simulated restart

---

## Decisions
- SQLite only; no JSON flat files
- Sandbox only (no production Tradier endpoints)
- Trade # format: `TRDS_{#####}_{TTT}` per GLOSSARY (`TRDS` = Tradier Sandbox)
- EXCLUDED: streaming API, MJ spreadsheet writes, trade signal generation, K9 integration, UI
