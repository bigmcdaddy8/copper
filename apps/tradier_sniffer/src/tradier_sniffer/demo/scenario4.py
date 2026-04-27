"""Scenario 4 — SIC Entry + Put Spread Adjustment.

Places a SIC entry order, polls briefly until it fills (up to max_wait_seconds),
then places a 2-leg adjustment: rolls the short put spread down 10 points.
The adjustment order is linked to the same Trade # as the entry.

This exercises the FAQ question: can an adjustment (BTC + STO) be placed as
a single multileg Day Limit order?

Usage:
    tradier_sniffer demo scenario4
"""

from __future__ import annotations

import sqlite3
import time

from tradier_sniffer.assign import assign_trade
from tradier_sniffer.demo import scenario1
from tradier_sniffer.engine import _raw_to_order
from tradier_sniffer.options import build_occ_symbol
from tradier_sniffer.tradier_client import TradierClient

_POLL_INTERVAL = 5   # seconds between fill checks
_WING_WIDTH = 10.0   # points — matches scenario1


def run(
    client: TradierClient,
    conn: sqlite3.Connection,
    account_id: str,
    max_wait_seconds: int = 60,
) -> dict:
    """Place SIC entry, wait for fill, then place adjustment.

    Returns a summary dict. If no fill is detected within max_wait_seconds,
    returns {"status": "entry_unfilled", "order_id": ..., "message": ...}.
    """
    # --- Place entry ---
    entry = scenario1.run(client, account_id)
    entry_order_id = entry["order_id"]

    # --- Poll briefly until filled ---
    filled_order = None
    elapsed = 0
    while elapsed < max_wait_seconds:
        time.sleep(_POLL_INTERVAL)
        elapsed += _POLL_INTERVAL
        orders = client.get_orders(account_id)
        current = next((o for o in orders if str(o.get("id")) == str(entry_order_id)), None)
        if current and current.get("status") in ("filled", "partially_filled"):
            filled_order = _raw_to_order(current, account_id)
            break

    if filled_order is None:
        return {
            "status": "entry_unfilled",
            "order_id": entry_order_id,
            "message": (
                f"Entry order not filled within {max_wait_seconds}s. "
                "Wait for a fill and then re-run scenario4, or use the poll loop."
            ),
        }

    # --- Find the Trade # for the filled entry ---
    from tradier_sniffer.db import upsert_order
    upsert_order(conn, filled_order)
    trade = assign_trade(conn, filled_order)  # idempotent — reuses existing if present

    # --- Build the adjustment: roll short put spread down 10 points ---
    short_put_sym = entry["legs"]["short_put"]["symbol"]
    long_put_sym  = entry["legs"]["long_put"]["symbol"]
    short_put_strike = float(entry["legs"]["short_put"]["strike"])
    long_put_strike  = float(entry["legs"]["long_put"]["strike"])
    expiry = entry["expiry"]

    new_short_put_sym = build_occ_symbol("SPX", expiry, "P", short_put_strike - _WING_WIDTH)
    new_long_put_sym  = build_occ_symbol("SPX", expiry, "P", long_put_strike  - _WING_WIDTH)

    # Get bid/ask for the adjustment legs from the current chain
    chain = client.get_option_chain("SPX", expiry, greeks=False)
    adj_credit = _calc_adj_credit(chain, short_put_sym, long_put_sym, new_short_put_sym, new_long_put_sym)

    adj_legs = [
        {"option_symbol": short_put_sym,     "side": "buy_to_close",  "quantity": 1},
        {"option_symbol": new_short_put_sym,  "side": "sell_to_open",  "quantity": 1},
    ]
    adj_response = client.place_multileg_order(account_id, adj_legs, adj_credit, underlying="SPX")
    adj_order_id = str(adj_response.get("order", {}).get("id", "unknown"))

    # Link adjustment order to the same Trade # (will be mapped on fill detection)
    # We record the pending adjustment order in the DB so it can be linked when filled
    from tradier_sniffer.models import Order, OrderStatus
    adj_order_stub = Order(
        order_id=adj_order_id,
        account_id=account_id,
        symbol="SPX",
        class_="multileg",
        order_type="limit",
        side="",
        quantity=1,
        status=OrderStatus.open,
        duration="day",
        limit_price=adj_credit,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )
    upsert_order(conn, adj_order_stub)
    # Explicitly link to the same Trade # as the entry (bypass proximity logic)
    from tradier_sniffer.db import insert_trade_order_map
    from tradier_sniffer.models import TradeOrderMap
    insert_trade_order_map(
        conn,
        TradeOrderMap(trade.trade_id, adj_order_id, "adjustment", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )

    return {
        "status": "adjustment_placed",
        "trade_id": trade.trade_id,
        "entry_order_id": entry_order_id,
        "adjustment_order_id": adj_order_id,
        "adjustment_credit": adj_credit,
    }


def _calc_adj_credit(
    chain: list[dict],
    btc_short: str,
    btc_long: str,
    sto_short: str,
    sto_long: str,
) -> float:
    """Calculate net credit for the roll adjustment.

    Credit = STO_short.bid - BTC_short.ask
    (We only roll the short leg in scenario4 for simplicity.)
    """
    def _find(sym: str) -> dict:
        return next((o for o in chain if o.get("symbol") == sym), {})

    sto = _find(sto_short)
    btc = _find(btc_short)
    credit = float(sto.get("bid", 0)) - float(btc.get("ask", 0))
    return round(credit, 2)
