from datetime import date

import pandas as pd

from trade_hunter.tradier.client import TradierAPIError, TradierClient
from trade_hunter.tradier.selector import select_call, select_expiration, select_put


def enrich_candidates(
    candidates: pd.DataFrame,
    side: str,
    client: TradierClient,
    run_date: date,
    min_dte: int = 30,
    max_dte: int = 60,
) -> tuple[pd.DataFrame, list[str]]:
    """Fetch Tradier data for each candidate and return an enriched DataFrame.

    For each ticker in candidates["Symbol"]:
      1. Fetch option expirations → select nearest monthly in DTE window.
         Skip with warning if none qualifies.
      2. Fetch current underlying last price (quotes endpoint).
         Skip with warning on API error.
      3. Fetch option chain for selected expiration.
         Apply select_put (BULL) or select_call (BEAR).
         Skip with warning if no qualifying option found.
      4. Append all required Tradier fields to the enriched row.

    Args:
        candidates:  Joined DataFrame from filter_and_join (Symbol + all prior columns).
        side:        "BULL" or "BEAR" — determines put vs call selection.
        client:      Configured TradierClient instance.
        run_date:    Date used for DTE calculation (normally today).
        min_dte:     Minimum DTE threshold (inclusive).
        max_dte:     Maximum DTE threshold (inclusive).

    Returns:
        (enriched_df, warnings)
        enriched_df has all original columns plus Tradier fields.
        An empty DataFrame is returned (not an error) if all tickers are skipped.
    """
    warnings: list[str] = []

    if candidates.empty:
        return pd.DataFrame(), warnings

    enriched_rows: list[dict] = []

    for _, row in candidates.iterrows():
        symbol: str = row["Symbol"]

        # Step 1: select expiration
        try:
            expirations = client.get_option_expirations(symbol)
        except TradierAPIError as exc:
            warnings.append(f"[{side}] '{symbol}' — Tradier API error ({exc}), skipped")
            continue

        expiration = select_expiration(expirations, run_date, min_dte, max_dte)
        if expiration is None:
            warnings.append(
                f"[{side}] '{symbol}' — no qualifying monthly expiration found, skipped"
            )
            continue

        # Step 2: fetch last price
        try:
            last_price = client.get_last_price(symbol)
        except TradierAPIError as exc:
            warnings.append(f"[{side}] '{symbol}' — Tradier API error ({exc}), skipped")
            continue

        # Step 3: fetch chain and select contract
        try:
            chain = client.get_option_chain(symbol, expiration)
        except TradierAPIError as exc:
            warnings.append(f"[{side}] '{symbol}' — Tradier API error ({exc}), skipped")
            continue

        contract = select_put(chain) if side == "BULL" else select_call(chain)

        if contract is None:
            option_label = "put" if side == "BULL" else "call"
            warnings.append(
                f"[{side}] '{symbol}' — no qualifying {option_label} for {expiration}, skipped"
            )
            continue

        # Step 4: build enriched row
        dte = (date.fromisoformat(expiration) - run_date).days
        enriched_row = row.to_dict()
        enriched_row["Expiration Date"] = expiration
        enriched_row["DTE"] = dte
        enriched_row["Last Price"] = last_price
        enriched_row["Strike"] = contract.get("strike")
        enriched_row["Option Type"] = contract.get("option_type")
        enriched_row["Delta"] = contract.get("delta")
        enriched_row["Open Interest"] = contract.get("open_interest")
        enriched_row["Bid"] = contract.get("bid")
        enriched_row["Ask"] = contract.get("ask")
        enriched_rows.append(enriched_row)

    if not enriched_rows:
        return pd.DataFrame(), warnings

    return pd.DataFrame(enriched_rows).reset_index(drop=True), warnings
