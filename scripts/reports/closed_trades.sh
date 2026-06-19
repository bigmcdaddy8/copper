#!/usr/bin/env bash
# Closed Trades Report — shows trades closed in the last N days.
#
# Usage:
#   ./closed_trades.sh               # last 7 days, TRD account
#   ./closed_trades.sh -d 30         # last 30 days
#   ./closed_trades.sh -a TRDS       # sandbox account
#   ./closed_trades.sh --from 2026-06-01 --to 2026-06-30

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

ACCOUNT="${K9_ACCOUNT:-TRD}"
DAYS=7
FROM_DATE=""
TO_DATE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--account) ACCOUNT="$2"; shift 2 ;;
        -d|--days)    DAYS="$2"; shift 2 ;;
        --from)       FROM_DATE="--from $2"; shift 2 ;;
        --to)         TO_DATE="--to $2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

uv run enc report closed \
    --account "$ACCOUNT" \
    --days "$DAYS" \
    $FROM_DATE \
    $TO_DATE
