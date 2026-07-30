"""Redacted JSON audit log for Tastytrade diagnostics."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from K9.tastytrade.diagnostic import TastytradeDiagnosticResult


class TastytradeDiagnosticLog:
    """Write diagnostic outcomes without broker credentials or account contents."""

    def __init__(self, log_dir: Path) -> None:
        self._log_dir = log_dir

    def write(self, result: TastytradeDiagnosticResult) -> Path:
        self._log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = self._log_dir / f"tastytrade_diagnostic_{timestamp}.json"
        path.write_text(json.dumps(result.to_dict(), indent=2))
        return path