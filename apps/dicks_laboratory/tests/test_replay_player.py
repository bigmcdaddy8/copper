"""0Z-C: replay evidence player, MarketStudyDelta and the tutor-facing evidence interface.

Uses the 0Z-B fixture day (test_replay): late print 09:55 received 10:05; 09:55:30 trade corrected
by a CORRECTION received 10:05:10; 09:56 trade canceled by a CANCEL received 10:05:20; disconnect
10:15:00, reconnect 10:15:30 (KNOWN_GAP between); capture stop 15:30 CT.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from dicks_laboratory.market_study_state import AnalysisProvenance, EvidenceKind, _dumps, encode
from dicks_laboratory.replay import MarketReplay, Maturity, ReplayCutoff, snapshot_sha256
from dicks_laboratory.replay_player import (
    DELTA_HASH_FIELD,
    DELTA_SCHEMA,
    ChangeKind,
    ReplaySession,
    TutorEvidenceSession,
    canonical_delta_json,
    compare_snapshot_states,
    delta_sha256,
    marker,
    relations,
    render_delta,
    render_player_view,
)

sys.path.insert(0, str(Path(__file__).parent))
import test_replay as fx_mod  # noqa: E402  (shared 0Z-B fixtures)

CUR, PRIOR, ct = fx_mod.CUR, fx_mod.PRIOR, fx_mod.ct
PROV = AnalysisProvenance("a" * 40, False)
REPO = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def session(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("player")
    prior = fx_mod._db(tmp, PRIOR, [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                       name="prior", gaps=False, rejected=False, stopped_ct=(16, 0))
    cur = fx_mod._db(tmp, CUR, fx_mod.OVERNIGHT + fx_mod._base_day() + fx_mod.SPECIAL, name="cur",
                     deferred=(fx_mod.CORRECTION, fx_mod.CANCEL))
    s = ReplaySession(MarketReplay.load(cur, PROV, prior))
    s.paths = (prior, cur)
    return s


def _kinds(delta):
    return {(c.path, c.kind) for c in delta.changes}


def _change(delta, path):
    found = [c for c in delta.changes if c.path == path]
    assert len(found) == 1, (path, [c.path for c in delta.changes])
    return found[0]


# --- session: seeking, timeline, stepping ------------------------------------------------------

def test_resolve_time_and_timeline(session):
    assert session.resolve_time("09:45") == ct(CUR, 9, 45)
    assert session.resolve_time("12:14:01") == ct(CUR, 12, 14, 1)
    assert session.resolve_time("17:30") == ct(CUR - timedelta(days=1), 17, 30)  # Sunday evening opens Monday
    assert session.resolve_time("2026-10-05T09:45:00-05:00") == ct(CUR, 9, 45)
    with pytest.raises(ValueError):
        session.resolve_time("2026-10-05T09:45:00")
    names = [m.name for m in session.timeline()]
    assert names == ["GLOBEX_OPEN 17:00", "CASH_OPEN 08:30", "OPENING_5MIN 08:35", "OPENING_15MIN 08:45",
                     "PERIOD_A_END 09:00", "IB_END 09:30", "CASH_STUDY_END 15:00", "SESSION_END 16:00"]
    assert session.timeline()[0].at_utc == ct(CUR - timedelta(days=1), 17, 0)
    assert session.step("09:45", "+1m") == ct(CUR, 9, 46) and session.step("09:45", "+5m") == ct(CUR, 9, 50)
    assert session.step("09:45", "next") == ct(CUR, 15, 0) and session.step("08:30", "next") == ct(CUR, 8, 35)
    with pytest.raises(ValueError):
        session.step("09:45", "+1h")


def test_seek_is_cached_and_equal_to_the_engine(session):
    a = session.snapshot("09:47")
    assert session.snapshot(ct(CUR, 9, 47)) is a
    assert snapshot_sha256(a) == snapshot_sha256(session.replay.snapshot(at=ct(CUR, 9, 47)))


# --- deltas ------------------------------------------------------------------------------------

def test_same_snapshot_is_a_zero_delta(session):
    d = session.compare("10:00", "10:00")
    assert d.changes == () and d.is_empty and d.from_snapshot_sha256 == d.to_snapshot_sha256
    assert d.newly_known.records == 0


def test_new_trade_evidence(session):
    d = session.compare("10:30", "10:31")  # the 10:30 @104 trade enters the market window
    c = _change(d, "/current_dataset/counts/known_records_with_market_time_at_or_after_cutoff")
    assert (c.before, c.after) == (1, 0)
    d2 = session.compare("12:00", "12:01")
    assert ("/current_dataset/counts/accepted_known", ChangeKind.OBSERVATION_ADDED) in _kinds(d2)


def test_late_print_is_a_late_observation(session):
    d = session.compare("10:04:59", "10:05:01")
    c = _change(d, "/evidence/newly_known_records_with_market_time_before_earlier_cutoff")
    assert (c.kind, c.before, c.after) == (ChangeKind.LATE_OBSERVATION_ADDED, 0, 1)
    assert "600.000000" in c.note and d.newly_known.max_receipt_lag_of_those == timedelta(minutes=10)
    assert _change(d, "/current_dataset/counts/accepted_known").kind is ChangeKind.OBSERVATION_ADDED


def test_correction_then_cancel(session):
    corr = session.compare("10:05:05", "10:05:15")
    assert {("/current_dataset/counts/corrections_known", ChangeKind.CORRECTION_KNOWN),
            ("/current_dataset/counts/corrections_applied", ChangeKind.CORRECTION_APPLIED)} <= _kinds(corr)
    assert corr.newly_known.corrections == 1
    cancel = session.compare("10:05:15", "10:05:25")
    assert {("/current_dataset/counts/cancels_known", ChangeKind.CANCEL_KNOWN),
            ("/current_dataset/counts/cancels_applied", ChangeKind.CANCEL_APPLIED)} <= _kinds(cancel)
    high = _change(cancel, "/tpo/profile/profile_high")
    assert (high.kind, high.before, high.after) == (ChangeKind.VALUE_CHANGED, "130.00", "125.00")


def test_opening_type_matures_at_0930(session):
    d = session.compare("09:29:59", "09:30")
    m = _change(d, "/maturity/opening_type")
    assert (m.kind, m.before, m.after) == (ChangeKind.COMPONENT_MATURED, "NOT_YET_DETERMINED", "WINDOW_COMPLETE")
    assert _change(d, "/maturity/initial_balance").after == "WINDOW_COMPLETE"
    assert _change(d, "/cash_opening/windows/60min/maturity").after == "WINDOW_COMPLETE"
    cands = [c for c in d.changes if c.kind is ChangeKind.CANDIDATE_AVAILABLE and c.domain == "opening_type"]
    assert [c.path for c in cands] == ["/opening_type/matched/OPEN_AUCTION_IN_RANGE",
                                       "/opening_type/matched/OPEN_TEST_DRIVE DOWN"]
    assert all(c.before is None and c.evidence_kind is EvidenceKind.CANDIDATE for c in cands)
    assert session.snapshot("09:29:59").opening_type.matched == ()


def test_day_type_matures_at_1500(session):
    d = session.compare("14:59:59", "15:00")
    for comp in ("day_type", "day_strength", "tpo_structure", "study_window_terminal"):
        c = _change(d, f"/maturity/{comp}")
        assert (c.before, c.after) == ("NOT_YET_DETERMINED", "WINDOW_COMPLETE")
    t = _change(d, "/prices/study_window_terminal_price")
    assert t.kind is ChangeKind.VALUE_AVAILABLE and t.before is None
    o = _change(d, "/day_type/classification/outcome")  # the fixture day matches no V1 policy: UNCLASSIFIED
    assert (o.kind, o.before, o.after) == (ChangeKind.CANDIDATE_AVAILABLE, None, "UNCLASSIFIED")
    assert _change(d, "/tpo_structure/structure/upper/excess_candidate").kind is ChangeKind.CANDIDATE_AVAILABLE


def test_quality_change_is_reported_when_first_knowable(session):
    assert session.snapshot("10:14").dataset_quality.known_gap_count == 0  # no future degradation
    d = session.compare("10:14", "10:15:10")
    ai = _change(d, "/dataset_quality/active_interruption")
    assert ai.kind is ChangeKind.QUALITY_CHANGED and ai.before is None
    assert ai.note == "first knowable at 2026-10-05T15:15:00.000000Z (SOURCE_DISCONNECTED observed)"
    conn = _change(d, "/current_dataset/connection_as_of")
    assert (conn.kind, conn.before, conn.after) == (ChangeKind.LIFECYCLE_CHANGED, "CONNECTED", "DISCONNECTED")
    d2 = session.compare("10:15:10", "10:20")
    gap = _change(d2, "/dataset_quality/gaps/KNOWN_GAP/2026-10-05T15:15:00.000000Z")
    assert gap.note == "first knowable at 2026-10-05T15:15:30.000000Z (interval closed at reconnect / close)"
    # the ACTIVE_INTERRUPTION already counted as a KNOWN_GAP (0Z-B); the count stays 1, the interval is now fixed
    assert not [c for c in d2.changes if c.path == "/dataset_quality/known_gap_count"]
    assert _change(d, "/dataset_quality/known_gap_count").after == 1


def test_not_available_stays_distinct_from_zero(session):
    d = session.compare("08:29", "08:31")
    vp = _change(d, "/volume_profile/total_volume")
    assert vp.kind is ChangeKind.VALUE_AVAILABLE and vp.before is None and vp.after is not None
    doc = json.loads(canonical_delta_json(d))
    entry = next(c for c in doc["changes"] if c["path"] == "/volume_profile/total_volume")
    assert entry["before"] is None
    assert "null ->" in render_delta(d)


def test_delta_is_deterministic_and_hashed(session):
    a = session.compare("09:29:59", "09:30")
    b = compare_snapshot_states(session.snapshot("09:29:59"), session.snapshot("09:30"),
                                session.newly_known(ReplayCutoff.at(ct(CUR, 9, 29, 59)), ReplayCutoff.at(ct(CUR, 9, 30))))
    ja, jb = canonical_delta_json(a), canonical_delta_json(b)
    assert ja == jb and delta_sha256(a) == delta_sha256(b)
    doc = json.loads(ja)
    assert doc[DELTA_HASH_FIELD] == delta_sha256(a) == hashlib.sha256(_dumps(encode(a)).encode()).hexdigest()
    assert doc["schema"] == DELTA_SCHEMA and not any("generated" in k for k in doc)
    assert doc["from_snapshot_sha256"] == snapshot_sha256(session.snapshot("09:29:59"))


def test_relations_are_deterministic_facts():
    doc = {"prices": {"last_known_price": "101.00"},
           "vwap": [{"anchor_kind": "US_CASH_OPEN", "study": {"vwap": "100.50"}},
                    {"anchor_kind": "SESSION_OPEN", "study": None}],
           "tpo": {"profile": {"value_area": {"low": "99.00", "high": "101.00"}, "initial_balance": None}},
           "volume_profile": {"value_area_low": None, "value_area_high": None},
           "prior_day": {"context": None}}
    r = relations(doc)
    assert r["last_price_vs_cash_vwap"] == "ABOVE" and r["last_price_vs_globex_vwap"] is None
    assert r["last_price_vs_developing_tpo_value_area"] == "INSIDE"
    assert r["last_price_vs_developing_volume_value_area"] is None and r["last_price_vs_prior_value_area"] is None


def test_compare_refuses_two_datasets(session, tmp_path):
    other = fx_mod._db(tmp_path, CUR, fx_mod._base_day(), name="other", gaps=False, rejected=False)
    s2 = MarketReplay.load(other, PROV).snapshot(at=ct(CUR, 10, 0))
    with pytest.raises(ValueError):
        compare_snapshot_states(session.snapshot("10:00"), s2)


def test_tutor_evidence_session(session):
    tutor = TutorEvidenceSession(session)
    assert tutor.state_at("10:00") is session.snapshot("10:00")
    assert canonical_delta_json(tutor.changes_between("09:29:59", "09:30")) == canonical_delta_json(
        session.compare("09:29:59", "09:30"))
    assert tutor.timeline() == session.timeline()
    assert not [n for n in dir(tutor) if not n.startswith("_") and n not in ("state_at", "changes_between", "timeline")]


# --- rendering ---------------------------------------------------------------------------------

FORBIDDEN = ("bullish", "bearish", "buy", "sell", "setup", "entry", "target", "probability", "confidence",
             "control", "strengthened", "rejected price")


def test_player_view_markers_and_no_interpretation(session):
    text = render_player_view(session.snapshot("09:47"))
    order = ["REPLAY TIME", "DATA / QUALITY", "CURRENT PRICE / RANGE", "VWAP", "VOLUME PROFILE", "TPO",
             "PRIOR DAY", "OVERNIGHT", "CASH OPEN / OPENING FACTS", "OPENING TYPE", "DAY TYPE",
             "NOT-YET-DETERMINED"]
    pos = [text.index(h) for h in order]
    assert pos == sorted(pos)
    assert "[DEVELOPING" in text and "IB [COMPLETE]" in text and "DAY TYPE (DAY_TYPE_V1)  [NOT_YET_DETERMINED]" in text
    assert "OPENING TYPE (OPENING_TYPE_V1)  [COMPLETE" in text
    assert not [w for w in FORBIDDEN if w in text.lower()] and "[--" not in text
    assert "DATA / QUALITY  [QUALITY_QUALIFIED]" in text and "PRIOR DAY  [AVAILABLE]" in text
    early = render_player_view(session.snapshot("07:00"))
    assert "cash open [NOT_YET_AVAILABLE]" in early and "OVERNIGHT  [DEVELOPING" in early
    assert not [w for w in FORBIDDEN if w in render_delta(session.compare("09:29:59", "09:30")).lower()]


def test_marker_labels():
    assert marker(Maturity.DEVELOPING, "QUALITY_QUALIFIED") == "DEVELOPING, QUALITY_QUALIFIED"
    assert marker(Maturity.WINDOW_COMPLETE, "AVAILABLE") == "COMPLETE"
    assert marker(Maturity.NOT_YET_DETERMINED, "NOT_AVAILABLE") == "NOT_YET_DETERMINED"
    assert marker(Maturity.WINDOW_COMPLETE, "NOT_AVAILABLE") == "NOT_AVAILABLE"


# --- CLI ---------------------------------------------------------------------------------------

def _run(*args):
    return subprocess.run([sys.executable, "scripts/dicks_lab_replay.py", *map(str, args)], cwd=REPO,
                          env=fx_mod._ENV, capture_output=True, text=True)


def test_player_cli_smoke(session):
    prior, cur = session.paths
    before = (prior.read_bytes(), cur.read_bytes())
    r = _run(cur, "--prior-db", prior, "--at", "09:45", "--analysis-commit", "a" * 40)
    assert r.returncode == 0, r.stderr
    assert r.stdout.startswith("REPLAY TIME") and "2026-10-05 09:45:00 CDT" in r.stdout
    c = _run(cur, "--compare", "09:29:59", "09:30", "--analysis-commit", "a" * 40)
    assert c.returncode == 0 and "[COMPONENT_MATURED] /maturity/opening_type" in c.stdout
    j = _run(cur, "--compare", "10:00", "+5m", "--json", "--analysis-commit", "a" * 40)
    assert j.returncode == 0, j.stderr
    doc = json.loads(j.stdout)
    assert doc["to_cutoff"]["market_time_cutoff_utc"] == "2026-10-05T15:05:00.000000Z"
    m = _run(cur, "--milestones", "--analysis-commit", "a" * 40)
    assert m.returncode == 0 and "IB_END 09:30" in m.stdout and "2026-10-05T14:30:00.000000Z" in m.stdout
    nxt = _run(cur, "--compare", "09:10", "next", "--analysis-commit", "a" * 40)
    assert nxt.returncode == 0 and "09:30:00 CDT" in nxt.stdout.splitlines()[0]
    assert (prior.read_bytes(), cur.read_bytes()) == before
    assert datetime.now(timezone.utc).isoformat()[:10] not in canonical_delta_json(session.compare("09:00", "09:30"))
