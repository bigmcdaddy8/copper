from datetime import date


def _is_monthly_expiration(exp_date: date) -> bool:
    """Return True if exp_date is the third Friday of its month (standard monthly cycle)."""
    first_of_month = date(exp_date.year, exp_date.month, 1)
    days_to_first_friday = (4 - first_of_month.weekday()) % 7  # weekday 4 = Friday
    third_friday = date(exp_date.year, exp_date.month, 1 + days_to_first_friday + 14)
    return exp_date == third_friday


def select_expiration(
    expirations: list[str],
    run_date: date,
    min_dte: int = 30,
    max_dte: int = 60,
) -> str | None:
    """Return the nearest qualifying monthly expiration string, or None.

    A qualifying expiration:
      - Falls on the third Friday of its month (standard monthly cycle).
      - Has DTE in [min_dte, max_dte] inclusive (calendar days from run_date).

    When multiple dates qualify, the one with the lowest DTE is returned.
    """
    best: tuple[int, str] | None = None  # (dte, date_string)

    for exp_str in expirations:
        exp_date = date.fromisoformat(exp_str)
        if not _is_monthly_expiration(exp_date):
            continue
        dte = (exp_date - run_date).days
        if dte < min_dte or dte > max_dte:
            continue
        if best is None or dte < best[0]:
            best = (dte, exp_str)

    return best[1] if best is not None else None


def select_put(chain: list[dict]) -> dict | None:
    """Return the put with delta <= -0.21 closest to -0.21 (highest / least-negative delta).

    Delta is read from the top-level "delta" key of each contract dict.
    Contracts where delta is None are skipped.
    Returns None if no qualifying put exists.
    """
    best: dict | None = None
    best_delta: float | None = None

    for contract in chain:
        if contract.get("option_type") != "put":
            continue
        delta = contract.get("delta")
        if delta is None:
            continue
        if delta > -0.21:
            continue
        if best_delta is None or delta > best_delta:
            best = contract
            best_delta = delta

    return best


def select_call(chain: list[dict]) -> dict | None:
    """Return the call with delta >= 0.21 closest to 0.21 (lowest positive delta).

    Delta is read from the top-level "delta" key of each contract dict.
    Contracts where delta is None are skipped.
    Returns None if no qualifying call exists.
    """
    best: dict | None = None
    best_delta: float | None = None

    for contract in chain:
        if contract.get("option_type") != "call":
            continue
        delta = contract.get("delta")
        if delta is None:
            continue
        if delta < 0.21:
            continue
        if best_delta is None or delta < best_delta:
            best = contract
            best_delta = delta

    return best
