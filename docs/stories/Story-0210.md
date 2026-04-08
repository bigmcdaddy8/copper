# Story-0210 — Yahoo Finance Sector Cache

**Status**: Completed  
**Phase**: 7 — Maintenance & Enhancements  
**Addresses**: Backlog-0040

---

## Goal

Replace TastyTrade as the sector data source with Yahoo Finance (`yfinance`) — a single, consistent, authoritative source for the standard GICS 11-sector classification. A persistent local disk cache ensures each ticker is only looked up once; subsequent runs use the cached value without hitting Yahoo. A new `--cache-dir` CLI parameter specifies where cache files are stored (outside the repository).

When `--cache-dir` is omitted, the cache operates in memory-only mode (lookups still work, nothing is persisted).

If yfinance cannot resolve a ticker's sector, the TastyTrade sector (already normalized via `SECTOR_MAP`) is kept as a fallback and a warning is logged.

---

## New / Modified Files

| File | Change |
|---|---|
| `apps/trade_hunter/src/trade_hunter/loaders/sector_cache.py` | **New**: `SectorCache` class — cache-first yfinance lookups, JSON persistence |
| `apps/trade_hunter/src/trade_hunter/pipeline/normalize.py` | Add `YFINANCE_SECTOR_MAP` (yfinance raw name → standard 11 sector name) |
| `apps/trade_hunter/src/trade_hunter/cli.py` | Add `--cache-dir` option (`Optional[Path]`, default `None`) |
| `apps/trade_hunter/src/trade_hunter/config.py` | Add `cache_dir: Path \| None = None` to `RunConfig` |
| `apps/trade_hunter/src/trade_hunter/pipeline/runner.py` | After TT join, resolve sector for each ticker via `SectorCache`; fall back to TT sector on miss |
| `apps/trade_hunter/pyproject.toml` | Add `yfinance` to dependencies |
| `apps/trade_hunter/tests/test_sector_cache.py` | **New**: tests with mocked `yfinance.Ticker` |

---

## Detailed Design

### 1. `YFINANCE_SECTOR_MAP` (`pipeline/normalize.py`)

```python
YFINANCE_SECTOR_MAP: dict[str, str] = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
    "Communication Services": "Communication Services",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Industrials": "Industrials",
    "Energy": "Energy",
}
```

### 2. `SectorCache` (`loaders/sector_cache.py`)

```python
import json
import yfinance
from pathlib import Path
from trade_hunter.pipeline.normalize import YFINANCE_SECTOR_MAP


class SectorCache:
    def __init__(self, cache_dir: Path | None) -> None:
        self._path = (cache_dir / "sector_cache.json") if cache_dir else None
        self._data: dict[str, str] = {}
        if self._path and self._path.exists():
            self._data = json.loads(self._path.read_text())

    def get(self, ticker: str) -> str | None:
        """Return normalized sector for ticker, or None if unresolvable."""
        if ticker in self._data:
            return self._data[ticker]
        try:
            raw = yfinance.Ticker(ticker).info.get("sector")
        except Exception:
            return None
        if raw:
            normalized = YFINANCE_SECTOR_MAP.get(raw)
            if normalized:
                self._data[ticker] = normalized
                self._flush()
                return normalized
        return None

    def _flush(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._data, indent=2))
```

### 3. CLI (`cli.py`)

```python
cache_dir: Optional[Path] = typer.Option(
    None,
    "--cache-dir",
    help="Directory for persistent cache files (e.g. sector data). Omit to disable caching.",
)
```

### 4. Config (`config.py`)

```python
@dataclass
class RunConfig:
    ...
    cache_dir: Path | None = None
```

### 5. Sector resolution in `runner.py`

After the TastyTrade/SeekingAlpha join produces the candidate DataFrame, for each ticker:

```python
cache = SectorCache(cfg.cache_dir)

for idx, row in df.iterrows():
    ticker = row["Symbol"]
    resolved = cache.get(ticker)
    if resolved:
        df.at[idx, "Sector"] = resolved
        df.at[idx, "Sector Bucket"] = assign_bucket(resolved)
    else:
        run_log.warn(f"[{side}] '{ticker}' — yfinance sector miss, using TastyTrade fallback")
```

`SectorCache` is instantiated once per pipeline run (shared across BULL and BEAR passes).

### 6. `pyproject.toml`

Add `yfinance` to the `[project] dependencies` list.

---

## Acceptance Criteria

1. `--cache-dir /tmp/th_cache` — after the first run, `sector_cache.json` exists and contains ticker→sector entries.
2. Second run with the same tickers — zero yfinance network calls (all served from cache).
3. If yfinance cannot resolve a ticker, TastyTrade sector is preserved and a `[WARN]` entry appears in the run_log.
4. Without `--cache-dir` — pipeline works normally; no file is written.
5. All sectors in the output spreadsheet are one of the standard 11 GICS sector names.
6. All existing tests pass.
7. `test_sector_cache.py` covers: cache hit, cache miss + yfinance success, cache miss + yfinance failure, JSON persistence round-trip, memory-only mode (no file written).

---

## Verification Steps

```bash
# Unit tests
uv run pytest apps/trade_hunter/tests/test_sector_cache.py -v

# Full test suite
uv run pytest apps/trade_hunter/tests/

# Live: first run — populates cache
uv run trade_hunter run \
  --output-dir /tmp/th_out \
  --cache-dir /tmp/th_cache \
  --verbose

# Inspect cache
cat /tmp/th_cache/sector_cache.json | python3 -m json.tool | head -30

# Live: second run — confirm no yfinance calls (fast sector resolution)
uv run trade_hunter run \
  --output-dir /tmp/th_out2 \
  --cache-dir /tmp/th_cache \
  --verbose
```
