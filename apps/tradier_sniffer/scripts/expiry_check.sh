#!/usr/bin/env bash
# expiry_check.sh — Poll for 0DTE option expiry status after market close.
# Intended to run at 3:10 PM CT / 4:10 PM ET (Mon–Fri) via cron.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
source .env 2>/dev/null || true
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/edge_cases_$(date +%Y-%m-%d).log"
echo "=== $(date --iso-8601=seconds) expiry_check ===" | tee -a "$LOG_FILE"
uv run tradier_sniffer demo edge_cases --run expiry_timing 2>&1 | tee -a "$LOG_FILE"
