from dicks_laboratory.fixture import synthetic_es_trades


def test_fixture_has_stable_total_dataset_order_despite_timestamp_tie():
    trades = synthetic_es_trades()

    assert [trade.dataset_sequence for trade in trades] == [1, 2, 3, 4, 5, 6]
    assert trades[0].event_timestamp == trades[1].event_timestamp
    assert trades[0].dataset_sequence < trades[1].dataset_sequence