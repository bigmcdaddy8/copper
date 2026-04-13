"""Journal — SQLite-backed trade record store."""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from captains_log.models import TradeRecord

_DEFAULT_DB = Path("data/captains_log/trades.db")

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id            TEXT PRIMARY KEY,
    spec_name           TEXT NOT NULL,
    environment         TEXT NOT NULL,
    underlying          TEXT NOT NULL,
    trade_type          TEXT NOT NULL,
    expiration          TEXT NOT NULL,
    short_put_strike    REAL,
    long_put_strike     REAL,
    short_call_strike   REAL,
    long_call_strike    REAL,
    outcome             TEXT NOT NULL,
    reason              TEXT NOT NULL,
    errors              TEXT NOT NULL,
    entry_order_id      TEXT NOT NULL,
    entry_filled_price  REAL,
    net_credit          REAL,
    tp_order_id         TEXT NOT NULL,
    tp_limit_price      REAL,
    tp_status           TEXT NOT NULL,
    tp_fill_price       REAL,
    realized_pnl        REAL,
    entered_at          TEXT NOT NULL
)
"""

_INSERT_SQL = """
INSERT OR IGNORE INTO trades (
    trade_id, spec_name, environment, underlying, trade_type, expiration,
    short_put_strike, long_put_strike, short_call_strike, long_call_strike,
    outcome, reason, errors,
    entry_order_id, entry_filled_price, net_credit,
    tp_order_id, tp_limit_price, tp_status, tp_fill_price,
    realized_pnl, entered_at
) VALUES (
    ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?
)
"""


def _row_to_record(row: sqlite3.Row) -> TradeRecord:
    return TradeRecord(
        trade_id=row["trade_id"],
        spec_name=row["spec_name"],
        environment=row["environment"],
        underlying=row["underlying"],
        trade_type=row["trade_type"],
        expiration=row["expiration"],
        short_put_strike=row["short_put_strike"],
        long_put_strike=row["long_put_strike"],
        short_call_strike=row["short_call_strike"],
        long_call_strike=row["long_call_strike"],
        outcome=row["outcome"],
        reason=row["reason"],
        errors=json.loads(row["errors"]),
        entry_order_id=row["entry_order_id"],
        entry_filled_price=row["entry_filled_price"],
        net_credit=row["net_credit"],
        tp_order_id=row["tp_order_id"],
        tp_limit_price=row["tp_limit_price"],
        tp_status=row["tp_status"],
        tp_fill_price=row["tp_fill_price"],
        realized_pnl=row["realized_pnl"],
        entered_at=row["entered_at"],
    )


class Journal:
    """Reads and writes TradeRecords to a SQLite database."""

    DEFAULT_DB = _DEFAULT_DB

    def __init__(self, db_path: Path | None = None) -> None:
        self._db = db_path or Path(os.environ.get("CL_DB_PATH", str(self.DEFAULT_DB)))
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_SQL)

    def record(self, trade: TradeRecord) -> None:
        """Insert a TradeRecord. Silently no-ops if trade_id already exists."""
        with self._connect() as conn:
            conn.execute(
                _INSERT_SQL,
                (
                    trade.trade_id,
                    trade.spec_name,
                    trade.environment,
                    trade.underlying,
                    trade.trade_type,
                    trade.expiration,
                    trade.short_put_strike,
                    trade.long_put_strike,
                    trade.short_call_strike,
                    trade.long_call_strike,
                    trade.outcome,
                    trade.reason,
                    json.dumps(trade.errors),
                    trade.entry_order_id,
                    trade.entry_filled_price,
                    trade.net_credit,
                    trade.tp_order_id,
                    trade.tp_limit_price,
                    trade.tp_status,
                    trade.tp_fill_price,
                    trade.realized_pnl,
                    trade.entered_at,
                ),
            )

    def get_trade(self, trade_id: str) -> TradeRecord | None:
        """Return a single TradeRecord by trade_id, or None if not found."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM trades WHERE trade_id = ?", (trade_id,)
            ).fetchone()
        return _row_to_record(row) if row else None

    def list_trades(
        self,
        date: str | None = None,
        outcome: str | None = None,
        spec_name: str | None = None,
    ) -> list[TradeRecord]:
        """Return TradeRecords matching the given filters, ordered by entered_at DESC."""
        clauses: list[str] = []
        params: list[object] = []

        if date:
            clauses.append("entered_at LIKE ?")
            params.append(f"{date}%")
        if outcome:
            clauses.append("outcome = ?")
            params.append(outcome)
        if spec_name:
            clauses.append("spec_name = ?")
            params.append(spec_name)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM trades {where} ORDER BY entered_at DESC"

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(r) for r in rows]

    def update_tp_fill(
        self,
        trade_id: str,
        tp_fill_price: float,
        realized_pnl: float,
    ) -> None:
        """Update a FILLED trade when its take-profit order executes."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET tp_fill_price = ?,
                    realized_pnl  = ?,
                    tp_status     = 'FILLED'
                WHERE trade_id = ?
                """,
                (tp_fill_price, realized_pnl, trade_id),
            )
