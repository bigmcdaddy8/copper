"""Interactive, read-only Tastytrade option-chain table support."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable
from zoneinfo import ZoneInfo

from rich.console import Console
from rich.table import Table

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkCollector, DxLinkSnapshot
from K9.tastytrade.settings import TastytradeSettings

_TZ = ZoneInfo("America/Chicago")
_TICKER_PATTERN = re.compile(r"[A-Z0-9/]+")
_DEFAULT_REFRESH_SECONDS = 30
_MIN_REFRESH_SECONDS = 15


@dataclass(frozen=True)
class ChainContract:
    strike: float
    call_streamer_symbol: str
    put_streamer_symbol: str


def validate_chain_parameters(ticker: str, strikes: int, dte: int, refresh_seconds: int) -> str:
    """Return a normalized ticker or raise ValueError for an invalid parameter."""
    normalized = ticker.strip().upper()
    if not normalized or not _TICKER_PATTERN.fullmatch(normalized):
        raise ValueError("ticker must contain only letters, digits, or '/'.")
    if strikes < 0:
        raise ValueError("strikes must be zero or greater.")
    if dte < 0:
        raise ValueError("dte must be zero or greater.")
    if refresh_seconds < _MIN_REFRESH_SECONDS:
        raise ValueError(f"refresh-seconds must be at least {_MIN_REFRESH_SECONDS}.")
    return normalized


def resolve_expiration(today: date, dte: int) -> date:
    """Resolve an exact calendar-day expiration from a DTE offset."""
    return date.fromordinal(today.toordinal() + dte)


def select_strike_window(
    chains: list[dict], expiration: date, underlying_last: float, strikes: int
) -> list[ChainContract]:
    """Return ATM plus *strikes* rows above and below for the requested expiration."""
    contracts: list[ChainContract] = []
    for chain in chains:
        expirations = chain.get("expirations")
        if not isinstance(expirations, list):
            continue
        for raw_expiration in expirations:
            if not isinstance(raw_expiration, dict):
                continue
            if raw_expiration.get("expiration-date") != expiration.isoformat():
                continue
            raw_strikes = raw_expiration.get("strikes")
            if not isinstance(raw_strikes, list):
                continue
            for raw_strike in raw_strikes:
                if not isinstance(raw_strike, dict):
                    continue
                try:
                    strike = float(raw_strike["strike-price"])
                except (KeyError, TypeError, ValueError):
                    continue
                call_symbol = raw_strike.get("call-streamer-symbol")
                put_symbol = raw_strike.get("put-streamer-symbol")
                if isinstance(call_symbol, str) and isinstance(put_symbol, str):
                    contracts.append(ChainContract(strike, call_symbol, put_symbol))

    contracts.sort(key=lambda contract: contract.strike)
    if not contracts:
        raise ValueError(f"No option chain found for expiration {expiration.isoformat()}.")
    atm_index = min(
        range(len(contracts)), key=lambda index: abs(contracts[index].strike - underlying_last)
    )
    return contracts[max(0, atm_index - strikes) : atm_index + strikes + 1]


def fetch_chain_snapshot(
    settings: TastytradeSettings,
    ticker: str,
    strikes: int,
    dte: int,
    client: TastytradeClient | None = None,
    dxlink_collector_factory: Callable[[str, str], DxLinkCollector] = DxLinkCollector,
    now: datetime | None = None,
) -> tuple[float, date, list[ChainContract], dict[str, DxLinkSnapshot]]:
    """Fetch one read-only chain snapshot for terminal rendering."""
    api = client or TastytradeClient(settings)
    now_ct = (now or datetime.now(tz=_TZ)).astimezone(_TZ)
    expiration = resolve_expiration(now_ct.date(), dte)
    quote_type = "index" if ticker in {"SPX", "XSP"} else "equity"
    quotes = api.get_quotes(quote_type, [ticker])
    if not quotes:
        raise ValueError(f"No underlying quote returned for {ticker}.")
    underlying_last = _quote_last(quotes[0])
    window = select_strike_window(
        api.get_nested_option_chain(ticker), expiration, underlying_last, strikes
    )
    quote_token = api.get_api_quote_token()
    token = quote_token.get("token")
    url = quote_token.get("dxlink-url")
    if not isinstance(token, str) or not isinstance(url, str):
        raise ValueError("Tastytrade API quote-token response was incomplete.")
    symbols = [symbol for contract in window for symbol in (contract.call_streamer_symbol, contract.put_streamer_symbol)]
    snapshots = dxlink_collector_factory(url, token).collect(symbols)
    return underlying_last, expiration, window, snapshots


def render_chain_table(
    console: Console,
    ticker: str,
    underlying_last: float,
    expiration: date,
    contracts: list[ChainContract],
    snapshots: dict[str, DxLinkSnapshot],
    previous_prices: dict[str, dict[str, float | None]] | None = None,
    refresh_seconds: int = _DEFAULT_REFRESH_SECONDS,
) -> None:
    """Render a call/put option chain in the requested column order."""
    table = Table(
        title=f"{ticker} {expiration.isoformat()} | Underlying {underlying_last:.2f}",
        show_lines=False,
    )
    for column in (
        "CALL IV",
        "CALL OI",
        "CALL Last",
        "CALL Delta",
        "CALL Bid",
        "CALL Ask",
        "Strike",
        "PUT Bid",
        "PUT Ask",
        "PUT Delta",
        "PUT Last",
        "PUT OI",
        "PUT IV",
    ):
        table.add_column(column, justify="right")

    previous_prices = previous_prices or {}
    divider_after = _divider_index(contracts, underlying_last)
    for index, contract in enumerate(contracts):
        call = snapshots.get(contract.call_streamer_symbol)
        put = snapshots.get(contract.put_streamer_symbol)
        call_previous = previous_prices.get(contract.call_streamer_symbol, {})
        put_previous = previous_prices.get(contract.put_streamer_symbol, {})
        table.add_row(
            _percent(call.volatility if call else None),
            _integer(call.open_interest if call else None),
            _price_change(call.last_price if call else None, call_previous.get("last")),
            _decimal(call.delta if call else None),
            _price_change(call.bid if call else None, call_previous.get("bid")),
            _price_change(call.ask if call else None, call_previous.get("ask")),
            f"{contract.strike:.2f}",
            _price_change(put.bid if put else None, put_previous.get("bid")),
            _price_change(put.ask if put else None, put_previous.get("ask")),
            _decimal(put.delta if put else None),
            _price_change(put.last_price if put else None, put_previous.get("last")),
            _integer(put.open_interest if put else None),
            _percent(put.volatility if put else None),
        )
        if index == divider_after:
            table.add_section()
    console.print(table)
    console.print(
        f"[dim]ATM divider follows the {underlying_last:.2f} underlying price. "
        f"Refreshes every {refresh_seconds}s. Press Ctrl+C to exit.[/dim]"
    )


def run_interactive_chain(
    settings: TastytradeSettings,
    ticker: str,
    strikes: int,
    dte: int,
    refresh_seconds: int,
    console: Console,
) -> None:
    """Refresh an option chain until interrupted by the user."""
    client = TastytradeClient(settings)
    previous_prices: dict[str, dict[str, float | None]] = {}
    while True:
        underlying_last, expiration, contracts, snapshots = fetch_chain_snapshot(
            settings, ticker, strikes, dte, client=client
        )
        console.clear()
        render_chain_table(
            console,
            ticker,
            underlying_last,
            expiration,
            contracts,
            snapshots,
            previous_prices,
            refresh_seconds,
        )
        previous_prices = _snapshot_prices(snapshots)
        time.sleep(refresh_seconds)


def _quote_last(quote: dict) -> float:
    for key in ("last", "mark", "mid"):
        value = _float_or_none(quote.get(key))
        if value is not None:
            return value
    bid = _float_or_none(quote.get("bid"))
    ask = _float_or_none(quote.get("ask"))
    if bid is not None and ask is not None:
        return (bid + ask) / 2.0
    raise ValueError("Underlying quote was missing numeric last, mark, mid, and bid/ask prices.")


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _price(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _price_change(value: float | None, previous: float | None) -> str:
    text = _price(value)
    if value is None or previous is None or value == previous:
        return text
    color = "green" if value > previous else "red"
    return f"[{color}]{text}[/{color}]"


def _decimal(value: float | None) -> str:
    return "-" if value is None else f"{value:.3f}"


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.2%}"


def _integer(value: float | None) -> str:
    return "-" if value is None else f"{value:,.0f}"


def _divider_index(contracts: list[ChainContract], underlying_last: float) -> int:
    """Return the row after which the ATM divider belongs."""
    at_or_below = [index for index, contract in enumerate(contracts) if contract.strike <= underlying_last]
    return at_or_below[-1] if at_or_below else -1


def _snapshot_prices(snapshots: dict[str, DxLinkSnapshot]) -> dict[str, dict[str, float | None]]:
    return {
        symbol: {"last": snapshot.last_price, "bid": snapshot.bid, "ask": snapshot.ask}
        for symbol, snapshot in snapshots.items()
    }