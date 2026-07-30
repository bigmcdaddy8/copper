#!/usr/bin/env bash
# compress_old_logs.sh — gzip .log files older than 90 days under logs/
#
# Runs weekly (Friday 07:18 CT) via cron.  See docs/K9/CRONTAB_K9.md for
# the crontab entry.  Only plain .log files are touched; already-compressed
# .log.gz files are skipped automatically by the -name filter.

set -euo pipefail

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
LOG_DIR="$REPO_ROOT/logs"
DAYS=90

TODAY_CT="$(TZ=America/Chicago date +%F)"
SELF_LOG="$REPO_ROOT/logs/K9/compress_old_logs_${TODAY_CT}.log"
mkdir -p "$(dirname "$SELF_LOG")"
exec >> "$SELF_LOG" 2>&1

echo "=== $(TZ=America/Chicago date '+%F %T %Z') compress_old_logs: start ==="
echo "Scanning: $LOG_DIR  (files older than ${DAYS} days)"

compressed=0
errors=0

while IFS= read -r -d '' file; do
    if gzip "$file"; then
        echo "  compressed: $file"
        (( compressed++ )) || true
    else
        echo "  ERROR compressing: $file"
        (( errors++ )) || true
    fi
done < <(find "$LOG_DIR" -type f -name "*.log" -mtime +"$DAYS" -print0)

echo "Done. compressed=${compressed} errors=${errors}"
echo "=== $(TZ=America/Chicago date '+%F %T %Z') compress_old_logs: end ==="
