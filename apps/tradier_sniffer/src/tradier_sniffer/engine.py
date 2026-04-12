"""Core polling engine for tradier_sniffer.

Responsibilities:
- Convert raw Tradier order dicts to Order dataclasses (_raw_to_order)
- Diff fresh broker state against local DB state (detect_events — pure, no I/O)
- Execute one poll cycle: fetch → diff → persist → update poll state (poll)
- Run the blocking poll loop with Rich status output (run_poll_loop)
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone

from rich.console import Console

from tradier_sniffer.assign import assign_trade
from tradier_sniffer.db import (
    append_event,
    get_order,
    set_poll_state,
    upsert_order,
)
from tradier_sniffer.models import (
    EventLog,
    EventType,
    Order,
    OrderLeg,
    OrderStatus,
)
from tradier_sniffer.tradier_client import TradierClient

console = Console()

# Statuses that map to EventType.filled
_FILL_STATUSES = {OrderStatus.filled, OrderStatus.partially_filled}

# Statuses that map to EventType.canceled
_CANCEL_STATUSES = {
    OrderStatus.canceled,
    OrderStatus.rejected,
    OrderStatus.expired,
    OrderStatus.partially_filled_canceled,
}


# ---------------------------------------------------------------------------
# Raw → dataclass conversion
# ---------------------------------------------------------------------------


def _raw_to_order(raw: dict, account_id: str) -> Order:
    """Convert a Tradier order dict to an Order dataclass.

    Handles missing / null fields defensively — unknown status values fall
    back to OrderStatus.pending.
    """
    # Tradier leg normalisation: may be absent, a single dict, or a list
    raw_legs = raw.get("leg") or []
    if isinstance(raw_legs, dict):
        raw_legs = [raw_legs]

    legs = [
        OrderLeg(
            option_symbol=str(leg.get("option_symbol") or ""),
            side=str(leg.get("side") or ""),
            quantity=int(leg.get("quantity") or 0),
            fill_price=float(leg["fill_price"]) if leg.get("fill_price") is not None else None,
            fill_quantity=int(leg["exec_quantity"]) if leg.get("exec_quantity") is not None else None,
        )
        for leg in raw_legs
    ]

    raw_status = str(raw.get("status") or "pending")
    try:
        status = OrderStatus(raw_status)
    except ValueError:
        status = OrderStatus.pending

    raw_fill_qty = raw.get("exec_quantity")
    raw_fill_price = raw.get("avg_fill_price")

    return Order(
        order_id=str(raw.get("id") or raw.get("order_id") or ""),
        account_id=account_id,
        symbol=str(raw.get("symbol") or ""),
        class_=str(raw.get("class") or ""),
        order_type=str(raw.get("type") or ""),
        side=str(raw.get("side") or ""),
        quantity=int(raw.get("quantity") or 0),
        status=status,
        duration=str(raw.get("duration") or ""),
        limit_price=float(raw["price"]) if raw.get("price") is not None else None,
        fill_price=float(raw_fill_price) if raw_fill_price is not None else None,
        fill_quantity=int(raw_fill_qty) if raw_fill_qty is not None else None,
        option_symbol=raw.get("option_symbol"),
        legs=legs,
        tag=raw.get("tag"),
        created_at=str(raw.get("create_date") or ""),
        updated_at=raw.get("transaction_date"),
    )


# ---------------------------------------------------------------------------
# Pure event detection
# ---------------------------------------------------------------------------


def detect_events(
    fresh: list[Order],
    get_known: Callable[[str], Order | None],
) -> list[tuple[Order, EventType]]:
    """Diff fresh orders against known DB state; return events to emit.

    Pure function — no I/O, no DB calls.  ``get_known`` is a callable that
    accepts an order_id string and returns the last known Order (or None).
    """
    events: list[tuple[Order, EventType]] = []
    for order in fresh:
        known = get_known(order.order_id)
        if known is None:
            events.append((order, EventType.new_order))
        elif order.status != known.status:
            if order.status in _FILL_STATUSES:
                events.append((order, EventType.filled))
            elif order.status in _CANCEL_STATUSES:
                events.append((order, EventType.canceled))
    return events


# ---------------------------------------------------------------------------
# Single poll cycle
# ---------------------------------------------------------------------------


def poll(
    conn: sqlite3.Connection,
    client: TradierClient,
    account_id: str,
) -> list[EventLog]:
    """Execute one poll cycle.

    1. Fetch orders from broker
    2. Convert to Order dataclasses
    3. Detect events vs DB state
    4. Persist events + upsert orders
    5. Update last_poll_at

    Returns the list of EventLog entries appended during this cycle.
    """
    import json

    raw_orders = client.get_orders(account_id)
    fresh = [_raw_to_order(r, account_id) for r in raw_orders]

    emitted: list[EventLog] = []
    for order, event_type in detect_events(fresh, lambda oid: get_order(conn, oid)):
        details = json.dumps({"order_id": order.order_id, "status": order.status.value})
        evt = EventLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            order_id=order.order_id,
            details=details,
        )
        event_id = append_event(conn, evt)
        evt.event_id = event_id
        emitted.append(evt)

        # Assign a Trade # for every filled event
        if event_type == EventType.filled:
            assign_trade(conn, order)

    for order in fresh:
        upsert_order(conn, order)

    set_poll_state(conn, "last_poll_at", datetime.now(timezone.utc).isoformat())

    return emitted


# ---------------------------------------------------------------------------
# Blocking poll loop
# ---------------------------------------------------------------------------


def run_poll_loop(
    conn: sqlite3.Connection,
    client: TradierClient,
    account_id: str,
    interval: int,
) -> None:
    """Run poll() in a loop, sleeping ``interval`` seconds between cycles.

    Prints a one-line Rich status after each cycle.
    Exits cleanly on KeyboardInterrupt.
    """
    console.print(f"[bold green]Polling started[/bold green] (interval={interval}s, Ctrl-C to stop)")
    try:
        while True:
            try:
                events = poll(conn, client, account_id)
                ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
                console.print(
                    f"[dim]{ts}[/dim]  polled — [cyan]{len(events)}[/cyan] event(s) detected"
                )
            except Exception as exc:  # noqa: BLE001
                console.print(f"[red]Poll error:[/red] {exc}")
            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[bold]Polling stopped.[/bold]")
