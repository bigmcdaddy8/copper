"""Local Tutor POC API: approved-session discovery, server-cut replay snapshots (0AC-A1), Tutor turns (0AC-A2)."""
from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from functools import cache
from pathlib import Path
from zoneinfo import ZoneInfo

from dicks_laboratory.tutor_evidence import LessonStage
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from tutor_poc import dev_sessions, timeline
from tutor_poc.dev_sessions import INSTRUMENT, DevSession, SealedDateError
from tutor_poc.snapshot import ReplayAction, VwapAnchor, build_snapshot, position_index, step
from tutor_poc.tutor import PROVIDER_ID, FakeTutorProvider, TutorAction, TutorProvider, next_stage, snapshot_evidence

CT = ZoneInfo("America/Chicago")
# 09:00 CT: the whole overnight session plus the first 30 minutes of the cash session are visible,
# seven hours of the session remain hidden for replay.
INITIAL_CUTOFF_CT = time(9, 0)
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def _cached_timeline(s: DevSession) -> timeline.ChartTimeline:
    path = timeline.cache_path(s.trading_date, s.database_sha256)
    if not path.exists():
        raise HTTPException(503, f"{s.trading_date} is not prepared; run `uv run tutor_poc prepare`")
    return timeline.load_timeline(path)


def initial_index(tl: timeline.ChartTimeline) -> int:
    target = datetime.combine(tl.trading_date, INITIAL_CUTOFF_CT, tzinfo=CT)
    return min(range(len(tl.positions)), key=lambda i: abs(tl.positions[i].cutoff_utc - target))


class TutorTurnRequest(BaseModel):
    """One Tutor interaction at one replay position. Closed: no dataset, path or date fields exist."""

    model_config = ConfigDict(extra="forbid")
    action: TutorAction
    replay_cutoff_utc: datetime
    stage: LessonStage = LessonStage.QUESTION  # the lesson stage the client is showing
    turn: int = Field(ge=0)  # client sequence number, echoed for correlation
    text: str | None = Field(default=None, max_length=4000)


def create_app(registry: tuple[DevSession, ...] = dev_sessions.APPROVED,
               load: Callable[[DevSession], timeline.ChartTimeline] = _cached_timeline,
               web_dist: Path | None = WEB_DIST, provider: TutorProvider | None = None) -> FastAPI:
    app = FastAPI(title="Dick's Laboratory Tutor POC", version="0AC-A2")
    provider = provider or FakeTutorProvider()
    load = cache(load)

    def session_for(trading_date: str) -> timeline.ChartTimeline:
        try:
            s = dev_sessions.approved_session(date.fromisoformat(trading_date), registry)
        except (ValueError, SealedDateError) as e:  # SealedDateError is a ValueError
            raise HTTPException(404, str(e)) from e
        return load(s)

    def index_at(tl: timeline.ChartTimeline, cutoff: datetime | str) -> int:
        try:
            return position_index(tl, cutoff if isinstance(cutoff, datetime) else datetime.fromisoformat(cutoff))
        except (ValueError, KeyError) as e:
            raise HTTPException(422, f"invalid replay cutoff: {e}") from e

    @app.get("/api/sessions")
    def sessions():
        shown = dev_sessions.discoverable(registry)
        enabled = [s for s in shown if s.enabled]
        return {"instrument": INSTRUMENT,
                "sessions": [{"trading_date": s.trading_date.isoformat(), "enabled": s.enabled} for s in shown],
                "default": enabled[0].trading_date.isoformat() if enabled else None}

    @app.get("/api/sessions/{trading_date}/replay")
    def replay(trading_date: str):
        tl = session_for(trading_date)
        return {"trading_date": tl.trading_date.isoformat(), "count": len(tl.positions), "step_minutes": 5,
                "first_cutoff_utc": tl.positions[0].cutoff_utc.isoformat(),
                "last_cutoff_utc": tl.positions[-1].cutoff_utc.isoformat(),
                "initial_cutoff_utc": tl.positions[initial_index(tl)].cutoff_utc.isoformat()}

    @app.get("/api/sessions/{trading_date}/snapshot")
    def snapshot(trading_date: str, cutoff: str | None = None, action: ReplayAction | None = None,
                 vwap_anchor: VwapAnchor = VwapAnchor.GLOBEX):
        tl = session_for(trading_date)
        if cutoff is None:
            i = initial_index(tl)
        else:
            i = index_at(tl, cutoff)
        if action is not None:
            i = step(tl, i, action)
        return build_snapshot(tl, i, vwap_anchor)

    @app.get("/api/sessions/{trading_date}/tutor/evidence")
    def tutor_evidence(trading_date: str, cutoff: str):
        tl = session_for(trading_date)
        return snapshot_evidence(tl, index_at(tl, cutoff))

    @app.post("/api/sessions/{trading_date}/tutor/turn")
    def tutor_turn(trading_date: str, req: TutorTurnRequest):
        tl = session_for(trading_date)
        i = index_at(tl, req.replay_cutoff_utc)
        text = (req.text or "").strip()
        if (req.action is TutorAction.MESSAGE) != bool(text):
            raise HTTPException(422, "a message needs non-empty text; other actions take none")
        evidence = snapshot_evidence(tl, i)
        stage = next_stage(req.stage, req.action)
        return {"turn_id": f"t{req.turn}", "turn": req.turn, "role": "tutor", "action": req.action.value,
                "text": provider.reply(req.action, stage, req.turn, text or None, evidence),
                "stage": stage.value, "trading_date": tl.trading_date.isoformat(),
                "replay_cutoff_utc": tl.positions[i].cutoff_utc.isoformat(), "provider": PROVIDER_ID}

    if web_dist is not None and (web_dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=web_dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(web_dist / "index.html")

    return app
