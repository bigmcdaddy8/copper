"""Read-only, offline Developing Profile Timeline over a durable Dick's Laboratory dataset.

Exposes the accepted 0R cumulative VWAP / Volume-at-Price / POC / Value Area
time series as a human-facing checkpoint table. Computes nothing new: every
row is a direct view of one `DevelopingProfileSnapshot` produced by the
accepted `build_developing_profile_series` service.
"""
from __future__ import annotations

from pathlib import Path
from uuid import UUID

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.cli_support import (
    ANCHOR_LABELS,
    format_timedelta,
    format_utc_and_chicago,
    parse_anchor_argument,
    parse_trading_date_argument,
    yes_no,
)
from dicks_laboratory.developing_profile import (
    DevelopingProfileSeries,
    DevelopingProfileSnapshot,
    SliceInterval,
    build_developing_profile_series,
)

app = typer.Typer(add_completion=False)

_INTERVAL_CHOICES: dict[str, SliceInterval] = {
    "1m": SliceInterval.ONE_MINUTE,
    "5m": SliceInterval.FIVE_MINUTES,
    "15m": SliceInterval.FIFTEEN_MINUTES,
}
_SOURCE_CHOICES: dict[str, VwapSourceMode] = {
    "effective": VwapSourceMode.EFFECTIVE_TAPE,
    "canonical": VwapSourceMode.CANONICAL_NEW_ONLY,
}


@app.command()
def analyze(
    database_path: Path = typer.Argument(..., help="Path to a durable Dick's Laboratory SQLite dataset."),
    anchor: str = typer.Option(
        ...,
        "--anchor",
        help="'session-open', 'cash-open', or an explicit aware UTC timestamp (e.g. 2026-08-24T14:15:00Z).",
    ),
    interval: str = typer.Option("5m", "--interval", help="'1m', '5m', or '15m'. Default '5m'."),
    source: str = typer.Option("effective", "--source", help="'effective' (default) or 'canonical'."),
    trading_date: str | None = typer.Option(
        None, "--trading-date", help="YYYY-MM-DD; required only when the dataset spans multiple trading dates."
    ),
    dataset_id: str | None = typer.Option(
        None, "--dataset-id", help="Required only when the database contains multiple datasets."
    ),
) -> None:
    """Print a factual developing VWAP/POC/Value-Area timeline computed only from retained trades."""
    anchor_kind, custom_timestamp = parse_anchor_argument(anchor)
    parsed_trading_date = parse_trading_date_argument(trading_date)
    parsed_dataset_id = UUID(dataset_id) if dataset_id else None
    slice_interval = _parse_interval(interval)
    source_mode = _parse_source(source)

    try:
        store = open_dataset_store(database_path)
        try:
            resolved_dataset_id = resolve_dataset_id(store, parsed_dataset_id)
            series = build_developing_profile_series(
                store, resolved_dataset_id, anchor_kind, parsed_trading_date, custom_timestamp, slice_interval, source_mode
            )
        finally:
            store.close()
    except LaboratoryAnalysisError as exc:
        typer.echo(f"Analysis error: {exc}", err=True)
        raise typer.Exit(code=2) from exc

    typer.echo(_render_report(series))
    if not series.snapshots:
        raise typer.Exit(code=1)


def _parse_interval(value: str) -> SliceInterval:
    interval = _INTERVAL_CHOICES.get(value)
    if interval is None:
        raise typer.BadParameter(f"Invalid --interval: {value!r}. Use '1m', '5m', or '15m'.")
    return interval


def _parse_source(value: str) -> VwapSourceMode:
    source_mode = _SOURCE_CHOICES.get(value)
    if source_mode is None:
        raise typer.BadParameter(f"Invalid --source: {value!r}. Use 'effective' or 'canonical'.")
    return source_mode


def _interval_label(slice_interval: SliceInterval) -> str:
    minutes = slice_interval.minutes
    return f"{minutes} minute" + ("s" if minutes != 1 else "")


def _source_label(source_mode: VwapSourceMode) -> str:
    if source_mode is VwapSourceMode.EFFECTIVE_TAPE:
        return "Effective tape"
    return "Canonical NEW-only"


def _render_report(series: DevelopingProfileSeries) -> str:
    lines = ["Dick's Laboratory -- Developing Profile Timeline", ""]
    lines += ["Dataset:", f"  {series.dataset_id}", ""]
    lines += ["Instrument:", f"  {series.instrument.canonical_id}", ""]
    if series.trading_date is not None:
        lines += ["Trading date:", f"  {series.trading_date.isoformat()}", ""]
    lines += [
        "Anchor:",
        f"  {ANCHOR_LABELS[series.anchor_kind]}",
        f"  Chicago: {format_utc_and_chicago(series.anchor_timestamp_utc)[1]}",
        f"  UTC:     {format_utc_and_chicago(series.anchor_timestamp_utc)[0]}",
        "",
    ]
    lines += ["Slice interval:", f"  {_interval_label(series.slice_interval)}", ""]
    lines += ["Source:", f"  {_source_label(series.source_mode)}"]
    if series.source_mode is VwapSourceMode.EFFECTIVE_TAPE:
        lines += [
            "  Retrospectively reconstructed using the final accepted",
            "  NEW/CORRECTION/CANCEL lifecycle state -- not what the feed",
            "  had told us by each historical instant.",
        ]
    lines.append("")

    lines += [
        "Coverage:",
        f"  {series.coverage.value}",
        "",
        "  First retained:",
        f"    {format_utc_and_chicago(series.dataset_first_trade_timestamp)[1]}",
        f"    {format_utc_and_chicago(series.dataset_first_trade_timestamp)[0]}",
        "  Last retained:",
        f"    {format_utc_and_chicago(series.dataset_last_trade_timestamp)[1]}",
        f"    {format_utc_and_chicago(series.dataset_last_trade_timestamp)[0]}",
    ]
    if series.unobserved_pre_capture_interval is not None:
        lines.append(f"  Unobserved pre-capture interval: {format_timedelta(series.unobserved_pre_capture_interval)}")
    if series.session_end_utc is not None:
        lines.append(f"  Dataset ends before session end: {yes_no(series.dataset_ends_before_session_end)}")
    lines.append("")

    if not series.snapshots:
        lines += [
            "No retained trades exist at or after the requested anchor.",
            "No developing profile timeline can be computed.",
        ]
        return "\n".join(lines)

    if series.dataset_begins_after_anchor:
        lines += [
            "No timeline rows are emitted before the first retained observation.",
            "The unobserved pre-capture interval must not be interpreted as zero market activity.",
            "",
        ]

    lines += _render_table(series)
    lines.append("")
    lines += [
        "Each row is cumulative from the requested anchor.",
        "This is not a rolling-window profile.",
        "Zero new retained trades in a row does not prove zero market activity.",
        "",
    ]

    terminal = series.snapshots[-1]
    lines += [
        "Terminal retained state:",
        f"  Trades: {terminal.cumulative_trade_count:,}",
        f"  Volume: {terminal.cumulative_volume}",
        "",
        "  Terminal exact VWAP:",
        f"    {terminal.vwap}",
        "",
        f"  POC: {terminal.poc_price}",
        f"  VAL: {terminal.val}",
        f"  VAH: {terminal.vah}",
        "",
    ]

    lines += [
        "Interpretation boundary:",
        "  - retained observations only",
        "  - cumulative from requested anchor",
        "  - not a rolling profile",
        "  - ordinary CME schedule only",
        "  - no claim of complete tape",
    ]
    if series.source_mode is VwapSourceMode.EFFECTIVE_TAPE:
        lines.append("  - effective timeline is retrospective, not point-in-time feed knowledge")
    return "\n".join(lines)


def _render_table(series: DevelopingProfileSeries) -> list[str]:
    header = f"{'Time':<8}{'New':>6}{'Cum':>8}{'Volume':>12}{'VWAP':>12}{'POC':>10}{'VAL':>10}{'VAH':>10}"
    lines = [header]
    terminal_snapshot: DevelopingProfileSnapshot | None = None
    for snapshot in series.snapshots:
        time_ct = format_utc_and_chicago(snapshot.slice_end_utc)[1].split(" ")[1][:5]
        marker = "*" if snapshot.terminal_snapshot else ""
        time_label = f"{time_ct}{marker}"
        vwap_display = f"{snapshot.vwap:.4f}" if snapshot.vwap is not None else "n/a"
        poc_display = f"{snapshot.poc_price}" if snapshot.poc_price is not None else "n/a"
        val_display = f"{snapshot.val}" if snapshot.val is not None else "n/a"
        vah_display = f"{snapshot.vah}" if snapshot.vah is not None else "n/a"
        volume_display = f"{snapshot.cumulative_volume}" if snapshot.cumulative_volume is not None else "n/a"
        lines.append(
            f"{time_label:<8}{snapshot.new_trade_count:>6}{snapshot.cumulative_trade_count:>8}"
            f"{volume_display:>12}{vwap_display:>12}{poc_display:>10}{val_display:>10}{vah_display:>10}"
        )
        if snapshot.terminal_snapshot:
            terminal_snapshot = snapshot
    if terminal_snapshot is not None:
        last_included = terminal_snapshot.last_included_trade_timestamp
        if last_included is not None:
            last_ct = format_utc_and_chicago(last_included)[1].split(" ")[1][:12]
            lines.append(f"* terminal analytical cutoff; last retained trade was {last_ct} CT")
    return lines


if __name__ == "__main__":
    app()
