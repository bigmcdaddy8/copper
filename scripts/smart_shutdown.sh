#!/usr/bin/env bash
# smart_shutdown.sh — Deallocate the Azure VM only if no active SSH/VS Code sessions.
# Requires: System-assigned Managed Identity with Virtual Machine Contributor on 'dragon'.
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

RESOURCE_GROUP="rg-dev-environment"
VM_NAME="dragon"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
LOG_DIR="$REPO_ROOT/logs/K9"
source "$REPO_ROOT/scripts/lib/require_ct_time.sh"
LOG_FILE="$LOG_DIR/smart_shutdown_$(TZ=America/Chicago date +%F).log"
mkdir -p "$LOG_DIR"
exec >> "$LOG_FILE" 2>&1

if ! require_ct_time "10:15" "smart shutdown"; then
    exit 0
fi

TIMESTAMP="$(TZ=America/Chicago date '+%F %T %Z')"

# Count active pts sessions — covers both regular SSH and VS Code Remote SSH
ACTIVE=$(who | grep -c "pts/" || true)

if [ "$ACTIVE" -gt 0 ]; then
    echo "=== $TIMESTAMP smart_shutdown: SKIPPED — $ACTIVE active session(s) ==="
    who | grep "pts/" || true
    echo "VM will be deallocated by the 01:08 AM Auto-Shutdown failsafe."
    exit 0
fi

echo "=== $TIMESTAMP smart_shutdown: No active sessions. Deallocating '$VM_NAME'. ==="
az login --identity --output none
az vm deallocate \
    --resource-group "$RESOURCE_GROUP" \
    --name "$VM_NAME" \
    --no-wait \
    --output none
echo "Deallocation initiated."
