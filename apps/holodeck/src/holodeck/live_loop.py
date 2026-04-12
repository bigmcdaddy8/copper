"""Shared infrastructure for live-updating Holodeck CLI views (HD-0130)."""
from __future__ import annotations
import time
from datetime import datetime

from holodeck.clock import VirtualClock

# Maps --speed token → virtual minutes advanced per real-second tick
SPEED_MINUTES: dict[str, int] = {
    "1m":  1,
    "5m":  5,
    "15m": 15,
    "30m": 30,
    "1h":  60,
    "1d":  1440,
}


class LiveLoop:
    """Advance a VirtualClock one real-second at a time, yielding each virtual time.

    Usage::

        loop = LiveLoop(clock, speed="5m", data_end=end_dt)
        for vtime in loop:
            renderable = build_chart(vtime)
            live.update(renderable)

    The loop stops when virtual time exceeds ``data_end`` or the caller breaks out
    (e.g., on KeyboardInterrupt).
    """

    def __init__(
        self,
        clock: VirtualClock,
        speed: str,
        data_end: datetime,
        tick_seconds: float = 1.0,
    ) -> None:
        if speed not in SPEED_MINUTES:
            raise ValueError(
                f"Unknown speed {speed!r}.  Valid: {sorted(SPEED_MINUTES)}"
            )
        self._clock = clock
        self._step = SPEED_MINUTES[speed]
        self._data_end = data_end
        self._tick_seconds = tick_seconds

    def __iter__(self):
        while self._clock.current_time() <= self._data_end:
            yield self._clock.current_time()
            self._clock.advance(self._step)
            time.sleep(self._tick_seconds)
