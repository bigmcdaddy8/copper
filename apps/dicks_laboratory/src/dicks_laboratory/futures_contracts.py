"""0X-A: futures contract identity, instrument universe and roll status.

Three concepts are kept deliberately separate (never one boolean):

A. Exchange contract lifecycle -- CME expiration and customary roll date
   (`ExchangeCalendarEntry`, `exchange_calendar_entry`).
B. Broker metadata -- Tastytrade `active-month` / `next-active-month`,
   tradeability, closing-only, streamer symbol (`FuturesContract`, parsed
   from `list_futures()` REST rows only; never a DXLink quote token).
C. Laboratory production pin -- the Human-approved contract to capture
   (`production_symbol.PINNED_ES_SYMBOL`).

`assess_roll` combines them into a deterministic, explained `RollAssessment`.
It only ever RECOMMENDS: no code path here changes the pin. A roll is a
Human-approved edit of the pin (see docs/dicks_laboratory/FUTURES_CONTRACT_ROLL_0XA.md).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from dicks_laboratory.models import InstrumentIdentity, InstrumentKind

# Standard exchange futures month codes. A product's own listed cycle
# (`FuturesProduct.listed_months`) decides which of them are valid for it.
MONTH_CODES: dict[str, int] = {
    "F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6,
    "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12,
}
_SYMBOL_PATTERN = re.compile(r"^/([A-Z0-9]+?)([FGHJKMNQUVXZ])(\d{1,2})$")

# Roll-rule identifiers (exchange lifecycle policy, product-specific).
CME_EQUITY_INDEX_ROLL_RULE = "CME_EQUITY_INDEX_MONDAY_BEFORE_EXPIRATION_V1"

# 0X-A proposed warning lead: ROLL_APPROACHING starts this many CALENDAR days
# before the customary roll date. 14 days = two weekly arming cycles before the
# deadline (for ES Dec-2026: first warning TD 2026-11-30; the new pin must be
# deployed before the Sunday 2026-12-13 17:00 CT open of TD 2026-12-14).
ROLL_LEAD_CALENDAR_DAYS = 14


class FuturesContractError(ValueError):
    """A symbol or metadata row cannot be interpreted as a futures contract."""


@dataclass(frozen=True)
class FuturesProduct:
    """Small Laboratory product-policy layer. Tick size and multiplier are NOT
    duplicated here -- they come from authoritative broker metadata."""

    root: str
    exchange: str
    description: str
    listed_months: tuple[str, ...]
    roll_rule: str
    standard_root: str | None = None  # set on a micro: the standard product it mirrors


_EQUITY_QUARTERLY = ("H", "M", "U", "Z")
LABORATORY_UNIVERSE: dict[str, FuturesProduct] = {
    p.root: p
    for p in (
        FuturesProduct("ES", "CME", "E-mini S&P 500", _EQUITY_QUARTERLY, CME_EQUITY_INDEX_ROLL_RULE),
        FuturesProduct("MES", "CME", "Micro E-mini S&P 500", _EQUITY_QUARTERLY, CME_EQUITY_INDEX_ROLL_RULE, "ES"),
        FuturesProduct("NQ", "CME", "E-mini Nasdaq-100", _EQUITY_QUARTERLY, CME_EQUITY_INDEX_ROLL_RULE),
        FuturesProduct("MNQ", "CME", "Micro E-mini Nasdaq-100", _EQUITY_QUARTERLY, CME_EQUITY_INDEX_ROLL_RULE, "NQ"),
    )
}


@dataclass(frozen=True)
class ContractSymbol:
    """A parsed broker display symbol, e.g. `/ESZ6`. The year here is only the
    display digit(s); the full year always comes from metadata."""

    root: str
    month_code: str
    month: int
    year_digits: str


def parse_contract_symbol(symbol: str) -> ContractSymbol:
    match = _SYMBOL_PATTERN.match(symbol)
    if match is None:
        raise FuturesContractError(f"{symbol!r} is not a futures display symbol (expected /<ROOT><MONTH><YEAR>, e.g. /ESZ6).")
    root, month_code, year_digits = match.groups()
    return ContractSymbol(root, month_code, MONTH_CODES[month_code], year_digits)


@dataclass(frozen=True)
class FuturesContract:
    """One listed contract as reported by broker metadata (concept B)."""

    root: str
    exchange: str
    month_code: str
    contract_month: int
    contract_year: int
    broker_symbol: str
    streamer_symbol: str
    expiration_date: date
    stops_trading_at: datetime | None
    active_month: bool
    next_active_month: bool
    tradeable: bool
    closing_only: bool
    tick_size: Decimal | None
    multiplier: Decimal | None
    broker_listed_months: tuple[str, ...]

    @property
    def instrument(self) -> InstrumentIdentity:
        return InstrumentIdentity(InstrumentKind.FUTURE, self.exchange, self.root, self.contract_year, self.contract_month)

    @property
    def instrument_id(self) -> str:
        return self.instrument.canonical_id


def _decimal(value: object) -> Decimal | None:
    try:
        return Decimal(str(value)) if value is not None else None
    except InvalidOperation:
        return None


def _utc(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(timezone.utc) if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def contract_from_metadata(row: dict) -> FuturesContract:
    """Parse one `list_futures()` row. Raises on anything identity-relevant
    that is missing -- identity is never guessed."""
    symbol = row.get("symbol")
    if not isinstance(symbol, str):
        raise FuturesContractError("metadata row has no symbol.")
    parsed = parse_contract_symbol(symbol)
    root = row.get("product-code")
    if root != parsed.root:
        raise FuturesContractError(f"{symbol!r} product-code {root!r} does not match its symbol root {parsed.root!r}.")
    streamer = row.get("streamer-symbol")
    if not isinstance(streamer, str) or not streamer:
        raise FuturesContractError(f"{symbol!r} metadata has no streamer-symbol.")
    exchange = row.get("exchange")
    if not isinstance(exchange, str) or not exchange:
        raise FuturesContractError(f"{symbol!r} metadata has no exchange.")
    try:
        expiration = date.fromisoformat(str(row.get("expiration-date")))
    except ValueError as exc:
        raise FuturesContractError(f"{symbol!r} metadata has no usable expiration-date.") from exc
    if expiration.month != parsed.month or not str(expiration.year).endswith(parsed.year_digits):
        raise FuturesContractError(
            f"{symbol!r} expiration-date {expiration.isoformat()} disagrees with its month code / year digit."
        )
    product = row.get("future-product") if isinstance(row.get("future-product"), dict) else {}
    return FuturesContract(
        root=root,
        exchange=exchange,
        month_code=parsed.month_code,
        contract_month=parsed.month,
        contract_year=expiration.year,
        broker_symbol=symbol,
        streamer_symbol=streamer,
        expiration_date=expiration,
        stops_trading_at=_utc(row.get("stops-trading-at")),
        active_month=row.get("active-month") is True,
        next_active_month=row.get("next-active-month") is True,
        tradeable=row.get("is-tradeable") is True,
        closing_only=row.get("is-closing-only") is True,
        tick_size=_decimal(row.get("tick-size")),
        multiplier=_decimal(row.get("notional-multiplier")),
        broker_listed_months=tuple(product.get("listed-months") or ()),
    )


def discover_chain(futures: list[dict], root: str) -> tuple[FuturesContract, ...]:
    """Every listed contract for `root`, nearest expiration first. Rows that
    cannot be parsed are skipped (their absence is visible in the chain)."""
    chain = []
    for row in futures:
        if isinstance(row, dict) and row.get("product-code") == root:
            try:
                chain.append(contract_from_metadata(row))
            except FuturesContractError:
                continue
    return tuple(sorted(chain, key=lambda c: c.expiration_date))


# ---- A. exchange lifecycle ---------------------------------------------------


@dataclass(frozen=True)
class ExchangeCalendarEntry:
    expiration_date: date
    customary_roll_date: date
    source: str  # "CME_PUBLISHED" (verified table) or "RULE_DERIVED"


# CME-published U.S. equity-index dates, verified for 0W-4B / 0X-A
# (cmegroup.com/trading/equity-index/rolldates.html: roll = Monday before the
# third-Friday expiration). Applies to ES, MES, NQ and MNQ alike.
CME_EQUITY_INDEX_PUBLISHED: dict[tuple[int, int], tuple[date, date]] = {
    (2026, 9): (date(2026, 9, 18), date(2026, 9, 14)),
    (2026, 12): (date(2026, 12, 18), date(2026, 12, 14)),
}


def _third_friday(year: int, month: int) -> date:
    first = date(year, month, 1)
    return first + timedelta(days=(4 - first.weekday()) % 7 + 14)


def exchange_calendar_entry(product: FuturesProduct, year: int, month: int) -> ExchangeCalendarEntry:
    if product.roll_rule != CME_EQUITY_INDEX_ROLL_RULE:
        raise FuturesContractError(f"no exchange calendar rule for {product.root} ({product.roll_rule}).")
    published = CME_EQUITY_INDEX_PUBLISHED.get((year, month))
    if published is not None:
        return ExchangeCalendarEntry(published[0], published[1], "CME_PUBLISHED")
    expiration = _third_friday(year, month)
    return ExchangeCalendarEntry(expiration, expiration - timedelta(days=4), "RULE_DERIVED")


def upcoming_trading_date(now: datetime) -> date:
    """The futures trading date a check run at `now` protects: the current
    trading date while in session, otherwise the next session's (e.g. the
    16:42 CT Sunday preflight -> Monday). Reuses the accepted `sessions.py`
    classifier -- no separate day-boundary arithmetic."""
    from dicks_laboratory.long_running_capture import next_session_open_after
    from dicks_laboratory.sessions import SessionState, classify_es_session

    membership = classify_es_session(now)
    if membership.state is SessionState.IN_SESSION and membership.trading_date is not None:
        return membership.trading_date
    trading_date = classify_es_session(next_session_open_after(now)).trading_date
    assert trading_date is not None
    return trading_date


# ---- roll assessment ----------------------------------------------------------


class RollState(StrEnum):
    CURRENT = "CURRENT"
    ROLL_APPROACHING = "ROLL_APPROACHING"
    ROLL_DUE = "ROLL_DUE"
    PIN_STALE = "PIN_STALE"
    METADATA_CONFLICT = "METADATA_CONFLICT"
    METADATA_UNAVAILABLE = "METADATA_UNAVAILABLE"
    PIN_INVALID = "PIN_INVALID"


class RollSeverity(StrEnum):
    OK = "OK"
    # Severity IS the production-preflight consequence (0X-B policy):
    WARN = "WARN"  # non-blocking: production preflight passes with warning lines
    FAIL = "FAIL"  # production preflight fails closed (incl. ROLL_DUE since 0X-B)


@dataclass(frozen=True)
class RollAssessment:
    product: str
    trading_date: date
    pinned_symbol: str
    state: RollState
    severity: RollSeverity
    reasons: tuple[str, ...]
    recommended_action: str
    pinned: FuturesContract | None = None
    exchange: ExchangeCalendarEntry | None = None
    approaching_from: date | None = None
    broker_active: FuturesContract | None = None
    broker_next_active: FuturesContract | None = None
    candidate: FuturesContract | None = None


def _result(product, trading_date, pin, state, severity, reasons, action, **facts) -> RollAssessment:
    return RollAssessment(product, trading_date, pin, state, severity, tuple(reasons), action, **facts)


def assess_roll(
    futures: list[dict] | None,
    pinned_symbol: str,
    trading_date: date,
    lead_days: int = ROLL_LEAD_CALENDAR_DAYS,
) -> RollAssessment:
    """Deterministic roll status for `pinned_symbol` on futures `trading_date`.

    Precedence: invalid pin / unavailable metadata / stale pin / identity
    conflicts FAIL first; otherwise the exchange lifecycle phase decides
    CURRENT (OK) / ROLL_APPROACHING (WARN) / ROLL_DUE (FAIL, 0X-B), and broker
    active-month disagreement is reported without overriding the exchange
    phase -- as a WARN-level METADATA_CONFLICT only while the pin is otherwise
    CURRENT (identity-level conflicts are FAIL above).
    """
    try:
        parsed = parse_contract_symbol(pinned_symbol)
    except FuturesContractError as exc:
        return _result("?", trading_date, pinned_symbol, RollState.PIN_INVALID, RollSeverity.FAIL, [str(exc)], "FIX PIN")
    root = parsed.root
    product = LABORATORY_UNIVERSE.get(root)
    if product is None:
        return _result(root, trading_date, pinned_symbol, RollState.PIN_INVALID, RollSeverity.FAIL,
                       [f"root {root!r} is not in the Laboratory instrument universe"], "FIX PIN")
    if parsed.month_code not in product.listed_months:
        return _result(root, trading_date, pinned_symbol, RollState.PIN_INVALID, RollSeverity.FAIL,
                       [f"month code {parsed.month_code} is not a listed {root} month {product.listed_months}"], "FIX PIN")
    if not isinstance(futures, list):
        return _result(root, trading_date, pinned_symbol, RollState.METADATA_UNAVAILABLE, RollSeverity.FAIL,
                       ["broker futures metadata unavailable"], "RETRY / INVESTIGATE METADATA")

    row = next((r for r in futures if isinstance(r, dict) and r.get("symbol") == pinned_symbol), None)
    chain = discover_chain(futures, root)
    broker_active = next((c for c in chain if c.active_month), None)
    broker_next = next((c for c in chain if c.next_active_month), None)
    facts = {"broker_active": broker_active, "broker_next_active": broker_next}
    if row is None:
        return _result(root, trading_date, pinned_symbol, RollState.PIN_STALE, RollSeverity.FAIL,
                       [f"{pinned_symbol} is no longer listed in broker metadata"], "HUMAN: RE-PIN REQUIRED", **facts)
    try:
        pinned = contract_from_metadata(row)
    except FuturesContractError as exc:
        return _result(root, trading_date, pinned_symbol, RollState.METADATA_UNAVAILABLE, RollSeverity.FAIL,
                       [str(exc)], "RETRY / INVESTIGATE METADATA", **facts)
    facts["pinned"] = pinned
    exchange = exchange_calendar_entry(product, pinned.contract_year, pinned.contract_month)
    approaching_from = exchange.customary_roll_date - timedelta(days=lead_days)
    facts.update(exchange=exchange, approaching_from=approaching_from)
    later = [c for c in chain if c.expiration_date > pinned.expiration_date
             and c.month_code in product.listed_months and c.tradeable and not c.closing_only]
    candidate = later[0] if later else None
    facts["candidate"] = candidate

    fail: list[str] = []
    if pinned.expiration_date != exchange.expiration_date:
        fail.append(f"broker expiration {pinned.expiration_date} != exchange expiration "
                    f"{exchange.expiration_date} ({exchange.source})")
    if pinned.exchange != product.exchange:
        fail.append(f"broker exchange {pinned.exchange} != product exchange {product.exchange}")
    if fail:
        return _result(root, trading_date, pinned_symbol, RollState.METADATA_CONFLICT, RollSeverity.FAIL,
                       fail, "HUMAN: RESOLVE METADATA CONFLICT", **facts)

    stale: list[str] = []
    if trading_date >= pinned.expiration_date:
        stale.append(f"trading date {trading_date} is on/after expiration {pinned.expiration_date} "
                     "(last trade day session is truncated)")
    if not pinned.tradeable:
        stale.append(f"{pinned_symbol} is not tradeable")
    if pinned.closing_only:
        stale.append(f"{pinned_symbol} is closing-only")
    if stale:
        return _result(root, trading_date, pinned_symbol, RollState.PIN_STALE, RollSeverity.FAIL,
                       stale, _roll_action("HUMAN: RE-PIN REQUIRED", pinned_symbol, candidate), **facts)

    roll_date = exchange.customary_roll_date
    broker_notes: list[str] = []
    if broker_active is not None and broker_active.broker_symbol != pinned_symbol:
        broker_notes.append(f"broker active-month is {broker_active.broker_symbol}, not the pin")
    if broker_active is None:
        broker_notes.append(f"broker reports no active-month {root} contract")
    if candidate is not None and broker_next is not None and broker_next.broker_symbol != candidate.broker_symbol \
            and broker_active is not None and broker_active.broker_symbol == pinned_symbol:
        broker_notes.append(f"broker next-active {broker_next.broker_symbol} != exchange successor "
                            f"{candidate.broker_symbol}")

    if trading_date >= roll_date:
        reasons = [f"customary roll {roll_date} reached (trading date {trading_date}); {pinned_symbol} expires {pinned.expiration_date}"]
        if broker_active is not None and broker_active.broker_symbol == pinned_symbol:
            reasons.append("note: broker still flags the pin as active-month")
        # 0X-B: the production objective is the intended LEAD contract. Past the
        # customary roll the pin is no longer the lead, so production fails
        # closed even though the contract is still tradeable. Never re-pins.
        reasons.append("production policy: the pin is no longer the customary lead contract")
        return _result(root, trading_date, pinned_symbol, RollState.ROLL_DUE, RollSeverity.FAIL, reasons,
                       _roll_action("ROLL REQUIRED BEFORE PRODUCTION CAPTURE -- HUMAN APPROVAL",
                                    pinned_symbol, candidate), **facts)
    if trading_date >= approaching_from:
        reasons = [f"customary roll {roll_date} is {(roll_date - trading_date).days} calendar days away "
                   f"(warning window starts {approaching_from})"] + broker_notes
        return _result(root, trading_date, pinned_symbol, RollState.ROLL_APPROACHING, RollSeverity.WARN, reasons,
                       _roll_action("HUMAN: REVIEW AND PREPARE ROLL", pinned_symbol, candidate), **facts)
    if broker_notes:
        return _result(root, trading_date, pinned_symbol, RollState.METADATA_CONFLICT, RollSeverity.WARN,
                       broker_notes + [f"exchange lifecycle: customary roll {roll_date} not yet reached"],
                       "HUMAN: REVIEW BROKER METADATA (pin remains valid)", **facts)
    return _result(root, trading_date, pinned_symbol, RollState.CURRENT, RollSeverity.OK,
                   [f"customary roll {roll_date}; warning window starts {approaching_from}"], "NONE", **facts)


def _roll_action(prefix: str, pinned_symbol: str, candidate: FuturesContract | None) -> str:
    if candidate is None:
        return f"{prefix} (no tradeable successor found in metadata)"
    return f"{prefix}: {pinned_symbol} -> {candidate.broker_symbol}"


# ---- roll provenance ------------------------------------------------------------


def roll_record_draft(assessment: RollAssessment, futures: list[dict], captured_at: datetime) -> dict:
    """Draft provenance record for a Human-approved roll. Decision fields are
    left for the Human; metadata is an exact snapshot of the two broker rows
    (public instrument metadata only -- never tokens or account data)."""
    if assessment.pinned is None or assessment.candidate is None or assessment.exchange is None:
        raise FuturesContractError("a roll record needs a resolved pin, exchange calendar and successor.")
    rows = {r.get("symbol"): r for r in futures if isinstance(r, dict)}
    old, new = assessment.pinned, assessment.candidate
    return {
        "record_type": "LABORATORY_CONTRACT_ROLL",
        "product": assessment.product,
        "old_contract": {"broker_symbol": old.broker_symbol, "streamer_symbol": old.streamer_symbol,
                         "instrument_id": old.instrument_id, "expiration_date": old.expiration_date.isoformat()},
        "new_contract": {"broker_symbol": new.broker_symbol, "streamer_symbol": new.streamer_symbol,
                         "instrument_id": new.instrument_id, "expiration_date": new.expiration_date.isoformat()},
        "cme_reference": {"customary_roll_date": assessment.exchange.customary_roll_date.isoformat(),
                          "expiration_date": assessment.exchange.expiration_date.isoformat(),
                          "source": assessment.exchange.source, "rule": CME_EQUITY_INDEX_ROLL_RULE},
        "assessment": {"trading_date": assessment.trading_date.isoformat(), "state": assessment.state.value,
                       "severity": assessment.severity.value, "reasons": list(assessment.reasons)},
        "broker_metadata_snapshot": {"captured_at_utc": captured_at.astimezone(timezone.utc).isoformat(), "old": rows.get(old.broker_symbol),
                                     "new": rows.get(new.broker_symbol)},
        "decision": {"approved_by": None, "decided_at_utc": None, "reason": None,
                     "effective_first_trading_date": None, "code_config_commit": None},
    }
