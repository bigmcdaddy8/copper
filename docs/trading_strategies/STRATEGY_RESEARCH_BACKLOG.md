# Futures Strategy Research Backlog

**Owner:** Mr. Dick Weasel  
**Revision:** 28  
**Date:** 2026-10-10 (America/Chicago)  
**Status:** Agreed organizational direction; setup mechanics below remain research questions  
**Repository location:** `copper/docs/trading_strategies/STRATEGY_RESEARCH_BACKLOG.md`

## 1. Scope and authority

Develop a long-term toolbox covering the four setups in Chris Drysdale's *VWAP Wave Core Setup Guide*, while completing the existing Momentum Breakout with Structural Trailing playbook first.

This backlog records future work. It neither changes [FUTURES_TREND_PLAYBOOK_V1.md](FUTURES_TREND_PLAYBOOK_V1.md) nor authorizes a new setup. The playbook is now V1-draft-28, recording the accepted chart configuration, session definitions, and Volume Profile/ATR settings. It remains a draft until its remaining open decisions are resolved and the owner accepts a frozen baseline.

The owner confirmed on 2026-10-10 that the existing draft was stored in Git and pushed to GitHub as written. The owner subsequently confirmed placing the revision-01 README and backlog beside the unchanged playbook. These are owner reports, not independently inspected repository states. The owner has now confirmed the supplied V1-draft-07 files were saved and committed. The revision-28 updated files supplied here still need to be copied and committed locally.

## 2. Agreed work sequence

| Order | Work | Decision references | Completion evidence |
| --- | --- | --- | --- |
| 1 | Preserve strategy inventory and research backlog | ORG-01 | README and this backlog |
| 2 | Define PB-TREND chart and analytical configuration | OD-16, OD-04, OD-05 | Accepted chart, instruments, sessions, anchors, and calculation settings |
| 3 | Make regime scoring executable | OD-02, OD-03 | Defined factors, thresholds, data sufficiency, and refresh rules |
| 4 | Make breakout and pivot structure executable | OD-06, OD-13 | Unambiguous selection and confirmation examples |
| 5 | Finish execution, protection, session/risk, and review decisions | Remaining V1 OD items | Resolved decision register and human review |
| 6 | Accept and freeze PB-TREND V1.0; practice and review | Existing playbook rules | Accepted revision and versioned attempt records |
| 7 | Expand the setup toolbox incrementally | SETUP-01 through SETUP-04 | Independently reviewed setup playbooks |

An accepted answer can close part of an OD item without closing the entire item. Do not mark OD-04 or OD-05 closed merely because the chart instrument or VWAP anchor has been chosen.

## 3. Organization and source fidelity

### ORG-01 — Independent playbooks

Keep the existing filename and rule IDs. Describe its strategy identity as **Momentum Breakout with Structural Trailing**. Give each future setup its own identity, status, decision register, and revision history.

Reserve V2 for a substantial revision of a particular playbook, such as adding pyramiding to PB-TREND. A new strategy has its own V1. Future priority among the four setups is not yet locked.

### ORG-02 — Shared principles and strategy-specific mechanics

Record shared process principles in the strategy index for now. Avoid prematurely extracting a large shared rulebook or changing the current V1 references.

Each playbook must answer: eligible market conditions; disqualifying evidence; entry trigger; structural invalidation; protection; exit policy; reentry; position size/adds; and review evidence. No common no-target or fixed-R:R policy is assumed.

### ORG-03 — Value terminology

Use explicitly different concepts:

- **VWAP value bands:** the deviation-band region used by the guide. Anchor, band formula, multiplier, and session settings still require confirmation.
- **Volume Profile value area:** VAH/VAL derived from traded volume at price under a named session and calculation policy.

These references can coexist. Their boundaries are not interchangeable. Avoid the unqualified word “value” in an executable rule when either interpretation is possible.

### ORG-04 — Target and order distinctions

Separate three decisions: protective/target order arrangement; market-based objective such as VWAP; and any fixed or minimum reward-to-risk requirement.

For future mean-reversion designs, investigate locating the stop and market objective first, then measuring the available reward/risk. This is a proposed design approach, not an accepted entry filter or a claim about performance.

### ORG-05 — Provenance and journal identity

Distinguish source statements, local decisions, proposed implementations, and evidence-based conclusions. Store source title/page and local rule references where practical.

Every attempt should retain playbook ID, revision, setup identity, and contemporaneous observations. A research comparison must not rewrite the strategy governing an actual attempt. If several playbooks eventually become active, define overlap, precedence, aggregate risk, and session loss accounting before concurrent use.

## 4. Setup backlog

These summaries paraphrase the attached guide. They are not full strategy specifications. Proposed management questions are our own research work.

### SETUP-01 — Price Discovery Continuation (PB-PDC)

**Source:** Guide page 3.

**Source concept:** Price moves outside VWAP value, establishes acceptance, and offers continuation. The guide describes a retest of the deviation band followed by strength and also permits direct breakout entry with rejection risk.

**Relationship to PB-TREND:** Similar continuation objective, but the existing playbook's significant swing/auction-reference breakout and structural trailing are not a complete reproduction of this setup.

**Research questions:**

- How are outside-value acceptance and band retests defined?
- Are direct breakout and retest entries distinct variants?
- Which rejection invalidates the setup?
- Does confirmed-pivot trailing fit, and what happens on reentry into value?
- Should PB-PDC be separate or a named PB-TREND variant?

### SETUP-02 — Fade Value Area Extremes (PB-FADE)

**Source:** Guide page 4.

**Source concept:** With price accepted inside VWAP value, seek rejection near an outer band. The guide also discusses touch/proximity entries and warns about continued movement through the band.

**Research questions:**

- What evidence distinguishes accepted balance from a developing breakout?
- Which entry variant will the initial training playbook allow?
- Is VWAP the first exit objective, and when is an opposite-band objective eligible?
- How do moving bands affect orders and invalidation?
- What maximum duration or failed-rejection exit is appropriate?

Do not import the guide's optional scaling-in concept into the one-lot training framework without a separate decision.

### SETUP-03 — Return to Value (PB-RTV)

**Source:** Guide page 5 and principles on page 2.

**Source concept:** After trading outside value, price reenters the VWAP value region. The guide describes an accepted reentry followed by a band retest, while also allowing direct reentry when a retest does not occur.

**Research questions:**

- How much prior outside-value activity is required?
- What makes reentry accepted rather than a temporary penetration?
- Are retest and direct-reentry variants separate?
- What is the contextual target: VWAP, opposite band, or a staged conditional objective?
- Is a target order appropriate, and is there a minimum available reward/risk filter?
- When does failed return-to-value evidence invalidate the trade?

No universal 2R or 3R target has been selected.

### SETUP-04 — VWAP Bounce (PB-BOUNCE)

**Source:** Guide page 6.

**Source concept:** After price enters value and tests VWAP, look for strength away from VWAP. The guide highlights volatility/context and possible traps near VWAP.

**Research questions:**

- What distinguishes rejection from acceptance across VWAP?
- Is the destination the nearer outer band or a larger continuation move?
- Should target-based and structural-trailing management be distinct variants?
- How does this differ operationally from a fade or return-to-value trade?
- How are failed tests, repeated attempts, and choppy VWAP crossings treated?

Do not classify every VWAP touch as this setup.

## 5. Immediate decision batch — chart and analytical definitions

| Batch ID | Question | Related V1 item | Status |
| --- | --- | --- | --- |
| CFG-01 | 5-minute ES primary decision chart | OD-16 | ACCEPTED 2026-10-10; OD-16 closed |
| CFG-02 | ES for charts/VWAP/Volume Profile; NES for execution | OD-04 | ACCEPTED 2026-10-10; exact contracts, alignment, and level handling remain open |
| CFG-03 | NinjaTrader Order Flow VWAP on ES; tick resolution subject to complete data; session reset; explicit 08:30–15:00 Chicago template | OD-05 | IMPLEMENTATION ACCEPTED 2026-10-10; template/data/boundary/parity verification remains open |
| CFG-04 | RTH 08:30–15:00; prior references from most recent completed RTH; overnight preceding day 17:00–08:30 (Sunday for Monday); holidays/shortened cash sessions observation only | OD-04, OD-01 | ACCEPTED 2026-10-10; entry/flatten cutoffs and operational/timestamp details remain open |
| CFG-05 | NinjaTrader Order Flow Volume Profile; traded volume; 68%; one ES tick/row; tick data subject to availability | OD-05 | SETTINGS ACCEPTED 2026-10-10; algorithm/tie reproducibility, data completeness, and fallback policy remain open |
| CFG-06 | ATR(13), Wilder smoothing, full-session ES 5-minute bars including overnight; no 08:30 reset; last completed bar at entry | OD-05 | INPUT POLICY ACCEPTED 2026-10-10; exact template/gap/seed/warm-up policy remains open |
| CFG-07 | Define VWAP Wave band formula/settings when developing those setups | Future playbooks | Deferred; not necessary to finalize PB-TREND unless added to its rules |

CFG-01 through CFG-04 and the primary CFG-05/06 indicator settings are accepted. Full-session ATR input including overnight history and continuity through 08:30 is also accepted. The NinjaTrader Order Flow VWAP tick/session implementation with an explicit 08:30–15:00 Chicago template is now accepted. OD-03 is now closed: assessment at 08:50 and after every completed 5-minute bar, latest scheduled assessment for intrabar entries, freshness check before entry, and UNKNOWN/no-entry for missing required evidence. Factors 1 and 2 are now accepted: two-close prior-value location, and two-close contemporaneous VWAP relationship plus at least 0.25-point VWAP change over 10 minutes (V1-REGIME-04/05). Factor 3 is now accepted: developing RTH VPOC and value-area midpoint each moving at least 1.0 point in the same direction over 10 minutes, measured from historical snapshots (V1-REGIME-06). Factor 4 is now accepted: current-RTH three-bar pivots recognized after the right-hand bar closes, comparing latest two highs and latest two lows (V1-REGIME-07). Complete data with too few pivots scores zero. Factor 5 is now accepted: two completed post-observation closes outside the frozen 08:30–08:50 ES range (V1-REGIME-08), with the first possible directional score at 09:00. Factor 6 is now accepted: known-swing rejection with immediate next-bar continuation, four-assessment window, and current-close validity (V1-REGIME-09). All six factor definitions, equal weighting, total-score thresholds, and regime/permission mapping are agreed; OD-02 is closed. Scores +4 through +6 permit longs only, -6 through -4 permit shorts only, and other valid totals permit no entries. Missing required evidence means UNKNOWN/no entry; breakout, protection, and risk rules still apply. Entry-swing identification is now accepted under V1-ENTRY-05: completed current-RTH ES three-bar strict pivots, recognized after the right-hand bar closes and known before entry. V1-ENTRY-06 now accepts the latest directional swing reference plus a subsequent confirmed opposite-pivot pullback, both known before entry. V1-ENTRY-07 accepts the most recent eligible subsequent opposite pivot, strictly below the reference high for longs or above the reference low for shorts, known before entry. Record the chosen pair at entry; later pivots do not rewrite original invalidation. V1-ENTRY-08 accepts consolidation formation from the latest three completed current-RTH ES bars, positive box width, and common overlap of at least 50% of box width. Directional penetration uses the opposite box boundary as candidate invalidation. V1-ENTRY-09 accepts frozen boundaries, a 15-minute exclusive first-breakout lifetime, termination at either boundary penetration, and replacement evaluation at the next scheduled assessment. Replacement does not reset attempts or rewrite existing trade invalidation. V1-ENTRY-10 accepts prior RTH VAH/VAL and high/low plus completed overnight high/low, preselection, completed-close approach qualification, and the most recent eligible known opposite-pivot invalidation. OD-06 is closed. V1-STOP-06 accepts the same strict completed-RTH ES three-bar trailing-pivot method, with both reference and candidate center bars beginning at/after entry fill and recognition only after the right-hand bar closes. V1-STOP-07 accepts strict unbuffered ES comparison against original structural invalidation initially and the last pivot used for an accepted stop tightening thereafter; advance that reference only after accepted tightening. V1-STOP-08 accepts frozen continuation-reference pairing at candidate recognition with the most recent eligible known preceding swing high for longs or low for shorts, with strict relative-price conditions and post-entry center restrictions. V1-STOP-09 accepts one active unconfirmed pair, independently qualifying strict-more-protective replacements, strict ES breach invalidation, and no revival of discarded/replaced pairs; existing protection and comparison anchor remain unchanged. V1-STOP-10 accepts post-activation approach-then-strict-penetration ES continuation, fresh tracking on replacement, breach-first discard, and discard when event order is unresolved. V1-STOP-11 accepts prompt intrabar tightening with current validity checks, one pending amendment, preservation/verification of protection, verified acceptance before anchor advancement, and reconciliation if conditions change. OD-13 is closed. OD-08 is now closed: both initial and trailing stops use minimum 0.50-point clearance beyond mapped structure, rounded away to the execution tick grid. This supersedes the earlier 1.00-point/two-NES-tick trailing buffer; one NES tick equals the nominal clearance for tick-aligned mapped levels. Buffer distance is a strategy/instrument-family setting rather than a universal fixed tick count. V1-RISK-03 accepts the combined ceiling min(percentage × allocated futures equity, fixed-dollar learning cap), retaining one NES and assessing planned structural price risk plus estimated fees/slippage. The ceiling is a maximum rather than a sizing target. Starting numbers are accepted: $3,500 futures allocation, 0.50% ceiling, and $15 fixed-dollar cap including estimated costs/slippage; initial effective ceiling is $15. OD-09 remains open for equity verification/snapshot/update/shared-fund policy, cost inputs, and actual-fill overshoot; OD-10 retains R0/gross-net accounting decisions; detailed operational recovery remains under OD-07; trigger/order handling, NES mapping, and reentry accounting remain separately open. Keep ATR template/gap/seed/warm-up, profile algorithm/data policy, VWAP template/data/boundary/parity verification, and exact contract alignment/cross-instrument handling open before freezing V1.0. Configuration acceptance is not proof of numerical reproducibility.

Use ES for contextual evidence and NES for actual entry/stop/fill prices. Do not silently copy an ES reference into a NES order. Acceptance of the two-instrument configuration does not yet specify a mapping algorithm.

## 6. Later research

- Pyramiding as a separate PB-TREND revision: triggers, quantity, aggregate risk, and coordinated protection.
- Automated entry-time evidence capture and forensic review in Dick's Laboratory.
- Simulated/replay classification of all four setups, without authorizing them for live execution.
- Per-setup performance and execution-quality analysis; avoid pooling strategies with different exit policies into one headline result.
- An overlap/precedence policy if more than one setup describes the same opportunity.

## 7. Change log

| Revision | Date | Change |
| --- | --- | --- |
| 28 | 2026-10-10 | Accepted $3,500 / 0.50% / $15 starting risk configuration, inclusive of estimated costs/slippage; retained equity/cost policy decisions. |
| 27 | 2026-10-10 | Accepted combined percentage-and-dollar entry-risk ceiling framework; numeric limits/equity/cost policies remain open under OD-09/10. |
| 26 | 2026-10-10 | Accepted minimum 0.50-point initial/trailing clearance and outward tick-grid rounding; closed OD-08, revised prior trailing setting, and retained mapping/risk decisions. |
| 25 | 2026-10-10 | Accepted stop-modification timing and acknowledgement policy; closed OD-13 while retaining mapping/platform verification and recovery work. |
| 24 | 2026-10-10 | Accepted continuation-confirmation event sequence and ambiguity handling; advanced to stop-modification timing. |
| 23 | 2026-10-10 | Accepted unconfirmed-candidate replacement/invalidation and unchanged protection/anchor; advanced to event ordering and modification timing. |
| 22 | 2026-10-10 | Accepted frozen continuation-reference pairing; advanced to candidate replacement/invalidation. |
| 21 | 2026-10-10 | Accepted higher-low/lower-high comparison and advancement only after accepted protective-stop tightening; advanced to reference pairing. |
| 20 | 2026-10-10 | Accepted trailing-pivot identification and post-fill center-bar restriction; OD-13 remains partially open. |
| 19 | 2026-10-10 | Accepted auction-reference qualification and closed OD-06; advanced to trailing-pivot mechanics. |
| 18 | 2026-10-10 | Accepted consolidation box duration/freezing/replacement; advanced to auction-reference qualification. |
| 17 | 2026-10-10 | Accepted three-bar consolidation formation, at least 50% common overlap, and breakout/invalidation structure; box lifecycle remains open. |
| 16 | 2026-10-10 | Accepted most recent eligible pullback-pivot selection and preservation of the entry-time pair. Advanced to consolidation qualification. |
| 15 | 2026-10-10 | Accepted latest directional swing reference and subsequent confirmed opposite-pivot pullback. Retained multiple-pullback selection, consolidation/auction-reference qualification, and execution details as open. |
| 14 | 2026-10-10 | Accepted entry-swing three-bar pivot identification and recognition timing; retained meaningful reference selection, consolidation qualification, and trailing mechanics as open decisions. |
| 13 | 2026-10-10 | Accepted aggregate score thresholds and directional entry permissions; closed OD-02 and advanced to entry structure definitions. |
| 12 | 2026-10-10 | Accepted Factor 6 event definition, validity/window, and scoring. All six components agreed; aggregate thresholds remain open. |
| 11 | 2026-10-10 | Accepted Factor 5 frozen-range extension and explicit 09:00 first possible directional score. |
| 10 | 2026-10-10 | Accepted Factor 4 swing structure and three-bar pivot method. Stop continuation confirmation remains separate. |
| 09 | 2026-10-10 | Accepted Factor 3 developing-value migration and historical snapshot requirements. No additional repository commit was reported in this acceptance turn. |
| 08 | 2026-10-10 | Accepted first two scoring measurements; retained four remaining factors and total-score thresholds. Recorded owner report that supplied V1-draft-07 files were saved and committed. |
| 07 | 2026-10-10 | Accepted regime assessment timing/freshness and UNKNOWN/no-entry policy; closed OD-03. Recorded owner report that V1-draft-06 was committed. |
| 06 | 2026-10-10 | Accepted NinjaTrader Order Flow VWAP tick/session implementation and explicit RTH template; retained operational checks and advanced design discussion to regime timing. Recorded owner report that V1-draft-05 was committed. |
| 05 | 2026-10-10 | Accepted full-session ATR input including overnight and no 08:30 reset; retained exact template, gap, seed, and warm-up decisions. Recorded owner report that V1-draft-04 was committed. |
| 04 | 2026-10-10 | Accepted CFG-05/06 settings with owner-selected 68% Volume Profile and 13-period ATR; retained unresolved calculation/history/data policies. Recorded owner report that V1-draft-03 was committed. |
| 03 | 2026-10-10 | Accepted CFG-04 session definitions; retained open operational/calendar, timestamp, and entry/flatten details. Recorded owner report that V1-draft-02 was committed. |
| 02 | 2026-10-10 | Accepted CFG-01/02/03; closed OD-16 and retained unresolved portions of OD-04/05. Recorded owner report that initial documents were placed in the repository. |
| 01 | 2026-10-10 | Initial strategy backlog and decision batch. Preserves the existing V1 draft and records the agreed sequence. No trading rules changed. |
