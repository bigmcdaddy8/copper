"""Read-only, offline, headless static visualization of the accepted 0R developing
profile series (Phase 0T).

Renders exactly the same `DevelopingProfileSeries` values already proven in
0R and shown textually in 0S -- no new analytics, no interpolation between
checkpoints, no trading interpretation. Decimal analytical truth is
converted to float only at this rendering boundary; the domain models
(`developing_profile.py`, `developing_profile_plot_data.py`) never import a
plotting library.
"""
from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")  # headless, non-interactive backend -- no display server required

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.anchored_vwap import VwapSourceMode
from dicks_laboratory.cli_support import (
    ANCHOR_LABELS,
    format_timedelta,
    format_utc_and_chicago,
    parse_anchor_argument,
    parse_trading_date_argument,
)
from dicks_laboratory.developing_profile import SliceInterval, build_developing_profile_series
from dicks_laboratory.developing_profile_plot_data import (
    DevelopingProfilePlotData,
    build_developing_profile_plot_data,
)

app = typer.Typer(add_completion=False)
_CHICAGO = ZoneInfo("America/Chicago")

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
def plot(
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
    output: Path | None = typer.Option(
        None, "--output", help="Output PNG path. Defaults to a descriptive filename next to the input database."
    ),
    overwrite: bool = typer.Option(False, "--overwrite", help="Allow overwriting an existing output file."),
) -> None:
    """Render a static PNG of cumulative VWAP/POC/VAL/VAH through the developing checkpoints."""
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

    plot_data = build_developing_profile_plot_data(series)

    if not plot_data.points:
        typer.echo("No retained trades exist at or after the requested anchor.")
        typer.echo("No developing profile visualization can be produced.")
        raise typer.Exit(code=1)

    output_path = output if output is not None else _default_output_path(database_path, plot_data, slice_interval)
    if output_path.exists() and not overwrite:
        typer.echo(f"Output already exists: {output_path}. Pass --overwrite to replace it.", err=True)
        raise typer.Exit(code=2)

    _render_figure(plot_data, output_path)
    typer.echo(f"Wrote {output_path}")


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


def _default_output_path(database_path: Path, plot_data: DevelopingProfilePlotData, slice_interval: SliceInterval) -> Path:
    interval_slug = {SliceInterval.ONE_MINUTE: "1m", SliceInterval.FIVE_MINUTES: "5m", SliceInterval.FIFTEEN_MINUTES: "15m"}[
        slice_interval
    ]
    date_slug = plot_data.trading_date.isoformat() if plot_data.trading_date is not None else "unknown-date"
    return Path(database_path).parent / f"developing_profile_{date_slug}_{interval_slug}.png"


def _interval_label(slice_interval: SliceInterval) -> str:
    minutes = slice_interval.minutes
    return f"{minutes}-minute"


def _source_label(source_mode: VwapSourceMode) -> str:
    return "Effective tape" if source_mode is VwapSourceMode.EFFECTIVE_TAPE else "Canonical NEW-only"


def _render_figure(plot_data: DevelopingProfilePlotData, output_path: Path) -> None:
    """Convert exact Decimal/datetime values to float/matplotlib coordinates only here."""
    times = [point.slice_end_utc for point in plot_data.points]
    vwap = [float(point.vwap) if point.vwap is not None else None for point in plot_data.points]
    poc = [float(point.poc_price) if point.poc_price is not None else None for point in plot_data.points]
    val = [float(point.val) if point.val is not None else None for point in plot_data.points]
    vah = [float(point.vah) if point.vah is not None else None for point in plot_data.points]

    fig, ax = plt.subplots(figsize=(10, 6))

    # VWAP: a normal connected line -- exact checkpoints only, the connecting
    # segment is a visual aid, not a claim of interpolated intermediate data.
    ax.plot(times, vwap, label="VWAP", color="tab:blue", marker="o", linewidth=1.5, zorder=3)
    # POC/VAL/VAH are discrete derived price levels held between checkpoints;
    # a post-step draws each value as constant from its own checkpoint until
    # the next one, rather than implying continuous interpolation.
    ax.step(times, poc, where="post", label="POC", color="tab:orange", marker="o", linewidth=1.5, linestyle="--", zorder=2)
    ax.step(times, val, where="post", label="VAL", color="tab:green", marker="s", linewidth=1.0, linestyle=":", zorder=1)
    ax.step(times, vah, where="post", label="VAH", color="tab:red", marker="s", linewidth=1.0, linestyle=":", zorder=1)

    terminal_index = next(i for i, point in enumerate(plot_data.points) if point.terminal_snapshot)
    terminal_point = plot_data.points[terminal_index]
    ax.plot(
        [times[terminal_index]], [vwap[terminal_index]],
        marker="D", markersize=11, markerfacecolor="none", markeredgecolor="black", markeredgewidth=1.5,
        linestyle="none", label="Terminal cutoff", zorder=4,
    )
    ax.axvline(times[terminal_index], color="black", linestyle="--", linewidth=0.8, alpha=0.5)

    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M\n%b %d", tz=_CHICAGO))
    fig.autofmt_xdate()
    ax.set_xlabel("Time (America/Chicago)")
    ax.set_ylabel("Price")
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)

    title = "Dick's Laboratory -- Developing Profile"
    subtitle = (
        f"{plot_data.instrument.canonical_id}"
        + (f"  |  Trading date {plot_data.trading_date.isoformat()}" if plot_data.trading_date else "")
        + f"  |  {_interval_label(plot_data.slice_interval)} checkpoints  |  {_source_label(plot_data.source_mode)}"
    )
    fig.suptitle(title, fontsize=13)
    ax.set_title(subtitle, fontsize=9)

    footer_lines = [
        f"Anchor: {ANCHOR_LABELS[plot_data.anchor_kind]} ({format_utc_and_chicago(plot_data.anchor_timestamp_utc)[1]})",
        f"Coverage: {plot_data.coverage.value}",
    ]
    if plot_data.unobserved_pre_capture_interval is not None:
        footer_lines.append(
            f"Unobserved pre-capture interval: {format_timedelta(plot_data.unobserved_pre_capture_interval)}"
            f" (first retained {format_utc_and_chicago(plot_data.dataset_first_trade_timestamp)[1]})"
        )
    last_included = terminal_point.last_included_trade_timestamp
    if last_included is not None:
        footer_lines.append(f"Terminal cutoff marks the checkpoint boundary; last retained trade was {format_utc_and_chicago(last_included)[1]}")
    footer_lines.append("Cumulative from requested anchor; not a rolling window.")
    if plot_data.source_mode is VwapSourceMode.EFFECTIVE_TAPE:
        footer_lines.append("Effective tape is retrospectively reconstructed (final accepted lifecycle state, not point-in-time feed knowledge).")

    fig.text(0.01, 0.01, "\n".join(footer_lines), fontsize=7, va="bottom", ha="left")
    fig.subplots_adjust(bottom=0.28)

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        fig.savefig(tmp_path, dpi=150, format="png")
    finally:
        plt.close(fig)
    os.replace(tmp_path, output_path)


if __name__ == "__main__":
    app()
