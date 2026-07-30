#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"
source "$REPO_ROOT/scripts/lib/require_ct_time.sh"

TODAY_CT="$(TZ=America/Chicago date +%F)"
LOG_DIR="$REPO_ROOT/logs/K9"
LOG_FILE="$LOG_DIR/k9_weekly_flow_report_xsp_${TODAY_CT}.log"
mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

if ! require_ct_time "07:00" "K9 weekly flow report"; then
  exit 0
fi

echo "=== $(TZ=America/Chicago date '+%F %T %Z') K9 weekly flow report ==="

# Weekly window ending today in CT.
DATE_TO="$TODAY_CT"
DATE_FROM="$(TZ=America/Chicago date -d "$TODAY_CT - 6 days" +%F)"

uv run enc report weekly-flow \
  --account TRD \
  --spec xsp_pcs_0dte_PROD \
  --from "$DATE_FROM" \
  --to "$DATE_TO"
