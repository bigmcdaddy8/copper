#!/usr/bin/env bash
# Orphan / Unreconciled Trades Report — filled trades past expiration with no close recorded.
#
# These trades require manual reconciliation: check the brokerage for the
# final settlement/expiry result and update captains_log accordingly.
#
# Usage:
#   ./orphans.sh                     # TRD account
#   ./orphans.sh -a TRDS             # sandbox account

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

uv run enc report orphans --account "$ACCOUNT"
