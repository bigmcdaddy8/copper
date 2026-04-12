from dataclasses import dataclass


@dataclass
class SnifferConfig:
    api_key: str
    account_id: str
    poll_interval: int = 10  # seconds between poll cycles
    db_path: str = "tradier_sniffer.db"
