"""Read-only, offline anchored-VWAP analysis over a durable Dick's Laboratory dataset."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import typer

from dicks_laboratory.analysis import (
    LaboratoryAnalysisError,
    VwapAnalysisResult,
    analyze_anchored_vwap_dataset,
    open_dataset_store,
    resolve_dataset_id,
)
from dicks_laboratory.sessions import AnchorKind

app = typer.Typer(add_completion=False)
_CT = ZoneInfo("America/Chicago")

_ANCHOR_LABELS = {
    AnchorKind.SESSION_OPEN: "CME equity-index session open",
    AnchorKind.US_CASH_OPEN: "US cash session open",
    AnchorKind.CUSTOM_TIMESTAMP: "Custom UTC anchor",
}


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
    anchor_kind, custom_timestamp = _parse_anchor(anchor)
    parsed_trading_date = _parse_trading_date(trading_date)
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


def _parse_anchor(value: str) -> tuple[AnchorKind, datetime | None]:
    if value == "session-open":
        return AnchorKind.SESSION_OPEN, None
    if value == "cash-open":
        return AnchorKind.US_CASH_OPEN, None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Invalid --anchor: {value!r}. Use 'session-open', 'cash-open', or an aware UTC timestamp."
        ) from exc
    if parsed.tzinfo is None:
        raise typer.BadParameter("Custom --anchor timestamps must be timezone-aware UTC (e.g. 2026-08-24T14:15:00Z).")
    return AnchorKind.CUSTOM_TIMESTAMP, parsed.astimezone(timezone.utc)


def _parse_trading_date(value: str | None) -> date | None:
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid --trading-date: {value!r}. Use YYYY-MM-DD.") from exc


def _render_report(result: VwapAnalysisResult) -> str:
    lines = ["Dick's Laboratory -- Anchored VWAP Analysis", ""]
    lines += ["Dataset:", f"  {result.dataset_id}", ""]
    lines += ["Instrument:", f"  {result.instrument.canonical_id}", ""]
    if result.trading_date is not None:
        lines += ["Trading date:", f"  {result.trading_date.isoformat()}", ""]
    lines += [
        "Anchor:",
        f"  {_ANCHOR_LABELS[result.anchor_kind]}",
        f"  Chicago: {_both(result.anchor_timestamp_utc)[1]}",
        f"  UTC:     {_both(result.anchor_timestamp_utc)[0]}",
        "",
    ]
    lines += [
        "Retained dataset:",
        f"  First trade: {_both(result.dataset_first_trade_timestamp)[1]}",
        f"  Last trade:  {_both(result.dataset_last_trade_timestamp)[1]}",
        "",
    ]
    lines += ["Coverage:", f"  {result.coverage.value}", f"  Dataset begins after requested anchor: {_yes_no(result.dataset_begins_after_anchor)}"]
    if result.unobserved_pre_capture_interval is not None:
        lines.append(f"  Unobserved pre-capture interval: {_format_timedelta(result.unobserved_pre_capture_interval)}")
    if result.session_end_utc is not None:
        lines.append(f"  Session end (Chicago): {_both(result.session_end_utc)[1]}")
        lines.append(f"  Dataset ends before session end: {_yes_no(result.dataset_ends_before_session_end)}")
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
    lines += ["", "Label:", f"  Captured-data developing {_anchor_label_slug(result)} anchored VWAP"]
    return "\n".join(lines)


def _anchor_label_slug(result: VwapAnalysisResult) -> str:
    if result.anchor_kind is AnchorKind.SESSION_OPEN:
        return "session-open"
    if result.anchor_kind is AnchorKind.US_CASH_OPEN:
        return "cash-open"
    return "custom-anchor"


def _both(timestamp: datetime) -> tuple[str, str]:
    utc_text = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    ct_text = timestamp.astimezone(_CT).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " America/Chicago"
    return utc_text, ct_text


def _yes_no(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "YES" if value else "no"


def _format_timedelta(delta) -> str:
    total_seconds = Decimal(str(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, Decimal(3600))
    minutes, seconds = divmod(remainder, Decimal(60))
    return f"{int(hours)}h {int(minutes)}m {seconds:.3f}s"


if __name__ == "__main__":
    app()
