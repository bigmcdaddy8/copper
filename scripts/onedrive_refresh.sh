#!/bin/bash

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

echo "INFO: refreshed onedrive directories: ${DOWNLOADS_DIR} ${WORKSHEETS_DIR}"

echo "INFO: ls -ls ${DOWNLOADS_DIR_FULLPATH}..."
ls -ls ${DOWNLOADS_DIR_FULLPATH}


