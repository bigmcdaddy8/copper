---
mode: agent
description: Daily K9 cron job and Azure VM status check. Run this each trading day (or after a multi-day absence) to review VM reliability, trade entries, and reconciliation progress.
---

You are analyzing the K9 automated options trading system running on an Azure VM named 'dragon'.
Today's date is {{CURRENT_DATE}}. The system trades XSP 0DTE Put Credit Spreads (2-leg spreads) once per trading day via cron jobs. All times are Chicago (CDT/CST).

## Your task

Examine all K9 cron job log files and the Captain's Log trade database, then produce a structured daily status report covering **every trading day since the last report** (or the last 5 trading days if this is a fresh session).

---

## Step 1 — Discover available logs

List the contents of `logs/K9/` to identify which dates have log files. The log files follow these naming patterns:
- `k9_daily_entry_xsp_YYYY-MM-DD.log` — entry cron (runs ~9:00 AM CDT)
- `k9_daily_close_xsp_YYYY-MM-DD.log` — close/reconciliation cron (runs ~7:15 AM CDT)
- `k9_morning_check_xsp_YYYY-MM-DD.log` — post-entry sanity check
- `smart_shutdown_YYYY-MM-DD.log` — VM shutdown cron (runs ~10:15 AM CDT)
- `xsp_pcs_0dte_w1_none_0900_trds_YYYYMMDD_HHMMSS.json` — structured run log per entry attempt

---

## Step 2 — Read all logs for each day

For each trading day with logs, read:
1. `smart_shutdown_YYYY-MM-DD.log` — did the VM run? was it deallocated cleanly or was a user session active?
2. `k9_daily_close_xsp_YYYY-MM-DD.log` — what was `checked`, `updated`, `skipped`, `orphaned`? any ORPHAN alerts?
3. `k9_daily_entry_xsp_YYYY-MM-DD.log` — was the entry FILLED, CANCELED, SKIPPED? if CANCELED, what was the reason?
4. `k9_morning_check_xsp_YYYY-MM-DD.log` — did it PASS? what does the trade table show?
5. The corresponding `xsp_pcs_0dte_w1_none_0900_trds_YYYYMMDD_*.json` file — `entry_attempts`, `filled_price`, `net_credit`, `reason`, and the `entry_attempt_log` array (if present — shows per-attempt limit prices and timestamps)

---

## Step 3 — Query the Captain's Log database

Run this Python snippet to get the current state of all trades:

```python
import sqlite3
conn = sqlite3.connect('data/captains_log/TRD.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute('''
    SELECT legacy_trade_num, expiration, short_put_strike, long_put_strike,
           net_credit, outcome, tp_status, realized_pnl, closed_at, exit_reason
    FROM trades
    WHERE outcome = 'FILLED'
    ORDER BY entered_at
''')
for r in cur.fetchall():
    print(dict(r))
conn.close()
```

---

## Step 4 — Produce the status report

### Section A: VM Reliability Table

| Date | Day | VM Ran | Shutdown Outcome |
|------|-----|--------|-----------------|
For each date in scope, one row. Note any days where the VM did NOT run (missing log files = VM never started).

### Section B: Daily Cron Results

For each trading day, report:
- **Close cron**: `checked` / `updated` / `skipped` / `orphaned` counts and whether any ORPHAN alerts fired
- **Entry cron**: FILLED / CANCELED / SKIPPED, the reason if not FILLED, `net_credit`, strikes, number of attempts
- **Morning check**: PASS or FAIL
- **Notable events**: holiday detection, credit-too-thin cancels, timeout-exhausted cancels, orphan resolutions

If `entry_attempt_log` is present in the JSON, include a sub-table showing each attempt's timestamp (Chicago time), limit price, and outcome.

### Section C: Trade Reconciliation Status

Show a table of all FILLED trades with current reconciliation state:

| # | Entry Date | Strikes | Credit | tp_status | P/L | Notes |
|---|-----------|---------|--------|-----------|-----|-------|

Reconciliation states to call out:
- **OPEN** — entered today or yesterday; broker settlement data not yet available (normal)
- **ORPHAN** — broker settlement window passed but no definitive data yet (normal up to ~2 days)
- **EXPIRED** — both legs expired OTM; full credit kept (max profit)
- **SETTLED** — one or both legs settled ITM; debit charged by broker
- **Complete** — `closed_at` is populated and `realized_pnl` is set

### Section D: Running P/L Summary

Summarize total P/L across all reconciled trades (tp_status = EXPIRED or SETTLED).

### Section E: Issues / Watch Items

Call out anything that warrants attention:
- Consecutive CANCELED entries (fill failures) — note the reason (credit too thin vs. timeout exhausted)
- Persistent ORPHAN trades (more than 3 trading days without resolution)
- Missing logs for expected trading days (VM may not have started)
- Any morning check FAIL
- Any `entry_attempt_log` patterns suggesting the retry price-walk is not behaving as expected (spec: 5 attempts, $0.02 decrement per retry, 55s fill window per attempt)

---

## Context: How the system works

- **Trade type**: XSP 0DTE Put Credit Spread — sell the short put (~0.41 delta), buy the long put ($1 wing below). Cash-settled, no assignment risk.
- **Entry**: Limit order at midpoint, walks down $0.02 per retry, up to 5 attempts × 55 seconds each. Minimum credit: $0.03. Entry window: 8:55–9:21 AM CDT.
- **Exit**: Let expire. No take-profit order. Broker settles cash at expiration.
- **Reconciliation lag**: Tradier typically takes 1–2 trading days to post gain/loss data for expired options. An ORPHAN on day+1 is normal; it should auto-resolve by day+2.
- **Possible outcomes**: (1) both legs expire OTM → full credit kept; (2) short leg expires ITM, long leg OTM → partial loss; (3) both legs expire ITM → maximum loss (short spread width minus credit).
- **Weekly flow report**: Generated Monday mornings; file is `k9_weekly_flow_report_xsp_YYYY-MM-DD.log` — read it if present.
- **Cron does NOT run on weekends or U.S. market holidays** — missing logs on those days is expected.
