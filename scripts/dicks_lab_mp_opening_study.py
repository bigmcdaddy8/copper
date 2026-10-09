"""Opening-auction fact study over a corpus of Laboratory datasets (0Y-F).

Read-only and offline. Analyses every database once, pairs each profiled day
with the dataset for its prior trading date (never the previous calendar day),
and writes per-day fact reports plus `opening_study.md`. No opening type is named.
"""
from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, opening_auction_facts
from dicks_laboratory.tpo_opening import render_early_matrix, render_opening_facts
from dicks_laboratory.tpo_opening_study import OpeningRow, render_study_report

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
        facts = opening_auction_facts(result, results, closure_dates)
        if facts is None:
            continue
        row = OpeningRow(result.trading_date.isoformat(), str(result.dataset_id), result.instrument.canonical_id, facts)
        rows.append(row)
        name = f"reports/{row.trading_date}_{row.dataset_id[:8]}.txt"
        paths[row.dataset_id] = name
        body = render_opening_facts(facts) + render_early_matrix(facts, result.profile)
        (out_dir / name).write_text(f"{row.trading_date}  {row.dataset_id}  {row.contract}\n\n"
                                    + "\n".join(body).rstrip("\n") + "\n")
        typer.echo(f"{row.trading_date} {row.dataset_id[:8]} {facts.outcome.value} {facts.session.quality.grade.value}")
    (out_dir / "opening_study.md").write_text(render_study_report(rows, paths))
    fact_seconds = time.monotonic() - t1
    (out_dir / "timings.tsv").write_text("trading_date\tdataset\tseconds\n" + "\n".join(timings)
                                         + f"\nLOAD_TOTAL\t\t{load_seconds:.1f}\nOPENING_FACTS_TOTAL\t\t{fact_seconds:.3f}\n")
    typer.echo(f"opening_study.md written ({len(rows)} profiled days; load {load_seconds:.1f}s, "
               f"opening facts {fact_seconds:.3f}s)")


if __name__ == "__main__":
    app()
