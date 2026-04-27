"""Formatting helpers for reporting-oriented trade notes."""
from __future__ import annotations

from datetime import datetime

from captains_log.models import TradeRecord


def _mdy(iso_dt: str | None) -> str:
    if not iso_dt:
        return "01/01/1970"
    dt = datetime.fromisoformat(iso_dt)
    return dt.strftime("%m/%d/%Y")


def _fmt_strike(strike: float | None) -> str:
    if strike is None:
        return "n/a"
    if strike.is_integer():
        return str(int(strike))
    return f"{strike:.2f}"


def _fmt_delta(delta: float | None) -> str:
    if delta is None:
        return "n/a"
    if delta == 0:
        return ".00d"
    sign = "-" if delta < 0 else ""
    return f"{sign}{abs(delta):.2f}".replace("0.", ".") + "d"


def _status(trade: TradeRecord) -> str:
    if trade.closed_at or trade.exit_reason in {"GTC", "MANUALLY", "EXPIRED"}:
        return "CLOSED"
    return "ACTIVE"


def format_daily_notes_header(trade: TradeRecord) -> str:
    """Return Daily Notes header line: UUU(XXX_#####_YYY): SSS."""
    trade_num = trade.legacy_trade_num or trade.trade_id[:8]
    return f"{trade.underlying}({trade_num}): {_status(trade)}"


def format_entry_line(trade: TradeRecord, occurred_at: str | None = None) -> str:
    """Return ENTRY line for the Daily Notes ledger (SIC format)."""
    event_date = _mdy(occurred_at or trade.entered_at)
    quantity = trade.quantity or 1
    dte = trade.entry_dte if trade.entry_dte is not None else 0
    entry_price = trade.entry_filled_price or 0.0
    bpr = trade.bpr or 0.0
    underlying_last = trade.entry_underlying_last or 0.0
    credit_fees = trade.credit_fees or 0.0

    return (
        f"{event_date}: ENTRY #1 SOLD {quantity}x "
        f"SIC({_fmt_strike(trade.long_put_strike)}/{_fmt_strike(trade.short_put_strike)}"
        f"/{_fmt_strike(trade.short_call_strike)}/{_fmt_strike(trade.long_call_strike)}) "
        f"DTE:{dte}d BPR(${bpr:.0f}) "
        f"{_fmt_delta(trade.long_put_delta)}/{_fmt_delta(trade.short_put_delta)}"
        f"/{_fmt_delta(trade.short_call_delta)}/{_fmt_delta(trade.long_call_delta)} "
        f"${underlying_last:.2f} @{entry_price:.2f} - ${credit_fees:.2f}"
    )


def format_gtc_line(
    trade: TradeRecord,
    tp_percent: float,
    occurred_at: str | None = None,
) -> str:
    """Return GTC line for pending take-profit order details."""
    event_date = _mdy(occurred_at or trade.entered_at)
    quantity = trade.quantity or 1
    tp_limit = trade.tp_limit_price or 0.0
    credit_balance = trade.credit_received or 0.0
    potential_profit = credit_balance * (tp_percent / 100.0)

    return (
        f"{event_date}: GTC Quantity:{quantity} "
        f"TP:{tp_percent:.0f}%@-{tp_limit:.2f} "
        f"PP:${potential_profit:.2f} CB:${credit_balance:.2f}"
    )


def format_exit_line(
    reason: str,
    occurred_at: str,
    exit_price: float,
    fees: float,
) -> str:
    """Return EXIT line in required Daily Notes format."""
    event_date = _mdy(occurred_at)
    return f"{event_date}: {reason} CLOSED TRADE @{exit_price:.2f} - ${fees:.2f}"