# AI Tutor Evidence and Lesson Foundation (0AA-A)

> A deterministic boundary between the accepted replay evidence and a future AI
> tutor. It answers **"What evidence was available to the student at time T?"**
> and nothing later. No AI model is called; no setup is classified; nothing is
> recommended.

```
TutorEvidenceContext != market opinion
curriculum rule      != observed fact
AI interpretation    != Laboratory evidence
```

- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/tutor_evidence.py`.
- **CLI:** `scripts/dicks_lab_tutor_lesson.py`.
- **Tests:** `apps/dicks_laboratory/tests/test_tutor_evidence.py`.
- **Real-data proof:** `AI_TUTOR_FOUNDATION_0AAA.md`, `evidence/0AA-A/`.
- **Temporal authority:** the accepted replay engine (`MARKET_STUDY_SNAPSHOT_V1`,
  0Z-B) through `ReplaySession` (0Z-C). This layer never computes a cutoff, a
  maturity or a market value; it selects evidence from snapshots the session
  built and refers to it by path.

```
ReplaySession ─ snapshot(T) / compare(T1, T2)       (replay: the only temporal authority)
      │
      ▼
TutorEvidenceContext   authorized AS_OF evidence + EvidenceRef paths + quality warnings
      │
      ▼
TutorLesson            definition · context · answer key · optional hidden future outcome
      │
      ├─ student_view(lesson, stage)   → what a student / a student-facing model may see
      └─ instructor_view(lesson)       → everything, incl. deterministic grading material
      ▼
TutorAnswer  ──validate_answer_grounding──▶ GroundingReport   (the target a future model must hit)
```

## 1. Evidence grounding

Every tutor-visible fact is an `EvidenceItem`:

| Field | Meaning |
|---|---|
| `ref` | `EvidenceRef(source_sha256, pointer)`: an RFC 6901 pointer into the canonical `MARKET_STUDY_SNAPSHOT_V1` (or `MARKET_STUDY_DELTA_V1`) document with that hash |
| `domain` | `EvidenceDomain` (DATA_QUALITY, PRICE, VWAP, VOLUME_PROFILE, TPO, INITIAL_BALANCE, PRIOR_DAY, OVERNIGHT, OPENING, DAY_TYPE, MATURITY, CHANGES) |
| `value` | the canonical JSON scalar at that path (structured values as canonical JSON text); `null` = absent, never 0 / false |
| `category` | `ClaimCategory` (§6) |
| `availability` | AVAILABLE, NOT_YET_AVAILABLE, NOT_YET_DETERMINED, NOT_AVAILABLE (from the snapshot's maturity) |
| `maturity`, `status` | the component's maturity and ComponentStatus in that snapshot |
| `derived_from` | for relations: the pointers they are computed from |

Paths are real schema paths, for example:

```
/prices/last_known_price
/vwap/1/study/vwap                              (US_CASH_OPEN; /vwap/0 is SESSION_OPEN)
/relations/last_price_vs_cash_vwap              (0Z-C relations() of the same snapshot)
/tpo/profile/initial_balance/high
/maturity/9/maturity                            (the initial_balance row)
/prior_day/context/value_area_high
/cash_opening/cash_open/price
/quality_matrix/10/status
/changes/3/after, /newly_known/records          (in a MARKET_STUDY_DELTA_V1 document)
```

`/relations/*` is the only path not stored in the snapshot itself; it resolves
into `replay_player.relations(snapshot)`, a deterministic function of the same
snapshot. A future answer cites `EvidenceRef`s: "claim supported by paths X, Y, Z".

## 2. Anti-lookahead boundary

- `TutorEvidenceContext` carries `evidence_temporality: AS_OF`,
  `replay_market_time`, `replay_knowledge_time` and `snapshot_sha256` (the
  lesson-time snapshot). Every item's `source_sha256` is one of the context's
  snapshots (or its delta).
- A lesson at 09:45 is built from the 09:45 snapshot only; a comparison lesson
  from its two snapshots and their delta. Tests prove that changing evidence after
  10:00 leaves a 10:00 lesson's student **and** instructor payloads byte-identical,
  and that a print received at 10:05 is absent from a 10:04:59 lesson.
- A hidden future outcome (`reveal_at`) is a separate snapshot, kept out of the
  context and the student payload until POST_REVEAL. A reference to it before then
  fails validation with HIDDEN_FUTURE_EVIDENCE.

## 3. Student vs instructor views

| Material | QUESTION | HINT | ANSWER | POST_REVEAL | Instructor |
|---|---|---|---|---|---|
| public lesson definition, curriculum sources, context (AS_OF evidence, quality warnings, policy registry, value-area convention) | yes | yes | yes | yes | yes (full definition) |
| hints | — | yes | yes | yes | yes |
| answer key (observations, rubric, incorrect claims, reference answer) | — | — | yes | yes | yes |
| future outcome (later snapshot evidence + its observations) | — | — | — | yes | yes |

- Withheld material is **absent** from the student payload; `withheld` names it
  (names only, no content, no hash of hidden content).
- The model that talks to the student receives `student_view(lesson, stage)`.
  An eventual grader may receive `instructor_view`; it must not converse with the
  student.
- Both payloads are canonical JSON (MARKET_STUDY_STATE_V1 encoding) with
  `payload_sha256` over the payload without that field. `lesson_definition_sha256`
  identifies the authored definition. No wall-clock field. Snapshot hashes give
  the evidence provenance.

## 4. Lesson stages (`TUTOR_REVEAL_V1`)

`QUESTION → HINT → ANSWER → POST_REVEAL`. The evidence available to the
student expands only by this fixed schedule (§3). No conversation is modeled.

## 5. Lessons and questions

`LessonDefinition`: lesson_id, title, objective, `LessonMode` (OBSERVE, IDENTIFY,
COMPARE, EXPLAIN_EVIDENCE — no recommendation, alert or decision mode),
`QuestionKind`, question text, trading date, `at`, optional `compare_from` and
`reveal_at`, allowed domains, curriculum module and sources, value-area
convention, hints. It needs no model and is validated on construction (aware
times, compare_from < at < reveal_at, required domains, convention stated when a
value area is used).

Representative question kinds (a small foundation, not a library):

| QuestionKind | Mode | Deterministic answer key |
|---|---|---|
| PRICE_VS_CASH_VWAP | OBSERVE | price, cash VWAP (with maturity), relation; NOT_YET_AVAILABLE before 08:30 |
| INITIAL_BALANCE_STATUS | IDENTIFY | IB maturity (DEVELOPING / COMPLETE) and the range so far / complete |
| EVIDENCE_CHANGES | COMPARE | state hash changed, newly known / late records, every delta change |
| VALUE_MIGRATION | COMPARE | developing volume / TPO POC, VAL, VAH at both times: HIGHER / LOWER / UNCHANGED |
| VALUE_OCCUPANCY | EXPLAIN_EVIDENCE | INSUFFICIENT_EVIDENCE (time outside value: NEEDS_IMPLEMENTATION) + the current relation |
| NOT_YET_DETERMINED_ITEMS | IDENTIFY | every NOT_YET_DETERMINED / NOT_YET_AVAILABLE component |
| DATA_QUALITY | IDENTIFY | status, completeness, gaps, every quality warning |

The `AnswerKey` holds `support` (EvidenceSupport), a summary, expected
observations with their refs, missing dependencies, a `GradingRubric` and a
deterministic `reference_answer` (a `TutorAnswer` that must itself pass grounding
against the QUESTION-stage student evidence: tested for every kind).

## 6. Observation vs interpretation

`ClaimCategory`: OBSERVED_FACT, DERIVED_FACT, LABORATORY_POLICY_RESULT,
CANDIDATE, QUALITY_WARNING, CURRICULUM_RULE, AI_INTERPRETATION.

- "The cash VWAP is 7710.25" is a DERIVED_FACT citing `/vwap/1/study/vwap`.
- "Price appears to be accepting above VWAP" is AI_INTERPRETATION: allowed only
  when it cites evidence, counted separately, never evidence. Labeled as an
  OBSERVED_FACT citing a DERIVED_FACT relation, it fails with
  CATEGORY_NOT_SUPPORTED. "Acceptance" itself has no Laboratory definition (§9).
- CURRICULUM_RULE claims cite a curriculum source of the lesson, not evidence.

## 7. Unsupported claims

`EvidenceSupport`: SUPPORTED, NOT_YET_AVAILABLE, NOT_YET_DETERMINED,
INSUFFICIENT_EVIDENCE. Lack of evidence is **never** FALSE. A `TutorAnswer`
states what it cannot prove as `UnsupportedClaim(statement, support, missing,
evidence_refs)`; marking one SUPPORTED fails validation. Rubrics list common
incorrect claims with the support the evidence actually gives them (e.g.
"Price is accepting above the cash VWAP" → INSUFFICIENT_EVIDENCE: no acceptance
policy; "The Initial Balance is complete" at 09:15 → NOT_YET_DETERMINED).

## 8. Future AI answer schema and grounding validation

```
TutorAnswer(schema TUTOR_ANSWER_V1, lesson_id, stage, snapshot_sha256, answer_text,
            claims[TutorClaim(statement, category, evidence_refs, asserted[(ref, value)],
                              curriculum_source_id)],
            uncertainties, quality_warnings[warning ids], unsupported_claims[UnsupportedClaim])
```

`validate_answer_grounding(answer, lesson)` → `GroundingReport(valid, stage,
checked_refs, interpretations, issues)`. Deterministic checks:

| Issue | When |
|---|---|
| WRONG_LESSON / WRONG_SNAPSHOT | the answer is for another lesson or snapshot |
| UNKNOWN_EVIDENCE | no such lesson source or path |
| UNAUTHORIZED_EVIDENCE | the path exists in a lesson snapshot but outside the authorized domains |
| HIDDEN_FUTURE_EVIDENCE | the future outcome before POST_REVEAL |
| EVIDENCE_NOT_AVAILABLE | a claim cites absent / not-yet-determined evidence as support |
| UNGROUNDED_CLAIM | a factual or interpretive claim cites nothing; an asserted value for an uncited ref |
| CATEGORY_NOT_SUPPORTED | a factual category not among the cited evidence's categories |
| VALUE_MISMATCH | an asserted value differs from the evidence |
| QUALITY_WARNING_OMITTED / UNKNOWN_QUALITY_WARNING | warnings must be preserved exactly |
| UNSUPPORTED_MARKED_SUPPORTED | an unsupported claim labeled SUPPORTED |
| CURRICULUM_SOURCE_INVALID | a curriculum rule without a lesson source, or a fact citing one |

`answer_text` is free text and is not graded; `rubric_ref_coverage` reports
which required refs an answer cites (coverage, not a grade). A model is
replaceable without changing any of these semantics.

## 9. Quality-aware grounding

Quality warnings are components whose status is QUALITY_QUALIFIED or
NOT_AVAILABLE once their window has passed (a not-yet-matured component is an
availability fact instead). The dataset warning reaches **every** lesson, even
one not authorized for DATA_QUALITY. Each warning is itself citable evidence
(`/quality_matrix/<i>/status`), is part of the rubric's quality caveats, and
must be acknowledged in every answer.

## 10. Curriculum sources and modules

`TutorCurriculumSource(source_id, title, origin, source_type, version, location,
redistributable_in_repository, notes)`:

| source_id | Type | Origin | In repository |
|---|---|---|---|
| DICKS_LAB_EVIDENCE | LABORATORY_NATIVE | this repository | yes |
| FUTURES_TREND_PLAYBOOK | PLAYBOOK | Human Product Owner | yes (`docs/trading_strategies`) |
| DRYSDALE_VWAP_WAVE_CORE_SETUP_GUIDE | EXTERNAL_GUIDE | Chris Drysdale | reference note only; the PDF is not redistributed |

Source types also cover BOOK and STUDY_GUIDE for later material. No source text
is copied beyond brief rule descriptions.

`CurriculumModule`: LAB_EVIDENCE_READING_V1 (READY_FOR_EVIDENCE_LESSONS,
executable; the example lessons) and **DRYSDALE_VWAP_WAVE_V1, registered as
NOT_READY_FOR_RULE_IMPLEMENTATION and not executable**. Building a lesson from it
raises `CurriculumNotReady` listing the missing dependencies.

## 11. Drysdale VWAP Wave: registered, deferred

Topics: Price Discovery Continuation, Fade Value Area Extremes, Return to Value,
VWAP Bounce (cross-referenced to playbook SETUP-01 … 04). Dependency matrix, the
0Z-C audit recorded as data (`DRYSDALE_DEPENDENCIES`):

| Status | Dependencies |
|---|---|
| FACT_AVAILABLE_NOW | session VWAP; price relative to VWAP; VWAP relation changes between snapshots; Initial Balance; developing Volume Profile value; prior Volume Profile value; developing value migration; replay free of hindsight |
| NEEDS_POLICY_DEFINITION | VWAP deviation bands; breakout; acceptance; backtest / retest; first sign of strength; first sign of weakness; rejection |
| NEEDS_IMPLEMENTATION | VWAP crossing path; time outside value; 5-minute price-action facts; volatility measure such as ATR |

None of the missing pieces is implemented. The module's "VWAP value area" is
band-based, not a profile percentage.

## 12. Value-area conventions

| convention_id | Fraction | Source | Computed by the Laboratory |
|---|---|---|---|
| LABORATORY_PROFILE_70 | 0.70 | DICKS_LAB_EVIDENCE (accepted Laboratory semantics) | yes |
| PLAYBOOK_NINJATRADER_68 | 0.68 | FUTURES_TREND_PLAYBOOK, CFG-05 (NinjaTrader) | no |

A lesson that uses a value area must name its convention (machine-readable in
the context). Building checks the convention against the snapshot's own value
area fractions; naming 68% for Laboratory evidence raises
`ValueAreaConventionError`. Neither is converted into, relabeled as, or
reconciled with the other.

## 13. Tutor session record (design only)

`TutorSessionRecord(schema TUTOR_SESSION_RECORD_V1, lesson_id,
lesson_definition_sha256, stage, snapshot_sha256, student_view_sha256,
student_response, tutor_response, evidence_refs, grounding, grading_outcome)`
is defined but not persisted. It would belong in a separate tutor store keyed by
the payload hash the student saw, never in a Laboratory dataset database and
never mutating replay evidence. `GradingOutcome` has only NOT_GRADED in 0AA-A.
No learning-management system is built.

## 14. API and CLI

```python
session = ReplaySession.load(db, provenance, prior_database=prior)
definition = example_lesson(session, QuestionKind.PRICE_VS_CASH_VWAP, "10:00", reveal_at="10:30")
lesson = build_tutor_lesson(session, definition)
student_view(lesson, LessonStage.QUESTION)   # dict, canonical_json(...) for bytes
instructor_view(lesson)
validate_answer_grounding(answer, lesson)    # GroundingReport
```

```
uv run python scripts/dicks_lab_tutor_lesson.py DB --prior-db PRIOR --lesson vwap --at 10:00 --reveal-at 10:30
  … --stage HINT | ANSWER | POST_REVEAL       student view at a later stage
  … --instructor                              answer key and future outcome
  … --lesson changes --at 12:14:01 --from 12:14:00 --json
```

Lessons: vwap, ib, changes, value-migration, occupancy, not-yet, quality.

## 15. Not in 0AA-A

No LLM or external AI API, no semantic grading, no Drysdale rule, no VWAP bands,
no acceptance / rejection definitions, no trading recommendation, signal or
entry decision mode, no persistence of tutor sessions.
