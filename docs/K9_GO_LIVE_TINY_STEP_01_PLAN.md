# K9 Go-Live Tiny Step 01 Plan

## Purpose
Establish a production-accurate, low-risk process for reconciling 0DTE option trades that are intentionally held through expiration, using live Tradier data as the source of truth.

## Why This Plan
Sandbox behavior for settlement and account history may differ from production. We will use tiny live trades to validate real brokerage payloads, then harden K9 reconciliation logic from observed evidence.

## Pilot Scope
- Account: TRD (live)
- Strategy: XSP 0DTE PCS (existing K9 spec) 'apps/K9/trade_specs/xsp_pcs_0dte_w1_none_0900_trds.yaml'
- Position size: 1 contract maximum
- Cadence:
1. Entry cron at 09:00 CT (weekdays)
2. Close reconciliation cron at 06:15 CT (weekdays only)
- Out of scope:
1. Scaling position size
2. Multi-strategy deployment
3. Intraday close reconciliation runs

## Safety Guardrails
- Hard limits:
1. `quantity = 1` only
2. No manual increase to size during Step 01
3. Keep minimum-credit guard enabled
- Operational controls:
1. Keep kill-switch available to disable live entry immediately
2. Keep morning check job active for daily validation
3. Require daily manual review of close log before market open
- Stop conditions (pause pilot immediately):
1. Unexpected order status transition that cannot be explained from broker payloads
2. Any mismatch between journal state and broker position state that persists > 1 business day
3. Any evidence of incorrect realized P&L assignment

## Evidence Capture Requirements
For each live FILLED trade, capture and retain the following artifacts:
1. Entry-time run JSON (`logs/K9/*.json`)
2. Daily close logs (`logs/K9/k9_daily_close_xsp_YYYY-MM-DD.log`)
3. Morning check logs (`logs/K9/k9_morning_check_xsp_YYYY-MM-DD.log`)
4. Journal records from `data/captains_log/TRD.db`:
- `trades` row
- related `trade_events` rows
5. Broker snapshots (manual command capture) for the trade window:
- `get-account-order` for the entry order id
- `get-account-orders` snapshot
- `get-account-history` snapshot
- `get-positions` snapshot

## Reconciliation Decision Policy (Step 01)
For stale FILLED no-TP trades (`exit_type: NONE`):
1. If broker evidence definitively confirms settlement/expiration outcome:
- Close trade automatically
- Record EXIT event with evidence marker: `definitive_settlement_evidence_found`
2. If evidence is unavailable but position is no longer open:
- Mark ORPHAN once (no repeated spam)
- Record ADJ event with marker: `broker_settlement_evidence_unavailable`
3. If position remains open:
- Keep trade open and re-evaluate next scheduled reconciliation run

## Daily Runbook (Operator Checklist)
At ~06:20 CT each weekday:
1. Review close log for `checked/updated/skipped/orphaned` counts
2. Confirm no unexpected exceptions
3. Query journal latest FILLED trades and closure fields
4. For any newly stale trade, run broker evidence checks:
- account order by ID
- account orders snapshot
- account history snapshot
- positions
5. Record findings in Notes section below

## Notes Log (Fill Daily During Pilot)
Use one row per trading day.

| Date | Entry Outcome | Entry Order ID | 06:15 Close Result | Broker History Evidence | Final Trade State | Notes |
|---|---|---|---|---|---|---|
| YYYY-MM-DD | FILLED/SKIPPED | <id or blank> | checked=x updated=y orphaned=z | present/absent | CLOSED/ORPHAN/OPEN | |

## Success Criteria (Step 01 Exit)
Step 01 is considered successful when all are true:
1. At least 5 live trading days completed with no safety stop conditions
2. At least 2 expired FILLED trades observed in live account
3. For each expired trade, reconciliation path is explainable from captured broker payloads
4. No duplicate ORPHAN event spam for the same trade
5. Journal and broker positions remain consistent at each morning check

## Step 01 Deliverables
1. Completed daily Notes Log in this file
2. Confirmed payload examples for expiration/settlement behavior in live environment
3. Recommendation memo for Step 02:
- keep current logic
- or adjust parsing/decision rules based on observed live payloads

## Approval Gate for Step 02
Do not increase size or broaden scope until this plan is reviewed and explicitly approved.
