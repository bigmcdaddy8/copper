#!/usr/bin/env bash
# Read-only 0W-5C downstream smoke against the finalized 2026-10-06 artifact.
set -u
cd ~/Documents/REPOs/copper
F=/srv/dicks_laboratory/data/sessions/es_20261006_2b6cc528.sqlite3
UV=$HOME/.local/bin/uv
side(){ echo "sidecars($1): $(ls ${F}-wal ${F}-shm ${F}-journal 2>/dev/null | wc -l)"; }
echo "######## $(date -u +%FT%TZ) pre"; side pre; sha256sum $F
echo "######## DatasetAudit (LaboratoryStore read_only=True)"
$UV run --frozen python - "$F" <<'PY'
import sys
from pathlib import Path
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.audit import audit_dataset
p = Path(sys.argv[1])
s = LaboratoryStore(p, read_only=True)
ds = s.list_datasets() if hasattr(s, "list_datasets") else None
import sqlite3
did = sqlite3.connect(f"file:{p}?mode=ro", uri=True).execute("SELECT dataset_id FROM datasets").fetchone()[0]
from uuid import UUID
a = audit_dataset(s, UUID(did))
print("dataset", a.dataset.dataset_id, a.dataset.label)
print("accepted_trade_count", a.accepted_trade_count)
print("first/last dataset_sequence", a.first_dataset_sequence, a.last_dataset_sequence)
print("first/last trade", a.first_trade_event_timestamp, a.last_trade_event_timestamp)
print("instrument_ids", a.instrument_ids)
print("rejected", a.rejected_record_count, a.rejection_counts_by_reason, a.rejection_counts_by_source_kind)
print("lifecycle_counts", [(t.value, n) for t, n in a.lifecycle_counts])
print("known_gap_count", a.known_gap_count, "suspected", a.suspected_gap_count, "known_gap_duration", a.known_gap_duration)
print("deferred", a.deferred_timesale_count, a.deferred_timesale_counts_by_classification)
print("DATASET_AUDIT=PASS")
PY
echo "rc=$?"
echo "######## VWAP"; $UV run --frozen python scripts/dicks_lab_analyze_vwap.py $F --anchor session-open 2>&1; echo "rc=$?"
echo "######## VOLUME PROFILE"; $UV run --frozen python scripts/dicks_lab_analyze_volume_profile.py $F --anchor session-open 2>&1; echo "rc=$?"
echo "######## DEVELOPING PROFILE (15m, tail 40)"; $UV run --frozen python scripts/dicks_lab_analyze_developing_profile.py $F --anchor session-open --interval 15m > /tmp/0w5c_dev.txt 2>&1; echo "rc=$?"; tail -40 /tmp/0w5c_dev.txt; rm -f /tmp/0w5c_dev.txt
echo "######## $(date -u +%FT%TZ) post"; side post; sha256sum $F
