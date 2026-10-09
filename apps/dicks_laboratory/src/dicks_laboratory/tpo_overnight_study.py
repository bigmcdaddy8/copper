"""Multi-day overnight-context and opening-path fact study over the research corpus (0Y-G).

Read-only and descriptive: one row of facts per profiled day and a mechanically selected
inspection set. No opening type, inventory label, preferred scale, threshold or
interpretation is produced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from dicks_laboratory.tpo_opening import ContextOutcome, Side
from dicks_laboratory.tpo_opening_path import GRACE_HORIZON_MINUTES, OpeningPathFacts, ReferenceEncounter

STUDY_SCALES = (30, 60, 180, 300, 900, 1800)


@dataclass(frozen=True)
class OvernightRow:
    trading_date: str
    dataset_id: str
    contract: str
    facts: OpeningPathFacts

    @property
    def open_available(self) -> bool:
        return self.facts.opening.session.available

    @property
    def overnight_available(self) -> bool:
        o = self.facts.overnight
        return o is not None and o.session.available

    @property
    def paired(self) -> bool:
        return self.facts.opening.outcome is ContextOutcome.AVAILABLE


def _reached(row: OvernightRow) -> list[ReferenceEncounter]:
    return [e for e in row.facts.encounters if e.reached_utc is not None and e.side_of_open is not Side.NONE]


# Inspection rules, fixed before the study ran. Ties -> earlier trading date.
SELECTION_RULES = (
    ("largest overnight range", "overnight available; max ON range ticks"),
    ("smallest overnight range", "overnight available; min ON range ticks"),
    ("cash open nearest ON high", "open + overnight available; min |open - ONH| ticks"),
    ("cash open nearest ON low", "open + overnight available; min |open - ONL| ticks"),
    ("most one-sided 5m opening", "open available; min 5-min counter/dominant, then max larger excursion"),
    ("most one-sided 30m opening", "open available; min 30-min counter/dominant, then max larger excursion"),
    ("latest last open cross", "open available; max (last open cross - open print) on the 60-min scale"),
    ("longest residence above open", "open available; max longest UP residence on the 60-min scale"),
    ("longest residence below open", "open available; max longest DOWN residence on the 60-min scale"),
    ("fastest reference reach -> open cross", "any prior/overnight reference reached in 30 min and followed by an "
                                              "open cross; min reach-to-cross delay"),
    ("largest opposite excursion after reference reach", "same encounters; max 30-min opposite excursion after the "
                                                         "open cross"),
)


def inspection_set(rows: list[OvernightRow]) -> list[tuple[str, OvernightRow | None, str]]:
    rows = sorted(rows, key=lambda r: (r.trading_date, r.dataset_id))
    on = [r for r in rows if r.overnight_available]
    both = [r for r in on if r.open_available]
    avail = [r for r in rows if r.open_available]

    def pick(cands, key):
        best = None
        for r in cands:  # strict improvement only: ties keep the earlier date
            if best is None or key(r) > key(best):
                best = r
        return best

    def sided(seconds):
        defined = [r for r in avail if r.facts.scale(seconds).counter_to_dominant is not None]
        r = pick(defined, lambda r: (-r.facts.scale(seconds).counter_to_dominant,
                                     max(r.facts.scale(seconds).excursion_up_ticks,
                                         r.facts.scale(seconds).excursion_down_ticks)))
        if r is None:
            return r, ""
        x = r.facts.scale(seconds)
        return r, (f"up {x.excursion_up_ticks} / down {x.excursion_down_ticks} ticks, counter/dominant "
                   f"{x.counter_to_dominant.quantize(Decimal('0.0001'))}")

    out = []
    r = pick(on, lambda r: r.facts.overnight.session.range_ticks)
    out.append((SELECTION_RULES[0][0], r, f"{r.facts.overnight.session.range_ticks} ticks" if r else ""))
    r = pick(on, lambda r: -r.facts.overnight.session.range_ticks)
    out.append((SELECTION_RULES[1][0], r, f"{r.facts.overnight.session.range_ticks} ticks" if r else ""))
    r = pick(both, lambda r: -abs(r.facts.overnight.open_vs_onh_ticks))
    out.append((SELECTION_RULES[2][0], r, f"open - ONH {r.facts.overnight.open_vs_onh_ticks} ticks" if r else ""))
    r = pick(both, lambda r: -abs(r.facts.overnight.open_vs_onl_ticks))
    out.append((SELECTION_RULES[3][0], r, f"open - ONL {r.facts.overnight.open_vs_onl_ticks} ticks" if r else ""))
    out.append((SELECTION_RULES[4][0], *sided(300)))
    out.append((SELECTION_RULES[5][0], *sided(1800)))
    crossed = [r for r in avail if r.facts.scale(3600).open_to_last_cross is not None]
    r = pick(crossed, lambda r: r.facts.scale(3600).open_to_last_cross)
    out.append((SELECTION_RULES[6][0], r, f"last cross {_secs(r.facts.scale(3600).open_to_last_cross)} after the "
                                          "open print" if r else ""))
    ups = [r for r in avail if r.facts.scale(3600).longest_up_residence is not None]
    r = pick(ups, lambda r: r.facts.scale(3600).longest_up_residence)
    out.append((SELECTION_RULES[7][0], r, _residence(r, "up") if r else ""))
    downs = [r for r in avail if r.facts.scale(3600).longest_down_residence is not None]
    r = pick(downs, lambda r: r.facts.scale(3600).longest_down_residence)
    out.append((SELECTION_RULES[8][0], r, _residence(r, "down") if r else ""))
    pairs = [(r, e) for r in avail for e in _reached(r) if e.crossed_open_after]
    best = None
    for r, e in pairs:
        if best is None or e.reach_to_cross < best[1].reach_to_cross:
            best = (r, e)
    out.append((SELECTION_RULES[9][0], best[0] if best else None,
                f"{best[1].reference} reached {best[1].side_of_open.value} of open; open crossed "
                f"{_secs(best[1].reach_to_cross)} later" if best else ""))
    best = None
    for r, e in pairs:
        if best is None or dict(e.opposite_excursion_after_cross)[30] > dict(best[1].opposite_excursion_after_cross)[30]:
            best = (r, e)
    out.append((SELECTION_RULES[10][0], best[0] if best else None,
                f"{best[1].reference}: {dict(best[1].opposite_excursion_after_cross)[30]} ticks beyond the open on the "
                "other side within 30 min of the cross" if best else ""))
    return out


def _secs(td) -> str:
    return "—" if td is None else f"{td.total_seconds():.3f}s"


def _residence(r: OvernightRow, side: str) -> str:
    x = r.facts.scale(3600)
    length, start = ((x.longest_up_residence, x.longest_up_residence_start_utc) if side == "up"
                     else (x.longest_down_residence, x.longest_down_residence_start_utc))
    return f"{_secs(length)} from {start:%H:%M:%S}Z"


def _p(value) -> str:
    return "—" if value is None else str(value.quantize(Decimal("0.0001")))


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _label(seconds: int) -> str:
    return f"{seconds}s" if seconds < 60 else f"{seconds // 60}m"


def scale_summary(rows: list[OvernightRow]) -> list[list[str]]:
    """Counts of days without an open cross per diagnostic scale. Descriptive; no scale is preferred."""
    avail = [r for r in rows if r.open_available]
    out = []
    windows = {5: 300, 15: 900, 30: 1800}
    out.append(["tick path (from the open print)", str(len(avail))]
               + [str(sum(1 for r in avail if r.facts.scale(windows[m]).open_cross_count == 0))
                  for m in GRACE_HORIZON_MINUTES])
    for i, g in enumerate(avail[0].facts.grace if avail else ()):
        held = [r for r in avail if r.facts.grace[i].held_side is not Side.NONE]
        out.append([f"after +{g.grace_seconds}s (held side; {len(avail) - len(held)} day(s) still at the open)",
                    str(len(held))]
                   + [str(sum(1 for r in held if not r.facts.grace[i].horizons[k].crossed_open))
                      for k in range(len(GRACE_HORIZON_MINUTES))])
    a_one_side = sum(1 for r in avail if not (r.facts.opening.session.window(30).traded_above_open
                                              and r.facts.opening.session.window(30).traded_below_open))
    out.append(["A-period (traded on one side of the open only)", str(len(avail)), "—", "—", str(a_one_side)])
    return out


def render_study_report(rows: list[OvernightRow], report_paths: dict[str, str]) -> str:
    rows = sorted(rows, key=lambda r: (r.trading_date, r.dataset_id))
    lines = ["# Overnight context and multi-scale opening study (0Y-G)", "",
             "Facts only. No opening type or inventory label is named; no threshold or preferred scale is applied. "
             "Ticks are 0.25. Times are seconds after the relevant print. ON = overnight [17:00, 08:30) CT.", "",
             "## Quality (kept separate)", ""]
    t = []
    for r in rows:
        q = r.facts.quality
        on = r.facts.overnight
        t.append([r.trading_date, r.dataset_id[:8], q.current_open.value, q.prior_day_outcome.value,
                  q.overnight.value if q.overnight else "—",
                  "; ".join(on.session.quality.reasons) if on is not None and on.session.quality.reasons else "—"])
    lines += _table(["date", "dataset", "CURRENT_OPEN", "PRIOR_DAY", "OVERNIGHT", "overnight reasons"], t)
    lines += ["", "## Overnight facts", ""]
    t = []
    for r in rows:
        if not r.overnight_available:
            continue
        ctx = r.facts.overnight
        s, rel = ctx.session, ctx.prior_relation
        term = ctx.occupancy("PRIOR_TERMINAL")
        t.append([
            r.trading_date, str(s.high), str(s.low), str(s.range_ticks), s.extreme_order.value,
            "—" if s.globex_open_price is None else str(s.globex_open_price),
            ctx.open_location.value if ctx.open_location else "—", _p(ctx.open_percentile_in_overnight_range),
            "—" if rel is None else f"{rel.excursion_above_prior_high_ticks}/{rel.excursion_below_prior_low_ticks}",
            "—" if rel is None else f"{rel.excursion_above_vah_ticks}/{rel.excursion_below_val_ticks}",
            "—" if rel is None else ("yes" if rel.inside_prior_value else "no"),
            "—" if term is None else f"{term.seconds_above:.0f}/{term.seconds_below:.0f}/{term.seconds_at:.0f}",
            "—" if term is None else f"{_p(term.fraction_above)}/{_p(term.fraction_below)}",
            "—" if term is None else f"{term.tpo_rows_above}/{term.tpo_rows_below}",
            "—" if term is None or term.volume_above is None else f"{term.volume_above:.0f}/{term.volume_below:.0f}",
            "—" if ctx.gap("CASH_OPEN_VS_PRIOR_TERMINAL") is None else str(ctx.gap("CASH_OPEN_VS_PRIOR_TERMINAL").ticks),
            "—" if ctx.gap("CASH_OPEN_VS_OVERNIGHT_TERMINAL") is None
            else str(ctx.gap("CASH_OPEN_VS_OVERNIGHT_TERMINAL").ticks),
        ])
    lines += _table(["date", "ONH", "ONL", "ON range t", "order", "Globex open", "cash open vs ON", "open pct in ON",
                     "ON beyond prior H/L t", "ON beyond VAH/VAL t", "ON inside prior value",
                     "sec above/below/at prior terminal", "frac above/below", "TPO rows above/below",
                     "volume above/below", "gap open-prior term t", "gap open-ON term t"], t)
    lines += ["", "## Multi-scale opening facts", "",
              "Each cell: dominant side, counter/dominant (smaller/larger excursion from the open).", ""]
    t = []
    for r in rows:
        if not r.open_available:
            continue
        f = r.facts
        cells = [f"{f.scale(s).dominant.value} {_p(f.scale(s).counter_to_dominant)}" for s in STUDY_SCALES]
        x30, x60 = f.scale(1800), f.scale(3600)
        e = f.opening.session.early_tpo
        t.append([r.trading_date, *cells, f"{f.opening.session.window(30).dominant.value}",
                  _p(e.ab_overlap_ratio), str(x30.open_cross_count), _secs(x30.open_to_last_cross),
                  _secs(x60.open_to_last_cross), _secs(x60.longest_up_residence), _secs(x60.longest_down_residence)])
    lines += _table(["date", *(_label(s) for s in STUDY_SCALES), "A-period", "A/B overlap", "crosses 30m",
                     "last cross 30m", "last cross 60m", "longest UP res 60m", "longest DOWN res 60m"], t)
    lines += ["", "## Reference encounters (first 30 minutes)", "",
              "Reach = first trade at or beyond the reference from the open's side. Opposite excursion = ticks beyond "
              "the open on the other side in [cross, cross+N).", ""]
    t = []
    for r in rows:
        if not r.open_available:
            continue
        first = r.facts.first_reference_reached
        reached = _reached(r)
        if first is None:
            t.append([r.trading_date, "none reached", "—", "—", "—", "—", str(len(reached))])
            continue
        after = ", ".join(f"{m}m {v}" for m, v in first.opposite_excursion_after_cross) or "—"
        t.append([r.trading_date, first.reference, first.side_of_open.value,
                  f"+{(first.reached_utc - r.facts.opening.session.cash_open.timestamp_utc).total_seconds():.3f}s",
                  "no cross" if not first.crossed_open_after else _secs(first.reach_to_cross), after, str(len(reached))])
    lines += _table(["date", "first reference reached", "side of open", "reached at", "reach → open cross",
                     "opposite excursion after cross", "references reached"], t)
    lines += ["", "## Grace-instant diagnostics (DIAGNOSTIC ONLY)", "",
              "Days whose held side at the grace instant was not crossed within the opening window. No grace period "
              "is preferred.", ""]
    lines += _table(["scale", "days evaluated", "no cross in 5m", "no cross in 15m", "no cross in 30m"],
                    scale_summary(rows))
    lines += ["", "## Mechanical inspection set", "",
              "Rules were fixed in code (`SELECTION_RULES`) before the study ran; ties go to the earlier date.", ""]
    t = []
    for (name, rule), (_, r, why) in zip(SELECTION_RULES, inspection_set(rows)):
        t.append([name, rule, r.trading_date if r else "none in corpus", why or "—",
                  f"`{report_paths[r.dataset_id]}`" if r else "—"])
    lines += _table(["slot", "rule", "day", "fact", "report"], t)
    return "\n".join(lines) + "\n"
