"""Edge case sandbox tests for tradier_sniffer.

Each test function executes an observation against the sandbox, prints Rich
findings, and returns a findings dict.  ``print_checklists()`` prints all
four observation checklists without making any API calls.

Usage:
    tradier_sniffer demo edge_cases                         # print checklists
    tradier_sniffer demo edge_cases --run nickel_pricing
    tradier_sniffer demo edge_cases --run expiry_timing
    tradier_sniffer demo edge_cases --run after_hours_gtc
    tradier_sniffer demo edge_cases --run after_hours_quotes
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tradier_sniffer.db import append_event
from tradier_sniffer.models import EventLog, EventType
from tradier_sniffer.tradier_client import TradierClient

console = Console()

_CHECKLIST_TEXT = """
[bold cyan]EC-1 Nickel Pricing[/bold cyan]
  Place a Day STO Limit with a penny price on a nickel-only option.
  □ Order rejected — reason_description = invalid_price
  □ Order accepted — price silently rounded to nearest nickel
  □ Order accepted — price as submitted (no nickel enforcement)
  Run: [bold]tradier_sniffer demo edge_cases --run nickel_pricing[/bold]

[bold cyan]EC-2 Option Expiration Timing[/bold cyan]
  After market close (4:10 PM ET), poll orders/positions for today's 0DTE SPX options.
  □ get_positions — option still visible at 4:10 PM; time of disappearance: ______
  □ get_orders   — status changed to 'expired' at: ______
  □ Delay from 4:00 PM close to 'expired' status: ______ minutes
  Run: [bold]tradier_sniffer demo edge_cases --run expiry_timing[/bold]  (after 4:00 PM ET)

[bold cyan]EC-3 After-hours GTC Placement[/bold cyan]
  After 4:05 PM ET, place a GTC BTC limit order for an open position.
  □ Order accepted — status 'open', queued for next session
  □ Order rejected — reason_description = market_closed
  □ Order accepted — status 'pending'
  Run: [bold]tradier_sniffer demo edge_cases --run after_hours_gtc[/bold]  (after 4:05 PM ET)

[bold cyan]EC-4 After-hours Stock Quotes[/bold cyan]
  After 4:05 PM ET, call GET /markets/quotes?symbols=SPY,QQQ.
  □ 'last' price matches after-hours price in Tradier desktop app
  □ 'last' is the regular-session closing price (no after-hours data)
  □ 'extended_trade' or 'post_market' sub-object present: yes / no
  Run: [bold]tradier_sniffer demo edge_cases --run after_hours_quotes[/bold]  (after 4:05 PM ET)
"""


def print_checklists() -> None:
    """Print all four observation checklists without making any API calls."""
    console.print(Panel(_CHECKLIST_TEXT.strip(), title="Edge Case Sandbox Checklists", border_style="cyan"))


# ---------------------------------------------------------------------------
# EC-1: Nickel pricing
# ---------------------------------------------------------------------------


def run_nickel_pricing(
    client: TradierClient,
    account_id: str,
    conn: sqlite3.Connection,
) -> dict:
    """Place a penny-priced limit on a nickel-only option and record the response."""
    from tradier_sniffer.options import get_0dte_expiration

    expirations = client.get_option_expirations("SPX")
    expiry = get_0dte_expiration(expirations)
    if not expiry:
        return {"test": "nickel_pricing", "status": "skipped", "reason": "No 0DTE expiration found"}

    chain = client.get_option_chain("SPX", expiry, greeks=False)
    # Find a put around strike 5000 (likely nickel-increment for SPX)
    target_strike = 5000.0
    candidate = min(
        (o for o in chain if o.get("option_type") == "put"),
        key=lambda o: abs(float(o.get("strike", 0)) - target_strike),
        default=None,
    )
    if not candidate:
        return {"test": "nickel_pricing", "status": "skipped", "reason": "No put options in chain"}

    opt_symbol = candidate["symbol"]
    # Use a deliberately non-nickel price: take the bid and add one penny
    raw_bid = float(candidate.get("bid") or 0.05)
    penny_price = round(raw_bid + 0.01, 2)

    console.print(f"[dim]Placing penny-priced order: {opt_symbol}  price=${penny_price:.2f}[/dim]")
    try:
        response = client.place_single_leg_order(
            account_id, opt_symbol, "sell_to_open", 1, "limit", penny_price, "day"
        )
        order_id = str(response.get("order", {}).get("id", "unknown"))
        order_status = response.get("order", {}).get("status", "unknown")
        findings = {
            "test": "nickel_pricing",
            "status": "placed",
            "order_id": order_id,
            "order_status": order_status,
            "submitted_price": penny_price,
            "option_symbol": opt_symbol,
            "raw_response": response,
        }
    except Exception as exc:  # noqa: BLE001
        findings = {
            "test": "nickel_pricing",
            "status": "api_error",
            "error": str(exc),
            "submitted_price": penny_price,
            "option_symbol": opt_symbol,
        }

    _log_findings(conn, findings)
    _print_findings(findings)
    return findings


# ---------------------------------------------------------------------------
# EC-2: Expiry timing
# ---------------------------------------------------------------------------


def run_expiry_timing(
    client: TradierClient,
    account_id: str,
    conn: sqlite3.Connection,
) -> dict:
    """Poll orders and positions for today's 0DTE options and record status."""
    from datetime import date

    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    orders = client.get_orders(account_id)
    positions = client.get_positions(account_id)

    def _order_matches_today(o: dict) -> bool:
        if (o.get("expiration_date") or "") == today:
            return True
        if today in str(o.get("option_symbol") or ""):
            return True
        return any(today in str(leg.get("option_symbol") or "") for leg in (o.get("leg") or []))

    today_orders = [o for o in orders if _order_matches_today(o)]
    today_positions = [
        p for p in positions
        if today.replace("-", "")[2:] in str(p.get("symbol") or "")
    ]

    findings = {
        "test": "expiry_timing",
        "polled_at": now,
        "today_orders_count": len(today_orders),
        "today_positions_count": len(today_positions),
        "order_statuses": {str(o.get("id")): o.get("status") for o in today_orders},
        "position_symbols": [p.get("symbol") for p in today_positions],
    }
    _log_findings(conn, findings)
    _print_findings(findings)
    return findings


# ---------------------------------------------------------------------------
# EC-4: After-hours quotes
# ---------------------------------------------------------------------------


def run_after_hours_quotes(
    client: TradierClient,
    account_id: str,
    conn: sqlite3.Connection,
) -> dict:
    """Query equity quotes after market close and record the response."""
    symbols = ["SPY", "QQQ", "SPX"]
    quotes = client.get_quotes(symbols)
    now = datetime.now(timezone.utc).isoformat()

    findings: dict = {
        "test": "after_hours_quotes",
        "queried_at": now,
        "quotes": [],
    }
    for q in quotes:
        findings["quotes"].append({
            "symbol": q.get("symbol"),
            "last": q.get("last"),
            "bid": q.get("bid"),
            "ask": q.get("ask"),
            "has_extended_trade": "extended_trade" in q,
            "has_post_market": "post_market" in q,
        })

    _log_findings(conn, findings)
    _print_findings(findings)
    return findings


# ---------------------------------------------------------------------------
# EC-3: After-hours GTC placement
# ---------------------------------------------------------------------------


def run_after_hours_gtc(
    client: TradierClient,
    account_id: str,
    conn: sqlite3.Connection,
) -> dict:
    """Attempt to place a GTC BTC limit order after market close.

    Uses the nearest next-day (1DTE+) expiration so this test works after
    today's 0DTE options have expired and their quotes are stale/zero.
    """
    from tradier_sniffer.options import get_next_expiration

    expirations = client.get_option_expirations("SPX")
    expiry = get_next_expiration(expirations)
    if not expiry:
        findings = {"test": "after_hours_gtc", "status": "skipped", "reason": "No expiration found"}
        _log_findings(conn, findings)
        return findings

    chain = client.get_option_chain("SPX", expiry, greeks=False)
    candidate = next(
        (o for o in chain if o.get("option_type") == "put" and float(o.get("bid") or 0) > 0),
        None,
    )
    if not candidate:
        findings = {"test": "after_hours_gtc", "status": "skipped", "reason": "No valid put option found"}
        _log_findings(conn, findings)
        return findings

    opt_symbol = candidate["symbol"]
    bid = float(candidate.get("bid") or 0.05)

    try:
        response = client.place_single_leg_order(
            account_id, opt_symbol, "buy_to_close", 1, "limit", bid, "gtc"
        )
        findings = {
            "test": "after_hours_gtc",
            "status": "placed",
            "order_id": str(response.get("order", {}).get("id", "unknown")),
            "order_status": response.get("order", {}).get("status", "unknown"),
            "option_symbol": opt_symbol,
        }
    except Exception as exc:  # noqa: BLE001
        findings = {
            "test": "after_hours_gtc",
            "status": "api_error",
            "error": str(exc),
            "option_symbol": opt_symbol,
        }

    _log_findings(conn, findings)
    _print_findings(findings)
    return findings


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _log_findings(conn: sqlite3.Connection, findings: dict) -> None:
    """Append findings to the event log."""
    evt = EventLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        event_type=EventType.new_order,
        details=json.dumps(findings),
    )
    append_event(conn, evt)


def _print_findings(findings: dict) -> None:
    """Print a findings dict as a Rich key-value table."""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")
    for k, v in findings.items():
        table.add_row(k, str(v))
    console.print(table)
