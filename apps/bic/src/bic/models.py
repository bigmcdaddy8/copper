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


@dataclass
class OrderRequest:
    symbol: str
    strategy_type: str   # e.g. "IRON_CONDOR", "PUT_CREDIT_SPREAD"
    legs: list[OrderLeg] = field(default_factory=list)
    quantity: int = 1
    order_type: str = "LIMIT"
    limit_price: float = 0.0


@dataclass
class OrderResponse:
    order_id: str
    status: str   # "ACCEPTED" or "REJECTED"


@dataclass
class Order:
    order_id: str
    status: str              # "OPEN", "FILLED", "CANCELED"
    filled_price: float | None = None
    remaining_quantity: int = 0


@dataclass
class OHLCVBar:
    symbol: str
    timestamp: datetime   # start of the bar period (naive, local market time)
    open: float
    high: float
    low: float
    close: float
    volume: int = 0       # always 0 for Holodeck (no synthetic volume data)
