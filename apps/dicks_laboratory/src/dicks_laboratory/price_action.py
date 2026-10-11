"""VWAP band and price-action evidence primitives (0AB-A): PRICE_ACTION_FACTS_V1.

Deterministic, as-of facts that a future Drysdale VWAP curriculum will depend on. No setup, no
breakout / rejection / acceptance / strength label is assigned here: only measurements.

Input: the replay-knowable, session-scoped effective tape at a ReplayCutoff (`replay.as_of_evidence`,
the accepted reconstruction; late prints, corrections and cancels are applied only once known) plus
the accompanying MARKET_STUDY_SNAPSHOT_V1 for static references (prior day, IB, overnight). The
snapshot itself is not changed; this document is separate and hashed (`price_action_sha256`).

Policies (Laboratory policies; the Drysdale guide states no formula, multiplier or ATR):

VWAP_BANDS_V1
    anchor       US_CASH_OPEN (08:30 America/Chicago), the accepted cash VWAP anchor
    population   the accepted cash-VWAP population: session-scoped EFFECTIVE_TAPE trades with
                 event_timestamp >= anchor and < market cutoff (session end 16:00 CT)
    VWAP         sum(v*p) / sum(v)
    variance     volume-weighted population variance about VWAP: sum(v*(p-VWAP)^2) / sum(v)
                 = sum(v*p^2)/sum(v) - VWAP^2   (exact integer arithmetic on scaled prices / sizes)
    sigma        sqrt(variance)
    bands        VWAP +/- k*sigma for k in (1, 2)
    developing   each trade's band state includes that trade (cumulative in event-time order,
                 ties by originating source index); bands change only on trades
    insufficient no trade at or after the anchor: NOT_YET_AVAILABLE; one price only: sigma 0, the bands
                 equal VWAP (zero width is reported); zero volume cannot occur for retained trades
BARS_5M_V1
    half-open [t, t+5m) bars aligned to 5-minute UTC multiples (= Chicago 5-minute marks) over the
    session-scoped tape; a bar with no trade is EMPTY (no OHLC); a bar is COMPLETE once its end <= clock
    (later-received records may still revise it), DEVELOPING while the clock is inside it
ATR_5M_V1
    period 13 (the owner's playbook setting CFG-06; not stated by Drysdale), Wilder smoothing,
    true range = max(H-L, |H-Cprev|, |L-Cprev|) with Cprev the previous non-empty bar's close (first
    bar: H-L), seed = simple mean of the first 13 true ranges, then ATR = (ATR*12 + TR)/13;
    completed non-empty full-session bars of the trading date only (17:00 prior evening to 16:00; no
    prior-session history, empty bars skipped); NOT_YET_AVAILABLE before 13 completed bars
REFERENCE_PATH_V1
    side of a trade vs a level: ABOVE / AT / BELOW (exact); a moving level is evaluated at that trade
    touch  = a trade AT the level or on the far side of it relative to the initial side (the first trade in
             the active window, or for a reference activated later (IB, 09:30) the last trade before it)
    cross  = a change between strict ABOVE and strict BELOW (AT trades neither cross nor reset)
    an excursion episode starts at each cross and ends at the next cross (its return)
    time   = last-observed-price-until-next-trade, over [first trade in the window, clock)
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from enum import StrEnum
from math import isqrt

from dicks_laboratory import market_study_state as mss
from dicks_laboratory.replay import (
    MarketStudySnapshot,
    Maturity,
    PreparedReplay,
    ReplayCutoff,
    as_of_evidence,
    snapshot_sha256,
)
from dicks_laboratory.sessions import AnchorKind, resolve_anchor

SCHEMA = "PRICE_ACTION_FACTS_V1"
HASH_FIELD = "price_action_sha256"
BAND_POLICY = "VWAP_BANDS_V1"
BAR_POLICY = "BARS_5M_V1"
ATR_POLICY = "ATR_5M_V1"
PATH_POLICY = "REFERENCE_PATH_V1"
BAND_MULTIPLIERS = (1, 2)
ATR_PERIOD = 13
BAR = timedelta(minutes=5)
CT_ZONE = "America/Chicago"
_Q = 10 ** 6  # sqrt fixed-point digits for moving-level distances
_POINTS = Decimal("0.000001")


class Side(StrEnum):
    ABOVE = "ABOVE"
    AT = "AT"
    BELOW = "BELOW"


class BandZone(StrEnum):
    ABOVE_UPPER_BAND = "ABOVE_UPPER_BAND"
    AT_UPPER_BAND = "AT_UPPER_BAND"
    BETWEEN_VWAP_AND_UPPER_BAND = "BETWEEN_VWAP_AND_UPPER_BAND"
    AT_VWAP = "AT_VWAP"
    BETWEEN_VWAP_AND_LOWER_BAND = "BETWEEN_VWAP_AND_LOWER_BAND"
    AT_LOWER_BAND = "AT_LOWER_BAND"
    BELOW_LOWER_BAND = "BELOW_LOWER_BAND"


class Direction(StrEnum):
    UP = "UP"
    DOWN = "DOWN"


class BarDirection(StrEnum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


# --- results -----------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Band:
    multiplier: int
    upper: Decimal
    lower: Decimal


@dataclass(frozen=True)
class VwapBandsAsOf:
    policy_id: str
    anchor_utc: datetime
    window_end_utc: datetime
    maturity: Maturity
    included_trade_count: int
    included_volume: Decimal | None
    vwap: Decimal | None  # equals the snapshot's cash VWAP (same population, same arithmetic)
    sigma: Decimal | None
    zero_width: bool | None
    bands: tuple[Band, ...]
    last_price: Decimal | None
    last_price_utc: datetime | None
    last_price_zones: tuple[tuple[int, BandZone], ...]  # (multiplier, zone) at the last known trade


@dataclass(frozen=True)
class BandOccupancy:
    multiplier: int
    window_start_utc: datetime
    observed_from_utc: datetime | None  # first trade in the window
    through_utc: datetime  # the clock (or window end)
    observed: timedelta
    window: timedelta
    seconds: tuple[tuple[BandZone, timedelta], ...]
    outside_above: timedelta
    outside_below: timedelta
    outside_total: timedelta
    fraction_outside_above: Decimal | None  # of observed time
    fraction_outside_below: Decimal | None
    fraction_outside_total: Decimal | None


@dataclass(frozen=True)
class CrossEvent:
    utc: datetime
    direction: Direction
    price: Decimal


@dataclass(frozen=True)
class Episode:
    """From one cross (direction = side now beyond the level) to the next cross (its return)."""

    direction: Direction
    start_utc: datetime
    start_price: Decimal
    first_close_beyond_utc: datetime | None  # end of the first completed 5m bar closing beyond
    bars_closing_beyond: int
    max_consecutive_closes_beyond: int
    max_excursion_points: Decimal
    max_excursion_utc: datetime
    seconds_beyond: timedelta
    volume_beyond: Decimal
    closest_approach_after_peak_points: Decimal | None  # smallest distance beyond after the max excursion
    touched_again_utc: datetime | None  # first later trade AT the level without crossing back
    excursion_after_touch_points: Decimal | None
    returned_utc: datetime | None  # the next cross (back through the level)
    seconds_to_return: timedelta | None
    excursion_after_return_points: Decimal | None  # max distance on the far side until the next cross / clock


@dataclass(frozen=True)
class ReferencePath:
    reference: str
    kind: str  # MOVING / STATIC
    source: str  # where the level comes from
    level_at_clock: Decimal | None
    active_from_utc: datetime
    maturity: Maturity
    initial_side: Side | None
    side_at_clock: Side | None
    first_touch_utc: datetime | None
    first_cross: CrossEvent | None
    last_cross: CrossEvent | None
    cross_count: int
    seconds_since_last_cross: timedelta | None
    seconds_above: timedelta
    seconds_at: timedelta
    seconds_below: timedelta
    first_close_beyond_utc: datetime | None  # first completed bar closing beyond, relative to initial side
    episode_count: int
    first_episode: Episode | None
    latest_episode: Episode | None


@dataclass(frozen=True)
class Bar5m:
    start_utc: datetime
    end_utc: datetime
    maturity: Maturity
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    range: Decimal
    body: Decimal
    upper_wick: Decimal
    lower_wick: Decimal
    direction: BarDirection
    trade_count: int
    volume: Decimal
    higher_high: bool | None  # vs the previous non-empty bar
    lower_high: bool | None
    higher_low: bool | None
    lower_low: bool | None
    inside_bar: bool | None  # high <= prior high and low >= prior low
    outside_bar: bool | None  # high >= prior high and low <= prior low, not identical
    close_above_prior_high: bool | None
    close_below_prior_low: bool | None
    close_vs_vwap: Side | None  # cash VWAP / bands as of the bar's last trade
    close_zones: tuple[tuple[int, BandZone], ...]
    atr_after: Decimal | None  # ATR_5M_V1 through this bar (completed bars only)


@dataclass(frozen=True)
class AtrAsOf:
    policy_id: str
    period: int
    maturity: Maturity
    value: Decimal | None
    through_bar_end_utc: datetime | None
    completed_bars_used: int
    empty_bars_skipped: int
    first_bar_start_utc: datetime | None
    reason: str | None


@dataclass(frozen=True)
class PriceActionFacts:
    schema: str
    dataset_id: object
    trading_date: object
    cutoff: ReplayCutoff
    clock_utc: datetime
    snapshot_sha256: str  # the MARKET_STUDY_SNAPSHOT_V1 these facts accompany (static references)
    policies: tuple[str, ...]
    status: str  # the cash VWAP component status (quality propagation)
    reasons: tuple[str, ...]
    bands: VwapBandsAsOf
    occupancy: tuple[BandOccupancy, ...]
    references: tuple[ReferencePath, ...]
    rth_bars: tuple[Bar5m, ...]  # bars starting at or after 08:30 CT (incl. the developing one)
    atr: AtrAsOf


# --- exact arithmetic --------------------------------------------------------------------------------

def _scale_of(values) -> int:
    e = min((v.as_tuple().exponent for v in values), default=0)
    return 10 ** max(0, -e)


class _Tape:
    """Scaled-integer view of the session tape (prices * ps, sizes * vs)."""

    def __init__(self, trades) -> None:
        self.trades = sorted(trades, key=lambda t: (t.event_timestamp, t.originating_source_index))
        self.ps = _scale_of(t.price for t in self.trades)
        self.vs = _scale_of(t.size for t in self.trades)
        self.P = [int(t.price * self.ps) for t in self.trades]
        self.V = [int(t.size * self.vs) for t in self.trades]

    def dec_price(self, p_int: int) -> Decimal:
        return Decimal(p_int) / Decimal(self.ps)


def _ratio(num: int, den: int) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = 28, ROUND_HALF_EVEN
        return Decimal(num) / Decimal(den)


def _points(num: int, den: int) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = 40, ROUND_HALF_EVEN
        return (Decimal(num) / Decimal(den)).quantize(_POINTS)


def _sqrt(v: Decimal) -> Decimal:
    with localcontext() as c:
        c.prec, c.rounding = 28, ROUND_HALF_EVEN
        return v.sqrt()


def _zone(D: int, var: int, k: int) -> BandZone:
    """Price vs VWAP +/- k*sigma, from D = P*S0 - S1 and var = S2*S0 - S1^2 (both scaled by S0)."""
    if D == 0:
        return BandZone.AT_VWAP
    lhs, rhs = D * D, k * k * var
    if D > 0:
        return (BandZone.ABOVE_UPPER_BAND if lhs > rhs else BandZone.AT_UPPER_BAND if lhs == rhs
                else BandZone.BETWEEN_VWAP_AND_UPPER_BAND)
    return (BandZone.BELOW_LOWER_BAND if lhs > rhs else BandZone.AT_LOWER_BAND if lhs == rhs
            else BandZone.BETWEEN_VWAP_AND_LOWER_BAND)


def _band_side(D: int, var: int, k: int) -> Side:
    """Side of the price vs the band VWAP + k*sigma (k > 0 upper, k < 0 lower, 0 = VWAP)."""
    if k == 0:
        return Side.ABOVE if D > 0 else Side.BELOW if D < 0 else Side.AT
    z = _zone(D, var, abs(k))
    if k > 0:
        return {BandZone.ABOVE_UPPER_BAND: Side.ABOVE, BandZone.AT_UPPER_BAND: Side.AT}.get(
            z, Side.AT if z is BandZone.AT_VWAP and var == 0 else Side.BELOW)
    return {BandZone.BELOW_LOWER_BAND: Side.BELOW, BandZone.AT_LOWER_BAND: Side.AT}.get(
        z, Side.AT if z is BandZone.AT_VWAP and var == 0 else Side.ABOVE)


# --- reference path engine ---------------------------------------------------------------------------

class _Ref:
    """Incremental REFERENCE_PATH_V1 state for one level."""

    def __init__(self, name, kind, source, active_from, static_level=None, k=None) -> None:
        self.name, self.kind, self.source, self.active_from = name, kind, source, active_from
        self.static, self.k = static_level, k  # static: scaled int; moving: band multiplier (+/-, 0 = VWAP)
        self.initial = self.side = self.strict = None
        self.first_touch = self.first_cross = self.last_cross = self.first_close_beyond = None
        self.crosses = 0
        self.secs = {Side.ABOVE: timedelta(0), Side.AT: timedelta(0), Side.BELOW: timedelta(0)}
        self.episodes = 0
        self.first_ep = self.cur = None
        self.prev_ep = None  # the episode before the current one (to record its excursion after return)
        self.last_t = None

    def dist(self, P, D, S0, var, tape) -> tuple[int, int]:
        """Signed distance price - level as (numerator, denominator), in points * ps."""
        if self.kind == "STATIC":
            return P - self.static, 1
        if self.k == 0:
            return D, S0
        sig = isqrt(var * _Q * _Q)  # floor(sqrt(var) * Q)
        return D * _Q - self.k * sig, S0 * _Q

    def side_of(self, P, D, var) -> Side:
        if self.kind == "STATIC":
            return Side.ABOVE if P > self.static else Side.BELOW if P < self.static else Side.AT
        return _band_side(D, var, self.k)


@dataclass
class _Ep:
    direction: Direction
    start: datetime
    start_price: Decimal
    peak: tuple[int, int]
    peak_t: datetime
    approach: tuple[int, int] | None = None
    touch: datetime | None = None
    after_touch: tuple[int, int] | None = None
    first_close: datetime | None = None
    closes: int = 0
    consec: int = 0
    max_consec: int = 0
    secs: timedelta = timedelta(0)
    volume: int = 0
    returned: datetime | None = None
    after_return: tuple[int, int] | None = None


def _gt(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] * b[1] > b[0] * a[1]


def _beyond(d: tuple[int, int], direction: Direction) -> tuple[int, int]:
    return (d[0], d[1]) if direction is Direction.UP else (-d[0], d[1])


# --- builder -----------------------------------------------------------------------------------------

def _bar_start(ts: datetime) -> datetime:
    s = int(ts.timestamp())
    return datetime.fromtimestamp(s - s % 300, tz=timezone.utc)


def build_price_action_facts(prep: PreparedReplay, snapshot: MarketStudySnapshot,
                             trades: tuple | None = None, timings: dict | None = None) -> PriceActionFacts:
    """PRICE_ACTION_FACTS_V1 at the snapshot's cutoff (the as-of tape is recomputed when not supplied).

    `timings`, if given, receives monotonic seconds per phase (diagnostic only; never serialized).
    """
    tick = _Ticker(timings)
    cutoff = snapshot.cutoff
    clock = cutoff.clock
    if trades is None:
        trades = as_of_evidence(prep, cutoff).scoped
    tick("as_of_tape")
    td = prep.trading_date
    anchor = resolve_anchor(AnchorKind.US_CASH_OPEN, td).anchor_timestamp_utc
    window_end = next(m.matures_at_utc for m in snapshot.maturity if m.component == "vwap US_CASH_OPEN")
    through = min(clock, window_end)
    tape = _Tape(trades)
    ps = tape.ps
    tick("sort_and_scale")
    doc = mss.encode(snapshot)

    refs = [_Ref("CASH_VWAP", "MOVING", f"{BAND_POLICY} VWAP", anchor, k=0)]
    for k in BAND_MULTIPLIERS:
        refs += [_Ref(f"VWAP_UPPER_{k}SD", "MOVING", f"{BAND_POLICY} VWAP + {k} sigma", anchor, k=k),
                 _Ref(f"VWAP_LOWER_{k}SD", "MOVING", f"{BAND_POLICY} VWAP - {k} sigma", anchor, k=-k)]
    statics: list[tuple[str, str, Decimal | None, datetime]] = []
    pc = doc["prior_day"]["context"] or {}
    for name, key in (("PRIOR_HIGH", "profile_high"), ("PRIOR_LOW", "profile_low"),
                      ("PRIOR_VALUE_AREA_HIGH", "value_area_high"), ("PRIOR_VALUE_AREA_LOW", "value_area_low"),
                      ("PRIOR_POC", "poc")):
        statics.append((name, f"/prior_day/context/{key}", pc.get(key), anchor))
    on = doc["overnight"]["session"] or {}
    statics += [("OVERNIGHT_HIGH", "/overnight/session/high", on.get("high"), anchor),
                ("OVERNIGHT_LOW", "/overnight/session/low", on.get("low"), anchor)]
    ib_end = anchor + timedelta(hours=1)  # the Initial Balance window [08:30, 09:30) CT
    ib_done = snapshot.tpo.initial_balance_maturity is Maturity.WINDOW_COMPLETE
    ib = (doc["tpo"]["profile"] or {}).get("initial_balance") or {}
    statics += [("IB_HIGH", "/tpo/profile/initial_balance/high", ib.get("high") if ib_done else None, ib_end),
                ("IB_LOW", "/tpo/profile/initial_balance/low", ib.get("low") if ib_done else None, ib_end)]
    unavailable = []
    for name, src, level, active in statics:
        if level is None:
            unavailable.append((name, src, active))
        else:
            refs.append(_Ref(name, "STATIC", src, active, static_level=int(Decimal(level) * ps)))

    # full-session bars (for ATR) and RTH bars (reported)
    bars: dict[datetime, dict] = {}
    S0 = S1 = S2 = 0
    cash_n = 0
    last_cash = None
    zone_secs = {k: {z: timedelta(0) for z in BandZone} for k in BAND_MULTIPLIERS}
    zone_now: dict[int, BandZone] | None = None
    first_cash_t = None
    state_at = {}  # bar start -> (D, var, S0, P) at the bar's last cash trade
    last_P = pre_P = None
    open_bar = None  # the RTH bar whose closes are not yet attributed

    def close_bar(b):
        if b + BAR > clock:
            return
        D_, var_, _, P_ = state_at[b]
        for r in refs:
            if r.side is not None and b + BAR > r.active_from:
                _close(r, r.side_of(P_, D_, var_), b + BAR)

    for i, t in enumerate(tape.trades):
        ts, P, V = t.event_timestamp, tape.P[i], tape.V[i]
        b0 = _bar_start(ts)
        if open_bar is not None and b0 != open_bar:
            close_bar(open_bar)
            open_bar = None
        bar = bars.get(b0)
        if bar is None:
            bar = bars[b0] = {"o": P, "h": P, "l": P, "c": P, "n": 0, "v": 0}
        bar["h"], bar["l"], bar["c"] = max(bar["h"], P), min(bar["l"], P), P
        bar["n"] += 1
        bar["v"] += V
        if ts < anchor:
            continue
        # time accounting for the state that held since the previous cash trade
        if last_cash is not None:
            dt = ts - last_cash
            for k in BAND_MULTIPLIERS:
                zone_secs[k][zone_now[k]] += dt
            for r in refs:
                if r.side is not None:
                    _advance(r, last_cash, ts)
        S0 += V
        S1 += V * P
        S2 += V * P * P
        cash_n += 1
        D, var = P * S0 - S1, S2 * S0 - S1 * S1
        zone_now = {k: _zone(D, var, k) for k in BAND_MULTIPLIERS}
        state_at[b0] = (D, var, S0, P)
        open_bar, last_P = b0, P
        if first_cash_t is None:
            first_cash_t = ts
        price = tape.dec_price(P)
        for r in refs:
            if ts >= r.active_from:
                if r.initial is None and pre_P is not None and r.kind == "STATIC" and r.active_from > anchor:
                    r.initial = r.side_of(pre_P, 0, 0)  # start from the last trade before activation
                    r.strict = r.initial if r.initial is not Side.AT else None
                _observe(r, ts, P, V, D, S0, var, tape, price)
        last_cash, pre_P = ts, P

    if open_bar is not None:
        close_bar(open_bar)
    tick("single_pass_bands_occupancy_paths_bars")
    # close the open interval up to the clock
    if last_cash is not None and through > last_cash:
        dt = through - last_cash
        for k in BAND_MULTIPLIERS:
            zone_secs[k][zone_now[k]] += dt
        for r in refs:
            if r.side is not None:
                _advance(r, last_cash, through)

    # bars, closes beyond, ATR
    ordered = sorted(bars)
    atr_value, atr_n, trs, prev_close, atr_after, empty = None, 0, [], None, {}, 0
    completed = [b for b in ordered if b + BAR <= clock]
    for j, b in enumerate(completed):
        if j and b - completed[j - 1] > BAR:
            empty += (b - completed[j - 1]) // BAR - 1
        h, lo, c = bars[b]["h"], bars[b]["l"], bars[b]["c"]
        tr = h - lo if prev_close is None else max(h - lo, abs(h - prev_close), abs(lo - prev_close))
        prev_close = c
        atr_n += 1
        trd = Decimal(tr) / Decimal(ps)
        with localcontext() as ctx:
            ctx.prec, ctx.rounding = 28, ROUND_HALF_EVEN
            if atr_n < ATR_PERIOD:
                trs.append(trd)
            elif atr_n == ATR_PERIOD:
                trs.append(trd)
                atr_value = sum(trs, Decimal(0)) / ATR_PERIOD
            else:
                atr_value = (atr_value * (ATR_PERIOD - 1) + trd) / ATR_PERIOD
        atr_after[b] = atr_value

    tick("atr")
    rth = []
    prev = None
    for b in ordered:
        if b < anchor:
            prev = bars[b]
            continue
        x = bars[b]
        o, h, lo, c = x["o"], x["h"], x["l"], x["c"]
        st = state_at.get(b)
        dp = tape.dec_price
        rel = (lambda f: None) if prev is None else (lambda f: f(prev))
        rth.append(Bar5m(
            b, b + BAR, Maturity.WINDOW_COMPLETE if b + BAR <= clock else Maturity.DEVELOPING,
            dp(o), dp(h), dp(lo), dp(c), dp(h - lo), dp(abs(c - o)), dp(h - max(o, c)), dp(min(o, c) - lo),
            BarDirection.UP if c > o else BarDirection.DOWN if c < o else BarDirection.FLAT, x["n"],
            Decimal(x["v"]) / Decimal(tape.vs),
            rel(lambda p: h > p["h"]), rel(lambda p: h < p["h"]), rel(lambda p: lo > p["l"]),
            rel(lambda p: lo < p["l"]), rel(lambda p: h <= p["h"] and lo >= p["l"]),
            rel(lambda p: h >= p["h"] and lo <= p["l"] and (h > p["h"] or lo < p["l"])),
            rel(lambda p: c > p["h"]), rel(lambda p: c < p["l"]),
            None if st is None else _band_side(st[0], st[1], 0),
            () if st is None else tuple((k, _zone(st[0], st[1], k)) for k in BAND_MULTIPLIERS),
            atr_after.get(b)))
        prev = x

    # bands at the clock
    cash_maturity = (Maturity.NOT_YET_AVAILABLE if clock <= anchor else
                     Maturity.WINDOW_COMPLETE if clock >= window_end else Maturity.DEVELOPING)
    if S0:
        vwap = _ratio(S1, S0 * ps)
        sigma = _sqrt(_ratio(S2 * S0 - S1 * S1, S0 * S0 * ps * ps))
        with localcontext() as c:
            c.prec, c.rounding = 28, ROUND_HALF_EVEN
            bands = tuple(Band(k, vwap + k * sigma, vwap - k * sigma) for k in BAND_MULTIPLIERS)
        lastP = last_P
        D, var = lastP * S0 - S1, S2 * S0 - S1 * S1
        band_doc = VwapBandsAsOf(BAND_POLICY, anchor, window_end, cash_maturity, cash_n,
                                 Decimal(S0) / Decimal(tape.vs), vwap, sigma, S2 * S0 == S1 * S1, bands,
                                 tape.dec_price(lastP), last_cash,
                                 tuple((k, _zone(D, var, k)) for k in BAND_MULTIPLIERS))
    else:
        band_doc = VwapBandsAsOf(BAND_POLICY, anchor, window_end, cash_maturity, 0, None, None, None, None, (),
                                 None, None, ())

    occ = []
    observed = (through - first_cash_t) if first_cash_t is not None and through > first_cash_t else timedelta(0)
    window = max(through - anchor, timedelta(0))
    for k in BAND_MULTIPLIERS:
        z = zone_secs[k]
        up, down = z[BandZone.ABOVE_UPPER_BAND], z[BandZone.BELOW_LOWER_BAND]

        def frac(x):
            return _ratio(x // timedelta(microseconds=1), observed // timedelta(microseconds=1)) if observed else None

        occ.append(BandOccupancy(k, anchor, first_cash_t, through, observed, window, tuple(z.items()), up, down,
                                 up + down, frac(up), frac(down), frac(up + down)))

    paths = [_finish(r, through, clock, cash_maturity, tape) for r in refs]
    for name, src, active in unavailable:
        paths.append(ReferencePath(name, "STATIC", src, None, active, Maturity.NOT_YET_AVAILABLE if clock < active
                                   else Maturity.NOT_AVAILABLE, None, None, None, None, None, 0, None,
                                   timedelta(0), timedelta(0), timedelta(0), None, 0, None, None))
    paths.sort(key=lambda p: p.reference)

    first_bar = ordered[0] if ordered else None
    atr = AtrAsOf(ATR_POLICY, ATR_PERIOD, Maturity.NOT_YET_AVAILABLE if atr_value is None else
                  Maturity.WINDOW_COMPLETE if clock >= window_end else Maturity.DEVELOPING,
                  atr_value, (completed[-1] + BAR) if completed else None, atr_n, empty, first_bar,
                  None if atr_value is not None else f"{atr_n} of {ATR_PERIOD} completed non-empty bars")
    tick("bar_relations_and_summaries")
    vw = next(v for v in snapshot.vwap if v.anchor_kind is AnchorKind.US_CASH_OPEN)
    return PriceActionFacts(SCHEMA, prep.dataset_id, td, cutoff, clock, snapshot_sha256(snapshot),
                            (BAND_POLICY, BAR_POLICY, ATR_POLICY, PATH_POLICY), vw.status.value,
                            tuple(vw.reasons) + tuple(snapshot.dataset_quality.reasons), band_doc, tuple(occ),
                            tuple(paths), tuple(rth), atr)


class _Ticker:
    def __init__(self, sink: dict | None) -> None:
        import time as _time
        self.sink, self.clock = sink, _time.monotonic
        self.t = self.clock()

    def __call__(self, phase: str) -> None:
        if self.sink is not None:
            now = self.clock()
            self.sink[phase] = self.sink.get(phase, 0.0) + now - self.t
            self.t = now


def _observe(r: _Ref, ts, P, V, D, S0, var, tape, price) -> None:
    side = r.side_of(P, D, var)
    d = None
    if r.initial is None:
        r.initial = side
    if r.first_touch is None and (side is Side.AT or (r.initial is not Side.AT and side is not r.initial)):
        r.first_touch = ts
    ep = r.cur
    if side is not Side.AT and r.strict is not None and side is not r.strict:  # a cross
        direction = Direction.UP if side is Side.ABOVE else Direction.DOWN
        ev = CrossEvent(ts, direction, price)
        r.crosses += 1
        r.first_cross = r.first_cross or ev
        r.last_cross = ev
        if ep is not None:
            ep.returned = ts
            r.prev_ep = ep
        d = r.dist(P, D, S0, var, tape)
        ep = r.cur = _Ep(direction, ts, price, _beyond(d, direction), ts)
        r.episodes += 1
        if r.first_ep is None:
            r.first_ep = ep
    if side is not Side.AT:
        r.strict = side
    if ep is not None:
        d = d or r.dist(P, D, S0, var, tape)
        e = _beyond(d, ep.direction)
        if _gt(e, ep.peak):
            ep.peak, ep.peak_t, ep.approach = e, ts, None
        elif ts > ep.start and (ep.approach is None or _gt(ep.approach, e)):
            ep.approach = e
        if side is Side.AT and ep.touch is None and ts > ep.start:
            ep.touch = ts
        elif ep.touch is not None and ts > ep.touch and e[0] > 0:
            ep.after_touch = e if ep.after_touch is None or _gt(e, ep.after_touch) else ep.after_touch
        beyond = (side is Side.ABOVE) == (ep.direction is Direction.UP) and side is not Side.AT
        if beyond:
            ep.volume += V
        prev = r.prev_ep
        if prev is not None and prev.returned is not None:  # distance moved after the previous return
            back = _beyond(d, prev.direction)
            back = (-back[0], back[1])
            prev.after_return = back if prev.after_return is None or _gt(back, prev.after_return) else \
                prev.after_return
    r.side = side
    r.last_t = ts


def _advance(r: _Ref, start: datetime, end: datetime) -> None:
    dt = end - start
    r.secs[r.side] += dt
    ep = r.cur
    if ep is not None and r.side is not Side.AT and (r.side is Side.ABOVE) == (ep.direction is Direction.UP):
        ep.secs += dt


def _close(r: _Ref, side: Side, bar_end: datetime) -> None:
    if r.initial in (Side.ABOVE, Side.BELOW) and r.first_close_beyond is None and side not in (Side.AT, r.initial):
        r.first_close_beyond = bar_end
    ep = r.cur
    if ep is None or bar_end <= ep.start:
        return
    if side is not Side.AT and (side is Side.ABOVE) == (ep.direction is Direction.UP):
        ep.closes += 1
        ep.consec += 1
        ep.max_consec = max(ep.max_consec, ep.consec)
        ep.first_close = ep.first_close or bar_end
    else:
        ep.consec = 0


def _ep(e: _Ep | None, tape: _Tape) -> Episode | None:
    if e is None:
        return None

    def pts(x):
        return None if x is None else _points(x[0], x[1] * tape.ps)

    return Episode(e.direction, e.start, e.start_price, e.first_close, e.closes, e.max_consec, pts(e.peak), e.peak_t,
                   e.secs, Decimal(e.volume) / Decimal(tape.vs), pts(e.approach),
                   e.touch, pts(e.after_touch), e.returned, (e.returned - e.start) if e.returned else None,
                   pts(e.after_return))


def _finish(r: _Ref, through, clock, maturity, tape) -> ReferencePath:
    level = None
    if r.kind == "STATIC":
        level = tape.dec_price(r.static)
    return ReferencePath(
        r.name, r.kind, r.source, level, r.active_from,
        Maturity.NOT_YET_AVAILABLE if clock <= r.active_from else maturity, r.initial, r.side, r.first_touch,
        r.first_cross, r.last_cross, r.crosses, (through - r.last_cross.utc) if r.last_cross else None,
        r.secs[Side.ABOVE], r.secs[Side.AT], r.secs[Side.BELOW], r.first_close_beyond, r.episodes,
        _ep(r.first_ep, tape), _ep(r.cur, tape))


# --- serialization -----------------------------------------------------------------------------------

def facts_payload(f: PriceActionFacts) -> dict:
    return mss.encode(f)


def price_action_sha256(f: PriceActionFacts) -> str:
    return hashlib.sha256(mss._dumps(facts_payload(f)).encode("ascii")).hexdigest()


def canonical_facts_json(f: PriceActionFacts) -> str:
    payload = facts_payload(f)
    payload[HASH_FIELD] = price_action_sha256(f)
    return mss._dumps(payload)
