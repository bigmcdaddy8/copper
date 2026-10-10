# 0Y-H evidence — OPENING_TYPE_V1 over the research corpus (DEVELOPMENT, NOT VALIDATION)

Produced after the policy freeze (commit `92e0a0cc5266076e51746f8a3510db902711c88a`;
`tpo_opening_type.py` sha256 `2b7b571c…798d7c`; policy document sha256
`1a952478…5af2ec`) with:

```
uv run python scripts/dicks_lab_mp_opening_type_study.py record OUT_DIR <the 22 corpus databases>
```

- The database paths are in `MARKET_PROFILE_CORPUS_0YD.md`.
- The sha256 of all 22 databases is identical before and after the run. No
  dragon boot was needed.
- Wall clock 26 min 52 s; peak RSS 4.7 GB.
- One run only. The policy was not changed after its output was seen.

| File | Content |
|---|---|
| `opening_type_run/opening_type_audit.md` | counts by cohort (all DEVELOPMENT), overlaps, quality-qualified candidates, per-day candidate table |
| `opening_type_run/reports/` | per-day `OPENING-TYPE CANDIDATES` explanations (every condition with its detail, evidence, continuous facts) |
| `opening_type_run/records/` | one JSON record per profiled day: opening-auction, overnight and opening-path facts (tape `path` arrays omitted; reproducible from dataset id + database sha256), the classification, the policy and fact-module sha256 values, the cohort |
| `opening_type_run/timings.tsv` | 1,603 s of tape loading; 8.0 s to classify and record 17 days |

Findings: `docs/dicks_laboratory/MARKET_PROFILE_OPENING_TYPE_0YH.md`. Every
record is `DEVELOPMENT`: descriptive, not validation.
