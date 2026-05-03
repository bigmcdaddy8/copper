"""Unit tests for calculate_scores() and build_active_diversity_lists()."""

from datetime import date, timedelta

import pandas as pd
import pytest

from trade_hunter.pipeline.scoring import (
    SCORE_COLUMNS,
    build_active_diversity_lists,
    calculate_scores,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

RUN_DATE = date(2025, 3, 19)
EXPIRATION = "2025-04-18"  # third Friday, DTE=30 from RUN_DATE


def _base_row(**overrides) -> dict:
    """Return a minimal valid enriched row for a BULL Growth-bucket candidate."""
    row = {
        "Symbol": "SPY",
        "IV Rank": 45.0,  # ivr_quality -> 4.0
        "IV %tile": 55.0,  # ivp_quality -> 5.0
        "Open Interest": 500,  # oi_quality  -> 4.5
        "Bid": 1.10,
        "Ask": 1.20,  # spread≈8.7% -> spread_quality -> 3.0
        "Last Price": 100.0,
        "Strike": 95.0,  # BPR=1610 -> bpr_quality -> 3.5
        "Option Type": "put",
        "Delta": -0.21,
        "Expiration Date": EXPIRATION,
        "Sector Bucket": "Growth",
        "Sector": "Information Technology",
        "Quant Rating": 4.0,  # quant_quality BULL -> 4.0
        "Growth": "B",  # grade_quality -> 2.5
        "Momentum": "A-",  # grade_quality -> 4.0; bid_quality -> 2.5
        "Earnings At": str(RUN_DATE + timedelta(days=80)),  # EaE=35 -> 5.0
        "Liquidity": "\u2605\u2605\u2605\u2606",  # ★★★☆ → quality 4.5
    }
    row.update(overrides)
    return row


def _df(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(list(rows))


# 2 of 10 active in Growth = 20% -> cyclical=5.0
# 1 of 10 active in IT = 10% -> sector=2.0
_ACTIVE_BUCKETS = [
    "Growth",
    "Growth",
    "Economic",
    "Economic",
    "Economic",
    "Defensive",
    "Defensive",
    "Economic",
    "Economic",
    "Economic",
]
_ACTIVE_SECTORS = [
    "Information Technology",
    "Financials",
    "Financials",
    "Energy",
    "Health Care",
    "Industrials",
    "Financials",
    "Energy",
    "Industrials",
    "Materials",
]


# ---------------------------------------------------------------------------
# Known-value test
# ---------------------------------------------------------------------------


def test_score_known_value():
    """Hand-computed expected score = 3.87 for the base row with Growth included.

    Metric qualities and weights:
      IVR=4.0 (w=3), IVP=5.0 (w=3), OI=4.5 (w=3), Spread=2.0 (w=3),
      BPR=3.5 (w=3), CycDiv=5.0 (w=3), Quant=4.0 (w=2), SecDiv=2.0 (w=1),
      Earn=5.0 (w=1), Growth=2.5 (w=1), Mom=4.0 (w=1), Bid=2.5 (w=1),
      Liquidity=4.5 (w=1) [★★★☆]
      numerator=100.5, denominator=26.0, score=3.8654→3.87

    Note: bid=1.10/ask=1.20 → spread≈8.7% → falls in 8–12% band → quality=2.0
    """
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    assert "Trade Score" in result.columns
    assert result.iloc[0]["Trade Score"] == pytest.approx(3.87, abs=1e-4)


# ---------------------------------------------------------------------------
# Growth active / inactive
# ---------------------------------------------------------------------------


def test_score_growth_bucket_included():
    """Sector Bucket=Growth → Growth weight active; score is in valid range."""
    df = _df(_base_row(sector_bucket="Growth"))
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    score = result.iloc[0]["Trade Score"]
    assert 0.0 <= score <= 5.0


def test_score_non_growth_bucket_excluded():
    """Sector Bucket=Economic → Growth excluded; score differs from Growth-included."""
    # Re-use same data, only change sector bucket
    row_growth = _base_row(**{"Sector Bucket": "Growth"})
    row_economic = _base_row(**{"Sector Bucket": "Economic"})
    # active buckets adjusted so cyclical % is the same (all Economic)
    active_buckets_eco = ["Economic"] * 10

    result_g = calculate_scores(_df(row_growth), "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    result_e = calculate_scores(
        _df(row_economic), "BULL", RUN_DATE, active_buckets_eco, _ACTIVE_SECTORS
    )

    # Growth excluded means denominator is 24 instead of 25
    assert result_g.iloc[0]["Trade Score"] != result_e.iloc[0]["Trade Score"]


# ---------------------------------------------------------------------------
# Earnings date resolution
# ---------------------------------------------------------------------------


def test_score_earnings_at_precedence():
    """Earnings At takes precedence over Upcoming Announce Date."""
    # Earnings At well past expiry → quality=3.0
    # Upcoming Announce Date safely after expiry → quality=5.0
    # If Earnings At is used, score will be lower on that metric
    earnings_at = str(date(2025, 3, 1))  # EaE = -48 → quality 3.0
    upcoming = str(date(2025, 5, 1))  # EaE = 13  → quality 5.0
    row = _base_row(**{"Earnings At": earnings_at, "Upcoming Announce Date": upcoming})
    result_with_precedence = calculate_scores(
        _df(row), "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS
    )
    # Without precedence (using Upcoming), earnings quality would be 5.0 → higher score
    row_upcoming_only = _base_row(**{"Earnings At": None, "Upcoming Announce Date": upcoming})
    result_upcoming_only = calculate_scores(
        _df(row_upcoming_only), "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS
    )
    # earnings_at gives quality 3.0, upcoming gives 5.0 → different scores
    assert (
        result_with_precedence.iloc[0]["Trade Score"] != result_upcoming_only.iloc[0]["Trade Score"]
    )


def test_score_earnings_fallback():
    """When both earnings columns are absent/null, fallback = run_date + 70 days.

    run_date + 70 = 2025-05-28; expiration = 2025-04-18 → EaE = 40 → quality 5.0.
    Same as using an explicit date 40 days after expiration.
    """
    row_fallback = _base_row(**{"Earnings At": None})
    if "Upcoming Announce Date" in row_fallback:
        row_fallback["Upcoming Announce Date"] = None

    # Explicit earnings 40 days after expiry (same quality)
    explicit_date = str(date(2025, 5, 28))
    row_explicit = _base_row(**{"Earnings At": explicit_date})

    result_fallback = calculate_scores(
        _df(row_fallback), "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS
    )
    result_explicit = calculate_scores(
        _df(row_explicit), "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS
    )
    assert result_fallback.iloc[0]["Trade Score"] == pytest.approx(
        result_explicit.iloc[0]["Trade Score"], abs=1e-4
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_score_empty_input():
    """Empty DataFrame returns empty DataFrame with no error."""
    cols = list(_base_row().keys())
    df = pd.DataFrame(columns=cols)
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    assert result.empty


def test_score_result_is_copy():
    """Input DataFrame is not mutated."""
    df = _df(_base_row())
    original_cols = list(df.columns)
    calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    assert list(df.columns) == original_cols


def test_score_in_valid_range():
    """Trade Score is always in [0.0, 5.0]."""
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    score = result.iloc[0]["Trade Score"]
    assert 0.0 <= score <= 5.0


def test_score_rounded_to_2dp():
    """Trade Score is rounded to 2 decimal places."""
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    score = result.iloc[0]["Trade Score"]
    assert score == round(score, 2)


# ---------------------------------------------------------------------------
# build_active_diversity_lists
# ---------------------------------------------------------------------------


def test_build_active_diversity_lists_basic():
    universal = pd.DataFrame(
        {
            "Symbol": ["AAPL", "MSFT", "JPM", "XOM"],
            "Sector": ["Information Technology", "Information Technology", "Financials", "Energy"],
            "Sector Bucket": ["Growth", "Growth", "Economic", "Economic"],
        }
    )
    active = frozenset({"AAPL", "JPM"})
    buckets, sectors = build_active_diversity_lists(active, universal)
    assert sorted(buckets) == sorted(["Growth", "Economic"])
    assert sorted(sectors) == sorted(["Information Technology", "Financials"])


def test_build_active_diversity_lists_symbol_not_in_universe():
    """Active symbols absent from TastyTrade Russell 1000 universe are silently skipped."""
    universal = pd.DataFrame(
        {
            "Symbol": ["AAPL"],
            "Sector": ["Information Technology"],
            "Sector Bucket": ["Growth"],
        }
    )
    active = frozenset({"AAPL", "GHOST"})  # GHOST not in universe
    buckets, sectors = build_active_diversity_lists(active, universal)
    assert buckets == ["Growth"]
    assert sectors == ["Information Technology"]


def test_scored_has_earnings_date_column():
    """calculate_scores output includes an Earnings Date column."""
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    assert "Earnings Date" in result.columns


def test_scored_has_bpr_column():
    """calculate_scores output includes a BPR column with a positive dollar value."""
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    assert "BPR" in result.columns
    assert result.iloc[0]["BPR"] > 0


def test_scored_has_all_individual_score_columns():
    """calculate_scores output includes all 13 individual score columns."""
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    for col in SCORE_COLUMNS:
        assert col in result.columns, f"Missing column: {col}"


def test_individual_scores_in_valid_range():
    """All individual score values are in [0.0, 5.0]."""
    df = _df(_base_row())
    result = calculate_scores(df, "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    for col in SCORE_COLUMNS:
        val = result.iloc[0][col]
        assert 0.0 <= val <= 5.0, f"{col} = {val} out of range"


def test_growth_score_zero_for_non_growth_bucket():
    """Growth Score is 0.0 when Sector Bucket is not Growth."""
    row = _base_row(**{"Sector Bucket": "Economic"})
    result = calculate_scores(_df(row), "BULL", RUN_DATE, ["Economic"] * 5, _ACTIVE_SECTORS)
    assert result.iloc[0]["Growth Score"] == 0.0


def test_growth_score_nonzero_for_growth_bucket():
    """Growth Score is non-zero when Sector Bucket is Growth and grade is above F."""
    row = _base_row(**{"Sector Bucket": "Growth", "Growth": "A"})
    result = calculate_scores(_df(row), "BULL", RUN_DATE, _ACTIVE_BUCKETS, _ACTIVE_SECTORS)
    assert result.iloc[0]["Growth Score"] > 0.0


# ---------------------------------------------------------------------------
# build_active_diversity_lists
# ---------------------------------------------------------------------------


def test_build_active_diversity_lists_empty_active():
    universal = pd.DataFrame(
        {
            "Symbol": ["AAPL"],
            "Sector": ["Information Technology"],
            "Sector Bucket": ["Growth"],
        }
    )
    buckets, sectors = build_active_diversity_lists(frozenset(), universal)
    assert buckets == []
    assert sectors == []
