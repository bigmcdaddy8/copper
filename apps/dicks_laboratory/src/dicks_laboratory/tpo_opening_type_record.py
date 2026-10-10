"""Prospective-validation records for the frozen OPENING_TYPE_V1 policy (0Y-H).

One JSON record per profiled trading date preserves, without changing any policy:
  - the OPENING_AUCTION_FACTS_V1 facts, the OVERNIGHT_CONTEXT_V1 facts and the
    OPENING_PATH_FACTS_V1 facts (tape-derived `path` arrays and the overnight
    volume-at-tick table are omitted; they are reproducible from the recorded
    dataset id and database sha256),
  - the OpeningTypeClassification,
  - the sha256 of the policy module and of the fact modules it reads,
  - the cohort: DEVELOPMENT (on or before the freeze date: the inspected
    corpus), VALIDATION (an unseen date after the freeze, scored by the
    unmodified frozen policy), or POLICY_MODIFIED (the policy source no longer
    matches the freeze; never counted as validation).

Aggregation counts candidates per cohort. It never tunes or re-scores anything.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from collections import Counter
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum, StrEnum
from pathlib import Path

from dicks_laboratory import tpo_opening, tpo_opening_path, tpo_opening_type, tpo_overnight
from dicks_laboratory.tpo_opening_type import CandidateResult, ClassificationStatus, OpeningTypeClassification

RECORD_SCHEMA = "OPENING_TYPE_V1_RECORD_1"
# The pre-registration freeze (0Y-H). Changing tpo_opening_type.py or the policy document requires OPENING_TYPE_V2.
OPENING_TYPE_V1_FROZEN_ON = date(2026, 10, 9)
OPENING_TYPE_V1_SOURCE_SHA256 = "2b7b571c0b813bd267d8f2591336f4fe2877a8f6c4258cb0427f6e665c798d7c"
OPENING_TYPE_V1_POLICY_DOC = "docs/dicks_laboratory/OPENING_TYPE_V1_POLICY.md"
OPENING_TYPE_V1_POLICY_DOC_SHA256 = "1a952478c7ef892de8933a2ad15307ceb2089cadf74a1cfdcd6f3e42ba5af2ec"
_OMITTED_FIELDS = frozenset({"path", "volume_at_tick", "facts"})


class Cohort(StrEnum):
    DEVELOPMENT = "DEVELOPMENT"  # trading date on/before the freeze: descriptive evidence only
    VALIDATION = "VALIDATION"  # unseen date after the freeze, frozen policy unchanged
    POLICY_MODIFIED = "POLICY_MODIFIED"  # source differs from the freeze: not validation evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def policy_source_sha256() -> str:
    return _sha256(Path(tpo_opening_type.__file__))


def fact_source_sha256() -> dict[str, str]:
    """The fact modules the policy reads; recorded for audit (they are not part of the frozen V1 hash)."""
    return {Path(m.__file__).name: _sha256(Path(m.__file__)) for m in (tpo_opening, tpo_opening_path, tpo_overnight)}


def cohort_for(trading_date: date, source_sha256: str) -> Cohort:
    if source_sha256 != OPENING_TYPE_V1_SOURCE_SHA256:
        return Cohort.POLICY_MODIFIED
    return Cohort.VALIDATION if trading_date > OPENING_TYPE_V1_FROZEN_ON else Cohort.DEVELOPMENT


def to_jsonable(obj):
    """Deterministic JSON-safe form: Decimal/timedelta as strings, datetimes ISO, enums by value."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)
                if f.name not in _OMITTED_FIELDS}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return f"{obj.total_seconds():.6f}"
    if isinstance(obj, tuple | list):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    return obj


def build_record(trading_date: date, dataset_id: str, contract: str, database_sha256: str | None,
                 classification: OpeningTypeClassification) -> dict:
    source = policy_source_sha256()
    facts = classification.facts
    return {
        "record_schema": RECORD_SCHEMA,
        "trading_date": trading_date.isoformat(),
        "dataset_id": dataset_id,
        "contract": contract,
        "database_sha256": database_sha256,
        "policy_id": classification.policy_id,
        "policy_version": classification.policy_version,
        "policy_constants": dict(classification.policy_constants),
        "policy_source_sha256": source,
        "policy_frozen_sha256": OPENING_TYPE_V1_SOURCE_SHA256,
        "policy_frozen_on": OPENING_TYPE_V1_FROZEN_ON.isoformat(),
        "fact_source_sha256": fact_source_sha256(),
        "cohort": cohort_for(trading_date, source).value,
        "opening_auction_facts": to_jsonable(facts.opening),
        "overnight_context": to_jsonable(facts.overnight),
        "opening_path_facts": to_jsonable(dataclasses.replace(facts, opening=None, overnight=None)),
        "classification": to_jsonable(classification),
    }


def write_record(out_dir: Path, record: dict) -> Path:
    path = out_dir / f"{record['trading_date']}_{record['dataset_id'][:8]}.json"
    path.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    return path


def load_records(paths) -> list[dict]:
    out = []
    for p in paths:
        p = Path(p)
        files = sorted(p.glob("*.json")) if p.is_dir() else [p]
        out += [json.loads(f.read_text()) for f in files]
    return sorted(out, key=lambda r: (r["trading_date"], r["dataset_id"]))


# --- descriptive aggregation -------------------------------------------------------------------

def _candidate(record: dict, name: str) -> dict:
    return next(c for c in record["classification"]["candidates"] if c["type"] == name)


def _matched(record: dict) -> list[dict]:
    return [c for c in record["classification"]["candidates"] if c["result"] == CandidateResult.CANDIDATE.value]


def _yes(record: dict, name: str) -> str:
    c = _candidate(record, name)
    if c["result"] == CandidateResult.CANDIDATE.value:
        return "YES" + (f" {c['direction']}" if c["direction"] else "")
    return {"NOT_CANDIDATE": "no", "NOT_CLASSIFIED": "n/c", "NOT_APPLICABLE": "--"}.get(c["result"], c["result"])


def render_audit(records: list[dict], title: str) -> str:
    """Counts and a per-day table. Labelled by cohort; DEVELOPMENT rows are never validation."""
    lines = [f"# {title}", "",
             "OPENING_TYPE_V1 is a pre-registered Laboratory candidate policy, not an industry-standard mechanical "
             "definition. Candidates are descriptive taxonomy, not signals.", ""]
    by_cohort = Counter(r["cohort"] for r in records)
    lines += ["Cohorts: " + ", ".join(f"{k} {v}" for k, v in sorted(by_cohort.items())) + ".",
              "DEVELOPMENT = inspected before or at the freeze: **NOT VALIDATION**. Only VALIDATION records (unseen "
              "dates after the freeze, scored by the unmodified frozen source) are validation evidence.", ""]
    for cohort in sorted(by_cohort):
        rows = [r for r in records if r["cohort"] == cohort]
        lines += [f"## Counts — {cohort}" + (" (NOT VALIDATION)" if cohort != Cohort.VALIDATION.value else ""), ""]
        classified = [r for r in rows if r["classification"]["status"] == ClassificationStatus.CLASSIFIED.value]
        types = Counter(c["type"] + (f" {c['direction']}" if c["direction"] else "") for r in rows for c in _matched(r))
        combos = Counter(" + ".join(c["type"] for c in _matched(r)) for r in classified if len(_matched(r)) > 1)
        qualified = sum(1 for r in rows for c in _matched(r) if c["quality"] == "QUALITY_QUALIFIED")
        lines += ["| Item | Count |", "|---|---|",
                  f"| profiled days | {len(rows)} |",
                  f"| NOT_CLASSIFIED days | {len(rows) - len(classified)} |",
                  f"| classified days with no candidate | {sum(1 for r in classified if not _matched(r))} |",
                  f"| classified days with one candidate | {sum(1 for r in classified if len(_matched(r)) == 1)} |",
                  f"| classified days with several candidates | {sum(1 for r in classified if len(_matched(r)) > 1)} |",
                  f"| matched candidates that are QUALITY_QUALIFIED | {qualified} |"]
        lines += [f"| candidate {k} | {v} |" for k, v in sorted(types.items())]
        lines += [f"| overlap {k} | {v} |" for k, v in sorted(combos.items())]
        lines.append("")
    lines += ["## Per-day candidate table", "",
              "| Date | Dataset | Cohort | Opening q. | Prior | Overnight q. | Open vs prior range / value | "
              "Open Drive | OAIR | OAOR | OA (no prior) | Open Test Drive | TD reference | Matched | "
              "Qualified candidates |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in records:
        c = r["classification"]
        q = c["quality"]
        prior = q["prior_day_outcome"] + (f" / {q['prior_day_quality']}" if q["prior_day_quality"] else "")
        st = c["strength"]
        loc = f"{st['range_location']} / {st['value_location']}" if st and st["range_location"] else "--"
        if c["status"] == ClassificationStatus.NOT_CLASSIFIED.value:
            lines.append(f"| {r['trading_date']} | {r['dataset_id'][:8]} | {r['cohort']} | {q['current_open']} | "
                         f"{prior} | {q['overnight'] or 'NOT_BUILT'} | {loc} | NOT_CLASSIFIED | | | | | | 0 | |")
            continue
        td = _candidate(r, "OPEN_TEST_DRIVE")
        ref = (td["evidence"] or {}).get("reference") if td["evidence"] else None
        matched = _matched(r)
        qual = ", ".join(m["type"] for m in matched if m["quality"] == "QUALITY_QUALIFIED") or "--"
        lines.append(f"| {r['trading_date']} | {r['dataset_id'][:8]} | {r['cohort']} | {q['current_open']} | {prior} | "
                     f"{q['overnight'] or 'NOT_BUILT'} | {loc} | {_yes(r, 'OPEN_DRIVE')} | "
                     f"{_yes(r, 'OPEN_AUCTION_IN_RANGE')} | {_yes(r, 'OPEN_AUCTION_OUT_OF_RANGE')} | "
                     f"{_yes(r, 'OPEN_AUCTION')} | {_yes(r, 'OPEN_TEST_DRIVE')} | {ref or '--'} | {len(matched)} | "
                     f"{qual} |")
    lines += ["", "Legend: YES = CANDIDATE; no = NOT_CANDIDATE; n/c = NOT_CLASSIFIED; -- = NOT_APPLICABLE. "
              "OPEN_REJECTION_REVERSE is DEFERRED (REFERENCE_DEFINITION_CONFLICT) on every day.", ""]
    return "\n".join(lines)
