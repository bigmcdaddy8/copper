"""TradeRecord — canonical data model for one trade lifecycle."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _new_trade_id() -> str:
    return uuid.uuid4().hex


# Maps captains_log trade_type strings to the abbreviations used in legacy Trade #s.
TRADE_TYPE_LEGACY_CODES: dict[str, str] = {
    "IRON_CONDOR":       "SIC",
    "PUT_CREDIT_SPREAD": "PCS",
    "CALL_CREDIT_SPREAD": "CCS",
    "NAKED_SHORT_PUT":   "NPUT",
    "NAKED_SHORT_CALL":  "NCALL",
}


def build_legacy_trade_num(account: str, seq: int, trade_type: str) -> str:
    """Build a legacy Trade # string, e.g. ``TRD_00001_PCS``.

    Raises ``ValueError`` if *trade_type* has no registered abbreviation.
    """
    code = TRADE_TYPE_LEGACY_CODES.get(trade_type)
    if code is None:
        raise ValueError(
            f"No legacy code for trade_type {trade_type!r}. "
            f"Known types: {list(TRADE_TYPE_LEGACY_CODES)}"
        )
    return f"{account}_{seq:05d}_{code}"


@dataclass
class TradeRecord:
    """Authoritative record of a single trade attempt, from entry through close."""

    # ── Identity ──────────────────────────────────────────────────────────────
    spec_name: str
    environment: str          # holodeck | sandbox | production

    # ── What was traded ───────────────────────────────────────────────────────
    underlying: str           # SPX, XSP, etc.
    trade_type: str           # IRON_CONDOR | PUT_CREDIT_SPREAD | CALL_CREDIT_SPREAD
    expiration: str           # ISO date string; "" when trade was not placed

    # ── Strikes (None for SKIPPED / ERROR outcomes) ───────────────────────────
    short_put_strike: float | None
    long_put_strike: float | None
    short_call_strike: float | None
    long_call_strike: float | None

    # ── Entry outcome ─────────────────────────────────────────────────────────
    outcome: str              # FILLED | SKIPPED | CANCELED | REJECTED | ERROR
    reason: str               # human-readable skip / cancel reason
    errors: list[str] = field(default_factory=list)

    # ── Entry fill ────────────────────────────────────────────────────────────
    entry_order_id: str = ""
    entry_filled_price: float | None = None
    net_credit: float | None = None

    # ── Take-profit ───────────────────────────────────────────────────────────
    tp_order_id: str = ""
    tp_limit_price: float | None = None
    tp_status: str = "UNKNOWN"    # PLACED | FAILED | UNKNOWN | FILLED
    tp_fill_price: float | None = None

    # ── P&L ───────────────────────────────────────────────────────────────────
    realized_pnl: float | None = None
    closed_at: str | None = None
    exit_reason: str | None = None   # GTC | MANUALLY | EXPIRED

    # ── Reporting components ──────────────────────────────────────────────────
    bpr: float | None = None
    credit_received: float | None = None
    credit_fees: float = 0.0
    debit_paid: float | None = None
    debit_fees: float = 0.0

    # ── Daily Notes data ──────────────────────────────────────────────────────
    quantity: int = 1
    entry_dte: int | None = None
    entry_underlying_last: float | None = None
    long_put_delta: float | None = None
    short_put_delta: float | None = None
    short_call_delta: float | None = None
    long_call_delta: float | None = None

    # ── Account ───────────────────────────────────────────────────────────────
    account: str = "TRD"           # TRD | TRDS | HD

    # ── Timing / Identity (auto-populated) ───────────────────────────────────
    entered_at: str = field(default_factory=_now_iso)
    trade_id: str = field(default_factory=_new_trade_id)
    legacy_trade_num: str | None = None   # e.g. TRD_00001_PCS; set on filled entry


@dataclass
class TradeLogEntry:
    """Structured ledger event associated with a trade lifecycle."""

    trade_id: str
    event_type: str            # ENTRY | ADJ | GTC | EXIT
    occurred_at: str = field(default_factory=_now_iso)
    line_text: str = ""
    payload: dict[str, object] = field(default_factory=dict)
