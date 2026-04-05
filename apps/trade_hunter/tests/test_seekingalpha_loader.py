import pandas as pd
import pytest

from trade_hunter.loaders.seekingalpha import (
    BULL_GLOB,
    discover_seekingalpha_file,
    load_seekingalpha,
)

_REQUIRED = ["Symbol", "Quant Rating", "Growth", "Momentum"]
_OPTIONAL = ["Company Name", "Upcoming Announce Date"]


def _make_xlsx(tmp_path, filename, rows=None, columns=None):
    """Write a SeekingAlpha xlsx to tmp_path/filename and return its Path."""
    if rows is None:
        rows = [
            {
                "Symbol": "AAPL",
                "Company Name": "Apple Inc",
                "Quant Rating": 4.5,
                "Growth": "A",
                "Momentum": "B+",
                "Upcoming Announce Date": "2026-07-30",
            }
        ]
    df = pd.DataFrame(rows, columns=columns or list(rows[0].keys()))
    path = tmp_path / filename
    df.to_excel(path, index=False)
    return path


# ---------------------------------------------------------------------------
# discover_seekingalpha_file
# ---------------------------------------------------------------------------


def test_discover_newest_bull_file(tmp_path):
    _make_xlsx(tmp_path, "Copper_BULLish 2026-03-01.xlsx")
    newer = _make_xlsx(tmp_path, "Copper_BULLish 2026-04-01.xlsx")
    result = discover_seekingalpha_file(tmp_path, BULL_GLOB)
    assert result == newer


def test_discover_no_files(tmp_path):
    with pytest.raises(FileNotFoundError, match="No SeekingAlpha file found"):
        discover_seekingalpha_file(tmp_path, BULL_GLOB)


# ---------------------------------------------------------------------------
# load_seekingalpha — error cases
# ---------------------------------------------------------------------------


def test_load_explicit_path_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_seekingalpha(tmp_path, explicit_path=tmp_path / "nonexistent.xlsx")


def test_load_missing_required_columns(tmp_path):
    rows = [{"Symbol": "AAPL", "Quant Rating": 4.5, "Growth": "A"}]  # Momentum missing
    path = tmp_path / "Copper_BULLish 2026-04-01.xlsx"
    pd.DataFrame(rows).to_excel(path, index=False)
    with pytest.raises(ValueError, match="Momentum"):
        load_seekingalpha(tmp_path, explicit_path=path)


# ---------------------------------------------------------------------------
# load_seekingalpha — warning cases
# ---------------------------------------------------------------------------


def test_load_null_symbol(tmp_path):
    rows = [
        {"Symbol": "AAPL", "Quant Rating": 4.5, "Growth": "A", "Momentum": "B+"},
        {"Symbol": None, "Quant Rating": 3.0, "Growth": "B", "Momentum": "C"},
    ]
    path = _make_xlsx(tmp_path, "Copper_BULLish 2026-04-01.xlsx", rows)
    df, warnings = load_seekingalpha(tmp_path, explicit_path=path)
    assert len(df) == 1
    assert any("null" in w.lower() or "symbol" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# load_seekingalpha — happy path
# ---------------------------------------------------------------------------


def test_load_bull_happy_path(tmp_path):
    path = _make_xlsx(tmp_path, "Copper_BULLish 2026-04-01.xlsx")
    df, warnings = load_seekingalpha(tmp_path, explicit_path=path, side="BULL")
    assert len(df) == 1
    assert set(_REQUIRED).issubset(df.columns)
    assert warnings == []


def test_load_bear_uses_bear_glob(tmp_path):
    _make_xlsx(tmp_path, "Copper_BEARish 2026-04-01.xlsx")
    df, warnings = load_seekingalpha(tmp_path, side="BEAR")
    assert len(df) == 1
    assert "Symbol" in df.columns


def test_load_optional_columns_included(tmp_path):
    path = _make_xlsx(tmp_path, "Copper_BULLish 2026-04-01.xlsx")
    df, _ = load_seekingalpha(tmp_path, explicit_path=path)
    assert "Company Name" in df.columns
    assert "Upcoming Announce Date" in df.columns


def test_load_optional_columns_absent(tmp_path):
    rows = [{"Symbol": "AAPL", "Quant Rating": 4.5, "Growth": "A", "Momentum": "B+"}]
    path = _make_xlsx(tmp_path, "Copper_BULLish 2026-04-01.xlsx", rows)
    df, warnings = load_seekingalpha(tmp_path, explicit_path=path)
    assert set(_REQUIRED).issubset(df.columns)
    assert "Company Name" not in df.columns
    assert warnings == []
