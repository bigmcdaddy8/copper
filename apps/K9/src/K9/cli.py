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
        ..., "--trade-spec", help="Trade spec name (without extension)."
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Run full selection/validation path without placing any orders.",
    ),
    specs_dir: str = typer.Option(
        str(_TRADE_SPECS_DIR),
        "--specs-dir",
        help="Directory containing trade spec YAML files.",
        hidden=True,
    ),
) -> None:
    """Execute a trade entry run using the given trade spec."""
    from K9.broker_factory import create_broker
    from K9.config import TradeSpec
    from K9.engine.runner import run_entry
    from K9.output.run_log import RunLog

    spec_path = _resolve_spec_path(Path(specs_dir), trade_spec)
    if spec_path is None:
        console.print(
            "[bold red]Trade spec not found:[/bold red] "
            f"{trade_spec} (looked for .yaml, .yml)"
        )
        raise typer.Exit(1)

    try:
        spec = TradeSpec.from_file(spec_path)
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

    result = run_entry(spec, trade_spec, broker, log_dir=log_dir, dry_run=dry_run)

    # Write run log
    log = RunLog(spec_name=trade_spec, log_dir=log_dir)
    log.record(result)
    log_path = log.write()

    # Write to trade journal
    from captains_log import (
        Journal,
        TradeLogEntry,
        TradeRecord,
        format_entry_line,
        format_gtc_line,
    )
    account = _ENV_ACCOUNT.get(spec.environment, "TRD")
    quantity = result.quantity or 1
    credit_received = (
        round((result.filled_price or 0.0) * 100 * quantity, 2)
        if result.filled_price is not None
        else None
    )
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
        bpr=result.bpr,
        credit_received=credit_received,
        quantity=quantity,
        entry_dte=result.entry_dte,
        entry_underlying_last=result.entry_underlying_last,
        long_put_delta=result.long_put_delta,
        short_put_delta=result.short_put_delta,
        short_call_delta=result.short_call_delta,
        long_call_delta=result.long_call_delta,
    )
    journal = Journal(account=account)
    journal.record(trade)

    if trade.outcome == "FILLED":
        trade_num = trade.legacy_trade_num or trade.trade_id[:8]
        entry_price = result.filled_price or 0.0
        entry_line = format_entry_line(trade, occurred_at=trade.entered_at)
        journal.append_event(
            TradeLogEntry(
                trade_id=trade.trade_id,
                event_type="ENTRY",
                occurred_at=trade.entered_at,
                line_text=entry_line,
                payload={
                    "trade_num": trade_num,
                    "quantity": quantity,
                    "entry_price": entry_price,
                    "credit_received": trade.credit_received,
                    "credit_fees": trade.credit_fees,
                },
            )
        )

        if trade.tp_order_id and trade.tp_limit_price is not None and trade.credit_received is not None:
            tp_keep = spec.exit.take_profit_percent
            potential_profit = round(trade.credit_received * (tp_keep / 100.0), 2)
            gtc_line = format_gtc_line(trade, tp_percent=tp_keep, occurred_at=trade.entered_at)
            journal.append_event(
                TradeLogEntry(
                    trade_id=trade.trade_id,
                    event_type="GTC",
                    occurred_at=trade.entered_at,
                    line_text=gtc_line,
                    payload={
                        "tp_percent": tp_keep,
                        "tp_limit_price": trade.tp_limit_price,
                        "potential_profit": potential_profit,
                        "credit_balance": trade.credit_received,
                    },
                )
            )

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
    if result.dry_run:
        console.print("[yellow]Mode:[/yellow] dry-run")
    if result.error_category or result.error_code:
        console.print(
            "[red]Error category:[/red] "
            f"{result.error_category or 'UNKNOWN'}"
            f" / {result.error_code or 'UNKNOWN'}"
        )
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


@app.command(name="preflight")
def preflight(
    trade_spec: str = typer.Option(
        ..., "--trade-spec", help="Trade spec name (without extension)."
    ),
    specs_dir: str = typer.Option(
        str(_TRADE_SPECS_DIR),
        "--specs-dir",
        help="Directory containing trade spec YAML files.",
        hidden=True,
    ),
) -> None:
    """Validate spec and broker/data readiness without placing orders."""
    from K9.broker_factory import create_broker
    from K9.config import TradeSpec
    from K9.engine.runner import run_preflight
    from K9.output.run_log import RunLog

    spec_path = _resolve_spec_path(Path(specs_dir), trade_spec)
    if spec_path is None:
        console.print(
            "[bold red]Trade spec not found:[/bold red] "
            f"{trade_spec} (looked for .yaml, .yml)"
        )
        raise typer.Exit(1)

    try:
        spec = TradeSpec.from_file(spec_path)
        spec.validate()
    except (KeyError, ValueError) as exc:
        console.print(f"[bold red]Invalid trade spec: {exc}[/bold red]")
        raise typer.Exit(1)

    try:
        broker = create_broker(spec)
    except (KeyError, FileNotFoundError, ValueError) as exc:
        console.print(f"[bold red]Broker init failed: {exc}[/bold red]")
        raise typer.Exit(1)

    log_dir = Path(os.environ.get("K9_LOG_DIR", "logs/K9"))
    result = run_preflight(spec, trade_spec, broker)

    log = RunLog(spec_name=trade_spec, log_dir=log_dir)
    log.record(result)
    log_path = log.write()

    if result.outcome == "PREFLIGHT_OK":
        console.print("[green]Preflight passed[/green]")
    else:
        console.print("[bold red]Preflight failed[/bold red]")

    if result.reason:
        console.print(f"[dim]{result.reason}[/dim]")
    if result.error_category or result.error_code:
        console.print(
            "[red]Error category:[/red] "
            f"{result.error_category or 'UNKNOWN'}"
            f" / {result.error_code or 'UNKNOWN'}"
        )
    if result.errors:
        for err in result.errors:
            console.print(f"[red]Error: {err}[/red]")
    console.print(f"[dim]Log: {log_path}[/dim]")

    raise typer.Exit(0 if result.outcome == "PREFLIGHT_OK" else 1)


def _resolve_spec_path(specs_dir: Path, trade_spec: str) -> Path | None:
    """Resolve trade spec file with deterministic extension preference."""
    if Path(trade_spec).suffix.lower() in {".yaml", ".yml"}:
        direct = specs_dir / trade_spec
        return direct if direct.exists() else None

    for ext in (".yaml", ".yml"):
        candidate = specs_dir / f"{trade_spec}{ext}"
        if candidate.exists():
            return candidate

    return None
