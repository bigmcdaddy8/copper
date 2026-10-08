# 0Y-B evidence — Deterministic Market Profile Structural Features

Design/reference: `../../TPO_MARKET_PROFILE_0YA.md` §13–§21. Runs are offline
and read-only, and every database's sha256 was unchanged after each run. No
dragon, Azure, collection or network.

| File | Dataset | Shows |
|---|---|---|
| `structure_2026-09-30_9ac5a21e_complete.txt` | TD 2026-09-30, `9ac5a21e…`, ES Z6, FINALIZED, 0 gaps | Primary real-data smoke: full structure section and annotated matrix. |
| `structure_2026-09-02_9c76e79c_known_gap.txt` | TD 2026-09-02, `9c76e79c…`, `KNOWN_GAP=1` (overnight, outside the window) | The dataset stays `INCOMPLETE`. The structure is not qualified, because no gap overlaps the window. Includes a real `INTERIOR` zone (51 B-only rows). |
| `structure_2026-09-11_3716af9f_truncated_capture.txt` | TD 2026-09-11, `3716af9f…`, capture ended 14:36 CT | `*** STRUCTURAL FEATURES ARE QUALITY-QUALIFIED ***` / `STUDY WINDOW NOT FULLY CAPTURED`; `YES` candidates are suffixed `(quality-qualified)`. |
| `independent_structure_crosscheck.py` + `_output.txt` | 2026-09-30 | Stdlib-only recompute from raw SQLite: 159 one-TPO rows, zones 7709.25–7747.00 (152 rows, M) and 7780.50–7782.00 (7 rows, C), high C, low M. Identical to the CLI. |

Additional check: on 2026-09-30, the default CLI output (without `--structure`)
is byte-identical to `../0Y-A/tpo_2026-09-30_9ac5a21e_complete.txt`.

## TD 2026-09-30 structural facts

| Fact | Value |
|---|---|
| One-TPO rows | 159; 2 zones, no interior zone |
| Upper extreme | 7782.00, letters `C` (1 TPO). Tail 7 rows / 1.50 pts down to 7780.50 (C). `EXCESS_HIGH_CANDIDATE: YES`, `POOR_HIGH_CANDIDATE: NO` |
| Lower extreme | 7709.25, letters `M` (1 TPO). Tail 152 rows / 37.75 pts up to 7747.00 (M), **formed in final period: yes**. `EXCESS_LOW_CANDIDATE: YES`, `POOR_LOW_CANDIDATE: NO` |
| IB extension | above 2.50 (0.0794 × IB), new post-IB highs `C`; below 38.75 (1.2302 × IB), new post-IB lows `KM` |

Matrix inspection around each zone:
- **Upper:** 7782.00–7780.50 is C-only. 7780.25 is `CE`, which ends the tail.
- **Lower:** 7747.25–7747.75 is `KM`. 7747.00 down to 7709.25 is M-only.

Facts only. The final-period lower tail is exactly the case where references
disagree (§13 item 4). It is reported, not interpreted. Likewise, 2026-09-02's
2-row (0.25 pt) upper tail meets the V1 excess threshold, which illustrates the
row-size caveat (§13 item 2).

Runtime: the structure layer is negligible against the shared ~2-minute tape
load (backlog, unchanged).
