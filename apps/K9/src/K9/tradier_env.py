"""Tradier environment variable resolution helpers."""
from __future__ import annotations

import os


def resolve_account_id(environment: str) -> str:
    """Resolve Tradier account id for *environment*.

    Sandbox prefers TRADIER_SANDBOX_ACCOUNT_ID and falls back to
    TRADIER_ACCOUNT_ID for backward compatibility.
    """
    if environment == "sandbox":
        return os.environ.get("TRADIER_SANDBOX_ACCOUNT_ID") or os.environ[
            "TRADIER_ACCOUNT_ID"
        ]
    if environment == "production":
        return os.environ["TRADIER_ACCOUNT_ID"]
    raise ValueError(
        f"Unsupported Tradier environment {environment!r}. "
        "Must be 'sandbox' or 'production'."
    )
