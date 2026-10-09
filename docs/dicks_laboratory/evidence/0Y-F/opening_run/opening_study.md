# Opening-auction fact study (0Y-F)

Facts only. No opening type is named; no threshold is applied. Times are seconds after the open print. Excursions are ticks from the cash open (up / down).

## Pairing and quality

| date | dataset | prior trading date | context | same contract | opening quality | prior quality |
|---|---|---|---|---|---|---|
| 2026-08-31 | befb7b0e | 2026-08-28 | CURRENT_OPEN_INCOMPLETE | yes | NOT_AVAILABLE | — |
| 2026-08-31 | c9ebc043 | 2026-08-28 | CURRENT_OPEN_INCOMPLETE | yes | NOT_AVAILABLE | — |
| 2026-09-02 | 9c76e79c | 2026-09-01 | NO_PRIOR_PROFILE | yes | UNQUALIFIED | — |
| 2026-09-07 | 85eccb13 | 2026-09-04 | NO_PRIOR_PROFILE | — | UNQUALIFIED | — |
| 2026-09-08 | e3110b72 | 2026-09-07 | PRIOR_PROFILE_INCOMPLETE | yes | QUALITY_QUALIFIED | INCOMPLETE |
| 2026-09-11 | 3716af9f | 2026-09-10 | NO_PRIOR_PROFILE | yes | UNQUALIFIED | — |
| 2026-09-15 | b07e92d4 | 2026-09-14 | NO_PRIOR_PROFILE | — | UNQUALIFIED | — |
| 2026-09-21 | 64d684c9 | 2026-09-18 | NO_PRIOR_PROFILE | — | UNQUALIFIED | — |
| 2026-09-23 | b2856c52 | 2026-09-22 | NO_PRIOR_PROFILE | — | UNQUALIFIED | — |
| 2026-09-24 | 31c92a57 | 2026-09-23 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-09-25 | c690ff8e | 2026-09-24 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-09-28 | 843a6ca0 | 2026-09-25 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-09-29 | 6af08205 | 2026-09-28 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-09-30 | 9ac5a21e | 2026-09-29 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-10-01 | fe280370 | 2026-09-30 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-10-02 | 7e8d7b5e | 2026-10-01 | AVAILABLE | yes | UNQUALIFIED | UNQUALIFIED |
| 2026-10-06 | 2b6cc528 | 2026-10-05 | NO_PRIOR_PROFILE | — | UNQUALIFIED | — |

## Opening facts (days with an available cash open)

| date | same contract | open | delay | vs prior range | vs prior value | gap ticks | 5m up/dn | 15m up/dn | 30m up/dn | open crosses 30m/60m | prior value (full window) | A/B overlap | quality |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-02 | yes | 7650.50 | 0.000s | — | — | — | 6/28 | 16/30 | 26/30 | 60/60 | — | 0.1754 | UNQUALIFIED |
| 2026-09-07 | — | 7714.75 | 0.161s | — | — | — | 10/3 | 10/11 | 10/11 | 9/13 | — | 0.7273 | UNQUALIFIED |
| 2026-09-08 | yes | 7711.50 | 0.000s | — | — | — | 25/18 | 25/81 | 25/93 | 12/12 | — | 0.5147 | QUALITY_QUALIFIED |
| 2026-09-11 | yes | 7665.00 | 0.000s | — | — | — | 46/21 | 51/21 | 68/21 | 26/38 | — | 1.0000 | UNQUALIFIED |
| 2026-09-15 | — | 7616.75 | 0.004s | — | — | — | 9/56 | 9/56 | 9/56 | 14/14 | — | 0.5000 | UNQUALIFIED |
| 2026-09-21 | — | 7760.50 | 0.000s | — | — | — | 16/9 | 23/9 | 58/9 | 9/9 | — | 0.4412 | UNQUALIFIED |
| 2026-09-23 | — | 7823.50 | 0.000s | — | — | — | 11/15 | 11/36 | 11/97 | 23/23 | — | 0.2385 | UNQUALIFIED |
| 2026-09-24 | yes | 7734.25 | 0.000s | BELOW_PRIOR_RANGE | BELOW_PRIOR_VALUE | -158 | 34/17 | 42/17 | 59/17 | 43/43 | outside; entry +10002s | 0.2500 | UNQUALIFIED |
| 2026-09-25 | yes | 7777.50 | 0.000s | INSIDE_PRIOR_RANGE | INSIDE_PRIOR_VALUE | 48 | 31/41 | 53/41 | 65/41 | 10/19 | inside; exit↑ +0s exit↓ — | 0.7944 | UNQUALIFIED |
| 2026-09-28 | yes | 7772.75 | 0.000s | INSIDE_PRIOR_RANGE | BELOW_PRIOR_VALUE | -128 | 10/36 | 10/56 | 10/56 | 23/34 | outside; entry +10593s | 1.0000 | UNQUALIFIED |
| 2026-09-29 | yes | 7757.50 | 0.000s | INSIDE_PRIOR_RANGE | INSIDE_PRIOR_VALUE | 44 | 4/67 | 4/74 | 4/91 | 3/3 | inside; exit↑ — exit↓ +194s | 1.0000 | UNQUALIFIED |
| 2026-09-30 | yes | 7751.75 | 0.000s | INSIDE_PRIOR_RANGE | ABOVE_PRIOR_VALUE | 77 | 36/12 | 36/12 | 64/15 | 62/62 | outside; entry +22656s | 0.3188 | UNQUALIFIED |
| 2026-10-01 | yes | 7729.75 | 0.000s | INSIDE_PRIOR_RANGE | BELOW_PRIOR_VALUE | 67 | 39/37 | 41/49 | 41/79 | 37/37 | outside; entry — | 0.0909 | UNQUALIFIED |
| 2026-10-02 | yes | 7789.50 | 0.000s | ABOVE_PRIOR_RANGE | ABOVE_PRIOR_VALUE | 254 | 10/45 | 45/45 | 61/64 | 63/66 | outside; entry — | 0.8532 | UNQUALIFIED |
| 2026-10-06 | — | 7862.50 | 0.000s | — | — | — | 26/6 | 26/9 | 74/9 | 36/36 | — | 0.6364 | UNQUALIFIED |

## Mechanical inspection set

Rules were fixed in code (`SELECTION_RULES`) before the study ran; ties go to the earlier date.

| slot | rule | day | fact | report |
|---|---|---|---|---|
| largest open above prior range | paired days opening ABOVE_PRIOR_RANGE; max open - prior high (ticks) | 2026-10-02 | 193 ticks above prior high | `reports/2026-10-02_7e8d7b5e.txt` |
| largest open below prior range | paired days opening BELOW_PRIOR_RANGE; max prior low - open (ticks) | 2026-09-24 | 100 ticks below prior low | `reports/2026-09-24_31c92a57.txt` |
| most one-sided first 30 min | available days; min 30-min counter/dominant excursion, then max larger excursion | 2026-09-29 | 30 min up 4 / down 91 ticks, counter/dominant 0.0440 | `reports/2026-09-29_6af08205.txt` |
| most balanced first 30 min | available days; max 30-min counter/dominant excursion | 2026-10-02 | 30 min up 61 / down 64 ticks, counter/dominant 0.9531 | `reports/2026-10-02_7e8d7b5e.txt` |
| largest initial move then opposite open cross | available days with a 60-min open cross; max ticks travelled in the first direction before the first cross | 2026-10-02 | 8 ticks UP before the first open cross at 13:30:00Z | `reports/2026-10-02_7e8d7b5e.txt` |
| most open-price crossings | available days; max 60-min open-cross count | 2026-10-02 | 66 crossings in 60 min | `reports/2026-10-02_7e8d7b5e.txt` |
| fastest outside-value re-entry | paired days opening outside prior value; min time from open to first entry | 2026-09-24 | first entry 2:46:42.352000 after the open print | `reports/2026-09-24_31c92a57.txt` |
