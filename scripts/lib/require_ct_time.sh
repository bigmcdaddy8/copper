#!/usr/bin/env bash
# Require an exact America/Chicago wall-clock minute before running a scheduled job.

require_ct_time() {
  local expected_time="$1"
  local job_name="$2"
  local actual_time

  if [[ ! "$expected_time" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]]; then
    printf 'Invalid expected Central Time %q for %s.\n' "$expected_time" "$job_name" >&2
    return 2
  fi

  actual_time="$(TZ=America/Chicago date +%H:%M)"
  if [[ "$actual_time" != "$expected_time" ]]; then
    printf '%s [SCHEDULE GUARD] Skipping %s: expected %s CT, got %s CT.\n' \
      "$(TZ=America/Chicago date '+%F %T %Z')" "$job_name" "$expected_time" "$actual_time"
    return 1
  fi

  printf '%s [SCHEDULE GUARD] Running %s at %s CT.\n' \
    "$(TZ=America/Chicago date '+%F %T %Z')" "$job_name" "$actual_time"
}