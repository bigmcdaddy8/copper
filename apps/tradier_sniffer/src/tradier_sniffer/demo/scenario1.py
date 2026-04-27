"""Scenario 1 — SPX 0DTE SIC Entry.

Places a 4-leg Short Iron Condor entry order (Day Limit credit) on the nearest
0DTE SPX expiration at approximately the 20-delta short strikes with $10 wings.
Returns immediately — the normal ``poll`` loop detects the fill.

Usage:
    tradier_sniffer demo scenario1
"""

from __future__ import annotations

from tradier_sniffer.options import (
    build_sic_legs,
    calc_sic_credit,
    get_0dte_expiration,
)
from tradier_sniffer.tradier_client import TradierClient

UNDERLYING = "SPX"
TARGET_DELTA = 0.20
WING_WIDTH = 10.0


def run(client: TradierClient, account_id: str) -> dict:
    """Place the SPX 0DTE SIC entry order.

    Returns a summary dict with order_id, credit, expiry, and leg strikes.
    Raises RuntimeError with a human-readable message if prerequisites fail
    (no expiration found, greeks unavailable).
    """
    # --- Step 1: find the 0DTE expiration ---
    expirations = client.get_option_expirations(UNDERLYING)
    expiry = get_0dte_expiration(expirations)
    if expiry is None:
        raise RuntimeError(
            "No option expiration found for SPX. "
            "Ensure the market is open and the Tradier sandbox is reachable."
        )

    # --- Step 2: fetch the chain with greeks ---
    chain = client.get_option_chain(UNDERLYING, expiry, greeks=True)
    if not chain:
        raise RuntimeError(f"Empty option chain returned for SPX {expiry}.")

    # --- Step 3: build SIC legs ---
    legs = build_sic_legs(chain, target_delta=TARGET_DELTA, wing_width=WING_WIDTH)
    if legs is None:
        raise RuntimeError(
            "Could not build SIC legs — greeks may be unavailable outside market hours, "
            "or the wing strikes are not listed in the chain. "
            "Run scenario1 during regular trading hours (9:30 AM – 4:00 PM ET)."
        )

    # --- Step 4: calculate the credit ---
    credit = calc_sic_credit(legs)

    # --- Step 5: build the Tradier leg list and place the order ---
    leg_list = [
        {"option_symbol": legs["short_put"]["symbol"],  "side": "sell_to_open",  "quantity": 1},
        {"option_symbol": legs["long_put"]["symbol"],   "side": "buy_to_open",   "quantity": 1},
        {"option_symbol": legs["short_call"]["symbol"], "side": "sell_to_open",  "quantity": 1},
        {"option_symbol": legs["long_call"]["symbol"],  "side": "buy_to_open",   "quantity": 1},
    ]

    response = client.place_multileg_order(account_id, leg_list, credit, underlying=UNDERLYING)
    order_id = str(response.get("order", {}).get("id", "unknown"))

    return {
        "order_id": order_id,
        "credit": credit,
        "expiry": expiry,
        "legs": {
            "short_put":  {"symbol": legs["short_put"]["symbol"],  "strike": legs["short_put"]["strike"]},
            "long_put":   {"symbol": legs["long_put"]["symbol"],   "strike": legs["long_put"]["strike"]},
            "short_call": {"symbol": legs["short_call"]["symbol"], "strike": legs["short_call"]["strike"]},
            "long_call":  {"symbol": legs["long_call"]["symbol"],  "strike": legs["long_call"]["strike"]},
        },
    }
