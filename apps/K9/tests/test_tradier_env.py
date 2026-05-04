from __future__ import annotations

import pytest

from K9.tradier_env import resolve_account_id


def test_resolve_account_id_sandbox_prefers_sandbox_var(monkeypatch):
    monkeypatch.setenv("TRADIER_ACCOUNT_ID", "PROD123")
    monkeypatch.setenv("TRADIER_SANDBOX_ACCOUNT_ID", "SANDBOX456")

    assert resolve_account_id("sandbox") == "SANDBOX456"


def test_resolve_account_id_sandbox_falls_back_to_primary(monkeypatch):
    monkeypatch.setenv("TRADIER_ACCOUNT_ID", "PROD123")
    monkeypatch.delenv("TRADIER_SANDBOX_ACCOUNT_ID", raising=False)

    assert resolve_account_id("sandbox") == "PROD123"


def test_resolve_account_id_production_uses_primary(monkeypatch):
    monkeypatch.setenv("TRADIER_ACCOUNT_ID", "PROD123")

    assert resolve_account_id("production") == "PROD123"


def test_resolve_account_id_invalid_environment():
    with pytest.raises(ValueError, match="Unsupported Tradier environment"):
        resolve_account_id("holodeck")
