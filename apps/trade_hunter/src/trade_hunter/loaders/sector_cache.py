"""Persistent ticker-to-sector cache backed by a local JSON file.

Lookups use Yahoo Finance (yfinance) as the data source. The cache is written
through on each new entry so subsequent runs avoid redundant network calls.
When cache_dir is None the cache operates in memory-only mode and nothing is
persisted to disk.
"""

import json
from pathlib import Path

import yfinance

from trade_hunter.pipeline.normalize import YFINANCE_SECTOR_MAP

_CACHE_FILENAME = "sector_cache.json"


class SectorCache:
    """Cache-first sector lookups backed by yfinance.

    Usage::

        cache = SectorCache(cache_dir=Path("/data/trade_hunter"))
        sector = cache.get("AAPL")   # "Information Technology"
        sector = cache.get("UNKNOWN")  # None — caller uses fallback

    Thread-safety: not thread-safe; designed for single-threaded pipeline use.
    """

    def __init__(self, cache_dir: Path | None) -> None:
        self._path = (cache_dir / _CACHE_FILENAME) if cache_dir else None
        self._data: dict[str, str] = {}
        if self._path and self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def get(self, ticker: str) -> str | None:
        """Return the normalized sector for ticker, or None if unresolvable.

        Lookup order:
          1. In-memory cache (populated from disk on init).
          2. yfinance API call — result is normalized via YFINANCE_SECTOR_MAP
             and written to cache before returning.
          3. Returns None if yfinance returns no sector or an unrecognized value.
        """
        if ticker in self._data:
            return self._data[ticker]

        try:
            raw = yfinance.Ticker(ticker).info.get("sector")
        except Exception:
            return None

        if not raw:
            return None

        normalized = YFINANCE_SECTOR_MAP.get(raw)
        if not normalized:
            return None

        self._data[ticker] = normalized
        self._flush()
        return normalized

    def _flush(self) -> None:
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, indent=2, sort_keys=True), encoding="utf-8"
            )
