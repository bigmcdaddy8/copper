#!/usr/bin/env python3
"""One-time script to manually reconcile the two ERROR trades from 07-07 and 07-09.

Both trades show outcome=ERROR in Captain's Log because K9's order-polling loop
crashed when Tradier returned HTTP 400 "order already in finalized state: filled"
on the first status poll — but the orders DID fill at the broker.

Broker-confirmed data (from Tradier /orders and /gainloss endpoints):

  2026-07-07  Order #135916939  753/752 PCS  filled @ $0.62 → SETTLED, P/L -$57.00
  2026-07-09  Order #136234854  747/746 PCS  filled @ $0.10 → OPEN (expires today)

This script:
  1. Finds each ERROR trade by expiration date and confirms it is still outcome=ERROR.
  2. Updates the row to outcome=FILLED with correct strike / credit / order fields.
  3. Assigns the next legacy_trade_num (TRD_00010, TRD_00011) and bumps the sequence.
  4. Sets tp_status=SETTLED + realized_pnl for the 07-07 trade (both legs expired ITM).
  5. Sets tp_status=OPEN for the 07-09 trade (expiration today; settlement pending).
  6. Prints a summary. Dry-run by default; pass --apply to commit.
"""
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path("data/captains_log/TRD.db")

# --------------------------------------------------------------------------- #
# Broker-confirmed fill data                                                   #
# --------------------------------------------------------------------------- #

TRADES_TO_RECONCILE = [
    {
        "expiration": "2026-07-07",
        "entry_order_id": "135916939",
        "short_put_strike": 753.0,
        "long_put_strike": 752.0,
        "entry_filled_price": 0.62,
        "net_credit": 0.62,
        "credit_received": 62.0,   # $0.62 × 100 shares × 1 contract
        "credit_fees": 0.00,       # commission charged to the short leg credit
        # Settlement: both legs expired ITM on 07-07.
        # From Tradier gainloss: long P752 P/L=-15.85, short P753 P/L=-41.15 → total -57.00
        "tp_status": "SETTLED",
        "realized_pnl": -57.00,
        "closed_at": "2026-07-08T12:15:00.000000+00:00",  # estimated next-day reconciliation
        "exit_reason": "SETTLED",
        "legacy_seq": 10,
    },
    {
        "expiration": "2026-07-09",
        "entry_order_id": "136234854",
        "short_put_strike": 747.0,
        "long_put_strike": 746.0,
        "entry_filled_price": 0.10,
        "net_credit": 0.10,
        "credit_received": 10.0,
        "credit_fees": 0.00,
        # Settlement not yet available — expires today.
        "tp_status": "OPEN",
        "realized_pnl": None,
        "closed_at": None,
        "exit_reason": None,
        "legacy_seq": 11,
    },
]


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def reconcile(dry_run: bool = True) -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    try:
        for td in TRADES_TO_RECONCILE:
            exp = td["expiration"]

            # Find the ERROR trade for this expiration
            row = conn.execute(
                "SELECT trade_id, outcome, legacy_trade_num, expiration, net_credit, tp_status "
                "FROM trades WHERE expiration = ? AND outcome = 'ERROR'",
                (exp,),
            ).fetchone()

            if row is None:
                # Check if already reconciled
                already = conn.execute(
                    "SELECT trade_id, outcome, legacy_trade_num FROM trades WHERE expiration = ?",
                    (exp,),
                ).fetchone()
                if already:
                    print(
                        f"[SKIP] {exp}: trade already has outcome={already['outcome']} "
                        f"legacy={already['legacy_trade_num']} — no action needed."
                    )
                else:
                    print(f"[WARN] {exp}: no trade found at all.")
                continue

            trade_id = row["trade_id"]
            legacy_num = f"TRD_{td['legacy_seq']:05d}_PCS"

            print(f"\n{'[DRY-RUN] ' if dry_run else ''}Reconciling {exp}:")
            print(f"  trade_id         = {trade_id}")
            print(f"  outcome          : ERROR → FILLED")
            print(f"  entry_order_id   = {td['entry_order_id']}")
            print(f"  short_put_strike = {td['short_put_strike']}")
            print(f"  long_put_strike  = {td['long_put_strike']}")
            print(f"  entry_filled_price = {td['entry_filled_price']}")
            print(f"  net_credit       = {td['net_credit']}")
            print(f"  tp_status        : NONE → {td['tp_status']}")
            print(f"  realized_pnl     = {td['realized_pnl']}")
            print(f"  legacy_trade_num = {legacy_num}")

            if not dry_run:
                conn.execute(
                    """
                    UPDATE trades SET
                        outcome             = 'FILLED',
                        entry_order_id      = ?,
                        short_put_strike    = ?,
                        long_put_strike     = ?,
                        entry_filled_price  = ?,
                        net_credit          = ?,
                        credit_received     = ?,
                        credit_fees         = ?,
                        tp_status           = ?,
                        realized_pnl        = ?,
                        closed_at           = ?,
                        exit_reason         = ?,
                        legacy_trade_num    = ?,
                        reason              = 'Manually reconciled: broker confirmed fill via Tradier /orders endpoint.'
                    WHERE trade_id = ? AND outcome = 'ERROR'
                    """,
                    (
                        td["entry_order_id"],
                        td["short_put_strike"],
                        td["long_put_strike"],
                        td["entry_filled_price"],
                        td["net_credit"],
                        td["credit_received"],
                        td["credit_fees"],
                        td["tp_status"],
                        td["realized_pnl"],
                        td["closed_at"],
                        td["exit_reason"],
                        legacy_num,
                        trade_id,
                    ),
                )

                # Bump the trade_sequence counter to match our highest assigned seq
                current_seq = conn.execute(
                    "SELECT last_seq FROM trade_sequence"
                ).fetchone()["last_seq"]
                if td["legacy_seq"] > current_seq:
                    conn.execute(
                        "UPDATE trade_sequence SET last_seq = ?", (td["legacy_seq"],)
                    )
                    print(f"  trade_sequence bumped: {current_seq} → {td['legacy_seq']}")

        if not dry_run:
            conn.commit()
            print("\n✓ Changes committed.")
        else:
            print("\n(Dry-run complete — no changes written. Pass --apply to commit.)")

        # Print final state
        print("\n--- Final FILLED trades in Captain's Log ---")
        rows = conn.execute(
            "SELECT legacy_trade_num, expiration, short_put_strike, long_put_strike, "
            "net_credit, tp_status, realized_pnl FROM trades WHERE outcome='FILLED' ORDER BY entered_at"
        ).fetchall()
        for r in rows:
            print(dict(r))

    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="Write changes to the database (default: dry-run)"
    )
    args = parser.parse_args()
    reconcile(dry_run=not args.apply)
