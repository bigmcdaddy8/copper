from pathlib import Path

import openpyxl
import pytest

from trade_hunter.loaders.journal import WORKSHEET_NAME, load_journal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_journal(
    tmp_path: Path,
    symbols: list,
    filename: str = "journal.xlsx",
    sheet_name: str = WORKSHEET_NAME,
    columns: list[str] | None = None,
) -> Path:
    """Write a journal xlsx with the given symbols to tmp_path/filename."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    headers = columns or ["Symbol", "M8 Trade #", "Entry Capital Required"]
    ws.append(headers)
    for sym in symbols:
        row = [sym] + [""] * (len(headers) - 1)
        ws.append(row)
    path = tmp_path / filename
    wb.save(path)
    return path


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


def test_load_file_not_found(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_journal(tmp_path, explicit_path=tmp_path / "nonexistent.xlsx")


def test_load_missing_worksheet(tmp_path):
    wb = openpyxl.Workbook()
    wb.active.title = "WrongSheet"
    path = tmp_path / "journal.xlsx"
    wb.save(path)
    with pytest.raises(ValueError, match="daJournal"):
        load_journal(tmp_path, explicit_path=path)


def test_load_missing_symbol_column(tmp_path):
    path = _make_journal(tmp_path, [], columns=["M8 Trade #", "Entry Capital Required"])
    with pytest.raises(ValueError, match="Symbol"):
        load_journal(tmp_path, explicit_path=path)


# ---------------------------------------------------------------------------
# Warning cases
# ---------------------------------------------------------------------------


def test_load_null_symbol_dropped(tmp_path):
    path = _make_journal(tmp_path, ["AAPL", None, "MSFT"])
    result, warnings = load_journal(tmp_path, explicit_path=path)
    assert "AAPL" in result
    assert "MSFT" in result
    assert any("null" in w.lower() or "symbol" in w.lower() for w in warnings)


def test_load_empty_journal(tmp_path):
    path = _make_journal(tmp_path, [])
    result, warnings = load_journal(tmp_path, explicit_path=path)
    assert result == frozenset()
    assert any("no active" in w.lower() for w in warnings)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_load_happy_path(tmp_path):
    path = _make_journal(tmp_path, ["AAPL", "MSFT", "GOOG"])
    result, warnings = load_journal(tmp_path, explicit_path=path)
    assert result == frozenset({"AAPL", "MSFT", "GOOG"})
    assert warnings == []


def test_load_deduplication(tmp_path):
    path = _make_journal(tmp_path, ["AAPL", "MSFT", "AAPL"])
    result, warnings = load_journal(tmp_path, explicit_path=path)
    assert result == frozenset({"AAPL", "MSFT"})
    assert len(result) == 2


def test_load_returns_frozenset(tmp_path):
    path = _make_journal(tmp_path, ["AAPL"])
    result, _ = load_journal(tmp_path, explicit_path=path)
    assert isinstance(result, frozenset)


def test_load_uses_default_path(tmp_path):
    _make_journal(tmp_path, ["AAPL", "TSLA"])
    result, warnings = load_journal(worksheets_dir=tmp_path)
    assert "AAPL" in result
    assert "TSLA" in result
    assert warnings == []
