"""Prepared Drysdale setup state at every replay cutoff (0AC-A4): TUTOR_SETUP_TIMELINE_V1.

Nothing here evaluates a setup. Each position is a compact projection of the frozen Laboratory analysis at
that cutoff, produced by the accepted pipeline:

    ReplaySession (dataset + prior day)      the 0AB-B audit inputs (prior day for the static references)
    dry.analyze(session, cutoff=at(T))       DRYSDALE_SETUP_ANALYSIS_V1 as of T (market = knowledge cutoff = T)
        -> project(analysis)                 values copied, never recomputed: analysis state / quality, the
                                             frozen per-bar facts of the latest bars, the context facts, the
                                             latest instance of each family x direction with every condition
                                             status, and every instance whose conditions are all satisfied

No-lookahead: dry.analyze only reads what is known at T (late prints count once received, and can turn a
completed instance back into DEVELOPING: the projection keeps that, it never uses a later value). The full
analysis is ~1 MB per cutoff, so only the projection and the analysis hash (drysdale_sha256) are cached, next
to the chart timeline and outside the repository.
"""
from __future__ import annotations

import gzip
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from dicks_laboratory import drysdale as dry
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.replay import ReplayCutoff
from dicks_laboratory.replay_player import ReplaySession
from dicks_laboratory.tutor_evidence import RECENT_BARS

from tutor_poc.timeline import cache_dir, replay_grid

SCHEMA = "TUTOR_SETUP_TIMELINE_V1"
PROJECTION = "TUTOR_POC_SETUP_PROJECTION_V1"
DONE = (dry.CandidateState.CANDIDATE.value, dry.CandidateState.QUALITY_QUALIFIED.value)


def _t(x: datetime | None) -> str | None:
    return None if x is None else x.isoformat()


def _s(x) -> str | None:
    return None if x is None else str(x)


def _candidate(c: dry.DrysdaleSetupCandidate) -> dict:
    b = c.breakout
    return {"candidate_id": c.candidate_id, "family": c.family.value, "direction": c.direction.value,
            "state": c.state.value, "stage": c.stage.value, "quality": c.quality,
            "can_still_complete": c.can_still_complete, "first_event_utc": _t(c.first_event_utc),
            "completed_at_utc": _t(c.completed_at_utc),
            "conditions": [{"order": k.order, "policy_id": k.policy_id, "status": k.status.value,
                            "satisfied_at_utc": _t(k.satisfied_at_utc), "rule": k.laboratory_rule}
                           for k in c.conditions],
            "breakout": None if b is None else {
                "reached_2sd": b.reached_2sd, "slope_in_breakout_direction": b.slope_in_breakout_direction,
                "completed_closes_beyond": b.completed_closes_beyond, "returned_inside": b.returned_inside},
            "supporting": [[k, v if isinstance(v, bool) or v is None else str(v)] for k, v in c.supporting]}


def project(a: dry.DrysdaleSetupAnalysis, recent: int = RECENT_BARS) -> dict:
    """The compact, citable projection of one frozen analysis. Values are copied, never derived here."""
    x = a.context
    latest = dry.latest_by_family(a)
    return {
        "projection": PROJECTION, "cutoff_utc": a.cutoff.market_time_cutoff_utc.isoformat(),
        "drysdale_sha256": dry.drysdale_sha256(a), "state": a.state.value, "status": a.status,
        "reasons": list(a.reasons), "bands_maturity": a.bands.maturity.value, "complete_bars": len(a.bars),
        "bars": [{"end_utc": _t(b.end_utc), "close": str(b.close), "value_position": b.value_position.value,
                  "close_zone_1sd": b.close_zone_1sd.value, "close_zone_2sd": b.close_zone_2sd.value,
                  "vwap_slope": None if b.vwap_slope is None else b.vwap_slope.value, "vwap_delta": _s(b.vwap_delta)}
                 for b in a.bars[-recent:]],
        "context": None if x is None else {
            "value_position": x.value_position.value, "vwap_slope": None if x.vwap_slope is None else x.vwap_slope.value,
            "vwap_delta": _s(x.vwap_delta), "trend_context": None if x.trend_context is None else x.trend_context.value,
            "higher_high": x.higher_high, "higher_low": x.higher_low, "lower_high": x.lower_high,
            "lower_low": x.lower_low, "consecutive_higher_highs_and_lows": x.consecutive_higher_highs_and_lows,
            "consecutive_lower_highs_and_lows": x.consecutive_lower_highs_and_lows,
            "recent_up_closes": x.recent_up_closes, "recent_down_closes": x.recent_down_closes,
            "current_episode_region": x.current_episode.region,
            "current_episode_closes": x.current_episode.completed_closes,
            "current_episode_lab_acceptance_time_v1": x.current_episode.lab_acceptance_time_v1,
            "session_bars_reaching_2sd": x.session_bars_reaching_2sd,
            "volume_ratio_to_mean": _s(x.volume.ratio_to_mean)},
        "latest": [_candidate(latest[k]) for k in sorted(latest, key=lambda k: (k[0].value, k[1].value))],
        "completed": [{"candidate_id": c.candidate_id, "family": c.family.value, "direction": c.direction.value,
                       "state": c.state.value, "first_event_utc": _t(c.first_event_utc),
                       "completed_at_utc": _t(c.completed_at_utc)} for c in a.candidates if c.state.value in DONE],
        "instances": len(a.candidates)}


@dataclass(frozen=True)
class SetupTimeline:
    trading_date: date
    dataset_id: str
    database_sha256: str
    positions: tuple[dict, ...]  # one projection per chart timeline position (same 5-minute grid)

    def at(self, cutoff: datetime) -> dict | None:
        iso = cutoff.astimezone(timezone.utc).isoformat()
        return next((p for p in self.positions if p["cutoff_utc"] == iso), None)


def build_setup_timeline(database: Path, prior: Path | None, grid: Sequence[datetime] | None = None,
                         progress: Callable[[int, int, datetime], None] | None = None) -> SetupTimeline:
    """Run the frozen analysis at every replay cutoff (slow: one as-of snapshot per cutoff)."""
    session = ReplaySession.load(database, AnalysisProvenance("tutor_poc", False), prior)
    prep = session.replay.current
    cutoffs = tuple(grid) if grid is not None else replay_grid(prep.trading_date)
    out = []
    for i, t in enumerate(cutoffs):
        out.append(project(dry.analyze(session, cutoff=ReplayCutoff.at(t))))
        session._cache.clear()  # snapshots are not reused across cutoffs; the Drysdale pass checkpoint is
        if progress:
            progress(i + 1, len(cutoffs), t)
    return SetupTimeline(prep.trading_date, str(prep.dataset_id), prep.database_sha256, tuple(out))


def cache_path(trading_date: date, database_sha256: str) -> Path:
    return cache_dir() / f"{SCHEMA}_{trading_date}_{database_sha256[:16]}.json.gz"


def save_setup_timeline(st: SetupTimeline, path: Path) -> None:
    doc = {"schema": SCHEMA, "trading_date": st.trading_date.isoformat(), "dataset_id": st.dataset_id,
           "database_sha256": st.database_sha256, "positions": list(st.positions)}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt") as f:
        json.dump(doc, f, separators=(",", ":"))
    tmp.replace(path)


def load_setup_timeline(path: Path) -> SetupTimeline:
    with gzip.open(path, "rt") as f:
        doc = json.load(f)
    if doc["schema"] != SCHEMA:
        raise ValueError(f"unexpected setup timeline schema {doc['schema']!r}")
    return SetupTimeline(date.fromisoformat(doc["trading_date"]), doc["dataset_id"], doc["database_sha256"],
                         tuple(doc["positions"]))
