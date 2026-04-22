"""Reader — reads TradeRecords from captains_log and provides aggregation helpers."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from captains_log.journal import Journal
from captains_log.models import TradeRecord

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
