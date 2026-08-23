"""Complete, known-good synthetic ES trade data for the Phase 0C VWAP proof."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from dicks_laboratory.models import (
    DatasetIdentity,
    DatasetKind,
    InstrumentIdentity,
    InstrumentKind,
    TradeObservation,
)

SYNTHETIC_ES_DATASET = DatasetIdentity(
    dataset_id=UUID("51c7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
    kind=DatasetKind.SYNTHETIC,
    label="phase-0c-complete-es-vwap",
)

ES_SEP_2026 = InstrumentIdentity(
    kind=InstrumentKind.FUTURE,
    exchange="CME",
    root="ES",
    expiration_year=2026,
    expiration_month=9,
)


def synthetic_es_trades() -> tuple[TradeObservation, ...]:
    """Return a fixed, complete synthetic fixture in deterministic dataset order."""
    timestamp = datetime(2026, 8, 21, 14, 47, 32, tzinfo=timezone.utc)
    dataset_id = SYNTHETIC_ES_DATASET.dataset_id
    rows = (
        (1, "6432.00", "2", timestamp),
        (2, "6432.25", "3", timestamp),
        (3, "6432.50", "1", datetime(2026, 8, 21, 14, 47, 33, tzinfo=timezone.utc)),
        (4, "6431.75", "4", datetime(2026, 8, 21, 14, 47, 34, tzinfo=timezone.utc)),
        (5, "6432.75", "2", datetime(2026, 8, 21, 14, 47, 35, tzinfo=timezone.utc)),
        (6, "6432.25", "3", datetime(2026, 8, 21, 14, 47, 36, tzinfo=timezone.utc)),
    )
    return tuple(
        TradeObservation(
            observation_id=UUID(f"51c7d1e4-3c38-4c16-9e04-e6f7c8a7c{sequence:03d}"),
            dataset_id=dataset_id,
            dataset_sequence=sequence,
            instrument=ES_SEP_2026,
            event_timestamp=event_timestamp,
            price=Decimal(price),
            size=Decimal(size),
        )
        for sequence, price, size, event_timestamp in rows
    )