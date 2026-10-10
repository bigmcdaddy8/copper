"""OPENING_TYPE_V1 records, reports and descriptive audit over Laboratory datasets (0Y-H).

Read-only and offline. `record` analyses every database once, pairs each profiled day
with the dataset for its prior trading date (never the previous calendar day), and
writes one JSON record, one report per day, and `opening_type_audit.md`. The same
command is the prospective-validation harness for dates collected after the freeze.
`summarize` aggregates existing records by cohort. Nothing is scheduled and no
policy is changed.
"""
from __future__ import annotations

import hashlib
import time
from datetime import date
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, opening_type_classification
from dicks_laboratory.tpo_opening_type import render_opening_types
from dicks_laboratory.tpo_opening_type_record import build_record, load_records, render_audit, write_record

app = typer.Typer(add_completion=False)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@app.command()
def record(
    out_dir: Path = typer.Argument(..., help="Output directory for records, reports and the audit table."),
    databases: list[Path] = typer.Argument(..., help="Durable Laboratory SQLite datasets (one trading date each)."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
) -> None:
    """Classify every profiled day with the frozen OPENING_TYPE_V1 policy. Never modifies a database."""
    started = time.monotonic()
    results, hashes, timings = [], {}, []
    for path in databases:
        t0 = time.monotonic()
        try:
            store = open_dataset_store(path)
            try:
                result = analyze_tpo_dataset(store, resolve_dataset_id(store, None))
            finally:
                store.close()
        except (LaboratoryAnalysisError, ValueError) as exc:
            typer.echo(f"FAILED {path.name}: {exc}", err=True)
            continue
        results.append(result)
        hashes[str(result.dataset_id)] = _sha256(path)
        timings.append(f"{result.trading_date}\t{str(result.dataset_id)[:8]}\t{time.monotonic() - t0:.1f}")
    load_seconds = time.monotonic() - started
    closure_dates = frozenset(date.fromisoformat(c) for c in closures)
    t1 = time.monotonic()
    for sub in ("records", "reports"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    records = []
    for result in results:
        c = opening_type_classification(result, results, closure_dates)
        if c is None:
            continue
        dataset = str(result.dataset_id)
        rec = build_record(result.trading_date, dataset, result.instrument.canonical_id, hashes[dataset], c)
        write_record(out_dir / "records", rec)
        records.append(rec)
        (out_dir / "reports" / f"{rec['trading_date']}_{dataset[:8]}.txt").write_text(
            f"{rec['trading_date']}  {dataset}  {rec['contract']}  cohort {rec['cohort']}\n\n"
            + "\n".join(render_opening_types(c)).rstrip("\n") + "\n")
        typer.echo(f"{rec['trading_date']} {dataset[:8]} {rec['cohort']} {c.status.value} matched "
                   f"{[m.type.value + (' ' + m.direction.value if m.direction else '') for m in c.matched]}")
    records.sort(key=lambda r: (r["trading_date"], r["dataset_id"]))
    (out_dir / "opening_type_audit.md").write_text(render_audit(records, "OPENING_TYPE_V1 descriptive audit"))
    seconds = time.monotonic() - t1
    (out_dir / "timings.tsv").write_text("trading_date\tdataset\tseconds\n" + "\n".join(timings)
                                         + f"\nLOAD_TOTAL\t\t{load_seconds:.1f}\nCLASSIFY_AND_RECORD_TOTAL\t\t"
                                         f"{seconds:.3f}\n")
    typer.echo(f"opening_type_audit.md written ({len(records)} profiled days; load {load_seconds:.1f}s, "
               f"classify/record {seconds:.3f}s)")


@app.command()
def summarize(
    out_file: Path = typer.Argument(..., help="Markdown file to write."),
    records: list[Path] = typer.Argument(..., help="Record JSON files or directories of them."),
) -> None:
    """Aggregate existing records by cohort (descriptive counts; no policy change)."""
    out_file.write_text(render_audit(load_records(records), "OPENING_TYPE_V1 record summary"))
    typer.echo(f"{out_file} written")


if __name__ == "__main__":
    app()
