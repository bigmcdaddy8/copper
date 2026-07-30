"""Read-only connectivity and market-data diagnostic for Tastytrade."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from K9.market_calendar import is_regular_session_open_ct
from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkCollector, DxLinkSnapshot
from K9.tastytrade.settings import TastytradeSettings

_TZ = ZoneInfo("America/Chicago")


@dataclass
class DiagnosticCheck:
    name: str
    duration_ms: int
    details: dict[str, object]


@dataclass
class TastytradeDiagnosticResult:
    environment: str
    started_at: str
    finished_at: str
    outcome: str
    checks: list[DiagnosticCheck]
    errors: list[str]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def run_diagnostic(
    settings: TastytradeSettings,
    underlyings: list[str],
    client: TastytradeClient | None = None,
    dxlink_collector_factory: Callable[[str, str], DxLinkCollector] = DxLinkCollector,
    now: datetime | None = None,
) -> TastytradeDiagnosticResult:
    """Execute bounded account and market-data checks without mutating broker state."""
    started = datetime.now(tz=timezone.utc)
    now_ct = (now or started).astimezone(_TZ)
    api = client or TastytradeClient(settings)
    checks: list[DiagnosticCheck] = []

    try:
        accounts = _record(checks, "account_discovery", api.list_accounts)
        if not _contains_account(accounts, settings.account_number):
            raise ValueError("Configured Tastytrade account was not returned by account discovery.")
        _record(checks, "balances", api.get_balances, summarize=_balance_summary)
        _record(checks, "positions", api.get_positions, summarize=lambda rows: {"count": len(rows)})
        _record(
            checks,
            "balance_snapshots",
            api.get_balance_snapshots,
            summarize=lambda rows: {"count": len(rows)},
        )
        day = now_ct.date().isoformat()
        _record(
            checks,
            "orders_today",
            lambda: api.search_orders(day, day),
            summarize=lambda rows: {"count": len(rows)},
        )
        _record(
            checks,
            "trade_transactions_today",
            lambda: api.get_trade_transactions(day, day),
            summarize=lambda rows: {"count": len(rows)},
        )

        if not is_regular_session_open_ct(now_ct):
            return _result(settings, started, "SKIPPED_MARKET_CLOSED", checks)

        probes = [
            _collect_probe(api, checks, underlying.upper(), now_ct.date())
            for underlying in underlyings
        ]
        quote_token = _record(checks, "dxlink_token", api.get_api_quote_token, summarize=lambda _: {})
        token = quote_token.get("token")
        url = quote_token.get("dxlink-url")
        if not isinstance(token, str) or not isinstance(url, str):
            raise ValueError("Tastytrade API quote-token response was incomplete.")
        symbols = [probe.streamer_symbol for probe in probes]
        snapshots = _record(
            checks,
            "dxlink_quote_and_greeks",
            lambda: dxlink_collector_factory(url, token).collect(symbols),
            summarize=lambda values: {"symbol_count": len(values)},
        )
        _validate_snapshots(snapshots, probes, started)
        checks.append(DiagnosticCheck("market_data_validation", 0, {"underlying_count": len(probes)}))
    except Exception as exc:
        return _result(settings, started, "ERROR", checks, errors=[str(exc)])

    return _result(settings, started, "OK", checks)


@dataclass(frozen=True)
class _Probe:
    underlying: str
    broker_symbol: str
    streamer_symbol: str


def _collect_probe(
    api: TastytradeClient,
    checks: list[DiagnosticCheck],
    underlying: str,
    today: date,
) -> _Probe:
    quote_type = "index" if underlying in {"SPX", "XSP"} else "equity"
    quotes = _record(
        checks,
        f"{underlying.lower()}_underlying_quote",
        lambda: api.get_quotes(quote_type, [underlying]),
        summarize=lambda rows: {"count": len(rows)},
    )
    if not quotes:
        raise ValueError(f"Tastytrade returned no underlying quote for {underlying}.")
    last = _quote_last(quotes[0])
    chains = _record(
        checks,
        f"{underlying.lower()}_option_chain",
        lambda: api.get_nested_option_chain(underlying),
        summarize=lambda rows: {"chain_count": len(rows)},
    )
    probe = _select_probe(chains, today, last)
    option_quotes = _record(
        checks,
        f"{underlying.lower()}_option_quote",
        lambda: api.get_quotes("equity-option", [probe.broker_symbol]),
        summarize=lambda rows: {"count": len(rows)},
    )
    if not option_quotes:
        raise ValueError(f"Tastytrade returned no option quote for {underlying} probe.")
    _quote_last(option_quotes[0])
    return probe


def _select_probe(chains: list[dict], today: date, underlying_last: float) -> _Probe:
    candidates: list[tuple[date, float, str, str]] = []
    for chain in chains:
        expirations = chain.get("expirations")
        if not isinstance(expirations, list):
            continue
        for expiration in expirations:
            if not isinstance(expiration, dict):
                continue
            try:
                expiration_date = date.fromisoformat(str(expiration["expiration-date"]))
            except (KeyError, TypeError, ValueError):
                continue
            if expiration_date < today:
                continue
            strikes = expiration.get("strikes")
            if not isinstance(strikes, list):
                continue
            for strike in strikes:
                if not isinstance(strike, dict):
                    continue
                try:
                    strike_price = float(strike["strike-price"])
                except (KeyError, TypeError, ValueError):
                    continue
                for symbol_key, streamer_key in (
                    ("call", "call-streamer-symbol"),
                    ("put", "put-streamer-symbol"),
                ):
                    broker_symbol = strike.get(symbol_key)
                    streamer_symbol = strike.get(streamer_key)
                    if isinstance(broker_symbol, str) and isinstance(streamer_symbol, str):
                        candidates.append((expiration_date, strike_price, broker_symbol, streamer_symbol))
    if not candidates:
        raise ValueError("Tastytrade option chain did not contain a valid current expiration probe.")
    expiration, _, broker_symbol, streamer_symbol = min(
        candidates,
        key=lambda row: (row[0], abs(row[1] - underlying_last), row[2]),
    )
    del expiration
    return _Probe(
        underlying="",
        broker_symbol=broker_symbol,
        streamer_symbol=streamer_symbol,
    )


def _validate_snapshots(
    snapshots: dict[str, DxLinkSnapshot], probes: list[_Probe], started: datetime
) -> None:
    for probe in probes:
        snapshot = snapshots.get(probe.streamer_symbol)
        if snapshot is None or not snapshot.is_complete:
            raise ValueError(f"DXLink did not return a complete snapshot for {probe.streamer_symbol!r}.")
        if snapshot.bid is None or snapshot.ask is None or snapshot.bid > snapshot.ask:
            raise ValueError(f"DXLink returned an invalid bid/ask for {probe.streamer_symbol!r}.")
        if snapshot.delta is None or not -1.0 <= snapshot.delta <= 1.0:
            raise ValueError(f"DXLink returned an invalid delta for {probe.streamer_symbol!r}.")
        if snapshot.updated_at is None or (started - snapshot.updated_at).total_seconds() > 60:
            raise ValueError(f"DXLink returned stale market data for {probe.streamer_symbol!r}.")


def _contains_account(accounts: list[dict], account_number: str) -> bool:
    matches = 0
    for record in accounts:
        account = record.get("account")
        if isinstance(account, dict):
            number = account.get("account-number")
        else:
            number = record.get("account-number")
        if number == account_number:
            matches += 1
    return matches == 1


def _balance_summary(balance: dict) -> dict[str, object]:
    return {"has_net_liquidating_value": balance.get("net-liquidating-value") is not None}


def _quote_last(quote: dict) -> float:
    bid = _float(quote.get("bid"))
    ask = _float(quote.get("ask"))
    last = _float_or_none(quote.get("last"))
    return last if last is not None else (bid + ask) / 2.0


def _float(value: object) -> float:
    parsed = _float_or_none(value)
    if parsed is None:
        raise ValueError("Tastytrade quote was missing a required numeric price.")
    return parsed


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record(
    checks: list[DiagnosticCheck],
    name: str,
    call: Callable[[], object],
    summarize: Callable[[object], dict[str, object]] = lambda _: {},
):
    started = time.monotonic()
    result = call()
    checks.append(
        DiagnosticCheck(name, round((time.monotonic() - started) * 1000), summarize(result))
    )
    return result


def _result(
    settings: TastytradeSettings,
    started: datetime,
    outcome: str,
    checks: list[DiagnosticCheck],
    errors: list[str] | None = None,
) -> TastytradeDiagnosticResult:
    return TastytradeDiagnosticResult(
        environment=settings.environment,
        started_at=started.isoformat(),
        finished_at=datetime.now(tz=timezone.utc).isoformat(),
        outcome=outcome,
        checks=checks,
        errors=errors or [],
    )