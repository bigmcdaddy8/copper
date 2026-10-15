"""tutor_poc: prepare approved development sessions and serve the local Tutor POC."""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import typer

from tutor_poc import dev_sessions, timeline

app = typer.Typer(help="AI Tutor UX POC (0AC-A1/A2): local chart, replay and fake Tutor shell.", no_args_is_help=True)

DEFAULT_PORT = 8765


def _database(s: dev_sessions.DevSession) -> Path:
    return dev_sessions.corpus_dir() / s.database


def ensure_prepared(s: dev_sessions.DevSession, echo=typer.echo) -> Path:
    """The cached timeline for an approved session, building it (slow, once) when missing."""
    path = timeline.cache_path(s.trading_date, s.database_sha256)
    if path.exists():
        return path
    echo(f"Preparing {s.trading_date} (one time; roughly 30 minutes, ~4 GB RAM) -> {path}")
    t0 = time.monotonic()

    def progress(i, n, t):
        if i == 1 or i % 12 == 0 or i == n:
            echo(f"  {i}/{n} cutoffs  ({time.monotonic() - t0:.0f}s)")

    tl = timeline.build_timeline(_database(s), progress)
    if tl.database_sha256 != s.database_sha256 or tl.trading_date != s.trading_date:
        raise typer.BadParameter(f"{_database(s)} is not the approved dataset for {s.trading_date}")
    timeline.save_timeline(tl, path)
    echo(f"Prepared {len(tl.positions)} cutoffs in {time.monotonic() - t0:.0f}s")
    return path


def _enabled() -> list[dev_sessions.DevSession]:
    return [s for s in dev_sessions.discoverable() if s.enabled]


@app.command()
def prepare(trading_date: str = typer.Option(None, "--date", help="Approved development date (default: enabled dates).")):
    """Build the cached replay timeline for approved development sessions."""
    targets = [dev_sessions.approved_session(date.fromisoformat(trading_date))] if trading_date else _enabled()
    for s in targets:
        typer.echo(f"{s.trading_date}: {ensure_prepared(s)}")


@app.command()
def serve(port: int = typer.Option(DEFAULT_PORT, help="Local port."),
          host: str = typer.Option("127.0.0.1", help="Bind address (local only by default).")):
    """Serve the Tutor POC at http://localhost:PORT (prepares missing sessions first)."""
    import uvicorn

    from tutor_poc.api import create_app

    for s in _enabled():
        ensure_prepared(s)
    typer.echo(f"Tutor POC: http://localhost:{port}")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
