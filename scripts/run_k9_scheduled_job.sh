#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <scheduled-job-name>" >&2
  exit 2
fi

case "$1" in
  compress_old_logs|k9_daily_close_xsp|k9_morning_check_xsp|k9_tastytrade_diagnostic|k9_tastytrade_entry_xsp|k9_weekly_flow_report_xsp|smart_shutdown)
    ;;
  *)
    echo "Unsupported scheduled job: $1" >&2
    exit 2
    ;;
esac

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
exec /usr/bin/bash "$REPO_ROOT/scripts/$1.sh"