"""Deterministic as-of replay player: MARKET_STUDY_SNAPSHOT_V1 at explicit cutoffs (0Z-B / 0Z-C).

Read-only and offline. The dataset is prepared once; each `--at` produces one snapshot as
fast as computation allows (no real-time sleeping).

Times: ISO with an offset (2026-09-30T09:45:00-05:00) or "HH:MM[:SS]" America/Chicago on
the replayed session (times at/after 17:00 belong to the session's opening evening).

  --at T [--at T2 ...]   player view at each time (`--view summary` = the 0Z-B summary)
  --compare T1 T2        structured differences; T2 may be +1m, +5m, +Ns or next (milestone)
  --milestones           the session's structural milestones
  --json                 canonical snapshot JSON (single --at) or delta JSON (--compare)

`--at` sets both the market-time and the knowledge-time cutoff; `--knowledge-at` /
`--source-order` set the knowledge clock separately (single `--at` only). `--diagnose`
prints the replay audit (it reads the full record by design and is never part of a snapshot).
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from uuid import UUID

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError
from dicks_laboratory.market_study_state import AnalysisProvenance, encode
from dicks_laboratory.replay import (
    MarketReplay,
    ReplayCutoff,
    canonical_snapshot_json,
    render_snapshot_summary,
    snapshot_sha256,
)
from dicks_laboratory.replay_player import (
    ReplaySession,
    canonical_delta_json,
    render_delta,
    render_player_view,
)

REPO = Path(__file__).resolve().parents[1]
_ANALYSIS_PATHS = ("apps/dicks_laboratory/src", "scripts/dicks_lab_replay.py")


def _provenance(explicit: str | None) -> AnalysisProvenance:
    if explicit:
        return AnalysisProvenance(explicit, None)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", *_ANALYSIS_PATHS], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise typer.BadParameter("cannot resolve the analysis git commit; pass --analysis-commit") from exc
    return AnalysisProvenance(commit, bool(dirty))


def main(
    database: Path = typer.Argument(..., help="Laboratory SQLite dataset to replay."),
    at: list[str] = typer.Option([], "--at", help="Cutoff: ISO with offset or HH:MM Chicago (repeatable)."),
    compare: tuple[str, str] | None = typer.Option(None, "--compare", help="T1 T2 (T2 may be +5m, +1m, next)."),
    milestones: bool = typer.Option(False, "--milestones", help="List the session's structural milestones."),
    view: str = typer.Option("player", "--view", help="player (default) or summary (the 0Z-B summary)."),
    prior_database: Path | None = typer.Option(None, "--prior-database", "--prior-db",
                                               help="Prior trading-date dataset."),
    knowledge_at: str | None = typer.Option(None, "--knowledge-at", help="Separate knowledge-time cutoff."),
    source_order: int | None = typer.Option(None, "--source-order", help="Knowledge source-order cursor."),
    json_output: bool = typer.Option(False, "--json", help="Canonical snapshot (single --at) or delta JSON."),
    out_dir: Path | None = typer.Option(None, "--out-dir", help="Write each snapshot JSON and summary here."),
    diagnose: bool = typer.Option(False, "--diagnose", help="Print the record-visibility audit."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
    dataset_id: UUID | None = typer.Option(None, "--dataset-id", help="Dataset id when the database holds several."),
    analysis_commit: str | None = typer.Option(None, "--analysis-commit", help="Explicit analysis git commit."),
) -> None:
    if view not in ("player", "summary"):
        raise typer.BadParameter("--view must be player or summary")
    if not at and compare is None and not milestones:
        raise typer.BadParameter("give --at, --compare or --milestones")
    if json_output and compare is None and len(at) != 1:
        raise typer.BadParameter("--json takes exactly one --at (or --compare)")
    if (knowledge_at or source_order is not None) and len(at) != 1:
        raise typer.BadParameter("--knowledge-at and --source-order take exactly one --at")
    provenance = _provenance(analysis_commit)
    try:
        session = ReplaySession(MarketReplay.load(database, provenance, prior_database,
                                                  frozenset(date.fromisoformat(c) for c in closures), dataset_id))
    except LaboratoryAnalysisError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        instants = [session.resolve_time(x) for x in at]
        knowledge = session.resolve_time(knowledge_at) if knowledge_at else None
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    if milestones:
        for m in session.timeline():
            typer.echo(f"{m.name:<22} {encode(m.at_utc)}")
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    for instant in instants:
        cutoff = ReplayCutoff(instant, knowledge or instant, source_order)
        snapshot = session.snapshot(cutoff=cutoff)
        sha = snapshot_sha256(snapshot)
        if out_dir is not None:
            stem = encode(cutoff.market_time_cutoff_utc).replace(":", "")
            (out_dir / f"{stem}.json").write_text(canonical_snapshot_json(snapshot))
            (out_dir / f"{stem}.txt").write_text(render_snapshot_summary(snapshot, sha))
        if json_output and compare is None:
            typer.echo(canonical_snapshot_json(snapshot))
        elif not json_output:
            render = render_player_view if view == "player" else render_snapshot_summary
            typer.echo(render(snapshot, sha), nl=False)
        if diagnose:
            typer.echo("RECORD VISIBILITY (replay audit; uses the full record)")
            typer.echo("  record      source_order  market_utc                   received_utc                 "
                       "lag_s        visibility")
            for v in session.replay.visibility(cutoff):
                typer.echo(f"  {v.record:<11} {v.source_order:>12}  {encode(v.market_timestamp_utc) or '--':<28} "
                           f"{encode(v.received_at_utc):<28} {encode(v.receipt_lag) or '--':>11}  "
                           f"{v.visibility.value}: {v.reason}")
    if compare is not None:
        try:
            t1 = session.resolve_time(compare[0])
            second = compare[1]
            t2 = session.step(t1, second) if second.startswith("+") or second == "next" else session.resolve_time(second)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        delta = session.compare(t1, t2)
        typer.echo(canonical_delta_json(delta) if json_output else render_delta(delta), nl=not json_output)
        if json_output:
            typer.echo("")


if __name__ == "__main__":
    typer.run(main)
