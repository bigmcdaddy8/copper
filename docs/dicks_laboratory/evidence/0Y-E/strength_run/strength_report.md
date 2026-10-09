# DAY_STRUCTURE_STRENGTH_V1 over the frozen 0Y-D corpus

- Frozen 0Y-D records: `records.jsonl` sha256 `b15fef0c059b0c2cf4f4368579aa4c3c8d881ceec177ccbc0fe3baa38ce5ae4e` (verified before use; not modified).
- Datasets re-analysed: 22; re-analysis reproduced the frozen V1 record byte-for-byte: 22/22.
- V1 labels below are the frozen 0Y-D labels (DAY_TYPE_V1). Strength facts are measurements beside them,
  not a re-classification, score or trading conclusion. Ratios: 4 dp; 'undefined' = zero denominator.

## Eligible days (12)

| date | V1 candidate | dir | IB share | above/IB | below/IB | dominant | dominant/IB | counter/dominant | new-high periods | new-low periods | terminal pct |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-02 | NORMAL_VARIATION_DAY | UP | 0.8187 | 0.2215 | 0.0000 | UP | 0.2215 | 0.0000 | 3 (CDE) | 0 (-) | 0.7306 |
| 2026-09-15 | NORMAL_VARIATION_DAY | DOWN | 0.7633 | 0.0000 | 0.3101 | DOWN | 0.3101 | 0.0000 | 0 (-) | 1 (C) | 0.3136 |
| 2026-09-21 | TREND_DAY | UP | 0.3680 | 1.7176 | 0.0000 | UP | 1.7176 | 0.0000 | 10 (CDEFGHIJKM) | 0 (-) | 0.8427 |
| 2026-09-23 | NORMAL_VARIATION_DAY | DOWN | 0.7201 | 0.0000 | 0.3886 | DOWN | 0.3886 | 0.0000 | 0 (-) | 4 (EFGH) | 0.2164 |
| 2026-09-24 | NEUTRAL_DAY | — | 0.4807 | 0.9107 | 0.1696 | UP | 0.9107 | 0.1863 | 2 (FG) | 1 (D) | 0.6910 |
| 2026-09-25 | NORMAL_VARIATION_DAY | UP | 0.6613 | 0.5122 | 0.0000 | UP | 0.5122 | 0.0000 | 2 (FM) | 0 (-) | 0.8387 |
| 2026-09-28 | NEUTRAL_DAY | — | 0.2739 | 0.6667 | 1.9848 | DOWN | 1.9848 | 0.3359 | 1 (F) | 1 (C) | 0.3402 |
| 2026-09-29 | NORMAL_VARIATION_DAY | DOWN | 0.5135 | 0.0000 | 0.9474 | DOWN | 0.9474 | 0.0000 | 0 (-) | 4 (CDGH) | 0.4378 |
| 2026-09-30 | NEUTRAL_DAY | — | 0.4330 | 0.0794 | 1.2302 | DOWN | 1.2302 | 0.0645 | 1 (C) | 2 (KM) | 0.0515 |
| 2026-10-01 | NEUTRAL_DAY | — | 0.8431 | 0.0216 | 0.1645 | DOWN | 0.1645 | 0.1316 | 1 (M) | 1 (D) | 0.7774 |
| 2026-10-02 | NEUTRAL_DAY | — | 0.6267 | 0.0426 | 0.5532 | DOWN | 0.5532 | 0.0769 | 1 (C) | 1 (D) | 0.4444 |
| 2026-10-06 | NORMAL_VARIATION_DAY | UP | 0.7450 | 0.3423 | 0.0000 | UP | 0.3423 | 0.0000 | 1 (D) | 0 (-) | 0.3423 |

## Persistence and structural context (eligible days)

| date | V1 candidate | consec. new hi/lo | HL/LH run | first/last ext | tail rows up/down | interior zones (rows) | POC pct | IB mid pct | VA mid pct |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-02 | NORMAL_VARIATION_DAY | 3/0 | 4/3 | UP/UP | 2/47 | 1 (51) | 0.7150 | 0.4093 | 0.7720 |
| 2026-09-15 | NORMAL_VARIATION_DAY | 0/1 | 3/4 | DOWN/DOWN | 33/12 | 1 (24) | 0.3195 | 0.6183 | 0.2544 |
| 2026-09-21 | TREND_DAY | 9/0 | 12/2 | UP/UP | 10/38 | 6 (84) | 0.8933 | 0.1840 | 0.6854 |
| 2026-09-23 | NORMAL_VARIATION_DAY | 0/4 | 3/6 | DOWN/DOWN | 83/7 | 0 (0) | 0.2836 | 0.6399 | 0.2985 |
| 2026-09-24 | NEUTRAL_DAY | 2/1 | 5/4 | DOWN/UP | 11/6 | 0 (0) | 0.6824 | 0.3219 | 0.6223 |
| 2026-09-25 | NORMAL_VARIATION_DAY | 1/0 | 5/3 | UP/UP | 15/37 | 0 (0) | 0.7016 | 0.3306 | 0.6613 |
| 2026-09-28 | NEUTRAL_DAY | 1/1 | 5/5 | DOWN/UP | 11/18 | 0 (0) | 0.5519 | 0.6805 | 0.5975 |
| 2026-09-29 | NORMAL_VARIATION_DAY | 0/2 | 5/8 | DOWN/DOWN | 46/1 | 0 (0) | 0.4973 | 0.7432 | 0.3838 |
| 2026-09-30 | NEUTRAL_DAY | 1/1 | 4/9 | UP/DOWN | 7/152 | 0 (0) | 0.7973 | 0.7491 | 0.7663 |
| 2026-10-01 | NEUTRAL_DAY | 1/1 | 6/5 | DOWN/UP | 5/18 | 0 (0) | 0.3139 | 0.5602 | 0.4672 |
| 2026-10-02 | NEUTRAL_DAY | 1/1 | 6/3 | UP/DOWN | 6/40 | 0 (0) | 0.3956 | 0.6600 | 0.4578 |
| 2026-10-06 | NORMAL_VARIATION_DAY | 1/0 | 3/5 | UP/UP | 5/24 | 0 (0) | 0.5101 | 0.3725 | 0.4832 |

## Facts inside each V1 label (descriptive)

| V1 candidate | n | counter/dominant min..max | dominant/IB min..max | terminal pct min..max |
|---|---|---|---|---|
| NEUTRAL_DAY | 5 | 0.0645 .. 0.3359 | 0.1645 .. 1.9848 | 0.0515 .. 0.7774 |
| NORMAL_VARIATION_DAY | 6 | 0.0000 .. 0.0000 | 0.2215 .. 0.9474 | 0.2164 .. 0.8387 |
| TREND_DAY | 1 | 0.0000 .. 0.0000 | 1.7176 .. 1.7176 | 0.8427 .. 0.8427 |

## Not eligible (10): no full-day strength assessment

| date | dataset | 0Y-D eligibility | strength scope | reason |
|---|---|---|---|---|
| 2026-08-26 | 30960d24 | NO_PROFILE | no profile | no retained trades inside the study window |
| 2026-08-27 | e068b74f | NO_PROFILE | no profile | no retained trades inside the study window |
| 2026-08-28 | 5a5fbbce | NO_PROFILE | no profile | no retained trades inside the study window |
| 2026-08-31 | befb7b0e | NOT_CLASSIFIED | RAW_FACTS_ONLY | STUDY WINDOW NOT FULLY CAPTURED; no Initial Balance (no trades in the first 60 minutes); period(s) with no retained trades: ABCDEFGHIJKL |
| 2026-08-31 | c9ebc043 | NOT_CLASSIFIED | RAW_FACTS_ONLY | STUDY WINDOW NOT FULLY CAPTURED; period(s) with no retained trades: BCDEFGHIJKLM |
| 2026-09-01 | bb8cce1f | NO_PROFILE | no profile | no retained trades inside the study window |
| 2026-09-07 | 85eccb13 | NOT_CLASSIFIED | RAW_FACTS_ONLY | period(s) with no retained trades: HIJKLM |
| 2026-09-08 | e3110b72 | NOT_CLASSIFIED | RAW_FACTS_ONLY | capture interval not recorded; study-window coverage unverified |
| 2026-09-10 | f6553efa | NO_PROFILE | no profile | no retained trades inside the study window |
| 2026-09-11 | 3716af9f | NOT_CLASSIFIED | RAW_FACTS_ONLY | STUDY WINDOW NOT FULLY CAPTURED |

## Demonstration days

- **2026-09-30** (principal example: V1 NEUTRAL_DAY with a token counter-extension): V1 NEUTRAL_DAY; state BOTH_SIDES; above 10 / below 155 ticks (IB 126); dominant DOWN 1.2302 x IB; counter/dominant 0.0645; new highs 1, new lows 2; terminal pct 0.0515 — report `reports/2026-09-30_9ac5a21e.txt`
- **2026-09-28** (the most two-sided V1 NEUTRAL_DAY): V1 NEUTRAL_DAY; state BOTH_SIDES; above 44 / below 131 ticks (IB 66); dominant DOWN 1.9848 x IB; counter/dominant 0.3359; new highs 1, new lows 1; terminal pct 0.3402 — report `reports/2026-09-28_843a6ca0.txt`
- **2026-09-21** (the accepted V1 TREND_DAY): V1 TREND_DAY UP; state UP_ONLY; above 225 / below 0 ticks (IB 131); dominant UP 1.7176 x IB; counter/dominant 0.0000; new highs 10, new lows 0; terminal pct 0.8427 — report `reports/2026-09-21_64d684c9.txt`
- **2026-09-02** (the smallest-extension V1 NORMAL_VARIATION_DAY): V1 NORMAL_VARIATION_DAY UP; state UP_ONLY; above 35 / below 0 ticks (IB 158); dominant UP 0.2215 x IB; counter/dominant 0.0000; new highs 3, new lows 0; terminal pct 0.7306 — report `reports/2026-09-02_9c76e79c.txt`
- **2026-09-29** (the day nearest the 0.50 IB-share boundary): V1 NORMAL_VARIATION_DAY DOWN; state DOWN_ONLY; above 0 / below 90 ticks (IB 95); dominant DOWN 0.9474 x IB; counter/dominant 0.0000; new highs 0, new lows 4; terminal pct 0.4378 — report `reports/2026-09-29_6af08205.txt`
