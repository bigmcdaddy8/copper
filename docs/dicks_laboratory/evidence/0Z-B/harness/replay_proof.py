"""0Z-B real-data replay proof (scratch harness; outputs evidence)."""
import json, resource, sys, time, dataclasses
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.replay import *

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
cur_db, prior_db, commit = Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4]
dirty = sys.argv[5] == "dirty"
CT = ZoneInfo("America/Chicago")
log = open(out / "proof.log", "w")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
sha_before = {p.name: mss.file_sha256(p) for p in (cur_db, prior_db)}
prov = mss.AnalysisProvenance(commit, dirty)
t0 = time.monotonic()
prep = prepare_replay(cur_db)
say(f"prepare_replay (current, once): {time.monotonic()-t0:.1f}s  rss {rss():.0f} MB")
t0 = time.monotonic()
prior_inputs = mss.load_study_inputs(prior_db)
say(f"prior study inputs (final prior day): {time.monotonic()-t0:.1f}s  rss {rss():.0f} MB")
rp = MarketReplay(prep, prior_inputs, prov)
td = rp.current.trading_date
times = [(7,0),(8,29),(8,31),(8,35),(9,0),(9,30),(10,0),(12,0),(14,59),(15,0),(16,0)]
rows = []
(out/"snapshots").mkdir(exist_ok=True); (out/"summaries").mkdir(exist_ok=True)
snaps = {}
for hh, mm in times:
    T = datetime(td.year, td.month, td.day, hh, mm, tzinfo=CT)
    t1 = time.monotonic(); a = rp.snapshot(at=T); ja = canonical_snapshot_json(a); dt_a = time.monotonic()-t1
    t1 = time.monotonic(); b = rp.snapshot(at=T); jb = canonical_snapshot_json(b); dt_b = time.monotonic()-t1
    h = json.loads(ja)[SNAPSHOT_HASH_FIELD]
    name = f"{hh:02d}{mm:02d}"
    (out/"snapshots"/f"{td}_{name}.json").write_text(ja)
    (out/"summaries"/f"{td}_{name}.txt").write_text(render_snapshot_summary(a, h))
    snaps[name] = a
    m = {e.component: e.maturity.value for e in a.maturity}
    rows.append((name, f"{dt_a:.1f}", f"{dt_b:.1f}", len(ja), ja == jb, h, a.tpo.periods_reached or "-",
                 m["initial_balance"], m["opening_type"], m["day_type"], a.current_dataset.lifecycle_as_of,
                 a.dataset_quality.known_gap_count, a.prices.study_window_terminal_price,
                 a.current_dataset.counts.known_records_with_market_time_at_or_after_cutoff))
    say(*rows[-1], f"rss {rss():.0f} MB")
with open(out/"snapshots.tsv", "w") as f:
    f.write("cutoff_ct\tbuild1_s\tbuild2_s\tbytes\tbyte_identical\tsnapshot_sha256\tperiods\tIB\topening_type\tday_type\tlifecycle\tknown_gaps\tterminal\tknown_future_market\n")
    for r in rows: f.write("\t".join(map(str, r)) + "\n")
say(f"replay-only peak rss after {len(rows)*2} snapshots: {rss():.0f} MB")
# authentic late prints: 12:14:00 CT, where trades from 12:13:40 arrived 20 s late
for (hh, mm, ss) in ((12, 14, 0), (12, 14, 1)):
    T = datetime(td.year, td.month, td.day, hh, mm, ss, tzinfo=CT)
    by = {t.observation_id: t for t in rp.current.canonical_trades}
    straddle = [p for p in rp.current.provenance if by[p.observation_id].event_timestamp < T <= p.received_at]
    s_late = rp.snapshot(at=T)
    (out/"snapshots"/f"{td}_{hh:02d}{mm:02d}{ss:02d}.json").write_text(canonical_snapshot_json(s_late))
    say(f"{hh:02d}:{mm:02d}:{ss:02d} CT: market-before-cutoff but not yet received: {len(straddle)}; "
        f"max lag {max(((p.received_at - by[p.observation_id].event_timestamp).total_seconds() for p in straddle), default=0):.3f}s; "
        f"snapshot sha {snapshot_sha256(s_late)}; volume {s_late.volume_profile.total_volume}")
# visibility diagnostics
for (hh, mm, ss) in ((10, 0, 0), (12, 14, 0), (16, 0, 0)):
    T = datetime(td.year, td.month, td.day, hh, mm, ss, tzinfo=CT)
    vis = rp.visibility(ReplayCutoff.at(T), late_print_limit=15)
    with open(out/f"visibility_{hh:02d}{mm:02d}{ss:02d}.tsv", "w") as f:
        f.write("record\tsource_order\tsource_index\tmarket_utc\treceived_utc\tlag_s\tvisibility\treason\n")
        for v in vis:
            f.write(f"{v.record}\t{v.source_order}\t{v.source_index}\t{mss.encode(v.market_timestamp_utc)}\t{mss.encode(v.received_at_utc)}\t{mss.encode(v.receipt_lag)}\t{v.visibility.value}\t{v.reason}\n")
# late-print knowledge proof at 10:00: trades with market < 10:00 received >= 10:00
T10 = datetime(td.year, td.month, td.day, 10, 0, tzinfo=CT)
by = {t.observation_id: t for t in rp.current.canonical_trades}
late = [p for p in rp.current.provenance if by[p.observation_id].event_timestamp < T10 <= p.received_at]
say(f"late prints at 10:00 (market < 10:00, received >= 10:00): {len(late)}; max lag "
    f"{max((p.received_at - by[p.observation_id].event_timestamp).total_seconds() for p in late) if late else 0:.3f}s")
# terminal snapshot for the separate-process convergence comparison (after capture stop 16:00:00.19 CT)
T = datetime(td.year, td.month, td.day, 17, 0, tzinfo=CT)
term = rp.snapshot(at=T)
(out/"terminal_snapshot_1700.json").write_text(canonical_snapshot_json(term))
say(f"terminal snapshot 17:00 CT sha {snapshot_sha256(term)}")
say(f"peak rss {rss():.0f} MB")

