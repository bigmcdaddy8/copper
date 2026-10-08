"""0Y-D follow-up hypotheses: what-if counts over the FROZEN blind records (diagnostic only).

Nothing here changes or proposes an accepted threshold. Each X / Y is an illustrative
grid point for a future policy experiment. Usage (repo root):
    uv run python docs/dicks_laboratory/evidence/0Y-D/hypothesis_whatif.py docs/dicks_laboratory/evidence/0Y-D/blind_run
"""
from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

from dicks_laboratory.tpo_validation import Eligibility, neutral_asymmetry, one_sided_extension, record_from_json

GRID = [Decimal(x) for x in ("0.10", "0.25", "0.50", "1.00")]


def main(run_dir: str) -> None:
    records = [record_from_json(line) for line in (Path(run_dir) / "records.jsonl").read_text().splitlines()]
    el = [r for r in records if r.eligibility == Eligibility.ELIGIBLE]
    neutral = [neutral_asymmetry(r) for r in el if r.day_type == "NEUTRAL_DAY"]
    nv = [r for r in el if r.day_type == "NORMAL_VARIATION_DAY"]
    both = [neutral_asymmetry(r) for r in el if r.directional_state == "BOTH_SIDES"]
    print("H1  NEUTRAL_DAY would require BOTH extensions >= X * IB")
    print("| X | Neutral candidates still passing (of %d) | dates no longer passing |" % len(neutral))
    print("|---|---|---|")
    for x in GRID:
        keep = [a for a in neutral if a.smaller_ib >= x]
        print(f"| {x} | {len(keep)} | {', '.join(a.record.trading_date for a in neutral if a not in keep) or '-'} |")
    print()
    print("H2  NORMAL_VARIATION_DAY would require extension >= Y * IB")
    print("| Y | NV candidates still passing (of %d) | dates no longer passing |" % len(nv))
    print("|---|---|---|")
    for y in GRID:
        keep = [r for r in nv if one_sided_extension(r)[2] >= y]
        print(f"| {y} | {len(keep)} | {', '.join(r.trading_date for r in nv if r not in keep) or '-'} |")
    print()
    print("H3  BOTH_SIDES days whose smaller side is < X * IB ('token counter-extension'); dominant side shown")
    print("| X | days | dominant side (larger extension) and larger/IB |")
    print("|---|---|---|")
    for x in GRID[:2]:
        token = [a for a in both if a.smaller_ib < x]
        desc = ", ".join(f"{a.record.trading_date} "
                         f"{'DOWN' if a.record.ext_below_ticks > a.record.ext_above_ticks else 'UP'} "
                         f"{a.larger_ib.quantize(Decimal('0.0001'))}" for a in token)
        print(f"| {x} | {len(token)} | {desc or '-'} |")


if __name__ == "__main__":
    main(*sys.argv[1:])
