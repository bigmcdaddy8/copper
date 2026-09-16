#!/usr/bin/env bash
# Date-scoped launch-gate marker: write and check subcommands.
#
# 0W-4A stale-marker fix. Attempt 6's marker was a bare `touch` — safe for a
# ONE-DATE experiment (the marker never outlives the single boot it was
# created in), but not proven safe for a RECURRING production timer, where
# dragon stays up across the whole Sun-Thu week and /run is never cleared
# between trading dates. `dicks-lab-preflight-gate.service` already does
# `rm -f` before every run, so a stale marker cannot survive an actual
# preflight re-run in front of it — but that safety property lived only in
# ExecStartPre ordering, with no independent check at the point of use. This
# script makes the date explicit and machine-checkable: the marker's PAYLOAD
# is the trading date it authorizes, and `check` refuses anything that is
# not today, in America/Chicago, regardless of file mtime or ordering.
#
# Usage:
#   dicks_lab_gate_marker.sh write <marker-file>   # called from preflight-gate ExecStartPost
#   dicks_lab_gate_marker.sh check <marker-file>   # called from launch-gate ExecCondition
set -euo pipefail

cmd="${1:?usage: dicks_lab_gate_marker.sh write|check <marker-file>}"
marker="${2:?usage: dicks_lab_gate_marker.sh write|check <marker-file>}"
today="$(TZ=America/Chicago date +%Y-%m-%d)"

case "$cmd" in
  write)
    printf '%s\n' "$today" > "$marker"
    ;;
  check)
    [ -f "$marker" ] || exit 1
    marker_date="$(cat "$marker")"
    [ "$marker_date" = "$today" ]
    ;;
  *)
    echo "unknown subcommand: $cmd" >&2
    exit 2
    ;;
esac
