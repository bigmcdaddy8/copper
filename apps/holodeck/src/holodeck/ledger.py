from __future__ import annotations
from dataclasses import dataclass
from datetime import date, datetime

from bic.models import AccountSnapshot, OrderLeg, OrderRequest, Position
from holodeck.config import HolodeckConfig


@dataclass
class SimPosition:
    """Internal position record. NOT a BIC model — not exported."""
    order_id: str
    symbol: str
    strategy_type: str
    quantity: int
    entry_credit: float      # net credit received at fill (positive = received)
    entry_time: datetime
    expiration: date
    legs: list[OrderLeg]
    max_loss: float          # buying power reduction in dollars (already × 100 × qty)
    status: str = "OPEN"     # "OPEN" or "CLOSED"


class AccountLedger:
    """In-memory account state for Holodeck simulation."""

    def __init__(self, config: HolodeckConfig) -> None:
        self._net_liquidation = config.starting_account_value
        self._available_funds = config.starting_account_value
        self._buying_power = config.starting_buying_power
        self._realized_pnl: float = 0.0
        self._positions: list[SimPosition] = []

    # --- BIC-facing reads ---

    def get_snapshot(self) -> AccountSnapshot:
        return AccountSnapshot(
            account_id="holodeck-sim",
            net_liquidation=self._net_liquidation,
            available_funds=self._available_funds,
            buying_power=self._buying_power,
        )

    def get_positions(self) -> list[Position]:
        """Return OPEN positions as BIC Position objects."""
        return [
            Position(
                symbol=p.symbol,
                quantity=p.quantity,
                avg_price=p.entry_credit,
                position_type=p.strategy_type,
            )
            for p in self._positions
            if p.status == "OPEN"
        ]

    # --- Internal reads ---

    def has_position_for(self, symbol: str) -> bool:
        return any(p.symbol == symbol and p.status == "OPEN" for p in self._positions)

    def get_sim_positions(self) -> list[SimPosition]:
        return list(self._positions)

    def get_open_sim_positions(self) -> list[SimPosition]:
        return [p for p in self._positions if p.status == "OPEN"]

    # --- Mutation ---

    def open_position(
        self,
        order_id: str,
        order: OrderRequest,
        entry_credit: float,
        entry_time: datetime,
    ) -> None:
        """Called when an entry order fills. Reduces buying power."""
        expiration = order.legs[0].expiration if order.legs else date.today()
        max_loss = self._compute_buying_power_reduction(order, entry_credit)

        sim_pos = SimPosition(
            order_id=order_id,
            symbol=order.symbol,
            strategy_type=order.strategy_type,
            quantity=order.quantity,
            entry_credit=entry_credit,
            entry_time=entry_time,
            expiration=expiration,
            legs=list(order.legs),
            max_loss=max_loss,
        )
        self._positions.append(sim_pos)
        self._available_funds -= max_loss
        self._buying_power -= max_loss

    def close_position(
        self,
        order_id: str,
        exit_debit: float,
        close_time: datetime,
    ) -> None:
        """Called by OrderEngine (TP fill) or ExpirationEngine. Releases buying power."""
        pos = self._find_open_position(order_id)
        if pos is None:
            return  # already closed or unknown — no-op
        pos.status = "CLOSED"

        pnl_per_unit = (pos.entry_credit - exit_debit) * 100
        pnl_total = pnl_per_unit * pos.quantity
        self._realized_pnl += pnl_total
        self._net_liquidation += pnl_total
        self._available_funds += pos.max_loss
        self._buying_power += pos.max_loss

    def expire_position(
        self,
        order_id: str,
        final_underlying: float,
        close_time: datetime,
    ) -> None:
        """Called by ExpirationEngine at end of trading day."""
        pos = self._find_open_position(order_id)
        if pos is None:
            return
        exit_debit = self._compute_expiration_debit(pos, final_underlying)
        self.close_position(order_id, exit_debit, close_time)

    # --- Private helpers ---

    def _find_open_position(self, order_id: str) -> SimPosition | None:
        for p in self._positions:
            if p.order_id == order_id and p.status == "OPEN":
                return p
        return None

    def _compute_buying_power_reduction(
        self, order: OrderRequest, entry_credit: float
    ) -> float:
        """Compute max_loss in dollars for the trade.
        For spreads/condors: wing_size = max spread width (strike distance × 100).
        max_loss = (wing_size - entry_credit × 100) × quantity.
        """
        sell_strikes = [leg.strike for leg in order.legs if leg.action == "SELL"]
        buy_strikes = [leg.strike for leg in order.legs if leg.action == "BUY"]
        if not sell_strikes or not buy_strikes:
            return 0.0

        wing_size = 0.0
        for s_strike in sell_strikes:
            for b_strike in buy_strikes:
                wing_size = max(wing_size, abs(s_strike - b_strike))

        wing_dollars = wing_size * 100
        credit_dollars = entry_credit * 100
        max_loss = max(0.0, (wing_dollars - credit_dollars) * order.quantity)
        return max_loss

    def _compute_expiration_debit(
        self, pos: SimPosition, final_underlying: float
    ) -> float:
        """Compute the net debit owed at expiration based on intrinsic values.

        Intrinsic values are expressed as option prices ($ per share).
        For SPX: 10 index points of intrinsic = $10.00 option price.
        Do NOT divide by 100 — strike math already yields option price directly.
        """
        net_debit = 0.0
        for leg in pos.legs:
            if leg.option_type == "CALL":
                intrinsic = max(0.0, final_underlying - leg.strike)
            else:
                intrinsic = max(0.0, leg.strike - final_underlying)

            if leg.action == "SELL":
                net_debit += intrinsic  # we owe this
            else:
                net_debit -= intrinsic  # we receive this (reduces debit)

        return max(0.0, net_debit)
