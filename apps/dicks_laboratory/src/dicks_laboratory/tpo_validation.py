"""Blind multi-day validation of the frozen day-type candidate policies (0Y-D).

Two stages, kept apart so the policy cannot be adjusted between them:

  1. `day_record(result)` flattens one `TpoAnalysisResult` (already classified by
     the frozen 0Y-C policy) into an immutable `DayRecord`; records are written
     once and hashed (the "blind run").
  2. Everything else here reads only those records: inventory, distribution,
     boundary proximity, per-type sensitivity, structural outliers and a
     mechanically selected inspection shortlist.

Nothing here classifies, re-thresholds or interprets. Diagnostics only; see
docs/dicks_laboratory/MARKET_PROFILE_VALIDATION_0YD.md.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from decimal import Decimal
from statistics import median

from dicks_laboratory.tpo_analysis import TpoAnalysisResult
from dicks_laboratory.tpo_day_structure import (
    NORMAL_MIN_IB_SHARE,
    NORMAL_VARIATION_MIN_IB_SHARE,
    ClassificationOutcome,
    DayType,
    DirectionalState,
    QualityGrade,
)

# Diagnostic proximity band around the frozen IB-share boundaries (PO-specified; not a policy).
BOUNDARY_BAND = Decimal("0.05")
BOUNDARIES = (NORMAL_VARIATION_MIN_IB_SHARE, NORMAL_MIN_IB_SHARE)


class Eligibility:
    ELIGIBLE = "ELIGIBLE"  # evaluated, quality UNQUALIFIED
    QUALITY_QUALIFIED = "QUALITY_QUALIFIED"  # evaluated, gap evidence inside window / not FINALIZED
    NOT_CLASSIFIED = "NOT_CLASSIFIED"  # not evaluated (coverage, empty periods, no IB, ...)
    NO_PROFILE = "NO_PROFILE"  # no retained trade inside the study window


@dataclass(frozen=True)
class DayRecord:
    trading_date: str
    dataset_id: str
    contract: str
    lifecycle: str | None
    window_captured: bool | None
    known_gap_count: int
    suspected_gap_count: int
    gaps_overlapping_window: int
    dataset_quality: str
    classification_quality: str | None
    eligibility: str
    reasons: tuple[str, ...]
    outcome: str | None
    day_type: str | None
    direction: str | None
    policy_version: str | None
    failed_conditions: tuple[str, ...]  # "<TYPE>:<condition>" for every evaluated candidate
    ib_range: Decimal | None = None
    profile_range: Decimal | None = None
    ib_share: Decimal | None = None
    range_multiple_of_ib: Decimal | None = None
    ext_above: Decimal | None = None
    ext_below: Decimal | None = None
    ext_above_ticks: int | None = None
    ext_below_ticks: int | None = None
    ext_above_ib: Decimal | None = None
    ext_below_ib: Decimal | None = None
    directional_state: str | None = None
    first_extension: str | None = None
    last_extension: str | None = None
    periods_extending_above: str = ""
    periods_extending_below: str = ""
    new_high_periods: str = ""
    new_low_periods: str = ""
    terminal_price: Decimal | None = None
    terminal_pct: Decimal | None = None
    poc_pct: Decimal | None = None
    upper_tail_rows: int | None = None
    lower_tail_rows: int | None = None
    interior_zones: int | None = None
    interior_zone_rows: int | None = None
    periods_without_trades: str = ""

    @property
    def evaluated(self) -> bool:
        return self.eligibility in (Eligibility.ELIGIBLE, Eligibility.QUALITY_QUALIFIED)

    @property
    def label(self) -> str:
        if self.outcome == ClassificationOutcome.CANDIDATE.value:
            return self.day_type + (f" {self.direction}" if self.direction else "")
        return self.outcome or Eligibility.NO_PROFILE


def day_record(result: TpoAnalysisResult) -> DayRecord:
    q = result.quality
    base = dict(
        trading_date=result.trading_date.isoformat(),
        dataset_id=str(result.dataset_id),
        contract=result.instrument.canonical_id,
        lifecycle=q.lifecycle_state,
        window_captured=q.study_window_captured,
        known_gap_count=q.known_gap_count,
        suspected_gap_count=q.suspected_gap_count,
        gaps_overlapping_window=q.gaps_overlapping_study_window,
        dataset_quality=q.status.value,
    )
    day = result.day_structure
    if day is None:
        return DayRecord(**base, classification_quality=None, eligibility=Eligibility.NO_PROFILE,
                         reasons=("no retained trades inside the study window",), outcome=None, day_type=None,
                         direction=None, policy_version=None, failed_conditions=())
    f = day.facts
    if day.outcome is ClassificationOutcome.NOT_CLASSIFIED:
        eligibility, reasons = Eligibility.NOT_CLASSIFIED, day.not_classified_reasons
    elif day.quality.grade is QualityGrade.QUALITY_QUALIFIED:
        eligibility, reasons = Eligibility.QUALITY_QUALIFIED, day.quality.reasons
    else:
        eligibility, reasons = Eligibility.ELIGIBLE, ()
    struct = result.structure
    return DayRecord(
        **base,
        classification_quality=day.quality.grade.value,
        eligibility=eligibility,
        reasons=tuple(reasons),
        outcome=day.outcome.value,
        day_type=day.primary.value if day.primary else None,
        direction=day.direction.value if day.direction else None,
        policy_version=day.policy_version,
        failed_conditions=tuple(f"{c.day_type.value}:{cond.name}" for c in day.candidates for cond in c.failed),
        ib_range=f.ib_range,
        profile_range=f.profile_range,
        ib_share=f.ib_share_of_range,
        range_multiple_of_ib=f.range_multiple_of_ib,
        ext_above=f.extension_above,
        ext_below=f.extension_below,
        ext_above_ticks=f.extension_above_ticks,
        ext_below_ticks=f.extension_below_ticks,
        ext_above_ib=f.extension_above_multiple_of_ib,
        ext_below_ib=f.extension_below_multiple_of_ib,
        directional_state=f.directional_state.value if f.directional_state else None,
        first_extension=f.first_extension_direction.value if f.first_extension_direction else None,
        last_extension=f.last_extension_direction.value if f.last_extension_direction else None,
        periods_extending_above=f.periods_extending_above_ib,
        periods_extending_below=f.periods_extending_below_ib,
        new_high_periods=f.new_post_ib_high_periods,
        new_low_periods=f.new_post_ib_low_periods,
        terminal_price=f.terminal.price if f.terminal else None,
        terminal_pct=f.terminal.percentile_in_range if f.terminal else None,
        poc_pct=f.poc_percentile,
        upper_tail_rows=f.upper_extreme.tail_level_count,
        lower_tail_rows=f.lower_extreme.tail_level_count,
        interior_zones=len(struct.interior_zones),
        interior_zone_rows=sum(z.level_count for z in struct.interior_zones),
        periods_without_trades=f.periods_without_trades,
    )


# --- serialization (Decimal kept exact as strings) ---------------------------------------

_DECIMAL_FIELDS = {f.name for f in fields(DayRecord) if "Decimal" in str(f.type)}
_TUPLE_FIELDS = {f.name for f in fields(DayRecord) if str(f.type).startswith("tuple")}


def record_to_json(record: DayRecord) -> str:
    data = {k: (str(v) if isinstance(v, Decimal) else list(v) if isinstance(v, tuple) else v)
            for k, v in asdict(record).items()}
    return json.dumps(data, sort_keys=True)


def record_from_json(line: str) -> DayRecord:
    data = json.loads(line)
    for key in _DECIMAL_FIELDS:
        if data.get(key) is not None:
            data[key] = Decimal(data[key])
    for key in _TUPLE_FIELDS:
        data[key] = tuple(data[key])
    return DayRecord(**data)


# --- derived diagnostics -------------------------------------------------------------------

def quantiles(values: list[Decimal]) -> dict[str, Decimal] | None:
    """min / q25 / median / q75 / max by nearest rank on sorted values (deterministic; no interpolation
    except the median of an even count)."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)

    def rank(p: Decimal) -> Decimal:
        k = int((p * n).to_integral_value(rounding="ROUND_CEILING"))
        return s[max(k, 1) - 1]

    return {"min": s[0], "q25": rank(Decimal("0.25")), "median": median(s), "q75": rank(Decimal("0.75")),
            "max": s[-1]}


def distribution(records: list[DayRecord]) -> dict[str, dict[str, int]]:
    """Counts by outcome label, separately for ELIGIBLE and QUALITY_QUALIFIED days."""
    out: dict[str, dict[str, int]] = {Eligibility.ELIGIBLE: {}, Eligibility.QUALITY_QUALIFIED: {}}
    for r in records:
        if r.evaluated:
            key = r.day_type if r.outcome == ClassificationOutcome.CANDIDATE.value else r.outcome
            out[r.eligibility][key] = out[r.eligibility].get(key, 0) + 1
    return out


@dataclass(frozen=True)
class BoundaryCase:
    record: DayRecord
    boundary: Decimal
    distance: Decimal  # ib_share - boundary (signed)

    @property
    def side(self) -> str:
        return "at/above" if self.distance >= 0 else "below"


def boundary_cases(records: list[DayRecord], band: Decimal = BOUNDARY_BAND) -> list[BoundaryCase]:
    cases = [BoundaryCase(r, b, r.ib_share - b) for r in records if r.evaluated and r.ib_share is not None
             for b in BOUNDARIES if abs(r.ib_share - b) <= band]
    return sorted(cases, key=lambda c: (c.boundary, abs(c.distance), c.record.trading_date))


@dataclass(frozen=True)
class NeutralAsymmetry:
    record: DayRecord
    smaller_ticks: int
    larger_ticks: int
    smaller_ib: Decimal
    larger_ib: Decimal
    smaller_over_larger: Decimal


def neutral_asymmetry(record: DayRecord) -> NeutralAsymmetry:
    up, down = (record.ext_above_ticks, record.ext_above_ib), (record.ext_below_ticks, record.ext_below_ib)
    small, large = sorted((up, down), key=lambda x: x[0])
    return NeutralAsymmetry(record, small[0], large[0], small[1], large[1], Decimal(small[0]) / Decimal(large[0]))


def one_sided_extension(record: DayRecord) -> tuple[Decimal, int, Decimal, int, int]:
    """(extension points, ticks, extension / IB, extending periods, new-extreme periods) on the extended side."""
    if record.directional_state == DirectionalState.DOWN_ONLY.value:
        return (record.ext_below, record.ext_below_ticks, record.ext_below_ib,
                len(record.periods_extending_below), len(record.new_low_periods))
    return (record.ext_above, record.ext_above_ticks, record.ext_above_ib,
            len(record.periods_extending_above), len(record.new_high_periods))


def of_type(records: list[DayRecord], day_type: DayType, eligibility: str = Eligibility.ELIGIBLE) -> list[DayRecord]:
    return [r for r in records if r.eligibility == eligibility and r.day_type == day_type.value]


def _extremes(rows: list[DayRecord], key, largest: bool) -> tuple[Decimal | int | None, list[str]]:
    vals = [(key(r), r.trading_date) for r in rows if key(r) is not None]
    if not vals:
        return None, []
    best = max(v for v, _ in vals) if largest else min(v for v, _ in vals)
    return best, sorted(d for v, d in vals if v == best)


def structural_outliers(records: list[DayRecord]) -> list[tuple[str, Decimal | int | None, list[str]]]:
    """Named-type-independent extremes over evaluated days; ties list every date."""
    ev = [r for r in records if r.evaluated]
    one = [r for r in ev if r.directional_state in (DirectionalState.UP_ONLY.value, DirectionalState.DOWN_ONLY.value)]
    both = [r for r in ev if r.directional_state == DirectionalState.BOTH_SIDES.value]
    sym = lambda r: neutral_asymmetry(r).smaller_over_larger  # noqa: E731
    return [
        ("largest profile / IB ratio", *_extremes(ev, lambda r: r.range_multiple_of_ib, True)),
        ("smallest profile / IB ratio", *_extremes(ev, lambda r: r.range_multiple_of_ib, False)),
        ("largest one-sided extension / IB", *_extremes(one, lambda r: one_sided_extension(r)[2], True)),
        ("most symmetric two-sided extension (smaller/larger)", *_extremes(both, sym, True)),
        ("most asymmetric two-sided extension (smaller/larger)", *_extremes(both, sym, False)),
        ("largest upper tail (rows)", *_extremes(ev, lambda r: r.upper_tail_rows, True)),
        ("largest lower tail (rows)", *_extremes(ev, lambda r: r.lower_tail_rows, True)),
        ("most periods making new post-IB highs", *_extremes(ev, lambda r: len(r.new_high_periods), True)),
        ("most periods making new post-IB lows", *_extremes(ev, lambda r: len(r.new_low_periods), True)),
        ("terminal price nearest high (percentile)", *_extremes(ev, lambda r: r.terminal_pct, True)),
        ("terminal price nearest low (percentile)", *_extremes(ev, lambda r: r.terminal_pct, False)),
    ]


# Recorded before any profile was inspected; each rule is mechanical over ELIGIBLE days.
SHORTLIST_RULES = (
    ("representative NORMAL_DAY", "ELIGIBLE NORMAL_DAY whose IB share is nearest that type's median IB share"),
    ("representative NORMAL_VARIATION_DAY", "same rule for NORMAL_VARIATION_DAY"),
    ("representative TREND_DAY", "same rule for TREND_DAY"),
    ("representative NEUTRAL_DAY", "same rule for NEUTRAL_DAY"),
    ("nearest 0.50 boundary", "ELIGIBLE day with the smallest |IB share - 0.50|"),
    ("nearest 0.85 boundary", "ELIGIBLE day with the smallest |IB share - 0.85|"),
    ("most asymmetric NEUTRAL_DAY", "smallest smaller/larger extension ratio"),
    ("smallest-extension NORMAL_VARIATION_DAY", "smallest extension / IB"),
    ("strongest TREND_DAY", "most new-extreme periods, then largest extension / IB"),
    ("first UNCLASSIFIED", "earliest ELIGIBLE UNCLASSIFIED day"),
)


def inspection_shortlist(records: list[DayRecord]) -> list[tuple[str, DayRecord | None]]:
    """Ties always resolve to the earlier trading date."""
    el = sorted((r for r in records if r.eligibility == Eligibility.ELIGIBLE), key=lambda r: r.trading_date)

    def pick(rows, key):
        return min(rows, key=lambda r: (key(r), r.trading_date)) if rows else None

    out: list[tuple[str, DayRecord | None]] = []
    for day_type in (DayType.NORMAL_DAY, DayType.NORMAL_VARIATION_DAY, DayType.TREND_DAY, DayType.NEUTRAL_DAY):
        rows = [r for r in el if r.day_type == day_type.value]
        med = median([r.ib_share for r in rows]) if rows else None
        out.append((f"representative {day_type.value}", pick(rows, lambda r: abs(r.ib_share - med))))
    for b in BOUNDARIES:
        out.append((f"nearest {b} boundary", pick([r for r in el if r.ib_share is not None],
                                                  lambda r, b=b: abs(r.ib_share - b))))
    neutral = [r for r in el if r.day_type == DayType.NEUTRAL_DAY.value]
    out.append(("most asymmetric NEUTRAL_DAY", pick(neutral, lambda r: neutral_asymmetry(r).smaller_over_larger)))
    nv = [r for r in el if r.day_type == DayType.NORMAL_VARIATION_DAY.value]
    out.append(("smallest-extension NORMAL_VARIATION_DAY", pick(nv, lambda r: one_sided_extension(r)[2])))
    trend = [r for r in el if r.day_type == DayType.TREND_DAY.value]
    out.append(("strongest TREND_DAY", pick(trend, lambda r: (-one_sided_extension(r)[4], -one_sided_extension(r)[2]))))
    uncl = [r for r in el if r.outcome == ClassificationOutcome.UNCLASSIFIED.value]
    out.append(("first UNCLASSIFIED", uncl[0] if uncl else None))
    return out


# --- markdown report -------------------------------------------------------------------------

def _d(value, places: str = "0.0001") -> str:
    if value is None:
        return "—"
    return str(value.quantize(Decimal(places))) if isinstance(value, Decimal) else str(value)


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _quantile_line(name: str, values: list[Decimal]) -> str:
    q = quantiles(values)
    if q is None:
        return f"- {name}: no values"
    return f"- {name} (n={len(values)}): " + ", ".join(f"{k} {_d(v)}" for k, v in q.items())


def render_validation_report(records: list[DayRecord], records_sha256: str, report_paths: dict[str, str]) -> str:
    """Facts-first markdown over frozen records. `report_paths` maps dataset_id -> raw report file."""
    records = sorted(records, key=lambda r: (r.trading_date, r.dataset_id))
    el = [r for r in records if r.eligibility == Eligibility.ELIGIBLE]
    qq = [r for r in records if r.eligibility == Eligibility.QUALITY_QUALIFIED]
    out = ["# 0Y-D blind validation report (generated)", "",
           f"Frozen records: `records.jsonl` sha256 `{records_sha256}`. Policy versions present: "
           + ", ".join(sorted({r.policy_version for r in records if r.policy_version})) + ".",
           "Generated mechanically from the frozen records; no threshold was changed.", ""]

    out += ["## 1. Corpus inventory", ""]
    out += _table(["TD", "dataset", "contract", "lifecycle", "window captured", "KNOWN_GAP", "SUSPECTED_GAP",
                   "gaps overlapping window", "eligibility", "reason if not ELIGIBLE"],
                  [[r.trading_date, r.dataset_id[:8], r.contract, r.lifecycle or "UNTRACKED",
                    {True: "yes", False: "NO", None: "unknown"}[r.window_captured], str(r.known_gap_count),
                    str(r.suspected_gap_count), str(r.gaps_overlapping_window), r.eligibility,
                    "; ".join(r.reasons) or "—"] for r in records])
    counts = {e: sum(r.eligibility == e for r in records) for e in
              (Eligibility.ELIGIBLE, Eligibility.QUALITY_QUALIFIED, Eligibility.NOT_CLASSIFIED, Eligibility.NO_PROFILE)}
    out += ["", "Counts: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f" (total {len(records)}).", ""]
    rule_counts = [
        ("study window not fully captured -> NOT_CLASSIFIED", sum(r.window_captured is False for r in records
                                                                  if r.eligibility != Eligibility.NO_PROFILE)),
        ("coverage unknown -> NOT_CLASSIFIED", sum(r.window_captured is None for r in records
                                                   if r.eligibility != Eligibility.NO_PROFILE)),
        ("gap inside window -> QUALITY_QUALIFIED", sum(r.eligibility == Eligibility.QUALITY_QUALIFIED
                                                       and r.gaps_overlapping_window > 0 for r in records)),
        ("gap only outside window -> ELIGIBLE", sum(r.eligibility == Eligibility.ELIGIBLE
                                                    and (r.known_gap_count + r.suspected_gap_count) > 0 for r in records)),
        ("window periods without trades -> NOT_CLASSIFIED", sum(bool(r.periods_without_trades) for r in records
                                                                if r.eligibility == Eligibility.NOT_CLASSIFIED)),
    ]
    out += _table(["quality rule", "days"], [[k, str(v)] for k, v in rule_counts]) + [""]

    head = ["TD", "IB", "range", "IB share", "ext ↑", "ext ↓", "ext ↑/IB", "ext ↓/IB", "state", "new highs",
            "new lows", "terminal pct", "tails ↑/↓", "interior zones", "candidate", "direction", "policy"]

    def row(r: DayRecord) -> list[str]:
        return [r.trading_date, _d(r.ib_range, "0.01"), _d(r.profile_range, "0.01"), _d(r.ib_share),
                _d(r.ext_above, "0.01"), _d(r.ext_below, "0.01"), _d(r.ext_above_ib), _d(r.ext_below_ib),
                r.directional_state or "—", r.new_high_periods or "-", r.new_low_periods or "-", _d(r.terminal_pct),
                f"{r.upper_tail_rows}/{r.lower_tail_rows}", str(r.interior_zones),
                r.day_type or r.outcome, r.direction or "-", r.policy_version]

    out += ["## 2. Blind results — ELIGIBLE days", ""] + _table(head, [row(r) for r in el]) + [""]
    out += ["## 3. Blind results — QUALITY_QUALIFIED days (reported separately)", ""]
    out += (_table(head, [row(r) for r in qq]) if qq else ["none"]) + [""]

    out += ["## 4. Classification distribution", ""]
    dist = distribution(records)
    keys = [t.value for t in DayType] + [ClassificationOutcome.UNCLASSIFIED.value, ClassificationOutcome.AMBIGUOUS.value]
    n = len(el)
    out += _table(["outcome", "ELIGIBLE count", "% of ELIGIBLE", "QUALITY_QUALIFIED count"],
                  [[k, str(dist[Eligibility.ELIGIBLE].get(k, 0)),
                    _d(Decimal(100 * dist[Eligibility.ELIGIBLE].get(k, 0)) / n, "0.1") if n else "—",
                    str(dist[Eligibility.QUALITY_QUALIFIED].get(k, 0))] for k in keys]
                  + [["NOT_CLASSIFIED (incl. NO_PROFILE; not a share of ELIGIBLE)", "—", "—",
                      str(counts[Eligibility.NOT_CLASSIFIED] + counts[Eligibility.NO_PROFILE])]])
    out += ["", _quantile_line("IB share, ELIGIBLE days", [r.ib_share for r in el]), ""]

    out += [f"## 5. Boundary proximity (|IB share − boundary| ≤ {BOUNDARY_BAND}; diagnostic only)", ""]
    cases = boundary_cases(records)
    out += (_table(["TD", "eligibility", "boundary", "IB share", "share − boundary", "side", "state", "candidate"],
                   [[c.record.trading_date, c.record.eligibility, str(c.boundary), _d(c.record.ib_share),
                     _d(c.distance), c.side, c.record.directional_state, c.record.label] for c in cases])
            if cases else ["none"]) + [""]

    neutral = [neutral_asymmetry(r) for r in of_type(records, DayType.NEUTRAL_DAY)]
    out += ["## 6. NEUTRAL_DAY sensitivity (ELIGIBLE)", ""]
    out += (_table(["TD", "ext ↑ ticks", "ext ↓ ticks", "smaller/IB", "larger/IB", "smaller/larger", "terminal pct"],
                   [[a.record.trading_date, str(a.record.ext_above_ticks), str(a.record.ext_below_ticks),
                     _d(a.smaller_ib), _d(a.larger_ib), _d(a.smaller_over_larger), _d(a.record.terminal_pct)]
                    for a in sorted(neutral, key=lambda a: (a.smaller_over_larger, a.record.trading_date))])
            if neutral else ["none"])
    out += ["", _quantile_line("smaller/larger", [a.smaller_over_larger for a in neutral]),
            _quantile_line("smaller extension / IB", [a.smaller_ib for a in neutral]),
            _quantile_line("terminal pct", [a.record.terminal_pct for a in neutral]), ""]

    def one_sided_rows(rows):
        res = []
        for r in rows:
            pts, ticks, rel, ext_periods, new_ext = one_sided_extension(r)
            res.append([r.trading_date, r.direction or r.directional_state, _d(r.ib_share), f"{_d(pts, '0.01')} ({ticks})",
                        _d(rel), _d(pts / r.profile_range), str(ext_periods), str(new_ext), _d(r.terminal_pct),
                        f"{r.upper_tail_rows}/{r.lower_tail_rows}", str(r.interior_zones)])
        return res

    os_head = ["TD", "direction", "IB share", "extension (ticks)", "ext/IB", "ext/range", "extending periods",
               "new-extreme periods", "terminal pct", "tails ↑/↓", "interior zones"]
    for day_type, title in ((DayType.NORMAL_VARIATION_DAY, "## 7. NORMAL_VARIATION_DAY sensitivity (ELIGIBLE)"),
                            (DayType.TREND_DAY, "## 8. TREND_DAY sensitivity (ELIGIBLE)")):
        rows = sorted(of_type(records, day_type), key=lambda r: (one_sided_extension(r)[2], r.trading_date))
        out += [title, ""] + (_table(os_head, one_sided_rows(rows)) if rows else ["none"])
        out += ["", _quantile_line("extension / IB", [one_sided_extension(r)[2] for r in rows]), ""]
        if day_type is DayType.TREND_DAY:
            out += ["Counter-extension on TREND candidates is 0 by construction (one-sided rule).", ""]

    normal = of_type(records, DayType.NORMAL_DAY)
    out += ["## 9. NORMAL_DAY sensitivity (ELIGIBLE)", "",
            "Historical \"wide IB\" context: NOT EVALUATED (V1 condition `ib_wide_vs_history`).", ""]
    out += (_table(["TD", "IB share", "IB", "range", "ext ↑", "ext ↓", "state", "terminal pct"],
                   [[r.trading_date, _d(r.ib_share), _d(r.ib_range, "0.01"), _d(r.profile_range, "0.01"),
                     _d(r.ext_above, "0.01"), _d(r.ext_below, "0.01"), r.directional_state, _d(r.terminal_pct)]
                    for r in normal]) if normal else ["none"]) + [""]

    uncl = [r for r in el if r.outcome == ClassificationOutcome.UNCLASSIFIED.value]
    out += ["## 10. UNCLASSIFIED days (ELIGIBLE) and the conditions that failed", ""]
    out += (_table(["TD", "state", "IB share", "failed conditions"],
                   [[r.trading_date, r.directional_state, _d(r.ib_share), ", ".join(r.failed_conditions)] for r in uncl])
            if uncl else ["none"]) + [""]

    out += ["## 11. Raw structural outliers (ELIGIBLE + QUALITY_QUALIFIED; type-independent)", ""]
    out += _table(["measure", "value", "trading date(s)"],
                  [[name, _d(v) if isinstance(v, Decimal) else str(v), ", ".join(d) or "—"]
                   for name, v, d in structural_outliers(records)]) + [""]

    out += ["## 12. Mechanical inspection shortlist", "", "Selection rules (fixed before inspection; ties → earlier date):", ""]
    out += [f"- **{name}**: {rule}" for name, rule in SHORTLIST_RULES] + [""]
    out += _table(["slot", "TD", "candidate", "IB share", "rendered profile"],
                  [[slot, r.trading_date if r else "—", r.label if r else "no qualifying day",
                    _d(r.ib_share) if r else "—", f"`{report_paths.get(r.dataset_id, '—')}`" if r else "—"]
                   for slot, r in inspection_shortlist(records)]) + [""]
    return "\n".join(out)
