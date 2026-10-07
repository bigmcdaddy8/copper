# 0W-5C Part-A actual-disk calibration (dragon data disk, 2026-10-05 00:11-01:14Z, HEAD a27013b)

Source: authentic 2026-09-30 tape (`es_20260930_9ac5a21e`, the 0W-4 worst day). Paced mode replays the 19:57-20:01Z (14:57-15:01 CT) window at real arrival times after a full-speed prefill; `--real-concurrency` lets the writer and WAL checkpointer contend on the real StandardSSD. Production modules imported unchanged (`bench_0w5c.py` is the scratch variant of `scripts/dicks_lab_writer_burst_benchmark.py`).

| run | journal | scale | paced events | queue peak | % of 50,000 | max lag s | ckpts (paced) | longest ckpt s | WAL peak (paced) | submitted = persisted | overloaded | finalize core s | quick/integrity | journal after | sidecars |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| a_wal_1x | wal | 1.0 | 111,862 | 2,758 | 5.5 | 5.621 | 52 | 44.864 | 1,099.7 MiB | 111,862 = 111,862 (diff 0) | False | 9.361 | ok/ok | delete | 0 |
| a_wal_1_5x | wal | 1.5 | 147,874 | 6,766 | 13.5 | 8.625 | 43 | 46.457 | 1,402.1 MiB | 147,874 = 147,874 (diff 0) | False | 12.473 | ok/ok | delete | 0 |
| a_wal_2x | wal | 2.0 | 183,887 | 24,376 | 48.8 | 14.546 | 52 | 47.29 | 1,680.6 MiB | 183,887 = 183,887 (diff 0) | False | 9.659 | ok/ok | delete | 0 |
| a_delete_1x | delete | 1.0 | 111,862 | 32,800 | 65.6 | 105.174 | 0 | 0.0 | 0.0 MiB | 111,862 = 111,862 (diff 0) | False | 9.038 | ok/ok | delete | 0 |

Prefill (full-speed, not a live condition) for a_wal_1x: WAL reached 4,272,728,432 B (force-checkpoint bound exercised), queue 19,997, lag 8.37 s, 1,246,895 events, diff 0.

For reference, the emulated-603-IOPS 0W-5B runs: p_wal_1x 6.2% / 2.23 s; p_delete_1x 78.1% / 99.4 s (see ../0W-5B/results_table.md).
