# Drysdale prospective validation: pre-registered quality reporting and stratification

Registered 2026-10-11, after Product Owner acceptance of 0AB-C and **before any date of the
2026-10-12 → 2026-11-06 campaign was inspected analytically**. This document fixes how candidate
quality is counted and stratified. It does not yet fix the validation outcome measures or
hypotheses; those are registered separately before the campaign data are opened.

Policies used, unchanged: `DRYSDALE_V1` (frozen), `DRYSDALE_QUALITY_SCOPE_V1` and
`DRYSDALE_VALIDATION_ELIGIBILITY_V1` (both accepted in 0AB-C; see
[DRYSDALE_QUALITY_SCOPE.md](DRYSDALE_QUALITY_SCOPE.md)).

## 1. PO decision this rests on

```text
DO NOT change capture-start behavior during the current
2026-10-12 through 2026-11-06 campaign.

Use ELIGIBLE_QUALITY_QUALIFIED as the expected validation
baseline for Globex-anchored Drysdale candidates.
```

- No boundary tolerance.
- No change to the Globex anchor (17:00 CT).
- No change to collector or session semantics during the campaign to make candidates appear unqualified.

Because the collector opens each dataset at session open, every campaign date is expected to carry
`CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR`. `ELIGIBLE_UNQUALIFIED` is therefore expected to be 0. It is
still reported, never dropped.

## 2. Evaluation point

Each candidate is evaluated once, at market 16:00 CT with a knowledge cutoff after the capture
stop and dataset finalization (as in the 0AB-C audit: 16:30 CT knowledge). DEVELOPING instances
(`NOT_A_CANDIDATE`) are not counted.

## 3. Quality counts (reported separately, never collapsed)

```text
total candidates

ELIGIBLE_UNQUALIFIED

ELIGIBLE_QUALITY_QUALIFIED:
- boundary PROVENANCE
- boundary LOCAL_EVIDENCE
- UPSTREAM_REFERENCE

NOT_ELIGIBLE
```

Definitions, applied only to candidates whose eligibility is `ELIGIBLE_QUALITY_QUALIFIED`:

| Sub-count | Candidate carries |
|---|---|
| boundary PROVENANCE | `CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR` with materiality `PROVENANCE` |
| boundary LOCAL_EVIDENCE | `CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR` with materiality `LOCAL_EVIDENCE` (its evidence window includes the first Globex bar) |
| UPSTREAM_REFERENCE | any `KNOWN_GAP` or `SUSPECTED_GAP` with materiality `UPSTREAM_REFERENCE` |

A candidate can carry more than one of these (in development, three 09-29 candidates carried the
boundary as PROVENANCE and an upstream gap). So:

- each sub-count is the number of candidates carrying that reason, and the sub-counts may overlap;
- the exact reason combinations are also reported, one row per combination, so that every
  `ELIGIBLE_QUALITY_QUALIFIED` candidate is counted exactly once;
- any other qualifying reason (for example `UNTRADED_INTERVAL`) is reported in that combination
  table rather than hidden.

The four top-level counts must sum to the total.

## 4. Stratification

Every result is also reported by the following strata. The reference time of a candidate is the
**end of its completing 5-minute bar**, in CT, on the trading date's session that begins at the
17:00 CT Globex anchor.

| Stratum | Definition |
|---|---|
| time since the 17:00 Globex anchor | reference time − anchor, in minutes; reported per candidate as a continuous value |
| first Globex hour vs later | first hour: reference time ≤ 18:00 CT on the anchor day; later: otherwise |
| overnight vs cash-session | overnight: completing bar inside [17:00, 08:30) CT; cash session: completing bar inside [08:30, 15:00) CT (`US_CASH_SESSION_V1`) |

The interval [15:00, 16:00) CT is neither overnight nor cash session. Candidates completing there
are reported as their own labelled group (`POST_CASH`); they are not merged into either stratum.

No binning of time since the anchor beyond these strata is registered. Any further binning must
be registered here before the campaign data are opened.

## 5. What this does not do

- It changes no Drysdale rule, threshold, anchor or quality policy.
- It inspects no campaign date.
- It does not register outcome measures or hypotheses (to come, before inspection).
