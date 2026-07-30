#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FAKE_BIN="$(mktemp -d)"
trap 'rm -rf "$FAKE_BIN"' EXIT

cat > "$FAKE_BIN/date" <<'EOF'
#!/usr/bin/env bash
if [[ "$*" == *"+%H:%M"* ]]; then
  printf '%s\n' "$FAKE_CT_TIME"
  exit 0
fi
printf '2026-07-30 09:45:00 CDT\n'
EOF
chmod +x "$FAKE_BIN/date"

export PATH="$FAKE_BIN:$PATH"
source "$REPO_ROOT/scripts/lib/require_ct_time.sh"

export FAKE_CT_TIME="09:45"
require_ct_time "09:45" "test job"

export FAKE_CT_TIME="10:45"
if require_ct_time "09:45" "test job"; then
  echo "Expected mismatched Central Time to skip." >&2
  exit 1
fi

if require_ct_time "9:45" "test job"; then
  echo "Expected malformed expected time to fail." >&2
  exit 1
fi

while IFS='|' read -r script expected_time; do
  if ! grep -Fq "require_ct_time \"$expected_time\"" "$REPO_ROOT/scripts/$script"; then
    echo "Missing $expected_time CT guard in $script." >&2
    exit 1
  fi
done <<'EOF'
compress_old_logs.sh|07:18
k9_daily_close_xsp.sh|07:15
k9_daily_entry_xsp.sh|09:00
k9_morning_check_xsp.sh|09:30
k9_tastytrade_diagnostic.sh|09:45
k9_weekly_flow_report_xsp.sh|07:00
smart_shutdown.sh|10:15
EOF

echo "require_ct_time tests passed"