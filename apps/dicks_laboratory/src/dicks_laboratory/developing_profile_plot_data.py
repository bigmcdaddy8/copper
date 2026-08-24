"""Pure conversion from an accepted `DevelopingProfileSeries` to plot-ready data.

This module performs no rendering and imports no plotting library. It exists
so the 0R/0S analytical domain models never depend on a visualization
library, and so the mapping from series -> plot points can be tested for
exact `Decimal` equality independent of any rendering boundary. Float
conversion for chart coordinates happens only in the plotting script
(`scripts/dicks_lab_plot_developing_profile.py`), never here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from dicks_laboratory.analysis import AnchorCoverage
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.developing_profile import DevelopingProfileSeries, SliceInterval
from dicks_laboratory.models import InstrumentIdentity
from dicks_laboratory.sessions import AnchorKind


@dataclass(frozen=True)
class DevelopingProfilePlotPoint:
    """One plotted checkpoint; values remain exact `Decimal` (or None)."""

    slice_end_utc: datetime
    terminal_snapshot: bool
    last_included_trade_timestamp: datetime | None

    vwap: Decimal | None
    poc_price: Decimal | None
    val: Decimal | None
    vah: Decimal | None

    cumulative_trade_count: int
    cumulative_volume: Decimal | None


@dataclass(frozen=True)
class DevelopingProfilePlotData:
    """Immutable plot-ready view of one `DevelopingProfileSeries`; no plotting types."""

    dataset_id: UUID
    instrument: InstrumentIdentity
    trading_date: date | None

    anchor_kind: AnchorKind
    anchor_timestamp_utc: datetime

    coverage: AnchorCoverage
    dataset_first_trade_timestamp: datetime
    dataset_last_trade_timestamp: datetime
    dataset_begins_after_anchor: bool
    unobserved_pre_capture_interval: timedelta | None

    source_mode: VwapSourceMode
    slice_interval: SliceInterval

    points: tuple[DevelopingProfilePlotPoint, ...]


def build_developing_profile_plot_data(series: DevelopingProfileSeries) -> DevelopingProfilePlotData:
    """Map an accepted `DevelopingProfileSeries` to plot-ready data, unchanged in value.

    A pure restructuring: every `Decimal`/`datetime` field is carried through
    exactly as computed by the accepted 0R service. No new analytics, no
    interpolation, no float conversion.
    """
    points = tuple(
        DevelopingProfilePlotPoint(
            slice_end_utc=snapshot.slice_end_utc,
            terminal_snapshot=snapshot.terminal_snapshot,
            last_included_trade_timestamp=snapshot.last_included_trade_timestamp,
            vwap=snapshot.vwap,
            poc_price=snapshot.poc_price,
            val=snapshot.val,
            vah=snapshot.vah,
            cumulative_trade_count=snapshot.cumulative_trade_count,
            cumulative_volume=snapshot.cumulative_volume,
        )
        for snapshot in series.snapshots
    )
    return DevelopingProfilePlotData(
        dataset_id=series.dataset_id,
        instrument=series.instrument,
        trading_date=series.trading_date,
        anchor_kind=series.anchor_kind,
        anchor_timestamp_utc=series.anchor_timestamp_utc,
        coverage=series.coverage,
        dataset_first_trade_timestamp=series.dataset_first_trade_timestamp,
        dataset_last_trade_timestamp=series.dataset_last_trade_timestamp,
        dataset_begins_after_anchor=series.dataset_begins_after_anchor,
        unobserved_pre_capture_interval=series.unobserved_pre_capture_interval,
        source_mode=series.source_mode,
        slice_interval=series.slice_interval,
        points=points,
    )
