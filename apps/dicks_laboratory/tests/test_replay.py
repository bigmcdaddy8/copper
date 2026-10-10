"""0Z-B: MARKET_STUDY_SNAPSHOT_V1 -- market-time vs knowledge-time replay, maturity, anti-lookahead.

Fixture day Mon 2026-10-05 (CDT; 08:30 CT = 13:30Z), prior Fri 2026-10-02. A NEW row is
(market seconds after 08:30 CT, price, receipt delay in seconds). Source order = receipt order.
Special records (market time -> received):
  late print   09:55:00 @120     -> 10:05:00
  corrected    09:55:30 @101     -> 09:55:30; CORRECTION to 125 received 10:05:10
  canceled     09:56:00 @130     -> 09:56:00; CANCEL received 10:05:20
  out of order 09:56:50 @102.25  -> 09:57:05 (after 09:57:00 @102.5 received 09:57:00)
  same receipt 09:58:00 @102.75 and 09:58:00.5 @101.25 both received 09:58:01
  future mkt   10:30:00 @104     -> 10:00:00 (provider timestamp ahead of receipt)
Quality: capture 17:00 CT Sun .. 15:30 CT; disconnect 10:15:00, reconnect 10:15:30, KNOWN_GAP between;
CAPTURE_STOPPED 15:30. One rejected record received 11:00.
"""
from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo

import pytest

from dicks_laboratory import market_study_state as mss
from dicks_laboratory.anchored_vwap import VwapSourceMode, calculate_anchored_vwap
from dicks_laboratory.dataset_state import DatasetClosingSummary, DatasetLifecycleState
from dicks_laboratory.dxlink_timesales import (
    DeferredDxLinkTimeAndSale,
    DxLinkTimeAndSaleProvenance,
    DxLinkTimeAndSaleSourceRecord,
    RejectedDxLinkTimeAndSaleSourceRecord,
)
from dicks_laboratory.market_study_state import AnalysisProvenance, ComponentStatus
from dicks_laboratory.models import DatasetIdentity, DatasetKind, InstrumentIdentity, InstrumentKind, TradeObservation
from dicks_laboratory.quality import DatasetQualityEvent, DatasetQualityEvidenceType as Q
from dicks_laboratory.rejections import NormalizationRejection, RejectionSourceKind
from dicks_laboratory.replay import (
    CUTOFF_SEMANTICS,
    SNAPSHOT_HASH_FIELD,
    SNAPSHOT_SCHEMA,
    CaptureStatus,
    ConnectionState,
    MarketReplay,
    Maturity,
    ReplayCutoff,
    SnapshotTemporality,
    Visibility,
    canonical_snapshot_json,
    prepare_replay,
    render_snapshot_summary,
    snapshot_identity,
    snapshot_sha256,
    verify_snapshot_json,
)
from dicks_laboratory.sessions import AnchorKind, resolve_anchor
from dicks_laboratory.store import LaboratoryStore
from dicks_laboratory.tpo_opening import cash_open_utc

D = Decimal
CT = ZoneInfo("America/Chicago")
CUR, PRIOR = date(2026, 10, 5), date(2026, 10, 2)
WINTER = date(2026, 12, 1)  # Tue, CST: 08:30 CT = 14:30Z
REPO = Path(__file__).resolve().parents[3]
PROV = AnalysisProvenance("a" * 40, False)
_NS = UUID("0e5a0000-0000-4000-8000-0000000000fb")
_ENV = {k: v for k, v in os.environ.items() if "TASTYTRADE" not in k.upper()}


def ct(td, hh, mm, ss=0, us=0):
    return datetime(td.year, td.month, td.day, hh, mm, ss, us, tzinfo=CT).astimezone(timezone.utc)


def _base_day():
    rows = [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 99), (6, 103))]
    return [(0, 102, 0), (10, 103, 0), (100, 110, 0), (200, 103, 0), (400, 101.5, 0), (1700, 101.75, 0)] + rows[2:]


def _s(hh, mm, ss=0.0):  # seconds after 08:30 CT
    return (hh - 8) * 3600 + (mm - 30) * 60 + ss


SPECIAL = [
    (_s(9, 55), 120, 600),  # late print
    (_s(9, 55, 30), 101, 0),  # corrected later
    (_s(9, 56), 130, 0),  # canceled later
    (_s(9, 57), 102.5, 0),
    (_s(9, 56, 50), 102.25, 15),  # out of order: received 09:57:05
    (_s(9, 58), 102.75, 1),  # same receipt 09:58:01
    (_s(9, 58, 0.5), 101.25, 0.5),
    (_s(10, 30), 104, -1800),  # future market timestamp, received 10:00
]
OVERNIGHT = [(-6.5 * 3600, 100, 0), (-3.5 * 3600, 106, 0), (-3600, 101, 0)]  # 02:00, 05:00, 07:30 CT


def _db(tmp_path, td, rows, *, month=12, name, deferred=(), lifecycle_events=True, gaps=True, stopped_ct=(15, 30),
        rejected=True):
    dataset_id = uuid5(_NS, f"{td}-{name}")
    es = InstrumentIdentity(InstrumentKind.FUTURE, "CME", "ES", 2026, month)
    o = cash_open_utc(td)
    start = resolve_anchor(AnchorKind.SESSION_OPEN, td).anchor_timestamp_utc
    stop = ct(td, *stopped_ct)
    ordered = sorted(((o + timedelta(seconds=s), D(str(p)), o + timedelta(seconds=s + d)) for s, p, d in rows),
                     key=lambda r: (r[2], r[0]))
    trades, prov = [], []
    for i, (mts, price, received) in enumerate(ordered):
        t = TradeObservation(uuid5(dataset_id, f"t{i}"), dataset_id, i + 1, es, mts, price, D(1))
        trades.append(t)
        prov.append(DxLinkTimeAndSaleProvenance(t.observation_id, f"evt:{i + 1}", i + 1, 1000 + i, i + 1, i + 1,
                                                received, event_classification="NEW"))
    path = tmp_path / f"rp-{name}.sqlite3"
    store = LaboratoryStore(path)
    store.save_dataset(DatasetIdentity(dataset_id, DatasetKind.HISTORICAL_IMPORT, f"rp-{name}",
                                       source_locator="TASTYTRADE_DXLINK:/ESZ26:XCME:TimeAndSale",
                                       capture_started_at=start, capture_ended_at=stop))
    store.save_dataset_trading_context(dataset_id, td, es)
    store.save_trade_observations(tuple(trades))
    store.save_dxlink_time_and_sale_provenance(tuple(prov))
    by_price = {(t.event_timestamp, t.price): (p.source_index, p.source_order) for t, p in zip(trades, prov)}
    n = len(trades)
    store.save_deferred_dxlink_time_and_sales(tuple(
        _deferred(dataset_id, n + 1 + j, by_price[(o + timedelta(seconds=s), D(str(p)))][0], cls, o + timedelta(
            seconds=s), new_price, o + timedelta(seconds=recv)) for j, (s, p, cls, new_price, recv) in enumerate(deferred)))
    events = []
    if lifecycle_events:
        events += [DatasetQualityEvent(uuid5(dataset_id, "cs"), dataset_id, Q.CAPTURE_STARTED, "capture_started",
                                       observed_at=start),
                   DatasetQualityEvent(uuid5(dataset_id, "sc"), dataset_id, Q.SOURCE_CONNECTED, "source_connected",
                                       observed_at=start + timedelta(seconds=1)),
                   DatasetQualityEvent(uuid5(dataset_id, "st"), dataset_id, Q.CAPTURE_STOPPED, "capture_stopped",
                                       observed_at=stop)]
    if gaps:
        d0, d1 = ct(td, 10, 15), ct(td, 10, 15, 30)
        events += [DatasetQualityEvent(uuid5(dataset_id, "sd"), dataset_id, Q.SOURCE_DISCONNECTED, "source_disconnected",
                                       observed_at=d0),
                   DatasetQualityEvent(uuid5(dataset_id, "sr"), dataset_id, Q.SOURCE_RECONNECTED, "source_reconnected",
                                       observed_at=d1),
                   DatasetQualityEvent(uuid5(dataset_id, "kg"), dataset_id, Q.KNOWN_GAP, "disconnect_to_reconnect",
                                       interval_start=d0, interval_end=d1)]
    store.save_quality_events(tuple(events))
    if rejected:
        rid = uuid5(dataset_id, "rej")
        store.save_rejections((NormalizationRejection(rid, dataset_id, RejectionSourceKind.DXLINK_TIME_AND_SALE,
                                                      "rej:1", 9000, "INVALID_PRICE"),))
        store.save_rejected_dxlink_time_and_sale_source_records((RejectedDxLinkTimeAndSaleSourceRecord(
            rid, dataset_id, 9000, _record("rej:1", "NEW", 1, ct(td, 11, 0), D("0"), ct(td, 11, 0))),))
    store.save_dataset_closing_summary(DatasetClosingSummary(
        dataset_id, n, len(deferred), 1 if rejected else 0, 1 if gaps else 0, 0, 1, n, stop,
        "phase-0v-serious-collection-v1", "c" * 40, submitted_events=n, persisted_events=n))
    store.set_dataset_lifecycle_state(dataset_id, DatasetLifecycleState.FINALIZED)
    store.close()
    return path


def _record(ref, cls, index, event_time, price, received):
    return DxLinkTimeAndSaleSourceRecord(
        ref, "/ESZ26:XCME", int(event_time.timestamp() * 1000), cls, index, index, index, 0, "X", str(price), "1",
        None, None, None, None, None, None, None, True, received)


def _deferred(dataset_id, order, index, cls, event_time, price, received):
    return DeferredDxLinkTimeAndSale(uuid5(dataset_id, f"d{order}"), dataset_id, order,
                                     _record(f"evt:{order}", cls, index, event_time, price or "102", received),
                                     f"DXLINK_{cls}")


CORRECTION = (_s(9, 55, 30), 101, "CORRECTION", 125, _s(10, 5, 10))
CANCEL = (_s(9, 56), 130, "CANCEL", None, _s(10, 5, 20))


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("replay")
    prior = _db(tmp, PRIOR, [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))], name="prior",
                gaps=False, rejected=False, stopped_ct=(16, 0))
    cur = _db(tmp, CUR, OVERNIGHT + _base_day() + SPECIAL, name="cur", deferred=(CORRECTION, CANCEL))
    return SimpleFx(tmp, prior, cur, MarketReplay.load(cur, PROV, prior))


@dataclasses.dataclass
class SimpleFx:
    tmp: Path
    prior: Path
    cur: Path
    replay: MarketReplay

    def at(self, hh, mm, ss=0, td=CUR):
        return self.replay.snapshot(at=ct(td, hh, mm, ss))


def _vis(fx, cutoff, price, mts=None):
    by = {t.observation_id: t for t in fx.replay.current.canonical_trades}
    orders = [p.source_order for p in fx.replay.current.provenance if by[p.observation_id].price == D(str(price))
              and (mts is None or by[p.observation_id].event_timestamp == mts)]
    vis = fx.replay.visibility(cutoff, source_orders=orders)
    assert len(vis) == 1, vis
    return vis[0]


def _prices(snapshot):
    return {lv.price for lv in snapshot.tpo.profile.levels if lv.tpo_count} if snapshot.tpo.profile else set()


def _tape_prices(fx, cutoff):
    from dicks_laboratory.replay import as_of_evidence
    return sorted(t.price for t in as_of_evidence(fx.replay.current, cutoff).scoped)


# --- cutoff model --------------------------------------------------------------------------------

def test_cutoff_keeps_two_clocks_and_strict_boundaries():
    m, k = ct(CUR, 10, 0), ct(CUR, 10, 5)
    c = ReplayCutoff(m, k)
    assert (c.market_time_cutoff_utc, c.knowledge_time_cutoff_utc, c.clock) == (m, k, m)
    assert ReplayCutoff.at(m) == ReplayCutoff(m, m) and ReplayCutoff.at(m, 7).knowledge_source_order_cutoff == 7
    assert c.knows(k - timedelta(microseconds=1), 1) and not c.knows(k, 1) and not c.knows(None, 1)
    assert c.in_market(m - timedelta(microseconds=1)) and not c.in_market(m)
    assert not ReplayCutoff(m, k, 5).knows(m, 6) and ReplayCutoff(m, k, 5).knows(m, 5)
    local = datetime(2026, 10, 5, 10, 0, tzinfo=CT)
    assert ReplayCutoff.at(local).market_time_cutoff_utc == ct(CUR, 10, 0)
    with pytest.raises(ValueError):
        ReplayCutoff.at(datetime(2026, 10, 5, 10, 0))
    assert any(s.startswith("KNOWLEDGE") for s in CUTOFF_SEMANTICS) and any(s.startswith("MARKET") for s in CUTOFF_SEMANTICS)


# --- feed knowledge vs market time ---------------------------------------------------------------

def test_late_print_absent_before_receipt_then_present(fx):
    late_mts = ct(CUR, 9, 55)
    at10, at1010 = ReplayCutoff.at(ct(CUR, 10, 0)), ReplayCutoff.at(ct(CUR, 10, 10))
    assert _vis(fx, at10, 120).visibility is Visibility.NOT_YET_RECEIVED
    v = _vis(fx, at1010, 120)
    assert v.visibility is Visibility.VISIBLE and v.market_timestamp_utc == late_mts
    assert v.receipt_lag == timedelta(minutes=10)
    default = fx.replay.visibility(at10, late_print_limit=1)  # cutoff-relative late prints come first
    assert any(x.market_timestamp_utc == late_mts and x.visibility is Visibility.NOT_YET_RECEIVED for x in default)
    assert D("120") not in _tape_prices(fx, at10) and D("120") in _tape_prices(fx, at1010)
    # 10:00: the 09:56 trade @130 is still visible (its CANCEL arrives 10:05:20); 10:10: cancel + correction applied
    assert fx.at(10, 0).tpo.profile.profile_high == D("130") and fx.at(10, 10).tpo.profile.profile_high == D("125")


def test_correction_is_not_applied_backward(fx):
    original = ct(CUR, 9, 55, 30)
    at10, at1010 = ReplayCutoff.at(ct(CUR, 10, 0)), ReplayCutoff.at(ct(CUR, 10, 10))
    assert _vis(fx, at10, 101, original).visibility is Visibility.VISIBLE
    assert D("101") in _tape_prices(fx, at10) and D("125") not in _tape_prices(fx, at10)
    assert _vis(fx, at1010, 101, original).visibility is Visibility.VISIBLE_CORRECTED
    assert D("125") in _tape_prices(fx, at1010)
    s10, s1010 = fx.at(10, 0), fx.at(10, 10)
    assert (s10.current_dataset.counts.corrections_known, s10.current_dataset.counts.corrections_applied) == (0, 0)
    assert (s1010.current_dataset.counts.corrections_known, s1010.current_dataset.counts.corrections_applied) == (1, 1)
    corr = [v for v in fx.replay.visibility(at1010) if v.record == "CORRECTION"]
    assert corr[0].visibility is Visibility.APPLIED and corr[0].receipt_lag == timedelta(minutes=9, seconds=40)


def test_cancel_is_not_applied_backward(fx):
    at10, at1010 = ReplayCutoff.at(ct(CUR, 10, 0)), ReplayCutoff.at(ct(CUR, 10, 10))
    assert _vis(fx, at10, 130).visibility is Visibility.VISIBLE
    assert D("130") in _tape_prices(fx, at10)
    assert _vis(fx, at1010, 130).visibility is Visibility.CANCELED_AS_OF
    assert D("130") not in _tape_prices(fx, at1010)
    assert fx.at(10, 10).current_dataset.counts.cancels_applied == 1


def test_out_of_order_market_timestamp(fx):
    rec = ct(CUR, 9, 56, 50)
    before, after = ReplayCutoff.at(ct(CUR, 9, 57, 2)), ReplayCutoff.at(ct(CUR, 9, 57, 10))
    assert _vis(fx, before, 102.25).visibility is Visibility.NOT_YET_RECEIVED
    assert _vis(fx, before, 102.5).visibility is Visibility.VISIBLE  # later market time, received earlier
    assert _vis(fx, after, 102.25).visibility is Visibility.VISIBLE
    from dicks_laboratory.replay import as_of_evidence
    tape = as_of_evidence(fx.replay.current, after).scoped
    i, j = [t.event_timestamp for t in tape].index(rec), [t.price for t in tape].index(D("102.5"))
    assert i < j  # effective order is market order


def test_same_receipt_time_is_split_only_by_source_order(fx):
    t = ct(CUR, 9, 58, 2)
    both = fx.replay.visibility(ReplayCutoff.at(t), source_orders=None, late_print_limit=0)
    by = {x.price: x for x in fx.replay.current.canonical_trades if x.price in (D("102.75"), D("101.25"))}
    orders = sorted(p.source_order for p in fx.replay.current.provenance if p.observation_id in
                    {x.observation_id for x in by.values()})
    assert len(orders) == 2 and both is not None
    first, second = orders
    v = fx.replay.visibility(ReplayCutoff(t, t, first), source_orders=orders)
    assert [x.visibility for x in v] == [Visibility.VISIBLE, Visibility.BEYOND_SOURCE_ORDER_CUTOFF]
    assert [x.visibility for x in fx.replay.visibility(ReplayCutoff.at(t), source_orders=orders)] == [
        Visibility.VISIBLE, Visibility.VISIBLE]
    steps = fx.replay.source_order_steps(t, t, (first - 1, first, second))
    hashes = [snapshot_sha256(s) for s in steps]
    assert len(set(hashes)) == 3
    assert [s.current_dataset.counts.accepted_known for s in steps] == [first - 1, first, second]


def test_future_market_timestamp_is_known_but_excluded(fx):
    at1015 = ReplayCutoff.at(ct(CUR, 10, 15))
    v = _vis(fx, at1015, 104)
    assert v.visibility is Visibility.MARKET_TIME_AT_OR_AFTER_CUTOFF and v.received_at_utc == ct(CUR, 10, 0)
    s = fx.at(10, 15)
    assert s.current_dataset.counts.known_records_with_market_time_at_or_after_cutoff >= 1
    assert D("104") not in _tape_prices(fx, at1015)
    assert _vis(fx, ReplayCutoff.at(ct(CUR, 10, 31)), 104).visibility is Visibility.VISIBLE


def test_knowledge_cutoff_alone_controls_receipt(fx):
    """Market cutoff 10:10 with knowledge 10:00: the late print and correction stay unknown."""
    c = ReplayCutoff(ct(CUR, 10, 10), ct(CUR, 10, 0))
    assert D("120") not in _tape_prices(fx, c) and D("125") not in _tape_prices(fx, c)
    assert fx.replay.snapshot(cutoff=c).cutoff.clock == ct(CUR, 10, 0)


# --- no final metadata / quality leakage ---------------------------------------------------------

def test_no_final_lifecycle_counts_or_summary_before_the_stop(fx):
    s = fx.at(10, 0)
    d = s.current_dataset
    assert (d.capture_status, d.lifecycle_as_of, d.capture_ended_at) == (CaptureStatus.RUNNING, "OPEN_AS_OF", None)
    assert (d.closing_summary, d.closing_summary_maturity, d.closing_accounting_difference) == (
        None, Maturity.NOT_YET_DETERMINED, None)
    assert "CAPTURE_STOPPED" not in [x for x, _ in d.lifecycle_evidence_known]
    total = len(fx.replay.current.canonical_trades)
    assert d.counts.accepted_known < total and d.counts.rejected_known == 0
    doc = canonical_snapshot_json(s)
    current = json.dumps(json.loads(doc)["current_dataset"])
    assert '"FINALIZED"' not in current and '"lifecycle_as_of": "OPEN_AS_OF"' in current
    assert "database_sha256" not in doc.split('"prior_day"')[0]  # the final file checksum is never as-of evidence
    end = fx.at(16, 0).current_dataset
    assert (end.capture_status, end.lifecycle_as_of, end.closing_summary_maturity) == (
        CaptureStatus.STOPPED, "FINALIZED", Maturity.WINDOW_COMPLETE)
    assert end.closing_summary.accepted_trade_count == total and end.closing_accounting_difference == 0
    assert end.counts.rejected_known == 1 and end.capture_ended_at == ct(CUR, 15, 30)


def test_future_gap_never_appears_early_and_interruption_is_honest(fx):
    q10 = fx.at(10, 0).dataset_quality
    assert (q10.known_gap_count, q10.active_interruption, q10.gaps) == (0, None, ())
    assert fx.at(10, 0).current_dataset.connection_as_of is ConnectionState.CONNECTED
    mid = fx.at(10, 15, 10)
    assert mid.current_dataset.connection_as_of is ConnectionState.DISCONNECTED
    assert mid.dataset_quality.active_interruption.start_utc == ct(CUR, 10, 15)
    assert mid.dataset_quality.active_interruption.end_utc == ct(CUR, 10, 15, 10)
    assert mid.dataset_quality.gaps == () and mid.dataset_quality.status is ComponentStatus.QUALITY_QUALIFIED
    after = fx.at(10, 20)
    assert after.dataset_quality.active_interruption is None and after.dataset_quality.known_gap_count == 1
    assert (after.dataset_quality.gaps[0].start_utc, after.dataset_quality.gaps[0].end_utc) == (
        ct(CUR, 10, 15), ct(CUR, 10, 15, 30))
    assert after.current_dataset.connection_as_of is ConnectionState.CONNECTED
    assert fx.at(9, 45).tpo.status is ComponentStatus.AVAILABLE  # the 10:15 gap does not qualify 09:45


# --- maturity ------------------------------------------------------------------------------------

def _m(s):
    return {e.component: e.maturity for e in s.maturity}


@pytest.mark.parametrize("td", [CUR, WINTER])
def test_clock_boundaries_cdt_and_cst(tmp_path, td):
    prior_td = td - timedelta(days=3 if td.weekday() == 0 else 1)
    prior = _db(tmp_path, prior_td, [(1800 * i + m, p, 0) for i in range(13) for m, p in ((5, 90), (6, 110))],
                name="p", gaps=False, rejected=False, stopped_ct=(16, 0))
    cur = _db(tmp_path, td, OVERNIGHT + _base_day(), name="c", gaps=False, rejected=False, stopped_ct=(16, 0))
    rp = MarketReplay.load(cur, PROV, prior)
    prev = resolve_anchor(AnchorKind.SESSION_OPEN, td).anchor_timestamp_utc
    assert prev == ct(td - timedelta(days=1), 17, 0)  # Sunday 17:00 CT opens Monday's session

    def m(t):
        return _m(rp.snapshot(at=t))

    assert m(prev - timedelta(seconds=1))["overnight"] is Maturity.NOT_YET_AVAILABLE
    assert m(prev - timedelta(seconds=1))["vwap SESSION_OPEN"] is Maturity.NOT_YET_AVAILABLE
    assert m(prev + timedelta(seconds=1))["overnight"] is Maturity.DEVELOPING
    assert m(ct(td, 8, 29, 59))["overnight"] is Maturity.DEVELOPING
    assert m(ct(td, 8, 30))["overnight"] is Maturity.WINDOW_COMPLETE
    assert m(ct(td, 8, 30))["cash_open"] is Maturity.NOT_YET_AVAILABLE  # strict: the 08:30:00.000 print not yet in
    assert m(ct(td, 8, 30, 1))["cash_open"] is Maturity.WINDOW_COMPLETE
    assert m(ct(td, 9, 29, 59))["initial_balance"] is Maturity.DEVELOPING
    assert m(ct(td, 9, 30))["initial_balance"] is Maturity.WINDOW_COMPLETE
    assert m(ct(td, 9, 29, 59))["opening_type"] is Maturity.NOT_YET_DETERMINED
    assert m(ct(td, 9, 30))["opening_type"] is Maturity.WINDOW_COMPLETE
    assert m(ct(td, 14, 59, 59))["day_type"] is Maturity.NOT_YET_DETERMINED
    assert m(ct(td, 15, 0))["day_type"] is Maturity.WINDOW_COMPLETE
    assert m(ct(td, 15, 59, 59))["vwap US_CASH_OPEN"] is Maturity.DEVELOPING
    assert m(ct(td, 16, 0))["vwap US_CASH_OPEN"] is Maturity.WINDOW_COMPLETE
    windows = {w.minutes: w for w in rp.snapshot(at=ct(td, 8, 34, 59)).cash_opening.windows}
    assert windows[5].maturity is Maturity.NOT_YET_DETERMINED and windows[5].facts is None
    for minutes, (hh, mm) in ((5, (8, 35)), (15, (8, 45)), (30, (9, 0)), (60, (9, 30))):
        w = {x.minutes: x for x in rp.snapshot(at=ct(td, hh, mm)).cash_opening.windows}
        assert w[minutes].maturity is Maturity.WINDOW_COMPLETE and w[minutes].facts is not None
        assert all(w[x].maturity is Maturity.NOT_YET_DETERMINED for x in w if x > minutes)


def test_tpo_has_no_future_periods_and_ib_matures_at_0930(fx):
    s = fx.at(10, 0)
    assert s.tpo.periods_reached == "ABC" and s.tpo.current_period is None
    s2 = fx.at(10, 10)
    assert s2.tpo.periods_reached == "ABCD" and s2.tpo.current_period == "D"
    assert all(p.start_utc < ct(CUR, 10, 10) for p in s2.tpo.profile.periods)
    assert fx.at(9, 10).tpo.initial_balance_maturity is Maturity.DEVELOPING
    final = fx.at(18, 0).tpo.profile.initial_balance
    ib = fx.at(9, 30).tpo.profile.initial_balance
    assert (ib.high, ib.low, ib.period_labels) == (final.high, final.low, final.period_labels)
    assert fx.at(8, 30).tpo.profile is None and fx.at(8, 30).tpo.periods_reached == ""


def test_final_study_components_are_not_yet_determined_before_1500(fx):
    s = fx.at(14, 59, 59)
    assert s.day_type.classification is None and s.day_type.reasons[0].startswith("NOT_YET_DETERMINED")
    assert s.day_strength.strength is None and s.tpo_structure.structure is None
    assert s.prices.study_window_terminal_price is None
    assert s.prices.study_window_terminal_maturity is Maturity.NOT_YET_DETERMINED
    assert s.prices.last_known_price is not None and s.prices.last_known_utc < ct(CUR, 14, 59, 59)
    doc = json.loads(canonical_snapshot_json(s))
    assert doc["day_type"]["classification"] is None and doc["tpo_structure"]["structure"] is None
    assert doc["day_strength"]["strength"] is None
    s15 = fx.at(15, 0)
    assert s15.day_type.classification is not None and s15.prices.study_window_terminal_price is not None


def test_opening_type_not_determined_before_0930_then_frozen_v1(fx):
    s = fx.at(9, 29, 59)
    assert s.opening_type.classification is None and s.opening_type.matched == ()
    assert s.opening_type.reasons == ("NOT_YET_DETERMINED: OPENING_TYPE_V1 is evaluated at 09:30 CT",)
    assert s.cash_opening.facts is None and s.cash_opening.path_facts is None
    s930, final = fx.at(9, 30), fx.at(18, 0)
    assert s930.opening_type.policy_source_matches_freeze

    def core(c):
        return [(x.type, x.direction, x.result, tuple((k.code, k.status) for k in x.conditions)) for x in c.candidates]

    assert core(s930.opening_type.classification) == core(final.opening_type.classification)
    assert s930.cash_opening.fields_developing_until_study_window_end
    assert final.cash_opening.fields_developing_until_study_window_end == ()


def test_cash_open_location_known_at_the_print(fx):
    s = fx.at(8, 31)
    assert s.cash_opening.cash_open.price == D("102") and s.cash_opening.range_location.value == "INSIDE_PRIOR_RANGE"
    assert s.cash_opening.gap_ticks is not None and s.prior_day.status is ComponentStatus.AVAILABLE
    assert fx.at(8, 29).cash_opening.cash_open is None and fx.at(8, 29).cash_opening.range_location is None


def test_overnight_develops_only_from_known_trades(fx):
    s3 = fx.at(3, 0)
    d = s3.overnight.developing
    assert (d.high, d.low, d.last_price) == (D("100"), D("100"), D("100")) and s3.overnight.session is None
    d6 = fx.at(6, 0).overnight.developing
    assert (d6.high, d6.low, d6.last_price) == (D("106"), D("100"), D("106"))
    s830 = fx.at(8, 30)
    assert s830.overnight.developing is None and s830.overnight.session.high == D("106")
    final = fx.at(18, 0).overnight.session
    # facts are final at 08:30; quality still says the dataset is OPEN (not FINALIZED) as of 08:30
    assert dataclasses.replace(s830.overnight.session, quality=None) == dataclasses.replace(final, quality=None)
    assert s830.overnight.session.quality.reasons == ("lifecycle OPEN (not FINALIZED)",)


def test_developing_vwap_uses_only_trades_before_the_cutoff(fx):
    s = fx.at(6, 0)
    glob, cash = s.vwap
    assert glob.maturity is Maturity.DEVELOPING and cash.maturity is Maturity.NOT_YET_AVAILABLE
    assert glob.study.vwap == D("103") and glob.study.included_trade_count == 2  # (100 + 106) / 2
    s10 = fx.at(10, 0)
    from dicks_laboratory.replay import as_of_evidence
    scoped = as_of_evidence(fx.replay.current, ReplayCutoff.at(ct(CUR, 10, 0))).scoped
    expected = calculate_anchored_vwap(scoped, resolve_anchor(AnchorKind.US_CASH_OPEN, CUR),
                                       VwapSourceMode.EFFECTIVE_TAPE)
    assert s10.vwap[1].study.vwap == expected.vwap and s10.vwap[1].maturity is Maturity.DEVELOPING


def test_developing_volume_profile_and_tpo_value_area(fx):
    s = fx.at(10, 0)
    assert s.volume_profile.poc is not None and s.volume_profile.total_volume < fx.at(18, 0).volume_profile.total_volume
    assert {e.component: e.maturity for e in s.maturity}["volume_profile"] is Maturity.DEVELOPING
    assert s.tpo.profile.value_area.low <= s.tpo.profile.poc <= s.tpo.profile.value_area.high


def test_prior_context_is_known_only_after_the_prior_closed(fx):
    early = fx.replay.snapshot(at=ct(PRIOR, 15, 0))
    assert early.prior_day.status is ComponentStatus.NOT_AVAILABLE and early.prior_day.context is None
    assert early.prior_day.reasons[0].startswith("NOT_YET_AVAILABLE")
    assert fx.at(7, 0).prior_day.context.profile_high == D("110")


# --- anti-lookahead mutation proofs --------------------------------------------------------------

def _copy(fx, name):
    dst = fx.tmp / f"mut-{name}.sqlite3"
    shutil.copyfile(fx.cur, dst)
    return dst


def _json(path, hh, mm):
    return canonical_snapshot_json(MarketReplay.load(path, PROV, None).snapshot(at=ct(CUR, hh, mm)))


@pytest.mark.parametrize("kind", ["trade", "correction", "quality"])
def test_mutating_evidence_after_the_cutoff_cannot_change_earlier_snapshots(fx, kind):
    base10, base15 = _json(fx.cur, 10, 0), _json(fx.cur, 15, 0)
    mutated = _copy(fx, kind)
    if kind == "trade":  # a NEW record received at 14:00:05 CT
        con = sqlite3.connect(mutated)
        n = con.execute("UPDATE trade_observations SET price = '107' WHERE event_timestamp LIKE '2026-10-05T19:00:05%'"
                        ).rowcount
        con.commit()
        con.close()
        assert n == 1
    else:
        store = LaboratoryStore(mutated)
        did = store.list_dataset_ids()[0]
        if kind == "correction":  # a CORRECTION received 14:00:30 CT for the 09:57:00 trade
            prov = {p.observation_id: p for p in store.load_dxlink_time_and_sale_provenance(did)}
            trade = next(t for t in store.load_trade_observations(did) if t.price == D("102.5"))
            store.save_deferred_dxlink_time_and_sales((_deferred(
                did, 99999, prov[trade.observation_id].source_index, "CORRECTION", trade.event_timestamp, 108,
                ct(CUR, 14, 0, 30)),))
        else:  # a disconnect at 14:00 with its gap, written at the reconnect
            store.save_quality_events((
                DatasetQualityEvent(uuid5(did, "m1"), did, Q.SOURCE_DISCONNECTED, "x", observed_at=ct(CUR, 14, 0)),
                DatasetQualityEvent(uuid5(did, "m2"), did, Q.SOURCE_RECONNECTED, "x", observed_at=ct(CUR, 14, 0, 9)),
                DatasetQualityEvent(uuid5(did, "m3"), did, Q.KNOWN_GAP, "x", interval_start=ct(CUR, 14, 0),
                                    interval_end=ct(CUR, 14, 0, 9))))
        store.close()
    assert _json(mutated, 10, 0) == base10  # byte-identical: same hash
    assert _json(mutated, 15, 0) != base15


# --- final convergence ---------------------------------------------------------------------------

def test_terminal_snapshot_converges_to_market_study_state_v1(fx):
    s = fx.at(18, 0)
    final = mss.build_market_study_state(mss.load_study_inputs(fx.cur), mss.load_study_inputs(fx.prior), PROV)
    assert s.contract == final.contract
    assert s.volume_profile == final.volume_profile
    assert s.tpo.profile == final.tpo.profile and s.tpo.status == final.tpo.status
    assert s.tpo_structure == final.tpo_structure
    assert s.day_type == final.day_type and s.day_strength == final.day_strength
    assert s.prior_day == final.prior_day
    assert (s.overnight.session, s.overnight.context) == (final.overnight.session, final.overnight.context)
    assert (s.cash_opening.facts, s.cash_opening.path_facts) == (final.cash_opening.facts, final.cash_opening.path_facts)
    assert s.opening_type == final.opening_type
    assert [v.study for v in s.vwap] == list(final.vwap.studies)
    assert s.prices.study_window_terminal_price == final.day_type.classification.facts.terminal.price
    d, f = s.current_dataset, final.current_dataset
    assert (d.lifecycle_as_of, d.capture_started_at, d.capture_ended_at) == (
        f.lifecycle_state, f.capture_started_at, f.capture_ended_at)
    assert (d.closing_summary.accepted_trade_count, d.closing_summary.rejected_record_count,
            d.closing_summary.deferred_event_count, d.closing_summary.submitted_events,
            d.closing_accounting_difference, d.collector_git_commit) == (
        f.accepted_trade_count, f.rejected_record_count, f.deferred_event_count, f.submitted_events,
        f.accounting_difference, f.collector_git_commit)
    assert (d.counts.accepted_known, d.counts.corrections_applied, d.counts.cancels_applied) == (
        f.retained_trade_count, f.applied_correction_count, f.applied_cancel_count)
    q, fq = s.dataset_quality, final.dataset_quality
    assert (q.completeness, q.known_gap_count, q.suspected_gap_count, q.known_gap_duration, q.gaps) == (
        fq.completeness, fq.known_gap_count, fq.suspected_gap_count, fq.known_gap_duration, fq.gaps)
    assert s.policy_registry[:-1] == final.policy_registry
    assert s.policy_registry[-1].policy_id == SNAPSHOT_SCHEMA


# --- canonical snapshot --------------------------------------------------------------------------

def test_snapshot_is_canonical_hashed_and_attributable(fx):
    a, b = fx.at(10, 0), fx.replay.snapshot(at=ct(CUR, 10, 0))
    ja, jb = canonical_snapshot_json(a), canonical_snapshot_json(b)
    assert ja == jb and verify_snapshot_json(ja)
    doc = json.loads(ja)
    assert doc[SNAPSHOT_HASH_FIELD] == snapshot_sha256(a) and SNAPSHOT_HASH_FIELD not in mss._dumps(
        mss.encode(a))
    assert doc["schema"] == "MARKET_STUDY_SNAPSHOT_V1" and doc["state_temporality"] == "AS_OF"
    assert doc["cutoff"] == {"knowledge_source_order_cutoff": None,
                             "knowledge_time_cutoff_utc": "2026-10-05T15:00:00.000000Z",
                             "market_time_cutoff_utc": "2026-10-05T15:00:00.000000Z"}
    assert any(e["policy_id"] == "OPENING_TYPE_V1" for e in doc["policy_registry"])
    assert not any("generated" in k for k in doc)
    other = fx.replay.snapshot(cutoff=ReplayCutoff(ct(CUR, 10, 0), ct(CUR, 10, 0, 1)))
    assert snapshot_sha256(other) != snapshot_sha256(a)  # knowledge cutoff is part of the identity
    ident = snapshot_identity(a)
    assert (ident.dataset_id, ident.schema, ident.analysis_git_commit, ident.snapshot_sha256) == (
        a.current_dataset.dataset_id, SNAPSHOT_SCHEMA, "a" * 40, snapshot_sha256(a))
    assert a.state_temporality is SnapshotTemporality.AS_OF


def test_snapshot_is_immutable(fx):
    s = fx.at(10, 0)
    with pytest.raises(FrozenInstanceError):
        s.cutoff = None
    with pytest.raises(FrozenInstanceError):
        s.cutoff.market_time_cutoff_utc = ct(CUR, 11, 0)


def test_replay_is_read_only(fx):
    before = fx.cur.read_bytes()
    prepare_replay(fx.cur)
    fx.at(12, 0)
    assert fx.cur.read_bytes() == before and not list(fx.tmp.glob("rp-cur.sqlite3-*"))


FORBIDDEN = ("bullish", "bearish", "buy", "sell", "setup", "entry", "target", "probability", "confidence")


def test_summary_is_evidence_only(fx):
    text = render_snapshot_summary(fx.at(10, 0))
    assert text.startswith("MARKET STUDY SNAPSHOT (AS OF)") and "NOT_YET_DETERMINED" in text
    assert "10:00:00 CDT" in text and not [w for w in FORBIDDEN if w in text.lower()]


# --- CLI -----------------------------------------------------------------------------------------

def _run(*args):
    return subprocess.run([sys.executable, "scripts/dicks_lab_replay.py", *map(str, args)], cwd=REPO, env=_ENV,
                          capture_output=True, text=True)


def test_replay_cli_smoke(fx, tmp_path):
    before = fx.cur.read_bytes()
    r = _run(fx.cur, "--prior-database", fx.prior, "--at", "2026-10-05T10:00:00-05:00", "--json",
             "--analysis-commit", "a" * 40)
    assert r.returncode == 0, r.stderr
    doc = r.stdout.rstrip("\n")
    assert verify_snapshot_json(doc)
    explicit = MarketReplay(fx.replay.current, fx.replay.prior, AnalysisProvenance("a" * 40, None))
    assert doc == canonical_snapshot_json(explicit.snapshot(at=ct(CUR, 10, 0)))
    many = _run(fx.cur, "--at", "2026-10-05T08:35:00-05:00", "--at", "2026-10-05T15:00:00-05:00",
                "--analysis-commit", "a" * 40, "--out-dir", tmp_path / "snaps", "--view", "summary")
    assert many.returncode == 0, many.stderr
    assert many.stdout.count("MARKET STUDY SNAPSHOT (AS OF)") == 2
    assert len(list((tmp_path / "snaps").glob("*.json"))) == 2
    diag = _run(fx.cur, "--at", "2026-10-05T10:10:00-05:00", "--diagnose", "--analysis-commit", "a" * 40)
    assert diag.returncode == 0 and "CANCELED_AS_OF" in diag.stdout and "VISIBLE_CORRECTED" in diag.stdout
    cursor = _run(fx.cur, "--at", "2026-10-05T10:00:00-05:00", "--knowledge-at", "2026-10-05T09:59:00-05:00",
                  "--source-order", "40", "--json", "--analysis-commit", "a" * 40)
    assert cursor.returncode == 0 and json.loads(cursor.stdout)["cutoff"]["knowledge_source_order_cutoff"] == 40
    bad = _run(fx.cur, "--at", "2026-10-05T10:00:00", "--analysis-commit", "a" * 40)
    assert bad.returncode != 0  # naive times are refused
    assert fx.cur.read_bytes() == before
