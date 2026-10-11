# VWAP and Price-Action Evidence Primitives (0AB-A)

> Deterministic, as-of measurements a future Drysdale VWAP curriculum will
> depend on. **No setup is classified.** Nothing here is called a breakout,
> rejection, acceptance, bounce, backtest, strength or weakness: those remain
> policy decisions. Every fact is replay-knowable at its cutoff.

- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/price_action.py`
  (`PRICE_ACTION_FACTS_V1`); tutor integration in `tutor_evidence.py`.
- **Tests:** `apps/dicks_laboratory/tests/test_price_action.py`.
- **Real-data study:** `DRYSDALE_PRIMITIVES_0ABA.md`, `evidence/0AB-A/`.

## 1. Source audit (what the guide actually says)

The *VWAP Wave Core Setup Guide* (Chris Drysdale; local copy, not
redistributed) was re-read page by page (7 image pages; no text layer).

| Topic | What the guide says | What it does not say |
|---|---|---|
| VWAP value area / deviation bands | "VWAP value area", "VWAP deviation band", "value band", "extreme value band", "the opposite end's value band"; charts (TradingView, ES, 5-minute) show one band pair around the VWAP | no formula (standard deviation, percentage or points), no multiplier, no anchor or session statement, no 68% or other percentage |
| Acceptance | "Must show price 'acceptance,' time or distance outside / inside of value" | no time or distance threshold |
| Backtest / retest | "Entry is on backtest pullback of VWAP deviation band"; "many times they will also retest again" | no distance or timing definition |
| First sign of strength / weakness | "Enter on first sign of strength after backtest"; "first sign of weakness or rejection on test of VWAP deviation band area" | qualitative only: **POLICY NOT YET DEFINED** |
| Rejection, breakout | "breaks out of VWAP value area", "be prepared for a rejection" | no mechanical definition |
| Volatility | "Higher Volatility days are better" | no measure (no ATR, no period) |
| Bar interval | chart screenshots are 5-minute ES charts | no statement that rules use 5-minute bars |

Playbook (`docs/trading_strategies`): CFG-07 (VWAP Wave band formula) is
**deferred**; CFG-06 accepts ATR(13), Wilder, full-session ES 5-minute bars with
no 08:30 reset, with seed, warm-up, gap and history depth still open.

Therefore every policy below is a **Laboratory policy**. None is attributed to
Drysdale.

## 2. Source term vs Laboratory fact vs policy vs deferred interpretation

| Source term (Drysdale) | Laboratory fact (0AB-A) | Laboratory policy | Deferred interpretation |
|---|---|---|---|
| VWAP | cash VWAP (= the accepted snapshot cash VWAP, same population) | US_CASH_SESSION anchor | — |
| deviation band, value band | `/bands`: VWAP ± k·σ for k = 1, 2 | VWAP_BANDS_V1 | which band pair is the guide's "VWAP value area" |
| inside / outside value | band zone of the last trade; time above / between / at / below per k | VWAP_BANDS_V1, REFERENCE_PATH_V1 time convention | "in value", "outside value" |
| breakout | first cross, first close beyond, max excursion, time beyond, return | REFERENCE_PATH_V1 | breakout |
| backtest / retest | touched again, closest approach after peak, excursion after touch, time to touch | REFERENCE_PATH_V1 | successful / failed backtest |
| rejection | touch / cross, max excursion through, time beyond, return, excursion after return | REFERENCE_PATH_V1 | rejection |
| acceptance | time beyond, closes and consecutive closes beyond, volume beyond, cross count | REFERENCE_PATH_V1, BARS_5M_V1 | acceptance (no threshold) |
| first sign of strength / weakness | 5-minute bar facts and relations | BARS_5M_V1 | strength / weakness |
| higher volatility | ATR value and evolution | ATR_5M_V1 | "higher volatility day" |

## 3. VWAP_BANDS_V1

| Item | Definition |
|---|---|
| anchor | US_CASH_OPEN, 08:30 America/Chicago (the accepted cash VWAP anchor) |
| population | the accepted cash-VWAP population: session-scoped EFFECTIVE_TAPE trades (late prints, corrections, cancels applied only once known) with `event_timestamp >= anchor` and `< market cutoff`; the window ends at the cash VWAP session end (16:00 CT) |
| VWAP | Σ v·p / Σ v (identical to the snapshot's cash VWAP; tested and checked on real data) |
| variance | volume-weighted **population** variance about VWAP: Σ v·(p − VWAP)² / Σ v = Σ v·p²/Σ v − VWAP² |
| sigma | √variance (Decimal, 28 significant digits, ROUND_HALF_EVEN) |
| bands | VWAP ± k·σ, k ∈ {1, 2} |
| developing | each trade's state includes that trade (cumulative in event-time order; ties by originating source index); bands change only on trades |
| comparisons | exact: with S0 = Σv, S1 = Σv·p, S2 = Σv·p² on scaled integers, D = p·S0 − S1 and V = S2·S0 − S1²; the price is above VWAP + kσ iff D > 0 and D² > k²·V; AT iff equal. No rounding decides a zone |
| insufficient | no trade at or after the anchor: NOT_YET_AVAILABLE; one price only: σ = 0, bands equal VWAP, `zero_width` true; retained trades never have zero volume |
| maturity | NOT_YET_AVAILABLE before 08:30, DEVELOPING until 16:00, then COMPLETE (never FINAL); status = the cash VWAP component status (quality propagates) |

Band zones of a price: ABOVE_UPPER_BAND, AT_UPPER_BAND,
BETWEEN_VWAP_AND_UPPER_BAND, AT_VWAP, BETWEEN_VWAP_AND_LOWER_BAND,
AT_LOWER_BAND, BELOW_LOWER_BAND (AT_VWAP wins when σ = 0).

**Not a profile value area.** These bands are not the Laboratory's 70%
volume / TPO value area and not the playbook's 68% NinjaTrader profile setting.
Under a normal-distribution assumption about 68% of volume would lie within
±1σ; that is statistical context only, not an equivalence, and nothing in
0AB-A relies on it.

## 4. REFERENCE_PATH_V1: crossings, time, episodes

References: CASH_VWAP, VWAP_UPPER_1SD / LOWER_1SD / UPPER_2SD / LOWER_2SD
(moving), PRIOR_HIGH / LOW, PRIOR_VALUE_AREA_HIGH / LOW, PRIOR_POC,
OVERNIGHT_HIGH / LOW (from 08:30), IB_HIGH / LOW (from 09:30, once the IB is
complete). Missing levels are NOT_YET_AVAILABLE / NOT_AVAILABLE. Opening-range
levels are not defined in the Laboratory and are not invented.

| Fact | Definition |
|---|---|
| side | ABOVE / AT / BELOW of each trade vs the level (a moving level evaluated at that trade) |
| initial side | the first trade in the active window; a reference activated later (IB at 09:30) starts from the last trade before activation |
| touch | first trade AT the level or on the far side relative to the initial side |
| cross | a change between strict ABOVE and strict BELOW; AT trades neither cross nor reset; direction UP / DOWN; first, last, count, time since the last cross |
| time above / at / below | last-observed-price-until-next-trade over [first trade in the window, clock) |
| first close beyond | end of the first completed 5-minute bar whose close is beyond, relative to the initial side |
| episode | from one cross to the next (its return): direction, start, first close beyond, closes beyond, max consecutive closes beyond, max excursion (points) and its time, time beyond, volume beyond, closest approach after the peak (before the return), touched again (a later trade AT the level without crossing back), excursion after that touch, returned (time), time to return, excursion after return (distance on the far side until the next cross or clock) |

The first and the latest episodes are reported, with the episode count. Moving
distances use an integer square root with 10⁻⁶ fixed-point digits; points are
reported to 10⁻⁶.

## 5. BARS_5M_V1

Half-open [t, t + 5 min) bars aligned to 5-minute UTC multiples (the Chicago
5-minute marks) over the session-scoped tape. Per bar: start, end, open, high,
low, close, range, body, upper and lower wick, direction (UP / DOWN / FLAT),
trade count, volume. Relations to the previous non-empty bar (the first RTH bar
compares with the last overnight bar): higher / lower high, higher / lower low,
inside (H ≤ pH and L ≥ pL), outside (H ≥ pH and L ≤ pL, not identical), close
above prior high, close below prior low. Close vs the cash VWAP and the band
zone of the close, both as of the bar's last trade. A bar is COMPLETE once its
end ≤ clock (a later-received record may still revise it), DEVELOPING while the
clock is inside it. Bars from 08:30 are reported; overnight bars feed ATR.

## 6. ATR_5M_V1

| Item | Definition |
|---|---|
| period | 13 (the owner's playbook setting CFG-06; Drysdale names no measure) |
| bars | completed, non-empty BARS_5M_V1 bars of the trading date's full session (17:00 prior evening to 16:00); empty bars skipped and counted |
| true range | max(H − L, \|H − Cprev\|, \|L − Cprev\|), Cprev = previous non-empty bar's close; first bar H − L |
| seed | simple mean of the first 13 true ranges |
| smoothing | Wilder: ATR = (ATR·12 + TR) / 13 (Decimal, 28 digits, ROUND_HALF_EVEN) |
| warm-up | NOT_YET_AVAILABLE before 13 completed bars; no prior-session history (the playbook's loaded-history depth remains open) |

## 7. Replay semantics

Facts are computed from `replay.as_of_evidence` at the snapshot's cutoff: only
records received before the knowledge cutoff and trades before the market
cutoff. A late print enters a completed bar only once known (tested; COMPLETE,
not FINAL). Mutating trades after a cutoff leaves the earlier facts
byte-identical (tested on a fixture and on a copy of 2026-09-29).

## 8. Serialization

`PRICE_ACTION_FACTS_V1` canonical JSON (MARKET_STUDY_STATE_V1 encoding; no
floats, no wall-clock field) with `price_action_sha256`; it records the
`snapshot_sha256` it accompanies and its four policy ids. The accepted
MARKET_STUDY_SNAPSHOT_V1 is unchanged.

## 9. Tutor integration

New source role `PRICE_ACTION` and opt-in evidence domains `VWAP_BANDS`,
`REFERENCE_PATHS`, `PRICE_ACTION_BARS` (the six most recent RTH bars) and
`VOLATILITY`. Lessons that do not request them are byte-identical to before.
Items cite `/bands/…`, `/occupancy/…`, `/references/<i>/…`, `/rth_bars/<i>/…`,
`/atr/…` in the facts document; a non-AVAILABLE status adds the warning
`PRICE_ACTION:price_action`. `TUTOR_SYSTEM_PROMPT_V2`: VWAP_BANDS_V1 bands are
defined facts named by multiplier; the guide's "VWAP value area" / "value band"
and acceptance, rejection, breakout, backtest / retest and first sign of
strength / weakness stay undefined (answer guard). No Drysdale lesson is
enabled.

## 10. Drysdale dependency matrix (after 0AB-A)

| Status | Dependencies |
|---|---|
| FACT_AVAILABLE_NOW | session VWAP; price relative to VWAP; VWAP relation changes; Initial Balance; developing and prior Volume Profile value; developing value migration; replay free of hindsight; **VWAP deviation bands (VWAP_BANDS_V1); VWAP crossing path; time outside the bands; 5-minute price-action facts; ATR (ATR_5M_V1)** |
| NEEDS_POLICY_DEFINITION | **VWAP value area (which band pair)**; breakout; acceptance; backtest / retest; first sign of strength; first sign of weakness; rejection (their measurable dimensions now exist) |
| NEEDS_IMPLEMENTATION | none |

The module stays REGISTERED / NOT_READY_FOR_RULE_IMPLEMENTATION.
