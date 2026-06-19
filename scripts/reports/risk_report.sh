#!/usr/bin/env bash
# Open Risk Report — capital at risk snapshot for all currently open trades.
#
# Usage:
#   ./risk_report.sh                 # TRD account
#   ./risk_report.sh -a TRDS         # sandbox account

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

ACCOUNT="${K9_ACCOUNT:-TRD}"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--account) ACCOUNT="$2"; shift 2 ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

uv run enc report risk --account "$ACCOUNT"
