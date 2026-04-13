"""Broker factory — instantiate the correct Broker from a TradeSpec (K9-0060)."""
from __future__ import annotations

import os

from bic.broker import Broker
from K9.config import TradeSpec

_HOLODECK_DATA = "data/holodeck/spx_2026_01_minutes.csv"


def create_broker(spec: TradeSpec) -> Broker:
    """Return the appropriate Broker implementation for *spec.environment*.

    - "holodeck"   → HolodeckBroker (local simulation, no API keys required)
    - "sandbox"    → TradierBroker  (sandbox.tradier.com, TRADIER_SANDBOX_API_KEY)
    - "production" → TradierBroker  (api.tradier.com, TRADIER_API_KEY)
    """
    env = spec.environment

    if env == "holodeck":
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from holodeck.broker import HolodeckBroker
        from holodeck.config import HolodeckConfig

        tz = ZoneInfo("America/Chicago")
        now = datetime.now(tz=tz)
        config = HolodeckConfig(
            starting_datetime=now.replace(hour=9, minute=30, second=0, microsecond=0),
            ending_datetime=now.replace(hour=15, minute=0, second=0, microsecond=0),
            data_path=_HOLODECK_DATA,
        )
        return HolodeckBroker(config)

    if env in ("sandbox", "production"):
        from dotenv import load_dotenv

        from K9.tradier.broker import TradierBroker

        load_dotenv()
        if env == "sandbox":
            api_key = os.environ["TRADIER_SANDBOX_API_KEY"]
            sandbox = True
        else:
            api_key = os.environ["TRADIER_API_KEY"]
            sandbox = False

        account_id = os.environ["TRADIER_ACCOUNT_ID"]
        return TradierBroker(api_key=api_key, account_id=account_id, sandbox=sandbox)

    raise ValueError(
        f"Unknown environment {env!r}. Must be 'holodeck', 'sandbox', or 'production'."
    )
