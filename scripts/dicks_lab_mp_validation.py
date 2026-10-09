"""Blind multi-day validation of the frozen Market Profile day-type candidates (0Y-D).

Read-only and offline. Two separate commands so the policy cannot move between them:

  run      classify every database with the frozen policy; write raw reports,
           `records.jsonl` and its sha256 (the frozen blind run), and timings
  analyze  verify the frozen records' sha256, then write `validation_report.md`
  strength (0Y-E) re-analyse the same databases, require each rebuilt V1 record to equal
           the frozen one byte-for-byte, and report DAY_STRUCTURE_STRENGTH_V1 beside
           the frozen labels in a separate output directory (the frozen run is read only)
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import typer

from dicks_laboratory.analysis import LaboratoryAnalysisError, open_dataset_store, resolve_dataset_id
from dicks_laboratory.tpo_analysis import analyze_tpo_dataset, render_day_strength, render_tpo_report
from dicks_laboratory.tpo_day_strength import strength_to_json
from dicks_laboratory.tpo_strength_corpus import render_strength_corpus_report
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


def _frozen_body(frozen_dir: Path) -> tuple[str, str]:
    body = (frozen_dir / "records.jsonl").read_text()
    digest = hashlib.sha256(body.encode()).hexdigest()
    expected = (frozen_dir / "records.sha256").read_text().split()[0]
    if digest != expected:
        typer.echo(f"records.jsonl sha256 {digest} != frozen {expected}", err=True)
        raise typer.Exit(code=2)
    return body, digest


@app.command()
def analyze(out_dir: Path = typer.Argument(..., help="Directory written by `run`.")) -> None:
    """Report over the frozen records only; refuses records whose sha256 changed."""
    body, digest = _frozen_body(out_dir)
    records = [record_from_json(line) for line in body.splitlines() if line]
    paths = {r.dataset_id: f"reports/{r.trading_date}_{r.dataset_id[:8]}.txt" for r in records}
    (out_dir / "validation_report.md").write_text(render_validation_report(records, digest, paths).rstrip("\n") + "\n")
    typer.echo(f"validation_report.md written ({len(records)} records, sha256 {digest[:12]})")


@app.command()
def strength(
    frozen_dir: Path = typer.Argument(..., help="Frozen 0Y-D `run` directory (read only)."),
    out_dir: Path = typer.Argument(..., help="New output directory for the derived strength report."),
    databases: list[Path] = typer.Argument(..., help="The same databases the frozen run classified."),
) -> None:
    """Strength facts beside the frozen V1 labels; exits 3 if any V1 record fails to reproduce."""
    body, digest = _frozen_body(frozen_dir)
    frozen = {record_from_json(line).dataset_id: line for line in body.splitlines() if line}
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)
    entries, strength_lines, repro, paths = [], [], [], {}
    started = time.monotonic()
    for path in databases:
        store = open_dataset_store(path)
        try:
            result = analyze_tpo_dataset(store, resolve_dataset_id(store, None))
        finally:
            store.close()
        line = record_to_json(day_record(result))
        record = record_from_json(line)
        same = frozen.get(record.dataset_id) == line
        repro.append(f"{record.trading_date}\t{record.dataset_id}\t{'IDENTICAL' if same else 'DIFFERENT'}")
        typer.echo(f"{record.trading_date} {record.dataset_id[:8]} frozen-record {'IDENTICAL' if same else 'DIFFERENT'}")
        s = result.day_strength
        entries.append((record, s))
        if s is not None:
            strength_lines.append(json.dumps({"dataset_id": record.dataset_id, "trading_date": record.trading_date,
                                              "strength": json.loads(strength_to_json(s))}, sort_keys=True))
            name = f"reports/{record.trading_date}_{record.dataset_id[:8]}.txt"
            paths[record.dataset_id] = name
            (out_dir / name).write_text(
                f"{record.trading_date}  {record.dataset_id}  {record.contract}\n\n"
                + "\n".join(render_day_strength(s)).rstrip("\n") + "\n")
    strength_body = "".join(sorted(line + "\n" for line in strength_lines))
    (out_dir / "strength_records.jsonl").write_text(strength_body)
    (out_dir / "strength_records.sha256").write_text(
        hashlib.sha256(strength_body.encode()).hexdigest() + "  strength_records.jsonl\n")
    (out_dir / "reproduction.tsv").write_text("trading_date\tdataset_id\tv1_record_vs_frozen\n"
                                              + "\n".join(sorted(repro)) + "\n")
    reproduced = sum(1 for r in repro if r.endswith("IDENTICAL"))
    (out_dir / "strength_report.md").write_text(render_strength_corpus_report(entries, digest, reproduced, paths))
    typer.echo(f"strength_report.md written ({len(entries)} datasets, {reproduced} reproduced, "
               f"{time.monotonic() - started:.1f}s)")
    if reproduced != len(entries):
        raise typer.Exit(code=3)


if __name__ == "__main__":
    app()
