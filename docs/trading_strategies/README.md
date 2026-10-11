# Futures Trading Strategies

**Owner:** Mr. Dick Weasel  
**Index revision:** 13  
**Date:** 2026-10-10 (America/Chicago)  
**Repository directory:** `copper/docs/trading_strategies`

## Purpose

Maintain a small, human-readable collection of independent trading playbooks. Each playbook defines the market conditions it addresses, eligible entries, structural invalidation, position management, exits, and evidence needed for review.

The two principal external influences are Tom Hougaard's *Best Loser Wins* and Chris Drysdale's *VWAP Wave Core Setup Guide*. Source ideas inform the work; the accepted rules of a named, versioned playbook govern a training trade.

## Current inventory

| ID | Playbook / setup | Document | Status |
| --- | --- | --- | --- |
| PB-TREND | Momentum Breakout with Structural Trailing | [FUTURES_TREND_PLAYBOOK_V1.md](FUTURES_TREND_PLAYBOOK_V1.md) | V1-draft-13; accepted configuration and indicator settings recorded; remaining open decisions prevent freezing V1.0 |
| PB-PDC | Price Discovery Continuation | Future `VWAP_PRICE_DISCOVERY_CONTINUATION_PLAYBOOK_V1.md` | Backlog; closest conceptual overlap with PB-TREND, not an identical implementation |
| PB-FADE | Fade Value Area Extremes | Future `VWAP_FADE_VALUE_AREA_EXTREMES_PLAYBOOK_V1.md` | Backlog; observation and design only |
| PB-RTV | Return to Value | Future `VWAP_RETURN_TO_VALUE_PLAYBOOK_V1.md` | Backlog; observation and design only |
| PB-BOUNCE | VWAP Bounce | Future `VWAP_BOUNCE_PLAYBOOK_V1.md` | Backlog; observation and design only |

The four VWAP setup names preserve Drysdale's terminology. PB-TREND remains the existing training design. During PB-PDC design, decide whether it needs a separate executable playbook or can be an explicitly named variant of PB-TREND; do not assume equivalence.

## Research and next decisions

See [STRATEGY_RESEARCH_BACKLOG.md](STRATEGY_RESEARCH_BACKLOG.md) for scope, decision IDs, setup questions, and the agreed work sequence.

Accepted on 2026-10-10: **5-minute ES analysis, one NES contract for execution, and ES session VWAP anchored at 08:30 America/Chicago**. OD-16 is closed. OD-04 and OD-05 remain partially open.

Accepted session definitions: RTH analysis 08:30–15:00 Chicago; prior references from the most recent completed RTH session; overnight context 17:00 on the preceding calendar day through 08:30 (Sunday for Monday); holidays/shortened cash sessions are observation/review only in initial V1 training.

Accepted indicator settings: NinjaTrader Order Flow Volume Profile, traded volume, 68% value area, one ES tick per row, tick resolution subject to availability; ATR(13) with Wilder smoothing on full-session ES 5-minute bars, including overnight history and without an 08:30 reset, using the most recently completed bar at entry.

Accepted VWAP implementation: NinjaTrader Order Flow VWAP on ES, tick resolution subject to complete data availability, session reset, and an explicitly verified 08:30–15:00 America/Chicago trading-hours template.

Accepted regime timing: first assessment at 08:50, then after each completed 5-minute bar; intrabar entry uses the latest scheduled completed assessment; missing required evidence means UNKNOWN/no new entry. OD-03 is closed.

Accepted score definitions: Factor 1 uses two completed ES closes strictly outside prior RTH Volume Profile value; Factor 2 uses two closes relative to their contemporaneous VWAP and a VWAP change of at least 0.25 points over 10 minutes.

Accepted Factor 3: developing RTH VPOC and value-area midpoint must each rise/fall at least 1.0 point over 10 minutes for a directional point; use historical snapshots.

Accepted Factor 4: current-RTH three-bar pivots recognized after the right-hand bar closes; compare the latest two highs and latest two lows for higher-high/higher-low or lower-high/lower-low structure. Complete data with too few formed pivots scores zero.

Accepted Factor 5: freeze the 08:30–08:50 ES range; score directional extension when two completed post-observation bars close strictly beyond its high/low. First possible directional score is 09:00.

Accepted Factor 6: rejection of an already-known current-RTH swing extreme followed by immediate next-bar continuation; use valid events within the last four scheduled assessments.

All six component definitions, equal weighting, and aggregate thresholds/permissions are accepted; OD-02 is closed. Scores +4 through +6 permit longs only, -6 through -4 permit shorts only, and other valid totals permit no entries. UNKNOWN blocks entry. Next design decisions: meaningful entry swing/consolidation and reference selection (OD-06), followed by trailing-pivot mechanics (OD-13). Configuration choices are recorded; operational template/data/reproducibility verification, ATR seed/warm-up, contract alignment and cross-instrument handling, and timestamp boundaries remain open before V1.0. This index and backlog do not independently authorize or change setup mechanics.

The owner confirmed that the supplied V1-draft-07 files were saved and committed. Revision 13 of this index/backlog and V1-draft-13 are supplied as updates; repository replacement/commit remains a local step.

## Document conventions

1. The committed repository copy of each playbook is authoritative. Chat messages and downloaded working copies do not synchronize automatically.
2. Committing a draft preserves it; it does not automatically resolve open decisions or declare V1.0 accepted.
3. Each playbook has its own version history. A new Return to Value playbook starts at its own V1; it is not V2 of the trend playbook.
4. Retain existing PB-TREND rule IDs (`V1-...`). Cite the playbook ID plus revision and rule ID when several playbooks exist. Assign a distinct rule prefix to each future playbook.
5. Shared process principles may include accepting planned losses, respecting protection, avoiding emotional intervention, and separating execution quality from P&L. Entry permission, targets, trailing, reentry, and add rules remain explicit per playbook.
6. A bracket order is an execution arrangement. A market-based target and a fixed-R target are distinct exit policies. Document them separately.
7. Use distinct names for VWAP deviation-band value and Volume Profile value. Record source instrument, session, anchor, and calculation policy.
8. Journal each attempt with playbook ID, revision, setup, and entry-time evidence. Do not change a losing trade's setup label afterward to justify a different exit.

## Source boundaries

The guide provides setup concepts and examples, not a complete operational specification for our platform. Any choices we add must be labeled source rule, agreed local rule, proposed implementation, or research question. No backlog item authorizes live execution.

The existing no-target rule remains specific to PB-TREND. It is not imposed on every future setup, and no fixed-R:R bracket has yet been accepted for a future setup.

## Change log

| Revision | Date | Change |
| --- | --- | --- |
| 13 | 2026-10-10 | Accepted aggregate score thresholds and directional entry permissions; closed OD-02 and advanced to entry structure definitions. |
| 12 | 2026-10-10 | Recorded accepted Factor 6; all component definitions agreed, aggregate thresholds remain open. |
| 11 | 2026-10-10 | Recorded accepted Factor 5 range extension; advanced to the final factor and total-score thresholds. |
| 10 | 2026-10-10 | Recorded accepted Factor 4 swing structure and three-bar pivot method; advanced to range extension. |
| 09 | 2026-10-10 | Recorded accepted developing-value migration (Factor 3); advanced to swing structure. |
| 08 | 2026-10-10 | Recorded accepted Factors 1/2; advanced to developing-value migration while retaining remaining factor/threshold decisions. |
| 07 | 2026-10-10 | Recorded accepted regime assessment timing and UNKNOWN/no-entry policy; closed OD-03 and advanced to scoring definitions. |
| 06 | 2026-10-10 | Recorded accepted Order Flow VWAP implementation; advanced design discussion to regime timing/factors while retaining operational configuration checks. |
| 05 | 2026-10-10 | Recorded accepted full-session ATR input without an 08:30 reset; advanced active work to VWAP implementation. |
| 04 | 2026-10-10 | Recorded accepted NinjaTrader Volume Profile and ATR settings; retained open history and calculation-policy details. |
| 03 | 2026-10-10 | Recorded accepted session definitions and advanced the active work to calculation settings. |
| 02 | 2026-10-10 | Recorded accepted chart/instrument/VWAP configuration and linked the V1-draft-02 state. |
| 01 | 2026-10-10 | Initial strategy index. |
