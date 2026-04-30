"""Policy tests for trade spec files in apps/K9/trade_specs."""
from __future__ import annotations

from pathlib import Path


def test_no_json_trade_specs() -> None:
    specs_dir = Path("apps/K9/trade_specs")
    json_specs = sorted(p.name for p in specs_dir.glob("*.json"))
    assert not json_specs, (
        "JSON trade spec(s) found. YAML v2 is required for all active specs: "
        + ", ".join(json_specs)
    )
