"""Read-only 0W-4 dataset audit. Opens every DB with mode=ro; writes nothing to the data dir."""
import hashlib, json, os, sqlite3, sys, glob
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

CT = ZoneInfo("America/Chicago")
out = {}
paths = sys.argv[1:]


def ct(ts):
    if not ts:
        return None
    d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return d.astimezone(CT).isoformat()


for p in paths:
    r = {"path": p, "size_bytes": os.path.getsize(p)}
    r["sidecars"] = sorted(os.path.basename(x) for x in glob.glob(p + "*") if x != p)
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    q = lambda s, *a: [dict(x) for x in c.execute(s, a)]
    one = lambda s, *a: c.execute(s, a).fetchone()[0]
    r["journal_mode"] = one("PRAGMA journal_mode")
    r["quick_check"] = one("PRAGMA quick_check")
    r["integrity_check"] = one("PRAGMA integrity_check")
    r["datasets"] = q("SELECT * FROM datasets")
    r["instruments"] = q("SELECT * FROM instruments")
    r["closing"] = q("SELECT * FROM dataset_closing_summaries")
    r["quality_events"] = q(
        "SELECT evidence_type, detail, observed_at, interval_start, interval_end, source_record_ref "
        "FROM dataset_quality_events ORDER BY COALESCE(observed_at, interval_start)")
    r["qe_counts"] = {x["evidence_type"]: x["n"] for x in q(
        "SELECT evidence_type, COUNT(*) n FROM dataset_quality_events GROUP BY 1")}
    r["accepted"] = one("SELECT COUNT(*) FROM trade_observations")
    r["dseq"] = dict(c.execute("SELECT MIN(dataset_sequence) mn, MAX(dataset_sequence) mx, "
                               "COUNT(DISTINCT dataset_sequence) nd, COUNT(*) n FROM trade_observations").fetchone())
    r["trade_actions"] = {x["trade_action"]: x["n"] for x in q(
        "SELECT trade_action, COUNT(*) n FROM trade_observations GROUP BY 1")}
    r["rejected"] = one("SELECT COUNT(*) FROM normalization_rejections")
    r["rejections_by_reason"] = q("SELECT reason, COUNT(*) n FROM normalization_rejections GROUP BY 1")
    r["rejection_rows"] = q(
        "SELECT n.source_order, n.reason, n.detail, s.event_symbol, s.event_time, s.event_classification, "
        "s.event_flags, s.price, s.size, s.received_at FROM normalization_rejections n "
        "LEFT JOIN rejected_dxlink_timesale_source_records s USING(rejection_id) ORDER BY n.source_order LIMIT 50")
    r["deferred"] = one("SELECT COUNT(*) FROM deferred_dxlink_timesale_events")
    r["deferred_by_reason"] = q("SELECT reason, event_classification, COUNT(*) n FROM deferred_dxlink_timesale_events GROUP BY 1,2")
    # source_order across all three dispositions
    so = ("SELECT source_order FROM observation_source_provenance UNION ALL "
          "SELECT source_order FROM normalization_rejections UNION ALL "
          "SELECT source_order FROM deferred_dxlink_timesale_events")
    r["source_order"] = dict(c.execute(
        f"SELECT MIN(source_order) mn, MAX(source_order) mx, COUNT(DISTINCT source_order) nd, COUNT(*) n FROM ({so})").fetchone())
    r["provenance_rows"] = one("SELECT COUNT(*) FROM observation_source_provenance")
    r["first_trade"] = dict(c.execute(
        "SELECT t.dataset_sequence, t.event_timestamp, p.received_at FROM trade_observations t "
        "JOIN observation_source_provenance p USING(observation_id) ORDER BY t.dataset_sequence LIMIT 1").fetchone() or {})
    r["last_trade"] = dict(c.execute(
        "SELECT t.dataset_sequence, t.event_timestamp, p.received_at FROM trade_observations t "
        "JOIN observation_source_provenance p USING(observation_id) ORDER BY t.dataset_sequence DESC LIMIT 1").fetchone() or {})
    r["min_max_event_ts"] = dict(c.execute(
        "SELECT MIN(event_timestamp) mn, MAX(event_timestamp) mx FROM trade_observations").fetchone())
    # trades bracketing each gap / disconnect
    brackets = []
    for e in r["quality_events"]:
        if e["evidence_type"] in ("KNOWN_GAP", "SUSPECTED_GAP", "SOURCE_DISCONNECTED", "SOURCE_RECONNECTED"):
            a = e["interval_start"] or e["observed_at"]
            b = e["interval_end"] or e["observed_at"]
            before = c.execute(
                "SELECT t.dataset_sequence, t.event_timestamp, p.received_at, p.source_order FROM trade_observations t "
                "JOIN observation_source_provenance p USING(observation_id) WHERE p.received_at <= ? "
                "ORDER BY p.received_at DESC LIMIT 1", (a,)).fetchone()
            after = c.execute(
                "SELECT t.dataset_sequence, t.event_timestamp, p.received_at, p.source_order FROM trade_observations t "
                "JOIN observation_source_provenance p USING(observation_id) WHERE p.received_at >= ? "
                "ORDER BY p.received_at LIMIT 1", (b,)).fetchone()
            brackets.append({"type": e["evidence_type"], "start": a, "end": b,
                             "before": dict(before) if before else None, "after": dict(after) if after else None})
    r["gap_brackets"] = brackets
    # per-minute received rate (CT) for 08:20-09:00 on the trading date, plus whole-day busiest minutes
    td = r["datasets"][0].get("label", "")
    per_min = q("SELECT substr(received_at,1,16) m, COUNT(*) n FROM observation_source_provenance GROUP BY 1")
    pm = []
    for x in per_min:
        d = datetime.fromisoformat(x["m"] + ":00+00:00").astimezone(CT)
        pm.append((d, x["n"]))
    pm.sort()
    r["busiest_minutes_ct"] = [(d.strftime("%a %H:%M"), n) for d, n in sorted(pm, key=lambda z: -z[1])[:10]]
    r["window_0820_0900_ct"] = [(d.strftime("%H:%M"), n) for d, n in pm
                                if d.weekday() < 5 and d.hour == 8 and d.minute >= 20]
    r["events_per_hour_ct"] = {}
    for d, n in pm:
        k = d.strftime("%a %H")
        r["events_per_hour_ct"][k] = r["events_per_hour_ct"].get(k, 0) + n
    # max received-to-received silence between consecutive accepted trades (not a gap proof)
    prev = None
    silences = []
    for (ra,) in c.execute("SELECT received_at FROM observation_source_provenance ORDER BY source_order"):
        d = datetime.fromisoformat(ra.replace("Z", "+00:00"))
        if prev is not None:
            s = (d - prev).total_seconds()
            if s > 60:
                silences.append((prev.isoformat(), d.isoformat(), round(s, 1)))
        prev = d
    r["receive_silences_gt60s"] = silences
    # dataset_sequence dup/hole detection
    r["dseq_holes"] = r["dseq"]["mx"] - r["dseq"]["nd"] if r["dseq"]["mx"] else 0
    r["dseq_dups"] = r["dseq"]["n"] - r["dseq"]["nd"]
    r["so_holes"] = (r["source_order"]["mx"] - r["source_order"]["mn"] + 1 - r["source_order"]["nd"]) if r["source_order"]["mx"] else 0
    r["so_dups"] = r["source_order"]["n"] - r["source_order"]["nd"]
    c.close()
    # manifest + checksum
    mp = p + ".manifest.json"
    if os.path.exists(mp):
        r["manifest"] = json.load(open(mp))
    else:
        r["manifest"] = None
    out[os.path.basename(p)] = r

json.dump(out, sys.stdout, indent=1, default=str)
