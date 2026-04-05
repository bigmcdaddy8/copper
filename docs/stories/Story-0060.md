# Story-0060 — Tradier API Client

**Status**: Completed  
**Phase**: 3 — Tradier API Integration

---

## Goal

Build the `TradierClient` — a thin, tested HTTP client that handles authentication, environment
selection (production vs. sandbox), and rate-limit awareness. This story establishes the
credential storage pattern and the two API methods needed by Story-0070. No real API calls are
made during tests.

---

## Background

From `docs/PROJECT_INTENT.md`:

> The implementation must respect Tradier rate limits and throttle or queue requests as needed.
> Rate-limit headers returned by Tradier should be used when practical.

From `docs/TRADIER_DOCUMENTATION.md`:
- Production base URL: `https://api.tradier.com/v1/`
- Sandbox base URL: `https://sandbox.tradier.com/v1/`
- Rate limit: 120 req/min (production) / 60 req/min (sandbox) for market data
- Rate limit headers: `X-Ratelimit-Available`, `X-Ratelimit-Expiry`

---

## Credential Storage Recommendation

**Use a `.env` file at the workspace root. Never commit it.**

### Why this approach

`python-dotenv` is already a project dependency and `load_dotenv()` is already called in
`cli.py`. A single `.env` file at the workspace root (`/home/temckee8/Documents/REPOs/copper/`)
is the simplest secure pattern — it loads once, never touches the repo, and is easily shared
via a password manager or secure note rather than version control.

### Action required before implementation begins

`.env` is **not currently listed in `.gitignore`**. This story adds it. Until that change is
committed, **do not create a `.env` file** with real credentials.

### `.env` file structure (do not commit)

```dotenv
# Tradier — production
TRADIER_API_KEY=your_production_api_key_here

# Tradier — sandbox (for testing)
TRADIER_SANDBOX_API_KEY=your_sandbox_api_key_here

# Active environment: "production" or "sandbox" (default: production)
TRADIER_ENV=production
```

A committed `.env.example` file documents this structure without real values.

### Account IDs

For this project's read-only market data use (options chains, expirations), no account ID is
required by the Tradier API. Account ID fields are omitted from the credential spec.

### Switching to sandbox

Set `TRADIER_ENV=sandbox` in `.env` (or pass `--sandbox` on the CLI). The client automatically
selects the correct base URL and API key. **Recommendation:** validate the sandbox key against
a simple API call (e.g., a quote for SPY) before Story-0070 relies on it.

---

## New Files

| File | Purpose |
|---|---|
| `apps/trade_hunter/src/trade_hunter/tradier/__init__.py` | Empty package marker |
| `apps/trade_hunter/src/trade_hunter/tradier/client.py` | `TradierClient` class |
| `.env.example` | Committed credential template (no real values) |
| `apps/trade_hunter/tests/test_tradier_client.py` | Mock-based unit tests |

## Modified Files

| File | Change |
|---|---|
| `.gitignore` | Add `.env` and `.env.*` (except `.env.example`) |
| `apps/trade_hunter/pyproject.toml` | Add `httpx>=0.27` dependency |
| `apps/trade_hunter/src/trade_hunter/config.py` | Add `sandbox: bool = False` |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Load `TRADIER_ENV`; add `--sandbox` flag; resolve correct API key |

---

## API Methods

The client exposes exactly two methods — the minimum needed for Stories 0070–0080:

```python
class TradierClient:
    def get_option_expirations(self, symbol: str) -> list[str]:
        """Return a list of expiration date strings ("YYYY-MM-DD") for the given symbol.
        Only monthly expirations are requested (includeAllRoots=false, strikes=false).
        """

    def get_option_chain(self, symbol: str, expiration: str) -> list[dict]:
        """Return all option contracts for symbol on the given expiration date.
        Each dict contains at minimum: strike, option_type, delta, bid, ask, open_interest, last.
        """
```

Endpoint mapping:

| Method | Endpoint | Key query params |
|---|---|---|
| `get_option_expirations` | `GET /markets/options/expirations` | `symbol`, `includeAllRoots=false` |
| `get_option_chain` | `GET /markets/options/chains` | `symbol`, `expiration`, `greeks=true` |

---

## Rate-Limit Handling

After every response, the client reads `X-Ratelimit-Available` and `X-Ratelimit-Expiry` from
the response headers and stores them as instance state. Before each request:

1. If `X-Ratelimit-Available <= 5`, sleep until `X-Ratelimit-Expiry` (epoch ms) + 1 second,
   then reset stored state. This prevents hitting the hard limit.
2. After each successful request, sleep `request_delay` seconds (default `0.5`). This avoids
   burst behaviour and keeps the client well within the 2 req/sec sustained rate.

`request_delay` is configurable via the `TradierClient` constructor to allow tests to set it
to `0`.

### `RunConfig` / CLI additions

```python
# config.py
sandbox: bool = False

# cli.py — resolved before constructing RunConfig
# 1. --sandbox flag overrides TRADIER_ENV
# 2. When sandbox=True, load TRADIER_SANDBOX_API_KEY instead of TRADIER_API_KEY
# 3. Fail loudly if the required key for the selected environment is not set
```

---

## Error Handling

| Condition | Behaviour |
|---|---|
| HTTP 4xx / 5xx response | Raise `TradierAPIError(status_code, message)` — caller logs and skips the ticker |
| Network timeout | Raise `TradierAPIError` wrapping the underlying `httpx` exception |
| Empty expirations list | Return `[]` (caller handles as "no valid expiration found") |
| Empty options chain | Return `[]` (caller handles as "no qualifying option found") |

`TradierAPIError` is a simple project-defined exception in `tradier/client.py`.

---

## Function / Class Signatures

```python
# tradier/client.py

class TradierAPIError(Exception):
    def __init__(self, status_code: int, message: str): ...

class TradierClient:
    def __init__(
        self,
        api_key: str,
        sandbox: bool = False,
        request_delay: float = 0.5,
    ): ...

    def get_option_expirations(self, symbol: str) -> list[str]: ...
    def get_option_chain(self, symbol: str, expiration: str) -> list[dict]: ...
```

---

## Acceptance Criteria

1. `.env` and `.env.*` (except `.env.example`) are listed in `.gitignore`.
2. `.env.example` exists at the workspace root and documents all three variables.
3. `TradierClient` injects `Authorization: Bearer <key>` and `Accept: application/json` on every request.
4. `TradierClient(sandbox=True)` uses the sandbox base URL; `sandbox=False` uses production.
5. After a response with `X-Ratelimit-Available: 3`, the client sleeps before the next request.
6. `get_option_expirations` returns a list of date strings parsed from the Tradier JSON response.
7. `get_option_chain` returns a list of contract dicts parsed from the Tradier JSON response.
8. A non-2xx response raises `TradierAPIError` with the status code.
9. `--sandbox` CLI flag sets `config.sandbox = True`; the correct API key is selected.
10. `uv run pytest` passes (all existing + new tests).
11. `uv run ruff check .` and `uv run ruff format --check .` report no issues.

---

## Tests (`tests/test_tradier_client.py`)

All tests use `httpx` mock transport — no real network calls.

- `test_auth_header_injected`: assert `Authorization` header is present on requests.
- `test_production_base_url`: assert requests go to `api.tradier.com` when `sandbox=False`.
- `test_sandbox_base_url`: assert requests go to `sandbox.tradier.com` when `sandbox=True`.
- `test_get_option_expirations_parses_response`: mock returns valid JSON; assert list of date strings returned.
- `test_get_option_expirations_empty`: mock returns empty expirations; assert `[]` returned.
- `test_get_option_chain_parses_response`: mock returns valid JSON; assert list of contract dicts returned.
- `test_get_option_chain_empty`: mock returns empty chain; assert `[]` returned.
- `test_non_2xx_raises_tradier_api_error`: mock returns HTTP 429; assert `TradierAPIError` raised.
- `test_rate_limit_throttle`: mock returns `X-Ratelimit-Available: 3`; assert `time.sleep` is called before next request.
- `test_no_delay_when_available_high`: mock returns `X-Ratelimit-Available: 100`; assert `time.sleep` is NOT called for rate-limit throttle (inter-request delay may still fire).

---

## Verification Steps

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run python -m trade_hunter run --help   # confirm --sandbox flag present
```

---

## Pre-Implementation Note for Vibe Engineer

Before Story-0070 uses the live client, please:

1. Confirm `.env` file has been created locally (after this story commits `.gitignore` first).
2. Validate the sandbox key manually — e.g., `curl -H "Authorization: Bearer <sandbox_key>" https://sandbox.tradier.com/v1/markets/quotes?symbols=SPY` should return a quote.
3. If sandbox works, set `TRADIER_ENV=sandbox` for initial Story-0070 testing before switching to production.
