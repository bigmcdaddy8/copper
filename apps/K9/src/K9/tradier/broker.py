"""TradierBroker — BIC Broker implementation wrapping the Tradier REST API (K9-0020/K9-0030)."""
from __future__ import annotations

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from bic.broker import Broker
from bic.models import (
    AccountSnapshot,
    OHLCVBar,
    OptionChain,
    OptionContract,
    Order,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
)

_SANDBOX_BASE = "https://sandbox.tradier.com/v1"
_PROD_BASE = "https://api.tradier.com/v1"
_TZ = ZoneInfo("America/Chicago")
_RATE_LIMIT_DELAY = 0.12   # ~8 req/s — well within Tradier's 120 req/min limit


class TradierBroker(Broker):
    """Implements the BIC Broker ABC against the Tradier REST API.

    Args:
        api_key: Tradier API token (production or sandbox).
        account_id: Tradier brokerage account ID.
        sandbox: If True, targets sandbox.tradier.com; otherwise api.tradier.com.
    """

    def __init__(self, api_key: str, account_id: str, sandbox: bool = True) -> None:
        self._api_key = api_key
        self._account_id = account_id
        self._base = _SANDBOX_BASE if sandbox else _PROD_BASE
        self._last_call: float = 0.0

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with adaptive rate-limit throttle."""
        elapsed = time.monotonic() - self._last_call
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)
        resp = httpx.get(
            f"{self._base}{path}",
            headers=self._headers(),
            params=params or {},
            timeout=10.0,
        )
        resp.raise_for_status()
        self._last_call = time.monotonic()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)
        resp = httpx.post(
            f"{self._base}{path}",
            headers=self._headers(),
            data=data,
            timeout=10.0,
        )
        resp.raise_for_status()
        self._last_call = time.monotonic()
        return resp.json()

    def _delete(self, path: str) -> dict:
        elapsed = time.monotonic() - self._last_call
        if elapsed < _RATE_LIMIT_DELAY:
            time.sleep(_RATE_LIMIT_DELAY - elapsed)
        resp = httpx.delete(
            f"{self._base}{path}",
            headers=self._headers(),
            timeout=10.0,
        )
        resp.raise_for_status()
        self._last_call = time.monotonic()
        return resp.json()

    # ------------------------------------------------------------------ #
    # BIC — Time                                                           #
    # ------------------------------------------------------------------ #

    def get_current_time(self) -> datetime:
        """Return real wall-clock time in CT."""
        return datetime.now(tz=_TZ)

    # ------------------------------------------------------------------ #
    # BIC — Market Data                                                    #
    # ------------------------------------------------------------------ #

    def get_underlying_quote(self, symbol: str) -> Quote:
        """Return the latest quote for *symbol* from Tradier /markets/quotes."""
        data = self._get("/markets/quotes", params={"symbols": symbol, "greeks": "false"})
        q = data["quotes"]["quote"]
        return Quote(
            symbol=q["symbol"],
            last=float(q["last"]),
            bid=float(q["bid"]),
            ask=float(q["ask"]),
        )

    def get_option_chain(self, symbol: str, expiration: date) -> OptionChain:
        """Return option chain for *symbol* expiring on *expiration*."""
        data = self._get(
            "/markets/options/chains",
            params={
                "symbol": symbol,
                "expiration": expiration.isoformat(),
                "greeks": "true",
            },
        )
        raw_options = (data.get("options") or {}).get("option") or []
        if isinstance(raw_options, dict):
            raw_options = [raw_options]

        contracts: list[OptionContract] = []
        for o in raw_options:
            delta_raw = (o.get("greeks") or {}).get("delta")
            contracts.append(
                OptionContract(
                    strike=float(o["strike"]),
                    option_type=o["option_type"].upper(),
                    bid=float(o["bid"]),
                    ask=float(o["ask"]),
                    delta=float(delta_raw) if delta_raw is not None else 0.0,
                )
            )
        return OptionChain(symbol=symbol, expiration=expiration, options=contracts)

    def get_ohlcv_bars(
        self, symbol: str, start: datetime, end: datetime, resolution: str
    ) -> list[OHLCVBar]:
        raise NotImplementedError("OHLCV bars not used by K9 MVP.")

    # ------------------------------------------------------------------ #
    # BIC — Account                                                        #
    # ------------------------------------------------------------------ #

    def get_account(self) -> AccountSnapshot:
        """Return account balances from Tradier /accounts/{id}/balances."""
        data = self._get(f"/accounts/{self._account_id}/balances")
        b = data["balances"]
        return AccountSnapshot(
            account_id=self._account_id,
            net_liquidation=float(b["total_equity"]),
            available_funds=float(b["cash"]["cash_available"]),
            buying_power=float(b["option_buying_power"]),
        )

    def get_positions(self) -> list[Position]:
        """Return all open positions from Tradier /accounts/{id}/positions."""
        data = self._get(f"/accounts/{self._account_id}/positions")
        raw = (data.get("positions") or {}).get("position") or []
        if isinstance(raw, dict):
            raw = [raw]
        return [
            Position(
                symbol=p["symbol"],
                quantity=int(p["quantity"]),
                avg_price=float(p["cost_basis"]) / abs(int(p["quantity"])) / 100,
                position_type="OPTION" if len(p["symbol"]) > 10 else "STOCK",
            )
            for p in raw
        ]

    def get_open_orders(self) -> list[Order]:
        """Return all open orders from Tradier /accounts/{id}/orders."""
        data = self._get(
            f"/accounts/{self._account_id}/orders",
            params={"includeTags": "false"},
        )
        raw = (data.get("orders") or {}).get("order") or []
        if isinstance(raw, dict):
            raw = [raw]
        open_orders = [o for o in raw if o.get("status") == "open"]
        return [
            Order(
                order_id=str(o["id"]),
                status="OPEN",
                filled_price=None,
                remaining_quantity=int(o.get("quantity", 1)),
            )
            for o in open_orders
        ]

    # ------------------------------------------------------------------ #
    # BIC — Orders                                                         #
    # ------------------------------------------------------------------ #

    def place_order(self, order: OrderRequest) -> OrderResponse:
        """Submit a multi-leg combo order to Tradier."""
        duration = getattr(order, "duration", "day")
        payload: dict = {
            "class": "multileg",
            "symbol": order.symbol,
            "type": "limit",
            "duration": duration,
            "price": round(order.limit_price, 2),
            "quantity": order.quantity,
        }
        for i, leg in enumerate(order.legs):
            payload[f"option_symbol[{i}]"] = _build_occ_symbol(leg)
            payload[f"side[{i}]"] = _tradier_side(leg.action, leg.option_type)
            payload[f"quantity[{i}]"] = order.quantity

        data = self._post(f"/accounts/{self._account_id}/orders", payload)
        result = data.get("order", {})
        status = result.get("status", "").upper()
        order_id = str(result.get("id", ""))
        return OrderResponse(
            order_id=order_id,
            status="ACCEPTED" if status == "OK" else "REJECTED",
        )

    def get_order(self, order_id: str) -> Order:
        """Return current order status from Tradier."""
        data = self._get(f"/accounts/{self._account_id}/orders/{order_id}")
        o = data.get("order", {})
        raw_status = o.get("status", "").lower()
        status_map = {
            "filled": "FILLED",
            "canceled": "CANCELED",
            "open": "OPEN",
            "pending": "OPEN",
        }
        bic_status = status_map.get(raw_status, "OPEN")
        avg_fill = o.get("avg_fill_price")
        return Order(
            order_id=order_id,
            status=bic_status,
            filled_price=float(avg_fill) if avg_fill else None,
            remaining_quantity=int(o.get("remaining_quantity", 0)),
        )

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order."""
        self._delete(f"/accounts/{self._account_id}/orders/{order_id}")


# ------------------------------------------------------------------ #
# Module-level helpers                                                #
# ------------------------------------------------------------------ #

def _build_occ_symbol(leg: "OrderLeg") -> str:  # noqa: F821
    """Build the OCC option symbol string expected by Tradier.

    Format: SYMBOL YYMMDD C/P STRIKE (21-char OCC format).
    Example: SPX   260105P05800000
    """
    exp = leg.expiration.strftime("%y%m%d")
    cp = "C" if leg.option_type == "CALL" else "P"
    strike_int = int(leg.strike * 1000)
    return f"{exp}{cp}{strike_int:08d}"


def _tradier_side(action: str, option_type: str) -> str:
    """Map BIC (action, option_type) to Tradier side string."""
    mapping = {
        ("BUY",  "CALL"): "buy_to_open",
        ("BUY",  "PUT"):  "buy_to_open",
        ("SELL", "CALL"): "sell_to_open",
        ("SELL", "PUT"):  "sell_to_open",
        ("BUY",  "CALL", "close"): "buy_to_close",
        ("BUY",  "PUT",  "close"): "buy_to_close",
        ("SELL", "CALL", "close"): "sell_to_close",
        ("SELL", "PUT",  "close"): "sell_to_close",
    }
    return mapping.get((action.upper(), option_type.upper()), "buy_to_open")
