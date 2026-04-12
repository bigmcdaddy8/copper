#!/usr/bin/env bash
# nickel_test.sh — Test penny-priced limit on a nickel-only option.
# Run once manually during market hours.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."
source .env 2>/dev/null || true
LOG_DIR="logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/edge_cases_$(date +%Y-%m-%d).log"
echo "=== $(date --iso-8601=seconds) nickel_test ===" | tee -a "$LOG_FILE"
uv run tradier_sniffer demo edge_cases --run nickel_pricing 2>&1 | tee -a "$LOG_FILE"
