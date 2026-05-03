#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

SPEC_NAME="xsp_pcs_0dte_w2_none_0900_trds"
ACCOUNT="TRDS"
UNDERLYING="XSP"
TRADE_TYPE="PUT_CREDIT_SPREAD"

TODAY_CT="$(TZ=America/Chicago date +%F)"
TODAY_YMD_CT="$(TZ=America/Chicago date +%Y%m%d)"
LOG_DIR="$REPO_ROOT/logs/K9"

FAILED=0

pass() {
  printf "[PASS] %s\n" "$1"
}

fail() {
  printf "[FAIL] %s\n" "$1"
  FAILED=1
}

section() {
  printf "\n=== %s ===\n" "$1"
}

section "K9 Morning Check"
printf "Spec: %s\n" "$SPEC_NAME"
printf "Account: %s\n" "$ACCOUNT"
printf "Date (CT): %s\n" "$TODAY_CT"

section "Checklist A: K9 Run Log"
if compgen -G "$LOG_DIR/${SPEC_NAME}_${TODAY_YMD_CT}_*.json" > /dev/null; then
  pass "Found K9 run log(s) for today."
  ls -1 "$LOG_DIR/${SPEC_NAME}_${TODAY_YMD_CT}_"*.json 2>/dev/null | tail -n 3
else
  fail "No K9 run logs found for ${SPEC_NAME} on ${TODAY_CT}."
fi

section "Checklist B/C: Journal Entry and Field Validation"
if "$REPO_ROOT/.venv/bin/python" - <<'PY'
import os
import sys
from captains_log.journal import Journal

spec = "xsp_pcs_0dte_w2_none_0900_trds"
account = "TRDS"
today = os.popen("TZ=America/Chicago date +%F").read().strip()

journal = Journal(account=account)
trades = journal.list_trades(date=today, spec_name=spec, account=account)
print(f"Trades found today for spec: {len(trades)}")

if not trades:
    print("VALIDATION_FAIL: no trade journal records for this spec/date")
    sys.exit(1)

latest = trades[0]
print(f"Latest trade_id: {latest.trade_id}")
print(f"Outcome: {latest.outcome}")
print(f"Underlying: {latest.underlying}")
print(f"Trade type: {latest.trade_type}")
print(f"Entry filled price: {latest.entry_filled_price}")
print(f"TP order id: {latest.tp_order_id}")
print(f"TP status: {latest.tp_status}")
print(f"Short put strike: {latest.short_put_strike}")
print(f"Long put strike: {latest.long_put_strike}")

errors = []
if latest.underlying != "XSP":
    errors.append(f"unexpected underlying: {latest.underlying}")
if latest.trade_type != "PUT_CREDIT_SPREAD":
    errors.append(f"unexpected trade_type: {latest.trade_type}")
if latest.short_put_strike is None or latest.long_put_strike is None:
    errors.append("put spread strikes are missing")

if latest.outcome == "FILLED":
    if latest.entry_filled_price is None:
        errors.append("filled trade missing entry_filled_price")
    if latest.tp_order_id:
        errors.append("exit_type NONE expected empty tp_order_id")
    if latest.tp_status not in {"NONE", "ORPHAN"}:
        errors.append(f"unexpected tp_status for NONE exit: {latest.tp_status}")

if errors:
    print("VALIDATION_FAIL:")
    for e in errors:
        print(f" - {e}")
    sys.exit(1)

print("VALIDATION_PASS")
sys.exit(0)
PY
then
  pass "Journal checks passed for latest trade record."
else
  fail "Journal checks failed."
fi

section "Checklist D: Optional Reporting Snapshot"
set +e
uv run enc trades -a "$ACCOUNT" -s FILLED
REPORT_RC=$?
set -e
if [[ $REPORT_RC -eq 0 ]]; then
  pass "Report snapshot command executed."
else
  fail "Report snapshot command failed (uv run enc trades)."
fi

section "Checklist B (Human Readable)"
set +e
uv run captains_log list --account "$ACCOUNT" --spec "$SPEC_NAME" --date "$TODAY_CT"
LIST_RC=$?
set -e
if [[ $LIST_RC -eq 0 ]]; then
  pass "captains_log list command executed."
else
  fail "captains_log list command failed."
fi

section "Final Result"
if [[ $FAILED -eq 0 ]]; then
  printf "PASS\n"
  exit 0
fi

printf "FAIL\n"
exit 1
