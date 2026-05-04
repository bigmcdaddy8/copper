from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
        tp_status=(
            "PLACED"
            if result.tp_order_id
            else ("NONE" if spec.exit.exit_type == "NONE" else "UNKNOWN")
        ),
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

        if (
            spec.exit.exit_type == "TAKE_PROFIT"
            and trade.tp_order_id
            and trade.tp_limit_price is not None
            and trade.credit_received is not None
        ):
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


@app.command(name="close")
def close(
    account: str = typer.Option("TRDS", "--account", help="Account code: TRDS or TRD."),
    spec_name: str | None = typer.Option(None, "--spec-name", help="Optional trade spec filter."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview closure actions without writing."),
) -> None:
    """Reconcile open FILLED trades and record closure outcomes.

    Conservative mode: only broker-confirmed TP fills auto-close positions.
    Unresolved stale trades are marked ORPHAN for manual intervention.
    """
    from bic.models import (
        ORDER_FILL_STATUSES,
        ORDER_STATUS_CANCELED,
        ORDER_STATUS_EXPIRED,
        ORDER_STATUS_REJECTED,
    )
    from captains_log import Journal, TradeLogEntry

    broker = _create_broker_for_account(account)
    journal = Journal(account=account)
    trades = journal.list_trades(outcome="FILLED", spec_name=spec_name, account=account)
    positions = broker.get_positions()
    now_utc = datetime.now(tz=timezone.utc)
    now_ct = now_utc.astimezone(ZoneInfo("America/Chicago"))

    checked = 0
    updated = 0
    skipped = 0
    orphaned = 0
    for trade in trades:
        if trade.closed_at is not None:
            skipped += 1
            continue
        checked += 1

        occurred_at = now_utc.isoformat()
        qty = trade.quantity or 1
        credit_received = trade.credit_received or (
            round((trade.entry_filled_price or 0.0) * 100 * qty, 2)
            if trade.entry_filled_price is not None
            else 0.0
        )
        is_stale = _trade_entered_before_today_ct(trade.entered_at, now_ct.date())
        has_open_position = _has_open_position_for_trade(positions, trade.underlying, trade.expiration)

        # No TP order (exit_type NONE): never auto-close without definitive broker settlement details.
        if not trade.tp_order_id:
            if is_stale:
                orphan_reason = (
                    "ORPHAN: no TP order and unresolved after next-day reconciliation window. "
                    f"open_position_detected={has_open_position}."
                )
                orphaned += 1
                if not dry_run:
                    journal.mark_orphan(trade.trade_id, orphan_reason)
                    journal.append_event(
                        TradeLogEntry(
                            trade_id=trade.trade_id,
                            event_type="ADJ",
                            occurred_at=occurred_at,
                            line_text=f"ORPHAN FLAGGED: {orphan_reason}",
                            payload={
                                "reason": "ORPHAN",
                                "open_position_detected": has_open_position,
                                "credit_received": credit_received,
                            },
                        )
                    )
                updated += 1
            continue

        order = broker.get_order(trade.tp_order_id)
        if order.status in ORDER_FILL_STATUSES and order.filled_price is not None:
            debit = round(order.filled_price * 100 * qty, 2)
            realized = round(credit_received - debit, 2)
            if not dry_run:
                journal.update_tp_fill(
                    trade.trade_id,
                    tp_fill_price=order.filled_price,
                    realized_pnl=realized,
                    closed_at=occurred_at,
                )
                journal.append_event(
                    TradeLogEntry(
                        trade_id=trade.trade_id,
                        event_type="EXIT",
                        occurred_at=occurred_at,
                        line_text=format_exit_line(
                            reason="GTC",
                            occurred_at=occurred_at,
                            exit_price=order.filled_price,
                            fees=0.0,
                        ),
                        payload={
                            "reason": "GTC",
                            "exit_price": order.filled_price,
                            "realized_pnl": realized,
                        },
                    )
                )
            updated += 1
            continue

        if order.status in {ORDER_STATUS_EXPIRED, ORDER_STATUS_CANCELED, ORDER_STATUS_REJECTED} and is_stale:
            orphan_reason = (
                "ORPHAN: TP order unresolved without broker fill confirmation after next-day "
                f"window. tp_order_status={order.status}; open_position_detected={has_open_position}."
            )
            orphaned += 1
            if not dry_run:
                journal.mark_orphan(trade.trade_id, orphan_reason)
                journal.append_event(
                    TradeLogEntry(
                        trade_id=trade.trade_id,
                        event_type="ADJ",
                        occurred_at=occurred_at,
                        line_text=f"ORPHAN FLAGGED: {orphan_reason}",
                        payload={
                            "reason": "ORPHAN",
                            "tp_order_status": order.status,
                            "open_position_detected": has_open_position,
                            "credit_received": credit_received,
                        },
                    )
                )
            updated += 1

    console.print(
        f"[green]close complete[/green] checked={checked} updated={updated} skipped={skipped}"
        f" orphaned={orphaned} dry_run={dry_run}"
    )
    if orphaned > 0:
        console.print(
            "[bold red]ORPHAN trades detected. Manual reconciliation required. "
            "Collect broker/journal diagnostics.[/bold red]"
        )
        raise typer.Exit(2)


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


def _create_broker_for_account(account: str):
    from dotenv import load_dotenv
    from K9.tradier.broker import TradierBroker
    from K9.tradier_env import resolve_account_id

    normalized = account.upper().strip()
    if normalized not in {"TRDS", "TRD"}:
        raise typer.BadParameter("--account must be TRDS or TRD")

    load_dotenv()
    if normalized == "TRDS":
        return TradierBroker(
            api_key=os.environ["TRADIER_SANDBOX_API_KEY"],
            account_id=resolve_account_id("sandbox"),
            sandbox=True,
        )
    return TradierBroker(
        api_key=os.environ["TRADIER_API_KEY"],
        account_id=resolve_account_id("production"),
        sandbox=False,
    )


def _trade_entered_before_today_ct(entered_at_iso: str, today_ct: date) -> bool:
    try:
        entered = datetime.fromisoformat(entered_at_iso)
    except ValueError:
        return True
    if entered.tzinfo is None:
        entered = entered.replace(tzinfo=timezone.utc)
    entered_ct_date = entered.astimezone(ZoneInfo("America/Chicago")).date()
    return entered_ct_date < today_ct


def _has_open_position_for_trade(positions, underlying: str, expiration_iso: str) -> bool:
    try:
        exp_token = datetime.fromisoformat(f"{expiration_iso}T00:00:00").strftime("%y%m%d")
    except ValueError:
        exp_token = ""
    needle = underlying.upper()
    for pos in positions:
        symbol = (pos.symbol or "").upper()
        if needle in symbol and (not exp_token or exp_token in symbol):
            return True
    return False
