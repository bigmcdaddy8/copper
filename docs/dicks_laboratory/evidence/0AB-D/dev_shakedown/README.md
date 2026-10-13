# 0AB-D development-corpus shakedown (DEVELOPMENT / DESCRIPTIVE — not validation)

The harness pre-registered in
[DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md](../../../DRYSDALE_PROSPECTIVE_VALIDATION_PLAN.md) was exercised end to end on
the already-inspected development corpus, 2026-09-29 … 2026-10-02 (the four 0AB-B / 0AB-C dates). Its purpose
was to show that the machinery runs correctly on real data. It was not used to choose any threshold: every
threshold in the plan came from the PO's 0AB-D brief. **No campaign date (2026-10-12 … 2026-11-06) was opened.**

## Code that ran

- **Frozen V1 and quality code:** analysis HEAD `d3e1ee2`.
  - `drysdale.py` sha256 `51948f80…165af` (byte-identical to the 0AB-B freeze).
  - `drysdale_quality.py` sha256 `1d54d63e…c8cc8d`.
- **Validation code:** a pinned byte copy of `drysdale_validation.py` (sha256 `8b5a51a7…d6b554`) and of the CLI (sha256 `b14c9675…ee8cbe`), loaded by `harness/run_pinned.py` so that working-tree edits could not reach a running date.
  - The CLI copy is byte-identical to the committed CLI.
  - The committed module differs from the pinned copy in `cohort_summary` / `render_report` only. Those two functions now label a run on non-cohort dates as such (`registered_cohort`, "NOT the registered validation cohort"). `date_record` is unchanged.
  - The cohort step was rerun with the committed module: `dev_cohort_summary.json` and `dev_readout.md`.

## Runs (one heavy job at a time)

| Run | Wall time | Peak RSS | Exit | Result |
|---|---|---|---|---|
| 2026-09-29 | 14:51 | 3.39 GB | 0 | ELIGIBLE, 15 candidates, determinism identical |
| 2026-09-30 | 23:29 | 3.95 GB | 0 | ELIGIBLE, 21 candidates, determinism identical |
| 2026-10-01 | 29:02 | 4.95 GB | 0 | ELIGIBLE, 15 candidates, determinism identical |
| 2026-10-02 | 17:55 | 4.49 GB | 0 | ELIGIBLE, 15 candidates, determinism identical |
| 2026-09-29 rerun (separate process) | 13:07 | 3.41 GB | 0 | record **byte-identical** (`record_sha256` `0b3dad52…`) |
| 2026-10-02 rerun (separate process) | 17:51 | 4.49 GB | 0 | record **byte-identical** (`record_sha256` `f5dca28f…`) |

**Interruptions, recorded rather than hidden.**

1. The first attempt was stopped by me after 4 minutes, to fix the harness. The fixes were: a KeyError in the first-known search, globally time-ordered probes, and the HARNESS_ERROR record.
2. The second attempt completed 2026-09-29 and 2026-09-30, then was stopped during 2026-10-01 by Claude Code's background memory-pressure handling. The workstation (11 GB) also had desktop applications open. Linux OOM was not involved.
3. On the PO's instruction the remaining dates were then run one at a time, with memory allowed to recover between runs. They completed. The pressure-reap override (`CLAUDE_CODE_DISABLE_BG_SHELL_PRESSURE_REAP`) was **not** used.
4. One relaunch of 2026-10-01 was detached (nohup) by mistake. It was stopped by PID within a minute and relaunched as a tracked task (noted in `run.log`).
5. The 2026-09-29 and 2026-09-30 records come from the second attempt and were not recomputed, except for the separate-process rerun of the first date.

Performance is recorded as a backlog finding ([BACKLOG.md](../../../BACKLOG.md)); nothing was optimized in 0AB-D.

## What the shakedown shows

**Implementation validity**

- **Determinism:** every date's cached/resumed analysis equals the cold rebuild (`drysdale_sha256` and quality-audit sha256). The first and last dates rerun in separate processes give byte-identical records.
- **Sequence and semantic checks:** 0 sequence violations and 0 semantic violations across 66 candidates. This covers H-FADE-1/2, H-RTV-1/2, H-BOUNCE-1/2 and the PDC structure.
- **Knowledge time:** 0 lookahead defects; 0 unresolved first-known times.
- **Absent / present:** every candidate is absent 1 µs before its completing bar ends and present at the first-known time.
- **Withdrawn or revised:** no candidate was withdrawn or revised by later knowledge (hourly sweep).
- **Database hashes:** unchanged (`db_sha_before.txt` = `db_sha_after.txt`).

**Receipt delay**

- **Observed:** 0 for all 66 development candidates.
- **Change points:** some completing bars did have later-received earlier-market records (2 and 82 change points), but V1's result at the completion instant was already final.
- **Not a general rule:** this does not mean receipt delay is always zero.
  - The fixture `test_receipt_delay_is_measured_from_what_was_knowable` proves a non-zero case (7.000001 s).
  - A raw-tape spot check on 2026-09-29 is supporting evidence only. It found a median receipt lag of about 15 ms, a 99th percentile of about 0.10 s, and 24 of 400,000 sampled trades received after their 5-minute bar had ended.

**Quality accounting — identical to the 0AB-C audit**

```text
total candidates             66
ELIGIBLE_UNQUALIFIED         0
ELIGIBLE_QUALITY_QUALIFIED   65
  - BOUNDARY_PROVENANCE      64
  - BOUNDARY_LOCAL_EVIDENCE  1
  - UPSTREAM_REFERENCE       3
NOT_ELIGIBLE                 1
```

Every ELIGIBLE_QUALITY_QUALIFIED candidate is counted exactly once in one of these combinations:

| Combination | Candidates |
|---|---|
| boundary / PROVENANCE only | 61 |
| boundary / LOCAL_EVIDENCE | 1 |
| boundary / PROVENANCE + KNOWN_GAP / UPSTREAM_REFERENCE | 3 |

The NOT_ELIGIBLE candidate is boundary + KNOWN_GAP / LOCAL_EVIDENCE.

**Cohort machinery**

- **Classification:** `INCONCLUSIVE`, because there are 4 eligible dates and the minimum is 10. This is correct for four dates.
- **Challenge flags:** none fired. The median was 15 eligible candidates per date; there were no zero-candidate dates; the largest family share was 0.52.
- **Human-review sample:** selected deterministically, two per family.

These descriptive counts are **development facts, not validation results**. No policy changes because of them.

## Files

| File | Contents |
|---|---|
| `*_record.json`, `*_record_rerun.json` | per-date records (`DRYSDALE_PROSPECTIVE_VALIDATION_V1`) and the separate-process reruns |
| `dev_cohort_summary.json`, `dev_readout.md` | the four-date cohort summary and machine readout |
| `run.log`, `*.time` | the run log and `/usr/bin/time -v` output per run |
| `db_sha_before.txt`, `db_sha_after.txt` | dataset sha256 before and after |
| `harness/` | the pinned-copy loader and the run scripts (paths are the workstation's) |
