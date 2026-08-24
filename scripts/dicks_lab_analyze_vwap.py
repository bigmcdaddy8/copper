"""Read-only, offline anchored-VWAP analysis over a durable Dick's Laboratory dataset."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import typer

from dicks_laboratory.analysis import (
    LaboratoryAnalysisError,
    VwapAnalysisResult,
    analyze_anchored_vwap_dataset,
    open_dataset_store,
    resolve_dataset_id,
)
from dicks_laboratory.cli_support import (
    ANCHOR_LABELS,
    anchor_label_slug,
    format_timedelta,
    format_utc_and_chicago,
    parse_anchor_argument,
    parse_trading_date_argument,
    yes_no,
)

app = typer.Typer(add_completion=False)


@app.command()
def analyze(
    database_path: Path = typer.Argument(..., help="Path to a durable Dick's Laboratory SQLite dataset."),
    anchor: str = typer.Option(
        ...,
        "--anchor",
        help="'session-open', 'cash-open', or an explicit aware UTC timestamp (e.g. 2026-08-24T14:15:00Z).",
    ),
    trading_date: str | None = typer.Option(
        None, "--trading-date", help="YYYY-MM-DD; required only when the dataset spans multiple trading dates."
    ),
    dataset_id: str | None = typer.Option(
        None, "--dataset-id", help="Required only when the database contains multiple datasets."
    ),
) -> None:
    """Print a factual anchored VWAP report computed only from retained trades."""
    anchor_kind, custom_timestamp = parse_anchor_argument(anchor)
    parsed_trading_date = parse_trading_date_argument(trading_date)
    parsed_dataset_id = UUID(dataset_id) if dataset_id else None

    try:
        store = open_dataset_store(database_path)
        try:
            resolved_dataset_id = resolve_dataset_id(store, parsed_dataset_id)
            result = analyze_anchored_vwap_dataset(
                store, resolved_dataset_id, anchor_kind, parsed_trading_date, custom_timestamp
            )
        finally:
            store.close()
    except LaboratoryAnalysisError as exc:
        typer.echo(f"Analysis error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(_render_report(result))
    if result.canonical_vwap is None and result.effective_vwap is None:
        raise typer.Exit(code=1)


def _render_report(result: VwapAnalysisResult) -> str:
    lines = ["Dick's Laboratory -- Anchored VWAP Analysis", ""]
    lines += ["Dataset:", f"  {result.dataset_id}", ""]
    lines += ["Instrument:", f"  {result.instrument.canonical_id}", ""]
    if result.trading_date is not None:
        lines += ["Trading date:", f"  {result.trading_date.isoformat()}", ""]
    lines += [
        "Anchor:",
        f"  {ANCHOR_LABELS[result.anchor_kind]}",
        f"  Chicago: {format_utc_and_chicago(result.anchor_timestamp_utc)[1]}",
        f"  UTC:     {format_utc_and_chicago(result.anchor_timestamp_utc)[0]}",
        "",
    ]
    lines += [
        "Retained dataset:",
        f"  First trade: {format_utc_and_chicago(result.dataset_first_trade_timestamp)[1]}",
        f"  Last trade:  {format_utc_and_chicago(result.dataset_last_trade_timestamp)[1]}",
        "",
    ]
    lines += ["Coverage:", f"  {result.coverage.value}", f"  Dataset begins after requested anchor: {yes_no(result.dataset_begins_after_anchor)}"]
    if result.unobserved_pre_capture_interval is not None:
        lines.append(f"  Unobserved pre-capture interval: {format_timedelta(result.unobserved_pre_capture_interval)}")
    if result.session_end_utc is not None:
        lines.append(f"  Session end (Chicago): {format_utc_and_chicago(result.session_end_utc)[1]}")
        lines.append(f"  Dataset ends before session end: {yes_no(result.dataset_ends_before_session_end)}")
    lines.append("")

    if result.canonical_vwap is None and result.effective_vwap is None:
        lines += [
            "No retained trades exist at or after the requested anchor.",
            "No VWAP was calculated.",
        ]
        return "\n".join(lines)

    lines += [
        "Canonical NEW-only:",
        f"  Trades: {result.canonical_included_trade_count:,}",
        f"  Volume: {result.canonical_included_volume}",
        f"  VWAP:   {result.canonical_vwap}",
        "",
        "Effective tape:",
        f"  Trades:              {result.effective_included_trade_count:,}",
        f"  Corrections applied:  {result.applied_correction_count}",
        f"  Cancels applied:      {result.applied_cancel_count}",
        f"  VWAP:                 {result.effective_vwap}",
    ]
    if result.reconstruction_anomaly_count:
        lines.append(f"  Reconstruction anomalies: {result.reconstruction_anomaly_count} {result.reconstruction_anomaly_counts_by_reason}")
    lines += ["", "Label:", f"  Captured-data developing {anchor_label_slug(result.anchor_kind)} anchored VWAP"]
    return "\n".join(lines)


if __name__ == "__main__":
    app()
