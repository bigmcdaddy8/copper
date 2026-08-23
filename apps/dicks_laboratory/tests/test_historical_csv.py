from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from dicks_laboratory.historical_csv import (
    HistoricalCsvImportPolicy,
    HistoricalTradeSourceRecord,
    load_historical_trade_csv,
    normalize_historical_trades,
)
from dicks_laboratory.models import DatasetIdentity, DatasetKind
from dicks_laboratory.vwap import calculate_vwap

_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "historical_es_sep_2026.csv"
_DATASET = DatasetIdentity(
    dataset_id=UUID("65d7d1e4-3c38-4c16-9e04-e6f7c8a7c001"),
    kind=DatasetKind.HISTORICAL_IMPORT,
    label="phase-0d-historical-es-import",
    source_locator="tests/fixtures/historical_es_sep_2026.csv",
    source_timezone="America/Chicago",
    normalizer_version="phase-0d-csv-v1",
)
_POLICY = HistoricalCsvImportPolicy(
    source_timezone="America/Chicago",
    source_locator="tests/fixtures/historical_es_sep_2026.csv",
    dataset=_DATASET,
)


def test_source_fixture_loads_in_physical_row_order_with_raw_values_preserved():
    records = load_historical_trade_csv(_FIXTURE_PATH)

    assert [record.source_record_ref for record in records] == [
        "row:2", "row:3", "row:4", "row:5", "row:6", "row:7",
    ]
    assert records[1].raw_timestamp == "08/21/2026 09:47:32"
    assert records[1].raw_contract == "ESU26"
    assert records[1].raw_price == "6432.25"
    assert records[1].raw_quantity == "3"


def test_declared_chicago_source_records_normalize_to_canonical_utc_observations():
    result = normalize_historical_trades(load_historical_trade_csv(_FIXTURE_PATH), _POLICY)

    assert result.rejected == ()
    assert [item.source_record_ref for item in result.accepted] == [
        "row:2", "row:3", "row:4", "row:5", "row:6", "row:7",
    ]
    assert [trade.dataset_sequence for trade in result.observations] == [1, 2, 3, 4, 5, 6]
    assert result.observations[0].instrument.canonical_id == "FUTURE:CME:ES:2026-09"
    assert result.observations[0].event_timestamp == datetime(
        2026, 8, 21, 14, 47, 32, tzinfo=timezone.utc
    )
    assert result.observations[0].price == Decimal("6432.00")
    assert result.observations[0].size == Decimal("2")
    assert result.observations[0].event_timestamp == result.observations[1].event_timestamp
    assert result.observations[0].dataset_sequence < result.observations[1].dataset_sequence


def test_accepted_observation_traces_to_its_source_record():
    records = load_historical_trade_csv(_FIXTURE_PATH)
    result = normalize_historical_trades(records, _POLICY)

    first_accepted = result.accepted[0]
    source_record = next(
        record for record in records if record.source_record_ref == first_accepted.source_record_ref
    )

    assert first_accepted.observation.dataset_id == _DATASET.dataset_id
    assert source_record.raw_price == "6432.00"


def test_missing_declared_source_timezone_rejects_record_without_guessing():
    record = HistoricalTradeSourceRecord(
        source_record_ref="row:2",
        raw_timestamp="08/21/2026 09:47:32",
        raw_contract="ESU26",
        raw_price="6432.00",
        raw_quantity="2",
    )
    policy = HistoricalCsvImportPolicy(
        source_timezone=None,
        source_locator="inline",
        dataset=_DATASET,
    )

    result = normalize_historical_trades((record,), policy)

    assert result.accepted == ()
    assert result.rejected[0].source_record_ref == "row:2"
    assert result.rejected[0].reason == "SOURCE_TIMEZONE_NOT_DECLARED"


def test_normalized_historical_fixture_preserves_phase_0c_golden_vwap():
    result = normalize_historical_trades(load_historical_trade_csv(_FIXTURE_PATH), _POLICY)

    assert calculate_vwap(result.observations) == Decimal("6432.166666666666666666666667")