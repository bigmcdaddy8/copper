"""Context-labeled exact VWAPs over retained canonical or effective trades."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from dicks_laboratory.effective_tape import EffectiveTrade
from dicks_laboratory.models import InstrumentIdentity, TradeObservation
from dicks_laboratory.sessions import SessionCoverageWindow, VwapAnchor


class VwapSourceMode(StrEnum):
    CANONICAL_NEW_ONLY = "CANONICAL_NEW_ONLY"
    EFFECTIVE_TAPE = "EFFECTIVE_TAPE"


@dataclass(frozen=True)
class AnchoredVwapResult:
    instrument: InstrumentIdentity
    trading_date: str | None
    anchor: VwapAnchor
    source_mode: VwapSourceMode
    first_included_trade_timestamp: datetime
    last_included_trade_timestamp: datetime
    included_trade_count: int
    included_volume: Decimal
    vwap: Decimal
    coverage: SessionCoverageWindow | None


def calculate_anchored_vwap(
    trades: tuple[TradeObservation | EffectiveTrade, ...],
    anchor: VwapAnchor,
    source_mode: VwapSourceMode,
    trading_date: str | None = None,
    coverage: SessionCoverageWindow | None = None,
) -> AnchoredVwapResult:
    """Calculate exact VWAP from retained trades at or after the explicit anchor."""
    selected = tuple(trade for trade in trades if trade.event_timestamp >= anchor.anchor_timestamp_utc)
    if not selected:
        raise ValueError("No retained trades are available at or after the requested anchor.")
    volume = sum((trade.size for trade in selected), Decimal("0"))
    price_volume = sum((trade.price * trade.size for trade in selected), Decimal("0"))
    return AnchoredVwapResult(
        instrument=selected[0].instrument,
        trading_date=trading_date,
        anchor=anchor,
        source_mode=source_mode,
        first_included_trade_timestamp=selected[0].event_timestamp,
        last_included_trade_timestamp=selected[-1].event_timestamp,
        included_trade_count=len(selected),
        included_volume=volume,
        vwap=price_volume / volume,
        coverage=coverage,
    )