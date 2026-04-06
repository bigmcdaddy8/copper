import time

import httpx

_PRODUCTION_BASE_URL = "https://api.tradier.com/v1/"
_SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1/"

# Adaptive throttle constants
_TARGET_UTILIZATION = 0.90  # target fraction of available calls to consume
_MIN_DELAY = 0.05           # floor — always a small pause between calls (seconds)
_MAX_DELAY = 2.00           # ceiling — never sleep longer than 2 s
_DEFAULT_DELAY = 0.20       # used before any rate-limit headers have been received


class TradierAPIError(Exception):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"HTTP {status_code}: {message}")
        self.status_code = status_code
        self.message = message


class TradierClient:
    def __init__(
        self,
        api_key: str,
        sandbox: bool = False,
    ) -> None:
        self._base_url = _SANDBOX_BASE_URL if sandbox else _PRODUCTION_BASE_URL
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
            timeout=30.0,
        )
        # Rate-limit state from response headers
        self._ratelimit_available: int | None = None
        self._ratelimit_expiry: int | None = None  # epoch ms
        self._last_computed_delay: float = _DEFAULT_DELAY

    @property
    def rate_limit_state(self) -> tuple[int | None, int | None]:
        """Return (available, expiry_ms) from the most recent response headers."""
        return self._ratelimit_available, self._ratelimit_expiry

    @property
    def last_computed_delay(self) -> float:
        """Return the inter-request delay computed after the most recent API call."""
        return self._last_computed_delay

    def _throttle(self) -> None:
        """Sleep before a request if the rate-limit window is nearly exhausted."""
        if self._ratelimit_available is not None and self._ratelimit_available <= 5:
            if self._ratelimit_expiry is not None:
                wake_at = self._ratelimit_expiry / 1000.0 + 1.0
                sleep_for = wake_at - time.time()
                if sleep_for > 0:
                    time.sleep(sleep_for)
            # Reset stored state after sleeping
            self._ratelimit_available = None
            self._ratelimit_expiry = None

    def _compute_delay(self) -> float:
        """Return the inter-request sleep duration based on current rate-limit state.

        Spreads remaining calls evenly across the remaining window at TARGET_UTILIZATION,
        clamped to [MIN_DELAY, MAX_DELAY].  Returns DEFAULT_DELAY before any headers seen.
        """
        if self._ratelimit_available is None:
            self._last_computed_delay = _DEFAULT_DELAY
            return _DEFAULT_DELAY

        if self._ratelimit_expiry is not None:
            remaining_seconds = max(1.0, self._ratelimit_expiry / 1000.0 - time.time())
        else:
            remaining_seconds = 60.0  # assumed window if header absent

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

    def _get(self, path: str, params: dict) -> dict:
        self._throttle()
        try:
            response = self._client.get(path, params=params)
        except httpx.RequestError as exc:
            raise TradierAPIError(0, str(exc)) from exc

        self._update_ratelimit(response.headers)

        if response.status_code < 200 or response.status_code >= 300:
            raise TradierAPIError(response.status_code, response.text)

        time.sleep(self._compute_delay())
        return response.json()

    def get_option_expirations(self, symbol: str) -> list[str]:
        """Return expiration date strings ("YYYY-MM-DD") for the given symbol.

        Only monthly expirations are requested (includeAllRoots=false, strikes=false).
        Returns [] if no expirations are available.
        """
        data = self._get(
            "markets/options/expirations",
            {"symbol": symbol, "includeAllRoots": "false", "strikes": "false"},
        )
        expirations = data.get("expirations") or {}
        dates = expirations.get("date") or []
        if isinstance(dates, str):
            dates = [dates]
        return dates

    def get_last_price(self, symbol: str) -> float:
        """Return the current last trade price for the underlying symbol.

        Calls GET /markets/quotes?symbols=<symbol>.
        Raises TradierAPIError on non-2xx responses or if last price is absent.
        """
        data = self._get("markets/quotes", {"symbols": symbol})
        try:
            last = data["quotes"]["quote"]["last"]
        except (KeyError, TypeError):
            raise TradierAPIError(0, f"no last price returned for {symbol}")
        if last is None:
            raise TradierAPIError(0, f"no last price returned for {symbol}")
        return float(last)

    def get_option_chain(self, symbol: str, expiration: str) -> list[dict]:
        """Return option contracts for symbol on the given expiration date.

        Each dict contains at minimum: strike, option_type, delta, bid, ask,
        open_interest, last.
        Returns [] if no contracts are available.
        """
        data = self._get(
            "markets/options/chains",
            {"symbol": symbol, "expiration": expiration, "greeks": "true"},
        )
        options = data.get("options") or {}
        option_list = options.get("option") or []
        if isinstance(option_list, dict):
            option_list = [option_list]
        # Tradier nests greeks under a "greeks" sub-object; flatten to top level
        # so callers can read delta/gamma/etc. directly from the contract dict.
        for contract in option_list:
            greeks = contract.pop("greeks", None) or {}
            for k, v in greeks.items():
                contract.setdefault(k, v)
        return option_list
