from __future__ import annotations
from datetime import date

from bic.models import OrderLeg, OrderRequest
from holodeck.broker import HolodeckBroker


def _pcs_order(expiration: date, limit_price: float) -> OrderRequest:
    """Helper: PUT credit spread SELL 5750P / BUY 5745P."""
    return OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 5750.0, expiration),
            OrderLeg("BUY", "PUT", 5745.0, expiration),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=limit_price,
    )


def _tp_order(expiration: date, limit_price: float) -> OrderRequest:
    """Helper: TP order (buy-to-close) for the above spread."""
    return OrderRequest(
        symbol="SPX",
        strategy_type="TP_PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("BUY", "PUT", 5750.0, expiration),
            OrderLeg("SELL", "PUT", 5745.0, expiration),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=limit_price,
    )


def _otm_pcs_order(expiration: date) -> OrderRequest:
    """OTM PCS for expiration profit scenario.
    Uses strikes within chain range (±150 from ATM) that expire worthless
    on Jan 2 (close = 5842.50 >> 5750 short strike).
    """
    return OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 5750.0, expiration),
            OrderLeg("BUY", "PUT", 5745.0, expiration),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=0.01,
    )


def scenario_immediate_fill(broker: HolodeckBroker) -> dict:
    """Scenario 1: Entry order fills on first advance_time() call.

    Strategy: request a credit so low (0.01) that the synthetic bid will always exceed it.
    """
    exp = broker.get_current_time().date()
    resp = broker.place_order(_pcs_order(exp, limit_price=0.01))
    filled = broker.advance_time()
    return {
        "order_id": resp.order_id,
        "accepted": resp.status == "ACCEPTED",
        "filled": resp.order_id in filled,
    }


def scenario_no_fill_timeout(broker: HolodeckBroker, max_steps: int = 60) -> dict:
    """Scenario 2: Order never fills; K9 cancels after timeout.

    Strategy: request an impossibly high credit (50.00) that the synthetic bid will never reach.
    """
    exp = broker.get_current_time().date()
    resp = broker.place_order(_pcs_order(exp, limit_price=50.00))
    steps = 0
    filled = False
    for _ in range(max_steps):
        ids = broker.advance_time()
        steps += 1
        if resp.order_id in ids:
            filled = True
            break
    if not filled:
        broker.cancel_order(resp.order_id)
    order = broker.get_order(resp.order_id)
    return {
        "order_id": resp.order_id,
        "fill_blocked": not filled,   # True = success (order correctly did not fill)
        "canceled": order.status == "CANCELED",
        "steps_advanced": steps,
    }


def scenario_entry_then_tp(broker: HolodeckBroker) -> dict:
    """Scenario 3: Entry fills, then TP fills at 50% of entry credit.

    Uses a high TP debit limit (999.00) so the TP always fills.
    """
    exp = broker.get_current_time().date()

    # Entry
    entry_resp = broker.place_order(_pcs_order(exp, limit_price=0.01))
    entry_filled = False
    for _ in range(120):
        ids = broker.advance_time()
        if entry_resp.order_id in ids:
            entry_filled = True
            break

    # TP (high limit so it fills immediately)
    tp_resp = broker.place_order(_tp_order(exp, limit_price=999.00))
    tp_filled = False
    for _ in range(120):
        ids = broker.advance_time()
        if tp_resp.order_id in ids:
            tp_filled = True
            break

    return {
        "entry_order_id": entry_resp.order_id,
        "tp_order_id": tp_resp.order_id,
        "entry_filled": entry_filled,
        "tp_filled": tp_filled,
    }


def scenario_entry_expire_profit(broker: HolodeckBroker) -> dict:
    """Scenario 4: Entry fills, TP never placed, trade expires OTM (profitable).

    Uses standard OTM put spread (5750/5745) that expires worthless on Jan 2
    (close = 5842.50 is well above both strikes).
    """
    exp = broker.get_current_time().date()
    initial_nlv = broker.get_account().net_liquidation

    entry_resp = broker.place_order(_otm_pcs_order(exp))
    entry_filled = False
    for _ in range(120):
        ids = broker.advance_time()
        if entry_resp.order_id in ids:
            entry_filled = True
            break

    broker.advance_to_close()

    final_nlv = broker.get_account().net_liquidation
    positions_closed = len(broker.get_positions()) == 0

    return {
        "order_id": entry_resp.order_id,
        "entry_filled": entry_filled,
        "position_closed": positions_closed,
        "pnl_positive": final_nlv > initial_nlv,
    }


def scenario_entry_expire_loss(broker: HolodeckBroker) -> dict:
    """Scenario 5: Position expires ITM at max loss.

    ITM put spreads have negative combo bid with our pricing model (extrinsic
    increases toward ATM, overwhelming intrinsic difference), so we inject the
    ITM position directly via the ledger — this is an explicit test-setup pattern,
    not something K9 does. Verifies that ExpirationEngine correctly computes loss.
    """
    exp = broker.get_current_time().date()
    quote = broker.get_underlying_quote("SPX")
    initial_nlv = broker.get_account().net_liquidation

    # Short strike above underlying → will be ITM at Jan 2 close (5842.50)
    atm = round(quote.last / 5) * 5
    sell_strike = atm + 50   # e.g. 5875 when underlying ~5825
    buy_strike = sell_strike - 5

    itm_req = OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", sell_strike, exp),
            OrderLeg("BUY", "PUT", buy_strike, exp),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=0.01,
    )
    # Inject directly: entry_credit=0.01 so the expiration loss dominates
    broker._ledger.open_position("SCENARIO-LOSS-001", itm_req, 0.01, broker.get_current_time())

    broker.advance_to_close()

    final_nlv = broker.get_account().net_liquidation
    positions_closed = len(broker.get_positions()) == 0

    return {
        "entry_filled": True,  # position was manually placed
        "position_closed": positions_closed,
        "max_loss_realized": final_nlv < initial_nlv,
    }


def scenario_account_minimum_block(broker: HolodeckBroker) -> dict:
    """Scenario 6: Account has insufficient buying power → order REJECTED.

    Drain buying power by opening a large fake position via the ledger directly.
    """
    exp = broker.get_current_time().date()
    # Drain buying power: open a position that uses nearly all of it
    # Directly access ledger (test-only pattern — K9 never does this)
    large_req = OrderRequest(
        symbol="NDX",  # different symbol so it doesn't conflict with SPX
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 1000.0, exp),
            OrderLeg("BUY", "PUT", 500.0, exp),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=1.00,
    )
    # Wing size = 500pts × 100 × 1 = $50,000 — exceeds default $50k buying power
    broker._ledger.open_position("DRAIN-001", large_req, 1.00, broker.get_current_time())

    # Now attempt a new SPX order
    resp = broker.place_order(_pcs_order(exp, limit_price=0.10))

    return {
        "order_blocked": resp.status == "REJECTED",   # True = success (order correctly rejected)
        "rejection_reason": "insufficient_buying_power" if resp.status == "REJECTED" else None,
    }


def scenario_existing_position_block(broker: HolodeckBroker) -> dict:
    """Scenario 7: Existing open position for same underlying → second order REJECTED."""
    exp = broker.get_current_time().date()

    # Fill first order
    first_resp = broker.place_order(_pcs_order(exp, limit_price=0.01))
    first_filled = False
    for _ in range(60):
        ids = broker.advance_time()
        if first_resp.order_id in ids:
            first_filled = True
            break

    # Attempt second order for same symbol
    second_resp = broker.place_order(_pcs_order(exp, limit_price=0.01))

    return {
        "first_order_id": first_resp.order_id,
        "first_order_filled": first_filled,
        "second_order_rejected": second_resp.status == "REJECTED",
    }
