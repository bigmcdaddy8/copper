"""Model evidence for one replay position (0AC-A3), as a Laboratory TutorLesson the frozen validator can check.

    ChartTimeline position at cutoff T  (the same as-of bars that feed the chart and Show Evidence)
        -> TUTOR_POC_MODEL_EVIDENCE_V1 document (latest completed bar + RECENT_BARS-1 bars before it)
        -> EvidenceItem / SnapshotEvidence / TutorEvidenceContext / TutorLesson   (dicks_laboratory.tutor_evidence)
        -> parse_answer / validate_answer_grounding / answer_guards                 (frozen, reused unchanged)

Adapter, not a new evidence model: the frozen Laboratory types refer to evidence by
EvidenceRef(source_sha256, RFC 6901 pointer) into a canonical document. Here that document is the chart
position's own evidence instead of a MARKET_STUDY_SNAPSHOT_V1 (whose price-action facts use the cash VWAP
and need a full replay per turn; the chart is Globex-anchored). Nothing is computed beyond the bars the
Laboratory prepared: the only relations added (close vs VWAP, its distance, the close's band region) are
comparisons of values in the same document, so the model never has to do arithmetic.

No-lookahead: the document is built from `tl.positions[index]` only, whose bars all end at or before the
cutoff. Nothing later exists in it.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID
from zoneinfo import ZoneInfo

from dicks_laboratory.tutor_evidence import (
    ANSWER_SCHEMA,
    AS_OF,
    CONTEXT_SCHEMA,
    LAB_MODULE,
    LAB_SOURCE,
    LESSON_SCHEMA,
    RECENT_BARS,
    AnswerKey,
    Availability,
    ClaimCategory,
    EvidenceDomain,
    EvidenceItem,
    EvidenceRef,
    EvidenceSupport,
    GradingRubric,
    LessonDefinition,
    LessonMode,
    LessonStage,
    QuestionKind,
    SnapshotEvidence,
    SourceRole,
    TutorAnswer,
    TutorEvidenceContext,
    TutorLesson,
    canonical_json,
    lesson_definition_sha256,
)

from tutor_poc.dev_sessions import INSTRUMENT
from tutor_poc.snapshot import PRICE_GRID
from tutor_poc.timeline import BAND_POLICY, ChartBar, ChartTimeline

MODEL_EVIDENCE_SCHEMA = "TUTOR_POC_MODEL_EVIDENCE_V1"
CT = ZoneInfo("America/Chicago")
ROLE = SourceRole.LESSON_TIME  # the only source a POC answer may cite
CENT = Decimal("0.01")
_O, _D = ClaimCategory.OBSERVED_FACT, ClaimCategory.DERIVED_FACT
DOMAINS = (EvidenceDomain.PRICE, EvidenceDomain.VWAP, EvidenceDomain.VWAP_BANDS, EvidenceDomain.PRICE_ACTION_BARS)


def _ct(t: datetime) -> str:
    return t.astimezone(CT).strftime("%H:%M")


def _price(v: Decimal) -> str:
    return f"{v:.2f}"  # bar prices are on the 0.25 tick grid: exact at two decimals


def _level(v: Decimal) -> str:
    """Analytical values (VWAP, sigma levels, distances) at 0.01, half-even: what the evidence panel shows."""
    return str(v.quantize(CENT, rounding=ROUND_HALF_EVEN))


def close_vs_vwap(b: ChartBar) -> str:
    return "ABOVE" if b.close > b.vwap else "BELOW" if b.close < b.vwap else "AT"


def close_region(b: ChartBar) -> str:
    """Which A1P chart region holds the close (level1: -1σ..+1σ, level2: ±1σ..±2σ), on exact values."""
    if b.close > b.upper_2sd:
        return "ABOVE_PLUS_2_SIGMA"
    if b.close > b.upper_1sd:
        return "LEVEL_2_UPPER (between +1σ and +2σ)"
    if b.close >= b.lower_1sd:
        return "LEVEL_1 (between -1σ and +1σ)"
    if b.close >= b.lower_2sd:
        return "LEVEL_2_LOWER (between -2σ and -1σ)"
    return "BELOW_MINUS_2_SIGMA"


def evidence_document(tl: ChartTimeline, index: int) -> dict:
    """The canonical evidence document for the position. Only bars known at its cutoff."""
    p = tl.positions[index]
    bars = [b for b in p.bars if b.end_utc <= p.cutoff_utc]
    doc = {"schema": MODEL_EVIDENCE_SCHEMA, "instrument": INSTRUMENT, "trading_date": tl.trading_date.isoformat(),
           "replay": {"cutoff_ct": _ct(p.cutoff_utc), "completed_bars": len(bars)},
           "study": {"bar_interval": "5m", "vwap_anchor": "GLOBEX", "vwap_anchor_ct": _ct(tl.anchor_utc),
                     "band_policy": BAND_POLICY, "tick_size": f"{PRICE_GRID['tick_size']:.2f}"},
           "latest_bar": None, "recent_bars": []}
    if not bars:
        return doc
    b = bars[-1]
    doc["latest_bar"] = {
        "start_ct": _ct(b.start_utc), "end_ct": _ct(b.end_utc), "open": _price(b.open), "high": _price(b.high),
        "low": _price(b.low), "close": _price(b.close), "vwap": _level(b.vwap), "upper_1sd": _level(b.upper_1sd),
        "lower_1sd": _level(b.lower_1sd), "upper_2sd": _level(b.upper_2sd), "lower_2sd": _level(b.lower_2sd),
        "close_vs_vwap": close_vs_vwap(b), "close_minus_vwap": _level(b.close - b.vwap),
        "close_region": close_region(b)}
    doc["recent_bars"] = [{"start_ct": _ct(r.start_utc), "end_ct": _ct(r.end_utc), "open": _price(r.open),
                           "high": _price(r.high), "low": _price(r.low), "close": _price(r.close),
                           "vwap": _level(r.vwap), "close_vs_vwap": close_vs_vwap(r)}
                          for r in bars[-RECENT_BARS:-1]]  # oldest first, the latest bar excluded
    return doc


# (field, label suffix, category, domain)
_STUDY = (("vwap_anchor", "VWAP anchor", _D, EvidenceDomain.VWAP),
          ("vwap_anchor_ct", "VWAP anchor time (CT, the Globex open)", _D, EvidenceDomain.VWAP),
          ("band_policy", "VWAP band policy", _D, EvidenceDomain.VWAP_BANDS),
          ("tick_size", "/ES tick size", _O, EvidenceDomain.PRICE),
          ("bar_interval", "bar interval", _D, EvidenceDomain.PRICE_ACTION_BARS))
_LATEST = (("start_ct", "start time (CT)", _D, EvidenceDomain.PRICE_ACTION_BARS),
           ("end_ct", "end time (CT)", _D, EvidenceDomain.PRICE_ACTION_BARS),
           ("open", "open", _O, EvidenceDomain.PRICE), ("high", "high", _O, EvidenceDomain.PRICE),
           ("low", "low", _O, EvidenceDomain.PRICE), ("close", "close", _O, EvidenceDomain.PRICE),
           ("vwap", "Globex VWAP at the bar's close", _D, EvidenceDomain.VWAP),
           ("upper_2sd", "+2σ band", _D, EvidenceDomain.VWAP_BANDS),
           ("upper_1sd", "+1σ band", _D, EvidenceDomain.VWAP_BANDS),
           ("lower_1sd", "-1σ band", _D, EvidenceDomain.VWAP_BANDS),
           ("lower_2sd", "-2σ band", _D, EvidenceDomain.VWAP_BANDS),
           ("close_vs_vwap", "close vs VWAP", _D, EvidenceDomain.VWAP),
           ("close_minus_vwap", "close minus VWAP (points)", _D, EvidenceDomain.VWAP),
           ("close_region", "band region holding the close", _D, EvidenceDomain.VWAP_BANDS))
_RECENT = (("start_ct", "start (CT)", _D, EvidenceDomain.PRICE_ACTION_BARS),
           ("end_ct", "end (CT)", _D, EvidenceDomain.PRICE_ACTION_BARS),
           ("open", "open", _O, EvidenceDomain.PRICE), ("high", "high", _O, EvidenceDomain.PRICE),
           ("low", "low", _O, EvidenceDomain.PRICE), ("close", "close", _O, EvidenceDomain.PRICE),
           ("vwap", "Globex VWAP at its close", _D, EvidenceDomain.VWAP),
           ("close_vs_vwap", "close vs VWAP", _D, EvidenceDomain.VWAP))


def _items(doc: dict, sha: str) -> tuple[EvidenceItem, ...]:
    def item(pointer, label, value, category, domain):
        return EvidenceItem(EvidenceRef(sha, pointer), domain, label, value, category, Availability.AVAILABLE,
                            "COMPLETE" if pointer.startswith(("/latest_bar", "/recent_bars")) else None, "AVAILABLE")

    out = [item(f"/study/{k}", s, doc["study"][k], c, d) for k, s, c, d in _STUDY]
    out.append(item("/replay/cutoff_ct", "replay cutoff (CT)", doc["replay"]["cutoff_ct"], _D,
                    EvidenceDomain.PRICE_ACTION_BARS))
    out.append(item("/replay/completed_bars", "completed 5m bars in the session so far",
                    doc["replay"]["completed_bars"], _D, EvidenceDomain.PRICE_ACTION_BARS))
    if doc["latest_bar"] is not None:
        out += [item(f"/latest_bar/{k}", f"latest completed bar {s}", doc["latest_bar"][k], c, d)
                for k, s, c, d in _LATEST]
    for i, r in enumerate(doc["recent_bars"]):
        out += [item(f"/recent_bars/{i}/{k}", f"bar {r['start_ct']}-{r['end_ct']} CT {s}", r[k], c, d)
                for k, s, c, d in _RECENT]
    return tuple(out)


@dataclass(frozen=True)
class ChartLesson:
    lesson: TutorLesson
    document: dict
    sha256: str


def chart_lesson(tl: ChartTimeline, index: int, lesson_id: str) -> ChartLesson:
    """A TutorLesson whose only authorized evidence is this replay position's document.

    The frozen LessonDefinition requires a QuestionKind; free conversation has none, so the adapter uses
    PRICE_VS_CASH_VWAP only to satisfy construction (its required PRICE / VWAP domains). The kind, the
    placeholder answer key and the reference answer are never sent to a model and nothing is graded
    against them; the answer key's support is SUPPORTED so the frozen INSUFFICIENT_EVIDENCE_NOT_STATED guard
    adds no lesson-specific requirement. The module is the Laboratory module (not Drysdale), so the V2
    answer guards apply.
    """
    doc = evidence_document(tl, index)
    sha = hashlib.sha256(canonical_json(doc).encode("ascii")).hexdigest()
    items = _items(doc, sha)
    cutoff = tl.positions[index].cutoff_utc
    definition = LessonDefinition(
        lesson_id, "Free conversation at the replay position", "Study the chart with grounded evidence",
        LessonMode.EXPLAIN_EVIDENCE, QuestionKind.PRICE_VS_CASH_VWAP, "(free conversation)", tl.trading_date, cutoff,
        DOMAINS, LAB_MODULE.module_id, (LAB_SOURCE.source_id,))
    snap = SnapshotEvidence(ROLE, sha, cutoff, cutoff, AS_OF, items, ())
    context = TutorEvidenceContext(CONTEXT_SCHEMA, lesson_id, tl.trading_date, UUID(tl.dataset_id), INSTRUMENT, AS_OF,
                                   cutoff, cutoff, sha, tuple(sorted(DOMAINS)), (snap,), None, (), (), None,
                                   (LAB_SOURCE.source_id,))
    reference = TutorAnswer(ANSWER_SCHEMA, lesson_id, LessonStage.QUESTION, sha, "", (), (), (), ())
    key = AnswerKey(QuestionKind.PRICE_VS_CASH_VWAP, EvidenceSupport.SUPPORTED, None, (), (),
                    GradingRubric((), (), (), (), False), reference)
    lesson = TutorLesson(LESSON_SCHEMA, definition, lesson_definition_sha256(definition), context, key, None,
                         ((sha, doc),))
    return ChartLesson(lesson, doc, sha)


def model_evidence(cl: ChartLesson) -> dict:
    """The evidence section a model receives: citable items (no hashes, ids or paths)."""
    return {"schema": MODEL_EVIDENCE_SCHEMA, "instrument": cl.document["instrument"],
            "trading_date": cl.document["trading_date"], "replay_cutoff_ct": cl.document["replay"]["cutoff_ct"],
            "items": [{"source": ROLE.value, "pointer": i.ref.pointer, "label": i.label, "value": i.value,
                       "category": i.category.value} for i in cl.lesson.context.snapshots[0].items],
            "quality_warnings": [w.warning_id for w in cl.lesson.context.quality_warnings],
            "curriculum_source_ids": list(cl.lesson.context.curriculum_source_ids)}
