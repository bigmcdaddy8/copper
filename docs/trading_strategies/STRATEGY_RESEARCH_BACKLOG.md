# Futures Strategy Research Backlog

**Owner:** Mr. Dick Weasel  
**Revision:** 07  
**Date:** 2026-10-10 (America/Chicago)  
**Status:** Agreed organizational direction; setup mechanics below remain research questions  
**Repository location:** `copper/docs/trading_strategies/STRATEGY_RESEARCH_BACKLOG.md`

## 1. Scope and authority

Develop a long-term toolbox covering the four setups in Chris Drysdale's *VWAP Wave Core Setup Guide*, while completing the existing Momentum Breakout with Structural Trailing playbook first.

This backlog records future work. It neither changes [FUTURES_TREND_PLAYBOOK_V1.md](FUTURES_TREND_PLAYBOOK_V1.md) nor authorizes a new setup. The playbook is now V1-draft-07, recording the accepted chart configuration, session definitions, and Volume Profile/ATR settings. It remains a draft until its remaining open decisions are resolved and the owner accepts a frozen baseline.

The owner confirmed on 2026-10-10 that the existing draft was stored in Git and pushed to GitHub as written. The owner subsequently confirmed placing the revision-01 README and backlog beside the unchanged playbook. These are owner reports, not independently inspected repository states. The owner has now confirmed V1-draft-06 was committed. The revision-07 updated files supplied here still need to be copied and committed locally.

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

CFG-01 through CFG-04 and the primary CFG-05/06 indicator settings are accepted. Full-session ATR input including overnight history and continuity through 08:30 is also accepted. The NinjaTrader Order Flow VWAP tick/session implementation with an explicit 08:30–15:00 Chicago template is now accepted. OD-03 is now closed: assessment at 08:50 and after every completed 5-minute bar, latest scheduled assessment for intrabar entries, freshness check before entry, and UNKNOWN/no-entry for missing required evidence. Next design discussion: OD-02 measurable score factors and thresholds. Keep ATR template/gap/seed/warm-up, profile algorithm/data policy, VWAP template/data/boundary/parity verification, and exact contract alignment/cross-instrument handling open before freezing V1.0. Configuration acceptance is not proof of numerical reproducibility.

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
| 07 | 2026-10-10 | Accepted regime assessment timing/freshness and UNKNOWN/no-entry policy; closed OD-03. Recorded owner report that V1-draft-06 was committed. |
| 06 | 2026-10-10 | Accepted NinjaTrader Order Flow VWAP tick/session implementation and explicit RTH template; retained operational checks and advanced design discussion to regime timing. Recorded owner report that V1-draft-05 was committed. |
| 05 | 2026-10-10 | Accepted full-session ATR input including overnight and no 08:30 reset; retained exact template, gap, seed, and warm-up decisions. Recorded owner report that V1-draft-04 was committed. |
| 04 | 2026-10-10 | Accepted CFG-05/06 settings with owner-selected 68% Volume Profile and 13-period ATR; retained unresolved calculation/history/data policies. Recorded owner report that V1-draft-03 was committed. |
| 03 | 2026-10-10 | Accepted CFG-04 session definitions; retained open operational/calendar, timestamp, and entry/flatten details. Recorded owner report that V1-draft-02 was committed. |
| 02 | 2026-10-10 | Accepted CFG-01/02/03; closed OD-16 and retained unresolved portions of OD-04/05. Recorded owner report that initial documents were placed in the repository. |
| 01 | 2026-10-10 | Initial strategy backlog and decision batch. Preserves the existing V1 draft and records the agreed sequence. No trading rules changed. |
