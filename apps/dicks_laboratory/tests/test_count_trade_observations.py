"""0W-2D: `LaboratoryStore.count_trade_observations` -- the O(1) counting path
that replaces `len(load_trade_observations(...))` in the closing-summary /
resume code (0W-2C measured that materialization at ~1.5 GB / ~22 s on the
Attempt-3 full-day dataset)."""
from dataclasses import replace
from uuid import UUID

from dicks_laboratory.fixture import SYNTHETIC_ES_DATASET, synthetic_es_trades
from dicks_laboratory.store import LaboratoryStore


def _store(tmp_path) -> LaboratoryStore:
    return LaboratoryStore(tmp_path / "es.sqlite3")


def test_zero_observations_counts_zero(tmp_path):
    store = _store(tmp_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)

    assert store.count_trade_observations(SYNTHETIC_ES_DATASET.dataset_id) == 0


def test_n_observations_counts_n(tmp_path):
    store = _store(tmp_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)
    trades = synthetic_es_trades()
    store.save_trade_observations(trades)

    assert store.count_trade_observations(SYNTHETIC_ES_DATASET.dataset_id) == len(trades)


def test_count_isolated_per_dataset(tmp_path):
    store = _store(tmp_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)
    trades = synthetic_es_trades()
    store.save_trade_observations(trades)

    other_id = UUID("51c7d1e4-3c38-4c16-9e04-e6f7c8a7c999")
    other_dataset = replace(SYNTHETIC_ES_DATASET, dataset_id=other_id, label="other")
    store.save_dataset(other_dataset)
    store.save_trade_observations(
        tuple(
            replace(
                trade,
                dataset_id=other_id,
                observation_id=UUID(f"51c7d1e4-3c38-4c16-9e04-e6f7c8a7d{trade.dataset_sequence:03d}"),
            )
            for trade in trades[:2]
        )
    )

    assert store.count_trade_observations(SYNTHETIC_ES_DATASET.dataset_id) == len(trades)
    assert store.count_trade_observations(other_id) == 2


def test_count_matches_len_of_full_load(tmp_path):
    store = _store(tmp_path)
    store.save_dataset(SYNTHETIC_ES_DATASET)
    store.save_trade_observations(synthetic_es_trades())

    dataset_id = SYNTHETIC_ES_DATASET.dataset_id
    assert store.count_trade_observations(dataset_id) == len(
        store.load_trade_observations(dataset_id)
    )
