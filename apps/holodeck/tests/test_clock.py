import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from holodeck.clock import VirtualClock

TZ = "America/Chicago"
START = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))


def make_clock(start=START):
    return VirtualClock(start, "09:30", "15:00", TZ)


def test_initial_time():
    clock = make_clock()
    assert clock.current_time() == START


def test_advance_one_minute():
    clock = make_clock()
    clock.advance(1)
    assert clock.current_time() == datetime(2026, 1, 2, 9, 31, tzinfo=ZoneInfo(TZ))


def test_advance_multiple():
    clock = make_clock()
    clock.advance(5)
    assert clock.current_time() == datetime(2026, 1, 2, 9, 35, tzinfo=ZoneInfo(TZ))


def test_advance_to():
    clock = make_clock()
    target = datetime(2026, 1, 2, 12, 0, tzinfo=ZoneInfo(TZ))
    clock.advance_to(target)
    assert clock.current_time() == target


def test_advance_to_backwards_raises():
    clock = make_clock()
    past = datetime(2026, 1, 2, 9, 0, tzinfo=ZoneInfo(TZ))
    with pytest.raises(ValueError):
        clock.advance_to(past)


def test_is_market_open_during_session():
    clock = make_clock(datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ)))
    assert clock.is_market_open() is True


def test_is_market_open_before_open():
    clock = make_clock(datetime(2026, 1, 2, 8, 0, tzinfo=ZoneInfo(TZ)))
    assert clock.is_market_open() is False


def test_is_market_open_after_close():
    clock = make_clock(datetime(2026, 1, 2, 16, 0, tzinfo=ZoneInfo(TZ)))
    assert clock.is_market_open() is False


def test_is_market_day_weekday():
    # 2026-01-02 is a Friday
    clock = make_clock(datetime(2026, 1, 2, 10, 0, tzinfo=ZoneInfo(TZ)))
    assert clock.is_market_day() is True


def test_is_market_day_saturday():
    clock = make_clock(datetime(2026, 1, 3, 10, 0, tzinfo=ZoneInfo(TZ)))
    assert clock.is_market_day() is False


def test_is_market_day_sunday():
    clock = make_clock(datetime(2026, 1, 4, 10, 0, tzinfo=ZoneInfo(TZ)))
    assert clock.is_market_day() is False


def test_session_close_time():
    clock = make_clock()
    close = clock.session_close_time()
    assert close.hour == 15
    assert close.minute == 0
    assert close.date() == START.date()
