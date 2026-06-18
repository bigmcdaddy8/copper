# Holodeck MVP — Implementation Plan

## Context

Holodeck is the simulation broker for the Copper trading system. It implements the Broker Interface Contract (BIC), enabling K9 to run deterministically in a local environment before touching Tradier sandbox or production. The BIC lives in a separate shared package (`apps/bic/`) so both Holodeck and K9 can import it independently.

This plan produces:
- `apps/bic/` — abstract `Broker` class + all normalized data models (shared library, no CLI)
- `apps/holodeck/` — concrete simulation broker with minimal CLI (`holodeck generate-data`, `holodeck run-scenario`)
- `docs/HOLODECK_PLAN.md` + `docs/HOLODECK_STORY_BOARD.md` — plan and story board docs
- `docs/stories/holodeck/HD-0000.md` … `HD-0090.md` — 10 story files

Story prefix: `HD-`, numbered 0000–0090 in steps of 10.

---

## Directory Structures

### `apps/bic/`
```
apps/bic/
├── pyproject.toml           # name="bic", no runtime deps, no CLI entry point
├── src/bic/
│   ├── __init__.py          # re-exports all models + Broker
│   ├── models.py            # 9 @dataclass BIC models
│   └── broker.py            # abstract Broker(ABC) base class
└── tests/
    ├── test_models.py
    └── test_broker.py
```

### `apps/holodeck/`
```
apps/holodeck/
├── pyproject.toml           # deps: typer, rich, bic (workspace sibling)
├── src/holodeck/
│   ├── __init__.py
│   ├── __main__.py          # delegates to cli:app
│   ├── cli.py               # holodeck generate-data, run-scenario
│   ├── config.py            # HolodeckConfig @dataclass
│   ├── clock.py             # VirtualClock
│   ├── market_data.py       # generate_spx_minutes() + MarketDataStore
│   ├── pricing.py           # build_option_chain(), compute_option_price(), compute_delta()
│   ├── ledger.py            # AccountLedger + SimPosition (internal)
│   ├── order_engine.py      # OrderEngine + SimOrder (internal)
│   ├── expiration.py        # ExpirationEngine
│   ├── broker.py            # HolodeckBroker(Broker) + advance_time/reset
│   └── scenarios/
│       ├── __init__.py
│       └── spx_0dte.py      # 7 deterministic scenario functions
└── tests/
    ├── test_smoke.py
    ├── test_clock.py
    ├── test_market_data.py
    ├── test_pricing.py
    ├── test_ledger.py
    ├── test_order_engine.py
    ├── test_expiration.py
    ├── test_broker.py
    └── test_scenarios.py
```

### Synthetic data
`data/holodeck/spx_2026_01_minutes.csv` — at workspace root (committed to git after generation)

---

## Story Map

### Phase 0 — Foundation (BIC Package)

**HD-0000 — BIC Data Models**
- New: `apps/bic/pyproject.toml`, `src/bic/models.py`, `src/bic/__init__.py`, `tests/test_models.py`
- Depends on: nothing
- Models (all `@dataclass`, stdlib only, no Pydantic):
  - `AccountSnapshot(account_id, net_liquidation, available_funds, buying_power)`
  - `Position(symbol, quantity, avg_price, position_type)`
  - `Quote(symbol, last, bid, ask)`
  - `OptionContract(strike, option_type, bid, ask, delta)`
  - `OptionChain(symbol, expiration: date, options: list[OptionContract])` — `field(default_factory=list)`
  - `OrderLeg(action, option_type, strike, expiration: date)`
  - `OrderRequest(symbol, strategy_type, legs: list[OrderLeg], quantity, order_type, limit_price)`
  - `OrderResponse(order_id, status)` — status: `"ACCEPTED"` or `"REJECTED"`
  - `Order(order_id, status, filled_price: float | None, remaining_quantity)` — status: `"OPEN"`, `"FILLED"`, `"CANCELED"`
- Register `apps/bic` in root `pyproject.toml` workspace members
- Acceptance: `uv run pytest apps/bic` green, `from bic.models import AccountSnapshot` works

**HD-0010 — BIC Abstract Broker**
- New: `src/bic/broker.py`, `tests/test_broker.py`
- Modified: `src/bic/__init__.py` to also export `Broker`
- Depends on: HD-0000
- `Broker(ABC)` with 9 `@abstractmethod` methods (full list per BIC spec):
  `get_current_time`, `get_account`, `get_positions`, `get_open_orders`,
  `get_underlying_quote`, `get_option_chain`, `place_order`, `cancel_order`, `get_order`
- Test: `StubBroker` implementing all 9 methods instantiates; `Broker()` raises `TypeError`
- Acceptance: `from bic.broker import Broker` works; cannot instantiate directly

---

### Phase 1 — Virtual Time & Data

**HD-0020 — Holodeck Scaffold & VirtualClock**
- New: full `apps/holodeck/` scaffold, `config.py`, `clock.py`, `tests/test_smoke.py`, `tests/test_clock.py`
- Depends on: HD-0000, HD-0010
- `HolodeckConfig @dataclass`: `starting_datetime`, `ending_datetime`, `timezone="America/Chicago"`, `random_seed=42`, `starting_account_value=100_000.0`, `starting_buying_power=50_000.0`, `underlying_symbol="SPX"`, `price_tick=0.05`, `strike_increment=5.0`, `session_open="09:30"`, `session_close="15:00"`, `data_path="data/holodeck/spx_2026_01_minutes.csv"`
- `VirtualClock(start, session_open, session_close, tz)`:
  - `current_time() -> datetime` (tz-aware, `zoneinfo.ZoneInfo`)
  - `advance(minutes=1) -> None`
  - `advance_to(target: datetime) -> None` — raises `ValueError` if target < current
  - `is_market_open() -> bool` — True during session on weekdays
  - `is_market_day() -> bool` — False Sat/Sun (no holiday calendar in MVP)
  - `session_close_time() -> datetime` — today's close as tz-aware datetime
- CLI: `holodeck generate-data` stub (prints "not yet implemented"), `holodeck --help` works
- Register `apps/holodeck` in root workspace
- 11 clock tests + 1 smoke test; acceptance: `uv run holodeck --help` exits 0

**HD-0030 — Synthetic SPX Data Generator & MarketDataStore**
- New: `market_data.py`, fully implemented `generate-data` CLI command, `tests/test_market_data.py`
- Modified: `cli.py` — `generate-data` fully implemented
- Depends on: HD-0020
- `generate_spx_minutes(seed: int, output_path: str) -> None`:
  - 20 Jan 2026 trading days hardcoded (Jan 2–30, skip weekends + Jan 1 + Jan 19 MLK)
  - 331 bars per day: 09:30–15:00 inclusive (1-min steps)
  - Piecewise random walk: `rng = random.Random(seed + day_index)`, start=open, end=close, drift toward close, `step = rng.gauss(0, 2.0) + drift * 0.1`, clamp `[-15, +15]`, round to 2 decimal places
  - `bid = round(last - 0.05, 2)`, `ask = round(last + 0.05, 2)`
  - CSV columns: `timestamp,last,bid,ask`; timestamps as `"2026-01-02T09:30:00"` (no tz in CSV)
  - Embed fixed daily open/close table as module constant (20 entries, ±2% drift from Jan 2 open ≈ 5825)
- `MarketDataStore(csv_path)`:
  - `load() -> None` — reads CSV into `dict[str, tuple[float,float,float]]` keyed by ISO timestamp string; raises `FileNotFoundError` if missing
  - `get_quote(dt: datetime) -> Quote` — strips seconds, looks up, raises `KeyError` if not found
  - `get_daily_close(trade_date: date) -> float` — returns last for 15:00 bar
  - `is_loaded() -> bool`
- CLI `generate-data` accepts `--output PATH` (default `data/holodeck/spx_2026_01_minutes.csv` relative to cwd); creates parent dirs; prints progress
- 12 tests (determinism, row count = 6620, bid/ask spread, store load/query)
- Acceptance: CSV has exactly 6621 lines; two runs produce identical file; `uv run holodeck generate-data` exits 0

---

### Phase 2 — Option Pricing

**HD-0040 — Synthetic Option Pricing & Delta Model**
- New: `pricing.py`, `tests/test_pricing.py`
- Depends on: HD-0030
- `build_option_chain(underlying, expiration, virtual_now, iv_base=0.20) -> OptionChain`:
  - Strikes: `underlying ± 150` in 5-point increments (61 strikes × 2 types = 122 contracts)
  - Returns `OptionChain(symbol="SPX", expiration=expiration, options=[...])`
- `compute_option_price(underlying, strike, option_type, minutes_to_close, iv_base) -> tuple[float, float]`:
  - `intrinsic = max(0, underlying-strike)` (CALL) / `max(0, strike-underlying)` (PUT)
  - `time_factor = max(0, minutes_to_close / 390.0)`
  - `extrinsic = iv_base * underlying * time_factor * exp(-moneyness_distance / (underlying * 0.02))`
  - `mid = round((intrinsic + extrinsic) / 0.05) * 0.05`
  - `bid = max(0.05, mid - 0.05)`, `ask = mid + 0.05`
- `compute_delta(underlying, strike, option_type, minutes_to_close) -> float`:
  - Sigmoid: `moneyness = (underlying - strike) / underlying * 100`
  - `time_factor = max(0.1, minutes_to_close / 390.0)`
  - `raw = 1 / (1 + exp(-moneyness / (time_factor * 5.0)))`
  - CALL: `round(raw, 2)` clamped `[0.01, 0.99]`; PUT: `round(raw - 1.0, 2)` clamped `[-0.99, -0.01]`
- `minutes_until_close(virtual_now, session_close="15:00") -> int`
- Key requirement: chain must have ≥1 put with `-0.25 ≤ delta ≤ -0.15` and ≥1 call with `0.15 ≤ delta ≤ 0.25`
- 14 tests (strike count, delta properties, price monotonicity, nickel tick, time decay)
- Acceptance: all prices multiples of 0.05; 20-delta put and call exist; `math` stdlib only (no numpy)

---

### Phase 3 — Account & Orders

**HD-0050 — AccountLedger**
- New: `ledger.py`, `tests/test_ledger.py`
- Depends on: HD-0000, HD-0020
- `SimPosition @dataclass` (internal, NOT a BIC model): `order_id, symbol, strategy_type, quantity, entry_credit, entry_time, expiration, legs: list[OrderLeg], max_loss, status="OPEN"`
- `AccountLedger(config: HolodeckConfig)`:
  - `get_snapshot() -> AccountSnapshot` — `account_id="holodeck-sim"`
  - `get_positions() -> list[Position]` — only OPEN SimPositions as BIC `Position` objects
  - `open_position(order_id, order, entry_credit, entry_time) -> None` — computes max_loss = `(wing_size - entry_credit) * 100 * qty`; reduces buying_power
  - `close_position(order_id, exit_debit, close_time) -> None` — marks CLOSED, releases buying_power, updates realized_pnl and net_liquidation
  - `expire_position(order_id, final_underlying, close_time) -> None` — computes intrinsic per leg, calls `close_position` internally
  - `has_position_for(symbol) -> bool`
  - `get_sim_positions() -> list[SimPosition]` (all statuses)
  - `get_open_sim_positions() -> list[SimPosition]` (OPEN only)
- 12 tests (initial state, open/close buying power, P&L profit/loss, expiry OTM/ITM)
- Acceptance: buying power releases after close; `get_positions()` returns BIC `Position` objects

**HD-0060 — OrderEngine**
- New: `order_engine.py`, `tests/test_order_engine.py`
- Depends on: HD-0040, HD-0050
- `SimOrder @dataclass` (internal): `order_id, request, status, submitted_at, filled_at=None, filled_price=None, remaining_quantity`
- `OrderEngine(ledger, market_data, clock, config)`:
  - `submit_order(request) -> OrderResponse`:
    - Reject if: not market open, existing position for symbol, `order_type != "LIMIT"`, insufficient buying power
    - Accept: `order_id = f"HD-{n:06d}"`, store `SimOrder(status="OPEN")`
  - `evaluate_orders() -> list[str]` — for each OPEN order, compute combo bid/ask via `build_option_chain`; fill credit orders if `combo_bid >= limit_price`; fill TP orders if `combo_ask_to_close <= limit_price`; call `ledger.open_position()` or `ledger.close_position()`; return filled IDs
  - `cancel_order(order_id) -> None` — sets CANCELED; no-op if already FILLED
  - `get_order(order_id) -> Order` — returns BIC `Order`; `KeyError` if unknown
  - `get_open_orders() -> list[Order]`
  - Fill detection: entry order = mixed BUY/SELL legs (credit); TP order = `strategy_type` contains `"TP"` or all BUY legs (debit)
  - Combo bid: `sum(sell_leg.bid) - sum(buy_leg.ask)`; combo ask-to-close: `sum(original_sell_leg.ask) - sum(original_buy_leg.bid)`
- 14 tests covering accept/reject, sequential IDs, fill/no-fill, cancel, open order list
- Acceptance: `get_order()` returns BIC `Order`; fills update ledger positions

---

### Phase 4 — Expiration & Wire-Up

**HD-0070 — ExpirationEngine**
- New: `expiration.py`, `tests/test_expiration.py`
- Depends on: HD-0050, HD-0060
- `ExpirationEngine(ledger, market_data, clock)`:
  - `run_expiration() -> list[str]` — at market close, for each OPEN SimPosition expiring today: get `get_daily_close()`, call `ledger.expire_position()`, collect order_ids
  - `should_run() -> bool` — True if `current_time >= session_close_time` AND open positions expiring today exist
- 8 tests (no positions, OTM/ITM expiry, future-expiry not touched, buying power released, should_run logic)
- Acceptance: ITM expiry reduces net_liquidation; OTM expiry restores buying_power fully

**HD-0080 — HolodeckBroker (BIC Wire-Up)**
- New: `broker.py`, `tests/test_broker.py`
- Depends on: HD-0020 through HD-0070
- `HolodeckBroker(Broker)`:
  - Constructor instantiates all 5 components from `HolodeckConfig`; calls `market_data.load()`
  - Implements all 9 BIC interface methods
  - `get_underlying_quote(symbol)`: validates `symbol == "SPX"`, raises `ValueError` otherwise
  - `get_option_chain(symbol, expiration)`: calls `build_option_chain` with current quote + virtual time
  - Simulation control (not in BIC interface):
    - `advance_time(minutes=1) -> list[str]` — advance clock, evaluate orders, run expiration if needed, return filled IDs
    - `advance_to_close() -> list[str]` — advance until `current_time >= session_close_time`, accumulate filled IDs
    - `reset(config) -> None` — reinitialize all components (for multi-scenario test runs)
- 13 integration tests including full IC lifecycle (entry → fill → TP fill) and expiration scenario
- Acceptance: `isinstance(broker, Broker)` is True; full lifecycle test passes end-to-end

---

### Phase 5 — Deterministic Test Scenarios

**HD-0090 — Deterministic Test Scenarios**
- New: `scenarios/__init__.py`, `scenarios/spx_0dte.py`, `tests/test_scenarios.py`
- Modified: `cli.py` — add `holodeck run-scenario --name <name>` command
- Depends on: HD-0080
- 7 scenario functions in `scenarios/spx_0dte.py` (each takes `HolodeckBroker`, returns `dict`):
  1. `scenario_immediate_fill` — low limit_price fills on first `advance_time()`
  2. `scenario_no_fill_timeout` — impossibly high credit, advance 60 steps, cancel → `filled=False`
  3. `scenario_entry_then_tp` — entry fills, TP at 50% credit fills → both True
  4. `scenario_entry_expire_profit` — far OTM IC expires worthless → `pnl_positive=True`
  5. `scenario_entry_expire_loss` — near-ATM IC, close ITM → `max_loss_realized=True`
  6. `scenario_account_minimum_block` — drain buying power, attempt order → `REJECTED`
  7. `scenario_existing_position_block` — fill first IC, attempt second IC same symbol → `REJECTED`
- `holodeck run-scenario --name <scenario>` command: instantiates broker from default config, runs scenario, prints result dict via Rich, exits 0/1
- Note: if `submit_order` buying-power check not added in HD-0060, add it here before testing scenario 6
- 8 tests (7 scenario functions + 1 CLI subprocess test)
- Acceptance: all 7 scenarios pass with deterministic seed 42; full suite green

---

## Supporting Docs to Create

**`docs/HOLODECK_PLAN.md`** — mirrors format of `docs/TRADE_SNIFFER_PLAN.md`:
- Context, phase table, directory structures, pyproject.toml deps, verification commands

**`docs/HOLODECK_STORY_BOARD.md`** — mirrors format of `docs/TRADE_SNIFFER_STORY_BOARD.md`:
- Table: Story | Phase | Title | Status (all `Pre-Approved` initially)

Story files go in `docs/stories/holodeck/HD-0000.md` through `HD-0090.md`.

---

## pyproject.toml Dependencies

**`apps/bic/pyproject.toml`** — no runtime deps (stdlib only), `dev = ["pytest>=8"]`

**`apps/holodeck/pyproject.toml`** — `dependencies = ["typer>=0.12", "rich>=13", "bic"]`, no httpx/pandas/python-dotenv, `dev = ["pytest>=8"]`

Both use `hatchling>=1.24` build backend.

---

## Verification (end-to-end)

```bash
uv sync --all-groups --all-packages
uv run pytest apps/bic                         # HD-0000, HD-0010
uv run pytest apps/holodeck                    # all holodeck stories
uv run ruff check apps/bic apps/holodeck
uv run holodeck generate-data                  # creates data/holodeck/spx_2026_01_minutes.csv
uv run holodeck run-scenario --name immediate-fill
uv run holodeck run-scenario --name no-fill-timeout
uv run holodeck run-scenario --name entry-expire-profit
```
