"""Scenario 2 — Multi-leg Trade Grouping Verification.

Read-only command.  Queries the DB for all Trade records and shows each trade
with its associated orders to confirm that multi-leg SIC orders are grouped
under a single Trade #.

Usage:
    tradier_sniffer demo scenario2
"""

from __future__ import annotations

import sqlite3

from tradier_sniffer.db import get_open_trades, get_orders_for_trade


def run(conn: sqlite3.Connection) -> list[dict]:
    """Return a list of trade summaries from the local DB.

    Each summary dict:
        trade_id    — e.g. TRDS_00001_SIC
        status      — open / closed
        underlying  — e.g. SPX
        order_count — number of orders linked to this trade
        order_ids   — list of order ID strings
    """
    trades = get_open_trades(conn)
    summaries = []
    for trade in trades:
        orders = get_orders_for_trade(conn, trade.trade_id)
        summaries.append({
            "trade_id": trade.trade_id,
            "status": trade.status.value,
            "underlying": trade.underlying,
            "order_count": len(orders),
            "order_ids": [o.order_id for o in orders],
        })
    return summaries
