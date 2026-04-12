"""Unit tests for options.py — all pure functions, no mocking needed."""

from datetime import date, timedelta

from tradier_sniffer.options import (
    build_occ_symbol,
    build_sic_legs,
    calc_sic_credit,
    find_delta_strike,
    get_0dte_expiration,
)


# ---------------------------------------------------------------------------
# build_occ_symbol
# ---------------------------------------------------------------------------


def test_build_occ_symbol_put():
    assert build_occ_symbol("SPX", "2024-01-19", "P", 4500.0) == "SPX240119P04500000"


def test_build_occ_symbol_call():
    assert build_occ_symbol("SPX", "2024-01-19", "C", 4600.0) == "SPX240119C04600000"


# ---------------------------------------------------------------------------
# get_0dte_expiration
# ---------------------------------------------------------------------------


def test_get_0dte_today_present():
    today = date.today().isoformat()
    expirations = [today, (date.today() + timedelta(days=7)).isoformat()]
    assert get_0dte_expiration(expirations) == today


def test_get_0dte_nearest_future():
    future1 = (date.today() + timedelta(days=1)).isoformat()
    future2 = (date.today() + timedelta(days=7)).isoformat()
    # today not present, past date present
    past = (date.today() - timedelta(days=1)).isoformat()
    expirations = [past, future2, future1]
    assert get_0dte_expiration(expirations) == future1


def test_get_0dte_empty():
    assert get_0dte_expiration([]) is None


# ---------------------------------------------------------------------------
# find_delta_strike
# ---------------------------------------------------------------------------

_CHAIN = [
    {"option_type": "put", "strike": 4400.0, "bid": 0.50, "ask": 0.60, "greeks": {"delta": -0.15}},
    {"option_type": "put", "strike": 4450.0, "bid": 0.80, "ask": 0.90, "greeks": {"delta": -0.21}},
    {"option_type": "put", "strike": 4500.0, "bid": 1.20, "ask": 1.30, "greeks": {"delta": -0.30}},
    {"option_type": "call", "strike": 4600.0, "bid": 0.75, "ask": 0.85, "greeks": {"delta": 0.21}},
    {"option_type": "call", "strike": 4650.0, "bid": 0.45, "ask": 0.55, "greeks": {"delta": 0.15}},
    {"option_type": "call", "strike": 4700.0, "bid": 0.20, "ask": 0.30, "greeks": {"delta": 0.09}},
]


def test_find_delta_strike_nearest():
    result = find_delta_strike(_CHAIN, 0.20, "put")
    assert result is not None
    assert result["strike"] == 4450.0  # delta -0.21 is closest to 0.20


def test_find_delta_strike_none_if_no_greeks():
    chain = [
        {"option_type": "put", "strike": 4400.0, "greeks": None},
        {"option_type": "put", "strike": 4450.0, "greeks": None},
    ]
    assert find_delta_strike(chain, 0.20, "put") is None


# ---------------------------------------------------------------------------
# build_sic_legs
# ---------------------------------------------------------------------------

_FULL_CHAIN = [
    {"option_type": "put",  "strike": 4440.0, "bid": 0.30, "ask": 0.40, "symbol": "SPX240119P04440000", "greeks": {"delta": -0.12}},
    {"option_type": "put",  "strike": 4450.0, "bid": 0.80, "ask": 0.90, "symbol": "SPX240119P04450000", "greeks": {"delta": -0.21}},
    {"option_type": "put",  "strike": 4460.0, "bid": 1.20, "ask": 1.30, "symbol": "SPX240119P04460000", "greeks": {"delta": -0.30}},
    {"option_type": "call", "strike": 4550.0, "bid": 0.75, "ask": 0.85, "symbol": "SPX240119C04550000", "greeks": {"delta": 0.21}},
    {"option_type": "call", "strike": 4560.0, "bid": 0.45, "ask": 0.55, "symbol": "SPX240119C04560000", "greeks": {"delta": 0.15}},
]


def test_build_sic_legs_complete():
    # short_put=4450 (delta 0.21 closest to 0.20), long_put=4440 (4450-10), short_call=4550, long_call=4560
    result = build_sic_legs(_FULL_CHAIN, target_delta=0.20, wing_width=10.0)
    assert result is not None
    assert result["short_put"]["strike"] == 4450.0
    assert result["long_put"]["strike"] == 4440.0
    assert result["short_call"]["strike"] == 4550.0
    assert result["long_call"]["strike"] == 4560.0


def test_build_sic_legs_none_if_wing_missing():
    # No put at 4440 (would need short_put=4450 minus 10)
    chain_no_wing = [o for o in _FULL_CHAIN if o["strike"] != 4440.0]
    result = build_sic_legs(chain_no_wing, target_delta=0.20, wing_width=10.0)
    assert result is None


# ---------------------------------------------------------------------------
# calc_sic_credit
# ---------------------------------------------------------------------------


def test_calc_sic_credit():
    legs = {
        "short_put":  {"bid": 1.20, "ask": 1.30},
        "short_call": {"bid": 0.80, "ask": 0.90},
        "long_put":   {"bid": 0.30, "ask": 0.40},  # we pay ask
        "long_call":  {"bid": 0.10, "ask": 0.20},
    }
    # (1.20 + 0.80) - (0.40 + 0.20) = 2.00 - 0.60 = 1.40
    assert calc_sic_credit(legs) == 1.40
