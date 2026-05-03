import pandas as pd
import pytest

from trade_hunter.pipeline.candidates import check_active_symbols_in_universe, filter_and_join

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def universe() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Symbol": "AAPL",
                "Sector": "Information Technology",
                "Sector Bucket": "Growth",
                "IV Rank": 45.0,
                "IV %tile": 60.0,
                "IV Idx": 25.0,
            },
            {
                "Symbol": "MSFT",
                "Sector": "Information Technology",
                "Sector Bucket": "Growth",
                "IV Rank": 50.0,
                "IV %tile": 65.0,
                "IV Idx": 30.0,
            },
            {
                "Symbol": "JPM",
                "Sector": "Financials",
                "Sector Bucket": "Economic",
                "IV Rank": 35.0,
                "IV %tile": 45.0,
                "IV Idx": 20.0,
            },
        ]
    )


@pytest.fixture()
def candidates() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"Symbol": "AAPL", "Quant Rating": 4.5, "Growth": "A", "Momentum": "B+"},
            {"Symbol": "MSFT", "Quant Rating": 4.0, "Growth": "B+", "Momentum": "A-"},
            {"Symbol": "NVDA", "Quant Rating": 4.8, "Growth": "A+", "Momentum": "A+"},
        ]
    )


# ---------------------------------------------------------------------------
# check_active_symbols_in_universe
# ---------------------------------------------------------------------------


def test_active_all_in_universe(universe):
    active = frozenset({"AAPL", "MSFT"})
    warnings = check_active_symbols_in_universe(active, universe)
    assert warnings == []


def test_active_missing_from_universe(universe):
    active = frozenset({"AAPL", "NVDA", "TSLA"})
    warnings = check_active_symbols_in_universe(active, universe)
    assert len(warnings) == 2
    assert any("NVDA" in w for w in warnings)
    assert any("TSLA" in w for w in warnings)


def test_active_empty_set(universe):
    warnings = check_active_symbols_in_universe(frozenset(), universe)
    assert warnings == []


# ---------------------------------------------------------------------------
# filter_and_join — exclusion
# ---------------------------------------------------------------------------


def test_open_trade_excluded(universe, candidates):
    active = frozenset({"AAPL"})
    df, warnings = filter_and_join(candidates, universe, active, side="BULL")
    assert "AAPL" not in df["Symbol"].values
    assert any("AAPL" in w and "open trade" in w for w in warnings)


def test_not_in_universe_excluded(universe, candidates):
    active = frozenset()
    df, warnings = filter_and_join(candidates, universe, active, side="BULL")
    assert "NVDA" not in df["Symbol"].values
    assert any("NVDA" in w and "TastyTrade Russell 1000 universe" in w for w in warnings)


def test_open_trade_check_runs_first(universe):
    # XYZ is an open trade AND not in the universe — only the open-trade warning should fire
    cands = pd.DataFrame([{"Symbol": "XYZ", "Quant Rating": 3.0, "Growth": "B", "Momentum": "C"}])
    active = frozenset({"XYZ"})
    _, warnings = filter_and_join(cands, universe, active, side="BULL")
    assert len(warnings) == 1
    assert "open trade" in warnings[0]
    assert "TastyTrade Russell 1000 universe" not in warnings[0]


# ---------------------------------------------------------------------------
# filter_and_join — join
# ---------------------------------------------------------------------------


def test_join_columns_combined(universe, candidates):
    active = frozenset()
    df, _ = filter_and_join(candidates, universe, active, side="BULL")
    # SeekingAlpha columns
    assert "Quant Rating" in df.columns
    assert "Momentum" in df.columns
    # TastyTrade Russell 1000 universe columns
    assert "IV Rank" in df.columns
    assert "Sector" in df.columns
    assert "Sector Bucket" in df.columns


def test_join_row_count(universe, candidates):
    # AAPL excluded (open trade), NVDA excluded (not in universe) → only MSFT survives
    active = frozenset({"AAPL"})
    df, _ = filter_and_join(candidates, universe, active, side="BULL")
    assert len(df) == 1
    assert df.iloc[0]["Symbol"] == "MSFT"


def test_goog_dropped_with_warning(universe):
    """GOOG is silently dropped before any other processing; a warning is emitted."""
    cands = pd.DataFrame(
        [
            {"Symbol": "GOOG", "Quant Rating": 4.0, "Growth": "A", "Momentum": "B"},
            {"Symbol": "AAPL", "Quant Rating": 4.5, "Growth": "A+", "Momentum": "A"},
        ]
    )
    df, warnings = filter_and_join(cands, universe, frozenset(), side="BULL")
    assert "GOOG" not in df["Symbol"].values
    assert any("GOOG" in w and "GOOGL" in w for w in warnings)


def test_goog_dropped_bear_side(universe):
    cands = pd.DataFrame([{"Symbol": "GOOG", "Quant Rating": 2.0, "Growth": "D", "Momentum": "D"}])
    df, warnings = filter_and_join(cands, universe, frozenset(), side="BEAR")
    assert df.empty
    assert any("[BEAR]" in w and "GOOG" in w for w in warnings)


def test_empty_candidates(universe):
    empty = pd.DataFrame(columns=["Symbol", "Quant Rating", "Growth", "Momentum"])
    df, warnings = filter_and_join(empty, universe, frozenset(), side="BULL")
    assert df.empty
    assert warnings == []


def test_no_exclusions(universe):
    cands = pd.DataFrame(
        [
            {"Symbol": "AAPL", "Quant Rating": 4.5, "Growth": "A", "Momentum": "B+"},
            {"Symbol": "MSFT", "Quant Rating": 4.0, "Growth": "B+", "Momentum": "A-"},
        ]
    )
    df, warnings = filter_and_join(cands, universe, frozenset(), side="BULL")
    assert len(df) == 2
    assert warnings == []
