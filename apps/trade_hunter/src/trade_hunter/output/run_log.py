"""Per-run log file writer for trade_hunter."""

from datetime import datetime
from pathlib import Path

_SEP_HEAVY = "=" * 50
_SEP_LIGHT = "-" * 50
_SUMMARY_VALUE_COL = 25


class RunLog:
    """Accumulates warning and info entries for a single pipeline run.

    Usage::

        log = RunLog(run_start=datetime.now())
        enriched, warnings = enrich_candidates(...)
        log.add_warnings(warnings)
        log.info("Run date: 2025-03-19")
        log.write(output_dir, summary={"Loaded (BULL)": 45, "Scored (BULL)": 28})
    """

    def __init__(self, run_start: datetime) -> None:
        self._run_start = run_start
        self._entries: list[str] = []

    def warn(self, message: str) -> None:
        """Append a [WARN] entry."""
        self._entries.append(f"[WARN] {message}")

    def add_warnings(self, warnings: list[str]) -> None:
        """Append all items from an existing warnings list as [WARN] entries.

        Items are expected to already carry their own prefix (e.g. "[WARN] …")
        and are appended verbatim. This matches the format returned by
        enrich_candidates() and apply_hard_filters().
        """
        self._entries.extend(warnings)

    def info(self, message: str) -> None:
        """Append an [INFO] entry."""
        self._entries.append(f"[INFO] {message}")

    def write(self, output_dir: Path, summary: dict[str, int] | None = None) -> Path:
        """Write the log file to output_dir and return its path.

        Creates output_dir if it does not exist.
        File name: run_log_YYYYMMDD_HHMMSS.txt
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = self._run_start.strftime("%Y%m%d_%H%M%S")
        log_path = output_dir / f"run_log_{timestamp}.txt"

        lines: list[str] = []

        # Header
        header_ts = self._run_start.strftime("%Y-%m-%d %H:%M:%S")
        lines.append(f"trade_hunter run log — {header_ts}")
        lines.append(_SEP_HEAVY)
        lines.append("")

        # Entries
        for entry in self._entries:
            lines.append(entry)

        # Summary section (omitted when None or empty)
        if summary:
            lines.append("")
            lines.append(_SEP_LIGHT)
            lines.append("Summary")
            lines.append(_SEP_LIGHT)
            for key, value in summary.items():
                label = f"{key}:"
                lines.append(f"{label:<{_SUMMARY_VALUE_COL}}{value}")

        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return log_path
