from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_DOWNLOADS_DIR = Path(
    "/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/downloads"
)

_DEFAULT_WORKSHEETS_DIR = Path(
    "/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading/worksheets"
)


@dataclass
class RunConfig:
    output_dir: Path
    tradier_api_key: str
    downloads_dir: Path = field(default_factory=lambda: _DEFAULT_DOWNLOADS_DIR)
    worksheets_dir: Path = field(default_factory=lambda: _DEFAULT_WORKSHEETS_DIR)
    tastytrade_file: Path | None = None
    bull_file: Path | None = None
    bear_file: Path | None = None
    journal_file: Path | None = None
    min_open_interest: int = 8
    min_bid: float = 0.55
    max_spread_pct: float = 0.13
    min_dte: int = 30
    max_dte: int = 60
    sandbox: bool = False
