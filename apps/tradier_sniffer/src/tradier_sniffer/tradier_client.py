import time
import urllib.parse

import httpx

_SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1/"

# Adaptive throttle constants — mirrors trade_hunter client
_TARGET_UTILIZATION = 0.90  # target fraction of available calls to consume
_MIN_DELAY = 0.05           # floor — always a small pause between calls (seconds)
_MAX_DELAY = 2.00           # ceiling — never sleep longer than 2 s
_DEFAULT_DELAY = 0.20       # used before any rate-limit headers have been received

# Known Tradier order statuses and their meanings.
# Source: https://documentation.tradier.com/brokerage-api/trading/get-orders
ORDER_STATUSES: dict[str, str] = {
    "filled": "Order fully filled",
    "partially_filled": "Order partially filled — some shares/contracts executed, remainder still open",
    "open": "Order is open and working at the exchange",
    "expired": "Order expired (Day order past session end, or GTC past expiry date)",
    "canceled": "Order canceled — either by user request or broker action",
    "pending": "Order received by broker, not yet routed to exchange",
    "pending_cancel": "Cancellation request submitted, awaiting exchange confirmation",
    "rejected": "Order rejected by broker or exchange (e.g., insufficient BP, bad price increment)",
    "partially_filled_canceled": "Partially filled, then canceled — filled portion stands",
}

# Known Tradier rejection / cancel reason codes surfaced in order response payloads.
# The 'reason_description' field on a rejected/canceled order may contain these values.
# Source: Tradier API docs + sandbox observation.
REJECTION_REASONS: dict[str, str] = {
    "insufficient_buying_power": "Account lacks sufficient buying power for the order",
    "invalid_price": "Order price violates exchange tick-size rules (e.g., penny price on nickel option)",
    "invalid_quantity": "Order quantity is zero or exceeds position size",
    "market_closed": "Order type not accepted outside regular trading hours",
    "duplicate_order": "A duplicate order was detected",
    "unknown": "Rejection reason not specified by broker",
}


class TradierAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class TradierClient:
    """HTTP client for the Tradier sandbox API.

    Always targets the sandbox base URL — this app is sandbox-only by design.
    Handles Bearer auth, rate-limit throttling, and response normalisation.
    """

    def __init__(self, api_key: str) -> None:
        self._base_url = _SANDBOX_BASE_URL
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        self._ratelimit_available: int | None = None
        self._ratelimit_expiry: int | None = None  # epoch ms
        self._last_computed_delay: float = _DEFAULT_DELAY

    @property
    def rate_limit_state(self) -> tuple[int | None, int | None]:
        return self._ratelimit_available, self._ratelimit_expiry

    @property
    def last_computed_delay(self) -> float:
        return self._last_computed_delay

    def _throttle(self) -> None:
        if self._ratelimit_available is not None and self._ratelimit_available <= 5:
            if self._ratelimit_expiry is not None:
                wake_at = self._ratelimit_expiry / 1000.0 + 1.0
                sleep_for = wake_at - time.time()
                if sleep_for > 0:
                    time.sleep(sleep_for)
            self._ratelimit_available = None
            self._ratelimit_expiry = None

    def _compute_delay(self) -> float:
        if self._ratelimit_available is None:
            self._last_computed_delay = _DEFAULT_DELAY
            return _DEFAULT_DELAY

        if self._ratelimit_expiry is not None:
            remaining_seconds = max(1.0, self._ratelimit_expiry / 1000.0 - time.time())
        else:
            remaining_seconds = 60.0

        safe_calls = self._ratelimit_available * _TARGET_UTILIZATION
        delay = remaining_seconds / max(safe_calls, 1.0)
        self._last_computed_delay = max(_MIN_DELAY, min(_MAX_DELAY, delay))
        return self._last_computed_delay

    def _update_ratelimit(self, headers: httpx.Headers) -> None:
        available = headers.get("X-Ratelimit-Available")
        expiry = headers.get("X-Ratelimit-Expiry")
        if available is not None:
            self._ratelimit_available = int(available)
        if expiry is not None:
            self._ratelimit_expiry = int(expiry)

    def _post(self, path: str, data: dict) -> dict:
        self._throttle()
        # Build form body with literal bracket keys — httpx's data= encoding
        # percent-encodes '[' and ']' which breaks Tradier's leg[N][field] parsing,
        # causing the API to see 0 legs and reject with "number of legs must be > 1".
        body = "&".join(
            f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in data.items()
        )
        try:
            response = self._client.post(
                path,
                content=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as exc:
            raise TradierAPIError(0, str(exc)) from exc

        self._update_ratelimit(response.headers)

        if response.status_code < 200 or response.status_code >= 300:
            raise TradierAPIError(response.status_code, response.text)

        time.sleep(self._compute_delay())
        return response.json()

    def _delete(self, path: str) -> dict:
        self._throttle()
        try:
            response = self._client.delete(path)
        except httpx.RequestError as exc:
            raise TradierAPIError(0, str(exc)) from exc

        self._update_ratelimit(response.headers)

        if response.status_code < 200 or response.status_code >= 300:
            raise TradierAPIError(response.status_code, response.text)

        time.sleep(self._compute_delay())
        return response.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._throttle()
        try:
            response = self._client.get(path, params=params or {})
        except httpx.RequestError as exc:
            raise TradierAPIError(0, str(exc)) from exc

        self._update_ratelimit(response.headers)

        if response.status_code < 200 or response.status_code >= 300:
            raise TradierAPIError(response.status_code, response.text)

        time.sleep(self._compute_delay())
        return response.json()

    def get_user_profile(self) -> dict:
        """Return the user profile for the authenticated account."""
        return self._get("user/profile")

    def get_orders(self, account_id: str) -> list[dict]:
        """Return all orders for the account.

        Tradier returns a bare dict (not a list) when exactly one order exists.
        This method always returns a list.
        """
        data = self._get(f"accounts/{account_id}/orders")
        orders_wrapper = data.get("orders") or {}
        if not isinstance(orders_wrapper, dict):
            return []
        order = orders_wrapper.get("order")
        if order is None:
            return []
        if isinstance(order, dict):
            return [order]
        return list(order)

    def get_positions(self, account_id: str) -> list[dict]:
        """Return all open positions for the account.

        Tradier returns a bare dict (not a list) when exactly one position exists.
        This method always returns a list.
        """
        data = self._get(f"accounts/{account_id}/positions")
        positions_wrapper = data.get("positions") or {}
        if not isinstance(positions_wrapper, dict):
            return []
        position = positions_wrapper.get("position")
        if position is None:
            return []
        if isinstance(position, dict):
            return [position]
        return list(position)

    def get_balances(self, account_id: str) -> dict:
        """Return account balances for the given account."""
        data = self._get(f"accounts/{account_id}/balances")
        return data.get("balances") or {}

    def get_history(self, account_id: str) -> list[dict]:
        """Return account transaction history.

        Tradier returns a bare dict (not a list) when exactly one event exists.
        This method always returns a list.
        """
        data = self._get(f"accounts/{account_id}/history")
        history_wrapper = data.get("history") or {}
        if not isinstance(history_wrapper, dict):
            return []
        event = history_wrapper.get("event")
        if event is None:
            return []
        if isinstance(event, dict):
            return [event]
        return list(event)

    def get_option_expirations(self, symbol: str) -> list[str]:
        """Return sorted list of option expiration dates (YYYY-MM-DD) for symbol."""
        data = self._get("markets/options/expirations", params={"symbol": symbol, "includeAllRoots": "true"})
        expirations = data.get("expirations") or {}
        if not isinstance(expirations, dict):
            return []
        dates = expirations.get("date") or []
        if isinstance(dates, str):
            dates = [dates]
        return sorted(dates)

    def get_option_chain(self, symbol: str, expiration: str, greeks: bool = True) -> list[dict]:
        """Return full option chain for symbol/expiration.

        Tradier returns a bare dict (not a list) when exactly one option exists.
        This method always returns a list.
        """
        params = {"symbol": symbol, "expiration": expiration, "greeks": "true" if greeks else "false"}
        data = self._get("markets/options/chains", params=params)
        options_wrapper = data.get("options") or {}
        if not isinstance(options_wrapper, dict):
            return []
        option = options_wrapper.get("option")
        if option is None:
            return []
        if isinstance(option, dict):
            return [option]
        return list(option)

    def place_multileg_order(
        self,
        account_id: str,
        legs: list[dict],
        price: float,
        underlying: str | None = None,
        duration: str = "day",
        tag: str | None = None,
    ) -> dict:
        """Place a multileg limit order (Iron Condor, spread, etc.).

        Each leg dict must have keys: option_symbol, side, quantity.
        Tradier expects flat indexed keys: option_symbol[N], side[N], quantity[N].
        Returns the raw Tradier order response dict.
        """
        net_type = "credit" if price > 0 else ("debit" if price < 0 else "even")
        data: dict = {
            "class": "multileg",
            "type": net_type,
            "duration": duration,
            "price": f"{abs(price):.2f}",
        }
        if underlying:
            data["symbol"] = underlying
        if tag:
            data["tag"] = tag
        for i, leg in enumerate(legs):
            data[f"option_symbol[{i}]"] = leg["option_symbol"]
            data[f"side[{i}]"] = leg["side"]
            data[f"quantity[{i}]"] = str(leg["quantity"])
        return self._post(f"accounts/{account_id}/orders", data)

    def cancel_order(self, account_id: str, order_id: str) -> dict:
        """Cancel an open order.  Returns the raw Tradier response dict."""
        return self._delete(f"accounts/{account_id}/orders/{order_id}")

    def get_quotes(self, symbols: list[str]) -> list[dict]:
        """Return quote data for the given symbols.

        Tradier returns a bare dict (not a list) when exactly one symbol is queried.
        This method always returns a list.
        """
        data = self._get("markets/quotes", params={"symbols": ",".join(symbols), "greeks": "false"})
        quotes_wrapper = data.get("quotes") or {}
        if not isinstance(quotes_wrapper, dict):
            return []
        quote = quotes_wrapper.get("quote")
        if quote is None:
            return []
        if isinstance(quote, dict):
            return [quote]
        return list(quote)

    def place_single_leg_order(
        self,
        account_id: str,
        option_symbol: str,
        side: str,
        quantity: int,
        order_type: str,
        price: float,
        duration: str = "day",
        tag: str | None = None,
    ) -> dict:
        """Place a single-leg option order (e.g. GTC BTC take-profit).

        Returns the raw Tradier order response dict.
        """
        data: dict = {
            "class": "option",
            "option_symbol": option_symbol,
            "side": side,
            "quantity": str(quantity),
            "type": order_type,
            "duration": duration,
            "price": f"{price:.2f}",
        }
        if tag:
            data["tag"] = tag
        return self._post(f"accounts/{account_id}/orders", data)
