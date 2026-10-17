"""tutor_poc: prepare approved development sessions and serve the local Tutor POC."""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import typer

from tutor_poc import dev_sessions, timeline

app = typer.Typer(help="AI Tutor UX POC (0AC-A1..A3): local chart, replay and the grounded Tutor.", no_args_is_help=True)

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


_KIND = {"question": "question", "message": "reply", "hint": "hint", "explain": "explain"}


def _provider():
    from tutor_poc.providers import ProviderConfigError, provider_from_env

    try:
        return provider_from_env()
    except ProviderConfigError as e:
        typer.echo(f"Tutor provider configuration error: {e}", err=True)
        raise typer.Exit(2) from e


def run_log_path() -> Path:
    return timeline.cache_dir() / "runs" / f"tutor_runs_{time.strftime('%Y%m%d')}.jsonl"


@app.command()
def serve(port: int = typer.Option(DEFAULT_PORT, help="Local port."),
          host: str = typer.Option("127.0.0.1", help="Bind address (local only by default).")):
    """Serve the Tutor POC at http://localhost:PORT (prepares missing sessions first).

    Provider from the environment: TUTOR_PROVIDER=fake (default) | anthropic, TUTOR_MODEL, TUTOR_EFFORT,
    ANTHROPIC_API_KEY (anthropic only)."""
    import logging

    import uvicorn

    from tutor_poc.api import create_app

    provider = _provider()
    for s in _enabled():
        ensure_prepared(s)
    cfg = provider.public_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    log = run_log_path() if cfg["mode"] == "real" else None
    typer.echo(f"Tutor provider: {cfg['provider']}" + (f"  model {cfg['model']}  effort {cfg['effort']}  "
                                                        f"prompt {cfg['prompt_version']}  run log {log}"
                                                        if cfg["mode"] == "real" else "  (no model, no cost)"))
    typer.echo(f"Tutor POC: http://localhost:{port}")
    uvicorn.run(create_app(provider=provider, run_log=log), host=host, port=port, log_level="warning")


@app.command("live-smoke")
def live_smoke(cutoff: str = typer.Option("09:30", help="Replay cutoff (CT, HH:MM) on the enabled development date."),
               message: str = typer.Option("What should I notice about the latest completed candle?",
                                           help="The Human message sent after the opening question."),
               yes: bool = typer.Option(False, "--yes", help="Confirm that this spends real API tokens.")):
    """OPT-IN live check of the real provider: 4 turns (question, message, hint, explain). SPENDS REAL TOKENS.

    Needs TUTOR_PROVIDER=anthropic and ANTHROPIC_API_KEY. Never part of pytest."""
    from datetime import datetime as dt

    from dicks_laboratory.tutor_evidence import LessonStage

    from tutor_poc.conversation import TutorSession
    from tutor_poc.providers import TurnContext, dumps, run_record, turn_diagnostics
    from tutor_poc.tutor import CT, TutorAction, next_stage

    if not yes:
        typer.echo("live-smoke calls the real model and spends API tokens; re-run with --yes to confirm.", err=True)
        raise typer.Exit(2)
    provider = _provider()
    if provider.public_config()["mode"] != "real":
        typer.echo("live-smoke needs TUTOR_PROVIDER=anthropic.", err=True)
        raise typer.Exit(2)
    s = _enabled()[0]
    tl = timeline.load_timeline(ensure_prepared(s))
    hh, mm = (int(x) for x in cutoff.split(":"))
    target = dt.combine(tl.trading_date, dt.min.time().replace(hour=hh, minute=mm), tzinfo=CT)
    index = next(i for i, p in enumerate(tl.positions) if p.cutoff_utc == target)
    session, stage, log = TutorSession(), LessonStage.QUESTION, run_log_path()
    log.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"{tl.trading_date} cutoff {cutoff} CT · {provider.public_config()}")
    typer.echo("turn  action    status             in(uncached)  cached  cache-write  out   model-s  repairs  "
               "evidence-B  cost-usd")
    for n, (action, text) in enumerate(((TutorAction.QUESTION, None), (TutorAction.MESSAGE, message),
                                        (TutorAction.HINT, None), (TutorAction.EXPLAIN, None))):
        stage = next_stage(stage, action)
        cut = tl.positions[index].cutoff_utc
        ctx = TurnContext(action, stage, n, text, tl, index, session.context(tl.trading_date, cut))
        r = provider.respond(ctx)
        session.record(tl.trading_date, cut, text, _KIND[action.value], r)
        with log.open("a") as f:
            f.write(dumps(run_record(r, ctx)) + "\n")
        d = turn_diagnostics(r)
        u = d["usage"] or {}
        typer.echo(f"{n:<5} {action.value:<9} {r.status:<18} {u.get('input_tokens')!s:>12}  "
                   f"{u.get('cached_input_tokens')!s:>6}  {u.get('cache_write_input_tokens')!s:>11}  "
                   f"{u.get('output_tokens')!s:>4}  {d['latency_ms']['model'] / 1000:>7.2f}  {d['repair_attempts']:>7}  "
                   f"{d['evidence_bytes']!s:>10}  {d['turn_cost_usd']}")
        typer.echo(f"      tutor: {r.text if r.accepted else r.error_message}")
    typer.echo(f"session: {session.totals.as_dict()}")
    typer.echo(f"run log: {log}")
