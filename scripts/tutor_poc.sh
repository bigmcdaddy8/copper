#!/usr/bin/env bash
# Tutor POC (0AC-A1/A2): build the browser app if needed, prepare the approved session if needed, serve.
#   scripts/tutor_poc.sh            -> http://localhost:8765
#   scripts/tutor_poc.sh --port 9000
set -euo pipefail
cd "$(dirname "$0")/.."
WEB=apps/tutor_poc/web
if [ ! -d "$WEB/node_modules" ]; then
  (cd "$WEB" && npm ci --no-audit --no-fund)
fi
if [ ! -f "$WEB/dist/index.html" ] || [ -n "$(find "$WEB/src" "$WEB/index.html" -newer "$WEB/dist/index.html" -print -quit)" ]; then
  (cd "$WEB" && npm run build)
fi
exec uv run tutor_poc serve "$@"
