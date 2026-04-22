from __future__ import annotations
import math
from datetime import date, datetime

from bic.models import OptionChain, OptionContract


def minutes_until_close(virtual_now: datetime, session_close: str = "15:00") -> int:
    """Return minutes from virtual_now to today's market close. Returns 0 if at/past close."""
    close_h, close_m = (int(x) for x in session_close.split(":"))
    close_minutes = close_h * 60 + close_m
    now_minutes = virtual_now.hour * 60 + virtual_now.minute
    return max(0, close_minutes - now_minutes)


def compute_option_price(
    underlying: float,
    strike: float,
    option_type: str,
    minutes_to_close: int,
    iv_base: float = 0.20,
) -> tuple[float, float]:
    """Return (bid, ask) for an option. Both rounded to nearest 0.05. Minimum bid 0.05."""
    if option_type == "CALL":
        intrinsic = max(0.0, underlying - strike)
    else:
        intrinsic = max(0.0, strike - underlying)

    moneyness_distance = abs(underlying - strike)
    time_factor = max(0.0, math.sqrt(minutes_to_close / (252 * 390)))
    extrinsic = (
        iv_base
        * underlying
        * time_factor
        * math.exp(-moneyness_distance / (underlying * 0.01))
    )

    raw_price = intrinsic + extrinsic
    mid = round(raw_price / 0.05) * 0.05
    bid = max(0.05, round(mid - 0.05, 2))
    ask = round(mid + 0.05, 2)
    return bid, ask


def compute_delta(
    underlying: float,
    strike: float,
    option_type: str,
    minutes_to_close: int,
) -> float:
    """Return synthetic delta rounded to 2 decimal places.
    Uses a sigmoid approximation of moneyness. Not financially rigorous."""
    moneyness = (underlying - strike) / underlying * 100
    time_factor = max(0.1, minutes_to_close / 390.0)
    raw = 1.0 / (1.0 + math.exp(-moneyness / (time_factor * 1.3)))

    if option_type == "CALL":
        delta = round(raw, 2)
        return max(0.01, min(0.99, delta))
    else:
        delta = round(raw - 1.0, 2)
        return max(-0.99, min(-0.01, delta))


def build_option_chain(
    underlying: float,
    expiration: date,
    virtual_now: datetime,
    iv_base: float = 0.20,
) -> OptionChain:
    """Build a synthetic OptionChain for SPX.

    Strike range: underlying ± 150 in 5-point increments.
    Returns 61 strikes × 2 types = 122 OptionContract objects, sorted by strike ascending.
    """
    minutes = minutes_until_close(virtual_now)

    # Compute strike range: round underlying to nearest 5, then ±150
    atm = round(underlying / 5.0) * 5.0
    strikes = [atm + (i * 5.0) for i in range(-30, 31)]  # 61 strikes

    contracts: list[OptionContract] = []
    for strike in strikes:
        for option_type in ("CALL", "PUT"):
            bid, ask = compute_option_price(underlying, strike, option_type, minutes, iv_base)
            delta = compute_delta(underlying, strike, option_type, minutes)
            contracts.append(
                OptionContract(
                    strike=strike,
                    option_type=option_type,
                    bid=bid,
                    ask=ask,
                    delta=delta,
                )
            )

    # Sort by strike ascending
    contracts.sort(key=lambda c: (c.strike, c.option_type))

    return OptionChain(symbol="SPX", expiration=expiration, options=contracts)
