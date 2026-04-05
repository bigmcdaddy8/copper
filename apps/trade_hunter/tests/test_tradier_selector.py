"""Unit tests for tradier/selector.py — all inline synthetic data, no mocking required."""

from datetime import date

from trade_hunter.tradier.selector import select_call, select_expiration, select_put

# ---------------------------------------------------------------------------
# Fixtures / constants
#
# Third Fridays near run_date = 2025-03-19:
#   2025-03-21  DTE=2   (too early)
#   2025-04-18  DTE=30  (exactly min_dte)
#   2025-05-16  DTE=58  (within window)
#   2025-06-20  DTE=93  (too late)
#
# Weekly (non-third) Fridays in April 2025:
#   2025-04-04, 2025-04-11, 2025-04-25
# ---------------------------------------------------------------------------

RUN_DATE = date(2025, 3, 19)

MONTHLY_APR = "2025-04-18"  # DTE=30 from RUN_DATE
MONTHLY_MAY = "2025-05-16"  # DTE=58 from RUN_DATE
MONTHLY_MAR = "2025-03-21"  # DTE=2  — inside same month but too soon
MONTHLY_JUN = "2025-06-20"  # DTE=93 — beyond max_dte

WEEKLY_APR_04 = "2025-04-04"
WEEKLY_APR_11 = "2025-04-11"
WEEKLY_APR_25 = "2025-04-25"


# ---------------------------------------------------------------------------
# select_expiration
# ---------------------------------------------------------------------------


def test_select_expiration_nearest_monthly():
    """Two qualifying monthlies — returns the one with lower DTE (April)."""
    result = select_expiration([MONTHLY_MAY, MONTHLY_APR], RUN_DATE)
    assert result == MONTHLY_APR


def test_select_expiration_skips_weekly():
    """Weekly expirations within the DTE window are ignored; monthly is returned."""
    expirations = [WEEKLY_APR_04, WEEKLY_APR_11, WEEKLY_APR_25, MONTHLY_APR]
    result = select_expiration(expirations, RUN_DATE)
    assert result == MONTHLY_APR


def test_select_expiration_no_qualifying_dte():
    """All monthlies are outside the DTE window → None."""
    expirations = [MONTHLY_MAR, MONTHLY_JUN]
    result = select_expiration(expirations, RUN_DATE)
    assert result is None


def test_select_expiration_empty_list():
    result = select_expiration([], RUN_DATE)
    assert result is None


def test_select_expiration_boundary_dte_min():
    """Expiration at exactly min_dte (30) qualifies."""
    # RUN_DATE=2025-03-19, MONTHLY_APR=2025-04-18 → DTE=30
    result = select_expiration([MONTHLY_APR], RUN_DATE, min_dte=30, max_dte=60)
    assert result == MONTHLY_APR


def test_select_expiration_boundary_dte_max():
    """Expiration at exactly max_dte (60) qualifies."""
    # run_date = 2025-03-17 → 2025-05-16 is DTE=60
    run = date(2025, 3, 17)
    result = select_expiration([MONTHLY_MAY], run, min_dte=30, max_dte=60)
    assert result == MONTHLY_MAY


def test_select_expiration_dte_just_outside():
    """DTE=29 (one below min) → None."""
    # run_date = 2025-03-20 → 2025-04-18 is DTE=29
    run = date(2025, 3, 20)
    result = select_expiration([MONTHLY_APR], run, min_dte=30, max_dte=60)
    assert result is None


# ---------------------------------------------------------------------------
# select_put
# ---------------------------------------------------------------------------

_PUT_CONTRACTS = [
    {"option_type": "put", "strike": 480.0, "delta": -0.19},  # delta too high (> -0.21)
    {"option_type": "put", "strike": 470.0, "delta": -0.21},  # exactly at threshold ← best
    {"option_type": "put", "strike": 460.0, "delta": -0.25},
    {"option_type": "put", "strike": 450.0, "delta": -0.35},
    {"option_type": "call", "strike": 520.0, "delta": 0.22},  # wrong side — ignored
]


def test_select_put_picks_closest_to_threshold():
    """Returns the put with delta closest to -0.21 (highest qualifying delta)."""
    result = select_put(_PUT_CONTRACTS)
    assert result is not None
    assert result["delta"] == -0.21
    assert result["strike"] == 470.0


def test_select_put_no_qualifying_delta():
    """All puts have delta above -0.21 → None."""
    chain = [
        {"option_type": "put", "strike": 490.0, "delta": -0.15},
        {"option_type": "put", "strike": 485.0, "delta": -0.10},
    ]
    assert select_put(chain) is None


def test_select_put_empty_chain():
    assert select_put([]) is None


def test_select_put_skips_none_delta():
    """Contract with delta=None is skipped; valid contract is returned."""
    chain = [
        {"option_type": "put", "strike": 480.0, "delta": None},
        {"option_type": "put", "strike": 470.0, "delta": -0.23},
    ]
    result = select_put(chain)
    assert result is not None
    assert result["delta"] == -0.23


# ---------------------------------------------------------------------------
# select_call
# ---------------------------------------------------------------------------

_CALL_CONTRACTS = [
    {"option_type": "call", "strike": 480.0, "delta": 0.15},  # delta too low (< 0.21)
    {"option_type": "call", "strike": 490.0, "delta": 0.21},  # exactly at threshold ← best
    {"option_type": "call", "strike": 500.0, "delta": 0.25},
    {"option_type": "call", "strike": 510.0, "delta": 0.35},
    {"option_type": "put", "strike": 460.0, "delta": -0.22},  # wrong side — ignored
]


def test_select_call_picks_closest_to_threshold():
    """Returns the call with delta closest to 0.21 (lowest qualifying delta)."""
    result = select_call(_CALL_CONTRACTS)
    assert result is not None
    assert result["delta"] == 0.21
    assert result["strike"] == 490.0


def test_select_call_no_qualifying_delta():
    """All calls have delta below 0.21 → None."""
    chain = [
        {"option_type": "call", "strike": 490.0, "delta": 0.15},
        {"option_type": "call", "strike": 485.0, "delta": 0.10},
    ]
    assert select_call(chain) is None
