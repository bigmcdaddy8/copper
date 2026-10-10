# Futures Trend Playbook — V1

**Owner:** Mr. Dick Weasel  
**Document revision:** V1-draft-07  
**Created:** 2026-10-03 (America/Chicago)  
**Last revised:** 2026-10-10 (America/Chicago)  
**Status:** Draft for human review; not yet the frozen V1.0 training baseline  
**Intended repository location:** `copper/docs/trading_strategies/FUTURES_TREND_PLAYBOOK_V1.md`

## How to use this document

This document preserves the decisions made in our trading-design discussion. Read the quick reference before practice; use the numbered rules for study and questions. Cite a rule and revision when discussing it: “In V1-draft-07, I have a question about V1-STOP-04.”

Each rule has a status:

- **Agreed:** explicitly accepted in the discussion.
- **Working configuration:** discussed and used as the working baseline, but requires confirmation during document review.
- **Proposed implementation:** a precise implementation offered for review, not an accepted decision.
- **Open:** a definition or choice remains unresolved.

An agreed principle can still have open implementation details. The regime-scoring architecture is agreed; the six factors and thresholds are proposals. Do not treat this draft as fully executable until Section 16's decision register is resolved. Examples illustrate mechanics and do not establish profitability.

The prior `gemini_playbook.md` and `blw_review.md` remain historical inputs. They do not override decisions recorded here. Pyramiding belongs to V2.

## Contents

1. Quick reference
2. Purpose and scope
3. Instrument, platform, and session
4. Chart and context
5. Observation and regime assessment
6. Proposed regime score
7. Trade permission and entry
8. Initial stop and protective orders
9. R and session risk
10. Failed breakouts and reentry
11. Confirmed-pivot trailing
12. Exits
13. Execution quality
14. Forensic record
15. Operating checklists
16. Open decision register
17. Glossary
18. Document management and change log
19. V2 backlog
20. Sources and provenance

## 1. Quick reference

| Item | V1 baseline | Status / reference |
| --- | --- | --- |
| Purpose | Learn trend trading, mechanics, and review using tiny size | Agreed; V1-SCOPE-01 |
| Execution instrument | E-nano S&P 500 futures (NES) | Agreed; V1-INSTRUMENT-01 |
| Learning lot | One NES contract; no adds | Agreed; V1-RISK-01 |
| Platform | NinjaTrader Desktop on Windows 11 (`weasel`) | Agreed; V1-INSTRUMENT-02 |
| Primary chart | 5-minute | Agreed; V1-CONTEXT-01 |
| Analytical instrument | ES for charts, VWAP, and Volume Profile; NES for execution | Agreed; V1-INSTRUMENT-03 |
| Session VWAP | NinjaTrader Order Flow VWAP on ES; tick resolution subject to complete data; session reset; 08:30–15:00 Chicago template | Agreed; V1-CONTEXT-04 |
| Volume Profile | NinjaTrader Order Flow Volume Profile; 68% value area; one ES tick per row; tick resolution subject to availability | Agreed; V1-CONTEXT-05 |
| ATR | ATR(13), Wilder smoothing, full-session ES 5-minute bars; no 08:30 reset; last completed bar at entry | Agreed; V1-CONTEXT-06 |
| Session focus | RTH analytical window 08:30–15:00 Chicago; overnight context only | Agreed; V1-SESSION-01/04 |
| Initial observation | 08:30–08:50 Chicago | Agreed; V1-SESSION-02 |
| Regime architecture | Score from -6 through +6; reassess as auction develops | Agreed architecture; V1-REGIME-01 |
| Regime timing | First assessment 08:50; then after every completed 5-minute bar; intrabar entry uses latest scheduled assessment | Agreed; V1-REGIME-02 |
| Proposed trade permission | +4 to +6 long; -4 to -6 short | Proposed thresholds; V1-REGIME-03 |
| Entry family | Momentum break of meaningful swing/consolidation or auction reference | Agreed; V1-ENTRY-01 |
| Trigger | Penetration; no completed-bar requirement | Agreed; V1-ENTRY-02 |
| Breakout volume | Record afterward; no volume gate | Agreed; V1-ENTRY-03 |
| Initial stop | Structural invalidation; ATR recorded | Agreed; V1-STOP-01 |
| Trailing | Confirmed higher lows / lower highs; 2 NES ticks beyond pivot | Agreed; V1-STOP-04 |
| Profit target | None; no automatic +1R breakeven move | Agreed; V1-STOP-05, V1-EXIT-01 |
| Reentry | Regime must still qualify; maximum two attempts per thesis/reference | Agreed; V1-ENTRY-04 |
| R | Original initial price risk of that trade; denominator remains fixed | Agreed principle; V1-RISK-02 |
| Daily cutoff | Gross realized losing-trade R reaches 3; winners do not replenish it | Agreed; V1-DAILY-01 |
| Overnight holding | Prohibited; exact flatten time remains open | Agreed / open; V1-SESSION-03 |
| Review | Outcome and execution quality scored separately | Agreed; V1-REVIEW-01 |

## 2. Purpose and scope

### V1-SCOPE-01 — Training objective

**Status: Agreed.**

V1 trains auction observation, trend identification, momentum entry, structural risk management, confirmed-pivot trailing, disciplined execution, and forensic review. The initial objective is repetition and learning rather than maximizing dollar P&L.

**Rationale:** A simple position allows attention to remain on the market and execution. Account capital does not determine the learning-lot size.

### V1-SCOPE-02 — Symmetry and trend focus

**Status: Agreed.**

Treat longs and shorts symmetrically. Trade only a qualifying directional imbalance. Balance does not permit a new trend entry. Transition is an observation state, not a trade-permission state.

This playbook does not claim a demonstrated edge. Regime factors, entry definitions, and management rules are hypotheses to assess with recorded evidence.

### V1-SCOPE-03 — V1 boundaries

**Status: Agreed; single-position implementation proposed.**

V1 uses one NES learning lot and excludes pyramiding. Proposed implementation: hold at most one position at a time; fully close it before any fresh attempt. Do not add to either a winning or losing V1 position.

## 3. Instrument, platform, and session

### V1-INSTRUMENT-01 — Contract identity and units

**Status: Agreed instrument; externally verified specifications.**

The training execution instrument is E-nano S&P 500 futures, product code **NES**. `/NES` is discussion shorthand; use NinjaTrader's actual dated contract identifier when placing orders and recording fills.

| NES unit | Value |
| --- | ---: |
| One index point, one contract | $0.50 |
| Minimum tick | 0.5 index points |
| Dollar value of one tick | $0.25 |
| Two-tick structural trailing buffer | 1.0 index point |

These specifications were checked against the CME E-nano FAQ on 2026-10-03 [S1]. A 0.25-point increment from an ES or MES example is not an NES tick. ES analysis with NES execution was accepted on 2026-10-10. Exact expiry selection, rollover, and cross-instrument level handling remain open (OD-04 and OD-07).

### V1-INSTRUMENT-02 — Execution platform

**Status: Agreed.**

Use NinjaTrader Desktop on the Windows 11 computer `weasel`. Record whether each practice session uses simulation, replay, or live execution. Specific order-entry and protective-order procedures remain open (OD-07).

### V1-SESSION-01 — Primary session and time convention

**Status: Agreed.**

Concentrate on the RTH auction during the analytical window **08:30–15:00 America/Chicago**. Overnight high, low, and profile are context references. This playbook does not authorize overnight-session entries.

Use Chicago local time for the human-facing journal and examples, with the date and timezone identified. Proposed research convention: retain timezone-aware UTC timestamps as well, so Dick's Laboratory can reconstruct events consistently.

### V1-SESSION-02 — Initial observation window

**Status: Agreed; 5-minute chart confirmed on 2026-10-10.**

Observe from 08:30 until 08:50 Chicago. Do not enter during these first 20 minutes. With the agreed 5-minute chart, the four bars starting at 08:30, 08:35, 08:40, and 08:45 constitute the initial observation panel. Entries may become eligible beginning at 08:50 if the other conditions qualify.

Call this the **initial observation range**, not the standard Initial Balance. Standard IB analysis may be added later.

### V1-SESSION-03 — No overnight positions

**Status: Agreed prohibition; exact cutoff open.**

Close all positions and remove outstanding entry orders before the chosen end-of-session cutoff. Do not carry a V1 position overnight. The exact latest-entry time, flatten time, and holiday/early-close handling must be decided under OD-01. Do not infer the cutoff from the earlier draft's Eastern-time wording.

### V1-SESSION-04 — Analytical sessions and calendar policy

**Status: Agreed on 2026-10-10.**

| Reference | Accepted definition (America/Chicago) |
| --- | --- |
| Current RTH analytical session | 08:30–15:00 |
| Prior-day high/low and Volume Profile | Most recent completed RTH session |
| Overnight high/low and contextual profile | 17:00 on the preceding calendar day through 08:30; Sunday evening for Monday |
| Holidays and shortened cash sessions | Observe/review only during initial V1 training; no V1 training entries |

The prior-session reference is the most recent completed session, not necessarily the preceding calendar date. Keep prior-session, overnight, and developing current-RTH profile observations distinct.

The analytical window follows the normal US cash-equity session [S2]. It does not set the latest entry or mandatory flatten times. Those remain open under OD-01. Calendar exceptions require identifying the applicable US cash-session schedule and verifying futures/platform availability; the accepted no-entry policy does not imply that all markets share the same holiday hours.

**Proposed implementation detail, not yet accepted:** represent data windows as half-open intervals, including the start and excluding the endpoint, to avoid double counting observations exactly at 08:30. Final timestamp/bin-boundary handling and treatment of incomplete or shortened prior-session data still need a reproducible calculation policy.

### V1-INSTRUMENT-03 — ES analysis with NES execution

**Status: Agreed on 2026-10-10; implementation details open.**

Use ES for the analytical chart, session VWAP, and Volume Profile. Execute the one-contract learning lot in NES. Journal both instruments with their actual dated contract identifiers, and distinguish ES analytical observations from NES fills and protective-order prices.

Acceptance of this configuration does not establish an automatic price mapping between instruments. Exact expiries, roll alignment, NES trigger/stop validation, and level conversion/rounding remain open under OD-04 and OD-07. An ES reference must not be silently treated as an executable NES order price. Record any cross-instrument discrepancy when evaluating entry, invalidation, and execution.

## 4. Chart and context

### V1-CONTEXT-01 — Primary decision chart

**Status: Agreed on 2026-10-10.**

Use a 5-minute ES primary decision chart. This produces four completed bars in the 20-minute observation panel. NES remains the execution instrument. OD-16 is closed.

### V1-CONTEXT-02 — Required contextual references

**Status: Agreed.**

Display or make readily available:

| Prior RTH session | Overnight | Current RTH session |
| --- | --- | --- |
| VAH, VAL, VPOC | High and low | Session VWAP |
| High and low | Profile for context | Developing VAH, VAL, VPOC |

Price structure remains part of the assessment. Use Volume Profile rather than TPO in V1. Layout can reduce clutter without removing the references needed for a decision.

### V1-CONTEXT-03 — VWAP, profile, and ATR roles

**Status: Agreed roles; calculation settings open.**

VWAP provides auction location and context; crossing it alone is not an entry signal. Volume Profile informs location, acceptance, and value migration. Raw breakout volume does not gate entry. ATR is descriptive evidence, not the mechanical initial-stop or trailing-stop algorithm.

The analytical source is ES and the session VWAP anchor is the 08:30 RTH open, both accepted on 2026-10-10. Analytical RTH, prior-session, and overnight windows and the holiday/shortened-session no-entry policy were accepted on 2026-10-10 (V1-SESSION-04). NinjaTrader Order Flow Volume Profile with 68% value area, one ES tick per row, tick-resolution data subject to availability, and ATR(13) settings were accepted on 2026-10-10 (V1-CONTEXT-05/06). Exact contract selection, timestamp boundary/data-completeness handling, profile calculation reproducibility, VWAP template/data/reproducibility verification, and ATR seed/warm-up policy remain open under OD-04 and OD-05.

### V1-CONTEXT-04 — RTH session VWAP anchor and implementation

**Status: Agreed on 2026-10-10; operational verification details open.**

Anchor the ES session VWAP at **08:30 America/Chicago**, resetting at each RTH session open. Overnight information remains separate context; overnight volume is not included in this RTH-anchored VWAP.

The following implementation was explicitly accepted on 2026-10-10:

| Setting | Accepted implementation |
| --- | --- |
| Indicator | NinjaTrader Order Flow VWAP |
| Analytical instrument | ES |
| Resolution | Tick, subject to complete data availability |
| Reset interval | Session |
| Trading-hours template | Explicitly match 08:30–15:00 America/Chicago |

NinjaTrader documents tick-resolution calculation, session resets, and a selectable trading-hours template [S5]. Verify the template's actual opening/closing hours, timezone, and applicable calendar rules rather than assuming its name matches the accepted window. Ensure the underlying data series contains the session data required by the indicator.

Use the named timezone rather than a fixed UTC offset. The analytical session endpoint and holiday/shortened-session no-entry policy are defined in V1-SESSION-04. Record the actual NinjaTrader build, indicator settings, trading-hours template, and data source. ATR retains its separate full-session input policy.

Exact timestamp inclusion, session-data completeness checks, behavior when tick history is unavailable, operational template verification, and numerical parity with a future Laboratory calculation remain open under OD-04/05. Do not silently substitute standard/bar resolution for the accepted tick-resolution implementation. This choice does not define the future VWAP Wave deviation-band formula, multipliers, or display settings; no VWAP-band entry rule is added to V1.

### V1-CONTEXT-05 — Volume Profile implementation and settings

**Status: Agreed on 2026-10-10; reproducibility and data availability details open.**

Use **NinjaTrader Order Flow Volume Profile** on ES with:

| Setting | Accepted choice |
| --- | --- |
| Profile type | Traded volume; not trade count or TPO |
| Value area | 68% |
| Price-row aggregation | One ES tick per row |
| Data resolution | Tick data, subject to availability |
| Session windows | Prior, overnight, and current RTH windows in V1-SESSION-04 |

Use these settings consistently for the contextual profiles. Preserve separate prior-session, overnight, and developing RTH profiles. The owner's traditional 68% setting supersedes the earlier unaccepted 70% proposal.

Tick **resolution** describes the source data; traded-volume **profile type** describes what is accumulated. These are distinct settings. Do not select trade-count “Tick Profile” merely because tick-resolution data is being used. NinjaTrader documents both distinctions [S3].

Record the actual indicator/build, data source, settings, and session template used. Do not assume a future Laboratory profile will match NinjaTrader merely because both use 68% and the same row size: value-area construction and POC tie handling must be verified or explicitly kept as separate policies. The VWAP Wave deviation-band region remains a different concept from this Volume Profile value area.

Tick-history availability, incomplete-profile handling, exact algorithm/tie behavior, and any fallback from tick to minute resolution remain open under OD-05. A minute-resolution fallback is not automatically authorized; it would change the underlying profile approximation and must be recorded and decided explicitly.

### V1-CONTEXT-06 — ATR observation settings

**Status: Agreed on 2026-10-10; seed/warm-up details open.**

Use **13-period ATR with Wilder smoothing on full-session ES 5-minute bars**, including overnight bars. **Do not reset the ATR at 08:30.** Continue the calculation across the RTH open using the full futures-session input history. This ATR input policy is separate from the RTH-only VWAP and analytical profile windows. At entry, record the value from the **most recently completed bar**, rather than the still-forming bar. Record the ATR in index points and the initial stop distance in ATR units, identifying the source instruments when comparing an NES stop distance with ES volatility.

ATR remains descriptive evidence. It does not place the initial stop, trigger an entry, or determine trailing in V1. The owner's traditional 13-period setting supersedes the earlier unaccepted 14-period proposal. NinjaTrader's built-in ATR documents Wilder smoothing [S4].

Do not restart the ATR history at 08:30 and silently treat the four bars available at 08:50 as a fully initialized 13-period calculation. Full-session input history and continuity across the RTH open are now accepted. Exact full-session trading-hours template, maintenance/holiday gap handling, seeding, loaded-history depth, and warm-up criteria remain open under OD-05. Do not infer synthetic bars or zero-range observations during exchange closures from the phrase “full session.”

## 5. Observation and regime assessment

### V1-REGIME-01 — Scored, dynamic classification

**Status: Agreed architecture.**

Use a scored framework ranging from **-6 to +6** to organize evidence and determine directional trade permission. The score does not place an order by itself. Reassess the regime as the auction develops; the 08:50 assessment is not a permanent label for the day.

The evidence families are auction location, value behavior, and price behavior. Section 6 proposes their implementation.

### V1-REGIME-02 — Assessment timing and contemporaneous evidence

**Status: Agreed on 2026-10-10; OD-03 closed.**

| Situation | Accepted timing policy |
| --- | --- |
| First assessment | 08:50 America/Chicago, using the first four completed RTH bars |
| Subsequent assessments | After every completed 5-minute bar |
| Intrabar breakout entry | Use the latest completed-bar regime assessment |
| Assessment freshness | Before entry, confirm the latest scheduled assessment was completed and permits the intended direction |
| Missing required evidence | Mark the assessment UNKNOWN; no new entry |

For example, a breakout at 09:12 uses the 09:10 assessment; the next scheduled assessment is 09:15. At or after a new scheduled assessment time, an older score is no longer the latest scheduled assessment: complete the new assessment before permitting an entry. Check freshness and permission before every entry or reentry; this check does not itself create an intrabar rescore.

Record the score, its assessment timestamp, and the six components available at that time. Entry may occur intrabar while regime scoring follows this completed-bar cadence. Preserve the original entry-time evidence; do not retrospectively replace it with a later assessment.

The six component definitions and directional thresholds remain open under OD-02. The timing policy does not make an incomplete classifier executable. Missing data is not neutral evidence. The open-position response to a later regime change remains a separate OD-14 decision.

## 6. Proposed regime score

### V1-REGIME-03 — Six-factor proposal and thresholds

**Status: Proposed implementation, not frozen.**

Each factor contributes -1, 0, or +1. Sum all six. The table describes the intended observations; terms such as “accepted,” “recent,” and “holding” need measurable definitions before use as an executable classifier.

| Factor | -1: bearish evidence | 0: neutral evidence | +1: bullish evidence |
| --- | --- | --- | --- |
| Relative to prior value | Accepted below prior VAL | Inside value / unclear acceptance | Accepted above prior VAH |
| VWAP relationship and slope | Below falling VWAP | Mixed relationship / flat slope | Above rising VWAP |
| Developing value migration | VPOC/value migrating lower | Stationary or overlapping | VPOC/value migrating higher |
| Swing structure | Lower highs and lower lows | Mixed / no established sequence | Higher highs and higher lows |
| Range extension | Downside extension holding | No sustained extension | Upside extension holding |
| Acceptance / rejection | Downside breaks accepted; upside attempts rejected | Mixed / insufficient evidence | Upside breaks accepted; downside attempts rejected |

| Proposed score | Classification | New entry permission |
| ---: | --- | --- |
| +4 to +6 | IMBALANCE UP | Long only |
| +2 to +3 | TRANSITION UP | None |
| -1 to +1 | BALANCE | None |
| -2 to -3 | TRANSITION DOWN | None |
| -4 to -6 | IMBALANCE DOWN | Short only |

**Rationale:** Scoring makes observations reviewable while preserving a separate entry decision. These factors are correlated; four points are not four independent proofs. A score near zero can also reflect conflicting directional evidence, so retain the component scores rather than treating every zero as the same auction.

**Open definitions (OD-02):** final factors and thresholds; lookback windows; acceptance duration; VWAP separation and slope tolerance; migration magnitude; pivot identification; range-extension reference; and which observations are required for each component. The accepted V1-REGIME-02 policy marks an assessment UNKNOWN and prohibits new entries when required evidence is missing. Do not silently treat unavailable data as neutral evidence.

## 7. Trade permission and entry

### V1-ENTRY-01 — Eligible breakout family

**Status: Agreed.**

An entry may break either:

1. A meaningful recent swing or consolidation high/low; or
2. A meaningful auction reference, such as prior VAH/VAL, prior-session high/low, or overnight high/low.

The direction must agree with the permitted regime. A random bar high/low is not automatically an eligible level. Breaking the initial observation range alone is not sufficient; it must qualify within the accepted entry family. Define “meaningful,” swing selection, and consolidation selection under OD-06.

### V1-ENTRY-02 — Penetration trigger

**Status: Agreed principle; exact trigger/order mechanics open.**

Enter on penetration of the eligible level; do not require a completed 5-minute bar. For a long, penetration is above the selected level; for a short, below it. A touch is not penetration.

Identify the level and initial structural invalidation before entry. Define trigger price source, tick rounding, any entry buffer, order type, and treatment of an already-broken level under OD-07. The two-tick trailing buffer is not an agreed entry buffer.

### V1-ENTRY-03 — Breakout volume

**Status: Agreed.**

Do not require a raw-volume confirmation for V1 entry. Record available breakout volume afterward for research, identifying its measurement window and whether a bar was incomplete at entry. Profile evidence still belongs in the contextual assessment.

### V1-ENTRY-04 — Reentry permission

**Status: Agreed.**

A failed attempt may be followed by another attempt if the current regime still qualifies and the session loss budget permits it. Maximum **two total attempts**, including the original entry, against the same breakout thesis/reference. See V1-REENTRY-01 for the unresolved grouping details.

## 8. Initial stop and protective orders

### V1-STOP-01 — Structural initial invalidation

**Status: Agreed.**

For a long breakout, place the initial stop beyond the meaningful pre-breakout swing low or consolidation low that invalidates the thesis. For a short, mirror this above the relevant swing or consolidation high.

Structure determines stop location. Do not move the stop closer merely to fit a preferred dollar risk. Record ATR and stop distance in ATR units for later analysis.

### V1-STOP-02 — Initial buffer and order protection

**Status: Open buffer; proposed protection procedure.**

The agreed **two-tick buffer applies to confirmed-pivot trailing**. Applying the same buffer to the initial structural stop is a proposal, not an explicit prior agreement (OD-08).

Proposed procedure: arrange the protective stop as part of the entry workflow; immediately verify its accepted status after a fill. The exact NinjaTrader procedure, partial-fill behavior, rejected-order response, and connection-loss handling must be documented under OD-07. A stop trigger is not a guarantee of a particular fill price.

### V1-STOP-03 — Stop discipline

**Status: Proposed explicit guardrail consistent with structural risk.**

Never widen a protective stop to increase risk after entry. A long stop may remain unchanged or move higher; a short stop may remain unchanged or move lower. If a candidate structural stop would loosen the existing stop, keep the existing stop.

## 9. R and session risk

### V1-RISK-01 — One learning lot

**Status: Agreed.**

Each V1 entry uses **one NES contract**. Do not optimize quantity against the approximately $50,000 capital context. A wider structural stop changes that trade's dollar risk, not its V1 quantity. A maximum acceptable stop distance/dollar risk has not yet been specified (OD-09).

### V1-RISK-02 — Fixed original denominator

**Status: Agreed principle; price-risk convention made explicit.**

Let `E` be the actual entry fill, `S0` the original protective-stop trigger, and `Q = 1` contract:

`Initial risk dollars (R0) = abs(E - S0) × $0.50 × Q`

`Gross realized trade R = gross realized trade P&L / R0`

Keep `R0` fixed throughout the trade. Moving the stop does not reset the denominator. Calculate planned risk before entry and preserve it separately from risk calculated from the actual fill. Initial dollar risk here is price risk; fees and slippage accounting require OD-10.

| Example | Entry | Initial stop | Distance | R0 |
| --- | ---: | ---: | ---: | ---: |
| Long A | 6000.0 | 5995.0 | 5 points | $2.50 |
| Long B | 6000.0 | 5986.0 | 14 points | $7.00 |
| Short C | 6000.0 | 6009.0 | 9 points | $4.50 |

For Long A, a $7.50 gross profit is +3R. It does not imply a +3R profit-target order. A stop filled at its original trigger produces -1R before costs; an adverse fill can lose more than 1R.

### V1-DAILY-01 — Gross realized loss budget

**Status: Agreed cutoff; cost basis open.**

For each completed trade, let `r_i` be its realized R under the selected accounting convention:

`Loss-R used = sum(max(0, -r_i))`

Stop taking new trades when **Loss-R used >= 3.00**. Equivalently, the signed sum of negative trade Rs is **<= -3.00**. The cutoff is reached at three, not only after exceeding three. Winners do not restore this budget. Partial losses consume their actual R; this is not simply a count of three stopouts.

| Completed sequence | Net R | Loss-R used | New entries? |
| --- | ---: | ---: | --- |
| +4, -1, -1 | +2 | 2 | Potentially, subject to all other rules |
| +4, -1, -1, -1 | +1 | 3 | No |
| -0.5, -0.75, -1, -0.75 | -3 | 3 | No |
| -1.2, -1, -0.8 | -3 | 3 | No |

**Proposed remaining-budget guard:** before entry, require enough remaining Loss-R budget for the planned full 1R price loss. For example, 2.6 Loss-R already used leaves 0.4; skip a fresh full-risk attempt. This prevents deliberately initiating a trade whose normal stop would cross the threshold, but fills/costs can still cause an overshoot. Confirm under OD-11.

Because each trade has its own R0, summed trade R is a normalized training measure, not a fixed-dollar session-loss limit.

### V1-DAILY-02 — Session metrics

**Status: Agreed tracking concept; formulas proposed.**

Track net realized R, gross Loss-R used, peak cumulative realized R, current drawdown from that peak, trade count, and full-stopout count.

`Cumulative R = sum(r_i)`  
`Peak R = max(0, all completed-trade cumulative R values)`  
`Current realized drawdown R = Peak R - current cumulative R`

Keep realized session drawdown distinct from intratrade unrealized drawdown. Peak or drawdown metrics are descriptive in V1; no additional cutoff has been agreed for them.

## 10. Failed breakouts and reentry

### V1-REENTRY-01 — Two attempts at one thesis

**Status: Agreed cap; thesis identity open.**

Assign a thesis/reference ID before the first attempt. The first fill is attempt 1; a qualifying reentry is attempt 2. Do not make attempt 3 against the same thesis/reference.

A stopout means that attempt failed; it does not automatically invalidate the directional session thesis. Reassess the regime and identify fresh valid entry/stop structure before reentry. An unchanged bullish opinion is not sufficient by itself.

OD-12 must define when adjacent levels represent the same thesis, whether the cap resets during the session, and how an unfilled or cancelled entry counts. Proposed policy: count filled attempts, retain the same ID through minor level relabeling, and do not reset its cap during the session.

## 11. Confirmed-pivot trailing

### V1-STOP-04 — Confirmation and two-tick trail

**Status: Agreed core rule; precise pivot-selection details open.**

For a **long**:

1. Keep the initial stop while price develops an impulse and pullback.
2. Identify the preceding swing high and the candidate higher low.
3. The higher low becomes confirmed when price subsequently penetrates the preceding swing high.
4. Move the protective stop to **two NES ticks below** that confirmed higher low.
5. Repeat for later confirmed higher lows, subject to the stop never being loosened.

For a **short**, mirror the sequence: a candidate lower high becomes confirmed when price penetrates the preceding swing low; trail **two NES ticks above** that lower high.

A two-tick NES buffer is **1.0 index point**. Confirmation requires continuation beyond the reference, not merely a touch. Pivot comparison, candidate tracking, and intrabar ambiguity remain OD-13.

**Long example:**

| Event | Price / action |
| --- | --- |
| Entry | 6000.0 |
| Original stop | 5994.0; R0 = $3.00 |
| Rally establishes swing high A | 6010.0 |
| Pullback establishes candidate higher low | 6005.0 |
| Continuation penetrates A | 6010.5 |
| Candidate becomes confirmed | Higher low at 6005.0 |
| New stop trigger | 6004.0 |

The trigger is four points above entry; an actual exit fill at 6004.0 would yield $2.00 gross, or approximately +0.67R. This is an intended trigger outcome, not a guaranteed profit.

**Short example:** entry 6000.0, original stop 6006.0, swing low 5990.0, candidate lower high 5995.0. Price subsequently trades at 5989.5: trail to 5996.0, two NES ticks above the confirmed lower high.

### V1-STOP-05 — Structure rather than a P&L milestone

**Status: Agreed.**

Do not move the stop solely because price reaches +1R, breakeven, or another arbitrary profit level. Do not use fixed-R or mechanical ATR trailing in V1. A confirmed structural pivot can justify a stop still below entry for a long, or above entry for a short; the confirmation does not have to lock in profit.

**Rationale:** The market must create the structural reason to tighten the stop. A normal pullback can occur after a +1R excursion.

## 12. Exits

### V1-EXIT-01 — No fixed profit target

**Status: Agreed.**

Do not place a fixed take-profit order, including at +3R. Let realized R emerge from structural stop management and the required session exit.

### V1-EXIT-02 — Normal and session exits

**Status: Agreed stop-management approach and no-overnight requirement.**

The normal exit is execution of the protective initial or trailed stop. Close any remaining position at the agreed session flatten cutoff. Record actual fills, not only stop triggers.

### V1-EXIT-03 — Regime changes and manual intervention

**Status: Open.**

Loss of directional trade permission blocks new entries. It has not yet been agreed whether an open position must be flattened immediately on a regime change, held under its structural stop, or exited under a separate persistence rule (OD-14).

Likewise, no “climax,” “exhaustion,” or discretionary balance exit from the historical drafts is automatically adopted. Define authorized manual and operational emergency exits before freezing V1.0, and record every intervention and reason.

## 13. Execution quality

### V1-REVIEW-01 — Separate process from outcome

**Status: Agreed.**

Assess trade outcome and execution quality independently. A rule-compliant loss can receive a high execution grade. A profitable rule violation can receive a low grade. Profit is not evidence that the decision process was correct.

### V1-REVIEW-02 — Proposed execution rubric

**Status: Proposed implementation.**

Score each item 0, 1, or 2: 0 = not followed, 1 = partly followed or evidence incomplete, 2 = followed and evidenced.

| Item | Evidence |
| --- | --- |
| Context and permission | Observation complete; recorded qualifying regime |
| Entry and thesis | Eligible preidentified reference; trigger and attempt cap respected |
| Initial protection | Correct lot, structural invalidation, accepted protective stop |
| Management and exit | Confirmed-pivot trail, no widening, required exits followed |
| Session discipline and review | Loss cutoff honored; honest, complete record |

Total: 0–10. Record individual rule violations separately; a serious violation must not disappear inside an average. Define final grading and treatment of missing evidence under OD-15. Keep post-trade analysis separate from the information available before entry.

## 14. Forensic record

### V1-REVIEW-03 — Minimum record for every filled attempt

**Status: Agreed capture intent; field schema proposed.**

| Group | Fields |
| --- | --- |
| Identity | Trade ID, thesis ID, attempt number, date, playbook revision, simulation/replay/live, actual instrument/expiry, direction, quantity |
| Timing | Entry and exit timestamps; Chicago display time and timezone; UTC for research |
| Pre-trade regime | Six component observations/scores, total score, classification, assessment timestamp, unknown/missing inputs |
| Context snapshot | Prior VAH/VAL/VPOC and high/low; overnight high/low; VWAP; developing VAH/VAL/VPOC; profile/chart source and settings |
| Entry thesis | Breakout type, level, planned trigger, actual fill, location relative to prior value, distance from VWAP, contemporaneous notes |
| Initial risk | Invalidation pivot, buffer, initial stop trigger, planned and actual stop distance, R0, ATR value/settings, stop distance in ATR units |
| Order handling | Entry/stop order identifiers if available, accepted statuses, delays/rejections, fills/slippage, stop-modification history |
| Outcome | Exit fill/time/reason, gross P&L, costs, net P&L, gross and net R, MAE, MFE, peak unrealized R, profit surrendered from peak |
| Process | Execution score/components, rule violations, manual interventions, protection and trailing compliance |
| Follow-up | Breakout failure/acceptance, subsequent regime, price behavior 15/30/60 minutes after exit, observations and hypotheses |
| Visual evidence | Pre-entry chart when feasible, entry chart, exit chart, marked-up post-trade chart |

Capture raw breakout volume without making it a gate. Record unavailable fields as missing, not invented values. Automating this record in Dick's Laboratory is a future capability; it is not a prerequisite to writing the playbook.

### V1-REVIEW-04 — Excursion and hindsight conventions

**Status: Proposed implementation.**

Measure MAE and MFE between actual entry and exit using direction-adjusted price movement; store points and R using the original R0. Identify whether the measurements use ticks or bar data. A bar-only record may not establish event order or exact fill opportunity.

Define peak profit surrender as `peak gross unrealized R - final gross realized R`, using consistent units. Keep costs separately. If assessing whether a pullback entry “would have worked,” specify an alternative entry/stop/exit rule and label it counterfactual research rather than a fact about an executable fill.

## 15. Operating checklists

These checklists summarize the rules; they do not override rule status or resolve an open decision.

### Before the session

- [ ] Confirm document revision and session mode.
- [ ] Confirm execution contract, chart/profile source, settings, and Chicago date/time.
- [ ] Confirm the session calendar, latest-entry time, and flatten time.
- [ ] Load prior-session and overnight context.
- [ ] Confirm order-protection procedure and begin session counters at zero.

### Before each entry

- [ ] Initial 20-minute observation period is complete.
- [ ] Latest scheduled completed-bar regime assessment is complete, not UNKNOWN, permits the intended direction, and has recorded score/components/timestamp.
- [ ] Meaningful breakout reference and thesis ID are identified before the trigger.
- [ ] Attempt count is below two and loss budget permits the trade.
- [ ] Initial structural invalidation, stop, R0, and ATR are recorded.
- [ ] Quantity is one NES; order protection is ready.
- [ ] Entry occurs on valid penetration under the agreed execution procedure.

### During the position

- [ ] Verify protective stop acceptance.
- [ ] Track candidate pivots and confirmation references.
- [ ] Trail only on confirmed structure, using two NES ticks beyond the pivot.
- [ ] Do not loosen the stop, add size, or install a fixed profit target.
- [ ] Follow the finalized regime-change/operational-exit policy and session cutoff.

### After exit / end of session

- [ ] Reconcile actual fills and record outcome separately from execution grade.
- [ ] Update Loss-R used, net R, peak/drawdown, and attempt counters.
- [ ] At Loss-R used >= 3, end new trading for the session.
- [ ] Capture screenshots and post-trade observations.
- [ ] Finish the session flat and remove outstanding entry orders.

## 16. Open decision register

Resolve the remaining open items explicitly before freezing V1.0. OD-03 and OD-16 are closed; OD-04 and OD-05 have accepted subdecisions but remain open. A later answer should cite the OD ID and any affected rule IDs.

| ID | Decision needed | Affected rules |
| --- | --- | --- |
| OD-01 | RTH analytical window and holiday/shortened-session no-entry policy accepted; latest entry, flatten deadline, and operational calendar procedure remain open | SESSION-03, EXIT-02 |
| OD-02 | Final six score factors, thresholds, measurable lookbacks/tolerances, and required evidence per factor; UNKNOWN/no-entry policy accepted | REGIME-01, REGIME-03 |
| OD-03 | CLOSED 2026-10-10: assess first at 08:50 and every completed 5-minute bar; use latest scheduled assessment for intrabar entries; missing required evidence means UNKNOWN/no entry | REGIME-02 |
| OD-04 | ES analysis / NES execution and prior/overnight/RTH windows accepted; exact expiries, rollover alignment, cross-instrument level handling, and timestamp boundary/data-completeness policies remain open | INSTRUMENT-01, CONTEXT-02/03 |
| OD-05 | VWAP anchor, NinjaTrader Volume Profile (68%, one ES tick/row, tick resolution subject to availability), and ATR(13) Wilder on completed full-session ES 5-minute bars with no 08:30 reset accepted; Order Flow VWAP tick/session implementation and 08:30–15:00 template accepted; VWAP operational template/data/parity verification, profile reproducibility/data policy, and ATR template/gap/seed/warm-up remain open | CONTEXT-03/04/05/06 |
| OD-06 | Meaningful swing/consolidation definition and reference selection | ENTRY-01 |
| OD-07 | Trigger price source, rounding/buffer, order type, protective workflow, fills/rejections/disconnection response | ENTRY-02, STOP-02 |
| OD-08 | Initial structural-stop buffer; whether to use two NES ticks here too | STOP-01/02 |
| OD-09 | Maximum initial stop distance/dollar risk; handling excessive width | RISK-01 |
| OD-10 | Gross versus net realized R for daily cutoff; fee and slippage treatment | RISK-02, DAILY-01 |
| OD-11 | Remaining-budget guard and one-position-at-a-time rule | DAILY-01, SCOPE-03 |
| OD-12 | Thesis identity/reset and attempt-count treatment for unfilled/cancelled orders | REENTRY-01 |
| OD-13 | Pivot selection/comparison, tracking changing candidates, same-bar event ambiguity, stop-modification timing | STOP-04 |
| OD-14 | Open-position treatment after regime change; authorized manual/emergency exits | EXIT-03 |
| OD-15 | Final execution rubric and practical minimum forensic fields | REVIEW-02/03 |
| OD-16 | CLOSED 2026-10-10: primary 5-minute ES chart accepted | CONTEXT-01 |

**Study priority:** first define the score and its timing; then swings/pivots and order mechanics; then session boundaries and accounting. These are gaps to close, not invitations to add V2 complexity.

## 17. Glossary

| Term | Meaning in this document |
| --- | --- |
| RTH | Accepted analytical window: 08:30–15:00 Chicago; entry and flatten cutoffs are separate |
| Overnight | Context window: preceding calendar day 17:00 through current day 08:30 Chicago; Sunday evening for Monday |
| VAH / VAL | Upper/lower boundaries of the selected Volume Profile value area |
| VPOC | Price row with the greatest traded volume under the selected profile settings |
| Developing value | Current-session VAH/VAL/VPOC as accumulated trading changes the profile |
| VWAP | Volume-weighted average price from the chosen anchor; context in V1 |
| ATR | Average True Range; descriptive volatility measure with settings to be recorded |
| Imbalance | Directional auction state under the finalized scoring framework |
| Transition | Intermediate regime without new-entry permission |
| Balance | Non-permission regime near the proposed score center; components preserve conflicting evidence |
| Penetration | Price trading beyond an identified level, rather than only touching it; execution source pending |
| Structural invalidation | Price location that contradicts the specific breakout thesis |
| Confirmed pivot | Candidate higher low/lower high validated by continuation beyond the preceding swing extreme |
| Learning lot | One NES contract in V1 |
| R0 / 1R | Fixed original price-risk dollars for that individual trade |
| Loss-R used | Sum of magnitudes of negative realized trade Rs; wins do not offset it |
| MAE / MFE | Maximum adverse/favorable excursion during the actual holding period |
| Thesis/reference ID | Identifier grouping attempts at the same breakout idea |
| Pyramiding | Adding to an existing winning position; excluded from V1 |

## 18. Document management and change log

### V1-DOC-01 — Authority and references

**Status: Agreed workflow.**

After review and commit, the repository copy at `copper/docs/trading_strategies/FUTURES_TREND_PLAYBOOK_V1.md` is authoritative. Chat messages and working copies support discussion. They do not automatically update the repository.

Keep rule IDs stable. Amend a rule under its existing ID when its purpose remains the same. Retire an ID explicitly rather than reusing it for an unrelated rule. Preserve trade records with the exact playbook revision used.

### V1-DOC-02 — Draft, freeze, and revisions

**Status: Proposed implementation of the agreed versioning approach.**

Use `V1-draft-01`, `V1-draft-02`, etc. during review. Resolve the decision register and obtain human acceptance before declaring **V1.0 — Frozen training baseline**. Later accepted changes receive V1.1, V1.2, etc., with affected IDs, rationale, effective date, and repository commit recorded.

Do not silently change rules after a few outcomes. Preserve evidence and record an intentional revision. Pyramiding or other multi-entry position mechanics require a separate V2 design.

### Change log

| Revision | Date (Chicago) | Change |
| --- | --- | --- |
| V1-draft-07 | 2026-10-10 | Accepted completed-bar regime assessment timing, pre-entry freshness check, latest-score use for intrabar entries, and UNKNOWN/no-entry policy. Updated V1-REGIME-02 and closed OD-03. Factors, thresholds, and open-position regime-change response remain open. |
| V1-draft-06 | 2026-10-10 | Accepted NinjaTrader Order Flow VWAP on ES, tick resolution subject to complete data, session reset, and explicit 08:30–15:00 Chicago template. Expanded V1-CONTEXT-04; retained operational verification/data/reproducibility details. |
| V1-draft-05 | 2026-10-10 | Accepted full-session ES 5-minute ATR input, including overnight history, without resetting at 08:30. Updated V1-CONTEXT-06; retained seed, warm-up, trading-hours template, and gap-handling details as open. |
| V1-draft-04 | 2026-10-10 | Accepted NinjaTrader Order Flow Volume Profile, 68% value area, one ES tick per row, tick resolution subject to availability, and ATR(13) Wilder on completed ES 5-minute bars. Added V1-CONTEXT-05/06. Retained open ATR history/session, profile reproducibility/data, and VWAP calculation details. |
| V1-draft-03 | 2026-10-10 | Accepted RTH analytical window, prior-session references, overnight window, and holiday/shortened-session observation-only policy. Added V1-SESSION-04; further resolved OD-01/04 without choosing entry/flatten cutoffs or calculation settings. |
| V1-draft-02 | 2026-10-10 | Accepted 5-minute ES analysis, NES execution, and 08:30 Chicago session VWAP anchor. Added V1-INSTRUMENT-03 and V1-CONTEXT-04; closed OD-16; partially resolved OD-04/05. No score, entry, stop, or exit mechanics changed. |
| V1-draft-01 | 2026-10-03 | Initial study draft. Preserves agreed single-lot mechanics, dynamic scoring architecture, intrabar breakout entry, structural stops, confirmed-pivot two-tick trailing, gross loss-R cutoff, and separate process review. Marks proposals and unresolved details explicitly. |

## 19. V2 backlog

These topics are discussion/research items, not V1 permissions:

- Pyramiding: first-add trigger, maximum adds, add size, combined stop management, aggregate risk, and combined-position R.
- Progression beyond one NES learning lot, including any eventual MES transition.
- Standard Initial Balance and other observation windows.
- Alternative entry families, including pullbacks.
- ATR-based buffers/trailing or fixed-R management, assessed against V1 evidence.
- Automated regime reconstruction, chart snapshots, replay, and forensic database integration in Dick's Laboratory.
- Empirical assessment of breakout volume and individual score factors.

## 20. Sources and provenance

**Primary authority for strategy choices:** the human decisions in the accompanying discussion through 2026-10-03. This document does not adopt every assertion or proposed mechanic from historical drafts.

**Historical inputs:** `gemini_playbook.md` and `blw_review.md`. Neither is the canonical V1 specification. In particular, claims that psychology guarantees profitability, that random-entry profitability is established, or that a pyramid is automatically risk-free are not accepted V1 rules.

**[S1] Contract specifications:** CME Group, [FAQ: E-nano Equity Index Futures](https://www.cmegroup.com/articles/faqs/faq-e-nano-equity-index-futures.html), questions 3 and 5; accessed 2026-10-03. Used here to verify NES multiplier, tick increment, and tick value. Strategy scoring and trailing rules are our design decisions, not CME recommendations.

**[S2] Cash-session calendar:** NYSE, [Holidays & Trading Hours](https://www.nyse.com/trade/hours-calendars), accessed 2026-10-10. Normal core hours of 09:30–16:00 Eastern correspond to 08:30–15:00 Chicago. Our overnight window and observation-only holiday policy are local design decisions, not rules prescribed by NYSE.

**[S3] Profile settings:** NinjaTrader, [Order Flow Volume Profile](https://static.ninjatrader.com/support/helpGuides/nt8/order_flow_volume_profile.htm), accessed 2026-10-10. Documents traded-volume versus trade-count profiles, configurable value-area percentage and ticks per level, and tick versus minute data resolution.

**[S4] ATR calculation:** NinjaTrader, [Average True Range (ATR)](https://static.ninjatrader.com/support/helpGuides/nt8/average_true_range_atr.htm), accessed 2026-10-10. Documents Wilder smoothing and a bar-count period parameter. The choice of 13 periods is the owner's accepted setting.

**[S5] VWAP implementation:** NinjaTrader, [Order Flow VWAP](https://static.ninjatrader.com/support/helpGuides/nt8/order_flow_vwap.htm), accessed 2026-10-10. Documents session reset, tick resolution, and trading-hours selection in combination with the underlying data-series hours. The explicit 08:30–15:00 Chicago window is our accepted local configuration.
