#!/usr/bin/env bash
# Tradier API — shared library for CLI wrapper scripts.
#
# Source with: source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"
#
# Provides:
#   trd_base_url  ENV            → base URL string
#   trd_token     ENV            → API token string
#   trd_account_id ENV           → account ID string
#   trd_get       ENV PATH ...   → authenticated GET, JSON to stdout
#   trd_post      ENV PATH ...   → authenticated POST, JSON to stdout
#   trd_build_qs  K=V ...        → builds "?k=v&k2=v2" (skips empty values)
#   trd_print_json               → pretty-print JSON from stdin
#   trd_print_table FILTER       → jq filter → column-aligned table from stdin
#   trd_check_deps               → verify jq and column are installed

# Repo root is two levels up from scripts/tradier/
_TRD_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

_trd_load_dotenv() {
    local envfile="$_TRD_REPO_ROOT/.env"
    if [[ -f "$envfile" ]]; then
        set -a
        # shellcheck disable=SC1090
        source "$envfile"
        set +a
    fi
}

trd_base_url() {
    # $1: TRD (production) | TRDS (sandbox)
    if [[ "${1:-TRD}" == "TRDS" ]]; then
        echo "https://sandbox.tradier.com/v1"
    else
        echo "https://api.tradier.com/v1"
    fi
}

trd_token() {
    # $1: TRD | TRDS
    _trd_load_dotenv
    if [[ "${1:-TRD}" == "TRDS" ]]; then
        echo "${TRADIER_SANDBOX_API_KEY:-}"
    else
        echo "${TRADIER_API_KEY:-}"
    fi
}

trd_account_id() {
    # $1: TRD | TRDS
    _trd_load_dotenv
    if [[ "${1:-TRD}" == "TRDS" ]]; then
        echo "${TRADIER_SANDBOX_ACCOUNT_ID:-}"
    else
        echo "${TRADIER_ACCOUNT_ID:-}"
    fi
}

trd_get() {
    # trd_get ENV PATH [extra-curl-args...]
    local env="$1" path="$2"; shift 2
    local token; token="$(trd_token "$env")"
    if [[ -z "$token" ]]; then
        echo "ERROR: No API token for environment '${env}'." \
             "Set TRADIER_API_KEY (TRD) or TRADIER_SANDBOX_API_KEY (TRDS)." >&2
        exit 1
    fi
    curl --silent --fail \
        --request GET \
        --url "$(trd_base_url "$env")${path}" \
        --header "Accept: application/json" \
        --header "Authorization: Bearer ${token}" \
        "$@"
}

trd_post() {
    # trd_post ENV PATH [extra-curl-args...]
    local env="$1" path="$2"; shift 2
    local token; token="$(trd_token "$env")"
    if [[ -z "$token" ]]; then
        echo "ERROR: No API token for environment '${env}'." \
             "Set TRADIER_API_KEY (TRD) or TRADIER_SANDBOX_API_KEY (TRDS)." >&2
        exit 1
    fi
    curl --silent --fail \
        --request POST \
        --url "$(trd_base_url "$env")${path}" \
        --header "Accept: application/json" \
        --header "Authorization: Bearer ${token}" \
        "$@"
}

trd_build_qs() {
    # trd_build_qs "key1=val1" "key2=val2" ...
    # Returns empty string or "?key1=val1&key2=val2" — skips pairs with empty value.
    local qs=""
    for kv in "$@"; do
        local key="${kv%%=*}"
        local val="${kv#*=}"
        [[ -z "$val" ]] && continue
        if [[ -z "$qs" ]]; then
            qs="?${key}=${val}"
        else
            qs="${qs}&${key}=${val}"
        fi
    done
    printf '%s' "$qs"
}

trd_print_json() {
    # Pretty-print JSON from stdin.
    jq .
}

trd_print_table() {
    # Apply jq filter to JSON from stdin, then column-align the TSV output.
    # $1: a jq -r filter that ends with | @tsv
    jq -r "$1" | column -t -s $'\t'
}

trd_check_deps() {
    local missing=()
    command -v jq     &>/dev/null || missing+=("jq")
    command -v column &>/dev/null || missing+=("column (util-linux)")
    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "ERROR: Missing required tools: ${missing[*]}" >&2
        echo "  Install with: sudo apt install jq util-linux" >&2
        exit 1
    fi
}
