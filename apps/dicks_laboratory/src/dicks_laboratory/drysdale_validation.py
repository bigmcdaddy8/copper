"""Drysdale prospective validation (0AB-D): DRYSDALE_PROSPECTIVE_VALIDATION_V1.

The machinery pre-registered in docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md. It reads frozen
DRYSDALE_V1 (drysdale.py) and DRYSDALE_CANDIDATE_QUALITY_V1 (drysdale_quality.py) and changes neither.

    IMPLEMENTATION VALIDITY  determinism, condition sequence, typed semantics re-checked on the bars, knowledge-time
                             integrity (first-known time, absent before / present at)
    STRUCTURAL VALIDITY      counts, strata, quality accounting, funnels, overlap, context facts, hypotheses,
                             challenge flags and the cohort classification
    TRADING EDGE             not here: no PnL, win rate, expectancy, entry, stop, target or sizing

Two layers:
    date_record(session, ...)   frozen analysis of one date -> a JSON-ready record (the only layer that reads data)
    cohort_summary(records,...) records -> registered outcomes, flags and classification (pure; tested on fixtures)

Campaign data access is guarded: a dataset whose trading date is on or after COHORT_START (or unknown) is refused
unless the 0AB-D freeze manifest exists, every file it lists verifies, and the caller names the frozen plan sha256.
Context facts are CONTEXT FACTS: no new threshold; nothing here is a candidate requirement.
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from zoneinfo import ZoneInfo

from dicks_laboratory import drysdale as dry
from dicks_laboratory import drysdale_quality as dq
from dicks_laboratory import market_study_state as mss
from dicks_laboratory.analysis import open_dataset_store, resolve_dataset_id
from dicks_laboratory.price_action import Direction, Side
from dicks_laboratory.replay import ReplayCutoff, as_of_evidence
from dicks_laboratory.sessions import AnchorKind, resolve_anchor

SCHEMA = "DRYSDALE_PROSPECTIVE_VALIDATION_V1"
PLAN = "docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md"
PREREGISTRATION = "docs/dicks_laboratory/DRYSDALE_PROSPECTIVE_REPORTING_PREREGISTRATION.md"
FREEZE_MANIFEST = "docs/dicks_laboratory/evidence/0AB-D/FREEZE.md"
FREEZE_ADDENDUM_GLOB = "FREEZE_ADDENDUM_*.md"  # beside FREEZE_MANIFEST; applied in numeric order
COHORT_START, COHORT_END = date(2026, 10, 12), date(2026, 11, 6)
COHORT_DATES = tuple(date(2026, m, d) for m, ds in ((10, (12, 13, 14, 15, 16, 19, 20, 21, 22, 23, 26, 27, 28, 29,
                                                          30)), (11, (2, 3, 4, 5, 6))) for d in ds)
CONTRACT = ("ES", 2026, 12)  # /ESZ6, the campaign pin

# Laboratory validation thresholds (registered by the PO in 0AB-D; not Drysdale concepts)
DENSITY_MEDIAN_MAX = 20  # median eligible candidates per eligible date > 20: CANDIDATE_DENSITY_CHALLENGED
SCARCITY_ZERO_SHARE = Fraction(1, 2)  # > 50% of eligible dates with zero eligible candidates
DOMINANCE_SHARE = Fraction(4, 5)  # one family > 80% of eligible candidates: FAMILY_DOMINANCE_FOR_REVIEW
MIN_ELIGIBLE_DATES = 10
MIN_ELIGIBLE_CANDIDATES = 20
MIN_FAMILY_CANDIDATES = 5
HUMAN_SAMPLE_PER_FAMILY = 2
LINEAR_PROBES = 8  # first-known search: change points scanned forward before bisection

CT = ZoneInfo("America/Chicago")
_US = timedelta(microseconds=1)
FAMILIES = tuple(dry.SetupFamily)
SHORT = {f: dry._SHORT[f] for f in FAMILIES}
N_CONDITIONS = {dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION: 4, dry.SetupFamily.FADE_VALUE_AREA_EXTREME: 4,
                dry.SetupFamily.RETURN_TO_VALUE: 3, dry.SetupFamily.VWAP_BOUNCE: 5}
QUAL = (dry.CandidateState.CANDIDATE, dry.CandidateState.QUALITY_QUALIFIED)
ELIGIBLE = (dq.Eligibility.ELIGIBLE_UNQUALIFIED.value, dq.Eligibility.ELIGIBLE_QUALITY_QUALIFIED.value)


class Stratum(StrEnum):
    """By candidate reference time (end of the completing 5-minute bar), registered in the 0AB-C pre-registration."""

    # Assigned by the completing bar's interval (plan §5, FREEZE_ADDENDUM_1); reference = bar end.
    FIRST_GLOBEX_HOUR = "FIRST_GLOBEX_HOUR"  # bars 17:00-17:05 .. 17:55-18:00 CT (bar end <= anchor + 1 h)
    LATER_OVERNIGHT = "LATER_OVERNIGHT"  # bars 18:00-18:05 .. 08:25-08:30 CT (bar end <= 08:30)
    US_CASH_SESSION = "US_CASH_SESSION"  # bars 08:30-08:35 .. 14:55-15:00 CT (US_CASH_SESSION_V1 study window)
    POST_CASH = "POST_CASH"  # bars 15:00-15:05 .. 15:55-16:00 CT


OVERNIGHT = (Stratum.FIRST_GLOBEX_HOUR, Stratum.LATER_OVERNIGHT)


class DateStatus(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    NOT_CAPTURED = "NOT_CAPTURED"
    NOT_FINALIZED = "NOT_FINALIZED"
    ANALYSIS_NOT_AVAILABLE = "ANALYSIS_NOT_AVAILABLE"
    CONTRACT_MISMATCH = "CONTRACT_MISMATCH"
    NOT_A_COHORT_DATE = "NOT_A_COHORT_DATE"
    HARNESS_ERROR = "HARNESS_ERROR"  # the dataset exists but could not be evaluated: BLOCKED, never dropped


class Classification(StrEnum):
    PASS = "PASS — STRUCTURALLY COHERENT"
    PASS_WITH_CHALLENGES = "PASS WITH CHALLENGES"
    INCONCLUSIVE = "INCONCLUSIVE"
    BLOCKED = "BLOCKED — IMPLEMENTATION / DATA QUALITY"
    FAIL = "FAIL — STRUCTURAL BREAKDOWN"


class Flag(StrEnum):
    CANDIDATE_DENSITY_CHALLENGED = "CANDIDATE_DENSITY_CHALLENGED"
    CANDIDATE_SCARCITY_CHALLENGED = "CANDIDATE_SCARCITY_CHALLENGED"
    FAMILY_DOMINANCE_FOR_REVIEW = "FAMILY_DOMINANCE_FOR_REVIEW"


class Attribution(StrEnum):
    """Recorded by the Human investigation of a sequence / semantic violation (never inferred)."""

    FROZEN_RULE = "FROZEN_RULE"  # frozen V1 itself produced it
    HARNESS = "HARNESS"
    DATA = "DATA"


# --- campaign data access guard ------------------------------------------------------------------------------

class CampaignAccessDenied(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def guarded(trading_date: date | None, capture_started_at: datetime | None = None) -> bool:
    """Unseen campaign data: a trading date on or after COHORT_START, an unknown date, or a capture that began at or
    after the first cohort session's Globex anchor."""
    if trading_date is None or trading_date >= COHORT_START:
        return True
    first = resolve_anchor(AnchorKind.SESSION_OPEN, COHORT_START).anchor_timestamp_utc
    return capture_started_at is not None and capture_started_at >= first


def dataset_identity(database: Path) -> tuple[date | None, datetime | None]:
    """Recorded trading date and capture start: metadata only (no trade is read)."""
    store = open_dataset_store(database)
    try:
        did = resolve_dataset_id(store, None)
        td, _ = store.load_dataset_trading_context(did)
        return td, store.load_dataset(did).capture_started_at
    finally:
        store.close()


_MANIFEST_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$")
_ADDENDUM_LINE = re.compile(r"^([0-9a-f]{64}) -> ([0-9a-f]{64})  (\S+)$")


def _addenda(repo: Path) -> list[Path]:
    def n(p: Path) -> int:
        tail = p.stem.rsplit("_", 1)[-1]
        return int(tail) if tail.isdigit() else -1
    return sorted((repo / FREEZE_MANIFEST).parent.glob(FREEZE_ADDENDUM_GLOB), key=lambda p: (n(p), p.name))


def _frozen_set(repo: Path) -> tuple[dict[str, str], list[str]]:
    """FREEZE.md entries with recorded addenda applied in order; each replacement must name the sha256 in force."""
    path = repo / FREEZE_MANIFEST
    if not path.is_file():
        return {}, []
    entries = {m.group(2): m.group(1) for m in map(_MANIFEST_LINE.match, path.read_text().splitlines()) if m}
    problems = []
    for add in _addenda(repo):
        if not add.stem.rsplit("_", 1)[-1].isdigit():
            problems.append(f"unnumbered freeze addendum: {add.name}")
            continue
        for m in filter(None, map(_ADDENDUM_LINE.match, add.read_text().splitlines())):
            old, new, rel = m.groups()
            if entries.get(rel) != old:
                problems.append(f"{add.name}: {rel} old sha256 is not the one in force")
            else:
                entries[rel] = new
    return entries, problems


def manifest_entries(repo: Path) -> dict[str, str]:
    return _frozen_set(repo)[0]


def freeze_problems(repo: Path, frozen_plan_sha256: str | None) -> list[str]:
    """Why campaign access is refused ([] = allowed)."""
    entries, out = _frozen_set(repo)
    if not entries:
        return [f"no 0AB-D freeze manifest at {FREEZE_MANIFEST}"]
    for rel in (PLAN, PREREGISTRATION):
        if rel not in entries:
            out.append(f"manifest does not list {rel}")
    if not frozen_plan_sha256:
        out.append("campaign data need --frozen-plan <sha256 of the frozen validation plan>")
    elif entries.get(PLAN) != frozen_plan_sha256:
        out.append("--frozen-plan does not match the plan sha256 in force (freeze manifest and addenda)")
    for rel, sha in sorted(entries.items()):
        f = repo / rel
        if not f.is_file():
            out.append(f"frozen file missing: {rel}")
        elif _sha256(f) != sha:
            out.append(f"frozen file changed: {rel}")
    return out


def require_access(repo: Path, database: Path, frozen_plan_sha256: str | None) -> bool:
    """Raises CampaignAccessDenied for unseen campaign data without a verified freeze. Returns whether guarded."""
    td, started = dataset_identity(database)
    if not guarded(td, started):
        return False
    problems = freeze_problems(repo, frozen_plan_sha256)
    if problems:
        raise CampaignAccessDenied(f"trading date {td} is unseen campaign data; refused: " + "; ".join(problems))
    return True


# --- strata and small helpers --------------------------------------------------------------------------------

def _iso(ts: datetime | None) -> str | None:
    return None if ts is None else mss.encode(ts)


def _ct(trading_date: date, hh: int, mm: int) -> datetime:
    return datetime.combine(trading_date, time(hh, mm), tzinfo=CT).astimezone(timezone.utc)


def anchor_of(trading_date: date) -> datetime:
    return resolve_anchor(AnchorKind.SESSION_OPEN, trading_date).anchor_timestamp_utc


def stratum(reference_utc: datetime, trading_date: date) -> Stratum:
    if reference_utc <= anchor_of(trading_date) + timedelta(hours=1):
        return Stratum.FIRST_GLOBEX_HOUR
    if reference_utc <= _ct(trading_date, 8, 30):
        return Stratum.LATER_OVERNIGHT
    if reference_utc <= _ct(trading_date, 15, 0):
        return Stratum.US_CASH_SESSION
    if reference_utc <= _ct(trading_date, 16, 0):
        return Stratum.POST_CASH
    raise ValueError(f"reference time {reference_utc} is after the Globex window")


def _s(x) -> str | None:
    return None if x is None else str(x)


def _ratio_word(r: Decimal | None) -> str:
    return "NOT_AVAILABLE" if r is None else "HIGHER" if r > 1 else "EQUAL" if r == 1 else "LOWER"


def _slope_word(slope: dry.Slope | None, direction: Direction) -> str:
    if slope is None:
        return "NOT_AVAILABLE"
    if slope is dry.Slope.FLAT:
        return "FLAT"
    return "ALIGNED" if slope is (dry.Slope.RISING if direction is Direction.UP else dry.Slope.FALLING) else "OPPOSED"


# --- implementation validity: sequence and typed semantics ------------------------------------------------------

def condition_bars(c: dry.DrysdaleSetupCandidate) -> list[int | None]:
    return [k.bar_index for k in sorted(c.conditions, key=lambda k: k.order)]


def structural_key(c: dry.DrysdaleSetupCandidate) -> str:
    return "|".join([c.candidate_id, c.family.value, c.direction.value, _iso(c.first_event_utc),
                     _iso(c.completed_at_utc) or "-"] +
                    [f"{k.order}:{k.status.value}:{k.bar_index}" for k in sorted(c.conditions, key=lambda k: k.order)])


_ORDER = {  # required order of the condition bars (index of the condition in `order`, 0-based)
    dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION: lambda b: [
        ("TRIGGER_BEFORE_ACCEPTANCE", b[1] == b[0] + 1), ("RETEST_AFTER_ACCEPTANCE", b[2] >= b[0] + 2),
        ("CONFIRMATION_AFTER_RETEST", b[3] == b[2] + 1)],
    dry.SetupFamily.FADE_VALUE_AREA_EXTREME: lambda b: [
        ("TEST_AFTER_ACCEPTANCE", b[1] >= b[0] + 1), ("REJECTION_AT_TEST_BAR", b[2] == b[1]),
        ("CONFIRMATION_AFTER_REJECTION", b[3] == b[2] + 1)],
    dry.SetupFamily.RETURN_TO_VALUE: lambda b: [
        ("RETURN_AFTER_OUTSIDE_ACCEPTANCE", b[1] > b[0]), ("INSIDE_ACCEPTANCE_AFTER_RETURN", b[2] == b[1] + 1)],
    dry.SetupFamily.VWAP_BOUNCE: lambda b: [
        ("RETURN_AFTER_OUTSIDE", b[1] > b[0]), ("RETURN_AT_OR_BEFORE_TEST", b[1] <= b[3]),
        ("TREND_AT_BAR_BEFORE_TEST", b[2] == b[3] - 1), ("TEST_AFTER_OUTSIDE", b[3] > b[0]),
        ("CONFIRMATION_AFTER_TEST", b[4] == b[3] + 1)],
}


def sequence_violations(c: dry.DrysdaleSetupCandidate, bars) -> list[str]:
    """Required order and monotonic timestamps of a completed candidate's conditions (0 expected; any is an
    IMPLEMENTATION DEFECT, not a market finding)."""
    conds = sorted(c.conditions, key=lambda k: k.order)
    out = []
    for k in conds:
        if k.status is not dry.ConditionStatus.SATISFIED or k.bar_index is None or k.satisfied_at_utc is None:
            out.append(f"CONDITION_{k.order}_NOT_SATISFIED_ON_A_COMPLETED_CANDIDATE")
        elif not 0 <= k.bar_index < len(bars) or bars[k.bar_index].end_utc != k.satisfied_at_utc:
            out.append(f"CONDITION_{k.order}_TIMESTAMP_NOT_ITS_BAR_END")
    if out:
        return out
    b = condition_bars(c)
    out += [name for name, ok in _ORDER[c.family](b) if not ok]
    ts = [k.satisfied_at_utc for k in conds]
    if c.completed_at_utc != max(ts):
        out.append("COMPLETED_AT_NOT_THE_LAST_CONDITION")
    if c.first_event_utc > c.completed_at_utc:
        out.append("FIRST_EVENT_AFTER_COMPLETION")
    if c.state not in QUAL:
        out.append("COMPLETED_STATE_NOT_A_CANDIDATE")
    return out


def _confirmed(bars, j: int, direction: Direction) -> bool:
    b, p = bars[j], bars[j - 1]
    return (b.close > b.open and b.close > p.high) if direction is Direction.UP else (b.close < b.open and
                                                                                       b.close < p.low)


def _touched(bar, level: dry.Level, from_side: Side) -> bool:
    t = dry._lv(bar, level)
    return t.traded_at or (t.traded_below if from_side is Side.ABOVE else t.traded_above)


def semantic_violations(c: dry.DrysdaleSetupCandidate, bars) -> list[str]:
    """Typed semantics re-checked independently on the complete bars (H-FADE-1/2, H-RTV-1/2, H-BOUNCE-1/2, and the
    PDC / confirmation structure). 0 expected; any is an IMPLEMENTATION DEFECT."""
    if sequence_violations(c, bars):
        return []  # reported as a sequence defect; the bars are not interpretable
    b, d, out = condition_bars(c), c.direction, []
    inside = dry.ValuePosition.INSIDE_VALUE
    if c.family is dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION:
        outside = dry._outside(d)
        if b[0] > 0 and bars[b[0] - 1].value_position is outside:
            out.append("PDC_TRIGGER_NOT_THE_EPISODE_START")
        if any(bars[j].value_position is not outside for j in range(b[0], b[2] + 1)):
            out.append("PDC_CLOSE_NOT_OUTSIDE_BEFORE_CONFIRMATION")
        if not _touched(bars[b[2]], dry._boundary(d), Side.ABOVE if d is Direction.UP else Side.BELOW):
            out.append("PDC_RETEST_DID_NOT_TOUCH_THE_BOUNDARY")
        if not _confirmed(bars, b[3], d):
            out.append("PDC_CONFIRMATION_NOT_DIRECTIONAL")
    elif c.family is dry.SetupFamily.FADE_VALUE_AREA_EXTREME:
        level = dry.Level.UPPER_1SD if d is Direction.DOWN else dry.Level.LOWER_1SD
        origin = Side.BELOW if level is dry.Level.UPPER_1SD else Side.ABOVE
        if any(bars[j].value_position is not inside for j in range(b[0] - 1, b[1])):  # H-FADE-1
            out.append("FADE_NO_PRIOR_INSIDE_ACCEPTANCE")
        if not _touched(bars[b[1]], level, origin):
            out.append("FADE_TEST_DID_NOT_TOUCH_THE_BOUNDARY")
        if dry._lv(bars[b[2]], level).close_side is not origin:  # H-FADE-2
            out.append("FADE_NO_REJECTION_CLOSE")
        if not _confirmed(bars, b[3], d):
            out.append("FADE_CONFIRMATION_NOT_TOWARD_THE_INTERIOR")
    elif c.family is dry.SetupFamily.RETURN_TO_VALUE:
        outside = dry._outside(dry._opposite(d))
        if any(bars[j].value_position is not outside for j in range(b[0] - 1, b[1])):  # H-RTV-1
            out.append("RTV_NO_PRIOR_ACCEPTED_OUTSIDE_STATE")
        if bars[b[1]].value_position is not inside or bars[b[2]].value_position is not inside:
            out.append("RTV_NOT_ACCEPTED_INSIDE")
        if any(k.policy_id == dry.RETEST_POLICY for k in c.conditions):  # H-RTV-2
            out.append("RTV_REQUIRES_A_RETEST")
    else:
        side = Side.ABOVE if d is Direction.UP else Side.BELOW
        slope = dry.Slope.RISING if d is Direction.UP else dry.Slope.FALLING
        if bars[b[0]].value_position is not dry._outside(d):
            out.append("BOUNCE_NO_PRIOR_OUTSIDE_CLOSE")
        if bars[b[1]].value_position is not inside:
            out.append("BOUNCE_NO_RETURN_INSIDE")
        p = bars[b[2]]
        if p.vwap_slope is not slope or dry._lv(p, dry.Level.GLOBEX_VWAP).close_side is not side:
            out.append("BOUNCE_TREND_CONTEXT_NOT_MET")
        if not _touched(bars[b[3]], dry.Level.GLOBEX_VWAP, side):  # H-BOUNCE-1
            out.append("BOUNCE_NO_VWAP_TEST")
        if not _confirmed(bars, b[4], d):  # H-BOUNCE-2
            out.append("BOUNCE_CONFIRMATION_NOT_AWAY_FROM_VWAP")
    return out


# --- context facts and family hypotheses (descriptive; no new threshold) ---------------------------------------

def _statics_interaction(statics, bars, j0: int, j1: int) -> dict[str, str]:
    out = {}
    for name, _, level, known_from in statics:
        if level is None:
            out[name] = "NOT_AVAILABLE"
            continue
        js = [j for j in range(j0, j1 + 1) if known_from is None or bars[j].end_utc >= known_from]
        if not js:
            out[name] = "NOT_YET_AVAILABLE"
        else:
            out[name] = "TRADED_THROUGH" if any(bars[j].low <= level <= bars[j].high for j in js) else "NOT_TRADED"
    return out


def _reach_2sd(bars, j0: int, j1: int, direction: Direction | None) -> list[str]:
    sides = ((dry.Level.UPPER_2SD, Side.BELOW, "UPPER_2SD"), (dry.Level.LOWER_2SD, Side.ABOVE, "LOWER_2SD"))
    return [name for lv, frm, name in sides
            if (direction is None or (lv is dry.Level.UPPER_2SD) == (direction is Direction.UP))
            and any(_touched(bars[j], lv, frm) for j in range(j0, j1 + 1))]


def _run_end(bars, s: int, pos) -> int:
    e = s
    while e + 1 < len(bars) and bars[e + 1].value_position is pos:
        e += 1
    return e


def context_facts(c: dry.DrysdaleSetupCandidate, bars, statics) -> dict:
    """§12 context facts over the candidate's own bars [first condition bar, completing bar] (as of final knowledge,
    which cannot change complete bars before the completion except by late prints already resolved)."""
    b = condition_bars(c)
    j0, j1 = min(b), max(b)
    last = bars[j1]
    vol = dry._volume(bars, j1)
    bound = {Direction.UP: dry.Level.UPPER_1SD, Direction.DOWN: dry.Level.LOWER_1SD}
    lt = dry._lv(last, bound[c.direction])
    beyond = (last.close - lt.level_at_close) if c.direction is Direction.UP else (lt.level_at_close - last.close)
    position = dq_div(last.close - last.vwap, last.sigma)
    excursion = seconds_out = closes_out = None
    if c.family is dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION:
        ts = [dry._lv(bars[j], bound[c.direction]) for j in range(b[0], j1 + 1)]
        excursion = max(t.max_above_points if c.direction is Direction.UP else t.max_below_points for t in ts)
        seconds_out = sum((t.seconds_above if c.direction is Direction.UP else t.seconds_below for t in ts), timedelta())
        closes_out = sum(bars[j].value_position is dry._outside(c.direction) for j in range(b[0], j1 + 1))
    elif c.family is dry.SetupFamily.RETURN_TO_VALUE:
        a = c.acceptance[0]
        excursion, seconds_out, closes_out = a.max_distance_beyond_points, a.seconds_beyond, a.completed_closes
    elif c.family is dry.SetupFamily.FADE_VALUE_AREA_EXTREME:
        ev = next(e for e in c.events if e.bar_index == b[1])
        excursion = ev.excursion_points
    else:
        ev = next(e for e in c.events if e.bar_index == b[3])
        excursion = ev.excursion_points
        a = b[0]
        s = a
        while s > 0 and bars[s - 1].value_position is dry._outside(c.direction):
            s -= 1
        closes_out = a - s + 1
    inter = _statics_interaction(statics, bars, j0, j1)
    return {
        "time_of_day_ct": c.completed_at_utc.astimezone(CT).strftime("%H:%M"),
        "vwap_slope_at_first_condition_bar": _s(bars[j0].vwap_slope),
        "vwap_slope_at_completing_bar": _s(last.vwap_slope),
        "completing_close_distance_beyond_1sd_points": _s(beyond),
        "completing_close_position_sigma": _s(position),
        "reached_2sd_during_candidate_bars": _reach_2sd(bars, j0, j1, None),
        "max_excursion_points": _s(excursion),
        "seconds_outside_value": None if seconds_out is None else str(seconds_out.total_seconds()),
        "completed_closes_outside_value": closes_out,
        "breakout_bar_volume": _s(c.breakout.volume.bar_volume) if c.breakout else None,
        "completing_bar_volume": _s(vol.bar_volume),
        "completing_bar_volume_ratio_to_baseline_mean": _s(vol.ratio_to_mean),
        "completing_bar_volume_ratio_to_baseline_median": _s(vol.ratio_to_median),
        "volume_baseline_bars": vol.baseline_bars,
        "ib_interaction": {k: inter[k] for k in ("IB_HIGH", "IB_LOW")},
        "prior_day_interaction": {k: inter[k] for k in ("PRIOR_HIGH", "PRIOR_LOW")},
        "overnight_interaction": {k: inter[k] for k in ("OVERNIGHT_HIGH", "OVERNIGHT_LOW")},
        "returned_into_value_by_session_end": (c.breakout.returned_inside if c.breakout else None),
    }


def dq_div(a: Decimal | None, b: Decimal | None) -> Decimal | None:
    return dry._div(a, b)


def pdc_facts(c: dry.DrysdaleSetupCandidate, bars) -> dict:
    """§13-§16 descriptive measures for a PRICE_DISCOVERY_CONTINUATION candidate."""
    b = condition_bars(c)
    s, done, d = b[0], b[3], c.direction
    outside = dry._outside(d)
    e = max(_run_end(bars, s, outside), done)
    outer, frm = (dry.Level.UPPER_2SD, Side.BELOW) if d is Direction.UP else (dry.Level.LOWER_2SD, Side.ABOVE)
    first = next((j for j in range(s, e + 1) if _touched(bars[j], outer, frm)), None)
    reach = ("NEVER_DURING_SEQUENCE" if first is None else "REACHED_AT_BREAKOUT_BAR" if first == s else
             "REACHED_AFTER_BREAKOUT_BEFORE_COMPLETION" if first <= done else "REACHED_AFTER_COMPLETION")
    approach = max((dry._lv(bars[j], outer).max_above_points if d is Direction.UP else
                    dry._lv(bars[j], outer).max_below_points) for j in range(s, done + 1))
    br = c.breakout
    refs = [r.reference for r in br.references if r.availability == "AVAILABLE" and r.traded_through_in_bar
            and r.close_side is (Side.ABOVE if d is Direction.UP else Side.BELOW)]
    slope = _slope_word(br.vwap_slope, d)
    volume = _ratio_word(br.volume.ratio_to_median)
    two = reach in ("REACHED_AT_BREAKOUT_BAR", "REACHED_AFTER_BREAKOUT_BEFORE_COMPLETION")
    reference_break = bool(refs) or bool(br.new_session_extreme)
    return {
        "outside_closes_trigger_to_completion": sum(bars[j].value_position is outside for j in range(s, done + 1)),
        "seconds_beyond_trigger_to_completion": str(sum(
            (dry._lv(bars[j], dry._boundary(d)).seconds_above if d is Direction.UP else
             dry._lv(bars[j], dry._boundary(d)).seconds_below for j in range(s, done + 1)), timedelta()).total_seconds()),
        "trigger_distance_beyond_sigma": _s(br.distance_beyond_sigma),
        "reach_2sd": reach,
        "max_beyond_2sd_points_by_completion": _s(approach),
        "max_beyond_2sd_sigma_by_completion": _s(dq_div(approach, bars[done].sigma)),
        "breakout_volume_ratio_to_median": _s(br.volume.ratio_to_median),
        "breakout_volume_ratio_to_mean": _s(br.volume.ratio_to_mean),
        "breakout_volume_vs_baseline_median": volume,
        "breakout_volume_vs_baseline_mean": _ratio_word(br.volume.ratio_to_mean),
        "vwap_slope_at_trigger": slope,
        "vwap_slope_at_completion": _slope_word(bars[done].vwap_slope, d),
        "references_broken_at_trigger": refs,
        "new_session_extreme_at_trigger": br.new_session_extreme,
        "supporting_context": {"SLOPE_ALIGNED": slope == "ALIGNED", "REACHED_2SD_BY_COMPLETION": two,
                               "VOLUME_ABOVE_BASELINE_MEDIAN": volume == "HIGHER",
                               "REFERENCE_BREAK": reference_break},
    }


def family_facts(c: dry.DrysdaleSetupCandidate, bars) -> dict:
    if c.family is dry.SetupFamily.PRICE_DISCOVERY_CONTINUATION:
        return pdc_facts(c, bars)
    if c.family is dry.SetupFamily.RETURN_TO_VALUE:
        sup = dict(c.supporting)
        return {"later_retest_present_by_session_end": bool(sup.get("RETURN_TO_VALUE_RETEST_PRESENT")),
                "retest_required": sup.get("retest_required")}
    if c.family is dry.SetupFamily.VWAP_BOUNCE:
        b = condition_bars(c)
        return {"vwap_slope_at_trend_bar": _s(bars[b[2]].vwap_slope),
                "vwap_slope_at_test_bar": _slope_word(bars[b[3]].vwap_slope, c.direction),
                "vwap_slope_at_confirmation_bar": _slope_word(bars[b[4]].vwap_slope, c.direction),
                "bars_from_outside_close_to_test": b[3] - b[0]}
    b = condition_bars(c)
    return {"bars_from_inside_acceptance_to_test": b[1] - b[0]}


# --- funnel -----------------------------------------------------------------------------------------------

def funnel(a: dry.DrysdaleSetupAnalysis) -> dict:
    """Per family: every instance at final knowledge (any state) and how far its conditions progressed."""
    out = {}
    for f in FAMILIES:
        inst = [c for c in a.candidates if c.family is f]
        n = N_CONDITIONS[f]
        reached, satisfied, stops = [0] * (n + 1), [0] * n, Counter()
        for c in inst:
            st = [k.status for k in sorted(c.conditions, key=lambda k: k.order)]
            p = 0
            while p < len(st) and st[p] is dry.ConditionStatus.SATISFIED:
                p += 1
            for k in range(p + 1):
                reached[k] += 1
            for k, x in enumerate(st):
                satisfied[k] += x is dry.ConditionStatus.SATISFIED
            if p < len(st):
                k = sorted(c.conditions, key=lambda k: k.order)[p]
                stops[f"{k.order}:{k.policy_id}:{k.status.value}"] += 1
        out[f.value] = {"instances": len(inst), "conditions": n,
                        "policies": [k.policy_id for k in sorted(inst[0].conditions, key=lambda k: k.order)]
                        if inst else [],
                        "reached_at_least": reached[1:], "satisfied_by_condition": satisfied,
                        "first_unsatisfied": dict(sorted(stops.items()))}
    return out


# --- quality tags -----------------------------------------------------------------------------------------

def quality_tags(cq: dq.CandidateQuality) -> list[str]:
    tags = set()
    for r in cq.reasons:
        if r.code is dq.ReasonCode.CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR and r.materiality in (
                dq.Materiality.PROVENANCE, dq.Materiality.LOCAL_EVIDENCE):
            tags.add(f"BOUNDARY_{r.materiality.value}")
        if r.code in (dq.ReasonCode.KNOWN_GAP, dq.ReasonCode.SUSPECTED_GAP) and \
                r.materiality is dq.Materiality.UPSTREAM_REFERENCE:
            tags.add("UPSTREAM_REFERENCE")
    return sorted(tags)


def reason_combination(cq: dq.CandidateQuality) -> str:
    """The exact set of dependency reasons (code/materiality), NOT_A_DEPENDENCY excluded; '' when none."""
    return "+".join(sorted({f"{r.code.value}/{r.materiality.value}" for r in cq.reasons
                            if r.materiality is not dq.Materiality.NOT_A_DEPENDENCY}))


# --- knowledge-time integrity -------------------------------------------------------------------------------

def final_knowledge_cutoff(prep) -> ReplayCutoff:
    """Market 16:00 CT; knowledge at max(16:30 CT, the latest recorded receipt / observation + 1 us)."""
    m = _ct(prep.trading_date, 16, 0)
    times = [p.received_at for p in prep.provenance if p.received_at is not None]
    times += [d.source_record.received_at for d in prep.deferred if d.source_record.received_at is not None]
    times += [e.observed_at for e in prep.quality_events if e.observed_at is not None]
    times += [e.interval_end for e in prep.quality_events if e.interval_end is not None]
    return ReplayCutoff(m, max([_ct(prep.trading_date, 16, 30)] + [t + _US for t in times]))


class _Receipts:
    """(received_at, market time) of every record, built once per date."""

    def __init__(self, prep) -> None:
        by_id = {t.observation_id: t.event_timestamp for t in prep.canonical_trades}
        self.trades = sorted((p.received_at, by_id[p.observation_id]) for p in prep.provenance
                             if p.received_at is not None and p.observation_id in by_id)
        self.deferred = sorted(d.source_record.received_at for d in prep.deferred
                               if d.source_record.received_at is not None)

    def change_points(self, completed: datetime, final: ReplayCutoff) -> list[datetime]:
        """Instants at which frozen V1's view of market times before `completed` can change after `completed`:
        `completed` itself, then 1 us after each later receipt of a record with an earlier market time (a record
        received at r is known to cutoffs after r), and of every later correction / cancel record."""
        k = final.knowledge_time_cutoff_utc
        rs = {r for r, m in self.trades if completed <= r < k and m < completed}
        rs |= {r for r in self.deferred if completed <= r < k}
        return [completed] + sorted(r + _US for r in rs)


def first_known(session, finals: list[dry.DrysdaleSetupCandidate], final: ReplayCutoff) -> dict[str, dict]:
    """Earliest ordinary replay instant (market = knowledge) at which each final candidate is present with its final
    structure (same id, a completed state, the same condition bars).

    Probes per candidate: 1 us before completion (must be absent: the completing bar is not complete), then the
    change points in time order (forward, globally ascending so the resumable pass is reused) up to LINEAR_PROBES,
    then bisection over the rest. Proof: absent at the preceding probe, present at the first-known probe."""
    prep = session.replay.current
    keys = {c.candidate_id: structural_key(c) for c in finals}
    receipts = _Receipts(prep)
    cache: dict[datetime, frozenset[str]] = {}

    def probe(t: datetime) -> frozenset[str]:
        if t not in cache:
            a = dry.analyze(session, cutoff=ReplayCutoff.at(t))
            cache[t] = frozenset(c.candidate_id for c in a.candidates
                                 if c.state in QUAL and keys.get(c.candidate_id) == structural_key(c))
        return cache[t]

    plans = {c.candidate_id: [c.completed_at_utc - _US] + receipts.change_points(c.completed_at_utc, final)
             for c in finals}
    found: dict[str, int | None] = {}
    bisect: dict[str, int] = {}
    heap = sorted((pts[0], cid, 0) for cid, pts in plans.items())
    while heap:
        t = heap[0][0]
        here = [x for x in heap if x[0] == t]
        heap = [x for x in heap if x[0] != t]
        seen = probe(t)
        for _, cid, i in here:
            pts = plans[cid]
            if cid in seen:
                found[cid] = i
            elif i + 1 >= len(pts):
                found[cid] = None
            elif i + 1 > LINEAR_PROBES:
                bisect[cid] = i + 1
            else:
                heap.append((pts[i + 1], cid, i + 1))
        heap.sort()
    for cid, lo in bisect.items():
        pts = plans[cid]
        hi = len(pts) - 1
        if cid not in probe(pts[hi]):
            found[cid] = None
            continue
        while lo < hi:
            mid = (lo + hi) // 2
            if cid in probe(pts[mid]):
                hi = mid
            else:
                lo = mid + 1
        found[cid] = lo
    result = {}
    for c in finals:
        cid, pts, i = c.candidate_id, plans[c.candidate_id], found.get(c.candidate_id)
        base = {"change_points": len(pts) - 1, "probes": len(cache)}
        if i is None:
            result[cid] = {**base, "first_known_utc": None, "receipt_delay_seconds": None, "absent_before": None,
                           "absent_probe_utc": None, "present_at": False, "resolved": False}
            continue
        before = pts[i - 1] if i > 0 else None
        result[cid] = {**base, "first_known_utc": _iso(pts[i]),
                       "receipt_delay_seconds": str(Decimal((pts[i] - c.completed_at_utc) // _US) / 10 ** 6),
                       "absent_before": None if before is None else cid not in probe(before),
                       "absent_probe_utc": _iso(before), "present_at": True, "resolved": True}
    return result


def _sweep(session, td: date) -> list[tuple[str, ReplayCutoff]]:
    hours = [18, 19, 20, 21, 22, 23, 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
    return [(f"{h:02d}:00", ReplayCutoff.at(session.resolve_time(f"{h:02d}:00"))) for h in hours]


# --- one date -------------------------------------------------------------------------------------------------

def date_record(session, *, first_known_search: bool = True, sweep: bool = True) -> dict:
    """The registered per-date record from frozen DRYSDALE_V1 at final knowledge (DRYSDALE_PROSPECTIVE_VALIDATION_V1).
    Factual only: no narrative."""
    prep = session.replay.current
    td = prep.trading_date
    fk = final_knowledge_cutoff(prep)
    snap = session.snapshot(cutoff=fk)
    a = dry.analyze(session, cutoff=fk)
    x = dq.audit(a, snap)
    # determinism: a second, cold run (fresh snapshot and as-of tape, no checkpoint) on identical inputs
    snap2 = session.replay.snapshot(cutoff=fk)  # MarketReplay: not the session snapshot cache
    a2 = dry.build_drysdale_analysis(prep, snap2, as_of_evidence(prep, fk).scoped)
    x2 = dq.audit(a2, snap2)
    det = {"drysdale_sha256": [dry.drysdale_sha256(a), dry.drysdale_sha256(a2)],
           "quality_sha256": [dq.audit_sha256(x), dq.audit_sha256(x2)]}
    det["identical"] = len(set(det["drysdale_sha256"])) == 1 and len(set(det["quality_sha256"])) == 1
    inst = prep.instrument
    contract_ok = (inst.root, inst.expiration_year, inst.expiration_month) == CONTRACT
    lifecycle = snap.current_dataset.lifecycle_as_of
    status = (DateStatus.NOT_A_COHORT_DATE if td not in COHORT_DATES and td >= COHORT_START else
              DateStatus.CONTRACT_MISMATCH if not contract_ok else
              DateStatus.NOT_FINALIZED if lifecycle != "FINALIZED" else
              DateStatus.ANALYSIS_NOT_AVAILABLE if a.state is dry.CandidateState.NOT_AVAILABLE else
              DateStatus.ELIGIBLE)
    finals = [c for c in a.candidates if c.state in QUAL]
    by_id = {q.candidate_id: q for q in x.candidates}
    fkn = first_known(session, finals, fk) if first_known_search and finals else {}
    statics = dry._statics(snap)
    anchor = a.bands.anchor_utc
    cands = []
    for c in finals:
        q = by_id[c.candidate_id]
        k = fkn.get(c.candidate_id)
        elig_first = None
        if k and k["resolved"]:
            cut = ReplayCutoff.at(datetime.fromisoformat(k["first_known_utc"].replace("Z", "+00:00")))
            af = dry.analyze(session, cutoff=cut)
            xf = dq.audit(af, session.snapshot(cutoff=cut))
            elig_first = next(z.eligibility.value for z in xf.candidates if z.candidate_id == c.candidate_id)
        lookahead = []
        if k and k["resolved"]:
            t = datetime.fromisoformat(k["first_known_utc"].replace("Z", "+00:00"))
            if t < c.completed_at_utc or q.evidence_window_end_utc > t:
                lookahead.append("KNOWN_BEFORE_ITS_COMPLETING_BAR_ENDED")
            if not k["absent_before"]:  # None: present 1 us before its completing bar ended
                lookahead.append("PRESENT_AT_THE_PRECEDING_PROBE")
        seq = sequence_violations(c, a.bars)
        cands.append({
            "candidate_id": c.candidate_id, "family": c.family.value, "short": SHORT[c.family],
            "direction": c.direction.value, "state": c.state.value, "trading_date": td.isoformat(),
            "first_event_utc": _iso(c.first_event_utc), "completed_at_utc": _iso(c.completed_at_utc),
            "minutes_since_anchor": int((c.completed_at_utc - anchor) // timedelta(minutes=1)),
            "stratum": stratum(c.completed_at_utc, td).value, "condition_bars": condition_bars(c),
            "structural_key": structural_key(c),
            "evidence_window_utc": [_iso(q.evidence_window_start_utc), _iso(q.evidence_window_end_utc)],
            "eligibility": q.eligibility.value, "eligibility_at_first_known": elig_first,
            "reasons": [[r.code.value, r.scope.value, r.materiality.value] for r in q.reasons],
            "reason_combination": reason_combination(q), "quality_tags": quality_tags(q),
            "knowledge": k, "lookahead_violations": lookahead, "sequence_violations": seq,
            "semantic_violations": semantic_violations(c, a.bars),
            "context": context_facts(c, a.bars, statics) if not seq else None,
            "family_facts": family_facts(c, a.bars) if not seq else None,
        })
    withdrawn = []
    if sweep:
        final_keys = {c["structural_key"] for c in cands}
        seen = set()
        for label, cut in _sweep(session, td):
            if cut.market_time_cutoff_utc > fk.market_time_cutoff_utc:
                continue
            for c in dry.analyze(session, cutoff=cut).candidates:
                key = structural_key(c)
                if c.state in QUAL and key not in final_keys and key not in seen:
                    seen.add(key)
                    withdrawn.append({"cutoff_ct": label, "candidate_id": c.candidate_id, "family": c.family.value,
                                      "completed_at_utc": _iso(c.completed_at_utc),
                                      "stratum": stratum(c.completed_at_utc, td).value,
                                      "present_at_final_with_other_structure": c.candidate_id in
                                      {z["candidate_id"] for z in cands}})
    gaps = snap.dataset_quality.gaps
    rec = {
        "schema": SCHEMA, "trading_date": td.isoformat(), "dataset_id": str(prep.dataset_id),
        "contract": inst.canonical_id, "date_status": status.value, "lifecycle_at_final_knowledge": lifecycle,
        "final_knowledge_cutoff": {"market_utc": _iso(fk.market_time_cutoff_utc),
                                   "knowledge_utc": _iso(fk.knowledge_time_cutoff_utc)},
        "analysis_status": a.status, "analysis_state": a.state.value,
        "analysis_reason_codes": sorted({dq.classify_reason(r).value for r in a.reasons}),
        "boundary_status": x.boundary_status.value, "capture_started_at_utc": _iso(x.capture_started_at),
        "known_gaps": [{"type": g.evidence_type, "start_utc": _iso(g.start_utc), "end_utc": _iso(g.end_utc)}
                       for g in gaps],
        "active_interruption": snap.dataset_quality.active_interruption is not None,
        "determinism": det, "candidates": cands, "not_a_candidate_instances":
            sum(1 for c in a.candidates if c.state not in QUAL),
        "funnel": funnel(a), "withdrawn_or_revised": withdrawn, "sweep_performed": sweep,
        "first_known_search_performed": first_known_search,
    }
    rec["record_sha256"] = record_sha256(rec)
    return rec


def error_record(trading_date: date | None, database: str, message: str) -> dict:
    rec = {"schema": SCHEMA, "trading_date": None if trading_date is None else trading_date.isoformat(),
           "dataset": database, "date_status": DateStatus.HARNESS_ERROR.value, "error": message}
    rec["record_sha256"] = record_sha256(rec)
    return rec


def record_sha256(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k != "record_sha256"}
    return hashlib.sha256(mss._dumps(body).encode("ascii")).hexdigest()


# --- cohort (pure) -------------------------------------------------------------------------------------------

def _median(xs: list[int]) -> Fraction | None:
    if not xs:
        return None
    s = sorted(xs)
    m = len(s) // 2
    return Fraction(s[m]) if len(s) % 2 else Fraction(s[m - 1] + s[m], 2)


def _num(x: Fraction | None) -> str | None:
    if x is None:
        return None
    return str(x.numerator) if x.denominator == 1 else str(Decimal(x.numerator) / Decimal(x.denominator))


def quality_counts(cands: list[dict]) -> dict:
    """The pre-registered quality accounting: four top-level counts, the overlapping ELIGIBLE_QUALITY_QUALIFIED
    sub-counts, and the exact reason combinations (each ELIGIBLE_QUALITY_QUALIFIED candidate counted once)."""
    top = Counter(c["eligibility"] for c in cands)
    eqq = [c for c in cands if c["eligibility"] == "ELIGIBLE_QUALITY_QUALIFIED"]
    sub = {t: sum(t in c["quality_tags"] for c in eqq)
           for t in ("BOUNDARY_PROVENANCE", "BOUNDARY_LOCAL_EVIDENCE", "UPSTREAM_REFERENCE")}
    combos = Counter(c["reason_combination"] for c in eqq)
    out = {"total": len(cands), "ELIGIBLE_UNQUALIFIED": top["ELIGIBLE_UNQUALIFIED"],
           "ELIGIBLE_QUALITY_QUALIFIED": top["ELIGIBLE_QUALITY_QUALIFIED"], "NOT_ELIGIBLE": top["NOT_ELIGIBLE"],
           "eligible_quality_qualified_subcounts": sub,
           "eligible_quality_qualified_combinations": dict(sorted(combos.items())),
           "not_eligible_combinations": dict(sorted(Counter(c["reason_combination"] for c in cands
                                                            if c["eligibility"] == "NOT_ELIGIBLE").items()))}
    out["coherent"] = (out["ELIGIBLE_UNQUALIFIED"] + out["ELIGIBLE_QUALITY_QUALIFIED"] + out["NOT_ELIGIBLE"] ==
                       out["total"] and sum(combos.values()) == out["ELIGIBLE_QUALITY_QUALIFIED"] and
                       not any("UNEXPLAINED_UPSTREAM_REASON" in c["reason_combination"] for c in cands))
    return out


def _window(c: dict) -> tuple[str, str]:
    return c["evidence_window_utc"][0], c["evidence_window_utc"][1]


def overlaps(cands: list[dict]) -> dict:
    """Among one date's eligible candidates: same completion time, sequence (evidence-window) overlap, family overlap
    and directional conflict, with exact family-pair combinations. Overlap is descriptive, never 'bad'."""
    order = {f.value: i for i, f in enumerate(FAMILIES)}
    pairs = Counter()
    same_time = seq = fam = conflict = 0
    involved = set()
    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = cands[i], cands[j]
            (sa, ea), (sb, eb) = _window(a), _window(b)
            if a["completed_at_utc"] == b["completed_at_utc"]:
                same_time += 1
            if sa < eb and sb < ea:
                seq += 1
                involved |= {a["candidate_id"], b["candidate_id"]}
                x, y = sorted((a, b), key=lambda c: (order[c["family"]], c["direction"]))
                pairs[f"{x['short']}+{y['short']}"] += 1
                fam += a["family"] != b["family"]
                conflict += a["direction"] != b["direction"]
    return {"same_time_pairs": same_time, "sequence_overlap_pairs": seq, "family_overlap_pairs": fam,
            "directional_conflict_pairs": conflict, "candidates_in_sequence_overlap": len(involved),
            "pair_combinations": dict(sorted(pairs.items())), "overlapping_ids": sorted(involved)}


def _eligible(c: dict) -> bool:
    return c["eligibility"] in ELIGIBLE


def date_summary(rec: dict) -> dict:
    """§28 deterministic date-level summary (factual only)."""
    cands = rec["candidates"]
    el = [c for c in cands if _eligible(c)]
    st = Counter(c["stratum"] for c in el)
    return {
        "trading_date": rec["trading_date"], "dataset_id": rec["dataset_id"], "contract": rec["contract"],
        "date_status": rec["date_status"], "quality_status": rec["analysis_status"],
        "quality_reason_codes": rec["analysis_reason_codes"], "total_candidates": len(cands),
        "eligible_candidates": len(el),
        "by_family": {f.value: sum(c["family"] == f.value for c in el) for f in FAMILIES},
        "UP": sum(c["direction"] == "UP" for c in el), "DOWN": sum(c["direction"] == "DOWN" for c in el),
        "first_hour": st[Stratum.FIRST_GLOBEX_HOUR.value],
        "overnight": st[Stratum.FIRST_GLOBEX_HOUR.value] + st[Stratum.LATER_OVERNIGHT.value],
        "cash_session": st[Stratum.US_CASH_SESSION.value], "post_cash": st[Stratum.POST_CASH.value],
        "overlaps": overlaps(el)["sequence_overlap_pairs"],
        "not_eligible_candidates": sum(c["eligibility"] == "NOT_ELIGIBLE" for c in cands),
        "known_gaps": len(rec["known_gaps"]), "active_interruption": rec["active_interruption"],
        "notes": [f"date_status {rec['date_status']}"] + ([f"{len(rec['withdrawn_or_revised'])} candidate(s) known "
                                                           "earlier and withdrawn or revised by later knowledge"]
                                                          if rec["withdrawn_or_revised"] else []),
    }


def _family_outcomes(el: list[dict], eligible_dates: list[dict], family: str | None) -> dict:
    cs = [c for c in el if family is None or c["family"] == family]
    per_date = [sum(1 for c in r["_el"] if family is None or c["family"] == family) for r in eligible_dates]
    n = len(eligible_dates)
    st = Counter(c["stratum"] for c in cs)
    mins = sorted(c["minutes_since_anchor"] for c in cs)
    q = quality_counts([c for r in eligible_dates for c in r["candidates"] if family is None or c["family"] == family])
    ov = sum(1 for c in cs if c["_overlap"])
    return {
        "eligible_candidates": len(cs),
        "count_per_date": {r["trading_date"]: k for r, k in zip(eligible_dates, per_date)},
        "per_eligible_date": {"mean": _num(Fraction(len(cs), n)) if n else None, "median": _num(_median(per_date)),
                              "min": min(per_date, default=None), "max": max(per_date, default=None)},
        "UP": sum(c["direction"] == "UP" for c in cs), "DOWN": sum(c["direction"] == "DOWN" for c in cs),
        "by_stratum": {s.value: {"count": st[s.value], "per_eligible_date": _num(Fraction(st[s.value], n)) if n
                                 else None} for s in Stratum},
        "minutes_since_anchor": {"values": mins, "min": mins[0] if mins else None,
                                 "median": _num(_median(mins)), "max": mins[-1] if mins else None},
        "quality": q, "overlap_frequency": {"in_sequence_overlap": ov, "of": len(cs)},
        "dates": {"zero": sum(k == 0 for k in per_date), "one": sum(k == 1 for k in per_date),
                  "multiple": sum(k > 1 for k in per_date)},
        "sample_too_small": family is not None and len(cs) < MIN_FAMILY_CANDIDATES,
    }


def _hypotheses(el: list[dict], eligible_dates: list[dict]) -> dict:
    pdc = [c for c in el if c["short"] == "PDC" and c["family_facts"]]

    def dist(key):
        return dict(sorted(Counter(c["family_facts"][key] for c in pdc).items()))

    support = Counter(sum(c["family_facts"]["supporting_context"].values()) for c in pdc)
    rtv = [c for c in el if c["short"] == "RTV" and c["family_facts"]]
    bounce = [c for c in el if c["short"] == "BOUNCE" and c["family_facts"]]
    same_date_pairs = identical = 0
    for r in eligible_dates:
        fs = [c for c in r["_el"] if c["short"] == "FADE"]
        ps = [c for c in r["_el"] if c["short"] == "PDC"]
        same_date_pairs += len(fs) * len(ps)
        identical += sum(f["condition_bars"] == p["condition_bars"] for f in fs for p in ps)
    return {
        "H-PDC-1": {"outside_closes_trigger_to_completion": dict(sorted(Counter(
            c["family_facts"]["outside_closes_trigger_to_completion"] for c in pdc).items())),
                    "seconds_beyond_trigger_to_completion": sorted(
                        Decimal(c["family_facts"]["seconds_beyond_trigger_to_completion"]) for c in pdc)},
        "H-PDC-2": {"supporting_facts_present": dict(sorted(support.items())),
                    **{k: sum(c["family_facts"]["supporting_context"][k] for c in pdc)
                       for k in ("SLOPE_ALIGNED", "REACHED_2SD_BY_COMPLETION", "VOLUME_ABOVE_BASELINE_MEDIAN",
                                 "REFERENCE_BREAK")}, "of": len(pdc)},
        "H-PDC-3": dict(sorted(Counter(c["stratum"] for c in pdc).items())),
        "2SD": dist("reach_2sd"), "VOLUME": {"breakout_vs_baseline_median": dist("breakout_volume_vs_baseline_median"),
                                             "breakout_vs_baseline_mean": dist("breakout_volume_vs_baseline_mean")},
        "SLOPE": {"at_trigger": dist("vwap_slope_at_trigger"), "at_completion": dist("vwap_slope_at_completion")},
        "H-FADE-3": {"same_date_fade_pdc_pairs": same_date_pairs, "identical_condition_bar_sequences": identical},
        "H-RTV-3": {"with_later_retest": sum(c["family_facts"]["later_retest_present_by_session_end"] for c in rtv),
                    "without_later_retest": sum(not c["family_facts"]["later_retest_present_by_session_end"]
                                                for c in rtv)},
        "H-BOUNCE-3": {"vwap_slope_at_test_bar": dict(sorted(Counter(
            c["family_facts"]["vwap_slope_at_test_bar"] for c in bounce).items())),
                       "vwap_slope_at_confirmation_bar": dict(sorted(Counter(
                           c["family_facts"]["vwap_slope_at_confirmation_bar"] for c in bounce).items()))},
    }


def human_review_sample(el: list[dict]) -> dict[str, list[str]]:
    """§38: per family the earliest eligible candidate (trading date, completion, id) and the lower-median one by
    minutes since the anchor among the rest (ties: date, id). Fewer than two: all. Never chosen by appearance."""
    out = {}
    for f in FAMILIES:
        cs = sorted((c for c in el if c["family"] == f.value),
                    key=lambda c: (c["trading_date"], c["completed_at_utc"], c["candidate_id"]))
        if len(cs) <= HUMAN_SAMPLE_PER_FAMILY:
            out[f.value] = [f"{c['trading_date']}/{c['candidate_id']}" for c in cs]
            continue
        rest = sorted(cs[1:], key=lambda c: (c["minutes_since_anchor"], c["trading_date"], c["candidate_id"]))
        med = rest[(len(rest) - 1) // 2]
        out[f.value] = [f"{c['trading_date']}/{c['candidate_id']}" for c in (cs[0], med)]
    return out


def challenge_flags(eligible_dates: list[dict], el: list[dict]) -> dict:
    per_date = [len(r["_el"]) for r in eligible_dates]
    med = _median(per_date)
    zero = sum(k == 0 for k in per_date)
    fam = Counter(c["family"] for c in el)
    top = max(fam.values(), default=0)
    out = {Flag.CANDIDATE_DENSITY_CHALLENGED.value: bool(med is not None and med > DENSITY_MEDIAN_MAX),
           Flag.CANDIDATE_SCARCITY_CHALLENGED.value: bool(per_date and Fraction(zero, len(per_date)) >
                                                          SCARCITY_ZERO_SHARE)}
    if len(el) < MIN_ELIGIBLE_CANDIDATES:
        out[Flag.FAMILY_DOMINANCE_FOR_REVIEW.value] = None  # distribution conclusions INCONCLUSIVE: not evaluated
    else:
        out[Flag.FAMILY_DOMINANCE_FOR_REVIEW.value] = Fraction(top, len(el)) > DOMINANCE_SHARE
    out["_inputs"] = {"median_eligible_per_date": _num(med), "zero_candidate_dates": zero,
                      "eligible_dates": len(per_date), "largest_family_share":
                          None if not el else _num(Fraction(top, len(el)))}
    return out


def classify(*, determinism_failures: int, lookahead_defects: int, knowledge_unresolved: int,
             sequence_or_semantic_violations: int, violating_candidates: int, attribution: Attribution | None,
             harness_errors: int, quality_coherent: bool, eligible_dates: int,
             flags: dict) -> tuple[Classification, list[str]]:
    """§31 precedence: BLOCKED / FAIL, then INCONCLUSIVE, then PASS WITH CHALLENGES, then PASS."""
    why = []
    if determinism_failures:
        why.append(f"NONDETERMINISM on {determinism_failures} date(s)")
    if lookahead_defects:
        why.append(f"LOOKAHEAD defect in {lookahead_defects} candidate(s)")
    if knowledge_unresolved:
        why.append(f"first-known time unresolved for {knowledge_unresolved} candidate(s)")
    if harness_errors:
        why.append(f"{harness_errors} date(s) could not be evaluated")
    if not quality_coherent:
        why.append("quality accounting not coherent")
    if sequence_or_semantic_violations:
        if attribution is Attribution.FROZEN_RULE and violating_candidates >= 2 and not why:
            return Classification.FAIL, [f"frozen rules repeatedly violate their own structure "
                                         f"({violating_candidates} candidates)"]
        why.append(f"{sequence_or_semantic_violations} sequence / semantic violation(s) "
                   + (f"attributed to {attribution.value}" if attribution else "pending investigation"))
    if why:
        return Classification.BLOCKED, why
    if eligible_dates < MIN_ELIGIBLE_DATES:
        return Classification.INCONCLUSIVE, [f"{eligible_dates} eligible dates < {MIN_ELIGIBLE_DATES}"]
    fired = [k for k, v in flags.items() if not k.startswith("_") and v]
    if fired:
        return Classification.PASS_WITH_CHALLENGES, fired
    return Classification.PASS, []


def cohort_summary(records: list[dict], expected: tuple[date, ...] = COHORT_DATES,
                   attribution: Attribution | None = None) -> dict:
    """§29 cohort summary, §6 primary outcomes, §7 funnels, §13-§20 hypotheses and overlap, §21-§23 flags, §25-§27
    subsets, §31-§34 classification and sample rules, §38 Human-review sample, §39 curriculum tables."""
    by_date = {r["trading_date"]: r for r in records}
    dates = []
    for d in expected:
        r = by_date.get(d.isoformat())
        dates.append(r if r is not None else {"trading_date": d.isoformat(), "date_status": "NOT_CAPTURED"})
    unexpected = sorted(set(by_date) - {d.isoformat() for d in expected})
    eligible_dates = [r for r in dates if r["date_status"] == DateStatus.ELIGIBLE.value]
    for r in eligible_dates:
        r["_el"] = [c for c in r["candidates"] if _eligible(c)]
        ids = set(overlaps(r["_el"])["overlapping_ids"])
        for c in r["_el"]:
            c["_overlap"] = c["candidate_id"] in ids
    el = [c for r in eligible_dates for c in r["_el"]]
    all_c = [c for r in eligible_dates for c in r["candidates"]]
    q = quality_counts(all_c)
    flags = challenge_flags(eligible_dates, el)
    seq = sum(len(c["sequence_violations"]) + len(c["semantic_violations"]) for c in all_c)
    viol_c = sum(1 for c in all_c if c["sequence_violations"] or c["semantic_violations"])
    look = sum(1 for c in all_c if c["lookahead_violations"])
    unresolved = sum(1 for c in all_c if c["knowledge"] is not None and not c["knowledge"]["resolved"])
    det = sum(1 for r in eligible_dates if not r["determinism"]["identical"])
    errors = sum(1 for r in dates if r.get("error"))
    cls, why = classify(determinism_failures=det, lookahead_defects=look, knowledge_unresolved=unresolved,
                        sequence_or_semantic_violations=seq, violating_candidates=viol_c, attribution=attribution,
                        harness_errors=errors, quality_coherent=q["coherent"], eligible_dates=len(eligible_dates),
                        flags=flags)
    first_hour = [c for c in all_c if c["stratum"] == Stratum.FIRST_GLOBEX_HOUR.value]
    fh_q = quality_counts(first_hour)
    funnels = {f.value: _sum_funnels([r["funnel"][f.value] for r in eligible_dates]) for f in FAMILIES}
    pair_totals = Counter()
    for r in eligible_dates:
        pair_totals.update(overlaps(r["_el"])["pair_combinations"])
    cash = [c for c in el if c["stratum"] == Stratum.US_CASH_SESSION.value]
    summary = {
        "schema": SCHEMA, "cohort": [min(expected).isoformat(), max(expected).isoformat()],
        "registered_cohort": expected == COHORT_DATES,
        "expected_dates": len(expected), "unexpected_records": unexpected,
        "dates": {"captured": sum(r["date_status"] != "NOT_CAPTURED" for r in dates),
                  "finalized_cleanly": sum(r.get("lifecycle_at_final_knowledge") == "FINALIZED" for r in dates),
                  "eligible": len(eligible_dates),
                  "with_quality_qualifications": sum(r["analysis_status"] != "AVAILABLE" for r in eligible_dates),
                  "excluded": {r["trading_date"]: r["date_status"] for r in dates
                               if r["date_status"] != DateStatus.ELIGIBLE.value}},
        "date_summaries": [date_summary(r) for r in eligible_dates],
        "quality": q,
        "all_families": _family_outcomes(el, eligible_dates, None),
        "families": {f.value: _family_outcomes(el, eligible_dates, f.value) for f in FAMILIES},
        "distinct_families_per_date": {r["trading_date"]: len({c["family"] for c in r["_el"]}) for r in eligible_dates},
        "funnels": funnels,
        "overlap": {"pair_combinations": dict(sorted(pair_totals.items())),
                    "candidates_in_sequence_overlap": sum(c["_overlap"] for c in el), "of": len(el)},
        "hypotheses": _hypotheses(el, eligible_dates),
        "first_hour": {"candidates": len(first_hour), "quality": fh_q,
                       "eligibility_changed_after_first_known": sum(
                           1 for c in first_hour if c["eligibility_at_first_known"] not in (None, c["eligibility"])),
                       "withdrawn_or_revised": sum(1 for r in eligible_dates for w in r["withdrawn_or_revised"]
                                                   if w["stratum"] == Stratum.FIRST_GLOBEX_HOUR.value)},
        "cash_session_subset": {"all_families": _subset(cash, eligible_dates),
                                "families": {f.value: _subset([c for c in cash if c["family"] == f.value],
                                                              eligible_dates) for f in FAMILIES}},
        "post_cash": _subset([c for c in el if c["stratum"] == Stratum.POST_CASH.value], eligible_dates),
        "knowledge_time": {"receipt_delay_seconds": sorted(Decimal(c["knowledge"]["receipt_delay_seconds"])
                                                           for c in all_c if c["knowledge"] and
                                                           c["knowledge"]["resolved"]),
                           "unresolved": unresolved, "lookahead_defects": look},
        "implementation": {"determinism_failures": det, "sequence_semantic_violations": seq,
                           "violating_candidates": viol_c, "harness_errors": errors},
        "flags": flags,
        "sample_rules": {"eligible_dates": len(eligible_dates), "min_eligible_dates": MIN_ELIGIBLE_DATES,
                         "eligible_candidates": len(el), "min_eligible_candidates": MIN_ELIGIBLE_CANDIDATES,
                         "distribution_conclusions": "INCONCLUSIVE" if len(el) < MIN_ELIGIBLE_CANDIDATES else
                         "INTERPRETABLE",
                         "family_sample_too_small": [f.value for f in FAMILIES
                                                     if sum(c["family"] == f.value for c in el) <
                                                     MIN_FAMILY_CANDIDATES]},
        "classification": cls.value, "classification_basis": why,
        "human_review_sample": human_review_sample(el),
        "curriculum": _curriculum(el, funnels, pair_totals, q),
        "human_review": "RESERVED FOR HUMAN REVIEW (not filled automatically)",
    }
    for r in eligible_dates:
        r.pop("_el")
        for c in r["candidates"]:
            c.pop("_overlap", None)
    return summary


def _subset(cs: list[dict], eligible_dates: list[dict]) -> dict:
    n = len(eligible_dates)
    per = Counter(c["trading_date"] for c in cs)
    vals = [per.get(r["trading_date"], 0) for r in eligible_dates]
    return {"eligible_candidates": len(cs), "UP": sum(c["direction"] == "UP" for c in cs),
            "DOWN": sum(c["direction"] == "DOWN" for c in cs),
            "by_family": {f.value: sum(c["family"] == f.value for c in cs) for f in FAMILIES},
            "per_eligible_date": {"mean": _num(Fraction(len(cs), n)) if n else None, "median": _num(_median(vals))},
            "minutes_since_anchor_median": _num(_median([c["minutes_since_anchor"] for c in cs])),
            "quality": quality_counts(cs), "dates": {"zero": sum(v == 0 for v in vals), "one": sum(v == 1 for v in vals),
                                                     "multiple": sum(v > 1 for v in vals)}}


def _sum_funnels(fs: list[dict]) -> dict:
    if not fs:
        return {}
    n = fs[0]["conditions"]
    stops = Counter()
    for f in fs:
        stops.update(f["first_unsatisfied"])
    return {"instances": sum(f["instances"] for f in fs), "conditions": n,
            "policies": next((f["policies"] for f in fs if f["policies"]), []),
            "reached_at_least": [sum(f["reached_at_least"][k] for f in fs) for k in range(n)],
            "satisfied_by_condition": [sum(f["satisfied_by_condition"][k] for f in fs) for k in range(n)],
            "first_unsatisfied": dict(sorted(stops.items()))}


def _curriculum(el: list[dict], funnels: dict, pairs: Counter, q: dict) -> dict:
    """§39 tables (curriculum questions; no trading recommendation). 'Enough' reuses the registered
    MIN_FAMILY_CANDIDATES (5) as a Laboratory curriculum convenience."""
    cell = Counter((c["family"], c["stratum"]) for c in el)
    fam = Counter(c["family"] for c in el)
    return {
        "family_counts": {f.value: fam[f.value] for f in FAMILIES},
        "families_too_sparse_for_lessons": [f.value for f in FAMILIES if fam[f.value] < MIN_FAMILY_CANDIDATES],
        "family_stratum_cells_with_enough_examples": sorted(f"{f}/{s}" for (f, s), k in cell.items()
                                                            if k >= MIN_FAMILY_CANDIDATES),
        "most_common_first_unsatisfied": {f: (max(v["first_unsatisfied"].items(), key=lambda kv: (kv[1], kv[0]))[0]
                                              if v.get("first_unsatisfied") else None) for f, v in funnels.items()},
        "overlap_combinations": dict(pairs.most_common()),
        "quality_warnings_to_explain": {**q["eligible_quality_qualified_combinations"],
                                        **{f"NOT_ELIGIBLE:{k}": v for k, v in q["not_eligible_combinations"].items()}},
    }


def render_report(s: dict) -> str:
    """Markdown first readout (machine-generated part; the Human review section stays empty)."""
    L = [f"# Drysdale prospective validation — first readout ({SCHEMA})", "",
         f"Dates {s['cohort'][0]} .. {s['cohort'][1]}; expected {s['expected_dates']} dates" +
         ("" if s["registered_cohort"] else " (NOT the registered validation cohort: development / descriptive only)")
         + ".", "",
         f"**Classification: {s['classification']}**" + (f" — {'; '.join(s['classification_basis'])}"
                                                          if s["classification_basis"] else ""), "",
         "## Dates", "", "| | |", "|---|---|"]
    L += [f"| {k} | {v} |" for k, v in s["dates"].items() if k != "excluded"]
    L += [f"| excluded | {', '.join(f'{d} {r}' for d, r in s['dates']['excluded'].items()) or 'none'} |", ""]
    L += ["## Date-level summary", "", "| Date | Status | Quality | Total | Eligible | PDC | FADE | RTV | BOUNCE | UP | "
          "DOWN | First hour | Overnight | Cash | POST_CASH | Overlaps | Not eligible | Gaps |", "|" + "---|" * 18]
    for d in s["date_summaries"]:
        bf = d["by_family"]
        L.append(f"| {d['trading_date']} | {d['date_status']} | {d['quality_status']} | {d['total_candidates']} | "
                 f"{d['eligible_candidates']} | " + " | ".join(str(bf[f.value]) for f in FAMILIES) +
                 f" | {d['UP']} | {d['DOWN']} | {d['first_hour']} | {d['overnight']} | {d['cash_session']} | "
                 f"{d['post_cash']} | {d['overlaps']} | {d['not_eligible_candidates']} | {d['known_gaps']} |")
    q = s["quality"]
    L += ["", "## Quality accounting (pre-registered)", "", "```text",
          f"total candidates             {q['total']}", f"ELIGIBLE_UNQUALIFIED         {q['ELIGIBLE_UNQUALIFIED']}",
          f"ELIGIBLE_QUALITY_QUALIFIED   {q['ELIGIBLE_QUALITY_QUALIFIED']}"]
    L += [f"  - {k:26s} {v}" for k, v in q["eligible_quality_qualified_subcounts"].items()]
    L += [f"NOT_ELIGIBLE                 {q['NOT_ELIGIBLE']}", "```", "", "Exact combinations:", ""]
    L += [f"- `{k or '(none)'}`: {v}" for k, v in q["eligible_quality_qualified_combinations"].items()]
    L += ["", "## Families", ""]
    for f, o in s["families"].items():
        L += [f"### {f}", "", f"- eligible candidates {o['eligible_candidates']} (UP {o['UP']}, DOWN {o['DOWN']}); "
              f"per eligible date mean {o['per_eligible_date']['mean']}, median {o['per_eligible_date']['median']}, "
              f"range {o['per_eligible_date']['min']}..{o['per_eligible_date']['max']}",
              "- by stratum: " + ", ".join(f"{k} {v['count']}" for k, v in o["by_stratum"].items()),
              f"- minutes since anchor: min {o['minutes_since_anchor']['min']}, median "
              f"{o['minutes_since_anchor']['median']}, max {o['minutes_since_anchor']['max']}",
              f"- dates zero / one / multiple: {o['dates']['zero']} / {o['dates']['one']} / {o['dates']['multiple']}",
              f"- in sequence overlap: {o['overlap_frequency']['in_sequence_overlap']} of {o['overlap_frequency']['of']}"]
        if o["sample_too_small"]:
            L.append("- **FAMILY SAMPLE TOO SMALL FOR STRUCTURAL CONCLUSION**")
        fn = s["funnels"][f]
        if fn:
            L.append(f"- funnel (instances {fn['instances']}): reached at least condition 1..{fn['conditions']}: "
                     f"{fn['reached_at_least']}; first unsatisfied: {fn['first_unsatisfied']}")
        L.append("")
    L += ["## Hypotheses (descriptive)", "", "```json", mss._dumps(mss.encode(s["hypotheses"])), "```", "",
          "## Overlap", "", f"{s['overlap']}", "", "## First Globex hour", "", f"{mss._dumps(mss.encode(s['first_hour']))}",
          "", "## Flags", "", f"{mss._dumps(mss.encode(s['flags']))}", "", "## Sample rules", "",
          f"{mss._dumps(mss.encode(s['sample_rules']))}", "", "## Human-review sample (deterministic)", ""]
    L += [f"- {f}: {', '.join(v) or 'none'}" for f, v in s["human_review_sample"].items()]
    L += ["", "## Curriculum questions", "", "```json", mss._dumps(mss.encode(s["curriculum"])), "```", "",
          "## Human review", "", s["human_review"], ""]
    return "\n".join(L)
