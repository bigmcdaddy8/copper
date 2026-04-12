import os

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from tradier_sniffer.config import SnifferConfig
from tradier_sniffer.db import init_db, reset_db
from tradier_sniffer.demo import edge_cases, scenario1, scenario1_5, scenario2, scenario3, scenario4
from tradier_sniffer.engine import run_poll_loop
from tradier_sniffer.reconcile import reconcile
from tradier_sniffer.tradier_client import TradierAPIError, TradierClient

app = typer.Typer()
demo_app = typer.Typer(name="demo", help="Sandbox demo scenarios.")
app.add_typer(demo_app)
console = Console()
err_console = Console(stderr=True)

# Fields we expect to find in the balances response for automated trading use.
# If absent, discover will flag them as gaps.
_NEEDED_BALANCE_FIELDS = [
    "total_equity",
    "total_cash",
    "option_buying_power",
    "day_trade_buying_power",
    "pending_orders_count",
]


@app.callback()
def _callback(ctx: typer.Context) -> None:
    """tradier_sniffer — Tradier sandbox automated trading POC."""
    load_dotenv()
    api_key = os.environ.get("TRADIER_SANDBOX_API_KEY", "")
    account_id = os.environ.get("TRADIER_SANDBOX_ACCOUNT_ID", "")

    # Allow --help to work without credentials
    if ctx.invoked_subcommand is None:
        return

    missing = []
    if not api_key:
        missing.append("TRADIER_SANDBOX_API_KEY")
    if not account_id:
        missing.append("TRADIER_SANDBOX_ACCOUNT_ID")
    if missing:
        err_console.print(f"[red]Missing required env vars: {', '.join(missing)}[/red]")
        err_console.print("Copy .env.example to .env and fill in your sandbox credentials.")
        raise typer.Exit(code=1)

    ctx.ensure_object(dict)
    ctx.obj["config"] = SnifferConfig(api_key=api_key, account_id=account_id)
    ctx.obj["client"] = TradierClient(api_key=api_key)


@app.command()
def discover(ctx: typer.Context) -> None:
    """Call sandbox account endpoints and print a structured summary."""
    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]

    # --- User profile ---
    console.rule("[bold]User Profile[/bold]")
    try:
        profile_data = client.get_user_profile()
        profile = profile_data.get("profile", {})
        account = profile.get("account", {})
        # account may be a list (multiple accounts) or a single dict
        if isinstance(account, list):
            account = account[0]
        console.print(f"  Name:    {profile.get('name', 'N/A')}")
        console.print(f"  Account: {account.get('number', cfg.account_id)}")
        console.print(f"  Type:    {account.get('type', 'N/A')}")
        console.print(f"  Status:  {account.get('status', 'N/A')}")
    except TradierAPIError as e:
        err_console.print(f"[red]Error fetching profile: {e}[/red]")

    # --- Balances ---
    console.rule("[bold]Account Balances[/bold]")
    try:
        balances = client.get_balances(cfg.account_id)
        if not balances:
            console.print("  [yellow]No balance data returned.[/yellow]")
        else:
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Field", style="dim")
            table.add_column("Value")
            table.add_column("Status")

            for key, value in sorted(balances.items()):
                if isinstance(value, dict):
                    # Flatten nested dicts (e.g., "option" sub-object)
                    for sub_key, sub_val in sorted(value.items()):
                        full_key = f"{key}.{sub_key}"
                        needed = full_key in _NEEDED_BALANCE_FIELDS or key in _NEEDED_BALANCE_FIELDS
                        status = "[green]OK[/green]" if needed else ""
                        table.add_row(full_key, str(sub_val), status)
                else:
                    needed = key in _NEEDED_BALANCE_FIELDS
                    status = "[green]OK[/green]" if needed else ""
                    table.add_row(key, str(value), status)

            console.print(table)

            # Flag any needed fields not found at top level
            found_keys: set[str] = set()
            for key, value in balances.items():
                found_keys.add(key)
                if isinstance(value, dict):
                    for sub_key in value:
                        found_keys.add(f"{key}.{sub_key}")

            gaps = [f for f in _NEEDED_BALANCE_FIELDS if f not in found_keys]
            if gaps:
                console.print("\n[yellow]GAP — needed fields not found in balances response:[/yellow]")
                for g in gaps:
                    console.print(f"  [yellow]• {g}[/yellow]")
            else:
                console.print("\n[green]All needed balance fields present.[/green]")

    except TradierAPIError as e:
        err_console.print(f"[red]Error fetching balances: {e}[/red]")

    # --- History ---
    console.rule("[bold]Account History[/bold]")
    try:
        history = client.get_history(cfg.account_id)
        if not history:
            console.print("  [yellow]No history entries returned (sandbox account may be empty).[/yellow]")
        else:
            console.print(f"  Total history entries: {len(history)}")
            recent = history[:5]
            table = Table(show_header=True, header_style="bold cyan")
            table.add_column("Date")
            table.add_column("Type")
            table.add_column("Description")
            table.add_column("Amount")
            for entry in recent:
                table.add_row(
                    str(entry.get("date", "")),
                    str(entry.get("type", "")),
                    str(entry.get("description", "")),
                    str(entry.get("amount", "")),
                )
            console.print(table)
    except TradierAPIError as e:
        err_console.print(f"[red]Error fetching history: {e}[/red]")

    console.rule()
    console.print("[bold green]discover complete.[/bold green]")
    console.print(
        "See [bold]docs/TRADIER_FAQ.md[/bold] for findings documented from this run."
    )


@app.command()
def poll(
    ctx: typer.Context,
    interval: int = typer.Option(None, help="Seconds between poll cycles (default: from config)"),
) -> None:
    """Poll Tradier sandbox for order state changes."""
    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]
    effective_interval = interval if interval is not None else cfg.poll_interval
    conn = init_db(cfg.db_path)
    result = reconcile(conn, client, cfg.account_id)
    console.print(f"[bold]Reconciliation:[/bold] {result.summary}")
    run_poll_loop(conn, client, cfg.account_id, effective_interval)


@app.command()
def status(ctx: typer.Context) -> None:
    """Show open trades and recent events from the local DB."""
    cfg: SnifferConfig = ctx.obj["config"]
    conn = init_db(cfg.db_path)

    from tradier_sniffer.db import get_open_trades, get_orders_for_trade, get_recent_events
    from rich.table import Table

    trades = get_open_trades(conn)
    if trades:
        t = Table(show_header=True, header_style="bold cyan", title="Open Trades")
        t.add_column("Trade #")
        t.add_column("Type")
        t.add_column("Underlying")
        t.add_column("Opened At")
        t.add_column("Orders")
        for trade in trades:
            orders = get_orders_for_trade(conn, trade.trade_id)
            t.add_row(
                trade.trade_id, trade.trade_type, trade.underlying,
                trade.opened_at[:16], str(len(orders)),
            )
        console.print(t)
    else:
        console.print("[yellow]No open trades in DB.[/yellow]")

    events = get_recent_events(conn, limit=20)
    if events:
        e = Table(show_header=True, header_style="bold cyan", title="Recent Events (last 20)")
        e.add_column("#")
        e.add_column("Time")
        e.add_column("Type")
        e.add_column("Order ID")
        e.add_column("Trade ID")
        e.add_column("Details")
        for evt in events:
            e.add_row(
                str(evt.event_id or ""),
                (evt.timestamp or "")[:19],
                evt.event_type.value,
                evt.order_id or "",
                evt.trade_id or "",
                evt.details[:60] + ("…" if len(evt.details) > 60 else ""),
            )
        console.print(e)
    else:
        console.print("[yellow]No events in DB yet.[/yellow]")


@app.command()
def reset(
    ctx: typer.Context,
    confirm: bool = typer.Option(False, "--confirm", help="Required — confirms you want to wipe the DB"),
) -> None:
    """Clear all local DB data (trades, orders, events). Requires --confirm."""
    if not confirm:
        err_console.print("[red]Aborted.[/red] Pass [bold]--confirm[/bold] to wipe the database.")
        raise typer.Exit(code=1)
    cfg: SnifferConfig = ctx.obj["config"]
    conn = init_db(cfg.db_path)
    reset_db(conn)
    console.print(f"[bold green]Database reset.[/bold green]  ({cfg.db_path})")


@demo_app.command(name="scenario1")
def demo_scenario1(ctx: typer.Context) -> None:
    """Place a SPX 0DTE Short Iron Condor entry order (Day Limit credit)."""
    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]
    try:
        result = scenario1.run(client, cfg.account_id)
    except RuntimeError as exc:
        err_console.print(f"[red]scenario1 failed:[/red] {exc}")
        raise typer.Exit(code=1)

    from rich.table import Table
    table = Table(show_header=True, header_style="bold cyan", title="Scenario 1 — SIC Order Placed")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Order ID", result["order_id"])
    table.add_row("Expiry", result["expiry"])
    table.add_row("Credit", f"${result['credit']:.2f}")
    for name, leg in result["legs"].items():
        table.add_row(name.replace("_", " ").title(), f"{leg['symbol']}  strike={leg['strike']}")
    console.print(table)
    console.print(
        "\n[dim]Order placed — run [bold]tradier_sniffer poll[/bold] to detect the fill.[/dim]"
    )


@demo_app.command(name="scenario1_5")
def demo_scenario1_5(
    ctx: typer.Context,
    wait: int = typer.Option(30, help="Seconds to wait before checking fill status"),
    tick: float = typer.Option(0.05, help="Credit reduction per reprice attempt"),
) -> None:
    """Place SIC entry, wait, and reprice if unfilled."""
    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]
    try:
        result = scenario1_5.run(client, cfg.account_id, wait_seconds=wait, tick_reduction=tick)
    except RuntimeError as exc:
        err_console.print(f"[red]scenario1_5 failed:[/red] {exc}")
        raise typer.Exit(code=1)

    if result["repriced"]:
        console.print(
            f"[yellow]Order unfilled after {wait}s — canceled and repriced.[/yellow]\n"
            f"  Original credit: ${result['original_credit']:.2f}  →  New credit: ${result['new_credit']:.2f}\n"
            f"  New order ID: {result['order_id']}"
        )
    else:
        console.print(f"[green]Order already filled — no reprice needed.[/green]  Order ID: {result['order_id']}")
    console.print("[dim]Run [bold]tradier_sniffer poll[/bold] to track fill status.[/dim]")


@demo_app.command(name="scenario2")
def demo_scenario2(ctx: typer.Context) -> None:
    """Show multi-leg trade groupings from the local DB."""
    cfg: SnifferConfig = ctx.obj["config"]
    conn = init_db(cfg.db_path)
    summaries = scenario2.run(conn)

    if not summaries:
        console.print("[yellow]No open trades in DB.  Run scenario1 and poll until a fill is detected.[/yellow]")
        return

    from rich.table import Table
    table = Table(show_header=True, header_style="bold cyan", title="Open Trades — Multi-leg Grouping")
    table.add_column("Trade #")
    table.add_column("Underlying")
    table.add_column("Orders")
    table.add_column("Order IDs")
    for s in summaries:
        table.add_row(s["trade_id"], s["underlying"], str(s["order_count"]), ", ".join(s["order_ids"]))
    console.print(table)


@demo_app.command(name="scenario3")
def demo_scenario3(
    ctx: typer.Context,
    tp_pct: float = typer.Option(0.50, "--tp-pct", help="Take-profit as fraction of entry credit (e.g. 0.50 = 50%)"),
) -> None:
    """Place SIC entry + GTC Take Profit order, then exit."""
    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]
    try:
        result = scenario3.run(client, cfg.account_id, tp_pct=tp_pct)
    except RuntimeError as exc:
        err_console.print(f"[red]scenario3 failed:[/red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[green]Entry order placed:[/green]  ID={result['entry_order_id']}  credit=${result['entry_credit']:.2f}")
    console.print(f"[green]TP order placed:[/green]     ID={result['tp_order_id']}  price=${result['tp_price']:.2f}  (GTC)")
    console.print(
        "\n[dim]Stop the poll loop (Ctrl-C), wait for the TP to trigger, "
        "then restart — reconcile() will detect the closure.[/dim]"
    )


@demo_app.command(name="scenario4")
def demo_scenario4(ctx: typer.Context) -> None:
    """Place SIC entry, wait for fill, then place a put-spread adjustment."""
    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]
    conn = init_db(cfg.db_path)
    try:
        result = scenario4.run(client, conn, cfg.account_id)
    except RuntimeError as exc:
        err_console.print(f"[red]scenario4 failed:[/red] {exc}")
        raise typer.Exit(code=1)

    if result.get("status") == "entry_unfilled":
        console.print(f"[yellow]{result['message']}[/yellow]")
        return

    console.print(f"[green]Adjustment placed.[/green]  Trade #: {result['trade_id']}")
    console.print(f"  Entry order:     {result['entry_order_id']}")
    console.print(f"  Adjustment order: {result['adjustment_order_id']}  credit=${result['adjustment_credit']:.2f}")


_EDGE_CASE_TESTS = ["nickel_pricing", "expiry_timing", "after_hours_gtc", "after_hours_quotes"]


@demo_app.command(name="edge_cases")
def demo_edge_cases(
    ctx: typer.Context,
    run: str = typer.Option(None, "--run", help=f"Test to run: {', '.join(_EDGE_CASE_TESTS)}"),
) -> None:
    """Print edge case observation checklists, or run a specific test."""
    if run is None:
        edge_cases.print_checklists()
        return

    if run not in _EDGE_CASE_TESTS:
        err_console.print(f"[red]Unknown test '{run}'. Choose from: {', '.join(_EDGE_CASE_TESTS)}[/red]")
        raise typer.Exit(code=1)

    cfg: SnifferConfig = ctx.obj["config"]
    client: TradierClient = ctx.obj["client"]
    conn = init_db(cfg.db_path)

    runners = {
        "nickel_pricing":    edge_cases.run_nickel_pricing,
        "expiry_timing":     edge_cases.run_expiry_timing,
        "after_hours_gtc":   edge_cases.run_after_hours_gtc,
        "after_hours_quotes": edge_cases.run_after_hours_quotes,
    }
    runners[run](client, cfg.account_id, conn)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
