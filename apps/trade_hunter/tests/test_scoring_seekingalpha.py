"""Unit tests for Quant Rating, Growth, Momentum, Earnings Date, and Bid quality functions."""

from datetime import date

import pytest

from trade_hunter.pipeline.scoring import (
    bid_quality,
    earnings_date_quality,
    grade_quality,
    growth_quality,
    momentum_quality,
    quant_rating_quality,
)

# ---------------------------------------------------------------------------
# quant_rating_quality
# ---------------------------------------------------------------------------


def test_quant_bull_direct():
    assert quant_rating_quality(4.2, "BULL") == pytest.approx(4.2)


def test_quant_bear_inverted():
    assert quant_rating_quality(4.2, "BEAR") == pytest.approx(1.8)


def test_quant_bull_min():
    assert quant_rating_quality(1.0, "BULL") == pytest.approx(1.0)


def test_quant_bull_max():
    assert quant_rating_quality(5.0, "BULL") == pytest.approx(5.0)


def test_quant_bear_min_rating():
    # lowest rating → highest bear quality
    assert quant_rating_quality(1.0, "BEAR") == pytest.approx(5.0)


def test_quant_bear_max_rating():
    # highest rating → lowest bear quality
    assert quant_rating_quality(5.0, "BEAR") == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# grade_quality (shared helper — all 13 grades)
# ---------------------------------------------------------------------------


_ALL_GRADES = [
    ("A+", 5.0),
    ("A", 4.5),
    ("A-", 4.0),
    ("B+", 3.0),
    ("B", 2.5),
    ("B-", 2.0),
    ("C+", 1.25),
    ("C", 1.0),
    ("C-", 0.75),
    ("D+", 0.5),
    ("D", 0.25),
    ("D-", 0.1),
    ("F", 0.0),
]


def test_all_grades():
    for grade, expected in _ALL_GRADES:
        assert grade_quality(grade) == pytest.approx(expected), f"grade={grade}"


# ---------------------------------------------------------------------------
# growth_quality
# ---------------------------------------------------------------------------


def test_growth_bull_a_plus():
    assert growth_quality("A+", "BULL") == pytest.approx(5.0)


def test_growth_bull_f():
    assert growth_quality("F", "BULL") == pytest.approx(0.0)


def test_growth_bear_inversion_a_plus():
    # A+ bull=5.0 → bear=0.0
    assert growth_quality("A+", "BEAR") == pytest.approx(0.0)


def test_growth_bear_inversion_f():
    # F bull=0.0 → bear=5.0
    assert growth_quality("F", "BEAR") == pytest.approx(5.0)


def test_growth_bear_inversion_mid():
    # B bull=2.5 → bear=2.5
    assert growth_quality("B", "BEAR") == pytest.approx(2.5)


# ---------------------------------------------------------------------------
# momentum_quality
# ---------------------------------------------------------------------------


def test_momentum_bull_a_plus():
    assert momentum_quality("A+", "BULL") == pytest.approx(5.0)


def test_momentum_bull_f():
    assert momentum_quality("F", "BULL") == pytest.approx(0.0)


def test_momentum_bear_inversion_a_plus():
    assert momentum_quality("A+", "BEAR") == pytest.approx(0.0)


def test_momentum_bear_inversion_f():
    assert momentum_quality("F", "BEAR") == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# earnings_date_quality
# ---------------------------------------------------------------------------

_EXP = date(2025, 4, 18)


def test_eae_well_past():
    # earnings 20 days before expiration → EaE = -20 → 3.0
    earnings = date(2025, 3, 29)
    assert earnings_date_quality(earnings, _EXP) == pytest.approx(3.0)


def test_eae_boundary_minus14():
    # EaE = -14 → <= -14 → 3.0
    earnings = date(2025, 4, 4)
    assert (earnings - _EXP).days == -14
    assert earnings_date_quality(earnings, _EXP) == pytest.approx(3.0)


def test_eae_just_inside_danger():
    # EaE = -13 → > -14 and <= 1 → 0.0
    earnings = date(2025, 4, 5)
    assert (earnings - _EXP).days == -13
    assert earnings_date_quality(earnings, _EXP) == pytest.approx(0.0)


def test_eae_same_day():
    # EaE = 0 → > -14 and <= 1 → 0.0
    assert earnings_date_quality(_EXP, _EXP) == pytest.approx(0.0)


def test_eae_boundary_1():
    # EaE = 1 → <= 1 → 0.0
    earnings = date(2025, 4, 19)
    assert (earnings - _EXP).days == 1
    assert earnings_date_quality(earnings, _EXP) == pytest.approx(0.0)


def test_eae_just_safe():
    # EaE = 2 → > 1 → 5.0
    earnings = date(2025, 4, 20)
    assert (earnings - _EXP).days == 2
    assert earnings_date_quality(earnings, _EXP) == pytest.approx(5.0)


def test_eae_safely_after():
    # EaE = 30 → > 1 → 5.0
    earnings = date(2025, 5, 18)
    assert earnings_date_quality(earnings, _EXP) == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# bid_quality
# ---------------------------------------------------------------------------


def test_bid_at_floor():
    assert bid_quality(0.55) == pytest.approx(0.0)


def test_bid_low():
    assert bid_quality(0.70) == pytest.approx(1.0)


def test_bid_boundary_089():
    assert bid_quality(0.89) == pytest.approx(1.0)
    assert bid_quality(0.90) == pytest.approx(2.5)


def test_bid_mid_low():
    assert bid_quality(1.10) == pytest.approx(2.5)


def test_bid_boundary_144():
    assert bid_quality(1.44) == pytest.approx(2.5)
    assert bid_quality(1.45) == pytest.approx(3.5)


def test_bid_mid():
    assert bid_quality(2.00) == pytest.approx(3.5)


def test_bid_boundary_233():
    assert bid_quality(2.33) == pytest.approx(3.5)
    assert bid_quality(2.34) == pytest.approx(4.5)


def test_bid_sweet_spot():
    assert bid_quality(3.00) == pytest.approx(4.5)


def test_bid_boundary_377():
    assert bid_quality(3.77) == pytest.approx(4.5)
    assert bid_quality(3.78) == pytest.approx(2.5)


def test_bid_high_fallback():
    # Non-monotonic: 5.00 is in the (3.77, 6.10] band → 2.5
    assert bid_quality(5.00) == pytest.approx(2.5)


def test_bid_boundary_610():
    assert bid_quality(6.10) == pytest.approx(2.5)
    assert bid_quality(6.11) == pytest.approx(0.0)


def test_bid_very_high():
    assert bid_quality(7.00) == pytest.approx(0.0)
