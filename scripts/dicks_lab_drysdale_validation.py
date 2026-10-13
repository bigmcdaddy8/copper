"""Drysdale prospective validation harness (0AB-D, DRYSDALE_PROSPECTIVE_VALIDATION_V1). Read-only, offline, no AI.

Runs the validation pre-registered in docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md over frozen
DRYSDALE_V1. Campaign data (trading date on or after 2026-10-12, or unknown) are refused unless the 0AB-D freeze
manifest verifies and --frozen-plan names the frozen plan sha256.

  date DB --prior-db P --out F      one date: the registered per-date record (JSON)
  cohort F... --json-out J --md-out M   records -> cohort summary, flags, classification, readout markdown
  guard DB                          whether this dataset is guarded and whether access would be allowed

Educational structure only: no trade, entry, stop, target, sizing, PnL or win rate.
"""
from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import typer

from dicks_laboratory import drysdale_validation as dv
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.analysis import LaboratoryAnalysisError
from dicks_laboratory.market_study_state import AnalysisProvenance
from dicks_laboratory.replay import MarketReplay
from dicks_laboratory.replay_player import ReplaySession

REPO = Path(__file__).resolve().parents[1]
app = typer.Typer(add_completion=False, no_args_is_help=True)


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


def _guard(database: Path, frozen_plan: str | None) -> bool:
    try:
        return dv.require_access(REPO, database, frozen_plan)
    except dv.CampaignAccessDenied as exc:
        typer.echo(f"REFUSED: {exc}", err=True)
        raise typer.Exit(code=3) from exc
    except LaboratoryAnalysisError as exc:
        typer.echo(f"ERROR: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@app.command("date")
def date_cmd(
    database: Path = typer.Argument(..., help="Laboratory SQLite dataset (one trading date)."),
    out: Path = typer.Option(..., "--out", help="Where to write the per-date record JSON."),
    prior_database: Path | None = typer.Option(None, "--prior-database", "--prior-db", help="Prior trading date."),
    frozen_plan: str | None = typer.Option(None, "--frozen-plan", help="sha256 of the frozen validation plan."),
    analysis_commit: str | None = typer.Option(None, "--analysis-commit", help="Explicit analysis git commit."),
    no_sweep: bool = typer.Option(False, "--no-sweep", help="Skip the hourly withdrawn-candidate sweep (tests)."),
) -> None:
    guarded = _guard(database, frozen_plan)  # metadata only, before any trade is read
    provenance = _provenance(analysis_commit)
    try:
        session = ReplaySession(MarketReplay.load(database, provenance, prior_database))
        rec = dv.date_record(session, sweep=not no_sweep)
    except Exception as exc:  # recorded, never dropped: a captured date that cannot be evaluated BLOCKS the cohort
        rec = dv.error_record(dv.dataset_identity(database)[0], database.name, f"{type(exc).__name__}: {exc}")
        out.write_text(mss._dumps(rec))
        typer.echo(f"HARNESS_ERROR recorded for {rec['trading_date']}: {rec['error']}", err=True)
        raise typer.Exit(code=4) from exc
    rec["campaign_guarded"] = guarded
    rec["record_sha256"] = dv.record_sha256(rec)
    out.write_text(mss._dumps(rec))
    typer.echo(f"{rec['trading_date']} {rec['date_status']}: {len(rec['candidates'])} candidates; determinism "
               f"{'identical' if rec['determinism']['identical'] else 'DIFFERENT'}; record {rec['record_sha256']}")


@app.command("cohort")
def cohort_cmd(
    records: list[Path] = typer.Argument(..., help="Per-date record JSON files."),
    json_out: Path = typer.Option(..., "--json-out"),
    md_out: Path = typer.Option(..., "--md-out"),
    frozen_plan: str | None = typer.Option(None, "--frozen-plan", help="sha256 of the frozen validation plan."),
    expected: list[str] = typer.Option([], "--date", help="Expected trading dates (default: the 20 cohort dates)."),
    attribution: dv.Attribution | None = typer.Option(None, "--attribution",
                                                      help="Human investigation result for violations."),
) -> None:
    recs = [json.loads(p.read_text()) for p in records]
    if any(date.fromisoformat(r["trading_date"]) >= dv.COHORT_START for r in recs):
        problems = dv.freeze_problems(REPO, frozen_plan)
        if problems:
            typer.echo("REFUSED: campaign records; " + "; ".join(problems), err=True)
            raise typer.Exit(code=3)
    dates = tuple(date.fromisoformat(d) for d in expected) if expected else dv.COHORT_DATES
    s = dv.cohort_summary(recs, dates, attribution)
    json_out.write_text(mss._dumps(mss.encode(s)))
    md_out.write_text(dv.render_report(s))
    typer.echo(f"{s['classification']}; eligible dates {s['dates']['eligible']}; eligible candidates "
               f"{s['all_families']['eligible_candidates']}")


@app.command("guard")
def guard_cmd(
    database: Path = typer.Argument(...),
    frozen_plan: str | None = typer.Option(None, "--frozen-plan"),
) -> None:
    td, started = dv.dataset_identity(database)
    if not dv.guarded(td, started):
        typer.echo(f"{td}: not campaign data (development); access allowed")
        return
    problems = dv.freeze_problems(REPO, frozen_plan)
    typer.echo(f"{td}: unseen campaign data; " + ("access allowed (freeze verified)" if not problems else
                                                  "REFUSED: " + "; ".join(problems)))
    if problems:
        raise typer.Exit(code=3)


if __name__ == "__main__":
    app()
