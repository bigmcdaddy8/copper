#!/bin/bash

# check for the -v | --verbose flag and set a variable to pass to the main script
VERBOSE=""
if [[ "$1" == "-v" || "$1" == "--verbose" ]]; then
  VERBOSE="--verbose"
fi

DROPBOX_MOUNT="/home/temckee8/OneDriveMount"
DROPBOX_DOWNLOADS_DIR="/DropboxClone/ToddStuff/trading/downloads"
DROPBOX_WORKSHEETS_DIR="/DropboxClone/ToddStuff/trading/worksheets"
DROPBOX_UPLOADS_DIR="/DropboxClone/ToddStuff/trading/uploads"
DROPBOX_DOWNLOADS_DIR_FULLPATH="${DROPBOX_MOUNT}${DROPBOX_DOWNLOADS_DIR}"
DROPBOX_WORKSHEETS_DIR_FULLPATH="${DROPBOX_MOUNT}${DROPBOX_WORKSHEETS_DIR}"
DROPBOX_UPLOADS_DIR_FULLPATH="${DROPBOX_MOUNT}${DROPBOX_UPLOADS_DIR}"

rclone rc vfs/refresh dir="${DROPBOX_DOWNLOADS_DIR}"
rclone rc vfs/refresh dir="${DROPBOX_WORKSHEETS_DIR}"
rclone rc vfs/refresh dir="${DROPBOX_UPLOADS_DIR}"

# Wait a few seconds to ensure rclone has completed the refresh before running the main script
sleep 8

# Resolve most recent input files (sorted by filename, not mtime)
TT_FILE=$(ls "${DROPBOX_DOWNLOADS_DIR_FULLPATH}"/tastytrade_watchlist_m8investments_Russell\ 1000_??????.csv 2>/dev/null | tail -1)
BULL_FILE=$(ls "${DROPBOX_DOWNLOADS_DIR_FULLPATH}"/Copper_BULLish\ 20??-??-??.xlsx 2>/dev/null | tail -1)
BEAR_FILE=$(ls "${DROPBOX_DOWNLOADS_DIR_FULLPATH}"/Copper_BEARish\ 20??-??-??.xlsx 2>/dev/null | tail -1)

# Guard: abort if any required file is missing
MISSING=0
[[ -z "$TT_FILE"   ]] && echo "ERROR: No TastyTrade CSV found in ${DROPBOX_DOWNLOADS_DIR_FULLPATH}" && MISSING=1
[[ -z "$BULL_FILE" ]] && echo "ERROR: No BULL-ish Excel found in ${DROPBOX_DOWNLOADS_DIR_FULLPATH}" && MISSING=1
[[ -z "$BEAR_FILE" ]] && echo "ERROR: No BEAR-ish Excel found in ${DROPBOX_DOWNLOADS_DIR_FULLPATH}" && MISSING=1
[[ "$MISSING" -eq 1 ]] && exit 1

echo "TastyTrade : ${TT_FILE}"
echo "BULL-ish   : ${BULL_FILE}"
echo "BEAR-ish   : ${BEAR_FILE}"
echo "Journal    : (auto-discovered from ${DROPBOX_WORKSHEETS_DIR_FULLPATH})"
echo "Output     : ${DROPBOX_UPLOADS_DIR_FULLPATH}"
echo ""

cd /home/temckee8/Documents/REPOs/copper/apps/trade_hunter

uv run python -m trade_hunter run \
  --tastytrade-file "${TT_FILE}" \
  --bull-file "${BULL_FILE}" \
  --bear-file "${BEAR_FILE}" \
  --worksheets-dir "${DROPBOX_WORKSHEETS_DIR_FULLPATH}" \
  --output-dir "${DROPBOX_UPLOADS_DIR_FULLPATH}" \
  ${VERBOSE} 2>&1 | tee /tmp/trade_hunter_verbose.log
EXIT_CODE=${PIPESTATUS[0]}

# Let the write flush back to the backend
sleep 8

rclone rc vfs/refresh dir="${DROPBOX_UPLOADS_DIR}"

# Wait a few seconds to ensure rclone has completed the refresh
sleep 8

# Rename the workbook with today's date on success
if [[ $EXIT_CODE -eq 0 ]]; then
  DATE_SUFFIX=$(date +%Y-%m-%d)
  SRC="${DROPBOX_UPLOADS_DIR_FULLPATH}/trade_signals.xlsx"
  DST="${DROPBOX_UPLOADS_DIR_FULLPATH}/trade_signals_${DATE_SUFFIX}.xlsx"
  if [[ -f "$SRC" ]]; then
    if cp "$SRC" "$DST"; then
      echo "Workbook copied to: trade_signals_${DATE_SUFFIX}.xlsx"
    else
      echo "WARNING: Could not copy workbook to trade_signals_${DATE_SUFFIX}.xlsx"
    fi
  fi
fi

exit $EXIT_CODE
