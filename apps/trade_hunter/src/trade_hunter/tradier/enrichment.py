import time
from datetime import date

import pandas as pd

from trade_hunter.tradier.client import TradierAPIError, TradierClient
from trade_hunter.tradier.selector import select_call, select_expiration, select_put

_THROTTLE_CHANGE_THRESHOLD = 0.50  # fire notice when delay shifts by >50%
_THROUGHPUT_REPORT_INTERVAL = 30.0  # seconds between periodic throughput lines


def enrich_candidates(
    candidates: pd.DataFrame,
    side: str,
    client: TradierClient,
    run_date: date,
    min_dte: int = 30,
    max_dte: int = 60,
    verbose: bool = False,
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
        verbose:     When True, print per-ticker progress, throttle-change notices,
                     periodic throughput lines, and an end-of-side summary.

    Returns:
        (enriched_df, warnings)
        enriched_df has all original columns plus Tradier fields.
        An empty DataFrame is returned (not an error) if all tickers are skipped.
    """
    warnings: list[str] = []

    if candidates.empty:
        return pd.DataFrame(), warnings

    enriched_rows: list[dict] = []
    total = len(candidates)

    # Monitoring state
    api_call_count: int = 0
    side_start_time: float = time.time()
    last_report_time: float = side_start_time
    prev_delay: float | None = None

    for idx, (_, row) in enumerate(candidates.iterrows(), start=1):
        symbol: str = row["Symbol"]
        current_pace = client.last_computed_delay

        if verbose:
            # Throttle-change notice — fires when pace shifts >50% from previous ticker
            if prev_delay is not None and prev_delay > 0:
                ratio = current_pace / prev_delay
                if ratio > (1 + _THROTTLE_CHANGE_THRESHOLD) or ratio < (1 - _THROTTLE_CHANGE_THRESHOLD):
                    _print_throttle_change(side, prev_delay, current_pace, client)

            # Periodic throughput line every ~30 seconds
            now = time.time()
            if api_call_count > 0 and (now - last_report_time) >= _THROUGHPUT_REPORT_INTERVAL:
                elapsed = now - side_start_time
                rate = api_call_count / elapsed * 60
                print(
                    f"[{side:<4}] throughput: {api_call_count} API calls"
                    f" in {_fmt_elapsed(elapsed)} = {rate:.1f} calls/min"
                )
                last_report_time = now

            _print_progress(idx, total, side, symbol, client, current_pace)

        prev_delay = current_pace

        # Step 1: select expiration
        api_call_count += 1
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
        api_call_count += 1
        try:
            last_price = client.get_last_price(symbol)
        except TradierAPIError as exc:
            warnings.append(f"[{side}] '{symbol}' — Tradier API error ({exc}), skipped")
            continue

        # Step 3: fetch chain and select contract
        api_call_count += 1
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

    if verbose:
        enriched_count = len(enriched_rows)
        skipped_count = total - enriched_count
        elapsed = time.time() - side_start_time
        rate = api_call_count / elapsed * 60 if elapsed > 0 else 0.0
        print(
            f"[{side:<4}] complete — enriched {enriched_count}/{total},"
            f" skipped {skipped_count}"
            f"  ({api_call_count} API calls in {_fmt_elapsed(elapsed)}"
            f" = {rate:.1f} calls/min)"
        )

    if not enriched_rows:
        return pd.DataFrame(), warnings

    return pd.DataFrame(enriched_rows).reset_index(drop=True), warnings


# ---------------------------------------------------------------------------
# Verbose output helpers
# ---------------------------------------------------------------------------


def _print_progress(
    idx: int,
    total: int,
    side: str,
    symbol: str,
    client: TradierClient,
    pace: float,
) -> None:
    width = len(str(total))
    available, expiry_ms = client.rate_limit_state
    if available is not None and expiry_ms is not None:
        secs = max(0, int(expiry_ms / 1000 - time.time()))
        rate_str = f"rate: {available} avail, resets in {secs}s | pace: {pace:.2f}s/call"
    elif available is not None:
        rate_str = f"rate: {available} avail | pace: {pace:.2f}s/call"
    else:
        rate_str = f"pace: {pace:.2f}s/call"
    line = f"[{side:<4}] {idx:{width}}/{total} — enriching {symbol:<8}  ({rate_str})"
    print(line)


def _print_throttle_change(
    side: str,
    prev_delay: float,
    current_delay: float,
    client: TradierClient,
) -> None:
    available, expiry_ms = client.rate_limit_state
    if available is not None and expiry_ms is not None:
        secs = max(0, int(expiry_ms / 1000 - time.time()))
        state_str = f"  (rate: {available} avail, resets in {secs}s)"
    else:
        state_str = ""
    direction = "slowing" if current_delay > prev_delay else "speeding up"
    print(
        f"[throttle] pacing adjusted ({direction}):"
        f" {prev_delay:.2f}s → {current_delay:.2f}s/call{state_str}"
    )


def _fmt_elapsed(seconds: float) -> str:
    secs = int(seconds)
    if secs < 60:
        return f"{secs}s"
    return f"{secs // 60}m {secs % 60}s"
