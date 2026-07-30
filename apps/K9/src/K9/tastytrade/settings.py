"""Tastytrade OAuth configuration for K9's read-only integration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping

_PRODUCTION_BASE_URL = "https://api.tastyworks.com"
_CERTIFICATION_BASE_URL = "https://api.cert.tastyworks.com"
_VALID_ENVIRONMENTS = frozenset({"tastytrade_production", "tastytrade_certification"})
_REQUIRED_VARIABLES = (
    "TW_APP_NAME",
    "TW_CLIENT_ID",
    "TW_CLIENT_SECRET",
    "TW_REFRESH_TOKEN",
    "TW_ACCOUNT_NUMBER",
)


class TastytradeConfigurationError(ValueError):
    """Raised when required Tastytrade settings are absent or invalid."""


@dataclass(frozen=True)
class TastytradeSettings:
    """Configuration required to make authenticated read-only API calls."""

    app_name: str
    client_id: str
    client_secret: str
    refresh_token: str
    account_number: str
    environment: str
    base_url: str

    @property
    def user_agent(self) -> str:
        """Return the API-required product/version user agent."""
        return f"{self.app_name}/1.0"

    @classmethod
    def from_environment(
        cls,
        environment: str,
        values: Mapping[str, str] | None = None,
    ) -> "TastytradeSettings":
        """Load read-only credentials without including their values in errors."""
        if environment not in _VALID_ENVIRONMENTS:
            raise TastytradeConfigurationError(
                f"Unsupported Tastytrade environment {environment!r}. "
                "Must be 'tastytrade_production' or 'tastytrade_certification'."
            )

        source = os.environ if values is None else values
        missing = [name for name in _REQUIRED_VARIABLES if not source.get(name, "").strip()]
        if missing:
            raise TastytradeConfigurationError(
                "Missing required Tastytrade environment variable(s): " + ", ".join(missing)
            )

        base_url = (
            _PRODUCTION_BASE_URL
            if environment == "tastytrade_production"
            else _CERTIFICATION_BASE_URL
        )
        return cls(
            app_name=source["TW_APP_NAME"].strip(),
            client_id=source["TW_CLIENT_ID"].strip(),
            client_secret=source["TW_CLIENT_SECRET"].strip(),
            refresh_token=source["TW_REFRESH_TOKEN"].strip(),
            account_number=source["TW_ACCOUNT_NUMBER"].strip(),
            environment=environment,
            base_url=base_url,
        )