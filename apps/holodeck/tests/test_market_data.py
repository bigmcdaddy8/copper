import csv
import pytest
from datetime import date, datetime
from pathlib import Path
from holodeck.market_data import generate_spx_minutes, MarketDataStore


@pytest.fixture
def csv_path(tmp_path):
    p = str(tmp_path / "spx_test.csv")
    generate_spx_minutes(42, p)
    return p


def test_generate_creates_file(tmp_path):
    p = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, p)
    assert Path(p).exists()


def test_csv_has_correct_columns(csv_path):
    with open(csv_path, newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
    assert header == ["timestamp", "last", "bid", "ask"]


def test_csv_row_count(csv_path):
    # 20 trading days * 331 bars = 6620 data rows + 1 header = 6621 lines
    with open(csv_path) as f:
        lines = f.readlines()
    assert len(lines) == 6621


def test_prices_are_positive(csv_path):
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert float(row["last"]) > 0


def test_bid_ask_spread(csv_path):
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            spread = round(float(row["ask"]) - float(row["bid"]), 4)
            assert abs(spread - 0.10) < 0.001


def test_bid_less_than_last_less_than_ask(csv_path):
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            assert float(row["bid"]) < float(row["last"]) < float(row["ask"])


def test_deterministic_same_seed(tmp_path):
    p1 = str(tmp_path / "a.csv")
    p2 = str(tmp_path / "b.csv")
    generate_spx_minutes(42, p1)
    generate_spx_minutes(42, p2)
    assert open(p1).read() == open(p2).read()


def test_different_seeds_differ(tmp_path):
    p1 = str(tmp_path / "a.csv")
    p2 = str(tmp_path / "b.csv")
    generate_spx_minutes(42, p1)
    generate_spx_minutes(99, p2)
    assert open(p1).read() != open(p2).read()


def test_store_load(csv_path):
    store = MarketDataStore(csv_path)
    store.load()
    assert store.is_loaded()


def test_store_get_quote(csv_path):
    store = MarketDataStore(csv_path)
    store.load()
    quote = store.get_quote(datetime(2026, 1, 2, 9, 30))
    assert quote.symbol == "SPX"
    assert quote.last > 0
    assert quote.bid < quote.last < quote.ask


def test_store_missing_file_raises(tmp_path):
    store = MarketDataStore(str(tmp_path / "nonexistent.csv"))
    with pytest.raises(FileNotFoundError):
        store.load()


def test_daily_close(csv_path):
    store = MarketDataStore(csv_path)
    store.load()
    close_price = store.get_daily_close(date(2026, 1, 2))
    assert close_price == 5842.50  # matches DAILY_PRICES["2026-01-02"][1]
