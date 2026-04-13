"""Tests for delta-based strike selector (K9-0040)."""
from __future__ import annotations

import pytest
from datetime import date
from bic.models import OptionChain, OptionContract
from K9.tradier.selector import (
    select_0dte_expiration,
    select_long_call,
    select_long_put,
    select_short_call,
    select_short_put,
)


# ------------------------------------------------------------------ #
# Fixture: synthetic SPX chain around 5820                           #
# ------------------------------------------------------------------ #

def _make_chain(underlying: float = 5820.0) -> OptionChain:
    """Build a minimal OptionChain with puts and calls at 5pt increments."""
    options = []
    for offset in range(-30, 35, 5):
        strike = underlying + offset
        c_delta = max(0.01, min(0.99, 0.5 + 0.02 * (offset / 5)))
        p_delta = c_delta - 1.0
        options.append(OptionContract(strike, "CALL", 0.50, 0.60, round(c_delta, 2)))
        options.append(OptionContract(strike, "PUT",  0.50, 0.60, round(p_delta, 2)))
    return OptionChain("SPX", date(2026, 1, 5), options)


CHAIN = _make_chain()


# ------------------------------------------------------------------ #
# select_0dte_expiration                                              #
# ------------------------------------------------------------------ #

def test_select_0dte_finds_today():
    today = date(2026, 1, 5)
    expirations = [date(2026, 1, 5), date(2026, 1, 12), date(2026, 1, 19)]
    assert select_0dte_expiration(expirations, today) == today


def test_select_0dte_raises_when_missing():
    today = date(2026, 1, 6)
    expirations = [date(2026, 1, 5), date(2026, 1, 12)]
    with pytest.raises(ValueError, match="No 0DTE"):
        select_0dte_expiration(expirations, today)


# ------------------------------------------------------------------ #
# select_short_put / select_short_call                               #
# ------------------------------------------------------------------ #

def test_select_short_put_returns_put(monkeypatch):
    put = select_short_put(CHAIN, target_delta=20)
    assert put.option_type == "PUT"
    assert put.delta < 0


def test_select_short_call_returns_call():
    call = select_short_call(CHAIN, target_delta=20)
    assert call.option_type == "CALL"
    assert call.delta > 0


def test_select_short_put_no_puts_raises():
    calls_only = OptionChain(
        "SPX",
        date(2026, 1, 5),
        [OptionContract(5820.0, "CALL", 1.0, 1.1, 0.50)],
    )
    with pytest.raises(ValueError, match="No PUT"):
        select_short_put(calls_only, 20)


def test_select_short_call_no_calls_raises():
    puts_only = OptionChain(
        "SPX",
        date(2026, 1, 5),
        [OptionContract(5820.0, "PUT", 1.0, 1.1, -0.50)],
    )
    with pytest.raises(ValueError, match="No CALL"):
        select_short_call(puts_only, 20)


# ------------------------------------------------------------------ #
# select_long_put / select_long_call                                 #
# ------------------------------------------------------------------ #

def test_select_long_put_is_below_short():
    short_put = select_short_put(CHAIN, target_delta=20)
    long_put = select_long_put(CHAIN, short_put, wing_size=5)
    assert long_put.option_type == "PUT"
    assert long_put.strike == short_put.strike - 5


def test_select_long_call_is_above_short():
    short_call = select_short_call(CHAIN, target_delta=20)
    long_call = select_long_call(CHAIN, short_call, wing_size=5)
    assert long_call.option_type == "CALL"
    assert long_call.strike == short_call.strike + 5


def test_select_long_put_missing_wing_raises():
    # Create a put at a strike that has no wing 5 points below
    short_put = OptionContract(5790.0, "PUT", 0.5, 0.6, -0.20)
    with pytest.raises(ValueError, match="No PUT contract found at strike"):
        select_long_put(CHAIN, short_put, wing_size=5)  # 5785 not in chain
