#!/usr/bin/env bash
# Tradier User API — CLI wrapper
#
# Usage: tradier-user.sh [FLAGS] SUBCOMMAND
#
# Subcommands:
#   profile     GET /v1/user/profile
#
# Flags:
#   -e, --env TRD|TRDS    Broker environment (default: TRD = production)
#   -j, --json            Raw JSON output (default)
#   -t, --table           Table-formatted output
#   -h, --help            Show this help
#
# Environment variables (loaded from .env automatically):
#   TRADIER_API_KEY             Production API token
#   TRADIER_SANDBOX_API_KEY     Sandbox API token
#
# Examples:
#   tradier-user.sh profile
#   tradier-user.sh -t profile
#   tradier-user.sh -e TRDS profile

set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_lib.sh
source "$SCRIPT_DIR/_lib.sh"

# --------------------------------------------------------------------------- #
# Usage                                                                        #
# --------------------------------------------------------------------------- #

usage() {
    cat >&2 <<'EOF'
Usage: tradier-user.sh [FLAGS] SUBCOMMAND

Subcommands:
  profile     Get user profile and linked account list

Flags:
  -e, --env TRD|TRDS    Broker environment (default: TRD)
  -j, --json            Raw JSON output (default)
  -t, --table           Table-formatted output
  -h, --help            Show this help

Examples:
  tradier-user.sh profile
  tradier-user.sh -t profile
  tradier-user.sh -e TRDS -t profile
EOF
    exit 1
}

# --------------------------------------------------------------------------- #
# Global flag parsing                                                          #
# --------------------------------------------------------------------------- #

ENV="TRD"
FMT="json"

while [[ $# -gt 0 ]]; do
    case "$1" in
        -e|--env)   ENV="$2"; shift 2 ;;
        -j|--json)  FMT="json"; shift ;;
        -t|--table) FMT="table"; shift ;;
        -h|--help)  usage ;;
        -*)         echo "Unknown flag: $1" >&2; usage ;;
        *)          break ;;
    esac
done

[[ $# -eq 0 ]] && usage
SUBCOMMAND="$1"; shift

trd_check_deps

# --------------------------------------------------------------------------- #
# Subcommands                                                                  #
# --------------------------------------------------------------------------- #

case "$SUBCOMMAND" in

# ---- profile ---------------------------------------------------------------
profile)
    raw=$(trd_get "$ENV" "/user/profile")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["ACCOUNT", "TYPE", "STATUS", "OPT_LVL", "DAY_TRADER", "CLASSIFICATION"],
             (.profile.account // [] | if type == "array" then .[] else . end |
              [.account_number, .type, .status,
               (.option_level | tostring), (.day_trader | tostring),
               .classification])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

*)
    echo "Unknown subcommand: '$SUBCOMMAND'" >&2
    usage
    ;;
esac
