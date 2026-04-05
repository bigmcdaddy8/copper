import pandas as pd


def apply_hard_filters(
    enriched: pd.DataFrame,
    side: str,
    min_open_interest: int = 8,
    min_bid: float = 0.55,
    max_spread_pct: float = 0.13,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply hard filters to the enriched candidate DataFrame.

    Filters applied in order:
      1. Open Interest >= min_open_interest
      2. Bid >= min_bid
      3. Spread% = (Ask - Bid) / ((Ask + Bid) / 2) <= max_spread_pct

    The Monthly Cycle filter is satisfied by construction (select_expiration
    guarantees a monthly expiration) and is not checked here.

    Args:
        enriched:           Enriched DataFrame from enrich_candidates().
        side:               "BULL" or "BEAR" — used in warning messages only.
        min_open_interest:  Minimum open interest (default 8).
        min_bid:            Minimum bid (default 0.55).
        max_spread_pct:     Maximum spread fraction (default 0.13 = 13%).

    Returns:
        (surviving_df, warnings)
        One warning per filtered-out row, stating the symbol and reason.
    """
    warnings: list[str] = []

    if enriched.empty:
        return pd.DataFrame(), warnings

    remaining = enriched.copy()

    # Filter 1: Open Interest
    fail_oi = remaining["Open Interest"] < min_open_interest
    for sym in remaining.loc[fail_oi, "Symbol"]:
        oi_val = int(remaining.loc[remaining["Symbol"] == sym, "Open Interest"].iloc[0])
        warnings.append(f"[{side}] '{sym}' filtered — open interest {oi_val} < {min_open_interest}")
    remaining = remaining[~fail_oi].copy()

    if remaining.empty:
        return pd.DataFrame(), warnings

    # Filter 2: Bid
    fail_bid = remaining["Bid"] < min_bid
    for sym in remaining.loc[fail_bid, "Symbol"]:
        bid_val = float(remaining.loc[remaining["Symbol"] == sym, "Bid"].iloc[0])
        warnings.append(f"[{side}] '{sym}' filtered — bid {bid_val:.2f} < {min_bid:.2f}")
    remaining = remaining[~fail_bid].copy()

    if remaining.empty:
        return pd.DataFrame(), warnings

    # Filter 3: Spread% = (Ask - Bid) / ((Ask + Bid) / 2)
    mid = (remaining["Ask"] + remaining["Bid"]) / 2.0
    spread_pct = (remaining["Ask"] - remaining["Bid"]) / mid
    fail_spread = spread_pct > max_spread_pct
    for sym in remaining.loc[fail_spread, "Symbol"]:
        idx = remaining.loc[remaining["Symbol"] == sym].index[0]
        sp = float(spread_pct.loc[idx]) * 100
        warnings.append(
            f"[{side}] '{sym}' filtered — spread {sp:.1f}% > {max_spread_pct * 100:.1f}%"
        )
    remaining = remaining[~fail_spread].copy()

    if remaining.empty:
        return pd.DataFrame(), warnings

    return remaining.reset_index(drop=True), warnings
