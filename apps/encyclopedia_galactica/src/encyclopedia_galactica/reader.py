"""Reader — reads TradeRecords from captains_log and provides aggregation helpers."""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from captains_log.journal import Journal
from captains_log.models import TradeLogEntry, TradeRecord

_FILLED_OUTCOMES = {"FILLED"}


class Reader:
    """Thin wrapper around captains_log.Journal for reporting queries."""

    def __init__(self, account: str, db_path: Path | None = None) -> None:
        self._journal = Journal(account=account, db_path=db_path)
        self.account = account

    def all_trades(
        self,
        outcome: str | None = None,
        environment: str | None = None,
    ) -> list[TradeRecord]:
        trades = self._journal.list_trades(outcome=outcome)
        if environment:
            trades = [t for t in trades if t.environment == environment]
        return trades

    def filled_trades(self) -> list[TradeRecord]:
        return self._journal.list_trades(outcome="FILLED")

    def trade_events(self, trade_id: str) -> list[TradeLogEntry]:
        return self._journal.list_events(trade_id)


def group_by_month(trades: list[TradeRecord]) -> dict[str, list[TradeRecord]]:
    """Group trades by YYYY-MM of their entered_at timestamp."""
    groups: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        month = t.entered_at[:7]  # YYYY-MM
        groups[month].append(t)
    return dict(sorted(groups.items()))


def group_by_year(trades: list[TradeRecord]) -> dict[str, list[TradeRecord]]:
    """Group trades by YYYY of their entered_at timestamp."""
    groups: dict[str, list[TradeRecord]] = defaultdict(list)
    for t in trades:
        year = t.entered_at[:4]
        groups[year].append(t)
    return dict(sorted(groups.items()))


def pnl_stats(trades: list[TradeRecord]) -> dict:
    """Compute P/L statistics over a list of FILLED trades with realized_pnl set."""
    values = [t.realized_pnl for t in trades if t.realized_pnl is not None]
    if not values:
        return {
            "count": len(trades),
            "pnl_count": 0,
            "total": None,
            "avg": None,
            "median": None,
            "best": None,
            "worst": None,
        }
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    median = (
        sorted_vals[n // 2]
        if n % 2 == 1
        else (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    )
    return {
        "count": len(trades),
        "pnl_count": n,
        "total": sum(sorted_vals),
        "avg": sum(sorted_vals) / n,
        "median": median,
        "best": sorted_vals[-1],
        "worst": sorted_vals[0],
    }


_OP_DATE_RE = re.compile(r"^(>=|<=|>|<)?\s*(\d{2}/\d{2}/\d{4})$")


def trade_number_seq(legacy_trade_num: str | None) -> int:
    """Extract the numeric sequence from legacy trade number (XXX_#####_YYY)."""
    if not legacy_trade_num:
        return -1
    parts = legacy_trade_num.split("_")
    if len(parts) != 3:
        return -1
    try:
        return int(parts[1])
    except ValueError:
        return -1


def sort_by_trade_number_desc(trades: list[TradeRecord]) -> list[TradeRecord]:
    return sorted(trades, key=lambda t: trade_number_seq(t.legacy_trade_num), reverse=True)


def trade_status(trade: TradeRecord) -> str:
    """Return ACTIVE or CLOSED for reporting views."""
    if trade.closed_at is not None or trade.exit_reason in {"GTC", "EXPIRED", "MANUALLY"}:
        return "CLOSED"
    return "ACTIVE"


def days_in_market(trade: TradeRecord) -> int | None:
    if trade_status(trade) != "CLOSED" or not trade.closed_at:
        return None
    entered = datetime.fromisoformat(trade.entered_at)
    closed = datetime.fromisoformat(trade.closed_at)
    delta = closed.date() - entered.date()
    return max(delta.days, 0)


def filter_by_expression(trades: list[TradeRecord], field: str, expr: str | None) -> list[TradeRecord]:
    """Filter trades by date expression like >=01/01/2026."""
    if not expr:
        return trades

    match = _OP_DATE_RE.match(expr.strip())
    if not match:
        raise ValueError(f"Invalid date expression: {expr!r}")

    op = match.group(1) or "="
    target = datetime.strptime(match.group(2), "%m/%d/%Y").date()

    def _ok(value: datetime) -> bool:
        d = value.date()
        if op == ">":
            return d > target
        if op == ">=":
            return d >= target
        if op == "<":
            return d < target
        if op == "<=":
            return d <= target
        return d == target

    out: list[TradeRecord] = []
    for t in trades:
        raw = getattr(t, field)
        if not raw:
            continue
        out_dt = datetime.fromisoformat(raw)
        if _ok(out_dt):
            out.append(t)
    return out


def tp_percent(trade: TradeRecord) -> float | None:
    """Percentage of credit retained. Negative for losing trades."""
    if trade.credit_received is None or trade.realized_pnl is None:
        return None
    if trade.credit_received == 0:
        return None
    return (trade.realized_pnl / trade.credit_received) * 100.0


def annualized_return_percent(trade: TradeRecord) -> float | None:
    """Annualized return based on BPR and days in market."""
    dim = days_in_market(trade)
    if dim is None or dim == 0 or trade.bpr is None or trade.bpr <= 0 or trade.realized_pnl is None:
        return None
    return (trade.realized_pnl / trade.bpr) * (365.0 / dim) * 100.0


def trailer_stats(closed_trades: list[TradeRecord]) -> dict[str, float | int | str | None]:
    """Compute trailer metrics for closed trades only."""
    if not closed_trades:
        return {
            "closed_count": 0,
            "winning_count": 0,
            "losing_count": 0,
            "win_pct": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "max_pnl": 0.0,
            "max_dd": 0.0,
            "avg_dim": 0.0,
            "avg_tp_pct": 0.0,
            "profit_factor": "N/A",
            "profit_expectancy": 0.0,
            "payoff_ratio": "N/A",
            "sharpe_ratio": "N/A",
            "sortino_ratio": "N/A",
            "calmar_ratio": "N/A",
        }

    pnl_vals = [t.realized_pnl or 0.0 for t in closed_trades]
    wins = [v for v in pnl_vals if v > 0]
    losses = [v for v in pnl_vals if v < 0]
    dims = [d for d in (days_in_market(t) for t in closed_trades) if d is not None]
    tp_vals = [v for v in (tp_percent(t) for t in closed_trades) if v is not None]

    running = 0.0
    peak = 0.0
    max_dd = 0.0
    for v in pnl_vals:
        running += v
        peak = max(peak, running)
        max_dd = min(max_dd, running - peak)

    total = sum(pnl_vals)
    avg = total / len(pnl_vals)
    win_pct = (len(wins) / len(pnl_vals)) * 100.0
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor: float | str = "N/A" if gross_loss == 0 else (gross_profit / gross_loss)

    avg_win = (sum(wins) / len(wins)) if wins else 0.0
    avg_loss = (abs(sum(losses)) / len(losses)) if losses else 0.0
    payoff_ratio: float | str = "N/A" if avg_loss == 0 else (avg_win / avg_loss)

    returns: list[float] = []
    for t in closed_trades:
        if t.bpr and t.bpr > 0 and t.realized_pnl is not None:
            returns.append(t.realized_pnl / t.bpr)

    sharpe: float | str = "N/A"
    sortino: float | str = "N/A"
    calmar: float | str = "N/A"
    if returns:
        mean_ret = sum(returns) / len(returns)
        if len(returns) > 1:
            variance = sum((r - mean_ret) ** 2 for r in returns) / (len(returns) - 1)
            stdev = math.sqrt(variance)
            if stdev > 0:
                sharpe = mean_ret / stdev

        downside = [r for r in returns if r < 0]
        if downside:
            downside_dev = math.sqrt(sum(r**2 for r in downside) / len(downside))
            if downside_dev > 0:
                sortino = mean_ret / downside_dev

        dd_for_calmar = abs(max_dd) if max_dd != 0 else 0
        if dd_for_calmar > 0:
            calmar = total / dd_for_calmar

    return {
        "closed_count": len(closed_trades),
        "winning_count": len(wins),
        "losing_count": len(losses),
        "win_pct": win_pct,
        "total_pnl": total,
        "avg_pnl": avg,
        "max_pnl": max(pnl_vals),
        "max_dd": max_dd,
        "avg_dim": (sum(dims) / len(dims)) if dims else 0.0,
        "avg_tp_pct": (sum(tp_vals) / len(tp_vals)) if tp_vals else 0.0,
        "profit_factor": profit_factor,
        "profit_expectancy": avg,
        "payoff_ratio": payoff_ratio,
        "sharpe_ratio": sharpe,
        "sortino_ratio": sortino,
        "calmar_ratio": calmar,
    }
