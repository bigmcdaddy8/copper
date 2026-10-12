# 0AB-C freeze addendum: tutor integration layer (DRYSDALE_V1 market policy unchanged)

This addendum adds to the original 0AB-B record
([../0AB-B/FREEZE.md](../0AB-B/FREEZE.md)). That record is not edited: its six
sha256 lines stay as they were written before the 0AB-B real-data audit.

## Lineage

```text
Original Drysdale V1 market-policy freeze (0AB-B, 553ac27):  UNCHANGED
Tutor integration layer:                                     ADDITIVELY VERSIONED IN 0AB-C
NO DRYSDALE MARKET RULE CHANGED
```

The Product Owner authorized this on 2026-10-11 (0AB-C, Option 1: "additive edit + freeze
addendum").

## Files that still verify against FREEZE.md (byte-identical)

```text
51948f806acd86d295f1a12432d2e0e37d49ec7de709e7afc1f1b957920165af  apps/dicks_laboratory/src/dicks_laboratory/drysdale.py
8bb1e4c14da0153ddb04ca97b32a4eb28924a4763c285d747c6e629df395d29a  docs/dicks_laboratory/DRYSDALE_VWAP_TRAINING_CANDIDATES.md
2a39fac87bddbfafc4cfe2a0c8078ca631cbe5d67200200a10fd376b8e1f9cb3  apps/dicks_laboratory/tests/test_drysdale.py
3143f8d63a59f88e39419751c64d5553a11a70bfc47c4f55ee5dfe1ca53b825b  apps/dicks_laboratory/src/dicks_laboratory/price_action.py
```

These four files are checked by
`test_drysdale_quality.py::test_drysdale_v1_market_rule_freeze_hashes_unchanged`.

## Integration files changed in 0AB-C

Old sha256 values are from FREEZE.md, the same as `553ac27`. New sha256 values are as committed in 0AB-C.

| File | Old sha256 | New sha256 |
|---|---|---|
| `apps/dicks_laboratory/src/dicks_laboratory/tutor_evidence.py` | `898dd904ab99b3eceba216433ded09acc55956df5483c31f540a0edfda10cbf3` | `318853db3bb8aadb7dc51075315f4afad7c18eb7977bd2472acdd74624c8e8b0` |
| `apps/dicks_laboratory/src/dicks_laboratory/tutor_ai.py` | `34b14f65ab1f8729027ae129bbe4628190f0814c1006298f77cb1a305ed47143` | `f9a702286e3126c07808f77d3a588056f661b87ad999fdc50504237f1e97f1c9` |

```text
318853db3bb8aadb7dc51075315f4afad7c18eb7977bd2472acdd74624c8e8b0  apps/dicks_laboratory/src/dicks_laboratory/tutor_evidence.py
f9a702286e3126c07808f77d3a588056f661b87ad999fdc50504237f1e97f1c9  apps/dicks_laboratory/src/dicks_laboratory/tutor_ai.py
```

**Reason for the change.** The tutor needs quality-scope evidence and grounded wording that keep
these apart:

- Globex-boundary completeness uncertainty;
- local setup-window impairment;
- other material quality warnings.

It also needs to explain validation eligibility.

**What changed (additive only):**

- in `tutor_evidence.py`:
  - source role and evidence domain `DRYSDALE_QUALITY`;
  - `_drysdale_quality_evidence`;
  - scope observations;
  - incorrect claims `QUALIFIED_MEANS_UNRELIABLE` and `BOUNDARY_AS_GAP`;
  - `drysdale_lesson(..., quality_scope=False)`;
  - `DRYSDALE_QUALITY_QUESTIONS`;
- in `tutor_ai.py`:
  - `TUTOR_SYSTEM_PROMPT_V4_DRYSDALE_QUALITY`, which is V3 plus rule 10;
  - the guard `QUALITY_SCOPE_MISSTATED`;
  - version selection.

**What did not change:**

- `TUTOR_SYSTEM_PROMPT_V2` and `TUTOR_SYSTEM_PROMPT_V3_DRYSDALE`: the text and its sha256 are unchanged, and the V3 sha256 equals the one in the 0AB-B run records (tested).
- The V3 guards.
- The default Drysdale lesson: without `quality_scope` it is the 0AB-B V3 lesson.
- Every frozen test.

**One visible side effect.** `ANSWER_JSON_SCHEMA` derives its source-role enum from
`SourceRole`, so it now also lists `DRYSDALE_QUALITY`, as 0AB-B added `DRYSDALE`.

New, unfrozen module: `drysdale_quality.py` (`DRYSDALE_CANDIDATE_QUALITY_V1`). It reads
DRYSDALE_V1 output and never changes it.
