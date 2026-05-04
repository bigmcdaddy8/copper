"""TradierBroker — BIC Broker implementation wrapping the Tradier REST API (K9-0020/K9-0030)."""
from __future__ import annotations

import time
import urllib.parse
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
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_PARTIALLY_FILLED,
    ORDER_STATUS_CANCELED,
    ORDER_STATUS_REJECTED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_PENDING_CANCEL,
)

_SANDBOX_BASE = "https://sandbox.tradier.com/v1"
_PROD_BASE = "https://api.tradier.com/v1"
_TZ = ZoneInfo("America/Chicago")

# Adaptive throttle constants (mirrors tradier_sniffer._compute_delay pattern).
_TARGET_UTILIZATION = 0.90
_THROTTLE_MIN_DELAY = 0.05
_THROTTLE_MAX_DELAY = 2.00
_THROTTLE_DEFAULT_DELAY = 0.20
_HTTP_TIMEOUT = 20.0
_MAX_HTTP_ATTEMPTS = 3

# Tradier raw status → canonical BIC status (Option B: mirror full Tradier granularity).
_STATUS_MAP: dict[str, str] = {
    "filled":                    ORDER_STATUS_FILLED,
    "partially_filled":          ORDER_STATUS_PARTIALLY_FILLED,
    "open":                      ORDER_STATUS_OPEN,
    "pending":                   ORDER_STATUS_PENDING,
    "pending_cancel":            ORDER_STATUS_PENDING_CANCEL,
    "canceled":                  ORDER_STATUS_CANCELED,
    "rejected":                  ORDER_STATUS_REJECTED,
    "expired":                   ORDER_STATUS_EXPIRED,
    "partially_filled_canceled": ORDER_STATUS_CANCELED,
}


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
        # Adaptive throttle state (populated from X-Ratelimit-* response headers).
        self._ratelimit_available: int | None = None
        self._ratelimit_expiry: int | None = None

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }

    # --- Adaptive throttle helpers ---

    def _update_ratelimit(self, headers: httpx.Headers) -> None:
        """Parse rate-limit headers from Tradier response and update internal state."""
        available = headers.get("X-Ratelimit-Available")
        expiry = headers.get("X-Ratelimit-Expiry")
        if available is not None:
            self._ratelimit_available = int(available)
        if expiry is not None:
            self._ratelimit_expiry = int(expiry)

    def _throttle(self) -> None:
        """Block if near rate-limit exhaustion, then sleep for the computed delay."""
        if self._ratelimit_available is not None and self._ratelimit_available <= 5:
            if self._ratelimit_expiry is not None:
                wake_at = self._ratelimit_expiry / 1000.0 + 1.0
                sleep_for = wake_at - time.time()
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._ratelimit_available = None
            self._ratelimit_expiry = None
        else:
            time.sleep(self._compute_delay())

    def _compute_delay(self) -> float:
        """Return inter-call sleep duration based on remaining rate-limit budget."""
        if self._ratelimit_available is None:
            return _THROTTLE_DEFAULT_DELAY
        if self._ratelimit_expiry is not None:
            remaining_seconds = max(1.0, self._ratelimit_expiry / 1000.0 - time.time())
        else:
            remaining_seconds = 60.0
        safe_calls = self._ratelimit_available * _TARGET_UTILIZATION
        delay = remaining_seconds / max(safe_calls, 1.0)
        return max(_THROTTLE_MIN_DELAY, min(_THROTTLE_MAX_DELAY, delay))

    def _raise_for_status_with_detail(self, resp: httpx.Response) -> None:
        """Raise HTTPStatusError enriched with broker response detail."""
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                payload = resp.json()
            except ValueError:
                payload = None

            if isinstance(payload, dict):
                fault = payload.get("fault")
                if isinstance(fault, dict):
                    detail = (
                        str(fault.get("faultstring") or "")
                        or str(fault.get("detail") or "")
                    )
                if not detail and isinstance(payload.get("errors"), list):
                    errors = payload["errors"]
                    if errors:
                        detail = str(errors[0])

            if not detail:
                detail = (resp.text or "").strip()
            detail = " ".join(detail.split())
            if len(detail) > 400:
                detail = f"{detail[:400]}..."

            if detail:
                raise httpx.HTTPStatusError(
                    f"{exc} Tradier response: {detail}",
                    request=exc.request,
                    response=exc.response,
                ) from exc
            raise

    def _get(self, path: str, params: dict | None = None) -> dict:
        """GET with adaptive rate-limit throttle."""
        last_exc: Exception | None = None
        for attempt in range(_MAX_HTTP_ATTEMPTS):
            self._throttle()
            try:
                resp = httpx.get(
                    f"{self._base}{path}",
                    headers=self._headers(),
                    params=params or {},
                    timeout=_HTTP_TIMEOUT,
                )
                break
            except httpx.ReadTimeout as exc:
                last_exc = exc
                if attempt == _MAX_HTTP_ATTEMPTS - 1:
                    raise
                continue
        else:
            raise RuntimeError("GET retry loop exhausted") from last_exc

        self._raise_for_status_with_detail(resp)
        self._update_ratelimit(resp.headers)
        self._last_call = time.monotonic()
        return resp.json()

    def _post(self, path: str, data: dict) -> dict:
        """POST with adaptive throttle and literal bracket-key form encoding.

        Uses urllib.parse.quote to encode values but preserves literal '[' and ']'
        in keys so that Tradier can parse indexed leg parameters (option_symbol[0] etc.).
        If the brackets were percent-encoded the broker would see 0 legs and reject.
        """
        body = "&".join(
            f"{k}={urllib.parse.quote(str(v), safe='')}"
            for k, v in data.items()
        )
        last_exc: Exception | None = None
        for attempt in range(_MAX_HTTP_ATTEMPTS):
            self._throttle()
            try:
                resp = httpx.post(
                    f"{self._base}{path}",
                    headers={
                        **self._headers(),
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                    content=body,
                    timeout=_HTTP_TIMEOUT,
                )
                break
            except httpx.ReadTimeout as exc:
                last_exc = exc
                if attempt == _MAX_HTTP_ATTEMPTS - 1:
                    raise
                continue
        else:
            raise RuntimeError("POST retry loop exhausted") from last_exc

        self._raise_for_status_with_detail(resp)
        self._update_ratelimit(resp.headers)
        self._last_call = time.monotonic()
        return resp.json()

    def _delete(self, path: str) -> dict:
        last_exc: Exception | None = None
        for attempt in range(_MAX_HTTP_ATTEMPTS):
            self._throttle()
            try:
                resp = httpx.delete(
                    f"{self._base}{path}",
                    headers=self._headers(),
                    timeout=_HTTP_TIMEOUT,
                )
                break
            except httpx.ReadTimeout as exc:
                last_exc = exc
                if attempt == _MAX_HTTP_ATTEMPTS - 1:
                    raise
                continue
        else:
            raise RuntimeError("DELETE retry loop exhausted") from last_exc

        self._raise_for_status_with_detail(resp)
        self._update_ratelimit(resp.headers)
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

        last = float(q["last"]) if q.get("last") is not None else None
        bid = float(q["bid"]) if q.get("bid") is not None else None
        ask = float(q["ask"]) if q.get("ask") is not None else None

        # Sandbox quote payloads sometimes omit `last`; midpoint is sufficient for
        # entry pre-checks and keeps the run moving when top-of-book is present.
        if last is None and bid is not None and ask is not None:
            last = (bid + ask) / 2.0
        if bid is None and last is not None:
            bid = last
        if ask is None and last is not None:
            ask = last
        if last is None or bid is None or ask is None:
            raise ValueError(
                "Tradier quote missing required numeric fields: "
                f"last={q.get('last')!r}, bid={q.get('bid')!r}, ask={q.get('ask')!r}"
            )

        return Quote(
            symbol=q["symbol"],
            last=last,
            bid=bid,
            ask=ask,
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

        cash_block = b.get("cash") if isinstance(b, dict) else None
        cash_available_raw = None
        if isinstance(cash_block, dict):
            cash_available_raw = cash_block.get("cash_available")
        if cash_available_raw is None:
            cash_available_raw = b.get("cash_available")
        if cash_available_raw is None:
            cash_available_raw = b.get("total_cash")

        buying_power_raw = b.get("option_buying_power")
        if buying_power_raw is None:
            buying_power_raw = b.get("buying_power")
        if buying_power_raw is None:
            buying_power_raw = cash_available_raw

        net_liquidation_raw = b.get("total_equity")
        if net_liquidation_raw is None:
            net_liquidation_raw = b.get("equity")

        if net_liquidation_raw is None or cash_available_raw is None or buying_power_raw is None:
            raise KeyError("missing required balance fields")

        return AccountSnapshot(
            account_id=self._account_id,
            net_liquidation=float(net_liquidation_raw),
            available_funds=float(cash_available_raw),
            buying_power=float(buying_power_raw),
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
            params={"includeTags": "true"},
        )
        raw = (data.get("orders") or {}).get("order") or []
        if isinstance(raw, dict):
            raw = [raw]
        open_orders = [o for o in raw if o.get("status") in ("open", "pending")]
        return [_raw_to_order(o) for o in open_orders]

    def get_orders(self, statuses: list[str] | None = None) -> list[Order]:
        """Return all recent orders, optionally filtered to canonical status list.

        Fetches all orders from the broker (Tradier returns up to the last 180 days
        for standard accounts). Used for startup reconciliation.
        """
        data = self._get(
            f"/accounts/{self._account_id}/orders",
            params={"includeTags": "true"},
        )
        raw = (data.get("orders") or {}).get("order") or []
        if isinstance(raw, dict):
            raw = [raw]
        orders = [_raw_to_order(o) for o in raw]
        if statuses:
            orders = [o for o in orders if o.status in statuses]
        return orders

    # ------------------------------------------------------------------ #
    # BIC — Orders                                                         #
    # ------------------------------------------------------------------ #

    def place_order(self, order: OrderRequest) -> OrderResponse:
        """Submit a multi-leg combo order to Tradier."""
        payload: dict = {
            "class": "multileg",
            "symbol": order.symbol,
            "type": _tradier_order_type(order),
            "duration": order.duration,
            "price": round(order.limit_price, 2),
            "quantity": order.quantity,
        }
        if order.tag:
            payload["tag"] = order.tag
        for i, leg in enumerate(order.legs):
            payload[f"option_symbol[{i}]"] = _build_occ_symbol(order.symbol, leg)
            payload[f"side[{i}]"] = _tradier_side(leg.action, leg.option_type)
            payload[f"quantity[{i}]"] = order.quantity

        data = self._post(f"/accounts/{self._account_id}/orders", payload)
        result = data.get("order", {})
        raw_status = result.get("status", "").upper()
        order_id = str(result.get("id", ""))
        if raw_status == "OK":
            return OrderResponse(order_id=order_id, status="ACCEPTED")
        # Extract broker-provided rejection detail when available.
        reason_code = result.get("reason_description", "") or ""
        return OrderResponse(
            order_id=order_id,
            status="REJECTED",
            rejection_reason=_normalize_rejection_reason(reason_code),
            rejection_text=reason_code or None,
        )

    def get_order(self, order_id: str) -> Order:
        """Return current order status from Tradier."""
        data = self._get(f"/accounts/{self._account_id}/orders/{order_id}")
        o = data.get("order", {})
        return _raw_to_order(o, order_id_fallback=order_id)

    def cancel_order(self, order_id: str) -> None:
        """Cancel an open order."""
        self._delete(f"/accounts/{self._account_id}/orders/{order_id}")


# ------------------------------------------------------------------ #
# Module-level helpers                                                #
# ------------------------------------------------------------------ #

# Known rejection reason codes mirrored from tradier_sniffer.REJECTION_REASONS.
_KNOWN_REJECTION_REASONS: frozenset[str] = frozenset({
    "insufficient_buying_power",
    "invalid_price",
    "invalid_quantity",
    "market_closed",
    "duplicate_order",
})


def _normalize_rejection_reason(raw: str) -> str:
    """Map a broker reason_description string to a known normalized code, or 'unknown'."""
    if not raw:
        return "unknown"
    key = raw.lower().replace(" ", "_")
    return key if key in _KNOWN_REJECTION_REASONS else "unknown"


def _raw_to_order(o: dict, order_id_fallback: str = "") -> Order:
    """Convert a Tradier order dict to a canonical BIC Order."""
    raw_status = o.get("status", "").lower()
    bic_status = _STATUS_MAP.get(raw_status, ORDER_STATUS_OPEN)
    avg_fill = o.get("avg_fill_price")
    return Order(
        order_id=str(o.get("id", order_id_fallback)),
        status=bic_status,
        filled_price=float(avg_fill) if avg_fill else None,
        remaining_quantity=int(o.get("remaining_quantity", 0)),
        tag=o.get("tag") or None,
        raw_status=raw_status or None,
    )


def _build_occ_symbol(underlying: str, leg: "OrderLeg") -> str:  # noqa: F821
    """Build the OCC option symbol string expected by Tradier.

    Format: SYMBOL + YYMMDD + C/P + STRIKE(8 digits, x1000).
    Example: SPX260105P05800000
    """
    root = underlying.upper().strip()
    exp = leg.expiration.strftime("%y%m%d")
    cp = "C" if leg.option_type == "CALL" else "P"
    strike_int = int(leg.strike * 1000)
    return f"{root}{exp}{cp}{strike_int:08d}"


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


def _tradier_order_type(order: OrderRequest) -> str:
    """Map BIC OrderRequest to Tradier multi-leg order type."""
    if order.order_type.upper() == "MARKET":
        return "market"

    strategy = order.strategy_type.upper()
    if strategy.endswith("_TP"):
        return "debit"
    if "DEBIT" in strategy:
        return "debit"
    if "CREDIT" in strategy or strategy in {"IRON_CONDOR", "SIC"}:
        return "credit"

    # Conservative fallback for current K9 strategies.
    return "credit"
