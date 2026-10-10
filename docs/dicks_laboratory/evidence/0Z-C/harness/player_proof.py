"""0Z-C real-data proof for one dataset (scratch harness; outputs evidence)."""
import json, resource, sys, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.replay import ReplayCutoff, canonical_snapshot_json, snapshot_sha256
from dicks_laboratory.replay_player import *
import time as clock

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
case, db, prior = sys.argv[2], Path(sys.argv[3]), (Path(sys.argv[4]) if sys.argv[4] != "-" else None)
commit = sys.argv[5]
log = open(out / f"{case}.log", "w")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
t0 = clock.monotonic()
session = ReplaySession.load(db, mss.AnalysisProvenance(commit, False), prior)
say(f"[{case}] prepare session: {clock.monotonic()-t0:.1f}s rss {rss():.0f} MB")
views = [v for v in sys.argv[6].split(",") if v]
deltas = [tuple(x.split("~")) for x in sys.argv[7].split(",") if x]
first = True
for v in views:
    t1 = clock.monotonic(); s = session.snapshot(v); dt = clock.monotonic() - t1
    say(f"[{case}] {'first' if first else 'subsequent'} snapshot {v}: {dt:.1f}s  sha {snapshot_sha256(s)}")
    first = False
    (out / f"{case}_view_{v.replace(':', '')}.txt").write_text(render_player_view(s))
for a, b in deltas:
    t1 = clock.monotonic(); d = session.compare(a, b); dt = clock.monotonic() - t1
    j = canonical_delta_json(d)
    # determinism: rebuild both snapshots uncached and compare again
    c1 = session.snapshot(a).cutoff; c2 = session.snapshot(b).cutoff
    d2 = compare_snapshot_states(session.replay.snapshot(cutoff=c1), session.replay.snapshot(cutoff=c2),
                                 session.newly_known(c1, c2))
    same = canonical_delta_json(d2) == j
    tag = f"{a.replace(':', '').replace('.', '')}_{b.replace(':', '').replace('.', '')}"
    (out / f"{case}_delta_{tag}.json").write_text(j)
    (out / f"{case}_delta_{tag}.txt").write_text(render_delta(d))
    say(f"[{case}] delta {a} -> {b}: {len(d.changes)} changes, compare {dt:.1f}s, deterministic {same}, "
        f"delta sha {delta_sha256(d)}; newly known {d.newly_known}")
say(f"[{case}] peak rss {rss():.0f} MB")
