# Overnight context and multi-scale opening study (0Y-G)

Facts only. No opening type or inventory label is named; no threshold or preferred scale is applied. Ticks are 0.25. Times are seconds after the relevant print. ON = overnight [17:00, 08:30) CT.

## Quality (kept separate)

| date | dataset | CURRENT_OPEN | PRIOR_DAY | OVERNIGHT | overnight reasons |
|---|---|---|---|---|---|
| 2026-08-31 | befb7b0e | NOT_AVAILABLE | NO_PRIOR_PROFILE | NOT_AVAILABLE | no eligible trade in the overnight window [17:00, 08:30) CT; capture began 21:32:55.472338 after 17:00 CT (overnight window starts late) |
| 2026-08-31 | c9ebc043 | NOT_AVAILABLE | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000177 after 17:00 CT (overnight window starts late); KNOWN_GAP overlaps the overnight window: 1; lifecycle INTERRUPTED (not FINALIZED) |
| 2026-09-02 | 9c76e79c | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000239 after 17:00 CT (overnight window starts late); KNOWN_GAP overlaps the overnight window: 1 |
| 2026-09-07 | 85eccb13 | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000263 after 17:00 CT (overnight window starts late) |
| 2026-09-08 | e3110b72 | QUALITY_QUALIFIED | PRIOR_PROFILE_INCOMPLETE | QUALITY_QUALIFIED | capture began 0:00:00.000235 after 17:00 CT (overnight window starts late); capture end not recorded; coverage to 08:30 CT unverified; lifecycle OPEN (not FINALIZED) |
| 2026-09-11 | 3716af9f | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000314 after 17:00 CT (overnight window starts late) |
| 2026-09-15 | b07e92d4 | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000228 after 17:00 CT (overnight window starts late) |
| 2026-09-21 | 64d684c9 | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000305 after 17:00 CT (overnight window starts late); KNOWN_GAP overlaps the overnight window: 1 |
| 2026-09-23 | b2856c52 | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000259 after 17:00 CT (overnight window starts late) |
| 2026-09-24 | 31c92a57 | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000266 after 17:00 CT (overnight window starts late) |
| 2026-09-25 | c690ff8e | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000284 after 17:00 CT (overnight window starts late) |
| 2026-09-28 | 843a6ca0 | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000265 after 17:00 CT (overnight window starts late) |
| 2026-09-29 | 6af08205 | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000256 after 17:00 CT (overnight window starts late); KNOWN_GAP overlaps the overnight window: 1 |
| 2026-09-30 | 9ac5a21e | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000363 after 17:00 CT (overnight window starts late) |
| 2026-10-01 | fe280370 | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000351 after 17:00 CT (overnight window starts late) |
| 2026-10-02 | 7e8d7b5e | UNQUALIFIED | AVAILABLE | QUALITY_QUALIFIED | capture began 0:00:00.000203 after 17:00 CT (overnight window starts late) |
| 2026-10-06 | 2b6cc528 | UNQUALIFIED | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | capture began 0:00:00.000209 after 17:00 CT (overnight window starts late) |

## Overnight facts

| date | ONH | ONL | ON range t | order | Globex open | cash open vs ON | open pct in ON | ON beyond prior H/L t | ON beyond VAH/VAL t | ON inside prior value | sec above/below/at prior terminal | frac above/below | TPO rows above/below | volume above/below | gap open-prior term t | gap open-ON term t |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-08-31 | 7723.50 | 7683.75 | 159 | HIGH_FIRST | — | — | — | — | — | — | — | — | — | — | — | — |
| 2026-09-02 | 7658.75 | 7618.50 | 161 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.7950 | — | — | — | — | — | — | — | — | 0 |
| 2026-09-07 | 7728.50 | 7703.50 | 100 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.4500 | — | — | — | — | — | — | — | — | 1 |
| 2026-09-08 | 7725.75 | 7687.50 | 153 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.6275 | — | — | — | — | — | — | — | — | 1 |
| 2026-09-11 | 7683.50 | 7594.25 | 357 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.7927 | — | — | — | — | — | — | — | — | 0 |
| 2026-09-15 | 7633.25 | 7576.75 | 226 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.7080 | — | — | — | — | — | — | — | — | 0 |
| 2026-09-21 | 7771.25 | 7713.75 | 230 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.8130 | — | — | — | — | — | — | — | — | 0 |
| 2026-09-23 | 7843.25 | 7818.75 | 98 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.1939 | — | — | — | — | — | — | — | — | 0 |
| 2026-09-24 | 7779.25 | 7707.25 | 288 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.3750 | 0/208 | 0/230 | no | 4402/51361/36 | 0.0789/0.9205 | 45/1171 | 4810/312282 | -158 | 1 |
| 2026-09-25 | 7800.75 | 7748.50 | 209 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.5550 | 69/0 | 91/0 | no | 29572/25874/353 | 0.5300/0.4637 | 571/417 | 170882/55166 | 48 | -1 |
| 2026-09-28 | 7803.00 | 7757.00 | 184 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.3424 | 0/0 | 0/79 | no | 0/55799/0 | 0.0000/1.0000 | 0/1083 | 0/281384 | -128 | 0 |
| 2026-09-29 | 7770.75 | 7716.00 | 219 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.7580 | 0/40 | 0/121 | no | 19460/35942/397 | 0.3487/0.6441 | 382/707 | 115621/161736 | 44 | 0 |
| 2026-09-30 | 7771.25 | 7719.50 | 207 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.6232 | 51/0 | 118/0 | no | 52380/3193/226 | 0.9387/0.0572 | 1027/95 | 289185/27292 | 77 | 0 |
| 2026-10-01 | 7767.75 | 7705.00 | 251 | HIGH_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.3944 | 0/17 | 0/187 | no | 54795/935/69 | 0.9820/0.0168 | 1349/94 | 376854/15047 | 67 | -1 |
| 2026-10-02 | 7802.75 | 7723.25 | 318 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.8333 | 246/0 | 310/0 | no | 54946/628/225 | 0.9847/0.0113 | 1171/12 | 374592/1327 | 254 | 0 |
| 2026-10-06 | 7867.75 | 7829.00 | 155 | LOW_FIRST | — | INSIDE_OVERNIGHT_RANGE | 0.8645 | — | — | — | — | — | — | — | — | -1 |

## Multi-scale opening facts

Each cell: dominant side, counter/dominant (smaller/larger excursion from the open).

| date | 30s | 1m | 3m | 5m | 15m | 30m | A-period | A/B overlap | crosses 30m | last cross 30m | last cross 60m | longest UP res 60m | longest DOWN res 60m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-02 | DOWN 0.2308 | DOWN 0.2308 | DOWN 0.2143 | DOWN 0.2143 | DOWN 0.5333 | DOWN 0.8667 | DOWN | 0.1754 | 60 | 1578.898s | 1578.898s | 2021.102s | 595.399s |
| 2026-09-07 | DOWN 0.6667 | TIE 1.0000 | UP 0.3000 | UP 0.3000 | DOWN 0.9091 | DOWN 0.9091 | DOWN | 0.7273 | 9 | 340.072s | 1860.584s | 217.258s | 1739.255s |
| 2026-09-08 | UP 0.0400 | UP 0.0400 | UP 0.4800 | UP 0.7200 | DOWN 0.3086 | DOWN 0.2688 | DOWN | 0.5147 | 12 | 166.524s | 166.524s | 52.250s | 3433.476s |
| 2026-09-11 | DOWN 0.1333 | DOWN 0.1333 | DOWN 0.7619 | UP 0.4565 | UP 0.4118 | UP 0.3088 | UP | 1.0000 | 26 | 1377.555s | 2867.029s | 1177.523s | 97.313s |
| 2026-09-15 | DOWN 0.9000 | DOWN 0.6000 | DOWN 0.1957 | DOWN 0.1607 | DOWN 0.1607 | DOWN 0.1607 | DOWN | 0.5000 | 14 | 33.546s | 33.546s | 19.240s | 3566.450s |
| 2026-09-21 | UP 0.0625 | UP 0.0625 | UP 0.5625 | UP 0.5625 | UP 0.3913 | UP 0.1552 | UP | 0.4412 | 9 | 235.646s | 235.646s | 3364.354s | 80.186s |
| 2026-09-23 | UP 0.5455 | UP 0.9091 | UP 0.9091 | DOWN 0.7333 | DOWN 0.3056 | DOWN 0.1134 | DOWN | 0.2385 | 23 | 246.584s | 246.584s | 26.112s | 3353.416s |
| 2026-09-24 | TIE 1.0000 | TIE 1.0000 | UP 0.6800 | UP 0.5000 | UP 0.4048 | UP 0.2881 | UP | 0.2500 | 43 | 91.040s | 91.040s | 3508.960s | 45.367s |
| 2026-09-25 | DOWN 0.0976 | DOWN 0.0976 | DOWN 0.2195 | DOWN 0.7561 | UP 0.7736 | UP 0.6308 | UP | 0.7944 | 10 | 185.971s | 1955.557s | 1725.130s | 1644.443s |
| 2026-09-28 | DOWN 0.1111 | DOWN 0.1000 | DOWN 0.2778 | DOWN 0.2778 | DOWN 0.1786 | DOWN 0.1786 | DOWN | 1.0000 | 23 | 1795.552s | 1974.537s | 18.570s | 1625.463s |
| 2026-09-29 | DOWN 0.1739 | DOWN 0.1333 | DOWN 0.0976 | DOWN 0.0597 | DOWN 0.0541 | DOWN 0.0440 | DOWN | 1.0000 | 3 | 0.932s | 0.932s | 0.222s | 3599.068s |
| 2026-09-30 | DOWN 0.8333 | DOWN 0.8333 | UP 0.3333 | UP 0.3333 | UP 0.3333 | UP 0.2344 | UP | 0.3188 | 62 | 1140.026s | 1140.026s | 2459.974s | 153.731s |
| 2026-10-01 | UP 0.1111 | UP 0.4722 | DOWN 0.9730 | UP 0.9487 | DOWN 0.8367 | DOWN 0.5190 | DOWN | 0.0909 | 37 | 703.837s | 703.837s | 336.298s | 2896.163s |
| 2026-10-02 | DOWN 0.9091 | DOWN 0.5556 | DOWN 0.2222 | DOWN 0.2222 | TIE 1.0000 | DOWN 0.9531 | DOWN | 0.8532 | 63 | 1794.820s | 1879.750s | 1720.250s | 321.324s |
| 2026-10-06 | UP 0.5455 | UP 0.2727 | UP 0.2308 | UP 0.2308 | UP 0.3462 | UP 0.1216 | UP | 0.6364 | 36 | 482.035s | 482.035s | 3117.965s | 25.077s |

## Reference encounters (first 30 minutes)

Reach = first trade at or beyond the reference from the open's side. Opposite excursion = ticks beyond the open on the other side in [cross, cross+N).

| date | first reference reached | side of open | reached at | reach → open cross | opposite excursion after cross | references reached |
|---|---|---|---|---|---|---|
| 2026-09-02 | none reached | — | — | — | — | 0 |
| 2026-09-07 | none reached | — | — | — | — | 0 |
| 2026-09-08 | none reached | — | — | — | — | 0 |
| 2026-09-11 | none reached | — | — | — | — | 0 |
| 2026-09-15 | none reached | — | — | — | — | 0 |
| 2026-09-21 | OVERNIGHT_HIGH | UP | +1341.690s | no cross | — | 1 |
| 2026-09-23 | OVERNIGHT_LOW | DOWN | +300.316s | no cross | — | 1 |
| 2026-09-24 | none reached | — | — | — | — | 0 |
| 2026-09-25 | PRIOR_VAH | UP | +0.046s | 0.099s | 5m 41, 15m 41, 30m 41 | 2 |
| 2026-09-28 | none reached | — | — | — | — | 0 |
| 2026-09-29 | PRIOR_VAL | DOWN | +193.303s | no cross | — | 1 |
| 2026-09-30 | PRIOR_HIGH | UP | +111.745s | 91.296s | 5m 7, 15m 15, 30m 15 | 1 |
| 2026-10-01 | none reached | — | — | — | — | 0 |
| 2026-10-02 | OVERNIGHT_HIGH | UP | +914.232s | 548.278s | 5m 64, 15m 64, 30m 64 | 1 |
| 2026-10-06 | OVERNIGHT_HIGH | UP | +53.163s | 230.791s | 5m 9, 15m 9, 30m 9 | 1 |

## Grace-instant diagnostics (DIAGNOSTIC ONLY)

Days whose held side at the grace instant was not crossed within the opening window. No grace period is preferred.

| scale | days evaluated | no cross in 5m | no cross in 15m | no cross in 30m |
|---|---|---|---|---|
| tick path (from the open print) | 15 | 0 | 0 | 0 |
| after +1s (held side; 0 day(s) still at the open) | 15 | 1 | 1 | 1 |
| after +5s (held side; 0 day(s) still at the open) | 15 | 2 | 1 | 1 |
| after +15s (held side; 0 day(s) still at the open) | 15 | 2 | 1 | 1 |
| after +30s (held side; 0 day(s) still at the open) | 15 | 2 | 1 | 1 |
| after +60s (held side; 0 day(s) still at the open) | 15 | 3 | 2 | 2 |
| A-period (traded on one side of the open only) | 15 | — | — | 0 |

## Mechanical inspection set

Rules were fixed in code (`SELECTION_RULES`) before the study ran; ties go to the earlier date.

| slot | rule | day | fact | report |
|---|---|---|---|---|
| largest overnight range | overnight available; max ON range ticks | 2026-09-11 | 357 ticks | `reports/2026-09-11_3716af9f.txt` |
| smallest overnight range | overnight available; min ON range ticks | 2026-09-23 | 98 ticks | `reports/2026-09-23_b2856c52.txt` |
| cash open nearest ON high | open + overnight available; min |open - ONH| ticks | 2026-10-06 | open - ONH -21 ticks | `reports/2026-10-06_2b6cc528.txt` |
| cash open nearest ON low | open + overnight available; min |open - ONL| ticks | 2026-09-23 | open - ONL 19 ticks | `reports/2026-09-23_b2856c52.txt` |
| most one-sided 5m opening | open available; min 5-min counter/dominant, then max larger excursion | 2026-09-29 | up 4 / down 67 ticks, counter/dominant 0.0597 | `reports/2026-09-29_6af08205.txt` |
| most one-sided 30m opening | open available; min 30-min counter/dominant, then max larger excursion | 2026-09-29 | up 4 / down 91 ticks, counter/dominant 0.0440 | `reports/2026-09-29_6af08205.txt` |
| latest last open cross | open available; max (last open cross - open print) on the 60-min scale | 2026-09-11 | last cross 2867.029s after the open print | `reports/2026-09-11_3716af9f.txt` |
| longest residence above open | open available; max longest UP residence on the 60-min scale | 2026-09-24 | 3508.960s from 13:31:31Z | `reports/2026-09-24_31c92a57.txt` |
| longest residence below open | open available; max longest DOWN residence on the 60-min scale | 2026-09-29 | 3599.068s from 13:30:00Z | `reports/2026-09-29_6af08205.txt` |
| fastest reference reach -> open cross | any prior/overnight reference reached in 30 min and followed by an open cross; min reach-to-cross delay | 2026-09-25 | PRIOR_VAH reached UP of open; open crossed 0.099s later | `reports/2026-09-25_c690ff8e.txt` |
| largest opposite excursion after reference reach | same encounters; max 30-min opposite excursion after the open cross | 2026-09-25 | PRIOR_HIGH: 99 ticks beyond the open on the other side within 30 min of the cross | `reports/2026-09-25_c690ff8e.txt` |
