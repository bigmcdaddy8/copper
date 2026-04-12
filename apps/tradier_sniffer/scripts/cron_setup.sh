#!/usr/bin/env bash
# cron_setup.sh — Print the recommended crontab entries for tradier_sniffer.
# Schedules are in US Central Time (America/Chicago).
# CT is always 1 hour behind ET regardless of DST — no seasonal adjustment needed.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"

echo ""
echo "=== tradier_sniffer cron setup (America/Chicago / CT) ==="
echo ""

SYS_TZ="${TZ:-$(timedatectl 2>/dev/null | grep 'Time zone' | awk '{print $3}' || cat /etc/timezone 2>/dev/null || echo 'unknown')}"
echo "Detected system timezone: $SYS_TZ"

if [[ "$SYS_TZ" != *"America/Chicago"* && "$SYS_TZ" != *"Central"* && "$SYS_TZ" != *"CST"* && "$SYS_TZ" != *"CDT"* ]]; then
    echo ""
    echo "⚠️  WARNING: System timezone is not America/Chicago."
    echo "   The schedules below target these CT times:"
    echo "     8:45 AM CT  = 9:45 AM ET  (daily SIC entry)"
    echo "     3:10 PM CT  = 4:10 PM ET  (expiry check)"
    echo "     3:15 PM CT  = 4:15 PM ET  (after-hours quotes)"
    echo "   Adjust the hour/minute fields to match your local clock."
fi

echo ""
echo "Add the following lines to your crontab (run: crontab -e):"
echo ""
echo "# tradier_sniffer — daily SPX 0DTE SIC entry at 8:45 AM CT / 9:45 AM ET (Mon–Fri)"
echo "45 8 * * 1-5  bash $SCRIPT_DIR/daily_entry.sh"
echo ""
echo "# tradier_sniffer — option expiry timing check at 3:10 PM CT / 4:10 PM ET (Mon–Fri)"
echo "10 15 * * 1-5  bash $SCRIPT_DIR/expiry_check.sh"
echo ""
echo "# tradier_sniffer — after-hours quote check at 3:15 PM CT / 4:15 PM ET (Mon–Fri)"
echo "15 15 * * 1-5  bash $SCRIPT_DIR/after_hours_check.sh"
echo ""
echo "Logs will be written to: $APP_DIR/logs/edge_cases_YYYY-MM-DD.log"
echo ""
echo "To run the nickel pricing test manually (during market hours):"
echo "  bash $SCRIPT_DIR/nickel_test.sh"
echo ""
