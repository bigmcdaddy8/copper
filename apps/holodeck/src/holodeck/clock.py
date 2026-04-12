from __future__ import annotations
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo


class VirtualClock:
    """Step-based virtual clock for Holodeck simulation."""

    def __init__(
        self,
        start: datetime,
        session_open: str,
        session_close: str,
        tz: str = "America/Chicago",
    ) -> None:
        self._tz = ZoneInfo(tz)
        self._session_open = time.fromisoformat(session_open)
        self._session_close = time.fromisoformat(session_close)
        # Ensure start is tz-aware
        if start.tzinfo is None:
            self._now = start.replace(tzinfo=self._tz)
        else:
            self._now = start.astimezone(self._tz)

    def current_time(self) -> datetime:
        """Return the current virtual time (timezone-aware)."""
        return self._now

    def advance(self, minutes: int = 1) -> None:
        """Advance virtual time by the given number of minutes."""
        self._now += timedelta(minutes=minutes)

    def advance_to(self, target: datetime) -> None:
        """Set virtual time to target. Raises ValueError if target is in the past."""
        if target.tzinfo is None:
            target = target.replace(tzinfo=self._tz)
        else:
            target = target.astimezone(self._tz)
        if target < self._now:
            raise ValueError(
                f"advance_to target {target} is before current time {self._now}"
            )
        self._now = target

    def is_market_day(self) -> bool:
        """Return True if the current virtual date is a weekday (Mon-Fri).
        No holiday calendar in MVP."""
        return self._now.weekday() < 5  # 0=Mon, 4=Fri

    def is_market_open(self) -> bool:
        """Return True if virtual time is within the market session on a market day."""
        if not self.is_market_day():
            return False
        t = self._now.time().replace(second=0, microsecond=0)
        return self._session_open <= t <= self._session_close

    def session_close_time(self) -> datetime:
        """Return today's market close as a timezone-aware datetime."""
        close_dt = self._now.replace(
            hour=self._session_close.hour,
            minute=self._session_close.minute,
            second=0,
            microsecond=0,
        )
        return close_dt
