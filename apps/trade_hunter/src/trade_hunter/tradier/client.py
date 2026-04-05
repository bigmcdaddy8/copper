import time

import httpx

_PRODUCTION_BASE_URL = "https://api.tradier.com/v1/"
_SANDBOX_BASE_URL = "https://sandbox.tradier.com/v1/"


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
        request_delay: float = 0.5,
    ) -> None:
        self._base_url = _SANDBOX_BASE_URL if sandbox else _PRODUCTION_BASE_URL
        self._request_delay = request_delay
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

        if self._request_delay > 0:
            time.sleep(self._request_delay)
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
        return option_list
