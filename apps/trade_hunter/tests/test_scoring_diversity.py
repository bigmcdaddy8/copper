"""Unit tests for cyclical_diversity_quality and sector_diversity_quality."""

import pytest

from trade_hunter.pipeline.scoring import cyclical_diversity_quality, sector_diversity_quality

# ---------------------------------------------------------------------------
# cyclical_diversity_quality
# ---------------------------------------------------------------------------


def test_cyclical_empty_active():
    assert cyclical_diversity_quality("Growth", []) == pytest.approx(5.0)


def test_cyclical_low_concentration():
    # 2 of 10 in "Growth" = 20% → <= 21% → 5.0
    active = [
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
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(5.0)


def test_cyclical_boundary_21pct():
    # exactly 21 of 100 → 21% → <= 21% → 5.0
    active = ["Growth"] * 21 + ["Economic"] * 79
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(5.0)


def test_cyclical_just_above_21pct():
    # 22 of 100 → 22% → > 21% → 2.0
    active = ["Growth"] * 22 + ["Economic"] * 78
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(2.0)


def test_cyclical_mid_concentration():
    # 4 of 10 = 40% → > 21% and <= 55% → 2.0
    active = ["Growth"] * 4 + ["Economic"] * 6
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(2.0)


def test_cyclical_boundary_55pct():
    # exactly 55 of 100 → 55% → <= 55% → 2.0
    active = ["Growth"] * 55 + ["Economic"] * 45
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(2.0)


def test_cyclical_just_above_55pct():
    # 56 of 100 → 56% → > 55% → 0.0
    active = ["Growth"] * 56 + ["Economic"] * 44
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(0.0)


def test_cyclical_high_concentration():
    # 6 of 10 = 60% → > 55% → 0.0
    active = ["Growth"] * 6 + ["Economic"] * 4
    assert cyclical_diversity_quality("Growth", active) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# sector_diversity_quality
# ---------------------------------------------------------------------------


def test_sector_empty_active():
    assert sector_diversity_quality("Information Technology", []) == pytest.approx(5.0)


def test_sector_low_concentration():
    # 1 of 50 = 2% → <= 3% → 5.0
    active = ["Information Technology"] + ["Financials"] * 49
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(5.0)


def test_sector_boundary_3pct():
    # exactly 3 of 100 → 3% → <= 3% → 5.0
    active = ["Information Technology"] * 3 + ["Financials"] * 97
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(5.0)


def test_sector_just_above_3pct():
    # 4 of 100 → 4% → > 3% → 2.0
    active = ["Information Technology"] * 4 + ["Financials"] * 96
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(2.0)


def test_sector_mid_concentration():
    # 10 of 100 = 10% → > 3% and <= 13% → 2.0
    active = ["Information Technology"] * 10 + ["Financials"] * 90
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(2.0)


def test_sector_boundary_13pct():
    # exactly 13 of 100 → 13% → <= 13% → 2.0
    active = ["Information Technology"] * 13 + ["Financials"] * 87
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(2.0)


def test_sector_just_above_13pct():
    # 14 of 100 → 14% → > 13% → 0.0
    active = ["Information Technology"] * 14 + ["Financials"] * 86
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(0.0)


def test_sector_high_concentration():
    # 3 of 5 = 60% → > 13% → 0.0
    active = ["Information Technology"] * 3 + ["Financials"] * 2
    assert sector_diversity_quality("Information Technology", active) == pytest.approx(0.0)
