"""Model evidence for one replay position, as a Laboratory TutorLesson the frozen validator can check.

0AC-A3 gave the model the latest bar with its bands and five earlier bars without them. 0AC-A4 (V2):

    ChartTimeline position at cutoff T        the as-of bars that feed the chart (LESSON_TIME source)
        -> TUTOR_POC_MODEL_EVIDENCE_V2        every bar of the window (latest + RECENT_BARS-1 before it) with its
                                              OWN as-of OHLC, Globex VWAP and +/-1 / +/-2 sigma, band relations,
                                              the frozen per-bar facts (DRYSDALE_VALUE_AREA_V1 position,
                                              LAB_VWAP_SLOPE_V1), bar-to-bar comparisons and window counts
    SetupTimeline projection at cutoff T      the frozen DRYSDALE_SETUP_ANALYSIS_V1 at T (DRYSDALE source)
        -> TUTOR_POC_SETUP_EVIDENCE_V1        analysis state and quality, context facts, the latest instance of
                                              every family x direction (8 rows) with each condition status, the
                                              instances completed so far, and the setup catalog
        -> EvidenceItem / SnapshotEvidence / TutorEvidenceContext / TutorLesson   (dicks_laboratory.tutor_evidence)
        -> parse_answer / validate_answer_grounding / answer_guards                 (frozen, reused unchanged)

The lesson belongs to the frozen Drysdale module (DRYSDALE_VWAP_WAVE_V1), so the frozen two-voice guards apply:
a Drysdale concept is stated as SOURCE SAYS (CURRICULUM_RULE), as a LABORATORY V1 result that cites and asserts
a DRYSDALE item, or as AI_INTERPRETATION.

Nothing is computed beyond the Laboratory's values except plain comparisons and counts of values in the same
document (close vs a band, higher / lower than the previous bar, how many closes above VWAP, the VWAP change
across the window), so the model never has to do arithmetic. No trend label, no threshold, no new indicator.

No-lookahead: the documents are built from `tl.positions[index]` and the projection at the same cutoff, whose
bars all end at or before the cutoff. A bar's values are the ones known at the cutoff (a late print revises a
completed bar only once it is known); `revised_since_completion` compares them with the same bar as first
completed, an earlier position, never a later one.
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
    DRYSDALE_BOOK_SOURCE,
    DRYSDALE_MODULE,
    DRYSDALE_SOURCE,
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
    QualityWarning,
    QuestionKind,
    SnapshotEvidence,
    SourceRole,
    TutorAnswer,
    TutorEvidenceContext,
    TutorLesson,
    canonical_json,
    lesson_definition_sha256,
    resolve_pointer,
)

from tutor_poc.catalog import CATALOG, CATALOG_VERSION, DIRECTIONS, FAMILIES
from tutor_poc.dev_sessions import INSTRUMENT
from tutor_poc.snapshot import PRICE_GRID
from tutor_poc.timeline import BAND_POLICY, STEP, ChartBar, ChartTimeline

MODEL_EVIDENCE_SCHEMA = "TUTOR_POC_MODEL_EVIDENCE_V2"
SETUP_EVIDENCE_SCHEMA = "TUTOR_POC_SETUP_EVIDENCE_V1"
CT = ZoneInfo("America/Chicago")
ROLE = SourceRole.LESSON_TIME  # the chart position's bars
SETUP_ROLE = SourceRole.DRYSDALE  # the frozen setup analysis at the same cutoff
ROLES = (ROLE, SETUP_ROLE)
CENT = Decimal("0.01")
_O, _D, _R, _C, _Q = (ClaimCategory.OBSERVED_FACT, ClaimCategory.DERIVED_FACT, ClaimCategory.LABORATORY_POLICY_RESULT,
                      ClaimCategory.CANDIDATE, ClaimCategory.QUALITY_WARNING)
DOMAINS = (EvidenceDomain.PRICE, EvidenceDomain.VWAP, EvidenceDomain.VWAP_BANDS, EvidenceDomain.PRICE_ACTION_BARS,
           EvidenceDomain.DRYSDALE_SETUPS)
SOURCES = (LAB_SOURCE.source_id, DRYSDALE_SOURCE.source_id, DRYSDALE_BOOK_SOURCE.source_id)
DRYSDALE_WARNING = f"{SETUP_ROLE.value}:drysdale"  # the frozen Laboratory warning id for a qualified analysis


class EvidenceMismatch(RuntimeError):
    """The chart position and the setup projection disagree (they must come from the same as-of tape)."""


def _ct(t: datetime | str | None) -> str | None:
    if t is None:
        return None
    t = datetime.fromisoformat(t) if isinstance(t, str) else t
    return t.astimezone(CT).strftime("%H:%M")


def _price(v: Decimal) -> str:
    return f"{v:.2f}"  # bar prices are on the 0.25 tick grid: exact at two decimals


def _level(v: Decimal) -> str:
    """Analytical values (VWAP, sigma levels, distances) at 0.01, half-even: what the evidence panel shows."""
    return str(v.quantize(CENT, rounding=ROUND_HALF_EVEN))


def _side(a: Decimal, b: Decimal) -> str:
    return "ABOVE" if a > b else "BELOW" if a < b else "AT"


def close_vs_vwap(b: ChartBar) -> str:
    return _side(b.close, b.vwap)


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


def _cmp(a: Decimal, b: Decimal) -> str:
    return "HIGHER" if a > b else "LOWER" if a < b else "EQUAL"


def _same(a: ChartBar, b: ChartBar) -> bool:
    return all(getattr(a, f) == getattr(b, f) for f in ("open", "high", "low", "close", "volume", "vwap", "sigma"))


def _completed_version(tl: ChartTimeline, index: int, b: ChartBar) -> ChartBar | None:
    """The bar as known at the position where it first completed (an earlier or the same position)."""
    p = tl.positions[index]
    j = index - int((p.cutoff_utc - b.end_utc) / STEP)
    if not (0 <= j <= index) or tl.positions[j].cutoff_utc != b.end_utc:
        j = next((k for k in range(index + 1) if tl.positions[k].cutoff_utc == b.end_utc), None)
        if j is None:
            return None
    return next((x for x in tl.positions[j].bars if x.start_utc == b.start_utc), None)


# Columns of the bar table: (column, category). The row's pointer is /latest_bar or /recent_bars/<i>.
BAR_COLUMNS = (
    ("start_ct", _D), ("end_ct", _D), ("open", _O), ("high", _O), ("low", _O), ("close", _O), ("vwap", _D),
    ("upper_2sd", _D), ("upper_1sd", _D), ("lower_1sd", _D), ("lower_2sd", _D), ("close_vs_vwap", _D),
    ("close_minus_vwap", _D), ("close_region", _D), ("close_vs_upper_2sd", _D), ("close_vs_upper_1sd", _D),
    ("close_vs_lower_1sd", _D), ("close_vs_lower_2sd", _D), ("value_position", _D), ("vwap_slope", _D),
    ("close_vs_prev_close", _D), ("high_vs_prev_high", _D), ("low_vs_prev_low", _D),
    ("revised_since_completion", _D))
BAR_LABELS = {
    "start_ct": "start (CT)", "end_ct": "end (CT)", "open": "open", "high": "high", "low": "low", "close": "close",
    "vwap": "Globex VWAP at its close", "upper_2sd": "+2σ band at its close", "upper_1sd": "+1σ band at its close",
    "lower_1sd": "-1σ band at its close", "lower_2sd": "-2σ band at its close", "close_vs_vwap": "close vs VWAP",
    "close_minus_vwap": "close minus VWAP (points)", "close_region": "band region holding the close",
    "close_vs_upper_2sd": "close vs +2σ", "close_vs_upper_1sd": "close vs +1σ", "close_vs_lower_1sd": "close vs -1σ",
    "close_vs_lower_2sd": "close vs -2σ",
    "value_position": "close vs the Drysdale VWAP value area (DRYSDALE_VALUE_AREA_V1, Globex VWAP ±1σ inclusive)",
    "vwap_slope": "Globex VWAP slope vs the previous bar (LAB_VWAP_SLOPE_V1)",
    "close_vs_prev_close": "close vs the previous bar's close", "high_vs_prev_high": "high vs the previous bar's high",
    "low_vs_prev_low": "low vs the previous bar's low",
    "revised_since_completion": "values revised by a late print since the bar completed (as known at the cutoff)"}


def _bar_row(b: ChartBar, prev: ChartBar | None, frozen: dict, revised: bool) -> dict:
    return {
        "start_ct": _ct(b.start_utc), "end_ct": _ct(b.end_utc), "open": _price(b.open), "high": _price(b.high),
        "low": _price(b.low), "close": _price(b.close), "vwap": _level(b.vwap), "upper_2sd": _level(b.upper_2sd),
        "upper_1sd": _level(b.upper_1sd), "lower_1sd": _level(b.lower_1sd), "lower_2sd": _level(b.lower_2sd),
        "close_vs_vwap": close_vs_vwap(b), "close_minus_vwap": _level(b.close - b.vwap), "close_region": close_region(b),
        "close_vs_upper_2sd": _side(b.close, b.upper_2sd), "close_vs_upper_1sd": _side(b.close, b.upper_1sd),
        "close_vs_lower_1sd": _side(b.close, b.lower_1sd), "close_vs_lower_2sd": _side(b.close, b.lower_2sd),
        "value_position": frozen["value_position"], "vwap_slope": frozen["vwap_slope"],
        "close_vs_prev_close": None if prev is None else _cmp(b.close, prev.close),
        "high_vs_prev_high": None if prev is None else _cmp(b.high, prev.high),
        "low_vs_prev_low": None if prev is None else _cmp(b.low, prev.low),
        "revised_since_completion": revised}


def _streak(rows: list[dict], column: str, value: str) -> int:
    n = 0
    for r in reversed(rows):
        if r[column] != value:
            break
        n += 1
    return n


def _sequence(rows: list[dict], bars: list[ChartBar]) -> dict:
    def count(col, val):
        return sum(1 for r in rows if r[col] == val)

    return {"window_bars": len(rows), "first_bar_start_ct": rows[0]["start_ct"],
            "closes_above_vwap": count("close_vs_vwap", "ABOVE"), "closes_below_vwap": count("close_vs_vwap", "BELOW"),
            "closes_above_upper_1sd": count("close_vs_upper_1sd", "ABOVE"),
            "closes_below_lower_1sd": count("close_vs_lower_1sd", "BELOW"),
            "closes_above_upper_2sd": count("close_vs_upper_2sd", "ABOVE"),
            "closes_below_lower_2sd": count("close_vs_lower_2sd", "BELOW"),
            "consecutive_higher_closes": _streak(rows, "close_vs_prev_close", "HIGHER"),
            "consecutive_lower_closes": _streak(rows, "close_vs_prev_close", "LOWER"),
            "consecutive_higher_highs": _streak(rows, "high_vs_prev_high", "HIGHER"),
            "consecutive_lower_highs": _streak(rows, "high_vs_prev_high", "LOWER"),
            "consecutive_higher_lows": _streak(rows, "low_vs_prev_low", "HIGHER"),
            "consecutive_lower_lows": _streak(rows, "low_vs_prev_low", "LOWER"),
            "vwap_rising_bars": count("vwap_slope", "RISING"), "vwap_falling_bars": count("vwap_slope", "FALLING"),
            "vwap_change_over_window": _level(bars[-1].vwap - bars[0].vwap)}


_SEQUENCE_LABELS = {
    "window_bars": "bars in the evidence window", "first_bar_start_ct": "first bar of the window (CT)",
    "closes_above_vwap": "closes above VWAP in the window", "closes_below_vwap": "closes below VWAP in the window",
    "closes_above_upper_1sd": "closes above their +1σ in the window",
    "closes_below_lower_1sd": "closes below their -1σ in the window",
    "closes_above_upper_2sd": "closes above their +2σ in the window",
    "closes_below_lower_2sd": "closes below their -2σ in the window",
    "consecutive_higher_closes": "consecutive higher closes ending at the latest bar (counted in the window)",
    "consecutive_lower_closes": "consecutive lower closes ending at the latest bar (counted in the window)",
    "consecutive_higher_highs": "consecutive higher highs ending at the latest bar (counted in the window)",
    "consecutive_lower_highs": "consecutive lower highs ending at the latest bar (counted in the window)",
    "consecutive_higher_lows": "consecutive higher lows ending at the latest bar (counted in the window)",
    "consecutive_lower_lows": "consecutive lower lows ending at the latest bar (counted in the window)",
    "vwap_rising_bars": "bars whose Globex VWAP rose vs the previous bar (LAB_VWAP_SLOPE_V1 RISING)",
    "vwap_falling_bars": "bars whose Globex VWAP fell vs the previous bar (LAB_VWAP_SLOPE_V1 FALLING)",
    "vwap_change_over_window": "Globex VWAP change from the first to the latest bar of the window (points)"}


def evidence_document(tl: ChartTimeline, index: int, setup: dict) -> dict:
    """The LESSON_TIME evidence document for the position. Only bars known at its cutoff."""
    p = tl.positions[index]
    bars = [b for b in p.bars if b.end_utc <= p.cutoff_utc]
    if setup["cutoff_utc"] != p.cutoff_utc.isoformat():
        raise EvidenceMismatch(f"setup projection {setup['cutoff_utc']} is not position {p.cutoff_utc.isoformat()}")
    window = bars[-RECENT_BARS:]
    frozen = {datetime.fromisoformat(b["end_utc"]): b for b in setup["bars"]}
    rows = []
    for k, b in enumerate(window):
        f = frozen.get(b.end_utc)
        if f is None or Decimal(f["close"]) != b.close:
            raise EvidenceMismatch(f"bar ending {b.end_utc.isoformat()} differs from the setup analysis")
        prev = bars[len(bars) - len(window) + k - 1] if len(bars) - len(window) + k > 0 else None
        first = _completed_version(tl, index, b)
        rows.append(_bar_row(b, prev, f, first is not None and not _same(first, b)))
    cutoff_ct = _ct(p.cutoff_utc)
    doc = {"schema": MODEL_EVIDENCE_SCHEMA, "instrument": INSTRUMENT, "trading_date": tl.trading_date.isoformat(),
           "replay": {"cutoff_ct": cutoff_ct, "completed_bars": len(bars), "values_as_of_ct": cutoff_ct,
                      "revised_bars_in_window": sum(1 for r in rows if r["revised_since_completion"])},
           "study": {"bar_interval": "5m", "vwap_anchor": "GLOBEX", "vwap_anchor_ct": _ct(tl.anchor_utc),
                     "band_policy": BAND_POLICY, "tick_size": f"{PRICE_GRID['tick_size']:.2f}"},
           "latest_bar": rows[-1] if rows else None, "recent_bars": rows[:-1],  # oldest first, latest excluded
           "sequence": _sequence(rows, window) if rows else None}
    return doc


def _setup_rows(setup: dict) -> list[dict]:
    latest = {(c["family"], c["direction"]): c for c in setup["latest"]}
    out = []
    for f in FAMILIES:
        for d in DIRECTIONS:
            c = latest.get((f.value, d.value))
            out.append({
                "family": f.value, "direction": d.value, "instance_exists": c is not None,
                "instance_id": c and c["candidate_id"], "state": c and c["state"], "stage": c and c["stage"],
                "can_still_complete": c and c["can_still_complete"], "first_event_ct": c and _ct(c["first_event_utc"]),
                "completed_at_ct": c and _ct(c["completed_at_utc"]),
                "conditions": [] if c is None else [{"order": k["order"], "policy_id": k["policy_id"],
                                                     "status": k["status"], "satisfied_at_ct": _ct(k["satisfied_at_utc"])}
                                                    for k in c["conditions"]]})
    return out


def setup_document(setup: dict) -> dict:
    """The DRYSDALE evidence document: the frozen analysis projection at the cutoff, plus the catalog."""
    x = setup["context"]
    return {
        "schema": SETUP_EVIDENCE_SCHEMA, "projection_of": "DRYSDALE_SETUP_ANALYSIS_V1",
        "drysdale_sha256": setup["drysdale_sha256"], "cutoff_ct": _ct(setup["cutoff_utc"]),
        "analysis": {"candidates_policy": CATALOG["candidates_policy"], "state": setup["state"],
                     "quality_status": setup["status"], "quality_reasons": "; ".join(setup["reasons"]),
                     "bands_maturity": setup["bands_maturity"], "instances_so_far": setup["instances"]},
        "context": None if x is None else {
            "value_position": x["value_position"], "vwap_slope": x["vwap_slope"],
            "vwap_delta": None if x["vwap_delta"] is None else _level(Decimal(x["vwap_delta"])),
            "trend_context": x["trend_context"] or "NEITHER",
            "current_episode_region": x["current_episode_region"],
            "current_episode_closes": x["current_episode_closes"],
            "current_episode_lab_acceptance_time_v1": x["current_episode_lab_acceptance_time_v1"],
            "higher_high": x["higher_high"], "higher_low": x["higher_low"], "lower_high": x["lower_high"],
            "lower_low": x["lower_low"], "consecutive_higher_highs_and_lows": x["consecutive_higher_highs_and_lows"],
            "consecutive_lower_highs_and_lows": x["consecutive_lower_highs_and_lows"],
            "recent_up_closes": x["recent_up_closes"], "recent_down_closes": x["recent_down_closes"],
            "session_bars_reaching_2sd": x["session_bars_reaching_2sd"],
            "volume_ratio_to_mean": None if x["volume_ratio_to_mean"] is None
            else _level(Decimal(x["volume_ratio_to_mean"]))},
        "setups": _setup_rows(setup),
        "completed_today": [{"instance_id": c["candidate_id"], "family": c["family"], "direction": c["direction"],
                             "state": c["state"], "completed_at_ct": _ct(c["completed_at_utc"])}
                            for c in setup["completed"]],
        "catalog": CATALOG}


_ANALYSIS = (("candidates_policy", "setup rules (Laboratory V1)", _R),
             ("state", "Drysdale setup analysis state (DRYSDALE_SETUP_CANDIDATES_V1)", _C),
             ("quality_status", "setup analysis quality status (inherited by every instance)", _Q),
             ("quality_reasons", "setup analysis quality reasons", _Q),
             ("bands_maturity", "VWAP_BANDS_GLOBEX_V1 maturity", _R),
             ("instances_so_far", "setup instances in this session so far", _D))
_CONTEXT = (("value_position", "last complete close vs the Drysdale VWAP value area", _D),
            ("vwap_slope", "Globex VWAP slope at the last complete bar (LAB_VWAP_SLOPE_V1)", _D),
            ("vwap_delta", "Globex VWAP change over the last complete bar (LAB_VWAP_SLOPE_V1, points)", _D),
            ("trend_context", "LAB_TREND_CONTEXT_V1 at the last complete bar (NEITHER: neither UP nor DOWN)", _R),
            ("current_episode_region", "current episode region (closes vs ±1σ)", _D),
            ("current_episode_closes", "current episode consecutive complete closes", _D),
            ("current_episode_lab_acceptance_time_v1", "LAB_ACCEPTANCE_TIME_V1 for the current episode", _R),
            ("higher_high", "last bar higher high", _D), ("higher_low", "last bar higher low", _D),
            ("lower_high", "last bar lower high", _D), ("lower_low", "last bar lower low", _D),
            ("consecutive_higher_highs_and_lows", "consecutive higher highs and higher lows (session)", _D),
            ("consecutive_lower_highs_and_lows", "consecutive lower highs and lower lows (session)", _D),
            ("recent_up_closes", "up closes of the last 6 complete bars", _D),
            ("recent_down_closes", "down closes of the last 6 complete bars", _D),
            ("session_bars_reaching_2sd", "complete bars reaching ±2σ this session", _D),
            ("volume_ratio_to_mean", "last bar volume / mean of the preceding bars (LAB_VOLUME_CONTEXT_V1)", _D))
SETUP_COLUMNS = (("family", _C), ("direction", _C), ("instance_exists", _C), ("instance_id", _C), ("state", _C),
                 ("stage", _R), ("can_still_complete", _R), ("first_event_ct", _C), ("completed_at_ct", _C))
CONDITION_COLUMNS = (("order", _R), ("policy_id", _R), ("status", _R), ("satisfied_at_ct", _R))
COMPLETED_COLUMNS = (("instance_id", _C), ("family", _C), ("direction", _C), ("state", _C), ("completed_at_ct", _C))


def _item(sha, pointer, label, value, category, domain, status=None) -> EvidenceItem:
    availability = Availability.AVAILABLE if value is not None else Availability.NOT_AVAILABLE
    return EvidenceItem(EvidenceRef(sha, pointer), domain, label, value, category, availability,
                        "COMPLETE" if pointer.startswith(("/latest_bar", "/recent_bars")) else None, status or "AVAILABLE")


_DOMAIN = {"start_ct": EvidenceDomain.PRICE_ACTION_BARS, "end_ct": EvidenceDomain.PRICE_ACTION_BARS,
           "open": EvidenceDomain.PRICE, "high": EvidenceDomain.PRICE, "low": EvidenceDomain.PRICE,
           "close": EvidenceDomain.PRICE, "vwap": EvidenceDomain.VWAP, "close_vs_vwap": EvidenceDomain.VWAP,
           "close_minus_vwap": EvidenceDomain.VWAP, "vwap_slope": EvidenceDomain.VWAP}
_STUDY = (("vwap_anchor", "VWAP anchor", _D, EvidenceDomain.VWAP),
          ("vwap_anchor_ct", "VWAP anchor time (CT, the Globex open)", _D, EvidenceDomain.VWAP),
          ("band_policy", "VWAP band policy", _D, EvidenceDomain.VWAP_BANDS),
          ("tick_size", "/ES tick size", _O, EvidenceDomain.PRICE),
          ("bar_interval", "bar interval", _D, EvidenceDomain.PRICE_ACTION_BARS))
_REPLAY = (("cutoff_ct", "replay cutoff (CT)"), ("completed_bars", "completed 5m bars in the session so far"),
           ("values_as_of_ct", "all bar values are as known at (CT)"),
           ("revised_bars_in_window", "bars in the window revised since they completed"))


def bar_rows(doc: dict) -> list[tuple[str, dict]]:
    """(pointer, row) for the window, oldest first; the latest bar last."""
    rows = [(f"/recent_bars/{i}", r) for i, r in enumerate(doc["recent_bars"])]
    return rows + ([("/latest_bar", doc["latest_bar"])] if doc["latest_bar"] is not None else [])


def _lesson_items(doc: dict, sha: str) -> list[EvidenceItem]:
    out = [_item(sha, f"/study/{k}", s, doc["study"][k], c, d) for k, s, c, d in _STUDY]
    out += [_item(sha, f"/replay/{k}", s, doc["replay"][k], _D, EvidenceDomain.PRICE_ACTION_BARS) for k, s in _REPLAY]
    for pointer, r in bar_rows(doc):
        name = "latest completed bar" if pointer == "/latest_bar" else f"bar {r['start_ct']}-{r['end_ct']} CT"
        out += [_item(sha, f"{pointer}/{k}", f"{name} {BAR_LABELS[k]}", r[k], c,
                      _DOMAIN.get(k, EvidenceDomain.VWAP_BANDS)) for k, c in BAR_COLUMNS]
    if doc["sequence"] is not None:
        out += [_item(sha, f"/sequence/{k}", v, doc["sequence"][k], _D, EvidenceDomain.PRICE_ACTION_BARS)
                for k, v in _SEQUENCE_LABELS.items()]
    return out


def _setup_items(doc: dict, sha: str) -> list[EvidenceItem]:
    E, status = EvidenceDomain.DRYSDALE_SETUPS, doc["analysis"]["quality_status"]

    def add(pointer, label, category):
        return _item(sha, pointer, label, resolve_pointer(doc, pointer), category, E, status)

    out = [add(f"/analysis/{k}", s, c) for k, s, c in _ANALYSIS]
    if doc["context"] is not None:
        out += [add(f"/context/{k}", s, c) for k, s, c in _CONTEXT]
    for i, r in enumerate(doc["setups"]):
        tag = f"{r['family']} {r['direction']}"
        out += [add(f"/setups/{i}/{k}", f"{tag} latest instance {k.replace('_', ' ')}", c) for k, c in SETUP_COLUMNS]
        for j, cond in enumerate(r["conditions"]):
            out += [add(f"/setups/{i}/conditions/{j}/{k}", f"{tag} {r['instance_id']} condition {cond['order']} "
                        f"{cond['policy_id']} {k.replace('_', ' ')}", c) for k, c in CONDITION_COLUMNS]
    for i, r in enumerate(doc["completed_today"]):
        out += [add(f"/completed_today/{i}/{k}", f"completed instance {r['instance_id']} {k.replace('_', ' ')}", c)
                for k, c in COMPLETED_COLUMNS]
    for f, fam in CATALOG["families"].items():
        base = f"/catalog/families/{f}"
        out += [add(f"{base}/title", f"{f} title", _R), add(f"{base}/candidate_policy", f"{f} candidate policy", _R)]
        for d, v in fam["directions"].items():
            for j in range(len(v["conditions"])):
                out += [add(f"{base}/directions/{d}/conditions/{j}/{k}", f"{f} {d} Laboratory V1 condition {j + 1} {k}",
                            _R) for k in ("policy_id", "rule")]
    return out


@dataclass(frozen=True)
class ChartLesson:
    lesson: TutorLesson
    document: dict  # LESSON_TIME
    sha256: str
    setup_document: dict  # DRYSDALE
    setup_sha256: str


def _sha(doc: dict) -> str:
    return hashlib.sha256(canonical_json(doc).encode("ascii")).hexdigest()


def chart_lesson(tl: ChartTimeline, index: int, lesson_id: str, setup: dict) -> ChartLesson:
    """A TutorLesson whose only authorized evidence is this replay position's two documents.

    The frozen LessonDefinition requires a QuestionKind; the adapter uses DRYSDALE_SETUPS (its required
    DRYSDALE_SETUPS domain is authorized). The placeholder answer key and the reference answer are never
    sent to a model and nothing is graded against them; the key's support is SUPPORTED so the frozen
    INSUFFICIENT_EVIDENCE_NOT_STATED guard adds no lesson-specific requirement. The module is the frozen
    Drysdale module, so the frozen Drysdale answer guards apply (prompt version TUTOR_SYSTEM_PROMPT_V3_DRYSDALE
    in tutor_ai.prompt_version: the module selects the guards; the POC sends its own system prompt).
    """
    doc = evidence_document(tl, index, setup)
    sdoc = setup_document(setup)
    sha, ssha = _sha(doc), _sha(sdoc)
    cutoff = tl.positions[index].cutoff_utc
    warnings = () if sdoc["analysis"]["quality_status"] == "AVAILABLE" else (
        QualityWarning(DRYSDALE_WARNING, "drysdale", sdoc["analysis"]["quality_status"], tuple(setup["reasons"]),
                       EvidenceRef(ssha, "/analysis/quality_status")),)
    definition = LessonDefinition(
        lesson_id, "Drysdale study at the replay position", "Study the chart and the Drysdale setups with grounded "
        "evidence", LessonMode.EXPLAIN_EVIDENCE, QuestionKind.DRYSDALE_SETUPS, "(tutor conversation)", tl.trading_date,
        cutoff, DOMAINS, DRYSDALE_MODULE.module_id, SOURCES)
    snaps = (SnapshotEvidence(ROLE, sha, cutoff, cutoff, AS_OF, tuple(_lesson_items(doc, sha)), ()),
             SnapshotEvidence(SETUP_ROLE, ssha, cutoff, cutoff, AS_OF, tuple(_setup_items(sdoc, ssha)), warnings))
    context = TutorEvidenceContext(CONTEXT_SCHEMA, lesson_id, tl.trading_date, UUID(tl.dataset_id), INSTRUMENT, AS_OF,
                                   cutoff, cutoff, sha, tuple(sorted(DOMAINS)), snaps, None, warnings, (), None, SOURCES)
    reference = TutorAnswer(ANSWER_SCHEMA, lesson_id, LessonStage.QUESTION, sha, "", (), (), (), ())
    key = AnswerKey(QuestionKind.DRYSDALE_SETUPS, EvidenceSupport.SUPPORTED, None, (), (),
                    GradingRubric((), (), (), (), False), reference)
    lesson = TutorLesson(LESSON_SCHEMA, definition, lesson_definition_sha256(definition), context, key, None,
                         ((sha, doc), (ssha, sdoc)))
    return ChartLesson(lesson, doc, sha, sdoc, ssha)


def _table(rows: list[tuple[str, dict]], columns) -> dict:
    return {"columns": ["pointer"] + [k for k, _ in columns], "categories": {k: c.value for k, c in columns},
            "rows": [[p] + [r[k] for k, _ in columns] for p, r in rows]}


def _flat(items) -> list[list]:
    return [[i.ref.pointer, i.value, i.category.value, i.label] for i in items]


def model_evidence(cl: ChartLesson) -> dict:
    """What the model receives each turn: compact, citable, no hashes, ids or paths.

    Scalar items are [pointer, value, category, label]. Tables give each row's pointer; a cell is cited as
    {"source", "pointer": "<row pointer>/<column>"} with the column's category. The setup catalog
    (/catalog/...) is invariant and is in the system prompt instead.
    """
    doc, sdoc = cl.document, cl.setup_document
    snap, ssnap = cl.lesson.context.snapshots
    plain = [i for i in snap.items if not i.ref.pointer.startswith(("/latest_bar", "/recent_bars"))]
    splain = [i for i in ssnap.items if i.ref.pointer.startswith(("/analysis", "/context"))]
    setups = [(f"/setups/{i}", r) for i, r in enumerate(sdoc["setups"])]
    return {
        "schema": MODEL_EVIDENCE_SCHEMA, "instrument": doc["instrument"], "trading_date": doc["trading_date"],
        "replay_cutoff_ct": doc["replay"]["cutoff_ct"],
        ROLE.value: {"items": _flat(plain), "bars": _table(bar_rows(doc), BAR_COLUMNS)},
        SETUP_ROLE.value: {
            "items": _flat(splain), "setups": _table(setups, SETUP_COLUMNS),
            "conditions": {"columns": ["pointer"] + [k for k, _ in CONDITION_COLUMNS],
                           "categories": {k: c.value for k, c in CONDITION_COLUMNS},
                           "rows": [[f"{p}/conditions/{j}"] + [c[k] for k, _ in CONDITION_COLUMNS]
                                    for p, r in setups for j, c in enumerate(r["conditions"])]},
            "completed_today": _table([(f"/completed_today/{i}", r) for i, r in enumerate(sdoc["completed_today"])],
                                      COMPLETED_COLUMNS),
            "catalog": f"{CATALOG_VERSION}: in the system prompt"},
        "quality_warnings": [w.warning_id for w in cl.lesson.context.quality_warnings],
        "curriculum_source_ids": list(cl.lesson.context.curriculum_source_ids)}
