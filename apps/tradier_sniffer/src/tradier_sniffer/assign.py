"""Trade # assignment logic for tradier_sniffer.

Functions:
    build_trade_id  — pure formatter for TRDS_{seq}_{type} strings
    infer_trade_type — infer TradeType from Order structure (pure, no I/O)
    assign_trade    — find-or-create a Trade and write the TradeOrderMap link
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from tradier_sniffer.db import (
    get_open_trades,
    get_orders_for_trade,
    insert_trade,
    insert_trade_order_map,
    next_trade_sequence,
)
from tradier_sniffer.models import Order, Trade, TradeOrderMap, TradeType

# OCC symbol regex: captures the C/P flag after the 6-digit date portion
# e.g. SPX240119P04500000  →  group(1) = '240119', group(2) = 'P'
_OCC_RE = re.compile(r"[A-Z]+(\d{6})([CP])\d+$")


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def build_trade_id(seq: int, trade_type: TradeType) -> str:
    """Format a Trade # string.

    Always zero-pads to at least 5 digits; larger seq values are not truncated.

    >>> build_trade_id(1, TradeType.NPUT)
    'TRDS_00001_NPUT'
    >>> build_trade_id(100000, TradeType.SIC)
    'TRDS_100000_SIC'
    """
    return f"TRDS_{seq:05d}_{trade_type.value}"


def infer_trade_type(order: Order) -> TradeType:
    """Infer the TradeType from the Order structure.

    Pure function — no DB calls.  Callers may override by passing an
    explicit ``trade_type`` argument to ``assign_trade()``.

    Inference rules (in priority order):
    - 4 legs          → SIC
    - 2 legs, all put  → PCS
    - 2 legs, all call → CCS
    - 1 leg, sell_to_open, put  → NPUT
    - 1 leg, sell_to_open, call → NCALL
    - equity / no option_symbol → STOCK
    - fallback                  → NPUT
    """
    legs = order.legs or []
    num_legs = len(legs)

    if num_legs >= 4:
        return TradeType.SIC

    if num_legs == 2:
        flags = [_option_flag(leg.option_symbol) for leg in legs]
        if all(f == "P" for f in flags):
            return TradeType.PCS
        if all(f == "C" for f in flags):
            return TradeType.CCS
        return TradeType.SIC  # mixed / unknown — treat as condor-like

    # Single-leg
    sym = order.option_symbol or (legs[0].option_symbol if legs else "")
    if not sym:
        # No option symbol → equity
        return TradeType.STOCK

    flag = _option_flag(sym)
    if order.side in ("sell_to_open",):
        return TradeType.NPUT if flag == "P" else TradeType.NCALL
    # buy_to_open with an option symbol — covered call leg or unusual; default NPUT
    return TradeType.NPUT


def _option_flag(symbol: str) -> str:
    """Return 'C' or 'P' from an OCC symbol, or '' if not parseable."""
    m = _OCC_RE.search(symbol or "")
    return m.group(2) if m else ""


# ---------------------------------------------------------------------------
# assign_trade
# ---------------------------------------------------------------------------


def assign_trade(
    conn: sqlite3.Connection,
    order: Order,
    trade_type: TradeType | None = None,
    role: str = "entry",
    opened_at: str | None = None,
) -> Trade:
    """Find or create a Trade for ``order`` and write a TradeOrderMap entry.

    Matching strategy (in order):
    1. Tag match — if ``order.tag`` is set, find an open Trade whose trade_id
       contains the tag as a suffix component.
    2. Proximity match — find an open Trade linked to an order with the same
       ``symbol`` and a ``mapped_at`` within 5 seconds of ``order.created_at``.
    3. Create new Trade using the next sequence number.

    Returns the matched or newly-created Trade.
    """
    resolved_type = trade_type or infer_trade_type(order)
    now = datetime.now(timezone.utc).isoformat()
    effective_opened_at = opened_at or order.created_at or now

    # --- Strategy 1: tag match ---
    if order.tag:
        trade = _find_by_tag(conn, order.tag)
        if trade:
            _map(conn, trade.trade_id, order.order_id, role, now)
            return trade

    # --- Strategy 2: proximity match ---
    trade = _find_by_proximity(conn, order)
    if trade:
        _map(conn, trade.trade_id, order.order_id, role, now)
        return trade

    # --- Strategy 3: create new trade ---
    seq = next_trade_sequence(conn)
    new_trade = Trade(
        trade_id=build_trade_id(seq, resolved_type),
        trade_type=resolved_type.value,
        underlying=order.symbol,
        opened_at=effective_opened_at,
    )
    insert_trade(conn, new_trade)
    _map(conn, new_trade.trade_id, order.order_id, role, now)
    return new_trade


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _map(conn: sqlite3.Connection, trade_id: str, order_id: str, role: str, now: str) -> None:
    insert_trade_order_map(conn, TradeOrderMap(trade_id, order_id, role, now))


def _find_by_tag(conn: sqlite3.Connection, tag: str) -> Trade | None:
    """Return first open Trade whose trade_id ends with _{tag}, or None."""
    for trade in get_open_trades(conn):
        if trade.trade_id.endswith(f"_{tag}"):
            return trade
    return None


def _find_by_proximity(conn: sqlite3.Connection, order: Order, window_seconds: int = 5) -> Trade | None:
    """Return first open Trade linked to a same-symbol order within ``window_seconds``."""
    order_dt = _parse_dt(order.created_at)
    if order_dt is None:
        return None

    for trade in get_open_trades(conn):
        if trade.underlying != order.symbol:
            continue
        for existing_order in get_orders_for_trade(conn, trade.trade_id):
            existing_dt = _parse_dt(existing_order.created_at)
            if existing_dt is None:
                continue
            delta = abs((order_dt - existing_dt).total_seconds())
            if delta <= window_seconds:
                return trade
    return None


def _parse_dt(ts: str | None) -> datetime | None:
    """Parse an ISO 8601 timestamp string; return None on failure."""
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
