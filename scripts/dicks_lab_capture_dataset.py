"""Create one durable, bounded live ES TimeAndSale study dataset."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkSourceCollector
from K9.tastytrade.settings import TastytradeSettings
from dicks_laboratory.live_capture import capture_es_timesales_dataset, effective_vwap

app = typer.Typer(add_completion=False)
_DATA_DIR = Path("apps/dicks_laboratory/data")


@app.command()
def capture(
    symbol: str = typer.Option("/ESU6", help="Verified Tastytrade futures display contract."),
    duration_minutes: float = typer.Option(15.0, min=0.1, max=30.0),
    max_events: int = typer.Option(25_000, min=1, max=100_000),
) -> None:
    """Capture one bounded durable ES TimeAndSale dataset and print factual results."""
    if symbol != "/ESU6":
        raise typer.BadParameter("Phase 0L supports only the verified /ESU6 display contract.")
    load_dotenv()
    client = TastytradeClient(TastytradeSettings.from_environment("tastytrade_production"))
    resolved = next((item for item in client.list_futures() if item.get("symbol") == symbol), None)
    if not isinstance(resolved, dict) or resolved.get("streamer-symbol") != "/ESU26:XCME":
        raise typer.BadParameter("Current futures metadata did not resolve /ESU6 to /ESU26:XCME.")
    token_data = client.get_api_quote_token()
    token = token_data.get("token")
    url = token_data.get("dxlink-url")
    if not isinstance(token, str) or not isinstance(url, str):
        raise typer.BadParameter("Tastytrade quote-token response was incomplete.")
    started = datetime.now(tz=timezone.utc)
    filename = f"es_{started.strftime('%Y%m%dT%H%M%SZ')}_{started.microsecond:06d}.sqlite3"
    result = capture_es_timesales_dataset(
        _DATA_DIR / filename,
        DxLinkSourceCollector(url, token),
        duration_minutes * 60,
        max_events,
    )
    payload = {
        "dataset_id": str(result.dataset_id),
        "database_path": str(result.database_path),
        "display_symbol": symbol,
        "streamer_symbol": "/ESU26:XCME",
        "canonical_instrument": "FUTURE:CME:ES:2026-09",
        "requested_duration_seconds": result.requested_duration_seconds,
        "capture_started_at": result.capture_started_at.isoformat(),
        "capture_ended_at": result.capture_ended_at.isoformat(),
        "source_event_count": result.source_event_count,
        "classification_counts": result.classification_counts,
        "accepted_trade_count": result.accepted_trade_count,
        "deferred_event_count": result.deferred_event_count,
        "rejection_count": result.rejection_count,
        "total_accepted_volume": str(result.total_accepted_volume),
        "canonical_new_only_vwap": str(result.canonical_vwap) if result.canonical_vwap else None,
        "effective_trade_count": len(result.effective_tape.effective_trades),
        "applied_corrections": result.effective_tape.applied_correction_count,
        "applied_cancels": result.effective_tape.applied_cancel_count,
        "effective_vwap": str(effective_vwap(result.effective_tape)) if effective_vwap(result.effective_tape) else None,
        "reconstruction_anomalies": [anomaly.reason for anomaly in result.effective_tape.anomalies],
        "known_gap_count": result.audit.known_gap_count,
        "suspected_gap_count": result.audit.suspected_gap_count,
        "lifecycle_counts": result.audit.lifecycle_counts,
    }
    typer.echo(json.dumps(payload, default=str, indent=2))


if __name__ == "__main__":
    app()