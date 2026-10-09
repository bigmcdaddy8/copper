"""DAY_STRUCTURE_STRENGTH_V1 over the frozen 0Y-D corpus (0Y-E): a derived, read-only report.

The V1 label of every day is taken from the frozen 0Y-D record (never re-decided);
the strength facts come from re-analysing the same immutable database, and the
caller verifies that the re-analysis reproduces the frozen record byte-for-byte.
Descriptive tables only: no threshold, ranking, score or interpretation.
"""
from __future__ import annotations

from decimal import Decimal

from dicks_laboratory.tpo_day_strength import DayStructureStrength
from dicks_laboratory.tpo_validation import DayRecord, Eligibility

# The days PO asked to be shown side by side (0Y-E §9-§10); a fixed list, not a selection rule.
DEMONSTRATION_DAYS = (
    ("2026-09-30", "principal example: V1 NEUTRAL_DAY with a token counter-extension"),
    ("2026-09-28", "the most two-sided V1 NEUTRAL_DAY"),
    ("2026-09-21", "the accepted V1 TREND_DAY"),
    ("2026-09-02", "the smallest-extension V1 NORMAL_VARIATION_DAY"),
    ("2026-09-29", "the day nearest the 0.50 IB-share boundary"),
)


def _d(value, places: str = "0.0001") -> str:
    if value is None:
        return "undefined"
    return str(value.quantize(Decimal(places))) if isinstance(value, Decimal) else str(value)


def _label(record: DayRecord) -> tuple[str, str]:
    if record.day_type:
        return record.day_type, record.direction or "—"
    return record.outcome or Eligibility.NO_PROFILE, "—"


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def render_strength_corpus_report(
    entries: list[tuple[DayRecord, DayStructureStrength]],
    frozen_sha256: str,
    reproduced: int,
    report_paths: dict[str, str],
) -> str:
    """`entries` pairs each frozen 0Y-D record with its strength facts; `report_paths` maps dataset_id."""
    entries = sorted(entries, key=lambda e: (e[0].trading_date, e[0].dataset_id))
    eligible = [e for e in entries if e[0].eligibility == Eligibility.ELIGIBLE]
    lines = [
        "# DAY_STRUCTURE_STRENGTH_V1 over the frozen 0Y-D corpus",
        "",
        f"- Frozen 0Y-D records: `records.jsonl` sha256 `{frozen_sha256}` (verified before use; not modified).",
        f"- Datasets re-analysed: {len(entries)}; re-analysis reproduced the frozen V1 record byte-for-byte: "
        f"{reproduced}/{len(entries)}.",
        "- V1 labels below are the frozen 0Y-D labels (DAY_TYPE_V1). Strength facts are measurements beside them,",
        "  not a re-classification, score or trading conclusion. Ratios: 4 dp; 'undefined' = zero denominator.",
        "",
        f"## Eligible days ({len(eligible)})",
        "",
    ]
    rows = []
    for record, s in eligible:
        day_type, direction = _label(record)
        rows.append([record.trading_date, day_type, direction, _d(s.ib_share_of_range),
                     _d(s.extension_above_per_ib), _d(s.extension_below_per_ib),
                     s.dominant_extension.value, _d(s.dominant_per_ib), _d(s.counter_to_dominant),
                     f"{s.new_high_period_count} ({s.new_high_periods or '-'})",
                     f"{s.new_low_period_count} ({s.new_low_periods or '-'})",
                     _d(s.terminal_percentile)])
    lines += _table(["date", "V1 candidate", "dir", "IB share", "above/IB", "below/IB", "dominant",
                     "dominant/IB", "counter/dominant", "new-high periods", "new-low periods", "terminal pct"], rows)

    lines += ["", "## Persistence and structural context (eligible days)", ""]
    rows = []
    for record, s in eligible:
        rows.append([record.trading_date, _label(record)[0],
                     f"{s.max_consecutive_new_high_periods}/{s.max_consecutive_new_low_periods}",
                     f"{s.longest_higher_low_run}/{s.longest_lower_high_run}",
                     f"{(s.first_extension_direction.value if s.first_extension_direction else '-')}/"
                     f"{(s.last_extension_direction.value if s.last_extension_direction else '-')}",
                     f"{s.upper_tail_rows}/{s.lower_tail_rows}",
                     f"{s.interior_one_tpo_zone_count} ({s.interior_one_tpo_rows})",
                     _d(s.poc_percentile), _d(s.ib_midpoint_percentile), _d(s.value_area_midpoint_percentile)])
    lines += _table(["date", "V1 candidate", "consec. new hi/lo", "HL/LH run", "first/last ext",
                     "tail rows up/down", "interior zones (rows)", "POC pct", "IB mid pct", "VA mid pct"], rows)

    lines += ["", "## Facts inside each V1 label (descriptive)", ""]
    labels = sorted({_label(r)[0] for r, _ in eligible})
    rows = []
    for name in labels:
        group = [s for r, s in eligible if _label(r)[0] == name]
        ratios = sorted(s.counter_to_dominant for s in group if s.counter_to_dominant is not None)
        dom = sorted(s.dominant_per_ib for s in group if s.dominant_per_ib is not None)
        pct = sorted(s.terminal_percentile for s in group if s.terminal_percentile is not None)
        rows.append([name, str(len(group)),
                     f"{_d(ratios[0])} .. {_d(ratios[-1])}" if ratios else "—",
                     f"{_d(dom[0])} .. {_d(dom[-1])}" if dom else "—",
                     f"{_d(pct[0])} .. {_d(pct[-1])}" if pct else "—"])
    lines += _table(["V1 candidate", "n", "counter/dominant min..max", "dominant/IB min..max",
                     "terminal pct min..max"], rows)

    others = [e for e in entries if e[0].eligibility != Eligibility.ELIGIBLE]
    lines += ["", f"## Not eligible ({len(others)}): no full-day strength assessment", ""]
    rows = []
    for record, s in others:
        scope = s.scope.value if s is not None else "no profile"
        rows.append([record.trading_date, record.dataset_id[:8], record.eligibility, scope,
                     "; ".join(record.reasons) or "—"])
    lines += _table(["date", "dataset", "0Y-D eligibility", "strength scope", "reason"], rows)

    lines += ["", "## Demonstration days", ""]
    by_date = {r.trading_date: (r, s) for r, s in eligible}
    for day, why in DEMONSTRATION_DAYS:
        if day not in by_date:
            lines.append(f"- {day}: not in the eligible corpus")
            continue
        record, s = by_date[day]
        day_type, direction = _label(record)
        lines.append(f"- **{day}** ({why}): V1 {day_type} {direction if direction != '—' else ''}".rstrip()
                     + f"; state {s.directional_state.value}; above {s.extension_above_ticks} / below "
                     f"{s.extension_below_ticks} ticks (IB {s.ib_range_ticks}); dominant {s.dominant_extension.value} "
                     f"{_d(s.dominant_per_ib)} x IB; counter/dominant {_d(s.counter_to_dominant)}; new highs "
                     f"{s.new_high_period_count}, new lows {s.new_low_period_count}; terminal pct "
                     f"{_d(s.terminal_percentile)} — report `{report_paths[record.dataset_id]}`")
    return "\n".join(lines) + "\n"
