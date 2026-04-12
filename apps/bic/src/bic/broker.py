from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date, datetime

from bic.models import (
    AccountSnapshot,
    OHLCVBar,
    OptionChain,
    Order,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
)


class Broker(ABC):
    """Abstract interface for all broker implementations (Holodeck, Tradier sandbox, production)."""

    # --- Time ---
    @abstractmethod
    def get_current_time(self) -> datetime:
        """Return current broker time (real or virtual)."""
        ...

    # --- Account ---
    @abstractmethod
    def get_account(self) -> AccountSnapshot:
        """Return account state including balances."""
        ...

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return all open positions."""
        ...

    @abstractmethod
    def get_open_orders(self) -> list[Order]:
        """Return all open orders."""
        ...

    # --- Market Data ---
    @abstractmethod
    def get_underlying_quote(self, symbol: str) -> Quote:
        """Return latest quote for underlying symbol."""
        ...

    @abstractmethod
    def get_option_chain(self, symbol: str, expiration: date) -> OptionChain:
        """Return option chain for symbol and expiration date."""
        ...

    @abstractmethod
    def get_ohlcv_bars(
        self, symbol: str, start: datetime, end: datetime, resolution: str
    ) -> list[OHLCVBar]:
        """Return OHLCV bars for symbol between start and end at the given resolution.

        resolution: "1m", "5m", "15m", "30m", "1h" (hourly), "1d" (daily), "1w" (weekly), "1M" (monthly)
        Returns bars sorted by timestamp ascending.
        """
        ...

    # --- Orders ---
    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResponse:
        """Submit an order. Returns ACCEPTED or REJECTED."""
        ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        """Cancel an existing open order."""
        ...

    @abstractmethod
    def get_order(self, order_id: str) -> Order:
        """Retrieve current order status."""
        ...
