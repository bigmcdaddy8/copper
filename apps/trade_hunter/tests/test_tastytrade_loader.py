import pandas as pd
import pytest

from trade_hunter.loaders.tastytrade import discover_tastytrade_file, load_tastytrade

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BASE_COLUMNS = [
    "Symbol",
    "Name",
    "Liquidity",
    "IV Idx",
    "IV Rank",
    "IV %tile",
    "Earnings At",
    "Sector",
]


def _make_csv(tmp_path, filename, rows=None):
    """Write a minimal valid TastyTrade CSV to tmp_path/filename and return its Path."""
    if rows is None:
        rows = [
            {
                "Symbol": "AAPL",
                "Name": "Apple Inc",
                "Liquidity": "High",
                "IV Idx": 25.0,
                "IV Rank": 45.0,
                "IV %tile": 60.0,
                "Earnings At": "2026-07-30",
                "Sector": "Technology",
            }
        ]
    df = pd.DataFrame(rows, columns=_BASE_COLUMNS)
    path = tmp_path / filename
    df.to_csv(path, index=False)
    return path


# ---------------------------------------------------------------------------
# discover_tastytrade_file
# ---------------------------------------------------------------------------


def test_discover_newest_file(tmp_path):
    _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv")
    newer = _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250315.csv")
    result = discover_tastytrade_file(tmp_path)
    assert result == newer


def test_discover_no_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="No TastyTrade file found"):
        discover_tastytrade_file(tmp_path)


# ---------------------------------------------------------------------------
# load_tastytrade — error cases
# ---------------------------------------------------------------------------


def test_load_explicit_path_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tastytrade(tmp_path, explicit_path=tmp_path / "nonexistent.csv")


def test_load_missing_required_column(tmp_path):
    # Drop IV Rank from the CSV
    rows = [{"Symbol": "AAPL", "IV Idx": 25.0, "IV %tile": 60.0, "Sector": "Technology"}]
    path = tmp_path / "tastytrade_watchlist_m8investments_Russell 1000_250101.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    with pytest.raises(ValueError, match="IV Rank"):
        load_tastytrade(tmp_path)


# ---------------------------------------------------------------------------
# load_tastytrade — warning cases
# ---------------------------------------------------------------------------


def test_load_unknown_sector(tmp_path):
    rows = [
        {
            "Symbol": "AAPL",
            "Name": "",
            "Liquidity": "",
            "IV Idx": 25.0,
            "IV Rank": 45.0,
            "IV %tile": 60.0,
            "Earnings At": "",
            "Sector": "Technology",
        },
        {
            "Symbol": "XYZ",
            "Name": "",
            "Liquidity": "",
            "IV Idx": 10.0,
            "IV Rank": 20.0,
            "IV %tile": 30.0,
            "Earnings At": "",
            "Sector": "Mystery Sector",
        },
    ]
    path = _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv", rows)
    df, warnings = load_tastytrade(tmp_path, explicit_path=path)
    assert len(df) == 1
    assert df.iloc[0]["Symbol"] == "AAPL"
    assert any("Mystery Sector" in w for w in warnings)


def test_load_null_symbol(tmp_path):
    rows = [
        {
            "Symbol": "AAPL",
            "Name": "",
            "Liquidity": "",
            "IV Idx": 25.0,
            "IV Rank": 45.0,
            "IV %tile": 60.0,
            "Earnings At": "",
            "Sector": "Technology",
        },
        {
            "Symbol": None,
            "Name": "",
            "Liquidity": "",
            "IV Idx": 10.0,
            "IV Rank": 20.0,
            "IV %tile": 30.0,
            "Earnings At": "",
            "Sector": "Technology",
        },
    ]
    path = _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv", rows)
    df, warnings = load_tastytrade(tmp_path, explicit_path=path)
    assert len(df) == 1
    assert any("null" in w.lower() or "symbol" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# load_tastytrade — happy path
# ---------------------------------------------------------------------------


def test_load_happy_path(tmp_path):
    path = _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv")
    df, warnings = load_tastytrade(tmp_path, explicit_path=path)
    assert len(df) == 1
    assert "Sector" in df.columns
    assert "Sector Bucket" in df.columns
    assert warnings == []


def test_load_sector_normalized(tmp_path):
    path = _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv")
    df, _ = load_tastytrade(tmp_path, explicit_path=path)
    assert df.iloc[0]["Sector"] == "Information Technology"


def test_load_sector_bucket_assigned(tmp_path):
    path = _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv")
    df, _ = load_tastytrade(tmp_path, explicit_path=path)
    assert df.iloc[0]["Sector Bucket"] == "Growth"


def test_load_uses_discovery_when_no_explicit_path(tmp_path):
    _make_csv(tmp_path, "tastytrade_watchlist_m8investments_Russell 1000_250101.csv")
    df, warnings = load_tastytrade(tmp_path)
    assert len(df) == 1
    assert "Sector Bucket" in df.columns
