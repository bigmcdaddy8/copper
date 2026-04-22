#!/usr/bin/env bash
# after_hours_check.sh — Query stock quotes after market close.
# Intended to run at 3:15 PM CT / 4:15 PM ET (Mon–Fri) via cron.
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
source .env 2>/dev/null || true
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/edge_cases_$(date +%Y-%m-%d).log"
echo "=== $(date --iso-8601=seconds) after_hours_check ===" | tee -a "$LOG_FILE"
uv run tradier_sniffer demo edge_cases --run after_hours_quotes 2>&1 | tee -a "$LOG_FILE"
