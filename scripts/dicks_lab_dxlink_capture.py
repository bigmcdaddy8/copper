"""Manual bounded DXLink source-event capture for Dick's Laboratory experiments."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkSourceCollector
from K9.tastytrade.settings import TastytradeSettings

app = typer.Typer(add_completion=False)


def _resolve_symbol(client: TastytradeClient, symbol: str, instrument_type: str) -> dict:
    if instrument_type == "crypto":
        instruments = client.list_cryptocurrencies()
    elif instrument_type == "future":
        instruments = client.list_futures()
    else:
        raise ValueError("instrument_type must be 'crypto' or 'future'.")
    for instrument in instruments:
        if instrument.get("symbol") == symbol:
            return instrument
    raise ValueError(f"No {instrument_type} instrument found for {symbol!r}.")


@app.command()
def capture(
    symbol: str = typer.Option(..., help="Tastytrade display symbol, e.g. BTC/USD or /ESU6."),
    instrument_type: str = typer.Option(..., help="crypto or future."),
    duration_seconds: float = typer.Option(60.0, min=1.0, max=600.0),
    max_events: int = typer.Option(500, min=1, max=10_000),
    event_types: str = typer.Option("TimeAndSale,Trade,Quote", help="Comma-separated DXLink event types."),
) -> None:
    """Capture bounded source-shaped DXLink events and print a compact summary."""
    load_dotenv()
    settings = TastytradeSettings.from_environment("tastytrade_production")
    client = TastytradeClient(settings)
    instrument = _resolve_symbol(client, symbol, instrument_type)
    streamer_symbol = instrument.get("streamer-symbol")
    if not isinstance(streamer_symbol, str):
        raise typer.BadParameter("Resolved instrument did not provide a streamer-symbol.")
    token_data = client.get_api_quote_token()
    token = token_data.get("token")
    url = token_data.get("dxlink-url")
    if not isinstance(token, str) or not isinstance(url, str):
        raise typer.BadParameter("Tastytrade quote-token response was incomplete.")
    requested_types = tuple(item.strip() for item in event_types.split(",") if item.strip())
    events = DxLinkSourceCollector(url, token).collect(
        streamer_symbol, requested_types, duration_seconds, max_events
    )
    counts: dict[str, int] = {}
    for event in events:
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
    payload = {
        "captured_at": datetime.now(tz=timezone.utc).isoformat(),
        "symbol": symbol,
        "streamer_symbol": streamer_symbol,
        "instrument_type": instrument_type,
        "requested_event_types": requested_types,
        "event_counts": counts,
        "first_received_at": events[0].received_at.isoformat() if events else None,
        "last_received_at": events[-1].received_at.isoformat() if events else None,
        "representative_events": [
            {
                "event_type": event.event_type,
                "streamer_symbol": event.streamer_symbol,
                "received_at": event.received_at.isoformat(),
                "fields": event.fields,
            }
            for event in events[:3]
        ],
    }
    typer.echo(json.dumps(payload, default=str, indent=2))


if __name__ == "__main__":
    app()