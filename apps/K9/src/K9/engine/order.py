"""Order placement, fill-polling loop, and take-profit placement (K9-0060/K9-0070)."""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from bic.broker import Broker
from bic.models import (
    Order,
    OrderRequest,
    OrderResponse,
    ORDER_FILL_STATUSES,
    ORDER_DONE_STATUSES,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_EXPIRED,
)


@dataclass
class OrderOutcome:
    status: str           # "FILLED" | "CANCELED" | "REJECTED" | "EXPIRED"
    order_id: str
    filled_price: float | None
    reason: str = ""
    rejection_reason: str | None = None   # normalized BIC rejection code when status=="REJECTED"
    timed_out: bool = False
    attempts_used: int = 1


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
            rejection_reason=getattr(response, "rejection_reason", None),
            timed_out=False,
            attempts_used=1,
        )

    order_id = response.order_id

    if tick is not None:
        # Simulation path: advance virtual time between polls
        for _ in range(max_fill_seconds):
            tick()
            current: Order = broker.get_order(order_id)
            if current.status in ORDER_FILL_STATUSES:
                return OrderOutcome(
                    status="FILLED",
                    order_id=order_id,
                    filled_price=current.filled_price,
                    timed_out=False,
                    attempts_used=1,
                )
            if current.status == ORDER_STATUS_REJECTED:
                return OrderOutcome(
                    status="REJECTED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order rejected during fill window.",
                    timed_out=False,
                    attempts_used=1,
                )
            if current.status == ORDER_STATUS_EXPIRED:
                return OrderOutcome(
                    status="EXPIRED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order expired during fill window.",
                    timed_out=False,
                    attempts_used=1,
                )
            if current.status in ORDER_DONE_STATUSES:
                return OrderOutcome(
                    status="CANCELED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order was canceled externally.",
                    timed_out=False,
                    attempts_used=1,
                )
            # ORDER_ACTIVE_STATUSES (OPEN, PENDING, PENDING_CANCEL) — continue polling
    else:
        # Real-time path: sleep between polls
        deadline = time.monotonic() + max_fill_seconds
        while time.monotonic() < deadline:
            current = broker.get_order(order_id)
            if current.status in ORDER_FILL_STATUSES:
                return OrderOutcome(
                    status="FILLED",
                    order_id=order_id,
                    filled_price=current.filled_price,
                    timed_out=False,
                    attempts_used=1,
                )
            if current.status == ORDER_STATUS_REJECTED:
                return OrderOutcome(
                    status="REJECTED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order rejected during fill window.",
                    timed_out=False,
                    attempts_used=1,
                )
            if current.status == ORDER_STATUS_EXPIRED:
                return OrderOutcome(
                    status="EXPIRED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order expired during fill window.",
                    timed_out=False,
                    attempts_used=1,
                )
            if current.status in ORDER_DONE_STATUSES:
                return OrderOutcome(
                    status="CANCELED",
                    order_id=order_id,
                    filled_price=None,
                    reason="Order was canceled externally.",
                    timed_out=False,
                    attempts_used=1,
                )
            # ORDER_ACTIVE_STATUSES — continue polling
            time.sleep(poll_interval)

    # Timeout — cancel the order
    broker.cancel_order(order_id)
    return OrderOutcome(
        status="CANCELED",
        order_id=order_id,
        filled_price=None,
        reason=f"Order not filled within {max_fill_seconds}s. Canceled.",
        timed_out=True,
        attempts_used=1,
    )


def place_with_retries(
    broker: Broker,
    order: OrderRequest,
    *,
    max_fill_seconds: int,
    max_entry_attempts: int,
    retry_price_decrement: float,
    min_credit_received: float,
    poll_interval: float = 5.0,
    tick: Callable[[], None] | None = None,
) -> OrderOutcome:
    """Submit entry order with cancel-replace retry logic.

    Attempt 1 uses order.limit_price (midpoint from constructor).
    Each retry decrements limit credit by retry_price_decrement until floor.
    """
    current_limit = float(order.limit_price)
    last_outcome: OrderOutcome | None = None

    for attempt in range(1, max(1, max_entry_attempts) + 1):
        attempt_order = OrderRequest(
            symbol=order.symbol,
            strategy_type=order.strategy_type,
            legs=order.legs,
            quantity=order.quantity,
            order_type=order.order_type,
            limit_price=round(current_limit, 2),
            duration=order.duration,
            tag=order.tag,
        )

        outcome = place_and_poll(
            broker,
            attempt_order,
            max_fill_seconds=max_fill_seconds,
            poll_interval=poll_interval,
            tick=tick,
        )
        outcome.attempts_used = attempt
        last_outcome = outcome

        if outcome.status in {"FILLED", "REJECTED", "EXPIRED"}:
            return outcome

        if outcome.status == "CANCELED" and not outcome.timed_out:
            return outcome

        if attempt >= max_entry_attempts:
            outcome.reason = (
                f"{outcome.reason} Attempts exhausted: {max_entry_attempts}/{max_entry_attempts}."
            )
            return outcome

        next_limit = round(current_limit - retry_price_decrement, 2)
        if next_limit < min_credit_received:
            outcome.reason = (
                f"Stopped retries: next entry credit {next_limit:.2f} would be below "
                f"min_credit_received {min_credit_received:.2f}."
            )
            return outcome
        current_limit = next_limit

    return last_outcome or OrderOutcome(
        status="CANCELED",
        order_id="",
        filled_price=None,
        reason="No entry attempts executed.",
        timed_out=False,
        attempts_used=0,
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
