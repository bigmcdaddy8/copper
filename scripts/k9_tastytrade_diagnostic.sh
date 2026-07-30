#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"
source "$REPO_ROOT/scripts/lib/require_ct_time.sh"

TODAY_CT="$(TZ=America/Chicago date +%F)"
LOG_DIR="$REPO_ROOT/logs/K9"
LOG_FILE="$LOG_DIR/k9_tastytrade_diagnostic_${TODAY_CT}.log"
mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

if ! require_ct_time "09:45" "Tastytrade diagnostic"; then
	exit 0
fi

echo "=== $(TZ=America/Chicago date '+%F %T %Z') Tastytrade diagnostic ==="
uv run K9 tastytrade-diagnostic