"""Authentic 10-02 CANCEL (market 07:00 CT? received later): visibility before / after its receipt."""
import sys, time, resource
from datetime import timedelta
from pathlib import Path
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.replay import *
db = Path(sys.argv[1]); out = Path(sys.argv[2])
before = mss.file_sha256(db)
t0 = time.monotonic(); prep = prepare_replay(db); prep_s = time.monotonic() - t0
d = prep.deferred[0]
recv = d.source_record.received_at
lines = [f"prepare_replay {prep_s:.1f}s rss {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB",
         f"deferred records: {len(prep.deferred)}; first: {d.source_record.event_classification} source_order {d.source_order} "
         f"index {d.source_record.source_index} event_time {d.source_record.event_time} received {mss.encode(recv)}"]
for k in (recv - timedelta(seconds=1), recv + timedelta(seconds=1)):
    c = ReplayCutoff.at(k)
    for v in record_visibility(prep, c, late_print_limit=0):
        lines.append(f"cutoff {mss.encode(k)}: {v.record} order {v.source_order} market {mss.encode(v.market_timestamp_utc)} "
                     f"received {mss.encode(v.received_at_utc)} -> {v.visibility.value}: {v.reason}")
    ev = as_of_evidence(prep, c)
    snap = build_snapshot(prep, None, c, mss.AnalysisProvenance(sys.argv[3], False))
    vol = sum(t.size for t in ev.scoped)
    lines.append(f"cutoff {mss.encode(k)}: snapshot sha {snapshot_sha256(snap)}; deferred known "
                 f"{snap.current_dataset.counts.deferred_known}; cancels known {snap.current_dataset.counts.cancels_known}; "
                 f"cancels applied {snap.current_dataset.counts.cancels_applied}; anomalies "
                 f"{snap.current_dataset.counts.reconstruction_anomalies}; effective trades {len(ev.scoped)}; volume {vol}")
    lines.append(f"cutoff {mss.encode(k)}: cancels known {sum(1 for x in ev.known_deferred if x.source_record.event_classification == 'CANCEL')}, "
                 f"applied {ev.tape.applied_cancel_count}, anomalies {[a.reason for a in ev.tape.anomalies]}")
lines.append(f"database sha256 unchanged: {mss.file_sha256(db) == before} {before}")
out.write_text("\n".join(lines) + "\n"); print("\n".join(lines))
