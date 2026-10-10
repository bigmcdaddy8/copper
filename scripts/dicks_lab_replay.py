"""Deterministic as-of replay: MARKET_STUDY_SNAPSHOT_V1 at explicit cutoffs (0Z-B). Read-only, offline.

The database is prepared once; each `--at` produces one snapshot as fast as computation
allows (no real-time sleeping). `--at` sets both the market-time and the knowledge-time
cutoff; `--knowledge-at` / `--source-order` set the knowledge clock separately (single
`--at` only). Times must carry a UTC offset, e.g. 2026-09-30T08:45:00-05:00.

`--diagnose` prints the replay audit (why each correction / cancel, its target and the
largest late prints are or are not visible). It reads the full record by design and is
never part of a snapshot.
"""
from __future__ import annotations

import subprocess
from datetime import date, datetime
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


def _instant(text: str) -> datetime:
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        raise typer.BadParameter(f"{text!r} has no UTC offset; replay times must be explicit")
    return value


def main(
    database: Path = typer.Argument(..., help="Laboratory SQLite dataset to replay."),
    at: list[str] = typer.Option(..., "--at", help="Cutoff instant with offset (repeatable)."),
    prior_database: Path | None = typer.Option(None, "--prior-database", help="Prior trading-date dataset."),
    knowledge_at: str | None = typer.Option(None, "--knowledge-at", help="Separate knowledge-time cutoff."),
    source_order: int | None = typer.Option(None, "--source-order", help="Knowledge source-order cursor."),
    json_output: bool = typer.Option(False, "--json", help="Print the canonical snapshot JSON (single --at)."),
    out_dir: Path | None = typer.Option(None, "--out-dir", help="Write each snapshot JSON and summary here."),
    diagnose: bool = typer.Option(False, "--diagnose", help="Print the record-visibility audit."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
    dataset_id: UUID | None = typer.Option(None, "--dataset-id", help="Dataset id when the database holds several."),
    analysis_commit: str | None = typer.Option(None, "--analysis-commit", help="Explicit analysis git commit."),
) -> None:
    instants = [_instant(x) for x in at]
    if (json_output or knowledge_at or source_order is not None) and len(instants) != 1:
        raise typer.BadParameter("--json, --knowledge-at and --source-order take exactly one --at")
    provenance = _provenance(analysis_commit)
    try:
        replay = MarketReplay.load(database, provenance, prior_database,
                                   frozenset(date.fromisoformat(c) for c in closures), dataset_id)
    except LaboratoryAnalysisError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
    for instant in instants:
        knowledge = _instant(knowledge_at) if knowledge_at else instant
        cutoff = ReplayCutoff(instant, knowledge, source_order)
        snapshot = replay.snapshot(cutoff=cutoff)
        document = canonical_snapshot_json(snapshot)
        sha = snapshot_sha256(snapshot)
        if out_dir is not None:
            stem = encode(cutoff.market_time_cutoff_utc).replace(":", "")
            (out_dir / f"{stem}.json").write_text(document)
            (out_dir / f"{stem}.txt").write_text(render_snapshot_summary(snapshot, sha))
        if json_output:
            typer.echo(document)
        else:
            typer.echo(render_snapshot_summary(snapshot, sha), nl=False)
        if diagnose:
            typer.echo("RECORD VISIBILITY (replay audit; uses the full record)")
            typer.echo("  record      source_order  market_utc                   received_utc                 "
                       "lag_s        visibility")
            for v in replay.visibility(cutoff):
                typer.echo(f"  {v.record:<11} {v.source_order:>12}  {encode(v.market_timestamp_utc) or '--':<28} "
                           f"{encode(v.received_at_utc):<28} {encode(v.receipt_lag) or '--':>11}  "
                           f"{v.visibility.value}: {v.reason}")


if __name__ == "__main__":
    typer.run(main)
