#!/usr/bin/env python3
"""probe_entry_price.py — show live bid/ask and K9 entry price for a trade spec.

Fetches the live XSP option chain from Tradier, runs the same strike-selection
and pricing logic K9 uses at entry, and prints a detailed breakdown.
Does NOT place any orders.

Usage (from repo root, with .venv active):
    python scripts/probe_entry_price.py
    python scripts/probe_entry_price.py --spec apps/K9/trade_specs/xsp_pcs_0dte_PROD.yaml
    python scripts/probe_entry_price.py --spec apps/K9/trade_specs/xsp_pcs_0dte_PROD.yaml --expiration 2026-08-01
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Ensure repo packages are importable when run as a plain script
repo_root = Path(__file__).resolve().parent.parent
for pkg_dir in [
    repo_root / "apps/K9/src",
    repo_root / "apps/bic/src",
]:
    if str(pkg_dir) not in sys.path:
        sys.path.insert(0, str(pkg_dir))

from dotenv import load_dotenv

load_dotenv(repo_root / ".env")

from K9.config import TradeSpec
from K9.tradier.broker import TradierBroker
from K9.tradier.selector import select_long_put, select_short_put_preferred

_CT = ZoneInfo("America/Chicago")
_DEFAULT_SPEC = repo_root / "apps/K9/trade_specs/xsp_pcs_0dte_PROD.yaml"


def _hr(label: str) -> None:
    width = 60
    print(f"\n{'─' * width}")
    print(f"  {label}")
    print(f"{'─' * width}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--spec",
        default=str(_DEFAULT_SPEC),
        help="Path to trade spec YAML (default: xsp_pcs_0dte_PROD.yaml)",
    )
    parser.add_argument(
        "--expiration",
        default=None,
        help="Expiration date YYYY-MM-DD (default: today CT)",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------ #
    # 1. Load spec                                                         #
    # ------------------------------------------------------------------ #
    spec = TradeSpec.from_file(args.spec)
    spec_name = Path(args.spec).stem

    now_ct = datetime.now(tz=_CT)
    expiration: date = (
        date.fromisoformat(args.expiration) if args.expiration else now_ct.date()
    )

    _hr("PROBE ENTRY PRICE")
    print(f"  Spec          : {spec_name}")
    print(f"  Underlying    : {spec.underlying}")
    print(f"  Strategy      : {spec.trade_type}")
    print(f"  Wing width    : ${spec.wing_size}")
    print(f"  Delta target  : {spec.short_put_selection.delta_preferred:+.2f}")
    print(f"  Delta range   : [{spec.short_put_selection.delta_range_min:+.3f}, "
          f"{spec.short_put_selection.delta_range_max:+.3f}]")
    print(f"  Min credit    : ${spec.minimum_net_credit:.2f}")
    print(f"  Max credit    : {'none' if spec.maximum_net_credit is None else f'${spec.maximum_net_credit:.2f}'}")
    print(f"  Expiration    : {expiration.isoformat()}")
    print(f"  Queried at    : {now_ct.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # ------------------------------------------------------------------ #
    # 2. Connect to Tradier                                                #
    # ------------------------------------------------------------------ #
    api_key = os.environ.get("TRADIER_API_KEY", "")
    account_id = os.environ.get("TRADIER_ACCOUNT_ID", "")
    if not api_key or not account_id:
        print("\nERROR: TRADIER_API_KEY and TRADIER_ACCOUNT_ID must be set in .env")
        sys.exit(1)

    broker = TradierBroker(api_key=api_key, account_id=account_id, sandbox=False)

    # ------------------------------------------------------------------ #
    # 3. Underlying quote                                                  #
    # ------------------------------------------------------------------ #
    _hr("UNDERLYING QUOTE")
    try:
        quote = broker.get_underlying_quote(spec.underlying)
        print(f"  {spec.underlying:6s}  last={quote.last:.2f}  bid={quote.bid:.2f}  ask={quote.ask:.2f}")
        underlying_last = quote.last
    except Exception as exc:
        print(f"  ERROR fetching underlying quote: {exc}")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 4. Option chain                                                      #
    # ------------------------------------------------------------------ #
    _hr("OPTION CHAIN FETCH")
    try:
        chain = broker.get_option_chain(spec.underlying, expiration)
        puts = [o for o in chain.options if o.option_type == "PUT"]
        print(f"  Fetched {len(chain.options)} contracts  ({len(puts)} puts) "
              f"for {spec.underlying} exp {expiration.isoformat()}")
    except Exception as exc:
        print(f"  ERROR fetching option chain: {exc}")
        sys.exit(1)

    # ------------------------------------------------------------------ #
    # 5. Strike selection (same logic as runner.py)                        #
    # ------------------------------------------------------------------ #
    _hr("STRIKE SELECTION")
    try:
        short_put = select_short_put_preferred(
            chain,
            delta_preferred=spec.short_put_selection.delta_preferred,
            delta_range_min=spec.short_put_selection.delta_range_min,
            delta_range_max=spec.short_put_selection.delta_range_max,
            underlying_last=underlying_last,
        )
        long_put = select_long_put(chain, short_put, spec.wing_size)
    except Exception as exc:
        print(f"  ERROR during strike selection: {exc}")
        sys.exit(1)

    sp = short_put
    lp = long_put
    print(f"  Short put selected: strike={sp.strike:.1f}  delta={sp.delta:+.4f}")
    print(f"  Long  put selected: strike={lp.strike:.1f}  delta={lp.delta:+.4f}")

    # ------------------------------------------------------------------ #
    # 6. Combo pricing (same formula as constructor.build_order)           #
    # ------------------------------------------------------------------ #
    _hr("COMBO PRICING  (K9 calculation)")
    combo_bid = round(sp.bid - lp.ask, 2)
    combo_ask = round(sp.ask - lp.bid, 2)
    combo_mid = round((combo_bid + combo_ask) / 2, 2)
    limit_price = round(combo_mid + spec.entry.limit_price_offset, 2)

    print(f"  {'':8s}  {'strike':>8s}  {'delta':>8s}  {'bid':>6s}  {'ask':>6s}  {'mid':>6s}")
    print(f"  {'Short put':8s}  {sp.strike:>8.1f}  {sp.delta:>+8.4f}  {sp.bid:>6.2f}  {sp.ask:>6.2f}  {round((sp.bid + sp.ask) / 2, 2):>6.2f}")
    print(f"  {'Long  put':8s}  {lp.strike:>8.1f}  {lp.delta:>+8.4f}  {lp.bid:>6.2f}  {lp.ask:>6.2f}  {round((lp.bid + lp.ask) / 2, 2):>6.2f}")
    print()
    print(f"  Combo bid   = short_put.bid − long_put.ask  = {sp.bid:.2f} − {lp.ask:.2f} = {combo_bid:.2f}")
    print(f"  Combo ask   = short_put.ask − long_put.bid  = {sp.ask:.2f} − {lp.bid:.2f} = {combo_ask:.2f}")
    print(f"  Combo mid   = (bid + ask) / 2               = {combo_mid:.2f}  ← K9 initial limit price")
    if spec.entry.limit_price_offset:
        print(f"  + offset    = {spec.entry.limit_price_offset:+.2f}")
        print(f"  Limit price =                                {limit_price:.2f}")

    # ------------------------------------------------------------------ #
    # 7. Entry eligibility verdict                                         #
    # ------------------------------------------------------------------ #
    _hr("ENTRY ELIGIBILITY VERDICT")
    effective_credit = limit_price
    capped = False
    if spec.maximum_net_credit is not None and effective_credit > spec.maximum_net_credit:
        effective_credit = spec.maximum_net_credit
        capped = True

    passes_min = effective_credit >= spec.minimum_net_credit

    print(f"  Initial limit price : ${limit_price:.2f}")
    if capped:
        print(f"  *** CAPPED to max   : ${effective_credit:.2f}  (max_credit_received={spec.maximum_net_credit:.2f})")
    print(f"  Min credit required : ${spec.minimum_net_credit:.2f}")
    print()
    if passes_min:
        print(f"  ✓  WOULD ENTER  —  K9 would submit at ${effective_credit:.2f}")
        retry_prices = []
        price = effective_credit
        for attempt in range(1, spec.entry.max_fill_time_seconds and spec.entry.max_entry_attempts + 1):
            if price < spec.minimum_net_credit:
                break
            retry_prices.append((attempt, round(price, 2)))
            price = round(price - spec.entry.retry_price_decrement, 2)
        print(f"\n  Retry price-walk (up to {spec.entry.max_entry_attempts} attempts, "
              f"${spec.entry.retry_price_decrement:.2f} decrement, "
              f"{spec.entry.max_fill_time_seconds}s window each):")
        for attempt, p in retry_prices:
            note = " ← would stop (below min)" if p < spec.minimum_net_credit else ""
            print(f"    Attempt {attempt}: ${p:.2f}{note}")
    else:
        print(f"  ✗  WOULD SKIP   —  ${effective_credit:.2f} < min_credit_received ${spec.minimum_net_credit:.2f}")

    print()


if __name__ == "__main__":
    main()
