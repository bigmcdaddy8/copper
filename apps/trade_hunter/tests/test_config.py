from pathlib import Path

from trade_hunter.config import RunConfig, _DEFAULT_DOWNLOADS_DIR, _DEFAULT_WORKSHEETS_DIR


def test_runconfig_defaults():
    config = RunConfig(
        output_dir=Path("/tmp/out"),
        tradier_api_key="key",
    )
    assert config.tastytrade_file is None
    assert config.bull_file is None
    assert config.bear_file is None
    assert config.journal_file is None
    assert config.downloads_dir == _DEFAULT_DOWNLOADS_DIR
    assert config.worksheets_dir == _DEFAULT_WORKSHEETS_DIR
    assert config.min_open_interest == 8
    assert config.min_bid == 0.55
    assert config.max_spread_pct == 0.13
    assert config.min_dte == 30
    assert config.max_dte == 60
