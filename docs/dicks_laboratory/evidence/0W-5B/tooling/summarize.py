"""Summarize 0W-5B benchmark JSONs into markdown tables (evidence tooling)."""
import json, sys
from pathlib import Path

R = Path(sys.argv[1])
def load(name):
    p = R / f"{name}.json"
    return json.loads(p.read_text()) if p.exists() else None

print("| run | mode | journal | scale | IOPS | events | queue peak | % limit | max lag s | commit units/ev | all units/ev | ckpts | ckpt max s | WAL max MiB | diff | overload | exact |")
print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for name in sys.argv[2:]:
    d = load(name)
    if d is None:
        print(f"| {name} | (missing) |"); continue
    w = [p for p in d["phases"] if p["phase"] in ("paced", "burst")][0]
    print(f"| {name} | {d['mode']} | {d['policy']['journal_mode']} | {w.get('scale', 1)} | {w.get('emulated_iops') or '-'} | "
          f"{w['events']:,} | {w['queue_depth_max']:,} | {w['queue_limit_pct']} | {w['max_persist_lag_seconds']} | "
          f"{w['commit_azure_units_per_event']} | {w['all_azure_units_per_event']} | {w['checkpoint_count']} | "
          f"{w['checkpoint_seconds_max']} | {round(w['wal_bytes_max']/2**20,1)} | {w['accounting_difference']} | {w.get('overloaded', False)} | {d['accounting']['exact']} |")
