"""Mock-based unit tests for tradier/enrichment.py."""

from datetime import date
from unittest.mock import MagicMock

import pandas as pd
import pytest

from trade_hunter.tradier.client import TradierAPIError
from trade_hunter.tradier.enrichment import enrich_candidates

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

# A third Friday within DTE window when run_date = 2025-03-19
_EXPIRATION = "2025-04-18"  # DTE=30
_RUN_DATE = date(2025, 3, 19)

_PUT_CONTRACT = {
    "option_type": "put",
    "strike": 470.0,
    "delta": -0.21,
    "bid": 1.10,
    "ask": 1.20,
    "open_interest": 500,
    "last": 1.15,
}

_CALL_CONTRACT = {
    "option_type": "call",
    "strike": 490.0,
    "delta": 0.21,
    "bid": 0.90,
    "ask": 1.00,
    "open_interest": 300,
    "last": 0.95,
}

_LAST_PRICE = 480.0


def _make_candidates(*symbols: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Symbol": list(symbols),
            "IV Rank": [45.0] * len(symbols),
            "Sector": ["Technology"] * len(symbols),
        }
    )


def _mock_client(
    expirations=None,
    last_price=_LAST_PRICE,
    chain=None,
    expiration_error=None,
    last_price_error=None,
    chain_error=None,
) -> MagicMock:
    client = MagicMock()

    if expiration_error:
        client.get_option_expirations.side_effect = expiration_error
    else:
        client.get_option_expirations.return_value = (
            expirations if expirations is not None else [_EXPIRATION]
        )

    if last_price_error:
        client.get_last_price.side_effect = last_price_error
    else:
        client.get_last_price.return_value = last_price

    if chain_error:
        client.get_option_chain.side_effect = chain_error
    else:
        client.get_option_chain.return_value = (
            chain if chain is not None else [_PUT_CONTRACT, _CALL_CONTRACT]
        )

    return client


# ---------------------------------------------------------------------------
# Success cases
# ---------------------------------------------------------------------------


def test_enrich_bull_success():
    candidates = _make_candidates("SPY")
    client = _mock_client()

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert len(result) == 1
    assert warnings == []
    row = result.iloc[0]
    assert row["Symbol"] == "SPY"
    assert row["Expiration Date"] == _EXPIRATION
    assert row["DTE"] == 30
    assert row["Last Price"] == pytest.approx(_LAST_PRICE)
    assert row["Option Type"] == "put"
    assert row["Strike"] == pytest.approx(470.0)
    assert row["Delta"] == pytest.approx(-0.21)
    assert row["Bid"] == pytest.approx(1.10)
    assert row["Ask"] == pytest.approx(1.20)
    assert int(row["Open Interest"]) == 500


def test_enrich_bear_success():
    candidates = _make_candidates("SPY")
    client = _mock_client()

    result, warnings = enrich_candidates(candidates, "BEAR", client, _RUN_DATE)

    assert len(result) == 1
    assert warnings == []
    assert result.iloc[0]["Option Type"] == "call"
    assert result.iloc[0]["Strike"] == pytest.approx(490.0)
    assert result.iloc[0]["Delta"] == pytest.approx(0.21)


# ---------------------------------------------------------------------------
# Skip — no qualifying expiration
# ---------------------------------------------------------------------------


def test_enrich_no_expiration():
    """get_option_expirations returns dates but none qualify (all outside DTE window)."""
    candidates = _make_candidates("SPY")
    # Only weekly expirations, none of which are third Fridays
    client = _mock_client(expirations=["2025-04-04", "2025-04-11", "2025-04-25"])

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert result.empty
    assert len(warnings) == 1
    assert "no qualifying monthly expiration" in warnings[0]
    assert "SPY" in warnings[0]


# ---------------------------------------------------------------------------
# Skip — no qualifying option
# ---------------------------------------------------------------------------


def test_enrich_no_qualifying_option():
    """Chain has puts but none with delta <= -0.21."""
    chain = [
        {
            "option_type": "put",
            "strike": 490.0,
            "delta": -0.15,
            "bid": 0.5,
            "ask": 0.6,
            "open_interest": 100,
            "last": 0.55,
        }
    ]
    candidates = _make_candidates("SPY")
    client = _mock_client(chain=chain)

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert result.empty
    assert len(warnings) == 1
    assert "no qualifying put" in warnings[0]


# ---------------------------------------------------------------------------
# Skip — API errors
# ---------------------------------------------------------------------------


def test_enrich_api_error_expirations():
    candidates = _make_candidates("SPY")
    client = _mock_client(expiration_error=TradierAPIError(500, "server error"))

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert result.empty
    assert len(warnings) == 1
    assert "Tradier API error" in warnings[0]
    assert "SPY" in warnings[0]


def test_enrich_api_error_chain():
    candidates = _make_candidates("SPY")
    client = _mock_client(chain_error=TradierAPIError(429, "rate limit"))

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert result.empty
    assert len(warnings) == 1
    assert "Tradier API error" in warnings[0]


# ---------------------------------------------------------------------------
# Multiple candidates — partial failure
# ---------------------------------------------------------------------------


def test_enrich_multiple_one_fails():
    """Two tickers; second has no qualifying expiration → one enriched row, one warning."""
    candidates = _make_candidates("SPY", "NOPE")

    call_count = 0

    def expiration_side_effect(symbol):
        nonlocal call_count
        call_count += 1
        if symbol == "SPY":
            return [_EXPIRATION]
        return ["2025-04-04"]  # weekly only — won't qualify

    client = MagicMock()
    client.get_option_expirations.side_effect = expiration_side_effect
    client.get_last_price.return_value = _LAST_PRICE
    client.get_option_chain.return_value = [_PUT_CONTRACT, _CALL_CONTRACT]

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert len(result) == 1
    assert result.iloc[0]["Symbol"] == "SPY"
    assert len(warnings) == 1
    assert "NOPE" in warnings[0]


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_enrich_empty_candidates():
    candidates = pd.DataFrame(columns=["Symbol", "IV Rank"])
    client = _mock_client()

    result, warnings = enrich_candidates(candidates, "BULL", client, _RUN_DATE)

    assert result.empty
    assert warnings == []
    client.get_option_expirations.assert_not_called()
    client.get_last_price.assert_not_called()
    client.get_option_chain.assert_not_called()
