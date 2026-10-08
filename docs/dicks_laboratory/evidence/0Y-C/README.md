# 0Y-C evidence — Deterministic Day-Structure / Day-Type Candidates

Design/reference: `../../TPO_MARKET_PROFILE_0YA.md` §22–§32.
- Runs were offline and read-only.
- Every database's sha256 was unchanged after the runs.
- No dragon, Azure, collection or network.
- Policy thresholds were fixed before any real day was run, and none was
  changed afterwards (§31).

| File | Shows |
|---|---|
| `cli_day_structure_2026-09-30_9ac5a21e.txt` | CLI `--day-structure` on TD 2026-09-30 (complete, FINALIZED), including the matrix. A second run was byte-identical. |
| `day_structure_<TD>_<id>.txt` | Report for every local dataset (`--day-structure`, no matrix): 09-30, 09-02, 09-08, 09-11, 09-07 |
| `study_table.md` | Compact study table, including the gate-removed DIAGNOSTIC column and the TPO-peak segmentation audit |
| `day_structure_study.py` | The script that produced the two items above |

Outcomes:

| TD | Outcome | Why |
|---|---|---|
| 2026-09-30 | `NEUTRAL_DAY` candidate | `BOTH_SIDES`: 10 ticks above, 155 below; terminal at 0.05 of range |
| 2026-09-02 | `NORMAL_VARIATION_DAY` candidate, direction UP | `UP_ONLY`, IB share 0.8187. The overnight `KNOWN_GAP` lies outside the window, so the result is unqualified. |
| 2026-09-08 | `NOT_CLASSIFIED` | lifecycle `OPEN`, capture interval not recorded |
| 2026-09-11 | `NOT_CLASSIFIED` | STUDY WINDOW NOT FULLY CAPTURED (14:36 CT) |
| 2026-09-07 | `NOT_CLASSIFIED` | Labor Day halt: periods H–M have no trades |

Byte-stability on 2026-09-30:
- Default output (`--compare-volume-profile`, as in 0Y-A) is identical to
  `../0Y-A/tpo_2026-09-30_9ac5a21e_complete.txt`.
- `--structure` output is identical to
  `../0Y-B/structure_2026-09-30_9ac5a21e_complete.txt`.

Facts and CANDIDATE labels only; no interpretation.
