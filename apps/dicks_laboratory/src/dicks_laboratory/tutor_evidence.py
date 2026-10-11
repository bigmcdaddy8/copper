"""AI tutor evidence and lesson foundation (0AA-A). Deterministic; no AI model, no network.

    replay / MARKET_STUDY_SNAPSHOT_V1 (+ MARKET_STUDY_DELTA_V1)
        -> TutorEvidenceContext   (authorized, AS_OF evidence with structured references)
        -> TutorLesson            (question, answer key, optional hidden future outcome)
        -> student_view / instructor_view (canonical JSON payloads a future model may receive)
        -> validate_answer_grounding(TutorAnswer)  (the constraint a future model must satisfy)

The accepted replay engine stays the only temporal authority: this module never computes a
cutoff, a maturity or a market value. It selects evidence from snapshots the ReplaySession built
and refers to it by `EvidenceRef(source_sha256, pointer)`, an RFC 6901 pointer into the canonical
MARKET_STUDY_SNAPSHOT_V1 / MARKET_STUDY_DELTA_V1 document with that hash. `/relations/*` resolves
into `replay_player.relations()` of the same snapshot (0Z-C derived price relations).

    TutorEvidenceContext != market opinion
    curriculum rule      != observed fact
    AI interpretation    != Laboratory evidence

Canonical JSON uses the MARKET_STUDY_STATE_V1 encoding; payload hashes are computed over the
payload without its hash field. No wall-clock field anywhere.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from dicks_laboratory import market_study_state as mss
from dicks_laboratory.price_action import build_price_action_facts, price_action_sha256
from dicks_laboratory.replay import MarketStudySnapshot, Maturity, snapshot_sha256
from dicks_laboratory.replay_player import (
    CT,
    MarketStudyDelta,
    ReplaySession,
    delta_sha256,
    relations,
)

CONTEXT_SCHEMA = "TUTOR_EVIDENCE_CONTEXT_V1"
LESSON_SCHEMA = "TUTOR_LESSON_V1"
STUDENT_VIEW_SCHEMA = "TUTOR_STUDENT_VIEW_V1"
INSTRUCTOR_VIEW_SCHEMA = "TUTOR_INSTRUCTOR_VIEW_V1"
ANSWER_SCHEMA = "TUTOR_ANSWER_V1"
SESSION_RECORD_SCHEMA = "TUTOR_SESSION_RECORD_V1"
REVEAL_POLICY = "TUTOR_REVEAL_V1"
PAYLOAD_HASH_FIELD = "payload_sha256"
AS_OF = "AS_OF"


# --- vocabularies --------------------------------------------------------------------------------

class ClaimCategory(StrEnum):
    """What kind of statement a piece of evidence (or a claim) is. Never blurred."""

    OBSERVED_FACT = "OBSERVED_FACT"  # a retained trade's own price / time; a recorded lifecycle fact
    DERIVED_FACT = "DERIVED_FACT"  # deterministic computation over retained trades (VWAP, value, relations)
    LABORATORY_POLICY_RESULT = "LABORATORY_POLICY_RESULT"  # outcome of a Laboratory policy (maturity, outcome)
    CANDIDATE = "CANDIDATE"  # a Laboratory candidate label (OPENING_TYPE_V1, DAY_TYPE_V1, structure)
    QUALITY_WARNING = "QUALITY_WARNING"  # availability / completeness evidence
    CURRICULUM_RULE = "CURRICULUM_RULE"  # a teaching rule from a registered curriculum source; not evidence
    AI_INTERPRETATION = "AI_INTERPRETATION"  # a model's reading of the evidence; never Laboratory evidence


EVIDENCE_CATEGORIES = frozenset({ClaimCategory.OBSERVED_FACT, ClaimCategory.DERIVED_FACT,
                                 ClaimCategory.LABORATORY_POLICY_RESULT, ClaimCategory.CANDIDATE,
                                 ClaimCategory.QUALITY_WARNING})


class EvidenceDomain(StrEnum):
    DATA_QUALITY = "DATA_QUALITY"
    PRICE = "PRICE"
    VWAP = "VWAP"
    VOLUME_PROFILE = "VOLUME_PROFILE"
    TPO = "TPO"
    INITIAL_BALANCE = "INITIAL_BALANCE"
    PRIOR_DAY = "PRIOR_DAY"
    OVERNIGHT = "OVERNIGHT"
    OPENING = "OPENING"
    DAY_TYPE = "DAY_TYPE"
    MATURITY = "MATURITY"
    CHANGES = "CHANGES"  # MARKET_STUDY_DELTA_V1 between two lesson snapshots
    VWAP_BANDS = "VWAP_BANDS"  # 0AB-A (PRICE_ACTION_FACTS_V1): VWAP_BANDS_V1 bands, zones, time outside
    REFERENCE_PATHS = "REFERENCE_PATHS"  # crossings / excursions vs VWAP, bands and static references
    PRICE_ACTION_BARS = "PRICE_ACTION_BARS"  # 5-minute bars (the most recent ones)
    VOLATILITY = "VOLATILITY"  # ATR_5M_V1


class Availability(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_YET_AVAILABLE = "NOT_YET_AVAILABLE"
    NOT_YET_DETERMINED = "NOT_YET_DETERMINED"
    NOT_AVAILABLE = "NOT_AVAILABLE"  # its window passed without the evidence it needs (never 0 / false)


class EvidenceSupport(StrEnum):
    """Whether evidence answers a question. Lack of evidence is never FALSE."""

    SUPPORTED = "SUPPORTED"
    NOT_YET_AVAILABLE = "NOT_YET_AVAILABLE"
    NOT_YET_DETERMINED = "NOT_YET_DETERMINED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # missing evidence, implementation or policy


class LessonMode(StrEnum):
    """Educational intents only. No recommendation, alert or decision mode exists."""

    OBSERVE = "OBSERVE"
    IDENTIFY = "IDENTIFY"
    COMPARE = "COMPARE"
    EXPLAIN_EVIDENCE = "EXPLAIN_EVIDENCE"


class LessonStage(StrEnum):
    QUESTION = "QUESTION"
    HINT = "HINT"
    ANSWER = "ANSWER"
    POST_REVEAL = "POST_REVEAL"


STAGE_ORDER = (LessonStage.QUESTION, LessonStage.HINT, LessonStage.ANSWER, LessonStage.POST_REVEAL)
# TUTOR_REVEAL_V1: the stage at which each instructor-only material reaches the student payload.
REVEAL_SCHEDULE = (("hints", LessonStage.HINT), ("answer_key", LessonStage.ANSWER),
                   ("future_outcome", LessonStage.POST_REVEAL))


def _reached(stage: LessonStage, at: LessonStage) -> bool:
    return STAGE_ORDER.index(stage) >= STAGE_ORDER.index(at)


class SourceRole(StrEnum):
    LESSON_TIME = "LESSON_TIME"  # the student's replay time
    COMPARE_FROM = "COMPARE_FROM"  # the earlier snapshot of a comparison lesson
    FUTURE_OUTCOME = "FUTURE_OUTCOME"  # instructor-only until POST_REVEAL
    DELTA = "DELTA"
    PRICE_ACTION = "PRICE_ACTION"  # 0AB-A: PRICE_ACTION_FACTS_V1 at the lesson time


class QuestionKind(StrEnum):
    PRICE_VS_CASH_VWAP = "PRICE_VS_CASH_VWAP"
    INITIAL_BALANCE_STATUS = "INITIAL_BALANCE_STATUS"
    EVIDENCE_CHANGES = "EVIDENCE_CHANGES"
    VALUE_MIGRATION = "VALUE_MIGRATION"
    VALUE_OCCUPANCY = "VALUE_OCCUPANCY"
    VWAP_ACCEPTANCE = "VWAP_ACCEPTANCE"  # 0AA-B: a question the Laboratory deliberately cannot answer
    NOT_YET_DETERMINED_ITEMS = "NOT_YET_DETERMINED_ITEMS"
    DATA_QUALITY = "DATA_QUALITY"


# --- curriculum sources, modules, value-area conventions ------------------------------------------

class CurriculumSourceType(StrEnum):
    LABORATORY_NATIVE = "LABORATORY_NATIVE"
    PLAYBOOK = "PLAYBOOK"
    EXTERNAL_GUIDE = "EXTERNAL_GUIDE"
    BOOK = "BOOK"
    STUDY_GUIDE = "STUDY_GUIDE"


@dataclass(frozen=True)
class TutorCurriculumSource:
    source_id: str
    title: str
    origin: str  # author / owner
    source_type: CurriculumSourceType
    version: str | None
    location: str | None  # repository reference (third-party text is never copied into the repository)
    redistributable_in_repository: bool
    notes: str | None = None


LAB_SOURCE = TutorCurriculumSource(
    "DICKS_LAB_EVIDENCE", "Dick's Laboratory accepted evidence and policies", "Dick's Laboratory (this repository)",
    CurriculumSourceType.LABORATORY_NATIVE, "MARKET_STUDY_SNAPSHOT_V1", "docs/dicks_laboratory", True,
    "Replay-backed deterministic evidence; policy ids in each snapshot's policy registry.")
PLAYBOOK_SOURCE = TutorCurriculumSource(
    "FUTURES_TREND_PLAYBOOK", "Futures Trend Playbook", "Human Product Owner", CurriculumSourceType.PLAYBOOK,
    "V1 (draft; revision in the document header)", "docs/trading_strategies/FUTURES_TREND_PLAYBOOK_V1.md", True,
    "Strategy / platform conventions (NinjaTrader); separate from Laboratory policies.")
DRYSDALE_SOURCE = TutorCurriculumSource(
    "DRYSDALE_VWAP_WAVE_CORE_SETUP_GUIDE", "VWAP Wave Core Setup Guide", "Chris Drysdale",
    CurriculumSourceType.EXTERNAL_GUIDE, "PDF created 2026-05-17", "docs/dicks_laboratory/DRYSDALE_VWAP_SETUP_GUIDE.md",
    False, "Third-party material; reference note only, the PDF is not redistributed.")
CURRICULUM_SOURCES = (LAB_SOURCE, PLAYBOOK_SOURCE, DRYSDALE_SOURCE)
_SOURCES = {s.source_id: s for s in CURRICULUM_SOURCES}


@dataclass(frozen=True)
class ValueAreaConvention:
    """A value-area convention is identified, never converted into another one."""

    convention_id: str
    fraction: Decimal
    source_id: str
    applies_to: str
    computed_by_laboratory: bool
    note: str


LABORATORY_PROFILE_70 = ValueAreaConvention(
    "LABORATORY_PROFILE_70", Decimal("0.70"), "DICKS_LAB_EVIDENCE",
    "Laboratory volume profile and TPO value areas (DICKS_LAB_VALUE_AREA_POLICY, DICKS_LAB_TPO_VALUE_AREA_POLICY)",
    True, "accepted Laboratory semantics")
PLAYBOOK_NINJATRADER_68 = ValueAreaConvention(
    "PLAYBOOK_NINJATRADER_68", Decimal("0.68"), "FUTURES_TREND_PLAYBOOK",
    "NinjaTrader Order Flow Volume Profile (playbook CFG-05)", False,
    "strategy / platform convention; no Laboratory evidence is computed at 68% and 70% values are not relabeled")
VALUE_AREA_CONVENTIONS = (LABORATORY_PROFILE_70, PLAYBOOK_NINJATRADER_68)
_CONVENTIONS = {c.convention_id: c for c in VALUE_AREA_CONVENTIONS}


class ModuleReadiness(StrEnum):
    READY_FOR_EVIDENCE_LESSONS = "READY_FOR_EVIDENCE_LESSONS"
    NOT_READY_FOR_RULE_IMPLEMENTATION = "NOT_READY_FOR_RULE_IMPLEMENTATION"


class DependencyStatus(StrEnum):
    FACT_AVAILABLE_NOW = "FACT_AVAILABLE_NOW"
    NEEDS_POLICY_DEFINITION = "NEEDS_POLICY_DEFINITION"
    NEEDS_IMPLEMENTATION = "NEEDS_IMPLEMENTATION"


@dataclass(frozen=True)
class CurriculumDependency:
    dependency: str
    status: DependencyStatus
    evidence: str | None  # where the available fact lives
    note: str | None = None


@dataclass(frozen=True)
class CurriculumTopic:
    topic_id: str
    title: str
    cross_reference: str | None = None


@dataclass(frozen=True)
class CurriculumModule:
    module_id: str
    source_id: str
    title: str
    readiness: ModuleReadiness
    executable: bool  # whether lessons may be built from it
    topics: tuple[CurriculumTopic, ...]
    dependencies: tuple[CurriculumDependency, ...]
    value_area_convention_id: str | None
    note: str | None = None


_A, _P, _I = (DependencyStatus.FACT_AVAILABLE_NOW, DependencyStatus.NEEDS_POLICY_DEFINITION,
              DependencyStatus.NEEDS_IMPLEMENTATION)
DRYSDALE_DEPENDENCIES = (
    CurriculumDependency("session VWAP", _A, "/vwap/*/study/vwap (MARKET_STUDY_SNAPSHOT_V1)"),
    CurriculumDependency("price relative to VWAP", _A, "/relations/last_price_vs_cash_vwap, last_price_vs_globex_vwap"),
    CurriculumDependency("VWAP relation changes between snapshots", _A, "MARKET_STUDY_DELTA_V1 RELATION_CHANGED"),
    CurriculumDependency("Initial Balance", _A, "/tpo/profile/initial_balance, /maturity initial_balance"),
    CurriculumDependency("developing Volume Profile value", _A, "/volume_profile/poc, value_area_low, value_area_high",
                         "Laboratory 70% convention"),
    CurriculumDependency("prior Volume Profile value", _A, "/prior_day/context/poc, value_area_low, value_area_high",
                         "Laboratory 70% convention"),
    CurriculumDependency("developing value migration", _A, "two snapshots + MARKET_STUDY_DELTA_V1",
                         "any threshold is a playbook policy"),
    CurriculumDependency("replay free of hindsight", _A, "MARKET_STUDY_SNAPSHOT_V1 cutoffs (0Z-B)"),
    # 0AB-A: implemented as Laboratory facts / policies (PRICE_ACTION_FACTS_V1)
    CurriculumDependency("VWAP deviation bands", _A, "PRICE_ACTION_FACTS_V1 /bands (VWAP_BANDS_V1)",
                         "Laboratory policy: volume-weighted sigma about the cash VWAP, k = 1, 2; the guide states no "
                         "formula or multiplier"),
    CurriculumDependency("VWAP crossing path", _A, "PRICE_ACTION_FACTS_V1 /references (REFERENCE_PATH_V1)"),
    CurriculumDependency("time outside value", _A, "PRICE_ACTION_FACTS_V1 /occupancy",
                         "time outside the VWAP_BANDS_V1 bands per multiplier; which band is the guide's 'VWAP value "
                         "area' is a separate open policy"),
    CurriculumDependency("5-minute price-action facts", _A, "PRICE_ACTION_FACTS_V1 /rth_bars (BARS_5M_V1)"),
    CurriculumDependency("volatility measure such as ATR", _A, "PRICE_ACTION_FACTS_V1 /atr (ATR_5M_V1)",
                         "ATR(13) Wilder on full-session 5m bars of the trading date; the guide names no measure"),
    # still policy decisions; their measurable dimensions now exist (references, episodes, bars, occupancy)
    CurriculumDependency("VWAP value area (which band pair)", _P, None,
                         "the guide's 'VWAP value area' / 'value band' is not mapped to a VWAP_BANDS_V1 multiplier"),
    CurriculumDependency("breakout", _P, "dimensions: /references episodes (first cross, first close beyond, "
                         "excursion, time beyond, return)"),
    CurriculumDependency("acceptance", _P, "dimensions: time beyond, closes / consecutive closes beyond, volume "
                         "beyond, adverse return, cross count", "the guide offers time or distance; no threshold"),
    CurriculumDependency("backtest / retest", _P, "dimensions: touched again, closest approach after peak, "
                         "excursion after touch"),
    CurriculumDependency("first sign of strength", _P, "dimensions: 5m bar facts and relations",
                         "qualitative in the guide"),
    CurriculumDependency("first sign of weakness", _P, "dimensions: 5m bar facts and relations",
                         "qualitative in the guide"),
    CurriculumDependency("rejection", _P, "dimensions: touch / cross, max excursion through, time beyond, return, "
                         "excursion after return"),
)
LAB_MODULE = CurriculumModule(
    "LAB_EVIDENCE_READING_V1", "DICKS_LAB_EVIDENCE", "Reading Laboratory evidence as of a replay time",
    ModuleReadiness.READY_FOR_EVIDENCE_LESSONS, True, (
        CurriculumTopic("LAB-VWAP", "Price relative to VWAP"),
        CurriculumTopic("LAB-IB", "Initial Balance maturity"),
        CurriculumTopic("LAB-CHANGES", "What changed in the evidence"),
        CurriculumTopic("LAB-VALUE", "Developing value"),
        CurriculumTopic("LAB-MATURITY", "What is not yet determined"),
        CurriculumTopic("LAB-QUALITY", "Qualified and unavailable evidence")),
    (), LABORATORY_PROFILE_70.convention_id)
DRYSDALE_MODULE = CurriculumModule(
    "DRYSDALE_VWAP_WAVE_V1", "DRYSDALE_VWAP_WAVE_CORE_SETUP_GUIDE", "VWAP Wave core curriculum",
    ModuleReadiness.NOT_READY_FOR_RULE_IMPLEMENTATION, False, (
        CurriculumTopic("DRYSDALE-PDC", "Price Discovery Continuation", "playbook SETUP-01 (PB-PDC)"),
        CurriculumTopic("DRYSDALE-FADE", "Fade Value Area Extremes", "playbook SETUP-02 (PB-FADE)"),
        CurriculumTopic("DRYSDALE-RTV", "Return to Value", "playbook SETUP-03 (PB-RTV)"),
        CurriculumTopic("DRYSDALE-BOUNCE", "VWAP Bounce", "playbook SETUP-04 (PB-BOUNCE)")),
    DRYSDALE_DEPENDENCIES, None,
    "Registered, not implemented: no rule may be built until each NEEDS_* dependency has an explicit policy. Its "
    "VWAP value area is band-based, not a profile percentage.")
CURRICULUM_MODULES = (LAB_MODULE, DRYSDALE_MODULE)
_MODULES = {m.module_id: m for m in CURRICULUM_MODULES}


class CurriculumNotReady(ValueError):
    pass


class ValueAreaConventionError(ValueError):
    pass


def curriculum_module(module_id: str) -> CurriculumModule:
    return _MODULES[module_id]


def require_executable(module_id: str) -> CurriculumModule:
    module = _MODULES.get(module_id)
    if module is None:
        raise CurriculumNotReady(f"unknown curriculum module {module_id!r}")
    if not module.executable or module.readiness is not ModuleReadiness.READY_FOR_EVIDENCE_LESSONS:
        missing = [d.dependency for d in module.dependencies if d.status is not DependencyStatus.FACT_AVAILABLE_NOW]
        raise CurriculumNotReady(f"{module_id} is {module.readiness.value}; missing: {', '.join(missing)}")
    return module


# --- evidence ------------------------------------------------------------------------------------

@dataclass(frozen=True)
class EvidenceRef:
    source_sha256: str  # a MARKET_STUDY_SNAPSHOT_V1 or MARKET_STUDY_DELTA_V1 hash
    pointer: str  # RFC 6901 pointer into that canonical document

    def __str__(self) -> str:
        return f"{self.source_sha256[:12]}#{self.pointer}"


Scalar = str | int | bool | None


@dataclass(frozen=True)
class EvidenceItem:
    ref: EvidenceRef
    domain: EvidenceDomain
    label: str
    value: Scalar  # canonical JSON scalar; structured values are canonical JSON text; None = absent
    category: ClaimCategory
    availability: Availability
    maturity: str | None  # the component's maturity in that snapshot
    status: str | None  # the component's ComponentStatus in that snapshot
    derived_from: tuple[str, ...] = ()  # pointers in the same source


@dataclass(frozen=True)
class QualityWarning:
    warning_id: str  # "<role>:<component>"
    component: str
    status: str
    reasons: tuple[str, ...]
    ref: EvidenceRef


@dataclass(frozen=True)
class SnapshotEvidence:
    role: SourceRole
    snapshot_sha256: str
    replay_market_time: datetime
    replay_knowledge_time: datetime
    evidence_temporality: str
    items: tuple[EvidenceItem, ...]
    quality_warnings: tuple[QualityWarning, ...]


@dataclass(frozen=True)
class DeltaEvidence:
    delta_sha256: str
    from_snapshot_sha256: str
    to_snapshot_sha256: str
    items: tuple[EvidenceItem, ...]


@dataclass(frozen=True)
class PolicyRef:
    component: str
    policy_id: str | None
    policy_version: str | None


@dataclass(frozen=True)
class TutorEvidenceContext:
    """Only the evidence authorized for one lesson, AS_OF its replay time. Not a market opinion."""

    schema: str
    lesson_id: str
    trading_date: date
    dataset_id: UUID
    instrument_id: str
    evidence_temporality: str
    replay_market_time: datetime
    replay_knowledge_time: datetime
    snapshot_sha256: str  # the lesson-time snapshot
    authorized_domains: tuple[EvidenceDomain, ...]
    snapshots: tuple[SnapshotEvidence, ...]  # COMPARE_FROM (if any), then LESSON_TIME
    delta: DeltaEvidence | None
    quality_warnings: tuple[QualityWarning, ...]
    policy_registry: tuple[PolicyRef, ...]
    value_area_convention: ValueAreaConvention | None
    curriculum_source_ids: tuple[str, ...]

    def items(self) -> tuple[EvidenceItem, ...]:
        return tuple(i for s in self.snapshots for i in s.items) + (self.delta.items if self.delta else ())


def _scalar(v) -> Scalar:
    return mss._dumps(v) if isinstance(v, dict | list) else v


def resolve_pointer(doc, pointer: str):
    """RFC 6901. Raises KeyError when the path does not exist (null is a value, not absence)."""
    node = doc
    if pointer == "":
        return node
    if not pointer.startswith("/"):
        raise KeyError(pointer)
    for raw in pointer[1:].split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(node, list):
            if not part.isdigit() or int(part) >= len(node):
                raise KeyError(pointer)
            node = node[int(part)]
        elif isinstance(node, dict):
            if part not in node:
                raise KeyError(pointer)
            node = node[part]
        else:
            raise KeyError(pointer)
    return node


def snapshot_document(s: MarketStudySnapshot) -> dict:
    """The canonical snapshot document references resolve into (+ its 0Z-C relations)."""
    doc = mss.encode(s)
    return {**doc, "relations": relations(doc)}


_NOT_YET = {Maturity.NOT_YET_DETERMINED.value: Availability.NOT_YET_DETERMINED,
            Maturity.NOT_YET_AVAILABLE.value: Availability.NOT_YET_AVAILABLE}
_DOMAIN_OF_COMPONENT = {
    "dataset": EvidenceDomain.DATA_QUALITY, "contract": EvidenceDomain.DATA_QUALITY,
    "vwap SESSION_OPEN": EvidenceDomain.VWAP, "vwap US_CASH_OPEN": EvidenceDomain.VWAP,
    "volume_profile": EvidenceDomain.VOLUME_PROFILE, "cash_tpo": EvidenceDomain.TPO,
    "tpo_structure": EvidenceDomain.DAY_TYPE, "day_type": EvidenceDomain.DAY_TYPE, "day_strength": EvidenceDomain.DAY_TYPE,
    "prior_context": EvidenceDomain.PRIOR_DAY, "overnight": EvidenceDomain.OVERNIGHT,
    "cash_opening": EvidenceDomain.OPENING, "opening_type": EvidenceDomain.OPENING,
}
_O, _D, _R, _C, _Q = (ClaimCategory.OBSERVED_FACT, ClaimCategory.DERIVED_FACT, ClaimCategory.LABORATORY_POLICY_RESULT,
                      ClaimCategory.CANDIDATE, ClaimCategory.QUALITY_WARNING)


def _snapshot_items(doc: dict, sha: str, domains: frozenset[EvidenceDomain]) -> tuple[EvidenceItem, ...]:
    mat = {m["component"]: (i, m["maturity"]) for i, m in enumerate(doc["maturity"])}
    qual = {q["component"]: q["status"] for q in doc["quality_matrix"]}
    out: list[EvidenceItem] = []

    def add(domain, label, pointer, category, maturity_of=None, status_of=None, derived=(), null_is_fact=False):
        if domain not in domains or any(i.ref.pointer == pointer for i in out):
            return  # one item per path (an absent parent object is reported once)
        value = _scalar(resolve_pointer(doc, pointer))
        maturity = mat[maturity_of][1] if maturity_of in mat else None
        availability = (Availability.AVAILABLE if value is not None or null_is_fact
                        else _NOT_YET.get(maturity, Availability.NOT_AVAILABLE))
        out.append(EvidenceItem(EvidenceRef(sha, pointer), domain, label, value, category, availability, maturity,
                                qual.get(status_of) if status_of else None, tuple(derived)))

    def opt(base: str, leaf: str) -> str:  # the leaf when its parent object exists, else the (null) parent
        return f"{base}/{leaf}" if resolve_pointer(doc, base) is not None else base

    E = EvidenceDomain
    add(E.DATA_QUALITY, "dataset quality status", "/dataset_quality/status", _Q, None, "dataset")
    add(E.DATA_QUALITY, "dataset completeness", "/dataset_quality/completeness", _Q, None, "dataset")
    add(E.DATA_QUALITY, "known gap count", "/dataset_quality/known_gap_count", _Q, None, "dataset")
    add(E.DATA_QUALITY, "active interruption start (null: no active interruption)",
        opt("/dataset_quality/active_interruption", "start_utc"), _Q, null_is_fact=True)  # 0AA-B
    for i, _ in enumerate(doc["dataset_quality"]["gaps"]):
        for leaf in ("evidence_type", "start_utc", "end_utc"):
            add(E.DATA_QUALITY, f"known gap {i + 1} {leaf}", f"/dataset_quality/gaps/{i}/{leaf}", _Q)
    add(E.DATA_QUALITY, "capture status", "/current_dataset/capture_status", _O)
    add(E.DATA_QUALITY, "lifecycle as of", "/current_dataset/lifecycle_as_of", _O)
    add(E.DATA_QUALITY, "connection as of", "/current_dataset/connection_as_of", _O)

    add(E.PRICE, "last known price", "/prices/last_known_price", _O)
    add(E.PRICE, "last known price time", "/prices/last_known_utc", _O)

    for i, v in enumerate(doc["vwap"]):
        kind = v["anchor_kind"]
        add(E.VWAP, f"{kind} VWAP", opt(f"/vwap/{i}/study", "vwap"), _D, f"vwap {kind}", f"vwap {kind}")
    for name, kind in (("last_price_vs_cash_vwap", "US_CASH_OPEN"), ("last_price_vs_globex_vwap", "SESSION_OPEN")):
        i = next(j for j, v in enumerate(doc["vwap"]) if v["anchor_kind"] == kind)
        add(E.VWAP, f"last known price vs {kind} VWAP", f"/relations/{name}", _D, f"vwap {kind}", f"vwap {kind}",
            ("/prices/last_known_price", f"/vwap/{i}/study/vwap"))

    for leaf, label in (("poc", "POC"), ("value_area_low", "value area low"), ("value_area_high", "value area high"),
                        ("profile_low", "profile low"), ("profile_high", "profile high"),
                        ("total_volume", "total volume")):
        add(E.VOLUME_PROFILE, f"volume profile {label}", f"/volume_profile/{leaf}", _D, "volume_profile",
            "volume_profile")
    add(E.VOLUME_PROFILE, "last known price vs developing volume value area",
        "/relations/last_price_vs_developing_volume_value_area", _D, "volume_profile", "volume_profile",
        ("/prices/last_known_price", "/volume_profile/value_area_low", "/volume_profile/value_area_high"))

    add(E.TPO, "TPO periods reached", "/tpo/periods_reached", _D, "tpo", "cash_tpo")
    add(E.TPO, "TPO current period", "/tpo/current_period", _D, "tpo", "cash_tpo")
    for leaf, label in (("poc", "POC"), ("value_area/low", "value area low"), ("value_area/high", "value area high"),
                        ("profile_low", "profile low"), ("profile_high", "profile high")):
        add(E.TPO, f"TPO {label}", opt("/tpo/profile", leaf), _D, "tpo", "cash_tpo")
    add(E.TPO, "last known price vs developing TPO value area", "/relations/last_price_vs_developing_tpo_value_area",
        _D, "tpo", "cash_tpo", ("/prices/last_known_price", "/tpo/profile/value_area/low",
                                "/tpo/profile/value_area/high"))

    if "initial_balance" in mat:
        add(E.INITIAL_BALANCE, "Initial Balance maturity", f"/maturity/{mat['initial_balance'][0]}/maturity", _R,
            "initial_balance")
    ib = "/tpo/profile/initial_balance" if resolve_pointer(doc, "/tpo/profile") is not None else "/tpo/profile"
    for leaf in ("high", "low", "range"):
        add(E.INITIAL_BALANCE, f"Initial Balance {leaf}", opt(ib, leaf) if ib.endswith("balance") else ib, _D,
            "initial_balance", "cash_tpo")
    add(E.INITIAL_BALANCE, "last known price vs Initial Balance", "/relations/last_price_vs_initial_balance", _D,
        "initial_balance", "cash_tpo", ("/prices/last_known_price", f"{ib}/low", f"{ib}/high"))

    add(E.PRIOR_DAY, "prior day status", "/prior_day/status", _Q, None, "prior_context")
    for leaf, label, cat in (("prior_trading_date", "prior trading date", _O), ("profile_high", "prior high", _D),
                             ("profile_low", "prior low", _D), ("value_area_high", "prior value area high", _D),
                             ("value_area_low", "prior value area low", _D), ("poc", "prior POC", _D),
                             ("terminal_price", "prior study-window terminal price", _O),
                             ("day_type", "prior DAY_TYPE_V1 candidate", _C)):
        add(E.PRIOR_DAY, label, opt("/prior_day/context", leaf), cat, None, "prior_context")
    add(E.PRIOR_DAY, "last known price vs prior value area", "/relations/last_price_vs_prior_value_area", _D, None,
        "prior_context", ("/prices/last_known_price", "/prior_day/context/value_area_low",
                          "/prior_day/context/value_area_high"))

    on = "/overnight/session" if doc["overnight"]["session"] is not None else "/overnight/developing"
    for leaf in ("high", "low"):
        add(E.OVERNIGHT, f"overnight {leaf}", opt(on, leaf), _D, "overnight", "overnight")
    add(E.OVERNIGHT, "overnight last price", opt(on, "terminal_price" if on.endswith("session") else "last_price"), _O,
        "overnight", "overnight")

    add(E.OPENING, "cash open price", opt("/cash_opening/cash_open", "price"), _O, "cash_open", "cash_opening")
    add(E.OPENING, "cash open vs prior range", "/cash_opening/range_location", _D, "cash_open", "cash_opening")
    add(E.OPENING, "cash open vs prior value", "/cash_opening/value_location", _D, "cash_open", "cash_opening")
    add(E.OPENING, "cash open gap (ticks)", "/cash_opening/gap_ticks", _D, "cash_open", "cash_opening")
    for i, w in enumerate(doc["cash_opening"]["windows"]):
        add(E.OPENING, f"opening window {w['minutes']}m maturity", f"/cash_opening/windows/{i}/maturity", _R)
    add(E.OPENING, "OPENING_TYPE_V1 status", "/opening_type/status", _Q, "opening_type", "opening_type")
    for i, m in enumerate(doc["opening_type"]["matched"]):
        add(E.OPENING, f"OPENING_TYPE_V1 candidate {i + 1}", f"/opening_type/matched/{i}/type", _C, "opening_type",
            "opening_type")
        add(E.OPENING, f"OPENING_TYPE_V1 candidate {i + 1} direction", f"/opening_type/matched/{i}/direction", _C,
            "opening_type", "opening_type")

    dt = opt("/day_type/classification", "outcome")
    add(E.DAY_TYPE, "DAY_TYPE_V1 outcome", dt, _R, "day_type", "day_type")
    if dt.endswith("outcome"):
        add(E.DAY_TYPE, "DAY_TYPE_V1 primary candidate", "/day_type/classification/primary", _C, "day_type", "day_type")
    add(E.DAY_TYPE, "study-window terminal price", "/prices/study_window_terminal_price", _O, "study_window_terminal")
    add(E.DAY_TYPE, "dominant extension", opt("/day_strength/strength", "dominant_extension"), _D, "day_strength",
        "day_strength")

    for i, m in enumerate(doc["maturity"]):
        add(E.MATURITY, f"{m['component']} maturity", f"/maturity/{i}/maturity", _R)
    return tuple(out)


def _quality_warnings(doc: dict, sha: str, role: SourceRole,
                      domains: frozenset[EvidenceDomain]) -> tuple[QualityWarning, ...]:
    """Qualified / unavailable components in the authorized domains; the dataset always propagates."""
    out = []
    for i, q in enumerate(doc["quality_matrix"]):
        domain = _DOMAIN_OF_COMPONENT.get(q["component"])
        if q["status"] == "AVAILABLE" or q["maturity"] in _NOT_YET:
            continue  # a not-yet-matured component is an availability fact, not a quality warning
        if q["component"] == "dataset" or domain in domains or (
                domain is EvidenceDomain.TPO and EvidenceDomain.INITIAL_BALANCE in domains):
            out.append(QualityWarning(f"{role.value}:{q['component']}", q["component"], q["status"],
                                      tuple(q["reasons"]), EvidenceRef(sha, f"/quality_matrix/{i}/status")))
    capture, last = doc["current_dataset"]["capture_status"], doc["prices"]["last_known_utc"]
    if EvidenceDomain.PRICE in domains and capture != "RUNNING" and last is not None:  # 0AA-B
        out.append(QualityWarning(f"{role.value}:last_known_price", "last_known_price", "STALE",
                                  (f"capture {capture} (ended {doc['current_dataset']['capture_ended_at']}); the last "
                                   f"known trade is at {last}, not at the replay time",),
                                  EvidenceRef(sha, "/current_dataset/capture_status")))
    return tuple(out)


PRICE_ACTION_DOMAINS = frozenset({EvidenceDomain.VWAP_BANDS, EvidenceDomain.REFERENCE_PATHS,
                                  EvidenceDomain.PRICE_ACTION_BARS, EvidenceDomain.VOLATILITY})
RECENT_BARS = 6


def _price_action_evidence(session: ReplaySession, snap: MarketStudySnapshot,
                           domains: frozenset[EvidenceDomain]) -> tuple[SnapshotEvidence, dict]:
    """PRICE_ACTION_FACTS_V1 for the lesson-time snapshot (same cutoff), as citable items."""
    facts = build_price_action_facts(session.replay.current, snap)
    doc, sha = mss.encode(facts), price_action_sha256(facts)
    out: list[EvidenceItem] = []
    E = EvidenceDomain

    def add(domain, label, pointer, category, maturity=None):
        if domain not in domains:
            return
        value = _scalar(resolve_pointer(doc, pointer))
        availability = (Availability.AVAILABLE if value is not None else
                        Availability.NOT_YET_AVAILABLE if maturity == Maturity.NOT_YET_AVAILABLE.value
                        else Availability.NOT_AVAILABLE)
        out.append(EvidenceItem(EvidenceRef(sha, pointer), domain, label, value, category, availability, maturity,
                                doc["status"]))

    bm = doc["bands"]["maturity"]
    add(E.VWAP_BANDS, "VWAP_BANDS_V1 maturity", "/bands/maturity", _R, bm)
    add(E.VWAP_BANDS, "cash VWAP (VWAP_BANDS_V1)", "/bands/vwap", _D, bm)
    add(E.VWAP_BANDS, "VWAP sigma (volume-weighted)", "/bands/sigma", _D, bm)
    add(E.VWAP_BANDS, "bands have zero width", "/bands/zero_width", _D, bm)
    for i, b in enumerate(doc["bands"]["bands"]):
        k = b["multiplier"]
        add(E.VWAP_BANDS, f"VWAP +{k} sigma upper band", f"/bands/bands/{i}/upper", _D, bm)
        add(E.VWAP_BANDS, f"VWAP -{k} sigma lower band", f"/bands/bands/{i}/lower", _D, bm)
    for i, z in enumerate(doc["bands"]["last_price_zones"]):
        add(E.VWAP_BANDS, f"last known price zone vs the {z[0]} sigma bands", f"/bands/last_price_zones/{i}/1", _D, bm)
    for i, o in enumerate(doc["occupancy"]):
        k = o["multiplier"]
        for leaf, label in (("observed", "observed time (s)"), ("outside_above", "time above the upper band (s)"),
                            ("outside_below", "time below the lower band (s)"),
                            ("outside_total", "time outside the bands (s)"),
                            ("fraction_outside_total", "fraction of observed time outside the bands")):
            add(E.VWAP_BANDS, f"{k} sigma bands: {label}", f"/occupancy/{i}/{leaf}", _D, bm)
    for i, r in enumerate(doc["references"]):
        name, m = r["reference"], r["maturity"]
        for leaf, label in (("level_at_clock", "level"), ("side_at_clock", "side of the last trade"),
                            ("cross_count", "cross count"), ("first_touch_utc", "first touch"),
                            ("first_cross/utc", "first cross time"), ("first_cross/direction", "first cross direction"),
                            ("last_cross/utc", "last cross time"), ("last_cross/direction", "last cross direction"),
                            ("seconds_since_last_cross", "time since the last cross (s)"),
                            ("first_close_beyond_utc", "first 5m close beyond (vs initial side)")):
            ptr = f"/references/{i}/{leaf}"
            if "/" in leaf and r[leaf.split("/")[0]] is None:
                ptr = f"/references/{i}/{leaf.split('/')[0]}"
            add(E.REFERENCE_PATHS, f"{name} {label}", ptr, _D, m)
        if r["latest_episode"] is not None:
            for leaf in ("direction", "start_utc", "max_excursion_points", "seconds_beyond", "bars_closing_beyond",
                         "max_consecutive_closes_beyond", "volume_beyond", "closest_approach_after_peak_points",
                         "touched_again_utc", "returned_utc"):
                add(E.REFERENCE_PATHS, f"{name} latest episode {leaf}", f"/references/{i}/latest_episode/{leaf}",
                    _D, m)
    bars = doc["rth_bars"]
    for i in range(max(0, len(bars) - RECENT_BARS), len(bars)):
        b = bars[i]
        tag = f"5m bar {b['start_utc'][11:16]}Z"
        add(E.PRICE_ACTION_BARS, f"{tag} maturity", f"/rth_bars/{i}/maturity", _R, b["maturity"])
        for leaf in ("open", "high", "low", "close"):
            add(E.PRICE_ACTION_BARS, f"{tag} {leaf}", f"/rth_bars/{i}/{leaf}", _O, b["maturity"])
        for leaf in ("range", "body", "upper_wick", "lower_wick", "direction", "volume", "higher_high", "lower_low",
                     "inside_bar", "outside_bar", "close_vs_vwap"):
            add(E.PRICE_ACTION_BARS, f"{tag} {leaf}", f"/rth_bars/{i}/{leaf}", _D, b["maturity"])
    am = doc["atr"]["maturity"]
    add(E.VOLATILITY, "ATR_5M_V1 maturity", "/atr/maturity", _R, am)
    add(E.VOLATILITY, "ATR_5M_V1 value (points)", "/atr/value", _D, am)
    add(E.VOLATILITY, "ATR_5M_V1 completed bars used", "/atr/completed_bars_used", _D, am)
    add(E.VOLATILITY, "ATR_5M_V1 through bar end", "/atr/through_bar_end_utc", _D, am)
    warnings = ()
    if doc["status"] != "AVAILABLE":
        warnings = (QualityWarning(f"{SourceRole.PRICE_ACTION.value}:price_action", "price_action", doc["status"],
                                   tuple(doc["reasons"]), EvidenceRef(sha, "/status")),)
        out.append(EvidenceItem(EvidenceRef(sha, "/status"), E.DATA_QUALITY, "price_action quality status",
                                doc["status"], _Q, Availability.AVAILABLE, None, doc["status"]))
    return SnapshotEvidence(SourceRole.PRICE_ACTION, sha, facts.cutoff.market_time_cutoff_utc,
                            facts.cutoff.knowledge_time_cutoff_utc, AS_OF, tuple(out), warnings), doc


def _snapshot_evidence(s: MarketStudySnapshot, role: SourceRole,
                       domains: frozenset[EvidenceDomain]) -> tuple[SnapshotEvidence, dict]:
    doc, sha = snapshot_document(s), snapshot_sha256(s)
    items, warnings = _snapshot_items(doc, sha, domains), _quality_warnings(doc, sha, role, domains)
    cited = {i.ref for i in items}
    items += tuple(EvidenceItem(w.ref, _DOMAIN_OF_COMPONENT.get(w.component, EvidenceDomain.DATA_QUALITY),
                                f"{w.component} quality status", resolve_pointer(doc, w.ref.pointer), _Q,
                                Availability.AVAILABLE, None, w.status)
                   for w in warnings if w.ref not in cited)  # a warning is itself citable evidence
    return SnapshotEvidence(role, sha, s.cutoff.market_time_cutoff_utc, s.cutoff.knowledge_time_cutoff_utc, AS_OF,
                            items, warnings), doc


_CHANGE_CATEGORY = {mss.EvidenceKind.OBSERVED_FACT: _O, mss.EvidenceKind.DERIVED_FACT: _D,
                    mss.EvidenceKind.CANDIDATE: _C, mss.EvidenceKind.QUALITY_QUALIFICATION: _Q,
                    mss.EvidenceKind.LABORATORY_POLICY: _R, mss.EvidenceKind.LABORATORY_POLICY_RESULT: _R}


def _delta_evidence(delta: MarketStudyDelta) -> tuple[DeltaEvidence, dict]:
    doc, sha = mss.encode(delta), delta_sha256(delta)
    E = EvidenceDomain.CHANGES
    items = [EvidenceItem(EvidenceRef(sha, p), E, label, _scalar(resolve_pointer(doc, p)), _O, Availability.AVAILABLE,
                          None, None)
             for p, label in (("/from_snapshot_sha256", "earlier snapshot hash"),
                              ("/to_snapshot_sha256", "later snapshot hash"))]
    if delta.newly_known is not None:
        for leaf in ("records", "with_market_time_before_earlier_market_cutoff", "max_receipt_lag_of_those",
                     "corrections", "cancels"):
            p = f"/newly_known/{leaf}"
            v = _scalar(resolve_pointer(doc, p))
            items.append(EvidenceItem(EvidenceRef(sha, p), E, f"newly known {leaf.replace('_', ' ')}", v, _O,
                                      Availability.AVAILABLE if v is not None else Availability.NOT_AVAILABLE,
                                      None, None))
    for i, ch in enumerate(delta.changes):
        cat = _CHANGE_CATEGORY[ch.evidence_kind]
        for side in ("before", "after"):
            p = f"/changes/{i}/{side}"
            items.append(EvidenceItem(EvidenceRef(sha, p), E, f"{ch.kind.value} {ch.path} ({side})",
                                      _scalar(resolve_pointer(doc, p)), cat, Availability.AVAILABLE,
                                      ch.maturity_after, ch.status_after, (f"/changes/{i}/kind",)))
    return DeltaEvidence(sha, delta.from_snapshot_sha256, delta.to_snapshot_sha256, tuple(items)), doc


# --- lessons --------------------------------------------------------------------------------------

@dataclass(frozen=True)
class QuestionSpec:
    kind: QuestionKind
    required_domains: tuple[EvidenceDomain, ...]
    compares: bool
    uses_value_area: bool


QUESTION_SPECS = {s.kind: s for s in (
    QuestionSpec(QuestionKind.PRICE_VS_CASH_VWAP, (EvidenceDomain.PRICE, EvidenceDomain.VWAP), False, False),
    QuestionSpec(QuestionKind.INITIAL_BALANCE_STATUS, (EvidenceDomain.INITIAL_BALANCE,), False, False),
    QuestionSpec(QuestionKind.EVIDENCE_CHANGES, (EvidenceDomain.CHANGES,), True, False),
    QuestionSpec(QuestionKind.VALUE_MIGRATION, (EvidenceDomain.VOLUME_PROFILE, EvidenceDomain.TPO), True, True),
    QuestionSpec(QuestionKind.VALUE_OCCUPANCY, (EvidenceDomain.PRICE, EvidenceDomain.VOLUME_PROFILE), False, True),
    QuestionSpec(QuestionKind.VWAP_ACCEPTANCE, (EvidenceDomain.PRICE, EvidenceDomain.VWAP), False, False),
    QuestionSpec(QuestionKind.NOT_YET_DETERMINED_ITEMS, (EvidenceDomain.MATURITY,), False, False),
    QuestionSpec(QuestionKind.DATA_QUALITY, (EvidenceDomain.DATA_QUALITY,), False, False),
)}


@dataclass(frozen=True)
class LessonDefinition:
    """Authored lesson; needs no AI model. Times are explicit UTC instants on one trading date."""

    lesson_id: str
    title: str
    objective: str
    mode: LessonMode
    question_kind: QuestionKind
    question: str
    trading_date: date
    at: datetime  # the student's replay time (market and knowledge cutoff)
    allowed_domains: tuple[EvidenceDomain, ...]
    curriculum_module_id: str
    curriculum_source_ids: tuple[str, ...]
    value_area_convention_id: str | None = None
    compare_from: datetime | None = None
    reveal_at: datetime | None = None  # hidden future outcome (instructor-only until POST_REVEAL)
    hints: tuple[str, ...] = ()
    reveal_policy: str = REVEAL_POLICY
    dataset_id: UUID | None = None

    def __post_init__(self) -> None:
        for name in ("at", "compare_from", "reveal_at"):
            t = getattr(self, name)
            if t is not None and t.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware")
        spec = QUESTION_SPECS[self.question_kind]
        if spec.compares != (self.compare_from is not None):
            raise ValueError(f"{self.question_kind.value} {'needs' if spec.compares else 'takes no'} compare_from")
        if self.compare_from is not None and not self.compare_from < self.at:
            raise ValueError("compare_from must be before the lesson time")
        if self.reveal_at is not None and not self.reveal_at > self.at:
            raise ValueError("reveal_at must be after the lesson time")
        missing = set(spec.required_domains) - set(self.allowed_domains)
        if missing:
            raise ValueError(f"{self.question_kind.value} needs domains {sorted(missing)}")
        if spec.uses_value_area and self.value_area_convention_id is None:
            raise ValueAreaConventionError(f"{self.question_kind.value} uses a value area: state its convention")
        if self.value_area_convention_id is not None and self.value_area_convention_id not in _CONVENTIONS:
            raise ValueAreaConventionError(f"unknown value-area convention {self.value_area_convention_id!r}")
        unknown = [s for s in self.curriculum_source_ids if s not in _SOURCES]
        if unknown:
            raise ValueError(f"unknown curriculum sources {unknown}")
        if self.reveal_policy != REVEAL_POLICY:
            raise ValueError(f"unsupported reveal policy {self.reveal_policy!r}")


@dataclass(frozen=True)
class ExpectedObservation:
    observation_id: str
    statement: str
    category: ClaimCategory
    refs: tuple[EvidenceRef, ...]
    value: Scalar


@dataclass(frozen=True)
class IncorrectClaim:
    claim_id: str
    statement: str
    support: EvidenceSupport  # what the evidence actually says about it (never FALSE for missing evidence)
    why: str
    refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class GradingRubric:
    """What an eventual grader must check. No natural-language grading is implemented."""

    required_evidence_refs: tuple[EvidenceRef, ...]
    acceptable_observation_ids: tuple[str, ...]
    common_incorrect_claims: tuple[IncorrectClaim, ...]
    quality_caveats: tuple[str, ...]  # warning ids an answer must preserve
    insufficient_evidence_is_correct: bool


@dataclass(frozen=True)
class AssertedValue:
    ref: EvidenceRef
    value: Scalar


@dataclass(frozen=True)
class TutorClaim:
    statement: str
    category: ClaimCategory
    evidence_refs: tuple[EvidenceRef, ...]
    asserted: tuple[AssertedValue, ...] = ()
    curriculum_source_id: str | None = None  # required for CURRICULUM_RULE


@dataclass(frozen=True)
class UnsupportedClaim:
    statement: str
    support: EvidenceSupport  # INSUFFICIENT_EVIDENCE / NOT_YET_DETERMINED / NOT_YET_AVAILABLE, never SUPPORTED
    missing: tuple[str, ...]  # missing evidence, implementation or policy
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class TutorAnswer:
    """The constrained target for a future model answer (none is generated here)."""

    schema: str
    lesson_id: str
    stage: LessonStage
    snapshot_sha256: str
    answer_text: str
    claims: tuple[TutorClaim, ...]
    uncertainties: tuple[str, ...]
    quality_warnings: tuple[str, ...]  # warning ids acknowledged
    unsupported_claims: tuple[UnsupportedClaim, ...]


@dataclass(frozen=True)
class AnswerKey:
    question_kind: QuestionKind
    support: EvidenceSupport
    summary: Scalar
    observations: tuple[ExpectedObservation, ...]
    missing_dependencies: tuple[str, ...]
    rubric: GradingRubric
    reference_answer: TutorAnswer  # deterministic, grounded in the QUESTION-stage student evidence


@dataclass(frozen=True)
class FutureOutcome:
    """Evidence at a later replay time. Instructor-only until POST_REVEAL."""

    evidence: SnapshotEvidence
    observations: tuple[ExpectedObservation, ...]
    summary: Scalar


@dataclass(frozen=True)
class TutorLesson:
    schema: str
    definition: LessonDefinition
    definition_sha256: str
    context: TutorEvidenceContext
    answer_key: AnswerKey
    future_outcome: FutureOutcome | None
    _documents: tuple[tuple[str, dict], ...] = field(default=(), compare=False, repr=False)  # not serialized

    def document(self, sha: str) -> dict | None:
        return dict(self._documents).get(sha)


def lesson_definition_sha256(d: LessonDefinition) -> str:
    return hashlib.sha256(mss._dumps(mss.encode(d)).encode("ascii")).hexdigest()


def _find(items, pointer: str, sha: str | None = None) -> EvidenceItem | None:
    return next((i for i in items if i.ref.pointer == pointer and (sha is None or i.ref.source_sha256 == sha)), None)


def _obs(oid, statement, category, items, value=None) -> ExpectedObservation:
    return ExpectedObservation(oid, statement, category, tuple(i.ref for i in items), value)


def _key_for(kind: QuestionKind, snap: SnapshotEvidence, earlier: SnapshotEvidence | None,
             delta: DeltaEvidence | None, warnings: tuple[QualityWarning, ...]):
    """(support, summary, observations, missing, incorrect claims) — deterministic, from evidence only."""
    items = snap.items
    obs: list[ExpectedObservation] = []
    wrong: list[IncorrectClaim] = []
    missing: tuple[str, ...] = ()
    if kind is QuestionKind.PRICE_VS_CASH_VWAP:
        price = _find(items, "/prices/last_known_price")
        vwap = next(i for i in items if i.label == "US_CASH_OPEN VWAP")
        rel = _find(items, "/relations/last_price_vs_cash_vwap")
        wrong.append(IncorrectClaim("ACCEPTANCE", "Price is accepting above (or below) the cash VWAP.",
                                    EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                    "acceptance has no deterministic definition (NEEDS_POLICY_DEFINITION)"))
        wrong.append(IncorrectClaim("VWAP_BANDS", "Price is inside (or outside) the VWAP value bands.",
                                    EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                    "VWAP deviation bands are not defined (NEEDS_POLICY_DEFINITION)"))
        if rel.value is None:
            support = {Availability.NOT_YET_AVAILABLE: EvidenceSupport.NOT_YET_AVAILABLE,
                       Availability.NOT_YET_DETERMINED: EvidenceSupport.NOT_YET_DETERMINED}.get(
                vwap.availability, EvidenceSupport.INSUFFICIENT_EVIDENCE)
            return support, None, (), ("cash VWAP" if vwap.value is None else "last known price",), tuple(wrong)
        when = _find(items, "/prices/last_known_utc")
        capture = _find(items, "/current_dataset/capture_status")
        if capture is not None and capture.value != "RUNNING":
            wrong.append(IncorrectClaim("PRICE_AT_LESSON_TIME", "The last known price is the price at the lesson time.",
                                        EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                        f"capture is {capture.value}; the last known trade is at {when.value}",
                                        (capture.ref, when.ref)))
        obs += [_obs("PRICE", f"The last known price is {price.value} (traded at {when.value}).", _O, [price, when],
                     price.value),
                _obs("CASH_VWAP", f"The cash VWAP is {vwap.value} ({vwap.maturity}).", _D, [vwap], vwap.value),
                _obs("RELATION", f"The last known price is {rel.value} the cash VWAP.", _D, [rel, price, vwap],
                     rel.value)]
        if vwap.maturity == Maturity.DEVELOPING.value:
            wrong.append(IncorrectClaim("VWAP_COMPLETE", "The cash VWAP value is complete for the day.",
                                        EvidenceSupport.NOT_YET_DETERMINED, "its maturity is DEVELOPING", (vwap.ref,)))
        return EvidenceSupport.SUPPORTED, rel.value, tuple(obs), missing, tuple(wrong)
    if kind is QuestionKind.INITIAL_BALANCE_STATUS:
        m = next(i for i in items if i.label == "Initial Balance maturity")
        hi, lo = _find(items, "/tpo/profile/initial_balance/high"), _find(items, "/tpo/profile/initial_balance/low")
        complete = m.value == Maturity.WINDOW_COMPLETE.value
        summary = "COMPLETE" if complete else m.value
        obs.append(_obs("IB_MATURITY", f"The Initial Balance maturity is {m.value}.", _R, [m], m.value))
        if hi is not None and lo is not None and hi.value is not None:
            word = "complete" if complete else "so far"
            obs.append(_obs("IB_RANGE", f"The Initial Balance {word} is {lo.value} - {hi.value}.", _D, [lo, hi],
                            f"{lo.value}-{hi.value}"))
        if complete:
            wrong.append(IncorrectClaim("IB_FINAL", "The Initial Balance can no longer change in this record.",
                                        EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                        "COMPLETE means its market window ended; later-received records may still "
                                        "revise it", (m.ref,)))
        else:
            wrong.append(IncorrectClaim("IB_COMPLETE", "The Initial Balance is complete.",
                                        EvidenceSupport.NOT_YET_DETERMINED, f"its maturity is {m.value}", (m.ref,)))
        return EvidenceSupport.SUPPORTED, summary, tuple(obs), missing, tuple(wrong)
    if kind is QuestionKind.EVIDENCE_CHANGES:
        d = delta.items
        a, b = _find(d, "/from_snapshot_sha256"), _find(d, "/to_snapshot_sha256")
        changed = a.value != b.value
        obs.append(_obs("STATE_HASH", f"The snapshot hash {'changed' if changed else 'did not change'}.", _O, [a, b],
                        changed))
        late = _find(d, "/newly_known/with_market_time_before_earlier_market_cutoff")
        n = _find(d, "/newly_known/records")
        if n is not None:
            obs.append(_obs("NEWLY_KNOWN", f"{n.value} source records became known.", _O, [n], n.value))
        if late is not None and late.value:
            lag = _find(d, "/newly_known/max_receipt_lag_of_those")
            obs.append(_obs("LATE_OBSERVATIONS", f"{late.value} newly known records have market times before the "
                            f"earlier cutoff (received up to {lag.value} s late).", _O, [late, lag], late.value))
            wrong.append(IncorrectClaim("LATE_AS_NEW_ACTIVITY",
                                        "The newly known trades are new market activity after the earlier time.",
                                        EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                        "their market times are before the earlier cutoff; they were received late",
                                        (late.ref,)))
        changes = [i for i in d if i.ref.pointer.startswith("/changes/") and i.ref.pointer.endswith("/after")]
        for i, after in enumerate(changes):
            before = _find(d, after.ref.pointer[:-len("after")] + "before")
            label = after.label[:-len(" (after)")]
            obs.append(_obs(f"CHANGE_{i + 1}", f"{label}: {before.value} -> {after.value}", after.category,
                            [before, after], after.value))
        return EvidenceSupport.SUPPORTED, len(changes), tuple(obs), missing, tuple(wrong)
    if kind is QuestionKind.VALUE_MIGRATION:
        moved = []
        for p, label in (("/volume_profile/poc", "volume POC"), ("/volume_profile/value_area_low", "volume VAL"),
                         ("/volume_profile/value_area_high", "volume VAH"), ("/tpo/profile/poc", "TPO POC"),
                         ("/tpo/profile/value_area/low", "TPO VAL"), ("/tpo/profile/value_area/high", "TPO VAH")):
            x, y = _find(earlier.items, p), _find(items, p)
            if x is None or y is None or x.value is None or y.value is None:
                continue
            dx = Decimal(y.value) - Decimal(x.value)
            word = "HIGHER" if dx > 0 else "LOWER" if dx < 0 else "UNCHANGED"
            moved.append(word)
            obs.append(_obs(f"{label.replace(' ', '_').upper()}", f"Developing {label}: {x.value} -> {y.value} "
                            f"({word}).", _D, [x, y], word))
        wrong.append(IncorrectClaim("PLAYBOOK_68", "These are 68% (playbook / NinjaTrader) value levels.",
                                    EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                    "Laboratory value areas use the 70% convention; 68% values are not computed"))
        if not obs:
            return EvidenceSupport.INSUFFICIENT_EVIDENCE, None, (), ("developing value at both times",), tuple(wrong)
        summary = moved[0] if len(set(moved)) == 1 else "MIXED"
        return EvidenceSupport.SUPPORTED, summary, tuple(obs), missing, tuple(wrong)
    if kind is QuestionKind.VWAP_ACCEPTANCE:
        rel = _find(items, "/relations/last_price_vs_cash_vwap")
        if rel.value is not None:
            obs.append(_obs("CURRENT_RELATION", f"The last known price is {rel.value} the cash VWAP.", _D, [rel],
                            rel.value))
        wrong.append(IncorrectClaim("ACCEPTANCE", "Price is accepting above (or below) the cash VWAP.",
                                    EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                    "acceptance has no deterministic definition (NEEDS_POLICY_DEFINITION); being "
                                    "above or below VWAP at one instant is not acceptance"))
        return (EvidenceSupport.INSUFFICIENT_EVIDENCE, None, tuple(obs), ("acceptance (NEEDS_POLICY_DEFINITION)",),
                tuple(wrong))
    if kind is QuestionKind.VALUE_OCCUPANCY:
        rel = _find(items, "/relations/last_price_vs_developing_volume_value_area")
        if rel.value is not None:
            obs.append(_obs("CURRENT_RELATION", f"Right now the last known price is {rel.value} the developing volume "
                            "value area.", _D, [rel], rel.value))
        wrong.append(IncorrectClaim("REMAINED", "Price has remained inside (or outside) value throughout.",
                                    EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                    "time outside value is not implemented (NEEDS_IMPLEMENTATION); a single relation "
                                    "at one instant says nothing about the path"))
        return (EvidenceSupport.INSUFFICIENT_EVIDENCE, None, tuple(obs), ("time outside value (NEEDS_IMPLEMENTATION)",),
                tuple(wrong))
    if kind is QuestionKind.NOT_YET_DETERMINED_ITEMS:
        pending = [i for i in items if i.domain is EvidenceDomain.MATURITY and i.value in _NOT_YET]
        for i in pending:
            obs.append(_obs(f"PENDING_{i.label.split(' maturity')[0].upper().replace(' ', '_')}",
                            f"{i.label} is {i.value}.", _R, [i], i.value))
            wrong.append(IncorrectClaim(f"DETERMINED_{i.label.split(' maturity')[0].upper().replace(' ', '_')}",
                                        f"The {i.label.split(' maturity')[0]} result is already known.",
                                        EvidenceSupport(i.value), f"its maturity is {i.value}", (i.ref,)))
        return EvidenceSupport.SUPPORTED, len(pending), tuple(obs), missing, tuple(wrong)
    if kind is QuestionKind.DATA_QUALITY:
        status = _find(items, "/dataset_quality/status")
        comp = _find(items, "/dataset_quality/completeness")
        gaps = _find(items, "/dataset_quality/known_gap_count")
        obs += [_obs("STATUS", f"The dataset quality status is {status.value}.", _Q, [status], status.value),
                _obs("COMPLETENESS", f"Completeness: {comp.value}.", _Q, [comp], comp.value),
                _obs("KNOWN_GAPS", f"{gaps.value} known gaps.", _Q, [gaps], gaps.value)]
        for w in warnings:
            obs.append(ExpectedObservation(f"WARNING_{w.component.upper().replace(' ', '_')}",
                                           f"{w.component} is {w.status}: {'; '.join(w.reasons) or 'no reason'}",
                                           _Q, (w.ref,), w.status))
        if status.value != "AVAILABLE":
            wrong.append(IncorrectClaim("PRISTINE", "The evidence is complete and unqualified.",
                                        EvidenceSupport.INSUFFICIENT_EVIDENCE,
                                        f"dataset quality status is {status.value}", (status.ref,)))
        return EvidenceSupport.SUPPORTED, status.value, tuple(obs), missing, tuple(wrong)
    raise ValueError(kind)


def _reference_answer(lesson_id: str, sha: str, support: EvidenceSupport, summary, observations, missing,
                      wrong: tuple[IncorrectClaim, ...], warnings: tuple[QualityWarning, ...],
                      items: dict[EvidenceRef, EvidenceItem]) -> TutorAnswer:
    claims = tuple(TutorClaim(o.statement, o.category, o.refs,
                              (AssertedValue(o.refs[0], items[o.refs[0]].value),) if o.refs[0] in items else ())
                   for o in observations)
    unsupported = [UnsupportedClaim(w.statement, w.support, (w.why,), w.refs) for w in wrong
                   if w.support is not EvidenceSupport.SUPPORTED]
    if support is not EvidenceSupport.SUPPORTED:
        unsupported.insert(0, UnsupportedClaim("The question cannot be answered from the authorized evidence.",
                                               support, missing))
    text = (f"Evidence answer: {summary}." if support is EvidenceSupport.SUPPORTED
            else f"{support.value}: {', '.join(missing)}.")
    return TutorAnswer(ANSWER_SCHEMA, lesson_id, LessonStage.QUESTION, sha, text, claims,
                       tuple(f"{w.component}: {w.status}" for w in warnings), tuple(w.warning_id for w in warnings),
                       tuple(unsupported))


def build_tutor_lesson(session: ReplaySession, definition: LessonDefinition) -> TutorLesson:
    """Select authorized AS_OF evidence for one lesson from the session's snapshots."""
    require_executable(definition.curriculum_module_id)
    if definition.trading_date != session.trading_date:
        raise ValueError("the lesson's trading date is not this session's")
    domains = frozenset(definition.allowed_domains)
    snap = session.snapshot(definition.at)
    dataset_id = snap.current_dataset.dataset_id
    if definition.dataset_id is not None and definition.dataset_id != dataset_id:
        raise ValueError("the lesson's dataset is not this session's")
    convention = _CONVENTIONS.get(definition.value_area_convention_id)
    if convention is not None:
        _check_convention(convention, snap)
    docs: list[tuple[str, dict]] = []
    evidence: list[SnapshotEvidence] = []
    earlier = None
    if definition.compare_from is not None:
        earlier, doc = _snapshot_evidence(session.snapshot(definition.compare_from), SourceRole.COMPARE_FROM, domains)
        evidence.append(earlier)
        docs.append((earlier.snapshot_sha256, doc))
    current, doc = _snapshot_evidence(snap, SourceRole.LESSON_TIME, domains)
    evidence.append(current)
    docs.append((current.snapshot_sha256, doc))
    if domains & PRICE_ACTION_DOMAINS:
        pa, pdoc = _price_action_evidence(session, snap, domains)
        evidence.append(pa)
        docs.append((pa.snapshot_sha256, pdoc))
    delta = None
    if definition.compare_from is not None and EvidenceDomain.CHANGES in domains:
        delta, ddoc = _delta_evidence(session.compare(definition.compare_from, definition.at))
        docs.append((delta.delta_sha256, ddoc))
    warnings = tuple(w for e in evidence for w in e.quality_warnings)
    sources = tuple(dict.fromkeys((LAB_SOURCE.source_id, *definition.curriculum_source_ids)))
    context = TutorEvidenceContext(
        CONTEXT_SCHEMA, definition.lesson_id, session.trading_date, dataset_id, snap.current_dataset.instrument_id,
        AS_OF, current.replay_market_time, current.replay_knowledge_time, current.snapshot_sha256,
        tuple(sorted(domains)), tuple(evidence), delta, warnings,
        tuple(PolicyRef(p.component, p.policy_id, p.policy_version) for p in snap.policy_registry), convention,
        sources)
    kind = definition.question_kind
    support, summary, observations, missing, wrong = _key_for(kind, current, earlier, delta, warnings)
    by_ref = {i.ref: i for i in context.items()}
    caveats = tuple(w.warning_id for w in warnings)
    rubric = GradingRubric(tuple(dict.fromkeys(r for o in observations for r in o.refs)),
                           tuple(o.observation_id for o in observations), wrong, caveats,
                           support is not EvidenceSupport.SUPPORTED)
    key = AnswerKey(kind, support, summary, observations, missing, rubric,
                    _reference_answer(definition.lesson_id, current.snapshot_sha256, support, summary, observations,
                                      missing, wrong, warnings, by_ref))
    future = None
    if definition.reveal_at is not None:
        later, fdoc = _snapshot_evidence(session.snapshot(definition.reveal_at), SourceRole.FUTURE_OUTCOME, domains)
        docs.append((later.snapshot_sha256, fdoc))
        if QUESTION_SPECS[kind].compares:
            fobs, fsum = (), None
        else:
            _, fsum, fobs, _, _ = _key_for(kind, later, None, None, later.quality_warnings)
        future = FutureOutcome(later, fobs, fsum)
    return TutorLesson(LESSON_SCHEMA, definition, lesson_definition_sha256(definition), context, key, future,
                       tuple(docs))


def _check_convention(convention: ValueAreaConvention, snap: MarketStudySnapshot) -> None:
    """A lesson's stated convention must be the one its evidence was computed with. Never converted."""
    fractions = {snap.volume_profile.value_area_target_fraction}
    if snap.tpo.profile is not None:
        fractions.add(snap.tpo.profile.value_area.target_fraction)
    if not convention.computed_by_laboratory or fractions != {convention.fraction}:
        raise ValueAreaConventionError(
            f"{convention.convention_id} ({convention.fraction}) does not describe this Laboratory evidence "
            f"(computed at {', '.join(sorted(format(f, 'f') for f in fractions))}); conventions are not converted")


# --- views ----------------------------------------------------------------------------------------

def _hashed(payload: dict) -> dict:
    payload = dict(payload)
    payload[PAYLOAD_HASH_FIELD] = hashlib.sha256(mss._dumps(payload).encode("ascii")).hexdigest()
    return payload


def _public_definition(d: LessonDefinition) -> dict:
    return {"lesson_id": d.lesson_id, "title": d.title, "objective": d.objective, "mode": d.mode.value,
            "question_kind": d.question_kind.value, "question": d.question, "trading_date": d.trading_date.isoformat(),
            "replay_time": mss.encode(d.at), "compare_from": mss.encode(d.compare_from),
            "allowed_domains": sorted(x.value for x in d.allowed_domains),
            "curriculum_module_id": d.curriculum_module_id, "value_area_convention_id": d.value_area_convention_id,
            "reveal_policy": d.reveal_policy}


def student_view(lesson: TutorLesson, stage: LessonStage = LessonStage.QUESTION) -> dict:
    """What the student (and a model talking to the student) may see at `stage`. Names withheld material only."""
    payload = {
        "schema": STUDENT_VIEW_SCHEMA, "audience": "STUDENT", "stage": stage.value,
        "lesson": _public_definition(lesson.definition), "lesson_definition_sha256": lesson.definition_sha256,
        "curriculum_sources": mss.encode(tuple(_SOURCES[s] for s in lesson.context.curriculum_source_ids)),
        "context": mss.encode(lesson.context),
    }
    withheld = []
    for material, at in REVEAL_SCHEDULE:
        value = {"hints": lesson.definition.hints, "answer_key": lesson.answer_key,
                 "future_outcome": lesson.future_outcome}[material]
        if material == "future_outcome" and value is None:
            continue
        if _reached(stage, at):
            payload[material] = mss.encode(value)
        else:
            withheld.append(material)
    payload["withheld"] = withheld
    return _hashed(payload)


def instructor_view(lesson: TutorLesson) -> dict:
    """Everything, including deterministic grading material and any hidden future outcome."""
    return _hashed({
        "schema": INSTRUCTOR_VIEW_SCHEMA, "audience": "INSTRUCTOR", "lesson": mss.encode(lesson.definition),
        "lesson_definition_sha256": lesson.definition_sha256,
        "curriculum_sources": mss.encode(tuple(_SOURCES[s] for s in lesson.context.curriculum_source_ids)),
        "context": mss.encode(lesson.context), "answer_key": mss.encode(lesson.answer_key),
        "future_outcome": mss.encode(lesson.future_outcome),
        "reveal_schedule": [[m, s.value] for m, s in REVEAL_SCHEDULE],
    })


def canonical_json(payload: dict) -> str:
    return mss._dumps(payload)


def verify_payload(payload: dict) -> bool:
    body = dict(payload)
    claimed = body.pop(PAYLOAD_HASH_FIELD, None)
    return claimed == hashlib.sha256(mss._dumps(body).encode("ascii")).hexdigest()


# --- grounding validation -------------------------------------------------------------------------

class GroundingIssueCode(StrEnum):
    WRONG_LESSON = "WRONG_LESSON"
    WRONG_SNAPSHOT = "WRONG_SNAPSHOT"
    UNKNOWN_EVIDENCE = "UNKNOWN_EVIDENCE"  # no such source or path
    UNAUTHORIZED_EVIDENCE = "UNAUTHORIZED_EVIDENCE"  # exists in a lesson source, outside the authorized domains
    HIDDEN_FUTURE_EVIDENCE = "HIDDEN_FUTURE_EVIDENCE"  # the future outcome before POST_REVEAL
    EVIDENCE_NOT_AVAILABLE = "EVIDENCE_NOT_AVAILABLE"  # cited as support while absent / not yet determined
    UNGROUNDED_CLAIM = "UNGROUNDED_CLAIM"
    CATEGORY_NOT_SUPPORTED = "CATEGORY_NOT_SUPPORTED"  # e.g. an interpretation labeled as an observed fact
    VALUE_MISMATCH = "VALUE_MISMATCH"
    QUALITY_WARNING_OMITTED = "QUALITY_WARNING_OMITTED"
    UNKNOWN_QUALITY_WARNING = "UNKNOWN_QUALITY_WARNING"
    UNSUPPORTED_MARKED_SUPPORTED = "UNSUPPORTED_MARKED_SUPPORTED"
    CURRICULUM_SOURCE_INVALID = "CURRICULUM_SOURCE_INVALID"


@dataclass(frozen=True)
class GroundingIssue:
    code: GroundingIssueCode
    where: str
    ref: str | None
    detail: str


@dataclass(frozen=True)
class GroundingReport:
    valid: bool
    stage: LessonStage
    checked_refs: int
    interpretations: int  # AI_INTERPRETATION claims (allowed, grounded, never evidence)
    issues: tuple[GroundingIssue, ...]


def authorized_items(lesson: TutorLesson, stage: LessonStage) -> dict[EvidenceRef, EvidenceItem]:
    items = list(lesson.context.items())
    if lesson.future_outcome is not None and _reached(stage, LessonStage.POST_REVEAL):
        items += lesson.future_outcome.evidence.items
    return {i.ref: i for i in items}


def validate_answer_grounding(answer: TutorAnswer, lesson: TutorLesson) -> GroundingReport:
    """Deterministic checks a future model answer must pass at its stage. No semantic grading."""
    stage = answer.stage
    allowed = authorized_items(lesson, stage)
    warnings = {w.warning_id for w in lesson.context.quality_warnings}
    if lesson.future_outcome is not None and _reached(stage, LessonStage.POST_REVEAL):
        warnings |= {w.warning_id for w in lesson.future_outcome.evidence.quality_warnings}
    future_sha = lesson.future_outcome.evidence.snapshot_sha256 if lesson.future_outcome else None
    issues: list[GroundingIssue] = []
    checked = 0

    def issue(code, where, ref, detail):
        issues.append(GroundingIssue(code, where, str(ref) if ref is not None else None, detail))

    def check_ref(ref: EvidenceRef, where: str, as_support: bool) -> EvidenceItem | None:
        nonlocal checked
        checked += 1
        item = allowed.get(ref)
        if item is not None:
            if as_support and item.availability is not Availability.AVAILABLE:
                issue(GroundingIssueCode.EVIDENCE_NOT_AVAILABLE, where, ref,
                      f"{item.label} is {item.availability.value} at the replay time")
            return item
        if ref.source_sha256 == future_sha:
            issue(GroundingIssueCode.HIDDEN_FUTURE_EVIDENCE, where, ref,
                  f"future outcome evidence is hidden until {LessonStage.POST_REVEAL.value}")
            return None
        doc = lesson.document(ref.source_sha256)
        try:
            if doc is None:
                raise KeyError(ref.pointer)
            resolve_pointer(doc, ref.pointer)
        except KeyError:
            issue(GroundingIssueCode.UNKNOWN_EVIDENCE, where, ref, "no such lesson source or evidence path")
            return None
        issue(GroundingIssueCode.UNAUTHORIZED_EVIDENCE, where, ref, "exists but is not authorized for this lesson")
        return None

    if answer.lesson_id != lesson.definition.lesson_id:
        issue(GroundingIssueCode.WRONG_LESSON, "answer", None, answer.lesson_id)
    if answer.snapshot_sha256 != lesson.context.snapshot_sha256:
        issue(GroundingIssueCode.WRONG_SNAPSHOT, "answer", None, answer.snapshot_sha256)
    interpretations = 0
    for n, claim in enumerate(answer.claims):
        where = f"claims[{n}]"
        if claim.category is ClaimCategory.CURRICULUM_RULE:
            if claim.curriculum_source_id not in lesson.context.curriculum_source_ids:
                issue(GroundingIssueCode.CURRICULUM_SOURCE_INVALID, where, None,
                      f"{claim.curriculum_source_id!r} is not a source of this lesson")
        elif claim.curriculum_source_id is not None:
            issue(GroundingIssueCode.CURRICULUM_SOURCE_INVALID, where, None,
                  "only CURRICULUM_RULE claims cite a curriculum source")
        if claim.category is ClaimCategory.AI_INTERPRETATION:
            interpretations += 1
        if not claim.evidence_refs and claim.category is not ClaimCategory.CURRICULUM_RULE:
            issue(GroundingIssueCode.UNGROUNDED_CLAIM, where, None, f"{claim.category.value} claim cites no evidence")
        cited = [check_ref(r, where, True) for r in claim.evidence_refs]
        cited = [c for c in cited if c is not None]
        if claim.category in EVIDENCE_CATEGORIES and cited and claim.category not in {c.category for c in cited}:
            issue(GroundingIssueCode.CATEGORY_NOT_SUPPORTED, where, None,
                  f"{claim.category.value} not among the cited evidence categories "
                  f"{sorted({c.category.value for c in cited})}")
        for a in claim.asserted:
            if a.ref not in claim.evidence_refs:
                issue(GroundingIssueCode.UNGROUNDED_CLAIM, where, a.ref, "asserted value for an uncited reference")
            elif a.ref in allowed and allowed[a.ref].value != a.value:
                issue(GroundingIssueCode.VALUE_MISMATCH, where, a.ref,
                      f"asserted {a.value!r}, evidence {allowed[a.ref].value!r}")
    for n, u in enumerate(answer.unsupported_claims):
        if u.support is EvidenceSupport.SUPPORTED:
            issue(GroundingIssueCode.UNSUPPORTED_MARKED_SUPPORTED, f"unsupported_claims[{n}]", None, u.statement)
        for r in u.evidence_refs:
            check_ref(r, f"unsupported_claims[{n}]", False)
    for w in sorted(warnings - set(answer.quality_warnings)):
        issue(GroundingIssueCode.QUALITY_WARNING_OMITTED, "quality_warnings", None, w)
    for w in sorted(set(answer.quality_warnings) - warnings):
        issue(GroundingIssueCode.UNKNOWN_QUALITY_WARNING, "quality_warnings", None, w)
    return GroundingReport(not issues, stage, checked, interpretations, tuple(issues))


def rubric_ref_coverage(answer: TutorAnswer, lesson: TutorLesson) -> tuple[tuple[EvidenceRef, ...], tuple[EvidenceRef, ...]]:
    """(cited, missing) required evidence refs. Reference coverage only; not a grade."""
    cited = {r for c in answer.claims for r in c.evidence_refs}
    required = lesson.answer_key.rubric.required_evidence_refs
    return tuple(r for r in required if r in cited), tuple(r for r in required if r not in cited)


# --- session record (design only; not persisted in 0AA-A) ------------------------------------------

class GradingOutcome(StrEnum):
    NOT_GRADED = "NOT_GRADED"  # 0AA-A implements no grading


@dataclass(frozen=True)
class TutorSessionRecord:
    """What a future tutor session would record. Belongs in a separate tutor store, never in a dataset DB."""

    schema: str
    lesson_id: str
    lesson_definition_sha256: str
    stage: LessonStage
    snapshot_sha256: str
    student_view_sha256: str
    student_response: str | None
    tutor_response: TutorAnswer | None
    evidence_refs: tuple[EvidenceRef, ...]
    grounding: GroundingReport | None
    grading_outcome: GradingOutcome


# --- example lessons (LAB_EVIDENCE_READING_V1) -----------------------------------------------------

_EXAMPLES = {
    QuestionKind.PRICE_VS_CASH_VWAP: (
        LessonMode.OBSERVE, "Price relative to the cash VWAP",
        "Read the last known price and the developing cash VWAP as of the replay time.",
        "Where is the last known price relative to the cash VWAP, and what evidence supports the answer?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.PRICE, EvidenceDomain.VWAP), None,
        ("Compare /prices/last_known_price with the US_CASH_OPEN VWAP.", "Check the VWAP maturity marker.")),
    QuestionKind.INITIAL_BALANCE_STATUS: (
        LessonMode.IDENTIFY, "Initial Balance maturity",
        "Tell a developing Initial Balance from a complete one.",
        "Is the Initial Balance complete yet?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.INITIAL_BALANCE), None,
        ("Read the initial_balance row of the maturity table.", "The Initial Balance window is 08:30-09:30 CT.")),
    QuestionKind.EVIDENCE_CHANGES: (
        LessonMode.COMPARE, "What changed in the evidence",
        "Read a MARKET_STUDY_DELTA_V1 between two replay times.",
        "What changed in the evidence between the two times?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.CHANGES), None,
        ("Start with the newly known records.", "Check whether their market times are before the earlier time.")),
    QuestionKind.VALUE_MIGRATION: (
        LessonMode.COMPARE, "Developing value between two times",
        "Compare developing volume and TPO value between two replay times.",
        "What changed in developing value between the two times?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.VOLUME_PROFILE, EvidenceDomain.TPO, EvidenceDomain.CHANGES),
        LABORATORY_PROFILE_70.convention_id,
        ("Compare POC, VAL and VAH at both times.", "These value areas use the Laboratory 70% convention.")),
    QuestionKind.VALUE_OCCUPANCY: (
        LessonMode.EXPLAIN_EVIDENCE, "Inside or outside value",
        "Separate what one snapshot shows from what it cannot show.",
        "Has price remained inside or outside value?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.PRICE, EvidenceDomain.VOLUME_PROFILE),
        LABORATORY_PROFILE_70.convention_id,
        ("What does the current relation show?", "Is there evidence about the path since the open?")),
    QuestionKind.VWAP_ACCEPTANCE: (
        LessonMode.EXPLAIN_EVIDENCE, "Acceptance and the cash VWAP",
        "Separate a defined fact (price relative to VWAP) from an undefined concept (acceptance).",
        "Is price accepting above the cash VWAP?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.PRICE, EvidenceDomain.VWAP), None,
        ("What does the evidence define about price and VWAP?", "Is acceptance defined anywhere in the evidence?")),
    QuestionKind.NOT_YET_DETERMINED_ITEMS: (
        LessonMode.IDENTIFY, "What is not yet determined",
        "Identify evidence that does not exist yet at the replay time.",
        "Which evidence is still NOT_YET_DETERMINED?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.MATURITY), None, ("Read the maturity table.",)),
    QuestionKind.DATA_QUALITY: (
        LessonMode.IDENTIFY, "Qualified evidence",
        "Recognize qualified or unavailable evidence before reading it.",
        "How complete and qualified is the evidence at this time?",
        (EvidenceDomain.DATA_QUALITY, EvidenceDomain.VWAP, EvidenceDomain.VOLUME_PROFILE, EvidenceDomain.TPO,
         EvidenceDomain.PRIOR_DAY, EvidenceDomain.OVERNIGHT, EvidenceDomain.OPENING),
        None, ("Read the dataset quality status and its reasons.", "List every quality warning.")),
}


def _hhmmss(t: datetime) -> str:
    return t.astimezone(CT).strftime("%H%M%S")


def example_lesson(session: ReplaySession, kind: QuestionKind, at: datetime | str,
                   compare_from: datetime | str | None = None, reveal_at: datetime | str | None = None
                   ) -> LessonDefinition:
    """A LAB_EVIDENCE_READING_V1 lesson definition for this session (deterministic id)."""
    mode, title, objective, question, domains, convention, hints = _EXAMPLES[kind]
    t = session.resolve_time(at)
    t0 = session.resolve_time(compare_from) if compare_from is not None else None
    t1 = session.resolve_time(reveal_at) if reveal_at is not None else None
    lesson_id = f"LAB-{kind.value}-{session.trading_date.isoformat()}-{_hhmmss(t)}" + (
        f"-FROM-{_hhmmss(t0)}" if t0 else "") + (f"-REVEAL-{_hhmmss(t1)}" if t1 else "")
    return LessonDefinition(lesson_id, title, objective, mode, kind, question, session.trading_date, t, domains,
                            LAB_MODULE.module_id, (LAB_SOURCE.source_id,), convention, t0, t1, hints)


# --- text ------------------------------------------------------------------------------------------

def _ct(iso: str | None) -> str:
    if iso is None:
        return "--"
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone(CT).strftime(
        "%Y-%m-%d %H:%M:%S %Z")


def render_view(payload: dict) -> str:
    """Concise text of a student or instructor payload. Facts and references only."""
    lesson, ctx = payload["lesson"], payload["context"]
    lines = [f"LESSON {lesson['lesson_id']}  [{payload['audience']}"
             + (f", stage {payload['stage']}]" if "stage" in payload else "]"),
             f"  {lesson['title']} ({lesson['mode']}; module {lesson['curriculum_module_id']})",
             f"  objective: {lesson['objective']}",
             f"  replay time {_ct(ctx['replay_market_time'])} (evidence {ctx['evidence_temporality']}, knowledge "
             f"{_ct(ctx['replay_knowledge_time'])})  snapshot {ctx['snapshot_sha256'][:16]}",
             "  value-area convention: "
             + (f"{ctx['value_area_convention']['convention_id']} ({ctx['value_area_convention']['fraction']})"
                if ctx["value_area_convention"] else "none used"),
             "", f"QUESTION  {lesson['question']}", "", "AUTHORIZED EVIDENCE"]
    for s in ctx["snapshots"]:
        lines.append(f"  {s['role']} {_ct(s['replay_market_time'])}  snapshot {s['snapshot_sha256'][:16]}")
        for i in s["items"]:
            lines.append(f"    {i['label']:<52} {'--' if i['value'] is None else i['value']!s:<28} "
                         f"[{i['availability']}{', ' + i['maturity'] if i['maturity'] else ''}] {i['ref']['pointer']}")
    if ctx["delta"]:
        d = ctx["delta"]
        lines.append(f"  DELTA {d['delta_sha256'][:16]} ({len(d['items'])} references)")
    lines += ["", "QUALITY WARNINGS"] + ([f"  {w['warning_id']}: {w['status']} - {'; '.join(w['reasons'])}"
                                          for w in ctx["quality_warnings"]] or ["  none"])
    if "hints" in payload and payload["hints"]:
        lines += ["", "HINTS"] + [f"  - {h}" for h in payload["hints"]]
    if payload.get("answer_key"):
        k = payload["answer_key"]
        lines += ["", f"ANSWER KEY  {k['support']}: {k['summary']}"]
        lines += [f"  [{o['observation_id']}] {o['statement']}" for o in k["observations"]]
        lines += [f"  missing: {m}" for m in k["missing_dependencies"]]
        lines += [f"  not supported [{c['claim_id']}] {c['statement']} -> {c['support']} ({c['why']})"
                  for c in k["rubric"]["common_incorrect_claims"]]
    if payload.get("future_outcome"):
        f = payload["future_outcome"]
        lines += ["", f"FUTURE OUTCOME {_ct(f['evidence']['replay_market_time'])}  snapshot "
                  f"{f['evidence']['snapshot_sha256'][:16]}  summary {f['summary']}"]
        lines += [f"  [{o['observation_id']}] {o['statement']}" for o in f["observations"]]
    if payload.get("withheld"):
        lines += ["", "WITHHELD (not in this payload): " + ", ".join(payload["withheld"])]
    lines += ["", f"payload {payload[PAYLOAD_HASH_FIELD][:16]}. Evidence only; no interpretation, no AI model."]
    return "\n".join(lines) + "\n"
