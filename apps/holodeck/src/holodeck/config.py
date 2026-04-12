from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime


@dataclass
class HolodeckConfig:
    starting_datetime: datetime
    ending_datetime: datetime
    timezone: str = "America/Chicago"
    random_seed: int = 42
    starting_account_value: float = 100_000.0
    starting_buying_power: float = 50_000.0
    underlying_symbol: str = "SPX"
    price_tick: float = 0.05
    strike_increment: float = 5.0
    session_open: str = "09:30"    # HH:MM, America/Chicago
    session_close: str = "15:00"   # HH:MM, America/Chicago
    data_path: str = "data/holodeck/spx_2026_01_minutes.csv"
