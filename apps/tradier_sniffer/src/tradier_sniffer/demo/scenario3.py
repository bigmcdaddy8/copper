"""Scenario 3 — SIC Entry + GTC Take Profit.

Places a SIC entry order (Day Limit credit) followed by a GTC BTC order at
the TP price (default 50% of entry credit).  Both orders are placed and the
command exits immediately.

The user should then stop the poll loop (Ctrl-C), wait for the TP to trigger
in the sandbox, and restart the poll loop.  reconcile() on startup will detect
the TP fill and close the trade.

Usage:
    tradier_sniffer demo scenario3 [--tp-pct FLOAT]
"""

from __future__ import annotations

from tradier_sniffer.demo import scenario1
from tradier_sniffer.tradier_client import TradierClient


def run(
    client: TradierClient,
    account_id: str,
    tp_pct: float = 0.50,
) -> dict:
    """Place SIC entry + GTC TP order.

    tp_pct — Take-profit as a fraction of the entry credit (default 0.50 = 50%).

    Returns a summary dict with entry_order_id, tp_order_id, tp_price, expiry, legs.
    """
    # --- Place the entry ---
    entry = scenario1.run(client, account_id)
    entry_order_id = entry["order_id"]
    entry_credit = entry["credit"]

    # --- Calculate the TP price ---
    tp_price = round(entry_credit * tp_pct, 2)

    # --- Place the GTC BTC multileg TP order (buy back all 4 legs) ---
    tp_legs = [
        {"option_symbol": entry["legs"]["short_put"]["symbol"],  "side": "buy_to_close",  "quantity": 1},
        {"option_symbol": entry["legs"]["long_put"]["symbol"],   "side": "sell_to_close", "quantity": 1},
        {"option_symbol": entry["legs"]["short_call"]["symbol"], "side": "buy_to_close",  "quantity": 1},
        {"option_symbol": entry["legs"]["long_call"]["symbol"],  "side": "sell_to_close", "quantity": 1},
    ]
    tp_response = client.place_multileg_order(account_id, tp_legs, tp_price, duration="gtc")
    tp_order_id = str(tp_response.get("order", {}).get("id", "unknown"))

    return {
        "entry_order_id": entry_order_id,
        "tp_order_id": tp_order_id,
        "entry_credit": entry_credit,
        "tp_price": tp_price,
        "expiry": entry["expiry"],
        "legs": entry["legs"],
    }
