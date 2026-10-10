"""MARKET_STUDY_STATE_V1: one deterministic, versioned study-state object per trading date (0Z-A).

SOURCE DATA -> NORMALIZED / EFFECTIVE TAPE -> DERIVED ANALYTICS -> UNIFIED MARKET STUDY STATE.

The state composes the accepted typed analytic objects (TPO, structure, DAY_TYPE_V1,
DAY_STRUCTURE_STRENGTH_V1, OPENING_AUCTION_FACTS_V1, OVERNIGHT_CONTEXT_V1,
OPENING_PATH_FACTS_V1, OPENING_TYPE_V1) and the accepted VWAP / Volume Profile
results. It computes no new market concept, adds no interpretation, and never
mutates an accepted component.

- Temporality: always FINAL_STUDY_STATE. It is end-state evidence over the complete
  study windows. It is not what was knowable at any intraday instant.
- Canonical JSON: sorted keys, no whitespace, ASCII. Decimal as plain-notation
  strings, timestamps as UTC `YYYY-MM-DDTHH:MM:SS.ffffffZ`, durations as exact
  seconds strings with 6 decimals, enums by value, absent values as null (never 0).
  Floats are refused.
- `market_study_state_sha256` is the SHA-256 of the canonical JSON of the payload
  WITHOUT the hash field; the hash is then attached as a top-level field.
- Duplicated sub-objects are serialized once and referenced as {"$ref": "<pointer>"};
  tape-sized arrays are replaced by {"$omitted": "<reason>"} (see SERIALIZATION_REFS).

Building is read-only: `load_study_inputs` opens a database read-only, and
`build_market_study_state` is a pure function. No network, broker or cloud access.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import Enum, StrEnum
from pathlib import Path
from uuid import UUID

from dicks_laboratory.analysis import AnchorCoverage, open_dataset_store, prepare_scoped_dataset, resolve_dataset_id
from dicks_laboratory.anchored_vwap import VwapSourceMode, calculate_anchored_vwap
from dicks_laboratory.futures_contracts import LABORATORY_UNIVERSE, MONTH_CODES
from dicks_laboratory.models import InstrumentIdentity
from dicks_laboratory.sessions import (
    ES_GLOBEX,
    US_CASH_SESSION_ID,
    US_CASH_SESSION_VERSION,
    AnchorKind,
    resolve_anchor,
    session_coverage,
)
from dicks_laboratory.tpo_analysis import (
    QualityStatus,
    TpoAnalysisResult,
    analyze_tpo_dataset,
    build_prior_context,
    opening_type_classification,
)
from dicks_laboratory.tpo_day_strength import (
    DAY_STRUCTURE_STRENGTH_V1,
    DAY_TYPE_V1,
    DayStructureStrength,
    StrengthScope,
)
from dicks_laboratory.tpo_day_structure import (
    DAY_TYPE_POLICY_ID,
    DAY_TYPE_POLICY_VERSION,
    ClassificationOutcome,
    DayTypeClassification,
    QualityGrade,
)
from dicks_laboratory.tpo_opening import (
    OPENING_FACTS_POLICY_ID,
    OPENING_QUALITY_WINDOW_MINUTES,
    CashOpenSession,
    ContextOutcome,
    OpeningAuctionFacts,
    OpeningQualityGrade,
    PriorContext,
    cash_open_utc,
)
from dicks_laboratory.tpo_opening_path import OPENING_PATH_POLICY_ID, OpeningPathFacts
from dicks_laboratory.tpo_opening_type import (
    OPENING_TYPE_POLICY_ID,
    OPENING_TYPE_POLICY_VERSION,
    ORR_DEFERRAL_REASON,
    CandidateResult,
    ClassificationStatus,
    OpeningTypeClassification,
)
from dicks_laboratory.tpo_opening_type_record import (
    OPENING_TYPE_V1_POLICY_DOC_SHA256,
    OPENING_TYPE_V1_SOURCE_SHA256,
    policy_source_sha256,
)
from dicks_laboratory.tpo_overnight import (
    OVERNIGHT_CONTEXT_POLICY_ID,
    OvernightContext,
    OvernightQualityGrade,
    OvernightSession,
    overnight_window_utc,
)
from dicks_laboratory.tpo_profile import (
    TPO_POC_POLICY_ID,
    TPO_POC_POLICY_VERSION,
    TPO_VALUE_AREA_POLICY_ID,
    TPO_VALUE_AREA_POLICY_VERSION,
    US_CASH_PROFILE,
    TpoProfile,
)
from dicks_laboratory.tpo_structure import (
    STRUCTURE_POLICY_ID,
    STRUCTURE_POLICY_VERSION,
    ProfileStructure,
)
from dicks_laboratory.value_area import DEFAULT_VALUE_AREA_FRACTION, VALUE_AREA_POLICY_ID, VALUE_AREA_POLICY_VERSION
from dicks_laboratory.volume_profile import POC_TIE_POLICY_ID, POC_TIE_POLICY_VERSION, price_grid_for_instrument

MARKET_STUDY_STATE_SCHEMA = "MARKET_STUDY_STATE_V1"  # a breaking semantic change is MARKET_STUDY_STATE_V2
HASH_FIELD = "market_study_state_sha256"
TEMPORALITY_NOTE = ("End-state evidence over the complete study windows of the trading date. It is NOT what was "
                    "knowable at any intraday instant (e.g. 10:00 CT); as-of snapshots belong to replay.")
VWAP_END_SEMANTICS = ("[anchor, end of the trading-date CME Globex session at 16:00 CT); every retained "
                      "effective-tape trade of that session at or after the anchor; no other end bound")
NOT_RECORDED = "NOT_RECORDED_IN_DATASET"
_LOCATOR = re.compile(r"^([A-Z0-9_]+):(/[^:]+:[A-Z0-9]+):([A-Za-z]+)$")


class StateTemporality(StrEnum):
    FINAL_STUDY_STATE = "FINAL_STUDY_STATE"


class ComponentStatus(StrEnum):
    AVAILABLE = "AVAILABLE"  # computed; no qualification recorded
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # computed; reasons say why it may be incomplete
    NOT_AVAILABLE = "NOT_AVAILABLE"  # not computed / not classifiable; reasons say why
    NOT_APPLICABLE = "NOT_APPLICABLE"  # the component does not apply to this state


class EvidenceKind(StrEnum):
    IDENTITY = "IDENTITY"  # what dataset / contract / code produced the state
    OBSERVED_FACT = "OBSERVED_FACT"  # a retained trade's own price / time
    DERIVED_FACT = "DERIVED_FACT"  # deterministic computation over retained trades
    LABORATORY_POLICY = "LABORATORY_POLICY"  # a policy identifier or constant
    LABORATORY_POLICY_RESULT = "LABORATORY_POLICY_RESULT"  # a policy outcome that is not a candidate label
    CANDIDATE = "CANDIDATE"  # a Laboratory candidate label (never an interpretation)
    DEFERRED = "DEFERRED"  # deliberately not evaluated
    QUALITY_QUALIFICATION = "QUALITY_QUALIFICATION"  # availability / completeness evidence


class ReplayReadiness(StrEnum):
    REPLAY_READY = "REPLAY_READY"  # known in full before or at a fixed instant; usable as-of unchanged
    NEEDS_AS_OF_IMPLEMENTATION = "NEEDS_AS_OF_IMPLEMENTATION"  # develops intraday; needs an as-of computation
    FINAL_DAY_ONLY = "FINAL_DAY_ONLY"  # defined only over the completed study window


# --- typed state ---------------------------------------------------------------------------------

@dataclass(frozen=True)
class AnalysisProvenance:
    """Code that produced the state. Explicit input: never a wall-clock value."""

    analysis_git_commit: str
    analysis_worktree_modified: bool | None  # None = not determined


@dataclass(frozen=True)
class DatasetSource:
    """Identity and collector accounting of one dataset file. None = not recorded (never fabricated)."""

    dataset_id: UUID
    trading_date: date  # the trading date the analysis resolved
    recorded_trading_date: date | None  # dataset-level column (None on pre-0V datasets)
    instrument_id: str
    kind: str
    origin: str
    label: str
    source_locator: str | None
    source_system: str | None  # parsed from source_locator
    streamer_symbol: str | None  # parsed from source_locator
    source_event_type: str | None
    normalizer_version: str | None
    collector_version: str | None
    collector_git_commit: str | None
    lifecycle_state: str | None
    capture_started_at: datetime | None
    capture_ended_at: datetime | None
    closing_summary_recorded: bool
    closing_summary_closed_at: datetime | None
    accepted_trade_count: int | None  # collector's closing summary
    rejected_record_count: int | None
    deferred_event_count: int | None
    submitted_events: int | None
    persisted_events: int | None
    accounting_difference: int | None
    retained_trade_count: int  # what the database holds now
    applied_correction_count: int  # effective-tape reconstruction
    applied_cancel_count: int
    database_sha256: str | None


@dataclass(frozen=True)
class ContractSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    instrument_id: str
    instrument: InstrumentIdentity
    root: str
    exchange: str
    contract_year: int
    contract_month: int
    month_code: str
    product_description: str | None  # Laboratory product-policy layer
    roll_rule: str | None
    tick_size: Decimal
    tick_size_source: str  # the price-grid policy that fixes the tick
    multiplier: Decimal | None
    multiplier_status: str
    broker_symbol: str | None
    broker_symbol_status: str
    streamer_symbol: str | None
    streamer_symbol_status: str


@dataclass(frozen=True)
class WindowCoverage:
    window: str
    start_utc: datetime
    end_utc: datetime
    fully_captured: bool | None  # None = capture interval not recorded
    known_gaps_overlapping: int
    suspected_gaps_overlapping: int


@dataclass(frozen=True)
class GapInterval:
    evidence_type: str
    start_utc: datetime
    end_utc: datetime


@dataclass(frozen=True)
class DatasetQualitySection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    completeness: QualityStatus
    known_gap_count: int
    suspected_gap_count: int
    known_gap_duration: timedelta
    gaps: tuple[GapInterval, ...]
    windows: tuple[WindowCoverage, ...]  # CASH_PROFILE, OPENING, OVERNIGHT
    lifecycle_state: str | None
    lifecycle_qualification: str | None  # None when FINALIZED
    structural_qualifications: tuple[str, ...]  # 0Y-B reasons a structure may be a data artifact


@dataclass(frozen=True)
class VwapStudy:
    anchor_kind: AnchorKind
    anchor_policy_id: str
    anchor_policy_version: str
    anchor_utc: datetime
    end_semantics: str
    session_end_utc: datetime
    source_mode: VwapSourceMode
    status: ComponentStatus
    reasons: tuple[str, ...]
    coverage: AnchorCoverage  # accepted 0N coverage (first retained trade vs anchor)
    vwap: Decimal | None
    included_trade_count: int | None
    included_volume: Decimal | None
    first_included_utc: datetime | None
    last_included_utc: datetime | None


@dataclass(frozen=True)
class VwapSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    studies: tuple[VwapStudy, ...]


@dataclass(frozen=True)
class VolumeProfileSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    window_id: str
    window_start_utc: datetime
    window_end_utc: datetime
    source_mode: VwapSourceMode
    poc: Decimal | None
    value_area_low: Decimal | None
    value_area_high: Decimal | None
    profile_high: Decimal | None
    profile_low: Decimal | None
    total_volume: Decimal | None
    selected_trade_count: int | None
    level_count: int | None
    value_area_target_fraction: Decimal
    value_area_included_fraction: Decimal | None
    window_vwap: Decimal | None  # VWAP of the same selected trades
    poc_policy: str
    value_area_policy: str
    distribution: tuple[tuple[Decimal, Decimal], ...]  # (price, volume) ascending; every traded level


@dataclass(frozen=True)
class TpoSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    window_id: str
    window_policy_version: str
    period_minutes: int
    profile: TpoProfile | None


@dataclass(frozen=True)
class TpoStructureSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    structure: ProfileStructure | None


@dataclass(frozen=True)
class DayTypeSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    outcome: ClassificationOutcome | None
    classification: DayTypeClassification | None


@dataclass(frozen=True)
class DayStrengthSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    scope: StrengthScope | None
    strength: DayStructureStrength | None


@dataclass(frozen=True)
class PriorDaySection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    outcome: ContextOutcome | None
    prior_dataset_supplied: bool
    source: DatasetSource | None  # the file that was supplied, whether or not it was usable
    context: PriorContext | None


@dataclass(frozen=True)
class OvernightSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    grade: OvernightQualityGrade | None
    globex_open_claimed: bool
    globex_open_boundary_proven: bool
    first_observed_overnight_trade_is_globex_open: bool  # True only when the boundary is proven
    session: OvernightSession | None
    context: OvernightContext | None


@dataclass(frozen=True)
class CashOpeningSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    grade: OpeningQualityGrade | None
    facts: OpeningAuctionFacts | None  # OPENING_AUCTION_FACTS_V1
    path_facts: OpeningPathFacts | None  # OPENING_PATH_FACTS_V1


@dataclass(frozen=True)
class MatchedOpeningType:
    type: str
    direction: str | None
    quality: str


@dataclass(frozen=True)
class OpeningTypeSection:
    status: ComponentStatus
    reasons: tuple[str, ...]
    classification_status: ClassificationStatus | None
    policy_id: str
    policy_version: str
    policy_source_sha256: str
    policy_frozen_sha256: str
    policy_source_matches_freeze: bool
    policy_document_sha256: str
    matched: tuple[MatchedOpeningType, ...]  # candidate set; no primary type, no precedence
    deferred: tuple[tuple[str, str], ...]  # (type, reason)
    classification: OpeningTypeClassification | None


@dataclass(frozen=True)
class PolicyEntry:
    component: str
    policy_id: str | None  # None = no accepted identifier exists (none is invented)
    policy_version: str | None
    frozen_source_sha256: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class QualityEntry:
    component: str
    status: ComponentStatus
    domain_status: str | None  # the component's own native status / grade
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceClass:
    pointer: str  # JSON pointer; '*' = every array element
    kind: EvidenceKind


@dataclass(frozen=True)
class MarketStudyState:
    """The canonical payload. Its hash is attached only at serialization (`canonical_state_json`)."""

    schema: str
    state_temporality: StateTemporality
    temporality_note: str
    provenance: AnalysisProvenance
    current_dataset: DatasetSource
    contract: ContractSection
    dataset_quality: DatasetQualitySection
    vwap: VwapSection
    volume_profile: VolumeProfileSection
    tpo: TpoSection
    tpo_structure: TpoStructureSection
    day_type: DayTypeSection
    day_strength: DayStrengthSection
    prior_day: PriorDaySection
    overnight: OvernightSection
    cash_opening: CashOpeningSection
    opening_type: OpeningTypeSection
    policy_registry: tuple[PolicyEntry, ...]
    quality_matrix: tuple[QualityEntry, ...]
    evidence_classification: tuple[EvidenceClass, ...]


# --- static V1 contract --------------------------------------------------------------------------

EVIDENCE_CLASSIFICATION = tuple(EvidenceClass(p, k) for p, k in (
    ("/provenance", EvidenceKind.IDENTITY),
    ("/current_dataset", EvidenceKind.IDENTITY),
    ("/prior_day/source", EvidenceKind.IDENTITY),
    ("/contract", EvidenceKind.IDENTITY),
    ("/dataset_quality", EvidenceKind.QUALITY_QUALIFICATION),
    ("/quality_matrix", EvidenceKind.QUALITY_QUALIFICATION),
    ("/policy_registry", EvidenceKind.LABORATORY_POLICY),
    ("/vwap/studies/*/vwap", EvidenceKind.DERIVED_FACT),
    ("/vwap/studies/*/status", EvidenceKind.QUALITY_QUALIFICATION),
    ("/volume_profile/poc", EvidenceKind.DERIVED_FACT),
    ("/volume_profile/distribution", EvidenceKind.DERIVED_FACT),
    ("/tpo/profile", EvidenceKind.DERIVED_FACT),
    ("/tpo/profile/poc_policy_version", EvidenceKind.LABORATORY_POLICY),
    ("/tpo_structure/structure/zones", EvidenceKind.DERIVED_FACT),
    ("/tpo_structure/structure/upper/excess_candidate", EvidenceKind.CANDIDATE),
    ("/tpo_structure/structure/upper/poor_candidate", EvidenceKind.CANDIDATE),
    ("/tpo_structure/structure/lower/excess_candidate", EvidenceKind.CANDIDATE),
    ("/tpo_structure/structure/lower/poor_candidate", EvidenceKind.CANDIDATE),
    ("/tpo_structure/structure/ib_extension", EvidenceKind.DERIVED_FACT),
    ("/day_type/classification/facts", EvidenceKind.DERIVED_FACT),
    ("/day_type/classification/facts/terminal/price", EvidenceKind.OBSERVED_FACT),
    ("/day_type/classification/outcome", EvidenceKind.LABORATORY_POLICY_RESULT),
    ("/day_type/classification/primary", EvidenceKind.CANDIDATE),
    ("/day_type/classification/candidates", EvidenceKind.CANDIDATE),
    ("/day_type/classification/deferred", EvidenceKind.DEFERRED),
    ("/day_type/classification/quality", EvidenceKind.QUALITY_QUALIFICATION),
    ("/day_strength/strength", EvidenceKind.DERIVED_FACT),
    ("/day_strength/strength/day_type", EvidenceKind.CANDIDATE),
    ("/prior_day/context", EvidenceKind.DERIVED_FACT),
    ("/prior_day/context/day_type", EvidenceKind.CANDIDATE),
    ("/prior_day/context/outcome", EvidenceKind.QUALITY_QUALIFICATION),
    ("/overnight/session", EvidenceKind.DERIVED_FACT),
    ("/overnight/session/first_price", EvidenceKind.OBSERVED_FACT),
    ("/overnight/session/globex_open_price", EvidenceKind.OBSERVED_FACT),
    ("/overnight/session/quality", EvidenceKind.QUALITY_QUALIFICATION),
    ("/overnight/context", EvidenceKind.DERIVED_FACT),
    ("/cash_opening/facts", EvidenceKind.DERIVED_FACT),
    ("/cash_opening/facts/session/cash_open", EvidenceKind.OBSERVED_FACT),
    ("/cash_opening/facts/session/quality", EvidenceKind.QUALITY_QUALIFICATION),
    ("/cash_opening/path_facts", EvidenceKind.DERIVED_FACT),
    ("/opening_type/matched", EvidenceKind.CANDIDATE),
    ("/opening_type/deferred", EvidenceKind.DEFERRED),
    ("/opening_type/classification/candidates", EvidenceKind.CANDIDATE),
    ("/opening_type/classification/strength", EvidenceKind.DERIVED_FACT),
    ("/opening_type/classification/quality", EvidenceKind.QUALITY_QUALIFICATION),
))

# (component, readiness, when the final value is fixed / what an as-of version needs)
REPLAY_READINESS = (
    ("provenance / policy_registry", ReplayReadiness.REPLAY_READY, "static for a given analysis commit"),
    ("current_dataset identity", ReplayReadiness.REPLAY_READY, "dataset id, contract and source fixed at capture start"),
    ("current_dataset closing summary", ReplayReadiness.FINAL_DAY_ONLY,
     "written at close; capture end and accepted/submitted/persisted counts unknown intraday"),
    ("contract", ReplayReadiness.REPLAY_READY, "fixed by the dataset identity"),
    ("dataset_quality", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION,
     "gap evidence must be filtered to what had been detected by the as-of instant"),
    ("vwap", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION, "cumulative from the anchor; as-of = trades before the instant"),
    ("volume_profile", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION,
     "POC/VA develop intraday; the accepted developing-profile module (0R) is the starting point"),
    ("tpo profile / initial balance", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION,
     "periods letter in as they close; IB fixed at 09:30 CT; TPO POC/VA develop"),
    ("tpo_structure (tails, excess/poor candidates, one-TPO zones)", ReplayReadiness.FINAL_DAY_ONLY,
     "V1 rules are defined over the completed profile; a later period can remove a tail"),
    ("day_type DAY_TYPE_V1", ReplayReadiness.FINAL_DAY_ONLY, "defined over the full study window"),
    ("day_strength DAY_STRUCTURE_STRENGTH_V1", ReplayReadiness.FINAL_DAY_ONLY,
     "terminal price and final extensions; defined over the full study window"),
    ("study-window terminal price", ReplayReadiness.FINAL_DAY_ONLY, "last eligible trade before 15:00 CT"),
    ("prior_day context", ReplayReadiness.REPLAY_READY, "fully known before the current overnight session starts"),
    ("overnight OVERNIGHT_CONTEXT_V1", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION,
     "develops 17:00-08:30 CT; final at the cash open, so it is complete for any as-of instant >= 08:30 CT"),
    ("cash open print", ReplayReadiness.REPLAY_READY, "fixed at the first print at/after 08:30 CT (<= 60 s)"),
    ("opening window facts 5/15/30/60 min", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION,
     "each window is final at its horizon end; 60-minute facts at 09:30 CT"),
    ("OPENING_PATH_FACTS_V1", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION, "final at 09:30 CT (3600 s scale)"),
    ("opening_type OPENING_TYPE_V1", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION,
     "conditions final at the end of period A (09:00 CT); opening quality window final at 09:30 CT; "
     "before that an as-of state must say NOT_YET_DETERMINED, never a partial candidate"),
    ("quality_matrix", ReplayReadiness.NEEDS_AS_OF_IMPLEMENTATION, "follows its components"),
)


def policy_registry(grid_policy: tuple[str, str]) -> tuple[PolicyEntry, ...]:
    """The accepted identifiers the state depends on. Values are the codebase constants."""
    source = policy_source_sha256()
    return (
        PolicyEntry("MARKET_STUDY_STATE", MARKET_STUDY_STATE_SCHEMA, MARKET_STUDY_STATE_SCHEMA),
        PolicyEntry("PRICE_GRID", *grid_policy),
        PolicyEntry("GLOBEX_SESSION", ES_GLOBEX.session_id, ES_GLOBEX.policy_version, note=ES_GLOBEX.limitation),
        PolicyEntry("CASH_SESSION_ANCHOR", US_CASH_SESSION_ID, US_CASH_SESSION_VERSION),
        PolicyEntry("STUDY_WINDOW", US_CASH_PROFILE.window_id, US_CASH_PROFILE.policy_version),
        PolicyEntry("VWAP", None, None, note="no separate VWAP policy id exists: exact sum(price*size)/sum(size) "
                    "over EFFECTIVE_TAPE trades from the GLOBEX_SESSION / CASH_SESSION_ANCHOR anchors"),
        PolicyEntry("VOLUME_PROFILE_POC", POC_TIE_POLICY_ID, POC_TIE_POLICY_VERSION),
        PolicyEntry("VOLUME_VALUE_AREA", VALUE_AREA_POLICY_ID, VALUE_AREA_POLICY_VERSION,
                    note=f"target fraction {DEFAULT_VALUE_AREA_FRACTION}"),
        PolicyEntry("TPO_POC", TPO_POC_POLICY_ID, TPO_POC_POLICY_VERSION),
        PolicyEntry("TPO_VALUE_AREA", TPO_VALUE_AREA_POLICY_ID, TPO_VALUE_AREA_POLICY_VERSION),
        PolicyEntry("TPO_STRUCTURE", STRUCTURE_POLICY_ID, STRUCTURE_POLICY_VERSION),
        PolicyEntry(DAY_TYPE_V1, DAY_TYPE_POLICY_ID, DAY_TYPE_POLICY_VERSION),
        PolicyEntry(DAY_STRUCTURE_STRENGTH_V1, DAY_STRUCTURE_STRENGTH_V1, None),
        PolicyEntry(OPENING_FACTS_POLICY_ID, OPENING_FACTS_POLICY_ID, None),
        PolicyEntry(OVERNIGHT_CONTEXT_POLICY_ID, OVERNIGHT_CONTEXT_POLICY_ID, None),
        PolicyEntry(OPENING_PATH_POLICY_ID, OPENING_PATH_POLICY_ID, None),
        PolicyEntry(OPENING_TYPE_POLICY_ID, OPENING_TYPE_POLICY_ID, OPENING_TYPE_POLICY_VERSION,
                    OPENING_TYPE_V1_SOURCE_SHA256,
                    note=f"frozen 0Y-H; current source sha256 {source} "
                         f"({'matches' if source == OPENING_TYPE_V1_SOURCE_SHA256 else 'DIFFERS FROM'} the freeze); "
                         f"policy document sha256 {OPENING_TYPE_V1_POLICY_DOC_SHA256}"),
    )


# --- read-only inputs ----------------------------------------------------------------------------

@dataclass(frozen=True)
class StudyInputs:
    """One analysed dataset: the accepted TPO-family result, its VWAP studies and its identity."""

    result: TpoAnalysisResult
    vwaps: tuple[VwapStudy, ...]
    source: DatasetSource


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_study_inputs(database: Path, dataset_id: UUID | None = None) -> StudyInputs:
    """Open the database read-only and analyse it once (one tape load for TPO and VWAP)."""
    store = open_dataset_store(database)
    try:
        resolved = resolve_dataset_id(store, dataset_id)
        context = prepare_scoped_dataset(store, resolved, AnchorKind.SESSION_OPEN, None, None)
        result = analyze_tpo_dataset(store, resolved, context=context)
        vwaps = tuple(_vwap_study(context, kind, result) for kind in (AnchorKind.SESSION_OPEN, AnchorKind.US_CASH_OPEN))
        identity = store.load_dataset(resolved)
        recorded_date, _ = store.load_dataset_trading_context(resolved)
        summary = store.load_dataset_closing_summary(resolved)
        retained = store.count_trade_observations(resolved)
    finally:
        store.close()
    match = _LOCATOR.match(identity.source_locator or "")
    source = DatasetSource(
        dataset_id=resolved,
        trading_date=result.trading_date,
        recorded_trading_date=recorded_date,
        instrument_id=result.instrument.canonical_id,
        kind=identity.kind.value,
        origin=identity.origin.value,
        label=identity.label,
        source_locator=identity.source_locator,
        source_system=match.group(1) if match else None,
        streamer_symbol=match.group(2) if match else None,
        source_event_type=match.group(3) if match else None,
        normalizer_version=identity.normalizer_version,
        collector_version=summary.collector_version if summary else None,
        collector_git_commit=summary.collector_git_commit if summary else None,
        lifecycle_state=result.quality.lifecycle_state,
        capture_started_at=identity.capture_started_at,
        capture_ended_at=identity.capture_ended_at,
        closing_summary_recorded=summary is not None,
        closing_summary_closed_at=summary.closed_at if summary else None,
        accepted_trade_count=summary.accepted_trade_count if summary else None,
        rejected_record_count=summary.rejected_record_count if summary else None,
        deferred_event_count=summary.deferred_event_count if summary else None,
        submitted_events=summary.submitted_events if summary else None,
        persisted_events=summary.persisted_events if summary else None,
        accounting_difference=summary.accounting_difference if summary else None,
        retained_trade_count=retained,
        applied_correction_count=result.applied_correction_count,
        applied_cancel_count=result.applied_cancel_count,
        database_sha256=file_sha256(database),
    )
    return StudyInputs(result, vwaps, source)


def _vwap_study(context, kind: AnchorKind, result: TpoAnalysisResult) -> VwapStudy:
    """The accepted anchored VWAP (0M/0N) over the session-scoped effective tape; no new anchor."""
    anchor = resolve_anchor(kind, result.trading_date)
    end = session_coverage((), result.trading_date).session_end_utc
    if anchor.anchor_timestamp_utc > context.dataset_last:
        coverage = AnchorCoverage.ANCHOR_AFTER_DATASET_END
    elif anchor.anchor_timestamp_utc < context.dataset_first:
        coverage = AnchorCoverage.DATASET_BEGINS_AFTER_ANCHOR
    else:
        coverage = AnchorCoverage.ANCHOR_COVERED
    try:
        vwap = calculate_anchored_vwap(context.scoped_effective, anchor, VwapSourceMode.EFFECTIVE_TAPE,
                                       str(result.trading_date))
    except ValueError:
        vwap = None
    q = result.quality
    reasons = []
    if vwap is None:
        status = ComponentStatus.NOT_AVAILABLE
        reasons.append("no retained effective trade at or after the anchor in the trading-date session")
    else:
        if q.capture_started_at is None or q.capture_ended_at is None:
            reasons.append("capture interval not recorded; anchor-to-session-end coverage unverified")
        else:
            if q.capture_started_at > anchor.anchor_timestamp_utc:
                reasons.append(f"capture began {q.capture_started_at - anchor.anchor_timestamp_utc} after the anchor")
            if q.capture_ended_at < end:
                reasons.append(f"capture ended {end - q.capture_ended_at} before the session end")
        reasons += _gap_reasons(q.gap_intervals, anchor.anchor_timestamp_utc, end, "the VWAP interval")
        if q.lifecycle_state != "FINALIZED":
            reasons.append(f"lifecycle {q.lifecycle_state or 'UNTRACKED'} (not FINALIZED)")
        status = ComponentStatus.QUALITY_QUALIFIED if reasons else ComponentStatus.AVAILABLE
    return VwapStudy(
        anchor_kind=kind, anchor_policy_id=anchor.policy_id, anchor_policy_version=anchor.policy_version,
        anchor_utc=anchor.anchor_timestamp_utc, end_semantics=VWAP_END_SEMANTICS, session_end_utc=end,
        source_mode=VwapSourceMode.EFFECTIVE_TAPE, status=status, reasons=tuple(reasons), coverage=coverage,
        vwap=vwap.vwap if vwap else None, included_trade_count=vwap.included_trade_count if vwap else None,
        included_volume=vwap.included_volume if vwap else None,
        first_included_utc=vwap.first_included_trade_timestamp if vwap else None,
        last_included_utc=vwap.last_included_trade_timestamp if vwap else None)


def _gap_reasons(gap_intervals, start: datetime, end: datetime, where: str) -> list[str]:
    known, suspected = _gap_counts(gap_intervals, start, end)
    return ([f"KNOWN_GAP overlaps {where}: {known}"] if known else []) + (
        [f"SUSPECTED_GAP overlaps {where}: {suspected}"] if suspected else [])


def _gap_counts(gap_intervals, start: datetime, end: datetime) -> tuple[int, int]:
    """Same overlap rule as the accepted quality code: interval_start < end and interval_end > start."""
    known = sum(1 for kind, s, e in gap_intervals if kind == "KNOWN_GAP" and s < end and e > start)
    suspected = sum(1 for kind, s, e in gap_intervals if kind == "SUSPECTED_GAP" and s < end and e > start)
    return known, suspected


# --- pure builder --------------------------------------------------------------------------------

def build_market_study_state(
    current: StudyInputs,
    prior: StudyInputs | None,
    provenance: AnalysisProvenance,
    closures: frozenset[date] = frozenset(),
) -> MarketStudyState:
    """Compose the accepted evidence for `current` (and its prior trading date, if supplied). Pure."""
    r = current.result
    if r.window != US_CASH_PROFILE:
        raise ValueError("MARKET_STUDY_STATE_V1 is defined over the US_CASH_PROFILE study window only.")
    candidates = (prior.result,) if prior is not None else ()
    classification = opening_type_classification(r, candidates, closures)
    path_facts = classification.facts if classification else None
    opening = path_facts.opening if path_facts else None
    overnight_ctx = path_facts.overnight if path_facts else None
    prior_ctx = opening.prior if opening else build_prior_context(r, candidates, closures)
    grid = price_grid_for_instrument(r.instrument)
    state = MarketStudyState(
        schema=MARKET_STUDY_STATE_SCHEMA,
        state_temporality=StateTemporality.FINAL_STUDY_STATE,
        temporality_note=TEMPORALITY_NOTE,
        provenance=provenance,
        current_dataset=current.source,
        contract=_contract(r, current.source, grid),
        dataset_quality=_dataset_quality(r),
        vwap=_vwap_section(current.vwaps),
        volume_profile=_volume_profile(r),
        tpo=_tpo(r),
        tpo_structure=_tpo_structure(r),
        day_type=_day_type(r),
        day_strength=_day_strength(r),
        prior_day=_prior_day(prior, prior_ctx),
        overnight=_overnight(r.overnight, overnight_ctx),
        cash_opening=_cash_opening(r.opening, opening, path_facts),
        opening_type=_opening_type(classification),
        policy_registry=policy_registry((grid.policy_id, grid.policy_version)),
        quality_matrix=(),
        evidence_classification=EVIDENCE_CLASSIFICATION,
    )
    return dataclasses.replace(state, quality_matrix=quality_matrix(state))


def quality_matrix(state: MarketStudyState) -> tuple[QualityEntry, ...]:
    def entry(name, section, domain):
        return QualityEntry(name, section.status, domain, section.reasons)

    s = state
    return (
        entry("dataset", s.dataset_quality, s.dataset_quality.completeness.value),
        entry("contract", s.contract, None),
        entry("vwap", s.vwap, None),
        entry("volume_profile", s.volume_profile, None),
        entry("cash_tpo", s.tpo, None),
        entry("tpo_structure", s.tpo_structure, None),
        entry("day_type", s.day_type, s.day_type.outcome.value if s.day_type.outcome else None),
        entry("day_strength", s.day_strength, s.day_strength.scope.value if s.day_strength.scope else None),
        entry("prior_context", s.prior_day, s.prior_day.outcome.value if s.prior_day.outcome else None),
        entry("overnight", s.overnight, s.overnight.grade.value if s.overnight.grade else None),
        entry("cash_opening", s.cash_opening, s.cash_opening.grade.value if s.cash_opening.grade else None),
        entry("opening_type", s.opening_type,
              s.opening_type.classification_status.value if s.opening_type.classification_status else None),
    )


def _status(reasons) -> ComponentStatus:
    return ComponentStatus.QUALITY_QUALIFIED if reasons else ComponentStatus.AVAILABLE


def _contract(r: TpoAnalysisResult, source: DatasetSource, grid) -> ContractSection:
    inst = r.instrument
    product = LABORATORY_UNIVERSE.get(inst.root.upper())
    month_code = next(code for code, month in MONTH_CODES.items() if month == inst.expiration_month)
    streamer_ok = source.streamer_symbol is not None
    return ContractSection(
        status=ComponentStatus.AVAILABLE, reasons=(), instrument_id=inst.canonical_id, instrument=inst,
        root=inst.root, exchange=inst.exchange, contract_year=inst.expiration_year,
        contract_month=inst.expiration_month, month_code=month_code,
        product_description=product.description if product else None, roll_rule=product.roll_rule if product else None,
        tick_size=grid.tick_size, tick_size_source=f"{grid.policy_id} {grid.policy_version}",
        multiplier=None, multiplier_status=NOT_RECORDED,
        broker_symbol=None, broker_symbol_status=NOT_RECORDED,
        streamer_symbol=source.streamer_symbol,
        streamer_symbol_status="RECORDED_IN_SOURCE_LOCATOR" if streamer_ok else NOT_RECORDED,
    )


def _windows(r: TpoAnalysisResult) -> tuple[WindowCoverage, ...]:
    q = r.quality
    open_utc = cash_open_utc(r.trading_date)
    spans = (("CASH_PROFILE", r.window_start_utc, r.window_end_utc),
             ("OPENING", open_utc, open_utc + timedelta(minutes=OPENING_QUALITY_WINDOW_MINUTES)),
             ("OVERNIGHT", *overnight_window_utc(r.trading_date)))
    out = []
    for name, start, end in spans:
        known, suspected = _gap_counts(q.gap_intervals, start, end)
        captured = (None if q.capture_started_at is None or q.capture_ended_at is None
                    else q.capture_started_at <= start and q.capture_ended_at >= end)
        out.append(WindowCoverage(name, start, end, captured, known, suspected))
    return tuple(out)


def _dataset_quality(r: TpoAnalysisResult) -> DatasetQualitySection:
    q = r.quality
    windows = _windows(r)
    reasons = []
    if q.known_gap_count:
        reasons.append(f"KNOWN_GAP evidence: {q.known_gap_count}")
    if q.suspected_gap_count:
        reasons.append(f"SUSPECTED_GAP evidence: {q.suspected_gap_count}")
    for w in windows:
        if w.fully_captured is None:
            reasons.append(f"{w.window} window coverage unverified (capture interval not recorded)")
        elif not w.fully_captured:
            reasons.append(f"{w.window} window not fully captured")
    lifecycle = None if q.lifecycle_state == "FINALIZED" else f"lifecycle {q.lifecycle_state or 'UNTRACKED'} (not FINALIZED)"
    if lifecycle:
        reasons.append(lifecycle)
    return DatasetQualitySection(
        status=_status(reasons), reasons=tuple(reasons), completeness=q.status, known_gap_count=q.known_gap_count,
        suspected_gap_count=q.suspected_gap_count, known_gap_duration=q.known_gap_duration,
        gaps=tuple(GapInterval(*g) for g in q.gap_intervals), windows=windows, lifecycle_state=q.lifecycle_state,
        lifecycle_qualification=lifecycle, structural_qualifications=q.structural_qualifications)


def _vwap_section(studies: tuple[VwapStudy, ...]) -> VwapSection:
    statuses = {s.status for s in studies}
    if statuses == {ComponentStatus.NOT_AVAILABLE}:
        status = ComponentStatus.NOT_AVAILABLE
    elif statuses <= {ComponentStatus.AVAILABLE}:
        status = ComponentStatus.AVAILABLE
    else:
        status = ComponentStatus.QUALITY_QUALIFIED
    reasons = tuple(f"{s.anchor_kind.value}: {reason}" for s in studies for reason in s.reasons)
    return VwapSection(status, reasons, studies)


def _profile_status(r: TpoAnalysisResult, missing: bool, what: str) -> tuple[ComponentStatus, tuple[str, ...]]:
    if missing:
        return ComponentStatus.NOT_AVAILABLE, (f"no retained trade inside the study window: no {what}",)
    reasons = r.quality.structural_qualifications
    return _status(reasons), reasons


def _volume_profile(r: TpoAnalysisResult) -> VolumeProfileSection:
    vp, va = r.volume_profile, r.volume_value_area
    status, reasons = _profile_status(r, vp is None or va is None, "volume profile")
    poc_policy = f"{POC_TIE_POLICY_ID} {POC_TIE_POLICY_VERSION}"
    va_policy = f"{VALUE_AREA_POLICY_ID} {VALUE_AREA_POLICY_VERSION}"
    if vp is None or va is None:
        return VolumeProfileSection(status, reasons, r.window.window_id, r.window_start_utc, r.window_end_utc,
                                    VwapSourceMode.EFFECTIVE_TAPE, None, None, None, None, None, None, None, None,
                                    DEFAULT_VALUE_AREA_FRACTION, None, None, poc_policy, va_policy, ())
    return VolumeProfileSection(
        status=status, reasons=reasons, window_id=r.window.window_id, window_start_utc=r.window_start_utc,
        window_end_utc=r.window_end_utc, source_mode=vp.source_mode, poc=vp.point_of_control.price,
        value_area_low=va.value_area_low.price, value_area_high=va.value_area_high.price,
        profile_high=vp.highest_price, profile_low=vp.lowest_price, total_volume=vp.total_volume,
        selected_trade_count=vp.selected_trade_count, level_count=len(vp.levels),
        value_area_target_fraction=va.target_fraction, value_area_included_fraction=va.included_fraction,
        window_vwap=vp.selected_trades_vwap, poc_policy=f"{vp.poc_policy_id} {vp.poc_policy_version}",
        value_area_policy=f"{va.value_area_policy_id} {va.value_area_policy_version}",
        distribution=tuple((level.price, level.volume) for level in vp.levels))


def _tpo(r: TpoAnalysisResult) -> TpoSection:
    status, reasons = _profile_status(r, r.profile is None, "TPO profile, POC, value area or Initial Balance")
    return TpoSection(status, reasons, r.window.window_id, r.window.policy_version, r.period_minutes, r.profile)


def _tpo_structure(r: TpoAnalysisResult) -> TpoStructureSection:
    status, reasons = _profile_status(r, r.structure is None, "structure")
    return TpoStructureSection(status, reasons, r.structure)


def _day_type(r: TpoAnalysisResult) -> DayTypeSection:
    d = r.day_structure
    if d is None:
        return DayTypeSection(ComponentStatus.NOT_AVAILABLE, ("no TPO profile: day type not evaluated",), None, None)
    if d.outcome is ClassificationOutcome.NOT_CLASSIFIED:
        return DayTypeSection(ComponentStatus.NOT_AVAILABLE, d.not_classified_reasons, d.outcome, d)
    qualified = d.quality.grade is QualityGrade.QUALITY_QUALIFIED
    return DayTypeSection(_status(qualified), d.quality.reasons if qualified else (), d.outcome, d)


def _day_strength(r: TpoAnalysisResult) -> DayStrengthSection:
    s = r.day_strength
    if s is None:
        return DayStrengthSection(ComponentStatus.NOT_AVAILABLE, ("no TPO profile: strength facts not computed",),
                                  None, None)
    if s.scope is StrengthScope.FULL_STUDY_WINDOW:
        return DayStrengthSection(ComponentStatus.AVAILABLE, (), s.scope, s)
    return DayStrengthSection(ComponentStatus.QUALITY_QUALIFIED, s.scope_reasons, s.scope, s)


def _prior_day(prior: StudyInputs | None, ctx: PriorContext) -> PriorDaySection:
    reasons = list(ctx.reasons)
    if prior is None:
        reasons.insert(0, "no prior dataset was supplied to the builder")
    if ctx.outcome is ContextOutcome.AVAILABLE:
        qualified = ctx.quality_grade is QualityGrade.QUALITY_QUALIFIED
        status = _status(qualified)
        reasons = list(ctx.quality_reasons) if qualified else []
    else:
        status = ComponentStatus.NOT_AVAILABLE
    return PriorDaySection(status, tuple(reasons), ctx.outcome, prior is not None,
                           prior.source if prior else None, ctx)


def _overnight(session: OvernightSession | None, ctx: OvernightContext | None) -> OvernightSection:
    if session is None:
        return OvernightSection(ComponentStatus.NOT_AVAILABLE, ("no cash-window profile: overnight not built",),
                                None, False, False, False, None, None)
    status = {OvernightQualityGrade.AVAILABLE: ComponentStatus.AVAILABLE,
              OvernightQualityGrade.QUALITY_QUALIFIED: ComponentStatus.QUALITY_QUALIFIED,
              OvernightQualityGrade.NOT_AVAILABLE: ComponentStatus.NOT_AVAILABLE}[session.quality.grade]
    proven = session.globex_open_boundary_proven
    claimed = session.globex_open_price is not None
    reasons = session.quality.reasons + (() if claimed or not session.available else (
        f"Globex open NOT CLAIMED: {session.globex_open_unavailable_reason}",))
    return OvernightSection(status, reasons, session.quality.grade, claimed, proven, claimed and proven, session, ctx)


def _cash_opening(session: CashOpenSession | None, facts: OpeningAuctionFacts | None,
                  path: OpeningPathFacts | None) -> CashOpeningSection:
    if session is None:
        return CashOpeningSection(ComponentStatus.NOT_AVAILABLE, ("no cash-window profile: opening facts not built",),
                                  None, None, None)
    status = {OpeningQualityGrade.UNQUALIFIED: ComponentStatus.AVAILABLE,
              OpeningQualityGrade.QUALITY_QUALIFIED: ComponentStatus.QUALITY_QUALIFIED,
              OpeningQualityGrade.NOT_AVAILABLE: ComponentStatus.NOT_AVAILABLE}[session.quality.grade]
    return CashOpeningSection(status, session.quality.reasons, session.quality.grade, facts, path)


def _opening_type(c: OpeningTypeClassification | None) -> OpeningTypeSection:
    source = policy_source_sha256()
    common = dict(policy_id=OPENING_TYPE_POLICY_ID, policy_version=OPENING_TYPE_POLICY_VERSION,
                  policy_source_sha256=source, policy_frozen_sha256=OPENING_TYPE_V1_SOURCE_SHA256,
                  policy_source_matches_freeze=source == OPENING_TYPE_V1_SOURCE_SHA256,
                  policy_document_sha256=OPENING_TYPE_V1_POLICY_DOC_SHA256)
    if c is None:
        return OpeningTypeSection(ComponentStatus.NOT_AVAILABLE, ("no cash-window profile: not evaluated",), None,
                                  matched=(), deferred=(("OPEN_REJECTION_REVERSE", ORR_DEFERRAL_REASON),),
                                  classification=None, **common)
    deferred = tuple((x.type.value, "; ".join(x.reasons)) for x in c.candidates if x.result is CandidateResult.DEFERRED)
    matched = tuple(MatchedOpeningType(m.type.value, m.direction.value if m.direction else None, m.quality.value)
                    for m in c.matched)
    if c.status is ClassificationStatus.NOT_CLASSIFIED:
        status, reasons = ComponentStatus.NOT_AVAILABLE, c.reasons
    else:
        reasons = tuple(f"{m.type.value}: {reason}" for m in c.matched
                        if m.quality is OpeningQualityGrade.QUALITY_QUALIFIED for reason in m.quality_reasons)
        status = _status(reasons)
    return OpeningTypeSection(status, reasons, c.status, matched=matched, deferred=deferred, classification=c,
                              **common)


# --- canonical serialization ---------------------------------------------------------------------

# Sub-objects serialized once elsewhere in the state ({"$ref": pointer}) or deliberately not
# serialized ({"$omitted": reason}). Everything else is serialized field by field.
SERIALIZATION_REFS: dict[tuple[type, str], str] = {
    (OpeningAuctionFacts, "prior"): "/prior_day/context",
    (OvernightContext, "session"): "/overnight/session",
    (OvernightContext, "prior"): "/prior_day/context",
    (OpeningPathFacts, "opening"): "/cash_opening/facts",
    (OpeningPathFacts, "overnight"): "/overnight/context",
    (OpeningTypeClassification, "facts"): "/cash_opening/path_facts",
}
SERIALIZATION_OMISSIONS: dict[tuple[type, str], str] = {
    (CashOpenSession, "path"): "TAPE_PATH: per-price-change cash path; reproducible from the source dataset",
    (OvernightSession, "path"): "TAPE_PATH: per-price-change overnight path; reproducible from the source dataset",
}


def encode(obj):
    """Canonical JSON-ready form (see module docstring). Raises TypeError on floats or unknown types."""
    if obj is None or isinstance(obj, bool | int) and not isinstance(obj, Enum):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, str):
        return obj
    if isinstance(obj, float):
        raise TypeError("floats are not part of the canonical state")
    if isinstance(obj, Decimal):
        if not obj.is_finite():
            raise TypeError(f"non-finite Decimal {obj}")
        return format(obj, "f")
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            raise TypeError("naive datetime in the canonical state")
        return obj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, time):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return format(Decimal(obj // timedelta(microseconds=1)).scaleb(-6), "f")
    if isinstance(obj, UUID):
        return str(obj)
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        out = {}
        for f in dataclasses.fields(obj):
            value = getattr(obj, f.name)
            key = (type(obj), f.name)
            if key in SERIALIZATION_OMISSIONS:
                out[f.name] = {"$omitted": SERIALIZATION_OMISSIONS[key]}
            elif key in SERIALIZATION_REFS and value is not None:
                out[f.name] = {"$ref": SERIALIZATION_REFS[key]}
            else:
                out[f.name] = encode(value)
        return out
    if isinstance(obj, tuple | list):
        return [encode(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): encode(v) for k, v in obj.items()}
    raise TypeError(f"unsupported type in the canonical state: {type(obj).__name__}")


def _dumps(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def check_references(state: MarketStudyState) -> None:
    """Every $ref must point at the very object it replaces (one provenance chain, no second calculation)."""
    targets = {
        "/prior_day/context": state.prior_day.context,
        "/overnight/session": state.overnight.session,
        "/overnight/context": state.overnight.context,
        "/cash_opening/facts": state.cash_opening.facts,
        "/cash_opening/path_facts": state.cash_opening.path_facts,
    }
    pairs = []
    if state.cash_opening.facts is not None:
        pairs.append((state.cash_opening.facts.prior, "/prior_day/context"))
    if state.overnight.context is not None:
        pairs += [(state.overnight.context.session, "/overnight/session"),
                  (state.overnight.context.prior, "/prior_day/context")]
    if state.cash_opening.path_facts is not None:
        pairs += [(state.cash_opening.path_facts.opening, "/cash_opening/facts"),
                  (state.cash_opening.path_facts.overnight, "/overnight/context")]
    if state.opening_type.classification is not None:
        pairs.append((state.opening_type.classification.facts, "/cash_opening/path_facts"))
    for value, pointer in pairs:
        if value is not None and value is not targets[pointer]:
            raise ValueError(f"$ref {pointer} does not resolve to the serialized object")


def state_payload(state: MarketStudyState) -> dict:
    check_references(state)
    return encode(state)


def canonical_payload_json(state: MarketStudyState) -> str:
    return _dumps(state_payload(state))


def market_study_state_sha256(state: MarketStudyState) -> str:
    """SHA-256 of the canonical payload JSON, which never contains the hash field."""
    return hashlib.sha256(canonical_payload_json(state).encode("ascii")).hexdigest()


def canonical_state_json(state: MarketStudyState) -> str:
    """The canonical document: the payload plus `market_study_state_sha256`."""
    payload = state_payload(state)
    payload[HASH_FIELD] = hashlib.sha256(_dumps(payload).encode("ascii")).hexdigest()
    return _dumps(payload)


def verify_state_json(text: str) -> bool:
    """Recompute the hash of a canonical document without its hash field."""
    document = json.loads(text)
    claimed = document.pop(HASH_FIELD, None)
    return claimed == hashlib.sha256(_dumps(document).encode("ascii")).hexdigest() and _dumps(
        {**document, HASH_FIELD: claimed}) == text


def resolve_pointer(document: dict, pointer: str) -> list:
    """Values at a JSON pointer ('*' expands arrays); used to check the evidence classification."""
    nodes = [document]
    for part in pointer.strip("/").split("/"):
        nxt = []
        for node in nodes:
            if part == "*" and isinstance(node, list):
                nxt += node
            elif isinstance(node, dict) and part in node:
                nxt.append(node[part])
        nodes = nxt
    return nodes


# --- human summary -------------------------------------------------------------------------------

def _v(value) -> str:
    if value is None:
        return "--"
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, datetime):
        return encode(value)
    return str(value)


def _yn(value: bool | None) -> str:
    return "unknown" if value is None else ("yes" if value else "no")


def _head(title: str, section) -> list[str]:
    lines = ["", f"{title}  [{section.status.value}]"]
    lines += [f"  ! {reason}" for reason in section.reasons]
    return lines


def render_summary(state: MarketStudyState, state_sha256: str | None = None) -> str:
    """Evidence by domain. No recommendation, bias or conclusion section."""
    s, d = state, state.current_dataset
    lines = ["MARKET STUDY STATE", f"  Schema: {s.schema}   Temporality: {s.state_temporality.value}",
             f"  {s.temporality_note}",
             f"  Analysis commit: {s.provenance.analysis_git_commit}"
             + ("  (worktree modified)" if s.provenance.analysis_worktree_modified else "")]
    lines += _head("DATASET / QUALITY", s.dataset_quality)
    lines += [f"  Dataset {d.dataset_id}  trading date {d.trading_date}  {d.instrument_id}",
              f"  Source {_v(d.source_system)} {_v(d.streamer_symbol)}  lifecycle {_v(d.lifecycle_state)}  "
              f"collector commit {_v(d.collector_git_commit)}",
              f"  Capture {_v(d.capture_started_at)} .. {_v(d.capture_ended_at)}",
              f"  Closing summary: accepted {_v(d.accepted_trade_count)}  rejected {_v(d.rejected_record_count)}  "
              f"deferred {_v(d.deferred_event_count)}  submitted {_v(d.submitted_events)}  persisted "
              f"{_v(d.persisted_events)}  difference {_v(d.accounting_difference)}",
              f"  Retained {d.retained_trade_count}  corrections {d.applied_correction_count}  cancels "
              f"{d.applied_cancel_count}  database sha256 {_v(d.database_sha256)}",
              f"  Completeness {s.dataset_quality.completeness.value}  KNOWN_GAP {s.dataset_quality.known_gap_count}  "
              f"SUSPECTED_GAP {s.dataset_quality.suspected_gap_count}"]
    lines += [f"  {w.window:<12} fully captured {_yn(w.fully_captured):<7} known gaps {w.known_gaps_overlapping}  "
              f"suspected {w.suspected_gaps_overlapping}" for w in s.dataset_quality.windows]
    c = s.contract
    lines += _head("CONTRACT", c)
    lines += [f"  {c.instrument_id}  {c.root} {c.month_code}{c.contract_year} ({c.product_description or '--'})  "
              f"tick {c.tick_size} ({c.tick_size_source})",
              f"  streamer {_v(c.streamer_symbol)}  broker symbol {_v(c.broker_symbol)} ({c.broker_symbol_status})  "
              f"multiplier {_v(c.multiplier)} ({c.multiplier_status})"]
    lines += _head("VWAP", s.vwap)
    lines += [f"  {v.anchor_kind.value:<13} from {_v(v.anchor_utc)}  VWAP {_v(v.vwap)}  trades "
              f"{_v(v.included_trade_count)}  volume {_v(v.included_volume)}  [{v.status.value}]" for v in s.vwap.studies]
    vp = s.volume_profile
    lines += _head("VOLUME PROFILE (cash study window)", vp)
    lines.append(f"  POC {_v(vp.poc)}  VAL {_v(vp.value_area_low)}  VAH {_v(vp.value_area_high)}  high "
                 f"{_v(vp.profile_high)}  low {_v(vp.profile_low)}  volume {_v(vp.total_volume)}  levels "
                 f"{_v(vp.level_count)}")
    p = s.tpo.profile
    lines += _head("TPO / INITIAL BALANCE", s.tpo)
    if p is not None:
        ib = p.initial_balance
        lines += [f"  {s.tpo.window_id} {s.tpo.period_minutes}-min periods, increment {p.price_increment}; "
                  f"high {p.profile_high}  low {p.profile_low}",
                  f"  TPO POC {p.poc}  VAL {p.value_area.low}  VAH {p.value_area.high}  value area "
                  f"{(p.value_area.included_fraction * 100).quantize(Decimal('0.01'))}%",
                  "  IB " + ("not available" if ib is None else
                             f"{ib.low}-{ib.high} ({ib.range}); extension above {ib.extension_above}, "
                             f"below {ib.extension_below}")]
    st = s.tpo_structure.structure
    lines += _head("PROFILE STRUCTURE", s.tpo_structure)
    if st is not None:
        lines += [f"  one-TPO zones {len(st.zones)}; upper tail {st.upper.tail_level_count} rows, lower tail "
                  f"{st.lower.tail_level_count} rows",
                  f"  EXCESS_HIGH_CANDIDATE {st.upper.excess_candidate.value}  POOR_HIGH_CANDIDATE "
                  f"{st.upper.poor_candidate.value}  EXCESS_LOW_CANDIDATE {st.lower.excess_candidate.value}  "
                  f"POOR_LOW_CANDIDATE {st.lower.poor_candidate.value}"]
    dt = s.day_type.classification
    lines += _head("DAY TYPE CANDIDATE (DAY_TYPE_V1)", s.day_type)
    if dt is not None:
        label = (f"{dt.primary.value}_CANDIDATE" + (f" {dt.direction.value}" if dt.direction else "")
                 if dt.primary else "--")
        lines.append(f"  outcome {dt.outcome.value}  candidate {label}  quality {dt.quality.grade.value}")
        lines.append("  deferred: " + ", ".join(x.name for x in dt.deferred))
    ds = s.day_strength.strength
    lines += _head("DAY STRENGTH (DAY_STRUCTURE_STRENGTH_V1)", s.day_strength)
    if ds is not None:
        lines += [f"  directional state {_v(ds.directional_state)}  dominant {_v(ds.dominant_extension)}  "
                  f"above {_v(ds.extension_above_ticks)} ticks  below {_v(ds.extension_below_ticks)} ticks  "
                  f"counter/dominant {_v(ds.counter_to_dominant)}",
                  f"  terminal {_v(ds.terminal_price)} at percentile {_v(ds.terminal_percentile)}"]
    pd = s.prior_day
    lines += _head("PRIOR DAY", pd)
    ctx = pd.context
    lines.append(f"  outcome {pd.outcome.value if pd.outcome else '--'}  expected {ctx.expected_prior_date}  "
                 f"supplied {'yes' if pd.prior_dataset_supplied else 'no'}"
                 + (f" ({pd.source.dataset_id}, {pd.source.trading_date}, {pd.source.instrument_id})" if pd.source else ""))
    if ctx.usable:
        lines.append(f"  high {ctx.profile_high}  low {ctx.profile_low}  POC {ctx.poc}  VAL {ctx.value_area_low}  "
                     f"VAH {ctx.value_area_high}  IB {_v(ctx.ib_low)}-{_v(ctx.ib_high)}  terminal "
                     f"{_v(ctx.terminal_price)}  V1 {_v(ctx.day_type) if ctx.day_type else ctx.day_type_outcome}"
                     + (f" {ctx.day_type_direction}" if ctx.day_type_direction else ""))
    on = s.overnight
    lines += _head("OVERNIGHT (OVERNIGHT_CONTEXT_V1)", on)
    if on.session is not None and on.session.available:
        o = on.session
        lines += [f"  Globex open claimed: {'yes' if on.globex_open_claimed else 'no'}   first observed overnight "
                  f"trade {o.first_price} at {_v(o.first_utc)} (not the Globex open unless claimed)",
                  f"  ONH {o.high}  ONL {o.low}  range {o.range_ticks} ticks  last {o.terminal_price}"]
        if on.context is not None and on.context.open_location is not None:
            lines.append(f"  cash open {on.context.open_location.value}, percentile "
                         f"{_v(on.context.open_percentile_in_overnight_range)}")
    co = s.cash_opening
    lines += _head("CASH OPENING (OPENING_AUCTION_FACTS_V1)", co)
    if co.facts is not None:
        f, op = co.facts, co.facts.session.cash_open
        lines.append(f"  open {_v(op.price)} at {_v(op.timestamp_utc)} (delay {_v(op.delay)})  vs prior range "
                     f"{_v(f.range_location)}  vs prior value {_v(f.value_location)}  gap {_v(f.gap_ticks)} ticks")
        for w in f.session.windows:
            lines.append(f"  {w.minutes:>2} min: high {w.high} low {w.low} up {w.excursion_up_ticks} down "
                         f"{w.excursion_down_ticks} ticks, open crosses {w.open_cross_count}")
    ot = s.opening_type
    lines += _head("OPENING-TYPE CANDIDATES (OPENING_TYPE_V1)", ot)
    lines.append(f"  status {_v(ot.classification_status)}  policy source matches freeze: "
                 f"{'yes' if ot.policy_source_matches_freeze else 'NO'}  (candidate set; no primary type)")
    lines += [f"  CANDIDATE {m.type}" + (f" {m.direction}" if m.direction else "") + f"  [{m.quality}]"
              for m in ot.matched] or ["  no matched candidate"]
    lines += [f"  DEFERRED {name}: {reason}" for name, reason in ot.deferred]
    lines += ["", "QUALITY MATRIX"]
    lines += [f"  {q.component:<15} {q.status.value:<18} {q.domain_status or ''}" for q in s.quality_matrix]
    lines += ["", "POLICY VERSIONS"]
    lines += [f"  {e.component:<26} {e.policy_id or '(none)'} {e.policy_version or ''}".rstrip()
              for e in s.policy_registry]
    lines += ["", f"STATE HASH  {state_sha256 or market_study_state_sha256(s)}",
              "Evidence only: candidate labels are Laboratory policy outputs, not market opinion or a "
              "trading recommendation."]
    return "\n".join(lines) + "\n"
