# Vibe Developer Notes

## Holodeck Commands

### One-time setup on a fresh machine
./setup.sh

uv run scripts/holodeck_sim.py --clear

## Reporting Commands

uv run enc trades -a HD
uv run enc trades -a HD --status FILLED
uv run enc pnl -a HD --month 2026-01
uv run enc trades -a HD
uv run log show 3ca6f33c
uv run captains_log show 3ca6f33c
uv run captains_log show 3ca6f33c -a HD
uv run captains_log show 3ca6f33c
uv run captains_log show 3ca6f33c -a HD
uv run enc trades -a HD
uv run captains_log show dd6b5f07 -a HD
uv run enc trades -a HD
uv run captains_log show 84cf8ca1 -a HD

### v2 Examples

- Trade Number / TradeManagerNotes (all for HD): ```uv run enc report trade-number -a HD```
- Trade Number for one trade: ```uv run enc report trade-number -a HD --trade-number HD_00001_SIC```
- Daily Notes / traders_daily_work_notes (all for HD): ```uv run enc report daily-notes -a HD```
- Daily Notes filtered by trade: ```uv run enc report daily-notes -a HD --trade-number HD_00012_SIC```
- Daily Notes filtered by underlying: ```uv run enc report daily-notes -a HD --underlying SPX```
- Trade PnL / TradeHistory (both statuses): ```uv run enc report trade-history -a HD```
- Trade PnL closed only with date window: ```uv run enc report trade-history -a HD --status CLOSED --entry-date ">=01/01/2026" --exit-date "<02/01/2026"```
- Trade PnL for one trade: ```uv run enc report trade-history -a HD --trade-number HD_00012_SIC```


### Useful Smoke Flow

- Ensure you have data first: ```uv run scripts/holodeck_sim.py --clear```
- Then run all 3 new reports quickly:
```uv run enc report trade-number -a HD && uv run enc report daily-notes -a HD && uv run enc report trade-history -a HD```


## Post 1st Trade Checklist
I’ll add a single shell script under scripts that checks for today’s K9 run log, verifies captains_log entry/state for the XSP spec, prints each check to stdout, and ends with a clear PASS or FAIL summary.

Read [](file:///home/temckee8/Documents/REPOs/copper/docs/VIBE_DEVELOPER_NOTES.md)

Read [](file:///home/temckee8/Documents/REPOs/copper/apps/K9/trade_specs/xsp_pcs_0dte_w2_none_0900_trds.yaml)

Read [](file:///home/temckee8/Documents/REPOs/copper/scripts)

I gathered the relevant context and will now add a single executable morning-check script that performs machine-verifiable checks plus human-readable report output, then prints a final PASS/FAIL and exits with matching code.

Created [](file:///home/temckee8/Documents/REPOs/copper/scripts/k9_morning_check_xsp.sh)

Ran terminal command:  chmod +x scripts/k9_morning_check_xsp.sh && bash scripts/k9_morning_check_xsp.sh
Completed with input:  chmod +x scripts/k9_morning_check_xsp.sh && bash scripts/k9_morning_check_xsp.sh

Implemented.

Created one-command morning check script:
- k9_morning_check_xsp.sh

What it does
1. Checks whether today’s K9 run log exists for the XSP spec.
2. Validates journal records for today/spec/account using a programmatic check:
- trade exists
- underlying is XSP
- trade type is PUT_CREDIT_SPREAD
- put strikes are present
- if FILLED, entry_filled_price exists, tp_order_id is empty, and tp_status is NONE or ORPHAN
3. Runs optional reporting snapshot:
- uv run enc trades -a TRDS -s FILLED
4. Runs human-readable journal listing:
- uv run captains_log list --account TRDS --spec xsp_pcs_0dte_w2_none_0900_trds --date YYYY-MM-DD (CT)
5. Prints final PASS or FAIL and exits with code 0/1 accordingly.

I also made it executable and test-ran it just now.
- Current result is FAIL, which is expected on Sunday before any scheduled entry for this spec.

How to run tomorrow
- bash k9_morning_check_xsp.sh

If you want, I can also add a cron entry for this morning check (for example 06:20 CT) and route output to a dated log file.

Made changes.

