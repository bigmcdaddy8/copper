# 0Y-E evidence — DAY_STRUCTURE_STRENGTH_V1 over the frozen 0Y-D corpus

This is a derived analytical layer. It does **not** reclassify anything.
- The V1 labels shown here are the frozen 0Y-D labels (`DAY_TYPE_V1`).
- The 0Y-D `blind_run/` was only read. Its `records.jsonl` sha256 is
  unchanged: `b15fef0c059b0c2cf4f4368579aa4c3c8d881ceec177ccbc0fe3baa38ce5ae4e`.
- No threshold was changed, added or fitted.

## How it was produced

```
uv run python scripts/dicks_lab_mp_validation.py strength \
  docs/dicks_laboratory/evidence/0Y-D/blind_run OUT_DIR <the 22 corpus databases>
```

The database paths are in `MARKET_PROFILE_CORPUS_0YD.md`. For each one, the
command:
1. re-analyses the database with the unchanged pipeline;
2. rebuilds the 0Y-D `DayRecord`;
3. requires it to equal the frozen line byte-for-byte;
4. writes the strength vector beside it.

Results:
- **Reproduction:** 22 of 22 IDENTICAL (`strength_run/reproduction.tsv`).
- **Databases:** sha256 of all 22 unchanged before and after (read-only).
- **Wall time:** 24 min 14 s, sequential. The shared tape load dominates. The
  strength layer itself is computed from facts already built and adds
  negligible time.

## Files

| File | Content |
|---|---|
| `strength_run/strength_report.md` | the corpus summary: per-day table (§11 of the PO request), persistence/context table, per-label ranges, not-eligible days, demonstration days |
| `strength_run/strength_records.jsonl` (+ `.sha256`) | one exact JSON line per profiled dataset: `{dataset_id, trading_date, strength}` |
| `strength_run/reports/` | `DAY STRUCTURE STRENGTH` text section per profiled dataset (17); not-classified days lead with the RAW FACTS ONLY banner |
| `strength_run/reproduction.tsv` | frozen-record reproduction check, 22 rows |

## Demonstration: one label, different structure

Values are exact outputs, rounded to 4 dp.

| Day | V1 label | above / below (ticks) | IB ticks | dominant | dominant/IB | counter/dominant | new hi / lo periods | terminal pct |
|---|---|---|---|---|---|---|---|---|
| **09-30** | NEUTRAL_DAY | 10 / 155 | 126 | DOWN | 1.2302 | **0.0645** | 1 / 2 | **0.0515** |
| 09-28 | NEUTRAL_DAY | 44 / 131 | 66 | DOWN | 1.9848 | 0.3359 | 1 / 1 | 0.3402 |
| 09-21 | TREND_DAY UP | 225 / 0 | 131 | UP | 1.7176 | 0.0000 | 10 / 0 | 0.8427 |
| 09-02 | NORMAL_VARIATION_DAY UP | 35 / 0 | 158 | UP | 0.2215 | 0.0000 | 3 / 0 | 0.7306 |
| 09-29 | NORMAL_VARIATION_DAY DOWN | 0 / 90 | 95 | DOWN | 0.9474 | 0.0000 | 0 / 4 | 0.4378 |

What the numbers show (measurement, not interpretation):

- **09-30** keeps its V1 NEUTRAL_DAY label. The strength vector adds that:
  - the counter-extension is 10 ticks, 0.0645 of the dominant side;
  - 0.9394 of the total extension is below the IB;
  - the terminal is at 0.0515 of the range, 15 ticks from the low;
  - the lower tail is 152 rows.
- **09-28** has the same V1 label. Its counter-extension is 0.3359 of the
  dominant side and 0.6667 × IB, and its terminal is at 0.3402.
- So the two NEUTRAL days differ by a factor of about 5 in counter/dominant.
  The V1 label alone does not show this.
- **09-21 vs 09-02** are both one-sided (counter/dominant 0), but the
  dominant extension is 1.7176 × IB against 0.2215 × IB. The labels (TREND vs
  NORMAL_VARIATION) differ, and the vector quantifies by how much.
- **09-29** has an IB share of 0.5135, 0.0135 above the 0.50 boundary. Its
  dominant/IB of 0.9474 is close to 1. It made 4 new-low periods (C D G H;
  max consecutive 2). The vector shows how near the boundary the day was
  without moving the boundary.

Across the eligible set, counter/dominant ranges from 0.0645 to 0.3359 within
NEUTRAL_DAY (n = 5), and dominant/IB ranges from 0.2215 to 0.9474 within
NORMAL_VARIATION_DAY (n = 6). These are descriptive ranges over 12 inspected
days, not validated bands.

## Quality

The 5 NOT_CLASSIFIED days (08-31 ×2, 09-07, 09-08, 09-11) are reported with
scope `RAW_FACTS_ONLY`. Their reasons are the V1 `not_classified_reasons`.
The 5 NO_PROFILE days have no strength object. No day was QUALITY_QUALIFIED.
