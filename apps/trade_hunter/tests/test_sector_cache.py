"""Unit tests for SectorCache — all yfinance calls are mocked."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from trade_hunter.loaders.sector_cache import SectorCache, _CACHE_FILENAME

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_YFINANCE_MODULE = "trade_hunter.loaders.sector_cache.yfinance"


def _mock_ticker(sector: str | None):
    """Return a mock yfinance.Ticker whose .info['sector'] returns sector."""
    ticker = MagicMock()
    ticker.info = {"sector": sector} if sector else {}
    return ticker


def _make_cache(tmp_path: Path, *, preload: dict | None = None) -> SectorCache:
    """Create a SectorCache backed by tmp_path, optionally pre-seeding the JSON file."""
    if preload:
        (tmp_path / _CACHE_FILENAME).write_text(
            json.dumps(preload), encoding="utf-8"
        )
    return SectorCache(cache_dir=tmp_path)


# ---------------------------------------------------------------------------
# Cache hit — no yfinance call
# ---------------------------------------------------------------------------


def test_cache_hit_returns_sector(tmp_path):
    cache = _make_cache(tmp_path, preload={"AAPL": "Information Technology"})
    with patch(_YFINANCE_MODULE) as mock_yf:
        result = cache.get("AAPL")
    assert result == "Information Technology"
    mock_yf.Ticker.assert_not_called()


def test_cache_hit_in_memory_after_lookup(tmp_path):
    """Second call is served from memory without re-reading the file or hitting yfinance."""
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        cache.get("AAPL")  # populates memory + file
        mock_yf.Ticker.reset_mock()
        result = cache.get("AAPL")  # should be a memory hit
    assert result == "Information Technology"
    mock_yf.Ticker.assert_not_called()


# ---------------------------------------------------------------------------
# Cache miss + yfinance hit
# ---------------------------------------------------------------------------


def test_cache_miss_calls_yfinance(tmp_path):
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        result = cache.get("AAPL")
    assert result == "Information Technology"
    mock_yf.Ticker.assert_called_once_with("AAPL")


def test_cache_miss_persists_to_file(tmp_path):
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Financial Services")
        cache.get("JPM")
    saved = json.loads((tmp_path / _CACHE_FILENAME).read_text(encoding="utf-8"))
    assert saved["JPM"] == "Financials"


def test_all_yfinance_sector_names_normalize_correctly(tmp_path):
    """Every yfinance sector name in YFINANCE_SECTOR_MAP normalizes to a standard sector."""
    from trade_hunter.pipeline.normalize import YFINANCE_SECTOR_MAP

    for yf_name, expected in YFINANCE_SECTOR_MAP.items():
        cache = SectorCache(cache_dir=None)  # memory-only, no file I/O
        with patch(_YFINANCE_MODULE) as mock_yf:
            mock_yf.Ticker.return_value = _mock_ticker(yf_name)
            result = cache.get("TEST")
        assert result == expected, f"yfinance '{yf_name}' → expected '{expected}', got '{result}'"


# ---------------------------------------------------------------------------
# Cache miss + yfinance failure / unrecognized sector
# ---------------------------------------------------------------------------


def test_yfinance_returns_none_sector(tmp_path):
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker(None)
        result = cache.get("UNKNOWN")
    assert result is None


def test_yfinance_raises_exception_returns_none(tmp_path):
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.side_effect = Exception("network error")
        result = cache.get("BROKEN")
    assert result is None


def test_unrecognized_yfinance_sector_returns_none(tmp_path):
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Some Unknown Sector")
        result = cache.get("XYZ")
    assert result is None


def test_unrecognized_sector_not_written_to_cache(tmp_path):
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Some Unknown Sector")
        cache.get("XYZ")
    assert not (tmp_path / _CACHE_FILENAME).exists()


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------


def test_cache_reloaded_from_disk_on_init(tmp_path):
    """Data persisted by one SectorCache instance is picked up by a second instance."""
    cache1 = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        cache1.get("AAPL")

    cache2 = SectorCache(cache_dir=tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        result = cache2.get("AAPL")
    assert result == "Information Technology"
    mock_yf.Ticker.assert_not_called()


def test_cache_file_is_sorted(tmp_path):
    """Keys in the persisted JSON are sorted for stable diffs."""
    cache = _make_cache(tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        cache.get("MSFT")
        mock_yf.Ticker.return_value = _mock_ticker("Financial Services")
        cache.get("JPM")
    raw = (tmp_path / _CACHE_FILENAME).read_text(encoding="utf-8")
    keys = [k for k in json.loads(raw)]
    assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Memory-only mode (cache_dir=None)
# ---------------------------------------------------------------------------


def test_memory_only_mode_no_file_written(tmp_path):
    cache = SectorCache(cache_dir=None)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        result = cache.get("AAPL")
    assert result == "Information Technology"
    # No file should exist anywhere under tmp_path
    assert not list(tmp_path.glob("**/*.json"))


def test_memory_only_mode_in_memory_hit(tmp_path):
    cache = SectorCache(cache_dir=None)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        cache.get("AAPL")
        mock_yf.Ticker.reset_mock()
        result = cache.get("AAPL")
    assert result == "Information Technology"
    mock_yf.Ticker.assert_not_called()


# ---------------------------------------------------------------------------
# Corrupted cache file is handled gracefully
# ---------------------------------------------------------------------------


def test_corrupted_cache_file_is_ignored(tmp_path):
    (tmp_path / _CACHE_FILENAME).write_text("not valid json", encoding="utf-8")
    cache = SectorCache(cache_dir=tmp_path)
    with patch(_YFINANCE_MODULE) as mock_yf:
        mock_yf.Ticker.return_value = _mock_ticker("Technology")
        result = cache.get("AAPL")
    assert result == "Information Technology"
