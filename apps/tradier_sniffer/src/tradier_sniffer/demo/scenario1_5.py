"""Scenario 1.5 — SIC Reprice and Re-enter.

Places a SIC entry order, waits, and if still unfilled cancels and re-enters
at a reduced credit (one tick lower).  Returns immediately after re-entry.

Usage:
    tradier_sniffer demo scenario1_5 [--wait SECONDS] [--tick FLOAT]
"""

from __future__ import annotations

import time

from tradier_sniffer.demo import scenario1
from tradier_sniffer.tradier_client import TradierClient

_CREDIT_FLOOR = 0.05  # never place an order below this credit


def run(
    client: TradierClient,
    account_id: str,
    wait_seconds: int = 30,
    tick_reduction: float = 0.05,
) -> dict:
    """Place SIC, wait, reprice if unfilled.

    Returns a summary dict with keys:
        repriced        — True if cancel + re-entry occurred
        order_id        — the active order ID after this call
        credit          — credit of the active order
        (on reprice also: original_order_id, original_credit, new_credit)
    """
    entry = scenario1.run(client, account_id)
    original_order_id = entry["order_id"]
    original_credit = entry["credit"]

    time.sleep(wait_seconds)

    # Check current order status
    orders = client.get_orders(account_id)
    current = next((o for o in orders if str(o.get("id")) == str(original_order_id)), None)

    if current is None or current.get("status") in ("filled", "partially_filled"):
        # Already filled — nothing to do
        return {
            "repriced": False,
            "order_id": original_order_id,
            "credit": original_credit,
            **entry,
        }

    # Still open — cancel and re-enter at a lower credit
    client.cancel_order(account_id, original_order_id)

    new_credit = max(_CREDIT_FLOOR, round(original_credit - tick_reduction, 2))

    # Rebuild the same legs but at the new credit
    leg_list = [
        {"option_symbol": entry["legs"]["short_put"]["symbol"],  "side": "sell_to_open", "quantity": 1},
        {"option_symbol": entry["legs"]["long_put"]["symbol"],   "side": "buy_to_open",  "quantity": 1},
        {"option_symbol": entry["legs"]["short_call"]["symbol"], "side": "sell_to_open", "quantity": 1},
        {"option_symbol": entry["legs"]["long_call"]["symbol"],  "side": "buy_to_open",  "quantity": 1},
    ]
    response = client.place_multileg_order(account_id, leg_list, new_credit, underlying="SPX")
    new_order_id = str(response.get("order", {}).get("id", "unknown"))

    return {
        "repriced": True,
        "order_id": new_order_id,
        "credit": new_credit,
        "original_order_id": original_order_id,
        "original_credit": original_credit,
        "new_credit": new_credit,
        "expiry": entry["expiry"],
        "legs": entry["legs"],
    }
