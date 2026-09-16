"""Generalized ES quarterly-contract resolution and validation (0W-4B).

Before 0W-4B the collector accepted exactly one literal symbol (`/ESU6`) and
rejected everything else outright. That is unsafe once the pinned contract
needs to change (e.g. after a roll/expiration): it forces an ad hoc string
edit with no structural validation. This module generalizes the check to any
recognized ES quarterly contract while still authoritatively verifying it
against live Tastytrade futures metadata -- never DXLink, so this never
starts a quote-token's lifetime clock (0W-2D invariant).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from dicks_laboratory.models import InstrumentIdentity, InstrumentKind

# CME quarterly futures month codes. ES only ever lists quarterlies.
_QUARTERLY_MONTH_CODES = {"H": 3, "M": 6, "U": 9, "Z": 12}
_SYMBOL_PATTERN = re.compile(r"^/ES([HMUZ])(\d)$")


class EsContractResolutionError(ValueError):
    """A requested symbol is not a valid, listed, tradeable ES quarterly contract."""


class SupportsListFutures(Protocol):
    def list_futures(self) -> list[dict]: ...


@dataclass(frozen=True)
class ResolvedEsContract:
    """A requested ES symbol, verified against live futures metadata."""

    display_symbol: str
    streamer_symbol: str
    instrument: InstrumentIdentity
    expiration_date: str


def expected_streamer_symbol(display_symbol: str) -> str:
    """Derive the expected DXLink streamer symbol for an ES quarterly display
    symbol, e.g. `/ESZ6` -> `/ESZ26:XCME`.

    Assumes a 2020s-decade single-digit year, matching Tastytrade's current
    display-symbol convention -- true for every contract this Laboratory can
    pin in the foreseeable operational horizon. Actual identity/provenance
    always comes from verified metadata (`resolve_es_contract`), never from
    this assumption alone.
    """
    match = _SYMBOL_PATTERN.match(display_symbol)
    if match is None:
        raise EsContractResolutionError(
            f"{display_symbol!r} is not a recognized ES quarterly contract symbol "
            "(expected /ES[HMUZ]<digit>, e.g. /ESZ6)."
        )
    month_code, year_digit = match.groups()
    return f"/ES{month_code}2{year_digit}:XCME"


def resolve_es_contract(client: SupportsListFutures, requested_symbol: str) -> ResolvedEsContract:
    """Verify `requested_symbol` is a listed, tradeable ES quarterly contract
    and return its authoritative streamer symbol and instrument identity.

    Rejects: malformed symbols, non-ES products, unresolved/unlisted symbols,
    untradeable contracts, and streamer-symbol mismatches. Uses only
    `list_futures()` -- a REST metadata call, never a DXLink quote token.
    """
    match = _SYMBOL_PATTERN.match(requested_symbol)
    if match is None:
        raise EsContractResolutionError(
            f"{requested_symbol!r} is not a recognized ES quarterly contract symbol "
            "(expected /ES[HMUZ]<digit>, e.g. /ESZ6)."
        )
    month = _QUARTERLY_MONTH_CODES[match.group(1)]
    expected_streamer = expected_streamer_symbol(requested_symbol)

    futures = client.list_futures()
    if not isinstance(futures, list):
        raise EsContractResolutionError("Futures metadata endpoint did not return a list.")
    resolved = next(
        (item for item in futures if isinstance(item, dict) and item.get("symbol") == requested_symbol),
        None,
    )
    if resolved is None:
        raise EsContractResolutionError(f"{requested_symbol!r} did not resolve via futures metadata.")
    if resolved.get("product-code") != "ES":
        raise EsContractResolutionError(
            f"{requested_symbol!r} resolved to product-code {resolved.get('product-code')!r}, not 'ES'."
        )
    if not resolved.get("is-tradeable", False):
        raise EsContractResolutionError(f"{requested_symbol!r} is not currently tradeable/listed.")
    streamer_symbol = resolved.get("streamer-symbol")
    if streamer_symbol != expected_streamer:
        raise EsContractResolutionError(
            f"{requested_symbol!r} resolved to streamer symbol {streamer_symbol!r}, "
            f"expected {expected_streamer!r}."
        )
    expiration_date = resolved.get("expiration-date")
    if not isinstance(expiration_date, str) or len(expiration_date) < 4 or not expiration_date[:4].isdigit():
        raise EsContractResolutionError(f"{requested_symbol!r} metadata is missing a usable expiration-date.")
    year = int(expiration_date[:4])

    instrument = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", year, month)
    return ResolvedEsContract(
        display_symbol=requested_symbol,
        streamer_symbol=streamer_symbol,
        instrument=instrument,
        expiration_date=expiration_date,
    )
