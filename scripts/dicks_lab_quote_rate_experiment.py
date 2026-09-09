"""Phase 0W-5 -- isolated Quote-rate measurement experiment.

Diagnostic-only. Does NOT touch the accepted serious-collector contract, does
NOT persist to any Laboratory SQLite dataset, and does NOT change what
TimeAndSale captures retain. Measures raw DXLink Quote event rate and
approximate payload size only, to inform (not decide) the 0U-deferred
standalone-Quote-retention question. Uses the same K9 credential-resolution
pattern as the production capture scripts.
"""
from __future__ import annotations

import json
import time
from collections import Counter

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkSourceCollector
from K9.tastytrade.settings import TastytradeSettings

app = typer.Typer(add_completion=False)
_ES_STREAMER_SYMBOL = "/ESU26:XCME"


@app.command()
def measure(
    duration_seconds: float = typer.Option(600.0, help="Bounded experiment duration in seconds."),
    include_timesale: bool = typer.Option(True, help="Also subscribe TimeAndSale for a rate comparison."),
) -> None:
    load_dotenv()
    client = TastytradeClient(TastytradeSettings.from_environment("tastytrade_production"))
    token_data = client.get_api_quote_token()
    token, url = token_data.get("token"), token_data.get("dxlink-url")
    if not isinstance(token, str) or not isinstance(url, str):
        raise typer.BadParameter("Tastytrade quote-token response was incomplete.")

    event_types = ("Quote", "TimeAndSale") if include_timesale else ("Quote",)
    counts: Counter[str] = Counter()
    bytes_by_type: Counter[str] = Counter()
    peak_1s: dict[str, int] = {}
    window_start = time.monotonic()
    window_counts: Counter[str] = Counter()

    def on_event(event) -> None:
        nonlocal window_start, window_counts
        counts[event.event_type] += 1
        bytes_by_type[event.event_type] += len(json.dumps(event.fields, default=str))
        window_counts[event.event_type] += 1
        if time.monotonic() - window_start >= 1.0:
            for event_type, count in window_counts.items():
                peak_1s[event_type] = max(peak_1s.get(event_type, 0), count)
            window_counts = Counter()
            window_start = time.monotonic()

    collector = DxLinkSourceCollector(url, token)
    typer.echo(f"Subscribing to {event_types} on {_ES_STREAMER_SYMBOL} for {duration_seconds:.0f}s...")
    started = time.monotonic()
    collector.collect(
        _ES_STREAMER_SYMBOL, event_types, duration_seconds, 10_000_000,
        on_event=on_event, retain_events=False,
    )
    elapsed = time.monotonic() - started

    summary = {
        "elapsed_seconds": round(elapsed, 1),
        "counts": dict(counts),
        "rate_per_second": {k: round(v / elapsed, 3) for k, v in counts.items()},
        "peak_1s_count": peak_1s,
        "approx_bytes": dict(bytes_by_type),
        "approx_bytes_per_event": {
            k: round(bytes_by_type[k] / v, 1) for k, v in counts.items() if v > 0
        },
        "projected_bytes_per_hour": {
            k: round(bytes_by_type[k] / elapsed * 3600, 0) for k in counts
        },
    }
    typer.echo(json.dumps(summary, indent=2))


if __name__ == "__main__":
    app()
