"""Phase 0V — resilient long-horizon ES TimeAndSale collection (Human-invoked).

Runs the serious-collection foundation (`long_running_capture.py`): full
source-field parity for accepted/deferred/rejected events, bounded reconnect
with explicit KNOWN_GAP evidence, one dataset per exact instrument + futures
trading date, and an explicit OPEN/FINALIZED/INTERRUPTED dataset lifecycle.

This does not yet run unbounded/always-on -- `--duration` always bounds the
session, matching the accepted bounded-capture convention. The eventual
always-on `weasel` deployment comes after Phase 0W's soak-test validation.
"""
from __future__ import annotations

import json
from pathlib import Path

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkSourceCollector
from K9.tastytrade.settings import TastytradeSettings
from dicks_laboratory.long_running_capture import (
    DEFAULT_RECONNECT_POLICY,
    InstrumentCaptureSpec,
    LongHorizonCaptureError,
    ReconnectPolicy,
    run_long_horizon_capture,
)
from dicks_laboratory.models import InstrumentIdentity, InstrumentKind

app = typer.Typer(add_completion=False)
_DEFAULT_DATA_DIR = Path("apps/dicks_laboratory/data")
_ES_INSTRUMENT = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9)
_ES_STREAMER_SYMBOL = "/ESU26:XCME"


@app.command()
def collect(
    symbol: str = typer.Option("/ESU6", help="Verified Tastytrade futures display contract."),
    duration: str = typer.Option(
        "3m", help="Bounded session duration, e.g. '3m', '90s', '2h'. Always bounded -- not unbounded/always-on yet."
    ),
    data_dir: Path = typer.Option(_DEFAULT_DATA_DIR, "--data-dir", help="Local runtime data directory (never cloud-synced)."),
    max_reconnect_attempts: int = typer.Option(
        DEFAULT_RECONNECT_POLICY.max_attempts, min=1, help="Bounded reconnect attempts before marking the dataset INTERRUPTED."
    ),
    max_events: int = typer.Option(1_000_000, min=1),
) -> None:
    """Run one bounded, reconnect-capable, serious ES TimeAndSale collection session."""
    if symbol != "/ESU6":
        raise typer.BadParameter("This command supports only the verified /ESU6 display contract.")
    duration_seconds = _parse_duration(duration)

    load_dotenv()
    client = TastytradeClient(TastytradeSettings.from_environment("tastytrade_production"))
    resolved = next((item for item in client.list_futures() if item.get("symbol") == symbol), None)
    if not isinstance(resolved, dict) or resolved.get("streamer-symbol") != _ES_STREAMER_SYMBOL:
        raise typer.BadParameter("Current futures metadata did not resolve /ESU6 to /ESU26:XCME.")
    token_data = client.get_api_quote_token()
    token = token_data.get("token")
    url = token_data.get("dxlink-url")
    if not isinstance(token, str) or not isinstance(url, str):
        raise typer.BadParameter("Tastytrade quote-token response was incomplete.")

    spec = InstrumentCaptureSpec(instrument=_ES_INSTRUMENT, streamer_symbol=_ES_STREAMER_SYMBOL)
    reconnect_policy = ReconnectPolicy(
        backoff_schedule_seconds=DEFAULT_RECONNECT_POLICY.backoff_schedule_seconds,
        max_attempts=max_reconnect_attempts,
    )

    typer.echo(f"Dataset directory: {data_dir}")
    typer.echo(f"Instrument: {_ES_INSTRUMENT.canonical_id}  Streamer symbol: {_ES_STREAMER_SYMBOL}")
    typer.echo(f"Bounded duration: {duration} ({duration_seconds:.0f}s)  Max reconnect attempts: {max_reconnect_attempts}")
    typer.echo("Connecting...")

    try:
        # A Ctrl+C during the collection loop itself is handled inside
        # `run_long_horizon_capture` (treated as a deliberate clean stop ->
        # FINALIZED); this guard only covers an interrupt during setup above,
        # before any dataset exists to finalize.
        result = run_long_horizon_capture(
            data_dir, spec, DxLinkSourceCollector(url, token), duration_seconds, max_events,
            reconnect_policy=reconnect_policy,
        )
    except LongHorizonCaptureError as exc:
        typer.echo(f"Collection error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    except KeyboardInterrupt:
        typer.echo("\nStop requested before any dataset was opened; nothing to finalize.")
        raise typer.Exit(code=0)

    summary = {
        "dataset_id": str(result.dataset_id),
        "database_path": str(result.database_path),
        "instrument": result.instrument.canonical_id,
        "trading_date": result.trading_date.isoformat(),
        "state": result.lifecycle_state.value,
        "accepted_trade_count": result.accepted_trade_count,
        "deferred_event_count": result.deferred_event_count,
        "rejected_record_count": result.rejected_record_count,
        "known_gap_count": result.known_gap_count,
        "reconnect_count": result.reconnect_count,
        "first_source_order": result.first_source_order,
        "last_source_order": result.last_source_order,
        "checksum_sha256": result.checksum_sha256,
        "manifest_path": str(result.manifest_path) if result.manifest_path else None,
    }
    typer.echo(json.dumps(summary, indent=2))
    if result.lifecycle_state.value == "INTERRUPTED":
        raise typer.Exit(code=1)


def _parse_duration(value: str) -> float:
    text = value.strip().lower()
    try:
        if text.endswith("h"):
            return float(text[:-1]) * 3600
        if text.endswith("m"):
            return float(text[:-1]) * 60
        if text.endswith("s"):
            return float(text[:-1])
        return float(text)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid --duration: {value!r}. Use e.g. '3m', '90s', '2h'.") from exc


if __name__ == "__main__":
    app()
