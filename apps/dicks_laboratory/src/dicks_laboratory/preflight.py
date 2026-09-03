"""Pre-arm credential + instrument preflight for long-horizon capture.

0W-2D: establishes only what is safe to establish *before* a run -- OAuth /
REST reachability, the futures endpoint, and display-symbol resolution -- and
deliberately does NOT request a DXLink quote token. `get_api_quote_token()`
returns a token whose ~24h `expires-at` is anchored to first issuance and is
re-served unchanged while still valid (0W-2C), so obtaining it hours/days ahead
of the capture burns its lifetime -- the 0W-2 Attempt-3 KNOWN_GAP root cause.
The quote token is obtained only at real collector startup.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SupportsListFutures(Protocol):
    """The single client capability the safe preflight needs."""

    def list_futures(self) -> list[dict]: ...


@dataclass(frozen=True)
class CredentialPreflightResult:
    """Factual outcome of the pre-arm safe checks. No secrets, only booleans
    and a count."""

    rest_reachable: bool
    futures_endpoint_usable: bool
    futures_count: int
    symbol_resolves: bool
    streamer_symbol_matches: bool

    @property
    def ok(self) -> bool:
        return (
            self.rest_reachable
            and self.futures_endpoint_usable
            and self.symbol_resolves
            and self.streamer_symbol_matches
        )


def run_credential_preflight(
    client: SupportsListFutures,
    display_symbol: str,
    expected_streamer_symbol: str,
) -> CredentialPreflightResult:
    """Prove the run's credentials/instrument without starting the quote-token
    clock.

    A single authenticated ``list_futures()`` call exercises the OAuth refresh,
    REST reachability, and the futures endpoint at once, then the response is
    checked for the expected display -> streamer symbol mapping. This function
    never calls ``get_api_quote_token()``.
    """
    try:
        futures = client.list_futures()
    except Exception:
        return CredentialPreflightResult(
            rest_reachable=False,
            futures_endpoint_usable=False,
            futures_count=0,
            symbol_resolves=False,
            streamer_symbol_matches=False,
        )
    if not isinstance(futures, list):
        return CredentialPreflightResult(
            rest_reachable=True,
            futures_endpoint_usable=False,
            futures_count=0,
            symbol_resolves=False,
            streamer_symbol_matches=False,
        )
    resolved = next(
        (item for item in futures if isinstance(item, dict) and item.get("symbol") == display_symbol),
        None,
    )
    symbol_resolves = isinstance(resolved, dict)
    streamer_symbol_matches = bool(
        symbol_resolves and resolved.get("streamer-symbol") == expected_streamer_symbol
    )
    return CredentialPreflightResult(
        rest_reachable=True,
        futures_endpoint_usable=True,
        futures_count=len(futures),
        symbol_resolves=symbol_resolves,
        streamer_symbol_matches=streamer_symbol_matches,
    )
