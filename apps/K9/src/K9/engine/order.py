"""Order placement, fill-polling loop, and take-profit placement (K9-0060/K9-0070)."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from bic.broker import Broker
from bic.models import Order, OrderRequest, OrderResponse


@dataclass
class OrderOutcome:
    status: str           # "FILLED" | "CANCELED" | "REJECTED"
    order_id: str
    filled_price: float | None
    reason: str = ""


@dataclass
class TpOutcome:
    status: str     # "PLACED" | "FAILED"
    order_id: str = ""
    tp_price: float | None = None
    reason: str = ""


def place_and_poll(
    broker: Broker,
    order: OrderRequest,
    max_fill_seconds: int,
    poll_interval: float = 5.0,
    tick: Callable[[], None] | None = None,
) -> OrderOutcome:
    """Submit *order* and poll until filled, canceled, or timeout.

    Args:
        broker: BIC Broker instance.
        order: The OrderRequest to submit.
        max_fill_seconds: Maximum seconds (or ticks when tick is set) before canceling.
        poll_interval: Seconds between polls (ignored when tick is set).
        tick: Optional callback invoked between each poll. Use with simulation brokers
              that require explicit time advancement (e.g. HolodeckBroker.advance_time).
              When set, max_fill_seconds is treated as a tick count, not wall-clock seconds.

    Returns:
        OrderOutcome describing the final state.
    """
    response: OrderResponse = broker.place_order(order)

    if response.status != "ACCEPTED":
        return OrderOutcome(
            status="REJECTED",
            order_id=response.order_id,
            filled_price=None,
            reason="Order was rejected by broker.",
        )

    order_id = response.order_id

    if tick is not None:
        # Simulation path: advance virtual time between polls
        for _ in range(max_fill_seconds):
            tick()
            current: Order = broker.get_order(order_id)
            if current.status == "FILLED":
                return OrderOutcome(
                    status="FILLED",
                    order_id=order_id,
                    filled_price=current.filled_price,
                )
            if current.status == "CANCELED":
                return OrderOutcome(
                    status="CANCELED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order was canceled externally.",
                )
    else:
        # Real-time path: sleep between polls
        deadline = time.monotonic() + max_fill_seconds
        while time.monotonic() < deadline:
            current = broker.get_order(order_id)
            if current.status == "FILLED":
                return OrderOutcome(
                    status="FILLED",
                    order_id=order_id,
                    filled_price=current.filled_price,
                )
            if current.status == "CANCELED":
                return OrderOutcome(
                    status="CANCELED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order was canceled externally.",
                )
            time.sleep(poll_interval)

    # Timeout — cancel the order
    broker.cancel_order(order_id)
    return OrderOutcome(
        status="CANCELED",
        order_id=order_id,
        filled_price=None,
        reason=f"Order not filled within {max_fill_seconds}s. Canceled.",
    )


def place_tp_order(broker: Broker, tp_order: OrderRequest) -> TpOutcome:
    """Submit the take-profit GTC order. Does not poll — fire and forget.

    Args:
        broker: BIC Broker instance.
        tp_order: The buy-to-close OrderRequest.

    Returns:
        TpOutcome with status "PLACED" or "FAILED".
    """
    try:
        response = broker.place_order(tp_order)
        if response.status == "ACCEPTED":
            return TpOutcome(
                status="PLACED",
                order_id=response.order_id,
                tp_price=tp_order.limit_price,
            )
        return TpOutcome(
            status="FAILED",
            reason=f"Broker rejected TP order: {response.status}",
        )
    except Exception as exc:  # noqa: BLE001
        return TpOutcome(status="FAILED", reason=str(exc))
