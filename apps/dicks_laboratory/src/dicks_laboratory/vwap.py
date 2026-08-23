"""Pure deterministic VWAP arithmetic over already-selected trade observations."""
from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from dicks_laboratory.models import TradeObservation


def calculate_vwap(trades: Iterable[TradeObservation]) -> Decimal:
    """Return exact trade-based VWAP for a non-empty sequence of valid trades."""
    total_price_volume = Decimal("0")
    total_volume = Decimal("0")

    for trade in trades:
        total_price_volume += trade.price * trade.size
        total_volume += trade.size

    if total_volume == Decimal("0"):
        raise ValueError("VWAP requires at least one trade.")
    return total_price_volume / total_volume