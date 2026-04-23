#!/usr/bin/env python
"""holodeck_sim.py — Phase 5.5 test harness.

Runs a 0DTE trade every trading day of January 2026 against the Holodeck
simulation broker, records all results to the HD journal, and prints a
final P/L summary.

Usage (from repo root):
    uv run scripts/holodeck_sim.py
    uv run scripts/holodeck_sim.py --clear
    uv run scripts/holodeck_sim.py --spec spx_pcs_20d_w5_tp50_0930
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer
from rich.console import Console
from rich.table import Table

# ── Repo root on sys.path (allows running from any directory) ─────────────────
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

app = typer.Typer(add_completion=False)
console = Console()

_CT = ZoneInfo("America/Chicago")
_SPECS_DIR = _ROOT / "apps" / "K9" / "trade_specs"
_SIM_LOG_DIR = _ROOT / "logs" / "holodeck_sim"
_HD_DB = _ROOT / "data" / "captains_log" / "HD.db"
_HOLODECK_DATA = _ROOT / "data" / "holodeck" / "spx_2026_01_minutes.csv"


def _fmt(val: float | None, decimals: int = 2) -> str:
    return f"{val:.{decimals}f}" if val is not None else "—"


@app.command()
def main(
    spec: str = typer.Option(
        "spx_ic_20d_w5_tp34_0900",
        "--spec",
        help="Trade spec name (without .json).",
    ),
    clear: bool = typer.Option(
        False,
        "--clear",
        help="Delete HD journal before running (fresh start).",
    ),
) -> None:
    """Run a 0DTE trade every day of January 2026 against the Holodeck broker."""
    from holodeck.broker import HolodeckBroker
    from holodeck.config import HolodeckConfig
    from holodeck.market_data import TRADING_DAYS

    from K9.config import TradeSpec
    from K9.engine.runner import run_entry

    from captains_log.journal import Journal
    from captains_log.models import TradeRecord

    from encyclopedia_galactica.reader import Reader, group_by_month, pnl_stats

    # ── Load and validate spec ────────────────────────────────────────────────
    spec_path = _SPECS_DIR / f"{spec}.json"
    if not spec_path.exists():
        console.print(f"[bold red]Spec not found: {spec_path}[/bold red]")
        raise typer.Exit(1)

    try:
        trade_spec = TradeSpec.from_json(spec_path)
        trade_spec.validate()
    except (KeyError, ValueError) as exc:
        console.print(f"[bold red]Invalid spec: {exc}[/bold red]")
        raise typer.Exit(1)

    if trade_spec.environment != "holodeck":
        console.print(
            f"[bold red]Spec environment is '{trade_spec.environment}', not 'holodeck'.[/bold red]"
        )
        raise typer.Exit(1)

    if not trade_spec.enabled:
        console.print("[yellow]Spec is disabled (enabled=false).[/yellow]")
        raise typer.Exit(0)

    console.print(
        f"[bold]Spec:[/bold] {spec}  "
        f"[dim]({trade_spec.trade_type} · {trade_spec.underlying} · "
        f"delta={trade_spec.short_strike_selection.value} · "
        f"wing={trade_spec.wing_size} · TP={trade_spec.exit.take_profit_percent}%)[/dim]"
    )

    # ── Check market data ─────────────────────────────────────────────────────
    if not _HOLODECK_DATA.exists():
        console.print(
            f"[bold red]Market data not found: {_HOLODECK_DATA}[/bold red]\n"
            "Run: [bold]holodeck generate-data[/bold]"
        )
        raise typer.Exit(1)

    # ── Clear HD journal and reports if requested ─────────────────────────────
    if clear:
        if _HD_DB.exists():
            _HD_DB.unlink()
        from encyclopedia_galactica.store import Store
        Store().reset_account("HD")
        console.print("[yellow]HD journal and reports cleared.[/yellow]")

    # ── Set up ────────────────────────────────────────────────────────────────
    _SIM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    journal = Journal(account="HD", db_path=_HD_DB)

    # ── Simulation loop ───────────────────────────────────────────────────────
    console.rule("[bold]Holodeck Simulation — January 2026[/bold]")
    console.print(f"  Trading days : {len(TRADING_DAYS)}")
    console.print(f"  Data file    : {_HOLODECK_DATA}")
    console.print(f"  Journal      : {_HD_DB}")
    console.print()

    day_results: list[dict] = []

    for trade_date_str in TRADING_DAYS:
        # Start each day at session open (09:30 CT) — inside the entry window
        start_dt = datetime.fromisoformat(f"{trade_date_str}T09:30:00").replace(tzinfo=_CT)
        end_dt = start_dt.replace(hour=15, minute=0)

        config = HolodeckConfig(
            starting_datetime=start_dt,
            ending_datetime=end_dt,
            data_path=str(_HOLODECK_DATA),
        )
        broker = HolodeckBroker(config)

        # Capture NAV before trade (for P/L calculation after close)
        pre_nav = broker.get_account().net_liquidation

        result = run_entry(
            trade_spec,
            spec,
            broker,
            log_dir=_SIM_LOG_DIR,
            tick=broker.advance_time,
        )

        # Build and record TradeRecord
        trade = TradeRecord(
            spec_name=spec,
            environment="holodeck",
            account="HD",
            underlying=trade_spec.underlying,
            trade_type=trade_spec.trade_type,
            expiration=result.expiration,
            short_put_strike=result.short_put_strike,
            long_put_strike=(result.short_put_strike - trade_spec.wing_size)
                if result.short_put_strike is not None else None,
            short_call_strike=result.short_call_strike,
            long_call_strike=(result.short_call_strike + trade_spec.wing_size)
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
        # Stamp the entered_at to the virtual time so journal dates make sense
        trade.entered_at = start_dt.isoformat()
        journal.record(trade)

        day_row: dict = {
            "date": trade_date_str,
            "outcome": result.outcome,
            "credit": result.net_credit,
            "realized_pnl": None,
            "close": None,
        }

        if result.outcome == "FILLED":
            filled_ids = broker.advance_to_close()
            post_nav = broker.get_account().net_liquidation
            realized_pnl = round(post_nav - pre_nav, 2)
            day_row["realized_pnl"] = realized_pnl
            day_row["close"] = post_nav

            if result.tp_order_id and result.tp_order_id in filled_ids:
                tp_order = broker.get_order(result.tp_order_id)
                journal.update_tp_fill(
                    trade.trade_id,
                    tp_fill_price=tp_order.filled_price or 0.0,
                    realized_pnl=realized_pnl,
                )
                day_row["exit"] = "TP"
            else:
                journal.update_expiration(trade.trade_id, realized_pnl=realized_pnl)
                day_row["exit"] = "EXP"
        else:
            day_row["exit"] = "—"

        # Per-day console output
        outcome_color = {
            "FILLED": "green", "SKIPPED": "yellow",
            "CANCELED": "yellow", "REJECTED": "red", "ERROR": "red",
        }.get(result.outcome, "white")

        pnl_str = ""
        if day_row["realized_pnl"] is not None:
            sign = "green" if day_row["realized_pnl"] >= 0 else "red"
            pnl_str = f"  P/L [{sign}]{_fmt(day_row['realized_pnl'])}[/{sign}]"
        credit_str = f"  credit={_fmt(result.net_credit)}" if result.net_credit else ""
        exit_str = f"  exit={day_row['exit']}" if day_row["exit"] != "—" else ""

        console.print(
            f"  {trade_date_str}  [{outcome_color}]{result.outcome:<8}[/{outcome_color}]"
            f"{credit_str}{exit_str}{pnl_str}"
            + (f"  [dim]{result.reason}[/dim]" if result.reason and result.outcome != "FILLED" else "")
        )

        day_results.append(day_row)

    # ── Final summary ─────────────────────────────────────────────────────────
    console.print()
    console.rule("[bold]Summary[/bold]")

    filled = [r for r in day_results if r["outcome"] == "FILLED"]
    skipped = [r for r in day_results if r["outcome"] != "FILLED"]
    pnl_values = [r["realized_pnl"] for r in filled if r["realized_pnl"] is not None]
    tp_hits = [r for r in filled if r.get("exit") == "TP"]
    exp_held = [r for r in filled if r.get("exit") == "EXP"]

    tbl = Table(show_header=False, box=None, padding=(0, 2))
    tbl.add_column("Label", style="bold dim", min_width=24)
    tbl.add_column("Value")

    total_days = len(TRADING_DAYS)
    tbl.add_row("Trading days", str(total_days))
    tbl.add_row("Filled", str(len(filled)))
    tbl.add_row("Skipped / other", str(len(skipped)))
    tbl.add_row("TP hits", str(len(tp_hits)))
    tbl.add_row("Held to expiration", str(len(exp_held)))

    if pnl_values:
        total = sum(pnl_values)
        avg = total / len(pnl_values)
        sorted_vals = sorted(pnl_values)
        n = len(sorted_vals)
        median = (
            sorted_vals[n // 2]
            if n % 2 == 1
            else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
        )
        sign = "green" if total >= 0 else "red"
        tbl.add_row("─" * 20, "─" * 12)
        tbl.add_row("Total P/L", f"[{sign}]{_fmt(total)}[/{sign}]")
        tbl.add_row("Avg P/L", f"[dim]{_fmt(avg)}[/dim]")
        tbl.add_row("Median P/L", f"[dim]{_fmt(median)}[/dim]")
        tbl.add_row("Best day", f"[green]{_fmt(sorted_vals[-1])}[/green]")
        tbl.add_row("Worst day", f"[red]{_fmt(sorted_vals[0])}[/red]")

    console.print(tbl)
    console.print()
    console.print(
        "[dim]View full journal:  [bold]enc trades -a HD[/bold][/dim]\n"
        "[dim]P/L breakdown:      [bold]enc pnl -a HD[/bold][/dim]"
    )


if __name__ == "__main__":
    app()
