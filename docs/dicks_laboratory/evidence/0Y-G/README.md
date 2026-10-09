# 0Y-G evidence — overnight context and multi-scale opening facts over the research corpus

Produced with:

```
uv run python scripts/dicks_lab_mp_overnight_study.py OUT_DIR <the 22 corpus databases>
```

The database paths are in `MARKET_PROFILE_CORPUS_0YD.md`. The databases were
read only: the sha256 of all 22 is identical before and after the run. No
dragon boot was needed.

| File | Content |
|---|---|
| `overnight_run/overnight_study.md` | quality (CURRENT_OPEN / PRIOR_DAY / OVERNIGHT kept separate) for 17 profiled days; overnight facts; multi-scale opening facts; reference encounters; grace-instant diagnostics; mechanical inspection set (rules fixed in code before the run) |
| `overnight_run/reports/` | per-day `OVERNIGHT CONTEXT` and `OPENING PATH DETAIL` |
| `overnight_run/timings.tsv` | per-dataset load times: 1,476 s of shared tape loading; all overnight and opening-path facts for 17 days took 7.9 s |

**Two runs.** Reviewing the first run (not kept) found one reporting defect.
09-08 has a recorded capture start (0.235 ms after 17:00 CT) but no recorded
end, and the overnight quality reasons said only "capture interval not
recorded", hiding the late start. Start and end are now judged
independently (with a test). The second run is this evidence: wall clock
24 min 45 s, peak RSS 4.7 GB. It differs from the first only in that 09-08
reason text and in timings. Every measured fact was identical. The
inspection rules were not changed.

The findings and the updated feasibility assessment are in
`docs/dicks_laboratory/MARKET_PROFILE_OVERNIGHT_0YG.md`. No day is named as any
opening type or inventory state.
