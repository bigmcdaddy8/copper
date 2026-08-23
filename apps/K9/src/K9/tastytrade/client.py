"""OAuth-authenticated HTTP client for the Tastytrade Open API."""
from __future__ import annotations

from typing import Any

import httpx

from K9.tastytrade.settings import TastytradeSettings

_HTTP_TIMEOUT = 20.0


class TastytradeAPIError(RuntimeError):
    """Raised when Tastytrade returns an invalid or unsuccessful API response."""


class TastytradeClient:
    """OAuth-authenticated client that exposes only token refresh and GET requests."""

    def __init__(self, settings: TastytradeSettings) -> None:
        self._settings = settings
        self._access_token: str | None = None

    def _get_json(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        """Return JSON from a read-only API endpoint, refreshing once after a 401."""
        response = self._get(path, params=params)
        if response.status_code == 401:
            self._access_token = None
            response = self._get(path, params=params)
        self._raise_for_status(response)
        return self._json_object(response)

    def list_accounts(self) -> list[dict[str, Any]]:
        """Return accounts available to the authenticated customer."""
        return self._items(self._get_json("/customers/me/accounts"))

    def get_balances(self) -> dict[str, Any]:
        """Return balances for the configured account."""
        return self._data(self._get_json(self._account_path("balances")))

    def get_balance_snapshots(self) -> list[dict[str, Any]]:
        """Return available balance snapshots for the configured account."""
        return self._items(self._get_json(self._account_path("balance-snapshots")))

    def get_positions(self) -> list[dict[str, Any]]:
        """Return open positions for the configured account."""
        return self._items(self._get_json(self._account_path("positions")))

    def search_orders(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Return orders within an explicit inclusive date range."""
        return self._items(
            self._get_json(
                self._account_path("orders"),
                params={"start-date": start_date, "end-date": end_date, "per-page": "100"},
            )
        )

    def get_order(self, order_id: str) -> dict[str, Any]:
        """Return one order by broker identifier for the configured account."""
        return self._data(self._get_json(self._account_path(f"orders/{order_id}")))

    def get_trade_transactions(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        """Return trade transactions within an explicit inclusive date range."""
        return self._items(
            self._get_json(
                self._account_path("transactions"),
                params={
                    "start-date": start_date,
                    "end-date": end_date,
                    "type": "Trade",
                    "per-page": "250",
                },
            )
        )

    def get_nested_option_chain(self, underlying: str) -> list[dict[str, Any]]:
        """Return nested expiration/strike data for an equity option chain."""
        return self._items(self._get_json(f"/option-chains/{underlying}/nested"))

    def get_quotes(self, instrument_type: str, symbols: list[str]) -> list[dict[str, Any]]:
        """Return a synchronous quote batch for a documented market-data type."""
        allowed_types = {
            "cryptocurrency",
            "equity",
            "equity-option",
            "future",
            "future-option",
            "index",
        }
        if instrument_type not in allowed_types:
            raise ValueError(f"Unsupported Tastytrade quote instrument type: {instrument_type!r}")
        if not symbols:
            return []
        return self._items(
            self._get_json("/market-data/by-type", params={instrument_type: ",".join(symbols)})
        )

    def get_api_quote_token(self) -> dict[str, Any]:
        """Return the short-lived DXLink quote token and endpoint."""
        return self._data(self._get_json("/api-quote-tokens"))

    def list_cryptocurrencies(self) -> list[dict[str, Any]]:
        """Return tradable cryptocurrency instruments and their streamer symbols."""
        return self._items(self._get_json("/instruments/cryptocurrencies"))

    def list_futures(self) -> list[dict[str, Any]]:
        """Return futures instruments and their streamer symbols."""
        return self._items(self._get_json("/instruments/futures"))

    def dry_run_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Validate an order against the account without routing it to a venue."""
        return self._data(self._post_json(self._account_path("orders/dry-run"), order))

    def submit_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Route an order to Tastytrade and return its accepted order payload."""
        return self._data(self._post_json(self._account_path("orders"), order))

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        """Request cancellation of a working order."""
        response = self._delete(self._account_path(f"orders/{order_id}"))
        if response.status_code == 401:
            self._access_token = None
            response = self._delete(self._account_path(f"orders/{order_id}"))
        self._raise_for_status(response)
        return self._data(self._json_object(response))

    def _get(self, path: str, params: dict[str, str] | None = None) -> httpx.Response:
        return httpx.get(
            f"{self._settings.base_url}{path}",
            headers=self._headers(),
            params=params,
            timeout=_HTTP_TIMEOUT,
        )

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._post(path, payload)
        if response.status_code == 401:
            self._access_token = None
            response = self._post(path, payload)
        self._raise_for_status(response)
        return self._json_object(response)

    def _post(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        return httpx.post(
            f"{self._settings.base_url}{path}",
            headers=self._headers(),
            json=payload,
            timeout=_HTTP_TIMEOUT,
        )

    def _delete(self, path: str) -> httpx.Response:
        return httpx.delete(
            f"{self._settings.base_url}{path}",
            headers=self._headers(),
            timeout=_HTTP_TIMEOUT,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._get_access_token()}",
            "User-Agent": self._settings.user_agent,
        }

    def _get_access_token(self) -> str:
        if self._access_token is None:
            self._access_token = self._refresh_access_token()
        return self._access_token

    def _refresh_access_token(self) -> str:
        response = httpx.post(
            f"{self._settings.base_url}/oauth/token",
            headers={"Accept": "application/json", "User-Agent": self._settings.user_agent},
            data={
                "grant_type": "refresh_token",
                "refresh_token": self._settings.refresh_token,
                "client_secret": self._settings.client_secret,
            },
            timeout=_HTTP_TIMEOUT,
        )
        self._raise_for_status(response)
        payload = self._json_object(response)
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise TastytradeAPIError("OAuth token response did not include an access_token.")
        return token

    def _account_path(self, suffix: str) -> str:
        return f"/accounts/{self._settings.account_number}/{suffix}"

    @staticmethod
    def _data(payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise TastytradeAPIError("Tastytrade response did not contain a data object.")
        return data

    @classmethod
    def _items(cls, payload: dict[str, Any]) -> list[dict[str, Any]]:
        items = cls._data(payload).get("items")
        if not isinstance(items, list):
            raise TastytradeAPIError("Tastytrade response did not contain a data.items list.")
        return [item for item in items if isinstance(item, dict)]

    @staticmethod
    def _json_object(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise TastytradeAPIError("Tastytrade response was not valid JSON.") from exc
        if not isinstance(payload, dict):
            raise TastytradeAPIError("Tastytrade response was not a JSON object.")
        return payload

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                payload = response.json()
            except ValueError:
                payload = None
            if isinstance(payload, dict):
                error = payload.get("error")
                if isinstance(error, dict):
                    detail = str(error.get("message") or error.get("code") or "")
            if not detail:
                detail = (response.text or "").strip()
            detail = " ".join(detail.split())
            suffix = f" Tastytrade response: {detail}" if detail else ""
            raise TastytradeAPIError(f"{exc}{suffix}") from exc