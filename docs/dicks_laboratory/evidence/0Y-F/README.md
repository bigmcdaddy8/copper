# 0Y-F evidence — opening-auction facts over the research corpus

Produced with:

```
uv run python scripts/dicks_lab_mp_opening_study.py OUT_DIR <the 22 corpus databases>
```

The database paths are in `MARKET_PROFILE_CORPUS_0YD.md`. The databases were
read only; the sha256 of all 22 is unchanged before and after. No dragon boot
was needed.

| File | Content |
|---|---|
| `opening_run/opening_study.md` | pairing/quality table (17 profiled days), opening-facts table (15 available opens), mechanical inspection set (rules fixed in code before the run) |
| `opening_run/reports/` | per-day `OPENING AUCTION FACTS` plus the A/B-only early TPO matrix, marked with OPEN and the prior references |
| `opening_run/timings.tsv` | per-dataset load times. The opening facts for all 17 days took 2.2 s, against 1,424 s of shared tape loading. |

**Two runs.** The first run (not kept) found three presentation issues, which
were fixed before this evidence was produced:
- trailing spaces in matrix rows;
- no explicit `study_window_truncated` fact (09-11);
- the prior-quality column showed the prior's 0Y-C grade, UNQUALIFIED, where
  the prior profile was incomplete (09-08).

Every measured fact was identical between the two runs. The inspection rules
were not changed.

The findings and the feasibility assessment are in
`docs/dicks_laboratory/MARKET_PROFILE_OPENING_0YF.md`. No day is named as any
opening type.
