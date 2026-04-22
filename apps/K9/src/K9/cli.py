from __future__ import annotations

import os
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(
    name="K9",
    help="Automated 0DTE options trade entry system.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def callback() -> None:
    """K9 — Automated 0DTE options trade entry system."""

_TRADE_SPECS_DIR = Path("apps/K9/trade_specs")

_ENV_ACCOUNT = {
    "holodeck":   "HD",
    "sandbox":    "TRDS",
    "production": "TRD",
}


@app.command(name="enter")
def enter(
    trade_spec: str = typer.Option(
        ..., "--trade-spec", help="Trade spec name (without .json extension)."
    ),
    specs_dir: str = typer.Option(
        str(_TRADE_SPECS_DIR),
        "--specs-dir",
        help="Directory containing trade spec JSON files.",
        hidden=True,
    ),
) -> None:
    """Execute a trade entry run using the given trade spec."""
    from K9.broker_factory import create_broker
    from K9.config import TradeSpec
    from K9.engine.runner import run_entry
    from K9.output.run_log import RunLog

    spec_path = Path(specs_dir) / f"{trade_spec}.json"
    if not spec_path.exists():
        console.print(f"[bold red]Trade spec not found: {spec_path}[/bold red]")
        raise typer.Exit(1)

    try:
        spec = TradeSpec.from_json(spec_path)
        spec.validate()
    except (KeyError, ValueError) as exc:
        console.print(f"[bold red]Invalid trade spec: {exc}[/bold red]")
        raise typer.Exit(1)

    if not spec.enabled:
        console.print("[yellow]Trade spec is disabled. Exiting.[/yellow]")
        raise typer.Exit(0)

    console.print(
        f"[green]Loaded:[/green] {trade_spec}  "
        f"[dim]({spec.environment} · {spec.trade_type} · {spec.underlying})[/dim]"
    )

    try:
        broker = create_broker(spec)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Broker init failed: {exc}[/bold red]")
        raise typer.Exit(1)

    # Resolve log dir (supports K9_LOG_DIR env override for testing)
    log_dir = Path(os.environ.get("K9_LOG_DIR", "logs/K9"))

    result = run_entry(spec, trade_spec, broker, log_dir=log_dir)

    # Write run log
    log = RunLog(spec_name=trade_spec, log_dir=log_dir)
    log.record(result)
    log_path = log.write()

    # Write to trade journal
    from captains_log import Journal, TradeRecord
    account = _ENV_ACCOUNT.get(spec.environment, "TRD")
    trade = TradeRecord(
        spec_name=trade_spec,
        environment=spec.environment,
        account=account,
        underlying=spec.underlying,
        trade_type=spec.trade_type,
        expiration=result.expiration,
        short_put_strike=result.short_put_strike,
        long_put_strike=(result.short_put_strike - spec.wing_size)
            if result.short_put_strike is not None else None,
        short_call_strike=result.short_call_strike,
        long_call_strike=(result.short_call_strike + spec.wing_size)
            if result.short_call_strike is not None else None,
        outcome=result.outcome,
        reason=result.reason,
        errors=result.errors,
        entry_order_id=result.order_id,
        entry_filled_price=result.filled_price,
        net_credit=result.net_credit,
        tp_order_id=result.tp_order_id,
        tp_limit_price=result.tp_price,
        tp_status="PLACED" if result.tp_order_id else "UNKNOWN",
    )
    Journal(account=account).record(trade)

    # Print outcome
    _OUTCOME_COLOR = {
        "FILLED":   "bold green",
        "CANCELED": "yellow",
        "REJECTED": "bold red",
        "SKIPPED":  "yellow",
        "ERROR":    "bold red",
    }
    color = _OUTCOME_COLOR.get(result.outcome, "white")
    console.print(f"[{color}]Outcome: {result.outcome}[/{color}]")
    if result.reason:
        console.print(f"[dim]{result.reason}[/dim]")
    if result.net_credit is not None:
        console.print(
            f"[dim]Net credit: {result.net_credit:.2f}  "
            f"· Expiration: {result.expiration}[/dim]"
        )
    if result.errors:
        for err in result.errors:
            console.print(f"[red]Error: {err}[/red]")
    console.print(f"[dim]Log: {log_path}[/dim]")

    # Exit code: 0 for normal outcomes, 1 for problems
    bad_outcomes = {"CANCELED", "REJECTED", "ERROR"}
    if result.outcome in bad_outcomes:
        raise typer.Exit(1)
