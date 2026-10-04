# 0W-5B evidence — WAL-decoupled persistence (2026-10-04)

The analysis is in `../../WAL_PERSISTENCE_0W5B.md`.

**Source and method.** Every run replays the authentic 2026-09-30 dataset
(read-only copy, sha256 `61489eea…` = its manifest) through the real
`DurableWriter`/`LaboratoryStore` into a disposable DB on robby, using
`scripts/dicks_lab_writer_burst_benchmark.py`. `paced` runs replay real arrival
times under an emulated 603-IOPS / 100 MB/s disk. `lifecycle` runs replay the
whole day at full speed to measure I/O totals and finalization. No network, no
dragon, no live data.

| File | What |
|---|---|
| `results_table.md` | one row per run (queue, lag, units/event, checkpoints, WAL max, accounting) |
| `bench_p_delete250_1x.json` | emulator calibration: the live 0W-4 configuration (DELETE, batch 250) replays to queue 48,420 / lag 220 s, against live 46,236 / 185.9 s |
| `bench_p_delete_{1x,1_5x,2x}.json` | accepted DELETE 20k/256 MiB: 78.1% / 99 s at 1×; **overload** at 1.5× and 2× |
| `bench_h_delete_2x_{1100,3500}iops.json` | hardware context: DELETE at P15-like IOPS (overload at 1,100; 66.5% at 3,500) |
| `bench_p_wal_1x_v1gate.json` | rejected v1 (writer-thread checkpoint, batch-size gate): 66.8% / 45.5 s |
| `bench_t_wal_v2_1x.json` | rejected v2 (writer-thread checkpoint, rate gate, interrupt-abort, 256 MiB force) with a full timeline: forced 38 s checkpoint 14 s before the spike → 91% / 45 s |
| `bench_p_wal_{1x,1_5x,2x}.json`, `bench_t_wal_v3_1x.json` | **v3 (shipped, background checkpointer)**: 6.2% / 2.2 s, 8.6% / 3.2 s, 43.5% / 7.4 s. Each includes a queue/WAL timeline and every checkpoint (start, duration, units, WAL size) |
| `bench_p_wal_{1x,2x}_harsh.json` | v3 under a harsh contention assumption (checkpoint 80% of the disk, +2 s per contended commit): 5.9% / 5.3 s, 52.6% / 17.5 s |
| `bench_l_{delete,wal}.json` | whole-day lifecycle: device I/O per component, WAL growth, finalization steps (warm and cold `quick_check`, checksum), single-file and checksum stability |
| `campaign.log` | every run, the code hashes it ran on, and every stopped or discarded run with its reason |
| `tooling/summarize.py`, `tooling/campaign{4,5}.sh` | exact commands |

**Discarded runs (see `campaign.log`).**
- Campaigns 1–3 were stopped when writer or benchmark code changed mid-run.
- Two failures were benchmark bugs, not production bugs, both fixed and rerun:
  - an int64 overflow in synthetic trade indices;
  - overloads crashing the benchmark instead of being recorded.
- The benchmark also originally failed to charge aborted-checkpoint I/O. This
  was found and fixed before v3; v3 has no abort path.
