#!/usr/bin/env bash
set -euo pipefail

TIMERS=(
  copper-k9-daily-close.timer
  copper-k9-morning-check.timer
  copper-k9-tastytrade-diagnostic.timer
  copper-k9-weekly-flow-report.timer
  copper-k9-smart-shutdown.timer
  copper-k9-compress-logs.timer
)
JOB_PATHS=(
  /home/temckee8/Documents/REPOs/copper/scripts/k9_daily_close_xsp.sh
  /home/temckee8/Documents/REPOs/copper/scripts/k9_morning_check_xsp.sh
  /home/temckee8/Documents/REPOs/copper/scripts/k9_weekly_flow_report_xsp.sh
  /home/temckee8/Documents/REPOs/copper/scripts/smart_shutdown.sh
)

for timer in "${TIMERS[@]}"; do
  if ! systemctl is-enabled --quiet "$timer" || ! systemctl is-active --quiet "$timer"; then
    echo "Refusing to remove cron: $timer is not enabled and active." >&2
    exit 1
  fi
done

backup_dir="$HOME/.local/state/copper/cron-backups"
mkdir -p "$backup_dir"
backup_path="$backup_dir/k9_before_systemd_$(date -u +%Y%m%d_%H%M%S).crontab"
current_crontab="$(mktemp)"
filtered_crontab="$(mktemp)"
trap 'rm -f "$current_crontab" "$filtered_crontab"' EXIT

crontab -l > "$current_crontab"
cp "$current_crontab" "$backup_path"

awk \
  -v close_job="${JOB_PATHS[0]}" \
  -v morning_job="${JOB_PATHS[1]}" \
  -v weekly_job="${JOB_PATHS[2]}" \
  -v shutdown_job="${JOB_PATHS[3]}" '
  index($0, close_job) || index($0, morning_job) || index($0, weekly_job) || index($0, shutdown_job) {
    next
  }
  { print }
' "$current_crontab" > "$filtered_crontab"

if grep -qvE '^[[:space:]]*(#|$)' "$filtered_crontab"; then
  crontab "$filtered_crontab"
else
  crontab -r
fi

echo "Removed legacy K9 cron invocations. Backup: $backup_path"
echo "Verify replacement timers with: systemctl list-timers 'copper-k9-*'"