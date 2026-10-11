"""Anti-lookahead proof on a copy: change trades in [11:00, 11:05) CT; facts at 11:00 must not change."""
import shutil, sqlite3, sys
from pathlib import Path
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.price_action import build_price_action_facts, canonical_facts_json
from dicks_laboratory.replay_player import ReplaySession
out, db, prior, commit, work = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], Path(sys.argv[5])
log = open(out / "anti_lookahead.log", "w")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def facts(path, t):
    s = ReplaySession.load(path, mss.AnalysisProvenance(commit, False), prior)
    return {x: build_price_action_facts(s.replay.current, s.snapshot(x)) for x in t}
T = ("11:00", "11:10")
base = facts(db, T)
work.mkdir(parents=True, exist_ok=True)
copy = work / "mutated.sqlite3"
shutil.copyfile(db, copy)
con = sqlite3.connect(copy)
n = con.execute("UPDATE trade_observations SET price = '7800' WHERE event_timestamp >= "
                "'2026-09-29T16:00:00' AND event_timestamp < '2026-09-29T16:05:00'").rowcount
con.commit(); con.close()
say(f"mutated copy: {n} trades in [11:00, 11:05) CT set to 7800 (above the +2 sigma band) (received at/after 11:00)")
mut = facts(copy, T)
for t in T:
    a, b = canonical_facts_json(base[t]), canonical_facts_json(mut[t])
    say(f"{t} CT facts identical: {a == b}")
bar = lambda f: next(x for x in f.rth_bars if x.start_utc.isoformat().startswith("2026-09-29T16:00"))
say(f"bar 11:00 at 11:10 original H {bar(base['11:10']).high} mutated H {bar(mut['11:10']).high}")
for name in ("CASH_VWAP", "VWAP_UPPER_1SD", "VWAP_UPPER_2SD"):
    r0 = next(r for r in base["11:10"].references if r.reference == name)
    r1 = next(r for r in mut["11:10"].references if r.reference == name)
    r00 = next(r for r in base["11:00"].references if r.reference == name)
    r10 = next(r for r in mut["11:00"].references if r.reference == name)
    say(f"{name}: crosses at 11:00 {r00.cross_count}/{r10.cross_count}; at 11:10 original {r0.cross_count} mutated {r1.cross_count}; "
        f"last cross original {r0.last_cross.utc if r0.last_cross else None} mutated {r1.last_cross.utc if r1.last_cross else None}")
copy.unlink()
say("mutated copy deleted")
