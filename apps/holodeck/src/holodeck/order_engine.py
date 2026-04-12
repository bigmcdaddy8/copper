from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

from bic.models import Order, OrderRequest, OrderResponse
from holodeck.clock import VirtualClock
from holodeck.config import HolodeckConfig
from holodeck.ledger import AccountLedger
from holodeck.market_data import MarketDataStore
from holodeck.pricing import build_option_chain


@dataclass
class SimOrder:
    """Internal order record. NOT a BIC model."""
    order_id: str
    request: OrderRequest
    status: str               # "OPEN", "FILLED", "CANCELED", "REJECTED"
    submitted_at: datetime
    filled_at: datetime | None = None
    filled_price: float | None = None
    remaining_quantity: int = 0


class OrderEngine:
    """Handles order lifecycle: accept, evaluate fills, cancel."""

    _MIN_BP_BUFFER = 0.0

    def __init__(
        self,
        ledger: AccountLedger,
        market_data: MarketDataStore,
        clock: VirtualClock,
        config: HolodeckConfig,
    ) -> None:
        self._ledger = ledger
        self._market_data = market_data
        self._clock = clock
        self._config = config
        self._orders: dict[str, SimOrder] = {}
        self._next_order_num = 1

    def submit_order(self, request: OrderRequest) -> OrderResponse:
        """Validate and accept or reject an order.

        Rejection conditions:
        - Market is not open
        - order_type is not "LIMIT"
        - An open position already exists for request.symbol (entry orders only)
        - Insufficient buying power (estimated max_loss > available buying_power)
        """
        if not self._clock.is_market_open():
            return OrderResponse(order_id="", status="REJECTED")

        if request.order_type != "LIMIT":
            return OrderResponse(order_id="", status="REJECTED")

        # Block duplicate positions (unless this is a TP/closing order)
        if not self._is_closing_order(request):
            if self._ledger.has_position_for(request.symbol):
                return OrderResponse(order_id="", status="REJECTED")

        # Check buying power for entry orders
        if not self._is_closing_order(request):
            estimated_bp = self._estimate_buying_power(request)
            if estimated_bp > self._ledger.get_snapshot().buying_power:
                return OrderResponse(order_id="", status="REJECTED")

        order_id = f"HD-{self._next_order_num:06d}"
        self._next_order_num += 1
        sim_order = SimOrder(
            order_id=order_id,
            request=request,
            status="OPEN",
            submitted_at=self._clock.current_time(),
            remaining_quantity=request.quantity,
        )
        self._orders[order_id] = sim_order
        return OrderResponse(order_id=order_id, status="ACCEPTED")

    def evaluate_orders(self) -> list[str]:
        """Evaluate all OPEN orders against current market data. Return filled order IDs."""
        filled_ids: list[str] = []
        now = self._clock.current_time()

        for order_id, sim_order in self._orders.items():
            if sim_order.status != "OPEN":
                continue

            try:
                quote = self._market_data.get_quote(now)
            except KeyError:
                continue  # Outside market hours or data gap — skip

            underlying = quote.last
            chain = build_option_chain(underlying, now.date(), now, iv_base=0.20)

            if self._is_closing_order(sim_order.request):
                # TP / debit order: fill if combo_ask_to_close <= limit_price
                combo_ask = self._compute_combo_ask_to_close(sim_order.request, chain)
                if combo_ask <= sim_order.request.limit_price:
                    self._fill_order(sim_order, combo_ask, now, closing=True)
                    filled_ids.append(order_id)
            else:
                # Entry / credit order: fill if combo_bid >= limit_price
                combo_bid = self._compute_combo_bid(sim_order.request, chain)
                if combo_bid >= sim_order.request.limit_price:
                    self._fill_order(sim_order, combo_bid, now, closing=False)
                    filled_ids.append(order_id)

        return filled_ids

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order. No-op if already filled or unknown."""
        sim_order = self._orders.get(order_id)
        if sim_order is not None and sim_order.status == "OPEN":
            sim_order.status = "CANCELED"

    def get_order(self, order_id: str) -> Order:
        """Return BIC Order for the given order_id. Raises KeyError if unknown."""
        sim_order = self._orders[order_id]
        return Order(
            order_id=sim_order.order_id,
            status=sim_order.status,
            filled_price=sim_order.filled_price,
            remaining_quantity=sim_order.remaining_quantity,
        )

    def get_open_orders(self) -> list[Order]:
        return [
            Order(
                order_id=o.order_id,
                status=o.status,
                filled_price=o.filled_price,
                remaining_quantity=o.remaining_quantity,
            )
            for o in self._orders.values()
            if o.status == "OPEN"
        ]

    # --- Private helpers ---

    def _is_closing_order(self, request: OrderRequest) -> bool:
        """Detect TP/closing order by strategy_type containing 'TP' or all-BUY legs."""
        if "TP" in request.strategy_type.upper():
            return True
        if request.legs and all(leg.action == "BUY" for leg in request.legs):
            return True
        return False

    def _fill_order(
        self,
        sim_order: SimOrder,
        filled_price: float,
        now: datetime,
        closing: bool,
    ) -> None:
        sim_order.status = "FILLED"
        sim_order.filled_at = now
        sim_order.filled_price = filled_price
        sim_order.remaining_quantity = 0

        if closing:
            open_positions = self._ledger.get_open_sim_positions()
            matching = [p for p in open_positions if p.symbol == sim_order.request.symbol]
            if matching:
                self._ledger.close_position(matching[0].order_id, filled_price, now)
        else:
            self._ledger.open_position(
                sim_order.order_id,
                sim_order.request,
                filled_price,
                now,
            )

    def _compute_combo_bid(self, request: OrderRequest, chain) -> float:
        """Combo bid = sum(sell_leg bids) - sum(buy_leg asks).
        This is the net credit the market pays us to enter the trade.
        """
        total = 0.0
        for leg in request.legs:
            contract = self._find_contract(chain, leg.strike, leg.option_type)
            if contract is None:
                return 0.0
            if leg.action == "SELL":
                total += contract.bid
            else:
                total -= contract.ask
        return round(total, 2)

    def _compute_combo_ask_to_close(self, request: OrderRequest, chain) -> float:
        """Combo ask-to-close = cost to buy back all sell legs and sell all buy legs.
        This is the debit we pay to exit the trade.
        """
        total = 0.0
        for leg in request.legs:
            contract = self._find_contract(chain, leg.strike, leg.option_type)
            if contract is None:
                return float("inf")
            # Reversed: original SELL → now BUY back (cost = ask)
            #           original BUY → now SELL (receive = bid)
            if leg.action == "SELL":
                total += contract.ask
            else:
                total -= contract.bid
        return round(max(0.0, total), 2)

    def _find_contract(self, chain, strike: float, option_type: str):
        for c in chain.options:
            if c.strike == strike and c.option_type == option_type:
                return c
        return None

    def _estimate_buying_power(self, request: OrderRequest) -> float:
        """Rough buying power estimate for pre-trade check.
        Uses wing_size from legs as a conservative upper bound.
        """
        sell_strikes = [leg.strike for leg in request.legs if leg.action == "SELL"]
        buy_strikes = [leg.strike for leg in request.legs if leg.action == "BUY"]
        if not sell_strikes or not buy_strikes:
            return 0.0
        wing_size = max(abs(s - b) for s in sell_strikes for b in buy_strikes)
        return wing_size * 100 * request.quantity
