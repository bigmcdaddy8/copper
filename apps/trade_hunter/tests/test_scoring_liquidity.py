"""Unit tests for liquidity_quality()."""

from trade_hunter.pipeline.scoring import liquidity_quality

# Raw star strings using Unicode characters
_ZERO_STARS = "\u2606\u2606\u2606\u2606"  # ☆☆☆☆
_ONE_STAR = "\u2605\u2606\u2606\u2606"  # ★☆☆☆
_TWO_STARS = "\u2605\u2605\u2606\u2606"  # ★★☆☆
_THREE_STARS = "\u2605\u2605\u2605\u2606"  # ★★★☆
_FOUR_STARS = "\u2605\u2605\u2605\u2605"  # ★★★★


def test_liquidity_0_stars():
    assert liquidity_quality(_ZERO_STARS) == 0.0


def test_liquidity_1_star():
    assert liquidity_quality(_ONE_STAR) == 0.5


def test_liquidity_2_stars():
    assert liquidity_quality(_TWO_STARS) == 2.0


def test_liquidity_3_stars():
    assert liquidity_quality(_THREE_STARS) == 4.5


def test_liquidity_4_stars():
    assert liquidity_quality(_FOUR_STARS) == 5.0


def test_liquidity_unknown_returns_zero():
    """Unrecognized string (no star characters) returns 0.0 without raising."""
    assert liquidity_quality("") == 0.0
