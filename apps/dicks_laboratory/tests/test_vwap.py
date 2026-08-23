from decimal import Decimal

import pytest

from dicks_laboratory.fixture import synthetic_es_trades
from dicks_laboratory.vwap import calculate_vwap


def test_synthetic_es_fixture_has_exact_independently_calculated_vwap():
    # (6432.00 * 2 + 6432.25 * 3 + 6432.50 * 1 + 6431.75 * 4
    #  + 6432.75 * 2 + 6432.25 * 3) / (2 + 3 + 1 + 4 + 2 + 3)
    expected = Decimal("96482.50") / Decimal("15")

    assert calculate_vwap(synthetic_es_trades()) == expected


def test_vwap_uses_decimal_not_binary_float():
    result = calculate_vwap(synthetic_es_trades())

    assert isinstance(result, Decimal)
    assert result == Decimal("6432.166666666666666666666667")


def test_empty_trade_sequence_has_explicit_domain_error():
    with pytest.raises(ValueError, match="at least one trade"):
        calculate_vwap(())