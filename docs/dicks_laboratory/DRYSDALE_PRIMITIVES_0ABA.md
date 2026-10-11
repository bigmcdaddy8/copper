# 0AB-A — Drysdale VWAP Evidence Primitives: real-data study (2026-10-10)

Reference: `VWAP_PRICE_ACTION_PRIMITIVES.md`. Evidence: `evidence/0AB-A/`
(`PRICE_ACTION_FACTS_V1` JSON at six cutoffs per day, logs, database sha256,
anti-lookahead log, harness). No setup label is assigned anywhere.

## 1. Method

- Code: `db2ab86b14ae87476eeb9ac97ced1858c8f89eef` ("feat: deterministic VWAP and
  price-action tutor primitives"); the study ran at that HEAD with a clean
  worktree under `apps/` and `scripts/`.
- Days (each with its prior trading day): 2026-09-30 (+09-29), 2026-09-29
  (+09-28), 2026-10-02 (+10-01). One process per day, sequential.
- Cutoffs: 08:00, 09:00, 10:00, 12:00, 15:00, 16:00 CT. Every facts document
  was built twice and compared byte for byte: all 18 identical.
- Every band VWAP equals the snapshot's accepted cash VWAP exactly (all 15
  cutoffs after 08:30).
- Source database sha256 before = after.

## 2. Examples (facts, no interpretation)

### 2026-09-30

| Cutoff | Cash VWAP / σ | ±1σ band | Last price, zone (1σ / 2σ) | Time outside ±1σ / ±2σ | ATR_5M_V1 |
|---|---|---|---|---|---|
| 10:00 | 7766.1983 / 8.6328, DEVELOPING | 7757.57 – 7774.83 | 7772.75: between VWAP and upper / between | 2594 s (48.0%) / 632 s (11.7%) of 5400 s | 8.6191 (204 bars) |
| 16:00 | 7753.8821 / 20.1772, COMPLETE, QUALITY_QUALIFIED | 7733.70 – 7774.06 | 7721: below lower / between VWAP and lower | 14788 s (54.8%) / 2870 s (10.6%) of 27000 s | 5.2142 (276 bars) |

References at 16:00:
- **IB_HIGH 7779.50:** 42 crosses. The first cross is UP at 09:54:02; the latest episode is DOWN from 10:50:31, touched again at 10:50:33, max excursion 74.00 points, 62 consecutive 5-minute closes beyond.
- **IB_LOW 7748.00:** first cross DOWN at 13:53:43.
- **PRIOR_VALUE_AREA_HIGH 7741.75:** first cross DOWN at 14:47:48.
- **CASH_VWAP:** 743 trade-level crosses; the last cross is DOWN at 12:12:56, with 46 consecutive closes below since.

5-minute bars at 10:00:
- **09:50 bar:** O 7774.25, H 7782, L 7772, C 7780, UP, higher high; close above the +1σ band.
- **09:55 bar:** inside bar, DOWN, closing back between VWAP and the upper band.

### 2026-09-29

| Cutoff | Cash VWAP / σ | Last price, zone (1σ) | Time outside ±1σ / ±2σ | ATR |
|---|---|---|---|---|
| 10:00 | 7742.1104 / 3.7360 | 7737.75: below lower | 1528 s (28.3%) / 81 s (1.5%) | 7.3869 |
| 16:00 | 7730.8534 / 9.2646 | 7738.25: between VWAP and upper | 11496 s (42.6%) / 1783 s (6.6%) | 3.4628 |

- **IB_LOW 7734.75:** first cross DOWN at 09:49:09; 116 crosses by 16:00.
- **PRIOR_VALUE_AREA_LOW 7746.25:** first cross DOWN at 08:33:14; 76 consecutive closes below in the latest episode.

### 2026-10-02

| Cutoff | Cash VWAP / σ | Last price, zone (1σ) | Time outside ±1σ / ±2σ | ATR |
|---|---|---|---|---|
| 10:00 | 7794.8124 / 8.1025 | 7793: between VWAP and lower | 2827 s (52.4%) / 224 s (4.1%) | 8.9303 |
| 16:00 | 7781.7268 / 11.7006 | 7776.5: between VWAP and lower | 6572 s (24.3%) / 1121 s (4.2%) | 3.2306 |

- **IB_HIGH 7808.75:** crossed UP at 09:42:19 and back DOWN at 09:42:40; touched again at 09:42:47; 76 consecutive closes below by 16:00.
- **11:50 bar (at 12:00):** outside bar (higher high and lower low).

Trade-level crossing counts are large (hundreds per day for VWAP and the ±1σ
bands): every change of strict side between consecutive trades is a cross. The
5-minute close facts are the coarser view. Choosing between them is a policy
question for later.

## 3. Anti-lookahead (real data, copy of 2026-09-29)

- First run: the 12,518 trades in [11:00, 11:05) CT were raised by 5 points on a copy.
  - Facts at 11:00 were byte-identical; facts at 11:10 changed (the 11:00 bar's high 7722.25 → 7727.25).
  - That change caused no new crossings.
- Second run (`anti_lookahead.log`): the same trades were set to 7800, above the +2σ band.

| | at 11:00 | at 11:10, original | at 11:10, mutated |
|---|---|---|---|
| facts identical to the original | **yes** | — | no |
| 11:00 bar high | — | 7722.25 | 7800 |
| CASH_VWAP crosses (last cross) | 459 / 459 | 459 (09:58:13 CT) | 461 (11:05:00.011 CT) |
| VWAP_UPPER_1SD crosses | 73 / 73 | 73 | 75 |
| VWAP_UPPER_2SD crosses | 9 / 9 | 9 | 11 |

The copy was made on disk (`~/.cache`) and deleted afterwards. The source
database sha256 is unchanged.

## 4. Incremental cost (replay already prepared)

| Phase (2026-09-30) | 09:00 | 12:00 | 16:00 |
|---|---|---|---|
| as-of effective tape (recomputed; the snapshot computes it separately) | 3.7 s | 9.8 s | 13.8 s |
| sort and scale | 0.8 s | 1.7 s | 3.3 s |
| single pass: bands, occupancy, 13 reference paths, bar aggregation | 3.8 s | 19.6 s | 51.9 s |
| ATR | < 0.01 s | < 0.01 s | < 0.01 s |
| bar relations and summaries | < 0.01 s | 0.01 s | < 0.01 s |
| facts document | 21 KB | 46 KB | 83 KB |

Other days have the same shape: 53 s (09-29) and 57 s (10-02) for a full day.
The single pass is pure Python over every cash trade: about 46 µs per trade
(1,133,651 cash trades on 09-30) for the bands, occupancy and 13 references. Replay preparation: 193–272 s. Peak RSS: 3.35–4.49 GB,
the existing replay-memory backlog. Not optimized in 0AB-A.
