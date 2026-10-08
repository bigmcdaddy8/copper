"""0Y-D: blind-validation helpers (records, diagnostics, shortlist) and the two-stage CLI (smoke)."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import DxLinkTimeAndSaleProvenance
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset
from dicks_laboratory.tpo_validation import (
    DayRecord,
    Eligibility,
    boundary_cases,
    day_record,
    distribution,
    inspection_shortlist,
    neutral_asymmetry,
    one_sided_extension,
    quantiles,
    record_from_json,
    record_to_json,
    render_validation_report,
    structural_outliers,
)

D = Decimal
_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = "scripts/dicks_lab_mp_validation.py"
_ES = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12)
_NS = UUID("0e5a0000-0000-4000-8000-0000000000d0")


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _db(tmp_path, name, ranges, *, gaps=(), capture_end=None):
    """FINALIZED ES dataset on TD 2026-10-06: period i trades (low, high) at minutes 1 and 2."""
    dataset_id = uuid5(_NS, name)
    open_ = _utc(2026, 10, 6, 13, 30)
    rows = [(open_ + timedelta(minutes=30 * i + m), p) for i, (lo, hi) in enumerate(ranges)
            for m, p in ((1, lo), (2, hi))]
    trades = tuple(TradeObservation(uuid5(dataset_id, str(i)), dataset_id, i + 1, _ES, ts, D(p), D(1))
                   for i, (ts, p) in enumerate(rows))
    path = tmp_path / f"{name}.sqlite3"
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(dataset_id, DatasetKind.HISTORICAL_IMPORT, "val-test",
                                       capture_started_at=_utc(2026, 10, 5, 22, 0),
                                       capture_ended_at=capture_end or _utc(2026, 10, 6, 21, 0)))
    store.save_trade_observations(trades)
    store.save_dxlink_time_and_sale_provenance(tuple(
        DxLinkTimeAndSaleProvenance(t.observation_id, f"evt:{t.dataset_sequence}", t.dataset_sequence,
                                    t.dataset_sequence, t.dataset_sequence, t.dataset_sequence, t.event_timestamp,
                                    event_classification="NEW") for t in trades))
    store.save_quality_events(tuple(
        DatasetQualityEvent(uuid5(dataset_id, f"g{i}"), dataset_id, DatasetQualityEvidenceType.KNOWN_GAP, "gap",
                            interval_start=s, interval_end=e) for i, (s, e) in enumerate(gaps)))
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.FINALIZED)
    store.close()
    return path, dataset_id


def _record(tmp_path, name, ranges, **kw):
    path, did = _db(tmp_path, name, ranges, **kw)
    store = LaboratoryStore(path, read_only=True)
    try:
        return day_record(analyze_tpo_dataset(store, did))
    finally:
        store.close()


NORMAL = [("100", "110")] * 2 + [("102", "108")] * 11
NEUTRAL = [("100", "110")] * 2 + [("108", "112"), ("95", "101")] + [("100", "105")] * 9
NV_DOWN = [("100", "110"), ("102", "110"), ("96", "104"), ("94", "100")] + [("95", "102")] * 9


def _synthetic(td, day_type, share, **kw):
    base = dict(trading_date=td, dataset_id=f"{td}-id", contract="FUTURE:CME:ES:2026-12", lifecycle="FINALIZED",
                window_captured=True, known_gap_count=0, suspected_gap_count=0, gaps_overlapping_window=0,
                dataset_quality="COMPLETE / NO KNOWN GAPS", classification_quality="UNQUALIFIED",
                eligibility=Eligibility.ELIGIBLE, reasons=(), outcome="CANDIDATE" if day_type else "UNCLASSIFIED",
                day_type=day_type, direction=None, policy_version="V1", failed_conditions=(), ib_share=D(share),
                ib_range=D(10), profile_range=D(10) / D(share), range_multiple_of_ib=D(1) / D(share),
                ext_above=D(0), ext_below=D(0), ext_above_ticks=0, ext_below_ticks=0, ext_above_ib=D(0),
                ext_below_ib=D(0), directional_state="NO_EXTENSION", terminal_pct=D("0.5"), upper_tail_rows=0,
                lower_tail_rows=0, interior_zones=0)
    base.update(kw)
    return DayRecord(**base)


# --- records from real analysis ----------------------------------------------------------------

def test_day_record_flattens_eligible_classification(tmp_path):
    r = _record(tmp_path, "nvd", NV_DOWN)
    assert (r.eligibility, r.outcome, r.day_type, r.direction) == (
        Eligibility.ELIGIBLE, "CANDIDATE", "NORMAL_VARIATION_DAY", "DOWN")
    assert (r.ib_share, r.ext_below_ticks, r.ext_below_ib, r.new_low_periods) == (D("0.625"), 24, D("0.6"), "CD")
    assert one_sided_extension(r) == (D("6.00"), 24, D("0.6"), 11, 2)
    assert "NORMAL_DAY:ib_share_wide" in r.failed_conditions and r.label == "NORMAL_VARIATION_DAY DOWN"


def test_day_record_eligibility_by_quality(tmp_path):
    gap = (_utc(2026, 10, 6, 15, 0), _utc(2026, 10, 6, 15, 1))
    qq = _record(tmp_path, "qq", NORMAL, gaps=[gap])
    assert (qq.eligibility, qq.reasons, qq.day_type) == (
        Eligibility.QUALITY_QUALIFIED, ("gap evidence (KNOWN/SUSPECTED) overlaps the study window: 1",), "NORMAL_DAY")
    outside = _record(tmp_path, "out", NORMAL, gaps=[(_utc(2026, 10, 6, 9, 0), _utc(2026, 10, 6, 9, 1))])
    assert (outside.eligibility, outside.known_gap_count, outside.gaps_overlapping_window) == (Eligibility.ELIGIBLE, 1, 0)
    cut = _record(tmp_path, "cut", NORMAL, capture_end=_utc(2026, 10, 6, 19, 36))
    assert (cut.eligibility, cut.reasons, cut.day_type) == (
        Eligibility.NOT_CLASSIFIED, ("STUDY WINDOW NOT FULLY CAPTURED",), None)


def test_json_round_trip_is_exact(tmp_path):
    r = _record(tmp_path, "neu", NEUTRAL)
    line = record_to_json(r)
    assert record_from_json(line) == r and json.loads(line)["ib_share"] == str(r.ib_share)
    assert record_to_json(record_from_json(line)) == line


# --- diagnostics ---------------------------------------------------------------------------------

def test_quantiles_nearest_rank():
    assert quantiles([D(x) for x in (5, 1, 4, 2, 3)]) == {
        "min": D(1), "q25": D(2), "median": D(3), "q75": D(4), "max": D(5)}
    assert quantiles([D(1), D(2), D(3), D(4)])["median"] == D("2.5")
    assert quantiles([]) is None


def test_distribution_separates_quality_qualified():
    recs = [_synthetic("2026-01-01", "NORMAL_DAY", "0.9"), _synthetic("2026-01-02", None, "0.4"),
            replace(_synthetic("2026-01-03", "NORMAL_DAY", "0.9"), eligibility=Eligibility.QUALITY_QUALIFIED),
            replace(_synthetic("2026-01-04", None, "0.9"), eligibility=Eligibility.NOT_CLASSIFIED,
                    outcome="NOT_CLASSIFIED")]
    assert distribution(recs) == {Eligibility.ELIGIBLE: {"NORMAL_DAY": 1, "UNCLASSIFIED": 1},
                                  Eligibility.QUALITY_QUALIFIED: {"NORMAL_DAY": 1}}


def test_boundary_cases_band_is_inclusive_and_signed():
    recs = [_synthetic("2026-01-01", "NORMAL_DAY", "0.90"), _synthetic("2026-01-02", None, "0.84"),
            _synthetic("2026-01-03", None, "0.45"), _synthetic("2026-01-04", None, "0.70")]
    got = [(c.record.trading_date, str(c.boundary), str(c.distance), c.side) for c in boundary_cases(recs)]
    assert got == [("2026-01-03", "0.50", "-0.05", "below"), ("2026-01-02", "0.85", "-0.01", "below"),
                   ("2026-01-01", "0.85", "0.05", "at/above")]


def test_neutral_asymmetry(tmp_path):
    a = neutral_asymmetry(_record(tmp_path, "neu", NEUTRAL))  # above 8 ticks, below 20 ticks, IB 10
    assert (a.smaller_ticks, a.larger_ticks, a.smaller_ib, a.larger_ib, a.smaller_over_larger) == (
        8, 20, D("0.2"), D("0.5"), D("0.4"))


def test_outliers_and_shortlist_are_mechanical_with_earlier_date_ties():
    recs = [_synthetic("2026-01-02", "NORMAL_DAY", "0.90"), _synthetic("2026-01-01", "NORMAL_DAY", "0.90"),
            _synthetic("2026-01-03", "NORMAL_DAY", "0.95"),
            _synthetic("2026-01-04", None, "0.40", directional_state="UP_ONLY", ext_above=D(5), ext_above_ticks=20,
                       ext_above_ib=D("0.5"), new_high_periods="C", terminal_pct=D("0.2"))]
    out = {name: (v, d) for name, v, d in structural_outliers(recs)}
    assert out["smallest profile / IB ratio"] == (D(1) / D("0.95"), ["2026-01-03"])
    assert out["terminal price nearest high (percentile)"] == (D("0.5"), ["2026-01-01", "2026-01-02", "2026-01-03"])
    assert out["most asymmetric two-sided extension (smaller/larger)"] == (None, [])
    short = dict(inspection_shortlist(recs))
    assert short["representative NORMAL_DAY"].trading_date == "2026-01-01"  # median 0.90, tie -> earlier
    assert short["nearest 0.85 boundary"].trading_date == "2026-01-01"
    assert short["nearest 0.50 boundary"].trading_date == "2026-01-04"
    assert short["first UNCLASSIFIED"].trading_date == "2026-01-04"
    assert short["representative TREND_DAY"] is None and short["strongest TREND_DAY"] is None


def test_report_renders_every_section_deterministically(tmp_path):
    recs = [_record(tmp_path, n, rg) for n, rg in (("a", NORMAL), ("b", NEUTRAL), ("c", NV_DOWN))]
    text = render_validation_report(recs, "abc", {r.dataset_id: f"reports/{r.dataset_id[:8]}.txt" for r in recs})
    for needle in ("## 1. Corpus inventory", "Counts: ELIGIBLE 3, QUALITY_QUALIFIED 0, NOT_CLASSIFIED 0",
                   "| NEUTRAL_DAY | 1 | 33.3 | 0 |", "## 6. NEUTRAL_DAY sensitivity", "smaller/larger (n=1)",
                   "## 12. Mechanical inspection shortlist", "Historical \"wide IB\" context: NOT EVALUATED"):
        assert needle in text, needle
    assert text == render_validation_report(list(reversed(recs)), "abc",
                                            {r.dataset_id: f"reports/{r.dataset_id[:8]}.txt" for r in recs})


# --- CLI smoke -----------------------------------------------------------------------------------

def _cli(*args):
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
    return subprocess.run([sys.executable, _SCRIPT, *args], cwd=_REPO, env=env, capture_output=True, text=True)


def test_cli_run_then_analyze_and_refuse_tampered_records(tmp_path):
    dbs = [_db(tmp_path, n, rg)[0] for n, rg in (("a", NORMAL), ("b", NEUTRAL))]
    before = [p.read_bytes() for p in dbs]
    out = tmp_path / "out"
    r = _cli("run", str(out), *map(str, dbs))
    assert r.returncode == 0, r.stderr
    assert (out / "records.jsonl").read_text().count("\n") == 2 and len(list((out / "reports").iterdir())) == 2
    assert "DAY-TYPE CANDIDATES" in next((out / "reports").iterdir()).read_text()
    assert [p.read_bytes() for p in dbs] == before  # read-only
    a = _cli("analyze", str(out))
    assert a.returncode == 0 and "## 12. Mechanical inspection shortlist" in (out / "validation_report.md").read_text()
    (out / "records.jsonl").write_text((out / "records.jsonl").read_text().replace("NEUTRAL_DAY", "TREND_DAY"))
    assert _cli("analyze", str(out)).returncode == 2
