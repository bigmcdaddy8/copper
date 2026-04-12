"""SQLite persistence layer for tradier_sniffer.

All public functions accept an open sqlite3.Connection; callers manage the
connection lifecycle.  Use init_db() to create the connection — it sets
row_factory and initialises the schema.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict

from tradier_sniffer.models import (
    EventLog,
    EventType,
    Order,
    OrderLeg,
    OrderStatus,
    Trade,
    TradeOrderMap,
    TradeStatus,
)

# ---------------------------------------------------------------------------
# Schema DDL
# ---------------------------------------------------------------------------

_DDL = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id    TEXT PRIMARY KEY,
    trade_type  TEXT NOT NULL,
    status      TEXT NOT NULL,
    underlying  TEXT NOT NULL,
    opened_at   TEXT NOT NULL,
    closed_at   TEXT,
    notes       TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id      TEXT PRIMARY KEY,
    account_id    TEXT NOT NULL,
    symbol        TEXT NOT NULL,
    order_class   TEXT NOT NULL,
    order_type    TEXT NOT NULL,
    side          TEXT NOT NULL,
    quantity      INTEGER NOT NULL,
    status        TEXT NOT NULL,
    duration      TEXT NOT NULL,
    limit_price   REAL,
    fill_price    REAL,
    fill_quantity INTEGER,
    option_symbol TEXT,
    legs_json     TEXT,
    tag           TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT
);

CREATE TABLE IF NOT EXISTS trade_order_map (
    trade_id  TEXT NOT NULL,
    order_id  TEXT NOT NULL,
    role      TEXT NOT NULL,
    mapped_at TEXT NOT NULL,
    PRIMARY KEY (trade_id, order_id)
);

CREATE TABLE IF NOT EXISTS event_log (
    event_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    order_id   TEXT,
    trade_id   TEXT,
    details    TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS poll_state (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_POLL_STATE_SEED = """
INSERT OR IGNORE INTO poll_state (key, value) VALUES ('last_poll_at', '');
INSERT OR IGNORE INTO poll_state (key, value) VALUES ('trade_sequence', '0');
"""


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def init_db(db_path: str) -> sqlite3.Connection:
    """Open (or create) the database, run schema migrations, return connection.

    Safe to call on an existing database — uses CREATE TABLE IF NOT EXISTS.
    Sets row_factory = sqlite3.Row on the returned connection.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(_DDL)
    conn.executescript(_POLL_STATE_SEED)
    conn.commit()
    return conn


# ---------------------------------------------------------------------------
# Serialisation helpers (module-private)
# ---------------------------------------------------------------------------


def _order_to_row(order: Order) -> dict:
    legs_json = None
    if order.legs:
        legs_json = json.dumps([asdict(leg) for leg in order.legs])
    return {
        "order_id": order.order_id,
        "account_id": order.account_id,
        "symbol": order.symbol,
        "order_class": order.class_,
        "order_type": order.order_type,
        "side": order.side,
        "quantity": order.quantity,
        "status": str(order.status.value) if isinstance(order.status, OrderStatus) else order.status,
        "duration": order.duration,
        "limit_price": order.limit_price,
        "fill_price": order.fill_price,
        "fill_quantity": order.fill_quantity,
        "option_symbol": order.option_symbol,
        "legs_json": legs_json,
        "tag": order.tag,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
    }


def _row_to_order(row: sqlite3.Row) -> Order:
    legs: list[OrderLeg] = []
    if row["legs_json"]:
        legs = [OrderLeg(**leg) for leg in json.loads(row["legs_json"])]
    return Order(
        order_id=row["order_id"],
        account_id=row["account_id"],
        symbol=row["symbol"],
        class_=row["order_class"],
        order_type=row["order_type"],
        side=row["side"],
        quantity=row["quantity"],
        status=OrderStatus(row["status"]),
        duration=row["duration"],
        limit_price=row["limit_price"],
        fill_price=row["fill_price"],
        fill_quantity=row["fill_quantity"],
        option_symbol=row["option_symbol"],
        legs=legs,
        tag=row["tag"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_trade(row: sqlite3.Row) -> Trade:
    return Trade(
        trade_id=row["trade_id"],
        trade_type=row["trade_type"],
        underlying=row["underlying"],
        opened_at=row["opened_at"],
        status=TradeStatus(row["status"]),
        closed_at=row["closed_at"],
        notes=row["notes"],
    )


def _row_to_event(row: sqlite3.Row) -> EventLog:
    return EventLog(
        event_id=row["event_id"],
        timestamp=row["timestamp"],
        event_type=EventType(row["event_type"]),
        order_id=row["order_id"],
        trade_id=row["trade_id"],
        details=row["details"],
    )


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


def upsert_order(conn: sqlite3.Connection, order: Order) -> None:
    """Insert or replace an order row."""
    row = _order_to_row(order)
    conn.execute(
        """
        INSERT OR REPLACE INTO orders
            (order_id, account_id, symbol, order_class, order_type, side,
             quantity, status, duration, limit_price, fill_price, fill_quantity,
             option_symbol, legs_json, tag, created_at, updated_at)
        VALUES
            (:order_id, :account_id, :symbol, :order_class, :order_type, :side,
             :quantity, :status, :duration, :limit_price, :fill_price, :fill_quantity,
             :option_symbol, :legs_json, :tag, :created_at, :updated_at)
        """,
        row,
    )
    conn.commit()


def get_order(conn: sqlite3.Connection, order_id: str) -> Order | None:
    row = conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,)).fetchone()
    return _row_to_order(row) if row else None


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------


def insert_trade(conn: sqlite3.Connection, trade: Trade) -> None:
    """Insert a new trade row.  Raises sqlite3.IntegrityError on duplicate trade_id."""
    conn.execute(
        """
        INSERT INTO trades (trade_id, trade_type, status, underlying, opened_at, closed_at, notes)
        VALUES (:trade_id, :trade_type, :status, :underlying, :opened_at, :closed_at, :notes)
        """,
        {
            "trade_id": trade.trade_id,
            "trade_type": trade.trade_type,
            "status": str(trade.status.value) if isinstance(trade.status, TradeStatus) else trade.status,
            "underlying": trade.underlying,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "notes": trade.notes,
        },
    )
    conn.commit()


def update_trade_status(
    conn: sqlite3.Connection,
    trade_id: str,
    status: TradeStatus,
    closed_at: str | None = None,
) -> None:
    conn.execute(
        "UPDATE trades SET status = ?, closed_at = ? WHERE trade_id = ?",
        (status.value, closed_at, trade_id),
    )
    conn.commit()


def get_trade(conn: sqlite3.Connection, trade_id: str) -> Trade | None:
    row = conn.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,)).fetchone()
    return _row_to_trade(row) if row else None


def get_open_trades(conn: sqlite3.Connection) -> list[Trade]:
    rows = conn.execute("SELECT * FROM trades WHERE status = 'open'").fetchall()
    return [_row_to_trade(r) for r in rows]


# ---------------------------------------------------------------------------
# Trade–Order mapping
# ---------------------------------------------------------------------------


def insert_trade_order_map(conn: sqlite3.Connection, mapping: TradeOrderMap) -> None:
    """Insert a trade→order mapping.  Silently ignores duplicates."""
    conn.execute(
        """
        INSERT OR IGNORE INTO trade_order_map (trade_id, order_id, role, mapped_at)
        VALUES (?, ?, ?, ?)
        """,
        (mapping.trade_id, mapping.order_id, mapping.role, mapping.mapped_at),
    )
    conn.commit()


def get_orders_for_trade(conn: sqlite3.Connection, trade_id: str) -> list[Order]:
    rows = conn.execute(
        """
        SELECT o.* FROM orders o
        JOIN trade_order_map m ON o.order_id = m.order_id
        WHERE m.trade_id = ?
        """,
        (trade_id,),
    ).fetchall()
    return [_row_to_order(r) for r in rows]


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------


def append_event(conn: sqlite3.Connection, event: EventLog) -> int:
    """Insert an event and return the assigned event_id."""
    cur = conn.execute(
        """
        INSERT INTO event_log (timestamp, event_type, order_id, trade_id, details)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            event.timestamp,
            str(event.event_type.value) if isinstance(event.event_type, EventType) else event.event_type,
            event.order_id,
            event.trade_id,
            event.details,
        ),
    )
    conn.commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_recent_events(conn: sqlite3.Connection, limit: int = 50) -> list[EventLog]:
    rows = conn.execute(
        "SELECT * FROM event_log ORDER BY event_id DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_event(r) for r in rows]


# ---------------------------------------------------------------------------
# Poll state
# ---------------------------------------------------------------------------


def get_poll_state(conn: sqlite3.Connection) -> dict[str, str]:
    rows = conn.execute("SELECT key, value FROM poll_state").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_poll_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO poll_state (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Trade sequence counter
# ---------------------------------------------------------------------------


def reset_db(conn: sqlite3.Connection) -> None:
    """Delete all rows from all tables and re-seed poll_state.

    Does NOT drop or recreate the tables — the schema remains intact.
    """
    conn.executescript("""
        DELETE FROM event_log;
        DELETE FROM trade_order_map;
        DELETE FROM orders;
        DELETE FROM trades;
        DELETE FROM poll_state;
    """)
    conn.executescript(_POLL_STATE_SEED)
    conn.commit()


def next_trade_sequence(conn: sqlite3.Connection) -> int:
    """Atomically increment and return the next trade sequence number."""
    row = conn.execute("SELECT value FROM poll_state WHERE key = 'trade_sequence'").fetchone()
    current = int(row["value"]) if row else 0
    nxt = current + 1
    conn.execute(
        "INSERT OR REPLACE INTO poll_state (key, value) VALUES ('trade_sequence', ?)",
        (str(nxt),),
    )
    conn.commit()
    return nxt
