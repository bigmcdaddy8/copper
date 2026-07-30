from __future__ import annotations

import pytest

from K9.tastytrade.settings import TastytradeConfigurationError, TastytradeSettings


def _settings_values() -> dict[str, str]:
    return {
        "TW_APP_NAME": "k9-diagnostic",
        "TW_CLIENT_ID": "client-id",
        "TW_CLIENT_SECRET": "client-secret",
        "TW_REFRESH_TOKEN": "refresh-token",
        "TW_ACCOUNT_NUMBER": "5WT00001",
    }


def test_loads_production_settings_from_values():
    settings = TastytradeSettings.from_environment(
        "tastytrade_production", values=_settings_values()
    )

    assert settings.base_url == "https://api.tastyworks.com"
    assert settings.account_number == "5WT00001"
    assert settings.user_agent == "k9-diagnostic/1.0"


def test_loads_certification_settings_from_values():
    settings = TastytradeSettings.from_environment(
        "tastytrade_certification", values=_settings_values()
    )

    assert settings.base_url == "https://api.cert.tastyworks.com"


def test_missing_value_names_the_variable_without_exposing_secrets():
    values = _settings_values()
    values["TW_REFRESH_TOKEN"] = ""

    with pytest.raises(TastytradeConfigurationError) as exc_info:
        TastytradeSettings.from_environment("tastytrade_production", values=values)

    message = str(exc_info.value)
    assert "TW_REFRESH_TOKEN" in message
    assert "client-secret" not in message


def test_rejects_unknown_environment():
    with pytest.raises(TastytradeConfigurationError, match="Unsupported Tastytrade environment"):
        TastytradeSettings.from_environment("production", values=_settings_values())