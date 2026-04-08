import pandas as pd


def check_active_symbols_in_universe(
    active_symbols: frozenset[str],
    universal_dataset: pd.DataFrame,
) -> list[str]:
    """Return a warning for each active symbol absent from the Universal Data Set.

    Does not raise — missing active symbols are informational, not a blocking error.
    """
    warnings: list[str] = []
    universe_symbols = set(universal_dataset["Symbol"])
    for sym in sorted(active_symbols):  # sorted for deterministic warning order
        if sym not in universe_symbols:
            warnings.append(f"[Journal] Active symbol '{sym}' not found in Universal Data Set")
    return warnings


def filter_and_join(
    candidates: pd.DataFrame,
    universal_dataset: pd.DataFrame,
    active_symbols: frozenset[str],
    side: str,
) -> tuple[pd.DataFrame, list[str]]:
    """Apply open-trade exclusion and universe membership filter, then join to Universal Data Set.

    Steps:
      1. Drop GOOG (use GOOGL instead).
      2. Remove rows whose Symbol is in active_symbols (open-trade exclusion).
      3. Remove rows whose Symbol is not in universal_dataset (log warning per ticker).
      4. Merge remaining rows with universal_dataset on Symbol (inner join).

    Args:
        candidates:        SeekingAlpha DataFrame (Symbol, Quant Rating, Growth, Momentum, …).
        universal_dataset: TastyTrade DataFrame (Symbol, IV Rank, IV %tile, Sector, …).
        active_symbols:    Deduplicated set of open-trade tickers.
        side:              "BULL" or "BEAR" — used only for warning message labels.

    Returns:
        (joined_df, warnings)
    """
    warnings: list[str] = []

    if candidates.empty:
        return pd.DataFrame(), warnings

    universe_symbols = set(universal_dataset["Symbol"])

    # Step 1: drop GOOG — GOOGL is the canonical ticker for this symbol
    goog_mask = candidates["Symbol"] == "GOOG"
    if goog_mask.any():
        warnings.append(f"[{side}] 'GOOG' dropped — use GOOGL")
        candidates = candidates[~goog_mask].copy()

    if candidates.empty:
        return pd.DataFrame(), warnings

    # Step 3: exclude open trades (checked before universe membership)
    open_trade_mask = candidates["Symbol"].isin(active_symbols)
    for sym in candidates.loc[open_trade_mask, "Symbol"]:
        warnings.append(f"[{side}] '{sym}' excluded — active open trade")
    remaining = candidates[~open_trade_mask].copy()

    if remaining.empty:
        return pd.DataFrame(), warnings

    # Step 4: exclude candidates not in the Universal Data Set
    not_in_universe_mask = ~remaining["Symbol"].isin(universe_symbols)
    for sym in remaining.loc[not_in_universe_mask, "Symbol"]:
        warnings.append(f"[{side}] '{sym}' not in Universal Data Set — skipped")
    remaining = remaining[~not_in_universe_mask].copy()

    if remaining.empty:
        return pd.DataFrame(), warnings

    # Step 5: join to Universal Data Set
    joined = pd.merge(remaining, universal_dataset, on="Symbol", how="inner")
    return joined.reset_index(drop=True), warnings
