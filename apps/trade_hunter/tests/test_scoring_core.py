"""Unit tests for pipeline/scoring.py — core quality metric functions."""

import pandas as pd
import pytest
from datetime import date

from trade_hunter.pipeline.scoring import (
    _resolve_earnings_date,
    bpr_quality,
    ivp_quality,
    ivr_quality,
    open_interest_quality,
    spread_pct_quality,
)

# ---------------------------------------------------------------------------
# ivr_quality
# ---------------------------------------------------------------------------


def test_ivr_band_zero():
    assert ivr_quality(5.0) == 0.0


def test_ivr_boundary_10_bottom():
    assert ivr_quality(10.0) == 0.0


def test_ivr_boundary_10_top():
    assert ivr_quality(10.01) == 1.0


def test_ivr_band_one():
    assert ivr_quality(15.0) == 1.0


def test_ivr_boundary_20_bottom():
    assert ivr_quality(20.0) == 1.0


def test_ivr_boundary_20_top():
    assert ivr_quality(20.01) == 2.0


def test_ivr_band_two():
    assert ivr_quality(25.0) == 2.0


def test_ivr_boundary_30_bottom():
    assert ivr_quality(30.0) == 2.0


def test_ivr_boundary_30_top():
    assert ivr_quality(30.01) == 4.0


def test_ivr_band_four():
    assert ivr_quality(40.0) == 4.0


def test_ivr_boundary_50_bottom():
    assert ivr_quality(50.0) == 4.0


def test_ivr_boundary_50_top():
    assert ivr_quality(50.01) == 5.0


def test_ivr_band_five():
    assert ivr_quality(75.0) == 5.0


# ---------------------------------------------------------------------------
# ivp_quality — identical table, tested independently
# ---------------------------------------------------------------------------


def test_ivp_band_zero():
    assert ivp_quality(5.0) == 0.0


def test_ivp_boundary_10():
    assert ivp_quality(10.0) == 0.0
    assert ivp_quality(10.01) == 1.0


def test_ivp_band_one():
    assert ivp_quality(15.0) == 1.0


def test_ivp_boundary_20():
    assert ivp_quality(20.0) == 1.0
    assert ivp_quality(20.01) == 2.0


def test_ivp_band_two():
    assert ivp_quality(25.0) == 2.0


def test_ivp_boundary_30():
    assert ivp_quality(30.0) == 2.0
    assert ivp_quality(30.01) == 4.0


def test_ivp_band_four():
    assert ivp_quality(40.0) == 4.0


def test_ivp_boundary_50():
    assert ivp_quality(50.0) == 4.0
    assert ivp_quality(50.01) == 5.0


def test_ivp_band_five():
    assert ivp_quality(75.0) == 5.0


# ---------------------------------------------------------------------------
# open_interest_quality
# ---------------------------------------------------------------------------


def test_oi_boundary_10_bottom():
    assert open_interest_quality(10) == 0.0


def test_oi_boundary_10_top():
    assert open_interest_quality(11) == 2.0


def test_oi_mid_band_two():
    assert open_interest_quality(50) == 2.0


def test_oi_boundary_100_bottom():
    assert open_interest_quality(100) == 2.0


def test_oi_boundary_100_top():
    assert open_interest_quality(101) == 4.5


def test_oi_mid_band_four_five():
    assert open_interest_quality(500) == 4.5


def test_oi_boundary_1000_bottom():
    assert open_interest_quality(1000) == 4.5


def test_oi_boundary_1000_top():
    assert open_interest_quality(1001) == 5.0


def test_oi_high():
    assert open_interest_quality(5000) == 5.0


# ---------------------------------------------------------------------------
# spread_pct_quality
# ---------------------------------------------------------------------------


def test_spread_band_five():
    # bid=1.00, ask=1.01 → mid=1.005, spread≈1.0% → ≤2% → 5.0
    assert spread_pct_quality(1.00, 1.01) == pytest.approx(5.0)


def test_spread_band_four_five():
    # bid=1.00, ask=1.03 → mid=1.015, spread≈2.96% → 2–4% → 4.5
    assert spread_pct_quality(1.00, 1.03) == pytest.approx(4.5)


def test_spread_band_four():
    # bid=1.00, ask=1.05 → mid=1.025, spread≈4.88% → 4–6% → 4.0
    assert spread_pct_quality(1.00, 1.05) == pytest.approx(4.0)


def test_spread_band_three():
    # bid=1.00, ask=1.07 → mid=1.035, spread≈6.76% → 6–8% → 3.0
    assert spread_pct_quality(1.00, 1.07) == pytest.approx(3.0)


def test_spread_band_two():
    # bid=1.00, ask=1.10 → mid=1.05, spread≈9.52% → 8–12% → 2.0
    assert spread_pct_quality(1.00, 1.10) == pytest.approx(2.0)


def test_spread_band_one():
    # bid=1.00, ask=1.16 → mid=1.08, spread≈14.8% → 12–20% → 1.0
    assert spread_pct_quality(1.00, 1.16) == pytest.approx(1.0)


def test_spread_band_zero():
    # bid=1.00, ask=1.25 → mid=1.125, spread≈22.2% → >20% → 0.0
    assert spread_pct_quality(1.00, 1.25) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# bpr_quality
# ---------------------------------------------------------------------------


def test_bpr_put_large_underlying():
    # underlying=500, put_strike=480, bid=2.00
    # OTM=20, BPR=max(82, 52, 4.5)*100=8200 → > 4500 → 0.0
    assert bpr_quality(500.0, 480.0, 2.00, "put") == pytest.approx(0.0)


def test_bpr_call_large_underlying():
    # underlying=500, call_strike=520, bid=2.00
    # OTM=20, same formula → BPR=8200 → 0.0
    assert bpr_quality(500.0, 520.0, 2.00, "call") == pytest.approx(0.0)


def test_bpr_mid_band():
    # underlying=100, put_strike=95, bid=0.80
    # OTM=5, BPR=max(15.8, 10.8, 3.3)*100=1580 → > 1500 and <= 3000 → 3.5
    assert bpr_quality(100.0, 95.0, 0.80, "put") == pytest.approx(3.5)


def test_bpr_sweet_spot():
    # underlying=30, put_strike=29, bid=0.40
    # OTM=1, BPR=max(5.4, 3.4, 2.9)*100=540 → > 500 and <= 1500 → 5.0
    assert bpr_quality(30.0, 29.0, 0.40, "put") == pytest.approx(5.0)


def test_bpr_low_band():
    # underlying=10, put_strike=9, bid=0.20
    # OTM=1, BPR=max(1.2, 1.2, 2.7)*100=270 → <= 500 → 3.0
    assert bpr_quality(10.0, 9.0, 0.20, "put") == pytest.approx(3.0)


def test_bpr_call_otm_direction():
    # Verify call OTM_amount uses call_strike - underlying (not underlying - call_strike)
    # underlying=30, call_strike=31, bid=0.40
    # OTM=1, same as put test → BPR=540 → 5.0
    assert bpr_quality(30.0, 31.0, 0.40, "call") == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# _resolve_earnings_date — TastyTrade "Earnings At" format
# ---------------------------------------------------------------------------

def _row(earnings_at=None, upcoming=None):
    data = {}
    if earnings_at is not None:
        data["Earnings At"] = earnings_at
    if upcoming is not None:
        data["Upcoming Announce Date"] = upcoming
    return pd.Series(data)


def test_resolve_earnings_plain_month_day():
    run = date(2026, 4, 8)
    result = _resolve_earnings_date(_row("May 27"), run)
    assert result == date(2026, 5, 27)


def test_resolve_earnings_with_gt_suffix():
    run = date(2026, 4, 8)
    result = _resolve_earnings_date(_row("Apr 16 >"), run)
    assert result == date(2026, 4, 16)


def test_resolve_earnings_with_lt_suffix():
    run = date(2026, 4, 8)
    result = _resolve_earnings_date(_row("Apr 29 <"), run)
    assert result == date(2026, 4, 29)


def test_resolve_earnings_past_month_wraps_to_next_year():
    # "Jan 15" when run_date is April — should resolve to next January
    run = date(2026, 4, 8)
    result = _resolve_earnings_date(_row("Jan 15"), run)
    assert result == date(2027, 1, 15)


def test_resolve_earnings_empty_falls_back():
    run = date(2026, 4, 8)
    result = _resolve_earnings_date(_row(""), run)
    assert result == run + __import__("datetime").timedelta(days=70)


def test_resolve_earnings_missing_col_falls_back():
    run = date(2026, 4, 8)
    result = _resolve_earnings_date(pd.Series({}), run)
    assert result == run + __import__("datetime").timedelta(days=70)
