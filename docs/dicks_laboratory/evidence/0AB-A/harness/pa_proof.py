"""0AB-A real-data study for one dataset (scratch harness; outputs evidence)."""
import json, resource, sys, time as clock
from pathlib import Path
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.price_action import build_price_action_facts, canonical_facts_json, price_action_sha256
from dicks_laboratory.replay import as_of_evidence, snapshot_sha256
from dicks_laboratory.replay_player import CT, ReplaySession

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
case, db, prior, commit = sys.argv[2], Path(sys.argv[3]), (Path(sys.argv[4]) if sys.argv[4] != "-" else None), sys.argv[5]
times = sys.argv[6].split(",")
log = open(out / f"{case}.log", "w")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
def ct(x): return "--" if x is None else x.astimezone(CT).strftime("%H:%M:%S")
t0 = clock.monotonic()
session = ReplaySession.load(db, mss.AnalysisProvenance(commit, False), prior)
say(f"[{case}] prepare session (replay layer): {clock.monotonic()-t0:.1f}s rss {rss():.0f} MB")
saved = {}
for t in times:
    t1 = clock.monotonic(); snap = session.snapshot(t); ts = clock.monotonic() - t1
    timings = {}
    f = build_price_action_facts(session.replay.current, snap, timings=timings)
    j = canonical_facts_json(f)
    again = canonical_facts_json(build_price_action_facts(session.replay.current, snap))
    saved[t] = f
    (out / f"{case}_facts_{t.replace(':', '')}.json").write_text(j + "\n")
    b = f.bands
    say(f"[{case}] {t} CT: snapshot {ts:.1f}s; facts {sum(timings.values()):.2f}s "
        + " ".join(f"{k}={v:.2f}s" for k, v in timings.items())
        + f"; {len(j):,} bytes; deterministic {j == again}; sha {price_action_sha256(f)[:16]}; snapshot {snapshot_sha256(snap)[:16]}")
    if b.vwap is None:
        say(f"    bands {b.maturity.value}")
    else:
        cash = next(v.study.vwap for v in snap.vwap if v.anchor_kind.value == "US_CASH_OPEN")
        say(f"    bands {b.maturity.value} [{f.status}]: VWAP {b.vwap:.4f} (== snapshot cash VWAP: {b.vwap == cash}) sigma {b.sigma:.4f} "
            + " ".join(f"+/-{x.multiplier}sd {x.lower:.2f}/{x.upper:.2f}" for x in b.bands)
            + f"; last {b.last_price} at {ct(b.last_price_utc)} zones {[(k, z.value) for k, z in b.last_price_zones]}")
        for o in f.occupancy:
            say(f"    time vs {o.multiplier}sd bands: observed {o.observed.total_seconds():.0f}s; above {o.outside_above.total_seconds():.0f}s "
                f"below {o.outside_below.total_seconds():.0f}s outside {o.outside_total.total_seconds():.0f}s "
                f"({o.fraction_outside_total:.4f} of observed)")
    for r in f.references:
        if r.reference in ("CASH_VWAP", "VWAP_UPPER_1SD", "VWAP_LOWER_1SD", "VWAP_UPPER_2SD", "VWAP_LOWER_2SD",
                           "IB_HIGH", "IB_LOW", "PRIOR_VALUE_AREA_HIGH", "PRIOR_VALUE_AREA_LOW"):
            e = r.latest_episode
            say(f"    {r.reference:<22} {r.maturity.value:<17} level {r.level_at_clock if r.level_at_clock is not None else '(moving)'}"
                f" side {r.side_at_clock.value if r.side_at_clock else '--'} crosses {r.cross_count}"
                f" first {ct(r.first_cross.utc) if r.first_cross else '--'} {r.first_cross.direction.value if r.first_cross else ''}"
                f" last {ct(r.last_cross.utc) if r.last_cross else '--'}"
                + (f" | latest {e.direction.value} from {ct(e.start_utc)}: max {e.max_excursion_points} pts, beyond "
                   f"{e.seconds_beyond.total_seconds():.0f}s, closes beyond {e.bars_closing_beyond} (max consec "
                   f"{e.max_consecutive_closes_beyond}), touched again {ct(e.touched_again_utc)}, returned {ct(e.returned_utc)}"
                   if e else ""))
    a = f.atr
    say(f"    ATR_5M_V1 {a.maturity.value}: {a.value if a.value is None else f'{a.value:.4f}'} through {ct(a.through_bar_end_utc)} "
        f"({a.completed_bars_used} bars, {a.empty_bars_skipped} empty skipped)")
    for bar in f.rth_bars[-3:]:
        say(f"    bar {ct(bar.start_utc)} {bar.maturity.value}: O {bar.open} H {bar.high} L {bar.low} C {bar.close} "
            f"{bar.direction.value} n {bar.trade_count} inside {bar.inside_bar} outside {bar.outside_bar} HH {bar.higher_high} "
            f"LL {bar.lower_low} close vs VWAP {bar.close_vs_vwap.value if bar.close_vs_vwap else '--'} "
            f"{[(k, z.value) for k, z in bar.close_zones]} ATR {bar.atr_after if bar.atr_after is None else f'{bar.atr_after:.4f}'}")
say(f"[{case}] peak rss {rss():.0f} MB")
