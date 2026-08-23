"""Manual bounded live ES TimeAndSale normalization and VWAP experiment."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import typer
from dotenv import load_dotenv

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkSourceCollector
from K9.tastytrade.settings import TastytradeSettings
from dicks_laboratory.audit import audit_dataset
from dicks_laboratory.dxlink_timesales import normalize_dxlink_time_and_sales, source_records_from_events
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, InstrumentIdentity, InstrumentKind
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.vwap import calculate_vwap

app = typer.Typer(add_completion=False)


@app.command()
def capture(
    duration_seconds: float = typer.Option(60.0, min=1.0, max=120.0),
    max_events: int = typer.Option(5000, min=1, max=10_000),
) -> None:
    """Run one bounded non-persistent live /ES TimeAndSale normalization experiment."""
    load_dotenv()
    client = TastytradeClient(TastytradeSettings.from_environment("tastytrade_production"))
    instrument = next(item for item in client.list_futures() if item.get("symbol") == "/ESU6")
    streamer_symbol = instrument["streamer-symbol"]
    token_data = client.get_api_quote_token()
    events = DxLinkSourceCollector(token_data["dxlink-url"], token_data["token"]).collect(
        streamer_symbol, ("TimeAndSale",), duration_seconds, max_events
    )
    dataset = DatasetIdentity(
        dataset_id=uuid4(),
        kind=DatasetKind.HISTORICAL_IMPORT,
        label="bounded-live-es-time-and-sale",
        source_locator="TASTYTRADE_DXLINK:/ESU26:XCME:TimeAndSale",
        source_timezone="UTC epoch milliseconds",
        normalizer_version="phase-0k4-dxlink-timesales-v1",
        capture_started_at=events[0].received_at if events else datetime.now(tz=timezone.utc),
        capture_ended_at=events[-1].received_at if events else datetime.now(tz=timezone.utc),
        origin=DatasetOrigin.AUTHENTIC_SOURCE,
    )
    result = normalize_dxlink_time_and_sales(
        source_records_from_events(events),
        dataset,
        InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 9),
        streamer_symbol,
    )
    with tempfile.TemporaryDirectory(prefix="dicks-lab-es-") as directory:
        store = LaboratoryStore(Path(directory) / "capture.db")
        store.save_dataset(dataset)
        store.save_trade_observations(result.observations)
        store.save_dxlink_time_and_sale_provenance(result.provenance)
        store.save_rejections(result.rejected)
        store.close()
        reopened = LaboratoryStore(Path(directory) / "capture.db")
        trades = reopened.load_trade_observations(dataset.dataset_id)
        provenance = reopened.load_dxlink_time_and_sale_provenance(dataset.dataset_id)
        audit = audit_dataset(reopened, dataset.dataset_id)
        total_volume = sum((trade.size for trade in trades), start=0)
        total_price_volume = sum((trade.price * trade.size for trade in trades), start=0)
        payload = {
            "dataset_id": str(dataset.dataset_id),
            "streamer_symbol": streamer_symbol,
            "source_events": len(events),
            "accepted_trades": len(trades),
            "rejected_events": len(result.rejected),
            "deferred_events": len(result.deferred),
            "first_event_timestamp": trades[0].event_timestamp.isoformat() if trades else None,
            "last_event_timestamp": trades[-1].event_timestamp.isoformat() if trades else None,
            "total_volume": str(total_volume),
            "total_price_volume": str(total_price_volume),
            "vwap": str(calculate_vwap(trades)) if trades else None,
            "provenance_count": len(provenance),
            "audit": {
                "origin": audit.dataset.origin,
                "instrument_ids": audit.instrument_ids,
                "accepted_trade_count": audit.accepted_trade_count,
                "rejected_record_count": audit.rejected_record_count,
                "known_gap_count": audit.known_gap_count,
                "suspected_gap_count": audit.suspected_gap_count,
            },
        }
        reopened.close()
    typer.echo(json.dumps(payload, default=str, indent=2))


if __name__ == "__main__":
    app()