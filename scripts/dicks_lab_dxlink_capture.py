"""Manual bounded DXLink source-event capture for Dick's Laboratory experiments."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkSourceCollector
from K9.tastytrade.settings import TastytradeSettings

app = typer.Typer(add_completion=False)


def _number_integrity(events: tuple[object, ...], field: str) -> dict[str, int]:
    counts = {"finite_positive": 0, "zero": 0, "negative": 0, "non_finite": 0}
    for event in events:
        value = event.fields.get(field)
        try:
            number = float(value)
        except (TypeError, ValueError):
            counts["non_finite"] += 1
            continue
        if not math.isfinite(number):
            counts["non_finite"] += 1
        elif number > 0:
            counts["finite_positive"] += 1
        elif number == 0:
            counts["zero"] += 1
        else:
            counts["negative"] += 1
    return counts


def _time_and_sale_summary(events: tuple[object, ...]) -> dict[str, object] | None:
    time_and_sales = tuple(event for event in events if event.event_type == "TimeAndSale")
    if not time_and_sales:
        return None
    classifications: dict[str, int] = {}
    valid_ticks: dict[str, int] = {}
    source_times: list[object] = []
    indexes: list[object] = []
    for event in time_and_sales:
        classification = str(event.fields.get("type"))
        classifications[classification] = classifications.get(classification, 0) + 1
        valid_tick = str(event.fields.get("validTick"))
        valid_ticks[valid_tick] = valid_ticks.get(valid_tick, 0) + 1
        source_times.append(event.fields.get("time"))
        indexes.append(event.fields.get("index"))
    return {
        "classification_counts": dict(sorted(classifications.items())),
        "valid_tick_counts": dict(sorted(valid_ticks.items())),
        "price_integrity": _number_integrity(time_and_sales, "price"),
        "size_integrity": _number_integrity(time_and_sales, "size"),
        "unique_source_times": len(set(source_times)),
        "duplicate_source_time_events": len(source_times) - len(set(source_times)),
        "index_strictly_increasing_in_capture_order": all(
            isinstance(current, int) and isinstance(previous, int) and current > previous
            for previous, current in zip(indexes, indexes[1:], strict=False)
        ),
    }


def _representative_events(events: tuple[object, ...]) -> list[object]:
    selected = []
    selected_ids: set[int] = set()
    for classification in ("NEW", "CORRECTION", "CANCEL"):
        for event in events:
            if event.event_type == "TimeAndSale" and event.fields.get("type") == classification:
                selected.append(event)
                selected_ids.add(id(event))
                break
    for event in events:
        if event.event_type == "TimeAndSale" and event.fields.get("validTick") is False:
            if id(event) not in selected_ids:
                selected.append(event)
                selected_ids.add(id(event))
            break
    for event in events:
        if id(event) not in selected_ids:
            selected.append(event)
            selected_ids.add(id(event))
        if len(selected) >= 3:
            break
    return selected[:4]


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
        "time_and_sale_summary": _time_and_sale_summary(events),
        "first_received_at": events[0].received_at.isoformat() if events else None,
        "last_received_at": events[-1].received_at.isoformat() if events else None,
        "representative_events": [
            {
                "event_type": event.event_type,
                "streamer_symbol": event.streamer_symbol,
                "received_at": event.received_at.isoformat(),
                "fields": event.fields,
            }
            for event in _representative_events(events)
        ],
    }
    typer.echo(json.dumps(payload, default=str, indent=2))


if __name__ == "__main__":
    app()