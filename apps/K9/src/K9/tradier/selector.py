"""Delta-based strike selection for K9 trade types (K9-0040)."""
from __future__ import annotations

from datetime import date

from bic.models import OptionChain, OptionContract


# ------------------------------------------------------------------ #
# Expiration selection                                                #
# ------------------------------------------------------------------ #

def select_0dte_expiration(expirations: list[date], today: date) -> date:
    """Return today's expiration from *expirations*, or raise if none exists.

    Args:
        expirations: List of available expiration dates.
        today: The reference date (use broker.get_current_time().date()).

    Raises:
        ValueError: If no 0DTE expiration is found for *today*.
    """
    for exp in expirations:
        if exp == today:
            return exp
    raise ValueError(
        f"No 0DTE expiration found for {today.isoformat()}. "
        f"Available: {[e.isoformat() for e in sorted(expirations)[:5]]}"
    )


# ------------------------------------------------------------------ #
# Short leg selection                                                 #
# ------------------------------------------------------------------ #

def select_short_put(chain: OptionChain, target_delta: float) -> OptionContract:
    """Return the put contract whose delta is closest to *-target_delta/100*.

    Args:
        chain: Full option chain (BIC OptionChain).
        target_delta: Absolute delta value as a whole number (e.g. 20 for ~0.20Δ).

    Raises:
        ValueError: If the chain has no put contracts.
    """
    puts = [o for o in chain.options if o.option_type == "PUT"]
    if not puts:
        raise ValueError(f"No PUT contracts found in chain for {chain.symbol}.")
    target = -abs(target_delta) / 100.0
    return min(puts, key=lambda o: abs(o.delta - target))


def select_short_put_preferred(
    chain: OptionChain,
    delta_preferred: float,
    delta_range_min: float,
    delta_range_max: float,
    underlying_last: float,
) -> OptionContract:
    """Select short put using preferred delta within range and ATM tie-break.

    Selection steps:
    1) Keep only puts within [delta_range_min, delta_range_max] inclusive.
    2) Pick contract with minimum distance to delta_preferred.
    3) On ties, pick strike closest to ATM (underlying_last).
    4) If still tied, prefer higher strike for deterministic behavior.
    """
    puts = [o for o in chain.options if o.option_type == "PUT"]
    if not puts:
        raise ValueError(f"No PUT contracts found in chain for {chain.symbol}.")

    low = min(delta_range_min, delta_range_max)
    high = max(delta_range_min, delta_range_max)
    in_range = [o for o in puts if low <= o.delta <= high]
    if not in_range:
        raise ValueError(
            "No PUT contracts matched short_put.delta_range "
            f"[{low:.3f}, {high:.3f}] for {chain.symbol}."
        )

    return min(
        in_range,
        key=lambda o: (
            abs(o.delta - delta_preferred),
            abs(o.strike - underlying_last),
            -o.strike,
        ),
    )


def select_short_call(chain: OptionChain, target_delta: float) -> OptionContract:
    """Return the call contract whose delta is closest to *+target_delta/100*.

    Args:
        chain: Full option chain (BIC OptionChain).
        target_delta: Absolute delta value as a whole number (e.g. 20 for ~0.20Δ).

    Raises:
        ValueError: If the chain has no call contracts.
    """
    calls = [o for o in chain.options if o.option_type == "CALL"]
    if not calls:
        raise ValueError(f"No CALL contracts found in chain for {chain.symbol}.")
    target = abs(target_delta) / 100.0
    return min(calls, key=lambda o: abs(o.delta - target))


def select_short_call_preferred(
    chain: OptionChain,
    delta_preferred: float,
    delta_range_min: float,
    delta_range_max: float,
    underlying_last: float,
) -> OptionContract:
    """Select short call using preferred delta within range and ATM tie-break."""
    calls = [o for o in chain.options if o.option_type == "CALL"]
    if not calls:
        raise ValueError(f"No CALL contracts found in chain for {chain.symbol}.")

    low = min(delta_range_min, delta_range_max)
    high = max(delta_range_min, delta_range_max)
    in_range = [o for o in calls if low <= o.delta <= high]
    if not in_range:
        raise ValueError(
            "No CALL contracts matched short_call.delta_range "
            f"[{low:.3f}, {high:.3f}] for {chain.symbol}."
        )

    return min(
        in_range,
        key=lambda o: (
            abs(o.delta - delta_preferred),
            abs(o.strike - underlying_last),
            o.strike,
        ),
    )


# ------------------------------------------------------------------ #
# Long (wing) leg selection                                           #
# ------------------------------------------------------------------ #

def select_long_put(
    chain: OptionChain, short_put: OptionContract, wing_size: int
) -> OptionContract:
    """Return the long put wing *wing_size* points below *short_put*.

    Raises:
        ValueError: If the wing strike is not found in the chain.
    """
    wing_strike = short_put.strike - wing_size
    return _find_put(chain, wing_strike)


def select_long_call(
    chain: OptionChain, short_call: OptionContract, wing_size: int
) -> OptionContract:
    """Return the long call wing *wing_size* points above *short_call*.

    Raises:
        ValueError: If the wing strike is not found in the chain.
    """
    wing_strike = short_call.strike + wing_size
    return _find_call(chain, wing_strike)


# ------------------------------------------------------------------ #
# Helpers                                                             #
# ------------------------------------------------------------------ #

def _find_put(chain: OptionChain, strike: float) -> OptionContract:
    for o in chain.options:
        if o.option_type == "PUT" and abs(o.strike - strike) < 0.01:
            return o
    raise ValueError(
        f"No PUT contract found at strike {strike:.0f} in chain for {chain.symbol}."
    )


def _find_call(chain: OptionChain, strike: float) -> OptionContract:
    for o in chain.options:
        if o.option_type == "CALL" and abs(o.strike - strike) < 0.01:
            return o
    raise ValueError(
        f"No CALL contract found at strike {strike:.0f} in chain for {chain.symbol}."
    )
