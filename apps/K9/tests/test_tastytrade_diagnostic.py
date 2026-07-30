from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from K9.output.tastytrade_diagnostic_log import TastytradeDiagnosticLog
from K9.tastytrade.diagnostic import run_diagnostic
from K9.tastytrade.dxlink import DxLinkSnapshot
from K9.tastytrade.settings import TastytradeSettings


class FakeClient:
    def __init__(self) -> None:
        self.market_calls = 0

    def list_accounts(self):
        return [{"account": {"account-number": "5WT00001"}, "authority-level": "owner"}]

    def get_balances(self):
        return {"net-liquidating-value": "1000"}

    def get_positions(self):
        return []

    def get_balance_snapshots(self):
        return []

    def search_orders(self, start_date, end_date):
        del start_date, end_date
        return []

    def get_trade_transactions(self, start_date, end_date):
        del start_date, end_date
        return []

    def get_quotes(self, instrument_type, symbols):
        self.market_calls += 1
        if instrument_type == "index":
            return [{"symbol": symbols[0], "bid": "600", "ask": "600.2", "last": "600.1"}]
        return [{"symbol": symbols[0], "bid": "1.0", "ask": "1.1", "last": "1.05"}]

    def get_nested_option_chain(self, underlying):
        strikes = []
        for strike in range(600, 583, -1):
            strikes.append(
                {
                    "strike-price": str(strike),
                    "call": f"{underlying}   260730C{strike * 1000:08d}",
                    "call-streamer-symbol": f".{underlying}260730C{strike}",
                    "put": f"{underlying}   260730P{strike * 1000:08d}",
                    "put-streamer-symbol": f".{underlying}260730P{strike}",
                }
            )
        return [
            {
                "underlying-symbol": underlying,
                "expirations": [
                    {
                        "expiration-date": "2026-07-30",
                        "strikes": strikes,
                    }
                ],
            }
        ]

    def get_api_quote_token(self):
        return {"token": "quote-token", "dxlink-url": "wss://dxlink.example"}


class FakeCollector:
    def __init__(self, url, token):
        assert url == "wss://dxlink.example"
        assert token == "quote-token"

    def collect(self, symbols):
        now = datetime.now(tz=timezone.utc)
        return {
            symbol: DxLinkSnapshot(
                symbol=symbol,
                updated_at=now,
                bid=1.0,
                ask=1.1,
                last_price=1.05,
                open_interest=1000,
                delta=0.2,
                gamma=0.01,
                theta=-0.02,
                rho=0.01,
                vega=0.03,
                volatility=0.18,
            )
            for symbol in symbols
        }


def _settings() -> TastytradeSettings:
    return TastytradeSettings(
        app_name="k9-diagnostic",
        client_id="client-id",
        client_secret="client-secret",
        refresh_token="refresh-token",
        account_number="5WT00001",
        environment="tastytrade_production",
        base_url="https://api.tastyworks.com",
    )


def test_market_hours_diagnostic_collects_xsp_and_spx_data(tmp_path):
    client = FakeClient()
    result = run_diagnostic(
        _settings(),
        ["XSP", "SPX"],
        client=client,
        dxlink_collector_factory=FakeCollector,
        now=datetime(2026, 7, 30, 9, 45, tzinfo=ZoneInfo("America/Chicago")),
    )

    assert result.outcome == "OK"
    assert not result.errors
    assert any(check.name == "dxlink_quote_and_greeks" for check in result.checks)
    scout = next(check for check in result.checks if check.name == "xsp_0dte_put_scout")
    assert scout.details["returned_strike_count"] == 16
    assert scout.details["rows"][0]["strike"] == 600.0
    assert scout.details["rows"][0]["open_interest"] == 1000
    catalog = next(check for check in result.checks if check.name == "dxlink_field_catalog")
    assert catalog.details["report_columns"]["volatility"] == "Greeks.volatility"

    path = TastytradeDiagnosticLog(tmp_path).write(result)
    payload = json.loads(path.read_text())
    assert payload["outcome"] == "OK"
    assert "refresh-token" not in path.read_text()
    assert "5WT00001" not in path.read_text()


def test_closed_market_skips_market_data_calls():
    client = FakeClient()
    result = run_diagnostic(
        _settings(),
        ["XSP"],
        client=client,
        dxlink_collector_factory=FakeCollector,
        now=datetime(2026, 8, 1, 9, 45, tzinfo=timezone.utc),
    )

    assert result.outcome == "SKIPPED_MARKET_CLOSED"
    assert client.market_calls == 0


def test_account_discovery_failure_reports_error_without_secret():
    class MissingAccountClient(FakeClient):
        def list_accounts(self):
            return []

    result = run_diagnostic(
        _settings(),
        ["XSP"],
        client=MissingAccountClient(),
        dxlink_collector_factory=FakeCollector,
        now=datetime(2026, 8, 1, 9, 45, tzinfo=timezone.utc),
    )

    assert result.outcome == "ERROR"
    assert "Configured Tastytrade account" in result.errors[0]
    assert "refresh-token" not in result.errors[0]


def test_duplicate_configured_account_is_rejected():
    class DuplicateAccountClient(FakeClient):
        def list_accounts(self):
            return [
                {"account": {"account-number": "5WT00001"}},
                {"account": {"account-number": "5WT00001"}},
            ]

    result = run_diagnostic(
        _settings(),
        ["XSP"],
        client=DuplicateAccountClient(),
        dxlink_collector_factory=FakeCollector,
        now=datetime(2026, 8, 1, 9, 45, tzinfo=timezone.utc),
    )

    assert result.outcome == "ERROR"
    assert "Configured Tastytrade account" in result.errors[0]