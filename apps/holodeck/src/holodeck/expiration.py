from __future__ import annotations

from holodeck.clock import VirtualClock
from holodeck.ledger import AccountLedger
from holodeck.market_data import MarketDataStore


class ExpirationEngine:
    """Resolves open 0DTE positions at market close."""

    def __init__(
        self,
        ledger: AccountLedger,
        market_data: MarketDataStore,
        clock: VirtualClock,
    ) -> None:
        self._ledger = ledger
        self._market_data = market_data
        self._clock = clock

    def should_run(self) -> bool:
        """Return True if it is time to run expiration.

        Conditions:
        - Current virtual time >= today's session close time
        - At least one OPEN position expires today
        """
        now = self._clock.current_time()
        close = self._clock.session_close_time()
        if now < close:
            return False
        today = now.date()
        return any(p.expiration == today for p in self._ledger.get_open_sim_positions())

    def run_expiration(self) -> list[str]:
        """Expire all OPEN positions with today's expiration date.

        Steps:
        1. Get final underlying price (15:00 bar) from MarketDataStore
        2. For each OPEN SimPosition expiring today: call ledger.expire_position()
        3. Return list of expired order_ids

        Returns empty list if no positions expire today.
        """
        now = self._clock.current_time()
        today = now.date()
        expired_ids: list[str] = []

        try:
            final_underlying = self._market_data.get_daily_close(today)
        except KeyError:
            # No data for today (e.g., not a trading day) — nothing to expire
            return []

        for pos in self._ledger.get_open_sim_positions():
            if pos.expiration == today:
                self._ledger.expire_position(pos.order_id, final_underlying, now)
                expired_ids.append(pos.order_id)

        return expired_ids
