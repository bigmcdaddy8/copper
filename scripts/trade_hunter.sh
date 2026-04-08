#!/bin/bash

# check for the -v | --verbose flag and set a variable to pass to the main script
VERBOSE=""
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
  VERBOSE="--verbose"
fi

ONEDRIVE_MOUNT="/home/temckee8/OneDriveMount"
LOCAL_DATA_DIR="/home/temckee8/Documents/data/copper/trade_hunter"
DOWNLOADS_DIR="/DropboxClone/ToddStuff/trading/downloads"
WORKSHEETS_DIR="/DropboxClone/ToddStuff/trading/worksheets"
UPLOADS_DIR="/uploads"
CACHE_DIR="/data"
LOG_DIR="/logs"
DOWNLOADS_DIR_FULLPATH="${ONEDRIVE_MOUNT}${DOWNLOADS_DIR}"
WORKSHEETS_DIR_FULLPATH="${ONEDRIVE_MOUNT}${WORKSHEETS_DIR}"
UPLOADS_DIR_FULLPATH="${LOCAL_DATA_DIR}${UPLOADS_DIR}"
CACHE_DIR_FULLPATH="${LOCAL_DATA_DIR}${CACHE_DIR}"
LOG_DIR_FULLPATH="${LOCAL_DATA_DIR}${LOG_DIR}"

rclone rc vfs/refresh dir="${DOWNLOADS_DIR}"
rclone rc vfs/refresh dir="${WORKSHEETS_DIR}"

# Wait a few seconds to ensure rclone has completed the refresh before running the main script
sleep 8

# Resolve most recent input files (sorted by filename, not mtime)
TT_FILE=$(ls "${DOWNLOADS_DIR_FULLPATH}"/tastytrade_watchlist_m8investments_Russell\ 1000_??????.csv 2>/dev/null | tail -1)
BULL_FILE=$(ls "${DOWNLOADS_DIR_FULLPATH}"/Copper_BULLish\ 20??-??-??.xlsx 2>/dev/null | tail -1)
BEAR_FILE=$(ls "${DOWNLOADS_DIR_FULLPATH}"/Copper_BEARish\ 20??-??-??.xlsx 2>/dev/null | tail -1)

# Guard: abort if any required file is missing
MISSING=0
[[ -z "$TT_FILE"   ]] && echo "ERROR: No TastyTrade CSV found in ${DOWNLOADS_DIR_FULLPATH}" && MISSING=1
[[ -z "$BULL_FILE" ]] && echo "ERROR: No BULL-ish Excel found in ${DOWNLOADS_DIR_FULLPATH}" && MISSING=1
[[ -z "$BEAR_FILE" ]] && echo "ERROR: No BEAR-ish Excel found in ${DOWNLOADS_DIR_FULLPATH}" && MISSING=1
[[ "$MISSING" -eq 1 ]] && exit 1

echo "TastyTrade : ${TT_FILE}"
echo "BULL-ish   : ${BULL_FILE}"
echo "BEAR-ish   : ${BEAR_FILE}"
echo "Journal    : (auto-discovered from ${WORKSHEETS_DIR_FULLPATH})"
echo "Cache      : ${CACHE_DIR_FULLPATH}"
echo "Logs       : ${LOG_DIR_FULLPATH}"
echo "Output     : ${UPLOADS_DIR_FULLPATH}"
echo ""

cd /home/temckee8/Documents/REPOs/copper/apps/trade_hunter
if [ $? -ne 0 ]; then
  echo "ERROR: Failed to change directory to /home/temckee8/Documents/REPOs/copper/apps/trade_hunter"
  exit 1
fi

uv run python -m trade_hunter run \
  --tastytrade-file "${TT_FILE}" \
  --bull-file "${BULL_FILE}" \
  --bear-file "${BEAR_FILE}" \
  --worksheets-dir "${WORKSHEETS_DIR_FULLPATH}" \
  --output-dir "${UPLOADS_DIR_FULLPATH}" \
  --cache-dir "${CACHE_DIR_FULLPATH}" \
  ${VERBOSE} 2>&1 | tee "${LOG_DIR_FULLPATH}/trade_hunter_verbose.log"
EXIT_CODE=${PIPESTATUS[0]}

# Rename the workbook with today's date on success
if [[ $EXIT_CODE -eq 0 ]]; then
  DATE_SUFFIX=$(date +%Y-%m-%d)
  SRC="${UPLOADS_DIR_FULLPATH}/trade_signals.xlsx"
  DST="${UPLOADS_DIR_FULLPATH}/trade_signals_${DATE_SUFFIX}.xlsx"
  if [[ -f "$SRC" ]]; then
    if cp "$SRC" "$DST"; then
      echo "Workbook copied to: trade_signals_${DATE_SUFFIX}.xlsx"
    else
      echo "WARNING: Could not copy workbook to trade_signals_${DATE_SUFFIX}.xlsx"
    fi
  fi
fi

exit $EXIT_CODE
