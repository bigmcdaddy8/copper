# Drysdale VWAP Wave: Laboratory V1 Training Candidates (0AB-B)

> Educational structure recognition. **No trade recommendation exists anywhere**:
> no buy / sell, long / short, entry, stop, target, scaling or sizing. A
> Laboratory candidate is the outcome of explicit, versioned Laboratory proxies.
> It is not Drysdale's judgment and not a trade signal.

- **Code:** `apps/dicks_laboratory/src/dicks_laboratory/drysdale.py` (`DRYSDALE_SETUP_ANALYSIS_V1`).
  The tutor integration is in `tutor_evidence.py` and `tutor_ai.py`.
- **Tests:** `apps/dicks_laboratory/tests/test_drysdale.py` (hand-built bar fixtures plus replay fixtures).
- **CLI:** `scripts/dicks_lab_drysdale_setups.py DB --prior-db PRIOR --at HH:MM [--json]`;
  `scripts/dicks_lab_tutor_lesson.py DB --lesson drysdale --question N --at HH:MM`.
- **Freeze:** the V1 policy is frozen before any real-data audit (see `evidence/0AB-B/FREEZE.md`).
  Changing a threshold or a rule requires V2.
- **Real-data study:** `DRYSDALE_TRAINING_CANDIDATES_0ABB.md` (development and descriptive evidence; not validation).

## 1. Sources and the learning philosophy

The source hierarchy, in order:

1. The Human's notes from Chris Drysdale's book *VWAP Wave System* (purchased copy).
2. The *VWAP Wave Core Setup Guide* (`DRYSDALE_VWAP_SETUP_GUIDE.md`; audited in `VWAP_PRICE_ACTION_PRIMITIVES.md` §1).
3. Accepted Laboratory evidence (0Z, 0AA and 0AB-A).
4. Explicit Laboratory V1 proxies, wherever the source stays discretionary.

Third-party text is not copied into the repository. The source statements below
are paraphrases of the Human's notes and of the guide.

Drysdale teaches a **blend of rules-based structure and discretionary judgment**.
The Human wants to learn the disciplined rules-based foundation first and to
develop discretion later through experience. The tutor therefore keeps five
voices apart:

| Voice | Meaning | Tutor claim category |
|---|---|---|
| SOURCE PRINCIPLE | what Drysdale teaches | `CURRICULUM_RULE` (Drysdale source id) |
| LABORATORY RULE | a versioned Laboratory V1 proxy and its result | `LABORATORY_POLICY_RESULT` / `CANDIDATE` |
| OBSERVED FACT | a trade, a bar's OHLC | `OBSERVED_FACT` |
| HUMAN DISCRETION | the student's judgment | not produced by the Laboratory |
| AI INTERPRETATION | a model's reading of the evidence | `AI_INTERPRETATION` |

The Laboratory does not pretend the source is more mechanical than it is. Every
mechanical rule that is ours is labeled **LABORATORY V1 OPERATIONALIZATION**,
never "Drysdale definition".

## 2. Terminology: what the source says vs. what the Laboratory does

The machine-readable version is `drysdale.SOURCE_MODEL` (`DRYSDALE_SOURCE_MODEL_V1`).

| Concept | Source status | Source says (paraphrase) | Laboratory V1 |
|---|---|---|---|
| Drysdale VWAP | SOURCE_SUPPORTED (book notes) | intraday VWAP anchored at the Globex session start, 17:00 America/Chicago | `VWAP_BANDS_GLOBEX_V1` (anchor SESSION_OPEN). The 08:30 cash VWAP is **not** Drysdale's VWAP |
| Drysdale VWAP value area | SOURCE_SUPPORTED (book notes) | VWAP ±1σ is the normal back-and-forth, dynamic value area | `DRYSDALE_VALUE_AREA_V1` = Globex VWAP ±1σ, inclusive (the V1 teaching convention) |
| outer / extreme region | SOURCE_SUPPORTED (book notes) | ±2σ: strong trend / price discovery, or exhaustion | ±2σ reach, excursion and time are **context facts only**, never a value boundary |
| profile value area | not a Drysdale VWAP concept | — | Laboratory 70% volume / TPO value area and the playbook's 68% NinjaTrader value area are **separate concepts and are never converted** |
| chart interval | SOURCE_PRACTICE | generally 5-minute charts for day trading, higher timeframes for swing trading; no single mandated timeframe | complete `BARS_5M_V1` bars: a **Laboratory instructional choice** aligned with the source's practice. Drysdale does not mandate 5-minute candles |
| breakout | SOURCE_DISCRETIONARY | multi-factor: a clear prior range / value boundary, movement beyond ±1σ, often extension toward ±2σ, volume expansion, VWAP slope in the breakout direction, limited nearby opposing reference, time of day, correlated markets / internals | `LAB_BREAKOUT_TRIGGER_V1` (trigger only) plus `DrysdaleBreakoutEvidence` (each dimension reported independently, none required) |
| acceptance | SOURCE_DISCRETIONARY | shown by **time or distance** outside / inside value; no number | `LAB_ACCEPTANCE_TIME_V1`: two consecutive complete 5-minute closes. **The source does not specify two bars**: this is a Laboratory training proxy. Distance acceptance: **source concept present, mechanical threshold not specified** (no Laboratory rule) |
| backtest / retest | SOURCE_DISCRETIONARY | a pullback that tests the band again, possibly more than once | `LAB_RETEST_V1` (no proximity rule) |
| rejection | SOURCE_DISCRETIONARY | touch or approach the band, wick / excursion, return; contrasted with acceleration through the band | `LAB_REJECTION_V1` (a narrow geometric proxy) |
| acceleration | SOURCE_DISCRETIONARY | movement that continues through the band | facts only; there is no `ACCELERATION` label |
| first sign of strength / weakness | SOURCE_DISCRETIONARY | contextual: higher-timeframe trend, no major divergence, pullback volume, ability to move away from VWAP, failure / success of repeated bounce attempts | `LAB_DIRECTIONAL_CONFIRMATION_V1` (named so as not to be called "Drysdale strength") |
| return to value | SOURCE_DISCRETIONARY | price comes back inside the VWAP value area; a backtest may not occur | `LAB_RETURN_TO_VALUE_V1`, then `LAB_ACCEPTANCE_TIME_V1` inside |
| VWAP bounce | SOURCE_DISCRETIONARY | trend resumption after a pullback to VWAP in an already trending market; trend definition, test tolerance and confirmation are discretionary | `LAB_VWAP_TEST_V1` + `LAB_TREND_CONTEXT_V1` + `LAB_DIRECTIONAL_CONFIRMATION_V1` |
| trend | SOURCE_DISCRETIONARY | an already trending market | `LAB_TREND_CONTEXT_V1` (a proxy, not a trend classifier) |
| volume expansion | SOURCE_DISCRETIONARY | participation matters; no threshold | `LAB_VOLUME_CONTEXT_V1`: volumes and ratios, no STRONG / WEAK label |
| VWAP slope | SOURCE_DISCRETIONARY | slope in the breakout / trend direction matters | `LAB_VWAP_SLOPE_V1`: Decimal delta plus RISING / FLAT / FALLING |
| volatility | SOURCE_DISCRETIONARY | higher-volatility days can be preferable; no threshold | `ATR_5M_V1` value and its change: **context only**, no HIGH / LOW label |
| correlated markets, internals, order flow, news | NOT_IN_LABORATORY | confirmation where available | always `NOT_AVAILABLE` (never false): `CORRELATED_MARKET_NQ`, `MARKET_INTERNALS`, `ORDER_FLOW_AGGRESSION`, `NEWS_CATALYST` |

The tutor also holds the value concepts machine-readably (`tutor_evidence.VALUE_CONCEPTS`):

| Concept | Kind | Definition |
|---|---|---|
| `DRYSDALE_VWAP_VALUE_AREA` | VWAP_SIGMA_BAND | Globex VWAP ±1σ, inclusive (`DRYSDALE_VALUE_AREA_V1`) |
| `DRYSDALE_VWAP_OUTER_CONTEXT` | VWAP_SIGMA_BAND | Globex VWAP ±2σ: outer / extreme context, not a value boundary |
| `LABORATORY_PROFILE_70` | PROFILE_FRACTION | the 70% volume / TPO profile value area |
| `PLAYBOOK_NINJATRADER_68` | PROFILE_FRACTION | the 68% NinjaTrader profile value area |

## 3. Policies (all versioned; any change requires V2)

| Policy id | Definition |
|---|---|
| `VWAP_BANDS_GLOBEX_V1` | Additive. `VWAP_BANDS_V1` arithmetic (volume-weighted population σ, exact integer zone comparisons, bands that change only on trades) over the session-scoped as-of EFFECTIVE_TAPE from the **SESSION_OPEN anchor (17:00 CT on the prior evening)** to the market cutoff; the window ends at 16:00 CT. The VWAP equals the snapshot's SESSION_OPEN (Globex) VWAP (tested). The accepted cash-anchored `VWAP_BANDS_V1` and `PRICE_ACTION_FACTS_V1` are unchanged. |
| `DRYSDALE_VALUE_AREA_V1` | Globex VWAP ±1σ, inclusive. A close strictly above +1σ is ABOVE_VALUE, strictly below −1σ is BELOW_VALUE, anything else is INSIDE_VALUE. A close exactly AT a boundary is inside. |
| `BARS_5M_V1` (reused) | Complete half-open 5-minute bars of the Globex session. Only non-empty bars count, so "consecutive" means consecutive non-empty bars. A bar's close is compared with the bands as of the bar's last trade, that trade included. "Trades at / through" a moving level uses the exact side of each trade vs the level as of that trade. A complete bar may still be revised by a later-received record (COMPLETE, not FINAL). |
| `ATR_5M_V1` (reused) | Unchanged. It is computed over the same full-session bars (equal to `PRICE_ACTION_FACTS_V1` /atr; tested). Context only. |
| `LAB_VWAP_SLOPE_V1` | The bar's Globex VWAP minus the previous complete bar's Globex VWAP (Decimal, kept visible). RISING if > 0, FALLING if < 0, **FLAT only if exactly 0** (no tolerance). |
| `LAB_VOLUME_CONTEXT_V1` | Bar volume; the previous bar's volume; the mean and median of **up to 12 preceding complete bars**; and the ratio of the bar's volume to each. No STRONG / WEAK label. |
| `LAB_BREAKOUT_TRIGGER_V1` | UP: a complete bar closes **strictly above** +1σ while the previous complete bar did not (or it is the session's first bar). DOWN is the mirror. It is a trigger only; `DrysdaleBreakoutEvidence` always accompanies it. |
| `LAB_ACCEPTANCE_TIME_V1` | Outside: **two consecutive complete closes strictly beyond the same ±1σ boundary**. Inside: two consecutive complete closes inside the inclusive −1σ…+1σ region. *The source does not specify two bars; this is a Laboratory training proxy chosen to create a reproducible rules-based learning foundation.* It was not tuned on any corpus. |
| `LAB_RETEST_V1` | Outward breakout: after the acceptance bar of the same outside episode, a complete bar trades at or through the broken boundary and closes back outside (strictly). Return to value: after the return bar, a complete bar of the same inside episode trades at or through the boundary and closes inside value. No proximity rule: an approach without a touch is **not** a retest. The closest approach is reported separately. |
| `LAB_REJECTION_V1` | A complete bar trades at or through a level and closes **strictly** back on the originating side. Drysdale does not formally define rejection this way. |
| `LAB_DIRECTIONAL_CONFIRMATION_V1` | The first subsequent complete bar (the next one) after the event bar. UP: closes above its own open **and** strictly above the event bar's high. DOWN is the mirror. |
| `LAB_RETURN_TO_VALUE_V1` | After an outside episode, the first complete close back inside value (a single close). Returning is kept separate from accepting inside. |
| `LAB_VWAP_TEST_V1` | A complete bar trades at or through the Globex VWAP, coming from the trend side. No proximity rule. |
| `LAB_TREND_CONTEXT_V1` | UP at a bar: `LAB_VWAP_SLOPE_V1` RISING (that bar vs the previous) and the close strictly above the Globex VWAP. DOWN is the mirror. A proxy, not a trend classifier. |
| `DRYSDALE_SETUP_CANDIDATES_V1` | The four family rules in §4, the state model in §5 and the quality propagation in §6. |

Episodes: an **outside episode** is a maximal run of consecutive complete closes
strictly beyond the same ±1σ boundary. An **inside episode** is a maximal run of
consecutive complete closes inside value. Every structure is evaluated within
its episode.

## 4. The four setup families

Each candidate carries `source_criteria` (SOURCE SAYS), its conditions
(LABORATORY V1 TRAINING PROXY, with status, bar and an `/bars/<i>` pointer), its
events (each test bar with acceleration facts) and its context evidence. Families
may overlap. A day can produce zero, one or several candidates, and the
Laboratory invents no precedence among them.

### Setup 1: `PRICE_DISCOVERY_CONTINUATION_CANDIDATE_V1` (per outside episode)

1. `LAB_BREAKOUT_TRIGGER_V1`: the episode's first bar.
2. `LAB_ACCEPTANCE_TIME_V1` outside: the episode's second bar.
3. `LAB_RETEST_V1`: a later bar of the episode trades at or through the broken boundary.
4. `LAB_DIRECTIONAL_CONFIRMATION_V1` in the breakout direction, at the bar after that retest.

The first retest whose next bar confirms decides. A failed confirmation is
reported, and a later retest in the same episode can still complete the
candidate. The intermediate stages are BREAKOUT_TRIGGERED, ACCEPTED_OUTSIDE,
RETEST_OBSERVED and WAITING_FOR_CONFIRMATION. None of them is a trade signal.

`DrysdaleBreakoutEvidence` is always attached. It reports:

- the distance of the trigger close beyond ±1σ, in points, ticks, σ and ATR;
- the maximum excursion beyond ±1σ, the time beyond it and the closes beyond it, all over the episode so far;
- whether ±2σ was reached, and when;
- the trigger-bar volume context;
- the VWAP delta and slope at the trigger, and whether the slope is in the breakout direction;
- the consecutive inside closes before the trigger, and whether they met inside acceptance;
- the Globex session high and low before the trigger, and whether the trigger made a new session extreme;
- the prior day high / low, overnight high / low and IB high / low: availability, side, traded through, distance (overnight levels only from 08:30 CT and IB levels only from 09:30 CT, so there is no lookahead);
- the nearest available opposing reference and its distance;
- the time of day (CT) and whether the trigger falls in the cash session;
- whether price returned inside, when, and the time to return;
- the four NOT_AVAILABLE confirmations.

### Setup 2: `FADE_VALUE_AREA_EXTREME_CANDIDATE_V1` (per accepted inside episode and boundary)

1. `LAB_ACCEPTANCE_TIME_V1` inside (the episode's second bar).
2. A later bar (of the episode, or the bar that ends it) trades at or through +1σ (−1σ).
3. `LAB_REJECTION_V1`: that bar closes strictly back inside the boundary.
4. `LAB_DIRECTIONAL_CONFIRMATION_V1` toward the interior: DOWN at the upper band, UP at the lower band.

There is no "enter on touch" and no "scale at proximity": those are execution
choices, and proximity is undefined. A test that closes beyond the boundary is
reported with its acceleration facts:

- crossed through;
- whether the next bar remains beyond;
- the volume change;
- the distance added after the cross.

### Setup 3: `RETURN_TO_VALUE_CANDIDATE_V1` (per accepted outside episode followed by an inside close)

1. `LAB_ACCEPTANCE_TIME_V1` outside.
2. `LAB_RETURN_TO_VALUE_V1` (one close).
3. `LAB_ACCEPTANCE_TIME_V1` inside: the return close and the next close.

No backtest is required, because the source allows that none occurs. A later
`LAB_RETEST_V1` of the same boundary within the inside episode is reported as
`RETURN_TO_VALUE_RETEST_PRESENT`, together with the closest approach.

### Setup 4: `VWAP_BOUNCE_CANDIDATE_V1` (per outside episode on the bounce side, up to the next outside close)

1. A prior close strictly beyond ±1σ on the bounce side.
2. A later close inside value, at or before the test.
3. `LAB_TREND_CONTEXT_V1` in the bounce direction, at the bar before the test. **Required.**
4. `LAB_VWAP_TEST_V1`.
5. `LAB_DIRECTIONAL_CONFIRMATION_V1` away from the VWAP, at the next bar.

Choice: `LAB_TREND_CONTEXT_V1` was implemented cleanly, so it is **required**
(the conservative reading). The alternative "or otherwise shows trend-context
evidence" path, and a `STRUCTURAL_CANDIDATE` state, were therefore not needed.
ATR is context only.

## 5. State model

| State | Meaning |
|---|---|
| NOT_AVAILABLE | no Globex bands (before the 17:00 anchor, or the Globex VWAP is NOT_AVAILABLE) |
| DEVELOPING | the instance exists; some Laboratory V1 condition is not satisfied |
| CANDIDATE | every Laboratory V1 condition is satisfied on AVAILABLE evidence |
| QUALITY_QUALIFIED | every condition is satisfied, but the evidence is qualified |

Condition statuses are SATISFIED, NOT_SATISFIED, PENDING and NOT_AVAILABLE.

- NOT_SATISFIED means "evaluated and not met". It can be an earlier attempt, or the episode can have ended.
- PENDING means "not met yet, and the structure can still meet it".
- `can_still_complete` says whether the instance is still open.
- Shown attempt: the first attempt that satisfies every condition, otherwise the latest of the attempts that progressed furthest.
- Instance created: from the first event that distinguishes the family. For setup 1 that is the trigger; for setup 2 the boundary test; for setup 3 the return; for setup 4 the VWAP test.
- There is no INVALIDATED state. A completed candidate stays a candidate (it was satisfied at `completed_at_utc`); later facts, such as a return inside value, are reported beside it.

## 6. Quality propagation and replay semantics

- The analysis status is the snapshot's Globex (SESSION_OPEN) VWAP component status. Its reasons include the dataset quality reasons.
- Every candidate inherits that status. A candidate whose conditions are all satisfied on qualified evidence is QUALITY_QUALIFIED, never CANDIDATE.
- V1 is conservative: it does not attribute a gap to individual bars.
- Inputs: the `replay.as_of_evidence` tape at the snapshot's cutoff, plus the snapshot's static references. Only records known before the knowledge cutoff count, and only trades before the market cutoff.
- A late print revises a complete bar only once it is known, and it can turn a CANDIDATE back into DEVELOPING (tested).
- Mutating trades after a cutoff leaves the earlier analysis byte-identical (tested).

## 7. Serialization

`DRYSDALE_SETUP_ANALYSIS_V1` uses canonical JSON (the MARKET_STUDY_STATE_V1
encoding: no floats, no wall-clock field) with `drysdale_sha256`. The document
records:

- the `snapshot_sha256` it accompanies;
- `source_model` `DRYSDALE_SOURCE_MODEL_V1`;
- all 15 policy ids.

The typed model is `DrysdaleSetupAnalysis`, made up of:

- `GlobexBands`;
- `GlobexBar` / `LevelTouch`;
- `DrysdaleContextEvidence`;
- `DrysdaleSetupCandidate`, which holds `DrysdaleSetupCondition`, `TestEvent`, `DrysdaleBreakoutEvidence`, `AcceptanceEvidence`, `VolumeContext` and `ReferenceContext`.

No consumer parses CLI text.

## 8. Tutor

### Curriculum

`DRYSDALE_VWAP_WAVE_V1` moved from NOT_READY_FOR_RULE_IMPLEMENTATION to
**LABORATORY_V1_TRAINING_CANDIDATES_AVAILABLE**, and it is now executable. Its
dependencies:

| Dependency status | Dependencies |
|---|---|
| FACT_AVAILABLE_NOW | the Globex bands, the value area, slope, volume |
| `LABORATORY_V1_PROXY` | breakout, acceptance, retest, strength, weakness, rejection, return, VWAP test, trend |
| NEEDS_POLICY_DEFINITION | distance acceptance |
| NOT_AVAILABLE | correlated market, internals, order flow, news |

The new curriculum source is `DRYSDALE_VWAP_WAVE_SYSTEM_BOOK` (BOOK; not redistributable).

### Evidence

- Domain: `DRYSDALE_SETUPS`. Source role: `DRYSDALE`.
- Items cite `/bands/*` and `/context/*`. For the latest instance of each family and direction they also cite: state, stage, `can_still_complete`, quality, each condition status, the breakout dimensions and the supporting facts.
- A non-AVAILABLE status adds the warning `DRYSDALE:drysdale`.
- Lessons that do not request the domain are byte-identical to before.

### Lesson

- `drysdale_lesson(session, at, question)` asks one of the nine `DRYSDALE_QUESTIONS` (which family is developing; which source criteria; which Laboratory V1 conditions are satisfied or missing; breakout context; ±2σ; VWAP slope; volume; candidate or developing).
- The answer key cites the evidence. Its rubric lists these incorrect claims:
  - "the market has accepted the new value" as a fact;
  - "Drysdale defines acceptance as two closes";
  - a candidate as a trade signal;
  - the cash VWAP as Drysdale's value area;
  - profile-value equivalence.

### Prompt

`TUTOR_SYSTEM_PROMPT_V3_DRYSDALE` is used **only** for Drysdale-module lessons.
Every other lesson keeps `TUTOR_SYSTEM_PROMPT_V2`, unchanged. Rule 6 of V3 teaches
the two voices:

- **SOURCE SAYS:** "acceptance" (`CURRICULUM_RULE`, Drysdale source).
- **LABORATORY V1 TRAINING PROXY:** "two consecutive completed 5m closes…" (`LABORATORY_POLICY_RESULT` / `CANDIDATE`).

### Guards (AI interpretation boundary)

In a Drysdale lesson, a claim that uses a Drysdale concept word passes only in
one of these forms:

- a `CURRICULUM_RULE` citing a Drysdale source ("Drysdale would consider volume expansion relevant context");
- an `AI_INTERPRETATION`;
- a `LABORATORY_POLICY_RESULT` / `CANDIDATE` claim that names "Laboratory V1" or the policy id, cites a DRYSDALE item **and asserts that item's value**. The validator then checks the value, so "Laboratory V1 acceptance is satisfied" passes only when the evidence says SATISFIED.

"The market accepted / rejected / broke out" is refused as an observed or derived
fact. It passes only as `AI_INTERPRETATION`. Trade advice is refused as in V2,
and "setup" is allowed in Drysdale lessons.

### Receipt-lag unit

No new tutor payload version was needed in 0AB-B: `MARKET_STUDY_DELTA_V1` and
`TUTOR_EVIDENCE_CONTEXT_V1` are unchanged. The accepted receipt-lag label
("max receipt lag of those", a duration in seconds) is therefore left as it is
and is not silently mutated. Correct it with the next payload version.

## 9. Performance reuse

`drysdale.analyze(session, …)` keeps a `DrysdaleCache` on the prepared `ReplaySession`:

- **Results per full `ReplayCutoff`.** A repeated lesson or question at the same time is a cache hit.
- **One resumable pass checkpoint.** A later cutoff resumes from the earlier pass only when both clocks move forward and nothing newly known between the two cutoffs has a market time before the earlier market cutoff. Corrections and cancels also refuse it. In every other case the pass is recomputed from the anchor (tested with a late print).

Market-time cutoff, knowledge-time cutoff and late-arrival semantics are
preserved. The resumed output is byte-identical to a fresh computation (tested).
The measurements are in the real-data study.

## 10. Known V1 behaviors (documented, not tuned)

- **Early Globex session.** In the first bars after 17:00 CT, σ is computed from very few trades. Closes beyond ±1σ, and therefore triggers and bounce prerequisites, are expected there. V1 evaluates the whole Globex session and does not exclude them.
- **Trade-level touches.** "At or through" uses trade-level touches. In an active market, ES bars often trade through a moving band, so retests and VWAP tests are frequent, which is why every proxy is narrow and sequential.
- **Pre-existing edge case.** A synthetic fixture with no trade in the first seconds after 08:30 makes the existing `tpo_opening_path._scale` raise IndexError at or after 09:30 (an empty opening window). Real captures always trade at the open. This was not changed in 0AB-B.
