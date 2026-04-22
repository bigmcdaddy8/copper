"""Store — SQLite-backed report history for encyclopedia_galactica."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

_DEFAULT_DB = Path("data/encyclopedia_galactica/reports.db")

_CREATE_MONTHLY = """
CREATE TABLE IF NOT EXISTS monthly_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account      TEXT NOT NULL,
    month        TEXT NOT NULL,
    num_trades   INTEGER NOT NULL,
    pnl_count    INTEGER NOT NULL,
    total_pnl    REAL,
    avg_pnl      REAL,
    median_pnl   REAL,
    best_pnl     REAL,
    worst_pnl    REAL,
    generated_at TEXT NOT NULL,
    UNIQUE(account, month)
)
"""

_CREATE_YEARLY = """
CREATE TABLE IF NOT EXISTS yearly_reports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    account      TEXT NOT NULL,
    year         TEXT NOT NULL,
    num_trades   INTEGER NOT NULL,
    pnl_count    INTEGER NOT NULL,
    total_pnl    REAL,
    avg_pnl      REAL,
    median_pnl   REAL,
    best_pnl     REAL,
    worst_pnl    REAL,
    generated_at TEXT NOT NULL,
    UNIQUE(account, year)
)
"""


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class Store:
    """Persists and retrieves generated reports."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db = db_path or _DEFAULT_DB
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_MONTHLY)
            conn.execute(_CREATE_YEARLY)

    def upsert_monthly(self, account: str, month: str, stats: dict) -> None:
        """Insert or replace a monthly snapshot."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO monthly_reports
                    (account, month, num_trades, pnl_count, total_pnl,
                     avg_pnl, median_pnl, best_pnl, worst_pnl, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account, month) DO UPDATE SET
                    num_trades=excluded.num_trades,
                    pnl_count=excluded.pnl_count,
                    total_pnl=excluded.total_pnl,
                    avg_pnl=excluded.avg_pnl,
                    median_pnl=excluded.median_pnl,
                    best_pnl=excluded.best_pnl,
                    worst_pnl=excluded.worst_pnl,
                    generated_at=excluded.generated_at
                """,
                (
                    account, month,
                    stats["count"], stats["pnl_count"],
                    stats["total"], stats["avg"],
                    stats["median"], stats["best"], stats["worst"],
                    _now_iso(),
                ),
            )

    def upsert_yearly(self, account: str, year: str, stats: dict) -> None:
        """Insert or replace a yearly snapshot."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO yearly_reports
                    (account, year, num_trades, pnl_count, total_pnl,
                     avg_pnl, median_pnl, best_pnl, worst_pnl, generated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account, year) DO UPDATE SET
                    num_trades=excluded.num_trades,
                    pnl_count=excluded.pnl_count,
                    total_pnl=excluded.total_pnl,
                    avg_pnl=excluded.avg_pnl,
                    median_pnl=excluded.median_pnl,
                    best_pnl=excluded.best_pnl,
                    worst_pnl=excluded.worst_pnl,
                    generated_at=excluded.generated_at
                """,
                (
                    account, year,
                    stats["count"], stats["pnl_count"],
                    stats["total"], stats["avg"],
                    stats["median"], stats["best"], stats["worst"],
                    _now_iso(),
                ),
            )

    def list_monthly(self, account: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM monthly_reports WHERE account = ? ORDER BY month",
                (account,),
            ).fetchall()

    def list_yearly(self, account: str) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT * FROM yearly_reports WHERE account = ? ORDER BY year",
                (account,),
            ).fetchall()

    def reset_account(self, account: str) -> None:
        """Delete all stored reports for the given account (use for HD resets)."""
        with self._connect() as conn:
            conn.execute("DELETE FROM monthly_reports WHERE account = ?", (account,))
            conn.execute("DELETE FROM yearly_reports WHERE account = ?", (account,))
