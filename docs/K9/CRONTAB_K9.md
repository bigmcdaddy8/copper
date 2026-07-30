# K9 Cron Jobs
The following are the crontab entries for 'K9' running on the Azure VM 'dragon'.
VM is started at 05:45 CT by an Azure Automation runbook (schedule TZ: Central Time US & Canada).
Smart shutdown runs at 10:15 CT but defers to the 01:08 AM Auto-Shutdown failsafe if a session is active.

**NOTE: CRON_TZ is NOT supported by the installed cron version (vixie cron 3.0pl1).
All times are hardcoded in UTC. DST adjustment required ~Nov 1 (CST=UTC-6, add 1h to all UTC times).**

Current offset: CDT = UTC-5 (valid Mar–Nov).

```
# K9 crontab — times in UTC. Current offset: CDT = UTC-5.
# DST ends ~Nov 1: update all times by +1 hour (CST = UTC-6).

# K9 — XSP 0DTE PCS closure reconciliation at 07:15 CT = 12:15 UTC (Mon–Fri)
# DST END: change to -> 15 13 * * 1-5
15 12 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_daily_close_xsp.sh

# K9 — XSP 0DTE PCS entry at 09:00 CT = 14:00 UTC (Mon–Fri)
# DST END: change to -> 0 15 * * 1-5
0 14 * * 1-5   bash /home/temckee8/Documents/REPOs/copper/scripts/k9_daily_entry_xsp.sh

# K9 — XSP morning check at 09:30 CT = 14:30 UTC (Mon–Fri)
# DST END: change to -> 30 15 * * 1-5
30 14 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_morning_check_xsp.sh >> /home/temckee8/Documents/REPOs/copper/logs/K9/k9_morning_check_xsp_$(TZ=America/Chicago date +\%F).log 2>&1

# K9 — weekly flow report at 07:00 CT = 12:00 UTC (Monday) — runs before the 07:15 close job
# DST END: change to -> 0 13 * * 1
0 12 * * 1     bash /home/temckee8/Documents/REPOs/copper/scripts/k9_weekly_flow_report_xsp.sh

# Smart shutdown at 10:15 CT = 15:15 UTC weekdays — skips if SSH/VS Code session active, defers to 01:08 AM failsafe
# DST END: change to -> 15 16 * * 1-5
15 15 * * 1-5 bash /home/temckee8/Documents/REPOs/copper/scripts/smart_shutdown.sh

# Compress .log files older than 90 days at 07:18 CT = 12:18 UTC (Friday)
# DST END: change to -> 18 13 * * 5
18 12 * * 5   bash /home/temckee8/Documents/REPOs/copper/scripts/compress_old_logs.sh
```
