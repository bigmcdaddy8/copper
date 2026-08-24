"""Shared Typer-facing parsing/rendering helpers reused by every Dick's Laboratory analysis CLI.

Kept deliberately thin: one accepted way to parse `--anchor` / `--trading-date`
and one accepted way to render a UTC timestamp alongside America/Chicago local
time, so no script invents a second, possibly conflicting, parsing rule.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import typer

from dicks_laboratory.sessions import AnchorKind

_CT = ZoneInfo("America/Chicago")

ANCHOR_LABELS = {
    AnchorKind.SESSION_OPEN: "CME equity-index session open",
    AnchorKind.US_CASH_OPEN: "US cash session open",
    AnchorKind.CUSTOM_TIMESTAMP: "Custom UTC anchor",
}


def parse_anchor_argument(value: str) -> tuple[AnchorKind, datetime | None]:
    """Parse '--anchor' as 'session-open', 'cash-open', or an aware UTC timestamp."""
    if value == "session-open":
        return AnchorKind.SESSION_OPEN, None
    if value == "cash-open":
        return AnchorKind.US_CASH_OPEN, None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise typer.BadParameter(
            f"Invalid --anchor: {value!r}. Use 'session-open', 'cash-open', or an aware UTC timestamp."
        ) from exc
    if parsed.tzinfo is None:
        raise typer.BadParameter("Custom --anchor timestamps must be timezone-aware UTC (e.g. 2026-08-24T14:15:00Z).")
    return AnchorKind.CUSTOM_TIMESTAMP, parsed.astimezone(timezone.utc)


def parse_trading_date_argument(value: str | None) -> date | None:
    """Parse '--trading-date' as YYYY-MM-DD, or None if not supplied."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise typer.BadParameter(f"Invalid --trading-date: {value!r}. Use YYYY-MM-DD.") from exc


def anchor_label_slug(anchor_kind: AnchorKind) -> str:
    if anchor_kind is AnchorKind.SESSION_OPEN:
        return "session-open"
    if anchor_kind is AnchorKind.US_CASH_OPEN:
        return "cash-open"
    return "custom-anchor"


def format_utc_and_chicago(timestamp: datetime) -> tuple[str, str]:
    """Render one timestamp as (UTC text, America/Chicago text)."""
    utc_text = timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    ct_text = timestamp.astimezone(_CT).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] + " America/Chicago"
    return utc_text, ct_text


def yes_no(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "YES" if value else "no"


def format_timedelta(delta: timedelta) -> str:
    total_seconds = Decimal(str(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, Decimal(3600))
    minutes, seconds = divmod(remainder, Decimal(60))
    return f"{int(hours)}h {int(minutes)}m {seconds:.3f}s"
