# 0X-A — Futures Instrument Universe & Contract-Roll Foundation

**Date:** 2026-10-06/07 CDT. **Baseline:** `ede5635` (0W-5 closed).
**Collection:** disarmed throughout. `dragon` deallocated. Not booted.
**Scope:** make futures contract identity and lifecycle deterministic,
centralized and observable before the December ES roll. **Not** automatic
rolling.

```
NO SILENT PRODUCTION AUTO-ROLL
code may discover / classify / recommend / validate
the Human explicitly authorizes the production contract pin
```

Code: `apps/dicks_laboratory/src/dicks_laboratory/futures_contracts.py`, CLI
`scripts/dicks_lab_roll_check.py`, preflight wiring in
`scripts/dicks_lab_preflight.py`. Evidence: `evidence/0X-A/`.

## 1. ES schedule and deadline (verified)

| | Value | Source |
|---|---|---|
| Production pin | `/ESZ6` → `/ESZ26:XCME` → `FUTURE:CME:ES:2026-12` | `production_symbol.PINNED_ES_SYMBOL`, live metadata |
| Expiration (last trade) | **2026-12-18** (Fri). Trading stops at 08:30 CST (14:30Z) | CME rule (third Friday); Tastytrade `expiration-date` / `stops-trading-at` |
| CME customary roll | **2026-12-14** (Mon) | CME equity-index roll-date calendar (roll = Monday before the third-Friday expiration) |
| Broker roll offset | `future-product.roll.business-days-offset = 4` → also Mon 2026-12-14 | Tastytrade metadata |
| Next contract | `/ESH7` → `/ESH27:XCME` → `FUTURE:CME:ES:2027-03`, expires 2027-03-19 | live metadata (`next-active-month: true`) |
| Warning window opens | **TD 2026-11-30** (Mon) | this policy (§6) |
| Deploy-by deadline | **before Sun 2026-12-13 17:00 CT** (the open of TD 2026-12-14) | session model |
| Fail-closed date | **TD 2026-12-14** (ROLL_DUE) if `/ESZ6` is still pinned; the Sunday 12-13 16:42 CT preflight refuses | 0X-B policy (§15) |

**CME verification note.** cmegroup.com refuses automated fetches (HTTP
403). The CME roll-dates page, as indexed by search, states the rule (Monday
before the third Friday) and the December 2026 dates (roll 12-14, expiration
12-18). Two independent checks agree: Tastytrade's expiration date and roll
offset, and the September 2026 pair (09-14 / 09-18) recorded in 0W-4B. The
Human should eyeball <https://www.cmegroup.com/trading/equity-index/rolldates.html>
once when approving the December roll.

## 2. Inventory of existing instrument assumptions (audited before any change)

**Production pin (concept C). Already centralized in 0W-4B. Unchanged:**

| Location | Assumption | Status |
|---|---|---|
| `production_symbol.py` | `PINNED_ES_SYMBOL = "/ESZ6"` | the single source of truth |
| `deploy/.../dicks-lab-es-session.service` | `--symbol /ESZ6` in `ExecStart` | test-enforced equal to the constant |
| `scripts/dicks_lab_collect_es.py` | CLI default = pin; `resolve_es_contract` at startup | metadata-verified |
| `scripts/dicks_lab_preflight.py` | pin + `expected_streamer_symbol` | **0X-A: adds roll status** |

**ES-specific production validation (kept; works, test-covered):**
`es_contract.py`. It hard-codes the ES root, quarterly codes `HMUZ`,
`/ES[HMUZ]\d` single-digit years, and `expected_streamer_symbol` assuming
the `2` decade digit (`/ESZ6` → `/ESZ26:XCME`, valid through 2029). The new
general model takes the streamer symbol and year from metadata, never from
the decade. The collector path was deliberately not refactored in this
phase.

**General futures domain (already instrument-driven):**
`models.InstrumentIdentity` (kind/exchange/root/year/month →
`FUTURE:CME:ES:2026-12`), `store.py` (instrument columns), `audit.py`,
`long_running_capture.py`, `vwap.py`, `dataset_state.py`. No contract
coupling.

**ES-specific analytics/session assumptions (correct for the current
universe; noted, not changed):**
- `sessions.py` `ES_GLOBEX` = the CME equity-index session. It is shared by
  ES/MES/NQ/MNQ, so it is correct for the whole initial universe. Holidays are
  not modeled (already documented).
- `volume_profile.py` `ES_PRICE_GRID` is the only defined grid. Volume
  profile / developing profile on an MES/NQ/MNQ dataset would raise "No price
  grid". The fix is a one-line grid each, when such capture is ever approved.
- `fixture.py` is the synthetic Sep-2026 ES dataset (test fixture).

**Historical / experimental hard-codes (Phase 0L–0O tools; not production;
left as-is):** `live_capture.py` (`/ESU6`, `/ESU26:XCME`, ES 2026-09
constants), `scripts/dicks_lab_capture_dataset.py` (accepts only `/ESU6`),
`scripts/dicks_lab_es_vwap_experiment.py`,
`scripts/dicks_lab_quote_rate_experiment.py`. These are bounded single-contract
research tools. They would fail loudly, not silently, against an expired
contract. **BACKLOG:** retire them or generalize them onto
`futures_contracts`.

**Docs/comments:** `dicks-lab-preflight-gate.service` header comment still
says `/ESU6 -> /ESU26:XCME`. It is cosmetic only, and is left unchanged so
the deployed unit file does not drift from git. Tests/fixtures use
`/ESU6`/`/ESZ6` deliberately as contract-independent examples.

**Dataset metadata:** every dataset stores its exact `instrument_id` and
`source_locator` (e.g. `TASTYTRADE_DXLINK:/ESZ26:XCME:TimeAndSale`). It is
correct per contract and never rewritten.

## 3. Futures contract domain model

`FuturesContract` (parsed only from a broker `list_futures()` row):

| Field | Source |
|---|---|
| `root`, `exchange` | `product-code`, `exchange` (root must equal the symbol root) |
| `month_code`, `contract_month` | display symbol (`MONTH_CODES`, all 12 codes F…Z) |
| `contract_year` | `expiration-date` year, cross-checked against the symbol's year digit(s). Never the clock or decade |
| `broker_symbol`, `streamer_symbol` | `symbol`, `streamer-symbol` |
| `instrument_id` | `InstrumentIdentity(...).canonical_id`, e.g. `FUTURE:CME:ES:2027-03` |
| `expiration_date`, `stops_trading_at` (UTC) | `expiration-date`, `stops-trading-at` |
| `active_month`, `next_active_month` | broker flags |
| `tradeable`, `closing_only` | `is-tradeable`, `is-closing-only` |
| `tick_size`, `multiplier` | `tick-size`, `notional-multiplier` (authoritative, not duplicated) |

Identity-relevant gaps (missing streamer, exchange or expiration; root
mismatch; expiration month or year disagreeing with the symbol) raise. Identity
is never guessed. This is a read model, not an OMS.

## 4. Instrument universe

`LABORATORY_UNIVERSE` is a small product-policy layer: root, exchange,
description, listed cycle, roll rule, micro→standard relation. It does not
enable capture. ES remains the only production product.

| Root | Description | Cycle | Micro of | Live: tick / multiplier |
|---|---|---|---|---|
| ES | E-mini S&P 500 | H M U Z | — | 0.25 / 50 |
| MES | Micro E-mini S&P 500 | H M U Z | ES | 0.25 / 5 |
| NQ | E-mini Nasdaq-100 | H M U Z | — | 0.25 / 20 |
| MNQ | Micro E-mini Nasdaq-100 | H M U Z | NQ | 0.25 / 2 |

The cycle lives on the product (and the broker's `listed-months` is shown
beside it), so a non-quarterly product later needs a new policy entry, not a
model change. Roll rules are named per product
(`CME_EQUITY_INDEX_MONDAY_BEFORE_EXPIRATION_V1`). An unknown rule raises.

## 5. Three separate concepts

| | Concept | Where | Example |
|---|---|---|---|
| A | Exchange contract lifecycle | `exchange_calendar_entry` → `ExchangeCalendarEntry(expiration, customary_roll, source)` | CME: roll 2026-12-14, expiry 2026-12-18 |
| B | Broker active-month metadata | `FuturesContract.active_month / next_active_month / tradeable / closing_only` | Tastytrade: `/ESZ6` active, `/ESH7` next-active |
| C | Laboratory production pin | `PINNED_ES_SYMBOL` | `/ESZ6` |

The exchange calendar is explicit data. It is a CME-published table
(`CME_EQUITY_INDEX_PUBLISHED`: 2026-09, 2026-12, flagged `CME_PUBLISHED`),
with a rule fallback flagged `RULE_DERIVED` (third Friday; roll = expiration
− 4 days = Monday). Dates are calendar `date`s. Timestamps are UTC, presented
in America/Chicago. Assessments are keyed by **futures trading date** (the
`sessions.py` classifier), never by local midnight.

## 6. Roll recommendation policy (`assess_roll`)

Inputs: the pin, the trading date, and one `list_futures()` response.
Precedence is FAIL conditions first, then the exchange phase, then broker
consistency.

| State | Severity | When |
|---|---|---|
| `PIN_INVALID` | FAIL | malformed symbol; root not in the universe; month not in its listed cycle |
| `METADATA_UNAVAILABLE` | FAIL | no/invalid metadata; the pin row lacks streamer/exchange/expiration or is internally inconsistent |
| `PIN_STALE` | FAIL | pin not listed; not tradeable; closing-only; trading date ≥ expiration date |
| `METADATA_CONFLICT` | FAIL | broker expiration ≠ exchange calendar; broker exchange ≠ product exchange |
| `ROLL_DUE` | **FAIL** (0X-B; WARN in 0X-A) | trading date ≥ customary roll date (and < expiration) |
| `ROLL_APPROACHING` | WARN | trading date ≥ roll − 14 calendar days |
| `METADATA_CONFLICT` | WARN | before the window, broker active-month ≠ pin, or broker next-active ≠ exchange successor (the pin itself is still valid) |
| `CURRENT` | OK | otherwise |

Every result carries `reasons` (plain sentences), a `recommended_action`
(`NONE` / `HUMAN: REVIEW AND PREPARE ROLL: /ESZ6 -> /ESH7` / `HUMAN: APPROVE
ROLL NOW: …` / `HUMAN: RE-PIN REQUIRED: …` / `FIX PIN` / …), and all three
concepts' facts. The successor candidate is the next listed contract in the
product's cycle that is tradeable and not closing-only. No volume, open
interest, intraday switching or continuous stitching is used (out of scope by
decision).

Live observation worth keeping: `/ESH8` is reported `is-closing-only: true`
with `closing-only-date: 2018-03-16`, a broker metadata oddity on a far
contract. The successor filter excludes closing-only rows, so it cannot be
recommended.

## 7. Proposed warning lead time and pin-validation policy

**`ROLL_LEAD_CALENDAR_DAYS = 14`** (calendar days, deliberately
holiday-agnostic and deterministic). Rationale:
- Production runs on a weekly arming rhythm, Sunday open to Friday close.
  A roll means a pin edit, a unit `ExecStart` edit, a test, a commit, a
  deploy to `dragon` and a preflight, which is naturally done at a weekend
  arming.
- The new pin must be live before the Sunday open preceding roll Monday
  (TD 12-14 opens Sun 12-13 17:00 CT).
- 14 days puts the first warning on TD 2026-11-30, giving **two weekend
  arming checkpoints (12-05/06 and 12-12/13)** with the warning visible. One
  is used for review, and the second leaves slack.
- 14 days avoids a warning that starts during Thanksgiving week but still
  arrives in time.

**Production preflight policy (implemented):**

| State | Preflight |
|---|---|
| CURRENT | PASS |
| ROLL_APPROACHING | **PASS + warning lines** |
| ROLL_DUE | **FAIL, closed (0X-B, PO decision).** Production captures the intended *lead* contract, not merely any still-tradeable one. (0X-A had proposed PASS + warning; superseded.) |
| METADATA_CONFLICT (WARN) | PASS + warning lines |
| PIN_STALE / PIN_INVALID / METADATA_UNAVAILABLE / METADATA_CONFLICT (FAIL) | **FAIL, closed.** No marker, so the launch gate does not start the collector. The pin is never changed. |

0X-B: the old pin fails from the **customary roll trading date** (ROLL_DUE).
From the **expiration trading date** it is additionally `PIN_STALE`: the 12-18
session is truncated at 08:30 CT by the last trade.

## 8. Human-approved roll workflow (not automated)

1. From TD 11-30, `dicks_lab_roll_check.py check` / preflight report
   `ROLL_APPROACHING: /ESZ6 -> /ESH7`.
2. The Human reviews `check` and `chain ES`, eyeballs the CME roll page, and
   approves `/ESZ6 → /ESH7`.
3. Run `check --roll-record-draft …` to produce the provenance draft (§10).
   The Human fills in the decision fields.
4. A commit changes `PINNED_ES_SYMBOL = "/ESH7"` and the unit `ExecStart
   --symbol /ESH7` (the existing test enforces that they agree), plus the
   roll record.
5. Deploy at a weekend arming (`git merge --ff-only`, `daemon-reload`) before
   Sun 12-13 17:00 CT. Run preflight → `CURRENT` for `/ESH7`, PASS.
6. From TD 12-14, datasets record `FUTURE:CME:ES:2027-03` /
   `/ESH27:XCME`.

There is no scheduled or unattended roll anywhere. The tool and the preflight
only recommend or block.

## 9. Historical dataset semantics

A pin change never touches existing datasets. `FUTURE:CME:ES:2026-09` and
`FUTURE:CME:ES:2026-12` datasets keep their identity forever. March data
becomes `FUTURE:CME:ES:2027-03`. Analytics already read each dataset's own
`instrument_id` (`price_grid_for_instrument`, `DatasetAudit`). There is no
implicit merge into a continuous ES series (BACKLOG).

## 10. Roll provenance model

`roll_record_draft()` (CLI `--roll-record-draft PATH`) emits a
`LABORATORY_CONTRACT_ROLL` JSON. Committed next to the pin change, it
records:

- old and new contract (broker symbol, streamer, `instrument_id`, expiration)
- CME reference (customary roll, expiration, source, rule)
- the assessment at decision time (trading date, state, reasons)
- an exact snapshot of the two broker metadata rows with `captured_at_utc`
  (public instrument metadata only)
- Human decision fields, left `null` for the Human: `approved_by`,
  `decided_at_utc`, `reason`, `effective_first_trading_date`,
  `code_config_commit`

Proposed home: `docs/dicks_laboratory/contract_rolls/<YYYY-MM-DD>_<ROOT>_<old>_to_<new>.json`.

## 11. Read-only CLI

```
uv run --frozen python scripts/dicks_lab_roll_check.py check [--trading-date YYYY-MM-DD] [--pin /ESZ6]
                                                       [--metadata-json saved.json] [--roll-record-draft out.json]
uv run --frozen python scripts/dicks_lab_roll_check.py chain {ES|MES|NQ|MNQ} [--count N] [--metadata-json saved.json]
```

The tool only calls REST `list_futures()` and never requests a quote token.
`check` exits 1 on FAIL severity, which since 0X-B includes ROLL_DUE. The exit status therefore equals production readiness: CURRENT / ROLL_APPROACHING exit 0, ROLL_DUE and all FAIL states exit 1. The output adds a `Production readiness (preflight policy)` line. The default trading date is the upcoming
one. Live output (2026-10-07): `Roll state: CURRENT (OK)`, `Recommended
production action: NONE`
(`evidence/0X-A/live_roll_check_and_chains_2026-10-07.txt`).

The offline replay of the same metadata across the window is
`evidence/0X-A/roll_schedule_replay_ES_Z6.txt`:

```
10-07 CURRENT · 11-27 CURRENT · 11-30 ROLL_APPROACHING · 12-11 ROLL_APPROACHING
12-14 ROLL_DUE · 12-17 ROLL_DUE · 12-18 PIN_STALE (FAIL, exit 1)
(0X-A capture; since 0X-B ROLL_DUE is also FAIL / exit 1 -- see evidence/0X-B/)
```

## 12. Preflight integration

`run_credential_preflight` now also returns the same single `list_futures()`
response (`futures_metadata`). `dicks_lab_preflight.py` assesses the pin for
`upcoming_trading_date(now)` (16:42 CT Sunday → Monday) and prints
`roll_trading_date=`, `roll_state= roll_severity=`, `roll_reason=` and
`roll_recommended_action=`. `PREFLIGHT_RESULT=FAIL` (exit 1) only on FAIL
severity. Existing lines are unchanged. There is still exactly one REST call
and no quote token. No systemd unit change is needed: the gate already fails
closed on a non-zero exit. **Not yet deployed to `dragon`** (it is at
`a27013b`). It ships at the next authorized arming.

Manual collector runs (`dicks_lab_collect_es.py` directly) still rely on
`resolve_es_contract` (listed / tradeable / streamer) without the roll check.
Production always goes through the preflight gate.

## 13. Tests

`tests/test_futures_contracts.py` (56) covers:
- month-code parsing, including micros and two-digit years; malformed symbols
- metadata identity, and inconsistent identity rejected
- Dec→Mar year transition
- universe and micro relations
- MES / NQ / MNQ resolution
- CME-published December 2026 dates; rule-derived March 2027
- current well before the roll; the lead-window boundary; approaching
- on the roll date; after the roll with the old pin; on expiration
- expired/unlisted pin; untradeable; closing-only
- broker says the pin is no longer active; broker next-active changed
- still tradeable but past the customary lead
- broker/exchange expiration conflict; missing metadata; missing streamer
- invalid pins; successor filtering; the pin is never mutated
- roll-record draft; upcoming trading date (CDT/CST, weekend)

`tests/test_roll_check_cli.py` (9) covers the CLI smoke tests (help, check,
approaching + draft, stale exit 1, chain) and the preflight gate (PASS when
current, approaching or due; FAIL closed when stale; one metadata call; no
quote token). Full repository: **1,326 passed**.

## 14. Backlog (kept separate)

- retire or generalize the Phase 0L–0O ES-Sep-2026 research tools (§2)
- price grids for MES/NQ/MNQ before any non-ES analytics
- CME holiday calendar (also affects sessions)
- continuous-futures stitching
- volume/open-interest roll analysis
- INVALID_DXLINK_TICK late prints
- cancel targeting a rejected print
- `es_contract.py` decade assumption (valid through 2029)

```
0X-A: READY FOR REVIEW  ->  PO 2026-10-07: PASS / ACCEPTED / CLOSED (see §15 for 0X-B)
CONTRACT-ROLL FOUNDATION: implemented, read-only, test-covered; preflight integration not yet deployed
PRODUCTION COLLECTION: DISARMED   DRAGON: DEALLOCATED
NEXT: PO REVIEW (then contract-roll live readiness at a future arming)
```

## 15. 0X-B — Contract-Roll Production Policy Hardening & Deployment (2026-10-07)

**PO decision:** 0X-A is PASS / ACCEPTED / CLOSED. The architecture, model,
CLI, provenance model, 14-day warning, Human approval workflow and the
no-silent-auto-roll principle are all accepted. **Policy correction:**
`ROLL_DUE` stays the domain assessment state, but its production consequence
is now **FAIL closed**.

**Rationale.** The production objective is to capture the *intended lead* ES
contract for the market-study dataset, not merely any still-tradeable ES
contract. The CME customary roll marks the hand-over to the next quarterly
lead month. Capturing `/ESZ6` for TD 2026-12-14…12-17 just because it is
still tradeable would violate that policy.

**Final state / severity / production-preflight table:**

| State | Severity | Production preflight | CLI `check` exit |
|---|---|---|---|
| CURRENT | OK | PASS | 0 |
| ROLL_APPROACHING (≥ roll − 14 calendar days) | WARN | **PASS + warning lines** | 0 |
| METADATA_CONFLICT, warning-level (before the window: broker active / next-active disagrees, pin itself valid) | WARN | PASS + warning lines | 0 |
| **ROLL_DUE** (≥ customary roll, < expiration) | **FAIL** | **FAIL** | 1 |
| PIN_STALE (unlisted / untradeable / closing-only / ≥ expiration) | FAIL | FAIL | 1 |
| PIN_INVALID (malformed / unknown root / month outside cycle) | FAIL | FAIL | 1 |
| METADATA_UNAVAILABLE | FAIL | FAIL | 1 |
| METADATA_CONFLICT, material (broker expiration ≠ CME calendar; exchange mismatch) | FAIL | FAIL | 1 |

A harmless early broker discrepancy (warning-level) and a production-invalid
identity conflict (FAIL) remain distinct. `RollSeverity` *is* the production
consequence. The CLI exit status equals production readiness and prints
`Production readiness (preflight policy): PASS | PASS + WARNING | FAIL`. On
ROLL_DUE the recommended action reads `ROLL REQUIRED BEFORE PRODUCTION
CAPTURE -- HUMAN APPROVAL: /ESZ6 -> /ESH7`. The successor is a
recommendation, never selected or applied.

**CME provenance.** December 2026 stays `CME_PUBLISHED` (roll 2026-12-14,
expiry 2026-12-18) and is never silently replaced by the rule. March 2027 is
currently `RULE_DERIVED` (roll 2027-03-15, expiry 2027-03-19). When approving
the December roll, the Human verifies March on the CME page. Direct automated
retrieval stays blocked (HTTP 403), which is acceptable. Adding verified March
dates to `CME_EQUITY_INDEX_PUBLISHED` is part of that roll commit.

**Production deadline.**

```
Current pin:          /ESZ6   (FUTURE:CME:ES:2026-12)
Required successor:   /ESH7   (FUTURE:CME:ES:2027-03), subject to authoritative
                      metadata verification at decision time
Deploy the explicit pin change before:  Sunday 2026-12-13 17:00 CT
  (that session open belongs to trading date 2026-12-14)
The Sunday 2026-12-13 16:42 CT preflight REFUSES (PREFLIGHT_RESULT=FAIL,
  roll_state=ROLL_DUE) if /ESZ6 is still pinned.
```

**Operational calendar.**

| When | Expected |
|---|---|
| TD 2026-11-30 (Mon) | `ROLL_APPROACHING` appears (preflight PASS + warning) |
| weekend 2026-12-05/06 | first preferred Human roll-review window: run `check` / `chain ES`, verify CME + broker metadata, approve, draft the provenance record |
| weekend 2026-12-12/13 | final deployment window |
| Sun 2026-12-13 before 17:00 CT | new production pin must be deployed (`git merge --ff-only`, `daemon-reload`), and preflight must show `/ESH7` CURRENT / PASS |
| TD 2026-12-14 | the old `/ESZ6` pin fails preflight (`ROLL_DUE`) |
| TD 2026-12-18 | `/ESZ6` expires (`PIN_STALE` as well) |

**Human roll workflow (unchanged).** The warning appears → the Human reviews
roll-check output → the Human verifies CME and broker metadata → the Human
approves the successor → the provenance record is completed in
`contract_rolls/` (see its README) → explicit production-pin commit (constant
+ unit `--symbol` + record) → deploy → preflight validates the new pin. There
is no unattended roll and no code path changes `PINNED_ES_SYMBOL`.

**Tests.** These are in addition to 0X-A:
- the December transition table:
  - 11-29 CURRENT/PASS
  - 11-30 and 12-11 APPROACHING/PASS + warning
  - 12-13 APPROACHING
  - 12-14, 12-15 and 12-17 ROLL_DUE/FAIL
  - 12-18 PIN_STALE/FAIL
- the real Sunday 2026-12-13 22:42Z (16:42 CST) preflight, which resolves to
  TD 2026-12-14:
  - `/ESZ6` → `ROLL_DUE`, `PREFLIGHT_RESULT=FAIL`
  - an explicit `/ESH7` pin with Dec-13 broker metadata → `CURRENT`,
    `PREFLIGHT_RESULT=PASS`
- CLI exit = production readiness
- a warning-level early discrepancy stays WARN
- December keeps `CME_PUBLISHED` provenance
- the production pin (constant, source bytes, unit bytes) is unchanged after
  assessment, CLI and preflight runs

**Unit consistency.** The stale `/ESU6 -> /ESU26:XCME` header comment in
`dicks-lab-preflight-gate.service` was corrected (comment lines only; the
non-comment content is byte-identical) and installed on `dragon` so the
installed copy equals git. All six units' installed sha256 equal the repo.
`systemd-analyze verify` is clean for them. The es-session unit still pins
`--symbol /ESZ6` = `PINNED_ES_SYMBOL`.

**Deployment (2026-10-07Z, `evidence/0X-B/`).**
- Start-Dragon job `8dff1ce9…` (user-started).
- Gate timers verified still disabled.
- `git fetch` + `merge --ff-only` from `a27013b` to `25ec3eb`.
- `uv sync --frozen --all-packages`.
- Clean tree.

The REST-only readiness smoke on `dragon` used `list_futures()` only. There
was no quote token, no gate marker and no capture.

| Check | Result |
|---|---|
| live production preflight (TD 2026-10-07, `/ESZ6`) | `roll_state=CURRENT`, `PREFLIGHT_RESULT=PASS` |
| live `check` | CURRENT (OK), readiness PASS, exit 0 |
| 2026-11-30 `/ESZ6` (live metadata) | ROLL_APPROACHING (WARN), PASS + WARNING, exit 0 |
| 2026-12-11 `/ESZ6` | ROLL_APPROACHING, PASS + WARNING, exit 0 |
| 2026-12-14 `/ESZ6` (live and Dec-13-derived metadata) | ROLL_DUE (FAIL), FAIL, exit 1 |
| 2026-12-14 `/ESH7` (Dec-13-derived metadata) | CURRENT (OK), PASS, exit 0 |
| 2026-12-18 `/ESZ6` | PIN_STALE (FAIL), exit 1 |
| 0X-B test files on deployed code | 107 passed |

"Dec-13-derived metadata" means the live ES rows with only `active-month` /
`next-active-month` advanced to `/ESH7` / `/ESM7`. That is the state
Tastytrade's 4-business-day roll offset implies. It is not a real broker
response.

```
0X-A: ACCEPTED / CLOSED
0X-B: PASS — CONTRACT-ROLL PRODUCTION POLICY READY
CURRENT PRODUCTION PIN: /ESZ6
DECEMBER ROLL: HUMAN ACTION REQUIRED BEFORE 2026-12-13 17:00 CT
PRODUCTION COLLECTION: DISARMED   DRAGON: DEALLOCATED
NEXT: MARKET PROFILE / TPO DEVELOPMENT
```
