#!/usr/bin/env bash
# Active Trades Report — shows all open (filled, not yet closed) trades.
#
# Usage:
#   ./active_trades.sh               # standard view, TRD account
#   ./active_trades.sh -a TRDS       # sandbox account
#   ./active_trades.sh -v            # verbose: includes strikes, BPR, order IDs, broker tag
#   ./active_trades.sh -a HD -v      # Holodeck verbose

set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

ACCOUNT="${K9_ACCOUNT:-TRD}"
VERBOSE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--account) ACCOUNT="$2"; shift 2 ;;
        -v|--verbose) VERBOSE="--verbose"; shift ;;
        *) echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

uv run enc report active --account "$ACCOUNT" $VERBOSE
