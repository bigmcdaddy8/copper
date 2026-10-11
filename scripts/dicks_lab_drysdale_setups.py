"""Drysdale VWAP Wave Laboratory V1 training candidates (0AB-B). Read-only, offline, no AI model.

Replays a Laboratory dataset to a time and prints DRYSDALE_SETUP_ANALYSIS_V1: the Globex-anchored VWAP
(17:00 CT), the Drysdale VWAP value area (+/-1 sigma, DRYSDALE_VALUE_AREA_V1), +/-2 sigma outer context and,
per setup family, the Drysdale source criteria next to the Laboratory V1 proxy conditions. Educational
structure only: no trade, entry, stop, target or sizing.

  --at T     replay time (ISO with offset or HH:MM[:SS] America/Chicago)
  --json     canonical DRYSDALE_SETUP_ANALYSIS_V1 JSON (with drysdale_sha256)
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError
from dicks_laboratory.drysdale import analyze, canonical_analysis_json, render_analysis
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.replay import MarketReplay
from dicks_laboratory.replay_player import ReplaySession

REPO = Path(__file__).resolve().parents[1]


def _provenance(explicit: str | None) -> AnalysisProvenance:
    if explicit:
        return AnalysisProvenance(explicit, None)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "apps/dicks_laboratory/src"], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise typer.BadParameter("cannot resolve the analysis git commit; pass --analysis-commit") from exc
    return AnalysisProvenance(commit, bool(dirty))


def main(
    database: Path = typer.Argument(..., help="Laboratory SQLite dataset to replay."),
    at: str = typer.Option(..., "--at", help="Replay time: ISO with offset or HH:MM Chicago."),
    prior_database: Path | None = typer.Option(None, "--prior-database", "--prior-db",
                                               help="Prior trading-date dataset."),
    json_output: bool = typer.Option(False, "--json", help="Canonical DRYSDALE_SETUP_ANALYSIS_V1 JSON."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
    analysis_commit: str | None = typer.Option(None, "--analysis-commit", help="Explicit analysis git commit."),
) -> None:
    try:
        session = ReplaySession(MarketReplay.load(database, _provenance(analysis_commit), prior_database,
                                                  frozenset(date.fromisoformat(c) for c in closures)))
    except LaboratoryAnalysisError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        analysis = analyze(session, at)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(canonical_analysis_json(analysis) if json_output else render_analysis(analysis), nl=json_output)


if __name__ == "__main__":
    typer.run(main)
