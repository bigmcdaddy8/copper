"""0W-2D finalization-memory regression: `_write_closing_summary` must obtain
the accepted-trade tally via the O(1) `count_trade_observations` path and must
NOT call `load_trade_observations` (which materializes every observation --
~1.5 GB / ~22 s on the 0W-2 Attempt-3 full-day dataset, per 0W-2C). Structural
proof, no RSS thresholds.
"""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from dicks_laboratory.fixture import ES_SEP_2026
from dicks_laboratory.long_running_capture import _write_closing_summary
from dicks_laboratory.models import DatasetIdentity, DatasetKind, DatasetOrigin, TradeObservation
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.store import LaboratoryStore

_DATASET = DatasetIdentity(
    dataset_id=UUID("7c0d2d0d-0000-4000-8000-00000000d2d0"),
    kind=DatasetKind.HISTORICAL_IMPORT,
    label="0w2d-closing-summary-regression",
    origin=DatasetOrigin.AUTHENTIC_SOURCE,
    capture_started_at=datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc),
    capture_ended_at=datetime(2026, 9, 2, 21, 0, tzinfo=timezone.utc),
)


class _NoLoadStore:
    """Delegates to a real store but fails the test if the closing-summary path
    ever reaches for the full observation list, and records that the count path
    was used instead."""

    def __init__(self, inner: LaboratoryStore) -> None:
        self._inner = inner
        self.count_calls = 0

    def count_trade_observations(self, dataset_id):
        self.count_calls += 1
        return self._inner.count_trade_observations(dataset_id)

    def load_trade_observations(self, dataset_id):  # pragma: no cover - must not run
        raise AssertionError(
            "closing-summary path called load_trade_observations() -- it must use "
            "count_trade_observations() for the tally (0W-2D)"
        )

    def __getattr__(self, name):
        return getattr(self._inner, name)


def _trades(n: int) -> tuple[TradeObservation, ...]:
    base = datetime(2026, 9, 1, 22, 0, tzinfo=timezone.utc)
    return tuple(
        TradeObservation(
            observation_id=UUID(f"7c0d2d0d-0000-4000-8000-0000000{seq:05d}"),
            dataset_id=_DATASET.dataset_id,
            dataset_sequence=seq,
            instrument=ES_SEP_2026,
            event_timestamp=base,
            price=Decimal("6432.00"),
            size=Decimal("2"),
        )
        for seq in range(1, n + 1)
    )


def _rejections() -> tuple[NormalizationRejection, ...]:
    return tuple(
        NormalizationRejection(
            rejection_id=UUID(f"7c0d2d0d-0000-4000-8000-0000000a{i:04d}"),
            dataset_id=_DATASET.dataset_id,
            source_kind=RejectionSourceKind.DXLINK_TIME_AND_SALE,
            source_record_ref=f"event:{i}",
            source_order=i,
            reason="INVALID_DXLINK_TICK",
        )
        for i in (11, 12, 13)
    )


def test_closing_summary_uses_count_not_full_load(tmp_path):
    real = LaboratoryStore(tmp_path / "es.sqlite3")
    real.save_dataset(_DATASET)
    real.save_trade_observations(_trades(9))
    real.save_rejections(_rejections())

    spy = _NoLoadStore(real)
    closed_at = datetime(2026, 9, 2, 21, 0, tzinfo=timezone.utc)

    _write_closing_summary(spy, _DATASET.dataset_id, closed_at, "test-collector", "deadbeef")

    assert spy.count_calls >= 1

    summary = real.load_dataset_closing_summary(_DATASET.dataset_id)
    assert summary is not None
    assert summary.accepted_trade_count == 9
    assert summary.rejected_record_count == 3
    assert summary.deferred_event_count == 0
    assert summary.known_gap_count == 0
    assert summary.suspected_gap_count == 0


def test_closing_summary_accepted_count_matches_prior_len_semantics(tmp_path):
    real = LaboratoryStore(tmp_path / "es.sqlite3")
    real.save_dataset(_DATASET)
    real.save_trade_observations(_trades(9))

    _write_closing_summary(
        real, _DATASET.dataset_id, _DATASET.capture_ended_at, "test-collector", "deadbeef"
    )

    summary = real.load_dataset_closing_summary(_DATASET.dataset_id)
    assert summary.accepted_trade_count == len(
        real.load_trade_observations(_DATASET.dataset_id)
    )


def test_closing_summary_is_frozen_once_written(tmp_path):
    real = LaboratoryStore(tmp_path / "es.sqlite3")
    real.save_dataset(_DATASET)
    real.save_trade_observations(_trades(9))
    _write_closing_summary(real, _DATASET.dataset_id, _DATASET.capture_ended_at, "v1", "aaa")

    # a second call with a spy that would explode on full load must be a no-op
    spy = _NoLoadStore(real)
    _write_closing_summary(spy, _DATASET.dataset_id, _DATASET.capture_ended_at, "v2", "bbb")
    assert real.load_dataset_closing_summary(_DATASET.dataset_id).collector_version == "v1"
