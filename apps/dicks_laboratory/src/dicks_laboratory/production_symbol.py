"""Single source of truth for the currently pinned production ES contract.

0W-4B: the pre-0W-4B collector and preflight scripts each hard-coded their own
copy of `/ESU6` (the September 2026 lead contract), which is unsafe once that
contract rolls off lead status -- two independently edited literals can drift.
Both scripts now import `PINNED_ES_SYMBOL` from here, so changing the pinned
contract for a new soak/production epoch means changing this one constant.

This is an explicit, Human/PO-reviewed pin, not an auto-roll mechanism: the
collector and preflight still independently verify this symbol against live
Tastytrade futures metadata (see `es_contract.resolve_es_contract`) every time
they run, so a stale or delisted pin fails safely rather than silently.
"""
from __future__ import annotations

# 0W-4B: pinned for the 2026-09-21..25 soak week. Historical September 2026
# datasets (`/ESU6`, `/ESU26:XCME`) are unaffected -- they remain valid on
# their own recorded instrument identity regardless of this constant.
PINNED_ES_SYMBOL = "/ESZ6"
