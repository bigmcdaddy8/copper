YFINANCE_SECTOR_MAP: dict[str, str] = {
    "Technology": "Information Technology",
    "Healthcare": "Health Care",
    "Financial Services": "Financials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Basic Materials": "Materials",
    "Communication Services": "Communication Services",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "Industrials": "Industrials",
    "Energy": "Energy",
}

SECTOR_MAP: dict[str, str] = {
    "Basic Materials": "Materials",
    "Capital Goods": "Industrials",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer/Non-Cyclical": "Consumer Staples",
    "Energy": "Energy",
    "Financial": "Financials",
    "Healthcare": "Health Care",
    "Services": "Communication Services",
    "Technology": "Information Technology",
    "Transportation": "Consumer Discretionary",
    "Utilities": "Utilities",
    "Real Estate": "Real Estate",
    "REIT": "Real Estate",
}

BUCKET_MAP: dict[str, str] = {
    "Materials": "Economic",
    "Industrials": "Economic",
    "Consumer Discretionary": "Growth",
    "Consumer Staples": "Defensive",
    "Energy": "Economic",
    "Financials": "Economic",
    "Health Care": "Defensive",
    "Communication Services": "Growth",
    "Information Technology": "Growth",
    "Utilities": "Defensive",
    "Real Estate": "Economic",
}


def normalize_sector(raw: str) -> str | None:
    """Return the standard sector name for a TastyTrade raw sector value, or None if unrecognized."""
    return SECTOR_MAP.get(raw.strip())


def assign_bucket(standard_sector: str) -> str:
    """Return the cyclical bucket for a standard sector name."""
    return BUCKET_MAP[standard_sector]
