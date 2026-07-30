from __future__ import annotations

from types import SimpleNamespace

import pytest

from K9.broker_factory import create_broker
from K9.tastytrade.broker import TastytradeBroker


@pytest.mark.parametrize(
    ("environment", "base_url"),
    [
        ("tastytrade_production", "https://api.tastyworks.com"),
        ("tastytrade_certification", "https://api.cert.tastyworks.com"),
    ],
)
def test_factory_creates_read_only_tastytrade_broker(monkeypatch, environment, base_url):
    monkeypatch.setenv("TW_APP_NAME", "k9-diagnostic")
    monkeypatch.setenv("TW_CLIENT_ID", "client-id")
    monkeypatch.setenv("TW_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("TW_REFRESH_TOKEN", "refresh-token")
    monkeypatch.setenv("TW_ACCOUNT_NUMBER", "5WT00001")

    broker = create_broker(SimpleNamespace(environment=environment))

    assert isinstance(broker, TastytradeBroker)
    assert broker._settings.base_url == base_url