"""Immutable normalized market-observation types for Dick's Laboratory."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID


class InstrumentKind(StrEnum):
    FUTURE = "FUTURE"


class DatasetKind(StrEnum):
    SYNTHETIC = "SYNTHETIC"


class TradeAction(StrEnum):
    NEW = "NEW"


@dataclass(frozen=True)
class InstrumentIdentity:
    """Provider-neutral identity for a specific futures contract."""

    kind: InstrumentKind
    exchange: str
    root: str
    expiration_year: int
    expiration_month: int

    def __post_init__(self) -> None:
        if self.kind is not InstrumentKind.FUTURE:
            raise ValueError("Phase 0C supports only FUTURE instruments.")
        if not self.exchange or not self.root:
            raise ValueError("Future exchange and root are required.")
        if self.expiration_year < 1:
            raise ValueError("Future expiration year must be positive.")
        if not 1 <= self.expiration_month <= 12:
            raise ValueError("Future expiration month must be between 1 and 12.")

    @property
    def canonical_id(self) -> str:
        return (
            f"{self.kind}:{self.exchange.upper()}:{self.root.upper()}:"
            f"{self.expiration_year:04d}-{self.expiration_month:02d}"
        )


@dataclass(frozen=True)
class DatasetIdentity:
    """Identifies a bounded collection of observations with one replay order."""

    dataset_id: UUID
    kind: DatasetKind
    label: str

    def __post_init__(self) -> None:
        if not self.label.strip():
            raise ValueError("Dataset label is required.")


@dataclass(frozen=True)
class TradeObservation:
    """An immutable, normalized trade used by deterministic analytics."""

    observation_id: UUID
    dataset_id: UUID
    dataset_sequence: int
    instrument: InstrumentIdentity
    event_timestamp: datetime
    price: Decimal
    size: Decimal
    trade_action: TradeAction = TradeAction.NEW

    def __post_init__(self) -> None:
        if self.dataset_sequence < 1:
            raise ValueError("Dataset sequence must be positive.")
        if self.event_timestamp.tzinfo is not timezone.utc:
            raise ValueError("Event timestamp must use timezone.utc.")
        if self.event_timestamp.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("Event timestamp must be UTC.")
        if self.trade_action is TradeAction.NEW:
            if self.price <= Decimal("0"):
                raise ValueError("New trade price must be positive.")
            if self.size <= Decimal("0"):
                raise ValueError("New trade size must be positive.")