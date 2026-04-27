"""Journal — SQLite-backed trade record store."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from captains_log.models import TradeLogEntry, TradeRecord, build_legacy_trade_num

_DEFAULT_DB_DIR = Path("data/captains_log")


def _default_db(account: str) -> Path:
    return _DEFAULT_DB_DIR / f"{account}.db"


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


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
    closed_at           TEXT,
    exit_reason         TEXT,
    bpr                 REAL,
    credit_received     REAL,
    credit_fees         REAL NOT NULL DEFAULT 0,
    debit_paid          REAL,
    debit_fees          REAL NOT NULL DEFAULT 0,
    quantity            INTEGER NOT NULL DEFAULT 1,
    entry_dte           INTEGER,
    entry_underlying_last REAL,
    long_put_delta      REAL,
    short_put_delta     REAL,
    short_call_delta    REAL,
    long_call_delta     REAL,
    entered_at          TEXT NOT NULL,
    account             TEXT NOT NULL DEFAULT 'TRD',
    legacy_trade_num    TEXT
)
"""

_CREATE_TRADE_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS trade_events (
    event_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    occurred_at         TEXT NOT NULL,
    line_text           TEXT NOT NULL,
    payload             TEXT NOT NULL,
    FOREIGN KEY(trade_id) REFERENCES trades(trade_id)
)
"""

_CREATE_TRADE_SEQUENCE_SQL = """
CREATE TABLE IF NOT EXISTS trade_sequence (
    last_seq INTEGER NOT NULL DEFAULT 0
)
"""

_INSERT_SQL = """
INSERT OR IGNORE INTO trades (
    trade_id, spec_name, environment, underlying, trade_type, expiration,
    short_put_strike, long_put_strike, short_call_strike, long_call_strike,
    outcome, reason, errors,
    entry_order_id, entry_filled_price, net_credit,
    tp_order_id, tp_limit_price, tp_status, tp_fill_price,
    realized_pnl, closed_at, exit_reason,
    bpr, credit_received, credit_fees, debit_paid, debit_fees,
    quantity, entry_dte, entry_underlying_last,
    long_put_delta, short_put_delta, short_call_delta, long_call_delta,
    entered_at, account, legacy_trade_num
) VALUES (
    ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?, ?,
    ?, ?, ?,
    ?, ?, ?, ?,
    ?, ?, ?
)
"""

_INSERT_EVENT_SQL = """
INSERT INTO trade_events (
    trade_id, event_type, occurred_at, line_text, payload
) VALUES (?, ?, ?, ?, ?)
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
        closed_at=row["closed_at"],
        exit_reason=row["exit_reason"],
        bpr=row["bpr"],
        credit_received=row["credit_received"],
        credit_fees=row["credit_fees"],
        debit_paid=row["debit_paid"],
        debit_fees=row["debit_fees"],
        quantity=row["quantity"],
        entry_dte=row["entry_dte"],
        entry_underlying_last=row["entry_underlying_last"],
        long_put_delta=row["long_put_delta"],
        short_put_delta=row["short_put_delta"],
        short_call_delta=row["short_call_delta"],
        long_call_delta=row["long_call_delta"],
        entered_at=row["entered_at"],
        account=row["account"],
        legacy_trade_num=row["legacy_trade_num"],
    )


def _row_to_event(row: sqlite3.Row) -> TradeLogEntry:
    return TradeLogEntry(
        trade_id=row["trade_id"],
        event_type=row["event_type"],
        occurred_at=row["occurred_at"],
        line_text=row["line_text"],
        payload=json.loads(row["payload"]),
    )


class Journal:
    """Reads and writes TradeRecords to a SQLite database.

    Each account (TRD, TRDS, HD) uses an isolated database file.
    """

    DEFAULT_DB_DIR = _DEFAULT_DB_DIR

    def __init__(
        self,
        account: str = "TRD",
        db_path: Path | None = None,
    ) -> None:
        self._account = account
        if db_path is not None:
            self._db = db_path
        else:
            env_path = os.environ.get("CL_DB_PATH")
            self._db = Path(env_path) if env_path else _default_db(account)
        self._db.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(_CREATE_SQL)
            conn.execute(_CREATE_TRADE_EVENTS_SQL)
            conn.execute(_CREATE_TRADE_SEQUENCE_SQL)
            # Seed the sequence row if the table was just created (empty).
            conn.execute("INSERT OR IGNORE INTO trade_sequence SELECT 0 WHERE NOT EXISTS (SELECT 1 FROM trade_sequence)")
            # Migrate existing DBs: add account column if absent
            cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
            if "account" not in cols:
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN account TEXT NOT NULL DEFAULT 'TRD'"
                )
            if "legacy_trade_num" not in cols:
                conn.execute(
                    "ALTER TABLE trades ADD COLUMN legacy_trade_num TEXT"
                )
            if "closed_at" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN closed_at TEXT")
            if "exit_reason" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN exit_reason TEXT")
            if "bpr" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN bpr REAL")
            if "credit_received" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN credit_received REAL")
            if "credit_fees" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN credit_fees REAL NOT NULL DEFAULT 0")
            if "debit_paid" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN debit_paid REAL")
            if "debit_fees" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN debit_fees REAL NOT NULL DEFAULT 0")
            if "quantity" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN quantity INTEGER NOT NULL DEFAULT 1")
            if "entry_dte" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN entry_dte INTEGER")
            if "entry_underlying_last" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN entry_underlying_last REAL")
            if "long_put_delta" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN long_put_delta REAL")
            if "short_put_delta" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN short_put_delta REAL")
            if "short_call_delta" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN short_call_delta REAL")
            if "long_call_delta" not in cols:
                conn.execute("ALTER TABLE trades ADD COLUMN long_call_delta REAL")

    def _next_seq(self, conn: sqlite3.Connection) -> int:
        """Atomically increment and return the per-account trade sequence counter."""
        conn.execute("UPDATE trade_sequence SET last_seq = last_seq + 1")
        return conn.execute("SELECT last_seq FROM trade_sequence").fetchone()[0]

    def record(self, trade: TradeRecord) -> None:
        """Insert a TradeRecord. Silently no-ops if trade_id already exists.

        If *trade.entry_filled_price* is set and this is a new record, a
        ``legacy_trade_num`` (e.g. ``TRD_00001_PCS``) is allocated and stored
        alongside the UUID ``trade_id``.
        """
        if trade.credit_received is None and trade.entry_filled_price is not None:
            trade.credit_received = round(trade.entry_filled_price * 100 * trade.quantity, 2)

        with self._connect() as conn:
            already_exists = conn.execute(
                "SELECT 1 FROM trades WHERE trade_id = ?", (trade.trade_id,)
            ).fetchone() is not None

            if not already_exists and trade.entry_filled_price is not None:
                seq = self._next_seq(conn)
                trade.legacy_trade_num = build_legacy_trade_num(
                    self._account, seq, trade.trade_type
                )

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
                    trade.closed_at,
                    trade.exit_reason,
                    trade.bpr,
                    trade.credit_received,
                    trade.credit_fees,
                    trade.debit_paid,
                    trade.debit_fees,
                    trade.quantity,
                    trade.entry_dte,
                    trade.entry_underlying_last,
                    trade.long_put_delta,
                    trade.short_put_delta,
                    trade.short_call_delta,
                    trade.long_call_delta,
                    trade.entered_at,
                    trade.account,
                    trade.legacy_trade_num,
                ),
            )

    def append_event(self, entry: TradeLogEntry) -> None:
        """Append a structured lifecycle event for a trade."""
        with self._connect() as conn:
            conn.execute(
                _INSERT_EVENT_SQL,
                (
                    entry.trade_id,
                    entry.event_type,
                    entry.occurred_at,
                    entry.line_text,
                    json.dumps(entry.payload),
                ),
            )

    def list_events(self, trade_id: str) -> list[TradeLogEntry]:
        """Return all events for a trade ordered by timestamp ascending."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT trade_id, event_type, occurred_at, line_text, payload
                FROM trade_events
                WHERE trade_id = ?
                ORDER BY occurred_at ASC, event_id ASC
                """,
                (trade_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

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
        account: str | None = None,
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
        if account:
            clauses.append("account = ?")
            params.append(account)

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
        closed_at: str | None = None,
        debit_fees: float = 0.0,
    ) -> None:
        """Update a FILLED trade when its take-profit order executes."""
        debit_paid = round(tp_fill_price * 100, 2)
        closed_ts = closed_at or _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET tp_fill_price = ?,
                    realized_pnl  = ?,
                    tp_status     = 'FILLED',
                    closed_at     = ?,
                    exit_reason   = 'GTC',
                    debit_paid    = ?,
                    debit_fees    = ?
                WHERE trade_id = ?
                """,
                (tp_fill_price, realized_pnl, closed_ts, debit_paid, debit_fees, trade_id),
            )

    def update_expiration(
        self,
        trade_id: str,
        realized_pnl: float,
        closed_at: str | None = None,
    ) -> None:
        """Update a FILLED trade that held to expiration (TP not hit)."""
        closed_ts = closed_at or _now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE trades
                SET realized_pnl = ?,
                    tp_status    = 'EXPIRED',
                    closed_at    = ?,
                    exit_reason  = 'EXPIRED',
                    debit_paid   = 0
                WHERE trade_id = ?
                """,
                (realized_pnl, closed_ts, trade_id),
            )
