"""Quality metric functions and Trade Score calculator.

Quality functions map a numeric input to a quality float in the range 0.0–5.0.
All quality functions are pure — no I/O or side effects.
"""

from datetime import date, timedelta

import pandas as pd


def ivr_quality(iv_rank: float) -> float:
    """Map TastyTrade IV Rank to a quality score."""
    if iv_rank <= 10.0:
        return 0.0
    if iv_rank <= 20.0:
        return 1.0
    if iv_rank <= 30.0:
        return 2.0
    if iv_rank <= 50.0:
        return 4.0
    return 5.0


def ivp_quality(iv_percentile: float) -> float:
    """Map TastyTrade IV %tile to a quality score."""
    if iv_percentile <= 10.0:
        return 0.0
    if iv_percentile <= 20.0:
        return 1.0
    if iv_percentile <= 30.0:
        return 2.0
    if iv_percentile <= 50.0:
        return 4.0
    return 5.0


def open_interest_quality(open_interest: int | float) -> float:
    """Map selected option open interest to a quality score."""
    if open_interest <= 10:
        return 0.0
    if open_interest <= 100:
        return 2.0
    if open_interest <= 1000:
        return 4.5
    return 5.0


def spread_pct_quality(bid: float, ask: float) -> float:
    """Compute Spread% and map to a quality score.

    Spread% = (ask - bid) / ((ask + bid) / 2)
    """
    mid = (ask + bid) / 2.0
    spread = (ask - bid) / mid  # as a fraction (e.g. 0.08 = 8%)

    if spread <= 0.02:
        return 5.0
    if spread <= 0.04:
        return 4.5
    if spread <= 0.06:
        return 4.0
    if spread <= 0.08:
        return 3.0
    if spread <= 0.12:
        return 2.0
    if spread <= 0.20:
        return 1.0
    return 0.0


def _bpr_value(
    underlying_price: float,
    strike: float,
    bid: float,
    option_type: str,
) -> float:
    """Compute the raw BPR dollar value (before quality mapping).

    premium = bid (conservative, consistent with trade entry)

    For puts:  OTM_amount = underlying_price - put_strike
    For calls: OTM_amount = call_strike - underlying_price

    BPR = max(
        0.20 * underlying_price - OTM_amount + premium,
        0.10 * underlying_price + premium,
        2.50 + premium,
    ) * 100
    """
    premium = bid
    otm_amount = underlying_price - strike if option_type == "put" else strike - underlying_price
    return (
        max(
            0.20 * underlying_price - otm_amount + premium,
            0.10 * underlying_price + premium,
            2.50 + premium,
        )
        * 100
    )


def bpr_quality(
    underlying_price: float,
    strike: float,
    bid: float,
    option_type: str,
) -> float:
    """Compute Buying Power Reduction and map to a quality score."""
    bpr = _bpr_value(underlying_price, strike, bid, option_type)

    if bpr <= 500:
        return 3.0
    if bpr <= 1500:
        return 5.0
    if bpr <= 3000:
        return 3.5
    if bpr <= 4500:
        return 1.5
    return 0.0


# ---------------------------------------------------------------------------
# Diversity metrics
# ---------------------------------------------------------------------------


def cyclical_diversity_quality(
    candidate_bucket: str,
    active_buckets: list[str],
) -> float:
    """Quality based on how concentrated active trades are in the candidate's sector bucket.

    active_buckets: one entry per deduplicated active ticker (their sector bucket).
    Returns 5.0 if active_buckets is empty (no concentration).
    """
    if not active_buckets:
        return 5.0
    pct = active_buckets.count(candidate_bucket) / len(active_buckets)
    if pct <= 0.21:
        return 5.0
    if pct <= 0.55:
        return 2.0
    return 0.0


def sector_diversity_quality(
    candidate_sector: str,
    active_sectors: list[str],
) -> float:
    """Quality based on how concentrated active trades are in the candidate's exact sector.

    active_sectors: one entry per deduplicated active ticker (their standardized sector).
    Returns 5.0 if active_sectors is empty (no concentration).
    """
    if not active_sectors:
        return 5.0
    pct = active_sectors.count(candidate_sector) / len(active_sectors)
    if pct <= 0.03:
        return 5.0
    if pct <= 0.13:
        return 2.0
    return 0.0


# ---------------------------------------------------------------------------
# SeekingAlpha metrics
# ---------------------------------------------------------------------------


def quant_rating_quality(quant_rating: float, side: str) -> float:
    """Map SeekingAlpha Quant Rating (1.0–5.0) to quality.

    BULL: quality = quant_rating (use directly).
    BEAR: quality = 6.0 - quant_rating (inverted).
    """
    if side == "BEAR":
        return 6.0 - quant_rating
    return quant_rating


_GRADE_MAP: dict[str, float] = {
    "A+": 5.0,
    "A": 4.5,
    "A-": 4.0,
    "B+": 3.0,
    "B": 2.5,
    "B-": 2.0,
    "C+": 1.25,
    "C": 1.0,
    "C-": 0.75,
    "D+": 0.5,
    "D": 0.25,
    "D-": 0.1,
    "F": 0.0,
}


def grade_quality(grade: str) -> float:
    """Map a letter grade (A+…F) to a bullish quality score (0.0–5.0)."""
    return _GRADE_MAP[grade]


def growth_quality(grade: str, side: str) -> float:
    """Map SeekingAlpha Growth grade to quality.

    Only called when the candidate is in the Growth sector bucket.
    BULL: bullish mapping. BEAR: 5.0 - bullish_quality.
    """
    bullish = grade_quality(grade)
    return 5.0 - bullish if side == "BEAR" else bullish


def momentum_quality(grade: str, side: str) -> float:
    """Map SeekingAlpha Momentum grade to quality.

    BULL: bullish mapping. BEAR: 5.0 - bullish_quality.
    """
    bullish = grade_quality(grade)
    return 5.0 - bullish if side == "BEAR" else bullish


# ---------------------------------------------------------------------------
# Earnings date metric
# ---------------------------------------------------------------------------


def earnings_date_quality(
    earnings_date: date,
    expiration_date: date,
) -> float:
    """Map EaE = (earnings_date - expiration_date).days to quality.

    EaE <= -14: 3.0  (earnings well past expiration)
    -14 < EaE <= 1:  0.0  (earnings near or during trade)
    EaE > 1:         5.0  (earnings safely after expiration)
    """
    eae = (earnings_date - expiration_date).days
    if eae <= -14:
        return 3.0
    if eae <= 1:
        return 0.0
    return 5.0


# ---------------------------------------------------------------------------
# Bid metric
# ---------------------------------------------------------------------------


def bid_quality(bid: float) -> float:
    """Map option bid to quality."""
    if bid <= 0.55:
        return 0.0
    if bid <= 0.89:
        return 1.0
    if bid <= 1.44:
        return 2.5
    if bid <= 2.33:
        return 3.5
    if bid <= 3.77:
        return 4.5
    if bid <= 6.10:
        return 2.5
    return 0.0


# ---------------------------------------------------------------------------
# Liquidity metric
# ---------------------------------------------------------------------------

_FILLED_STAR = "\u2605"  # ★

_LIQUIDITY_QUALITY_MAP: dict[int, float] = {
    0: 0.0,
    1: 0.5,
    2: 2.0,
    3: 4.5,
    4: 5.0,
}


def liquidity_quality(liquidity_str: str) -> float:
    """Map TastyTrade Liquidity star string to a quality score.

    Counts filled stars (★, U+2605) in the raw string.
    Returns 0.0 for any unrecognized value.
    """
    stars = liquidity_str.count(_FILLED_STAR)
    return _LIQUIDITY_QUALITY_MAP.get(stars, 0.0)


# ---------------------------------------------------------------------------
# Diversity list builder
# ---------------------------------------------------------------------------


def build_active_diversity_lists(
    active_symbols: frozenset[str],
    universal_dataset: pd.DataFrame,
) -> tuple[list[str], list[str]]:
    """Return (active_buckets, active_sectors) for diversity quality calculations.

    Filters the Universal Data Set to active symbols and extracts their
    Sector Bucket and Sector. Active symbols not found in the Universal Data Set
    are silently skipped (they were already warned about in Story-0050).

    Returns:
        (active_buckets, active_sectors) — one entry per matched active ticker.
    """
    active_rows = universal_dataset[universal_dataset["Symbol"].isin(active_symbols)]
    return active_rows["Sector Bucket"].tolist(), active_rows["Sector"].tolist()


# ---------------------------------------------------------------------------
# Trade Score calculator
# ---------------------------------------------------------------------------

_WEIGHTS: dict[str, float] = {
    "IVR": 3.0,
    "IVP": 3.0,
    "Open Interest": 3.0,
    "Spread%": 3.0,
    "BPR": 3.0,
    "Cyclical Diversity": 3.0,
    "Quant Rating": 2.0,
    "Sector Diversity": 1.0,
    "Earnings Date": 1.0,
    "Growth": 1.0,
    "Momentum": 1.0,
    "Bid": 1.0,
    "Liquidity": 1.0,
}

# Output column names for individual metric scores (same order as _WEIGHTS keys).
# Growth Score is always emitted; it is 0.0 when Sector Bucket != "Growth".
SCORE_COLUMNS: list[str] = [
    "IVR Score",
    "IVP Score",
    "Open Interest Score",
    "Spread% Score",
    "BPR Score",
    "Cyclical Diversity Score",
    "Quant Rating Score",
    "Sector Diversity Score",
    "Earnings Date Score",
    "Growth Score",
    "Momentum Score",
    "Bid Score",
    "Liquidity Score",
]


def _resolve_earnings_date(row: pd.Series, run_date: date) -> date:
    """Resolve earnings date using three-source precedence.

    1. TastyTrade 'Earnings At'
    2. SeekingAlpha 'Upcoming Announce Date'
    3. Fallback: run_date + 70 days
    """
    for col in ("Earnings At", "Upcoming Announce Date"):
        if col not in row.index:
            continue
        val = row[col]
        if val is None or (hasattr(val, "__class__") and val.__class__.__name__ in ("float",)):
            continue
        try:
            import pandas as _pd

            if _pd.isna(val):
                continue
        except (TypeError, ValueError):
            pass
        if isinstance(val, _pd.Timestamp):
            return val.date()
        if isinstance(val, date):
            return val
        try:
            return date.fromisoformat(str(val)[:10])
        except (ValueError, TypeError):
            pass
    return run_date + timedelta(days=70)


def calculate_scores(
    enriched: pd.DataFrame,
    side: str,
    run_date: date,
    active_buckets: list[str],
    active_sectors: list[str],
) -> pd.DataFrame:
    """Compute Trade Score for each row and return DataFrame with 'Trade Score' column added.

    Trade Score = sum(weight * quality) / sum(active weights)

    Growth is excluded from the weighted average when Sector Bucket != "Growth".
    Score is clamped to [0.0, 5.0] and rounded to 2 decimal places.

    Args:
        enriched:        Filtered, enriched DataFrame from apply_hard_filters().
        side:            "BULL" or "BEAR" — passed to side-sensitive quality functions.
        run_date:        Used as fallback earnings date base (run_date + 70 days).
        active_buckets:  One sector bucket per deduplicated active ticker.
        active_sectors:  One sector per deduplicated active ticker.

    Returns:
        Copy of enriched with 'Trade Score' column added (float, 2 d.p., clamped 0–5).
    """
    if enriched.empty:
        return enriched.copy()

    result = enriched.copy()
    scores: list[float] = []
    earnings_date_strs: list[str] = []
    bpr_values: list[float] = []
    individual_score_rows: list[dict[str, float]] = []

    for _, row in result.iterrows():
        exp_date = date.fromisoformat(str(row["Expiration Date"])[:10])
        resolved_earnings = _resolve_earnings_date(row, run_date)
        sector_bucket = row["Sector Bucket"]

        bpr_val = _bpr_value(
            float(row["Last Price"]),
            float(row["Strike"]),
            float(row["Bid"]),
            str(row["Option Type"]),
        )

        qualities: dict[str, float] = {
            "IVR": ivr_quality(float(row["IV Rank"]) if pd.notna(row["IV Rank"]) else 0.0),
            "IVP": ivp_quality(float(row["IV %tile"]) if pd.notna(row["IV %tile"]) else 0.0),
            "Open Interest": open_interest_quality(float(row["Open Interest"])),
            "Spread%": spread_pct_quality(float(row["Bid"]), float(row["Ask"])),
            "BPR": bpr_quality(
                float(row["Last Price"]),
                float(row["Strike"]),
                float(row["Bid"]),
                str(row["Option Type"]),
            ),
            "Cyclical Diversity": cyclical_diversity_quality(sector_bucket, active_buckets),
            "Quant Rating": quant_rating_quality(float(row["Quant Rating"]), side),
            "Sector Diversity": sector_diversity_quality(str(row["Sector"]), active_sectors),
            "Earnings Date": earnings_date_quality(resolved_earnings, exp_date),
            "Momentum": momentum_quality(str(row["Momentum"]), side),
            "Bid": bid_quality(float(row["Bid"])),
            "Liquidity": liquidity_quality(str(row["Liquidity"])),
        }

        # Active weight rule: include Growth only for Growth sector bucket
        growth_score = 0.0
        if sector_bucket == "Growth":
            growth_score = growth_quality(str(row["Growth"]), side)
            qualities["Growth"] = growth_score

        numerator = sum(_WEIGHTS[k] * v for k, v in qualities.items())
        denominator = sum(_WEIGHTS[k] for k in qualities)
        raw_score = numerator / denominator
        final_score = round(max(0.0, min(5.0, raw_score)), 2)
        scores.append(final_score)
        earnings_date_strs.append(resolved_earnings.isoformat())
        bpr_values.append(bpr_val)

        individual_score_rows.append({
            "IVR Score": qualities["IVR"],
            "IVP Score": qualities["IVP"],
            "Open Interest Score": qualities["Open Interest"],
            "Spread% Score": qualities["Spread%"],
            "BPR Score": qualities["BPR"],
            "Cyclical Diversity Score": qualities["Cyclical Diversity"],
            "Quant Rating Score": qualities["Quant Rating"],
            "Sector Diversity Score": qualities["Sector Diversity"],
            "Earnings Date Score": qualities["Earnings Date"],
            "Growth Score": growth_score,
            "Momentum Score": qualities["Momentum"],
            "Bid Score": qualities["Bid"],
            "Liquidity Score": qualities["Liquidity"],
        })

    result["Trade Score"] = scores
    result["Earnings Date"] = earnings_date_strs
    result["BPR"] = bpr_values

    individual_df = pd.DataFrame(individual_score_rows, index=result.index)
    result = pd.concat([result, individual_df], axis=1)

    return result
