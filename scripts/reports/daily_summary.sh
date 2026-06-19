#!/usr/bin/env bash
# Daily Summary Report — entries, closes, gross credit, and realized P/L per day.
#
# Usage:
#   ./daily_summary.sh               # last 7 days, TRD account
#   ./daily_summary.sh -d 14         # last 14 days
#   ./daily_summary.sh -a HD         # Holodeck account

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

ACCOUNT="${K9_ACCOUNT:-TRD}"
DAYS=7

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--account) ACCOUNT="$2"; shift 2 ;;
        -d|--days)    DAYS="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

uv run enc report daily --account "$ACCOUNT" --days "$DAYS"
