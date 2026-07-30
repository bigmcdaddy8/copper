# K9 Scheduling

K9 jobs run on Azure VM `dragon`, which starts at 05:45 America/Chicago through an Azure Automation schedule. Every scheduled wrapper independently requires its exact America/Chicago wall-clock minute before performing work. This protects against a late manual invocation, an incorrect scheduler configuration, and duplicate UTC fallback entries.

Do not enable both scheduler options below. The preferred option is systemd because it natively understands the `America/Chicago` timezone and handles daylight saving automatically.

## Preferred: systemd Timers

The checked-in units under [deploy/systemd](../../deploy/systemd) express each schedule in Central Time:

| Timer | Schedule |
|---|---|
| `copper-k9-daily-close.timer` | Weekdays 07:15 CT |
| `copper-k9-morning-check.timer` | Weekdays 09:30 CT |
| `copper-k9-tastytrade-diagnostic.timer` | Weekdays 09:45 CT |
| `copper-k9-weekly-flow-report.timer` | Monday 07:00 CT |
| `copper-k9-smart-shutdown.timer` | Weekdays 10:15 CT |
| `copper-k9-compress-logs.timer` | Friday 07:18 CT |

The timers use `Persistent=false`. A job missed while the VM is stopped is not replayed after boot, which is required for market-time-sensitive work. The disabled K9 entry job intentionally has no timer.

Install the units on `dragon` with administrative access:

```bash
cd /home/temckee8/Documents/REPOs/copper

sudo install -m 0644 deploy/systemd/copper-k9-job@.service /etc/systemd/system/
sudo install -m 0644 deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload

sudo systemctl enable --now \
	copper-k9-daily-close.timer \
	copper-k9-morning-check.timer \
	copper-k9-tastytrade-diagnostic.timer \
	copper-k9-weekly-flow-report.timer \
	copper-k9-smart-shutdown.timer \
	copper-k9-compress-logs.timer

systemctl list-timers 'copper-k9-*'
```

After that command succeeds and shows every timer as active, remove the replacement cron invocations:

```bash
cd /home/temckee8/Documents/REPOs/copper
bash scripts/retire_k9_cron_jobs.sh
crontab -l
```

The retirement script refuses to alter crontab unless all replacement timers are enabled and active, and writes a backup under `~/.local/state/copper/cron-backups/`. Verify upcoming runs with `systemctl list-timers` before relying on the timers. `systemd` uses the installed timezone database, so no November or March schedule edit is needed.

## Fallback: DST-Safe UTC Cron

Use this only if systemd timers cannot be installed. Vixie cron 3.0pl1 does not support `CRON_TZ`, so each Central-Time job has both possible UTC mappings. The script guard accepts only the exact expected Central-Time minute; the other invocation exits successfully without working.

```cron
# K9 cron fallback. Keep every dual UTC entry year-round.
# Do not use these lines while the systemd timers above are enabled.

# Daily close: 07:15 America/Chicago = 12:15 UTC (CDT) or 13:15 UTC (CST)
15 12,13 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_daily_close_xsp.sh

# Morning check: 09:30 America/Chicago = 14:30 UTC (CDT) or 15:30 UTC (CST)
30 14,15 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_morning_check_xsp.sh >> /home/temckee8/Documents/REPOs/copper/logs/K9/k9_morning_check_xsp_$(TZ=America/Chicago date +\%F).log 2>&1

# Tastytrade diagnostic: 09:45 America/Chicago = 14:45 UTC (CDT) or 15:45 UTC (CST)
# Enable only after three successful manual production diagnostics.
# 45 14,15 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_tastytrade_diagnostic.sh

# Weekly flow report: Monday 07:00 America/Chicago = 12:00 UTC (CDT) or 13:00 UTC (CST)
0 12,13 * * 1  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_weekly_flow_report_xsp.sh

# Smart shutdown: 10:15 America/Chicago = 15:15 UTC (CDT) or 16:15 UTC (CST)
15 15,16 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/smart_shutdown.sh

# Log compression: Friday 07:18 America/Chicago = 12:18 UTC (CDT) or 13:18 UTC (CST)
18 12,13 * * 5  bash /home/temckee8/Documents/REPOs/copper/scripts/compress_old_logs.sh

# Disabled K9 entry: 09:00 America/Chicago = 14:00 UTC (CDT) or 15:00 UTC (CST)
# 0 14,15 * * 1-5  bash /home/temckee8/Documents/REPOs/copper/scripts/k9_daily_entry_xsp.sh
```

## Guard Verification

Run the guard test after changing any schedule wrapper:

```bash
bash scripts/tests/test_require_ct_time.sh
```

The test uses a fake `date` command to prove that an exact `09:45 CT` invocation runs, while `10:45 CT` exits without work. It does not alter the VM clock or invoke a broker API.
