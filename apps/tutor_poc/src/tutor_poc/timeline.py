"""Prepared chart timeline: the Laboratory's as-of Globex bars at every 5-minute replay cutoff.

Nothing here calculates market truth. Each position is produced by the accepted Laboratory pipeline:

    prepare_replay                     (one read-only load of the dataset)
    ReplayCutoff.at(T)                 (market cutoff = knowledge cutoff = T; REPLAY_AS_OF_SEMANTICS)
    as_of_evidence(prep, cutoff)       (the effective tape known at T, trades with market time < T)
    drysdale.run_pass / _bars          (VWAP_BANDS_GLOBEX_V1 + BARS_5M_V1: complete bars, each with the
                                        Globex VWAP and sigma as of the bar's last trade)
    DrysdaleCache.usable               (the accepted 0AB-B rule for resuming the pass from an earlier cutoff)

A position therefore contains only what the Laboratory knew at its cutoff, including late-print
behavior. Preparing every cutoff is slow (the as-of tape is rebuilt per cutoff), so the result is
written once to a local cache outside the repository and served from memory.
"""
from __future__ import annotations

import gzip
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from dicks_laboratory import drysdale as dry
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.replay import MarketReplay, ReplayCutoff, as_of_evidence, prepare_replay
from dicks_laboratory.replay_player import ReplaySession
from dicks_laboratory.sessions import AnchorKind, resolve_anchor, session_coverage

SCHEMA = "TUTOR_CHART_TIMELINE_V1"
STEP = timedelta(minutes=5)
BAND_POLICY = dry.GLOBEX_BAND_POLICY


@dataclass(frozen=True)
class ChartBar:
    start_utc: datetime
    end_utc: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    vwap: Decimal  # Globex VWAP as of the bar's last trade
    sigma: Decimal
    upper_1sd: Decimal  # the Laboratory's band levels at the bar's close (LevelTouch.level_at_close)
    lower_1sd: Decimal
    upper_2sd: Decimal
    lower_2sd: Decimal


@dataclass(frozen=True)
class ChartPosition:
    cutoff_utc: datetime
    bars: tuple[ChartBar, ...]  # complete bars known at the cutoff


@dataclass(frozen=True)
class ChartTimeline:
    trading_date: date
    dataset_id: str
    database_sha256: str
    anchor_utc: datetime  # Globex session open (VWAP anchor)
    session_end_utc: datetime
    positions: tuple[ChartPosition, ...]  # ascending cutoffs on the 5-minute grid


def replay_grid(trading_date: date) -> tuple[datetime, ...]:
    """5-minute cutoffs from the first possible complete bar to the session end."""
    anchor = resolve_anchor(AnchorKind.SESSION_OPEN, trading_date).anchor_timestamp_utc
    end = session_coverage((), trading_date).session_end_utc
    n = (end - anchor) // STEP
    return tuple(anchor + k * STEP for k in range(1, n + 1))


def _chart_bar(b: dry.GlobexBar) -> ChartBar:
    lv = {t.level: t.level_at_close for t in b.levels}
    return ChartBar(b.start_utc, b.end_utc, b.open, b.high, b.low, b.close, b.volume, b.vwap, b.sigma,
                    lv[dry.Level.UPPER_1SD], lv[dry.Level.LOWER_1SD], lv[dry.Level.UPPER_2SD], lv[dry.Level.LOWER_2SD])


def build_timeline(database: Path,
                   progress: Callable[[int, int, datetime], None] | None = None) -> ChartTimeline:
    prep = prepare_replay(database)
    # The session only supplies newly_known() to the reuse rule; no snapshot is built, so no provenance is recorded.
    session = ReplaySession(MarketReplay(prep, None, AnalysisProvenance("not-recorded", None)))
    td = prep.trading_date
    anchor = resolve_anchor(AnchorKind.SESSION_OPEN, td).anchor_timestamp_utc
    end = session_coverage((), td).session_end_utc
    reuse = dry.DrysdaleCache()
    grid = replay_grid(td)
    positions = []
    for i, t in enumerate(grid):
        cutoff = ReplayCutoff.at(t)
        trades = as_of_evidence(prep, cutoff).scoped
        acc = dry.run_pass(trades, anchor, cutoff, reuse.usable(session, cutoff))
        reuse.checkpoint = dry._Checkpoint(cutoff, acc)
        bars, _ = dry._bars(acc, cutoff.clock, end)
        positions.append(ChartPosition(t, tuple(_chart_bar(b) for b in bars)))
        if progress:
            progress(i + 1, len(grid), t)
    return ChartTimeline(td, str(prep.dataset_id), prep.database_sha256, anchor, end, tuple(positions))


# --- local cache ------------------------------------------------------------------------------------

def cache_dir() -> Path:
    return Path(os.environ.get("TUTOR_POC_CACHE_DIR", Path.home() / ".cache" / "copper" / "tutor_poc"))


def cache_path(trading_date: date, database_sha256: str) -> Path:
    return cache_dir() / f"{SCHEMA}_{trading_date}_{database_sha256[:16]}.json.gz"


_BAR_FIELDS = ("open", "high", "low", "close", "volume", "vwap", "sigma", "upper_1sd", "lower_1sd", "upper_2sd",
               "lower_2sd")


def save_timeline(tl: ChartTimeline, path: Path) -> None:
    doc = {
        "schema": SCHEMA, "trading_date": tl.trading_date.isoformat(), "dataset_id": tl.dataset_id,
        "database_sha256": tl.database_sha256, "anchor_utc": tl.anchor_utc.isoformat(),
        "session_end_utc": tl.session_end_utc.isoformat(),
        "positions": [{"cutoff_utc": p.cutoff_utc.isoformat(),
                       "bars": [[b.start_utc.isoformat(), b.end_utc.isoformat()]
                                + [str(getattr(b, f)) for f in _BAR_FIELDS] for b in p.bars]}
                      for p in tl.positions]}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(doc, f, separators=(",", ":"))
    tmp.replace(path)


def load_timeline(path: Path) -> ChartTimeline:
    with gzip.open(path, "rt") as f:
        doc = json.load(f)
    if doc["schema"] != SCHEMA:
        raise ValueError(f"unexpected timeline schema {doc['schema']!r}")
    dt = datetime.fromisoformat

    def bar(r):
        return ChartBar(dt(r[0]), dt(r[1]), *(Decimal(x) for x in r[2:]))

    return ChartTimeline(date.fromisoformat(doc["trading_date"]), doc["dataset_id"], doc["database_sha256"],
                         dt(doc["anchor_utc"]), dt(doc["session_end_utc"]),
                         tuple(ChartPosition(dt(p["cutoff_utc"]), tuple(bar(r) for r in p["bars"]))
                               for p in doc["positions"]))
