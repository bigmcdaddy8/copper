# Phase 0V — Resilient Long-Running Capture Foundation

Implements the minimum durable/resilient collection contract established by
[`LONG_HORIZON_DATA_REPLAY_READINESS_AUDIT.md`](LONG_HORIZON_DATA_REPLAY_READINESS_AUDIT.md)
(Phase 0U), so the next real datasets captured on `robby` are suitable for
serious long-horizon retention, replay research, and future AI-tutor work.

```
0L bounded experimental capture (unchanged, still usable)
        v
0U retention/replay audit
        v
0V resilient serious-collection foundation  <-- this document
        v
0W full-session / multi-day soak on robby (not yet run)
```

0V is proven on `robby` first. The eventual always-on deployment to `weasel`
(Windows 11, WSL Ubuntu, UPS-backed) comes later, after 0W.

## The five 0U MUST-FIX items, mapped to what changed

1. **Accepted NEW source-field parity** — `DxLinkTimeAndSaleProvenance`
   (`dxlink_timesales.py`) widened to full field parity with the deferred
   (CORRECTION/CANCEL) record: `event_symbol`, `event_classification`,
   `event_flags`, `exchange_code`, `bid_price`, `ask_price`,
   `exchange_sale_conditions`, `trade_through_exempt`, `aggressor_side`,
   `spread_leg`, `extended_trading_hours`, `valid_tick` are now durably
   retained for every accepted NEW trade (`observation_source_provenance`
   table, additive migration). Canonical `price`/`size`/`event_timestamp`
   are **not** duplicated here — they already live on `TradeObservation`.
2. **Rejected-source evidence parity** — a new
   `RejectedDxLinkTimeAndSaleSourceRecord` type and
   `rejected_dxlink_timesale_source_records` table preserve the complete
   structured source record for every rejected TimeAndSale event, 1:1 keyed
   by `rejection_id` alongside the existing `normalization_rejections` reason
   row. No raw JSON — the same structured field set as the deferred table.
3. **Resilient reconnect** — `long_running_capture.py`'s
   `run_long_horizon_capture` catches `DxLinkError`, records
   `SOURCE_DISCONNECTED`, backs off (deterministic bounded schedule), and
   calls `collect()` again (a full reconnect/resubscribe — no DXLink client
   changes needed, see below). A successful reconnect records
   `SOURCE_RECONNECTED` and an explicit `KNOWN_GAP` for the disconnect
   interval — **never** silently assumed recovered.
4. **Explicit dataset closure state** — `DatasetLifecycleState`
   (`dataset_state.py`): `OPEN` / `FINALIZED` / `INTERRUPTED`, stored on the
   `datasets` table. `FINALIZED` means the collector closed the artifact
   deliberately and cleanly — **it does not mean the market tape is
   complete**. `INTERRUPTED` means reconnect attempts were exhausted or an
   unexpected error occurred.
5. **Instrument + trading-date segmentation** — one logical dataset = one
   exact futures contract (`InstrumentIdentity`) + one futures trading date
   (reusing `sessions.py`'s existing `classify_es_session`, never a new
   midnight-based boundary), stored as first-class `datasets` columns
   (`trading_date`, `instrument_id`). Adopted immediately, even while
   collecting only ES.

## Architecture

```
DxLinkSourceCollector.collect()   <-- unmodified transport, called repeatedly
        |
        v
run_long_horizon_capture()  (long_running_capture.py)
        |  full source-field parity (accepted / deferred / rejected)
        |  durable source_order continuity across restarts
        |  bounded reconnect + KNOWN_GAP evidence
        |  instrument + trading-date segmentation & rotation
        v
LaboratoryStore  (one SQLite file per closed dataset)
        v
OPEN -> FINALIZED / INTERRUPTED
        v
checksum (SHA-256) + small sidecar manifest
```

**No DXLink transport reconnect logic was needed.** `DxLinkSourceCollector.
collect()` already performs a full connect/auth/subscribe cycle on every
call — so "reconnect" is simply calling `collect()` again for the remaining
time budget after a caught `DxLinkError`. The only K9 change (see below) is
generic and unrelated to reconnect orchestration itself.

## Reconnect policy

```
disconnect (DxLinkError)
    -> record SOURCE_DISCONNECTED
    -> deterministic bounded backoff (default: 1s, 2s, 5s, 10s, 30s, repeating)
    -> collect() again (fresh connect/auth/subscribe)
    -> on success: record SOURCE_RECONNECTED + close KNOWN_GAP[disconnect, reconnect)
    -> exceeding max_attempts (default 5): dataset -> INTERRUPTED, stop
```

**`reconnect != proof of gap recovery`.** The disconnect-to-reconnect
interval is *always* recorded as an explicit `KNOWN_GAP` — this collector
never assumes provider-side backfill occurred. No historical-recovery
mechanism exists in 0V; adding one is future work (0U left this an explicit
open research question, not resolved here).

### Continuous connection, not periodic polling (0V-A correction)

**A healthy connection is never intentionally torn down merely to check the
clock.** An earlier 0V draft bounded every `collect()` call to a fixed
poll interval (300s) so the supervisor could periodically regain control —
but since `DxLinkSourceCollector.collect()` performs a full connect/auth/
subscribe cycle on every call, this meant a perfectly healthy subscription
was deliberately closed and recreated roughly every five minutes, creating
exactly the kind of manufactured unobserved interval this project's own
`KNOWN_GAP` model exists to avoid. This was corrected (0V-A) before any real
long-duration use: each trading-date session now gets **exactly one**
continuous `collect()` call, spanning from connect through the *earlier* of
that session's own scheduled close or the Human-requested deadline. The
supervisor regains control only when that one call returns — either because
the requested span genuinely elapsed (a clean, scheduled stop) or because a
real `DxLinkError` was raised (a genuine disconnect). There is no
orchestration-driven mid-session reconnect of any kind.

## Duplicate handling across reconnect

A provider *might* conceivably redeliver an already-accepted `NEW` event
after a resubscribe. Detected via the same source identity dxFeed itself
uses for correction/cancel correlation (`index`/`source_index`) — **never**
via `event_timestamp + price + size`, which would risk collapsing
legitimately distinct trades that share those values. A detected duplicate
is not silently dropped: it is preserved as a `NormalizationRejection` with
reason `DUPLICATE_SOURCE_INDEX_ACROSS_RECONNECT`, alongside its own rejected
source-record evidence.

## Dataset segmentation, rotation, and resume

- **Filename**: `<root>_<YYYYMMDD>_<dataset-id-fragment>.sqlite3` (e.g.
  `es_20260825_c3abc88c.sqlite3`) — deterministic and human-readable, but
  **never authoritative**; `dataset_id` (inside the database) remains the
  real identity.
- **Resume**: at startup, the collector globs `data_dir` for files matching
  the instrument's filename pattern, opens each read-only to inspect its
  trading_date/instrument/lifecycle_state, and resumes the one `OPEN`
  dataset for the current instrument+trading-date if it exists — `source_
  order` continues at `max(durable source_order) + 1` (verified never to
  reset to 1 mid-dataset).
- **Stale prior-day OPEN dataset**: never silently resumed. Marked
  `INTERRUPTED` with durable lifecycle evidence before the current
  trading-date's dataset is opened.
- **Conflict**: if a file for the exact instrument+trading-date already
  exists and is already `FINALIZED`/`INTERRUPTED`, `run_long_horizon_capture`
  refuses to overwrite or duplicate it — a clear `LongHorizonCaptureError` is
  raised instead.
- **Rotation**: each trading date's session is bounded by `min(overall Human
  deadline, that session's own scheduled close)`. When a session ends on
  schedule (not via reconnect exhaustion) and Human budget remains, the
  dataset is finalized (`FINALIZED`) and the outer loop proceeds to the next
  trading date — waiting through the intervening maintenance interval first
  (see below) — all within the same bounded run.
- **Maintenance interval** (16:00–17:00 CT): a **scheduled closed interval,
  never a `KNOWN_GAP`, never a `SOURCE_DISCONNECTED`**. `resolve_current_
  trading_date` raises a clear error for any timestamp in this window or
  outside the session entirely; the supervisor responds by computing the
  next session open (`next_session_open_after`) and sleeping (deterministic,
  dependency-injected `sleeper`) until then, capped at the overall Human
  deadline. No dataset exists for the maintenance window itself. This
  applies equally whether the collector starts mid-maintenance or reaches it
  mid-run — both wait the same way, then open the next trading date's
  dataset with a fresh `SOURCE_CONNECTED` (never a `SOURCE_RECONNECTED` of
  the prior day's dataset).
- **Disconnect crossing a session close**: if a genuine disconnect's
  reconnect attempts have not yet succeeded by the time the session's own
  close (or the Human deadline) arrives, the unobserved interval is capped
  as a `KNOWN_GAP` ending exactly at that boundary — it is never extended
  into the maintenance interval, and no fake `SOURCE_RECONNECTED` is
  recorded for a dataset that is closing on schedule anyway. The dataset
  still closes `FINALIZED` (a clean, scheduled artifact closure is not the
  same thing as reconnect exhaustion) — `FINALIZED` never implies the
  session's tape was complete.

## Closure states

```
                 OPEN
                   |
        +----------+----------+
        |                     |
  clean close           unrecoverable
        |                 failure
        v                     v
   FINALIZED             INTERRUPTED
```

`FINALIZED != complete market tape.` It only means the artifact was closed
intentionally and cleanly — completeness is separate quality evidence
(`KNOWN_GAP`/`SUSPECTED_GAP`, coverage classification already established in
0N/0Q). A `FINALIZED` dataset can and often will contain `KNOWN_GAP`
evidence from an earlier reconnect. Both the bounded duration elapsing and a
`KeyboardInterrupt` (Ctrl+C) during collection are treated as a deliberate
clean stop → `FINALIZED` (with truthfully partial coverage, never implying a
complete session).

## Closing metadata

A frozen `DatasetClosingSummary` is written exactly once per dataset, at the
moment it closes: accepted/deferred/rejected counts, known/suspected gap
counts, first/last `source_order`, `closed_at`, `collector_version`
(`phase-0v-serious-collection-v1`), and `collector_git_commit` (resolved
once at startup via `git rev-parse HEAD`, falling back to `"UNKNOWN"` if
unavailable — never resolved per-event). This answers *"what did the
collector record when it finalized?"* — distinct from, and not a
replacement for, the existing recomputed `DatasetAudit`, which answers
*"what does the database contain right now?"* The two normally agree.

## Checksum and manifest

After a dataset closes, its SQLite file's SHA-256 is computed and a small
sidecar manifest (`<file>.manifest.json`) is written alongside it —
`dataset_id`, `instrument`, `trading_date`, `state`, `sha256`,
`collector_git_commit`, `closed_at`. **This is an archival-integrity aid
only** — it proves the file's bytes are unaltered since closure, and is
explicitly **not** a market-data completeness claim (`checksum_scope` states
this directly in the manifest). The SQLite database's own `datasets`/
`dataset_closing_summaries` rows remain the single source of truth; the
manifest is never an independently editable second copy of that metadata.

## Backward compatibility

Every new column is additive (`ALTER TABLE ... ADD COLUMN`, applied only on
a writable connection — never on a read-only one, so opening an old file
read-only never mutates it). A database captured before 0V:

- has no `trading_date`/`instrument_id`/`lifecycle_state` columns at all —
  `load_dataset_trading_context` returns `(None, None)` and
  `load_dataset_lifecycle_state` returns `None` (untracked, never fabricated
  as `OPEN`).
- has no widened provenance columns — `bid_price`, `aggressor_side`, etc. on
  `DxLinkTimeAndSaleProvenance` load as `None` for every pre-0V row.
- is fully readable by every existing accepted analysis command (VWAP,
  Volume Profile, developing timeline, visualization) with **zero** change
  in output — proven against the real accepted 0L dataset
  (`es_20260823T231601Z_997555.sqlite3`), read-only, unmodified.

## Runtime data location

Default output remains under `apps/dicks_laboratory/data/` (git-ignored). No
OneDrive/cloud-sync behavior is introduced. The operational principle from
0U stands: an actively-written SQLite file must live on local Linux/WSL
storage, never a synced directory — this is documented convention, not
(yet) enforced in code (0U identified this as the same gap; still open).

## CLI

```bash
uv run python scripts/dicks_lab_collect_es.py \
  --symbol /ESU6 \
  --duration 3m \
  --data-dir apps/dicks_laboratory/data \
  --max-reconnect-attempts 5
```

- `--duration`: bounded session length (`3m`, `90s`, `2h`, ...). Always
  bounded — this is not an unbounded daemon yet.
- `--data-dir`: local runtime directory (default `apps/dicks_laboratory/data`).
- `--max-reconnect-attempts`: reconnect budget before `INTERRUPTED`.
- Prints a compact JSON summary on exit: dataset id/path, instrument, trading
  date, state, counts, gap count, reconnect count, first/last `source_order`,
  checksum, manifest path. Exit code `1` if the dataset ended `INTERRUPTED`.

Credentials are resolved exactly as the existing `dicks_lab_capture_dataset.py`
does (`TastytradeClient` + `.env`) — no new credential-handling code, and
nothing from this pipeline persists a token, account ID, or auth header
anywhere in SQLite, the manifest, or logs.

## Real acceptance capture (this phase)

A real 2-minute ES capture was run against the live feed on 2026-08-24
(21:45–21:47 CT, trading date 2026-08-25):

```
dataset_id: c3abc88c-9ad3-4749-bf8a-f7247b7974c5
state: FINALIZED
accepted_trade_count: 208
deferred_event_count: 0
rejected_record_count: 0
known_gap_count: 0
reconnect_count: 0
first/last source_order: 1 / 208
checksum verified: yes
collector_git_commit: 2ff1e2796abc8e94f38e4e7a4deab49408e02896
```

Accepted-NEW source metadata parity confirmed live (sample row): `event_
classification=NEW`, `event_flags=0`, `exchange_code=G`, `bid_price=7671.25`,
`ask_price=7671.50`, `aggressor_side=SELL`, `spread_leg=0`,
`extended_trading_hours=0`, `valid_tick=1` — all durably present, none
fabricated. The existing `dicks_lab_analyze_vwap.py` CLI reads this new
dataset correctly with zero changes.

## Limitations / deliberate scope decisions

- **Not yet a true always-on daemon.** An overall Human `duration_seconds`
  deadline still bounds the whole run (potentially spanning many trading
  dates and maintenance intervals in sequence). Genuinely unattended,
  indefinite operation is `weasel`'s eventual deployment, gated on Phase 0W.
- **Wait-for-session-open is now implemented** (0V-A correction): if invoked
  during the maintenance interval or outside the session entirely,
  `run_long_horizon_capture` computes the next session open
  (`next_session_open_after`) and sleeps until then (capped at the overall
  Human deadline) rather than failing immediately. Only a duration that
  expires entirely within a closed interval (never reaching any session
  open) raises a clear "no dataset was ever opened" error — a truthful
  no-capture result, never a fabricated empty dataset.
- **No periodic artificial reconnects** (0V-A correction, superseding the
  original 0V poll-interval design): a healthy connection persists for the
  entire span of one trading date's session, bounded only by that session's
  own scheduled close or the Human deadline — never by a fixed polling
  timer. Real multi-hour continuous-connection behavior under actual network
  conditions is still validated empirically in Phase 0W, not claimed
  complete from unit tests alone.
- **Single instrument at a time.** `InstrumentCaptureSpec` is generic, but
  0V does not implement simultaneous multi-instrument capture.
- **No WAL, no concurrency tuning.** Single-writer SQLite semantics
  preserved as-is; performance/concurrency tuning is explicitly deferred to
  0W's empirical measurement.
- **No standalone Quote-stream capture.** Deferred to 0W's measurement per
  0U §19 — only trade-time `bidPrice`/`askPrice` (already inline on
  TimeAndSale) are retained now.
- **No TPO, OHLC, delta, AI tutor, or GUI work** — 0U already established
  current+future retained trade data is sufficient for these; they remain
  separate, unimplemented feature work.
- **No contract-roll policy.** `InstrumentCaptureSpec` accepts an exact
  contract; choosing *which* contract to run remains a Human/later-phase
  decision.

## K9/DXLink change

One generic, backward-compatible, tested change: `DxLinkCollector._receive`
now wraps *any* exception during `socket.recv()` (not only `TimeoutError`)
as a `DxLinkError`, so a genuinely dropped connection (e.g. `websockets`'
`ConnectionClosed`) reliably surfaces as a detectable disconnect signal for
reconnect orchestration, rather than propagating an arbitrary
transport-specific exception. No trading semantics changed; existing K9
tests pass unmodified, and a new test proves the wrapping behavior.
