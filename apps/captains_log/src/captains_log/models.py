"""TradeRecord — canonical data model for one trade lifecycle."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _new_trade_id() -> str:
    return uuid.uuid4().hex


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

    # ── Account ───────────────────────────────────────────────────────────────
    account: str = "TRD"           # TRD | TRDS | HD

    # ── Timing / Identity (auto-populated) ───────────────────────────────────
    entered_at: str = field(default_factory=_now_iso)
    trade_id: str = field(default_factory=_new_trade_id)
