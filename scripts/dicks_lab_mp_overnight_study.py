"""Overnight-context and multi-scale opening study over a corpus of Laboratory datasets (0Y-G).

Read-only and offline. Analyses every database once, pairs each profiled day with the
dataset for its prior trading date (never the previous calendar day), and writes per-day
reports plus `overnight_study.md`. No opening type or inventory label is named.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, opening_path_facts
from dicks_laboratory.tpo_opening_path import render_opening_path
from dicks_laboratory.tpo_overnight import render_overnight_facts
from dicks_laboratory.tpo_overnight_study import OvernightRow, render_study_report

app = typer.Typer(add_completion=False)


@app.command()
def run(
    out_dir: Path = typer.Argument(..., help="Output directory for reports and the study table."),
    databases: list[Path] = typer.Argument(..., help="Durable Laboratory SQLite datasets (one trading date each)."),
    closures: list[str] = typer.Option([], "--closure", help="YYYY-MM-DD full CME closure (repeatable)."),
) -> None:
    """Never modifies a database."""
    started = time.monotonic()
    results, timings = [], []
    for path in databases:
        t0 = time.monotonic()
        try:
            store = open_dataset_store(path)
            try:
                results.append(analyze_tpo_dataset(store, resolve_dataset_id(store, None)))
            finally:
                store.close()
        except (LaboratoryAnalysisError, ValueError) as exc:
            typer.echo(f"FAILED {path.name}: {exc}", err=True)
            continue
        timings.append(f"{results[-1].trading_date}\t{str(results[-1].dataset_id)[:8]}\t{time.monotonic() - t0:.1f}")
    load_seconds = time.monotonic() - started
    closure_dates = frozenset(date.fromisoformat(c) for c in closures)
    t1 = time.monotonic()
    rows, paths = [], {}
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    for result in results:
        facts = opening_path_facts(result, results, closure_dates)
        if facts is None:
            continue
        row = OvernightRow(result.trading_date.isoformat(), str(result.dataset_id), result.instrument.canonical_id, facts)
        rows.append(row)
        name = f"reports/{row.trading_date}_{row.dataset_id[:8]}.txt"
        paths[row.dataset_id] = name
        body = (render_overnight_facts(facts.overnight) if facts.overnight is not None else []) + render_opening_path(facts)
        (out_dir / name).write_text(f"{row.trading_date}  {row.dataset_id}  {row.contract}\n\n"
                                    + "\n".join(body).rstrip("\n") + "\n")
        q = facts.quality
        typer.echo(f"{row.trading_date} {row.dataset_id[:8]} open {q.current_open.value} prior "
                   f"{q.prior_day_outcome.value} overnight {q.overnight.value if q.overnight else '-'}")
    (out_dir / "overnight_study.md").write_text(render_study_report(rows, paths))
    fact_seconds = time.monotonic() - t1
    (out_dir / "timings.tsv").write_text("trading_date\tdataset\tseconds\n" + "\n".join(timings)
                                         + f"\nLOAD_TOTAL\t\t{load_seconds:.1f}\nOVERNIGHT_AND_PATH_FACTS_TOTAL\t\t"
                                         f"{fact_seconds:.3f}\n")
    typer.echo(f"overnight_study.md written ({len(rows)} profiled days; load {load_seconds:.1f}s, "
               f"overnight/path facts {fact_seconds:.3f}s)")


if __name__ == "__main__":
    app()
