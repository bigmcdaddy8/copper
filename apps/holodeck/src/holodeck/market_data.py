from __future__ import annotations
import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

from bic.models import Quote


TRADING_DAYS = [
    "2026-01-02", "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
    "2026-01-09", "2026-01-12", "2026-01-13", "2026-01-14", "2026-01-15",
    "2026-01-16", "2026-01-20", "2026-01-21", "2026-01-22", "2026-01-23",
    "2026-01-26", "2026-01-27", "2026-01-28", "2026-01-29", "2026-01-30",
]  # 20 trading days

DAILY_PRICES: dict[str, tuple[float, float]] = {
    "2026-01-02": (5825.00, 5842.50),
    "2026-01-05": (5843.00, 5860.25),
    "2026-01-06": (5861.00, 5838.75),
    "2026-01-07": (5839.00, 5855.00),
    "2026-01-08": (5856.00, 5871.50),
    "2026-01-09": (5872.00, 5868.00),
    "2026-01-12": (5869.00, 5890.25),
    "2026-01-13": (5891.00, 5878.50),
    "2026-01-14": (5879.00, 5895.75),
    "2026-01-15": (5896.00, 5912.00),
    "2026-01-16": (5913.00, 5905.25),
    "2026-01-20": (5906.00, 5925.50),
    "2026-01-21": (5926.00, 5918.75),
    "2026-01-22": (5919.00, 5934.00),
    "2026-01-23": (5935.00, 5948.25),
    "2026-01-26": (5949.00, 5961.50),
    "2026-01-27": (5962.00, 5955.75),
    "2026-01-28": (5956.00, 5970.00),
    "2026-01-29": (5971.00, 5983.25),
    "2026-01-30": (5984.00, 5975.50),
}


def generate_spx_minutes(seed: int, output_path: str) -> None:
    """Generate synthetic SPX 1-minute bars for January 2026 and write to CSV."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    for day_index, trade_date in enumerate(TRADING_DAYS):
        daily_open, daily_close = DAILY_PRICES[trade_date]
        rng = random.Random(seed + day_index)

        # Generate 331 bars: 09:30 through 15:00 inclusive
        session_start = datetime.fromisoformat(f"{trade_date}T09:30:00")
        prices = [0.0] * 331
        prices[0] = daily_open
        prices[330] = daily_close

        for i in range(1, 330):
            remaining = 330 - i
            drift = (prices[330] - prices[i - 1]) / remaining * 0.1
            step = rng.gauss(0, 2.0) + drift
            step = max(-15.0, min(15.0, step))  # clamp
            prices[i] = round(prices[i - 1] + step, 2)

        for i, price in enumerate(prices):
            ts = session_start + timedelta(minutes=i)
            bid = round(price - 0.05, 2)
            ask = round(price + 0.05, 2)
            rows.append((ts.strftime("%Y-%m-%dT%H:%M:%S"), price, bid, ask))

    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "last", "bid", "ask"])
        writer.writerows(rows)


class MarketDataStore:
    """Loads synthetic SPX minute-bar data from CSV and provides quote lookups."""

    def __init__(self, csv_path: str) -> None:
        self._csv_path = csv_path
        self._data: dict[str, tuple[float, float, float]] = {}

    def load(self) -> None:
        """Read CSV into memory. Raises FileNotFoundError if CSV does not exist."""
        path = Path(self._csv_path)
        if not path.exists():
            raise FileNotFoundError(
                f"Market data file not found: {self._csv_path}\n"
                "Run 'holodeck generate-data' to create it."
            )
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                key = row["timestamp"]  # "YYYY-MM-DDTHH:MM:SS"
                self._data[key] = (
                    float(row["last"]),
                    float(row["bid"]),
                    float(row["ask"]),
                )

    def is_loaded(self) -> bool:
        return len(self._data) > 0

    def get_quote(self, dt: datetime) -> Quote:
        """Return Quote for the given virtual datetime. Raises KeyError if not found."""
        key = dt.strftime("%Y-%m-%dT%H:%M:00")  # strip seconds
        last, bid, ask = self._data[key]
        return Quote(symbol="SPX", last=last, bid=bid, ask=ask)

    def get_daily_close(self, trade_date: date) -> float:
        """Return the 'last' price for the 15:00 bar on the given date."""
        key = f"{trade_date.strftime('%Y-%m-%d')}T15:00:00"
        last, _, _ = self._data[key]
        return last

    def get_bars_range(
        self, start: datetime, end: datetime
    ) -> list[tuple[datetime, float]]:
        """Return (timestamp, last) pairs for all 1-minute bars in [start, end].

        start/end may be tz-aware; comparisons use naive local market time to match
        the CSV keys (which have no timezone suffix).
        Returns list sorted by timestamp ascending.
        """
        naive_start = start.replace(tzinfo=None) if start.tzinfo else start
        naive_end = end.replace(tzinfo=None) if end.tzinfo else end

        result: list[tuple[datetime, float]] = []
        for key, (last, _bid, _ask) in self._data.items():
            dt = datetime.fromisoformat(key)
            if naive_start <= dt <= naive_end:
                result.append((dt, last))
        result.sort(key=lambda x: x[0])
        return result
