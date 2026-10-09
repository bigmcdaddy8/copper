"""Multi-day opening-auction fact study over the research corpus (0Y-F).

Read-only and descriptive: one row of facts per profiled day, joined to its prior
trading date when one exists, and a mechanically selected inspection set. No
opening-type name, threshold or interpretation is produced here.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from dicks_laboratory.tpo_opening import ContextOutcome, OpeningAuctionFacts, Side


@dataclass(frozen=True)
class OpeningRow:
    trading_date: str
    dataset_id: str
    contract: str
    facts: OpeningAuctionFacts

    @property
    def available(self) -> bool:
        return self.facts.session.available

    @property
    def paired(self) -> bool:
        return self.facts.outcome is ContextOutcome.AVAILABLE


def initial_move_before_cross(facts: OpeningAuctionFacts, minutes: int = 60) -> tuple[Side, int, object] | None:
    """(first direction, ticks travelled that way before the first open cross, cross time) or None if no cross."""
    s = facts.session
    w = s.window(minutes)
    if w is None or w.first_open_cross_utc is None:
        return None
    o = s.cash_open.tick
    before = [p.tick for p in s.path if p.timestamp_utc < w.first_open_cross_utc]
    sign = 1 if w.first_direction is Side.UP else -1
    return w.first_direction, max(sign * (t - o) for t in before), w.first_open_cross_utc


# Inspection rules, fixed before the study ran. Ties -> earlier trading date.
SELECTION_RULES = (
    ("largest open above prior range", "paired days opening ABOVE_PRIOR_RANGE; max open - prior high (ticks)"),
    ("largest open below prior range", "paired days opening BELOW_PRIOR_RANGE; max prior low - open (ticks)"),
    ("most one-sided first 30 min", "available days; min 30-min counter/dominant excursion, then max larger excursion"),
    ("most balanced first 30 min", "available days; max 30-min counter/dominant excursion"),
    ("largest initial move then opposite open cross", "available days with a 60-min open cross; max ticks travelled "
                                                      "in the first direction before the first cross"),
    ("most open-price crossings", "available days; max 60-min open-cross count"),
    ("fastest outside-value re-entry", "paired days opening outside prior value; min time from open to first entry"),
)


def inspection_set(rows: list[OpeningRow]) -> list[tuple[str, OpeningRow | None, str]]:
    rows = sorted(rows, key=lambda r: (r.trading_date, r.dataset_id))
    avail = [r for r in rows if r.available]
    paired = [r for r in rows if r.paired]

    def pick(cands, key):
        best = None
        for r in cands:  # strict improvement only: ties keep the earlier date
            if best is None or key(r) > key(best):
                best = r
        return best

    out = []
    above = [r for r in paired if r.facts.range_location.value == "ABOVE_PRIOR_RANGE"]
    r = pick(above, lambda r: r.facts.open_vs_prior_high_ticks)
    out.append((SELECTION_RULES[0][0], r, f"{r.facts.open_vs_prior_high_ticks} ticks above prior high" if r else ""))
    below = [r for r in paired if r.facts.range_location.value == "BELOW_PRIOR_RANGE"]
    r = pick(below, lambda r: -r.facts.open_vs_prior_low_ticks)
    out.append((SELECTION_RULES[1][0], r, f"{-r.facts.open_vs_prior_low_ticks} ticks below prior low" if r else ""))
    defined = [r for r in avail if r.facts.session.window(30).counter_to_dominant is not None]
    r = pick(defined, lambda r: (-r.facts.session.window(30).counter_to_dominant,
                                 r.facts.session.window(30).larger_excursion_ticks))
    out.append((SELECTION_RULES[2][0], r, _w30(r)))
    r = pick(defined, lambda r: r.facts.session.window(30).counter_to_dominant)
    out.append((SELECTION_RULES[3][0], r, _w30(r)))
    moved = [r for r in avail if initial_move_before_cross(r.facts) is not None]
    r = pick(moved, lambda r: initial_move_before_cross(r.facts)[1])
    if r:
        side, ticks, at = initial_move_before_cross(r.facts)
        why = f"{ticks} ticks {side.value} before the first open cross at {at:%H:%M:%S}Z"
    out.append((SELECTION_RULES[4][0], r, why if r else ""))
    r = pick(avail, lambda r: r.facts.session.window(60).open_cross_count)
    out.append((SELECTION_RULES[5][0], r, f"{r.facts.session.window(60).open_cross_count} crossings in 60 min" if r else ""))
    entered = [r for r in paired if not r.facts.value_zone.open_inside and r.facts.value_zone.first_entry_utc]
    r = pick(entered, lambda r: -_entry_delay(r).total_seconds())
    out.append((SELECTION_RULES[6][0], r, f"first entry {_entry_delay(r)} after the open print" if r else ""))
    return out


def _entry_delay(r: OpeningRow) -> timedelta:
    return r.facts.value_zone.first_entry_utc - r.facts.session.cash_open.timestamp_utc


def _w30(r: OpeningRow | None) -> str:
    if r is None:
        return ""
    w = r.facts.session.window(30)
    return (f"30 min up {w.excursion_up_ticks} / down {w.excursion_down_ticks} ticks, counter/dominant "
            f"{w.counter_to_dominant.quantize(Decimal('0.0001'))}")


def _d(value, places: str = "0.0001") -> str:
    if value is None:
        return "—"
    return str(value.quantize(Decimal(places))) if isinstance(value, Decimal) else str(value)


def _table(head: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)] + ["| " + " | ".join(r) + " |" for r in rows]


def _hms(ts, origin) -> str:
    return "—" if ts is None else f"+{int((ts - origin).total_seconds())}s"


def render_study_report(rows: list[OpeningRow], report_paths: dict[str, str]) -> str:
    rows = sorted(rows, key=lambda r: (r.trading_date, r.dataset_id))
    lines = ["# Opening-auction fact study (0Y-F)", "",
             "Facts only. No opening type is named; no threshold is applied. Times are seconds after the "
             "open print. Excursions are ticks from the cash open (up / down).", "",
             "## Pairing and quality", ""]
    t = []
    for r in rows:
        f, p, q = r.facts, r.facts.prior, r.facts.session.quality
        t.append([r.trading_date, r.dataset_id[:8], str(p.expected_prior_date), f.outcome.value,
                  "—" if p.same_contract is None else ("yes" if p.same_contract else "no"), q.grade.value,
                  "INCOMPLETE" if f.outcome is ContextOutcome.PRIOR_PROFILE_INCOMPLETE
                  else p.quality_grade.value if p.quality_grade else "—"])
    lines += _table(["date", "dataset", "prior trading date", "context", "same contract", "opening quality",
                     "prior quality"], t)
    lines += ["", "## Opening facts (days with an available cash open)", ""]
    t = []
    for r in rows:
        if not r.available:
            continue
        f, s = r.facts, r.facts.session
        w5, w15, w30, w60 = (s.window(m) for m in (5, 15, 30, 60))
        o = s.cash_open.timestamp_utc
        v = f.value_zone
        if v is None:
            value_facts = "—"
        elif v.open_inside:
            value_facts = f"inside; exit↑ {_hms(v.first_exit_above_utc, o)} exit↓ {_hms(v.first_exit_below_utc, o)}"
        else:
            value_facts = f"outside; entry {_hms(v.first_entry_utc, o)}"
        t.append([
            r.trading_date, "yes" if f.prior.same_contract else ("no" if f.prior.same_contract is False else "—"),
            str(s.cash_open.price), f"{s.cash_open.delay.total_seconds():.3f}s",
            f.range_location.value if f.range_location else "—", f.value_location.value if f.value_location else "—",
            _d(f.gap_ticks),
            f"{w5.excursion_up_ticks}/{w5.excursion_down_ticks}", f"{w15.excursion_up_ticks}/{w15.excursion_down_ticks}",
            f"{w30.excursion_up_ticks}/{w30.excursion_down_ticks}", f"{w30.open_cross_count}/{w60.open_cross_count}",
            value_facts, _d(s.early_tpo.ab_overlap_ratio), s.quality.grade.value])
    lines += _table(["date", "same contract", "open", "delay", "vs prior range", "vs prior value", "gap ticks",
                     "5m up/dn", "15m up/dn", "30m up/dn", "open crosses 30m/60m", "prior value (full window)",
                     "A/B overlap", "quality"], t)
    lines += ["", "## Mechanical inspection set", "",
              "Rules were fixed in code (`SELECTION_RULES`) before the study ran; ties go to the earlier date.", ""]
    t = []
    for (name, rule), (_, r, why) in zip(SELECTION_RULES, inspection_set(rows)):
        t.append([name, rule, r.trading_date if r else "none in corpus", why or "—",
                  f"`{report_paths[r.dataset_id]}`" if r else "—"])
    lines += _table(["slot", "rule", "day", "fact", "report"], t)
    return "\n".join(lines) + "\n"
