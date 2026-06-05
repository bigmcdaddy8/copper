"""encyclopedia_galactica CLI — reporting and accounting for the trading system."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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


def _mdy(iso_dt: str | None) -> str:
    if not iso_dt:
        return "—"
    return iso_dt[5:7] + "/" + iso_dt[8:10] + "/" + iso_dt[0:4]


def _fmt_metric(val: float | str | None, decimals: int = 2) -> str:
    if isinstance(val, str):
        return val
    if val is None:
        return "—"
    return f"{val:.{decimals}f}"


def _to_ct(iso_dt: str | None) -> str:
    if not iso_dt:
        return "—"
    dt = datetime.fromisoformat(iso_dt)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d %H:%M:%S %Z")


def _parse_yyyy_mm_dd(value: str, option_name: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise typer.BadParameter(f"{option_name} must be YYYY-MM-DD") from exc


def _entry_date(iso_dt: str) -> str:
    return iso_dt[:10]


def _credit_dollars(trade) -> float | None:
    qty = trade.quantity or 1
    if trade.credit_received is not None:
        return float(trade.credit_received)
    if trade.net_credit is not None:
        return round(float(trade.net_credit) * 100 * qty, 2)
    if trade.entry_filled_price is not None:
        return round(abs(float(trade.entry_filled_price) * 100 * qty), 2)
    return None


def _market_close_bucket(trade) -> str:
    """Infer market-close condition from realized P/L vs spread economics.

    The journal does not persist underlying close directly, so this reports an inferred
    close bucket for put credit spreads once they are closed.
    """
    if trade.outcome != "FILLED" or trade.closed_at is None or trade.realized_pnl is None:
        return "N/A (not closed)"

    if trade.trade_type != "PUT_CREDIT_SPREAD":
        return "N/A (unsupported trade_type)"

    if trade.short_put_strike is None or trade.long_put_strike is None:
        return "N/A (missing strikes)"

    credit = _credit_dollars(trade)
    if credit is None:
        return "N/A (missing credit)"

    qty = trade.quantity or 1
    width_points = abs(float(trade.short_put_strike) - float(trade.long_put_strike))
    width_dollars = width_points * 100 * qty

    max_profit = round(credit, 2)
    max_loss = round(credit - width_dollars, 2)
    realized = round(float(trade.realized_pnl), 2)

    # Allow a small tolerance for fee/rounding drift.
    tol = 1.0
    if realized >= max_profit - tol:
        return "Above both strikes"
    if realized <= max_loss + tol:
        return "Below both strikes"
    return "Between strikes"


def _flow_label(trade, events: list) -> tuple[str, bool]:
    has_orphan = any(ev.event_type == "ADJ" and "ORPHAN FLAGGED:" in ev.line_text for ev in events)
    has_exit = any(ev.event_type == "EXIT" for ev in events)

    if trade.outcome != "FILLED":
        return f"ENTRY->{trade.outcome}", False

    if trade.closed_at is None:
        return ("ENTRY->ORPHAN->OPEN" if has_orphan else "ENTRY->OPEN"), False

    closed_reason = trade.exit_reason or trade.tp_status or "CLOSED"
    if has_orphan and has_exit:
        return f"ENTRY->ORPHAN->CLOSED({closed_reason})", True
    if has_exit:
        return f"ENTRY->CLOSED({closed_reason})", False
    return "ENTRY->CLOSED(no EXIT event)", False


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


@report_app.command(name="trade-number")
def report_trade_number(
    account: str = _ACCOUNT_OPTION,
    trade_number: str = typer.Option(None, "--trade-number", help="Filter exact trade number."),
) -> None:
    """Trade Number report (TradeManagerNotes)."""
    from encyclopedia_galactica.reader import Reader, sort_by_trade_number_desc, trade_status

    records = Reader(account=account).all_trades()
    records = [t for t in records if t.legacy_trade_num]
    if trade_number:
        records = [t for t in records if t.legacy_trade_num == trade_number]
    records = sort_by_trade_number_desc(records)

    if not records:
        console.print("[dim]No trades found.[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold", title=f"Trade Number Report - {account}")
    tbl.add_column("Trade #")
    tbl.add_column("Status")
    tbl.add_column("Entry Date")
    tbl.add_column("Underlying")

    for t in records:
        tbl.add_row(
            t.legacy_trade_num or "—",
            trade_status(t),
            _mdy(t.entered_at),
            t.underlying,
        )
    console.print(tbl)


@report_app.command(name="daily-notes")
def report_daily_notes(
    account: str = _ACCOUNT_OPTION,
    trade_number: str = typer.Option(None, "--trade-number", help="Filter exact trade number."),
    underlying: str = typer.Option(None, "--underlying", help="Filter by underlying symbol."),
) -> None:
    """Daily Notes multi-line ledger report (traders_daily_work_notes)."""
    from encyclopedia_galactica.reader import Reader, sort_by_trade_number_desc, trade_status

    reader = Reader(account=account)
    records = reader.all_trades()
    records = [t for t in records if t.legacy_trade_num]

    if trade_number:
        records = [t for t in records if t.legacy_trade_num == trade_number]
    if underlying:
        records = [t for t in records if t.underlying.upper() == underlying.upper()]

    records = sort_by_trade_number_desc(records)
    if not records:
        console.print("[dim]No trades found.[/dim]")
        return

    for t in records:
        header = f"{t.underlying}({t.legacy_trade_num}): {trade_status(t)}"
        console.print(f"[bold]{header}[/bold]")
        events = reader.trade_events(t.trade_id)
        if not events:
            console.print("  [dim]No notes available[/dim]")
            continue
        for ev in events:
            console.print(f"  {ev.line_text}")
        console.print()


@report_app.command(name="trade-history")
def report_trade_history(
    account: str = _ACCOUNT_OPTION,
    status: str = typer.Option("BOTH", "--status", help="ACTIVE, CLOSED, or BOTH."),
    trade_number: str = typer.Option(None, "--trade-number", help="Filter exact trade number."),
    entry_date: str = typer.Option(None, "--entry-date", help='Date filter like ">=01/01/2026".'),
    exit_date: str = typer.Option(None, "--exit-date", help='Date filter like "<02/01/2026".'),
) -> None:
    """Trade PnL history report with trailer metrics."""
    from encyclopedia_galactica.reader import (
        Reader,
        annualized_return_percent,
        days_in_market,
        filter_by_expression,
        sort_by_trade_number_desc,
        tp_percent,
        trade_status,
        trailer_stats,
    )

    reader = Reader(account=account)
    records = reader.all_trades()
    records = [t for t in records if t.legacy_trade_num]

    if trade_number:
        records = [t for t in records if t.legacy_trade_num == trade_number]

    status_u = status.upper()
    if status_u not in {"ACTIVE", "CLOSED", "BOTH"}:
        console.print("[red]Invalid status. Use ACTIVE, CLOSED, or BOTH.[/red]")
        raise typer.Exit(1)
    if status_u != "BOTH":
        records = [t for t in records if trade_status(t) == status_u]

    try:
        records = filter_by_expression(records, "entered_at", entry_date)
        records = filter_by_expression(records, "closed_at", exit_date)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(1)

    records = sort_by_trade_number_desc(records)
    if not records:
        console.print("[dim]No trades found.[/dim]")
        return

    tbl = Table(show_header=True, header_style="bold", title=f"Trade History - {account}")
    tbl.add_column("Trade #")
    tbl.add_column("Status")
    tbl.add_column("Entry Date")
    tbl.add_column("Exit Date")
    tbl.add_column("DiM", justify="right")
    tbl.add_column("CREDIT Received", justify="right")
    tbl.add_column("CREDIT Fees", justify="right")
    tbl.add_column("DEBIT Paid", justify="right")
    tbl.add_column("DEBIT Fees", justify="right")
    tbl.add_column("Total", justify="right")
    tbl.add_column("TP%", justify="right")
    tbl.add_column("Annualized Return%", justify="right")

    for t in records:
        st = trade_status(t)
        credit_received = t.credit_received or 0.0
        credit_fees = t.credit_fees or 0.0
        debit_paid = t.debit_paid or 0.0
        debit_fees = t.debit_fees or 0.0
        total = credit_received - credit_fees - debit_paid - debit_fees
        dim = days_in_market(t)
        tp_pct_val = tp_percent(t)
        ann_ret = annualized_return_percent(t)

        total_style = "green" if total >= 0 else "red"
        tbl.add_row(
            t.legacy_trade_num or "—",
            st,
            _mdy(t.entered_at),
            _mdy(t.closed_at),
            str(dim) if dim is not None else "—",
            _fmt(credit_received),
            _fmt(credit_fees),
            _fmt(debit_paid),
            _fmt(debit_fees),
            f"[{total_style}]{_fmt(total)}[/{total_style}]",
            _fmt(tp_pct_val),
            _fmt(ann_ret),
        )

    console.print(tbl)

    closed = [t for t in records if trade_status(t) == "CLOSED"]
    stats = trailer_stats(closed)
    trailer = Table(show_header=False, box=None, padding=(0, 2))
    trailer.add_column("Metric", style="bold dim")
    trailer.add_column("Value")
    trailer.add_row("Closed Trade Count", str(stats["closed_count"]))
    trailer.add_row("Winning Trade Count", str(stats["winning_count"]))
    trailer.add_row("Losing Trade Count", str(stats["losing_count"]))
    trailer.add_row("Win%", _fmt_metric(stats["win_pct"]))
    trailer.add_row("Total PnL", _fmt_metric(stats["total_pnl"]))
    trailer.add_row("Average PnL", _fmt_metric(stats["avg_pnl"]))
    trailer.add_row("Max PnL", _fmt_metric(stats["max_pnl"]))
    trailer.add_row("Max DD", _fmt_metric(stats["max_dd"]))
    trailer.add_row("Avg. DiM", _fmt_metric(stats["avg_dim"]))
    trailer.add_row("Avg. TP%", _fmt_metric(stats["avg_tp_pct"]))
    trailer.add_row("Profit Factor", _fmt_metric(stats["profit_factor"]))
    trailer.add_row("Profit Expectancy", _fmt_metric(stats["profit_expectancy"]))
    trailer.add_row("Payoff Ratio", _fmt_metric(stats["payoff_ratio"]))
    trailer.add_row("Sharpe Ratio", _fmt_metric(stats["sharpe_ratio"]))
    trailer.add_row("Sortino Ratio", _fmt_metric(stats["sortino_ratio"]))
    trailer.add_row("Calmar Ratio", _fmt_metric(stats["calmar_ratio"]))
    console.print(trailer)


@report_app.command(name="weekly-flow")
def report_weekly_flow(
    account: str = _ACCOUNT_OPTION,
    spec: str = typer.Option(
        "xsp_pcs_0dte_w1_none_0900_trds",
        "--spec",
        help="Trade spec to analyze.",
    ),
    date_from: str = typer.Option(
        None,
        "--from",
        help="Inclusive start date YYYY-MM-DD. Defaults to 7 days ending today (CT).",
    ),
    date_to: str = typer.Option(
        None,
        "--to",
        help="Inclusive end date YYYY-MM-DD. Defaults to today (CT).",
    ),
) -> None:
    """Weekly flow report with market-condition buckets and non-standard flow capture."""
    from encyclopedia_galactica.reader import Reader

    today_ct = datetime.now(tz=ZoneInfo("America/Chicago")).date()
    to_date = _parse_yyyy_mm_dd(date_to, "--to").date() if date_to else today_ct
    from_date = _parse_yyyy_mm_dd(date_from, "--from").date() if date_from else (to_date - timedelta(days=6))
    if from_date > to_date:
        raise typer.BadParameter("--from must be on or before --to")

    reader = Reader(account=account)
    records = [
        t
        for t in reader.all_trades()
        if t.spec_name == spec and from_date.isoformat() <= _entry_date(t.entered_at) <= to_date.isoformat()
    ]
    records.sort(key=lambda t: t.entered_at)

    title = (
        f"Weekly Flow Report — {account} / {spec} "
        f"({from_date.isoformat()} to {to_date.isoformat()})"
    )

    if not records:
        console.print(f"[dim]{title}[/dim]")
        console.print("[dim]No trades found for this window.[/dim]")
        return

    flow_counts: Counter[str] = Counter()
    bucket_counts: Counter[str] = Counter()
    non_standard_rows: list[tuple[str, str, str, str, str]] = []

    details = Table(show_header=True, header_style="bold", title=title)
    details.add_column("Trade ID", style="dim", width=9)
    details.add_column("Entered (CT)")
    details.add_column("Flow")
    details.add_column("Market Condition")
    details.add_column("Outcome")
    details.add_column("P/L", justify="right")

    for trade in records:
        events = reader.trade_events(trade.trade_id)
        flow, is_standard = _flow_label(trade, events)
        bucket = _market_close_bucket(trade)

        flow_counts[flow] += 1
        bucket_counts[bucket] += 1

        pnl_text = _fmt(trade.realized_pnl)
        if trade.realized_pnl is not None:
            pnl_style = "green" if trade.realized_pnl >= 0 else "red"
            pnl_text = f"[{pnl_style}]{pnl_text}[/{pnl_style}]"

        details.add_row(
            trade.trade_id[:8],
            _to_ct(trade.entered_at),
            flow,
            bucket,
            trade.outcome,
            pnl_text,
        )

        if not is_standard:
            non_standard_rows.append(
                (
                    trade.trade_id[:8],
                    _to_ct(trade.entered_at),
                    flow,
                    trade.outcome,
                    _fmt(trade.realized_pnl),
                )
            )

    console.print(details)

    flow_tbl = Table(show_header=True, header_style="bold", title="Flow Pattern Counts")
    flow_tbl.add_column("Flow")
    flow_tbl.add_column("Count", justify="right")
    for flow, count in flow_counts.items():
        flow_tbl.add_row(flow, str(count))
    console.print(flow_tbl)

    bucket_tbl = Table(show_header=True, header_style="bold", title="Market Condition Buckets")
    bucket_tbl.add_column("Condition")
    bucket_tbl.add_column("Count", justify="right")
    ordered_buckets = [
        "Above both strikes",
        "Between strikes",
        "Below both strikes",
    ]
    for name in ordered_buckets:
        bucket_tbl.add_row(name, str(bucket_counts.get(name, 0)))
    for name, count in bucket_counts.items():
        if name not in ordered_buckets:
            bucket_tbl.add_row(name, str(count))
    console.print(bucket_tbl)

    non_std_tbl = Table(show_header=True, header_style="bold", title="Non-Standard Flow Trades")
    non_std_tbl.add_column("Trade ID", style="dim", width=9)
    non_std_tbl.add_column("Entered (CT)")
    non_std_tbl.add_column("Flow")
    non_std_tbl.add_column("Outcome")
    non_std_tbl.add_column("P/L", justify="right")

    if non_standard_rows:
        for row in non_standard_rows:
            non_std_tbl.add_row(*row)
    else:
        non_std_tbl.add_row("—", "—", "All trades matched ENTRY->ORPHAN->CLOSED", "—", "—")
    console.print(non_std_tbl)


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
