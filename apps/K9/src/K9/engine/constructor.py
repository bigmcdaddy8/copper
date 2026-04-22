"""Trade constructor — builds BIC OrderRequest from selected strikes (K9-0050/K9-0070)."""
from __future__ import annotations

from datetime import date

from bic.models import OptionContract, OrderLeg, OrderRequest
from K9.config import TradeSpec


def build_order(
    spec: TradeSpec,
    expiration: date,
    short_put: OptionContract,
    long_put: OptionContract,
    short_call: OptionContract | None,
    long_call: OptionContract | None,
) -> OrderRequest:
    """Build a multi-leg entry OrderRequest from selected strikes.

    - IRON_CONDOR:        sell short put, buy long put, sell short call, buy long call
    - PUT_CREDIT_SPREAD:  sell short put, buy long put
    - CALL_CREDIT_SPREAD: sell short call, buy long call

    limit_price is the mid of the full combo (positive = credit received).
    """
    legs: list[OrderLeg] = []
    combo_bid = 0.0
    combo_ask = 0.0

    trade_type = spec.trade_type

    if trade_type in ("IRON_CONDOR", "PUT_CREDIT_SPREAD"):
        legs.append(OrderLeg("SELL", "PUT", short_put.strike, expiration))
        legs.append(OrderLeg("BUY",  "PUT", long_put.strike,  expiration))
        combo_bid += short_put.bid - long_put.ask
        combo_ask += short_put.ask - long_put.bid

    if trade_type in ("IRON_CONDOR", "CALL_CREDIT_SPREAD"):
        assert short_call is not None and long_call is not None
        legs.append(OrderLeg("SELL", "CALL", short_call.strike, expiration))
        legs.append(OrderLeg("BUY",  "CALL", long_call.strike,  expiration))
        combo_bid += short_call.bid - long_call.ask
        combo_ask += short_call.ask - long_call.bid

    mid = round((combo_bid + combo_ask) / 2, 2)

    return OrderRequest(
        symbol=spec.underlying,
        strategy_type=trade_type,
        legs=legs,
        quantity=spec.position_size.contracts,
        order_type="LIMIT",
        limit_price=mid,
    )


def build_tp_order(
    spec: TradeSpec,
    entry_order: OrderRequest,
    filled_price: float,
) -> OrderRequest:
    """Build the GTC buy-to-close take-profit order.

    TP limit price = filled_price × (1 - take_profit_percent / 100),
    rounded to the nearest $0.05 tick.
    Legs are the inverse of the entry legs (SELL ↔ BUY).
    """
    tp_pct = spec.exit.take_profit_percent / 100.0
    raw_price = filled_price * (1.0 - tp_pct)
    tp_price = round(round(raw_price / 0.05) * 0.05, 2)

    reversed_legs = [
        OrderLeg(
            action="BUY" if leg.action == "SELL" else "SELL",
            option_type=leg.option_type,
            strike=leg.strike,
            expiration=leg.expiration,
        )
        for leg in entry_order.legs
    ]

    return OrderRequest(
        symbol=entry_order.symbol,
        strategy_type=entry_order.strategy_type + "_TP",
        legs=reversed_legs,
        quantity=entry_order.quantity,
        order_type="LIMIT",
        limit_price=tp_price,
    )


def net_credit(order: OrderRequest) -> float:
    """Return the net credit (positive = credit received) for *order*."""
    return order.limit_price


def combo_bid_ask_width(
    short_put: OptionContract,
    long_put: OptionContract,
    short_call: OptionContract | None,
    long_call: OptionContract | None,
) -> float:
    """Return the sum of all leg bid/ask spreads for the full combo."""
    width = (short_put.ask - short_put.bid) + (long_put.ask - long_put.bid)
    if short_call and long_call:
        width += (short_call.ask - short_call.bid) + (long_call.ask - long_call.bid)
    return round(width, 4)
