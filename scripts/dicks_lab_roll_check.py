"""0X-A read-only futures contract-roll check (the Human's primary roll tool).

REST metadata only (`list_futures()`); never requests a DXLink quote token and
never changes the production pin. `--metadata-json` replays a saved
`list_futures()` response offline.

  check  -- roll status of the pinned production contract for a trading date
  chain  -- nearby listed contracts for a Laboratory universe root
Exit code reflects production readiness (0X-B): `check` exits 0 for CURRENT /
ROLL_APPROACHING (and a warning-level METADATA_CONFLICT), 1 for ROLL_DUE and
every FAIL state -- exactly when the production preflight would refuse.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from dicks_laboratory.futures_contracts import (
    LABORATORY_UNIVERSE,
    FuturesContract,
    RollSeverity,
    assess_roll,
    discover_chain,
    roll_record_draft,
    upcoming_trading_date,
)
from dicks_laboratory.production_symbol import PINNED_ES_SYMBOL

app = typer.Typer(add_completion=False)
_CT = ZoneInfo("America/Chicago")


def _load_futures(metadata_json: Path | None) -> list[dict] | None:
    if metadata_json is not None:
        data = json.loads(metadata_json.read_text())
        return data if isinstance(data, list) else None
    from dotenv import load_dotenv

    from K9.tastytrade.client import TastytradeClient
    from K9.tastytrade.settings import TastytradeSettings

    load_dotenv(".env")
    client = TastytradeClient(TastytradeSettings.from_environment("tastytrade_production"))
    try:
        return client.list_futures()
    except Exception as exc:  # noqa: BLE001 -- reported as METADATA_UNAVAILABLE
        typer.echo(f"metadata_error={type(exc).__name__}", err=True)
        return None


def _trading_date(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return upcoming_trading_date(datetime.now(tz=timezone.utc))


def _contract_line(c: FuturesContract | None) -> str:
    if c is None:
        return "none"
    return f"{c.broker_symbol}  {c.streamer_symbol}  {c.instrument_id}  expires {c.expiration_date}"


@app.command()
def check(
    trading_date: str | None = typer.Option(None, "--trading-date", help="YYYY-MM-DD futures trading date; default: the upcoming one."),
    pin: str = typer.Option(PINNED_ES_SYMBOL, "--pin", help="Contract to assess; default: the production pin."),
    metadata_json: Path | None = typer.Option(None, "--metadata-json", help="Saved list_futures() JSON (offline)."),
    roll_record_draft_path: Path | None = typer.Option(None, "--roll-record-draft", help="Write a draft roll provenance JSON here."),
) -> None:
    """Roll status of the pinned contract (read-only)."""
    td = _trading_date(trading_date)
    futures = _load_futures(metadata_json)
    a = assess_roll(futures, pin, td)
    typer.echo(f"Product: {a.product}")
    typer.echo(f"Trading date: {td}")
    typer.echo("")
    typer.echo("Pinned:")
    typer.echo(f"  {pin}")
    if a.pinned is not None:
        p = a.pinned
        typer.echo(f"  {p.instrument_id}  streamer {p.streamer_symbol}")
        stops = f" (trading stops {p.stops_trading_at.astimezone(_CT):%Y-%m-%d %H:%M %Z})" if p.stops_trading_at else ""
        typer.echo(f"  expires {p.expiration_date}{stops}")
        typer.echo(f"  tradeable={str(p.tradeable).lower()} closing_only={str(p.closing_only).lower()} "
                   f"tick={p.tick_size} multiplier={p.multiplier}")
    typer.echo("")
    typer.echo("Exchange (CME):")
    if a.exchange is not None:
        typer.echo(f"  customary roll {a.exchange.customary_roll_date}  expiration {a.exchange.expiration_date}  "
                   f"[{a.exchange.source}]")
        typer.echo(f"  warning window from {a.approaching_from}")
    else:
        typer.echo("  unresolved")
    typer.echo("")
    typer.echo("Broker (Tastytrade metadata):")
    typer.echo(f"  active-month       {_contract_line(a.broker_active)}")
    typer.echo(f"  next-active-month  {_contract_line(a.broker_next_active)}")
    typer.echo("")
    typer.echo(f"Exchange successor candidate:\n  {_contract_line(a.candidate)}")
    typer.echo("")
    typer.echo(f"Roll state:\n  {a.state.value} ({a.severity.value})")
    for reason in a.reasons:
        typer.echo(f"  - {reason}")
    typer.echo("")
    typer.echo(f"Recommended production action:\n  {a.recommended_action}")
    readiness = {RollSeverity.OK: "PASS", RollSeverity.WARN: "PASS + WARNING", RollSeverity.FAIL: "FAIL"}[a.severity]
    typer.echo(f"\nProduction readiness (preflight policy):\n  {readiness}")
    typer.echo("")
    typer.echo("Read-only: no quote token requested; the production pin is never changed by this tool.")
    if roll_record_draft_path is not None:
        record = roll_record_draft(a, futures or [], datetime.now(tz=timezone.utc))
        roll_record_draft_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        typer.echo(f"Draft roll record written: {roll_record_draft_path}")
    if a.severity is RollSeverity.FAIL:
        raise typer.Exit(code=1)


@app.command()
def chain(
    root: str = typer.Argument("ES", help=f"Universe root: {', '.join(LABORATORY_UNIVERSE)}."),
    count: int = typer.Option(4, min=1, help="Nearest contracts to show."),
    metadata_json: Path | None = typer.Option(None, "--metadata-json", help="Saved list_futures() JSON (offline)."),
) -> None:
    """Nearby listed contracts for one universe root (read-only)."""
    product = LABORATORY_UNIVERSE.get(root.upper())
    if product is None:
        raise typer.BadParameter(f"{root!r} is not in the Laboratory universe ({', '.join(LABORATORY_UNIVERSE)}).")
    futures = _load_futures(metadata_json)
    if futures is None:
        typer.echo("METADATA_UNAVAILABLE")
        raise typer.Exit(code=1)
    contracts = discover_chain(futures, product.root)
    typer.echo(f"Product: {product.root} -- {product.description} ({product.exchange})")
    typer.echo(f"Listed cycle (policy): {''.join(product.listed_months)}"
               + (f"   micro of {product.standard_root}" if product.standard_root else ""))
    if contracts:
        c0 = contracts[0]
        typer.echo(f"Broker: listed-months {''.join(c0.broker_listed_months) or '?'}  tick {c0.tick_size}  "
                   f"multiplier {c0.multiplier}")
    typer.echo("")
    typer.echo(f"{'symbol':9} {'streamer':15} {'instrument_id':24} {'expires':10}  active next  tradeable closing_only")
    for c in contracts[:count]:
        typer.echo(f"{c.broker_symbol:9} {c.streamer_symbol:15} {c.instrument_id:24} {c.expiration_date}  "
                   f"{'yes' if c.active_month else 'no':6} {'yes' if c.next_active_month else 'no':5} "
                   f"{'yes' if c.tradeable else 'no':9} {'yes' if c.closing_only else 'no'}")
    if not contracts:
        typer.echo("(no listed contracts)")


if __name__ == "__main__":
    app()
