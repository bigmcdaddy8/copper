#!/usr/bin/env bash
# 0X-B REST-only production-readiness smoke on dragon. No quote token, no capture, no systemd start.
set -u
cd ~/Documents/REPOs/copper
UV=$HOME/.local/bin/uv
W=$(mktemp -d /tmp/0xb.XXXX)
echo "##### $(date -u +%FT%TZ) host=$(hostname) HEAD=$(git rev-parse HEAD)"
echo "##### 1. live production preflight script (REST list_futures only; run directly, so no gate marker is written)"
$UV run --frozen python scripts/dicks_lab_preflight.py; echo "rc=$?"
ls /run/dicks-lab-launch-gate/preflight-ok 2>/dev/null && echo "MARKER PRESENT (unexpected)" || echo "no gate marker (expected)"
echo "##### 2. live roll check (default: upcoming trading date)"
$UV run --frozen python scripts/dicks_lab_roll_check.py check; echo "rc=$?"
echo "##### snapshot live metadata for offline replays (REST only)"
$UV run --frozen python - "$W" <<'PY'
import json, sys
from dotenv import load_dotenv
load_dotenv(".env")
from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.settings import TastytradeSettings
rows = [r for r in TastytradeClient(TastytradeSettings.from_environment("tastytrade_production")).list_futures()
        if r.get("product-code") == "ES"]
json.dump(rows, open(f"{sys.argv[1]}/live.json", "w"))
# Expected Sunday 2026-12-13 broker state: broker roll offset (4 business days -> Mon 12-14) has advanced
# active-month to /ESH7 and next-active to /ESM7. Derived from the live rows; only the two flags change.
for r in rows:
    r["active-month"] = r["symbol"] == "/ESH7"
    r["next-active-month"] = r["symbol"] == "/ESM7"
json.dump(rows, open(f"{sys.argv[1]}/dec13_derived.json", "w"))
print("ES rows", len(rows))
PY
for spec in "2026-11-30 /ESZ6 live" "2026-12-11 /ESZ6 live" "2026-12-14 /ESZ6 live" "2026-12-14 /ESZ6 dec13_derived" "2026-12-14 /ESH7 dec13_derived" "2026-12-18 /ESZ6 dec13_derived"; do
  set -- $spec
  echo "##### 3. offline check --trading-date $1 --pin $2 (metadata: $3)"
  $UV run --frozen python scripts/dicks_lab_roll_check.py check --trading-date $1 --pin $2 --metadata-json $W/$3.json | sed -n '/^Exchange (CME)/,$p'; echo "rc=${PIPESTATUS[0]}"
done
echo "##### 4. 0X-B tests on the deployed code (offline)"
$UV run --frozen pytest -q -p no:cacheprovider apps/dicks_laboratory/tests/test_futures_contracts.py apps/dicks_laboratory/tests/test_roll_check_cli.py apps/dicks_laboratory/tests/test_preflight.py apps/dicks_laboratory/tests/test_production_unit_config.py apps/dicks_laboratory/tests/test_es_contract.py 2>&1 | tail -1
rm -rf "$W"; echo "##### done $(date -u +%FT%TZ); temp removed"
