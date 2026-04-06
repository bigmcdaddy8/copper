#!/usr/bin/env python3
"""
Diagnostic: fetch an option chain from Tradier and inspect contracts near a
target delta, or look up a specific strike.

Reads TRADIER_API_KEY (and optionally TRADIER_ENV=sandbox) from a .env file
in the repo root, or from the environment directly.

Usage:
    python scripts/probe_tradier_chain.py [OPTIONS]

Options (all optional — defaults shown):
    --symbol      AAPL             Underlying ticker symbol
    --expiration  2026-05-15       Expiration date (YYYY-MM-DD)
    --option-type both             call | put | both
    --strike      <none>           If set, show only contracts at this exact strike
    --target-delta 0.20            Delta target for "closest to" display
    --sandbox                      Use Tradier sandbox endpoint

Environment:
    TRADIER_API_KEY            Production API key
    TRADIER_SANDBOX_API_KEY    Sandbox API key (used with --sandbox)
    TRADIER_ENV=sandbox        Alternative way to enable sandbox mode
"""

import argparse
import json
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Allow running directly without an editable install
# ---------------------------------------------------------------------------
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "apps" / "trade_hunter" / "src"))

from dotenv import load_dotenv  # noqa: E402

from trade_hunter.tradier.client import TradierAPIError, TradierClient  # noqa: E402

# ---------------------------------------------------------------------------
# Load .env from repo root
# ---------------------------------------------------------------------------
load_dotenv(_repo_root / ".env")

# ---------------------------------------------------------------------------
# CLI args
# ---------------------------------------------------------------------------
parser = argparse.ArgumentParser(
    description="Probe a Tradier option chain for a given symbol and expiration."
)
parser.add_argument("--symbol", default="AAPL", help="Underlying ticker (default: AAPL)")
parser.add_argument("--expiration", default="2026-05-15", help="Expiration date YYYY-MM-DD (default: 2026-05-15)")
parser.add_argument(
    "--option-type",
    dest="option_type",
    choices=["call", "put", "both"],
    default="both",
    help="Filter to call, put, or both (default: both)",
)
parser.add_argument(
    "--strike",
    type=float,
    default=None,
    help="Show only contracts at this exact strike price",
)
parser.add_argument(
    "--target-delta",
    dest="target_delta",
    type=float,
    default=0.20,
    help="Delta target for closest-to display (default: 0.20)",
)
parser.add_argument(
    "--sandbox",
    action="store_true",
    default=False,
    help="Use Tradier sandbox endpoint",
)
args = parser.parse_args()

# Resolve sandbox from flag or env
sandbox = args.sandbox or os.environ.get("TRADIER_ENV", "").lower() == "sandbox"

# Resolve API key
if sandbox:
    api_key = os.environ.get("TRADIER_SANDBOX_API_KEY", "")
    if not api_key:
        print("ERROR: TRADIER_SANDBOX_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)
else:
    api_key = os.environ.get("TRADIER_API_KEY", "")
    if not api_key:
        print("ERROR: TRADIER_API_KEY is not set.", file=sys.stderr)
        sys.exit(1)

SYMBOL = args.symbol.upper()
EXPIRATION = args.expiration
TARGET_DELTA = args.target_delta
OPTION_TYPE = args.option_type
STRIKE_FILTER = args.strike

print(f"Endpoint     : {'SANDBOX' if sandbox else 'PRODUCTION'}")
print(f"Symbol       : {SYMBOL}")
print(f"Expiry       : {EXPIRATION}")
print(f"Option type  : {OPTION_TYPE}")
print(f"Strike filter: {STRIKE_FILTER if STRIKE_FILTER else '(none — show nearest delta)'}")
print(f"Target Δ     : ±{TARGET_DELTA}")
print("-" * 60)

client = TradierClient(api_key=api_key, sandbox=sandbox)

# ---------------------------------------------------------------------------
# Step 1: confirm expiration is available
# ---------------------------------------------------------------------------
print(f"[1] Fetching option expirations for {SYMBOL} ...")
try:
    expirations = client.get_option_expirations(SYMBOL)
except TradierAPIError as exc:
    print(f"    ERROR: {exc}", file=sys.stderr)
    sys.exit(1)

print(f"    Available ({len(expirations)}): {expirations[:10]}{'...' if len(expirations) > 10 else ''}")

if EXPIRATION not in expirations:
    print(f"    WARNING: {EXPIRATION} not in expirations list — proceeding anyway ...")
else:
    print(f"    OK — {EXPIRATION} is present.")

# ---------------------------------------------------------------------------
# Step 2: fetch the option chain
# ---------------------------------------------------------------------------
print(f"\n[2] Fetching option chain for {SYMBOL} {EXPIRATION} (greeks=true) ...")
try:
    chain = client.get_option_chain(SYMBOL, EXPIRATION)
except TradierAPIError as exc:
    print(f"    ERROR: {exc}", file=sys.stderr)
    sys.exit(1)

print(f"    Contracts returned: {len(chain)}")
if not chain:
    print("    Chain is empty — no data from Tradier for this expiration.")
    sys.exit(0)

# ---------------------------------------------------------------------------
# Step 2b: dump raw first contract to inspect shape
# ---------------------------------------------------------------------------
print("\n[2b] Raw first contract (structure check):")
print(json.dumps(chain[0], indent=4))

# ---------------------------------------------------------------------------
# Step 3: filter by option type and optionally by strike
# ---------------------------------------------------------------------------
calls = [c for c in chain if c.get("option_type") == "call"]
puts  = [c for c in chain if c.get("option_type") == "put"]
print(f"\n[3] Calls: {len(calls)}  |  Puts: {len(puts)}")

calls_with_delta = [c for c in calls if c.get("delta") is not None]
puts_with_delta  = [p for p in puts  if p.get("delta") is not None]
print(f"    Calls with delta: {len(calls_with_delta)}  |  Puts with delta: {len(puts_with_delta)}")

# ---------------------------------------------------------------------------
# Step 4: exact strike lookup or nearest-delta display
# ---------------------------------------------------------------------------
def fmt_contract(c: dict) -> str:
    return (
        f"  symbol      : {c.get('symbol')}\n"
        f"  option_type : {c.get('option_type')}\n"
        f"  strike      : {c.get('strike')}\n"
        f"  delta       : {c.get('delta')}\n"
        f"  bid / ask   : {c.get('bid')} / {c.get('ask')}\n"
        f"  open_int    : {c.get('open_interest')}\n"
        f"  last        : {c.get('last')}\n"
    )


if STRIKE_FILTER is not None:
    print(f"\n[4] Contracts at strike {STRIKE_FILTER}:")
    matched = [c for c in chain if c.get("strike") == STRIKE_FILTER]
    if OPTION_TYPE != "both":
        matched = [c for c in matched if c.get("option_type") == OPTION_TYPE]
    if matched:
        for c in matched:
            print(fmt_contract(c))
    else:
        print(f"    No contracts found at strike {STRIKE_FILTER}"
              f"{' (' + OPTION_TYPE + ')' if OPTION_TYPE != 'both' else ''}.")
else:
    if OPTION_TYPE in ("call", "both"):
        print(f"\n[4] CALL closest to Δ +{TARGET_DELTA}:")
        candidates = sorted(calls_with_delta, key=lambda c: abs(c["delta"] - TARGET_DELTA))
        if candidates:
            print(fmt_contract(candidates[0]))
            print(f"    Top 3 calls nearest Δ +{TARGET_DELTA}:")
            for c in candidates[:3]:
                print(f"      strike={c.get('strike'):>8}  delta={c.get('delta'):>8.4f}"
                      f"  bid={c.get('bid')}  ask={c.get('ask')}  OI={c.get('open_interest')}")
        else:
            print("    No qualifying calls (all deltas null).")

    if OPTION_TYPE in ("put", "both"):
        print(f"\n[5] PUT closest to Δ -{TARGET_DELTA}:")
        candidates = sorted(puts_with_delta, key=lambda c: abs(c["delta"] - (-TARGET_DELTA)))
        if candidates:
            print(fmt_contract(candidates[0]))
            print(f"    Top 3 puts nearest Δ -{TARGET_DELTA}:")
            for p in candidates[:3]:
                print(f"      strike={p.get('strike'):>8}  delta={p.get('delta'):>8.4f}"
                      f"  bid={p.get('bid')}  ask={p.get('ask')}  OI={p.get('open_interest')}")
        else:
            print("    No qualifying puts (all deltas null).")

print("\nDone.")
