import pytest

from trade_hunter.pipeline.normalize import (
    BUCKET_MAP,
    SECTOR_MAP,
    assign_bucket,
    normalize_sector,
)


def test_sector_map_complete():
    expected_raw = {
        "Basic Materials",
        "Capital Goods",
        "Consumer Cyclical",
        "Consumer/Non-Cyclical",
        "Energy",
        "Financial",
        "Healthcare",
        "Services",
        "Technology",
        "Transportation",
        "Utilities",
        "Real Estate",
        "REIT",
    }
    assert set(SECTOR_MAP.keys()) == expected_raw


def test_bucket_map_complete():
    expected_standard = {
        "Materials",
        "Industrials",
        "Consumer Discretionary",
        "Consumer Staples",
        "Energy",
        "Financials",
        "Health Care",
        "Communication Services",
        "Information Technology",
        "Utilities",
        "Real Estate",
    }
    assert set(BUCKET_MAP.keys()) == expected_standard


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("REIT", "Real Estate"),
        ("Transportation", "Consumer Discretionary"),
        ("Technology", "Information Technology"),
        ("Healthcare", "Health Care"),
        ("Services", "Communication Services"),
        ("Financial", "Financials"),
        ("Consumer/Non-Cyclical", "Consumer Staples"),
    ],
)
def test_normalize_sector_known(raw, expected):
    assert normalize_sector(raw) == expected


def test_normalize_sector_unknown():
    assert normalize_sector("Bogus Sector") is None


def test_normalize_sector_strips_whitespace():
    assert normalize_sector("  Technology  ") == "Information Technology"


@pytest.mark.parametrize(
    "standard, expected_bucket",
    [
        ("Information Technology", "Growth"),
        ("Communication Services", "Growth"),
        ("Consumer Discretionary", "Growth"),
        ("Health Care", "Defensive"),
        ("Consumer Staples", "Defensive"),
        ("Utilities", "Defensive"),
        ("Financials", "Economic"),
        ("Energy", "Economic"),
        ("Real Estate", "Economic"),
        ("Materials", "Economic"),
        ("Industrials", "Economic"),
    ],
)
def test_assign_bucket(standard, expected_bucket):
    assert assign_bucket(standard) == expected_bucket
