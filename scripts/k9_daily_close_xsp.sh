#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

REPO_ROOT="/home/temckee8/Documents/REPOs/copper"
cd "$REPO_ROOT"

uv run K9 close --account TRDS --spec-name xsp_pcs_0dte_w2_none_0900_trds
