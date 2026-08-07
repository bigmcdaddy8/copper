from __future__ import annotations

from datetime import date

import pytest
from rich.console import Console
from typer.testing import CliRunner

from K9.cli import app
from K9.tastytrade.dxlink import DxLinkSnapshot
from K9.tastytrade.terminal_chain import (
    ChainContract,
    render_chain_table,
    resolve_expiration,
    select_strike_window,
    validate_chain_parameters,
)

runner = CliRunner()


def _chain() -> list[dict]:
    strikes = []
    for strike in range(95, 106):
        strikes.append(
            {
                "strike-price": str(strike),
                "call-streamer-symbol": f".ABC260807C{strike}",
                "put-streamer-symbol": f".ABC260807P{strike}",
            }
        )
    return [{"expirations": [{"expiration-date": "2026-08-07", "strikes": strikes}]}]


def test_validate_chain_parameters_normalizes_ticker_and_rejects_invalid_values():
    assert validate_chain_parameters(" spy ", 13, 0, 30) == "SPY"
    with pytest.raises(ValueError, match="ticker"):
        validate_chain_parameters("SP Y", 13, 0, 30)
    with pytest.raises(ValueError, match="strikes"):
        validate_chain_parameters("SPY", -1, 0, 30)
    with pytest.raises(ValueError, match="dte"):
        validate_chain_parameters("SPY", 13, -1, 30)
    with pytest.raises(ValueError, match="refresh-seconds"):
        validate_chain_parameters("SPY", 13, 0, 14)


def test_chain_command_rejects_invalid_ticker_before_loading_credentials():
    result = runner.invoke(app, ["tastytrade-chain", "SP Y"])

    assert result.exit_code == 1
    assert "Invalid parameter" in result.output


def test_chain_command_rejects_refresh_under_15_seconds():
    result = runner.invoke(app, ["tastytrade-chain", "SPY", "--refresh-seconds", "14"])

    assert result.exit_code == 2
    assert "Invalid value for '--refresh-seconds'" in result.output


def test_resolve_expiration_uses_calendar_days():
    assert resolve_expiration(date(2026, 8, 7), 3) == date(2026, 8, 10)


def test_select_strike_window_returns_atm_and_otm_rows_on_both_sides():
    contracts = select_strike_window(_chain(), date(2026, 8, 7), 100.2, 2)

    assert [contract.strike for contract in contracts] == [98.0, 99.0, 100.0, 101.0, 102.0]


def test_select_strike_window_rejects_missing_expiration():
    with pytest.raises(ValueError, match="No option chain"):
        select_strike_window(_chain(), date(2026, 8, 8), 100.0, 2)


def test_render_chain_table_uses_requested_column_order_and_ascending_strikes():
    contracts = [
        ChainContract(100.0, ".ABC260807C100", ".ABC260807P100"),
        ChainContract(101.0, ".ABC260807C101", ".ABC260807P101"),
    ]
    snapshots = {}
    for contract in contracts:
        snapshots[contract.call_streamer_symbol] = DxLinkSnapshot(
            symbol=contract.call_streamer_symbol,
            bid=1.0,
            ask=1.1,
            last_price=1.05,
            open_interest=100,
            delta=0.2,
            volatility=0.15,
        )
        snapshots[contract.put_streamer_symbol] = DxLinkSnapshot(
            symbol=contract.put_streamer_symbol,
            bid=0.9,
            ask=1.0,
            last_price=0.95,
            open_interest=200,
            delta=-0.2,
            volatility=0.16,
        )
    console = Console(record=True, width=180)

    render_chain_table(console, "ABC", 100.2, date(2026, 8, 7), contracts, snapshots)

    output = console.export_text()
    assert output.index("CALL IV") < output.index("Strike") < output.index("PUT Bid")
    assert output.index("100.00") < output.index("101.00")
    assert "15.00%" in output
    assert "16.00%" in output
    assert "ATM divider follows the 100.20" in output


def test_render_chain_table_colors_price_changes_and_divides_below_exact_atm():
    contract = ChainContract(100.0, ".ABC260807C100", ".ABC260807P100")
    snapshots = {
        contract.call_streamer_symbol: DxLinkSnapshot(
            symbol=contract.call_streamer_symbol,
            bid=1.1,
            ask=1.0,
            last_price=1.2,
            open_interest=100,
            delta=0.2,
            volatility=0.15,
        ),
        contract.put_streamer_symbol: DxLinkSnapshot(
            symbol=contract.put_streamer_symbol,
            bid=0.8,
            ask=0.7,
            last_price=0.6,
            open_interest=200,
            delta=-0.2,
            volatility=0.16,
        ),
    }
    previous = {
        contract.call_streamer_symbol: {"last": 1.1, "bid": 1.0, "ask": 1.1},
        contract.put_streamer_symbol: {"last": 0.7, "bid": 0.9, "ask": 0.6},
    }
    console = Console(record=True, width=180)

    render_chain_table(
        console,
        "ABC",
        100.0,
        date(2026, 8, 7),
        [contract],
        snapshots,
        previous,
        15,
    )

    ansi_output = console.export_text(styles=True, clear=False)
    assert "\x1b[32m1.20" in ansi_output
    assert "\x1b[31m1.00" in ansi_output
    assert "Refreshes every 15s" in console.export_text(clear=False)