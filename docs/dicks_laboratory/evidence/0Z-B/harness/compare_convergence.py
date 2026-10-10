"""Process C: compare the terminal snapshot with MARKET_STUDY_STATE_V1 component by component (canonical JSON)."""
import json, sys
from pathlib import Path
snap = json.loads(Path(sys.argv[1]).read_text()); final = json.loads(Path(sys.argv[2]).read_text())
def at(doc, ptr):
    for part in ptr.strip("/").split("/"):
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc
pairs = [(x, x) for x in (
    "/provenance", "/contract", "/volume_profile", "/tpo/profile", "/tpo/status", "/tpo/reasons", "/tpo_structure",
    "/day_type", "/day_strength", "/prior_day", "/overnight/session", "/overnight/context", "/overnight/status",
    "/overnight/reasons", "/overnight/globex_open_claimed", "/overnight/globex_open_boundary_proven",
    "/overnight/first_observed_overnight_trade_is_globex_open", "/cash_opening/facts", "/cash_opening/path_facts",
    "/cash_opening/status", "/cash_opening/reasons", "/opening_type")]
pairs += [("/vwap/0/study", "/vwap/studies/0"), ("/vwap/1/study", "/vwap/studies/1"),
          ("/prices/study_window_terminal_price", "/day_type/classification/facts/terminal/price"),
          ("/current_dataset/lifecycle_as_of", "/current_dataset/lifecycle_state"),
          ("/current_dataset/counts/accepted_known", "/current_dataset/retained_trade_count"),
          ("/current_dataset/counts/corrections_applied", "/current_dataset/applied_correction_count"),
          ("/current_dataset/counts/cancels_applied", "/current_dataset/applied_cancel_count"),
          ("/current_dataset/closing_summary/accepted_trade_count", "/current_dataset/accepted_trade_count"),
          ("/current_dataset/closing_summary/rejected_record_count", "/current_dataset/rejected_record_count"),
          ("/current_dataset/closing_summary/deferred_event_count", "/current_dataset/deferred_event_count"),
          ("/current_dataset/closing_summary/submitted_events", "/current_dataset/submitted_events"),
          ("/current_dataset/closing_summary/persisted_events", "/current_dataset/persisted_events"),
          ("/current_dataset/closing_summary/closed_at", "/current_dataset/closing_summary_closed_at"),
          ("/current_dataset/closing_accounting_difference", "/current_dataset/accounting_difference"),
          ("/current_dataset/dataset_quality_placeholder", None)]
pairs = [p for p in pairs if p[1] is not None]
for f in ("dataset_id", "trading_date", "recorded_trading_date", "instrument_id", "kind", "origin", "label",
          "source_locator", "source_system", "streamer_symbol", "normalizer_version", "collector_version",
          "collector_git_commit", "capture_started_at", "capture_ended_at"):
    pairs.append((f"/current_dataset/{f}", f"/current_dataset/{f}"))
for f in ("completeness", "known_gap_count", "suspected_gap_count", "known_gap_duration", "gaps"):
    pairs.append((f"/dataset_quality/{f}", f"/dataset_quality/{f}"))
results = []
for sp, fp in pairs:
    a, b = at(snap, sp), at(final, fp)
    results.append({"snapshot": sp, "final_state": fp, "equal": a == b})
reg_equal = snap["policy_registry"][:-1] == final["policy_registry"] and snap["policy_registry"][-1]["policy_id"] == "MARKET_STUDY_SNAPSHOT_V1"
results.append({"snapshot": "/policy_registry[:-1]", "final_state": "/policy_registry", "equal": reg_equal})
n_eq = sum(r["equal"] for r in results)
out = {"compared": len(results), "equal": n_eq, "all_equal": n_eq == len(results),
       "expected_differences_by_design": ["schema", "state_temporality", "temporality_note", "cutoff",
           "cutoff_semantics", "maturity", "quality_matrix shape", "as-of counts beyond accepted/applied",
           "MARKET_STUDY_SNAPSHOT_V1 registry entry", "no database_sha256 / file checksum in the snapshot",
           "evidence_classification (0Z-A only)", "dataset_quality windows/status (as-of model)", "hash field name"],
       "results": results}
Path(sys.argv[3]).write_text(json.dumps(out, indent=1))
print(f"compared {len(results)} components: {n_eq} equal; all_equal={n_eq == len(results)}")
for r in results:
    if not r["equal"]: print("DIFFERS", r)
