"""Replay evidence player and snapshot delta interface (0Z-C).

Consumes the accepted replay engine (MARKET_STUDY_SNAPSHOT_V1); it never redefines a cutoff,
the knowledge / market semantics, correction-cancel handling, quality timing or maturity.

- `ReplaySession`: one prepared trading date (prior optional); seek to explicit times
  (ISO with offset, or "HH:MM[:SS]" America/Chicago on the session), structural milestones,
  +1m / +5m / next-milestone stepping; snapshots are computed, never played in real time.
- `compare_snapshot_states(before, after)` -> `MarketStudyDelta`: a typed, ordered list of
  deterministic differences (`ChangeKind`), each with path, before / after (canonical
  values), evidence kind, status and maturity after. No interpretation, no prose engine.
- `TutorEvidenceSession`: `state_at(T)` / `changes_between(T1, T2)` for a future tutor.
- `render_player_view` / `render_delta`: concise text with explicit maturity markers.

Canonical delta JSON uses the MARKET_STUDY_STATE_V1 encoding; `market_study_delta_sha256`
is computed over the payload without the hash field. No current-time field anywhere.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from dicks_laboratory import market_study_state as mss
from dicks_laboratory.market_study_state import AnalysisProvenance, EvidenceKind
from dicks_laboratory.replay import (
    MarketReplay,
    MarketStudySnapshot,
    Maturity,
    ReplayCutoff,
    snapshot_sha256,
)
from dicks_laboratory.sessions import AnchorKind, resolve_anchor

DELTA_SCHEMA = "MARKET_STUDY_DELTA_V1"
DELTA_HASH_FIELD = "market_study_delta_sha256"
CT = ZoneInfo("America/Chicago")
_HHMM = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?$")
_STEP = re.compile(r"^\+(\d+)([ms])$")


class ChangeKind(StrEnum):
    OBSERVATION_ADDED = "OBSERVATION_ADDED"  # more accepted source records known
    LATE_OBSERVATION_ADDED = "LATE_OBSERVATION_ADDED"  # newly known records with market time before the earlier cutoff
    VALUE_AVAILABLE = "VALUE_AVAILABLE"  # null -> value
    VALUE_CHANGED = "VALUE_CHANGED"
    VALUE_WITHDRAWN = "VALUE_WITHDRAWN"  # value -> null
    RELATION_CHANGED = "RELATION_CHANGED"  # e.g. last price BELOW -> ABOVE the cash VWAP
    COMPONENT_MATURED = "COMPONENT_MATURED"  # maturity changed
    QUALITY_CHANGED = "QUALITY_CHANGED"
    LIFECYCLE_CHANGED = "LIFECYCLE_CHANGED"
    CANDIDATE_AVAILABLE = "CANDIDATE_AVAILABLE"  # a candidate label became determined
    CANDIDATE_REMOVED = "CANDIDATE_REMOVED"
    CORRECTION_KNOWN = "CORRECTION_KNOWN"
    CORRECTION_APPLIED = "CORRECTION_APPLIED"
    CANCEL_KNOWN = "CANCEL_KNOWN"
    CANCEL_APPLIED = "CANCEL_APPLIED"
    REJECTION_KNOWN = "REJECTION_KNOWN"
    RECONSTRUCTION_ANOMALY_KNOWN = "RECONSTRUCTION_ANOMALY_KNOWN"


class Relation(StrEnum):
    ABOVE = "ABOVE"
    AT = "AT"
    BELOW = "BELOW"
    INSIDE = "INSIDE"  # within an inclusive [low, high] band


@dataclass(frozen=True)
class EvidenceChange:
    domain: str
    path: str  # JSON pointer into the snapshot (or a named derived fact under /relations, /evidence)
    kind: ChangeKind
    before: object  # canonical JSON value (null = not available)
    after: object
    evidence_kind: EvidenceKind
    status_after: str | None  # the component's ComponentStatus in the later snapshot
    maturity_after: str | None
    note: str | None = None  # deterministic qualifier, e.g. when quality evidence first became knowable


@dataclass(frozen=True)
class NewlyKnownEvidence:
    """Source records known at the later cutoff but not at the earlier one (from the prepared record)."""

    records: int
    with_market_time_before_earlier_market_cutoff: int
    max_receipt_lag_of_those: timedelta | None
    corrections: int
    cancels: int


@dataclass(frozen=True)
class MarketStudyDelta:
    schema: str
    dataset_id: UUID
    from_snapshot_sha256: str
    to_snapshot_sha256: str
    from_cutoff: ReplayCutoff
    to_cutoff: ReplayCutoff
    newly_known: NewlyKnownEvidence | None
    changes: tuple[EvidenceChange, ...]

    @property
    def is_empty(self) -> bool:
        return not self.changes and (self.newly_known is None or self.newly_known.records == 0)


@dataclass(frozen=True)
class Milestone:
    name: str
    at_utc: datetime


# --- comparison --------------------------------------------------------------------------------

_MISSING = object()


def _get(doc, path: str):
    node = doc
    for part in path.strip("/").split("/"):
        if isinstance(node, list):
            node = node[int(part)] if part.isdigit() and int(part) < len(node) else _MISSING
        elif isinstance(node, dict):
            node = node.get(part, _MISSING)
        else:
            return None
        if node is _MISSING or node is None:
            return None
    return node


def _num(v) -> Decimal | None:
    return None if v is None else Decimal(v)


def _relation(price, low, high=None) -> str | None:
    p, lo = _num(price), _num(low)
    if p is None or lo is None:
        return None
    if high is None:
        return Relation.ABOVE.value if p > lo else Relation.BELOW.value if p < lo else Relation.AT.value
    hi = _num(high)
    return Relation.ABOVE.value if p > hi else Relation.BELOW.value if p < lo else Relation.INSIDE.value


def relations(doc: dict) -> dict[str, str | None]:
    """Deterministic price relations at the cutoff (facts only)."""
    last = _get(doc, "/prices/last_known_price")
    vwap = {v["anchor_kind"]: _get(v, "/study/vwap") for v in doc["vwap"]}
    ib = _get(doc, "/tpo/profile/initial_balance")
    prior = doc["prior_day"]["context"] or {}
    return {
        "last_price_vs_cash_vwap": _relation(last, vwap.get("US_CASH_OPEN")),
        "last_price_vs_globex_vwap": _relation(last, vwap.get("SESSION_OPEN")),
        "last_price_vs_developing_tpo_value_area": _relation(last, _get(doc, "/tpo/profile/value_area/low"),
                                                             _get(doc, "/tpo/profile/value_area/high")),
        "last_price_vs_developing_volume_value_area": _relation(last, _get(doc, "/volume_profile/value_area_low"),
                                                                _get(doc, "/volume_profile/value_area_high")),
        "last_price_vs_initial_balance": _relation(last, ib["low"], ib["high"]) if ib else None,
        "last_price_vs_prior_value_area": _relation(last, prior.get("value_area_low"), prior.get("value_area_high"))
        if prior.get("value_area_low") else None,
    }


_COUNT_KINDS = (
    ("accepted_known", ChangeKind.OBSERVATION_ADDED),
    ("rejected_known", ChangeKind.REJECTION_KNOWN),
    ("corrections_known", ChangeKind.CORRECTION_KNOWN),
    ("corrections_applied", ChangeKind.CORRECTION_APPLIED),
    ("cancels_known", ChangeKind.CANCEL_KNOWN),
    ("cancels_applied", ChangeKind.CANCEL_APPLIED),
    ("reconstruction_anomalies", ChangeKind.RECONSTRUCTION_ANOMALY_KNOWN),
    ("known_records_with_market_time_at_or_after_cutoff", ChangeKind.VALUE_CHANGED),
)
# (domain, path, quality-matrix component, evidence kind)
_VALUES = (
    ("price", "/prices/last_known_price", None, EvidenceKind.OBSERVED_FACT),
    ("price", "/prices/last_known_utc", None, EvidenceKind.OBSERVED_FACT),
    ("volume_profile", "/volume_profile/poc", "volume_profile", EvidenceKind.DERIVED_FACT),
    ("volume_profile", "/volume_profile/value_area_low", "volume_profile", EvidenceKind.DERIVED_FACT),
    ("volume_profile", "/volume_profile/value_area_high", "volume_profile", EvidenceKind.DERIVED_FACT),
    ("volume_profile", "/volume_profile/profile_high", "volume_profile", EvidenceKind.DERIVED_FACT),
    ("volume_profile", "/volume_profile/profile_low", "volume_profile", EvidenceKind.DERIVED_FACT),
    ("volume_profile", "/volume_profile/total_volume", "volume_profile", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/periods_reached", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/current_period", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/poc", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/value_area/low", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/value_area/high", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/profile_high", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/profile_low", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/initial_balance/high", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("tpo", "/tpo/profile/initial_balance/low", "cash_tpo", EvidenceKind.DERIVED_FACT),
    ("overnight", "/overnight/developing/high", "overnight", EvidenceKind.DERIVED_FACT),
    ("overnight", "/overnight/developing/low", "overnight", EvidenceKind.DERIVED_FACT),
    ("overnight", "/overnight/developing/last_price", "overnight", EvidenceKind.OBSERVED_FACT),
    ("overnight", "/overnight/session/high", "overnight", EvidenceKind.DERIVED_FACT),
    ("overnight", "/overnight/session/low", "overnight", EvidenceKind.DERIVED_FACT),
    ("overnight", "/overnight/session/terminal_price", "overnight", EvidenceKind.OBSERVED_FACT),
    ("cash_opening", "/cash_opening/cash_open/price", "cash_opening", EvidenceKind.OBSERVED_FACT),
    ("cash_opening", "/cash_opening/range_location", "cash_opening", EvidenceKind.DERIVED_FACT),
    ("cash_opening", "/cash_opening/value_location", "cash_opening", EvidenceKind.DERIVED_FACT),
    ("cash_opening", "/cash_opening/gap_ticks", "cash_opening", EvidenceKind.DERIVED_FACT),
    ("prior_day", "/prior_day/outcome", "prior_context", EvidenceKind.QUALITY_QUALIFICATION),
    ("terminal", "/prices/study_window_terminal_price", "day_type", EvidenceKind.OBSERVED_FACT),
    ("day_strength", "/day_strength/strength/dominant_extension", "day_strength", EvidenceKind.DERIVED_FACT),
)
_STRUCTURE = tuple((f"/tpo_structure/structure/{side}/{label}_candidate") for side in ("upper", "lower")
                   for label in ("excess", "poor"))
# quality-matrix component -> maturity-table component
_MATURITY_KEY = {"cash_tpo": "tpo", "cash_opening": "opening_facts", "prior_context": None, "dataset": None,
                 "contract": None}
_LIFECYCLE = ("capture_status", "lifecycle_as_of", "connection_as_of", "closing_summary_maturity")


def _value_kind(before, after) -> ChangeKind:
    if before is None:
        return ChangeKind.VALUE_AVAILABLE
    return ChangeKind.VALUE_WITHDRAWN if after is None else ChangeKind.VALUE_CHANGED


def compare_snapshot_states(before: MarketStudySnapshot, after: MarketStudySnapshot,
                            newly_known: NewlyKnownEvidence | None = None) -> MarketStudyDelta:
    """Deterministic, structured differences between two snapshots of one dataset (facts only)."""
    if before.current_dataset.dataset_id != after.current_dataset.dataset_id:
        raise ValueError("snapshots belong to different datasets")
    a, b = mss.encode(before), mss.encode(after)
    status = {q["component"]: q["status"] for q in b["quality_matrix"]}
    status_a = {q["component"]: q["status"] for q in a["quality_matrix"]}
    maturity = {m["component"]: m["maturity"] for m in b["maturity"]}
    maturity_a = {m["component"]: m["maturity"] for m in a["maturity"]}
    changes: list[EvidenceChange] = []

    def add(domain, path, kind, x, y, ek, component=None, note=None):
        mkey = _MATURITY_KEY.get(component, component)
        changes.append(EvidenceChange(domain, path, kind, x, y, ek, status.get(component) if component else None,
                                      maturity.get(mkey) if mkey else None, note))

    if newly_known is not None and newly_known.with_market_time_before_earlier_market_cutoff:
        add("evidence", "/evidence/newly_known_records_with_market_time_before_earlier_cutoff",
            ChangeKind.LATE_OBSERVATION_ADDED, 0, newly_known.with_market_time_before_earlier_market_cutoff,
            EvidenceKind.OBSERVED_FACT, None,
            f"max receipt lag {mss.encode(newly_known.max_receipt_lag_of_those)} s; history revised by newly received "
            "evidence")
    for field, kind in _COUNT_KINDS:
        x, y = a["current_dataset"]["counts"][field], b["current_dataset"]["counts"][field]
        if x != y:
            add("source_evidence", f"/current_dataset/counts/{field}", kind, x, y, EvidenceKind.OBSERVED_FACT)
    for field in _LIFECYCLE:
        x, y = a["current_dataset"][field], b["current_dataset"][field]
        if x != y:
            add("lifecycle", f"/current_dataset/{field}", ChangeKind.LIFECYCLE_CHANGED, x, y,
                EvidenceKind.QUALITY_QUALIFICATION, "dataset")
    qa, qb = a["dataset_quality"], b["dataset_quality"]
    for field in ("status", "completeness", "known_gap_count", "suspected_gap_count"):
        if qa[field] != qb[field]:
            add("quality", f"/dataset_quality/{field}", ChangeKind.QUALITY_CHANGED, qa[field], qb[field],
                EvidenceKind.QUALITY_QUALIFICATION, "dataset")
    if qa["active_interruption"] != qb["active_interruption"]:
        ai = qb["active_interruption"]
        add("quality", "/dataset_quality/active_interruption", ChangeKind.QUALITY_CHANGED, qa["active_interruption"],
            ai, EvidenceKind.QUALITY_QUALIFICATION, "dataset",
            f"first knowable at {ai['start_utc']} (SOURCE_DISCONNECTED observed)" if ai and not qa["active_interruption"]
            else None)
    known_before = {(g["evidence_type"], g["start_utc"], g["end_utc"]) for g in qa["gaps"]}
    for g in qb["gaps"]:
        if (g["evidence_type"], g["start_utc"], g["end_utc"]) not in known_before:
            add("quality", f"/dataset_quality/gaps/{g['evidence_type']}/{g['start_utc']}", ChangeKind.QUALITY_CHANGED,
                None, g, EvidenceKind.QUALITY_QUALIFICATION, "dataset",
                f"first knowable at {g['end_utc']} (interval closed at reconnect / close)")
    for component in sorted(set(status) | set(status_a)):
        if status_a.get(component) != status.get(component):
            add("quality", f"/quality_matrix/{component}/status", ChangeKind.QUALITY_CHANGED, status_a.get(component),
                status.get(component), EvidenceKind.QUALITY_QUALIFICATION, component)
    for component in [m["component"] for m in b["maturity"]]:
        if maturity_a.get(component) != maturity[component]:
            changes.append(EvidenceChange("maturity", f"/maturity/{component}", ChangeKind.COMPONENT_MATURED,
                                          maturity_a.get(component), maturity[component],
                                          EvidenceKind.LABORATORY_POLICY, None, maturity[component]))
    wa = {w["minutes"]: w for w in a["cash_opening"]["windows"]}
    for w in b["cash_opening"]["windows"]:
        if wa[w["minutes"]]["maturity"] != w["maturity"]:
            changes.append(EvidenceChange("maturity", f"/cash_opening/windows/{w['minutes']}min/maturity",
                                          ChangeKind.COMPONENT_MATURED, wa[w["minutes"]]["maturity"], w["maturity"],
                                          EvidenceKind.LABORATORY_POLICY, status.get("cash_opening"), w["maturity"]))
    va = {v["anchor_kind"]: v for v in a["vwap"]}
    for v in b["vwap"]:
        component = f"vwap {v['anchor_kind']}"
        x, y = _get(va[v["anchor_kind"]], "/study/vwap"), _get(v, "/study/vwap")
        if x != y:
            add("vwap", f"/vwap/{v['anchor_kind']}/study/vwap", _value_kind(x, y), x, y, EvidenceKind.DERIVED_FACT,
                component)
    for domain, path, component, ek in _VALUES:
        x, y = _get(a, path), _get(b, path)
        if x != y:
            add(domain, path, _value_kind(x, y), x, y, ek, component)
    ra, rb = relations(a), relations(b)
    for name in ra:
        if ra[name] != rb[name]:
            add("relations", f"/relations/{name}", ChangeKind.RELATION_CHANGED, ra[name], rb[name],
                EvidenceKind.DERIVED_FACT)
    for path in _STRUCTURE:
        x, y = _get(a, path), _get(b, path)
        if x != y:
            add("tpo_structure", path, ChangeKind.CANDIDATE_AVAILABLE if x is None else _value_kind(x, y), x, y,
                EvidenceKind.CANDIDATE, "tpo_structure")
    for path in ("/day_type/classification/outcome", "/day_type/classification/primary",
                 "/day_type/classification/direction"):
        x, y = _get(a, path), _get(b, path)
        if x != y:
            add("day_type", path, ChangeKind.CANDIDATE_AVAILABLE if x is None else _value_kind(x, y), x, y,
                EvidenceKind.CANDIDATE, "day_type")
    ma = {(m["type"], m["direction"]): m for m in a["opening_type"]["matched"]}
    mb = {(m["type"], m["direction"]): m for m in b["opening_type"]["matched"]}
    for key in sorted(set(ma) | set(mb), key=lambda k: (k[0], k[1] or "")):
        label = key[0] + (f" {key[1]}" if key[1] else "")
        if key not in ma:
            add("opening_type", f"/opening_type/matched/{label}", ChangeKind.CANDIDATE_AVAILABLE, None, mb[key],
                EvidenceKind.CANDIDATE, "opening_type", "OPENING_TYPE_V1 (frozen); a candidate, not an interpretation")
        elif key not in mb:
            add("opening_type", f"/opening_type/matched/{label}", ChangeKind.CANDIDATE_REMOVED, ma[key], None,
                EvidenceKind.CANDIDATE, "opening_type")
        elif ma[key]["quality"] != mb[key]["quality"]:
            add("opening_type", f"/opening_type/matched/{label}/quality", ChangeKind.QUALITY_CHANGED,
                ma[key]["quality"], mb[key]["quality"], EvidenceKind.QUALITY_QUALIFICATION, "opening_type")
    return MarketStudyDelta(DELTA_SCHEMA, after.current_dataset.dataset_id, snapshot_sha256(before),
                            snapshot_sha256(after), before.cutoff, after.cutoff, newly_known, tuple(changes))


def canonical_delta_json(delta: MarketStudyDelta) -> str:
    payload = mss.encode(delta)
    payload[DELTA_HASH_FIELD] = hashlib.sha256(mss._dumps(payload).encode("ascii")).hexdigest()
    return mss._dumps(payload)


def delta_sha256(delta: MarketStudyDelta) -> str:
    return hashlib.sha256(mss._dumps(mss.encode(delta)).encode("ascii")).hexdigest()


# --- session -----------------------------------------------------------------------------------

class ReplaySession:
    """One prepared trading date. Seeks compute snapshots from the prepared record (no SQLite reload)."""

    def __init__(self, replay: MarketReplay, cache_size: int = 16) -> None:
        self.replay = replay
        self._cache: dict[ReplayCutoff, MarketStudySnapshot] = {}
        self._cache_size = cache_size

    @classmethod
    def load(cls, database: Path, provenance: AnalysisProvenance, prior_database: Path | None = None,
             closures: frozenset[date] = frozenset(), dataset_id: UUID | None = None) -> ReplaySession:
        return cls(MarketReplay.load(database, provenance, prior_database, closures, dataset_id))

    @property
    def trading_date(self) -> date:
        return self.replay.current.trading_date

    def timeline(self) -> tuple[Milestone, ...]:
        td = self.trading_date
        globex = resolve_anchor(AnchorKind.SESSION_OPEN, td).anchor_timestamp_utc

        def ct(hh, mm):
            return datetime.combine(td, time(hh, mm), tzinfo=CT).astimezone(timezone.utc)

        return (Milestone("GLOBEX_OPEN 17:00", globex), Milestone("CASH_OPEN 08:30", ct(8, 30)),
                Milestone("OPENING_5MIN 08:35", ct(8, 35)), Milestone("OPENING_15MIN 08:45", ct(8, 45)),
                Milestone("PERIOD_A_END 09:00", ct(9, 0)), Milestone("IB_END 09:30", ct(9, 30)),
                Milestone("CASH_STUDY_END 15:00", ct(15, 0)), Milestone("SESSION_END 16:00", ct(16, 0)))

    def resolve_time(self, value: datetime | str) -> datetime:
        """An aware datetime, ISO text with offset, or "HH:MM[:SS]" America/Chicago on this session.

        Clock times at or after 17:00 belong to the session's opening evening (the calendar day
        of the Globex open, e.g. Sunday for a Monday trading date); earlier ones to the trading date.
        """
        if isinstance(value, datetime):
            if value.tzinfo is None:
                raise ValueError("replay times must be timezone-aware")
            return value.astimezone(timezone.utc)
        m = _HHMM.match(value.strip())
        if m:
            t = time(int(m.group(1)), int(m.group(2)), int(m.group(3) or 0))
            day = (resolve_anchor(AnchorKind.SESSION_OPEN, self.trading_date).anchor_timestamp_utc.astimezone(CT).date()
                   if t >= time(17, 0) else self.trading_date)
            return datetime.combine(day, t, tzinfo=CT).astimezone(timezone.utc)
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            raise ValueError(f"{value!r} has no UTC offset; use HH:MM (Chicago) or an explicit offset")
        return parsed.astimezone(timezone.utc)

    def step(self, at: datetime | str, step: str) -> datetime:
        """'+1m', '+5m', '+30s' ... or 'next' (the next structural milestone after `at`)."""
        start = self.resolve_time(at)
        if step == "next":
            later = [m.at_utc for m in self.timeline() if m.at_utc > start]
            if not later:
                raise ValueError("no structural milestone after this time")
            return later[0]
        m = _STEP.match(step)
        if not m:
            raise ValueError(f"unsupported step {step!r}; use +Nm, +Ns or next")
        n = int(m.group(1))
        return start + (timedelta(minutes=n) if m.group(2) == "m" else timedelta(seconds=n))

    def snapshot(self, at: datetime | str | None = None, *, cutoff: ReplayCutoff | None = None) -> MarketStudySnapshot:
        key = cutoff or ReplayCutoff.at(self.resolve_time(at))
        if key not in self._cache:
            if len(self._cache) >= self._cache_size:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = self.replay.snapshot(cutoff=key)
        return self._cache[key]

    def newly_known(self, earlier: ReplayCutoff, later: ReplayCutoff) -> NewlyKnownEvidence:
        prep = self.replay.current
        by_id = {t.observation_id: t for t in prep.canonical_trades}
        late, lag = 0, None
        n = 0
        for p in prep.provenance:
            if later.knows(p.received_at, p.source_order) and not earlier.knows(p.received_at, p.source_order):
                n += 1
                mts = by_id[p.observation_id].event_timestamp
                if mts < earlier.market_time_cutoff_utc:
                    late += 1
                    d = p.received_at - mts
                    lag = d if lag is None or d > lag else lag
        new_deferred = [d for d in prep.deferred if later.knows(d.source_record.received_at, d.source_order)
                        and not earlier.knows(d.source_record.received_at, d.source_order)]
        classes = [d.source_record.event_classification for d in new_deferred]
        return NewlyKnownEvidence(n + len(new_deferred), late, lag, classes.count("CORRECTION"), classes.count("CANCEL"))

    def compare(self, t1: datetime | str, t2: datetime | str) -> MarketStudyDelta:
        before, after = self.snapshot(t1), self.snapshot(t2)
        return compare_snapshot_states(before, after, self.newly_known(before.cutoff, after.cutoff))

    def compare_cutoffs(self, c1: ReplayCutoff, c2: ReplayCutoff) -> MarketStudyDelta:
        return compare_snapshot_states(self.snapshot(cutoff=c1), self.snapshot(cutoff=c2), self.newly_known(c1, c2))


class TutorEvidenceSession:
    """The evidence surface a future tutor will use: no replay internals, no interpretation."""

    def __init__(self, session: ReplaySession) -> None:
        self._session = session

    def state_at(self, t: datetime | str) -> MarketStudySnapshot:
        return self._session.snapshot(t)

    def changes_between(self, t1: datetime | str, t2: datetime | str) -> MarketStudyDelta:
        return self._session.compare(t1, t2)

    def timeline(self) -> tuple[Milestone, ...]:
        return self._session.timeline()


# --- rendering -----------------------------------------------------------------------------------

def marker(maturity: Maturity | str | None, status: str | None = None) -> str:
    """Explicit maturity/quality marker. COMPLETE = the component's market window has ended."""
    m = maturity.value if isinstance(maturity, Maturity) else maturity
    if m in (Maturity.NOT_YET_DETERMINED.value, Maturity.NOT_YET_AVAILABLE.value):
        return m
    if m == Maturity.NOT_AVAILABLE.value or status == "NOT_AVAILABLE":
        return "NOT_AVAILABLE"
    label = {Maturity.DEVELOPING.value: "DEVELOPING", Maturity.WINDOW_COMPLETE.value: "COMPLETE"}.get(m, m or "--")
    return label + (", QUALITY_QUALIFIED" if status == "QUALITY_QUALIFIED" else "")


def _ct(ts: datetime | None) -> str:
    return "--" if ts is None else ts.astimezone(CT).strftime("%Y-%m-%d %H:%M:%S %Z")


def _v(x) -> str:
    return "--" if x is None else mss._v(x)


def render_player_view(s: MarketStudySnapshot, sha: str | None = None) -> str:
    doc = mss.encode(s)
    mat = {e.component: e.maturity for e in s.maturity}
    rel = relations(doc)
    d, c = s.current_dataset, s.cutoff
    lines = ["REPLAY TIME",
             f"  market cutoff    {_ct(c.market_time_cutoff_utc)}   knowledge cutoff {_ct(c.knowledge_time_cutoff_utc)}"
             + (f"  source_order <= {c.knowledge_source_order_cutoff}" if c.knowledge_source_order_cutoff else ""),
             f"  trading date {d.trading_date}  {d.instrument_id}  snapshot {(sha or snapshot_sha256(s))[:16]}",
             "", f"DATA / QUALITY  [{s.dataset_quality.status.value}]",
             f"  capture {d.capture_status.value}  lifecycle {d.lifecycle_as_of}  connection {d.connection_as_of.value}",
             f"  known: accepted {d.counts.accepted_known:,}  corrections {d.counts.corrections_known}  cancels "
             f"{d.counts.cancels_known}  rejected {d.counts.rejected_known}  known gaps {s.dataset_quality.known_gap_count}"]
    lines += [f"  ! {r}" for r in s.dataset_quality.reasons[:4]]
    tp = s.tpo.profile
    on = s.overnight.developing or s.overnight.session
    lines += ["", "CURRENT PRICE / RANGE",
              f"  last known {_v(s.prices.last_known_price)} at {_ct(s.prices.last_known_utc)}",
              f"  cash range so far {_v(tp.profile_low) if tp else '--'} - {_v(tp.profile_high) if tp else '--'}"
              f"   overnight range {_v(on.low) if on else '--'} - {_v(on.high) if on else '--'}"]
    lines += ["", "VWAP"]
    for v in s.vwap:
        rel_key = "last_price_vs_cash_vwap" if v.anchor_kind is AnchorKind.US_CASH_OPEN else "last_price_vs_globex_vwap"
        lines.append(f"  {v.anchor_kind.value:<13} [{marker(v.maturity, v.status.value)}] "
                     + (f"{_v(v.study.vwap.quantize(Decimal('0.01')))}  last price {rel[rel_key] or '--'}" if v.study
                        else "--"))
    vp = s.volume_profile
    lines += ["", f"VOLUME PROFILE  [{marker(mat['volume_profile'], vp.status.value)}]",
              f"  POC {_v(vp.poc)}  VAL {_v(vp.value_area_low)}  VAH {_v(vp.value_area_high)}  volume "
              f"{_v(vp.total_volume)}  last price vs value {rel['last_price_vs_developing_volume_value_area'] or '--'}"]
    lines += ["", f"TPO  [{marker(mat['tpo'], s.tpo.status.value)}]   IB [{marker(mat['initial_balance'])}]",
              f"  periods {s.tpo.periods_reached or '--'}  current {s.tpo.current_period or '--'}"]
    if tp is not None:
        ib = tp.initial_balance
        lines.append(f"  TPO POC {tp.poc}  VAL {tp.value_area.low}  VAH {tp.value_area.high}"
                     + (f"  IB {ib.low}-{ib.high}" if ib else "")
                     + f"  last price vs TPO value {rel['last_price_vs_developing_tpo_value_area'] or '--'}")
    pc = s.prior_day.context
    lines += ["", f"PRIOR DAY  [{s.prior_day.status.value}]"]
    if pc is not None and pc.usable:
        lines.append(f"  {pc.prior_trading_date}: high {pc.profile_high} low {pc.profile_low} VAH {pc.value_area_high} "
                     f"VAL {pc.value_area_low} POC {pc.poc} terminal {pc.terminal_price}"
                     f"  last price vs prior value {rel['last_price_vs_prior_value_area'] or '--'}")
    else:
        lines.append(f"  {s.prior_day.reasons[0] if s.prior_day.reasons else '--'}")
    lines += ["", f"OVERNIGHT  [{marker(mat['overnight'], s.overnight.status.value)}]  Globex open claimed "
              f"{'yes' if s.overnight.globex_open_claimed else 'no'}"]
    if on is not None:
        last = getattr(on, "last_price", None) or getattr(on, "terminal_price", None)
        lines.append(f"  high {_v(on.high)}  low {_v(on.low)}  range {_v(on.range_ticks)} ticks  last {_v(last)}")
    co = s.cash_opening
    lines += ["", f"CASH OPEN / OPENING FACTS  [{marker(mat['opening_facts'], co.status.value)}]",
              f"  cash open [{marker(co.cash_open_maturity)}] {_v(co.cash_open.price) if co.cash_open else '--'}"
              f"  vs prior range {_v(co.range_location)}  vs prior value {_v(co.value_location)}  gap "
              f"{_v(co.gap_ticks)} ticks",
              "  windows " + "  ".join(f"{w.minutes}m [{marker(w.maturity)}]" for w in co.windows)]
    ot = s.opening_type
    lines += ["", f"OPENING TYPE (OPENING_TYPE_V1)  [{marker(mat['opening_type'], ot.status.value)}]"]
    lines += [f"  CANDIDATE {m.type}" + (f" {m.direction}" if m.direction else "") + f"  ({m.quality})"
              for m in ot.matched] or ["  " + (ot.reasons[0] if ot.reasons else "no matched candidate")]
    dt = s.day_type.classification
    lines += ["", f"DAY TYPE (DAY_TYPE_V1)  [{marker(mat['day_type'], s.day_type.status.value)}]"]
    if dt is not None:
        lines.append(f"  {dt.outcome.value} " + (f"{dt.primary.value}_CANDIDATE" if dt.primary else "")
                     + (f" {dt.direction.value}" if dt.direction else "")
                     + f"   terminal {_v(s.prices.study_window_terminal_price)}")
        ds = s.day_strength.strength
        if ds is not None:
            lines.append(f"  strength: dominant {_v(ds.dominant_extension)}  above {_v(ds.extension_above_ticks)} / "
                         f"below {_v(ds.extension_below_ticks)} ticks")
    pending = [e.component for e in s.maturity if e.maturity in (Maturity.NOT_YET_DETERMINED, Maturity.NOT_YET_AVAILABLE)]
    pending += [f"opening window {w.minutes}m" for w in co.windows if w.maturity is Maturity.NOT_YET_DETERMINED]
    lines += ["", "NOT-YET-DETERMINED / NOT-YET-AVAILABLE ITEMS", "  " + (", ".join(pending) if pending else "none")]
    lines += ["", "Markers: DEVELOPING = window in progress; COMPLETE = market window ended (later receipts may still",
              "revise it); NOT_YET_DETERMINED = final-study item before its window ends. Facts only; no interpretation."]
    return "\n".join(lines) + "\n"


def render_delta(delta: MarketStudyDelta) -> str:
    lines = [f"CHANGES {_ct(delta.from_cutoff.market_time_cutoff_utc)} -> {_ct(delta.to_cutoff.market_time_cutoff_utc)}",
             f"  snapshots {delta.from_snapshot_sha256[:16]} -> {delta.to_snapshot_sha256[:16]}   delta "
             f"{delta_sha256(delta)[:16]}"]
    n = delta.newly_known
    if n is not None:
        lines.append(f"  newly known source records: {n.records:,} (with market time before the earlier cutoff: "
                     f"{n.with_market_time_before_earlier_market_cutoff:,}"
                     + (f", max receipt lag {mss.encode(n.max_receipt_lag_of_those)} s" if n.max_receipt_lag_of_those
                        else "") + f"; corrections {n.corrections}, cancels {n.cancels})")
    if not delta.changes:
        lines.append("  no change")
    domain = None
    for ch in delta.changes:
        if ch.domain != domain:
            domain = ch.domain
            lines.append(f"  {domain.upper()}")
        lines.append(f"    [{ch.kind.value}] {ch.path}: {_fmt(ch.before)} -> {_fmt(ch.after)}"
                     + (f"  ({ch.note})" if ch.note else ""))
    lines.append("Deterministic differences only; no market interpretation.")
    return "\n".join(lines) + "\n"


def _fmt(v) -> str:
    if v is None:
        return "null"
    if isinstance(v, dict):
        if "type" in v:
            return v["type"] + (f" {v['direction']}" if v.get("direction") else "") + f" ({v.get('quality')})"
        return "{" + ", ".join(f"{k}={v[k]}" for k in sorted(v)) + "}"
    return str(v)
