#!/usr/bin/env bash
# Tradier Market Data API — CLI wrapper
#
# Usage: tradier-market.sh [FLAGS] SUBCOMMAND [SUBCOMMAND_FLAGS]
#
# Subcommands:
#   quotes        SYMBOLS                            GET /v1/markets/quotes
#   chains        SYMBOL EXPIRATION [--greeks]       GET /v1/markets/options/chains
#   strikes       SYMBOL EXPIRATION                  GET /v1/markets/options/strikes
#   expirations   SYMBOL                             GET /v1/markets/options/expirations
#   options-lookup UNDERLYING                        GET /v1/markets/options/lookup
#   history       SYMBOL [--start D] [--end D] [--interval INTERVAL]
#                                                    GET /v1/markets/history
#   timesales     SYMBOL [--start D] [--end D] [--interval INTERVAL]
#                                                    GET /v1/markets/timesales
#   etb                                              GET /v1/markets/etb
#   clock                                            GET /v1/markets/clock
#   calendar      [--month MM] [--year YYYY]         GET /v1/markets/calendar
#   search        QUERY [--indexes-only]             GET /v1/markets/search
#   lookup        QUERY [--exchanges E] [--types T]  GET /v1/markets/lookup
#
# Flags:
#   -e, --env TRD|TRDS    Broker environment (default: TRD = production)
#   -j, --json            Raw JSON output (default)
#   -t, --table           Table-formatted output
#   -h, --help            Show this help
#
# history --interval values:    daily (default), weekly, monthly
# timesales --interval values:  tick, 1min (default), 5min, 15min
#
# Examples:
#   tradier-market.sh clock
#   tradier-market.sh -t quotes XSP,SPY
#   tradier-market.sh -t chains XSP 2026-06-20 --greeks
#   tradier-market.sh -t expirations XSP
#   tradier-market.sh -t history XSP --start 2026-01-01 --end 2026-06-20
#   tradier-market.sh -t calendar --month 06 --year 2026
#   tradier-market.sh -t search "S&P 500"
#   tradier-market.sh -t etb

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
Usage: tradier-market.sh [FLAGS] SUBCOMMAND [SUBCOMMAND_FLAGS]

Subcommands:
  quotes        SYMBOLS                       Quotes (comma-separated symbols)
  chains        SYMBOL EXPIRATION [--greeks]  Options chain for expiration
  strikes       SYMBOL EXPIRATION             Available strikes
  expirations   SYMBOL                        Available expiration dates
  options-lookup UNDERLYING                   Option symbols for underlying
  history       SYMBOL [--start D] [--end D] [--interval I]  Historical OHLCV
  timesales     SYMBOL [--start D] [--end D] [--interval I]  Intraday time/sales
  etb           Easy-to-borrow securities list
  clock         Current market clock / session status
  calendar      [--month MM] [--year YYYY]    Market calendar
  search        QUERY [--indexes-only]        Symbol search
  lookup        QUERY [--exchanges E] [--types T]  Symbol lookup

Flags:
  -e, --env TRD|TRDS    Broker environment (default: TRD)
  -j, --json            Raw JSON output (default)
  -t, --table           Table-formatted output
  -h, --help            Show this help

history --interval:   daily (default), weekly, monthly
timesales --interval: tick, 1min (default), 5min, 15min

Examples:
  tradier-market.sh clock
  tradier-market.sh -t quotes XSP,SPY,QQQ
  tradier-market.sh -t chains XSP 2026-06-20 --greeks
  tradier-market.sh -t strikes XSP 2026-06-20
  tradier-market.sh -t expirations XSP
  tradier-market.sh -t history XSP --start 2026-01-01 --end 2026-06-20
  tradier-market.sh -t timesales XSP --interval 5min
  tradier-market.sh -t calendar --month 06 --year 2026
  tradier-market.sh -t search "S&P 500"
  tradier-market.sh -t lookup SPX --types I
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

# ---- quotes ----------------------------------------------------------------
quotes)
    [[ $# -eq 0 ]] && { echo "ERROR: SYMBOLS required (e.g. XSP,SPY)" >&2; exit 1; }
    SYMBOLS="$1"; shift
    GREEKS=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --greeks) GREEKS="true"; shift ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "symbols=${SYMBOLS}" "greeks=${GREEKS}")
    raw=$(trd_get "$ENV" "/markets/quotes${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "LAST", "CHANGE", "CHG%", "BID", "ASK", "VOLUME", "OPEN", "CLOSE"],
             (.quotes.quote // [] |
              if type == "array" then .[] else . end |
              [.symbol,
               ((.last // 0) | tostring),
               ((.change // 0) | tostring),
               ((.change_percentage // 0) | tostring),
               ((.bid // 0) | tostring),
               ((.ask // 0) | tostring),
               ((.volume // 0) | tostring),
               ((.open // 0) | tostring),
               ((.prevclose // 0) | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- options chains --------------------------------------------------------
chains)
    [[ $# -lt 2 ]] && { echo "ERROR: SYMBOL and EXPIRATION required" >&2; exit 1; }
    SYMBOL="$1"; EXPIRATION="$2"; shift 2
    GREEKS=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --greeks) GREEKS="true"; shift ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "symbol=${SYMBOL}" "expiration=${EXPIRATION}" "greeks=${GREEKS}")
    raw=$(trd_get "$ENV" "/markets/options/chains${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "TYPE", "STRIKE", "BID", "ASK", "LAST", "DELTA", "VOLUME", "OI"],
             (.options.option // [] |
              if type == "array" then .[] else . end |
              [.symbol, .option_type,
               (.strike | tostring),
               ((.bid // 0) | tostring),
               ((.ask // 0) | tostring),
               ((.last // 0) | tostring),
               ((.greeks.delta // "n/a") | tostring),
               ((.volume // 0) | tostring),
               ((.open_interest // 0) | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- options strikes -------------------------------------------------------
strikes)
    [[ $# -lt 2 ]] && { echo "ERROR: SYMBOL and EXPIRATION required" >&2; exit 1; }
    SYMBOL="$1"; EXPIRATION="$2"; shift 2
    QS=$(trd_build_qs "symbol=${SYMBOL}" "expiration=${EXPIRATION}")
    raw=$(trd_get "$ENV" "/markets/options/strikes${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["STRIKE"],
             (.strikes.strike // [] |
              if type == "array" then .[] else . end |
              [tostring])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- options expirations ---------------------------------------------------
expirations)
    [[ $# -eq 0 ]] && { echo "ERROR: SYMBOL required" >&2; exit 1; }
    SYMBOL="$1"; shift
    QS=$(trd_build_qs "symbol=${SYMBOL}")
    raw=$(trd_get "$ENV" "/markets/options/expirations${QS}")
    if [[ "$FMT" == "table" ]]; then
        # Response has either .expirations.date[] (strings) or
        # .expirations.expiration[] (objects with .date and .expiration_type)
        echo "$raw" | trd_print_table \
            '["DATE", "TYPE"],
             (.expirations |
              if .expiration then
                (.expiration // [] | if type == "array" then .[] else . end |
                 [.date, (.expiration_type // "")])
              else
                (.date // [] | if type == "array" then .[] else . end |
                 [., ""])
              end)
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- options lookup --------------------------------------------------------
options-lookup)
    [[ $# -eq 0 ]] && { echo "ERROR: UNDERLYING required" >&2; exit 1; }
    UNDERLYING="$1"; shift
    QS=$(trd_build_qs "underlying=${UNDERLYING}")
    raw=$(trd_get "$ENV" "/markets/options/lookup${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["ROOT_SYMBOL"],
             (.symbols // [] | .[].rootSymbol | [.])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- history ---------------------------------------------------------------
history)
    [[ $# -eq 0 ]] && { echo "ERROR: SYMBOL required" >&2; exit 1; }
    SYMBOL="$1"; shift
    START="" END="" INTERVAL=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --start)    START="$2";    shift 2 ;;
            --end)      END="$2";      shift 2 ;;
            --interval) INTERVAL="$2"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "symbol=${SYMBOL}" "start=${START}" "end=${END}" "interval=${INTERVAL}")
    raw=$(trd_get "$ENV" "/markets/history${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["DATE", "OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"],
             (.history.day // [] |
              if type == "array" then .[] else . end |
              [.date,
               (.open | tostring), (.high | tostring),
               (.low | tostring),  (.close | tostring),
               (.volume | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- timesales -------------------------------------------------------------
timesales)
    [[ $# -eq 0 ]] && { echo "ERROR: SYMBOL required" >&2; exit 1; }
    SYMBOL="$1"; shift
    START="" END="" INTERVAL=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --start)    START="$2";    shift 2 ;;
            --end)      END="$2";      shift 2 ;;
            --interval) INTERVAL="$2"; shift 2 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "symbol=${SYMBOL}" "start=${START}" "end=${END}" "interval=${INTERVAL}")
    raw=$(trd_get "$ENV" "/markets/timesales${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["TIME", "OPEN", "HIGH", "LOW", "CLOSE", "PRICE", "VOLUME"],
             (.series.data // [] |
              if type == "array" then .[] else . end |
              [.time,
               ((.open // 0) | tostring),  ((.high // 0) | tostring),
               ((.low // 0) | tostring),   ((.close // 0) | tostring),
               ((.price // 0) | tostring), ((.volume // 0) | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- etb -------------------------------------------------------------------
etb)
    raw=$(trd_get "$ENV" "/markets/etb")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "DESCRIPTION"],
             (.securities.security // [] |
              if type == "array" then .[] else . end |
              [.symbol, (.description // "")])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- clock -----------------------------------------------------------------
clock)
    raw=$(trd_get "$ENV" "/markets/clock")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["FIELD", "VALUE"],
             (.clock | to_entries[] | [.key, (.value | tostring)])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- calendar --------------------------------------------------------------
calendar)
    MONTH="" YEAR=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --month) MONTH="$2"; shift 2 ;;
            --year)  YEAR="$2";  shift 2 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "month=${MONTH}" "year=${YEAR}")
    raw=$(trd_get "$ENV" "/markets/calendar${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["DATE", "STATUS", "DESCRIPTION"],
             (.calendar.days.day // [] |
              if type == "array" then .[] else . end |
              [.date, .status, (.description // "")])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- search ----------------------------------------------------------------
search)
    [[ $# -eq 0 ]] && { echo "ERROR: QUERY required" >&2; exit 1; }
    QUERY="$1"; shift
    INDEXES_ONLY=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --indexes-only) INDEXES_ONLY="true"; shift ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "q=${QUERY}" "indexes_only=${INDEXES_ONLY}")
    raw=$(trd_get "$ENV" "/markets/search${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "EXCHANGE", "TYPE", "DESCRIPTION"],
             (.securities.security // [] |
              if type == "array" then .[] else . end |
              [.symbol, (.exch // ""), (.type // ""), (.description // "")])
             | @tsv'
    else
        echo "$raw" | trd_print_json
    fi
    ;;

# ---- lookup ----------------------------------------------------------------
lookup)
    [[ $# -eq 0 ]] && { echo "ERROR: QUERY required" >&2; exit 1; }
    QUERY="$1"; shift
    EXCHANGES="" TYPES=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --exchanges) EXCHANGES="$2"; shift 2 ;;
            --types)     TYPES="$2";     shift 2 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done
    QS=$(trd_build_qs "q=${QUERY}" "exchanges=${EXCHANGES}" "types=${TYPES}")
    raw=$(trd_get "$ENV" "/markets/lookup${QS}")
    if [[ "$FMT" == "table" ]]; then
        echo "$raw" | trd_print_table \
            '["SYMBOL", "EXCHANGE", "TYPE", "DESCRIPTION"],
             (.securities.security // [] |
              if type == "array" then .[] else . end |
              [.symbol, (.exch // ""), (.type // ""), (.description // "")])
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
