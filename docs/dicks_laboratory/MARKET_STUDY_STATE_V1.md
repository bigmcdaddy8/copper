# MARKET_STUDY_STATE_V1 — Unified Market Study State (0Z-A)

> **MarketStudyState is evidence, not opinion.**
> - MarketStudyState ≠ market opinion.
> - MarketStudyState ≠ trading recommendation.
> - FINAL_STUDY_STATE ≠ a historical as-of snapshot.
>
> The state assembles accepted Laboratory evidence for one trading date. Later
> consumers (replay, a tutor) interpret it. The state itself contains no bias,
> no setup, no score and no synthetic "overall market condition".

- **Schema id:** `MARKET_STUDY_STATE_V1` (`MARKET_STUDY_STATE_SCHEMA`). A breaking
  semantic change becomes `MARKET_STUDY_STATE_V2`; V1 is never mutated silently.
- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/market_study_state.py`.
- **CLI:** `scripts/dicks_lab_market_study_state.py`.
- **Tests:** `apps/dicks_laboratory/tests/test_market_study_state.py`.

## 1. Source / derived boundary

```
SOURCE DATA → NORMALIZED / EFFECTIVE TAPE → DERIVED ANALYTICS → UNIFIED MARKET STUDY STATE
```

- The state is built from the accepted typed objects. It does not recompute or
  redefine any of them:

| Section | Accepted object (unchanged) | Phase |
|---|---|---|
| `tpo.profile` | `TpoProfile` | 0Y-A |
| `volume_profile` | headline + distribution projected from `VolumeAtPriceProfile` / `ValueAreaResult` over the same tape and window | 0O / 0P |
| `vwap.studies` | `calculate_anchored_vwap` over the session-scoped effective tape, at the two accepted anchors | 0M / 0N |
| `tpo_structure.structure` | `ProfileStructure` | 0Y-B |
| `day_type.classification` | `DayTypeClassification` (`DAY_TYPE_V1`) | 0Y-C |
| `day_strength.strength` | `DayStructureStrength` (`DAY_STRUCTURE_STRENGTH_V1`) | 0Y-E |
| `prior_day.context` | `PriorContext` | 0Y-F |
| `cash_opening.facts` | `OpeningAuctionFacts` (`OPENING_AUCTION_FACTS_V1`) | 0Y-F |
| `overnight.session` / `.context` | `OvernightSession` / `OvernightContext` (`OVERNIGHT_CONTEXT_V1`) | 0Y-G |
| `cash_opening.path_facts` | `OpeningPathFacts` (`OPENING_PATH_FACTS_V1`) | 0Y-G |
| `opening_type.classification` | `OpeningTypeClassification` (`OPENING_TYPE_V1`, frozen) | 0Y-H |

- One provenance chain: the opening-type classification is built through the
  accepted `opening_type_classification`, and the prior context, opening facts,
  overnight context and path facts in the state are the very objects that
  classification used. `check_references` enforces this (identity, not just
  equality).
- One tape load: `load_study_inputs` scopes the dataset once and passes the
  scoped context to `analyze_tpo_dataset` (new optional `context` argument; the
  default path is unchanged) and to the VWAP studies.
- `build_market_study_state` is a pure function of already-analysed inputs.
  `load_study_inputs` opens the database read-only. No network, broker, Azure
  or dragon access.

## 2. Schema (top-level fields)

| Field | Content |
|---|---|
| `schema` | `MARKET_STUDY_STATE_V1` |
| `state_temporality` | `FINAL_STUDY_STATE` (§8) |
| `temporality_note` | fixed text: end-state evidence, not knowable intraday |
| `provenance` | `analysis_git_commit`, `analysis_worktree_modified` (§6) |
| `current_dataset` | `DatasetSource` (§5) |
| `contract` | canonical instrument, root, exchange, contract month/year and month code, tick size and its price-grid policy, streamer symbol; broker symbol and multiplier as null with status `NOT_RECORDED_IN_DATASET` |
| `dataset_quality` | completeness, gap counts and intervals, per-window coverage (CASH_PROFILE, OPENING, OVERNIGHT), lifecycle qualification, 0Y-B structural qualifications |
| `vwap` | `SESSION_OPEN` (17:00 CT) and `US_CASH_OPEN` (08:30 CT) anchored VWAP: anchor, end semantics, VWAP, trade count, volume, coverage, status |
| `volume_profile` | POC, VAL, VAH, high, low, total volume, trade count, level count, VA fractions, window VWAP, policies, `(price, volume)` distribution |
| `tpo` | `TpoProfile`: window, period size, increment, high/low, IB, extensions, TPO POC/VAL/VAH, value-area %, periods, levels |
| `tpo_structure` | `ProfileStructure`: one-TPO levels and zones, upper/lower extremes with EXCESS / POOR candidates, IB extension detail, period facts |
| `day_type` | `DayTypeClassification` (candidate, direction, every condition, deferred types, quality, the day-structure facts) |
| `day_strength` | `DayStructureStrength` |
| `prior_day` | whether a prior file was supplied, its `DatasetSource`, the `PriorContext` (with outcome and exact reasons) |
| `overnight` | `OvernightSession`, `OvernightContext`, `globex_open_claimed`, `globex_open_boundary_proven`, `first_observed_overnight_trade_is_globex_open` |
| `cash_opening` | `OpeningAuctionFacts`, `OpeningPathFacts` |
| `opening_type` | the candidate set (`matched`), deferred types with reason, policy id/version, policy source sha256, frozen sha256, freeze match, policy document sha256, the full classification |
| `policy_registry` | §7 |
| `quality_matrix` | §9 |
| `evidence_classification` | §10 |
| `market_study_state_sha256` | §4 — attached at serialization, not part of the hashed payload |

Every section carries `status` (`ComponentStatus`) and `reasons`.

## 3. Serialization boundary (no database dump)

- No trade observation is serialized. The source is identified by
  `dataset_id` and `database_sha256`.
- The volume and TPO distributions are kept, compactly: one `(price, volume)`
  pair per traded level and one TPO level row (price, count, period letters).
  Overnight `volume_at_tick` (tick index, volume) is kept.
- **Omitted** (`{"$omitted": "TAPE_PATH: …"}`): `CashOpenSession.path` and
  `OvernightSession.path`. They are per-price-change tape paths (hundreds of
  thousands of points on a full day). They stay accessible through the
  accepted objects, rebuilt from the same dataset.
- **Referenced once** (`{"$ref": "<JSON pointer>"}`):

| Field | Pointer |
|---|---|
| `OpeningAuctionFacts.prior` | `/prior_day/context` |
| `OvernightContext.session` | `/overnight/session` |
| `OvernightContext.prior` | `/prior_day/context` |
| `OpeningPathFacts.opening` | `/cash_opening/facts` |
| `OpeningPathFacts.overnight` | `/overnight/context` |
| `OpeningTypeClassification.facts` | `/cash_opening/path_facts` |

## 4. Canonical JSON and the state hash

- `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)`.
- `Decimal`: plain notation (`format(d, "f")`), never an exponent; trailing
  zeros are kept as computed (`102.00` ≠ `102.0`).
- `datetime`: must be timezone-aware; written in UTC as
  `YYYY-MM-DDTHH:MM:SS.ffffffZ`.
- `timedelta`: exact seconds with 6 decimals, from integer microseconds
  (`"60.000000"`).
- `date` ISO; `time` ISO; `UUID` string; enums by value; `None` → `null`.
- Floats are refused (`TypeError`), as are naive datetimes and non-finite
  Decimals.
- **Hash:** `market_study_state_sha256 = sha256(canonical JSON of the payload
  WITHOUT the hash field)`. The hash is then attached as a top-level field and
  the document is re-serialized canonically. `verify_state_json` removes the
  field, recomputes, and also checks that the document is in canonical form.
- **No wall-clock field** is in the canonical state. A presentation wrapper
  may add a generation time outside it.
- Same datasets + same code/policies → byte-identical JSON and identical hash
  (tested; §11).
- A golden-hash test pins the fixture state. A change to any accepted analytic
  output, to the schema or to the encoding fails it. That is a V2 question,
  not a test to update casually.

## 5. Dataset identity and missing-value semantics

`DatasetSource` (current and prior each carry one):
- `dataset_id`, the resolved `trading_date`, the dataset-level
  `recorded_trading_date`, `instrument_id`, kind, origin, label;
- `source_locator` and its parsed `source_system` / `streamer_symbol` /
  `source_event_type` (e.g. `TASTYTRADE_DXLINK`, `/ESZ26:XCME`, `TimeAndSale`);
- `normalizer_version`, `collector_version`, `collector_git_commit`;
- `lifecycle_state`, `capture_started_at`, `capture_ended_at`;
- closing summary: recorded?, closed at, accepted, rejected, deferred,
  submitted, persisted, difference;
- `retained_trade_count` (what the database holds now), applied corrections
  and cancels (effective tape), `database_sha256`.

Rules:
- Anything not recorded is `null`, never `0`. A pre-0W-5B dataset has
  `submitted_events` / `persisted_events` / `accounting_difference` null. A
  dataset without a closing summary has every closing field null and
  `closing_summary_recorded: false`.
- The historical dataset is authoritative for what was captured. No live
  broker metadata is queried: `broker_symbol` and `multiplier` are null with
  `NOT_RECORDED_IN_DATASET`. The tick size comes from the Laboratory price-grid
  policy (`CME_ES_TICK_GRID_V1`).

## 6. Collection vs analysis provenance

- `current_dataset.collector_git_commit`: the code that collected the data.
- `provenance.analysis_git_commit`: the code that built the state. It is an
  explicit input. The CLI resolves `git rev-parse HEAD` unless
  `--analysis-commit` is given, and sets `analysis_worktree_modified` from
  `git status --porcelain` over the Laboratory source and the CLI
  (`null` when the commit was supplied explicitly).

## 7. Policy registry

The actual codebase constants, one entry per semantic dependency:

| Component | Policy id | Version |
|---|---|---|
| MARKET_STUDY_STATE | `MARKET_STUDY_STATE_V1` | `MARKET_STUDY_STATE_V1` |
| PRICE_GRID | `CME_ES_TICK_GRID` | `CME_ES_TICK_GRID_V1` |
| GLOBEX_SESSION | `CME_EQUITY_INDEX_GLOBEX` | `CME_EQUITY_INDEX_STANDARD_V1` |
| CASH_SESSION_ANCHOR | `US_CASH_SESSION` | `US_CASH_SESSION_V1` |
| STUDY_WINDOW | `US_CASH_PROFILE` | `US_CASH_PROFILE_V1` |
| VWAP | *(none exists; none invented)* | exact Σ(price·size)/Σ(size) over the effective tape |
| VOLUME_PROFILE_POC | `DICKS_LAB_POC_TIE_POLICY` | `V1_NEAREST_VOLUME_WEIGHTED_MEAN_THEN_LOWER_PRICE` |
| VOLUME_VALUE_AREA | `DICKS_LAB_VALUE_AREA_POLICY` | `V1_SINGLE_ROW_GREATER_VOLUME_NEAREST_POC_TIE_ABOVE` (0.70) |
| TPO_POC | `DICKS_LAB_TPO_POC_POLICY` | `V1_MAX_TPO_NEAREST_RANGE_MIDPOINT_THEN_LOWER_PRICE` |
| TPO_VALUE_AREA | `DICKS_LAB_TPO_VALUE_AREA_POLICY` | `V1_TWO_ROW_GREATER_SUM_TIE_ABOVE` |
| TPO_STRUCTURE | `DICKS_LAB_TPO_STRUCTURE_POLICY` | `V1_EXCESS_TAIL_GE_2_ROWS_POOR_EXTREME_GE_2_TPOS` |
| DAY_TYPE_V1 | `DICKS_LAB_DAY_TYPE_POLICY` | `V1_DIRECTIONAL_STATE_X_IB_SHARE` |
| DAY_STRUCTURE_STRENGTH_V1 | `DAY_STRUCTURE_STRENGTH_V1` | — |
| OPENING_AUCTION_FACTS_V1 | `OPENING_AUCTION_FACTS_V1` | — |
| OVERNIGHT_CONTEXT_V1 | `OVERNIGHT_CONTEXT_V1` | — |
| OPENING_PATH_FACTS_V1 | `OPENING_PATH_FACTS_V1` | — |
| OPENING_TYPE_V1 | `OPENING_TYPE_V1` | `V1_A_PERIOD_60S_GRACE_EXACT_REFERENCE_TEST_PRIOR_RANGE_ANCHOR`; frozen source sha256 `2b7b571c…798d7c`; the note states whether the current source matches the freeze, plus the policy document sha256 |

The registry is part of the hashed payload, so a policy change changes the
state hash.

## 8. Temporality

- `state_temporality: FINAL_STUDY_STATE` on every V1 state.
- It is end-state evidence over the complete study windows (cash
  08:30–15:00 CT; overnight 17:00–08:30 CT; VWAP to the 16:00 CT session end).
  It must never be presented as what was known at, say, 10:00 CT: the final
  TPO value area, day type, terminal price and structure did not exist then.
- Replay will produce a separate `MarketStudyStateSnapshot` (or an as-of
  temporality value) with its own knowledge cutoff. V1 reserves nothing in its
  payload for that and does not need to be discarded: a snapshot is a new
  temporality, built per component as §12 describes.

## 9. Quality model

- `ComponentStatus` per section:
  - `AVAILABLE`: computed, nothing qualifies it;
  - `QUALITY_QUALIFIED`: computed, `reasons` say why it may be incomplete;
  - `NOT_AVAILABLE`: not computed / not classifiable, `reasons` say why;
  - `NOT_APPLICABLE`: the component does not apply.
- Each section keeps its native domain status as well (opening grade,
  overnight grade, `ContextOutcome`, `ClassificationOutcome`,
  `StrengthScope`, `ClassificationStatus`).
- `quality_matrix`: one entry per component — dataset, contract, vwap,
  volume_profile, cash_tpo, tpo_structure, day_type, day_strength,
  prior_context, overnight, cash_opening, opening_type — each with `status`,
  `domain_status`, `reasons`. **No overall score**, no `quality = GOOD`.
- One unavailable section never suppresses the state: a dataset without a
  cash profile still produces a state whose profile sections are
  `NOT_AVAILABLE` with reasons.
- A consumer distinguishes "false" from "not available": every boolean fact
  that can be unknown is `bool | null` (e.g. `fully_captured: null` = capture
  interval not recorded), and every unavailable component has
  `NOT_AVAILABLE` plus reasons.
- Prior context is never omitted. Its `outcome` keeps the exact reason
  (`NO_PRIOR_PROFILE`, `CONTRACT_CHANGED`, `PRIOR_PROFILE_INCOMPLETE`,
  `MULTIPLE_PRIOR_DATASETS`), and a builder call without a prior file says so
  first. A different-contract prior is `CONTRACT_CHANGED`: no cross-contract
  price comparison and no stitching.
- Globex open (0Y-H PO decision): `globex_open_claimed` is true only when the
  capture start is recorded at or before 17:00:00 CT.
  `first_observed_overnight_trade_is_globex_open` is false otherwise; the first
  observed overnight trade is still reported and never renamed.

## 10. Evidence vs candidate (AI-safety design)

- `evidence_classification` lists JSON pointers with an `EvidenceKind`:
  `IDENTITY`, `OBSERVED_FACT`, `DERIVED_FACT`, `LABORATORY_POLICY`,
  `LABORATORY_POLICY_RESULT`, `CANDIDATE`, `DEFERRED`,
  `QUALITY_QUALIFICATION`. A test resolves every pointer in a real state.
- Candidate status is always an enum field, never only a word in a string:
  - `EXCESS_*` / `POOR_*`: `YES` / `NO` / `NOT_CLASSIFIED` at
    `/tpo_structure/structure/{upper,lower}/{excess,poor}_candidate`;
  - day type: `outcome`, `primary`, `direction`, and per-candidate
    `result` with per-condition `satisfied`;
  - opening type: per-candidate `result` (`CANDIDATE`, `NOT_CANDIDATE`,
    `NOT_CLASSIFIED`, `NOT_APPLICABLE`, `DEFERRED`) and per-condition `status`.
- `EXCESS_HIGH_CANDIDATE = YES` is a Laboratory policy output. It is not "the
  market rejected the high". An `OPEN_DRIVE` candidate remains a candidate.
- The opening-type section is a set: no primary type, no forced exclusivity.

## 11. Real-data proof

See `MARKET_STUDY_STATE_0ZA.md` and `evidence/0Z-A/`: authentic corpus dates
built twice each, byte-identical JSON, identical hashes, database sha256
unchanged.

## 12. Replay-readiness inventory

`REPLAY_READINESS` in the module; nothing here is implemented yet.

| Component | Readiness | When final / what an as-of version needs |
|---|---|---|
| provenance / policy registry | REPLAY_READY | static for an analysis commit |
| current dataset identity | REPLAY_READY | fixed at capture start |
| current dataset closing summary | FINAL_DAY_ONLY | written at close |
| contract | REPLAY_READY | fixed by the dataset identity |
| dataset quality | NEEDS AS-OF | gap evidence filtered to what was detected by the instant |
| VWAP | NEEDS AS-OF | cumulative from the anchor |
| volume profile | NEEDS AS-OF | the accepted developing-profile module (0R) is the starting point |
| TPO profile / IB | NEEDS AS-OF | periods letter in as they close; IB fixed at 09:30 CT |
| TPO structure (tails, excess/poor, one-TPO zones) | FINAL_DAY_ONLY | V1 rules are defined over the completed profile |
| DAY_TYPE_V1 | FINAL_DAY_ONLY | full study window |
| DAY_STRUCTURE_STRENGTH_V1 | FINAL_DAY_ONLY | terminal and final extensions |
| study-window terminal price | FINAL_DAY_ONLY | last eligible trade before 15:00 CT |
| prior-day context | REPLAY_READY | known before the current overnight starts |
| OVERNIGHT_CONTEXT_V1 | NEEDS AS-OF | develops 17:00–08:30; complete for any as-of ≥ 08:30 CT |
| cash open print | REPLAY_READY | fixed at the first print (≤ 60 s after 08:30) |
| opening windows 5/15/30/60 min | NEEDS AS-OF | each final at its horizon end |
| OPENING_PATH_FACTS_V1 | NEEDS AS-OF | final at 09:30 CT |
| OPENING_TYPE_V1 | NEEDS AS-OF | conditions final at 09:00 CT, quality window at 09:30 CT; before that an as-of state must say "not yet determined", never a partial candidate |
| quality matrix | NEEDS AS-OF | follows its components |

## 13. OPEN_TEST_DRIVE V1 limitation (preserved, PO §17)

`OPEN_TEST_DRIVE` under `OPENING_TYPE_V1` requires only:

```
exact reference encounter → later open cross → at least one opposite-side trade
```

It does **not** require:
- period A to end on the post-cross side;
- a minimum opposite excursion;
- a minimum persistence.

In the development corpus, 3 of the 4 Test Drive candidates ended period A
back on the probe side (09-25, 09-30, 10-06). That is evidence about V1. V1 is
not changed.

**Research hypothesis (documentation only, not implemented):**
`OPEN_TEST_DRIVE_V2_HOLD_HYPOTHESIS` — a Test Drive variant that additionally
requires the period-A terminal to be strictly on the post-cross side. It would
be a new policy id, pre-registered and frozen before any corpus run, and
judged only on unseen dates. Nothing in V1 or in the state changes because of
it.

## 14. CLI

```
uv run python scripts/dicks_lab_market_study_state.py CURRENT_DB \
    [--prior-database PRIOR_DB] [--json | --summary] [--json-out FILE] \
    [--closure YYYY-MM-DD ...] [--analysis-commit SHA] [--dataset-id UUID]
```

- `--json`: the canonical document on stdout, directly usable by automation.
- `--summary` (default): evidence by domain — Dataset / Quality, Contract,
  VWAP, Volume Profile, TPO / Initial Balance, Profile Structure, Day Type
  Candidate, Day Strength, Prior Day, Overnight, Cash Opening, Opening-Type
  Candidates, Quality Matrix, Policy Versions, State Hash. There is no
  recommendation section.
- `--json-out`: also write the canonical document to a file.
- Both databases are opened read-only and never modified.
