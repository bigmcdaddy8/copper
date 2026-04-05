"""Unit tests for pipeline/filters.py — all inline synthetic data."""

import pandas as pd

from trade_hunter.pipeline.filters import apply_hard_filters

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_row(
    symbol: str = "SPY",
    open_interest: int = 500,
    bid: float = 1.10,
    ask: float = 1.20,
) -> dict:
    return {
        "Symbol": symbol,
        "Open Interest": open_interest,
        "Bid": bid,
        "Ask": ask,
        "Strike": 470.0,
        "Delta": -0.21,
    }


def _df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# ---------------------------------------------------------------------------
# Pass — all filters satisfied
# ---------------------------------------------------------------------------


def test_passes_all_filters():
    # bid=1.10, ask=1.20 → spread = 0.10 / 1.15 ≈ 8.7% (< 13%)
    df = _df(_make_row(open_interest=500, bid=1.10, ask=1.20))
    result, warnings = apply_hard_filters(df, "BULL")
    assert len(result) == 1
    assert warnings == []


# ---------------------------------------------------------------------------
# Fail — open interest
# ---------------------------------------------------------------------------


def test_fails_open_interest():
    df = _df(_make_row(open_interest=5))
    result, warnings = apply_hard_filters(df, "BULL")
    assert result.empty
    assert len(warnings) == 1
    assert "open interest" in warnings[0]
    assert "SPY" in warnings[0]


def test_open_interest_boundary():
    """OI exactly equal to min_open_interest passes."""
    df = _df(_make_row(open_interest=8))
    result, warnings = apply_hard_filters(df, "BULL", min_open_interest=8)
    assert len(result) == 1
    assert warnings == []


# ---------------------------------------------------------------------------
# Fail — bid
# ---------------------------------------------------------------------------


def test_fails_bid():
    df = _df(_make_row(bid=0.40, ask=0.50))
    result, warnings = apply_hard_filters(df, "BULL")
    assert result.empty
    assert len(warnings) == 1
    assert "bid" in warnings[0]
    assert "SPY" in warnings[0]


def test_bid_boundary():
    """Bid exactly equal to min_bid passes (ask kept tight so spread filter does not fire)."""
    # bid=0.55, ask=0.60 → mid=0.575, spread=0.05/0.575 ≈ 8.7% (< 13%)
    df = _df(_make_row(bid=0.55, ask=0.60))
    result, warnings = apply_hard_filters(df, "BULL", min_bid=0.55)
    assert len(result) == 1
    assert warnings == []


# ---------------------------------------------------------------------------
# Fail — spread
# ---------------------------------------------------------------------------


def test_fails_spread():
    # bid=1.00, ask=1.25 → mid=1.125, spread=0.25/1.125 ≈ 22.2% (> 13%)
    df = _df(_make_row(bid=1.00, ask=1.25))
    result, warnings = apply_hard_filters(df, "BULL")
    assert result.empty
    assert len(warnings) == 1
    assert "spread" in warnings[0]
    assert "SPY" in warnings[0]


def test_spread_boundary():
    """Spread exactly equal to max_spread_pct passes.

    bid=1.00, ask=1.30 → mid=1.15, spread=0.30/1.15 ≈ 26.1%
    Use bid=0.935, ask=1.065 → mid=1.00, spread=0.13/1.00 = 13.0% exactly.
    """
    df = _df(_make_row(bid=0.935, ask=1.065))
    result, warnings = apply_hard_filters(df, "BULL", max_spread_pct=0.13)
    assert len(result) == 1
    assert warnings == []


# ---------------------------------------------------------------------------
# Filter ordering
# ---------------------------------------------------------------------------


def test_open_interest_checked_first():
    """Row that fails both OI and bid generates only the OI warning."""
    df = _df(_make_row(open_interest=2, bid=0.30, ask=0.40))
    result, warnings = apply_hard_filters(df, "BULL")
    assert result.empty
    assert len(warnings) == 1
    assert "open interest" in warnings[0]
    assert "bid" not in warnings[0]


# ---------------------------------------------------------------------------
# Multiple candidates
# ---------------------------------------------------------------------------


def test_multiple_candidates_partial_failure():
    """Three rows; one fails bid → two rows survive, one warning."""
    rows = [
        _make_row("SPY", open_interest=500, bid=1.10, ask=1.20),
        _make_row("AAPL", open_interest=300, bid=0.30, ask=0.40),  # bid fails
        _make_row("MSFT", open_interest=200, bid=0.90, ask=0.95),
    ]
    df = _df(*rows)
    result, warnings = apply_hard_filters(df, "BULL")
    assert len(result) == 2
    assert list(result["Symbol"]) == ["SPY", "MSFT"]
    assert len(warnings) == 1
    assert "AAPL" in warnings[0]
    assert "bid" in warnings[0]


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_empty_input():
    df = pd.DataFrame(columns=["Symbol", "Open Interest", "Bid", "Ask"])
    result, warnings = apply_hard_filters(df, "BULL")
    assert result.empty
    assert warnings == []
