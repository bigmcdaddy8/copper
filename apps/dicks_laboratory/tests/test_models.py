from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from dicks_laboratory.fixture import ES_SEP_2026, SYNTHETIC_ES_DATASET
from dicks_laboratory.models import TradeObservation


def _trade(**overrides: object) -> TradeObservation:
    values: dict[str, object] = {
        "observation_id": UUID("51c7d1e4-3c38-4c16-9e04-e6f7c8a7c101"),
        "dataset_id": SYNTHETIC_ES_DATASET.dataset_id,
        "dataset_sequence": 1,
        "instrument": ES_SEP_2026,
        "event_timestamp": datetime(2026, 8, 21, 14, 47, 32, tzinfo=timezone.utc),
        "price": Decimal("6432.25"),
        "size": Decimal("2"),
    }
    values.update(overrides)
    return TradeObservation(**values)  # type: ignore[arg-type]


def test_future_identity_has_provider_neutral_canonical_id():
    assert ES_SEP_2026.canonical_id == "FUTURE:CME:ES:2026-09"


def test_dataset_and_trade_observations_are_immutable():
    trade = _trade()

    with pytest.raises(FrozenInstanceError):
        trade.price = Decimal("1")  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        SYNTHETIC_ES_DATASET.label = "changed"  # type: ignore[misc]


def test_utc_timestamp_is_accepted():
    assert _trade().event_timestamp.tzinfo is timezone.utc


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2026, 8, 21, 14, 47, 32),
        datetime(2026, 8, 21, 9, 47, 32, tzinfo=timezone(timedelta(hours=-5))),
    ],
)
def test_non_utc_or_naive_timestamp_is_rejected(timestamp):
    with pytest.raises(ValueError, match="timestamp"):
        _trade(event_timestamp=timestamp)


@pytest.mark.parametrize("price", [Decimal("0"), Decimal("-0.01")])
def test_new_trade_requires_positive_price(price):
    with pytest.raises(ValueError, match="price"):
        _trade(price=price)


@pytest.mark.parametrize("size", [Decimal("0"), Decimal("-1")])
def test_new_trade_requires_positive_size(size):
    with pytest.raises(ValueError, match="size"):
        _trade(size=size)


def test_dataset_sequence_must_be_positive():
    with pytest.raises(ValueError, match="sequence"):
        _trade(dataset_sequence=0)