from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class AccountSnapshot:
    account_id: str
    net_liquidation: float
    available_funds: float
    buying_power: float


@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float
    position_type: str  # e.g. "OPTION", "STOCK"


@dataclass
class Quote:
    symbol: str
    last: float
    bid: float
    ask: float


@dataclass
class OptionContract:
    strike: float
    option_type: str  # "CALL" or "PUT"
    bid: float
    ask: float
    delta: float


@dataclass
class OptionChain:
    symbol: str
    expiration: date
    options: list[OptionContract] = field(default_factory=list)


@dataclass
class OrderLeg:
    action: str       # "BUY" or "SELL"
    option_type: str  # "CALL" or "PUT"
    strike: float
    expiration: date


# Canonical order status values shared by all broker adapters.
# Adapters must map broker-native strings to one of these values.
ORDER_STATUS_OPEN = "OPEN"
ORDER_STATUS_PENDING = "PENDING"
ORDER_STATUS_FILLED = "FILLED"
ORDER_STATUS_PARTIALLY_FILLED = "PARTIALLY_FILLED"
ORDER_STATUS_CANCELED = "CANCELED"
ORDER_STATUS_REJECTED = "REJECTED"
ORDER_STATUS_EXPIRED = "EXPIRED"
ORDER_STATUS_PENDING_CANCEL = "PENDING_CANCEL"

# Statuses that mean the order is still active and should keep being polled.
ORDER_ACTIVE_STATUSES: frozenset[str] = frozenset({
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PENDING_CANCEL,
})

# Statuses that mean the order has reached a terminal fill/partial-fill state.
ORDER_FILL_STATUSES: frozenset[str] = frozenset({
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIALLY_FILLED,
})

# Statuses that mean the order is done without a fill.
ORDER_DONE_STATUSES: frozenset[str] = frozenset({
    ORDER_STATUS_CANCELED,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_EXPIRED,
})


@dataclass
class OrderRequest:
    symbol: str
    strategy_type: str   # e.g. "IRON_CONDOR", "PUT_CREDIT_SPREAD"
    legs: list[OrderLeg] = field(default_factory=list)
    quantity: int = 1
    order_type: str = "LIMIT"
    limit_price: float = 0.0
    duration: str = "day"       # time-in-force: "day" | "gtc"
    tag: str | None = None      # broker correlation / trade-reference tag


@dataclass
class OrderResponse:
    order_id: str
    status: str                          # "ACCEPTED" or "REJECTED"
    rejection_reason: str | None = None  # normalized reason code, e.g. "insufficient_buying_power"
    rejection_text: str | None = None    # broker-native description for diagnostics


@dataclass
class Order:
    order_id: str
    status: str              # canonical: see ORDER_STATUS_* constants above
    filled_price: float | None = None
    remaining_quantity: int = 0
    tag: str | None = None           # correlation / trade-reference tag (round-tripped from OrderRequest)
    raw_status: str | None = None    # broker-native status string, preserved for diagnostics


@dataclass
class OHLCVBar:
    symbol: str
    timestamp: datetime   # start of the bar period (naive, local market time)
    open: float
    high: float
    low: float
    close: float
    volume: int = 0       # always 0 for Holodeck (no synthetic volume data)
