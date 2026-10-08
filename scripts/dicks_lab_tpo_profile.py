"""Read-only, offline TPO / Market Profile report over a durable Dick's Laboratory dataset (0Y-A).

Deterministic: the same database always yields the same output. No network
access; the database is opened read-only and never modified.
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.cli_support import parse_trading_date_argument
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, render_tpo_report
from dicks_laboratory.tpo_profile import DEFAULT_PERIOD_MINUTES, US_CASH_PROFILE

app = typer.Typer(add_completion=False)

_SESSIONS = {"cash": US_CASH_PROFILE}


@app.command()
def profile(
    database_path: Path = typer.Argument(..., help="Path to a durable Dick's Laboratory SQLite dataset."),
    session: str = typer.Option("cash", "--session", help="Study window: 'cash' = US_CASH_PROFILE 08:30-15:00 CT."),
    period_minutes: int = typer.Option(DEFAULT_PERIOD_MINUTES, "--period-minutes", help="TPO period length."),
    trading_date: str | None = typer.Option(
        None, "--trading-date", help="YYYY-MM-DD; required only when the dataset spans multiple trading dates."
    ),
    dataset_id: str | None = typer.Option(
        None, "--dataset-id", help="Required only when the database contains multiple datasets."
    ),
    matrix: bool = typer.Option(True, "--matrix/--no-matrix", help="Print the TPO price/period matrix."),
    compare_volume: bool = typer.Option(
        False, "--compare-volume-profile", help="Also show Volume Profile POC/VAL/VAH over the same trades."
    ),
    structure: bool = typer.Option(
        False, "--structure", help="Add structural facts (one-TPO zones, extremes, IB/period range facts)."
    ),
) -> None:
    """Print a factual TPO profile (POC, value area, initial balance) for one study window."""
    window = _SESSIONS.get(session)
    if window is None:
        raise typer.BadParameter(f"Unsupported --session {session!r}; supported: {', '.join(_SESSIONS)}.")
    parsed_trading_date = parse_trading_date_argument(trading_date)
    parsed_dataset_id = UUID(dataset_id) if dataset_id else None
    try:
        store = open_dataset_store(database_path)
        try:
            resolved = resolve_dataset_id(store, parsed_dataset_id)
            result = analyze_tpo_dataset(store, resolved, parsed_trading_date, period_minutes, window)
        finally:
            store.close()
    except ValueError as exc:  # LaboratoryAnalysisError and invalid period lengths
        label = "Analysis error" if isinstance(exc, LaboratoryAnalysisError) else "Invalid request"
        typer.echo(f"{label}: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(render_tpo_report(result, show_matrix=matrix, compare_volume=compare_volume, show_structure=structure))
    if result.profile is None:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
