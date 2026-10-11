# 0AA-A — AI Tutor Evidence & Lesson Foundation: real-data proof (2026-10-10)

Reference: `AI_TUTOR_EVIDENCE_FOUNDATION.md`. Evidence: `evidence/0AA-A/` (student
QUESTION payloads and instructor payloads as JSON and text, logs, database
sha256, harness). No AI model was called.

Phase identifier: `0AA-A` was unused and is kept.

## 1. Method

- Code: `0c7c9ce913011f00e53ff744323b1aeac46de9e1` (feature) and
  `dd3e3181ac04cb8ffe465b123052afd69bf48da4` (the VWAP lesson cites when the last
  known price traded). The proof ran at `dd3e3181` with a clean worktree under
  `apps/` and `scripts/`.
- One process per dataset, sequential. Every lesson was built twice; all five
  payloads (student QUESTION, HINT, ANSWER, POST_REVEAL and instructor) were
  compared byte for byte. Each lesson's deterministic reference answer was
  validated with `validate_answer_grounding` against its QUESTION stage.
- Databases: 2026-09-30 (+ prior 09-29), 2026-08-31 `c9ebc043` (INTERRUPTED; +
  prior 08-28 with no profile), 2026-09-21 (a real overnight disconnect).
  sha256 before = after (`db_sha_before.txt`, `db_sha_after.txt`).
- Snapshot hashes include the analysis commit (provenance), so they differ
  from the 0Z-C proof's hashes for the same instants.

## 2. Results

| Dataset | Lesson | Answer key | Grounded | Hidden until stage | Deterministic |
|---|---|---|---|---|---|
| 09-30 | VWAP observation at 10:00, hidden outcome 10:30 | SUPPORTED: ABOVE (7772.75 vs cash VWAP 7766.198…, DEVELOPING); outcome at 10:30: ABOVE | yes (7 refs) | future sha only in POST_REVEAL | yes |
| 09-30 | Initial Balance at 09:15 | DEVELOPING, IB so far 7748.00 - 7779.50 | yes | — | yes |
| 09-30 | Initial Balance at 09:30 | COMPLETE (COMPLETE, not FINAL: "later-received records may still revise it") | yes | — | yes |
| 09-30 | Evidence change 12:14:00 → 12:14:01 | 10 changes: state hash changed; 754 newly known records, 750 with market times before 12:14:00 (up to 20.293056 s late); volume 805943 → 806881; both VWAPs, TPO value area, relation INSIDE → BELOW the developing volume value area | yes (26 refs) | — | yes |
| 09-30 | Value 09:30 → 10:00 (LABORATORY_PROFILE_70) | MIXED: volume POC unchanged 7773.00; VAL / VAH, TPO POC / VAL / VAH HIGHER | yes (12 refs) | — | yes |
| 09-30 | Inside / outside value at 10:00 | INSUFFICIENT_EVIDENCE (time outside value: NEEDS_IMPLEMENTATION); the current relation is still given | yes | — | yes |
| 09-30 | Not yet determined at 10:00 | 5 components NOT_YET_DETERMINED | yes | — | yes |
| 08-31 | Data quality at 10:00 (interrupted) | QUALITY_QUALIFIED, INCOMPLETE, 4 known gaps; 9 warnings incl. cash opening and OPENING_TYPE_V1 NOT_AVAILABLE, prior day NOT_AVAILABLE | yes | — | yes |
| 08-31 | VWAP observation at 10:00 (interrupted) | BELOW, with the last known trade at 13:47:35.894Z (08:47 CT); "the last known price is the price at the lesson time" → INSUFFICIENT_EVIDENCE (capture STOPPED); 3 warnings | yes (9 refs) | — | yes |
| 09-21 | Data quality during the disconnect (21:55:12.5 CT), hidden outcome 21:55:14 | QUALITY_QUALIFIED; active interruption since 02:55:11.948328Z, connection DISCONNECTED; the outcome shows the fixed gap after the reconnect | yes | future sha only in POST_REVEAL | yes |

For every lesson: the QUESTION payload has no answer key, hints or future
outcome (`withheld` names them); rubric required refs are all cited by the
reference answer; and no bias, recommendation or trade vocabulary appears
in either rendered view.

Quality-aware behavior: the 08-31 lessons do not teach from pristine
evidence. Every component warning is part of the context and the rubric, and
an answer that drops one fails with QUALITY_WARNING_OMITTED.

## 3. Incremental tutor-layer cost

| Dataset | Replay session prepare (not tutor) | First lesson build (computes its snapshots) | Tutor layer with cached snapshots (rebuild + 5 payloads) | Student payload | Peak RSS |
|---|---|---|---|---|---|
| 09-30 + prior | 196.0 s | 8.5–31.6 s | 0.011–0.029 s; 0.78–0.83 s for comparison lessons (the delta's newly-known scan of the prepared record) | 9–34 KB | 3.70 GB |
| 08-31 + prior | 15.1 s | 3.9 s | 0.015–0.023 s | 16–34 KB | 0.61 GB |
| 09-21 | 64.7 s | 2.9 s | 0.016 s | 24 KB | 2.32 GB |

The tutor layer adds tens of milliseconds over cached snapshots. The replay
memory backlog item is unchanged and separate.

## 4. Read-only

All database sha256 values are unchanged; no network, broker, AI API or Azure
access by the tutor layer.
