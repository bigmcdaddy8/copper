"""captains_log CLI — query the trade journal."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="captains_log",
    help="Trade journal — query and inspect recorded trades.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def callback() -> None:
    """captains_log — Trade journal for the automated trading system."""


@app.command(name="list")
def list_trades(
    date: str = typer.Option(
        None, "--date", help="Filter by date (YYYY-MM-DD, today, yesterday, tomorrow)."
    ),
    from_date: str = typer.Option(
        None,
        "--from",
        help="Filter from date inclusive (YYYY-MM-DD, today, yesterday, tomorrow).",
    ),
    to_date: str = typer.Option(
        None,
        "--to",
        help="Filter to date inclusive (YYYY-MM-DD, today, yesterday, tomorrow).",
    ),
    outcome: str = typer.Option(
        None, "--outcome", help="Filter by outcome (FILLED, SKIPPED, etc.)."
    ),
    spec: str = typer.Option(
        None, "--spec", help="Filter by spec name."
    ),
    account: str = typer.Option(
        "TRD", "--account", "-a", help="Account DB to query (TRD, TRDS, HD)."
    ),
) -> None:
    """List recorded trades, most recent first."""
    from captains_log.journal import Journal

    if date and (from_date or to_date):
        raise typer.BadParameter("Use either --date or --from/--to, not both")

    normalized_date = _normalize_date_filter(date, option_name="--date")
    normalized_from = _normalize_date_filter(from_date, option_name="--from")
    normalized_to = _normalize_date_filter(to_date, option_name="--to")

    if normalized_from and normalized_to and normalized_from > normalized_to:
        raise typer.BadParameter("--from must be <= --to")

    trades = Journal(account=account).list_trades(
        date=normalized_date,
        date_from=normalized_from,
        date_to=normalized_to,
        outcome=outcome,
        spec_name=spec,
    )

    if not trades:
        console.print("[dim]No trades found.[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("ID", style="dim", width=9)
    tbl.add_column("Legacy #")
    tbl.add_column("Spec")
    tbl.add_column("Outcome")
    tbl.add_column("Underlying")
    tbl.add_column("Expiration")
    tbl.add_column("Credit", justify="right")
    tbl.add_column("TP Status")
    tbl.add_column("Entered At")

    _OUTCOME_STYLE = {
        "FILLED":   "bold green",
        "SKIPPED":  "yellow",
        "CANCELED": "yellow",
        "REJECTED": "bold red",
        "ERROR":    "bold red",
    }

    for t in trades:
        style = _OUTCOME_STYLE.get(t.outcome, "white")
        credit = f"{t.net_credit:.2f}" if t.net_credit is not None else "—"
        tbl.add_row(
            t.trade_id[:8],
            t.legacy_trade_num or "—",
            t.spec_name,
            f"[{style}]{t.outcome}[/{style}]",
            t.underlying,
            t.expiration or "—",
            credit,
            t.tp_status,
            t.entered_at[:19].replace("T", " "),
        )

    console.print(tbl)
    console.print(f"[dim]{len(trades)} record(s)[/dim]")


def _normalize_date_filter(value: str | None, option_name: str) -> str | None:
    """Normalize human-friendly date filters to ISO YYYY-MM-DD."""
    if value is None:
        return None

    token = value.strip().lower()
    if token == "today":
        return datetime.now(timezone.utc).date().isoformat()
    if token == "yesterday":
        return (datetime.now(timezone.utc).date() - timedelta(days=1)).isoformat()
    if token == "tomorrow":
        return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()

    try:
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError as exc:
        raise typer.BadParameter(
            f"{option_name} must be YYYY-MM-DD, today, yesterday, or tomorrow"
        ) from exc


@app.command(name="show")
def show_trade(
    trade_id: str = typer.Argument(..., help="Trade ID (or prefix) to display."),
    account: str = typer.Option(
        "TRD", "--account", "-a", help="Account DB to query (TRD, TRDS, HD)."
    ),
) -> None:
    """Show all fields for a single trade record."""
    from captains_log.journal import Journal

    journal = Journal(account=account)

    # Try exact match first, then prefix search
    trade = journal.get_trade(trade_id)
    if trade is None:
        all_trades = journal.list_trades()
        matches = [t for t in all_trades if t.trade_id.startswith(trade_id)]
        if len(matches) == 1:
            trade = matches[0]
        elif len(matches) > 1:
            console.print(
                f"[yellow]Ambiguous prefix '{trade_id}' matches {len(matches)} records.[/yellow]"
            )
            raise typer.Exit(1)

    if trade is None:
        console.print(f"[bold red]Trade not found: {trade_id}[/bold red]")
        raise typer.Exit(1)

    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Field", style="bold dim", min_width=22)
    tbl.add_column("Value")

    rows = [
        ("trade_id",            trade.trade_id),
        ("legacy_trade_num",    trade.legacy_trade_num or "—"),
        ("account",             trade.account),
        ("spec_name",           trade.spec_name),
        ("environment",         trade.environment),
        ("underlying",          trade.underlying),
        ("trade_type",          trade.trade_type),
        ("expiration",          trade.expiration or "—"),
        ("outcome",             trade.outcome),
        ("reason",              trade.reason or "—"),
        ("errors",              ", ".join(trade.errors) if trade.errors else "—"),
        ("short_put_strike",    str(trade.short_put_strike) if trade.short_put_strike else "—"),
        ("long_put_strike",     str(trade.long_put_strike) if trade.long_put_strike else "—"),
        ("short_call_strike",   str(trade.short_call_strike) if trade.short_call_strike else "—"),
        ("long_call_strike",    str(trade.long_call_strike) if trade.long_call_strike else "—"),
        ("entry_order_id",      trade.entry_order_id or "—"),
        ("entry_filled_price",  f"{trade.entry_filled_price:.2f}" if trade.entry_filled_price else "—"),
        ("net_credit",          f"{trade.net_credit:.2f}" if trade.net_credit else "—"),
        ("tp_order_id",         trade.tp_order_id or "—"),
        ("tp_limit_price",      f"{trade.tp_limit_price:.2f}" if trade.tp_limit_price else "—"),
        ("tp_status",           trade.tp_status),
        ("tp_fill_price",       f"{trade.tp_fill_price:.2f}" if trade.tp_fill_price else "—"),
        ("realized_pnl",        f"{trade.realized_pnl:.2f}" if trade.realized_pnl is not None else "—"),
        ("entered_at",          trade.entered_at),
    ]
    for label, value in rows:
        tbl.add_row(label, value)

    console.print(tbl)
