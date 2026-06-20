#!/usr/bin/env bash
# Tradier Accounts API — CLI wrapper
#
# Usage: tradier-account.sh [FLAGS] SUBCOMMAND [SUBCOMMAND_FLAGS]
#
# Subcommands:
#   balance                                    GET /v1/accounts/{id}/balances
#   positions                                  GET /v1/accounts/{id}/positions
#   history    [--limit N] [--type TYPE]       GET /v1/accounts/{id}/history
#   gainloss   [--limit N] [--start D] [--end D]  GET /v1/accounts/{id}/gainloss
#   orders     [--tags]                        GET /v1/accounts/{id}/orders
#   order      ORDER_ID                        GET /v1/accounts/{id}/orders/{id}
#
# Flags:
#   -e, --env TRD|TRDS    Broker environment (default: TRD = production)
#   -a, --account ACCT    Account number (default: from .env)
#   -j, --json            Raw JSON output (default)
#   -t, --table           Table-formatted output
#   -h, --help            Show this help
#
# Environment variables (loaded from .env automatically):
#   TRADIER_API_KEY             Production API token
#   TRADIER_SANDBOX_API_KEY     Sandbox API token
#   TRADIER_ACCOUNT_ID          Production account number
#   TRADIER_SANDBOX_ACCOUNT_ID  Sandbox account number
#
# history --type values: trade, option, ach, wire, dividend, fee, tax, journal,
#                        check, transfer, adjustment, interest
#
# Examples:
#   tradier-account.sh balance
#   tradier-account.sh -t positions
#   tradier-account.sh -e TRDS -t history --limit 20 --type trade
#   tradier-account.sh -t gainloss --start 2026-01-01 --end 2026-06-30
#   tradier-account.sh -t orders --tags
#   tradier-account.sh -t order 12345678

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
Usage: tradier-account.sh [FLAGS] SUBCOMMAND [SUBCOMMAND_FLAGS]

Subcommands:
  balance                                        Account balances
  positions                                      Open positions
  history    [--limit N] [--type TYPE]           Account history events
  gainloss   [--limit N] [--start DATE] [--end DATE]  Closed position P&L
  orders     [--tags]                            All account orders
  order      ORDER_ID                            Single order detail

Flags:
  -e, --env TRD|TRDS    Broker environment (default: TRD)
  -a, --account ACCT    Override account number
  -j, --json            Raw JSON output (default)
  -t, --table           Table-formatted output
  -h, --help            Show this help

history --type values:
  trade, option, ach, wire, dividend, fee, tax, journal,
  check, transfer, adjustment, interest

Examples:
  tradier-account.sh balance
  tradier-account.sh -t positions
  tradier-account.sh -e TRDS -t history --limit 20 --type trade
  tradier-account.sh -t gainloss --start 2026-01-01 --end 2026-06-30
  tradier-account.sh -t orders --tags
  tradier-account.sh -t order 12345678
EOF
    exit 1
}

# --------------------------------------------------------------------------- #
# Global flag parsing                                                          #
# --------------------------------------------------------------------------- #

ENV="TRD"
FMT="json"
ACCT_OVERRIDE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -e|--env)     ENV="$2"; shift 2 ;;
        -a|--account) ACCT_OVERRIDE="$2"; shift 2 ;;
        -j|--json)    FMT="json"; shift ;;
        -t|--table)   FMT="table"; shift ;;
        -h|--help)    usage ;;
        -*)           echo "Unknown flag: $1" >&2; usage ;;
        *)            break ;;
    esac
done

[[ $# -eq 0 ]] && usage
SUBCOMMAND="$1"; shift

trd_check_deps

# Resolve account ID (override > env var from .env)
_acct() {
    local id="${ACCT_OVERRIDE:-$(trd_account_id "$ENV")}"
    if [[ -z "$id" ]]; then
        echo "ERROR: No account ID. Set TRADIER_ACCOUNT_ID (TRD) or" \
             "TRADIER_SANDBOX_ACCOUNT_ID (TRDS), or use -a/--account." >&2
        exit 1
    fi
    echo "$id"
}

# --------------------------------------------------------------------------- #
# Subcommands                                                                  #
# --------------------------------------------------------------------------- #

case "$SUBCOMMAND" in

# ---- balance ---------------------------------------------------------------
balance)
    ACCT="$(_acct)"
    raw=$(trd_get "$ENV" "/accounts/${ACCT}/balances")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["FIELD", "VALUE"],
             (.balances | to_entries[] |
              select(.value | type == "number" or type == "string") |
              [.key, (.value | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- positions -------------------------------------------------------------
positions)
    ACCT="$(_acct)"
    raw=$(trd_get "$ENV" "/accounts/${ACCT}/positions")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "QTY", "COST_BASIS", "DATE_ACQUIRED"],
             (.positions | if type == "object" then .position // [] else [] end |
              if type == "array" then .[] else . end |
              [.symbol, (.quantity | tostring),
               (.cost_basis | tostring), (.date_acquired // "")])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- history ---------------------------------------------------------------
history)
    LIMIT="" TYPE=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --limit) LIMIT="$2"; shift 2 ;;
            --type)  TYPE="$2";  shift 2 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    ACCT="$(_acct)"
    QS=$(trd_build_qs "limit=${LIMIT}" "type=${TYPE}")
    raw=$(trd_get "$ENV" "/accounts/${ACCT}/history${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["DATE", "TYPE", "DESCRIPTION", "AMOUNT"],
             (.history | if type == "object" then .event // [] else [] end |
              if type == "array" then .[] else . end |
              [.date, .type, (.description // ""),
               ((.amount // 0) | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- gainloss --------------------------------------------------------------
gainloss)
    LIMIT="" START="" END=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --limit) LIMIT="$2"; shift 2 ;;
            --start) START="$2"; shift 2 ;;
            --end)   END="$2";   shift 2 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    ACCT="$(_acct)"
    QS=$(trd_build_qs "limit=${LIMIT}" "start=${START}" "end=${END}")
    raw=$(trd_get "$ENV" "/accounts/${ACCT}/gainloss${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "OPEN_DATE", "CLOSE_DATE", "GAIN_LOSS", "GAIN_LOSS_PCT"],
             (.gainloss.closed_position // [] |
              if type == "array" then .[] else . end |
              [.symbol, (.open_date // ""), (.close_date // ""),
               ((.gain_loss // 0) | tostring),
               ((.gain_loss_percent // 0) | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- orders ----------------------------------------------------------------
orders)
    TAGS=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --tags) TAGS="true"; shift ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    ACCT="$(_acct)"
    QS=$(trd_build_qs "includeTags=${TAGS}")
    raw=$(trd_get "$ENV" "/accounts/${ACCT}/orders${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["ID", "TYPE", "SYMBOL", "SIDE", "QTY", "STATUS", "PRICE", "TAG"],
             (.orders | if type == "object" then .order // [] else [] end |
              if type == "array" then .[] else . end |
              [(.id | tostring), .type, (.symbol // ""), .side,
               (.quantity | tostring), .status,
               ((.price // "MKT") | tostring),
               (.tag // "")])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- order (single) --------------------------------------------------------
order)
    [[ $# -eq 0 ]] && { echo "ERROR: ORDER_ID required" >&2; usage; }
    ORDER_ID="$1"; shift
    ACCT="$(_acct)"
    raw=$(trd_get "$ENV" "/accounts/${ACCT}/orders/${ORDER_ID}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["FIELD", "VALUE"],
             (.order | to_entries[] |
              select(.value | type != "object" and type != "array") |
              [.key, (.value | tostring)])
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
