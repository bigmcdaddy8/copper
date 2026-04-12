"""Startup reconciliation for tradier_sniffer.

On startup, compares the local DB state against fresh broker data and replays
any order events that occurred while the program was offline.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from tradier_sniffer.assign import assign_trade
from tradier_sniffer.db import append_event, get_order, set_poll_state, upsert_order
from tradier_sniffer.engine import _raw_to_order, detect_events
from tradier_sniffer.models import EventLog, EventType
from tradier_sniffer.tradier_client import TradierClient


@dataclass
class ReconcileResult:
    checked: int   # total orders fetched from broker
    replayed: int  # events emitted for missed state transitions
    summary: str   # human-readable one-liner


def reconcile(
    conn: sqlite3.Connection,
    client: TradierClient,
    account_id: str,
) -> ReconcileResult:
    """Detect and replay missed order events since the last poll.

    Fetches all current orders from the broker, diffs against local DB state,
    and emits EventLog entries (marked ``"reconciled": true``) for any
    transitions that were missed while offline.

    Returns a :class:`ReconcileResult` summarising what was found.
    """
    raw_orders = client.get_orders(account_id)
    fresh = [_raw_to_order(r, account_id) for r in raw_orders]

    replayed = 0
    for order, event_type in detect_events(fresh, lambda oid: get_order(conn, oid)):
        details = json.dumps({
            "order_id": order.order_id,
            "status": order.status.value,
            "reconciled": True,
        })
        evt = EventLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            order_id=order.order_id,
            details=details,
        )
        event_id = append_event(conn, evt)
        evt.event_id = event_id

        upsert_order(conn, order)

        if event_type == EventType.filled:
            assign_trade(conn, order)

        replayed += 1

    # Upsert all fresh orders (refreshes status / fill fields even if no event)
    for order in fresh:
        upsert_order(conn, order)

    set_poll_state(conn, "last_poll_at", datetime.now(timezone.utc).isoformat())

    summary = f"checked {len(fresh)} order(s), replayed {replayed} missed event(s)"
    return ReconcileResult(checked=len(fresh), replayed=replayed, summary=summary)
