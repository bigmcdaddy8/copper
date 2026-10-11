"""0AB-B real-data audit for one dataset (frozen DRYSDALE_V1; scratch harness; writes evidence).

Development / descriptive evidence only: nothing here may revise the frozen policy.
"""
import json, resource, statistics, sys, time as clock
from collections import Counter
from pathlib import Path
from dicks_laboratory import drysdale as dry
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.price_action import build_price_action_facts
from dicks_laboratory.replay import as_of_evidence
from dicks_laboratory.replay_player import CT, ReplaySession
from dicks_laboratory.tutor_ai import FakeTutorModel, answer_to_model_json, run_record, run_tutor
from dicks_laboratory.tutor_evidence import LessonStage, build_tutor_lesson, drysdale_lesson

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
case, db, prior, commit = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
log = open(out / f"{case}.log", "w")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def rss(): return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
def cur_rss():
    for line in open("/proc/self/status"):
        if line.startswith("VmRSS"): return int(line.split()[1]) / 1024
def ct(x): return "--" if x is None else x.astimezone(CT).strftime("%H:%M")
def r2(x): return "--" if x is None else f"{x:.2f}"

t0 = clock.monotonic()
session = ReplaySession.load(db, mss.AnalysisProvenance(commit, False), prior)
say(f"[{case}] frozen DRYSDALE_V1 at {commit}; prepare session: {clock.monotonic()-t0:.1f}s; rss {cur_rss():.0f} MB (peak {rss():.0f})")

# --- performance: cold vs cache hit vs resumed -------------------------------------------------------
def timed(f):
    t = clock.monotonic(); v = f(); return v, clock.monotonic() - t
snap16, ts = timed(lambda: session.snapshot("16:00"))
say(f"[{case}] snapshot 16:00: {ts:.1f}s")
ev, t_asof = timed(lambda: as_of_evidence(session.replay.current, snap16.cutoff).scoped)
say(f"[{case}] as-of tape 16:00 (recomputed, as every derived fact does): {t_asof:.1f}s, {len(ev):,} scoped trades")
r0 = cur_rss()
a_cold, t_cold = timed(lambda: dry.build_drysdale_analysis(session.replay.current, snap16, ev))
say(f"[{case}] COLD (no reuse) analysis 16:00 given the tape: {t_cold:.1f}s (pass + bars + candidates); "
    f"+tape {t_asof:.1f}s = {t_cold + t_asof:.1f}s; rss {cur_rss():.0f} MB (+{cur_rss()-r0:.0f})")
pa, t_pa = timed(lambda: build_price_action_facts(session.replay.current, snap16, ev))
say(f"[{case}] reference: 0AB-A PRICE_ACTION_FACTS_V1 16:00 given the tape: {t_pa:.1f}s")
atr_eq = a_cold.bars[-1].atr == pa.atr.value
del pa
j_cold = dry.canonical_analysis_json(a_cold)
again = dry.canonical_analysis_json(dry.build_drysdale_analysis(session.replay.current, snap16, ev))
say(f"[{case}] deterministic (cold twice): {j_cold == again}; {len(j_cold):,} bytes; sha {dry.drysdale_sha256(a_cold)[:16]}")
del ev, again
globex = next(v for v in snap16.vwap if v.anchor_kind.value == "SESSION_OPEN")
cash = next(v for v in snap16.vwap if v.anchor_kind.value == "US_CASH_OPEN")
b = a_cold.bands
say(f"[{case}] Globex VWAP {b.vwap:.4f} == snapshot SESSION_OPEN VWAP: {b.vwap == globex.study.vwap} (cash VWAP {cash.study.vwap:.4f}); "
    f"sigma {b.sigma:.4f}; value area {b.lower_1sd:.2f}-{b.upper_1sd:.2f}; outer {b.lower_2sd:.2f}-{b.upper_2sd:.2f}; "
    f"{b.maturity.value} [{a_cold.status}] {'; '.join(a_cold.reasons) or ''}")
say(f"[{case}] last bar ATR equals PRICE_ACTION_FACTS_V1 ATR_5M_V1: {atr_eq} ({a_cold.bars[-1].atr})")

# hourly progression with reuse (first-known timestamps)
times = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00", "02:00", "03:00", "04:00", "05:00",
         "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
first_seen, step_times, seen_states = {}, [], {}
for t in times:
    tt = clock.monotonic()
    a = dry.analyze(session, t)
    dt = clock.monotonic() - tt
    st = dict(session.drysdale_cache.stats)
    step_times.append((t, dt))
    n_c = sum(1 for c in a.candidates if c.state in (dry.CandidateState.CANDIDATE, dry.CandidateState.QUALITY_QUALIFIED))
    say(f"[{case}] {t} CT: analyze {dt:.1f}s (cache {st}); bars {len(a.bars)}; instances {len(a.candidates)}; "
        f"candidates {n_c}; state {a.state.value} [{a.status}]; rss {cur_rss():.0f} MB")
    for c in a.candidates:
        seen_states.setdefault(c.candidate_id, []).append((t, c.state.value))
        if c.state in (dry.CandidateState.CANDIDATE, dry.CandidateState.QUALITY_QUALIFIED) and c.candidate_id not in first_seen:
            first_seen[c.candidate_id] = t
final = a
j_res = dry.canonical_analysis_json(final)
say(f"[{case}] RESUMED analysis 16:00 identical to COLD: {j_res == j_cold}")
_, t_hit = timed(lambda: dry.analyze(session, "16:00"))
say(f"[{case}] cache HIT 16:00: {t_hit*1000:.2f} ms; cache stats {session.drysdale_cache.stats}")

# lessons on real data (deterministic reference answer through the AI pipeline; no network)
for t in ("10:00", "12:00"):
    tt = clock.monotonic()
    lesson = build_tutor_lesson(session, drysdale_lesson(session, t, question=0))
    tl = clock.monotonic() - tt
    tt = clock.monotonic()
    lesson2 = build_tutor_lesson(session, drysdale_lesson(session, t, question=2))
    tl2 = clock.monotonic() - tt
    res = run_tutor(lesson, LessonStage.QUESTION, FakeTutorModel([answer_to_model_json(lesson.answer_key.reference_answer, lesson)], "reference-answer"), allow_repair=False)
    rec = run_record(res)
    (out / f"{case}_lesson_{t.replace(':', '')}_run_record.json").write_text(mss._dumps(rec) + "\n")
    items = sum(len(e.items) for e in lesson.context.snapshots)
    say(f"[{case}] lesson {t}: build {tl:.1f}s, second question same time {tl2:.1f}s; {items} cited items; answer key "
        f"{lesson.answer_key.support.value}: {lesson.answer_key.summary}; reference answer via pipeline: {res.status.value} "
        f"({rec['system_prompt_version']}); warnings {[w.warning_id for w in lesson.context.quality_warnings]}")

# --- audit ------------------------------------------------------------------------------------------
(out / f"{case}_drysdale_1600.json").write_text(j_res + "\n")
for t in ("10:00", "12:00", "16:00"):
    (out / f"{case}_render_{t.replace(':', '')}.txt").write_text(dry.render_analysis(dry.analyze(session, t)))
C = final.candidates
say(f"[{case}] AUDIT (16:00, {len(final.bars)} complete Globex bars)")
fam = Counter((c.family.value, c.direction.value, c.state.value) for c in C)
for k in sorted(fam): say(f"    {k[0]:<30} {k[1]:<5} {k[2]:<18} {fam[k]}")
stages = Counter((c.family.value, c.stage.value) for c in C)
for k in sorted(stages): say(f"    stage {k[0]:<30} {k[1]:<26} {stages[k]}")
done = [c for c in C if c.state in (dry.CandidateState.CANDIDATE, dry.CandidateState.QUALITY_QUALIFIED)]
say(f"    candidates (all conditions satisfied): {len(done)}; QUALITY_QUALIFIED {sum(1 for c in done if c.state.value == 'QUALITY_QUALIFIED')}")
from datetime import time as _t
rth = [c for c in done if _t(8, 35) <= c.first_event_utc.astimezone(CT).time() <= _t(16, 0)]
say(f"    of which first event in 08:35-16:00 CT: {len(rth)}")
for c in done:
    fs = first_seen.get(c.candidate_id)
    hist = seen_states.get(c.candidate_id, [])
    flips = [s for s in hist if s[1] == 'DEVELOPING' and fs is not None and s[0] > fs]
    extra = ""
    if c.breakout:
        x = c.breakout
        extra = (f" | 2sd {x.reached_2sd} slope {x.vwap_slope.value if x.vwap_slope else '--'} in-dir {x.slope_in_breakout_direction} "
                 f"vol/mean {r2(x.volume.ratio_to_mean)} dist {r2(x.distance_beyond_sigma)}sd at {x.bar_end_ct}")
    say(f"    {c.candidate_id:<34} {c.state.value:<17} first {ct(c.first_event_utc)} completed {ct(c.completed_at_utc)} "
        f"first seen at hourly cutoff {fs or '--'}{' REVISED LATER' if flips else ''}{extra}")
# overlaps: candidates completing on the same bar, and intersecting [first, completed] intervals
by_bar = Counter(c.completed_at_utc for c in done)
same = {k: v for k, v in by_bar.items() if v > 1}
inter = sum(1 for i, x in enumerate(done) for y in done[i + 1:] if x.family is not y.family and
            x.first_event_utc <= y.completed_at_utc and y.first_event_utc <= x.completed_at_utc)
say(f"    overlaps: {len(same)} bars complete >1 candidate {[(ct(k), v) for k, v in same.items()]}; "
    f"{inter} cross-family candidate pairs with intersecting first-to-completion intervals")
pdc = [c for c in C if c.family is dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION]
if pdc:
    reach = sum(1 for c in pdc if c.breakout.reached_2sd)
    reach_c = sum(1 for c in pdc if c.breakout.reached_2sd and c in done)
    pdc_done = [c for c in pdc if c in done]
    say(f"    PDC instances {len(pdc)}: +/-2 sigma reached in {reach} ({reach / len(pdc):.2%}); among PDC candidates "
        f"{reach_c}/{len(pdc_done)}")
    ratios = sorted(c.breakout.volume.ratio_to_mean for c in pdc if c.breakout.volume.ratio_to_mean is not None)
    if ratios:
        say(f"    trigger-bar volume / mean of preceding bars: min {r2(ratios[0])} median {r2(statistics.median(ratios))} "
            f"max {r2(ratios[-1])} (n {len(ratios)}); >1: {sum(1 for x in ratios if x > 1)}")
    ind = Counter(str(c.breakout.slope_in_breakout_direction) for c in pdc)
    say(f"    VWAP slope in the trigger direction at the trigger: {dict(ind)}")
    acc = Counter(c.conditions[1].status.value for c in pdc)
    ret = Counter(c.conditions[2].status.value for c in pdc)
    say(f"    PDC acceptance {dict(acc)}; retest {dict(ret)}")
    early = sum(1 for c in pdc if c.first_event_utc.astimezone(CT).hour in (17, 18))
    say(f"    PDC triggers in the first two Globex hours (17:00-19:00 CT): {early}")
x = final.context
say(f"    context 16:00: {x.value_position.value}, slope {x.vwap_slope.value if x.vwap_slope else '--'}, trend {x.trend_context.value if x.trend_context else 'neither'}, "
    f"time above +1sd {int(x.session_seconds_above_1sd.total_seconds())}s below -1sd {int(x.session_seconds_below_1sd.total_seconds())}s, "
    f"bars reaching 2sd {x.session_bars_reaching_2sd}, ATR {r2(x.atr)} (12 bars earlier {r2(x.atr_12_bars_earlier)})")
say(f"[{case}] step times: " + ", ".join(f"{t} {d:.1f}s" for t, d in step_times))
say(f"[{case}] peak rss {rss():.0f} MB")
