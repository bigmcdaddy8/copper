"""0X-A: futures contract identity, universe, exchange calendar and the
deterministic roll assessment. No network, no quote token."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from dicks_laboratory.futures_contracts import (
    CME_EQUITY_INDEX_ROLL_RULE,
    LABORATORY_UNIVERSE,
    MONTH_CODES,
    ROLL_LEAD_CALENDAR_DAYS,
    FuturesContractError,
    RollSeverity,
    RollState,
    assess_roll,
    contract_from_metadata,
    discover_chain,
    exchange_calendar_entry,
    parse_contract_symbol,
    roll_record_draft,
    upcoming_trading_date,
)


def _row(symbol, expiration, *, root=None, streamer=None, active=False, next_active=False,
         tradeable=True, closing_only=False, exchange="CME", tick="0.25", mult="50.0"):
    parsed = parse_contract_symbol(symbol)
    month_year = symbol[len(parsed.root) + 1:]
    return {
        "symbol": symbol,
        "product-code": root or parsed.root,
        "streamer-symbol": streamer if streamer is not None else f"/{parsed.root}{month_year[0]}2{month_year[1:]}:XCME",
        "exchange": exchange,
        "expiration-date": expiration,
        "stops-trading-at": f"{expiration}T14:30:00.000+00:00",
        "active-month": active,
        "next-active-month": next_active,
        "is-tradeable": tradeable,
        "is-closing-only": closing_only,
        "tick-size": tick,
        "notional-multiplier": mult,
        "future-product": {"listed-months": ["H", "M", "U", "Z"]},
    }


def _es_chain(*, z6_active=True, h7_next=True, **z6_overrides):
    return [
        {"symbol": "/CLZ6", "product-code": "CL", "streamer-symbol": "/CLZ26:XNYM"},
        _row("/ESZ6", "2026-12-18", active=z6_active, **z6_overrides),
        _row("/ESH7", "2027-03-19", next_active=h7_next),
        _row("/ESM7", "2027-06-17"),
    ]


# --- identity / month codes ----------------------------------------------------


@pytest.mark.parametrize("symbol,root,code,month,digits", [
    ("/ESH7", "ES", "H", 3, "7"), ("/ESM7", "ES", "M", 6, "7"), ("/ESU6", "ES", "U", 9, "6"),
    ("/ESZ6", "ES", "Z", 12, "6"), ("/MESZ6", "MES", "Z", 12, "6"), ("/NQH7", "NQ", "H", 3, "7"),
    ("/MNQZ6", "MNQ", "Z", 12, "6"), ("/CLF27", "CL", "F", 1, "27"),
])
def test_contract_symbol_parsing(symbol, root, code, month, digits):
    parsed = parse_contract_symbol(symbol)
    assert (parsed.root, parsed.month_code, parsed.month, parsed.year_digits) == (root, code, month, digits)


@pytest.mark.parametrize("bad", ["ESZ6", "/ESZ", "/ES", "/ESA6", "/esz6", "", "/ESZ6:XCME"])
def test_contract_symbol_parsing_rejects_malformed(bad):
    with pytest.raises(FuturesContractError):
        parse_contract_symbol(bad)


def test_month_codes_cover_all_twelve_months():
    assert sorted(MONTH_CODES.values()) == list(range(1, 13))


def test_contract_identity_comes_from_metadata():
    c = contract_from_metadata(_row("/ESZ6", "2026-12-18", active=True))
    assert c.instrument_id == "FUTURE:CME:ES:2026-12"
    assert (c.broker_symbol, c.streamer_symbol) == ("/ESZ6", "/ESZ26:XCME")
    assert c.expiration_date == date(2026, 12, 18)
    assert c.stops_trading_at == datetime(2026, 12, 18, 14, 30, tzinfo=timezone.utc)
    assert c.active_month and not c.next_active_month and c.tradeable and not c.closing_only
    assert str(c.tick_size) == "0.25" and str(c.multiplier) == "50.0"


def test_december_to_march_year_transition():
    chain = discover_chain(_es_chain(), "ES")
    assert [c.instrument_id for c in chain] == [
        "FUTURE:CME:ES:2026-12", "FUTURE:CME:ES:2027-03", "FUTURE:CME:ES:2027-06"]


@pytest.mark.parametrize("override,msg", [
    ({"product-code": "MES"}, "does not match"),
    ({"streamer-symbol": ""}, "streamer"),
    ({"exchange": None}, "exchange"),
    ({"expiration-date": None}, "expiration"),
    ({"expiration-date": "2026-11-20"}, "disagrees"),
])
def test_contract_from_metadata_rejects_inconsistent_identity(override, msg):
    row = _row("/ESZ6", "2026-12-18")
    row.update(override)
    with pytest.raises(FuturesContractError, match=msg):
        contract_from_metadata(row)


# --- universe ----------------------------------------------------------------------


def test_initial_universe_and_micro_relationships():
    assert set(LABORATORY_UNIVERSE) == {"ES", "MES", "NQ", "MNQ"}
    assert LABORATORY_UNIVERSE["MES"].standard_root == "ES"
    assert LABORATORY_UNIVERSE["MNQ"].standard_root == "NQ"
    assert LABORATORY_UNIVERSE["ES"].standard_root is None
    for p in LABORATORY_UNIVERSE.values():
        assert p.exchange == "CME" and p.listed_months == ("H", "M", "U", "Z")
        assert p.roll_rule == CME_EQUITY_INDEX_ROLL_RULE


@pytest.mark.parametrize("root,symbol,mult,instrument_id", [
    ("MES", "/MESZ6", "5.0", "FUTURE:CME:MES:2026-12"),
    ("NQ", "/NQZ6", "20.0", "FUTURE:CME:NQ:2026-12"),
    ("MNQ", "/MNQZ6", "2.0", "FUTURE:CME:MNQ:2026-12"),
])
def test_mes_nq_mnq_metadata_resolution(root, symbol, mult, instrument_id):
    futures = _es_chain() + [_row(symbol, "2026-12-18", active=True, mult=mult)]
    (c,) = discover_chain(futures, root)
    assert c.instrument_id == instrument_id and str(c.multiplier) == mult
    assert assess_roll(futures, symbol, date(2026, 10, 7)).state is RollState.CURRENT


# --- exchange calendar --------------------------------------------------------------


def test_cme_published_december_2026_dates():
    entry = exchange_calendar_entry(LABORATORY_UNIVERSE["ES"], 2026, 12)
    assert (entry.expiration_date, entry.customary_roll_date, entry.source) == (
        date(2026, 12, 18), date(2026, 12, 14), "CME_PUBLISHED")


def test_rule_derived_march_2027_is_monday_before_third_friday():
    entry = exchange_calendar_entry(LABORATORY_UNIVERSE["ES"], 2027, 3)
    assert (entry.expiration_date, entry.customary_roll_date, entry.source) == (
        date(2027, 3, 19), date(2027, 3, 15), "RULE_DERIVED")
    assert entry.customary_roll_date.weekday() == 0


# --- roll assessment -----------------------------------------------------------------


def test_current_well_before_roll():
    a = assess_roll(_es_chain(), "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity, a.recommended_action) == (RollState.CURRENT, RollSeverity.OK, "NONE")
    assert a.candidate.broker_symbol == "/ESH7"
    assert a.broker_active.broker_symbol == "/ESZ6" and a.broker_next_active.broker_symbol == "/ESH7"
    assert a.approaching_from == date(2026, 11, 30)


def test_lead_window_boundary():
    assert ROLL_LEAD_CALENDAR_DAYS == 14
    assert assess_roll(_es_chain(), "/ESZ6", date(2026, 11, 27)).state is RollState.CURRENT
    a = assess_roll(_es_chain(), "/ESZ6", date(2026, 11, 30))
    assert (a.state, a.severity) == (RollState.ROLL_APPROACHING, RollSeverity.WARN)
    assert "/ESZ6 -> /ESH7" in a.recommended_action


def test_approaching_the_day_before_roll():
    a = assess_roll(_es_chain(), "/ESZ6", date(2026, 12, 11))
    assert (a.state, a.severity) == (RollState.ROLL_APPROACHING, RollSeverity.WARN)


def test_on_customary_roll_date_is_roll_due_warn():
    a = assess_roll(_es_chain(), "/ESZ6", date(2026, 12, 14))
    assert (a.state, a.severity) == (RollState.ROLL_DUE, RollSeverity.WARN)
    assert "APPROVE ROLL" in a.recommended_action and "/ESH7" in a.recommended_action


def test_after_roll_while_old_pin_remains():
    a = assess_roll(_es_chain(z6_active=False, h7_next=False), "/ESZ6", date(2026, 12, 17))
    assert (a.state, a.severity) == (RollState.ROLL_DUE, RollSeverity.WARN)


def test_on_expiration_trading_date_pin_is_stale_fail():
    a = assess_roll(_es_chain(), "/ESZ6", date(2026, 12, 18))
    assert (a.state, a.severity) == (RollState.PIN_STALE, RollSeverity.FAIL)


def test_expired_pin_no_longer_listed_fails():
    futures = [r for r in _es_chain() if r["symbol"] != "/ESZ6"]
    a = assess_roll(futures, "/ESZ6", date(2026, 12, 21))
    assert (a.state, a.severity) == (RollState.PIN_STALE, RollSeverity.FAIL)
    assert "no longer listed" in a.reasons[0]


@pytest.mark.parametrize("override,text", [({"tradeable": False}, "not tradeable"),
                                           ({"closing_only": True}, "closing-only")])
def test_untradeable_or_closing_only_pin_fails(override, text):
    a = assess_roll(_es_chain(**override), "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.PIN_STALE, RollSeverity.FAIL)
    assert any(text in r for r in a.reasons)


def test_broker_says_pin_no_longer_active_before_roll_window_warns():
    # Pin still valid, but broker active-month disagrees with exchange lifecycle.
    futures = _es_chain(z6_active=False)
    futures[2]["active-month"] = True
    a = assess_roll(futures, "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.METADATA_CONFLICT, RollSeverity.WARN)
    assert any("broker active-month is /ESH7" in r for r in a.reasons)


def test_broker_next_active_changed_to_non_successor_warns():
    futures = _es_chain(h7_next=False)
    futures[3]["next-active-month"] = True  # broker points at /ESM7, skipping /ESH7
    a = assess_roll(futures, "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.METADATA_CONFLICT, RollSeverity.WARN)
    assert a.candidate.broker_symbol == "/ESH7"


def test_pin_still_tradeable_but_no_longer_customary_lead():
    # Past customary roll: still tradeable and broker-active, yet ROLL_DUE.
    a = assess_roll(_es_chain(), "/ESZ6", date(2026, 12, 15))
    assert a.state is RollState.ROLL_DUE and a.pinned.tradeable
    assert any("broker still flags" in r for r in a.reasons)


def test_broker_exchange_expiration_conflict_fails():
    futures = _es_chain()
    futures[1]["expiration-date"] = "2026-12-11"  # broker disagrees with CME-published 12-18
    a = assess_roll(futures, "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.METADATA_CONFLICT, RollSeverity.FAIL)


@pytest.mark.parametrize("futures", [None, "not a list"])
def test_missing_metadata_fails(futures):
    a = assess_roll(futures, "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.METADATA_UNAVAILABLE, RollSeverity.FAIL)


def test_pin_row_missing_streamer_fails():
    a = assess_roll(_es_chain(streamer=""), "/ESZ6", date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.METADATA_UNAVAILABLE, RollSeverity.FAIL)


@pytest.mark.parametrize("pin", ["ESZ6", "/CLZ6", "/ESF7"])
def test_invalid_pin_fails(pin):
    a = assess_roll(_es_chain(), pin, date(2026, 10, 7))
    assert (a.state, a.severity) == (RollState.PIN_INVALID, RollSeverity.FAIL)


def test_successor_skips_closing_only_and_untradeable():
    futures = _es_chain()
    futures[2]["is-closing-only"] = True
    a = assess_roll(futures, "/ESZ6", date(2026, 12, 14))
    assert a.candidate.broker_symbol == "/ESM7"


def test_assessment_never_mutates_the_production_pin():
    from dicks_laboratory import production_symbol
    before = production_symbol.PINNED_ES_SYMBOL
    assess_roll(_es_chain(), before, date(2026, 12, 18))
    assert production_symbol.PINNED_ES_SYMBOL == before


# --- provenance / trading date ------------------------------------------------------


def test_roll_record_draft_captures_provenance_without_decision():
    futures = _es_chain()
    a = assess_roll(futures, "/ESZ6", date(2026, 12, 14))
    rec = roll_record_draft(a, futures, datetime(2026, 12, 13, 22, 42, tzinfo=timezone.utc))
    assert rec["old_contract"]["instrument_id"] == "FUTURE:CME:ES:2026-12"
    assert rec["new_contract"]["instrument_id"] == "FUTURE:CME:ES:2027-03"
    assert rec["cme_reference"]["customary_roll_date"] == "2026-12-14"
    assert rec["broker_metadata_snapshot"]["old"]["symbol"] == "/ESZ6"
    assert rec["broker_metadata_snapshot"]["captured_at_utc"] == "2026-12-13T22:42:00+00:00"
    assert all(v is None for v in rec["decision"].values())


@pytest.mark.parametrize("now,expected", [
    ("2026-12-13T22:42:00+00:00", date(2026, 12, 14)),  # Sun 16:42 CST preflight -> Monday
    ("2026-12-14T15:00:00+00:00", date(2026, 12, 14)),  # in session
    ("2026-12-17T22:42:00+00:00", date(2026, 12, 18)),  # Thu preflight -> Fri (expiration day)
    ("2026-12-19T15:00:00+00:00", date(2026, 12, 21)),  # Saturday -> Monday
    ("2026-10-05T21:42:00+00:00", date(2026, 10, 6)),   # CDT: Mon 16:42 preflight -> Tue
])
def test_upcoming_trading_date(now, expected):
    assert upcoming_trading_date(datetime.fromisoformat(now)) == expected
