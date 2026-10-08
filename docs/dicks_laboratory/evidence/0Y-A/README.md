# 0Y-A evidence — Deterministic TPO / Market Profile Foundation

Design/reference: `../../TPO_MARKET_PROFILE_0YA.md`.

All runs are offline. Each database is opened read-only, and its sha256 was
identical before and after every run. No dragon, no Azure change, no
collection, no network.

The primary dataset (`2b6cc528-8928-4c2b-a27d-77794fc61d26`, TD 2026-10-06) is
on dragon only, and dragon stays deallocated. The trusted local finalized ES
datasets below were used instead.

| File | Dataset | Purpose |
|---|---|---|
| `tpo_2026-09-30_9ac5a21e_complete.txt` | `9ac5a21e-a5c0-427c-91fc-af300539b711`, TD 2026-09-30, `FUTURE:CME:ES:2026-12`, FINALIZED, 0 gaps (0W-5A) | Primary real-data smoke: full matrix and the TPO vs Volume comparison. A second run was byte-identical (deterministic). |
| `tpo_2026-09-02_9c76e79c_known_gap.txt` | `9c76e79c-f4dd-45c7-acb9-d9890dc20671`, TD 2026-09-02, ES 2026-09, FINALIZED, **KNOWN_GAP=1** (1.795 s, 2026-09-02T02:00:25Z, overnight) | Quality qualification on a real gap: the profile still computes, `INCOMPLETE / KNOWN_GAP=1` is visible, and the report makes no completeness claim. The 2026-09-29 dataset itself is on dragon only; a fixture reproduces its state (`test_known_gap_dataset_still_computes_but_stays_qualified`). |
| `tpo_2026-09-11_3716af9f_truncated_capture.txt` | `3716af9f-28bf-4611-b56c-cbeb8a4f0fff`, TD 2026-09-11, FINALIZED, 0 gaps; capture ended 19:36:11Z (14:36 CT, max-events cap) | Shows a gap-free dataset that still flags `STUDY WINDOW NOT FULLY CAPTURED`. |
| `independent_crosscheck.py`, `independent_crosscheck_2026-09-30_output.txt` | 2026-09-30 | Stdlib-only recompute from raw SQLite. Total 858 TPOs, POC 7767.25 (9 TPOs), high 7782.00, low 7709.25, IB 7779.50/7748.00, all identical to the CLI. |

## TD 2026-09-30 summary (US_CASH_PROFILE, 30 min, 0.25)

| Fact | Value |
|---|---|
| Profile high / low / range | 7782.00 / 7709.25 / 72.75 (291 ticks) |
| IB high / low / range (A+B) | 7779.50 / 7748.00 / 31.50 (126 ticks) |
| Extension above / below IB | 2.50 (first C) / 38.75 (first K) |
| TPO POC / VAL / VAH | 7767.25 / 7751.75 / 7778.25 |
| Value area | 603/858 TPOs = 70.28% |
| Periods present | ABCDEFGHIJKLM (13 of 13) |

## Market Profile vs Volume Profile (same effective tape, same window)

|  | TPO | Volume |
|---|---|---|
| POC | 7767.25 | 7770.00 |
| VAL | 7751.75 | 7752.00 |
| VAH | 7778.25 | 7778.50 |

TPO measures a time/opportunity distribution (distinct 30-minute periods per
price). Volume Profile measures a contract-volume distribution (1,448,748
contracts). The two are close here but not identical, and that is expected.
No interpretation is drawn.

Runtime note: the CLI takes about 2 min on a 1.4 M-trade dataset. Almost all
of that is the existing shared `prepare_scoped_dataset` load and
session-scoping path, which the Volume Profile CLI also uses. The TPO math
itself is linear. This is a backlog item, not a correctness issue.
