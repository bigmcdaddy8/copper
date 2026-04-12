"""Pure option-chain helpers for tradier_sniffer.

All functions are stateless and take already-fetched data as arguments — no
HTTP calls, no DB calls.  Tested directly without mocking.
"""

from __future__ import annotations

from datetime import date


# ---------------------------------------------------------------------------
# OCC symbol builder
# ---------------------------------------------------------------------------


def build_occ_symbol(underlying: str, expiry: str, option_type: str, strike: float) -> str:
    """Build an OCC option symbol string.

    Args:
        underlying:  Ticker root (e.g. ``"SPX"``)
        expiry:      Expiration date as ``"YYYY-MM-DD"``
        option_type: ``"C"`` for call, ``"P"`` for put
        strike:      Strike price as a float (e.g. ``4500.0``)

    Returns:
        OCC symbol, e.g. ``"SPX240119P04500000"``
    """
    yy = expiry[2:4]
    mm = expiry[5:7]
    dd = expiry[8:10]
    strike_int = round(strike * 1000)
    return f"{underlying}{yy}{mm}{dd}{option_type}{strike_int:08d}"


# ---------------------------------------------------------------------------
# Expiration helpers
# ---------------------------------------------------------------------------


def get_0dte_expiration(expirations: list[str]) -> str | None:
    """Return the 0DTE (today) expiration if available, else the nearest future date.

    Args:
        expirations: Sorted list of ``YYYY-MM-DD`` expiration strings.

    Returns:
        The best expiration string, or ``None`` if the list is empty.
    """
    if not expirations:
        return None

    today = date.today().isoformat()

    if today in expirations:
        return today

    # Return nearest future expiration
    for exp in sorted(expirations):
        if exp > today:
            return exp

    return None


# ---------------------------------------------------------------------------
# Delta-strike selection
# ---------------------------------------------------------------------------


def find_delta_strike(
    chain: list[dict],
    target_delta: float,
    option_type: str,
) -> dict | None:
    """Find the option whose |delta| is closest to target_delta.

    Args:
        chain:        Full option chain (list of option dicts from Tradier).
        target_delta: Absolute delta value to target (e.g. ``0.20``).
        option_type:  ``"put"`` or ``"call"``.

    Returns:
        The option dict closest to the target delta, or ``None`` if no options
        with valid (non-null) greeks exist for the requested type.
    """
    candidates = [
        opt for opt in chain
        if opt.get("option_type") == option_type
        and isinstance(opt.get("greeks"), dict)
        and opt["greeks"].get("delta") is not None
    ]
    if not candidates:
        return None

    return min(candidates, key=lambda o: abs(abs(o["greeks"]["delta"]) - target_delta))


# ---------------------------------------------------------------------------
# SIC leg construction
# ---------------------------------------------------------------------------


def build_sic_legs(
    chain: list[dict],
    target_delta: float = 0.20,
    wing_width: float = 10.0,
) -> dict | None:
    """Build the four legs of a Short Iron Condor.

    Legs:
        short_put  — nearest target_delta put (STO)
        long_put   — short_put_strike − wing_width (BTO)
        short_call — nearest target_delta call (STO)
        long_call  — short_call_strike + wing_width (BTO)

    Returns:
        Dict with keys ``short_put``, ``long_put``, ``short_call``, ``long_call``
        (each an option dict from the chain), or ``None`` if any leg cannot be found
        (e.g. greeks unavailable, wing strike not in chain).
    """
    short_put = find_delta_strike(chain, target_delta, "put")
    short_call = find_delta_strike(chain, target_delta, "call")

    if short_put is None or short_call is None:
        return None

    put_short_strike = float(short_put["strike"])
    call_short_strike = float(short_call["strike"])

    long_put = _find_by_strike(chain, put_short_strike - wing_width, "put")
    long_call = _find_by_strike(chain, call_short_strike + wing_width, "call")

    if long_put is None or long_call is None:
        return None

    return {
        "short_put": short_put,
        "long_put": long_put,
        "short_call": short_call,
        "long_call": long_call,
    }


def _find_by_strike(chain: list[dict], strike: float, option_type: str) -> dict | None:
    """Find an option by exact strike and type, tolerating float imprecision."""
    for opt in chain:
        if opt.get("option_type") == option_type and abs(float(opt.get("strike", -1)) - strike) < 0.01:
            return opt
    return None


# ---------------------------------------------------------------------------
# Credit calculation
# ---------------------------------------------------------------------------


def calc_sic_credit(legs: dict) -> float:
    """Calculate the net credit for a Short Iron Condor.

    Credit = (short_put.bid + short_call.bid) − (long_put.ask + long_call.ask)

    Rounds to 2 decimal places.  May be negative if the market has moved.
    """
    credit = (
        float(legs["short_put"].get("bid", 0))
        + float(legs["short_call"].get("bid", 0))
        - float(legs["long_put"].get("ask", 0))
        - float(legs["long_call"].get("ask", 0))
    )
    return round(credit, 2)
