"""Tutor lesson demonstrator (0AA-A): one replay-backed lesson, student or instructor view. No AI model.

Read-only and offline. Builds a LAB_EVIDENCE_READING_V1 example lesson on the replayed session and
prints the question, the authorized AS_OF evidence and the names of withheld material; with
`--instructor`, the deterministic answer key (and any hidden future outcome) as well.

  --lesson vwap|ib|changes|value-migration|occupancy|not-yet|quality
  --at T            the student's replay time (ISO with offset or HH:MM[:SS] America/Chicago)
  --from T0         earlier time for comparison lessons (changes, value-migration)
  --reveal-at T2    hidden future outcome (instructor-only until --stage POST_REVEAL)
  --stage S         QUESTION (default), HINT, ANSWER, POST_REVEAL (student view)
  --json            canonical payload JSON
"""
from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.replay import MarketReplay
from dicks_laboratory.replay_player import ReplaySession
from dicks_laboratory.tutor_evidence import (
    LessonStage,
    QuestionKind,
    build_tutor_lesson,
    canonical_json,
    example_lesson,
    instructor_view,
    render_view,
    student_view,
)

REPO = Path(__file__).resolve().parents[1]
LESSONS = {"vwap": QuestionKind.PRICE_VS_CASH_VWAP, "ib": QuestionKind.INITIAL_BALANCE_STATUS,
           "changes": QuestionKind.EVIDENCE_CHANGES, "value-migration": QuestionKind.VALUE_MIGRATION,
           "occupancy": QuestionKind.VALUE_OCCUPANCY, "not-yet": QuestionKind.NOT_YET_DETERMINED_ITEMS,
           "quality": QuestionKind.DATA_QUALITY}


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
    lesson: str = typer.Option(..., "--lesson", help="|".join(LESSONS)),
    at: str = typer.Option(..., "--at", help="Student replay time: ISO with offset or HH:MM Chicago."),
    compare_from: str | None = typer.Option(None, "--from", help="Earlier time (comparison lessons)."),
    reveal_at: str | None = typer.Option(None, "--reveal-at", help="Hidden future outcome time."),
    stage: str = typer.Option("QUESTION", "--stage", help="QUESTION, HINT, ANSWER or POST_REVEAL."),
    instructor: bool = typer.Option(False, "--instructor", help="Instructor view (answer key, future outcome)."),
    prior_database: Path | None = typer.Option(None, "--prior-database", "--prior-db",
                                               help="Prior trading-date dataset."),
    json_output: bool = typer.Option(False, "--json", help="Canonical payload JSON."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
    analysis_commit: str | None = typer.Option(None, "--analysis-commit", help="Explicit analysis git commit."),
) -> None:
    if lesson not in LESSONS:
        raise typer.BadParameter(f"--lesson must be one of {', '.join(LESSONS)}")
    try:
        lesson_stage = LessonStage(stage)
    except ValueError as exc:
        raise typer.BadParameter("--stage must be QUESTION, HINT, ANSWER or POST_REVEAL") from exc
    try:
        session = ReplaySession(MarketReplay.load(database, _provenance(analysis_commit), prior_database,
                                                  frozenset(date.fromisoformat(c) for c in closures)))
    except LaboratoryAnalysisError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    try:
        definition = example_lesson(session, LESSONS[lesson], at, compare_from, reveal_at)
        built = build_tutor_lesson(session, definition)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    payload = instructor_view(built) if instructor else student_view(built, lesson_stage)
    typer.echo(canonical_json(payload) if json_output else render_view(payload), nl=json_output)


if __name__ == "__main__":
    typer.run(main)
