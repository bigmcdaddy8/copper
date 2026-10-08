"""0Y-C real-data study set: day-structure facts, V1 candidates and a segmentation audit.

Read-only and offline. Usage (repo root):
    uv run python docs/dicks_laboratory/evidence/0Y-C/day_structure_study.py OUT_DIR DB[:TRADING_DATE] ...

For each database: writes `day_structure_<date>_<id8>.txt` (the --day-structure
report without the matrix) and prints one study-table row. Policies are applied
blindly; nothing here tunes a threshold. The DIAGNOSTIC column re-runs the same V1
policy with the coverage gate removed, only for days the gate blocked, and is
never a classification.
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

from dicks_laboratory.analysis import open_dataset_store, resolve_dataset_id
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, render_tpo_report
from dicks_laboratory.tpo_day_structure import (
    ClassificationOutcome,
    ClassificationQuality,
    QualityGrade,
    classify_day_type,
)


def label(day) -> str:
    if day.outcome is ClassificationOutcome.CANDIDATE:
        return day.primary.value + (f" {day.direction.value}" if day.direction else "")
    return day.outcome.value


def peaks(counts: list[int], min_prominence: int) -> int:
    """Plateau-collapsed local maxima whose drop to the deeper-of-the-higher valley side is >= min_prominence."""
    runs = [c for i, c in enumerate(counts) if i == 0 or c != counts[i - 1]]
    found = 0
    for i, c in enumerate(runs):
        left, right = runs[:i], runs[i + 1:]
        if (left and left[-1] >= c) or (right and right[0] >= c):
            continue
        # prominence: c minus the highest valley floor separating it from a higher peak (or profile edge)
        def floor(side):
            low = c
            for v in side:
                if v > c:
                    return low
                low = min(low, v)
            return low
        prom = c - max(floor(reversed(left)), floor(right))
        found += prom >= min_prominence
    return found


def main(out_dir: str, *specs: str) -> None:
    out = Path(out_dir)
    rows = []
    for spec in specs:
        path, _, td = spec.partition(":")
        store = open_dataset_store(Path(path))
        try:
            did = resolve_dataset_id(store, None)
            r = analyze_tpo_dataset(store, did, date.fromisoformat(td) if td else None)
        finally:
            store.close()
        day, p = r.day_structure, r.profile
        name = f"day_structure_{r.trading_date}_{str(did)[:8]}.txt"
        (out / name).write_text(render_tpo_report(r, show_matrix=False, show_day_structure=True) + "\n")
        f = day.facts
        diag = "--"
        if day.quality.grade is QualityGrade.NOT_CLASSIFIABLE:
            d = classify_day_type(f, ClassificationQuality(QualityGrade.UNQUALIFIED, ()))
            diag = label(d) + ("" if d.outcome is not ClassificationOutcome.NOT_CLASSIFIED
                               else " (" + "; ".join(d.not_classified_reasons) + ")")
        counts = [lv.tpo_count for lv in p.levels]
        rows.append([
            str(r.trading_date), str(did)[:8], r.quality.status.value.split(" /")[0], day.quality.grade.value,
            str(f.ib_range), str(f.profile_range),
            "undef" if f.range_multiple_of_ib is None else str(f.range_multiple_of_ib.quantize(Decimal("0.01"))),
            "undef" if f.ib_share_of_range is None else str(f.ib_share_of_range.quantize(Decimal("0.0001"))),
            str(f.extension_above), str(f.extension_below), f.directional_state.value,
            f.new_post_ib_high_periods or "-", f.new_post_ib_low_periods or "-",
            f"{f.upper_extreme.tail_level_count}/{f.lower_extreme.tail_level_count}/{len(f.interior_one_tpo_zones)}",
            f"{f.terminal.price} @{f.terminal.percentile_in_range.quantize(Decimal('0.01'))}",
            label(day), day.direction.value if day.direction else "-", day.policy_version, diag,
            f"{peaks(counts, 1)}/{peaks(counts, 2)}/{peaks(counts, 3)}/{peaks(counts, 5)}",
        ])
    head = ["TD", "dataset", "dataset quality", "class. quality", "IB", "range", "range/IB", "IB share",
            "ext above", "ext below", "state", "new highs", "new lows", "tails up/low/interior zones",
            "terminal @pct", "candidate", "direction", "policy", "DIAGNOSTIC (gate removed)",
            "TPO peaks prom>=1/2/3/5"]
    print("| " + " | ".join(head) + " |")
    print("|" + "---|" * len(head))
    for row in rows:
        print("| " + " | ".join(row) + " |")


if __name__ == "__main__":
    main(*sys.argv[1:])
