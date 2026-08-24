"""Exact, provider-independent Volume-at-Price aggregation and Point of Control.

Consumes already-selected canonical or effective trades; it does not reconstruct
sessions, anchors, capture coverage, or lifecycle (correction/cancel) semantics.
Selection semantics first, price normalization second, profile analytics third.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.models import InstrumentIdentity

# Point of Control is a Market Profile / Volume Profile analytical convention
# (originating outside any single exchange's product rules); CME does not
# publish a POC tie-break rule. This is an explicit Dick's Laboratory policy,
# not an exchange fact or a claimed universal vendor standard.
POC_TIE_POLICY_ID = "DICKS_LAB_POC_TIE_POLICY"
POC_TIE_POLICY_VERSION = "V1_NEAREST_VOLUME_WEIGHTED_MEAN_THEN_LOWER_PRICE"


@dataclass(frozen=True)
class PriceGrid:
    """A versioned exact tick-size definition for one instrument family."""

    instrument_family: str
    tick_size: Decimal
    policy_id: str
    policy_version: str

    def __post_init__(self) -> None:
        if self.tick_size <= Decimal("0"):
            raise ValueError("tick_size must be positive.")

    def tick_index(self, price: Decimal) -> int | None:
        """Return the exact integer tick index for a price, or None if off-grid."""
        ratio = price / self.tick_size
        rounded = ratio.to_integral_value()
        return int(rounded) if rounded * self.tick_size == price else None

    def price_at(self, tick_index: int) -> Decimal:
        return Decimal(tick_index) * self.tick_size


ES_PRICE_GRID = PriceGrid(
    instrument_family="ES",
    tick_size=Decimal("0.25"),
    policy_id="CME_ES_TICK_GRID",
    policy_version="CME_ES_TICK_GRID_V1",
)

_SUPPORTED_PRICE_GRIDS: dict[str, PriceGrid] = {ES_PRICE_GRID.instrument_family: ES_PRICE_GRID}


def price_grid_for_instrument(instrument: InstrumentIdentity) -> PriceGrid:
    """Look up the supported price grid for an instrument's root symbol."""
    grid = _SUPPORTED_PRICE_GRIDS.get(instrument.root.upper())
    if grid is None:
        raise ValueError(f"No price grid is defined for instrument root: {instrument.root!r}")
    return grid


@dataclass(frozen=True)
class InvalidTickPriceTrade:
    """A selected trade whose price does not conform to the instrument's tick grid."""

    price: Decimal
    size: Decimal
    event_timestamp: datetime
    reason: str = "PRICE_NOT_ON_TICK_GRID"


@dataclass(frozen=True)
class VolumeAtPriceLevel:
    price: Decimal
    volume: Decimal
    trade_count: int


@dataclass(frozen=True)
class VolumeAtPriceProfile:
    """Immutable Volume-at-Price aggregation over an already-selected trade set."""

    instrument: InstrumentIdentity
    source_mode: VwapSourceMode
    tick_size: Decimal
    price_grid_policy_id: str
    price_grid_policy_version: str
    selected_trade_count: int
    total_volume: Decimal
    lowest_price: Decimal
    highest_price: Decimal
    levels: tuple[VolumeAtPriceLevel, ...]  # ascending price order
    point_of_control: VolumeAtPriceLevel
    poc_policy_id: str
    poc_policy_version: str
    selected_trades_vwap: Decimal | None = None


@dataclass(frozen=True)
class VolumeAtPriceResult:
    """profile is None when no on-grid trades were available to aggregate."""

    profile: VolumeAtPriceProfile | None
    invalid_tick_trades: tuple[InvalidTickPriceTrade, ...]


def build_volume_at_price_profile(
    trades: tuple,
    grid: PriceGrid,
    source_mode: VwapSourceMode,
) -> VolumeAtPriceResult:
    """Aggregate exact Decimal volume at each valid tick-grid price level."""
    invalid: list[InvalidTickPriceTrade] = []
    on_grid: list[tuple[int, object]] = []
    for trade in trades:
        tick_index = grid.tick_index(trade.price)
        if tick_index is None:
            invalid.append(InvalidTickPriceTrade(trade.price, trade.size, trade.event_timestamp))
            continue
        on_grid.append((tick_index, trade))

    if not on_grid:
        return VolumeAtPriceResult(None, tuple(invalid))

    volumes: dict[int, Decimal] = {}
    counts: dict[int, int] = {}
    for tick_index, trade in on_grid:
        volumes[tick_index] = volumes.get(tick_index, Decimal("0")) + trade.size
        counts[tick_index] = counts.get(tick_index, 0) + 1

    levels = tuple(
        VolumeAtPriceLevel(price=grid.price_at(tick_index), volume=volumes[tick_index], trade_count=counts[tick_index])
        for tick_index in sorted(volumes)
    )
    total_volume = sum((level.volume for level in levels), Decimal("0"))
    total_price_volume = sum((trade.price * trade.size for _tick_index, trade in on_grid), Decimal("0"))
    instrument = on_grid[0][1].instrument
    profile = VolumeAtPriceProfile(
        instrument=instrument,
        source_mode=source_mode,
        tick_size=grid.tick_size,
        price_grid_policy_id=grid.policy_id,
        price_grid_policy_version=grid.policy_version,
        selected_trade_count=len(on_grid),
        total_volume=total_volume,
        lowest_price=levels[0].price,
        highest_price=levels[-1].price,
        levels=levels,
        point_of_control=_resolve_point_of_control(levels),
        poc_policy_id=POC_TIE_POLICY_ID,
        poc_policy_version=POC_TIE_POLICY_VERSION,
        selected_trades_vwap=total_price_volume / total_volume,
    )
    return VolumeAtPriceResult(profile, tuple(invalid))


def _resolve_point_of_control(levels: tuple[VolumeAtPriceLevel, ...]) -> VolumeAtPriceLevel:
    max_volume = max(level.volume for level in levels)
    candidates = tuple(level for level in levels if level.volume == max_volume)
    if len(candidates) == 1:
        return candidates[0]
    total_volume = sum((level.volume for level in levels), Decimal("0"))
    total_price_volume = sum((level.price * level.volume for level in levels), Decimal("0"))
    mean_price = total_price_volume / total_volume
    return min(candidates, key=lambda level: (abs(level.price - mean_price), level.price))
