"""0Y-A: TPO dataset analysis, quality qualification and the read-only CLI (smoke)."""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5

from dicks_laboratory.dataset_state import DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import DxLinkTimeAndSaleProvenance
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_analysis import QualityStatus, analyze_tpo_dataset, render_tpo_report
from dicks_laboratory.tpo_day_structure import ClassificationOutcome, DayType, DirectionalState, QualityGrade

_REPO = Path(__file__).resolve().parents[3]
_SCRIPT = "scripts/dicks_lab_tpo_profile.py"
_ES = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, 12)
_NS = UUID("0e5a0000-0000-4000-8000-000000000000")
D = Decimal


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def _build(tmp_path, *, trading_day=6, gaps=(), suspected=(), capture_end=None, name="tpo.sqlite3", extra=()):
    """A FINALIZED ES dataset for trading date 2026-10-<day> (CDT: cash open 13:30Z)."""
    dataset_id = uuid5(_NS, f"{name}-{trading_day}")
    open_ = _utc(2026, 10, trading_day, 13, 30)
    rows = [
        (_utc(2026, 10, trading_day - 1, 23, 0), "99.00", 1),   # overnight: same trading date, outside window
        (open_ + timedelta(minutes=1), "100.00", 500),            # A -- heavy volume at 100.00
        (open_ + timedelta(minutes=2), "101.00", 1),              # A
        (open_ + timedelta(minutes=31), "100.50", 1),             # B
        (open_ + timedelta(minutes=32), "101.50", 1),             # B
        (_utc(2026, 10, trading_day, 20, 0), "120.00", 1),        # 15:00 CT -- excluded
        *extra,
    ]
    trades = tuple(
        TradeObservation(uuid5(dataset_id, str(i)), dataset_id, i + 1, _ES, ts, D(price), D(size))
        for i, (ts, price, size) in enumerate(rows)
    )
    started = _utc(2026, 10, trading_day - 1, 22, 0)
    ended = capture_end or _utc(2026, 10, trading_day, 21, 0)
    events = tuple(
        DatasetQualityEvent(uuid5(dataset_id, f"{kind}{i}"), dataset_id, kind, "test gap",
                            interval_start=start, interval_end=end)
        for kind, spans in ((DatasetQualityEvidenceType.KNOWN_GAP, gaps), (DatasetQualityEvidenceType.SUSPECTED_GAP, suspected))
        for i, (start, end) in enumerate(spans)
    )
    path = tmp_path / name
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(dataset_id, DatasetKind.HISTORICAL_IMPORT, "tpo-test",
                                       capture_started_at=started, capture_ended_at=ended))
    store.save_trade_observations(trades)
    # DXLink provenance: the effective tape (the profiled source) is rebuilt from it.
    store.save_dxlink_time_and_sale_provenance(tuple(
        DxLinkTimeAndSaleProvenance(t.observation_id, f"evt:{t.dataset_sequence}", t.dataset_sequence,
                                    t.dataset_sequence, t.dataset_sequence, t.dataset_sequence, t.event_timestamp,
                                    event_classification="NEW")
        for t in trades))
    store.save_quality_events(events)
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.FINALIZED)
    store.close()
    return path, dataset_id


def _analyze(path, dataset_id, **kwargs):
    store = LaboratoryStore(path, read_only=True)
    try:
        return analyze_tpo_dataset(store, dataset_id, **kwargs)
    finally:
        store.close()


def _run(*args):
    env = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}
    return subprocess.run([sys.executable, _SCRIPT, *args], cwd=_REPO, env=env, capture_output=True, text=True)


# Represents the 2026-09-29 qualification (one 1.593 s KNOWN_GAP at 04:14:58.865 CT, overnight),
# placed on this fixture's trading date.
_SEP29_GAP = (_utc(2026, 10, 6, 9, 14, 58, 865000), _utc(2026, 10, 6, 9, 15, 0, 458000))


def test_clean_dataset_reports_complete_and_window_only_trades(tmp_path):
    path, did = _build(tmp_path)
    r = _analyze(path, did)
    assert r.quality.status is QualityStatus.COMPLETE and r.quality.study_window_captured is True
    p = r.profile
    assert p.selected_trade_count == 4  # overnight and 15:00 trades excluded
    assert [(str(lv.price), lv.periods) for lv in reversed(p.levels)] == [
        ("101.50", "B"), ("101.25", "B"), ("101.00", "AB"), ("100.75", "AB"),
        ("100.50", "AB"), ("100.25", "A"), ("100.00", "A")]
    text = render_tpo_report(r)
    assert "QUALITY:\n  COMPLETE / NO KNOWN GAPS" in text and "KNOWN_GAP=" not in text


def test_known_gap_dataset_still_computes_but_stays_qualified(tmp_path):
    path, did = _build(tmp_path, gaps=[_SEP29_GAP])
    r = _analyze(path, did)
    assert r.profile is not None and r.profile.poc == D("100.75")
    assert r.quality.status is QualityStatus.INCOMPLETE and r.quality.known_gap_count == 1
    assert r.quality.gaps_overlapping_study_window == 0
    text = render_tpo_report(r)
    assert "QUALITY:\n  INCOMPLETE\n  KNOWN_GAP=1\n  SUSPECTED_GAP=0" in text
    assert "Known-gap duration: 1.593s" in text and "NOT complete" in text
    assert "COMPLETE / NO KNOWN GAPS" not in text


def test_gap_does_not_change_profile_math(tmp_path):
    clean = _analyze(*_build(tmp_path, name="a.sqlite3")).profile
    gapped = _analyze(*_build(tmp_path, name="b.sqlite3",
                              gaps=[(_utc(2026, 10, 6, 13, 45), _utc(2026, 10, 6, 13, 46))])).profile
    assert gapped.levels == clean.levels and gapped.value_area == clean.value_area


def test_gap_inside_window_and_suspected_gap_are_reported(tmp_path):
    path, did = _build(tmp_path, suspected=[(_utc(2026, 10, 6, 14, 0), _utc(2026, 10, 6, 14, 1))])
    r = _analyze(path, did)
    assert r.quality.status is QualityStatus.SUSPECTED and r.quality.gaps_overlapping_study_window == 1
    assert "QUALIFIED / SUSPECTED GAPS" in render_tpo_report(r)


def test_capture_ending_before_window_end_is_visible(tmp_path):
    path, did = _build(tmp_path, capture_end=_utc(2026, 10, 6, 19, 36))
    r = _analyze(path, did)
    assert r.quality.study_window_captured is False
    assert "STUDY WINDOW NOT FULLY CAPTURED" in render_tpo_report(r)


def test_tpo_and_volume_profile_coexist_and_differ(tmp_path):
    r = _analyze(*_build(tmp_path))
    assert r.profile.poc == D("100.75")  # time: AB overlap, nearest midpoint
    assert r.volume_profile.point_of_control.price == D("100.00")  # volume: 500 contracts
    text = render_tpo_report(r, compare_volume=True)
    assert "  POC      100.75      100.00" in text
    assert "TPO: time/opportunity distribution" in text and "Volume: contract-volume distribution" in text


def test_matrix_marks_poc_value_area_and_ib(tmp_path):
    text = render_tpo_report(_analyze(*_build(tmp_path)))
    rows = {line.split()[0]: line for line in text.splitlines() if line.startswith("  10")}
    assert "POC" in rows["100.75"] and "| " in rows["100.75"]
    assert "VAH" in rows["101.25"] and "VAL" in rows["100.25"]
    assert "IBH" in rows["101.50"] and "IBL" in rows["100.00"]
    assert rows["100.00"].rstrip().endswith("A") and "|" not in rows["100.00"]


# --- CLI ------------------------------------------------------------------------

def test_cli_help():
    r = _run("--help")
    assert r.returncode == 0 and "--period-minutes" in r.stdout and "--session" in r.stdout


def test_cli_reports_and_is_deterministic_and_read_only(tmp_path):
    path, _ = _build(tmp_path, gaps=[_SEP29_GAP])
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    first = _run(str(path), "--session", "cash", "--period-minutes", "30", "--compare-volume-profile")
    second = _run(str(path), "--session", "cash", "--period-minutes", "30", "--compare-volume-profile")
    assert first.returncode == 0, first.stderr
    assert first.stdout == second.stdout
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    for text in ("US_CASH_PROFILE", "08:30-15:00 America/Chicago", "Period size:    30 minutes",
                 "TPO POC:        100.75", "TPO VAL:", "TPO VAH:", "IB range:", "Periods present: AB (2 of 13)",
                 "KNOWN_GAP=1", "Range extension above IB: 0.00 (0 ticks)"):
        assert text in first.stdout, text


def test_cli_period_minutes_15_and_invalid(tmp_path):
    path, _ = _build(tmp_path)
    ok = _run(str(path), "--period-minutes", "15", "--no-matrix")
    assert ok.returncode == 0 and "Periods present: AC (2 of 26)" in ok.stdout and "TPO matrix" not in ok.stdout
    bad = _run(str(path), "--period-minutes", "45")
    assert bad.returncode == 2 and "does not tile" in bad.stderr


def test_cli_unsupported_session_and_missing_file(tmp_path):
    assert _run("nope.sqlite3").returncode == 2
    path, _ = _build(tmp_path)
    assert _run(str(path), "--session", "globex").returncode != 0


def test_cli_no_window_trades_exits_one(tmp_path):
    path, _ = _build(tmp_path)
    r = _run(str(path), "--trading-date", "2026-10-07")
    assert r.returncode == 1
    assert "No TPO profile, POC, Value Area or Initial Balance was calculated." in r.stdout


# --- 0Y-B structure section ---------------------------------------------------------

def test_structure_is_programmatic_and_clean_dataset_is_unqualified(tmp_path):
    r = _analyze(*_build(tmp_path))
    assert r.structure is not None and r.quality.structural_qualifications == ()
    assert [(str(z.low), str(z.high), z.periods) for z in r.structure.zones] == [
        ("100.00", "100.25", "A"), ("101.25", "101.50", "B")]
    text = render_tpo_report(r, show_structure=True)
    assert "QUALITY-QUALIFIED" not in text
    assert "EXCESS_HIGH_CANDIDATE: YES   (rule: tail >= 2 one-TPO rows)" in text
    assert "POOR_LOW_CANDIDATE:   NO" in text


def test_known_gap_inside_window_qualifies_structure_prominently(tmp_path):
    path, did = _build(tmp_path, gaps=[(_utc(2026, 10, 6, 13, 45), _utc(2026, 10, 6, 13, 46))])
    r = _analyze(path, did)
    text = render_tpo_report(r, show_structure=True)
    assert "*** STRUCTURAL FEATURES ARE QUALITY-QUALIFIED ***" in text
    assert "gap evidence (KNOWN/SUSPECTED) overlaps the study window: 1" in text
    assert "EXCESS_HIGH_CANDIDATE: YES (quality-qualified)" in text
    assert "INCOMPLETE" in text and "COMPLETE / NO KNOWN GAPS" not in text


def test_gap_outside_window_keeps_dataset_incomplete_but_structure_unqualified(tmp_path):
    r = _analyze(*_build(tmp_path, gaps=[_SEP29_GAP]))
    assert r.quality.structural_qualifications == ()
    assert "QUALITY:\n  INCOMPLETE" in render_tpo_report(r, show_structure=True)


def test_truncated_capture_qualifies_structure(tmp_path):
    r = _analyze(*_build(tmp_path, capture_end=_utc(2026, 10, 6, 19, 36)))
    assert r.quality.structural_qualifications == ("STUDY WINDOW NOT FULLY CAPTURED",)
    text = render_tpo_report(r, show_structure=True)
    assert "*** STRUCTURAL FEATURES ARE QUALITY-QUALIFIED ***\n    - STUDY WINDOW NOT FULLY CAPTURED" in text


def test_cli_structure_flag_and_default_output_unchanged(tmp_path):
    path, _ = _build(tmp_path)
    plain = _run(str(path))
    structured = _run(str(path), "--structure")
    assert plain.returncode == structured.returncode == 0
    assert "STRUCTURE (" not in plain.stdout and "Str " not in plain.stdout
    assert "STRUCTURE (DICKS_LAB_TPO_STRUCTURE_POLICY" in structured.stdout
    assert structured.stdout == _run(str(path), "--structure").stdout
    rows = {line.split()[0]: line for line in structured.stdout.splitlines() if line.startswith("  10")}
    assert "TAIL" in rows["101.50"] and "TAIL" in rows["100.00"] and "TAIL" not in rows["100.75"]


# --- 0Y-C day structure --------------------------------------------------------------

def _full_day():
    """Periods C..M each trade 100.50-101.00 inside the IB (100.00-101.50): no extension."""
    open_ = _utc(2026, 10, 6, 13, 30)
    return tuple((open_ + timedelta(minutes=30 * i + m), price, 1)
                 for i in range(2, 13) for m, price in ((5, "100.50"), (6, "101.00")))


def test_day_structure_is_programmatic_and_partial_window_is_not_classified(tmp_path):
    r = _analyze(*_build(tmp_path))
    day = r.day_structure
    assert day.facts.periods_without_trades == "CDEFGHIJKLM" and day.facts.ib_range == D("1.50")
    assert (day.facts.terminal.price, day.facts.terminal.period_label) == (D("101.50"), "B")
    assert (day.outcome, day.candidates) == (ClassificationOutcome.NOT_CLASSIFIED, ())
    assert day.quality.grade is QualityGrade.UNQUALIFIED


def test_full_clean_day_is_classified_and_rendered_with_conditions(tmp_path):
    r = _analyze(*_build(tmp_path, extra=_full_day()))
    day = r.day_structure
    assert (day.outcome, day.primary, day.facts.directional_state) == (
        ClassificationOutcome.CANDIDATE, DayType.NORMAL_DAY, DirectionalState.NO_EXTENSION)
    text = render_tpo_report(r, show_day_structure=True)
    for needle in ("DAY STRUCTURE FACTS:", "Directional state: NO_EXTENSION", "Study-window terminal price: 101.00",
                   "Outcome: CANDIDATE -- NORMAL_DAY_CANDIDATE", "[satisfied    ] ib_share_wide",
                   "[not evaluated] ib_wide_vs_history", "TREND_DAY_CANDIDATE: NO", "Deferred (not evaluated): NON_TREND_DAY"):
        assert needle in text, needle
    assert "QUALITY-QUALIFIED" not in text


def test_gap_inside_window_qualifies_named_day_type(tmp_path):
    r = _analyze(*_build(tmp_path, extra=_full_day(), gaps=[(_utc(2026, 10, 6, 15, 0), _utc(2026, 10, 6, 15, 1))]))
    assert r.day_structure.quality.grade is QualityGrade.QUALITY_QUALIFIED
    text = render_tpo_report(r, show_day_structure=True)
    assert "*** DAY-TYPE CLASSIFICATION IS QUALITY-QUALIFIED ***" in text
    assert "NORMAL_DAY_CANDIDATE (quality-qualified)" in text


def test_overnight_gap_outside_window_leaves_classification_unqualified(tmp_path):
    r = _analyze(*_build(tmp_path, extra=_full_day(), gaps=[_SEP29_GAP]))
    assert r.quality.status is QualityStatus.INCOMPLETE
    assert (r.day_structure.quality.grade, r.day_structure.primary) == (QualityGrade.UNQUALIFIED, DayType.NORMAL_DAY)


def test_truncated_capture_is_not_classified(tmp_path):
    r = _analyze(*_build(tmp_path, extra=_full_day(), capture_end=_utc(2026, 10, 6, 19, 36)))
    day = r.day_structure
    assert (day.outcome, day.not_classified_reasons) == (
        ClassificationOutcome.NOT_CLASSIFIED, ("STUDY WINDOW NOT FULLY CAPTURED",))
    text = render_tpo_report(r, show_day_structure=True)
    assert "Outcome: NOT_CLASSIFIED -- no named day type is claimed\n    - STUDY WINDOW NOT FULLY CAPTURED" in text
    assert "_CANDIDATE: YES" not in text and "DAY STRUCTURE FACTS:" in text


def test_cli_day_structure_flag_leaves_default_and_structure_output_unchanged(tmp_path):
    path, _ = _build(tmp_path, extra=_full_day())
    plain, structured, day = _run(str(path)), _run(str(path), "--structure"), _run(str(path), "--day-structure")
    assert plain.returncode == structured.returncode == day.returncode == 0
    assert "DAY STRUCTURE" not in plain.stdout + structured.stdout
    assert "Boundary: derived facts only -- no interpretation, day type or signal." in plain.stdout
    assert day.stdout.startswith(plain.stdout.split("TPO matrix")[0])
    assert "Outcome: CANDIDATE -- NORMAL_DAY_CANDIDATE" in day.stdout
    assert day.stdout == _run(str(path), "--day-structure").stdout
