"""Read-only, offline Volume Profile analysis over a durable Dick's Laboratory dataset.

Combines the accepted 0N anchor/coverage selection, 0O Volume-at-Price/POC
foundation, and 0P Value Area/VAH/VAL policy into one human-facing report.
Never shows POC/VAH/VAL without also showing which retained trades and
anchor produced them.
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import typer

from dicks_laboratory.analysis import (
    LaboratoryAnalysisError,
    VolumeProfileAnalysisResult,
    analyze_volume_profile_dataset,
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

_DEFAULT_TOP_LEVELS = 10
_MIN_TOP_LEVELS = 1
_MAX_TOP_LEVELS = 100


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
    top_levels: int = typer.Option(
        _DEFAULT_TOP_LEVELS,
        "--top-levels",
        min=_MIN_TOP_LEVELS,
        max=_MAX_TOP_LEVELS,
        help="Number of top-volume price levels to display (presentation only; does not affect POC/Value Area).",
    ),
) -> None:
    """Print a factual Volume Profile report (VWAP, POC, VAL/VAH) computed only from retained trades."""
    anchor_kind, custom_timestamp = parse_anchor_argument(anchor)
    parsed_trading_date = parse_trading_date_argument(trading_date)
    parsed_dataset_id = UUID(dataset_id) if dataset_id else None

    try:
        store = open_dataset_store(database_path)
        try:
            resolved_dataset_id = resolve_dataset_id(store, parsed_dataset_id)
            result = analyze_volume_profile_dataset(
                store, resolved_dataset_id, anchor_kind, parsed_trading_date, custom_timestamp
            )
        finally:
            store.close()
    except LaboratoryAnalysisError as exc:
        typer.echo(f"Analysis error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(_render_report(result, top_levels))
    if result.profile is None:
        raise typer.Exit(code=1)


def _render_report(result: VolumeProfileAnalysisResult, top_levels: int) -> str:
    lines = ["Dick's Laboratory -- Volume Profile Analysis", ""]
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
    lines += [
        "Coverage:",
        f"  {result.coverage.value}",
        f"  Dataset begins after requested anchor: {yes_no(result.dataset_begins_after_anchor)}",
    ]
    if result.unobserved_pre_capture_interval is not None:
        lines.append(f"  Unobserved pre-capture interval: {format_timedelta(result.unobserved_pre_capture_interval)}")
    if result.session_end_utc is not None:
        lines.append(f"  Session end (Chicago): {format_utc_and_chicago(result.session_end_utc)[1]}")
        lines.append(f"  Dataset ends before session end: {yes_no(result.dataset_ends_before_session_end)}")
    lines.append("")

    if result.profile is None:
        lines += [
            "No retained trades exist at or after the requested anchor.",
            "No VWAP, Volume Profile, POC, or Value Area was calculated.",
        ]
        return "\n".join(lines)

    profile = result.profile
    value_area = result.value_area

    lines += [
        "Selected Effective Tape:",
        f"  Trades: {result.selected_trade_count:,}",
        f"  Volume: {result.selected_volume}",
        f"  Corrections applied: {result.applied_correction_count}",
        f"  Cancels applied:     {result.applied_cancel_count}",
        "",
        "VWAP:",
        f"  {result.vwap}",
        "",
        "Volume Profile:",
        f"  Low:  {profile.lowest_price}",
        f"  High: {profile.highest_price}",
        f"  Occupied levels: {len(profile.levels)}",
        f"  Tick size: {result.tick_size}",
    ]
    if result.invalid_tick_trade_count:
        lines.append(f"  Invalid tick-grid trades (excluded): {result.invalid_tick_trade_count}")
    lines.append("")

    lines += [
        "Point of Control:",
        f"  Price: {profile.point_of_control.price}",
        f"  Volume: {profile.point_of_control.volume}",
        f"  Prints: {profile.point_of_control.trade_count}",
        "",
    ]

    if value_area is not None:
        lines += [
            "Value Area:",
            f"  Target: {value_area.target_fraction * 100}%",
            f"  Actual: {value_area.included_fraction * 100}%",
            f"  VAL: {value_area.value_area_low.price}",
            f"  VAH: {value_area.value_area_high.price}",
            f"  Included levels: {value_area.included_level_count}",
            "",
        ]

    ranked = sorted(profile.levels, key=lambda level: (-level.volume, level.price))[:top_levels]
    lines.append(f"Top {len(ranked)} Volume Levels (ranked by volume desc, then price asc):")
    for level in ranked:
        lines.append(f"  {level.price}   {level.volume}   ({level.trade_count} prints)")
    lines.append("")

    if result.differs_from_canonical is not None:
        lines += [
            "Canonical NEW-only comparison:",
            f"  Differs from effective tape: {yes_no(result.differs_from_canonical)}",
            "",
        ]

    if result.reconstruction_anomaly_count:
        lines += [
            "Reconstruction anomalies:",
            f"  {result.reconstruction_anomaly_count} {result.reconstruction_anomaly_counts_by_reason}",
            "",
        ]

    lines += [
        "Interpretation Boundary:",
        f"  Captured-data developing {anchor_label_slug(result.anchor_kind)} Volume Profile.",
        "  Retained captured observations only; not a completed full-session profile.",
        "  Ordinary CME schedule only; holiday/early-close overrides not modeled.",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    app()
