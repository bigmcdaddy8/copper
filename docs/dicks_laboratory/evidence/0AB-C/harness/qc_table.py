"""0AB-C: aggregate the per-date quality JSON into the propagation table and summary statistics (development only)."""
import json, sys
from collections import Counter
from pathlib import Path

src = Path(sys.argv[1])
dates = ["2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02"]
rows, stats = [], Counter()
cause = Counter()
md = ["| Date | Candidate | Family | Dir | First known (cutoff) | Frozen quality | Reasons (code / scope / materiality) "
      "at first known | Globex boundary | Known gap in window? | Untraded slot in window? | Local evidence complete "
      "| Eligibility (first known) | Eligibility (16:00, final knowledge) |", "|" + "---|" * 13]
for d in dates:
    j = json.loads((src / f"{d}_quality.json").read_text())
    fk, fin = j["first_known"], j["final_knowledge"]
    for cid in sorted(fk, key=lambda c: fk[c]["first_event_ct"] if fk[c]["first_event_ct"] >= "17:00" else
                      "~" + fk[c]["first_event_ct"]):
        r, f = fk[cid], fin.get(cid)
        reasons = r["reasons"]
        rc = {x[0] for x in reasons}
        gap_in = any(x[0] in ("KNOWN_GAP", "SUSPECTED_GAP", "ACTIVE_INTERRUPTION") and x[2] == "LOCAL_EVIDENCE"
                     for x in reasons)
        untraded = any(x[0] == "UNTRADED_INTERVAL" for x in reasons)
        rows.append({"date": d, **r, "final": f})
        md.append(f"| {d} | {cid} | {r['family']} | {r['direction']} | {r['cutoff']} | {r['candidate_quality']} | "
                  + "<br>".join(f"{x[0]} / {x[1]} / {x[2]}" for x in reasons) + f" | {r['boundary_status']} | "
                  f"{'YES' if gap_in else 'no'} | {'YES' if untraded else 'no'} | {r['local_evidence_complete']} | "
                  f"{r['eligibility']} | {f['eligibility'] if f else 'n/a'} |")
        # why was the frozen state QUALITY_QUALIFIED at first known? the status-driving codes at that cutoff
        sb = next(s for s in j["status_by_cutoff"] if s["cutoff"] == r["cutoff"])
        driving = tuple(sorted(set(sb["codes"])))
        cause[driving] += 1
        stats[f"eligibility_first_known:{r['eligibility']}"] += 1
        if f:
            stats[f"eligibility_final:{f['eligibility']}"] += 1
            stats["final_reasons:" + ",".join(sorted({x[0] + "/" + x[2] for x in f["reasons"]}))] += 1
        stats["candidate_reasons_first_known:" + ",".join(sorted({x[0] + "/" + x[2] for x in reasons}))] += 1
        stats[f"total"] += 1
        stats[f"frozen_quality:{r['candidate_quality']}"] += 1
out = {"rows": rows, "stats": dict(sorted(stats.items())), "status_driving_codes_at_first_known":
       {"+".join(k): v for k, v in cause.items()}}
(src / "propagation_table.md").write_text("\n".join(md) + "\n")
(src / "propagation_summary.json").write_text(json.dumps(out, indent=1, sort_keys=True))
print(json.dumps(out["stats"], indent=1)); print(json.dumps(out["status_driving_codes_at_first_known"], indent=1))
