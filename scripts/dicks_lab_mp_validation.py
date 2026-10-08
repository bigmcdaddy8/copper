"""Blind multi-day validation of the frozen Market Profile day-type candidates (0Y-D).

Read-only and offline. Two separate commands so the policy cannot move between them:

  run      classify every database with the frozen policy; write raw reports,
           `records.jsonl` and its sha256 (the frozen blind run), and timings
  analyze  verify the frozen records' sha256, then write `validation_report.md`
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, render_tpo_report
from dicks_laboratory.tpo_validation import day_record, record_from_json, record_to_json, render_validation_report

app = typer.Typer(add_completion=False)


@app.command()
def run(
    out_dir: Path = typer.Argument(..., help="Output directory for reports, records and timings."),
    databases: list[Path] = typer.Argument(..., help="Durable Laboratory SQLite datasets (one trading date each)."),
) -> None:
    """Apply the frozen policy blindly to every database; never modifies a database."""
    reports = out_dir / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    records, timings, failures = [], [], []
    started = time.monotonic()
    for path in databases:
        t0 = time.monotonic()
        try:
            store = open_dataset_store(path)
            try:
                result = analyze_tpo_dataset(store, resolve_dataset_id(store, None))
            finally:
                store.close()
        except (LaboratoryAnalysisError, ValueError) as exc:
            failures.append(f"{path.name}\t{exc}")
            typer.echo(f"FAILED {path.name}: {exc}", err=True)
            continue
        record = day_record(result)
        name = f"reports/{record.trading_date}_{record.dataset_id[:8]}.txt"
        (out_dir / name).write_text(render_tpo_report(
            result, show_matrix=True, show_structure=True, show_day_structure=True) + "\n")
        records.append(record)
        timings.append(f"{record.trading_date}\t{record.dataset_id[:8]}\t{time.monotonic() - t0:.1f}")
        typer.echo(f"{record.trading_date} {record.dataset_id[:8]} {record.eligibility} {record.label}")
    records.sort(key=lambda r: (r.trading_date, r.dataset_id))
    body = "".join(record_to_json(r) + "\n" for r in records)
    (out_dir / "records.jsonl").write_text(body)
    (out_dir / "records.sha256").write_text(hashlib.sha256(body.encode()).hexdigest() + "  records.jsonl\n")
    (out_dir / "timings.tsv").write_text("trading_date\tdataset\tseconds\n" + "\n".join(timings)
                                         + f"\nTOTAL\t\t{time.monotonic() - started:.1f}\n")
    if failures:
        (out_dir / "failures.tsv").write_text("\n".join(failures) + "\n")
    if not records:
        raise typer.Exit(code=1)


@app.command()
def analyze(out_dir: Path = typer.Argument(..., help="Directory written by `run`.")) -> None:
    """Report over the frozen records only; refuses records whose sha256 changed."""
    body = (out_dir / "records.jsonl").read_text()
    digest = hashlib.sha256(body.encode()).hexdigest()
    expected = (out_dir / "records.sha256").read_text().split()[0]
    if digest != expected:
        typer.echo(f"records.jsonl sha256 {digest} != frozen {expected}", err=True)
        raise typer.Exit(code=2)
    records = [record_from_json(line) for line in body.splitlines() if line]
    paths = {r.dataset_id: f"reports/{r.trading_date}_{r.dataset_id[:8]}.txt" for r in records}
    (out_dir / "validation_report.md").write_text(render_validation_report(records, digest, paths).rstrip("\n") + "\n")
    typer.echo(f"validation_report.md written ({len(records)} records, sha256 {digest[:12]})")


if __name__ == "__main__":
    app()
