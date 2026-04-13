"""Per-execution run log for K9 (K9-0080)."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from K9.engine.runner import RunResult

_DEFAULT_LOG_DIR = Path(os.environ.get("K9_LOG_DIR", "logs/K9"))


class RunLog:
    """Accumulates run metadata and writes a JSON log file.

    Log file path:
        <log_dir>/<spec_name>_<YYYYMMDD_HHMMSS>.json

    Example::

        log = RunLog(spec_name="spx_ic_20d_w5_tp34_0900")
        log.record(result)
        path = log.write()
    """

    def __init__(self, spec_name: str, log_dir: Path | None = None) -> None:
        self._spec_name = spec_name
        self._log_dir = log_dir or _DEFAULT_LOG_DIR
        self._started_at = datetime.now(tz=timezone.utc)
        self._payload: dict = {}

    def record(self, result: RunResult) -> None:
        """Populate log payload from a RunResult."""
        self._payload = {
            "spec_name":         result.spec_name,
            "environment":       result.environment,
            "started_at":        self._started_at.isoformat(),
            "outcome":           result.outcome,
            "order_id":          result.order_id,
            "filled_price":      result.filled_price,
            "net_credit":        result.net_credit,
            "expiration":        result.expiration,
            "short_put_strike":  result.short_put_strike,
            "short_call_strike": result.short_call_strike,
            "tp_order_id":       result.tp_order_id,
            "tp_price":          result.tp_price,
            "reason":            result.reason,
            "errors":            result.errors,
        }

    def write(self) -> Path:
        """Write the log to disk and return the file path."""
        self._log_dir.mkdir(parents=True, exist_ok=True)
        ts = self._started_at.strftime("%Y%m%d_%H%M%S")
        filename = f"{self._spec_name}_{ts}.json"
        path = self._log_dir / filename
        path.write_text(json.dumps(self._payload, indent=2, default=str))
        return path
