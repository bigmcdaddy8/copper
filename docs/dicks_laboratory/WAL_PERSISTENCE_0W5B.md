# 0W-5B — WAL-Decoupled Persistence: Design & Deterministic Proof

**Date:** 2026-10-04. **Baseline:** `ddb6f0e` (0W-5A accepted: stop-race fix
`ef4f133`, batching/cache `eb11b29`). **Collection:** disarmed throughout. Not
deployed: `dragon` is still at `6f5247f` and deallocated. No live market data.

**Result: PASS — WAL-decoupled persistence ready for a one-day live proof.**
- The design is implemented behind `WriterFlushPolicy.journal_mode="wal"`, now
  the default, with the accepted DELETE path retained.
- Correctness, crash recovery and finalization are proven by deterministic
  tests: real process kills against the production writer.
- Performance is measured on the authentic 2026-09-30 stream through the real
  writer under an emulated 603-IOPS StandardSSD. The emulator is validated
  against live 0W-4 telemetry.
- Every acceptance target is met with margin, including under a deliberately
  harsh disk-contention assumption. The remaining uncertainty (real Azure I/O
  interleaving between checkpoint and commits) is exactly what 0W-5C measures.

## 1. Historical qualification (preserved, not reopened)

| | |
|---|---|
| 0W-4 operational capability | **ACCEPTED** |
| Historical pre-`ef4f133` tail completeness | **NOT FULLY PROVABLE** |

The stop-race fixed in 0W-5A could drop events enqueued during an idle flush in
progress at the final `drain_and_stop()`. Those datasets were written before
`submitted_events` existed, so their persisted accounting is exact (contiguous
`source_order`), but a submitted-vs-persisted proof is unavailable for the
final milliseconds before each 16:00 CT stop.

No dataset is rewritten and no evidence is manufactured. Datasets closed by
this code carry `submitted_events` / `persisted_events` /
`accounting_difference` in `dataset_closing_summaries`, the manifest, the
`CAPTURE_STOPPED` detail and the collector's JSON summary. Older files load
those fields as `None` (test `test_pre_0w5b_closing_summary_loads_without_fabricated_accounting`).

## 2. SQLite WAL semantics for this workload

Verified on the shipping SQLite **3.50.4** (Python 3.13) by experiment and by
the deterministic tests in `tests/test_wal_persistence.py`.

| Question | Behaviour | Evidence |
|---|---|---|
| Durable at COMMIT | With `journal_mode=WAL` + `synchronous=FULL`, COMMIT appends the transaction's page images to `-wal` and **fsyncs the WAL before returning**. A returned commit survives process death and (by fsync contract) host power loss. | `test_capture_mode_is_wal_full_no_autocheckpoint`; test A |
| Only in the WAL | Every commit since the last completed checkpoint. The main file may be arbitrarily stale; readers combine both via the `-shm` wal-index. | test A: 3,000 committed events present with a 4 KiB main file |
| What a checkpoint does | Copies the newest image of each page from WAL into the main file (in page order), fsyncs the main file, then records progress (`nBackfill`). It never commits, discards or reorders data. | |
| PASSIVE | Checkpoints as many frames as possible without waiting. Frames newer than an active reader's snapshot are left for later. Returns `(busy, log, checkpointed)`. | reader experiment: `(0, 722, 14)` with a reader open |
| TRUNCATE | Like FULL: waits (busy handler) for writers and readers, checkpoints everything, then truncates `-wal` to 0 bytes. If it cannot finish it returns `busy=1` and/or `checkpointed < log`, and data stays in the WAL. | `(1, 722, 14)` after a 0.5 s busy timeout with a reader open |
| WAL restart | After a checkpoint has backfilled every frame, the **next write** restarts the WAL at offset 0. With `journal_size_limit=0` the file is truncated then, so `-wal` size equals the live un-checkpointed volume. | `test_checkpoint_runs_when_quiet_and_restarts_the_wal` |
| Process crash | `-wal` and `-shm` remain. On the next open (read-write **or** read-only, even with `-shm` deleted) SQLite rebuilds the wal-index from the WAL and exposes exactly the committed transactions. An uncommitted batch is absent. | tests A, C, H; ro-without-shm experiment |
| Host crash | Same as process crash for committed transactions, because each COMMIT fsynced the WAL. The un-fsynced tail of an uncommitted transaction is discarded by checksum/salt validation on recovery. | SQLite WAL format; cannot be power-cut in CI |
| Interrupted checkpoint | `nBackfill` advances only after the main-file fsync, so a checkpoint killed midway leaves all frames valid in the WAL. Recovery re-applies them, and partially written main-file pages are superseded. | test B (kills at 0–50 ms into checkpoints); 12 raw kill trials during TRUNCATE and the DELETE conversion all recovered 200,000/200,000 rows, `integrity_check ok` |
| `journal_mode=DELETE` | Checkpoints and **deletes** `-wal` and `-shm` immediately. It needs exclusive access: with any reader open it fails with `database is locked`. | experiment; test G |
| Last connection close | Auto-checkpoints and removes the WAL. Therefore the design never relies on close; collapse is explicit and verified. | experiment |
| Readers during capture | A read-only connection sees a consistent committed snapshot and never blocks the writer. A **long-held** read transaction pins checkpoint progress and WAL restart, and blocks the final collapse. | test G |

## 3. Architecture (v3, shipped)

```
OPEN dataset (created in DELETE mode by _open_or_resume_dataset)
  writer thread start: PRAGMA journal_mode=WAL, synchronous=FULL,
                       wal_autocheckpoint=0, journal_size_limit=0, cache 256 MiB
  ingestion (unchanged 0W-5A): queue 50,000; batch <= 20,000; 0.1 s idle flush;
     each batch = one COMMIT = sequential WAL append + WAL fsync (durable)
  checkpointer thread (own connection, WalCheckpointer): every 1 s
     if WAL >= 64 MiB AND writer queue empty AND persisted rate over the
        trailing 5 s < 150 ev/s           -> PASSIVE checkpoint
     or WAL >= 1 GiB (growth bound)       -> PASSIVE checkpoint even if busy
     PASSIVE never takes the write lock and never waits: commits continue
finalization (long_running_capture):
  1  source intake stopped (collect() returned / failure path)
  2  drain_and_stop(): writer drained; checkpointer stopped and joined;
     submitted == persisted, else CaptureWriterError (-> INTERRUPTED)
  3  explicit gate: accounting_difference != 0 -> INTERRUPTED
  4  gap evidence (KNOWN_GAP / SOURCE_DISCONNECTED) committed (still WAL)
  5  collapse_to_single_file(): wal_checkpoint(TRUNCATE) must return busy=0
     and log == checkpointed; journal_mode=DELETE must return 'delete';
     no -wal/-shm/-journal may remain
  6  quick_check == 'ok'
  7  CAPTURE_STOPPED (+ submitted/persisted/difference), capture_ended,
     lifecycle state, closing summary -- ordinary DELETE-mode commits
  8  sidecar re-check; checksum; manifest (incl. submitted/persisted/difference)
  any failure in 5-6 -> INTERRUPTED, CAPTURE_STOPPED detail
     'finalization_failed=...', no checksum, no manifest; data intact in WAL
```

**Why the order differs from "checkpoint after the closing writes".** The
closing writes (step 7) happen after the collapse, in DELETE mode, so they
never exist only in a WAL. No sidecar can hold evidence at checksum time, and
FINALIZED is only ever written into an already single-file database.
`quick_check` runs on the collapsed file before the state is chosen.

### How the design got here (two rejected iterations, kept as evidence)

| Iteration | Checkpoint placement | Measured under 603-IOPS emulation, authentic 1× | Why rejected |
|---|---|---|---|
| v1 | writer thread, gate "no batch >= 500 in 5 s" | queue 66.8%, lag 45.5 s | the gate only fires above ~5,000 ev/s, so the 300–1,200 ev/s ramp counted as quiet |
| v2 | writer thread, trailing-rate gate, interrupt-abort on queue growth, 256 MiB force bound | queue 91.0%, lag 45.3 s | timeline (`bench_t_wal_v2_1x.json`): the WAL crossed 256 MiB during the ramp, and a forced 38 s checkpoint started 14 s before the spike. `interrupt()` aborts only the page-copy loop; the expensive final fsync is not interruptible. On the writer thread, **max lag can never be shorter than the longest checkpoint** (~45–90 s of dragon disk time after a 1× burst) |
| **v3** | **background thread, own connection**, trailing-rate gate, 1 GiB bound | **queue 6.2%, lag 2.2 s** | — |

**Why a separate connection is safe.** PASSIVE checkpoints take only the
checkpointer lock, never the write lock, and never invoke the busy handler, so
a commit is never blocked by one (test
`test_writer_keeps_committing_while_a_checkpoint_runs`: 5,000 events committed
while a checkpoint was held). The earlier concern that a concurrent
checkpointer could be chased forever by new commits, so the WAL never
restarts, does not hold for this workload. Checkpoints run only when quiet,
and quiet ES flow has frequent idle gaps longer than a catch-up checkpoint.
Measured WAL size returns to tens of MB after every quiet checkpoint
(`test_real_background_checkpoints_concurrent_with_commits_are_exact_and_bound_the_wal`,
and the benchmark timelines). A checkpointer failure never loses data, because
the frames stay in the WAL, but it fails the drain loudly (INTERRUPTED).

**Unchanged:** `source_order` assignment (feed thread), `dataset_sequence`, the
single writer, batch commit points, rejections/deferred/quality events, the
stop-race fix, the queue bound, DELETE-mode FINALIZED artifact and checksum.
`journal_mode="delete"` in `WriterFlushPolicy` keeps the accepted 0W-5A path
available.

## 4. OPEN-dataset read compatibility

| Tool | WAL OPEN dataset | Notes |
|---|---|---|
| `LaboratoryStore(read_only=True)` (DatasetAudit, analytics loader, stale/resume probes) | works: consistent committed snapshot, never blocks the writer | test `test_writer_runs_in_wal_and_open_dataset_is_readable_read_only`; works after a crash too, even without `-shm` |
| VWAP / volume-profile / developing-profile scripts | work (same read-only store) | each query holds a read snapshot for its duration |
| `sqlite3 -readonly`, `db_audit.py`-style spot checks | work | same caveat |
| `sha256sum` / copying the `.sqlite3` of an OPEN dataset | **meaningless / unsafe** | committed data may live only in `-wal`. Never copy or checksum an OPEN dataset file alone; copy `.sqlite3` + `-wal` (+ `-shm`) together or wait for FINALIZED |

**Operational rule (documented, no extra code):** do not hold long read
transactions on an OPEN dataset, and do not run audits or analytics against it
near 16:00 CT. A reader pins checkpoint progress, and at finalization it makes
the collapse wait up to 60 s and then fail. The result is a truthful
INTERRUPTED dataset with intact data, not a false FINALIZED (test G). Use these
tools on FINALIZED datasets.

## 5. Crash / recovery matrix (`tests/test_wal_persistence.py`)

| Case | Test(s) | Result |
|---|---|---|
| A crash after committed WAL txns, before checkpoint | `test_A_…` (child `os._exit` after 3,000 committed) | all 3,000 recovered, contiguous `source_order`, `integrity_check ok`; data lived only in `-wal` |
| B crash during checkpoint | `test_B_…` ×4 kill delays (marker proves a checkpoint had started) + 12 raw kill trials | no committed loss, contiguous, `integrity_check ok` |
| C killed with an uncommitted batch | `test_C_…` (WAL **and** DELETE) | exactly the committed prefix recovers. The in-flight batch is absent; lifecycle stays OPEN with no closing summary (no completion claim). Max non-durable window = queue (≤ 50,000) + current batch (≤ 20,000), **identical** to the accepted DELETE design (same commit points); in practice smaller because WAL commits are faster |
| D normal drain | `test_D_F_…`, writer suite | submitted == persisted, queue empty |
| E stop during active flush (`ef4f133`) | `test_events_enqueued_during_idle_flush_survive_a_concurrent_stop` (now under WAL default) | zero loss |
| F final checkpoint / conversion | `test_D_F_…`, `test_capture_mode_is_wal_full_no_autocheckpoint` | no sidecars, DELETE mode, exact counts, `integrity_check ok`, checksum stable after a later read-only open |
| G interrupted finalization | `test_G_reader_blocking_…` (real reader lock), `test_G_collapse_failure_injected_…` | INTERRUPTED, no checksum, no manifest, `finalization_failed=wal_collapse:…` evidence, all data intact |
| H recovery then lifecycle policy | `test_H_…next_day` (stale → INTERRUPTED + collapsed single file, `submitted_events=None`), `test_H_…same_day` (resume → continues `source_order` → FINALIZED single file) | existing lifecycle policy; no new auto-repair |
| background checkpointer | `test_writer_keeps_committing_while_a_checkpoint_runs`, `test_drain_waits_…`, `test_checkpointer_failure_fails_the_drain_loudly_…`, `test_real_background_checkpoints_concurrent_with_commits_…` | commits never blocked; failure → INTERRUPTED with data intact; real concurrent run exact and WAL-bounded |
| gating | `test_checkpoint_waits_while_ingestion_is_busy`, `…runs_when_quiet…`, `…force_bound…`, `test_delete_journal_mode_never_uses_wal` | mutation-checked |

## 6. Submitted / persisted invariant

`submitted_events` (counted only once the writer owns an item),
`persisted_events` and `accounting_difference` are recorded in four places:
- `dataset_closing_summaries` (additive migration; legacy files read as `None`)
- the manifest
- the `CAPTURE_STOPPED` detail (`writer_submitted_events=…;
  writer_accounting_difference=…`)
- the collector JSON summary

`drain_and_stop()` raises on any mismatch, and finalization separately gates
on `accounting_difference != 0` → INTERRUPTED. FINALIZED requires difference 0,
in either journal mode.

## 7. Benchmark method

`scripts/dicks_lab_writer_burst_benchmark.py` drives the **real**
`DurableWriter`/`LaboratoryStore` from the authentic 2026-09-30 stream
(read-only copy, sha256 = manifest) into disposable databases:

- **paced:** the index is prefilled to its real 19:57Z size (a collapsed
  snapshot reused across runs). The 19:57–20:06Z window is then replayed at
  its real arrival times, with the 19:59–20:01Z burst scaled ×1.5 / ×2 by
  distinct synthetic trades. The authentic 1× peak is 55,416 events/min,
  6,015 in one second.
- **Emulated disk:** after every commit, checkpoint and collapse, the
  operation's measured device writes (`/proc/diskstats`, Azure units = max(IOs,
  bytes/256 KiB)) hold the issuing thread until a 603-unit/s, 100 MB/s disk
  would have completed them. Real execution is serialized for clean
  attribution, while emulated waits overlap.
- **Contention model** (assumption): while a background checkpoint holds the
  disk, commits get 50% of it plus 0.5 s latency, and the checkpoint runs at
  50%. "Harsh" uses 20% plus 2.0 s.
- **Calibration:** the old live configuration (DELETE, batch 250) replays to a
  48,420 queue / 220 s lag, against **live 46,236 / 185.9 s**. The accepted
  DELETE-20k replays to 78.1% / 99 s, against the 0W-5A model's 80% / 100 s.
  So the emulator is close to live and slightly pessimistic.
- **lifecycle:** the whole day at full speed, giving whole-lifecycle device
  I/O per component and finalization timings.

## 8. Results — authentic burst cases (603 IOPS emulated)

| Writer | 1× queue / lag | 1.5× | 2× | commit units/ev | all units/ev (window) |
|---|---|---|---|---|---|
| live 0W-4 (DELETE, 250) | 96.8% / 220 s (live 92.5% / 185.9 s) | — | — | 2.74 | 2.74 |
| accepted DELETE 20k/256 MiB | 78.1% / 99.4 s | **OVERLOAD** (queue full at event 113,222 of 147,874) | **OVERLOAD** (at 101,261 of 183,887) | 1.53–1.95 | same |
| **WAL v3** | **6.2% / 2.2 s** | **8.6% / 3.2 s** | **43.5% / 7.4 s** | 0.04–0.07 | 0.66–0.84 |
| WAL v3, harsh contention | 5.9% / 5.3 s | — | 52.6% / 17.5 s | 0.055–0.075 | 0.66–0.92 |

Every run: `writer_overloaded` false (WAL), submitted == persisted, exact
source accounting (overloaded DELETE runs: exact over the submitted prefix),
`quick_check`/`integrity_check ok`, single-file FINALIZED artifact, stable
checksum. Results are in `evidence/0W-5B/results_table.md`. The 2× WAL queue
peak comes from the 1 GiB growth bound starting a background checkpoint at the
end of the spike (WAL 1.08 GB). It stays inside target. Raising the bound
would trade WAL size for more 2× headroom.

## 9. Checkpoint cost and WAL growth

| Checkpoint | WAL at start | device units | uncontended disk time @603 |
|---|---|---|---|
| quiet-flow (64 MiB trigger) | 64–112 MiB | 10,300–15,500 | 17–26 s |
| post-burst, 1× | 811–851 MiB | ~27,100 | ~45 s (90 s at 50% share) |
| post-burst / forced, 2× | 1.04–1.09 GiB | 27,200–28,500 | ~47 s |
| final (residual WAL at close) | ≤ 64 MiB | ≤ ~10,000 | ≤ ~17 s (measured 16.2–16.5 s emulated) |

**Whole lifecycle, 1,396,936 events (lifecycle mode):** WAL 806,858 units
(0.58/event: commits 27,498, checkpoints 798,533), against accepted DELETE
1,382,486 (0.99/event; DELETE looks better here only because full-speed replay
always fills 20,000 batches — paced realistic flow costs it 1.95/event) and
live DELETE-250 ~2.57/event. DB size is identical: 700.5 MB vs 700.6 MB.

**WAL growth:**

| Load | WAL growth | Basis |
|---|---|---|
| Normal / quiet flow | stays ≈ 64–110 MiB, checkpointed within seconds of crossing 64 MiB | timelines |
| 09-30 authentic day | max 811 MiB paced (608 MiB lifecycle), right after the close burst | measured |
| busy day (10-01: 1.67M events, peak minute 33k < 09-30's 55k) | inside the 09-30 envelope | inference from its smaller peak |
| 1.5× burst | 1.03 GiB | measured |
| 2× burst | 1.04–1.09 GiB | measured |

The 1 GiB bound starts a checkpoint even under load. The practical ceiling is
1 GiB plus growth during that one checkpoint (≈ 2 GiB worst case), against
232 GiB free.

## 10. Finalization time (target: comfortably inside 16:00 → ~16:10 CT)

The service runs from the 16:55 launch with `RuntimeMaxSec=84300`, so the hard
limit is 16:20, the nominal end 16:10, and finalization starts at 16:00:00.
Measured components, projected to 603 IOPS:

| Step | Warm page cache | Fully cold |
|---|---|---|
| drain + join an in-flight quiet checkpoint (worst: a 64 MiB one just started) | ≤ 17 s | ≤ 17 s |
| final TRUNCATE checkpoint (residual ≤ 64 MiB) | ≤ 17 s (16.5 s measured) | ≤ 17 s |
| journal conversion | 0.04 s | 0.04 s |
| `quick_check` (700 MB DB) | 1.3–22.7 s measured (CPU / page cache) | 163,882 reads → ~272 s |
| closing writes (DELETE mode) | < 0.1 s | < 0.1 s |
| checksum | ~2 s | 700 MB / 100 MB/s ≈ 7 s |
| **total** | **≈ 66 s worst** | **≈ 5.2 min worst** |

Proposed target:
- ≤ **2 min** projected with a warm page cache, the expected case on dragon (an
  8 GB VM; the DB pages were written that day).
- ≤ **6 min** fully cold (≥ 4 min margin to 16:10, ≥ 14 min to the 16:20 hard
  limit).
- 0W-5C must record the actual figure.

## 11. Accepted 0W-5 target vs evidence

| Criterion | Target | WAL v3 (603 IOPS) | |
|---|---|---|---|
| 09-30 1× queue | ≤ 50% | 6.2% (harsh 5.9%) | met |
| 09-30 1× max persist lag | ≤ 30 s | 2.2 s (harsh 5.3 s) | met |
| 2× overload | none | none (43.5%; harsh 52.6%) | met |
| 2× max persist lag | ≤ 120 s | 7.4 s (harsh 17.5 s) | met |
| submitted == persisted, exact accounting, not overloaded, integrity | all cases | all cases | met |
| finalization | proposed ≤ 2 min warm / ≤ 6 min cold | ≈ 66 s / ≈ 5.2 min projected | met (to verify live) |
| single-file FINALIZED, `synchronous=FULL` | required | yes | met |

## 12. DELETE vs WAL (identical authentic input)

| | Accepted DELETE 20k | WAL v3 |
|---|---|---|
| 1× queue / lag | 78.1% / 99.4 s | 6.2% / 2.2 s |
| 1.5× / 2× | overload / overload | 8.6% / 43.5%, no overload |
| commit units/event (paced) | 1.53–1.95 | 0.04–0.07 |
| whole-day units (lifecycle) | 1,382,486 | 806,858 |
| finalization (measured warm, robby) | 7–28 s (checks + checksum) | 16–31 s (+ final checkpoint) |
| durability at COMMIT | rollback journal + FULL | WAL + FULL (equivalent) |
| crash window | queue + batch | identical |
| complexity | none added | checkpointer thread (~50 lines), collapse step, WAL sidecars while OPEN, reader caveat |

## 13. Hardware comparison (analytical, emulated; no Azure change, no cost claims)

| Configuration (2× burst) | Queue / lag |
|---|---|
| DELETE @ 1,100 IOPS / 125 MB/s (P15-baseline-like) | **OVERLOAD** (at event 134,707 of 183,887) |
| DELETE @ 3,500 IOPS / 170 MB/s (P15-burst-like) | 66.5% / 17.1 s |
| **WAL @ 603 IOPS (existing StandardSSD)** | **43.5% / 7.4 s** |

For this workload, WAL on the existing disk outperforms DELETE on a disk with
about six times the IOPS. **A disk upgrade is not required for the accepted
headroom target.** Faster storage would add margin on top of WAL, but is not
needed by current evidence.

## 14. Proposed runtime design (for 0W-5C, not deployed)

`WriterFlushPolicy()` defaults:
- `journal_mode="wal"`, `synchronous=FULL`
- `max_events=20,000`, `max_interval_seconds=0.1`, `queue_maxsize=50,000`,
  cache 256 MiB
- checkpointer: min 64 MiB, quiet 5 s / < 150 ev/s with an empty queue, force
  1 GiB, poll 1 s

Finalization as in §3. No unit or systemd change is needed (same command; the
CLI JSON gains submitted/difference/WAL fields).

0W-5C should verify on one live trading date:
- checkpoint timing relative to the 15:00 CT burst
- real commit latency during checkpoints (the contention assumption)
- queue/lag
- WAL peak
- finalization wall time
- submitted == persisted
- single-file FINALIZED artifact

## 15. 0W-5C live outcome (TD 2026-10-06) — ACCEPTED PRODUCTION DESIGN

Evidence: `evidence/0W-5C/README.md`. The design in §14 ran unchanged on
`dragon` (`a27013b`) for one full autonomous trading date.

| §14 verification item | Live result |
|---|---|
| queue / lag | **568 / 50,000 = 1.14%**, **2.497 s** max persist lag, `writer_overloaded=false` |
| WAL peak | **405.8 MiB**; the 1 GiB force bound was not reached, so no forced checkpoint; no checkpointer error |
| checkpoints | **662**, longest **24.693 s** |
| finalization wall time | **12.4 s** CAPTURE_STOPPED → manifest (the §10 projection was ≈ 66 s warm) |
| submitted == persisted | **893,081 == 893,081**, difference **0** in all four durable records |
| single-file FINALIZED artifact | journal **DELETE**, sidecars **NONE**, quick/integrity ok, checksum agrees |
| disk | StandardSSD peak **59%** IOPS consumed, 0 minutes ≥ 95% |
| checkpoint timing vs 15:00 CT burst | **not observable in production** (aggregates only). The Azure disk peak at 15:01 came two minutes after the 14:59 event peak, which is consistent with quiet-time deferral but not a measurement. |
| commit latency during checkpoints | **not observable in production**. Part-A actual disk at 2×: p50 0.89 s, max 6.5 s during checkpoints, 0.27 s max outside them. |

**Load qualification.** The live peak minute had 26,243 events, against
55,416 on 2026-09-30. Part-A on the actual StandardSSD replayed the authentic
09-30 burst at 1× (5.5% / 5.6 s), 1.5× (13.5% / 8.6 s) and **2× (48.8% /
14.5 s, no overload, exact accounting)**. The lighter live tape and the
harder actual-disk replay together support the decision.

**Decision (PO, 2026-10-06):**
- WAL + `synchronous=FULL` is the **ACCEPTED PRODUCTION DESIGN**.
- StandardSSD is **SUFFICIENT**.
- A premium disk is **NOT REQUIRED**.
- An additional persistence soak is **NOT REQUIRED**.
- The DELETE path and all historical DELETE-mode evidence are retained.

**Backlog (non-blocking):**
- per-checkpoint production timestamps
- live commit-latency-during-checkpoint telemetry
- collector memory peak ~1.2 GiB (informational; ample capacity)
