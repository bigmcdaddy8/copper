#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

TODAY_CT="$(TZ=America/Chicago date +%F)"
LOG_DIR="$REPO_ROOT/logs/K9"
LOG_FILE="$LOG_DIR/k9_daily_close_xsp_${TODAY_CT}.log"
mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

echo "=== $(TZ=America/Chicago date '+%F %T %Z') K9 daily close ==="

uv run K9 close --account TRD --spec-name xsp_pcs_0dte_PROD
