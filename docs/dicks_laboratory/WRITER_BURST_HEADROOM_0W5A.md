# 0W-5A — Writer / Persistence Burst-Headroom Analysis

**Date:** 2026-10-04. **Baseline:** `c72bd11` (0W-4 closed). **Collection:** disarmed
throughout. No disk, SKU, VM or queue-size change.

**Result: READY FOR FOLLOW-UP.**
- The bottleneck is proven: random-key index page writes, forced to the disk on
  every commit, hit the StandardSSD IOPS ceiling.
- One latent **silent event-loss defect** in the writer stop path was found and
  fixed.
- A minimal, durability-neutral batching change was shipped. It cuts device
  writes per event 2.3× on the authentic burst.
- The proposed headroom target is **not yet met** by that change alone.
- A WAL-decoupled commit path is measured to be roughly two orders of magnitude
  cheaper in IOPS on the commit path. It is projected to meet the target on the
  existing disk. Hardware is not yet shown to be the material limit.

Evidence: `evidence/0W-5A/` (benchmark JSONs, models, pre-fix loss log).
Benchmark tool: `scripts/dicks_lab_writer_burst_benchmark.py`.

## 1. Current writer path (traced from code)

```
DXLink feed thread: on_event -> DurableWriter.submit_event(source_order, event)
   queue.Queue(maxsize=50_000); put(timeout=10 s) -> CaptureBackpressureError if still full
writer thread (_run): get(timeout = last_flush + 0.1 s - now)
   _stage_event: source_records_from_events -> duplicate-index check -> normalize (1 event)
   flush when: batch >= max_events (250) | queue quiet until the 0.1 s deadline (Empty)
               | lifecycle marker (connected/disconnected) | STOP
_flush: ONE transaction (LaboratoryStore.transaction) -> commit
   per accepted event: INSERT OR IGNORE instruments (lookup), INSERT trade_observations,
   INSERT observation_source_provenance  (3 statements; rejections/deferred: 2 / 1)
SQLite: journal_mode=DELETE (rollback journal), synchronous=FULL (default),
   page 4096, cache_size default -2000 (2 MiB). No custom indexes.
   Maintained per accepted event: trade_observations rowid + sqlite_autoindex_1
   (observation_id TEXT PK, uuid5 -> RANDOM position) + autoindex_2
   (dataset_id, dataset_sequence -> append); provenance rowid + autoindex_1
   (observation_id, RANDOM).
```

On 2026-09-30 the two random indexes held ~17,283 leaf pages each.

## 2. Why 1,396,936 events took 127,706 flushes (10.9 events/flush)

The 0.1 s idle timer, not the 250 cap, makes most flushes. Arrival is ~16.7
events/s on average, so in ordinary flow the queue goes quiet within the 0.1 s
deadline, and each flush carries whatever arrived in that window.

Replaying the exact `_run` policy against the day's 1,396,936 authentic
`received_at` times gives 133–139k flushes (live: 127,706), an average of
10.0–10.5, a **median of 4**, and only ~200–600 full 250-event batches.

These small flushes happen when the disk is idle, so they are **not** the
capacity problem. During the burst the writer was already committing full
250-event batches.

## 3. Live 09-30 capacity (calibrated from telemetry)

A FIFO drain at **250 events/s**, fed the real per-event arrivals
(19:30–20:30Z), reproduces both live observables with one parameter:

| | Model | Live |
|---|---|---|
| queue peak | 46,239 | 46,236 |
| max persist lag | 186.0 s | 185.9 s |

At that time the data disk was pinned at ~603 write IOPS (100% consumed
15:02–15:07 CT) while writer CPU was 5–7%. That gives **≈2.4 device writes per
persisted event**.

Most of the burst landed in about 15 s: 19:59:45–20:00:01Z, with 6,015 events in
19:59:59 alone.

Limiting-factor verdict:

| | Factor | Evidence | Role |
|---|---|---|---|
| A | commit frequency | burst batches were already full (250). Fixed commit cost ≈ 8 writes per 250 events ≈ 0.03/event | minor |
| B | SQLite statement count | CPU only: 0.17–0.23 ms/event, which is a ~4,300–5,800 ev/s CPU ceiling | not binding |
| C | StandardSSD IOPS ceiling | 603 IOPS pinned; one-parameter fit at 250 ev/s | **binding resource** |
| D | single writer thread | CPU 5–7% during the burst | not binding |
| E | queue configuration | a buffer, not a cause | not a cause |
| F | write amplification | ~2.1 random index leaf pages dirtied per event (2 uuid5 PK indexes) + rollback-journal copy: **~23 KB written per ~500 B stored event (46×)** | **root cause × C** |

## 4. Deterministic burst benchmark

`dicks_lab_writer_burst_benchmark.py run` replays the authentic 2026-09-30
stream (read-only copy, sha256 `61489eea…` = manifest), rebuilt in
`source_order` into raw `DxLinkSourceEvent`s (accepted + rejected + deferred).
It drives the **real** `DurableWriter` + `LaboratoryStore` into a disposable DB
on robby's local SSD:

- **prefill:** 1,253,944 events, growing the indexes to their pre-burst size.
- **burst:** 104,813 events, 19:58–20:06Z, always backlogged as in the live
  drain.

It measures device writes from `/proc/diskstats`, plus flushes, batch-size
distribution, queue, lag, CPU, size and exact accounting. robby cannot cap
IOPS (no root / io cgroup), so the transferable number is **device writes per
event**: predicted dragon rate = 603 / that.

**Calibration:** the baseline measures 2.72 writes/event, predicting 221 ev/s.
Live was 250 (benchmark ~12% pessimistic).

| Config (burst phase) | writes/event | predicted ev/s @603 | Exact |
|---|---|---|---|
| baseline: batch 250, DELETE, 2 MiB cache | 2.72 | 221 | yes |
| 64 MiB cache | 2.72 | 222 | yes |
| batch 2,000 | 2.37 | 255 | yes |
| WAL (default checkpoint) | 2.66 | 227 | yes |
| WAL + batch 2,000 | 2.36 | 256 | yes |
| batch 10,000, 256 MiB | 1.64 | 367 | yes |
| batch 20,000, 256 MiB | 1.22 | 496 | yes |
| batch 50,000, 512 MiB | 0.69 | 877 | yes (after fix §5) |
| WAL, 100k-page checkpoint, batch 2,000 (checkpoint counted) | 0.74 | 811 | yes |
| WAL commit path only (checkpoint deferred) | **0.014** | (≈43,000) | yes |
| **post-change defaults (20,000 / 256 MiB / DELETE / FULL)** | **1.17** | **514** | **yes** |

These results match a page model: N random inserts into P leaf pages dirty
P(1−e^(−N/P)) pages. Batching helps only when N approaches P, and the cache
only removes spills. In WAL the commit is a sequential append (~740 KB per
device write). The random writes move into checkpoints, where repeated pages
are coalesced.

## 5. Defect found: silent loss at writer stop (fixed)

In `_run`'s idle branch the writer flushed, then returned as soon as
`_stop_event` was set. Items enqueued **during that flush** were abandoned,
`drain_and_stop()` returned normally, and `persisted_events` silently
undercounted `submitted_events`.

| | |
|---|---|
| **Found by** | benchmark c6, which lost 48,838 events (= `queue_depth_max`); `bench_c6_batch50000_PRE_FIX_event_loss.log` |
| **Reproduced** | deterministically with the **production default policy** (20 submitted, 10 persisted, no error) |
| **Production exposure** | `drain_and_stop()` runs once per dataset, at the final close. A loss requires an idle-timer flush in progress at that instant, with events enqueued during it, i.e. only the last few tens of ms before 16:00 CT. Not provable either way for 0W-4 datasets: `submitted_events` was never logged, and a dropped tail leaves `source_order` contiguous. Close-boundary evidence looked normal (last trades 15:59:58.1–15:59:59.99 CT). Mid-session reconnects do not stop the writer, so no hole could arise there. |
| **Fix** | stop only when the queue is actually empty. `submitted_events` now counts only items the writer owns. `drain_and_stop()` raises `CaptureWriterError` (→ INTERRUPTED) if `persisted_events != submitted_events`, so any future loss is loud. |
| **Tests** | race test (fails before the fix, verified by mutation) + invariant test |

## 6. Change shipped (minimal, durability-neutral)

- `WriterFlushPolicy.max_events` changed 250 → **20,000**, and a new
  `sqlite_cache_size_kib` = **262,144** (256 MiB) is applied to the writer
  connection by `LaboratoryStore.set_cache_size_kib()`.
- A batch exceeds the 0.1 s window only while the writer is behind, i.e. it
  commits what is already queued. Those items are equally un-durable in the
  queue, so the crash-loss window is unchanged.
- Unchanged: journal mode DELETE, `synchronous=FULL`, transaction-per-batch,
  `source_order` / `dataset_sequence` assignment, rejections / deferred /
  quality events, finalization, manifest and checksum, and the queue bound of
  50,000.
- Memory: up to ~256 MiB page cache plus one staged batch, against the ~1 GB
  MemoryPeak observed (B2ms has 8 GB).

## 7. Projected effect on the real 09-30 burst

The event-driven timeline model replays the real arrivals. Each commit costs
the measured writes/event for its batch size at 603 IOPS, plus CPU. The model
gives 98% / 234 s for the baseline, so it is slightly pessimistic.

| Writer | 1× queue peak / lag | 1.5× | 2× |
|---|---|---|---|
| baseline 250 | 98% / 234 s (live 92.5% / 185.9 s) | overload | overload |
| **shipped 20,000** | **80% / 100 s** | overload (134%) | overload (191%) |
| cap 50,000 | 80% / 86 s | overload | overload |
| WAL commit path, checkpoint off-burst (projection) | **10% / 1.9 s** | 21% / 3.5 s | 35% / 5.4 s |

Batching does not lower the 1× queue peak below ~80%. Early in the 15 s spike
the queue is shallow, so batches are small and inefficient. Then a single large
commit (tens of seconds at 603 IOPS) is in flight while the rest of the spike
arrives. Batching improves lag and sustained drain, not the spike itself.

A constant-rate view at the measured 514 ev/s would give 58% / 57 s. That view
is optimistic for the same reason.

## 8. Proposed 0W-5 acceptance target

The criterion is checked by the benchmark plus the calibrated timeline model
against the authentic 2026-09-30 stream at 603 IOPS, and later confirmed live:

1. Real 09-30 burst (1×): queue peak ≤ **50%** of `queue_maxsize` and max
   persist lag ≤ **30 s**.
2. 2× burst scale: **no overload** (queue peak < 100%) and lag ≤ 120 s.
3. Exact accounting, `writer_overloaded=false`, `submitted_events ==
   persisted_events`.
4. DELETE-mode, sidecar-free FINALIZED artifact and checksum unchanged.
5. `synchronous=FULL` (no durability weakening).

| Status | Criteria 1–2 | Criteria 3–5 |
|---|---|---|
| Baseline | fail | met |
| Shipped change | not yet met (80% / 100 s; 2× overloads) | met |
| WAL design (projection) | met | to be confirmed |

## 9. Hardware decision gate

**Not "StandardSSD is the material limit" yet.** The writer is not reasonably
efficient. It writes ~11–23 KB per stored ~500 B event, and its commit path
does synchronous random index writes. A WAL-decoupled commit path measures
0.014 writes/event on the commit path. With checkpoints kept off bursts (or
throttled), the existing 500/603-IOPS disk is projected to absorb 2× the 09-30
burst.

Faster storage would also work. For example, Premium SSD P15 is 1,100 IOPS
(burst 3,500); at the shipped 1.17 writes/event that is ~940–3,000 ev/s. It
should be weighed against the 0W-5B software option, not chosen by default.

## 10. Follow-up candidate (not started) — 0W-5B WAL-decoupled persistence

- WAL with `synchronous=FULL` during capture (durable on commit).
- Autocheckpoint off on the writer connection; a PASSIVE checkpoint from a
  separate connection, scheduled or throttled outside bursts.
- `wal_checkpoint(TRUNCATE)` + `journal_mode=DELETE` before finalization /
  checksum, so the FINALIZED file stays single-file.
- Crash/resume tests with `-wal`/`-shm` present; read-only analytics
  compatibility.
- Acceptance per §8.
