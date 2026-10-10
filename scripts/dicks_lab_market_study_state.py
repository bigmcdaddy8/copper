"""MARKET_STUDY_STATE_V1 for one trading-date dataset (0Z-A). Read-only and offline.

Builds the unified FINAL_STUDY_STATE from a current Laboratory database and an
optional prior trading-date database. `--json` prints the canonical JSON document
(payload + market_study_state_sha256); `--summary` (the default) prints the
evidence by domain. Databases are opened read-only; nothing is written to them.

The analysis commit is resolved from this repository (`git rev-parse HEAD`) unless
`--analysis-commit` is given. No generation time is recorded in the state.
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path
from uuid import UUID

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError
from dicks_laboratory.market_study_state import (
    AnalysisProvenance,
    build_market_study_state,
    canonical_state_json,
    load_study_inputs,
    market_study_state_sha256,
    render_summary,
)

REPO = Path(__file__).resolve().parents[1]
_ANALYSIS_PATHS = ("apps/dicks_laboratory/src", "scripts/dicks_lab_market_study_state.py")


def resolve_provenance(explicit_commit: str | None) -> AnalysisProvenance:
    if explicit_commit:
        return AnalysisProvenance(explicit_commit, None)
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                                check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", *_ANALYSIS_PATHS], cwd=REPO,
                               capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise typer.BadParameter("cannot resolve the analysis git commit; pass --analysis-commit") from exc
    return AnalysisProvenance(commit, bool(dirty))


def main(
    database: Path = typer.Argument(..., help="Current trading-date Laboratory SQLite dataset."),
    prior_database: Path | None = typer.Option(None, "--prior-database", help="Prior trading-date dataset."),
    dataset_id: UUID | None = typer.Option(None, "--dataset-id", help="Dataset id when the database holds several."),
    json_output: bool = typer.Option(False, "--json", help="Print the canonical JSON document."),
    summary: bool = typer.Option(False, "--summary", help="Print the human summary (default)."),
    json_out: Path | None = typer.Option(None, "--json-out", help="Also write the canonical JSON document here."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
    analysis_commit: str | None = typer.Option(None, "--analysis-commit", help="Explicit analysis git commit."),
) -> None:
    if json_output and summary:
        raise typer.BadParameter("choose --json or --summary (use --json-out to keep both)")
    provenance = resolve_provenance(analysis_commit)
    try:
        current = load_study_inputs(database, dataset_id)
        prior = load_study_inputs(prior_database) if prior_database is not None else None
    except LaboratoryAnalysisError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    state = build_market_study_state(current, prior, provenance, frozenset(date.fromisoformat(c) for c in closures))
    document = canonical_state_json(state)
    if json_out is not None:
        json_out.write_text(document)
    if json_output:
        typer.echo(document)
    else:
        typer.echo(render_summary(state, market_study_state_sha256(state)), nl=False)


if __name__ == "__main__":
    typer.run(main)
