"""encyclopedia_galactica CLI — reporting and accounting for the trading system."""
from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(
    name="enc",
    help="encyclopedia_galactica — trade reporting and accounting.",
    no_args_is_help=True,
)
report_app = typer.Typer(help="Scheduled report commands.", no_args_is_help=True)
app.add_typer(report_app, name="report")
console = Console()

_ACCOUNT_OPTION = typer.Option("TRD", "--account", "-a", help="Account (TRD, TRDS, HD).")

_OUTCOME_STYLE = {
    "FILLED":   "bold green",
    "SKIPPED":  "yellow",
    "CANCELED": "yellow",
    "REJECTED": "bold red",
    "ERROR":    "bold red",
}


def _fmt(val: float | None, decimals: int = 2) -> str:
    return f"{val:.{decimals}f}" if val is not None else "—"


# ── enc trades ────────────────────────────────────────────────────────────────

@app.command(name="trades")
def trades_cmd(
    account: str = _ACCOUNT_OPTION,
    status: str = typer.Option(None, "--status", "-s", help="Filter by outcome."),
    env: str = typer.Option(None, "--env", "-e", help="Filter by environment."),
) -> None:
    """List all trades for an account."""
    from encyclopedia_galactica.reader import Reader

    records = Reader(account=account).all_trades(outcome=status, environment=env)

    if not records:
        console.print("[dim]No trades found.[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold")
    tbl.add_column("Account")
    tbl.add_column("Trade ID", style="dim", width=9)
    tbl.add_column("Legacy #")
    tbl.add_column("Outcome")
    tbl.add_column("Underlying")
    tbl.add_column("Expiration")
    tbl.add_column("Credit", justify="right")
    tbl.add_column("P/L", justify="right")
    tbl.add_column("Entered At")

    for t in records:
        style = _OUTCOME_STYLE.get(t.outcome, "white")
        pnl = _fmt(t.realized_pnl)
        if t.realized_pnl is not None:
            pnl_style = "green" if t.realized_pnl >= 0 else "red"
            pnl = f"[{pnl_style}]{pnl}[/{pnl_style}]"
        tbl.add_row(
            t.account,
            t.trade_id[:8],
            t.legacy_trade_num or "—",
            f"[{style}]{t.outcome}[/{style}]",
            t.underlying,
            t.expiration or "—",
            _fmt(t.net_credit),
            pnl,
            t.entered_at[:19].replace("T", " "),
        )

    console.print(tbl)
    console.print(f"[dim]{len(records)} record(s)[/dim]")


# ── enc pnl ───────────────────────────────────────────────────────────────────

@app.command(name="pnl")
def pnl_cmd(
    account: str = _ACCOUNT_OPTION,
    month: str = typer.Option(None, "--month", "-m", help="Filter to a single month (YYYY-MM)."),
    year: str = typer.Option(None, "--year", "-y", help="Filter to a single year (YYYY)."),
) -> None:
    """Show realized P/L summary, grouped by month."""
    from encyclopedia_galactica.reader import Reader, group_by_month, group_by_year, pnl_stats

    reader = Reader(account=account)
    trades = reader.filled_trades()

    if month:
        trades = [t for t in trades if t.entered_at.startswith(month)]
    elif year:
        trades = [t for t in trades if t.entered_at.startswith(year)]

    if not trades:
        console.print("[dim]No filled trades found.[/dim]")
        return

    groups = group_by_month(trades)

    tbl = Table(show_header=True, header_style="bold", title=f"P/L Summary — {account}")
    tbl.add_column("Month")
    tbl.add_column("Trades", justify="right")
    tbl.add_column("Total P/L", justify="right")
    tbl.add_column("Avg", justify="right")
    tbl.add_column("Median", justify="right")
    tbl.add_column("Best", justify="right")
    tbl.add_column("Worst", justify="right")

    overall: list[float] = []
    for m, group in groups.items():
        s = pnl_stats(group)
        if s["total"] is not None:
            overall.append(s["total"])
        total_style = "green" if (s["total"] or 0) >= 0 else "red"
        tbl.add_row(
            m,
            str(s["pnl_count"]),
            f"[{total_style}]{_fmt(s['total'])}[/{total_style}]",
            _fmt(s["avg"]),
            _fmt(s["median"]),
            f"[green]{_fmt(s['best'])}[/green]" if s["best"] is not None else "—",
            f"[red]{_fmt(s['worst'])}[/red]" if s["worst"] is not None else "—",
        )

    console.print(tbl)

    if overall:
        total_all = sum(overall)
        sign = "green" if total_all >= 0 else "red"
        console.print(
            f"[bold]Total: [{sign}]{_fmt(total_all)}[/{sign}][/bold]  "
            f"across {len(trades)} filled trade(s)"
        )


# ── enc report monthly ────────────────────────────────────────────────────────

@report_app.command(name="monthly")
def report_monthly(
    account: str = _ACCOUNT_OPTION,
) -> None:
    """Snapshot all months for an account into the report store."""
    from encyclopedia_galactica.reader import Reader, group_by_month, pnl_stats
    from encyclopedia_galactica.store import Store

    reader = Reader(account=account)
    trades = reader.filled_trades()
    store = Store()

    if not trades:
        console.print(f"[yellow]No filled trades found for account {account}.[/yellow]")
        return

    groups = group_by_month(trades)
    for m, group in groups.items():
        stats = pnl_stats(group)
        store.upsert_monthly(account=account, month=m, stats=stats)
        console.print(f"[dim]  Saved {account} / {m}: {stats['pnl_count']} trades, total={_fmt(stats['total'])}[/dim]")

    console.print(f"[bold green]Monthly report saved — {len(groups)} month(s) for {account}.[/bold green]")


@report_app.command(name="yearly")
def report_yearly(
    account: str = _ACCOUNT_OPTION,
) -> None:
    """Snapshot all years for an account into the report store."""
    from encyclopedia_galactica.reader import Reader, group_by_year, pnl_stats
    from encyclopedia_galactica.store import Store

    reader = Reader(account=account)
    trades = reader.filled_trades()
    store = Store()

    if not trades:
        console.print(f"[yellow]No filled trades found for account {account}.[/yellow]")
        return

    groups = group_by_year(trades)
    for y, group in groups.items():
        stats = pnl_stats(group)
        store.upsert_yearly(account=account, year=y, stats=stats)
        console.print(f"[dim]  Saved {account} / {y}: {stats['pnl_count']} trades, total={_fmt(stats['total'])}[/dim]")

    console.print(f"[bold green]Yearly report saved — {len(groups)} year(s) for {account}.[/bold green]")


@report_app.command(name="show")
def report_show(
    period: str = typer.Argument(..., help="Period type: monthly or yearly"),
    account: str = _ACCOUNT_OPTION,
) -> None:
    """Display stored report history for an account."""
    from encyclopedia_galactica.store import Store

    store = Store()

    if period == "monthly":
        rows = store.list_monthly(account=account)
        period_col = "Month"
        period_key = "month"
    elif period == "yearly":
        rows = store.list_yearly(account=account)
        period_col = "Year"
        period_key = "year"
    else:
        console.print(f"[red]Unknown period '{period}'. Use 'monthly' or 'yearly'.[/red]")
        raise typer.Exit(1)

    if not rows:
        console.print(f"[dim]No {period} reports found for {account}.[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold", title=f"{period.title()} Reports — {account}")
    tbl.add_column(period_col)
    tbl.add_column("Trades", justify="right")
    tbl.add_column("Total P/L", justify="right")
    tbl.add_column("Avg", justify="right")
    tbl.add_column("Median", justify="right")
    tbl.add_column("Best", justify="right")
    tbl.add_column("Worst", justify="right")
    tbl.add_column("Generated At", style="dim")

    for r in rows:
        total = r["total_pnl"]
        sign = "green" if (total or 0) >= 0 else "red"
        tbl.add_row(
            r[period_key],
            str(r["pnl_count"]),
            f"[{sign}]{_fmt(total)}[/{sign}]",
            _fmt(r["avg_pnl"]),
            _fmt(r["median_pnl"]),
            f"[green]{_fmt(r['best_pnl'])}[/green]" if r["best_pnl"] is not None else "—",
            f"[red]{_fmt(r['worst_pnl'])}[/red]" if r["worst_pnl"] is not None else "—",
            r["generated_at"][:19].replace("T", " "),
        )

    console.print(tbl)

    # Summary footer for monthly view
    if period == "monthly":
        totals = [r["total_pnl"] for r in rows if r["total_pnl"] is not None]
        if totals:
            grand = sum(totals)
            sign = "green" if grand >= 0 else "red"
            console.print(f"[bold]Grand total: [{sign}]{_fmt(grand)}[/{sign}][/bold]")


# ── enc reset ─────────────────────────────────────────────────────────────────

@app.command(name="reset")
def reset_cmd(
    account: str = typer.Argument(..., help="Account to reset report data for (e.g. HD)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
) -> None:
    """Delete all stored report data for an account (intended for HD resets)."""
    from encyclopedia_galactica.store import Store

    if not yes:
        confirm = typer.confirm(
            f"Delete all stored report data for account '{account}'?", default=False
        )
        if not confirm:
            console.print("[dim]Aborted.[/dim]")
            raise typer.Exit(0)

    Store().reset_account(account=account)
    console.print(f"[bold yellow]Report data for '{account}' has been cleared.[/bold yellow]")
