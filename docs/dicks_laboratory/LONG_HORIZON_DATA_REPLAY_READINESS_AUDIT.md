# Phase 0U — Long-Horizon Data & Replay Readiness Audit

**Date:** 2026-08-24
**Accepted baseline commit:** `c2c1491` (Phase 0T — Developing Profile Visualization, accepted/closed)
**Scope:** Architecture audit + source-data retention audit + replay readiness analysis + long-horizon storage design. No production code changed. No new tables. No live-capture, DXLink client, or analytics changes.

This document is intentionally self-contained. It should be usable by a future reader (Human or AI) without needing this conversation's history.

**Human-confirmed project constraint (2026-08-24):** long-horizon local archival is permitted for this personal-use research project — the Human reviewed the actual Tastytrade/dxFeed subscriber agreement and confirmed months-long personal archival is allowed for personal use. This does **not** extend to any inference about redistribution or publication rights, which remain explicitly out of scope for this project and this audit. See §39 for the full finding.

---

## 1. Purpose

Before Dick's Laboratory begins collecting `/ES` market data intended to be kept for months or years, this audit inventories:

- which DXLink provider fields currently reach the process;
- which of those are durably persisted, and where;
- which are silently discarded, and whether that loss is recoverable;
- what future capabilities (replay, TPO, AI tutoring, GUI annotation) depend on which facts;
- what the minimum durable-collection contract for Phase 0V should be.

Governing principle: **data not retained today may be impossible to reconstruct tomorrow** — but "store everything forever" is not a policy. The goal is an intentional, justified retention boundary.

---

## 2. Method

- Read the actual current implementation end-to-end: `models.py`, `dxlink_timesales.py`, `store.py` (schema + queries), `effective_tape.py`, `rejections.py`, `quality.py`, `capture_lifecycle.py`, `audit.py`, `live_capture.py`, `historical_csv.py`, `fixture.py`, and the K9 DXLink client (`K9/src/K9/tastytrade/dxlink.py`).
- Queried the real accepted 0L dataset (`apps/dicks_laboratory/data/es_20260823T231601Z_997555.sqlite3`) read-only via `sqlite3` for empirical row counts, ranges, and file size. The database's mtime and content were not modified.
- Researched authoritative dxFeed API documentation (`docs.dxfeed.com`) for `TimeAndSale`, `Quote`, `EventFlags`, and the dxFeed terms-of-use pages, plus the DXLink WebSocket protocol used by Tastytrade. Findings are cited with URLs; anything not confirmed by a fetched source is marked as inferred from code, not provider documentation.
- No code was written except this document. No datasets, schema, or dependencies were changed.

---

## 3. Current Durable Data Architecture (as implemented today)

```
DxLinkSourceEvent (K9, raw source-shaped dict of requested fields)
        |  received_at = datetime.now(UTC) at socket-frame-parse time
        v
source_records_from_events() -> DxLinkTimeAndSaleSourceRecord (dxlink_timesales.py)
        |  assigns source_order (per-capture-run 1..N, in receipt order)
        v
normalize_dxlink_time_and_sales()
        |
        +--(type == "NEW", validTick == True, symbol matches, well-formed)---+
        |                                                                    v
        |                                            AcceptedDxLinkTimeAndSaleNormalization
        |                                              -> TradeObservation (canonical)
        |                                              -> DxLinkTimeAndSaleProvenance (partial source facts)
        |
        +--(type in {CORRECTION, CANCEL})----------------------------------->
        |                                            DeferredDxLinkTimeAndSale
        |                                              (FULL source_record retained, unconditionally)
        |
        +--(fails NEW validation: bad symbol/type/tick/price/size/index/seq)->
                                                     NormalizationRejection
                                                       (reason only, NO source payload retained)
        v
LaboratoryStore (SQLite, one file per capture run)
        v
reconstruct_effective_tape()  <-- combines TradeObservation + provenance + deferred, in-memory, on demand
        v
analytics (VWAP / Volume-at-Price / POC / Value Area / developing series) — all recomputed on demand, never persisted
```

Key modules/classes:

| Stage | Module | Type |
|---|---|---|
| Raw source event | `K9/tastytrade/dxlink.py` | `DxLinkSourceEvent` (process memory only) |
| Source-shaped record | `dxlink_timesales.py` | `DxLinkTimeAndSaleSourceRecord` (process memory only, until persisted piecewise) |
| Canonical trade | `models.py` | `TradeObservation` (durable, `trade_observations` table) |
| NEW provenance | `dxlink_timesales.py` / `store.py` | `DxLinkTimeAndSaleProvenance` (durable, **partial** fields, `observation_source_provenance` table) |
| Deferred CORRECTION/CANCEL | `dxlink_timesales.py` / `store.py` | `DeferredDxLinkTimeAndSale` (durable, **full** source record, `deferred_dxlink_timesale_events` table) |
| Rejection | `rejections.py` / `store.py` | `NormalizationRejection` (durable, reason only, `normalization_rejections` table) |
| Capture lifecycle | `quality.py` / `capture_lifecycle.py` | `DatasetQualityEvent` (durable, `dataset_quality_events` table) |
| Effective tape | `effective_tape.py` | `EffectiveTrade` (**derived, never persisted** — recomputed from durable tables every time) |

For every stage:

| Stage | Received from provider | Retained only in memory | Persisted durably | Derived later |
|---|---:|---:|---:|---:|
| Raw `DxLinkSourceEvent.fields` | YES | YES (until normalized) | NO (not as a whole) | — |
| `DxLinkTimeAndSaleSourceRecord` (full, all requested fields) | — | YES | **partially** (full only if CORRECTION/CANCEL; partial if accepted NEW; reason-only if rejected) | — |
| `TradeObservation` | — | — | YES | — |
| `DxLinkTimeAndSaleProvenance` (NEW) | — | — | YES (subset of fields) | — |
| `DeferredDxLinkTimeAndSale` | — | — | YES (full source record) | — |
| `EffectiveTrade` / effective tape | — | — | **NO** | YES, recomputed from `TradeObservation` + provenance + deferred on every access |
| VWAP / Volume Profile / POC / Value Area / developing series | — | — | NO | YES, recomputed on demand |

This asymmetry — **full source record retained for CORRECTION/CANCEL but only a partial subset retained for accepted NEW trades** — is the single most important finding of this audit (§7, §12, §23).

---

## 4. Current SQLite Schema (from `store.py`, verified against the live 0L database)

| Table | Purpose | Primary identity | Key timestamps | Source ordering | Source identifiers | Market fields | Lineage |
|---|---|---|---|---|---|---|---|
| `datasets` | One bounded capture run | `dataset_id` (UUID) | `capture_started_at`, `capture_ended_at` | — | `source_locator` (free-text label, not a secret) | — | `parent_dataset_id` (for derived/synthetic only) |
| `instruments` | Canonical futures contract identity | `canonical_id` (e.g. `FUTURE:CME:ES:2026-09`) | — | — | — | exchange/root/expiration | — |
| `trade_observations` | Canonical accepted NEW trades | `observation_id` (UUID) | `event_timestamp` | `dataset_sequence` (1..N, acceptance order) | — | `price`, `size`, `trade_action` | FK to `datasets`, `instruments` |
| `observation_source_provenance` | Partial source facts for one accepted NEW trade | `observation_id` (1:1 with trade) | `received_at` | `source_order` | `source_index`, `source_sequence`, `source_trade_id` | — (no price/size — redundant with `trade_observations`, correctly) | FK to `trade_observations` |
| `deferred_dxlink_timesale_events` | Full source record for CORRECTION/CANCEL | `deferred_event_id` (UUID) | `event_time`, `received_at` | `source_order` | `source_index`, `source_sequence`, `source_trade_id` | full: price, size, bid/ask, sale conditions, aggressor, spread leg, extended hours, valid tick, event flags, exchange code | FK to `datasets` |
| `normalization_rejections` | Audit evidence for records that failed NEW validation | `rejection_id` (UUID) | **none** | `source_order` | — (only `source_record_ref` string) | — | FK to `datasets` |
| `dataset_quality_events` | Capture lifecycle + gap evidence | `event_id` (UUID) | `observed_at` or `interval_start`/`interval_end` | — | — | — | FK to `datasets`; `quality_event_links` join table for supporting evidence |
| `quality_event_links` | Links a derived gap to its supporting lifecycle events | composite (`event_id`, `link_sequence`) | — | `link_sequence` | — | — | FK both ways to `dataset_quality_events` |

All timestamps are stored as ISO-8601 UTC text (`_timestamp_text`/`_timestamp_from_text` in `store.py`); the store rejects any non-UTC-aware timestamp at write time. All prices/sizes are stored as `TEXT` (Decimal-preserving strings), never as floating point — confirmed by `_decimal_text`/`Decimal(row["price"])`.

---

## 5. TimeAndSale Field Retention Matrix

Fields requested by the K9 client (`_SOURCE_EVENT_FIELDS["TimeAndSale"]`, `K9/tastytrade/dxlink.py:55-76`), cross-referenced against the actual persistence paths in `store.py` and dxFeed's documented field semantics ([TimeAndSale — dxFeed API 3.350](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html)):

| Source field | Provider meaning | Received? | Durable for accepted NEW? | Durable for CORRECTION/CANCEL? | Where persisted | Derivable later? | Future usefulness | Retention recommendation |
|---|---|---:|---:|---:|---|---:|---|---|
| `eventSymbol` | Streamer symbol | YES | Indirectly (via `instruments` FK, not the raw string) | YES (`event_symbol` column) | `trade_observations`→`instruments`; `deferred_dxlink_timesale_events.event_symbol` | YES for NEW (instrument is a hard requirement already) | Symbol audit / multi-instrument disambiguation | SHOULD retain raw symbol for NEW too (currently implicit only) |
| `time` (event time, ms) | Original event timestamp | YES | YES (`event_timestamp`) | YES (`event_time`) | `trade_observations.event_timestamp`; deferred table | — | Core analytical truth | MUST retain (already retained) |
| `type` (NEW/CORRECTION/CANCEL) | dxFeed `TimeAndSaleType` | YES | Implicit (`trade_action = NEW` always, since only NEW is accepted into `trade_observations`) | YES (`event_classification`) | — | YES (accepted rows are always NEW by construction) | Lifecycle reconstruction | MUST retain (already retained for deferred; implicit-but-safe for NEW) |
| `index` | Composed of time+sequence; **used by dxFeed itself for correction/cancellation correlation** ([TimeAndSale docs](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html)) | YES | YES (`source_index`) | YES (`source_index`) | `observation_source_provenance`; deferred table | NO — this is the correlation key; if lost, CORRECTION/CANCEL could not be matched to their target NEW at all | Effective-tape reconstruction (currently used exactly this way, `effective_tape.py`) | MUST retain (already retained) |
| `sequence` | Distinguishes same-`time` events; **not required to be unique or sequential** ([TimeAndSale docs](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html)) | YES | YES (`source_sequence`) | YES (`source_sequence`) | both | Partially — a secondary key, not a completeness proof | Tie-breaking, NOT gap detection | MUST retain (already retained) |
| `tradeId` | Identifies the trade for correction/cancellation | YES | YES (`source_trade_id`) | YES (`source_trade_id`) | both | possibly, from `index`, but not guaranteed identical semantics | Cross-check against `index`-based correlation | SHOULD retain (already retained) |
| `eventFlags` | Snapshot/transaction bits; **observed as always zero under our current regular (non-time-series) subscription** ([TimeAndSale docs](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html); [EventFlags reminder](https://dxfeed.com/dxfeed-eventflags-field-reminder/)) | YES | **NO — not persisted for accepted NEW at all** | YES (`event_flags`) | deferred table only | Not needed for current live NEW normalization logic, but dxFeed's own indexed/time-series event model uses event flags for snapshot/transaction state (`SNAPSHOT_BEGIN`/`SNAPSHOT_END`/`TX_PENDING`) in applicable subscription modes, and future reconnect/history-recovery work may make this useful | Cheap to retain now that §25 recommends widening NEW provenance to source-field parity anyway | **SHOULD retain** as part of NEW source-field parity (§25/§43) — cheap future-proofing, not because current normalization needs it |
| `exchangeCode` | Exchange where the event occurred | YES | **NO** | YES (`exchange_code`) | deferred table only | NO once discarded | Multi-venue/exchange studies | SHOULD retain for NEW (currently lost) |
| `price` | Trade price | YES | YES (`price`) | YES (`price`) | `trade_observations`; deferred table | — | Core | MUST retain (already retained) |
| `size` | Trade size | YES | YES (`size`) | YES (`size`) | `trade_observations`; deferred table | — | Core | MUST retain (already retained) |
| `bidPrice` | BBO bid at time of sale | YES | **NO** | YES (`bid_price`) | deferred table only | NO once discarded (no independent Quote capture today — see §21) | Trade-at-bid/aggressor cross-check | SHOULD retain for NEW (currently lost) |
| `askPrice` | BBO ask at time of sale | YES | **NO** | YES (`ask_price`) | deferred table only | NO once discarded | Same as above | SHOULD retain for NEW (currently lost) |
| `exchangeSaleConditions` | Feed-specific sale-condition string | YES | **NO** | YES | deferred table only | NO | Filtering unusual prints (auction, odd-lot, etc.) | SHOULD retain for NEW (currently lost) |
| `tradeThroughExempt` | Regulatory exemption flag | YES | **NO** | YES | deferred table only | NO | Low priority for futures (a Reg NMS equities concept; unclear applicability to CME futures — see note below) | MAY retain |
| `aggressorSide` | Buyer/seller-initiated indicator | YES | **NO** | YES | deferred table only | NO | Future order-flow/delta study (§23) | SHOULD retain for NEW (currently lost) |
| `spreadLeg` | Marks a spread-transaction component | YES | **NO** | YES | deferred table only | NO | Filtering multi-leg prints out of single-instrument profile | SHOULD retain for NEW (currently lost) |
| `extendedTradingHours` | Outside-RTH marker | YES | **NO** | YES | deferred table only | NO | Session-classification cross-check (we already derive our own session windows in `sessions.py`, but this is independent provider evidence) | SHOULD retain for NEW (currently lost) |
| `validTick` | Whether this counts as a valid intraday tick (CORRECTION counts; CANCEL does not — [TimeAndSale docs](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html)) | YES | Implicit (only `validTick == True` NEW rows are ever accepted) | YES (`valid_tick`) | — | YES for NEW (gate already enforces it) | Confirms our NEW-acceptance gate matches provider semantics | MUST retain (already effectively retained via the gate) |
| `timeNanoPart` | Sub-millisecond precision | **NOT requested** | NO | NO | — | N/A | Unclear; ES trade timing is unlikely to need sub-ms precision for Volume Profile work | SAFE to omit unless a future need for sub-millisecond ordering emerges |
| `received_at` (ours, not a dxFeed field) | Local receipt wall-clock time | YES (assigned in K9 at frame-parse time) | YES (`received_at`) | YES (`received_at`) | both | — | Feed-knowledge replay, latency study | MUST retain (already retained) |
| `source_order` (ours) | Per-capture-run receipt sequence | YES (assigned in `dxlink_timesales.py`) | YES | YES | both, **and `normalization_rejections`** | — | Deterministic replay ordering | MUST retain (already retained) |

**Note on `tradeThroughExempt`:** dxFeed's own documentation describes this as "a flag character indicating regulatory exemption status," a concept with clear meaning for Reg NMS-governed US equities trade-through rules. Its applicability/semantics for CME futures TimeAndSale data is not confirmed by the fetched documentation and should be treated as *unclear, needs provider/CME-specific research* rather than assumed irrelevant.

---

## 6. Fields We Currently Throw Away

For every field reaching the process for an **accepted NEW trade** that is not durably retained (`exchangeCode`, `bidPrice`, `askPrice`, `exchangeSaleConditions`, `tradeThroughExempt`, `aggressorSide`, `spreadLeg`, `extendedTradingHours`, `eventFlags`):

- **What is discarded:** the full `DxLinkTimeAndSaleSourceRecord` for the NEW branch is held in memory only long enough to build `TradeObservation` + the narrow `DxLinkTimeAndSaleProvenance`; the record object itself is never persisted for the NEW path (`normalize_dxlink_time_and_sales`, `dxlink_timesales.py:166-184`; `store.save_dxlink_time_and_sale_provenance`, `store.py:290-313`).
- **Why it was originally unnecessary:** Phase 0C-era design deliberately kept the canonical schema minimal — `TradeObservation` needed only `price`/`size`/`event_timestamp` for VWAP/Volume-Profile analytics, and provenance existed only to support audit (`source_record_ref`) and lifecycle correlation (`source_index`/`source_sequence`/`source_trade_id`).
- **Whether future capabilities could need it:** yes, specifically §21-23 (order-flow/aggressor study, BBO-at-trade cross-check, spread-leg filtering, multi-exchange studies).
- **Whether it can be reconstructed later:** **NO.** Once a `NEW` `DxLinkTimeAndSaleSourceRecord` is normalized and its provenance saved, the discarded fields are permanently gone — there is no independent record of them anywhere in the schema. This is a genuine, irreversible loss for every accepted NEW trade in every dataset captured so far.
- **Classification:** **worth retaining before serious collection** for `bidPrice`, `askPrice`, `aggressorSide`, `spreadLeg`, `extendedTradingHours`, `exchangeSaleConditions`, `exchangeCode`, and — as cheap future-proofing rather than a current normalization need — `eventFlags` (observed as always zero under our current regular subscription mode, but dxFeed's indexed/time-series event model uses it for snapshot/transaction state in other subscription modes, and future reconnect/history-recovery work may make it useful; since §25 already recommends widening NEW provenance to full field parity, retaining `eventFlags` alongside the rest is essentially free); **safe to discard** for `timeNanoPart` (never requested, unlikely to matter at ms resolution for futures Volume Profile work); **unknown/needs provider research** for `tradeThroughExempt` (unclear applicability to CME futures, but MAY retain regardless since it is cheap once parity is adopted).

For **rejected records** (`NormalizationRejection`): the entire source payload is discarded — only `source_record_ref`, `source_order`, and `reason` survive. A rejected record's `time`/`price`/`size`/etc. are permanently unrecoverable. **Product Owner decision:** although rejections are expected to be rare (bad symbol, invalid tick, malformed field), this is promoted to a **MUST FIX** item (§44), not merely a lower-priority nicety — the governing principle is that *every* received market source event, regardless of disposition (accepted, deferred, or rejected), must preserve sufficient source-shaped evidence for independent future examination. Without it, the information that caused a rejection is irretrievably lost, and normalization policy itself can never be independently re-evaluated against real historical evidence — a serious collector cannot later ask "was this rejection rule too strict?" without the original data to check it against.

---

## 7. Canonical `TradeObservation` Audit

Actual fields (`models.py:97-121`): `observation_id`, `dataset_id`, `dataset_sequence`, `instrument`, `event_timestamp`, `price`, `size`, `trade_action`.

There is **no `received_timestamp` or `ingested_timestamp` field on `TradeObservation` itself.** Local receipt time exists only in the separate `observation_source_provenance.received_at` column (a 1:1 side table keyed by `observation_id`), not on the canonical trade record.

- **`event_timestamp`** = the market event's own time, as reported by the exchange/provider (dxFeed `time` field). This is what every accepted-0N/0Q/0R analysis anchors, scopes, and orders by. It answers: *when did this trade occur, according to the exchange?*
- **`received_timestamp`** (via provenance, not on `TradeObservation`) = when our process's socket-frame-parsing code stamped `datetime.now(UTC)` (`K9/tastytrade/dxlink.py:558`). It answers: *when did our collector learn this fact?*
- There is **no separate "ingestion"/"normalization" timestamp** distinct from `received_at` anywhere in the pipeline — normalization happens synchronously, in the same call, immediately after receipt (`live_capture.py:91-111`), so a third timestamp would currently be redundant. See §16 for the explicit ingestion-time question.

`dataset_sequence` is a monotonic 1..N acceptance-order counter, **not** a market-time-derived value; it happens to track `source_order` 1:1 in the real 0L sample only because zero rejections/corrections occurred in that capture.

Future questions and which timestamp they depend on:
- *"What was VWAP at market time T?"* → `event_timestamp` (already the accepted-phase convention).
- *"What had we actually received by wall-clock T?"* → `received_at` (exists, but only per-observation via provenance, and **not at all for rejected/deferred-target correlation beyond the deferred table's own `received_at`**).
- *"How much latency did our collector have?"* → `event_timestamp` vs `received_at`, both exist for NEW trades; achievable today.

---

## 8. Accepted NEW Event Source Provenance

Durable evidence for one accepted `NEW`, combining `TradeObservation` + `DxLinkTimeAndSaleProvenance`:

| Survives? | Field |
|---|---|
| YES | source index (`source_index`) |
| YES | source sequence (`source_sequence`) |
| YES | trade ID (`source_trade_id`) |
| YES | source order (`source_order`) |
| YES | source event time (`event_timestamp` on `TradeObservation`) |
| YES | received_at |
| Implicit only | classification (always `NEW` by construction — not stored as a literal string per-row for the accepted path, unlike the deferred table which stores `event_classification` explicitly) |
| **NO** | event flags |
| **NO** | bid/ask-at-sale |
| **NO** | aggressor side |
| **NO** | sale conditions |
| **NO** | exchange code |
| **NO** | spread leg / extended trading hours flags |

**Conclusion:** we can reconstruct the original source event's *identity, timing, and price/size* for an accepted NEW trade, but **not** its full original source-shaped record. A future re-normalization against new rules (e.g. "what if we now want to exclude spread-leg prints from the profile?") **cannot** be retroactively applied to already-captured NEW trades — that information is gone the moment the trade was accepted.

---

## 9. CORRECTION / CANCEL Evidence

`deferred_dxlink_timesale_events` retains the **complete** `DxLinkTimeAndSaleSourceRecord` for every CORRECTION/CANCEL: `event_symbol`, `event_time`, `event_classification`, `source_index`, `source_sequence`, `source_trade_id`, `event_flags`, `exchange_code`, `price`, `size`, `bid_price`, `ask_price`, `exchange_sale_conditions`, `trade_through_exempt`, `aggressor_side`, `spread_leg`, `extended_trading_hours`, `valid_tick`, `received_at` — every field the K9 client requests, with nothing dropped (`store.py:315-345`).

**Do we already retain enough durable evidence to replay CORRECTION/CANCEL events at the moment they were received?**

**Partially.** We retain `received_at` (wall-clock receipt time) and `source_order` (receipt-order position) for every CORRECTION/CANCEL — so we *can* place a correction/cancel at a specific point in wall-clock time and in receipt order relative to other events **in the same capture run**. What we cannot do is combine this with an equivalently-complete picture of the accepted NEW events around it, because (§8) the NEW side is missing several fields. A replay that says "at receipt time T, the feed told us: NEW trade at price P size S with bid/ask B1/A1, then five events later a CORRECTION arrived changing it to P2/S2" is achievable for the CORRECTION's own fields but not for a full-fidelity NEW-side comparison.

---

## 10. Timestamp / Ordering Semantics

| Field | Role |
|---|---|
| `event_timestamp` | Market-time truth, as reported by the exchange via the provider. The correct axis for **retrospective market reconstruction** (§I) — "what did the market actually do." |
| `source_index` | dxFeed's own index, combining time+sequence, and — per dxFeed's documentation — the mechanism dxFeed itself uses to correlate a CORRECTION/CANCEL with its target NEW event ([TimeAndSale docs](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html)). This is exactly how `effective_tape.py` already uses it (`active[item.source_index]`), which is now confirmed to match documented provider intent rather than being an ad hoc assumption.
| `source_sequence` | A same-timestamp tie-breaker; **not** documented as unique or gapless, so it cannot be used as a completeness proof (§19). |
| `source_order` | Our own receipt-order counter, assigned once per capture run in `dxlink_timesales.py`. This is the correct axis for **feed-knowledge / point-in-time replay** (§J) — "what had we received, in the order we received it." |
| `received_at` | Wall-clock receipt time, independent of and later-or-equal to `event_timestamp`. Needed alongside `source_order` for feed-knowledge replay to assign real timestamps to "as of this wall-clock instant" queries. |
| `dataset_sequence` | Acceptance-order counter for the canonical `trade_observations` table only (NEW trades that passed validation) — a derived convenience, not independent evidence. |

**Retrospective market reconstruction** should order by `event_timestamp` (already how every accepted analysis phase 0N-0T works) with `source_index` used only to correlate corrections/cancels to their target — never to reorder the timeline itself.

**Point-in-time feed-knowledge replay** must order by `(source_order, received_at)` — the sequence in which facts actually arrived at the process — which is exactly the axis `reconstruct_effective_tape` already sorts its internal lifecycle list by (`(item.source_order, item.source_index, item.source_record_ref)`, `effective_tape.py:92`), but the *result* of that reconstruction is thrown away as soon as the final `active` dict is produced — no intermediate step-by-step ledger survives (this is the exact 0R design-checkpoint finding, reaffirmed here for the general case).

---

## 11. Ingestion Time

`ingested_timestamp` does not exist anywhere in the current schema, and — given normalization happens synchronously inside the same event-received callback as receipt (`live_capture.py:91-111`) — it would currently be **identical** to `received_at` in every case. It adds no independent durable value **today**.

It could add value in a *future* architecture where normalization is deferred, batched, or asynchronous (e.g. a queue between the socket-reader and the normalizer) — in that design, `received_at` (network arrival) and `ingested_timestamp` (normalization applied) could diverge and both would matter for feed-knowledge replay. This is a **forward-looking distinction to keep in mind for Phase 0V**, not a current gap, since 0V's premise (resilient long-running capture) may well introduce exactly this kind of buffering/backpressure architecture.

---

## 12. Capture Lifecycle Audit

Evidence types (`quality.py:12-19`): `CAPTURE_STARTED`, `SOURCE_CONNECTED`, `SOURCE_DISCONNECTED`, `SOURCE_RECONNECTED`, `CAPTURE_STOPPED`, `KNOWN_GAP`, `SUSPECTED_GAP`.

What the **live** capture path (`live_capture.py`) actually emits: `CAPTURE_STARTED` (before collection), `SOURCE_CONNECTED` (once, on the collector's `on_connected` callback), and exactly one of `CAPTURE_STOPPED` (normal completion) or `SOURCE_DISCONNECTED` (on `DxLinkError`). **`SOURCE_RECONNECTED` is never emitted by the live path** — it exists only in the historical CSV lifecycle importer (`capture_lifecycle.py`), a different, non-live data source. This confirms `capture_es_timesales_dataset` is a **single bounded run with no reconnect logic at all** — any `DxLinkError` ends the entire capture. This is expected for the phase it was built in ("Human-invoked, explicitly bounded durable DXLink TimeAndSale capture workflow," `live_capture.py:1`) but is a direct, explicit reason Phase 0V is needed before serious always-on collection.

Each lifecycle event has an `observed_at` UTC timestamp and is stored with its own `event_id`, so events **can** be interleaved with market source events on a shared wall-clock timeline in a future replay (join on `observed_at`/`received_at` ordering) — the data model supports this; only the live-path reconnect *behavior* is missing, not the lifecycle *schema*.

`derive_gap_conclusions` (`capture_lifecycle.py:101-135`) can derive a `KNOWN_GAP` interval strictly from an explicit disconnect→reconnect pair, gated by an explicit `CaptureLossPolicy`. This machinery exists but is currently exercised only by the historical CSV import path, never by live capture (since live capture never reconnects).

---

## 13. Completeness / Gap Evidence Audit

Reaffirmed: **no retained trades for N seconds is not proof of a capture gap** — nothing in the current schema or analysis layer claims otherwise (`quality.py`'s `summarize_dataset_quality` counts only *explicit* `KNOWN_GAP`/`SUSPECTED_GAP` evidence rows, never infers one from trade timing).

What current durable evidence **can** tell us: exactly when `CAPTURE_STARTED`/`SOURCE_CONNECTED`/`CAPTURE_STOPPED`/`SOURCE_DISCONNECTED` occurred, and (only via the historical CSV path) explicit disconnect/reconnect-derived known gaps.

What current durable evidence **cannot** tell us: whether the live collector silently missed events *while still connected* (e.g. a slow consumer, a dropped WebSocket frame the OS/library didn't surface as an error, or a server-side conflation). Per §19/§14 below, dxFeed's own `sequence`/`index` fields cannot be used as a gap-detection mechanism because they are explicitly not documented as gapless or unique. A serious collector would need independent evidence: provider heartbeats (not currently used — the K9 client sends client-initiated `KEEPALIVE` pings every 20s but does not appear to depend on or record any server-originated heartbeat/pong for health evidence beyond it not erroring), connection-health monitoring, explicit reconnect evidence, and subscription acknowledgement tracking (`FEED_CONFIG` is currently only used to confirm the accepted field set, not stored as durable evidence that the subscription was actually live at a given instant).

No completeness *score* is proposed here, per instruction — only an inventory of what evidence exists and does not.

---

## 14. Can Current Durable Data Support Feed-Knowledge Replay? — Explicit Conclusion

> **PARTIAL.**

We can reconstruct the ordered **receipt** sequence of accepted-NEW and CORRECTION/CANCEL events (via `source_order` + `received_at`, present on both paths) with **high fidelity for CORRECTION/CANCEL** (full source record) but **reduced fidelity for NEW** (missing `eventFlags`, `exchangeCode`, `bidPrice`/`askPrice`, `exchangeSaleConditions`, `tradeThroughExempt`, `aggressorSide`, `spreadLeg`, `extendedTradingHours`).

Rejected records cannot be replayed at all beyond "a record was rejected here, for this reason" — their content is gone.

Blockers, concretely:

- Missing NEW-side source fields (§6, §8) — the largest gap.
- No unified receipt-order ledger spanning accepted + deferred + rejected in one place — reconstructing the full interleaved stream today requires joining three separate tables (`trade_observations`+`observation_source_provenance`, `deferred_dxlink_timesale_events`, `normalization_rejections`) by `source_order`, which is *possible* (the ordering key exists uniformly on all three) but not provided as a single queryable view today.
- No live reconnect evidence to interleave (§12) — not a data-loss blocker for a single bounded run, but a real one for a multi-hour/day always-on capture.

---

## 15. Retrospective vs. Feed-Knowledge Replay — Explicit Conclusion

**Retrospective market-history replay** ("what does the market look like after all known corrections/cancels are reconciled"): **YES, already fully supported** — this is exactly what `reconstruct_effective_tape` + every accepted 0Q/0R/0S/0T analysis already does, ordering strictly by `event_timestamp` (with `source_index`-based correlation for corrections/cancels). Nothing new is needed for this replay type; it is the current default and already validated end-to-end.

**Point-in-time / feed-knowledge replay** ("at 09:47:30, what had actually reached us"): **PARTIAL today**, per §14 — the *ordering* infrastructure (`source_order`, `received_at`) is substantially present and exists uniformly across accepted/deferred/rejected records, but the *content* fidelity is asymmetric (full for CORRECTION/CANCEL, partial for NEW, reason-only for rejections), and no live-path reconnect evidence exists yet to interleave. These are **different replay products** and must not be conflated: today's `EFFECTIVE_TAPE` developing series (0R/0S/0T) is explicitly retrospective, and this audit confirms that labeling is correct and should remain — building a true feed-knowledge replay is a larger, separate undertaking gated on closing the NEW-side and rejected-side field gaps first.

**Target state after the Phase 0V retention changes (§43/§44):** once NEW-side field parity and rejected-record source-field parity are adopted, feed-knowledge replay should become **materially reconstructable** from durable event receipt/order evidence for datasets captured going forward — subject always to whatever reconnect/loss boundaries actually exist (§16/§17). This is **not** a claim of feed completeness or a guarantee that every disconnect window will be recoverable; it is a statement that the *retained-content* blocker (as opposed to the *live-monitoring* blocker) would be closed. Existing datasets captured before this fix remain permanently limited to today's PARTIAL fidelity (§8, §42).

**No-future-knowledge invariant (critical for any future AI tutor "replay" feature, §23):**

```
market-time cutoff  ≠  feed-knowledge cutoff
```

Filtering by `event_timestamp < T` only prevents future-information leakage when the tape being filtered was itself built **without** applying any lifecycle event (correction/cancel) received after `T`. The accepted retrospective `EFFECTIVE_TAPE` is reconciled to its **final** state before any historical cutoff is ever applied to it, so:

```
retrospective effective tape + historical timestamp cutoff
        ≠
guaranteed no-future-information replay
```

A correction received at 09:50 that amends a 09:40 trade will already be baked into the effective tape's 09:40 entry — a replay paused at 09:45 using that tape would show the *corrected* price, which the collector did not actually know at 09:45. Canonical NEW-only replay avoids this specific leak (nothing is ever corrected) but then is not final corrected history; only a genuine point-in-time lifecycle reconstruction (§23, not yet built) would satisfy both properties at once. See §23 for the full mode-by-mode breakdown.

---

## 16. DXFeed Sequence / Reconnect Findings

From dxFeed's own documentation ([TimeAndSale — dxFeed API 3.350](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/TimeAndSale.html), [EventFlags reminder](https://dxfeed.com/dxfeed-eventflags-field-reminder/)):

- `index` is composed of time + `sequence`, and is documented as the mechanism used for correction/cancellation correlation — confirming our `effective_tape.py` design is aligned with provider intent, not merely convenient.
- `sequence` "does not have to be unique and does not need to be sequential" — **it cannot be used to detect missing events.** (Empirically confirmed against the real 0L dataset: `source_sequence` advances by 1-2 per event rather than a strict +1, consistent with this documented non-guarantee.)
- **Regular** (non-time-series) subscriptions — which is what our DXLink `FEED_SUBSCRIPTION` setup uses — produce `eventFlags` that are "always zero." Time-series/snapshot subscriptions (a different DXLink/dxFeed subscription mode, `DXFeedTimeSeriesSubscription`) use `eventFlags` for `SNAPSHOT_BEGIN`/`SNAPSHOT_END`/`TX_PENDING`/etc. **We do not use that subscription mode today**, so `eventFlags` currently carries no live analytical information for us — but per §6/§41, this is reclassified as **SHOULD retain** (cheap future-proofing alongside the rest of NEW source-field parity) rather than safe to discard outright, since a future reconnect/history-recovery mechanism could plausibly need it if a different subscription mode is ever adopted.
- The fetched EventFlags reminder page does not document whether a *regular* subscription (ours) receives any historical backfill/snapshot on resubscribe/reconnect; it only describes snapshot semantics for the time-series subscription mode. **This is an open question requiring further provider research or empirical testing before Phase 0V is designed** — the working (unconfirmed) assumption should be: *no automatic backfill occurs on reconnect for a regular subscription* — meaning any events during a disconnect are genuinely and permanently lost unless a redundant/parallel recovery mechanism is built.
- Community-sourced material (not authoritative dxFeed documentation, so treated as directional only) describes the modern DXLink WebSocket client ecosystem as generally including "robust error handling and reconnection logic" and exponential-backoff disconnect/reconnect hooks in at least one official Tastytrade SDK — suggesting reconnect is a known, solvable problem with established patterns, but our own K9 client (`DxLinkSourceCollector`) implements none of it today (§12).

---

## 17. Reconnect Implications (Conceptual, Not Implemented)

- Does TimeAndSale subscription resume only live events after reconnect? — **Assumed yes** (unconfirmed by fetched docs, per above) for a regular subscription; needs empirical verification in Phase 0V design.
- Is any historical recovery/snapshot delivered? — **Not documented for our subscription mode**; the time-series/snapshot subscription mode is a different, more complex API surface with its own event-flag protocol that would itself need adoption, entitlement, and design work (out of scope for 0V per this audit's recommendation — see §AJ/§AK).
- Can events during disconnect be recovered? — **Likely not**, from the same source, without switching subscription modes or having a redundant secondary feed. A gap during disconnect should be recorded as an explicit `KNOWN_GAP` (schema already supports this — §12), not silently absorbed.
- How would duplicates be identified? — `source_index`/`source_trade_id` correlation (already the mechanism for corrections) is the natural dedup key candidate for a future reconnect design; this audit does not design that mechanism, only notes the identifiers already exist to build it from.
- How should source ordering restart or continue? — `source_order` is currently scoped to one bounded capture run (`start_source_order` resets each call in `live_capture.py`/`dxlink_timesales.py`). A multi-day always-on collector needs an explicit decision here — this becomes a Phase 0V design question, not resolved by this audit.

**Product Owner decision, recorded here as a binding Phase 0V requirement:**

> Automatic recovery of TimeAndSale events missed during a normal disconnect/reconnect is **NOT proven** by anything found in this audit's provider-documentation research.

Therefore serious collection must follow this policy:

```
disconnect observed
    ↓
record lifecycle evidence (SOURCE_DISCONNECTED)
    ↓
reconnect / resubscribe
    ↓
record lifecycle evidence (SOURCE_RECONNECTED)
    ↓
do NOT assume disconnect-window events were recovered
    ↓
the interval becomes a KNOWN_GAP unless a future recovery
mechanism explicitly requests historical TimeAndSale data
for that interval AND produces explicit, durable evidence
that the interval was actually recovered
```

**`reconnect ≠ proof of gap recovery.`** A future recovery mechanism (e.g. a historical/time-series-subscription-based backfill, or a redundant secondary feed) is not precluded by this policy, but it must prove its own recovery with explicit evidence — reconnecting alone proves nothing about the disconnect window's content. This is now a **Phase 0V requirement**, not merely an open question; provider behavior around backfill may still be empirically investigated in 0V/0W (§50), but the architecture must not wait on that investigation before adopting this conservative default.

---

## 18. Quote Data Findings

- The K9 DXLink client already requests Quote fields generically (`_QUOTE_FIELDS = ("eventType", "eventSymbol", "eventTime", "bidPrice", "askPrice", "bidSize", "askSize")`, `K9/tastytrade/dxlink.py:14-22`), and `DxLinkSourceCollector.collect()` can subscribe to any `event_types` tuple the caller passes — **but `capture_es_timesales_dataset` only ever requests `("TimeAndSale",)`** (`live_capture.py:114`). **Quote is never subscribed to during ES capture today.**
- dxFeed's own documentation ([Quote — dxFeed API 3.346](https://docs.dxfeed.com/dxfeed/api/com/dxfeed/event/market/Quote.html)) confirms Quote is "a snapshot of the best bid and ask prices... representing the most recent information available about the best quote on the market at any given moment" — i.e. **BBO only**, not a full order book, and `bidTime`/`askTime` are documented as "by default transferred with seconds precision" (coarser than TimeAndSale's millisecond `time`).
- Nothing in the fetched documentation suggests Quote provides a complete historical quote tape by itself, independent of when the client happened to be subscribed and connected — it is a live-update stream like TimeAndSale, with the same reconnect/gap characteristics.

---

## 19. Quote Retention Recommendation

> **Defer until measured (0W), but plan the schema now.**

Reasoning:

- **Future AI-tutor usefulness:** real (aggressor/BBO context, "was this trade lifting the offer or hitting the bid," §26), but not required for the currently-accepted VWAP/Volume-Profile/Value-Area capabilities, which need only trade prints.
- **Replay usefulness:** Quote data would materially improve feed-knowledge replay and order-flow study, but is a genuinely separate, higher-volume stream (BBO updates are far more frequent than trades) with its own storage-growth question — exactly the kind of thing Phase 0W's empirical measurement should inform before committing to always-on retention.
- **Storage cost / event volume:** unmeasured; BBO updates on a liquid futures contract like ES can be substantially higher-frequency than trade prints. Should not be decided blind.
- **Ability to derive later:** **NO** — like TimeAndSale, a discarded Quote stream cannot be reconstructed after the fact. This argues for *not* discarding it forever once serious collection begins, but does not argue for retaining it *before* it has been measured.
- **Recommendation:** do not add Quote capture in 0V's first iteration; but Phase 0V's design should explicitly reserve the concept (e.g. leave room for a future `quote_observations`-shaped table) so that when 0W's soak test measures Quote volume/cost, adding it is additive, not a redesign. In the interim, `bidPrice`/`askPrice` **at time of trade** (already delivered inline on the TimeAndSale event itself, currently discarded for NEW per §6) is a cheap, already-available partial substitute for full BBO replay and should be retained regardless of the standalone-Quote decision.

**Explicit distinction — this is important and easy to conflate:**

```
retain TimeAndSale BBO context (bidPrice/askPrice at time of trade) NOW
        ≠
commit to a full standalone Quote-stream tape NOW
```

The first is cheap (already arrives inline on every TimeAndSale event, just needs the schema-widening already recommended in §25/§44), carries no independent storage-growth question, and is recommended as a **MUST FIX** item now (§44). The second is a separate, higher-volume, independently-measured decision that Phase 0W must inform before any permanent commitment — it is **not** decided here, and the `bidPrice`/`askPrice`-at-trade recommendation must not be read as an implicit decision to also capture full Quote.

---

## 20. Trade Metadata Retention Recommendation (for future order-flow study)

| Field | Recommendation | Reason |
|---|---|---|
| `aggressorSide` | **SHOULD retain** | Directly enables future buy/sell volume and delta study (§37 defers *implementing* delta, but the raw fact must exist first if delta is ever wanted; currently lost for NEW). |
| `bidPrice` / `askPrice` (at time of trade) | **SHOULD retain** | Cheapest available proxy for trade-at-bid/trade-at-ask context without a separate Quote stream; currently lost for NEW. |
| `exchangeCode` | **SHOULD retain** | Needed for any future multi-venue/exchange study; currently lost for NEW. |
| `exchangeSaleConditions` | **SHOULD retain** | Needed to filter unusual prints (auction prints, odd-lot, etc.) out of a clean Volume Profile if ever desired; currently lost for NEW. |
| `spreadLeg` | **SHOULD retain** | A spread-leg print arguably should not count toward a single-instrument outright Volume Profile; currently we cannot even identify which historical prints were spread legs. |
| `extendedTradingHours` | **MAY retain** | We already derive our own session windows (`sessions.py`); this is a convenient independent cross-check, not a hard requirement. |
| `validTick` | **MUST retain (already effectively is)** | The NEW-acceptance gate already enforces `validTick == True`; this is provider-confirmed correct behavior (§5), not something to weaken. |
| `tradeThroughExempt` | **MAY retain** | Unclear applicability to CME futures (§5 note) — cheap to store, low confidence it will ever be used. |

No delta/aggregate order-flow analytics are implemented or recommended for implementation here — this table only classifies raw-field retention.

---

## 21. TPO / Market Profile Readiness

Current durable trade data (`event_timestamp`, `price`, `size`) is **sufficient** to derive, for the retained coverage window:

- price presence by arbitrary time bracket (already how the 0R/0S/0T developing series works, just at 1/5/15-minute checkpoints instead of 30-minute TPO brackets — the same cumulative-prefix machinery generalizes trivially to any bracket width);
- 30-minute TPO brackets and letters (a presentation/bracketing concept over the same retained trades, not new source data);
- Initial Balance (first N brackets of a session — derivable from retained trades + the accepted session model, `sessions.py`);
- TPO POC and TPO Value Area (a different aggregation convention — count of *brackets* touching a price, not volume — but computable from the same retained `(price, event_timestamp)` pairs, no new fields needed);
- single prints (price levels touched in only one bracket — derivable the same way);
- session highs/lows (trivially derivable from retained `price`, already what `VolumeAtPriceProfile.lowest_price`/`highest_price` compute, just needs session-scoping instead of anchor-scoping, both of which already exist).

**Nothing about TPO/Market Profile requires information beyond what is already retained for NEW trades.** This is a pure future-analytics question, not a retention gap — consistent with the instruction not to implement it in 0U, and confirming Phase 0U need not add anything for future TPO work.

---

## 22. OHLC / Price-Bar Derivability

Deterministic 1/5/30-minute OHLC bars **can** be derived from current durable trades for the retained coverage window, using the same wall-clock-aligned bracket mechanism 0R already implements (open = first trade's price in the bracket, high/low = max/min price, close = last trade's price, using the accepted half-open `[start, end)` convention).

Limitations, all inherited from the accepted 0N/0Q/0R coverage model (no new limitation introduced by bars specifically):

- **Capture begins mid-bar:** the first bar's "open" would only reflect the first *retained* trade, not the bar's true market open if capture started partway through it — exactly the same `DATASET_BEGINS_AFTER_ANCHOR` distinction already modeled and reported.
- **Data gaps:** a bar spanning an unrecorded gap would silently show artificially flat/missing price action — the same "absence of retained events is not evidence of absence of market activity" principle (§13) applies to bars exactly as it does to the developing-profile snapshots.
- **Source completeness unknown:** since we cannot currently prove zero silent event loss while connected (§13), any derived bar is only as trustworthy as the connected-and-not-silently-dropping-events assumption. This matters more for OHLC (which implies a claim about the *entire* bar) than for cumulative Volume Profile snapshots (which only claim "this is what we saw," not "this is everything that happened").

No implementation is proposed here.

---

## 23. AI Tutor Capability Matrix

**Important distinction, stated explicitly to avoid any ambiguity:** the "Currently supportable?" column below describes what a **future dataset** could support **after** the §25/§43/§44 retention fixes are adopted. It does **not** mean any **existing** dataset already captured under the current schema — including the real accepted 0L dataset (`es_20260823T231601Z_997555.sqlite3`) — retroactively gains these facts. For BBO-at-trade and aggressor questions specifically: **existing datasets are missing `bidPrice`/`askPrice`/`aggressorSide` for every accepted NEW trade already captured, permanently (§6/§8/§42), and no future schema change can recover that.** Only *newly collected* data, captured after the widened schema is deployed, would answer these questions.

| Tutor capability | Source facts needed | Derived facts needed | Currently supportable? | Retention gap |
|---|---|---|---|---|
| "What was VWAP at this moment?" | `event_timestamp`, `price`, `size` | Cumulative VWAP (0R/0S) | YES | None |
| "Where was developing POC?" | same | Volume-at-Price + POC (0O/0R) | YES | None |
| "How had Value Area migrated?" | same | Value Area (0P/0R) | YES | None |
| "What was best bid/ask [at trade time]?" | `bidPrice`/`askPrice` on TimeAndSale | — | **NO for any dataset captured under the current schema** (lost for NEW, §6/§8, permanently — including the existing real 0L dataset); YES for CORRECTION/CANCEL only; would become YES for NEW too **only in datasets captured after §44 fix #1 is deployed** | Retain `bidPrice`/`askPrice` for NEW (0V) |
| "Was this trade lifting the offer or hitting the bid?" | `aggressorSide` | — | **NO for any dataset captured under the current schema** (lost for NEW, §6/§8, permanently); would become YES **only in future datasets** captured after §44 fix #1 | Retain `aggressorSide` for NEW (0V) |
| "What did we know before the correction arrived?" | `source_order`, `received_at` on both NEW and CORRECTION | Feed-knowledge ordering | **PARTIAL today** (§14/§15) for existing datasets; ordering infrastructure already exists, but content fidelity is asymmetric. Would become **materially stronger for future datasets** once NEW-side field parity (§44 fix #1) and rejected-record parity (§44 fix #2) are adopted — still not a claim of feed completeness | Full NEW-side + rejected-side field parity |
| "What was the 30-minute Initial Balance?" | `event_timestamp`, `price` | TPO/session bracketing (§21, not yet implemented) | YES (data-sufficient; feature not built) | None (analytics gap, not retention gap) |
| "Replay the market without revealing future data." | `source_order`, `received_at`, lifecycle source facts (NEW/CORRECTION/CANCEL), plus `event_timestamp` for the analytical state being replayed | Point-in-time lifecycle reconstruction (does not yet exist) | **PARTIAL / MODE-DEPENDENT** — see the three-mode breakdown immediately below. No single existing mode is a true, general-purpose no-future-knowledge replay | Point-in-time lifecycle reconstruction (a larger undertaking than field-parity alone; see §15/§23 invariant) |

**This row requires unpacking — a strict `event_timestamp` cutoff alone does not, by itself, guarantee no future-information leakage.** Three distinct replay modes must be evaluated separately:

- **Canonical NEW-only replay:** filtering immutable `NEW` observations by `event_timestamp < replay_cutoff` genuinely reveals no information from any correction/cancel that arrives later, because corrections/cancels are never applied to this tape at all. **However, canonical NEW-only replay ≠ final corrected market history** — it is missing every correction and cancel by construction, so it answers a different, narrower question than "what actually happened."
- **Retrospective effective-tape replay (the accepted 0R/0S/0T `EFFECTIVE_TAPE` developing series):** correctly reproduces final corrected history — but the tape it replays from was already fully reconciled *before* any historical cutoff is applied. Filtering the *final* reconstructed tape by `event_timestamp < replay_cutoff` can silently incorporate a correction or cancel that was only received well *after* that cutoff (worked example: a `NEW` trade at 09:40, corrected by an event received at 09:50 — a replay paused at 09:45 using the final effective tape would show the *corrected* 09:40 trade, even though the collector did not know about the correction until 09:50). **This is therefore NOT suitable as a true no-future-knowledge tutor replay** without additional point-in-time lifecycle reconstruction that does not currently exist (per the 0R design checkpoint, reaffirmed here).
- **True feed-knowledge replay:** requires `source_order`, `received_at`, and NEW/CORRECTION/CANCEL lifecycle application *as events actually became known*, not applied retrospectively. This is the same capability already classified elsewhere in this audit as **PARTIAL today**, with materially stronger (never complete) support for datasets captured after the Phase 0V retention fixes (§14/§15/§40).

The eventual AI tutor should reason over these already-computed facts (per this project's stated principle: "Code computes facts. AI interprets evidence. Human makes decisions.") — no tutor capability examined here requires raw provider payload access; all route through the canonical/derived layers already established. **A tutor built directly on the retrospective effective-tape series, presented as a "replay," must not claim or imply no-future-knowledge guarantees** unless it is explicitly using canonical NEW-only replay (accepting the corrected-history gap) or a genuine future point-in-time reconstruction (not yet built).

---

## 24. GUI / Annotation Data Requirements

Reviewed the described future design (`quantitative market state -> AI reasoning -> structured annotation intent -> GUI renderer`). No additional *source-data* retention requirement is introduced by this design: a horizontal-level annotation references a derived price (e.g. a POC or VAH value already computed); an arrow or region references a time range and derived levels already produced by the analytics layer. The annotation protocol itself (schema for "horizontal level," "arrow," "label," etc.) is a future GUI/rendering concern, entirely downstream of facts already computed — it does not need raw DXLink fields, only the derived analytical results this project already produces. No retention gap identified here.

---

## 25. Raw Payload / Source Archive Recommendation

Three options were compared:

- **Option A — canonical/source-shaped fields only** (current architecture): simplest, smallest, but the §6/§8 field gaps mean some future re-normalization or new-metric work is permanently blocked for already-captured NEW trades.
- **Option B — canonical fields + complete structured provider event record** (i.e., close the §6/§8 gap by widening `observation_source_provenance` to match `deferred_dxlink_timesale_events`'s completeness): moderate schema change, closes the exact gap this audit identifies, keeps everything queryable in the same relational schema, no new operational complexity (still one SQLite file, same backup/rotation story).
- **Option C — canonical database + compressed append-only raw/source event archive sidecar** (e.g. newline-delimited JSON or similar, gzipped, alongside the SQLite file): maximum future-proofing against fields we did not anticipate requesting at all (protocol/schema evolution, provider adding new fields), but adds real operational complexity — a second artifact to keep in sync, back up, and reason about per dataset, and a second read path for any future re-normalization tooling.

**Recommendation: Option B**, with a note that Option C's underlying concern (unanticipated future fields) is real but best addressed by widening the *requested* field set in K9 (a client-side change, not a storage-architecture change) rather than by archiving raw JSON blobs whose parsing logic would itself need to be maintained forever. Option B closes the concrete, already-identified gap (§6/§8) without adding a second artifact type to operate. Considerations addressed:

- **Future re-normalization:** Option B makes this possible for every field currently requested; a field we never requested at all is not solved by any of these options — it requires requesting it going forward.
- **Storage growth:** Option B's added columns are the same fields already stored for every CORRECTION/CANCEL row today (proven cheap enough there); extending to NEW rows roughly doubles the per-trade metadata footprint, which should be included in 0W's empirical measurement.
- **Schema evolution:** handled the same way `_ensure_provenance_source_order` already handles a prior schema addition (`store.py:159-166`) — an additive `ALTER TABLE`/migration, the established pattern.
- **Debugging:** Option B keeps everything in one queryable place, easier to debug than a sidecar archive requiring a separate tool.
- **Privacy/secrets:** neither the current schema nor Option B/C ever stores credentials (§AE) — the DXLink `fields` dict K9 requests contains no auth material, only public market-data fields.
- **Provider licensing/terms:** Option B does not change what is being stored (it is provider market-data fields we are already contractually receiving), only where; it does not create new licensing exposure beyond what already exists (§AF).
- **Operational complexity:** Option B stays within the current one-file-per-dataset SQLite model; Option C would not.

---

## 26. Unified Source Event Ledger Recommendation

Evaluated whether a single immutable `SourceEvent`/`SourceEventLedger` table (one row per *every* received provider event, in receipt order, regardless of disposition) would materially help future feed-knowledge replay versus the current three-table split (`observation_source_provenance` for accepted NEW, `deferred_dxlink_timesale_events` for CORRECTION/CANCEL, `normalization_rejections` for rejected).

**Existing tables already provide the equivalent information, but not as a single queryable view.** All three tables share a `source_order` column and a `dataset_id`, so a `UNION`-style query ordered by `source_order` already reconstructs the full receipt-order stream today — the *data* exists; only a convenience view is missing, not a new concept. Given §25 recommends widening `observation_source_provenance` (Option B) to field-parity with the deferred table, the three tables would become even more structurally similar, making a future unified view (a `CREATE VIEW` or a small query helper, not a new physical table) the smallest correct solution — **not** a new `SourceEvent` ledger table, which would duplicate data already captured elsewhere and introduce a fourth place market facts could theoretically diverge from the canonical tables.

**Recommendation:** do not introduce a new ledger table. If Phase 0V finds the three-way join cumbersome in practice, add a read-only `SQL VIEW` (or a Python helper function analogous to `prepare_scoped_dataset`) that presents the union in `source_order` order — a presentation convenience, not a new durability decision.

---

## 27. Source vs. Canonical vs. Derived Retention Boundary

| Layer | Durable today? | Should be durable? |
|---|---|---|
| Source facts (full provider record) | Partial (full for CORRECTION/CANCEL, partial for NEW, reason-only for rejections) | YES, full, for **every** disposition — accepted, deferred, and rejected alike (§25 Option B closes the NEW gap; rejected-record parity is likewise a MUST-FIX item per §6/§44, not a lower priority) |
| Canonical observations (`TradeObservation`) | YES | YES (unchanged) |
| Derived effective tape | NO (recomputed on demand) | Recompute (correct as-is — this is intentional, not a gap) |
| VWAP / Volume Profile / Value Area / developing series | NO (recomputed on demand) | Recompute (correct as-is) |
| AI interpretation | N/A (does not exist yet) | Ephemeral / not durable in the market-data schema — an AI's *interpretation* is not a market fact and should not be persisted alongside authentic source data; if ever logged for product reasons, it belongs in a separate, clearly-labeled non-authoritative store |

The current implementation already meets the "source facts → durable, canonical facts → durable, derived analytics → recompute" ideal **structurally** — the only shortfall is *field-level completeness* of the source-fact layer for NEW trades (§6/§8), not a structural violation of the boundary itself.

---

## 28. Dataset Identity / Segmentation Recommendation

Current implementation: **Option A, one dataset per process run** (`capture_es_timesales_dataset` creates a fresh `DatasetIdentity` with a timestamp-based label every call, `live_capture.py:70-79`). There is no trading-date or instrument grouping concept in `DatasetIdentity` today — nothing prevents a dataset from spanning multiple trading dates or (schema-wise) multiple instruments, though the *analysis* layer already enforces single-instrument-per-dataset at read time (`analysis.py:200`, "Dataset spans multiple instruments; unsupported").

Comparison for the future always-on collector:

- **A. One dataset per process run:** simplest today, but for an always-on collector a "process run" could span many trading dates (weeks/months uptime) — a single ever-growing dataset makes crash recovery, backup, and per-day audit awkward, and conflates "one continuous collector process" with "one unit of market history," which are different concepts for an always-on system.
- **B. One dataset per futures trading date:** matches the existing `sessions.py` trading-date concept exactly, aligns with how Human already reasons about the data (per-day study), bounds dataset size predictably, and makes crash recovery natural (a new trading date always means a new dataset regardless of whether the collector process itself restarted).
- **C. One dataset per instrument + trading date:** the correct refinement of B once multiple instruments (§30) are captured simultaneously — necessary the moment ES + NQ + MES + MNQ are captured together, since (per the accepted principle) each contract's Volume Profile must never be merged with another's.
- **D. Long-lived dataset across many trading dates:** operationally the worst fit for crash recovery and audit; actively rejected.

**Product Owner decision: adopt C (one dataset = one exact futures contract + one futures trading date) immediately in the serious collector, even while initially collecting only one instrument (ES).** Do not wait until a second instrument is added — the identity scheme should be instrument+trading-date-shaped from the first serious dataset onward, so adding a second instrument later is purely additive, never a redesign or a migration of already-collected datasets. Trading-date boundaries should reuse the exact accepted `sessions.py` trading-date definition (`classify_es_session`), not a new calendar-day concept, to stay consistent with every accepted analysis phase.

Advantages of adopting this immediately rather than deferring:

- **Natural finalization boundary** — a trading date's session close is an unambiguous, already-modeled point at which a dataset becomes eligible for the `FINALIZED` state (§30/§37).
- **Replay boundary** — every accepted 0N-0T analysis already scopes by trading date; a one-dataset-per-trading-date identity keeps the storage boundary aligned with the analytical boundary from day one.
- **Audit boundary** — `audit_dataset` naturally produces one clean report per trading date rather than an ever-growing, harder-to-audit multi-date dataset.
- **Archive/checksum boundary** — §29's one-file-per-closed-dataset recommendation only has a clean rotation point if the dataset boundary itself is daily.
- **Future multi-instrument isolation** — adopting the instrument dimension now means the schema/identity convention never has to be retrofitted onto already-collected single-instrument data later.
- **Clean contract-roll behavior** — a CME quarterly roll is a multi-day event; per-trading-date datasets mean a roll never has to be handled *mid-dataset* (§35).

---

## 29. Physical SQLite File Rotation Recommendation

**Recommendation: one SQLite file per closed dataset** (i.e., physical file rotation follows dataset segmentation from §28 — one file per instrument+trading-date), explicitly keeping **dataset identity distinct from physical file identity** even though they would align 1:1 in the common case: the schema's `dataset_id` (UUID) remains the durable identity; the file path is an operational/deployment detail that could change (e.g. archival compression, moving to cold storage) without altering the dataset's identity or requiring any in-schema rename.

Reasoning: an always-on collector writing to one ever-growing file for months has no natural "closed, immutable, ready to archive/checksum" boundary; per-trading-date files give a clean daily rotation point that matches the operational principle already stated in the brief (§34: actively-written DB stays on the local Linux filesystem; a *closed* dataset moves to archive/backup) — a file naturally becomes eligible for archival the moment its trading date's session has ended and no further writes will occur to it.

**This is the initial serious-collection preference, subject to Phase 0W's empirical performance/storage validation (§33/§48).** The load-bearing architectural point is that **logical dataset identity is not a fundamental requirement for physical file identity** — `dataset_id` remains the durable identity regardless of file layout, so if 0W's measurements ever warrant a different physical rotation strategy (e.g. multiple datasets per file for very small instruments, or a different archival cadence), that change would not require renaming or reinterpreting any existing dataset's identity.

---

## 30. Closed Dataset / Archive Recommendation

Proposed metadata for a dataset transitioning `OPEN → FINALIZED`:

- `dataset_id`, `instrument` (canonical ID), `capture_started_at`/`capture_ended_at` (already exist)
- `trading_date` (new — currently only derivable from trades post hoc via `sessions.py`, not stored as a first-class dataset field; worth adding once segmentation (§28) is implemented)
- provider/source locator (already exists: `source_locator`)
- normalization policy/version (already exists: `normalizer_version`)
- collector software version / Git commit — **does not exist today**; should be added so a closed dataset can state exactly which code produced it, independent of this document or any conversation history
- quality summary (row counts, known/suspected gap counts — computable today via `audit_dataset`, but not currently *persisted* as a frozen snapshot; a closed dataset's audit could drift if computed fresh later against a database that was, in principle, still being written)
- row counts per table (computable, not currently persisted as a frozen closing snapshot)
- checksum (does not exist today — recommended for archival integrity, e.g. a SHA-256 of the finalized SQLite file, stored alongside it, not inside it, to avoid a chicken-and-egg self-referential hash)

None of this is implemented in 0U. This is a requirements list for Phase 0V.

---

## 31. Active Database Location

Current live-capture tests/usage write directly to a caller-supplied `database_path` (`Path`) with no built-in assumption about cloud-sync directories. The principle ("actively-written DB → local Linux filesystem, not OneDrive-synced") is **not currently violated by any code**, because the path is entirely caller-controlled — but it is also **not currently enforced or documented anywhere in code**, so nothing would stop a future caller from pointing `capture_es_timesales_dataset` at a synced directory by mistake. This is a documentation/operational-convention gap, not a code gap, appropriate for Phase 0V's deployment documentation rather than a code change.

---

## 32. Storage-Growth Findings

**Empirical measurement of the real accepted 0L dataset** (`es_20260823T231601Z_997555.sqlite3`, read-only query, database unmodified):

| Metric | Value |
|---|---|
| File size | 598,016 bytes (~584 KiB) |
| Capture window | 2026-08-23T23:16:01.998Z → 2026-08-23T23:31:02.491Z (≈15.0 minutes) |
| `trade_observations` rows | 1,182 |
| `observation_source_provenance` rows | 1,182 |
| `deferred_dxlink_timesale_events` rows | 0 |
| `normalization_rejections` rows | 0 |
| `dataset_quality_events` rows | 3 (`CAPTURE_STARTED`, `SOURCE_CONNECTED`, `CAPTURE_STOPPED`) |
| Approx. bytes per retained trade (incl. provenance + fixed schema/index overhead) | ≈506 bytes/trade |
| Approx. trade rate observed | ≈1.31 trades/second |

**This 15-minute Sunday-evening (ES Globex reopen) sample is explicitly NOT representative of active RTH event rates.** Zero corrections, zero cancels, and zero rejections occurred in this quiet window — none of those code paths' storage cost is reflected in the byte-per-trade figure above. Do not linearly extrapolate this to a "bytes per month" figure; RTH trade rates on a liquid front-month ES contract are known qualitatively to be substantially higher during active session hours (open, economic releases, etc.), but this audit found no authoritative source giving a specific RTH ES trades/second figure to cite, and none is assumed here.

**Measurement plan for Phase 0W** (the future `robby` soak test) should establish, empirically, not by extrapolation:

- full-RTH-session event counts (NEW, CORRECTION, CANCEL, rejected) for at least one complete regular trading day;
- resulting database size for that full day;
- peak instantaneous event rate (for buffering/backpressure design in 0V);
- correction/cancel frequency as a fraction of total events;
- Quote event rate, if a Quote-capture experiment is included, to inform §19's deferred decision;
- reconnect behavior under real network conditions (WSL/Windows), if 0V's reconnect logic is ready to be tested by then;
- database reopen time and `audit_dataset`/replay/profile-calculation performance against a full-day file (informs §33's SQLite-suitability thresholds).

---

## 33. SQLite Suitability

No evidence in this audit suggests SQLite is currently inadequate for one instrument, one full trading day, or a reasonable number of archived daily files (the per-file segmentation recommended in §28-29 keeps each individual file small and bounded by construction, sidestepping the main risk of "one giant ever-growing database"). Recommendation: **continue SQLite until Phase 0W measures otherwise.**

Concrete thresholds/risks to measure in 0W, rather than assume:

- write throughput under peak event rate (does per-event `commit()` — the current pattern in `save_trade_observations` et al., which commits per batch call — become a bottleneck at RTH volume?);
- database size at full-session scale (extrapolated from §32's baseline once a real RTH sample exists);
- index growth and query performance on `trade_observations`/`observation_source_provenance` at full-day row counts;
- reopen speed for a full-day file (affects every read-only CLI's startup cost);
- audit/replay/profile-calculation scan speed at full-day scale (every current analysis recomputes from scratch on each invocation — acceptable at 1,182 rows, unverified at a full session's row count);
- backup/rotation cost per daily file.

---

## 34. Multi-Instrument Architecture Findings

The schema **already** supports simultaneous multi-instrument capture at the row level: `instruments` is a proper table keyed by `canonical_id`, and `trade_observations.instrument_id` is a per-row foreign key — nothing prevents two different instruments' trades from coexisting in one dataset today, schema-wise. The accepted principle (`ES volume profile ≠ MES volume profile`, never merge) is currently enforced **at the analysis layer**, not the storage layer: `analyze_anchored_vwap_dataset`/`analyze_volume_profile_dataset` explicitly raise `LaboratoryAnalysisError` if a dataset's trades span more than one instrument (`analysis.py:200`). This means the schema is multi-instrument-ready, but the current analysis contract deliberately treats "more than one instrument in one dataset" as an error rather than something to disambiguate — which is exactly why §28's recommended segmentation (one dataset per instrument+trading-date) is the correct fit: it keeps every dataset single-instrument by construction, matching what analysis already assumes, rather than requiring analysis to learn to filter a mixed-instrument dataset.

No final instrument-universe decision (ES/NQ/MES/MNQ/RTY/YM) is made here, per instruction.

---

## 35. Contract-Rollover Requirements

`InstrumentIdentity` already encodes the specific contract (`expiration_year`/`expiration_month`, e.g. `FUTURE:CME:ES:2026-09`) as an immutable identity — nothing in the current model conflates a specific contract with a continuous/generic instrument concept, satisfying the accepted principle that historical observations must never be rewritten from one expiration to another.

Requirements for a later contract-roll phase to address (not solved here):

- what the collector should know about "current active contract" vs. "next contract" (no such concept exists today — each capture call hard-codes `_ES_INSTRUMENT`/`_ES_STREAMER_SYMBOL` as module constants in `live_capture.py:21-23`, appropriate for a bounded single-contract capture tool but not for an always-on multi-month collector that must track the calendar roll itself);
- when/whether the collector begins dual-capturing the next contract before the current one expires (a policy decision, not an architecture one — the schema already supports it via §34's multi-instrument readiness);
- what happens to an *open* dataset when a roll occurs mid-session (should not happen if §28's one-dataset-per-instrument+trading-date segmentation is followed, since a roll is a multi-day event, not an intra-day one, for CME quarterly futures);
- how the old, now-expired contract remains identifiable and queryable indefinitely (already satisfied — its `InstrumentIdentity` and datasets remain exactly as captured, forever, since nothing rewrites history).

---

## 36. Clock / Host Integrity Requirements

`received_at` (and therefore point-in-time feed-knowledge replay, §14/§15) is only as trustworthy as the collector host's system clock. Every `received_at`/`observed_at` in the current schema requires `tzinfo is timezone.utc` (`store.py`'s `_timestamp_text`) but nothing validates that the underlying wall clock itself is *accurate* — that is an operating-system/NTP concern outside this codebase's control.

Future operational requirements to verify in Phase 0V/0Y (not implemented here):

- Windows host clock and WSL clock synchronization (WSL2 has historically had known clock-drift-after-suspend issues that should be explicitly tested on `weasel` before trusting multi-day `received_at` sequences);
- NTP/time-sync service running and healthy on the collector host;
- behavior across suspend/resume and host reboot (does WSL's clock resync promptly, or does a drift window need to be flagged as a `SUSPECTED_GAP`-adjacent quality concern?);
- whether a clock-integrity check should itself become a new `DatasetQualityEvidenceType` in a future phase (a genuine possibility, not decided here).

---

## 37. Process Restart / Crash Requirements

Durable invariants a future resilient collector (Phase 0V) must maintain across crash/WSL-restart/Windows-reboot/network-loss/reconnect:

- **No dataset identity collision:** `dataset_id` is a `uuid4()` generated fresh per `capture_es_timesales_dataset` call today (`live_capture.py:71`) — safe from collision, but a restarted collector must decide whether a crash mid-trading-date resumes the *same* dataset or starts a new one for the remainder of that date (an open design question for 0V, not resolved here).
- **No `source_order` ambiguity:** currently reset to 1 at the start of every capture call — a restart-and-resume design must decide whether `source_order` continues from where it left off (requiring durable tracking of the last-used value) or restarts, which would then require a compound key (e.g. `(process_run_id, source_order)`) to remain globally unambiguous within a dataset. This is a concrete, specific requirement for 0V's design, surfaced directly by this audit.
- **Partial data remains auditable:** already true today — `audit_dataset` works against any state of a database, complete or partial, using only durable facts, no special "was this dataset finished cleanly" flag currently exists to distinguish a cleanly-closed dataset from one truncated by a crash (see §30's proposed `FINALIZED` state — currently absent).
- **Capture lifecycle records survive:** already true — lifecycle events are committed to SQLite as they occur (`_save_lifecycle`, `live_capture.py:158-169`), not held in memory until the end, so a crash mid-capture still leaves the lifecycle trail up to that point durable.
- **Reconnect does not silently duplicate events:** not currently applicable (no reconnect exists), but must be designed in 0V using the `source_index`/`source_trade_id` correlation keys already available (§17).
- **Closed vs. interrupted datasets distinguishable:** **not currently possible** — there is no `FINALIZED`/`INTERRUPTED` state on `DatasetIdentity` today; `capture_ended_at` is set in both the normal-completion and the `DxLinkError`-triggered paths (`live_capture.py:122-128`), so a reader cannot currently tell a clean stop from a disconnect-triggered stop by looking at `capture_ended_at` alone — they would need to also check for a `CAPTURE_STOPPED` vs. `SOURCE_DISCONNECTED` lifecycle event, which *is* durable and does allow this distinction today, just not as a single first-class dataset-level flag. This is a real, concrete requirement for 0V (§30's proposed `FINALIZED` state should formalize it).

---

## 38. Credential / Secret Boundary

Confirmed by full schema and code review: **no table, column, or field in the current Dick's Laboratory schema stores any credential, API token, account ID, or auth header.** The only credential-adjacent code is `source_locator`, a free-text human-readable label (e.g. `"TASTYTRADE_DXLINK:/ESU26:XCME:TimeAndSale"`) — a description of the source, not a secret. The DXLink `quote_token` and connection `url` are passed as constructor arguments to `DxLinkSourceCollector`/`DxLinkCollector` by the caller and never touch the `dicks_laboratory` persistence layer at all (`live_capture.py`'s `SourceCollector` protocol receives no credential parameters; the caller wires the token in separately, outside this package).

If Option B (§25) is adopted, the widened `observation_source_provenance` fields (`bid_price`, `ask_price`, `aggressor_side`, etc.) are all ordinary public market-data fields, not credential-bearing — no new secret-exposure risk is introduced.

---

## 39. Provider / Exchange Retention-Term Findings

Researched dxFeed's public terms pages ([Third Party Terms](https://dxfeed.com/3pty/), [General Terms and Conditions](https://dxfeed.com/general-terms-and-conditions-for-services/)):

- **Clearly documented:** for non-professional/private subscribers, market data is "licensed only for personal use"; redistribution, retransmission, or reproduction beyond the described service use requires prior written approval from dxFeed *and* the original data source/exchange; general terms prohibit copying, reformatting, downloading, storing, reproducing, reprocessing, transmitting, or redistributing data without consent.
- **Resolved by Human review (2026-08-24):** Human reviewed the actual current Tastytrade/dxFeed subscriber agreement under their own account and confirmed **months-long personal archival is permitted for personal use.** This closes open question AS-1 below. The general public-page caution above (redistribution/reproduction requiring prior written approval) still applies to any future redistribution or third-party access — it is the personal-use archival question specifically that is now resolved as permitted.

---

## 40. Future Capability Readiness Matrix

**Two distinct subjects, not to be conflated:**

```
CURRENT EXISTING DATASETS
(already captured under today's schema, e.g. the real 0L dataset)
        vs.
FUTURE SERIOUS DATASETS
(captured only after the §44 MUST-FIX retention changes are deployed)
```

The "Current Data Sufficient?" column below states, for each capability, whether **already-captured data** (left column concept) is sufficient **as-is**. Where a fix is listed under "Action Before Serious Collection," that fix can only ever benefit **newly captured, future datasets** — it can never retroactively add `bidPrice`/`askPrice`/`aggressorSide`/etc. to a NEW trade already normalized under today's schema (§6/§8/§42). The real 0L dataset, specifically, will **permanently** remain PARTIAL for BBO/aggressor/feed-knowledge-replay purposes no matter what Phase 0V does.

| Future Capability | Current (Existing) Datasets Sufficient? | Missing Durable Facts | Reconstructable Later for Existing Data? | Sufficient in Future Datasets After §44 Fixes? | Action Before Serious Collection? |
|---|---|---|---|---|---|
| Standard VWAP | YES | None | — | YES | None |
| Anchored VWAP | YES | None | — | YES | None |
| Volume-at-Price | YES | None | — | YES | None |
| POC | YES | None | — | YES | None |
| VAH / VAL | YES | None | — | YES | None |
| Developing retrospective profiles | YES | None | — | YES | None |
| TPO / Market Profile | YES (data-sufficient; feature unbuilt) | None | — | YES | None |
| OHLC bars | YES (data-sufficient; feature unbuilt) | None | — | YES | None |
| Trade aggressor / delta | **NO** | `aggressorSide` for NEW | **NO, never, for already-captured data** | YES, for datasets captured after fix #1 | **YES — retain `aggressorSide` for NEW before serious collection (§44 #1)** |
| BBO/spread replay | **PARTIAL** (CORRECTION/CANCEL only) | `bidPrice`/`askPrice` for NEW (full standalone Quote stream not retained at all) | **NO, never, for already-captured NEW trades** | Materially better, for datasets captured after fix #1; full Quote tape still deferred to §19 | **YES — retain `bidPrice`/`askPrice` for NEW (§44 #1); decide standalone Quote capture per §19/0W** |
| Retrospective corrected replay | YES | None | — | YES | None (already the accepted default) |
| Feed-knowledge replay | **PARTIAL** | Full NEW-side + rejected-side field parity; live reconnect evidence | **NO, never, for already-captured data** | Materially stronger (not complete — subject to reconnect/loss boundaries, §15/§17), for datasets captured after fixes #1-#3 | **YES — close NEW-side (§44 #1) and rejected-side (§44 #2) field gaps before serious collection** |
| Capture-gap audit | **PARTIAL** (explicit evidence only, correctly never inferred) | Reconnect evidence, connection-health signals (0V) | N/A — a live-monitoring gap, not a retention gap | Improved once reconnect is implemented (§44 #3), still governed by "reconnect ≠ proof of recovery" (§17) | Deferred to 0V (resilience), not a schema gap |
| AI tutoring | YES for facts already computed; **PARTIAL, permanently, for existing datasets'** aggressor/BBO-dependent questions | Same as above | **NO for existing datasets** | Materially better for future datasets | Same actions as above close this gap for future data only |
| GUI annotations | YES | None | — | YES | None |
| Multi-session comparison | YES (data-sufficient; feature unbuilt, needs dataset segmentation per §28 to be convenient) | None strictly required, but §28's segmentation makes this materially easier | — | YES, more conveniently | Adopt §28 segmentation immediately (Product Owner decision, §28/§44 #5) for operational convenience, not because data would otherwise be lost |

---

## 41. Field Retention Decision Matrix

| Field (NEW-trade context) | Decision | Reason |
|---|---|---|
| `event_timestamp` / `time` | MUST RETAIN | Core analytical truth; already retained |
| `price`, `size` | MUST RETAIN | Core; already retained |
| `source_index`, `source_sequence`, `source_trade_id` | MUST RETAIN | Correction/cancel correlation key, provider-confirmed; already retained |
| `source_order`, `received_at` | MUST RETAIN | Feed-knowledge replay ordering; already retained |
| `event_classification` (NEW, explicit) | SHOULD RETAIN | Currently only implicit for accepted rows; cheap, closes a small consistency gap with the deferred table |
| `bidPrice`, `askPrice` | SHOULD RETAIN | Cheapest available BBO-at-trade context; currently lost for NEW |
| `aggressorSide` | SHOULD RETAIN | Enables future order-flow study; currently lost for NEW |
| `exchangeCode` | SHOULD RETAIN | Multi-venue studies; currently lost for NEW |
| `exchangeSaleConditions` | SHOULD RETAIN | Filtering unusual prints; currently lost for NEW |
| `spreadLeg` | SHOULD RETAIN | Filtering multi-leg prints from a single-instrument profile; currently lost for NEW |
| `extendedTradingHours` | MAY RETAIN | Convenient cross-check against our own session model; not required |
| `tradeThroughExempt` | MAY RETAIN | Unclear applicability to CME futures; cheap to store regardless |
| `validTick` | MUST RETAIN (already effectively is, via the acceptance gate) | Provider-confirmed correctness of the NEW-acceptance filter |
| `eventFlags` | **SHOULD RETAIN** (reclassified, cheap future-proofing) | Not needed for current live NEW normalization (observed always zero under our regular subscription), but dxFeed's indexed/time-series event model uses it elsewhere, and retaining it is essentially free alongside the rest of NEW source-field parity (§44 #1) |
| `timeNanoPart` | SAFE TO DISCARD | Never requested; unlikely to matter at ES/futures trade-timing resolution |
| Full raw JSON/text payload | SAFE TO DISCARD (Option B preferred over Option C, §25) | Structured field retention (once widened) covers the identified needs without a second archive artifact |
| Rejected-record full payload | **MUST RETAIN (promoted, Product Owner decision)** | Currently reason-only; every received event regardless of disposition must preserve sufficient source-shaped evidence for later audit/re-normalization — otherwise the cause of rejection is irretrievably lost |

---

## 42. "Can Be Derived Later" Test — Summary

Applied explicitly throughout this audit:

- `event_timestamp`, `price`, `size`, `source_index`/`sequence`/`trade_id`, `source_order`, `received_at` — **already retained**, so the question is moot.
- `bidPrice`/`askPrice`/`aggressorSide`/`exchangeCode`/`exchangeSaleConditions`/`spreadLeg`/`extendedTradingHours` for NEW trades — **NO, cannot be derived later** once a NEW event has been normalized and its narrow provenance saved; this is the single largest permanent-loss risk identified.
- `eventFlags` — carries no live analytical information today (observed always zero under our regular subscription), so the "derived later" question is largely moot in the sense that nothing is currently *lost*; it is still classified SHOULD RETAIN (§41) purely as cheap future-proofing alongside the rest of NEW source-field parity, not because current data is at risk.
- Rejected-record payloads — **NO, cannot be derived later**; genuinely permanent once lost, which is exactly why this is now a MUST-FIX item (§44) rather than a deferred nicety, despite rejections being expected to be low-frequency.
- Derived analytics (VWAP, POC, Value Area, developing series, future TPO/OHLC) — **YES, always derivable later** from durable source+canonical facts, which is exactly why they correctly remain unpersisted today.

This test is the primary justification for every MUST/SHOULD recommendation in §41: every "SHOULD RETAIN" item above fails this test (cannot be recreated later); every item correctly left un-persisted passes it (can always be recomputed).

---

## 43. Proposed Minimum Serious-Collection Contract (for Phase 0V)

> **For every market source event received by the serious collector, regardless of normalization disposition (accepted, deferred, or rejected), retain:**
>
> - dataset identity
> - source event identity/reference (`source_record_ref`)
> - provider symbol (`eventSymbol`)
> - source event classification (`type`: NEW / CORRECTION / CANCEL, or the rejection reason)
> - source market timestamp (`event_timestamp` / `time`)
> - receipt timestamp (`received_at`)
> - `source_order`
> - source index (`index`)
> - source sequence (`sequence`)
> - `tradeId` where supplied
> - `price` / `size` where supplied
> - trade-time bid / ask where supplied (`bidPrice` / `askPrice`)
> - exchange / sale metadata where supplied (`exchangeCode`, `exchangeSaleConditions`, `tradeThroughExempt`)
> - aggressor / spread metadata where supplied (`aggressorSide`, `spreadLeg`, `extendedTradingHours`)
> - other accepted source-field-parity metadata (`validTick`, `eventFlags`)
> - normalization disposition (accepted NEW / deferred CORRECTION / deferred CANCEL / rejected, with reason if rejected)
>
> This explicitly extends today's CORRECTION/CANCEL-only field completeness to **every** disposition — accepted NEW and rejected records included. This wording is a retention-content requirement, not a schema design; Phase 0V decides the narrow implementation (table shape, migration approach).
>
> **For every capture lifecycle transition:**
> a durable `DatasetQualityEvent` with an explicit `observed_at` UTC timestamp — already satisfied today for `CAPTURE_STARTED`/`SOURCE_CONNECTED`/`SOURCE_DISCONNECTED`/`CAPTURE_STOPPED`; Phase 0V must additionally emit genuine `SOURCE_RECONNECTED` events (currently never produced by the live path) and derive `KNOWN_GAP` evidence from real disconnect/reconnect pairs (machinery for this already exists in `capture_lifecycle.py`, currently exercised only by the historical-CSV path) — and must never treat a reconnect as proof that the disconnect-window events were recovered (§17).
>
> **For each closed dataset:**
> `dataset_id`, `instrument` (canonical ID), `trading_date` (new first-class field, per the immediate §28 segmentation decision), `capture_started_at`/`capture_ended_at` (already exist), `source_locator`, `normalizer_version` (already exist), collector software version/Git commit (new), an explicit `FINALIZED`/`INTERRUPTED` closing state (new), a frozen quality-summary snapshot (row counts, gap counts — new as a *persisted* snapshot, though computable today), and a checksum of the finalized file stored alongside it (new).

This contract is the direct output of §6/§8/§25/§30/§37 combined, and is deliberately scoped to information-loss/replay-integrity concerns only — no new analytics, no TPO, no standalone-Quote-stream capture commitment, no reconnect *implementation* (only the *evidence* reconnect must produce). Preserve the existing boundary throughout: **source evidence → durable; canonical normalized observations → durable; derived analytics → recompute** (§27).

---

## 44. MUST FIX Before Long-Horizon Collection We Care About

1. **Accepted NEW source-field parity.** Widen `observation_source_provenance` to field-parity with `deferred_dxlink_timesale_events`, so every accepted NEW trade retains `bidPrice`, `askPrice`, `aggressorSide`, `exchangeCode`, `exchangeSaleConditions`, `spreadLeg`, `extendedTradingHours`, `eventFlags`, and an explicit `event_classification`, matching what is already correctly retained for CORRECTION/CANCEL. This is an information-loss issue, not an analytics enhancement — once a NEW trade is captured under the current schema, this data is gone forever.
2. **Rejected-source evidence parity.** Preserve sufficient structured source fields for rejected `TimeAndSale` records (not merely `source_record_ref`/`reason`) to allow later audit and independent re-normalization-policy evaluation — otherwise the information that caused a rejection is irretrievably lost and the normalization policy itself can never be checked against real historical evidence.
3. **Resilient reconnect.** Record disconnect/reconnect lifecycle evidence and resume collection, without ever pretending that missed events during the disconnect window were automatically recovered — `reconnect ≠ proof of gap recovery` (§17). A disconnect interval becomes a `KNOWN_GAP` unless a future recovery mechanism explicitly proves otherwise with its own durable evidence.
4. **Explicit dataset closure state.** Add a `FINALIZED`/`INTERRUPTED` state to `DatasetIdentity`, so a reader can distinguish a cleanly-completed dataset from one truncated by a crash or disconnect without needing to separately inspect lifecycle events — this is a replay-integrity concern (§37), not a nicety.
5. **Instrument + trading-date segmentation.** The serious collector opens and finalizes datasets on the explicit `one exact futures contract + one futures trading date` boundary (§28), adopted immediately even while collecting only ES — not deferred until a second instrument is added.

## 45. SHOULD FIX Soon

- Add collector software version/Git commit and a persisted quality-summary snapshot + checksum to closed datasets (§30).
- Decide and record the `source_order` restart-vs-continue policy for a crash-and-resume collector (§37) as part of Phase 0V's design, before it is needed in practice.
- Investigate (empirically or via deeper provider documentation) whether a regular DXLink subscription ever receives any backfill on reconnect (§16/§17) — this is non-blocking research that informs how much of item 3 above can ever be automatically recovered versus how much will always remain a genuine, permanent gap; the conservative "no automatic recovery assumed" policy (§17) already governs architecture regardless of this investigation's outcome.

## 46. SAFE TO DEFER

- TPO/Market Profile analytics (§21 — data already sufficient whenever built).
- OHLC bar analytics (§22 — data already sufficient whenever built).
- Standalone Quote/BBO capture as an independent stream (§19 — defer to measured 0W decision; the cheaper bid/ask-at-trade fields should be retained now regardless).
- GUI, AI tutor, chart-annotation protocol (§24/§26 — no additional source-data requirement identified; purely downstream of already-adequate facts).
- Advanced visualization, cross-session comparison (data-sufficient once §28 segmentation exists; feature work, not retention work).
- A dedicated unified `SourceEvent` ledger table (§26 — a view/helper suffices; a new physical table would duplicate data unnecessarily).
- Contract-rollover *policy* implementation (§35 — architecture already supports it; the policy itself is a later decision).
- `timeNanoPart` retention (never requested; safe to omit unless a future need for sub-millisecond ordering emerges). Note: `eventFlags` is **not** on this deferred list — it is reclassified as a MUST-FIX item 1 SHOULD-retain field (§5/§6/§44), cheap future-proofing alongside the rest of NEW source-field parity, even though it carries no live analytical information under the current subscription mode.

---

## 47. Recommended Phase 0V Scope

**Phase 0V — Resilient Long-Running Capture Foundation**

Should contain, per the final §44 MUST-FIX list:
- Reconnect logic in the live DXLink capture path, with genuine `SOURCE_RECONNECTED` lifecycle emission, `KNOWN_GAP` derivation reused from existing `capture_lifecycle.py` machinery, and the explicit `reconnect ≠ proof of gap recovery` policy (§17) enforced by design.
- Accepted-NEW source-field parity (widen `observation_source_provenance` to match the deferred table, including `eventFlags`).
- Rejected-record source-field parity (structured evidence, not raw-JSON, per §25's Option B reasoning).
- An explicit `FINALIZED`/`INTERRUPTED` dataset closing state.
- Instrument + trading-date dataset segmentation (§28), adopted immediately, not deferred to a second instrument.
- A `source_order` restart/resume policy for crash recovery (§45, SHOULD-FIX-SOON).
- Closed-dataset finalization metadata (§30/§45: version/commit, quality snapshot, checksum).

Should **not** contain:
- Quote/BBO standalone capture (deferred to a measured decision, §19/§46).
- TPO/Market Profile, OHLC, AI tutor, or GUI annotation features (§46 — all data-sufficient already, all separate feature work).
- Contract-rollover policy implementation (requirements only, §35).
- Any change to the accepted analysis-layer semantics (VWAP/Volume Profile/Value Area/developing series) — 0V is purely about the durability/resilience of the *input* layer.

## 48. Proposed Phase 0W Robby Soak-Test Measurements

A future empirical measurement plan (not run in 0U), to be executed once Phase 0V's resilience work exists:

- Full regular-trading-hours event counts (NEW/CORRECTION/CANCEL/rejected) for at least one complete trading day.
- Resulting database size for that day, compared against the §32 quiet-period baseline to establish a real RTH-vs-quiet ratio.
- Peak instantaneous event rate (informs any future buffering/backpressure design).
- Correction/cancel frequency as a fraction of total volume.
- **Quote-stream empirical measurement (optional experiment, to finally resolve §19's deferred permanent decision):**
  - Quote events per second.
  - Quote rows per session.
  - Storage bytes per session.
  - Peak Quote rate.
  - Write-load impact on the collector.
  - Replay usefulness observed in practice.
  The permanent Quote-retention decision follows this measurement — it is not decided by this audit, and Quote capture itself is not implemented until 0W's results are available.
- Observed reconnect behavior and recovery time under real (not simulated) network conditions on `robby`.
- Database reopen time and `audit_dataset`/replay/profile-calculation performance against a full trading-day file, to validate or revise §33's SQLite-suitability assumption.

## 49. Future `weasel` Deployment Requirements (Documented Only, Not Performed)

Expected direction, restated as requirements rather than implementation:

- `robby`: development + Phase 0V/0W soak-test validation continues here first.
- Git commit/push of the validated Phase 0V code.
- `weasel` (Windows 11, WSL Ubuntu, UPS-backed): pulls the same repository, runs the always-on collector inside WSL's Linux filesystem (never a Windows-side synced directory) per the already-stated operational principle (§31/§34).
- Before any deployment: verify WSL clock integrity (§36) and confirm the actively-written database path on `weasel` is genuinely local WSL filesystem, not an auto-synced Windows directory, using whatever `weasel`-specific verification Phase 0V/deployment tooling establishes.
- No Windows service/startup-script design is specified here — that belongs to the later deployment phase once current WSL behavior on `weasel` itself can be verified firsthand, per instruction.

---

## 50. Open Questions Requiring Human/Product-Owner Decision

Resolved by this correction pass (kept here only as a record, not as pending decisions):

1. ~~**dxFeed/Tastytrade personal-archival terms (§39):**~~ **RESOLVED — Human confirmed: yes, permitted for personal use** (§39, top-of-document constraint note). Redistribution/publication rights remain explicitly out of scope.
2. ~~**Rejected-record full-payload retention priority:**~~ **RESOLVED — Product Owner decision: promoted to MUST-FIX #2** (§44). No longer optional.
3. ~~**Dataset segmentation timing:**~~ **RESOLVED — Product Owner decision: adopt instrument+trading-date segmentation immediately** (§28/§44 #5), not deferred until a second instrument is added.
4. ~~**Reconnect/backfill blocking architecture:**~~ **RESOLVED as a non-blocking policy** — the collector assumes no automatic recovery of disconnect-window events until an explicit recovery mechanism proves otherwise with its own durable evidence (§17). This no longer blocks Phase 0V's design.

Genuinely remaining open items:

1. **Regular-subscription reconnect backfill — empirical/documentation confirmation (§16/§17):** does a DXLink regular (non-time-series) subscription ever receive any historical backfill on resubscribe? Not confirmed by the documentation fetched in this audit. This is now explicitly **non-blocking research** (§17/§45) — Phase 0V's conservative "no automatic recovery assumed" policy governs regardless of the answer — but the answer would still be useful to know, and may be investigated empirically in 0V/0W.
2. **`tradeThroughExempt` applicability to CME futures (§5):** unclear from documentation whether this Reg-NMS-flavored field has any real meaning for futures TimeAndSale data. Classified **MAY RETAIN** regardless (§6/§20/§41), so this does not block anything — worth a Human/product note only if it ever surfaces meaningfully in tooling.

---

## 51. Files Added / Changed

- **Added (original 0U pass):** `docs/dicks_laboratory/LONG_HORIZON_DATA_REPLAY_READINESS_AUDIT.md` (this document).
- **Changed (this correction/finalization pass):** this same document only — incorporating the Human's AS-1 resolution, the eventFlags reclassification, the rejected-record MUST-FIX promotion, the reconnect/backfill policy decision, the immediate dataset-segmentation decision, the rewritten minimum serious-collection contract, the corrected AI-tutor/BBO current-vs-future distinction, and the reduced open-questions list.
- No production code, tests, schema, or dependencies were modified in either pass. No throwaway inspection script was needed beyond ad hoc read-only `sqlite3` queries against the existing real dataset.

## 52. Validation

- `git status --short` reviewed before and after: only this new document appears.
- `git diff --check`: run, clean (see handoff message).
- No production/test code was changed, so the full `pytest`/`ruff` suite was not required to be re-run per this phase's own instructions; a targeted read-only baseline check (`sqlite3` queries against the real dataset, confirmed the database's mtime and row counts were unaffected) was performed instead, consistent with "documentation-only" validation.

## 53. Git Status

Not committed, not pushed — awaiting Human/Product Owner review, per instruction. `apps/dicks_laboratory/data/` (including the retained 0T smoke-test PNGs and the real SQLite study dataset) was not modified, moved, or deleted.
