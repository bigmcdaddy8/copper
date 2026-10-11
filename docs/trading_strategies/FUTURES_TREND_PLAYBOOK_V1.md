# Futures Trend Playbook — V1

**Owner:** Mr. Dick Weasel  
**Document revision:** V1-draft-43  
**Created:** 2026-10-03 (America/Chicago)  
**Last revised:** 2026-10-10 (America/Chicago)  
**Status:** Draft for human review; not yet the frozen V1.0 training baseline  
**Intended repository location:** `copper/docs/trading_strategies/FUTURES_TREND_PLAYBOOK_V1.md`

## How to use this document

This document preserves the decisions made in our trading-design discussion. Read the quick reference before practice; use the numbered rules for study and questions. Cite a rule and revision when discussing it: “In V1-draft-28, I have a question about V1-STOP-04.”

Each rule has a status:

- **Agreed:** explicitly accepted in the discussion.
- **Working configuration:** discussed and used as the working baseline, but requires confirmation during document review.
- **Proposed implementation:** a precise implementation offered for review, not an accepted decision.
- **Open:** a definition or choice remains unresolved.

An agreed principle can still have open implementation details. The regime-scoring architecture, assessment timing, and all six factor definitions, equal weighting, total-score thresholds, and entry permissions are agreed. Operational and other trading definitions remain open. Do not treat this draft as fully executable until Section 16's decision register is resolved. Examples illustrate mechanics and do not establish profitability.

The prior `gemini_playbook.md` and `blw_review.md` remain historical inputs. They do not override decisions recorded here. Pyramiding belongs to V2.

## Contents

1. Quick reference
2. Purpose and scope
3. Instrument, platform, and session
4. Chart and context
5. Observation and regime assessment
6. Accepted regime score
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
| Concurrency | One open V1 position; while flat at most one active entry order; unresolved position/orders block entries | Agreed; V1-SCOPE-03 |
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
| Accepted trade permission | +4 to +6 long; -4 to -6 short; otherwise no entries | Agreed thresholds; V1-REGIME-03 |
| Entry family | Momentum break of meaningful swing/consolidation or auction reference | Agreed; V1-ENTRY-01 |
| Trigger | Penetration; no completed-bar requirement | Agreed; V1-ENTRY-02 |
| Breakout volume | Record afterward; no volume gate | Agreed; V1-ENTRY-03 |
| Initial stop | Structural invalidation plus minimum 0.50-point clearance; round away on execution tick grid; ATR recorded | Agreed; V1-STOP-01/02 |
| Trailing | Confirmed higher lows / lower highs; minimum 0.50-point clearance beyond mapped pivot; round away | Agreed; V1-STOP-02/04 |
| Profit target | None; no automatic +1R breakeven move | Agreed; V1-STOP-05, V1-EXIT-01 |
| Reentry | Regime must still qualify; maximum two filled attempts per direction per RTH trading date | Agreed; V1-ENTRY-04 |
| R | Original initial price risk of that trade; denominator remains fixed | Agreed principle; V1-RISK-02 |
| Daily cutoff | Net realized losing-trade R reaches 3; winners do not replenish it | Agreed; V1-DAILY-01 |
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

**Status: Agreed scope and one-position/pending-entry policy; OD-11 policy decisions closed 2026-10-10.**

**Accepted one-position and pending-entry policy — 2026-10-10:**

1. Starting V1 permits one open position of one NES contract. Submit no additional entry while that position is open; do not add to winning or losing positions.
2. While flat, permit at most one active entry order. Confirm cancellation or other final resolution before submitting a replacement; a cancellation request alone is not confirmation.
3. Before another entry, verify the previous position is flat, its associated orders are resolved, and equity, net Loss-R, and attempt counters are updated.
4. Pending exits, cancellations, or uncertain position/order status block new entries until reconciled.
5. A direction change requires closing and reconciling the existing position first, then independently qualifying the new entry. It does not automatically reset attempt limits.

Protective stops and exit orders belong to the existing position; their exact coordination, acknowledgements, fill/cancel races, and recovery remain under OD-07. This policy closes OD-11's intended concurrency rules, not platform implementation verification. Starting V1 excludes pyramiding.

## 3. Instrument, platform, and session

### V1-INSTRUMENT-01 — Contract identity and units

**Status: Agreed instrument; externally verified specifications.**

The training execution instrument is E-nano S&P 500 futures, product code **NES**. `/NES` is discussion shorthand; use NinjaTrader's actual dated contract identifier when placing orders and recording fills.

| NES unit | Value |
| --- | ---: |
| One index point, one contract | $0.50 |
| Minimum tick | 0.5 index points |
| Dollar value of one tick | $0.25 |
| Minimum initial/trailing buffer (local strategy policy) | 0.50 index points; one NES tick when the mapped level is tick-aligned |

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

The evidence families are auction location, value behavior, and price behavior. Section 6 records their accepted scoring implementation.

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

All six factors are defined in V1-REGIME-04/05/06/07/08/09. Total-score directional thresholds and permissions are accepted under V1-REGIME-03; OD-02 is closed. Operational data and calculation verification remain open under OD-04/05. Missing data is not neutral evidence. The accepted open-position regime-change response is defined in V1-EXIT-03: changes in permission alone do not trigger exit; operational emergency scope remains open under OD-14.

## 6. Accepted regime score

### V1-REGIME-03 — Six-factor framework and accepted total-score thresholds

**Status: Agreed on 2026-10-10; OD-02 closed.**

Each factor contributes -1, 0, or +1 with equal weight. Sum all six only when all required evidence is available. The table summarizes the observations. The exact accepted definitions for all six factors are in V1-REGIME-04/05/06/07/08/09. Their component scores and the aggregate trade-permission thresholds below are accepted as the starting research configuration.

| Factor | -1: bearish evidence | 0: neutral evidence | +1: bullish evidence |
| --- | --- | --- | --- |
| Relative to prior value (agreed) | Last two completed ES closes strictly below prior RTH VAL | Neither directional condition | Last two completed ES closes strictly above prior RTH VAH |
| VWAP relationship and slope (agreed) | Last two closes below their contemporaneous VWAP; VWAP down at least 0.25 points in 10 minutes | Neither directional condition | Last two closes above their contemporaneous VWAP; VWAP up at least 0.25 points in 10 minutes |
| Developing value migration (agreed) | Developing RTH VPOC and value-area midpoint each down at least 1.0 point over 10 minutes | Neither directional condition | Developing RTH VPOC and value-area midpoint each up at least 1.0 point over 10 minutes |
| Swing structure (agreed) | Latest two confirmed swing highs and latest two confirmed swing lows are both descending | Neither directional condition / too few formed pivots | Latest two confirmed swing highs and latest two confirmed swing lows are both ascending |
| Range extension (agreed) | Last two completed post-observation ES closes strictly below frozen initial 20-minute range low | Neither directional condition / fewer than two completed post-observation bars | Last two completed post-observation ES closes strictly above frozen initial 20-minute range high |
| Acceptance / rejection (agreed) | Valid bearish rejection-plus-continuation event(s), with no valid bullish event | Both directions, neither, or no eligible swings with complete data | Valid bullish rejection-plus-continuation event(s), with no valid bearish event |

| Accepted score | Classification | New entry permission |
| ---: | --- | --- |
| +4 to +6 | IMBALANCE UP | Long only |
| +2 to +3 | TRANSITION UP | None |
| -1 to +1 | BALANCE | None |
| -3 to -2 | TRANSITION DOWN | None |
| -6 to -4 | IMBALANCE DOWN | Short only |

**Rationale:** Scoring makes observations reviewable while preserving a separate entry decision. These factors are correlated; four points are not four independent proofs. A score near zero can also reflect conflicting directional evidence, so retain the component scores rather than treating every zero as the same auction.

**Accepted permission policy (OD-02 closed):** +4 through +6 permits long entries only; -6 through -4 permits short entries only; all other valid totals prohibit new entries. Permission is contextual, not an order signal: the breakout, protection, and risk requirements still apply. All six factors have agreed measurement conditions and missing-data handling. These starting thresholds have not established a performance edge. The accepted V1-REGIME-02 policy marks an assessment UNKNOWN and prohibits new entries when required evidence is missing. Do not silently treat unavailable data as neutral evidence.

### V1-REGIME-04 — Factor 1: location relative to prior Volume Profile value

**Status: Agreed on 2026-10-10.**

At each scheduled assessment, use the **last two completed ES RTH 5-minute bar closes** and VAH/VAL from the most recent completed RTH Volume Profile under V1-SESSION-04 and V1-CONTEXT-05.

| Score | Accepted condition |
| ---: | --- |
| +1 | Both closes are strictly above prior RTH VAH |
| -1 | Both closes are strictly below prior RTH VAL |
| 0 | Neither directional condition holds, with required evidence available |

A close equal to the relevant boundary does not satisfy a strict above/below comparison. No additional separation buffer is imposed for this factor. Missing required prior-profile or bar data makes the overall assessment UNKNOWN under V1-REGIME-02, not neutral.

This is an accepted **two-close proxy** for outside-value acceptance. It does not assert that price remained outside value throughout both bars. Preserve the actual closes and reference levels in the assessment record. This factor uses Volume Profile value, not VWAP deviation bands.

### V1-REGIME-05 — Factor 2: VWAP relationship and slope

**Status: Agreed on 2026-10-10.**

At assessment time `t`, compare the last two completed ES RTH 5-minute closes with their **respective contemporaneous ES RTH VWAP values**. Measure the change from the VWAP snapshot at `t - 10 minutes` to the snapshot at `t`.

| Score | Accepted condition |
| ---: | --- |
| +1 | Both closes are strictly above their respective VWAP values AND VWAP has risen at least 0.25 ES index points over 10 minutes |
| -1 | Both closes are strictly below their respective VWAP values AND VWAP has fallen at least 0.25 ES index points over 10 minutes |
| 0 | Neither directional condition holds, with required evidence available |

The slope comparison is inclusive at 0.25 points; the price/VWAP comparisons are strict. A close exactly at VWAP fails that directional price condition. Use numerical VWAP values where available; do not round a small change into a qualifying change merely because of displayed decimal precision.

At 08:50, the two closes are the bars ending at 08:45 and 08:50, and the slope comparison uses the VWAP snapshots at 08:40 and 08:50. These times identify completed-bar endpoints, not bar start labels. Missing required bar or VWAP snapshots makes the assessment UNKNOWN under V1-REGIME-02.

Preserve the historical VWAP at each endpoint. Do not compare both earlier closes against the current or final-session VWAP. These accepted measurements contribute contextual score points; neither factor is a standalone entry signal or a demonstrated performance threshold.

### V1-REGIME-06 — Factor 3: developing value migration

**Status: Agreed on 2026-10-10.**

At each scheduled assessment time `t`, compare the developing **ES RTH Volume Profile** at `t` with its historical snapshot at `t - 10 minutes`. Use the same indicator, data-resolution policy, 68% value-area setting, row aggregation, and current RTH session for both snapshots.

Record two quantities at each endpoint:

- Developing VPOC.
- Developing value-area midpoint: `(developing VAH + developing VAL) / 2`.

| Score | Accepted condition |
| ---: | --- |
| +1 | VPOC AND value-area midpoint have each risen at least 1.0 ES index point over 10 minutes |
| -1 | VPOC AND value-area midpoint have each fallen at least 1.0 ES index point over 10 minutes |
| 0 | Neither directional condition holds, with required snapshots available |

The 1.0-point comparisons are inclusive. Conflicting movement, no movement, or a qualifying move in only one quantity scores zero when both required snapshots are available. Missing required snapshots or profile values makes the assessment UNKNOWN under V1-REGIME-02.

At 08:50, compare the snapshots captured at 08:40 and 08:50. Preserve the actual historical VPOC/VAH/VAL values. Do not substitute the final-session profile or use future observations to reconstruct an earlier value state.

The midpoint is the arithmetic center of the Volume Profile value-area boundaries, not VWAP, a volume-weighted mean, or the VWAP Wave deviation-band center. The 10-minute lookback and 1.0-point threshold are accepted training measurements to evaluate with evidence; they are not established performance thresholds.

### V1-REGIME-07 — Factor 4: swing structure

**Status: Agreed on 2026-10-10.**

Identify three-bar pivots using **completed ES RTH 5-minute bars** from the current RTH session:

- A swing high is a middle bar whose high is strictly higher than the highs of both its immediate neighboring bars.
- A swing low is a middle bar whose low is strictly lower than the lows of both its immediate neighboring bars.
- Recognize the pivot only after the right-hand neighboring bar closes. Equal neighboring extremes do not qualify.

At each scheduled assessment, compare the **two most recent confirmed swing highs** and the **two most recent confirmed swing lows** from the current RTH session. Order each pair by time; compare the latest with its predecessor.

| Score | Accepted condition |
| ---: | --- |
| +1 | Latest swing high is strictly higher than the preceding swing high AND latest swing low is strictly higher than the preceding swing low |
| -1 | Latest swing high is strictly lower than the preceding swing high AND latest swing low is strictly lower than the preceding swing low |
| 0 | Neither directional condition holds, including equal swings or too few formed pivots, when required price data is complete |

Complete price data with no established swing sequence scores zero. Missing required price data makes the assessment UNKNOWN under V1-REGIME-02. Do not import overnight pivots to satisfy this current-RTH structure definition.

Record pivot bar times, confirmation times, and prices. Only pivots confirmed by the assessment time are eligible; future bars must not be used to label a pivot earlier than it could have been recognized.

These pivots measure the regime structure. A three-bar pivot alone does not authorize moving a protective stop: V1-STOP-04 still requires directional continuation beyond the preceding swing extreme. V1-ENTRY-05 now adopts the same pivot identification method for entry swings. V1-ENTRY-06 records the accepted swing-reference selection and subsequent pullback requirement. Remaining reference/consolidation details and stop-specific candidate tracking remain separate OD-06/13 decisions.

### V1-REGIME-08 — Factor 5: range extension holding

**Status: Agreed on 2026-10-10.**

Use the **initial 20-minute ES observation range**, formed from the four completed RTH 5-minute bars beginning at 08:30, 08:35, 08:40, and 08:45 America/Chicago:

- Range high: highest high of those four bars.
- Range low: lowest low of those four bars.
- Freeze both references at 08:50; do not expand them with later bars.

At each scheduled assessment, use the **last two completed post-observation ES 5-minute bars**. The first eligible post-observation bar begins at 08:50 and ends at 08:55.

| Score | Accepted condition |
| ---: | --- |
| +1 | Both eligible closes are strictly above the frozen initial observation range high |
| -1 | Both eligible closes are strictly below the frozen initial observation range low |
| 0 | Neither directional condition holds, including fewer than two completed post-observation bars, with required price data complete |

A close equal to the relevant boundary fails the strict directional comparison. Complete price data with fewer than two elapsed post-observation bars scores zero; missing required data makes the assessment UNKNOWN under V1-REGIME-02.

This factor scores zero at 08:50 and 08:55. The first possible directional score is 09:00, using the bars ending at 08:55 and 09:00. Other factors can contribute earlier; this factor is a score component, not a mandatory opening-range breakout gate.

The two-close condition is an accepted proxy for extension holding; price need not remain outside the range throughout both bars. Record the frozen range, the eligible close prices, and bar endpoint times. This is the 20-minute observation range, not the standard Initial Balance.

### V1-REGIME-09 — Factor 6: rejected counterdirectional break with continuation

**Status: Agreed on 2026-10-10.**

Use completed ES RTH 5-minute bars and the Factor 4 three-bar pivots. For each candidate rejection bar, select the latest confirmed current-RTH swing low for a bullish candidate, or swing high for a bearish candidate, that was already known when the rejection bar began. Freeze that reference for the event; later pivot discoveries do not replace it retrospectively.

| Event | Accepted confirmation condition |
| --- | --- |
| Bullish rejection confirmed | The rejection bar trades strictly below its known swing-low reference and closes strictly above it; the immediately following bar closes strictly above the rejection bar's high |
| Bearish rejection confirmed | The rejection bar trades strictly above its known swing-high reference and closes strictly below it; the immediately following bar closes strictly below the rejection bar's low |

Recognize the event at the close of the immediately following continuation bar, not at the earlier rejection-bar close. A later bar cannot rescue a candidate whose immediately following bar failed the confirmation condition. Equal prices do not satisfy the strict comparisons.

At each scheduled assessment, consider events confirmed at the **last four assessment times, including the current assessment**. For a normal five-minute cadence, these are `t`, `t - 5`, `t - 10`, and `t - 15 minutes`. Only scheduled RTH assessment times at or after 08:50 are eligible. An event whose confirmation time is earlier than 08:50 is outside this four-assessment event policy.

An event remains valid for the current assessment only while the latest completed close is strictly above its original swing-low reference (bullish), or strictly below its original swing-high reference (bearish). Check validity against that frozen reference at each assessment. Expiry and current-close validity both apply.

| Score | Accepted condition |
| ---: | --- |
| +1 | At least one bullish event remains valid in the window AND no bearish event remains valid |
| -1 | At least one bearish event remains valid in the window AND no bullish event remains valid |
| 0 | Both directions qualify, neither qualifies, or no eligible swings have formed, with required price data complete |

Multiple same-direction events still contribute only one point. Complete data with no formed reference or no event scores zero; missing required price data makes the assessment UNKNOWN under V1-REGIME-02. Preserve pivot confirmation times, the rejection and continuation bars, event confirmation time, original reference, and latest-close validity evidence.

**Bullish example:** a known swing low is 6000.0. A rejection bar trades below 6000.0, closes above it, and has a high of 6003.0. The immediately following bar closes at 6003.50, confirming a bullish event. Its reference remains 6000.0 during the four-assessment window.

This factor contributes contextual evidence. It does not authorize an entry, change the structural initial stop, or replace V1-STOP-04's continuation requirement for trailing. V1-EXIT-03 accepts continued structural management through regime changes; operational emergency scope remains open under OD-14.

## 7. Trade permission and entry

### V1-ENTRY-01 — Eligible breakout family

**Status: Agreed.**

An entry may break either:

1. A meaningful recent swing or consolidation high/low; or
2. A meaningful auction reference, such as prior VAH/VAL, prior-session high/low, or overnight high/low.

The direction must agree with the permitted regime. A random bar high/low is not automatically an eligible level. Breaking the initial observation range alone is not sufficient; it must qualify within the accepted entry family. Entry swing identification follows the accepted V1-ENTRY-05 method. V1-ENTRY-06 adds the accepted swing-reference selection and pullback requirement. Pullback selection and consolidation formation are now accepted in V1-ENTRY-07/08. V1-ENTRY-09 accepts consolidation lifetime/replacement. V1-ENTRY-10 accepts meaningful auction-reference qualification; OD-06 is closed. Remaining trigger/execution details stay under OD-07; pivot identification alone does not make every pivot an eligible breakout reference.

### V1-ENTRY-02 — Penetration trigger

**Status: Agreed principle; exact trigger/order mechanics open.**

Enter on penetration of the eligible level; do not require a completed 5-minute bar. For a long, penetration is above the selected level; for a short, below it. A touch is not penetration.

Identify the level and initial structural invalidation before entry. Define trigger price source, tick rounding, any entry buffer, order type, and treatment of an already-broken level under OD-07. The accepted 0.50-point stop buffer is not an agreed entry buffer. Stop rounding is defined in V1-STOP-02; entry-trigger rounding remains open.

### V1-ENTRY-03 — Breakout volume

**Status: Agreed.**

Do not require a raw-volume confirmation for V1 entry. Record available breakout volume afterward for research, identifying its measurement window and whether a bar was incomplete at entry. Profile evidence still belongs in the contextual assessment.

### V1-ENTRY-04 — Reentry permission

**Status: Agreed.**

A failed attempt may be followed by another attempt if the current regime still qualifies, fresh entry/stop structure is valid, and both risk guards permit it. Starting V1 allows maximum **two filled long attempts and two filled short attempts per RTH trading date**, across all references/setup families within PB-TREND. The original entry counts. See V1-REENTRY-01 for accepted directional thesis identity/reset and counting rules; a new reference does not create a fresh directional allowance.

### V1-ENTRY-05 — Entry-swing pivot identification

**Status: Agreed on 2026-10-10; OD-06 closed.**

Reuse V1-REGIME-07's three-bar pivot method for identifying entry swings on the current-RTH ES 5-minute chart:

- Use completed current-RTH bars for all three observations.
- A swing high's center-bar high must be strictly higher than both immediately adjacent bar highs.
- A swing low's center-bar low must be strictly lower than both immediately adjacent bar lows.
- Recognize a pivot only after the right-hand bar closes. Equal neighboring highs/lows do not qualify for the corresponding pivot.
- The pivot must already be known before entry. Preserve its center-bar timestamp, recognition timestamp, and ES price; do not use a later-confirmed pivot retrospectively.

This accepts swing identification, not a rule that every pivot is meaningful or eligible. The accepted swing-reference and pullback requirements are in V1-ENTRY-06. V1-ENTRY-07/08 record accepted pullback selection and consolidation formation. V1-ENTRY-09 accepts consolidation lifetime/replacement. V1-ENTRY-10 accepts auction-reference qualification; OD-06 is closed. An ES pivot price does not resolve NES order-level mapping under OD-04/07. Trailing-stop movement retains V1-STOP-04's separate continuation-confirmation requirement; acceptance of an entry pivot does not itself authorize a stop modification.

### V1-ENTRY-06 — Swing-reference selection and pullback requirement

**Status: Agreed on 2026-10-10; OD-06 closed.**

For the swing-breakout variant, use this starting structure:

| Direction | Breakout reference | Required pullback structure |
| --- | --- | --- |
| Long | Latest confirmed current-RTH swing high | Most recent eligible confirmed swing low formed after that high, with its price below that high |
| Short | Latest confirmed current-RTH swing low | Most recent eligible confirmed swing high formed after that low, with its price above that low |

Identify both pivots with V1-ENTRY-05. “Formed after” refers to their center-bar order; both recognition timestamps must precede entry. Record the selected reference and pullback pivot using evidence available before entry.

The opposite pivot supplies the candidate structural invalidation for this swing → pullback → breakout sequence. V1-STOP-02 specifies the accepted stop buffer/rounding; executable NES level mapping and cross-instrument handling remain separate OD-04/07 decisions. The latest scheduled regime assessment must permit the direction, and the existing entry/protection/risk requirements still apply.

When multiple pullback pivots exist, select the most recent eligible opposite pivot as defined in V1-ENTRY-07. The pivot pair is recorded at entry; later pivots do not rewrite the original invalidation. V1-ENTRY-08/09 define consolidation formation and lifetime/replacement; V1-ENTRY-10 accepts meaningful auction-reference qualification. Treatment of already-penetrated references remains under OD-07, and a changed reference does not automatically reset the attempt count under OD-12. Entry-swing identification and selection do not replace the separate continuation confirmation required for trailing-stop movement.

### V1-ENTRY-07 — Pullback-pivot selection

**Status: Agreed on 2026-10-10; OD-06 closed.**

| Direction | Accepted pullback-pivot selection |
| --- | --- |
| Long | Most recent confirmed swing low formed after the selected swing high, with its price below that high |
| Short | Most recent confirmed swing high formed after the selected swing low, with its price above that low |

“Most recent” refers to the center-bar timestamp among pivots that meet all listed conditions and are already recognized before entry. Use V1-ENTRY-05's identification method. If no eligible opposite pivot exists, the swing-breakout variant lacks its required pullback structure.

Record the chosen reference/pullback pair at entry. Later pivots do not rewrite the original structural invalidation or the original risk reference. Subsequent protective-stop movement is governed separately by the trailing rules. NES price mapping remains open under OD-04/07; V1-STOP-02 specifies the accepted stop buffer/rounding. V1-ENTRY-08 defines consolidation formation. V1-ENTRY-09 accepts consolidation lifetime/replacement. V1-ENTRY-10 accepts meaningful auction-reference qualification; OD-06 is closed; already-penetrated levels and reentry accounting remain separate OD-07/12 decisions.

### V1-ENTRY-08 — Consolidation formation and breakout structure

**Status: Agreed on 2026-10-10; OD-06 closed.**

| Element | Accepted starting definition |
| --- | --- |
| Formation | Latest three consecutive completed current-RTH ES 5-minute bars |
| Box boundaries | Highest high (H) and lowest low (L) of those three bars |
| Overlap requirement | Price interval shared by all three bars spans at least 50% of the total box width |
| Recognition | After the third bar closes; require positive box width |
| Entry structure | Penetrate above the box for a permitted long; below it for a permitted short |
| Candidate invalidation | Opposite box boundary; apply accepted stop buffer/rounding after NES mapping, subject to risk limits |

Let W = H - L. Let overlap upper = minimum of the three bar highs and overlap lower = maximum of the three bar lows. Shared overlap width O = overlap upper - overlap lower. The formation qualifies only when W > 0 and O >= 0.50 × W. Equality at 50% qualifies. Disjoint ranges or a single-price common touch do not satisfy the requirement for a positive-width box. Missing required bars/prices cannot be treated as a qualifying formation.

For example, a four-point box requires at least two points of common overlap. Record the three source bars, recognition time, boundaries, overlap width, and overlap ratio using completed evidence available at recognition. Preserve the entry-time box and its candidate invalidation in the attempt record.

The three-bar and 50% choices are accepted starting research settings, not established performance thresholds or a source-prescribed consolidation definition. Formation may use completed bars from the initial observation window; the existing no-entry-before-08:50 rule still applies. The latest scheduled regime assessment must permit the breakout direction. Entry remains on penetration rather than a completed breakout bar; other protection and risk requirements still apply.

V1-ENTRY-09 accepts box freezing, first-breakout lifetime, and replacement. Reentry after penetration, detailed trigger/order handling, and thesis/attempt accounting remain separate OD-07/12 decisions. This rule does not resolve NES order-level mapping or maximum risk. V1-STOP-02 supplies the accepted stop buffer/rounding. V1-ENTRY-10 accepts meaningful auction-reference qualification; OD-06 is closed. ATR remains descriptive evidence rather than a consolidation-entry filter.

### V1-ENTRY-09 — Consolidation box duration and replacement

**Status: Agreed on 2026-10-10; OD-06 closed.**

| Situation | Accepted handling |
| --- | --- |
| Box qualifies | Freeze its boundaries and recognition timestamp |
| Subsequent bars | Keep that box; do not redraw or replace it while active |
| Lifetime | Eligible for a first breakout until 15 minutes after recognition, excluding that deadline |
| Either boundary is penetrated | First-breakout candidacy ends, whether or not an entry occurred |
| Box expires or breaks | Evaluate a replacement from the latest three completed bars at the next scheduled assessment |

A touch alone is not penetration. A qualifying directional penetration is the first-breakout event itself: it may supply an entry if contemporaneous permission and all other requirements are satisfied. It also ends the box's unbroken first-breakout candidacy. Penetration without an entry does not leave that box eligible for a delayed first-breakout chase.

A box recognized at 09:00 is eligible before 09:15 unless either boundary is penetrated sooner. At 09:15 the old box is expired. Evaluate a replacement at the first scheduled assessment at or after expiry, or the next scheduled assessment following an intrabar break; the replacement must independently satisfy V1-ENTRY-08. Do not change the old recognition timestamp to extend its lifetime. Ordinary regime reassessment does not redraw or extend an active box; current directional permission remains required for entry. Existing observation, session, data-sufficiency, and risk restrictions still apply.

Preserve box identity, source bars, recognition/expiry times, and any penetration event in the record. A replacement does not reset attempt counts, rewrite an existing trade's original invalidation or risk reference, or change its management rules. Reentry following a failed breakout remains separate under OD-07/12. The 15-minute lifetime is an accepted starting research setting rather than an established performance threshold. V1-ENTRY-10 accepts auction-reference qualification; OD-06 is closed.

### V1-ENTRY-10 — Auction-reference qualification

**Status: Agreed on 2026-10-10; OD-06 closed.**

| Element | Accepted starting research rule |
| --- | --- |
| Eligible references | Prior RTH Volume Profile VAH/VAL, prior RTH high/low, and completed overnight high/low |
| Selection | Identify and record one reference before its entry trigger |
| Long approach | Latest completed ES close is at or below the reference; entry requires subsequent penetration above it |
| Short approach | Latest completed ES close is at or above the reference; entry requires subsequent penetration below it |
| Structural invalidation | Most recent confirmed current-RTH swing low below the reference for longs; swing high above it for shorts |
| Missing structure | No eligible opposite pivot means no auction-reference entry |

Use the accepted session definitions and analytical ES references. For VAH/VAL, use Volume Profile value rather than VWAP deviation-band value. Select the most recent eligible opposite pivot by center-bar timestamp using V1-ENTRY-05's identification and recognition policy. Unlike the swing-breakout pair, a current-RTH invalidation pivot need not form after the historical reference's source session; it must meet the direction-specific relative-price condition and be known before entry.

Both the selected reference and invalidation pivot must be known before entry. Record their prices, source/session identity, selection time, pivot center/recognition times, and the latest completed ES close used for the approach condition. Equality of that close to the reference is allowed; a touch alone is not an entry trigger.

The latest scheduled regime assessment must permit the direction, and the existing protection/risk requirements still apply. The opposite pivot is candidate structural invalidation; V1-STOP-02 supplies the accepted stop buffer/rounding; NES level mapping and executable order workflow remain separate OD-04/07 decisions. Approach-side qualification does not authorize chasing a level already penetrated intrabar. Already-penetrated levels, exact trigger handling, and reentry accounting remain separate OD-07/12 decisions.

This completes OD-06's accepted starting definitions for swing, consolidation, and auction-reference entry families. It does not establish a performance edge or freeze the entire V1 playbook. Trailing-pivot selection remains separate under OD-13.

## 8. Initial stop and protective orders

### V1-STOP-01 — Structural initial invalidation

**Status: Agreed.**

For a long breakout, place the initial stop beyond the meaningful pre-breakout swing low or consolidation low that invalidates the thesis. For a short, mirror this above the relevant swing or consolidation high.

Structure determines stop location. Do not move the stop closer merely to fit a preferred dollar risk. Record ATR and stop distance in ATR units for later analysis.

### V1-STOP-02 — Initial buffer and order protection

**Status: Buffer and outward stop rounding agreed on 2026-10-10; OD-08 closed. Initial protection workflow remains open under OD-07.**

For both initial and trailing stops in this S&P 500 playbook, use a **minimum 0.50-index-point clearance beyond the mapped structural-invalidation level**, then round the resulting stop price away from structure to a valid execution-contract tick. This supersedes the earlier two-NES-tick (1.00-point) trailing policy.

| Direction | Accepted calculation |
| --- | --- |
| Long | Subtract 0.50 points from the mapped level, then round downward to the execution tick grid |
| Short | Add 0.50 points to the mapped level, then round upward to the execution tick grid |

Let P be the mapped structural level before stop rounding and q the execution tick size. For the standard zero-based tick grid, long stop = floor((P - 0.50) / q) × q; short stop = ceil((P + 0.50) / q) × q. Obtain tick size from the execution instrument's verified specification/metadata. Do not round inward merely to fit an order or risk preference.

The 0.50-point setting corresponds to two ES/MES ticks or one NES tick when the mapped level is tick-aligned. If the mapped level lies between executable ticks, outward rounding can increase actual clearance. With NES q = 0.50 and a mapped long invalidation P = 6000.25, the desired stop is 5999.75 and the executable outward-rounded stop is 5999.50: actual clearance is 0.75 points. For a short at the same mapped reference, 6000.75 rounds upward to 6001.00, also giving 0.75-point clearance.

Define buffer distance by strategy/instrument family and convert it using the execution tick size; do not automatically carry 0.50 points into unrelated futures such as NQ. Record nominal buffer, mapped level, tick size, rounded trigger, actual clearance, and resulting risk. Structure determines invalidation; if the resulting initial stop exceeds the eventual accepted risk limit, skip the entry rather than moving the stop closer. V1-RISK-03 accepts the combined percentage-and-dollar ceiling; starting allocation and numeric limits are accepted; equity update/verification and starting fee/slippage policies are agreed; OD-09 policy decisions are closed with no separate distance filter; platform implementation/validation remains under OD-07, gross/net realized accounting is agreed under closed OD-10, and funding/reconciliation evidence remains required.

This closes OD-08 and the stop-price rounding subdecision of OD-07. ES-to-NES level mapping, entry-trigger rounding/buffer, and operational order procedures remain open. A mapped reference in the arithmetic example is a supplied input, not an accepted ES-to-NES mapping algorithm.

Proposed procedure: arrange the protective stop as part of the entry workflow; immediately verify its accepted status after a fill. The exact NinjaTrader procedure, partial-fill behavior, rejected-order response, and connection-loss handling must be documented under OD-07. A stop trigger is not a guarantee of a particular fill price.

### V1-STOP-03 — Stop discipline

**Status: Proposed explicit guardrail consistent with structural risk.**

Never widen a protective stop to increase risk after entry. A long stop may remain unchanged or move higher; a short stop may remain unchanged or move lower. If a candidate structural stop would loosen the existing stop, keep the existing stop.

## 9. R and session risk

### V1-RISK-01 — One learning lot

**Status: Agreed.**

Each V1 entry uses **one NES contract**. The accepted starting futures allocation is $3,500; the earlier approximately $50,000 account illustration is not the V1 allocated risk base. Do not optimize quantity to consume the allowance. A wider structural stop changes that trade's dollar risk, not its V1 quantity. V1-RISK-03 now accepts a combined percentage-and-dollar ceiling. Its starting allocation, percentage, and dollar cap are accepted; equity update/verification and starting fee/slippage policies are agreed; OD-09 policy decisions are closed with no separate distance filter; platform implementation/validation remains under OD-07, gross/net realized accounting is agreed under closed OD-10, and funding/reconciliation evidence remains required. The ceiling filters entry eligibility; it does not increase V1 quantity or prescribe stop placement.

### V1-RISK-02 — Fixed original denominator

**Status: Fixed price-risk denominator and gross/net reporting agreed; OD-10 policy decisions CLOSED 2026-10-10.**

Let `E` be the actual entry fill, `S0` the original protective-stop trigger, and `Q = 1` contract:

`Initial risk dollars (R0) = abs(E - S0) × $0.50 × Q`

`Gross realized trade R = gross realized trade P&L / R0`

Keep `R0` fixed throughout the trade. Moving the stop does not reset the denominator. Calculate planned risk before entry and preserve it separately from risk calculated from the actual fill. Initial dollar risk here is price risk; the accepted gross/net accounting policy below keeps costs out of the fixed R0 denominator.

**Accepted gross/net reporting and realized-cost policy:**

`Gross realized trade P&L = direction-adjusted actual entry-to-exit price difference × $0.50 × 1`

`Net realized trade P&L = gross realized trade P&L - applicable transaction fees`

`Net realized trade R = net realized trade P&L / R0`

Record both gross and net realized R for each completed filled attempt, including an overshoot exit. Live accounting uses actual fills and applicable transaction charges, reconciled to account records. Replay/simulation uses its documented fee model and mode-identified fills. Subtract transaction fees once; if a source already supplies net P&L, do not subtract the same fees again.

Actual fills already capture execution slippage. Do not subtract the $1.50 planning allowance or any separately measured slippage amount again from realized P&L. For replay/simulation, any modeled slippage must be represented consistently in its fills and counted once, not treated as observed live execution. Preserve slippage measurements as separate execution evidence.

Non-trade account charges remain in the allocation ledger and are not assigned as transaction fees to trade R. The daily cutoff uses net losing-trade R under V1-DAILY-01; gross R remains available for strategy/process analysis. Verify the NinjaTrader commission template and displayed P&L against the documented fee model/account charges before relying on those displays. See [NinjaTrader Accounts Tab documentation](https://static.ninjatrader.com/support/helpGuides/nt8/accounts_tab.htm), checked 2026-10-10: displayed commissions may be calculated from the local template rather than supplied by the data provider.

| Example | Entry | Initial stop | Distance | R0 |
| --- | ---: | ---: | ---: | ---: |
| Long A | 6000.0 | 5995.0 | 5 points | $2.50 |
| Long B | 6000.0 | 5986.0 | 14 points | $7.00 |
| Short C | 6000.0 | 6009.0 | 9 points | $4.50 |

For Long A, a $7.50 gross profit is +3R. It does not imply a +3R profit-target order. A stop filled at its original trigger produces -1R before costs; an adverse fill can lose more than 1R.

### V1-RISK-03 — Combined percentage-and-dollar entry-risk ceiling

**Status: Starting risk configuration and input/update/verification/overshoot policies agreed on 2026-10-10; no separate stop-distance filter in starting V1. OD-09 policy decisions CLOSED 2026-10-10. Actual funding/reconciliation evidence, live cost/slippage validation, and platform execution/recovery remain required.**

For the one-NES learning configuration, use the smaller of a percentage-of-equity ceiling and a fixed-dollar learning cap:

`Allowed planned risk = min(p × A, D)`

| Input | Accepted starting configuration |
| --- | ---: |
| Initial futures allocation | $3,500 |
| Percentage ceiling p | 0.50% (0.005) |
| Fixed-dollar learning cap D | $15 |
| Initial percentage-based allowance | $17.50 |
| Initial effective combined ceiling | $15, including estimated round-trip fees and slippage allowance |
| Execution quantity | One NES contract |

Here A is the pre-entry equity basis defined below for capital explicitly allocated to futures trading, initially $3,500; p is the accepted 0.005 risk fraction; and D is the accepted $15 fixed-dollar learning cap. These are starting learning/research settings. They do not establish that every qualifying structural stop fits or that the strategy has a performance edge. The percentage is a ceiling rather than a target amount to consume. Keep Q = 1 NES; do not enlarge quantity or widen a structural stop to reach the allowance. Account for other positions drawing on the same allocated capital when finalizing the risk policy.

**Accepted equity-update policy:**

1. Before each session, record verified allocated futures equity as the session-start snapshot, accounting for actual trading results, costs, deposits, and withdrawals.
2. Before every entry, use `A = min(verified session-start allocated equity, current verified allocated equity)`. Losses and withdrawals can reduce the percentage allowance during the session; profits and deposits cannot increase it until the next session. Recalculate the combined ceiling as `min(0.005 × A, $15)`.
3. Keep the $15 fixed-dollar ceiling and one-NES quantity. The $3,500 is the initial allocation; never reset the equity basis to that amount merely because losses occurred.

For illustration, A = $3,200 still gives a $15 combined ceiling; A = $2,800 gives a $14 ceiling. These examples only show the accepted calculation and do not establish a minimum funded balance or margin eligibility. Equity verification, pending-transaction reconciliation, and shared-capital treatment follow the accepted policy below; record actual funding/reconciliation evidence rather than treating the starting allocation as proof of funded capital.

**Accepted equity-verification policy:**

1. Maintain a futures-allocation ledger beginning with the funded $3,500, updated for actual trading results, transaction costs, account charges, deposits, and withdrawals. The initial allocation is a design setting; verify actual funding before treating it as available capital.
2. Reconcile the ledger to NinjaTrader account records before each session and verify changes before another entry. Buying power and margin allowances do not count as allocated equity. Preserve the account-record source, timestamp, ledger balance, and reconciliation result.
3. Exclude pending deposits until available. Reserve requested withdrawals immediately, without subtracting them again when posted; track pending-to-posted transitions so each movement is counted once.
4. Do not count capital assigned to other strategies twice. If allocated equity cannot be reconciled, block new entries until resolved.

Apply the accepted `A = min(verified session-start allocated equity, current verified allocated equity)` calculation to this verified allocation. Preserve actual ledger entries and account evidence; acceptance of this policy is not a claim that funding or account records have been inspected. Unresolved allocation discrepancies are not permission to estimate a larger equity base.

**Accepted fee-input policy:**

1. Use the broker's applicable one-NES round-trip transaction cost, including commissions and exchange, clearing, and regulatory charges. Determine the total applicable to the owner's pricing plan rather than assuming a generic advertised rate.
2. Record the fee amount, source, and verification date. Refresh the input when applicable pricing changes.
3. Keep the fee input separate from the slippage allowance; include both in the combined-ceiling affordability check. The hypothetical $3 combined-cost example below is not a default fee input.
4. If the applicable fee input is unknown, block entry until verified. Acceptance of this input policy does not establish the actual fee amount.

**Broker and pricing plan — owner confirmed 2026-10-10:** NinjaTrader Brokerage, Free trading plan, standard NinjaTrader connection, one NES contract.

**Published NES Free-plan base transaction rate verified from owner-provided screenshot on 2026-10-10:**

| Component | Per side, one NES | Round trip, one NES |
| --- | ---: | ---: |
| Exchange + NFA | $0.36 | $0.72 |
| Clearing | $0.19 | $0.38 |
| Free-plan commission | $0.39 | $0.78 |
| Published all-in base rate | $0.94 | $1.88 |

Source: owner-provided `image.png`, showing the NES / E-nano S&P 500 / CME row, supplied and inspected 2026-10-10. The row establishes the NES rate directly; it is not inferred from MES. Reference pages: [NinjaTrader commission schedule](https://ninjatrader.com/pricing/commissions/) and [account/technology fees](https://ninjatrader.com/pricing/account-fees/). The retrieved commission schedule labels its data as of 2026-08-14; the screenshot itself has no visible effective date. Preserve the verification date and refresh under the accepted fee policy.

Use $1.88 as the starting one-NES round-trip fee input for the owner-selected Free plan and standard NinjaTrader connection, confirmed by the owner on 2026-10-10. No optional third-party routing/technology transaction add-on is included in this starting configuration. This records the selected configuration and published rate; it does not assert that an account statement has been inspected. Verify charges against the applicable account schedule/statement before live use; refresh the input if pricing, routing, optional technology, or actual charged transaction fees differ. Include any newly applicable transaction add-ons and apply the unknown-fee no-entry rule if the applicable input becomes unresolved. Do not double-count exchange, NFA, clearing, or commission components already included in $1.88.

For the selected starting configuration, round-trip fees plus accepted replay/simulation slippage allowance total `$1.88 + $1.50 = $3.38`. At the initial $15 ceiling, this leaves $11.62 for planned structural price risk. Do not narrow a structural stop to fit the remainder. Any subsequently applicable transaction add-ons reduce the remaining allowance. Account-level recurring/non-trade charges are not invented as per-trade fees here; treatment in allocated equity remains part of equity verification/reconciliation.

**Accepted starting slippage allowance and measurement policy — replay/simulation:**

| Component | NES ticks | Index points | Dollar allowance, one NES |
| --- | ---: | ---: | ---: |
| Adverse entry slippage | 2 | 1.00 | $0.50 |
| Adverse protective-stop exit slippage | 4 | 2.00 | $1.00 |
| Total | 6 | 3.00 | $1.50 |

These are provisional research assumptions, not measured NES execution estimates. Use $1.50 once in the pre-entry affordability check, in addition to verified round-trip fees. Keep planned entry price separate from the allowance; do not embed an adverse entry adjustment in that price and then charge the same adjustment again. The larger protective-stop exit component provides additional planning room; it does not guarantee the stop fill or maximum loss.

Record actual adverse entry and protective-stop exit slippage separately, preserving the planned NES entry reference, applicable stop trigger, direction, actual fills, and timestamps so the measurements can be checked. Review the assumption against execution evidence before adopting a live baseline. Keep replay/simulation evidence identified by mode rather than presenting it as observed live execution. The allowance does not change the structural-stop buffer, move the stop, or redefine R0. Realized-cost and daily net Loss-R accounting are agreed under V1-RISK-02 and V1-DAILY-01; OD-10 policy decisions are closed.

`Planned structural price risk + verified round-trip fees + $1.50 <= allowed planned risk`

Determine structural invalidation first, map to the execution instrument, and apply V1-STOP-02's 0.50-point minimum clearance and outward tick-grid rounding. Assess affordability using the resulting planned price risk plus estimated round-trip fees and a slippage allowance:

`Planned price risk = abs(planned NES entry - rounded initial NES stop) × $0.50 × 1`

`Estimated planned total risk = planned price risk + estimated round-trip fees + slippage allowance`

Compare estimated planned total risk with the combined ceiling. If it exceeds the ceiling, skip the entry rather than moving the stop closer or increasing the ceiling for that opportunity. Actual loss may exceed the estimate because stop execution and entry fills can differ from the plan. Preserve planned inputs separately from actual fills and realized results.

This affordability check does not redefine V1-RISK-02's fixed price-risk R0 denominator. Realized gross/net accounting and the net Loss-R cutoff are accepted separately under V1-RISK-02 and V1-DAILY-01. The fee-input policy and NinjaTrader Free-plan selection are recorded; the $1.88 NES round-trip starting fee input is recorded for the selected standard connection, with account-statement verification and refresh before live use. The starting replay/simulation slippage allowance and separate measurement policy are accepted. The actual-entry overshoot response is accepted below. Live validation and detailed execution-reference/platform recovery verification remain required under the accepted risk policy and OD-07; realized accounting follows closed OD-10.

**Accepted actual-entry risk-overshoot policy:**

1. Immediately after the entry fill, recalculate assessed risk using the actual NES fill and original rounded structural stop:

   `Post-fill assessed risk = abs(actual NES entry fill - original rounded NES stop) × $0.50 × 1 + applicable round-trip fees + $1.00 protective-stop exit slippage allowance`

   Remove the $0.50 entry-slippage allowance from this post-fill calculation: the actual entry fill already captures that price effect. Keep the $1.00 exit allowance as the accepted research assumption, not a guaranteed exit cost. Preserve the original R0 convention.

2. Compare the result with the allowed ceiling recorded before entry. If post-fill assessed risk strictly exceeds that ceiling, promptly initiate exit of the one-NES position. Do not tighten the structural stop merely to make the calculation pass or raise the ceiling after the fill. Equality does not trigger this overshoot rule.
3. Use a coordinated exit/protection procedure, then verify the position is flat and associated orders are resolved. Exact NinjaTrader steps, order/stop races, acknowledgements, rejection/disconnection handling, and recovery remain open under OD-07. Acceptance of the intended response is not proof that platform behavior has been verified.
4. Record the pre-entry ceiling, planned risk, actual fill/original stop, fees, post-fill exit allowance, assessed risk, overshoot amount, exit fills, and reconciliation outcome. The filled entry counts as an attempt even when promptly exited for overshoot; realized accounting follows the accepted V1-RISK-02 gross/net convention and V1-DAILY-01 net Loss-R cutoff.

This policy cannot guarantee that realized loss stays within the ceiling. The original structural stop and fill/order status still require the protection workflow; a risk calculation does not establish that protection is working or that the position remains open.

**Accepted stop-distance policy — starting V1:**

1. Use no additional stop-distance filter. Structure determines invalidation; apply the accepted minimum buffer and outward execution-tick rounding.
2. At one NES, the combined percentage-and-dollar risk ceiling determines affordability. Skip setups whose total planned risk exceeds it; do not move the structural stop to make them qualify.
3. Record initial stop distance in index points, execution ticks, and ATR multiples for research. Use the accepted last-completed-bar ES ATR input at entry and identify the price distance/ATR source explicitly; ATR remains descriptive, not an entry permission or stop-placement rule. Missing ATR cannot be treated as a valid ratio; indicator/data handling remains under OD-05.
4. Consider any later distance filter only after replay evidence review through an explicit revision. Do not introduce an ad hoc ATR/point/tick maximum for an individual opportunity.

**OD-09 policy decisions closed 2026-10-10:** starting risk limits, equity update/verification, fee/slippage inputs, overshoot response, and no separate stop-distance filter are agreed. Actual-entry risk-overshoot handling is agreed; exact exit/protection/recovery implementation remains under OD-07. Equity-source verification, pending-deposit/withdrawal treatment, and no double allocation are agreed; actual funding and reconciliation evidence still must be obtained/applied under that policy. Session-start/current-equity comparison, profits/losses and deposit/withdrawal treatment, and no reset after losses are now accepted. The fee-input and starting replay/simulation slippage policies are accepted; the $1.88 starting NES fee input and standard connection are recorded, while actual equity reconciliation evidence, live fee reconciliation, and live slippage validation remain required. Gross/net realized accounting and net Loss-R cutoff policy are agreed; OD-10 policy decisions are closed.

At the starting configuration, $15 is the effective maximum estimated planned total risk per attempt; it is not a $15 price-risk allowance plus additional costs. For a hypothetical combined fee/slippage allowance of $3, the remaining price-risk allowance is $12, equivalent to 24 NES index points at one contract. That $3 is arithmetic illustration only, not an accepted cost estimate. Replay should measure valid-setup exclusions under the cap before considering changes; do not raise it ad hoc to admit a particular trade.

Record verified session-start and current allocated equity, their sources/timestamps, the smaller pre-entry equity basis, percentage and dollar ceilings, effective minimum, planned entry/stop distance, verified round-trip fee input/source/date, separate $1.50 starting replay/simulation slippage allowance, total planned risk, and pass/skip outcome. OD-09 policy closure does not establish actual funding, verified platform behavior, or live execution validation, and does not freeze V1.0. Retain equity/fee reconciliation and slippage review evidence in the risk record; resolve operational execution/recovery under OD-07 and apply the accepted gross/net accounting under closed OD-10.

### V1-DAILY-01 — Net realized losing-trade R budget

**Status: Net losing-trade R cutoff agreed on 2026-10-10; OD-10 policy decisions closed. Remaining-budget guard agreed on 2026-10-10; one-position/pending-entry policy agreed; OD-11 policy decisions closed 2026-10-10.**

For each completed filled attempt, let `r_i` be its net realized trade R under V1-RISK-02:

`Loss-R used = sum(max(0, -r_i))`

Stop taking new trades when **Loss-R used >= 3.00**. Equivalently, the signed sum of negative trade Rs is **<= -3.00**. The cutoff is reached at three, not only after exceeding three. Winners do not restore this budget. Partial losses consume their actual net R; this is not simply a count of three stopouts. A gross breakeven or small gross winner can be a net loser after fees and therefore consume this budget. This revises the earlier gross losing-trade R basis; the 3.00 threshold and no replenishment by winners remain unchanged.

| Completed sequence of net trade Rs | Cumulative net R | Net Loss-R used | New entries? |
| --- | ---: | ---: | --- |
| +4, -1, -1 | +2 | 2 | Potentially, subject to all other rules |
| +4, -1, -1, -1 | +1 | 3 | No |
| -0.5, -0.75, -1, -0.75 | -3 | 3 | No |
| -1.2, -1, -0.8 | -3 | 3 | No |

With R0 = $5, a $5 actual-fill price loss and $1.88 round-trip fees give net P&L = -$6.88, net trade R = -1.376, and 1.376 Loss-R used. The planning slippage allowance is not subtracted again. Three such losses would consume 4.128 Loss-R; fees mean three nominal price-risk stopouts need not equal the 3.00 budget.

**Accepted remaining-budget guard — 2026-10-10:**

1. Before entry, record `Remaining Loss-R = 3.00 - net Loss-R already used`. No entries are permitted once used Loss-R reaches/exceeds 3.00.
2. Let P be the positive planned one-NES entry-to-original-rounded-stop price risk in dollars, F the applicable round-trip transaction fee input, and S the accepted $1.50 replay/simulation planning slippage allowance. Calculate:

   `Assessed planned Loss-R = (P + F + S) / P`

   P is the prospective price-risk denominator for this admission check; actual R0 is still determined from the entry fill under V1-RISK-02. Require valid, reconciled inputs; no valid positive denominator means no entry.

3. Permit entry only if assessed planned Loss-R does not exceed the remaining budget and the separate V1-RISK-03 dollar-risk check passes. Equality is allowed. With P = $5, F = $1.88, and S = $1.50, assessed planned Loss-R is 1.676; if 1.50 remains, skip the entry.
4. Immediately after the fill, recheck against the remaining budget recorded before entry:

   `Assessed post-fill Loss-R = (actual R0 + applicable round-trip fees + $1.00 protective-stop exit allowance) / actual R0`

   The actual fill already captures entry slippage, so remove the $0.50 entry allowance. If the post-fill assessed loss strictly exceeds the recorded remainder, initiate the coordinated exit/protection procedure and verify flat position/resolved orders, as in V1-RISK-03. A pass on the dollar-risk check does not override failure of this Loss-R check, or vice versa. Exact NinjaTrader implementation and recovery remain under OD-07.
5. Record the pre-entry used/remaining budget, P/F/S inputs and assessed ratio, dollar-risk result, actual R0, post-fill fees/exit allowance and ratio, and pass/skip/exit outcome. Never tighten structural invalidation or increase the budget merely to admit the attempt.

These are admission/reassessment checks, not guarantees against realized overshoot. Do not charge the estimated assessed ratio to the realized daily budget: update that budget from the completed attempt's actual net trade R under V1-RISK-02. Filled overshoot exits count as attempts. The one-position/pending-entry policy is accepted under V1-SCOPE-03; OD-11 policy decisions are closed. Exact platform execution/recovery remains under OD-07.

Because each trade has its own R0, summed trade R is a normalized training measure, not a fixed-dollar session-loss limit.

### V1-DAILY-02 — Session metrics

**Status: Agreed tracking concept; formulas proposed.**

Track net realized R, net Loss-R used, peak cumulative net realized R, current drawdown from that peak, trade count, and full-stopout count.

`Cumulative R = sum(net realized trade R_i)`  
`Peak R = max(0, all completed-trade cumulative R values)`  
`Current realized drawdown R = Peak R - current cumulative R`

Keep realized session drawdown distinct from intratrade unrealized drawdown. Peak or drawdown metrics are descriptive in V1; no additional cutoff has been agreed for them.

## 10. Failed breakouts and reentry

### V1-REENTRY-01 — Two attempts at one thesis

**Status: Filled-attempt counting and starting directional thesis identity/reset agreed on 2026-10-10; OD-12 CLOSED (policy decisions).**

Assign the PB-TREND RTH-date/direction thesis ID and a separate selected reference ID before the first attempt. The first fill in that direction/date is attempt 1; a qualifying later fill in that direction/date is attempt 2. Do not make attempt 3 in that direction on the same RTH trading date.

A stopout means that attempt failed; it does not automatically invalidate the directional session thesis. Reassess the regime and identify fresh valid entry/stop structure before reentry. An unchanged bullish opinion is not sufficient by itself.

**Accepted filled-attempt counting policy:**

1. An attempt counts when its entry receives its first fill. Preserve that fill's time, order ID, thesis ID, and assigned attempt number.
2. Any filled entry counts regardless of outcome, including an immediate risk-overshoot exit, manual exit, or profitable exit. A single filled attempt is not counted again because its order status changes.
3. A confirmed unfilled cancellation, rejection, or expiration does not consume an attempt. Record it as an order event.
4. If cancellation races with a fill, the fill determines whether an attempt occurred. Uncertain status blocks another entry until reconciled under V1-SCOPE-03/OD-07; do not infer no fill merely from a cancellation request.
5. Canceling or replacing an unfilled order does not reset the thesis's existing attempt count. Each separately filled reentry consumes the next attempt.

**Accepted starting thesis identity and reset policy:**

1. Define one long thesis and one short thesis per RTH trading date for PB-TREND. Use an identity such as `PB-TREND / Chicago RTH date / LONG` or `... / SHORT`; record actual ES/NES contract identities separately. This identity scheme does not resolve contract selection/roll handling under OD-04.
2. All qualifying references in the same direction share that thesis's two-filled-attempt cap. A new swing, consolidation box, or auction reference does not create a fresh allowance. The cap covers all accepted entry families within PB-TREND.
3. Keep reference IDs separately for analysis. Changing setup family, reference, regime score, or direction does not erase an existing thesis's count. Returning to a previously traded direction resumes its existing count for that date.
4. Reset counts at the next RTH trading date. Every entry still requires current permission, fresh qualifying structure, sufficient remaining net Loss-R budget, the dollar-risk check, and V1-SCOPE-03 position/order reconciliation. A date reset does not override holiday/session/operational restrictions.

Example: long attempt 1, short attempt 1, then another qualifying long is long attempt 2. A third long is prohibited that date, even if it uses a different reference or setup family. Starting V1 permits at most two long and two short filled attempts per RTH date; daily risk guards can stop entries earlier. This is a conservative starting grouping policy, not a claim that every new reference represents the same market opportunity. Finer reference-specific thesis definitions require later research and an explicit revision.

OD-12 policy decisions are closed. Exact order-status verification and fill/cancel recovery remain under OD-07; the acceptance does not establish a live-verified implementation.

## 11. Confirmed-pivot trailing

### V1-STOP-04 — Confirmation and structural trail

**Status: Agreed core rule and complete OD-13 design policy; operational mapping/order verification remains open under OD-04/07.**

For a **long**:

1. Keep the initial stop while price develops an impulse and pullback.
2. Identify the preceding swing high and the candidate higher low.
3. The higher low becomes confirmed when price subsequently penetrates the preceding swing high.
4. Move the protective stop at least **0.50 index points below the mapped confirmed higher low**, rounding downward under V1-STOP-02.
5. Repeat for later confirmed higher lows, subject to the stop never being loosened.

For a **short**, mirror the sequence: a candidate lower high becomes confirmed when price penetrates the preceding swing low; trail at least **0.50 index points above the mapped lower high**, rounding upward under V1-STOP-02.

The accepted minimum buffer is **0.50 index points**, one NES tick for a tick-aligned mapped pivot; apply outward rounding under V1-STOP-02. Confirmation requires continuation beyond the reference, not merely a touch. V1-STOP-06 specifies accepted trailing-pivot identification. V1-STOP-07 specifies accepted higher-low/lower-high comparison. V1-STOP-08 specifies accepted continuation-reference pairing. V1-STOP-09 specifies accepted candidate replacement/invalidation. V1-STOP-10 specifies accepted continuation-confirmation event order. V1-STOP-11 accepts stop-modification timing; OD-13 is closed.

**Long example (assumes level mapping yields the prices shown; does not define the mapping policy):**

| Event | Price / action |
| --- | --- |
| Entry | 6000.0 |
| Original mapped invalidation / stop | 5994.5 / 5994.0; R0 = $3.00 |
| Rally establishes swing high A | 6010.0 |
| Pullback establishes candidate higher low | 6005.0 |
| Continuation penetrates A | 6010.5 |
| Candidate becomes confirmed | Higher low at 6005.0 |
| New stop trigger | 6004.5 |

The trigger is 4.5 points above entry; an actual exit fill at 6004.5 would yield $2.25 gross, or +0.75R. This is an intended trigger outcome, not a guaranteed profit.

**Short example (same mapping assumption):** entry 6000.0, original mapped invalidation 6005.5, original stop 6006.0, swing low 5990.0, candidate lower high 5995.0. Price subsequently trades at 5989.5: trail to 5995.5, 0.50 points above the mapped confirmed lower high.

### V1-STOP-05 — Structure rather than a P&L milestone

**Status: Agreed.**

Do not move the stop solely because price reaches +1R, breakeven, or another arbitrary profit level. Do not use fixed-R or mechanical ATR trailing in V1. A confirmed structural pivot can justify a stop still below entry for a long, or above entry for a short; the confirmation does not have to lock in profit.

**Rationale:** The market must create the structural reason to tighten the stop. A normal pullback can occur after a +1R excursion.

### V1-STOP-06 — Trailing-pivot identification

**Status: Agreed on 2026-10-10; OD-13 closed.**

Reuse V1-ENTRY-05's completed current-RTH ES 5-minute strict three-bar pivot method for trailing-pivot identification. A center-bar high must strictly exceed both adjacent highs; a center-bar low must be strictly below both adjacent lows. Equal neighboring extremes do not qualify for the corresponding pivot. Recognize each pivot only after its right-hand bar closes.

For both the continuation reference and the pullback candidate, require the pivot's center bar to begin at or after the actual entry fill timestamp. This time restriction applies to the center bar; the three-bar identification still uses its immediately adjacent completed current-RTH bars. Do not substitute order-submission time for fill time or use an entry-bar center that began before an intrabar fill.

For example, an entry fill at 09:12 makes the 09:15 bar the earliest eligible center bar for a trailing pivot. Its recognition requires completion of the right-hand bar. Record center-bar start time, recognition time, ES price, and actual fill time. Both reference and candidate must be recognized before they can be used prospectively in trailing decisions.

Recognition alone does not authorize a stop move. V1-STOP-04's separate continuation requirement and 0.50-point minimum trailing clearance and outward rounding remain in force. V1-STOP-07 now resolves higher-low/lower-high comparison. V1-STOP-08 now resolves continuation-reference pairing. V1-STOP-09 accepts candidate replacement/invalidation. V1-STOP-10 resolves continuation event order/same-bar ambiguity. V1-STOP-11 accepts modification timing; OD-13 is closed. ES-to-NES level handling remains separately open under OD-04/07.

### V1-STOP-07 — Higher-low / lower-high comparison

**Status: Agreed on 2026-10-10; OD-13 closed.**

| Candidate | Accepted comparison requirement |
| --- | --- |
| First higher low, long | Strictly above the original ES structural-invalidation reference |
| Later higher low, long | Strictly above the ES pivot last used to tighten the protective stop |
| First lower high, short | Strictly below the original ES structural-invalidation reference |
| Later lower high, short | Strictly below the ES pivot last used to tighten the protective stop |

Compare unbuffered ES structure prices rather than NES stop triggers. Equal prices do not qualify. The first comparison reference is the recorded original opposite swing pivot for swing/auction-reference entries, or the original opposite box boundary for consolidation entries. Preserve that original ES reference with the entry record; do not substitute the buffered NES stop or entry price.

A qualifying comparison only makes a recognized pivot a candidate. V1-STOP-04's continuation confirmation, executable NES mapping, and a protective-stop update that tightens protection are still required. Advance the comparison reference only after the protective-stop update is accepted. An unconfirmed candidate, an unsubmitted modification, a rejected modification, or a mapped stop that does not tighten protection does not advance it. Until the first accepted tightening, retain the original structural-invalidation reference for comparison.

After an accepted tightening, record the ES pivot used, the NES stop trigger, and update acceptance evidence. Later pivots do not rewrite the original invalidation or R0. V1-STOP-08 records accepted continuation-reference pairing. V1-STOP-09 accepts candidate replacement/invalidation. V1-STOP-10 resolves continuation event order/same-bar ambiguity. V1-STOP-11 accepts modification timing; OD-13 is closed; exact mapping and order-response handling remain under OD-04/07.

### V1-STOP-08 — Continuation-reference pairing

**Status: Agreed on 2026-10-10; OD-13 closed.**

| Candidate | Accepted continuation reference |
| --- | --- |
| Long higher low | Most recent eligible recognized swing high formed before the candidate low, with its price strictly above that low |
| Short lower high | Most recent eligible recognized swing low formed before the candidate high, with its price strictly below that high |

At candidate recognition, select the reference from information already available. Apply V1-STOP-06's identification, recognition, and post-entry center-bar restriction to both pivots. Use center-bar timestamps to determine formation order and recency; the reference's center bar must precede the candidate's center bar. The reference must already be recognized when the pair is selected. The candidate must satisfy V1-STOP-07's comparison condition.

Freeze the candidate/reference pair. Later swings do not retarget that candidate. If no eligible reference exists at candidate recognition, that candidate cannot authorize trailing; do not retroactively supply a later reference. Record both pivot prices, center/recognition times, pair-selection time, and the comparison reference in force at selection.

Pair selection does not itself confirm continuation or authorize a stop modification. V1-STOP-09 accepts candidate replacement/invalidation. V1-STOP-10 accepts the recognition/activation-before-confirmation sequence and excludes retrospective penetration. V1-STOP-11 accepts modification timing; OD-13 is closed. NES mapping and order-response handling remain separate OD-04/07 decisions.

### V1-STOP-09 — Unconfirmed-candidate replacement and invalidation

**Status: Agreed on 2026-10-10; OD-13 closed.**

| Situation | Accepted handling |
| --- | --- |
| Tracking | Keep one active unconfirmed candidate/reference pair |
| New qualifying candidate | Replace the active candidate only with a strictly higher low for longs or strictly lower high for shorts |
| Replacement | New candidate independently satisfies identification, comparison, and pairing; freeze its own pair |
| Equal or less protective candidate | Retain the active candidate |
| Candidate breached | Discard if ES trades strictly below its low for a long, or strictly above its high for a short; a touch alone does not invalidate |
| After discard | Wait for a newly recognized qualifying candidate; do not revive a discarded or replaced pair |

Apply V1-STOP-06/07/08 independently to a proposed replacement using evidence available at its recognition. Compare the new candidate's unbuffered ES pivot price with the active candidate's price when testing whether it is strictly more protective. A new pivot that lacks an eligible continuation reference does not replace a valid active pair. If no pair is active, a newly recognized candidate must still satisfy all three rules before becoming active.

Replacing or discarding a candidate leaves the existing protective stop and V1-STOP-07 comparison anchor unchanged. The anchor advances only after an accepted stop tightening. Candidate invalidation alone does not authorize a discretionary position exit or loosening/removing protection. Do not restore an older pair when the replacement later fails; wait for a newly recognized qualifying candidate.

Record candidate identity, frozen continuation reference, activation/replacement/discard time, replacement eligibility, and the observed ES breach when applicable. V1-STOP-10 resolves exact continuation event order, ambiguity, and the transition from unconfirmed to continuation-confirmed. V1-STOP-11 accepts stop-modification timing; OD-13 is closed. Order acknowledgement/rejection and connection-loss handling remain separate OD-07 decisions.

### V1-STOP-10 — Continuation-confirmation event order

**Status: Agreed on 2026-10-10; OD-13 closed.**

| Situation | Accepted handling |
| --- | --- |
| Candidate recognized and pair activated | Only subsequent observed ES price events can confirm continuation |
| Long confirmation | After activation, observe ES at/below the frozen reference high, then strictly above it |
| Short confirmation | After activation, observe ES at/above the frozen reference low, then strictly below it |
| Penetration before activation | Does not count retrospectively |
| Replacement candidate | Restart confirmation tracking for its newly frozen pair |
| Candidate breach occurs first | Discard the pair; later continuation cannot rescue it |
| Event order cannot be established | Discard the affected pair and retain existing protection |

Use the observed event sequence. Both the approach-side observation and subsequent strict penetration must occur after pair activation. The bar/price event used to recognize a pivot cannot be reused retrospectively as a post-activation confirmation event. Preserve event ordering when timestamps alone do not establish sequence; do not invent order among indistinguishable events.

For example, a pair activated at 09:25 cannot use a reference penetration at 09:23. It needs the qualifying approach-then-penetration sequence after activation. A candidate recognized while ES is already beyond its frozen continuation reference is not automatically confirmed: it still needs the accepted post-activation sequence. Replacement restarts this evidence requirement even if the old pair had an approach-side observation.

A bar's high and low alone may not establish which boundary was crossed first. If available evidence cannot establish the required order, discard that pair, preserve the reason in the record, and wait for a newly recognized qualifying candidate under V1-STOP-09. Do not manufacture confirmation from a bar that contains both candidate breach and reference penetration with unresolved order.

When an active pair satisfies the ordered sequence before any candidate breach, mark it continuation-confirmed and record the approach observation, penetration observation, and confirmation time/sequence. This permits evaluation of a protective-stop tightening; it does not itself prove that an amendment was submitted or accepted. V1-STOP-11 accepts modification timing, pre-submission validity checks, one pending amendment, and reconciliation when conditions change during acknowledgement; OD-13 is closed. Exact ES/NES mapping, data/event-order verification, platform procedures, and order failures remain separate OD-04/05/07 implementation decisions.

### V1-STOP-11 — Stop-modification timing and acknowledgement

**Status: Agreed on 2026-10-10; OD-13 closed.**

| Situation | Accepted design policy |
| --- | --- |
| Continuation confirmed | Evaluate and submit tightening promptly, intrabar; do not wait for another 5-minute close |
| Before submission | Verify position remains open, candidate has not been breached, and mapped NES stop is valid and strictly tighter |
| Checks fail | Discard proposed update; retain existing protection and comparison anchor |
| Amendment submitted | Freeze confirmed pair; allow only one stop amendment awaiting acknowledgement |
| Protection during amendment | Use a workflow that preserves protection; never cancel existing stop in advance merely to prepare replacement |
| Tightening accepted | Verify working stop, advance comparison anchor, retire pair, and resume tracking newly recognized candidates |

Use V1-STOP-02/04's 0.50-point minimum trailing clearance and outward rounding beyond the mapped candidate under the ES-to-NES mapping policy once that policy is resolved. Evaluate validity on the executable NES instrument under the eventual platform/broker procedure. A theoretical ES confirmation alone does not establish that a valid, tighter NES order is available. Confirmation time, pre-submission verification, amendment submission, and acceptance are distinct events; record them separately.

While an amendment awaits acknowledgement, keep the confirmed pair frozen and do not send a competing second stop amendment. Do not treat submission as acceptance or advance the comparison anchor prematurely. A pending amendment is not proof that either the old or proposed stop is currently working; the operational workflow must verify actual protection. This rule specifies the required protection outcome rather than asserting unverified NinjaTrader/broker behavior.

If the position exits, the candidate is breached while acknowledgement is pending, or the amendment is rejected or uncertain, reconcile actual position and orders before another amendment. Do not assume that the prior stop remains working after a failure or race. Detailed recovery procedures, acknowledgement timeouts, fill/cancel races, and connection-loss handling remain under OD-07. Advance V1-STOP-07's comparison anchor only after a verified accepted tightening for the open position. Preserve original invalidation and R0.

This closes OD-13's intended timing and state-transition design. It does not resolve ES-to-NES mapping, tick rounding, instrument alignment, data/event-order verification, or operational platform procedures under OD-04/05/07, and does not freeze V1.0.

## 12. Exits

### V1-EXIT-01 — No fixed profit target

**Status: Agreed.**

Do not place a fixed take-profit order, including at +3R. Let realized R emerge from structural stop management and the required session exit.

### V1-EXIT-02 — Normal and session exits

**Status: Agreed stop-management approach and no-overnight requirement.**

The normal exit is execution of the protective initial or trailed stop. Close any remaining position at the agreed session flatten cutoff. Record actual fills, not only stop triggers.

### V1-EXIT-03 — Regime changes and manual intervention

**Status: Open-position regime-change policy agreed on 2026-10-10; manual/operational emergency scope remains open under OD-14.**

1. A change to transition, balance, or opposite directional permission does not itself trigger an exit of an existing position.
2. Continue managing the position under its existing structural stop and accepted continuation-confirmed trailing rules. Trailing does not require the regime score to retain entry permission; all trailing evidence, candidate validity, mapping, and order/protection checks still apply.
3. Never loosen the stop because the score changes. Record the new scheduled regime assessment while the position remains open.
4. New entries require current directional permission. Any direction change still requires closing and reconciling the existing position first, then independently qualifying the new entry under V1-SCOPE-03; it is not an automatic reversal instruction.
5. Accepted dollar-risk/Loss-R overshoot exits and the eventual session-flatten deadline retain priority. Missing data, protection failures, and other operational emergencies require their separate policy/procedure; this regime rule does not authorize ignoring them.

The regime score governs entry permission; structural rules govern ordinary position management. This accepts management through valid regime changes, not a missing-data or unverified-protection rule. UNKNOWN/no-entry and data/protection restrictions remain in force.

No “climax,” “exhaustion,” or discretionary balance exit from historical drafts is automatically adopted. Define authorized manual and operational emergency exit scope under OD-14 and exact implementation/recovery under OD-07 before freezing V1.0. Record every intervention and reason.

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
- [ ] Pre-entry assessed Loss-R fits recorded remaining budget and the separate dollar-risk check passes (DAILY-01/RISK-03).
- [ ] Entry occurs on valid penetration under the agreed execution procedure.
- [ ] Immediately recheck actual-fill dollar risk and assessed Loss-R; use coordinated exit/protection if either accepted ceiling is exceeded.

### During the position

- [ ] Verify protective stop acceptance.
- [ ] Track candidate pivots and confirmation references.
- [ ] Trail only on confirmed structure, applying minimum 0.50-point clearance beyond the mapped pivot and outward execution-tick rounding.
- [ ] Do not loosen the stop, add size, or install a fixed profit target.
- [ ] Continue structural protection/qualifying trailing through regime changes; record assessments (EXIT-03).
- [ ] Follow the eventual authorized operational-exit procedure and session cutoff; exact policies remain open.

### After exit / end of session

- [ ] Reconcile actual fills and record outcome separately from execution grade.
- [ ] Update Loss-R used from completed net trade R, net R, peak/drawdown, and attempt counters.
- [ ] At Loss-R used >= 3, end new trading for the session.
- [ ] Capture screenshots and post-trade observations.
- [ ] Finish the session flat and remove outstanding entry orders.

## 16. Open decision register

Resolve the remaining open items explicitly before freezing V1.0. OD-02, OD-03, OD-06, OD-08, OD-09, OD-10, OD-11, OD-12, OD-13, and OD-16 are closed; OD-04 and OD-05 have accepted subdecisions but remain open. A later answer should cite the OD ID and any affected rule IDs.

| ID | Decision needed | Affected rules |
| --- | --- | --- |
| OD-01 | RTH analytical window and holiday/shortened-session no-entry policy accepted; latest entry, flatten deadline, and operational calendar procedure remain open | SESSION-03, EXIT-02 |
| OD-02 | CLOSED 2026-10-10: all six factor definitions, equal-weight sum, aggregate thresholds, regime/entry permissions, and UNKNOWN/no-entry policy accepted | REGIME-01/03/04/05/06/07/08/09 |
| OD-03 | CLOSED 2026-10-10: assess first at 08:50 and every completed 5-minute bar; use latest scheduled assessment for intrabar entries; missing required evidence means UNKNOWN/no entry | REGIME-02 |
| OD-04 | ES analysis / NES execution and prior/overnight/RTH windows accepted; exact expiries, rollover alignment, cross-instrument level handling, and timestamp boundary/data-completeness policies remain open | INSTRUMENT-01, CONTEXT-02/03 |
| OD-05 | VWAP anchor, NinjaTrader Volume Profile (68%, one ES tick/row, tick resolution subject to availability), and ATR(13) Wilder on completed full-session ES 5-minute bars with no 08:30 reset accepted; Order Flow VWAP tick/session implementation and 08:30–15:00 template accepted; VWAP operational template/data/parity verification, profile reproducibility/data policy, and ATR template/gap/seed/warm-up remain open | CONTEXT-03/04/05/06 |
| OD-06 | CLOSED 2026-10-10: swing/pullback selection, consolidation formation/lifetime/replacement, and eligible auction references with approach-side and known structural-invalidation requirements accepted | ENTRY-01/05/06/07/08/09/10 |
| OD-07 | Stop rounding away from structure accepted under STOP-02; entry trigger price/rounding/buffer, mapping/order type, protective workflow, fills/rejections/disconnection response remain open | ENTRY-02, STOP-02/11 |
| OD-08 | CLOSED 2026-10-10: initial and trailing minimum clearance 0.50 index points, outward execution-tick rounding, and strategy/instrument-family configuration accepted; supersedes earlier 1.00-point NES trailing buffer | STOP-01/02/04/06/11 |
| OD-09 | CLOSED (policy decisions) 2026-10-10: $3,500 allocation, 0.50%/$15 combined cap, equity update/verification and pending/shared-capital policy, $1.88 starting NES Free-plan standard-connection round-trip fees, $1.50 replay/simulation slippage, actual-entry overshoot response, and no separate stop-distance filter accepted. Funding/equity/fee reconciliation and live slippage review evidence remain required; operational exit/protection/recovery remains under OD-07; realized accounting follows closed OD-10 | RISK-01/03 |
| OD-10 | CLOSED (policy decisions) 2026-10-10: fixed price-risk R0, both gross/net reporting, actual-fill P&L minus transaction fees once, documented replay/simulation fee model, no second slippage subtraction, non-trade charges in allocation ledger, and daily sum of negative net trade Rs >= 3.00 accepted. NinjaTrader template/account reconciliation remains required | RISK-02, DAILY-01 |
| OD-11 | CLOSED (policy decisions) 2026-10-10: net-cost-aware pre-entry/post-fill remaining-budget guard, separate dollar gate, equality allowed/strict overshoot coordinated exit, one open one-NES V1 position, at most one active entry while flat, replacement only after confirmed resolution, flat/order/accounting reconciliation before another entry, uncertain-status no-entry, and no automatic attempt reset on direction change. Exact execution/recovery remains under OD-07 | DAILY-01, SCOPE-03 |
| OD-12 | CLOSED (policy decisions) 2026-10-10: first-fill/outcome-independent counting; confirmed unfilled events do not consume attempts; fill/cancel reconciliation; one long and one short PB-TREND thesis per RTH date, separate reference IDs, two filled attempts per direction across all references/families, no intraday reset from score/reference/direction changes, and reset next RTH date. Current qualification/risk/position rules still apply; order verification/recovery under OD-07 | ENTRY-04, REENTRY-01 |
| OD-13 | CLOSED 2026-10-10: trailing identification/comparison/pairing/tracking, ordered continuation confirmation, prompt intrabar tightening checks, single pending amendment, verified acceptance, and reconciliation policy agreed. Operational mapping/platform recovery remains under OD-04/07 | STOP-04/06/07/08/09/10/11 |
| OD-14 | Open-position regime-change policy accepted 2026-10-10: transition/balance/opposite permission alone does not exit; continue verified structural protection and qualifying continuation trailing without an entry-score requirement, never loosen, record assessments, retain entry/risk/session priorities. Authorized manual/operational emergency scope remains open; exact execution/recovery under OD-07 | EXIT-03 |
| OD-15 | Final execution rubric and practical minimum forensic fields | REVIEW-02/03 |
| OD-16 | CLOSED 2026-10-10: primary 5-minute ES chart accepted | CONTEXT-01 |

**Study priority:** scoring definitions and timing are agreed. Entry-swing pivot identification is also agreed. Swing-reference selection and the subsequent confirmed pullback requirement are agreed. Pullback-pivot selection is also agreed. Consolidation formation is agreed. Box lifetime/replacement is also agreed. Auction-reference qualification is agreed and OD-06 is closed. Trailing-pivot identification and the post-fill center-bar restriction are agreed. Higher-low/lower-high comparison and advancement only after accepted tightening are also agreed. Continuation-reference pairing is agreed. Candidate replacement/invalidation is agreed. Continuation event ordering and confirmation transition are agreed. Stop-modification timing is agreed and OD-13 is closed. Initial/trailing buffer and outward rounding are agreed and OD-08 is closed. Combined percentage-and-dollar entry-risk ceiling framework is agreed. Starting allocation/numeric limits are agreed. Equity-update policy is agreed. Fee-input policy is agreed. Starting replay/simulation slippage allowance and measurement policy are agreed. Standard connection and the $1.88 starting round-trip fee input are recorded. Equity-verification policy is agreed. Actual-entry risk-overshoot policy is agreed. No separate stop-distance filter is accepted for starting V1; OD-09 policy decisions are closed. Gross/net reporting and daily net Loss-R accounting are agreed; OD-10 policy decisions are closed. Remaining-budget guard and post-fill recheck are agreed. One-position/pending-entry policy is agreed; OD-11 policy decisions are closed. Filled-attempt counting is agreed. Starting directional thesis identity/reset is agreed; OD-12 policy decisions are closed. Open-position regime-change policy is agreed. Next resolve manual/emergency exit scope under OD-14, then mapping/protection/order mechanics and session boundaries. Funding/reconciliation and execution-validation evidence remain required. These are gaps to close, not invitations to add V2 complexity.

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
| Balance | Non-permission regime at the accepted score center (-1 through +1); components preserve conflicting evidence |
| Penetration | Price trading beyond an identified level, rather than only touching it; execution source pending |
| Structural invalidation | Price location that contradicts the specific breakout thesis |
| Confirmed pivot | Candidate higher low/lower high validated by continuation beyond the preceding swing extreme |
| Learning lot | One NES contract in V1 |
| R0 / 1R | Fixed original price-risk dollars for that individual trade |
| Loss-R used | Sum of magnitudes of negative net realized trade Rs; wins do not offset it |
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
| V1-draft-43 | 2026-10-10 | Accepted open-position management through transition/balance/opposite regime permission: no score-only exit, continue valid structural protection/continuation trailing without entry-score requirement, never loosen, record assessments, and retain risk/session priorities. Manual/emergency scope remains open under OD-14 and exact procedure under OD-07. |
| V1-draft-42 | 2026-10-10 | Accepted one long/one short PB-TREND thesis per RTH date, each with two filled attempts across references/setup families; reference IDs separate, no intraday reset from reference/score/direction changes, next-RTH-date reset, and all qualification/risk guards retained. Closed OD-12 policy decisions and aligned ENTRY-04/quick reference. |
| V1-draft-41 | 2026-10-10 | Accepted first-fill attempt counting regardless of exit/outcome; confirmed unfilled cancellations/rejections/expirations recorded without consuming attempts, fill/cancel race reconciliation, and no count reset from unfilled replacement. Two-attempt cap retained; thesis identity/reset remain open under OD-12. |
| V1-draft-40 | 2026-10-10 | Accepted one open one-NES V1 position, at most one active entry while flat, confirmed resolution before replacement, flat/order/equity/Loss-R/attempt reconciliation before new entries, uncertain-status entry block, and independently qualifying direction changes without automatic attempt reset. Closed OD-11 policy decisions; platform coordination remains under OD-07. |
| V1-draft-39 | 2026-10-10 | Accepted net-cost-aware remaining-budget guard: (planned price risk + fees + $1.50 allowance)/planned price risk must fit remaining 3.00 Loss-R budget; actual R0/fees/$1.00 exit-allowance recheck and strict-overshoot coordinated exit, equality allowed. Separate dollar gate also required; one-position rule remains open under OD-11. |
| V1-draft-38 | 2026-10-10 | Accepted gross/net reporting with fixed price-risk R0, actual-fill P&L minus transaction fees once, documented replay/simulation fee model, no second slippage subtraction, and daily negative-net-R sum >= 3.00. Closed OD-10 policy decisions; revised summary/examples/metrics and retained net-cost-aware remaining-budget decision under OD-11. |
| V1-draft-37 | 2026-10-10 | Accepted no separate stop-distance filter in starting V1: structure/buffer/rounding and one-NES combined risk gate determine eligibility; record points/ticks/ATR distance descriptively and require evidence/revision for later filters. Closed OD-09 policy decisions while retaining funding/cost/slippage evidence and operational/accounting work. |
| V1-draft-36 | 2026-10-10 | Accepted immediate post-fill risk check using actual fill/original structural stop, applicable round-trip fees and $1.00 exit allowance (entry allowance removed); strict ceiling overshoot prompts coordinated exit, flat/order verification, and attempt/evidence recording. Platform procedure remains open under OD-07. |
| V1-draft-35 | 2026-10-10 | Accepted funded-allocation ledger reconciled to NinjaTrader records before each session/changes before entries, actual results and charges, exclusion of pending deposits, immediate withdrawal reservation without double subtraction, no shared-capital double counting, and unreconciled-equity no-entry rule. Actual funding evidence, overshoot, and validation remain pending. |
| V1-draft-34 | 2026-10-10 | Recorded owner-selected standard NinjaTrader connection and $1.88 starting one-NES round-trip fee input without optional routing add-ons; fees plus replay/simulation slippage total $3.38. Retained before-live charge reconciliation/refresh and remaining equity/overshoot/accounting decisions. |
| V1-draft-33 | 2026-10-10 | Verified owner-provided NES Free-plan fee row: $0.36 exchange/NFA + $0.19 clearing + $0.39 commission = $0.94/side, $1.88 round trip. Documented conditional $3.38 base fees plus slippage; account-specific transaction add-ons remain unverified. |
| V1-draft-32 | 2026-10-10 | Recorded owner-selected NinjaTrader Brokerage Free plan and checked published $0.39/side e-Nano commission ($0.78 round trip, commission only). Complete NES transaction cost/account routing remains unverified; preserved unknown-fee no-entry rule and remaining OD-09 decisions. |
| V1-draft-31 | 2026-10-10 | Accepted replay/simulation allowance of two NES entry ticks plus four protective-stop exit ticks ($1.50 total), counted once separately from planned price and verified fees; separate adverse entry/exit measurement and review before a live baseline. Actual fee, equity verification, overshoot, live validation, and realized accounting remain open. |
| V1-draft-30 | 2026-10-10 | Accepted broker-specific one-NES round-trip fee input including commissions/exchange/clearing/regulatory charges, amount/source/date recording, refresh on pricing changes, separate slippage input, and unknown-fee no-entry rule. Actual fee amount, slippage policy, and realized accounting remain open. |
| V1-draft-29 | 2026-10-10 | Accepted session-start verified allocated-equity snapshot and smaller-of-session-start/current-equity pre-entry basis; losses/withdrawals can reduce the cap intraday, gains/deposits wait until next session, and no reset to $3,500 after losses. Retained $15 cap and one NES; verification/shared-fund/cost details remain open. |
| V1-draft-28 | 2026-10-10 | Accepted $3,500 starting futures allocation, 0.50% percentage ceiling, and $15 fixed-dollar cap including estimated fees/slippage; initial effective ceiling $15. Retained one NES; equity snapshot/update and cost-input policies remain open under OD-09/10. |
| V1-draft-27 | 2026-10-10 | Accepted combined percentage-and-dollar risk-ceiling framework for one NES, with estimated fee/slippage affordability and structural-stop-first skip policy. Added V1-RISK-03; numeric limits/equity/cost inputs remain open, and R0/daily accounting is unchanged. |
| V1-draft-26 | 2026-10-10 | Accepted minimum 0.50-point initial/trailing clearance with rounding away from structure; closed OD-08 and stop-rounding subdecision of OD-07. Superseded two-NES-tick/1.00-point trailing setting, updated current rules/checklist and examples. Mapping and numeric risk ceiling remain open. |
| V1-draft-25 | 2026-10-10 | Accepted prompt intrabar tightening, pre-submission validity checks, one pending amendment, preservation/verification of protection, and advancement only after accepted tightening. Added V1-STOP-11 and closed OD-13; actual mapping and platform recovery remain under OD-04/07. |
| V1-draft-24 | 2026-10-10 | Accepted post-activation ES approach-then-penetration continuation, fresh tracking on replacement, breach-first discard, and discard when order cannot be established. Added V1-STOP-10; modification timing remains open under OD-13. |
| V1-draft-23 | 2026-10-10 | Accepted one active unconfirmed pair, strict-more-protective independent replacement, strict ES breach invalidation, and no revival of discarded/replaced pairs. Added V1-STOP-09; existing protection and comparison anchor remain unchanged until accepted tightening. Event/modification timing remains open. |
| V1-draft-22 | 2026-10-10 | Accepted continuation-reference pairing at candidate recognition using the most recent eligible known preceding opposite swing and strict relative-price conditions. Added V1-STOP-08; pair is frozen without later retargeting. Candidate replacement and event/modification timing remain open. |
| V1-draft-21 | 2026-10-10 | Accepted strict unbuffered ES higher-low/lower-high comparison against original invalidation for the first tightening and the last pivot used for an accepted tightening thereafter. Added V1-STOP-07; comparison reference advances only after accepted stop tightening. |
| V1-draft-20 | 2026-10-10 | Accepted strict three-bar trailing-pivot identification on completed current-RTH ES bars; both reference and candidate center bars must begin at/after entry fill. Added V1-STOP-06; OD-13 remains open for comparison, pairing, replacement, and event/modification timing. |
| V1-draft-19 | 2026-10-10 | Accepted auction-reference inventory, preselection, completed-close approach condition, and most recent eligible known opposite-pivot invalidation. Added V1-ENTRY-10 and closed OD-06. Trigger, NES mapping/protection, reentry, and trailing mechanics remain separate open decisions. |
| V1-draft-18 | 2026-10-10 | Accepted frozen consolidation boundaries, 15-minute exclusive first-breakout lifetime, termination at either boundary penetration, and replacement at the next scheduled assessment. Added V1-ENTRY-09; attempt counts and original trade invalidation are preserved. Auction-reference qualification remains open. |
| V1-draft-17 | 2026-10-10 | Accepted latest-three-completed-RTH-bar consolidation, positive box width, at least 50% common overlap, directional penetration, and opposite-boundary candidate invalidation. Added V1-ENTRY-08; box lifetime/replacement and auction-reference qualification remain open. |
| V1-draft-16 | 2026-10-10 | Accepted most recent eligible subsequent opposite-pivot selection, strict relative-price requirement, and recording the pivot pair at entry without retrospective replacement. Added V1-ENTRY-07; consolidation/auction-reference qualification remains open under OD-06. |
| V1-draft-15 | 2026-10-10 | Accepted latest directional swing reference and subsequent confirmed opposite-pivot pullback, both known before entry. Added V1-ENTRY-06. Multiple-pullback selection, consolidation/auction-reference qualification, and NES protection details remain open. |
| V1-draft-14 | 2026-10-10 | Accepted current-RTH completed ES three-bar strict pivot identification for entry swings, with right-hand-bar recognition and no hindsight. Added V1-ENTRY-05; OD-06 remains open for meaningful reference selection and consolidation rules. |
| V1-draft-13 | 2026-10-10 | Accepted equal-weight total-score thresholds and regime/entry permissions; closed OD-02. UNKNOWN blocks entry; retain component evidence and separate breakout/risk requirements. Advanced to entry structure definitions. |
| V1-draft-12 | 2026-10-10 | Accepted Factor 6 rejected counterdirectional swing break plus next-bar continuation, four-assessment window, current-close validity, and conflicting-event neutrality. Added V1-REGIME-09. All factors agreed; total-score thresholds remain open. |
| V1-draft-11 | 2026-10-10 | Accepted Factor 5: frozen 08:30–08:50 ES range and two completed post-observation closes outside its high/low. Added V1-REGIME-08; first directional reading possible at 09:00. Factor 6 and total-score thresholds remain open. |
| V1-draft-10 | 2026-10-10 | Accepted Factor 4 current-RTH three-bar pivots and latest-two-high/latest-two-low structure score. Added V1-REGIME-07; preserved continuation requirement for stop movement. Two factors and total-score thresholds remain open. |
| V1-draft-09 | 2026-10-10 | Accepted developing-value migration: current versus 10-minute-prior RTH snapshots; VPOC and value-area midpoint must each move at least 1.0 point in the same direction. Added V1-REGIME-06; three factors and total-score thresholds remain open. |
| V1-draft-08 | 2026-10-10 | Accepted Factor 1 two-close prior-value measurement and Factor 2 contemporaneous VWAP/two-close relationship with 0.25-point change over 10 minutes. Added V1-REGIME-04/05; OD-02 remains open for four factors and total-score thresholds. |
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
