"""Replay positions and the typed chart snapshot served to the browser (TUTOR_CHART_SNAPSHOT_V1).

The snapshot is cut server-side: it contains only the bars of the requested cutoff's prepared position,
which the Laboratory computed from what it knew at that cutoff. Overlays are named series so later
references / indicators are additional entries, not new response fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from tutor_poc.dev_sessions import INSTRUMENT
from tutor_poc.timeline import BAND_POLICY, ChartPosition, ChartTimeline

SNAPSHOT_SCHEMA = "TUTOR_CHART_SNAPSHOT_V1"


class VwapAnchor(StrEnum):
    """Study-semantic setting. A1 supports only the Globex anchor (computed server-side)."""

    GLOBEX = "GLOBEX"


SUPPORTED_ANCHORS = (VwapAnchor.GLOBEX,)


class ReplayAction(StrEnum):
    PREVIOUS = "previous"
    NEXT = "next"  # adjacent position today; a later "next event" can differ without changing callers
    PLUS_5M = "plus5m"


@dataclass(frozen=True)
class OverlaySpec:
    id: str
    label: str
    group: str  # presentation grouping, e.g. one color/visibility setting for both +/-1 sigma lines
    field: str  # ChartBar attribute


OVERLAYS: tuple[OverlaySpec, ...] = (
    OverlaySpec("vwap", "Globex VWAP", "vwap", "vwap"),
    OverlaySpec("upper_1sd", "+1σ", "sigma1", "upper_1sd"),
    OverlaySpec("lower_1sd", "−1σ", "sigma1", "lower_1sd"),
    OverlaySpec("upper_2sd", "+2σ", "sigma2", "upper_2sd"),
    OverlaySpec("lower_2sd", "−2σ", "sigma2", "lower_2sd"),
)


def position_index(tl: ChartTimeline, cutoff: datetime) -> int:
    for i, p in enumerate(tl.positions):
        if p.cutoff_utc == cutoff:
            return i
    raise KeyError(f"{cutoff.isoformat()} is not a replay position of {tl.trading_date}")


def step(tl: ChartTimeline, index: int, action: ReplayAction) -> int:
    """The new position index, clamped to the session's first/last positions."""
    last = len(tl.positions) - 1
    if action is ReplayAction.PREVIOUS:
        return max(index - 1, 0)
    if action is ReplayAction.NEXT:
        return min(index + 1, last)
    # PLUS_5M: five market minutes later (the grid is 5 minutes, so this is one position today)
    target = tl.positions[index].cutoff_utc.timestamp() + 300
    for i in range(index + 1, last + 1):
        if tl.positions[i].cutoff_utc.timestamp() >= target:
            return i
    return last


def _ts(t: datetime) -> int:
    return int(t.timestamp())


def build_snapshot(tl: ChartTimeline, index: int, anchor: VwapAnchor = VwapAnchor.GLOBEX) -> dict:
    if anchor not in SUPPORTED_ANCHORS:
        raise ValueError(f"unsupported VWAP anchor {anchor}")
    p: ChartPosition = tl.positions[index]
    bars = tuple(b for b in p.bars if b.end_utc <= p.cutoff_utc)  # defensive; positions are already as-of
    return {
        "schema": SNAPSHOT_SCHEMA,
        "instrument": INSTRUMENT,
        "trading_date": tl.trading_date.isoformat(),
        "replay": {
            "cutoff_utc": p.cutoff_utc.isoformat(),
            "market_time_cutoff_utc": p.cutoff_utc.isoformat(),
            "knowledge_time_cutoff_utc": p.cutoff_utc.isoformat(),
            "index": index,
            "count": len(tl.positions),
            "at_start": index == 0,
            "at_end": index == len(tl.positions) - 1,
        },
        "study": {"vwap_anchor": anchor.value, "band_policy": BAND_POLICY, "anchor_utc": tl.anchor_utc.isoformat(),
                  "bar_interval": "5m"},
        "candles": [{"time": _ts(b.start_utc), "end_time": _ts(b.end_utc), "open": float(b.open),
                     "high": float(b.high), "low": float(b.low), "close": float(b.close),
                     "volume": float(b.volume)} for b in bars],
        "series": [{"id": o.id, "label": o.label, "group": o.group, "kind": "line",
                    "points": [{"time": _ts(b.start_utc), "value": float(getattr(b, o.field))} for b in bars]}
                   for o in OVERLAYS],
        "source": {"dataset_id": tl.dataset_id, "database_sha256": tl.database_sha256},
    }
