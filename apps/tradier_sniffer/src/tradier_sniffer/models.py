from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OrderStatus(str, Enum):
    open = "open"
    pending = "pending"
    pending_cancel = "pending_cancel"
    partially_filled = "partially_filled"
    filled = "filled"
    partially_filled_canceled = "partially_filled_canceled"
    canceled = "canceled"
    rejected = "rejected"
    expired = "expired"


class EventType(str, Enum):
    new_order = "new_order"
    filled = "filled"
    closed = "closed"
    canceled = "canceled"


class TradeStatus(str, Enum):
    open = "open"
    closed = "closed"


class TradeType(str, Enum):
    SIC = "SIC"
    PCS = "PCS"
    CCS = "CCS"
    NPUT = "NPUT"
    NCALL = "NCALL"
    CCALL = "CCALL"
    STOCK = "STOCK"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TRADE_ID_RE = re.compile(r"^TRDS_\d{5,}_[A-Z]+$")


def is_valid_trade_id(trade_id: str) -> bool:
    """Return True if trade_id matches the TRDS_{#####}_{TTT} format."""
    return bool(_TRADE_ID_RE.match(trade_id))


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class OrderLeg:
    """One leg of a Tradier multileg option order."""

    option_symbol: str
    side: str
    quantity: int
    fill_price: float | None = None
    fill_quantity: int | None = None


@dataclass
class Order:
    """A single Tradier order (single-leg or multileg)."""

    order_id: str
    account_id: str
    symbol: str
    class_: str
    order_type: str
    side: str
    quantity: int
    status: OrderStatus
    duration: str
    limit_price: float | None = None
    fill_price: float | None = None
    fill_quantity: int | None = None
    option_symbol: str | None = None
    legs: list[OrderLeg] = field(default_factory=list)
    tag: str | None = None
    created_at: str = ""
    updated_at: str | None = None


@dataclass
class Position:
    """A single open position from GET /accounts/{id}/positions."""

    account_id: str
    symbol: str
    quantity: int
    cost_basis: float
    date_acquired: str


@dataclass
class Trade:
    """Proprietary logical grouping of orders under a single Trade #."""

    trade_id: str
    trade_type: str
    underlying: str
    opened_at: str
    status: TradeStatus = TradeStatus.open
    closed_at: str | None = None
    notes: str | None = None


@dataclass
class TradeOrderMap:
    """Maps a Trade to an Order with a role label."""

    trade_id: str
    order_id: str
    role: str  # entry | tp | adjustment | exit
    mapped_at: str


@dataclass
class EventLog:
    """Append-only audit trail entry for a state transition."""

    timestamp: str
    event_type: EventType
    order_id: str | None = None
    trade_id: str | None = None
    details: str = "{}"
    event_id: int | None = None  # assigned by DB on insert
