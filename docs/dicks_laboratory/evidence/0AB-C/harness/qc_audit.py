"""0AB-C quality-propagation audit for one development-corpus date (frozen DRYSDALE_V1; read-only; scratch).

dq_pinned.py was a byte copy of drysdale_quality.py (sha256 1d54d63e..., the committed module), pinned so
that later edits could not reach a running date. To rerun: import dicks_laboratory.drysdale_quality as dq.

Development / descriptive evidence only. The sensitivity section prepends HYPOTHETICAL trades to an in-memory
copy of the as-of tape (SENSITIVITY ANALYSIS, never source truth); nothing is written to any dataset.
"""
import dataclasses, json, sys, time as clock, uuid
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from dicks_laboratory import drysdale as dry
sys.path.insert(0, str(Path(__file__).parent)); import dq_pinned as dq  # pinned copy of drysdale_quality.py
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.replay import ReplayCutoff, as_of_evidence
from dicks_laboratory.replay_player import CT, ReplaySession

out = Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
case, db, prior, commit = sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
log = open(out / f"{case}_quality.log", "w")
def say(*a):
    print(*a, file=log, flush=True); print(*a, flush=True)
def ct(x): return "--" if x is None else x.astimezone(CT).strftime("%H:%M")
QUAL = (dry.CandidateState.CANDIDATE, dry.CandidateState.QUALITY_QUALIFIED)

t0 = clock.monotonic()
session = ReplaySession.load(db, mss.AnalysisProvenance(commit, False), prior)
say(f"[{case}] DRYSDALE_V1 frozen code at {commit}; prepare {clock.monotonic()-t0:.0f}s")

def row(c: dq.CandidateQuality, cutoff_label):
    return {"cutoff": cutoff_label, "candidate_id": c.candidate_id, "family": c.family.value,
            "direction": mss.encode(c.direction), "state": c.state.value, "candidate_quality": c.candidate_quality,
            "first_event_ct": ct(c.first_event_utc), "completed_ct": ct(c.completed_at_utc),
            "evidence_window_ct": [ct(c.evidence_window_start_utc), ct(c.evidence_window_end_utc)],
            "boundary_status": c.boundary_status.value,
            "reasons": [[r.code.value, r.scope.value, r.materiality.value, r.detail] for r in c.reasons],
            "gaps_overlapping_window": c.gaps_overlapping_window, "gaps_upstream": c.gaps_upstream,
            "gaps_after_candidate": c.gaps_after_candidate, "local_evidence_complete": c.local_evidence_complete,
            "eligibility": c.eligibility.value, "eligibility_basis": list(c.eligibility_basis)}

times = ["18:00", "19:00", "20:00", "21:00", "22:00", "23:00", "00:00", "01:00", "02:00", "03:00", "04:00", "05:00",
         "06:00", "07:00", "08:00", "09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
first_known, status_by_cutoff, proof_fail = {}, [], []
for t in times:
    a = dry.analyze(session, t)
    snap = session.snapshot(t)
    x = dq.audit(a, snap)
    vw = next(v for v in snap.vwap if v.anchor_kind.value == "SESSION_OPEN")
    # dependency proof: the frozen propagation, exactly
    if not (a.status == vw.status.value and a.reasons[:len(vw.reasons)] == vw.reasons
            and all(c.quality == a.status for c in a.candidates)):
        proof_fail.append(t)
    status_by_cutoff.append({"cutoff": t, "globex_vwap_status": vw.status.value, "globex_vwap_maturity":
                             vw.maturity.value, "status_driving_reasons": list(vw.reasons),
                             "codes": [dq.classify_reason(r).value for r in vw.reasons],
                             "context_reasons": list(a.reasons[len(vw.reasons):]),
                             "context_codes": [dq.classify_reason(r).value for r in a.reasons[len(vw.reasons):]]})
    for c in x.candidates:
        if c.state in QUAL and c.candidate_id not in first_known:
            first_known[c.candidate_id] = row(c, t)
    last_a, last_snap, last_x = a, snap, x
say(f"[{case}] hourly cutoffs analysed; dependency proof failures: {proof_fail or 'none'}")
for s in status_by_cutoff:
    say(f"[{case}]   {s['cutoff']} Globex VWAP {s['globex_vwap_status']} ({s['globex_vwap_maturity']}): "
        f"{s['codes']} | context {s['context_codes']}")

at16 = {c.candidate_id: row(c, "16:00 as-of") for c in last_x.candidates if c.state in QUAL}
# final knowledge: market cutoff 16:00 CT, knowledge cutoff 16:30 CT (the capture stop and FINALIZED are known)
m16 = last_a.cutoff.market_time_cutoff_utc
fk = ReplayCutoff(m16, m16 + timedelta(minutes=30))
a_fk = dry.analyze(session, cutoff=fk)
s_fk = session.snapshot(cutoff=fk)
x_fk = dq.audit(a_fk, s_fk)
final = {c.candidate_id: row(c, "16:00 market / 16:30 knowledge") for c in x_fk.candidates if c.state in QUAL}
say(f"[{case}] final-knowledge cutoff: status {a_fk.status} reasons {list(a_fk.reasons)}; lifecycle "
    f"{s_fk.current_dataset.lifecycle_as_of}; candidates {len(final)} (16:00 as-of {len(at16)})")
say(f"[{case}] final-knowledge candidate set == 16:00 as-of set: {set(final) == set(at16)}")

prop = mss.encode(dq.propagation(last_a, last_snap))
counts = {"first_known": Counter(r["eligibility"] for r in first_known.values()),
          "16:00_as_of": Counter(r["eligibility"] for r in at16.values()),
          "final_knowledge": Counter(r["eligibility"] for r in final.values())}
say(f"[{case}] eligibility counts {json.dumps(counts)}")
for cid, r in first_known.items():
    say(f"    {cid:34s} first-known {r['cutoff']} {r['state']:17s} window {r['evidence_window_ct'][0]}-"
        f"{r['evidence_window_ct'][1]} -> {r['eligibility']} | " + "; ".join(
            f"{x[0]}/{x[1]}/{x[2]}" for x in r["reasons"]))

# --- SENSITIVITY ANALYSIS (illustrative; hypothetical trades in [anchor, capture start); never source truth) -----
snap16 = session.snapshot("16:00")
tape = as_of_evidence(session.replay.current, snap16.cutoff).scoped
anchor = last_a.bands.anchor_utc
first = min((t for t in tape if t.event_timestamp >= anchor), key=lambda t: t.event_timestamp)
tick = Decimal("0.25")
base = dry.build_drysdale_analysis(session.replay.current, snap16, tape)
def key(a): return sorted((c.candidate_id, c.state.value, mss.encode(c.completed_at_utc)) for c in a.candidates
                          if c.state in QUAL)
def bar_at(a, hhmm):
    return next((b for b in a.bars if ct(b.end_utc) == hhmm), None)
first_bar_volume = base.bars[0].volume
sens = {"first_observed_trade_utc": mss.encode(first.event_timestamp), "first_observed_price": str(first.price),
        "capture_started_after_anchor_s": str((session.replay.current.dataset.capture_started_at - anchor)
                                              .total_seconds()),
        "first_5m_bar_volume": str(first_bar_volume), "runs": []}
for vol in (1, 10, 100, 1000):
    for k in (-20, 0, 20):
        hyp = dataclasses.replace(first, effective_trade_id=uuid.uuid4(), original_observation_id=uuid.uuid4(),
                                  event_timestamp=anchor, price=first.price + k * tick, size=Decimal(vol))
        a = dry.build_drysdale_analysis(session.replay.current, snap16, (hyp,) + tuple(tape))
        run = {"volume": vol, "price_offset_ticks": k}
        for label in ("18:00", "09:30", "16:00"):
            b0, b1 = bar_at(base, label), bar_at(a, label)
            if b0 is None or b1 is None:
                continue
            run[label] = {"vwap_shift_ticks": str(((b1.vwap - b0.vwap) / tick).quantize(Decimal("0.0001"))),
                          "sigma_shift_ticks": str(((b1.sigma - b0.sigma) / tick).quantize(Decimal("0.0001")))}
        changed = sorted(set(map(tuple, key(a))) ^ set(map(tuple, key(base))))
        run["candidates_changed"] = len(changed)
        run["changed"] = [list(c) for c in changed]
        sens["runs"].append(run)
        say(f"[{case}] SENSITIVITY vol {vol:5d} offset {k:+3d} ticks: " + " ".join(
            f"{lbl} dVWAP {run[lbl]['vwap_shift_ticks']}t dSigma {run[lbl]['sigma_shift_ticks']}t"
            for lbl in ("18:00", "09:30", "16:00") if lbl in run) + f"; candidates changed {len(changed)}")

json.dump({"case": case, "frozen_commit": commit, "propagation_16_00": prop, "proof_failures": proof_fail,
           "status_by_cutoff": status_by_cutoff, "first_known": first_known, "at_16_00_as_of": at16,
           "final_knowledge": final, "counts": counts, "sensitivity": sens},
          open(out / f"{case}_quality.json", "w"), indent=1, sort_keys=True, default=str)
say(f"[{case}] done in {clock.monotonic()-t0:.0f}s")
