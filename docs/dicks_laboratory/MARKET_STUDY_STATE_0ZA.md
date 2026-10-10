# 0Z-A — Unified Market Study State: real-data proof (2026-10-10)

Reference: `MARKET_STUDY_STATE_V1.md`. Evidence: `evidence/0Z-A/`.

## 1. Method

- Code: commit `73c6b6d2cb82898146e59f8983b628b8360d3d1e`
  ("feat: unified deterministic market study state"). Every state records it as
  `analysis_git_commit` with `analysis_worktree_modified: false`.
- For each date the CLI was run **twice, in separate processes**:
  - build 1: `--json` (stdout);
  - build 2: `--json-out` (canonical file), with the summary on stdout.
- Then:
  - canonical bytes compared;
  - `market_study_state_sha256` compared;
  - sha256 of every database used compared before and after.
- Databases were opened read-only from local copies. No dragon boot, no
  network, no broker access.
- Wall clock 30 min 39 s for all 10 builds; peak RSS 4.5 GB.

## 2. Results

| Trading date | Current | Prior supplied | Build 1 / 2 (s) | Bytes | Byte-identical | State sha256 | DB sha256 unchanged |
|---|---|---|---|---|---|---|---|
| 2026-09-30 | `9ac5a21e` | 09-29 `6af08205` | 260.1 / 262.2 | 115,802 | YES | `9d54e066…8aaf3d76` | YES |
| 2026-09-29 | `6af08205` | 09-28 `843a6ca0` | 216.1 / 214.5 | 100,382 | YES | `234070dc…1bcf9e19` | YES |
| 2026-10-02 | `7e8d7b5e` | 10-01 `fe280370` | 327.6 / 286.3 | 105,769 | YES | `3fd8c5ff…06b9e1b3` | YES |
| 2026-09-21 | `64d684c9` | none | 81.0 / 81.8 | 116,255 | YES | `21fe107e…626942aa` | YES |
| 2026-08-31 | `c9ebc043` (INTERRUPTED) | 08-28 `5a5fbbce` (no profile) | 21.8 / 21.3 | 61,650 | YES | `cd84dc4c…b57d2f53` | YES |

Full hashes: `evidence/0Z-A/validation.tsv`. All five canonical documents pass
`verify_state_json`.

A preliminary 09-30 build made before the feature commit had a different hash
(`4952ba1a…`). That is expected and correct: its provenance recorded the
previous commit with a modified worktree, and provenance is part of the hashed
payload.

## 3. What each date demonstrates

- **2026-09-30 (primary human-readable proof, prior context available).** The
  state exposes the known tensions without reconciling them:
  - `DAY_TYPE_V1`: `NEUTRAL_DAY_CANDIDATE` (BOTH_SIDES);
  - `DAY_STRUCTURE_STRENGTH_V1`: dominant DOWN, 155 ticks below the IB vs 10
    above (counter/dominant 0.0645), terminal at percentile 0.0515;
  - structure: EXCESS_HIGH_CANDIDATE YES and EXCESS_LOW_CANDIDATE YES (upper
    tail 7 rows, lower tail 152 rows);
  - opening: open INSIDE the prior range and ABOVE prior value;
  - `OPENING_TYPE_V1`: OPEN_AUCTION_IN_RANGE + OPEN_TEST_DRIVE DOWN, as frozen
    in 0Y-H;
  - overnight QUALITY_QUALIFIED: capture began 0.000363 s after 17:00 CT, so
    no Globex open is claimed and the first observed trade (7739.25) is not
    renamed;
  - quality matrix: dataset QUALITY_QUALIFIED only for the overnight window,
    SESSION_OPEN VWAP qualified by the same 363 µs, everything else AVAILABLE.
- **2026-09-29.** Prior 09-28 available; OPEN_DRIVE DOWN (0Y-H agreement);
  one overnight KNOWN_GAP carried into the overnight and SESSION_OPEN VWAP
  qualifications only.
- **2026-10-02.** OPEN_AUCTION_OUT_OF_RANGE (UNQUALIFIED) +
  OPEN_TEST_DRIVE DOWN (QUALITY_QUALIFIED via its ONH reference): the
  opening-type section is QUALITY_QUALIFIED with the candidate-specific reason;
  the prior-only candidate stays UNQUALIFIED.
- **2026-09-21 (no prior).** First ES 2026-12 dataset; no file for the prior
  trading date 2026-09-18. `prior_day` is NOT_AVAILABLE with both reasons
  ("no prior dataset was supplied", "no dataset for prior trading date
  2026-09-18"); the generic OPEN_AUCTION candidate applies; TREND_DAY_CANDIDATE
  UP with a 225-tick one-sided extension; INCOMPLETE dataset (one overnight
  KNOWN_GAP) qualifies only overnight-dependent components.
- **2026-08-31 (partial / NOT_CLASSIFIED).** INTERRUPTED lifecycle, capture
  ended 08:48 CT, 4 KNOWN_GAPs. The state is still built:
  - TPO, volume profile and structure QUALITY_QUALIFIED (structure candidates
    NOT_CLASSIFIED);
  - DAY_TYPE_V1 NOT_AVAILABLE (NOT_CLASSIFIED) while strength is
    RAW_FACTS_ONLY;
  - cash opening NOT_AVAILABLE and OPENING_TYPE_V1 NOT_CLASSIFIED with the
    exact reasons;
  - the prior file was supplied (08-28) but has no study-window profile:
    `NO_PRIOR_PROFILE`, `prior_dataset_supplied: true`, and its identity is
    still recorded.

The contract-transition case (current ES 2026-12, prior ES 2026-09 →
`CONTRACT_CHANGED`, no cross-contract price comparison) has no authentic pair
in the corpus with a matching prior trading date; it is covered by a
deterministic fixture test.

## 4. Size boundary

States are 62–116 KB. The largest parts on 09-30 are the cash-opening facts
(27 KB), the TPO profile with its levels (26 KB), the structure (16 KB) and
the overnight session with `volume_at_tick` (14 KB). No trade and no tape path
is serialized.

## 5. Not done in 0Z-A

- No replay, no as-of snapshot, no intraperiod state.
- No new Market Profile concept; no policy changed; OPENING_TYPE_V1 still
  matches its freeze.
- `OPEN_TEST_DRIVE_V2_HOLD_HYPOTHESIS` is documentation only
  (`MARKET_STUDY_STATE_V1.md` §13).
