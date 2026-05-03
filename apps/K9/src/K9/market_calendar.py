"""US options market calendar helpers for K9 entry gating."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, time, timedelta


_SESSION_OPEN_CT = time(8, 30)
_SESSION_CLOSE_CT = time(15, 0)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    first = date(year, month, 1)
    shift = (weekday - first.weekday()) % 7
    day = 1 + shift + (n - 1) * 7
    return date(year, month, day)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    last_dom = monthrange(year, month)[1]
    last = date(year, month, last_dom)
    shift = (last.weekday() - weekday) % 7
    return last - timedelta(days=shift)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _easter_date(year: int) -> date:
    # Anonymous Gregorian algorithm.
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def us_market_holidays(year: int) -> set[date]:
    """Return major US options-market holidays for a given year."""
    easter = _easter_date(year)
    good_friday = easter - timedelta(days=2)

    holidays = {
        _observed(date(year, 1, 1)),
        _nth_weekday(year, 1, 0, 3),  # MLK Day
        _nth_weekday(year, 2, 0, 3),  # Presidents Day
        good_friday,
        _last_weekday(year, 5, 0),  # Memorial Day
        _observed(date(year, 6, 19)),  # Juneteenth
        _observed(date(year, 7, 4)),  # Independence Day
        _nth_weekday(year, 9, 0, 1),  # Labor Day
        _nth_weekday(year, 11, 3, 4),  # Thanksgiving
        _observed(date(year, 12, 25)),  # Christmas
    }
    return holidays


def is_us_market_holiday(day: date) -> bool:
    return day in us_market_holidays(day.year)


def is_regular_session_open_ct(now_ct: datetime) -> bool:
    if now_ct.weekday() >= 5:
        return False
    if is_us_market_holiday(now_ct.date()):
        return False
    t = now_ct.time().replace(second=0, microsecond=0)
    return _SESSION_OPEN_CT <= t <= _SESSION_CLOSE_CT
