from __future__ import annotations
import itertools
from datetime import date, datetime
from zoneinfo import ZoneInfo

from bic.broker import Broker
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
from holodeck.clock import VirtualClock
from holodeck.config import HolodeckConfig
from holodeck.expiration import ExpirationEngine
from holodeck.ledger import AccountLedger
from holodeck.market_data import MarketDataStore
from holodeck.order_engine import OrderEngine
from holodeck.pricing import build_option_chain


class HolodeckBroker(Broker):
    """Concrete BIC implementation backed by Holodeck simulation components."""

    def __init__(self, config: HolodeckConfig) -> None:
        self._config = config
        self._init_components(config)

    def _init_components(self, config: HolodeckConfig) -> None:
        tz = ZoneInfo(config.timezone)
        start = config.starting_datetime
        if start.tzinfo is None:
            start = start.replace(tzinfo=tz)

        self._clock = VirtualClock(
            start,
            config.session_open,
            config.session_close,
            config.timezone,
        )
        self._market_data = MarketDataStore(config.data_path)
        self._market_data.load()
        self._ledger = AccountLedger(config)
        self._order_engine = OrderEngine(
            self._ledger, self._market_data, self._clock, config
        )
        self._expiration_engine = ExpirationEngine(
            self._ledger, self._market_data, self._clock
        )

    # ==========================================================================
    # BIC Interface — required by Broker(ABC)
    # ==========================================================================

    def get_current_time(self) -> datetime:
        return self._clock.current_time()

    def get_account(self) -> AccountSnapshot:
        return self._ledger.get_snapshot()

    def get_positions(self) -> list[Position]:
        return self._ledger.get_positions()

    def get_open_orders(self) -> list[Order]:
        return self._order_engine.get_open_orders()

    def get_underlying_quote(self, symbol: str) -> Quote:
        if symbol != "SPX":
            raise ValueError(
                f"HolodeckBroker only supports SPX in MVP. Got: {symbol!r}"
            )
        return self._market_data.get_quote(self._clock.current_time())

    def get_option_chain(self, symbol: str, expiration: date) -> OptionChain:
        if symbol != "SPX":
            raise ValueError(
                f"HolodeckBroker only supports SPX in MVP. Got: {symbol!r}"
            )
        quote = self._market_data.get_quote(self._clock.current_time())
        return build_option_chain(
            underlying=quote.last,
            expiration=expiration,
            virtual_now=self._clock.current_time(),
        )

    def place_order(self, order: OrderRequest) -> OrderResponse:
        return self._order_engine.submit_order(order)

    def cancel_order(self, order_id: str) -> None:
        self._order_engine.cancel_order(order_id)

    def get_order(self, order_id: str) -> Order:
        return self._order_engine.get_order(order_id)

    def get_ohlcv_bars(
        self, symbol: str, start: datetime, end: datetime, resolution: str
    ) -> list[OHLCVBar]:
        """Return aggregated OHLCV bars from Holodeck synthetic minute data.

        resolution: "1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"
        Raises ValueError for unsupported symbol or unknown resolution.
        """
        if symbol != "SPX":
            raise ValueError(
                f"HolodeckBroker only supports SPX in MVP. Got: {symbol!r}"
            )
        valid = {"1m", "5m", "15m", "30m", "1h", "1d", "1w", "1M"}
        if resolution not in valid:
            raise ValueError(
                f"Unknown resolution {resolution!r}. Must be one of {sorted(valid)}."
            )

        raw = self._market_data.get_bars_range(start, end)
        if not raw:
            return []

        def _bar_key(dt: datetime) -> tuple:
            if resolution == "1m":
                return (dt.year, dt.month, dt.day, dt.hour, dt.minute)
            if resolution == "5m":
                return (dt.year, dt.month, dt.day, dt.hour, dt.minute // 5 * 5)
            if resolution == "15m":
                return (dt.year, dt.month, dt.day, dt.hour, dt.minute // 15 * 15)
            if resolution == "30m":
                return (dt.year, dt.month, dt.day, dt.hour, dt.minute // 30 * 30)
            if resolution == "1h":
                return (dt.year, dt.month, dt.day, dt.hour)
            if resolution == "1d":
                return (dt.year, dt.month, dt.day)
            if resolution == "1M":
                return (dt.year, dt.month)
            # "1w"
            iso = dt.isocalendar()
            return (iso[0], iso[1])  # (year, week)

        bars: list[OHLCVBar] = []
        for _key, group in itertools.groupby(raw, key=lambda x: _bar_key(x[0])):
            points = list(group)
            timestamps, prices = zip(*points)
            bars.append(
                OHLCVBar(
                    symbol=symbol,
                    timestamp=timestamps[0],
                    open=prices[0],
                    high=max(prices),
                    low=min(prices),
                    close=prices[-1],
                )
            )
        return bars

    # ==========================================================================
    # Simulation Control — Holodeck-only (not part of BIC interface)
    # ==========================================================================

    def advance_time(self, minutes: int = 1) -> list[str]:
        """Advance virtual time, evaluate orders, run expiration if needed.
        Returns list of order_ids that filled during this step.
        """
        self._clock.advance(minutes)
        filled_ids = self._order_engine.evaluate_orders()
        if self._expiration_engine.should_run():
            self._expiration_engine.run_expiration()
        return filled_ids

    def advance_to_close(self) -> list[str]:
        """Advance minute-by-minute to today's market close.
        Returns all order_ids that filled during the advance.
        """
        close = self._clock.session_close_time()
        all_filled: list[str] = []
        while self._clock.current_time() < close:
            filled = self.advance_time(1)
            all_filled.extend(filled)
        # Evaluate one final time at close (triggers expiration if needed)
        if self._clock.current_time() == close:
            filled = self._order_engine.evaluate_orders()
            all_filled.extend(filled)
            if self._expiration_engine.should_run():
                self._expiration_engine.run_expiration()
        return all_filled

    def reset(self, config: HolodeckConfig | None = None) -> None:
        """Reinitialize all components. Useful for running multiple scenarios back-to-back."""
        if config is not None:
            self._config = config
        self._init_components(self._config)
