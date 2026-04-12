#!/usr/bin/env bash
# daily_entry.sh — Place the daily SPX 0DTE SIC entry order.
# Intended to run at 8:45 AM CT / 9:45 AM ET (Mon–Fri) via cron.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
source .env 2>/dev/null || true
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/edge_cases_$(date +%Y-%m-%d).log"
echo "=== $(date --iso-8601=seconds) daily_entry ===" | tee -a "$LOG_FILE"
uv run tradier_sniffer demo scenario1 2>&1 | tee -a "$LOG_FILE"
