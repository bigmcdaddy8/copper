#!/usr/bin/env bash
# Account Balance History Report — daily account balance over time.
#
# Usage:
#   ./account_balance_history.sh                  # last 7 days (WEEK), TRD account
#   ./account_balance_history.sh -p MONTH         # last month
#   ./account_balance_history.sh -p YTD           # year to date
#   ./account_balance_history.sh -p YEAR          # 1 year
#   ./account_balance_history.sh -p YEAR_3        # 3 years
#   ./account_balance_history.sh -p YEAR_5        # 5 years
#   ./account_balance_history.sh -p ALL           # all available history
#   ./account_balance_history.sh -a TRDS          # sandbox account
#   ./account_balance_history.sh --json           # raw JSON output

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

ACCOUNT="${K9_ACCOUNT:-TRD}"
PERIOD="WEEK"
JSON_FLAG=""
RAW_FLAG=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--account) ACCOUNT="$2"; shift 2 ;;
        -p|--period)  PERIOD="$2";  shift 2 ;;
        --json|-j)    JSON_FLAG="--json"; shift ;;
        --raw|-r)     RAW_FLAG="--raw";   shift ;;
        *) echo "Unknown option: $1" >&2
           echo "Usage: $0 [-a ACCOUNT] [-p WEEK|MONTH|YTD|YEAR|YEAR_3|YEAR_5|ALL] [--json] [--raw]" >&2
           exit 1 ;;
    esac
done

uv run enc report balance-history --account "$ACCOUNT" --period "$PERIOD" $JSON_FLAG $RAW_FLAG

