import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from holodeck.pricing import (
    build_option_chain,
    compute_delta,
    compute_option_price,
)

TZ = "America/Chicago"
NOW_MID = datetime(2026, 1, 2, 10, 30, tzinfo=ZoneInfo(TZ))   # 270 minutes to close
NOW_LATE = datetime(2026, 1, 2, 14, 0, tzinfo=ZoneInfo(TZ))    # 60 minutes to close
UNDERLYING = 5825.0
EXP = date(2026, 1, 2)


def test_build_chain_strike_count():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    assert len(chain.options) == 122  # 61 strikes × 2 types


def test_build_chain_has_calls_and_puts():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    types = {c.option_type for c in chain.options}
    assert "CALL" in types
    assert "PUT" in types


def test_build_chain_strike_range():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    strikes = sorted({c.strike for c in chain.options})
    assert min(strikes) == round(UNDERLYING / 5) * 5 - 150
    assert max(strikes) == round(UNDERLYING / 5) * 5 + 150


def test_atm_call_delta_near_50():
    # ATM call should have delta close to 0.50
    atm_strike = round(UNDERLYING / 5) * 5
    delta = compute_delta(UNDERLYING, atm_strike, "CALL", 270)
    assert 0.40 <= delta <= 0.60


def test_atm_put_delta_near_neg50():
    atm_strike = round(UNDERLYING / 5) * 5
    delta = compute_delta(UNDERLYING, atm_strike, "PUT", 270)
    assert -0.60 <= delta <= -0.40


def test_20_delta_put_exists():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    puts = [c for c in chain.options if c.option_type == "PUT"]
    near_20 = [c for c in puts if -0.25 <= c.delta <= -0.15]
    assert len(near_20) >= 1, "No put with delta near -0.20 found"


def test_20_delta_call_exists():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    calls = [c for c in chain.options if c.option_type == "CALL"]
    near_20 = [c for c in calls if 0.15 <= c.delta <= 0.25]
    assert len(near_20) >= 1, "No call with delta near +0.20 found"


def test_itm_call_delta_high():
    # Strike 100 below underlying → deep ITM call
    delta = compute_delta(UNDERLYING, UNDERLYING - 100, "CALL", 270)
    assert delta > 0.70


def test_otm_call_delta_low():
    # Strike 100 above underlying → deep OTM call
    delta = compute_delta(UNDERLYING, UNDERLYING + 100, "CALL", 270)
    assert delta < 0.30


def test_prices_at_nickel():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    for c in chain.options:
        assert round(c.bid / 0.05) * 0.05 == pytest.approx(c.bid, abs=0.001)
        assert round(c.ask / 0.05) * 0.05 == pytest.approx(c.ask, abs=0.001)


def test_bid_less_than_ask():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    for c in chain.options:
        assert c.bid < c.ask


def test_atm_more_expensive_than_otm():
    atm_strike = round(UNDERLYING / 5) * 5
    otm_strike = atm_strike + 50
    atm_bid, atm_ask = compute_option_price(UNDERLYING, atm_strike, "CALL", 270)
    otm_bid, otm_ask = compute_option_price(UNDERLYING, otm_strike, "CALL", 270)
    atm_mid = (atm_bid + atm_ask) / 2
    otm_mid = (otm_bid + otm_ask) / 2
    assert atm_mid > otm_mid


def test_extrinsic_decays_over_time():
    strike = round(UNDERLYING / 5) * 5  # ATM
    bid_early, ask_early = compute_option_price(UNDERLYING, strike, "PUT", 270)
    bid_late, ask_late = compute_option_price(UNDERLYING, strike, "PUT", 60)
    mid_early = (bid_early + ask_early) / 2
    mid_late = (bid_late + ask_late) / 2
    assert mid_early > mid_late


def test_min_bid_is_nickel():
    chain = build_option_chain(UNDERLYING, EXP, NOW_MID)
    for c in chain.options:
        assert c.bid >= 0.05
