# 0Y-D blind validation report (generated)

Frozen records: `records.jsonl` sha256 `b15fef0c059b0c2cf4f4368579aa4c3c8d881ceec177ccbc0fe3baa38ce5ae4e`. Policy versions present: V1_DIRECTIONAL_STATE_X_IB_SHARE.
Generated mechanically from the frozen records; no threshold was changed.

## 1. Corpus inventory

| TD | dataset | contract | lifecycle | window captured | KNOWN_GAP | SUSPECTED_GAP | gaps overlapping window | eligibility | reason if not ELIGIBLE |
|---|---|---|---|---|---|---|---|---|---|
| 2026-08-26 | 30960d24 | FUTURE:CME:ES:2026-09 | FINALIZED | NO | 0 | 0 | 0 | NO_PROFILE | no retained trades inside the study window |
| 2026-08-27 | e068b74f | FUTURE:CME:ES:2026-09 | INTERRUPTED | NO | 1 | 0 | 0 | NO_PROFILE | no retained trades inside the study window |
| 2026-08-28 | 5a5fbbce | FUTURE:CME:ES:2026-09 | FINALIZED | NO | 0 | 0 | 0 | NO_PROFILE | no retained trades inside the study window |
| 2026-08-31 | befb7b0e | FUTURE:CME:ES:2026-09 | FINALIZED | NO | 0 | 0 | 0 | NOT_CLASSIFIED | STUDY WINDOW NOT FULLY CAPTURED; no Initial Balance (no trades in the first 60 minutes); period(s) with no retained trades: ABCDEFGHIJKL |
| 2026-08-31 | c9ebc043 | FUTURE:CME:ES:2026-09 | INTERRUPTED | NO | 4 | 0 | 3 | NOT_CLASSIFIED | STUDY WINDOW NOT FULLY CAPTURED; period(s) with no retained trades: BCDEFGHIJKLM |
| 2026-09-01 | bb8cce1f | FUTURE:CME:ES:2026-09 | FINALIZED | NO | 0 | 0 | 0 | NO_PROFILE | no retained trades inside the study window |
| 2026-09-02 | 9c76e79c | FUTURE:CME:ES:2026-09 | FINALIZED | yes | 1 | 0 | 0 | ELIGIBLE | — |
| 2026-09-07 | 85eccb13 | FUTURE:CME:ES:2026-09 | FINALIZED | yes | 0 | 0 | 0 | NOT_CLASSIFIED | period(s) with no retained trades: HIJKLM |
| 2026-09-08 | e3110b72 | FUTURE:CME:ES:2026-09 | OPEN | unknown | 0 | 0 | 0 | NOT_CLASSIFIED | capture interval not recorded; study-window coverage unverified |
| 2026-09-10 | f6553efa | FUTURE:CME:ES:2026-09 | FINALIZED | NO | 0 | 0 | 0 | NO_PROFILE | no retained trades inside the study window |
| 2026-09-11 | 3716af9f | FUTURE:CME:ES:2026-09 | FINALIZED | NO | 0 | 0 | 0 | NOT_CLASSIFIED | STUDY WINDOW NOT FULLY CAPTURED |
| 2026-09-15 | b07e92d4 | FUTURE:CME:ES:2026-09 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-09-21 | 64d684c9 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 1 | 0 | 0 | ELIGIBLE | — |
| 2026-09-23 | b2856c52 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-09-24 | 31c92a57 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-09-25 | c690ff8e | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-09-28 | 843a6ca0 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-09-29 | 6af08205 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 1 | 0 | 0 | ELIGIBLE | — |
| 2026-09-30 | 9ac5a21e | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-10-01 | fe280370 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-10-02 | 7e8d7b5e | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |
| 2026-10-06 | 2b6cc528 | FUTURE:CME:ES:2026-12 | FINALIZED | yes | 0 | 0 | 0 | ELIGIBLE | — |

Counts: ELIGIBLE 12, QUALITY_QUALIFIED 0, NOT_CLASSIFIED 5, NO_PROFILE 5 (total 22).

| quality rule | days |
|---|---|
| study window not fully captured -> NOT_CLASSIFIED | 3 |
| coverage unknown -> NOT_CLASSIFIED | 1 |
| gap inside window -> QUALITY_QUALIFIED | 0 |
| gap only outside window -> ELIGIBLE | 3 |
| window periods without trades -> NOT_CLASSIFIED | 3 |

## 2. Blind results — ELIGIBLE days

| TD | IB | range | IB share | ext ↑ | ext ↓ | ext ↑/IB | ext ↓/IB | state | new highs | new lows | terminal pct | tails ↑/↓ | interior zones | candidate | direction | policy |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-02 | 39.50 | 48.25 | 0.8187 | 8.75 | 0.00 | 0.2215 | 0.0000 | UP_ONLY | CDE | - | 0.7306 | 2/47 | 1 | NORMAL_VARIATION_DAY | UP | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-15 | 32.25 | 42.25 | 0.7633 | 0.00 | 10.00 | 0.0000 | 0.3101 | DOWN_ONLY | - | C | 0.3136 | 33/12 | 1 | NORMAL_VARIATION_DAY | DOWN | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-21 | 32.75 | 89.00 | 0.3680 | 56.25 | 0.00 | 1.7176 | 0.0000 | UP_ONLY | CDEFGHIJKM | - | 0.8427 | 10/38 | 6 | TREND_DAY | UP | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-23 | 48.25 | 67.00 | 0.7201 | 0.00 | 18.75 | 0.0000 | 0.3886 | DOWN_ONLY | - | EFGH | 0.2164 | 83/7 | 0 | NORMAL_VARIATION_DAY | DOWN | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-24 | 28.00 | 58.25 | 0.4807 | 25.50 | 4.75 | 0.9107 | 0.1696 | BOTH_SIDES | FG | D | 0.6910 | 11/6 | 0 | NEUTRAL_DAY | - | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-25 | 41.00 | 62.00 | 0.6613 | 21.00 | 0.00 | 0.5122 | 0.0000 | UP_ONLY | FM | - | 0.8387 | 15/37 | 0 | NORMAL_VARIATION_DAY | UP | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-28 | 16.50 | 60.25 | 0.2739 | 11.00 | 32.75 | 0.6667 | 1.9848 | BOTH_SIDES | F | C | 0.3402 | 11/18 | 0 | NEUTRAL_DAY | - | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-29 | 23.75 | 46.25 | 0.5135 | 0.00 | 22.50 | 0.0000 | 0.9474 | DOWN_ONLY | - | CDGH | 0.4378 | 46/1 | 0 | NORMAL_VARIATION_DAY | DOWN | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-09-30 | 31.50 | 72.75 | 0.4330 | 2.50 | 38.75 | 0.0794 | 1.2302 | BOTH_SIDES | C | KM | 0.0515 | 7/152 | 0 | NEUTRAL_DAY | - | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-10-01 | 57.75 | 68.50 | 0.8431 | 1.25 | 9.50 | 0.0216 | 0.1645 | BOTH_SIDES | M | D | 0.7774 | 5/18 | 0 | NEUTRAL_DAY | - | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-10-02 | 35.25 | 56.25 | 0.6267 | 1.50 | 19.50 | 0.0426 | 0.5532 | BOTH_SIDES | C | D | 0.4444 | 6/40 | 0 | NEUTRAL_DAY | - | V1_DIRECTIONAL_STATE_X_IB_SHARE |
| 2026-10-06 | 27.75 | 37.25 | 0.7450 | 9.50 | 0.00 | 0.3423 | 0.0000 | UP_ONLY | D | - | 0.3423 | 5/24 | 0 | NORMAL_VARIATION_DAY | UP | V1_DIRECTIONAL_STATE_X_IB_SHARE |

## 3. Blind results — QUALITY_QUALIFIED days (reported separately)

none

## 4. Classification distribution

| outcome | ELIGIBLE count | % of ELIGIBLE | QUALITY_QUALIFIED count |
|---|---|---|---|
| NORMAL_DAY | 0 | 0.0 | 0 |
| NORMAL_VARIATION_DAY | 6 | 50.0 | 0 |
| TREND_DAY | 1 | 8.3 | 0 |
| NEUTRAL_DAY | 5 | 41.7 | 0 |
| UNCLASSIFIED | 0 | 0.0 | 0 |
| AMBIGUOUS | 0 | 0.0 | 0 |
| NOT_CLASSIFIED (incl. NO_PROFILE; not a share of ELIGIBLE) | — | — | 10 |

- IB share, ELIGIBLE days (n=12): min 0.2739, q25 0.4330, median 0.6440, q75 0.7450, max 0.8431

## 5. Boundary proximity (|IB share − boundary| ≤ 0.05; diagnostic only)

| TD | eligibility | boundary | IB share | share − boundary | side | state | candidate |
|---|---|---|---|---|---|---|---|
| 2026-09-29 | ELIGIBLE | 0.50 | 0.5135 | 0.0135 | at/above | DOWN_ONLY | NORMAL_VARIATION_DAY DOWN |
| 2026-09-24 | ELIGIBLE | 0.50 | 0.4807 | -0.0193 | below | BOTH_SIDES | NEUTRAL_DAY |
| 2026-10-01 | ELIGIBLE | 0.85 | 0.8431 | -0.0069 | below | BOTH_SIDES | NEUTRAL_DAY |
| 2026-09-02 | ELIGIBLE | 0.85 | 0.8187 | -0.0313 | below | UP_ONLY | NORMAL_VARIATION_DAY UP |

## 6. NEUTRAL_DAY sensitivity (ELIGIBLE)

| TD | ext ↑ ticks | ext ↓ ticks | smaller/IB | larger/IB | smaller/larger | terminal pct |
|---|---|---|---|---|---|---|
| 2026-09-30 | 10 | 155 | 0.0794 | 1.2302 | 0.0645 | 0.0515 |
| 2026-10-02 | 6 | 78 | 0.0426 | 0.5532 | 0.0769 | 0.4444 |
| 2026-10-01 | 5 | 38 | 0.0216 | 0.1645 | 0.1316 | 0.7774 |
| 2026-09-24 | 102 | 19 | 0.1696 | 0.9107 | 0.1863 | 0.6910 |
| 2026-09-28 | 44 | 131 | 0.6667 | 1.9848 | 0.3359 | 0.3402 |

- smaller/larger (n=5): min 0.0645, q25 0.0769, median 0.1316, q75 0.1863, max 0.3359
- smaller extension / IB (n=5): min 0.0216, q25 0.0426, median 0.0794, q75 0.1696, max 0.6667
- terminal pct (n=5): min 0.0515, q25 0.3402, median 0.4444, q75 0.6910, max 0.7774

## 7. NORMAL_VARIATION_DAY sensitivity (ELIGIBLE)

| TD | direction | IB share | extension (ticks) | ext/IB | ext/range | extending periods | new-extreme periods | terminal pct | tails ↑/↓ | interior zones |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-02 | UP | 0.8187 | 8.75 (35) | 0.2215 | 0.1813 | 5 | 3 | 0.7306 | 2/47 | 1 |
| 2026-09-15 | DOWN | 0.7633 | 10.00 (40) | 0.3101 | 0.2367 | 9 | 1 | 0.3136 | 33/12 | 1 |
| 2026-10-06 | UP | 0.7450 | 9.50 (38) | 0.3423 | 0.2550 | 3 | 1 | 0.3423 | 5/24 | 0 |
| 2026-09-23 | DOWN | 0.7201 | 18.75 (75) | 0.3886 | 0.2799 | 9 | 4 | 0.2164 | 83/7 | 0 |
| 2026-09-25 | UP | 0.6613 | 21.00 (84) | 0.5122 | 0.3387 | 8 | 2 | 0.8387 | 15/37 | 0 |
| 2026-09-29 | DOWN | 0.5135 | 22.50 (90) | 0.9474 | 0.4865 | 11 | 4 | 0.4378 | 46/1 | 0 |

- extension / IB (n=6): min 0.2215, q25 0.3101, median 0.3655, q75 0.5122, max 0.9474

## 8. TREND_DAY sensitivity (ELIGIBLE)

| TD | direction | IB share | extension (ticks) | ext/IB | ext/range | extending periods | new-extreme periods | terminal pct | tails ↑/↓ | interior zones |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-21 | UP | 0.3680 | 56.25 (225) | 1.7176 | 0.6320 | 11 | 10 | 0.8427 | 10/38 | 6 |

- extension / IB (n=1): min 1.7176, q25 1.7176, median 1.7176, q75 1.7176, max 1.7176

Counter-extension on TREND candidates is 0 by construction (one-sided rule).

## 9. NORMAL_DAY sensitivity (ELIGIBLE)

Historical "wide IB" context: NOT EVALUATED (V1 condition `ib_wide_vs_history`).

none

## 10. UNCLASSIFIED days (ELIGIBLE) and the conditions that failed

none

## 11. Raw structural outliers (ELIGIBLE + QUALITY_QUALIFIED; type-independent)

| measure | value | trading date(s) |
|---|---|---|
| largest profile / IB ratio | 3.6515 | 2026-09-28 |
| smallest profile / IB ratio | 1.1861 | 2026-10-01 |
| largest one-sided extension / IB | 1.7176 | 2026-09-21 |
| most symmetric two-sided extension (smaller/larger) | 0.3359 | 2026-09-28 |
| most asymmetric two-sided extension (smaller/larger) | 0.0645 | 2026-09-30 |
| largest upper tail (rows) | 83 | 2026-09-23 |
| largest lower tail (rows) | 152 | 2026-09-30 |
| most periods making new post-IB highs | 10 | 2026-09-21 |
| most periods making new post-IB lows | 4 | 2026-09-23, 2026-09-29 |
| terminal price nearest high (percentile) | 0.8427 | 2026-09-21 |
| terminal price nearest low (percentile) | 0.0515 | 2026-09-30 |

## 12. Mechanical inspection shortlist

Selection rules (fixed before inspection; ties → earlier date):

- **representative NORMAL_DAY**: ELIGIBLE NORMAL_DAY whose IB share is nearest that type's median IB share
- **representative NORMAL_VARIATION_DAY**: same rule for NORMAL_VARIATION_DAY
- **representative TREND_DAY**: same rule for TREND_DAY
- **representative NEUTRAL_DAY**: same rule for NEUTRAL_DAY
- **nearest 0.50 boundary**: ELIGIBLE day with the smallest |IB share - 0.50|
- **nearest 0.85 boundary**: ELIGIBLE day with the smallest |IB share - 0.85|
- **most asymmetric NEUTRAL_DAY**: smallest smaller/larger extension ratio
- **smallest-extension NORMAL_VARIATION_DAY**: smallest extension / IB
- **strongest TREND_DAY**: most new-extreme periods, then largest extension / IB
- **first UNCLASSIFIED**: earliest ELIGIBLE UNCLASSIFIED day

| slot | TD | candidate | IB share | rendered profile |
|---|---|---|---|---|
| representative NORMAL_DAY | — | no qualifying day | — | — |
| representative NORMAL_VARIATION_DAY | 2026-10-06 | NORMAL_VARIATION_DAY UP | 0.7450 | `reports/2026-10-06_2b6cc528.txt` |
| representative TREND_DAY | 2026-09-21 | TREND_DAY UP | 0.3680 | `reports/2026-09-21_64d684c9.txt` |
| representative NEUTRAL_DAY | 2026-09-24 | NEUTRAL_DAY | 0.4807 | `reports/2026-09-24_31c92a57.txt` |
| nearest 0.50 boundary | 2026-09-29 | NORMAL_VARIATION_DAY DOWN | 0.5135 | `reports/2026-09-29_6af08205.txt` |
| nearest 0.85 boundary | 2026-10-01 | NEUTRAL_DAY | 0.8431 | `reports/2026-10-01_fe280370.txt` |
| most asymmetric NEUTRAL_DAY | 2026-09-30 | NEUTRAL_DAY | 0.4330 | `reports/2026-09-30_9ac5a21e.txt` |
| smallest-extension NORMAL_VARIATION_DAY | 2026-09-02 | NORMAL_VARIATION_DAY UP | 0.8187 | `reports/2026-09-02_9c76e79c.txt` |
| strongest TREND_DAY | 2026-09-21 | TREND_DAY UP | 0.3680 | `reports/2026-09-21_64d684c9.txt` |
| first UNCLASSIFIED | — | no qualifying day | — | — |
