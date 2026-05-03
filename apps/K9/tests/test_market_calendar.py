from __future__ import annotations

from datetime import datetime, date
from zoneinfo import ZoneInfo

from K9.market_calendar import (
    is_regular_session_open_ct,
    is_us_market_holiday,
)

_CT = ZoneInfo("America/Chicago")


def test_known_2026_market_holidays():
    assert is_us_market_holiday(date(2026, 1, 1))
    assert is_us_market_holiday(date(2026, 1, 19))
    assert is_us_market_holiday(date(2026, 2, 16))
    assert is_us_market_holiday(date(2026, 4, 3))
    assert is_us_market_holiday(date(2026, 5, 25))
    assert is_us_market_holiday(date(2026, 6, 19))
    assert is_us_market_holiday(date(2026, 7, 3))
    assert is_us_market_holiday(date(2026, 9, 7))
    assert is_us_market_holiday(date(2026, 11, 26))
    assert is_us_market_holiday(date(2026, 12, 25))


def test_non_holiday_not_flagged():
    assert not is_us_market_holiday(date(2026, 1, 2))


def test_regular_session_open_ct_true():
    dt = datetime(2026, 1, 6, 9, 0, tzinfo=_CT)
    assert is_regular_session_open_ct(dt)


def test_regular_session_open_ct_false_on_weekend():
    dt = datetime(2026, 1, 10, 9, 0, tzinfo=_CT)
    assert not is_regular_session_open_ct(dt)


def test_regular_session_open_ct_false_on_holiday():
    dt = datetime(2026, 1, 19, 9, 0, tzinfo=_CT)
    assert not is_regular_session_open_ct(dt)


def test_regular_session_open_ct_false_outside_hours():
    pre = datetime(2026, 1, 6, 8, 0, tzinfo=_CT)
    post = datetime(2026, 1, 6, 15, 30, tzinfo=_CT)
    assert not is_regular_session_open_ct(pre)
    assert not is_regular_session_open_ct(post)
