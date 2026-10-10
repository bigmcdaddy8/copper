# TPO / Market Profile Foundation (0Y-A), Structural Facts (0Y-B) and Day Structure (0Y-C)

Status: 0Y-A and 0Y-B are accepted. 0Y-B adds structural facts (§13–§21).
0Y-C adds day-structure facts and explained day-type CANDIDATES (§22–§32).
Everything here is deterministic. There is no interpretation: no opening type,
bias, initiative/responsive label, setup or signal (§12, §21, §32).

Code: `apps/dicks_laboratory/src/dicks_laboratory/tpo_profile.py` (pure profile
math), `tpo_structure.py` (0Y-B), `tpo_day_structure.py` (0Y-C),
`tpo_analysis.py` (dataset orchestration, quality, rendering),
`scripts/dicks_lab_tpo_profile.py` (read-only CLI).

## 1. Inventory: what is reused, what stays distinct

| Existing piece | Decision for TPO |
|---|---|
| `volume_profile.PriceGrid` / `price_grid_for_instrument` (exact Decimal tick index, `CME_ES_TICK_GRID_V1`) | **Reused.** Price levels are tick indices on the instrument's grid; off-grid prices are excluded and counted exactly as in Volume Profile. The tick size comes from the grid (instrument metadata), never from the algorithm. |
| `analysis.prepare_scoped_dataset` (trading-date resolution, effective-tape reconstruction, Globex session scoping) | **Reused.** TPO and Volume Profile therefore see one identical retained tape. |
| `sessions.select_trades_from_anchor` (half-open `[start, end)`) | **Reused** to select the study window. |
| `sessions.cash_session_bounds` / `US_CASH_OPEN` anchor (VWAP anchor) | **Not reused as the definition.** The TPO study window is its own versioned `StudyWindow` (`US_CASH_PROFILE`). It has the same 08:30–15:00 CT times, but it is a profile window, not a VWAP anchor. Keeping them as separate concepts lets either change without silently moving the other. |
| `volume_profile` POC tie rule (`V1_NEAREST_VOLUME_WEIGHTED_MEAN_THEN_LOWER_PRICE`) | **Distinct.** A TPO profile has no volume-weighted mean. TPO uses the nearest range midpoint, then the lower price (§6). The final "lower price" step matches the Volume POC convention. |
| `value_area` (single-row expansion, POC-anchored, tie → nearer then above) | **Distinct algorithm** (§7). TPO counts are small integers, so single-row comparisons tie constantly. TPO uses the two-row expansion. The final "tie → above" step matches the Laboratory Value Area convention. |
| `developing_profile` | Not used. A developing TPO is a later phase. |
| `quality.summarize_dataset_quality`, lifecycle state, `DatasetIdentity` capture interval | **Reused, read-only**, to qualify the report (§9). |

Shared vs distinct, in one line: TPO and Volume Profile share the tape, the
window selection and the price grid. They differ in the quantity measured
(distinct periods vs contracts) and therefore in their POC and Value Area
policies.

## 2. Time semantics (kept separate)

| Concept | 0Y-A value |
|---|---|
| Dataset capture interval | The full captured ES trading date (Globex 17:00–16:00 CT); unchanged. |
| Exchange session membership | `CME_EQUITY_INDEX_GLOBEX` (`classify_es_session`); unchanged. |
| **Study / profile window** | `US_CASH_PROFILE` (`US_CASH_PROFILE_V1`): **08:30:00–15:00:00 America/Chicago, `[start, end)`**. A Laboratory cash-study window, not "the CME session". |
| VWAP anchor | Unchanged and unrelated. |
| TPO period | 30 minutes (configurable: any length that tiles both the 390-minute window and the 60-minute IB, with at most 52 periods, e.g. 10/15/30). |

Stored timestamps stay timezone-aware UTC. Chicago time is used only to place
the window, which is built from local wall-clock times on the trading date.
So it is 13:30–20:00Z under CDT and 14:30–21:00Z under CST. No UTC open is
hard-coded anywhere. The 08:30–15:00 window never contains a DST transition,
which happens at 02:00 local.

## 3. Periods

Periods are lettered chronologically from the window start, `A–Z` then `a–z`.
At 30 minutes: `A` 08:30–09:00, `B` 09:00–09:30, … `M` 14:30–15:00. Each period
is half-open, `[start, end)`, so every eligible trade belongs to exactly one
period. A trade at exactly 09:00:00 is in `B`; a trade at exactly 15:00:00 is
outside the window. Labels are generated, not hand-listed. A period with no
eligible trade has no high/low and contributes no TPOs. It is still listed,
which is how a quiet or missing period stays visible.

## 4. Price occupancy (the TPO rule)

For each period, take its low and high (on the price grid). Mark **every grid
price from low through high inclusive** with that period's letter.

- **One TPO per period per price.** A thousand trades at one price in `C` still
  give a single `C` there.
- **TPO count at a price** = the number of distinct periods whose range
  includes that price. It is never trade count, contract volume or
  volume-at-price.
- Profile rows are every grid price from profile low to profile high. If two
  periods' ranges do not overlap (a price jump), the prices between them are
  rows with 0 TPOs. They stay in the matrix and contribute 0 to the value area.

No project evidence argued for actual-print-only occupancy, so the PO's
preferred contiguous-range rule was adopted as specified.

## 5. Profile and Initial Balance facts

- `PROFILE_HIGH`, `PROFILE_LOW`, `PROFILE_RANGE` over the study window, and a
  high/low (and trade count) for every period.
- **Initial Balance**: the periods inside the first 60 minutes, `[08:30, 09:30)`
  (A + B at 30-minute periods). `IB_HIGH`/`IB_LOW` are the max/min over those
  periods that traded. `IB_RANGE = IB_HIGH − IB_LOW`. If neither A nor B traded,
  there is no IB.
- **Range extension** (facts only): extension above = highest later-period high
  − `IB_HIGH` (0 if none exceeded it), plus the first later period that did.
  Extension below is the mirror image. Reported in points and ticks. No
  bullish/bearish or signal meaning is attached.

## 6. TPO POC (`DICKS_LAB_TPO_POC_POLICY` / `V1_MAX_TPO_NEAREST_RANGE_MIDPOINT_THEN_LOWER_PRICE`)

1. The candidates are the price(s) with the maximum TPO count.
2. Tie: choose the candidate nearest the profile-range midpoint
   `(PROFILE_HIGH + PROFILE_LOW) / 2`.
3. Still tied (two candidates equidistant): the lower price.

The result is independent of input order (tested). "Nearest the center of the
range" is a commonly described Market Profile convention, but it is not
claimed as universal. The equidistant fallback is a Laboratory choice
consistent with the Volume POC's final lower-price rule.

## 7. TPO Value Area (`DICKS_LAB_TPO_VALUE_AREA_POLICY` / `V1_TWO_ROW_GREATER_SUM_TIE_ABOVE`)

Target: 70% of total TPOs (`target_tpos = total × 0.70`, exact Decimal).

1. **Start**: the POC row alone.
2. **Expand**: while included TPOs are below the target, sum the TPOs of the
   next **two** rows above the current region and the next two below. Use fewer
   rows at a profile edge. Add the whole pair with the greater sum. If only one
   side has rows left, add that side.
3. **Tie** (equal pair sums): add the pair above.
4. **Stop** as soon as included ≥ target, or when no rows remain. Pairs are
   never split, so the achieved percentage can exceed 70%. It is always
   reported: e.g. `603/858 TPOs = 70.28%`.

Why two rows rather than the Volume Profile's single row: TPO counts are small
integers, so single-row comparisons tie constantly and the tie rule, not the
data, would decide most steps. Comparing two-row sums is a commonly described TPO
formulation in Market Profile literature. References disagree: some describe
single-row expansion for TPO too. So this is a declared Laboratory policy,
with a hand-worked trace in the tests (`test_two_overlapping_periods`,
`test_value_area_tie_adds_pair_above`).

## 8. Text rendering

`scripts/dicks_lab_tpo_profile.py DATABASE [--session cash] [--period-minutes 30]
[--trading-date D] [--dataset-id ID] [--no-matrix] [--compare-volume-profile]`

The report contains:
- a summary: dataset, instrument, trading date, window, period size, increment,
  profile high/low/range, IB high/low/range, extensions, TPO POC/VAL/VAH,
  value-area %, total TPOs, periods present
- a per-period high/low table
- the matrix

The matrix has prices descending and letters chronological. A `Marks` column
tags `POC`, `VAH`, `VAL`, `IBH` and `IBL`, and `|` marks rows inside the value
area:

```
   Price  TPO  Marks                Periods
  101.50    1    IBH                B
  101.25    1  | VAH                B
  100.75    2  | POC                AB
  100.25    1  | VAL                A
  100.00    1    IBL                A
```

Exit codes: 0 = profile computed, 1 = no trades in the window (nothing is
fabricated), 2 = bad request or unreadable dataset. The database is opened
read-only, and output contains nothing time-of-run dependent. Identical input
gives byte-identical output (tested, and checked on real data).

## 9. Dataset-quality semantics

The report always carries a `QUALITY:` block restating recorded evidence. The
TPO math is never altered to "fill" a gap.

| Recorded evidence | Shown |
|---|---|
| no KNOWN_GAP, no SUSPECTED_GAP | `COMPLETE / NO KNOWN GAPS` |
| ≥1 KNOWN_GAP | `INCOMPLETE`, `KNOWN_GAP=n`, `SUSPECTED_GAP=n`, the gap duration, gaps overlapping the study window, and "the source tape is NOT complete …" |
| SUSPECTED_GAP only | `QUALIFIED / SUSPECTED GAPS` and the counts |

It also always shows the lifecycle state (FINALIZED / OPEN / INTERRUPTED /
untracked) and whether the recorded capture interval covers the study window.
If it does not, it shows `STUDY WINDOW NOT FULLY CAPTURED`. A FINALIZED dataset
is not necessarily complete, and a gap outside the window still keeps the
dataset `INCOMPLETE`. The overlap count is reported as a separate fact.

## 10. Relationship to Volume Profile

Both are derived from the same effective tape over the same window
(`--compare-volume-profile`).

- **TPO** is a *time/opportunity* distribution: how many periods a price was
  available.
- **Volume Profile** is a *contract-volume* distribution: how many contracts
  traded there.

They are not expected to agree. The fixture test
`test_tpo_and_volume_profile_coexist_and_differ` shows a TPO POC of 100.75
against a Volume POC of 100.00, where 500 contracts traded in one period.

Source tape: the profile uses the effective tape, which is rebuilt from DXLink
provenance (corrections/cancels applied), exactly as the Volume Profile
headline does. A dataset without DXLink provenance therefore yields no
effective trades. This is existing Laboratory behaviour and is unchanged here.

## 11. Source / derived boundary

SOURCE DATA → NORMALIZED TRADE OBSERVATIONS → DERIVED TPO PROFILE. Nothing is
written. Trade observations, dataset metadata, quality events and source
ordering are untouched. The tests and the real-data smoke verify that the
database's sha256 is unchanged.

## 12. Deferred (not implemented in 0Y-A)

- opening type; day type (normal / normal variation / trend / neutral)
- single prints, excess tails, poor highs/lows, prominent POC
- multiple distributions, overnight inventory, prior-day references
- IB extensions as signals, value migration, responsive vs initiative activity
- trade setups, AI commentary
- developing (intraperiod) TPO, holiday/early-close windows, and price
  increments coarser than the tick (the grid accepts any `PriceGrid`, but
  aggregation into coarser rows is not built yet)

---

# 0Y-B — Structural facts

Code: `tpo_structure.py`, a pure derived layer over `TpoProfile` that never
alters it. It is rendered by `tpo_analysis.render_structure` and enabled with
`--structure` on the same CLI. 0Y-A output without `--structure` is
byte-identical to the accepted 0Y-A evidence; this was verified on the
2026-09-30 real dataset.

Three kinds of statement are kept apart throughout:

| Kind | Meaning | Examples |
|---|---|---|
| **OBSERVED FACT** | Mechanically true of the TPO matrix | one-TPO rows, zone bounds and letters, extreme letters and count, tail length, IB-extension amounts and periods |
| **LABORATORY STRUCTURAL POLICY** | A versioned threshold applied to facts; labelled `CANDIDATE` | `EXCESS_*_CANDIDATE`, `POOR_*_CANDIDATE` |
| **MARKET INTERPRETATION** | Meaning attributed to structure. **Not implemented.** | "unfinished auction", "must repair", "rejection", "will return", bullish/bearish, day type |

## 13. Reference survey (terminology)

Sources consulted, all secondary or educational. The CBOT's original Market
Profile manuals and Dalton's *Mind Over Markets* are the primary lineage; they
were not available here in full text and are cited only through these:

- LuxAlgo concept library: single prints, excess, poor high/low
- NexusFi: single prints / poor highs and lows / value area
- marketcalls.in Market Profile glossary
- ATAS: "Analyzing TPO: 5 important elements in Jim Dalton's opinion"
- Exocharts: single-print/tail settings
- TradingView TPO documentation and community scripts

| Term | Mechanical definition found | Agreement |
|---|---|---|
| **Single prints** | Price levels where only one period's letter appears (one TPO). Several sources reserve the term for the profile *interior* and call extreme single prints *tails*. | Broad on "one TPO"; **differs** on whether extremes count as single prints. |
| **Tail** (buying tail at the low, selling tail at the high) | Single prints at a profile extreme. Several sources require **at least two** single-print levels. | Broad on location; the minimum length is usually 2. Some tools make it configurable. |
| **Excess** | A tail at a session extreme; the "classic teaching threshold" is a tail of **≥ 2** single-print levels. Dalton's usage is broader (it can also be a gap or a fast move away). | Agreement on the ≥ 2 tail form. The broader Dalton sense is interpretive. |
| **Poor high / poor low** | A "flat" extreme: **two or more TPOs at the same extreme price**, with no tail. | Broad. Some variants use "at or *near* the extreme" or add volume. |

Material disagreements and how they are handled:

1. **Interior vs extreme single prints.** The data model keeps them as
   distinct geometric objects (§14), so either convention can be applied later.
2. **Row size.** "Two single-print levels" depends on the profile row size.
   ES charts are often drawn with coarser rows than the 0.25 tick. At tick
   rows, ≥ 2 rows is only 0.25 points of span. The threshold is therefore tied
   to the policy version and to V1's tick rows. A coarser row size would need
   a new policy version.
3. **"Near" the extreme** (poor extremes). Not adopted; V1 uses the exact
   extreme price only.
4. **Tails formed in the final period.** Some teaching discounts a tail made
   by the last period, since the session clock ended it. This is not encoded
   in the label. It is reported as a raw fact (`tail_formed_in_final_period`).
5. **What the structures mean** (rejection, unfinished business, repair).
   This is interpretation and is excluded.

## 14. Raw primitives and one-TPO zones (OBSERVED FACT)

- Every profile row keeps its TPO count, its period letters and its position:
  the rows run in ascending order from `PROFILE_LOW` to `PROFILE_HIGH` on the
  instrument `PriceGrid`.
- **One-TPO levels:** rows with exactly one TPO.
- **`OneTpoZone`:** a maximal run of *adjacent grid rows* that each have
  exactly one TPO.
  - Adjacency is integer row order on the profile grid; there is no
    floating-point comparison.
  - A row with ≥ 2 TPOs, or a 0-TPO row (a price jump between non-overlapping
    periods), ends the run.
  - Each zone reports: low, high, `level_count` (rows), `tick_count` (equal to
    rows, because V1 rows are instrument ticks), `span_points` (high − low, 0
    for a one-row zone), period letters (a zone may be made of more than one
    period), and the per-row `(price, letter)`.
- **Location (purely geometric):**
  - `UPPER_EXTREME` touches `PROFILE_HIGH`.
  - `LOWER_EXTREME` touches `PROFILE_LOW`.
  - `INTERIOR` touches neither.
  - `ENTIRE_PROFILE` touches both, which only happens when every row is
    one-TPO.
- **vs Initial Balance:** `ABOVE_IB` / `BELOW_IB` (entirely beyond),
  `INSIDE_IB` (within `[IBL, IBH]`), `OVERLAPPING_IB`, or `NO_IB`.
- **vs value area:** `ABOVE_VAH` / `BELOW_VAL`, `INSIDE_VALUE` (within
  `[VAL, VAH]`), or `OVERLAPPING_BOUNDARY`.
- **Terminology policy:** the internal object is `OneTpoZone`. Human-facing
  output says "One-TPO zones (single-print candidates)". An interior zone is
  what most references call *single prints*. An extreme zone is a *tail* (see
  §15). The word "single prints" is never used as a stored label.

## 15. Extreme structure and tail measurement (OBSERVED FACT)

The same facts are reported for each extreme (`HIGH` and `LOW`):
- the extreme price
- the letters at the exact extreme price and their count (one period vs several)
- the **tail**: the run of one-TPO rows contiguous *inward from the extreme*.
  It is 0 if the extreme row has ≥ 2 TPOs. Reported as rows, ticks, span in
  points, the innermost tail price, and the tail's period letters.
- `tail_formed_in_final_period`, which is true when the last study period
  (`M`) contributes to the tail

## 16. Candidate labels (LABORATORY STRUCTURAL POLICY)

Policy `DICKS_LAB_TPO_STRUCTURE_POLICY` / `V1_EXCESS_TAIL_GE_2_ROWS_POOR_EXTREME_GE_2_TPOS`:

| Label | Rule (V1) | Basis |
|---|---|---|
| `EXCESS_HIGH_CANDIDATE` / `EXCESS_LOW_CANDIDATE` | tail at that extreme ≥ **2** one-TPO rows (`EXCESS_MIN_TAIL_LEVELS = 2`) | The common "≥ 2 single-print tail" threshold |
| `POOR_HIGH_CANDIDATE` / `POOR_LOW_CANDIDATE` | ≥ **2** distinct periods at the *exact* extreme price (`POOR_EXTREME_MIN_TPOS = 2`) | The common "flat extreme, ≥ 2 TPOs at the same extreme price" |

- Values are `YES`, `NO` or `NOT_CLASSIFIED`. `NOT_CLASSIFIED` applies when
  fewer than two periods traded, so there was no auction across time.
- By construction the two labels never both say `YES` for one extreme:
  ≥ 2 TPOs at the extreme means the tail is 0.
- A one-row tail (one TPO at the extreme, then a multi-TPO row) is **neither**.
  It is reported as such and not forced into either label.
- The word `CANDIDATE` is deliberate. A `YES` means only that the structure
  meets the threshold. It does not claim an unfinished auction, a required
  repair, or any future price behaviour.
- The raw facts are always printed next to each label.

## 17. IB-extension detail and period range facts (OBSERVED FACT)

**`IbExtensionDetail`** reports:
- IB high/low/range
- maximum extension above and below, in points and ticks
- each extension as a fraction of the IB range, which is mathematical only. If
  the IB range is 0, the fraction is `None`, rendered "undefined (IB range = 0)",
  and `ib_range_is_zero` is set.
- every post-IB period that set a new high or low beyond all earlier highs or
  lows, with the IB counting as earlier

**`PeriodStructure`** (for every period A–M) reports:
- high and low
- `new_profile_high` / `new_profile_low` relative to all earlier periods (none
  for A, which has no earlier period)
- for post-IB periods only: `extended_ib_high` / `extended_ib_low` and the
  extension amounts
- `None` (rendered `--`) wherever a fact does not apply, such as IB periods or
  periods with no trades

There are no trend, initiative or responsive labels.

## 18. Quality qualification

Structural facts are more sensitive to missing trades than POC or value area,
because one missing burst can manufacture a one-TPO zone or a flat extreme.
The 0Y-A `QUALITY:` block is unchanged.
`TpoDatasetQuality.structural_qualifications` lists the reasons structure is
qualified:
- gap evidence (KNOWN or SUSPECTED) overlapping the study window
- `STUDY WINDOW NOT FULLY CAPTURED`
- capture interval not recorded
- lifecycle not FINALIZED

If any reason applies, the structure section opens with
**`*** STRUCTURAL FEATURES ARE QUALITY-QUALIFIED ***`** followed by the
reasons, and every `YES` candidate is suffixed `(quality-qualified)`. Facts are
still computed, nothing is filled, and nothing is suppressed.

A known gap *outside* the window (e.g. the 2026-09-29 overnight gap) keeps the
dataset `INCOMPLETE` but does not qualify the cash-window structure. The
overlap count is reported separately.

## 19. Data model (for later consumers)

`ProfileStructure` contains:
- `one_tpo_levels`
- `zones: tuple[OneTpoZone]`
- `upper` and `lower: ExtremeStructure`
- `ib_extension: IbExtensionDetail | None`
- `periods: tuple[PeriodStructure]`
- the policy id/version and thresholds

All of these are frozen dataclasses. `TpoAnalysisResult.structure` carries it.
Day-type work, replay, Market Study State and the tutor are meant to consume
these objects, not CLI text.

## 20. Text output (`--structure`)

`--structure` adds a `STRUCTURE` section after the period table:
- the qualification banner, if any
- the zone table, high to low: bounds, rows, ticks, span, periods, location,
  vs IB and vs value area
- the upper and lower extreme facts with both candidate labels and their rules
- the IB-extension detail
- the period range-fact table

The matrix gains a `Str` column: `TAIL` marks rows in an extreme one-TPO run
and `SP` marks interior one-TPO zone rows. Without `--structure`, the matrix
and the whole report are unchanged from 0Y-A.

Performance: building the structure is linear in profile rows (hundreds) and
adds negligible time. The roughly 2-minute runtime on a 1.4M-trade dataset is
still the shared tape load, which remains backlog.

## 21. Still deferred (interpretation)

- day types: Normal, Normal Variation, Trend, Neutral, Non-Trend, Double
  Distribution Trend (0Y-C later added candidates for four of them; see §26–§27)
- opening types: Open Drive, Open Test Drive, Open Rejection Reverse, Open
  Auction In/Out of Range
- initiative vs responsive activity, direction, signals, setups
- AI commentary, overnight inventory and prior-day context
- any meaning attached to excess, poor extremes or single prints

## 22. Reference survey (day types)

Sources consulted, all secondary or educational. The CBOT Market Profile
manuals (Steidlmayer) and Dalton's *Mind Over Markets* are the primary lineage
but were not available in full text. Even the type count differs across that
lineage: Steidlmayer first defined three types, later four, and *Mind Over
Markets* lists nine (Wikipedia, "Market profile").

- LuxAlgo concept library: day-type taxonomy, profile-shape taxonomy
- marketcalls.in: "Market Profile – different types of profile days"; "What
  traders really need to understand about trend days"
- Linn Software, DayTypes (RTX) indicator documentation. This is the only
  *mechanical* classifier found with published parameters.
- Wikipedia, "Market profile"
- TradingView community scripts (e.g. "Daily Volume Profile Pro"), which
  classify by volume-bin concentration rather than by IB extension

| Type | Commonly agreed traits | Ambiguous / subjective traits | Quantitative thresholds found | Differences among sources |
|---|---|---|---|---|
| **Normal** | IB contains (nearly) the whole session; rotational trade inside it; most common type | "wide" IB; "little" extension | Linn: IB range ≥ **85 %** of day range, plus an **18-tick** minimum day range | LuxAlgo: IB "contains the whole session". Linn allows a small extension. |
| **Normal Variation** | Extension beyond the IB on **one** side; less directional than a trend day | "meaningful" extension; "roughly doubling" | Linn: IB 50–84 % of day range (≈ range up to 2 × IB) | marketcalls: "range extension more than 2 times the Initial Range", which conflicts with "up to double" |
| **Trend** | Narrow IB; one-directional extension; persistent new highs/lows ("one-timeframing"); little rotation; closes near the extreme | "narrow", "relentless", "near", "elongated", "little rotation" | none published | marketcalls: POC is irrelevant on a trend day. Some sources stress single prints early in the day. |
| **Neutral** | Range extension on **both** sides of the IB | whether a token extension counts | none (no materiality threshold anywhere) | Close location splits it into Neutral Center vs Neutral Extreme. TradingView-style scripts reuse "Neutral" for an evenly spread *volume* distribution, which is a different concept. |
| **Neutral Extreme / Center** | Neutral, closing near one extreme / in the middle | "near", "middle" | none | — |
| **Non-Trend** | Narrow IB, no or negligible extension, narrow range, low participation; often before news | "narrow", "dull", "low volume" | Linn: a Normal-shaped day failing the **18-tick** minimum range (an absolute, instrument-specific constant) | Some list it as a "common addition", not canonical. |
| **Double Distribution Trend** | Small IB; first balance, a fast one-directional move, then a second balance; the two separated by single prints | "distinct", "thin band", "bulge" | none; identified visually ("shapes are only clean in hindsight", LuxAlgo) | LuxAlgo treats it as a shape; marketcalls treats it as a trend-day form |

Shared caveat (LuxAlgo): "mechanical definitions of extension multiples vary
between authors", and a type is only certain at the close.

None of the words *wide, narrow, small, large, significant, elongated,
balanced, near* was converted to a constant silently. Each threshold below is
either a published default (cited) or a named Laboratory proxy. Anything that
could not be defended is deferred (§27).

## 23. Day-structure primitive facts (DERIVED FACT)

`build_day_structure_facts(profile, structure, terminal)` returns the frozen
`DayStructureFacts`. It reads only the accepted 0Y-A profile and 0Y-B structure.

| Fact | Definition |
|---|---|
| profile range, midpoint | high − low; (high + low) / 2 (may sit between grid prices) |
| IB range, midpoint | from the 0Y-A `InitialBalance` (A + B) |
| `ib_share_of_range` | IB range / profile range. **None** when the profile range = 0 |
| `range_multiple_of_ib` | profile range / IB range. **None** when the IB range = 0 |
| extension above / below | points and ticks, from 0Y-A |
| extension above / below as multiple of IB | **None** when the IB range = 0 (from 0Y-B) |
| `periods_extending_above_ib` / `_below_ib` | every post-IB period whose high > IB high (low < IB low); the count is its length |
| `new_post_ib_high_periods` / `_low_periods` | 0Y-B: each period that beat every earlier high (IB high included) |
| POC, VAL, VAH, value-area midpoint | from 0Y-A |
| `poc_percentile`, `value_area_midpoint_percentile`, `ib_midpoint_percentile` | (price − low) / range; **None** when the range = 0 |
| periods at profile high / low, first such period | the letters at the extreme (0Y-B) and the earliest of them |
| `longest_higher_low_run` / `longest_lower_high_run` | longest chain of consecutive traded periods, each with a strictly higher low (lower high) than the previous one. A "one-timeframing" measurement; an empty period breaks the chain. |
| `periods_without_trades` | window periods with no retained trade |
| upper / lower extreme, interior one-TPO zones | the 0Y-B objects, by reference |
| `terminal` (study-window terminal price) | below |

**Study-window terminal price.** The last eligible trade in [08:30, 15:00) CT:
in window and on grid. Equal timestamps resolve to the later tape position. The
price is put on the grid scale. Also reported: its period, its percentile
within the range, and its distance from the high and the low. It is **not**
the CME settlement and not the Globex session close. No interpretation is
attached.

## 24. Directional structure (DERIVED FACT)

`directional_state` is independent of any named type and stays valid if a
naming rule changes:

| State | Rule |
|---|---|
| `NO_EXTENSION` | extension above = 0 and below = 0 |
| `UP_ONLY` | above > 0, below = 0 |
| `DOWN_ONLY` | above = 0, below > 0 |
| `BOTH_SIDES` | above > 0 and below > 0 (≥ 1 tick each) |

- **First extension:** the direction of the first post-IB period beyond the IB.
- **Last extension:** the direction of the last period that set a new post-IB
  extreme.
- Either is `BOTH_IN_SAME_PERIOD` when one period did both.
- Magnitudes are the extension facts in §23.

## 25. IB size context

"Wide" and "narrow" IB are relative judgements. Two candidate frames were
considered:

1. **IB share of the final profile range (adopted).** It is the same-day
   ratio that every reference implicitly uses ("contains the session", "range
   roughly double the IB"), and the only one with published numbers (Linn
   85 % / 50 %). It needs no history.
2. **Historical context** (IB percentile vs recent days, ATR, average daily
   range). This would be the only responsible way to say "narrow IB" or
   "narrow range" in absolute terms. It is **not** built. No rolling
   statistics were added. The types that inherently need it are deferred and
   say so (§27).

Linn's 18-tick minimum day range was **not** adopted. It is an absolute,
instrument-specific constant with no stated rationale, and it is exactly the
kind of fabricated threshold this phase avoids.

## 26. Adopted candidate policies (`DICKS_LAB_DAY_TYPE_POLICY` / `V1_DIRECTIONAL_STATE_X_IB_SHARE`)

Constants (`tpo_day_structure.py`):

| Constant | Value | Source |
|---|---|---|
| `NORMAL_MIN_IB_SHARE` | 0.85 | Linn default |
| `NORMAL_VARIATION_MIN_IB_SHARE` | 0.50 | Linn default; also the "range ≈ 2 × IB" boundary |
| `TREND_MIN_NEW_EXTREME_PERIODS` | 2 | Laboratory: the minimal literal reading of "multiple periods" |

A candidate is `YES` when every *evaluated* condition is satisfied. A
condition whose dependency lies outside the same-day profile is recorded as
`not evaluated` and does not block the match. It is printed, so the gap is
visible.

### NORMAL_DAY_CANDIDATE
- **REFERENCE DESCRIPTION:** a wide IB that contains (nearly) the whole session,
  with rotation inside it.
- **LABORATORY V1 POLICY:**
  1. `directional_state` ≠ `BOTH_SIDES`
  2. IB share ≥ 0.85
  3. *(not evaluated)* IB wide versus recent sessions
- **DOES NOT CLAIM:** that the IB was absolutely wide. The same-day profile
  cannot tell Normal from Non-Trend (§27). It also says nothing about rotation
  quality, balance, or what comes next.

### NORMAL_VARIATION_DAY_CANDIDATE (+ direction)
- **REFERENCE DESCRIPTION:** a one-sided extension that takes over mid-session,
  short of a trend day (range up to about 2 × IB).
- **LABORATORY V1 POLICY:**
  1. `UP_ONLY` or `DOWN_ONLY`
  2. 0.50 ≤ IB share < 0.85

  Direction is the extension side.
- **DOES NOT CLAIM:** that the extension was "meaningful". An IB share of
  0.84 is a 0.19 × IB extension, and the band admits it (see §31, 2026-09-02).
  It makes no claim about who was active or why, and the direction is a
  geometric side, not a bias.

### TREND_DAY_CANDIDATE (+ direction)
- **REFERENCE DESCRIPTION:** a narrow IB, relentless one-directional extension,
  persistent new extremes, little rotation, closing near the extreme.
- **LABORATORY V1 POLICY.** All four of these independently observable
  conditions must hold:
  1. `UP_ONLY` or `DOWN_ONLY` (no counter-extension)
  2. IB share < 0.50 (range more than 2 × IB)
  3. at least 2 post-IB periods each set a new extreme in that direction
  4. the study-window terminal price is strictly beyond the profile midpoint
     on the extension side (a Laboratory proxy for "closes toward the
     extreme", deliberately weaker than "near")
- **DOES NOT CLAIM:** one-timeframing, elongation, or single-print structure.
  These are reported as facts (`longest_*_run`, tails, zones) but are not
  conditions, because no reference gives a threshold. It does not claim a
  close "near" the extreme or anything about continuation.

### NEUTRAL_DAY_CANDIDATE
- **REFERENCE DESCRIPTION:** range extension on both sides of the IB.
- **LABORATORY V1 POLICY:** `BOTH_SIDES`, meaning at least 1 tick of extension
  on each side. No reference gives a materiality threshold, so none was
  invented. Both magnitudes are printed with the label.
- **DOES NOT CLAIM:** Neutral Center or Neutral Extreme (§27), that both
  extensions were material, or any balance or conflict meaning.

### Mutual exclusivity (by construction)

| `directional_state` | IB share ≥ 0.85 | 0.50 ≤ share < 0.85 | share < 0.50 |
|---|---|---|---|
| `NO_EXTENSION` (share is then exactly 1) | NORMAL | — | — |
| `UP_ONLY` / `DOWN_ONLY` | NORMAL | NORMAL_VARIATION | TREND if conditions 3 and 4 hold, else **UNCLASSIFIED** |
| `BOTH_SIDES` | NEUTRAL | NEUTRAL | NEUTRAL |

- The cells are disjoint, so at most one candidate can be `YES`.
- `test_v1_policies_are_mutually_exclusive_over_generated_days` checks this
  over 400 seeded random profiles. That test also checks that every adopted
  type, and `UNCLASSIFIED`, is reachable.
- The resolver still supports `AMBIGUOUS`, which a later policy version that
  overlaps would produce. That path is tested directly.
- The boundaries are inclusive exactly as written above (tested at 0.85 and
  0.50).

## 27. Deferred day types and the segmentation audit

| Type | Why deferred |
|---|---|
| `NON_TREND_DAY` | Its defining traits ("narrow IB", "narrow range", "low participation") are absolute or historical. Same-day it is indistinguishable from `NORMAL_DAY` (both have IB ≈ the whole range). The only numeric rule found is Linn's absolute 18-tick constant (§25). It needs historical context. |
| `NEUTRAL_EXTREME` / `NEUTRAL_CENTER` | They split on the close being "near an extreme" or "in the middle"; neither is defined. The terminal-price percentile is reported so a later policy can use it. |
| `DOUBLE_DISTRIBUTION_TREND_DAY` | Needs two distributions, a separator and migration. None of these is a primitive yet. |

**Distribution segmentation audit.** Could the TPO row-count profile support
deterministic segmentation as it is? On the real days in §31, I counted the
local TPO-count peaks (plateaus collapsed) at minimum prominence 1 / 2 / 3 / 5
TPOs:

| TD | 1 | 2 | 3 | 5 | interior one-TPO zones |
|---|---|---|---|---|---|
| 2026-09-30 | 4 | 2 | 1 | 1 | 0 |
| 2026-09-02 | 2 | 1 | 1 | 1 | 1 (51 rows) |
| 2026-09-08 | 2 | 2 | 1 | 1 | 0 |
| 2026-09-11 | 3 | 3 | 3 | 3 | 0 |
| 2026-09-07 | 2 | 1 | 1 | 0 | 0 |

- The number of "distributions" depends on a prominence parameter that no
  reference supplies. It also depends on the row size (0.25-tick rows vs the
  coarser rows used on most ES charts).
- 2026-09-02 has a real 51-row interior single-print zone, yet only one peak
  at prominence ≥ 2. This is concrete evidence that an interior zone alone
  must not imply a double distribution.

Segmentation is therefore its own piece of work: a row-size and prominence
policy, separator rules, and migration measurement. It is recorded as a
**0Y-D candidate**. The audit code is
`evidence/0Y-C/day_structure_study.py::peaks` (evidence only, not library code).

## 28. Quality behaviour (`classification_quality`)

A named type is more sensitive to missing data than a profile, so V1 grades
severity:

| Condition | Grade | Named type |
|---|---|---|
| study window not fully captured (e.g. the 14:36 CT capture end) | `NOT_CLASSIFIABLE` | `NOT_CLASSIFIED` |
| capture interval not recorded (e.g. lifecycle `OPEN`) | `NOT_CLASSIFIABLE` | `NOT_CLASSIFIED` |
| gap evidence (KNOWN/SUSPECTED) overlapping the window | `QUALITY_QUALIFIED` | evaluated; banner `*** DAY-TYPE CLASSIFICATION IS QUALITY-QUALIFIED ***` and a `(quality-qualified)` suffix |
| lifecycle not `FINALIZED` (with a recorded, covering capture interval) | `QUALITY_QUALIFIED` | as above |
| gap only outside the window (e.g. overnight), window fully captured | `UNQUALIFIED` | evaluated normally; the dataset still reads `INCOMPLETE` |

These intrinsic blockers also give `NOT_CLASSIFIED`, with reasons:
- no IB
- IB range = 0
- profile range = 0
- any window period with no retained trades (e.g. the Labor Day 12:00 CT
  halt)

In every `NOT_CLASSIFIED` case the day-structure facts are still returned.
No candidate is evaluated, so no label can leak.

## 29. Outcomes and ambiguity

| Outcome | Meaning |
|---|---|
| `CANDIDATE` | exactly one adopted policy matched. `primary` and `direction` are set. |
| `AMBIGUOUS` | more than one matched. No winner is forced; `matched` lists them. |
| `UNCLASSIFIED` | evaluated, but no adopted policy matched (e.g. a one-sided narrow-IB day that failed persistence or reversed). |
| `NOT_CLASSIFIED` | not evaluated (§28). |

Direction is always a separate field (`direction = UP / DOWN`), never part of
the type name.

## 30. Data model, explainability and CLI

The programmatic object is `TpoAnalysisResult.day_structure: DayTypeClassification`:
- policy id/version and the three thresholds
- `quality` (grade, reasons)
- `outcome`, `primary`, `direction`
- `candidates` — every evaluated policy, each a `DayTypeCandidate(day_type,
  result, direction, conditions)`
- `not_classified_reasons`
- `deferred`
- `facts`

Each `Condition` holds a `name`, a `rule` (text of the policy rule), what was
`observed` (with the actual numbers), and `satisfied` (True / False /
None = not evaluated). `.satisfied`, `.failed` and `.not_evaluated` answer
"why was it classified this way?" without parsing text. Everything is frozen,
and recomputation is deterministic.

CLI: `--day-structure` adds `DAY STRUCTURE FACTS:` and `DAY-TYPE CANDIDATES`.
For every candidate, each condition is printed as `[satisfied]`,
`[NOT satisfied]` or `[not evaluated]`, followed by its observed value. The
deferred types follow. Default output and `--structure` output are
byte-identical to the accepted 0Y-A and 0Y-B evidence on 2026-09-30.

## 31. Real-data study set (applied blindly)

Every locally available dataset whose profile exists was run. Thresholds were
fixed before any real day was looked at, and none was changed afterwards. The
other finalized datasets live on dragon, which this phase does not touch.

| TD | dataset | dataset quality | classification quality | IB | range | range/IB | IB share | ext ↑ | ext ↓ | state | new highs | new lows | tails ↑/↓, interior zones | terminal (pct) | candidate | direction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2026-09-30 | `9ac5a21e` | COMPLETE | UNQUALIFIED | 31.50 | 72.75 | 2.31 | 0.4330 | 2.50 | 38.75 | BOTH_SIDES | C | KM | 7/152, 0 | 7713.00 (0.05) | **NEUTRAL_DAY** | — |
| 2026-09-02 | `9c76e79c` | INCOMPLETE (overnight gap) | UNQUALIFIED | 39.50 | 48.25 | 1.22 | 0.8187 | 8.75 | 0.00 | UP_ONLY | CDE | — | 2/47, 1 | 7678.25 (0.73) | **NORMAL_VARIATION_DAY** | UP |
| 2026-09-08 | `e3110b72` | COMPLETE, lifecycle OPEN | NOT_CLASSIFIABLE | 37.75 | 45.50 | 1.21 | 0.8297 | 0.00 | 7.75 | DOWN_ONLY | — | KM | 55/18, 0 | 7681.00 (0.19) | NOT_CLASSIFIED | — |
| 2026-09-11 | `3716af9f` | COMPLETE, capture ended 14:36 CT | NOT_CLASSIFIABLE | 22.25 | 28.75 | 1.29 | 0.7739 | 0.00 | 6.50 | DOWN_ONLY | — | C | 3/8, 0 | 7666.25 (0.45) | NOT_CLASSIFIED | — |
| 2026-09-07 | `85eccb13` | COMPLETE (Labor Day) | UNQUALIFIED | 8.50 | 13.75 | 1.62 | 0.6182 | 0.00 | 5.25 | DOWN_ONLY | — | CD | 6/4, 0 | 7708.75 (0.38) | NOT_CLASSIFIED (H–M empty) | — |

All rows use policy `V1_DIRECTIONAL_STATE_X_IB_SHARE`. A diagnostic re-run
with the coverage gate removed would give `NORMAL_VARIATION_DAY DOWN` for
09-08 and 09-11. **That is not a classification.** It is printed only in the
evidence table, to show what the gate withholds.

Surprises, documented rather than tuned:
1. **09-30 is a `NEUTRAL_DAY` candidate on a 10-tick (0.08 × IB) upside
   extension.** The downside was 155 ticks, and the terminal price sat at the
   0.05 percentile. V1 has no materiality threshold, because no reference
   gives one. Neutral Extreme is deferred. A reader may well see this day
   differently. The facts needed to argue it are all printed.
2. **09-02 is a `NORMAL_VARIATION_DAY` candidate with only a 0.22 × IB
   extension.** The IB share was 0.8187, just under the 0.85 Normal boundary.
   The Linn band admits small extensions that a "roughly doubling" description
   would not.
3. **09-08 has trades to 15:56 CT but is `NOT_CLASSIFIED`.** Its lifecycle is
   `OPEN` with no recorded capture end, so coverage cannot be verified (§28).
4. **Diversity cannot really be judged from two classifiable days.** They did
   receive different labels, and the three blocked days were blocked for three
   different, correct reasons. A larger blind study needs the finalized
   datasets now on dragon. That is a PO decision.

Evidence: `evidence/0Y-C/`.

## 32. Still deferred

(0Y-D blind validation of the V1 policies over a 22-dataset corpus:
`MARKET_PROFILE_VALIDATION_0YD.md`. V1 is unchanged. 0Y-E adds continuous
strength facts beside the frozen label: §33–§39.)

- `NON_TREND_DAY`, `NEUTRAL_EXTREME` / `NEUTRAL_CENTER`,
  `DOUBLE_DISTRIBUTION_TREND_DAY` (§27); distribution segmentation (0Y-D
  candidate)
- historical IB/range context (percentiles, ATR)
- opening types, overnight inventory, prior-day value relationships
- bias, initiative/responsive labelling, setups, entries/exits, AI
  interpretation

## 33. Why `DAY_TYPE_V1` stays frozen (0Y-E)

0Y-D applied the V1 rules blindly to 12 eligible days
(`MARKET_PROFILE_VALIDATION_0YD.md`). The results:

| V1 label | Days | Assessment |
|---|---|---|
| NORMAL_VARIATION | 6 | plausible but needs more evidence |
| NEUTRAL | 5 | **structurally over-permissive**; 3 of 5 have a counter-extension ≤ 10 ticks |
| TREND | 1 | plausible but needs more evidence |
| NORMAL | 0 | insufficient evidence |

The quality gates and the fact layer were robust.

The PO kept V1 as the **provisional reference classification** and did not
tune it. The reasons:
- 12 days, now inspected, cannot validate a new threshold. A threshold chosen
  to "fix" known days would only describe those days.
- Historical 0Y-C / 0Y-D results must stay reproducible. Changing V1 in place
  would silently relabel them.
- The weakness 0Y-D exposed is one of **resolution**, not just thresholds. One
  label cannot say how one-sided, extended or persistent a day was. That is
  continuous evidence, so it is reported as numbers beside the label (§34).

Frozen means:
- `tpo_day_structure.py` is byte-identical to the accepted 0Y-C commit
  (sha256 `8d745aab…`). A test asserts this.
- The 0.50 / 0.85 thresholds, the 1-tick-per-side NEUTRAL rule and the
  2-period TREND rule are unchanged.
- Every 0Y-D frozen record re-analysed in 0Y-E reproduced byte-for-byte
  (§39).

## 34. Taxonomy versus structural strength

```
named candidate (DAY_TYPE_V1)  +  continuous evidence (DAY_STRUCTURE_STRENGTH_V1)
```

The label answers "which V1 rule matched". The strength vector answers "what
did the day measure". They are independent:
- strength is computed from the same `DayStructureFacts` whatever the label
  is;
- strength never feeds back into the label;
- there is no composite score. No weighting model has been validated, so
  the result stays a vector of inspectable facts for a later human or AI
  reader.

**A V1 candidate label is not a trading conclusion.** Neither the label nor
any strength number is a bias, signal, setup or forecast.

## 35. `DAY_STRUCTURE_STRENGTH_V1` fact definitions (DERIVED FACT)

Conventions:
- Ticks are grid rows (ES 0.25).
- "/ IB" divides by the IB range.
- A ratio with a zero denominator is **None (undefined)**, never 0 or ∞.
- With no Initial Balance, every extension fact is None.

| Group | Fact | Definition |
|---|---|---|
| Asymmetry | `extension_above_ticks` / `_points`; `extension_below_…` | 0Y-C IB extension (max high − IB high; IB low − min low), ≥ 0 |
| | `extension_above_per_ib`, `extension_below_per_ib` | extension / IB range |
| | `dominant_extension` | UP if above > below; DOWN if below > above; TIE if equal and > 0; NONE if both 0 |
| | `dominant_extension_ticks`, `counter_extension_ticks` | max, min of the two sides (on a TIE both equal the common value) |
| | `dominant_per_ib`, `counter_per_ib` | / IB range |
| | `counter_to_dominant` | counter / dominant. This is also smaller / larger, so it is reported once. 0 on a one-sided day; undefined when there is no extension |
| | `dominant_share_of_total` | larger / (above + below); undefined when there is no extension |
| Terminal | `terminal_price`, `terminal_timestamp_utc` | study-window terminal (§23): the last eligible trade before 15:00 CT, **not** the CME settlement |
| | `terminal_percentile` | (terminal − low) / range |
| | `terminal_from_high_ticks` / `_low_ticks`; `…_per_range` | distance to each extreme; / profile range |
| Persistence | `new_high_periods`, `new_low_periods` (+ counts) | 0Y-C post-IB periods that set a new extreme |
| | `max_consecutive_new_high_periods` / `_low_` | longest run of chronologically adjacent letters in those sets |
| | `longest_higher_low_run`, `longest_lower_high_run` | 0Y-C traded-period runs |
| | `first_extension_direction`, `last_extension_direction` | 0Y-C |
| Context | `upper_tail_rows` / `_ticks`, `lower_tail_…` | 0Y-B extreme one-TPO run |
| | `interior_one_tpo_zone_count`, `interior_one_tpo_rows` | 0Y-B interior zones; rows summed |
| | `poc_percentile`, `ib_midpoint_percentile`, `value_area_midpoint_percentile` | 0Y-C location in the profile range |

There are no labels such as BALANCED, UNBALANCED or TOKEN_COUNTER_EXTENSION.
Each would need a hidden threshold.

## 36. Quality behaviour

The 0Y-C quality gates are reused unchanged. `scope` says what the vector
represents:

| `scope` | When | Meaning |
|---|---|---|
| `FULL_STUDY_WINDOW` | V1 evaluated, quality UNQUALIFIED | a full-day measurement |
| `QUALITY_QUALIFIED` | V1 evaluated, gap evidence / lifecycle reasons | full window; `scope_reasons` lists the qualifications |
| `RAW_FACTS_ONLY` | V1 NOT_CLASSIFIED (partial window, unknown coverage, empty period, zero/no IB) | **not a full-day assessment**; `scope_reasons` = the V1 `not_classified_reasons` |

A partial study window still exposes its raw facts. It is labelled
`RAW_FACTS_ONLY`, and the text output leads with
`*** RAW FACTS ONLY -- NOT A FULL-DAY STRENGTH ASSESSMENT ***`, so it cannot
pass as a full-day strength assessment.

## 37. Policy versioning

| Policy key | What | Where |
|---|---|---|
| `DAY_TYPE_V1` | named reference taxonomy = `DICKS_LAB_DAY_TYPE_POLICY` / `V1_DIRECTIONAL_STATE_X_IB_SHARE` | `tpo_day_structure.py` (frozen) |
| `DAY_STRUCTURE_STRENGTH_V1` | continuous measurements | `tpo_day_strength.py` |

- `DAY_TYPE_POLICY_KEYS` maps the classifier's exact (id, version) stamp to
  `DAY_TYPE_V1`. An unknown stamp is refused, not guessed.
- A future change gets a **new key** (e.g. `DAY_TYPE_V2`) that coexists with
  V1. V1 results stay reproducible for replay and research.
- The same applies to the strength vector: adding, removing or redefining a
  fact means `DAY_STRUCTURE_STRENGTH_V2`.

## 38. Research hypotheses and prospective validation

The 0Y-D hypotheses (`MARKET_PROFILE_VALIDATION_0YD.md` §10) are
**RESEARCH HYPOTHESES, NOT PRODUCTION POLICY**. None is implemented in the
classifier.
- **H1:** NEUTRAL needs both extensions ≥ X × IB.
- **H2:** NORMAL_VARIATION needs extension ≥ Y × IB.
- **H3:** a token counter-extension does not block the dominant side.
- **H4:** NORMAL needs historical IB context or H3.

The strength vector makes each one measurable without adopting it:
- H1 and H3 read `counter_per_ib`;
- H2 reads `dominant_per_ib`.

The existing offline what-if script (`evidence/0Y-D/hypothesis_whatif.py`)
counts a fixed illustrative grid (0.10 / 0.25 / 0.50 / 1.00) written in the
script. None of those values is an accepted default. It reads the frozen
records only, never touches the classifier, and its output is a what-if count,
not validation. The optional helper was not expanded in 0Y-E.

**Prospective-validation principle.** The 0Y-D corpus has been inspected. A
future threshold policy (e.g. `DAY_TYPE_V2`) should be:
1. **pre-registered**: rule and thresholds written and committed first;
2. **evaluated on unseen future trading dates**, with the 0Y-D two-stage
   blind method (frozen records, then analysis).

A threshold is **not** validated because it improves the labels of the
existing 12 eligible days.

## 39. Data model, CLI and corpus report

- Programmatic: `TpoAnalysisResult.day_strength: DayStructureStrength`, built
  by `build_day_structure_strength(day_structure, price_increment)`.
  - The chain `TpoProfile → ProfileStructure → DayStructureFacts →
    DayTypeClassification → DayStructureStrength` can be consumed without
    parsing text.
  - Every strength value is read or derived from `DayStructureFacts`.
    Nothing is re-measured from trades, and the added cost once the profile is
    loaded is negligible.
  - `strength_to_json` gives one exact line (Decimals as strings).
- CLI: `--day-strength` adds the `DAY STRUCTURE STRENGTH:` section. It
  restates the V1 label, lists the numeric facts and prints both policy keys.
  - There is no interpretive language.
  - Default, `--structure` and `--day-structure` output are unchanged.
- Corpus report:
  - Command: `scripts/dicks_lab_mp_validation.py strength FROZEN_DIR OUT_DIR
    DBS...`.
  - It verifies the frozen records' sha256 and re-analyses each database.
  - It requires every rebuilt V1 record to equal the frozen 0Y-D line
    byte-for-byte; otherwise it exits 3.
  - It then writes the strength vector beside the frozen label.
  - The 0Y-D `blind_run/` is only read.
  - Evidence: `evidence/0Y-E/` (§33).

## 40. Reference survey (opening types) (0Y-F)

Sources consulted are secondary and educational. The primary lineage is
Steidlmayer (CBOT) and Dalton, *Mind Over Markets* (1990), which codified the
opening classifications. That book was not available here in full text.
- LuxAlgo concept library, "Open Types"
- marketcalls.in, "Market Profile open type and confidence"
- ATAS, "Open Drive" (open types overview)
- Reverend's Crowstack, "Five easy tapes: Open-Rejection-Reverse"
- futures.io / NexusFi "Opening Types", OAIR and OAOR articles, known from
  search summaries only (the pages refused automated fetch)

Kinds of statement:
- **REFERENCE DESCRIPTION**: what a source says (this table).
- **OBSERVED FACT**: what 0Y-F measures (§42–§47).
- **LABORATORY POLICY**: the few explicit choices in §41 and §48.
- **MARKET INTERPRETATION**: "confidence", "other-timeframe participation";
  excluded.

| Type | Mechanical description (sources) | Prior-day context used | Time horizon implied | Reference levels | Subjective words |
|---|---|---|---|---|---|
| **Open Drive** | A move away from the opening print that "never trades back through it" (LuxAlgo). Auctions "one-sided right from the beginning" (marketcalls). Moves "without significant rollbacks" (ATAS). | Usually opens outside prior value, often outside the prior range (marketcalls, ATAS). LuxAlgo does not require it. | first 30–60 min ("give the label half an hour"). marketcalls: the first-30-min extreme typically holds all day. | opening price; prior value and range | persistent, strong, focused, significant |
| **Open Test Drive** | A probe "to one side that finds no business", then a reversal through the open and a drive the other way (LuxAlgo). Tests "a key reference level (VA, POC, prior high/low) in the reverse direction" (marketcalls). ATAS: an initial focused move "then sharply reverses". | the reference tested is usually prior-day (VAH/VAL/POC/high/low) | opening period | prior high/low, VAH/VAL, POC, open | finds no business, conviction, test, sharply |
| **Open Rejection Reverse** | An early run "gets rejected and trades back through the open" (LuxAlgo). Tests a reference, rejects and auctions back (marketcalls). Crowstack: "typically within the first period (30 minutes)". NexusFi (via search): may happen without hitting any reference. | marketcalls/ATAS: opening relative to prior value. Others: none required. | first period (30 min) | open; optionally a reference | rejected, strongly, falls back |
| **Open Auction** | "Quiet rotation on both sides of the open, most often inside the prior day's value" (LuxAlgo). "Price rotates around the day open" (marketcalls). | **In Range**: opens inside the prior range (and value). **Out of Range**: opens above/below the prior range. | not stated | open; prior value and range | quiet, little conviction, rotates |

**Where the sources disagree**
- **Test Drive vs Rejection Reverse.** These are the least stable pair.
  - LuxAlgo and marketcalls: a test drive probes and then drives *away from*
    the probe; a rejection-reverse is a run that fails *back through the open*.
  - ATAS describes OTD in words others use for ORR ("moves in a focused manner
    then sharply reverses").
  - Whether ORR requires a reference touch differs: marketcalls yes, NexusFi no.
- **Location requirement for a drive.** Some sources require an open outside
  value or range; LuxAlgo does not.
- **Horizon.** Ranges from "first period" to "30–60 minutes". No source
  states a minute count as a definition.
- **Open-auction split.** In Range / Out of Range is keyed to the prior
  *range* (marketcalls, OAIR/OAOR). LuxAlgo keys open-auction to prior *value*.
- **Numbers.** No source gives a numeric threshold for anything ("Numeric
  thresholds: none"; "classification involves judgment", LuxAlgo).

None of the words *immediate, strong, aggressive, quick, near, test, drive,
rejection, conviction, significant, material* was converted into a constant.

## 41. Cash open (LABORATORY POLICY `OPENING_AUCTION_FACTS_V1`)

- **Cash open instant:** 08:30:00 America/Chicago on the trading date, through
  the existing `AnchorKind.US_CASH_OPEN` resolver.
  - UTC is derived, never hard-coded: 13:30Z under CDT, 14:30Z under CST.
  - It equals the US_CASH_PROFILE window start (asserted).
- **`cash_open_price`:** the first eligible (effective-tape, on-grid) trade at
  or after 08:30:00 CT. Ties at one timestamp are broken by tape position.
  - `cash_open_timestamp` and `delay_from_08_30` are kept.
  - **Maximum tolerated delay: 60 s.** This is a data-coverage bound, not a
    market concept. If the first eligible trade is later than that, no open
    price is claimed. The opening facts are `NOT_AVAILABLE` and the context
    outcome is `CURRENT_OPEN_INCOMPLETE`. No 08:30 price is ever invented.
- **Price path:** the cash-window tape reduced to price changes, i.e. the
  first trade at each new tick.
  - This keeps every first-reach time, high, low, last price, touch and
    crossing exactly, without the full tape.
  - It is stored on the session object (`CashOpenSession.path`), so later
    classifiers never re-read raw trades.

## 42. Prior trading-date context

`prior_trading_date(d, closures)` is the previous weekday not in `closures`.
- It is never the previous calendar day: Monday → Friday, including across
  DST changes.
- No holiday calendar is modelled. Full CME closures (e.g. Good Friday,
  Thanksgiving) must be supplied explicitly (`--closure`).
- Early-close days such as Labor Day are trading dates. Their truncated
  profile then reports as `PRIOR_PROFILE_INCOMPLETE`.

`build_prior_context(current, candidates)` selects the dataset for exactly
that date:

| Outcome | When | Prior-relative facts |
|---|---|---|
| `AVAILABLE` | one dataset, same contract, prior V1 classification evaluated | computed. `prior.quality_grade` (UNQUALIFIED / QUALITY_QUALIFIED) and its reasons travel with them. |
| `NO_PRIOR_PROFILE` | no dataset for that date, or it has no study-window profile | none |
| `CONTRACT_CHANGED` | the prior dataset is another contract | none; no prices carried, **no stitching or back-adjustment**, no continuous ES |
| `PRIOR_PROFILE_INCOMPLETE` | the prior day's V1 classification was NOT_CLASSIFIED (window not captured, coverage unknown, empty periods, no/zero IB) | none. Raw references are shown, labelled incomplete. |
| `MULTIPLE_PRIOR_DATASETS` | more than one dataset for that date | none (no silent choice) |
| `CURRENT_OPEN_INCOMPLETE` | the current day's opening facts are NOT_AVAILABLE | none |

The prior context exposes:
- range, TPO POC/VAH/VAL, IB high/low and the study-window terminal (last
  eligible trade, not the settlement);
- V1 day type and direction;
- `DayStructureStrength`;
- the prior classification quality and dataset quality status.

So `CURRENT_DAY_QUALITY` (§48) and `PRIOR_DAY_QUALITY` are independent and
both explicit.

## 43. Opening location and gap (OBSERVED FACT)

All comparisons are exact tick-grid comparisons. Distances are signed `open −
reference`, in ticks and points.
- **Range:** `ABOVE_PRIOR_RANGE` (> high), `AT_PRIOR_HIGH` (= high),
  `INSIDE_PRIOR_RANGE`, `AT_PRIOR_LOW` (= low), `BELOW_PRIOR_RANGE`.
- **Value:** the same five, against VAH / VAL.
- **Gap:** `open − prior terminal` in points and ticks; direction UP / DOWN /
  NONE.
  - `BEYOND_PRIOR_RANGE` if the open is strictly outside the prior range,
    else `WITHIN_PRIOR_RANGE`.
  - Not "accepted" or "rejected".

## 44. Opening windows, revisits and crossings (OBSERVED FACT)

Windows are half-open `[08:30, 08:30 + N)` for N = 5, 15, 30 and 60 min,
measured from the open print. With 30-minute periods, 30 min is period A and
60 min is A+B (the IB).

Per window:
- high, low, range, last price;
- excursion up (`high − open`) and down (`open − low`);
- larger / smaller excursion, dominant UP / DOWN / TIE / NONE, and
  counter / dominant (undefined when both are 0);
- first direction away from the open, and the first trade above / below it;
- time of high and low (first reached) and their order (HIGH_FIRST /
  LOW_FIRST / NO_RANGE);
- traded above / below the open;
- first revisit of the open, first open cross and the number of crosses;
- "up first, then crossed below" and "down first, then crossed above".

Tick-grid definitions (module docstring):

| Term | Definition |
|---|---|
| **away** | a trade at any other tick |
| **touch** | a trade at exactly the reference tick |
| **cross** | a change of *strict* side relative to the reference; trades at the reference keep the previous side |
| **revisit** (of the open) | a touch after price first left the open tick |

**Path ordering.** The first above- and below-open trades and the
high/low-first order are raw ordered events. No "material" extreme is
defined.

**A-extreme follow-through** (for the period-A high and low, through the end
of the IB):
- when the extreme was first reached;
- the largest later move back from it;
- whether price later traded strictly on the other side of the open, when,
  and how long after;
- how far beyond the open it went.

Not labelled rejection.

## 45. Reference interactions (OBSERVED FACT)

References: prior high, low, VAH, VAL and POC (when context is AVAILABLE),
and the cash open (always). For each horizon (5/15/30/60 min) the facts are:
- the open's offset;
- the minimum distance in ticks;
- touched, with the first touch;
- crossed, with the first cross.

A touch is not declared a "test".

## 46. Prior value / range entry and exit (OBSERVED FACT)

Zones are inclusive `[VAL, VAH]` and `[prior low, prior high]`, over the whole
study window. An open exactly at a boundary counts as inside.
- **Open outside the zone:** first entry.
- **Open inside the zone:** first exit above, first exit below, first return
  after the first exit, and the time to return.
- **Occupancy during A** (both cases):
  - **trade-time:** the seconds for which the last traded price was inside
    the zone, from the open print to the end of A, with the observed seconds
    alongside;
  - **TPO:** A-range rows inside the zone, against A rows.

None of this is called acceptance, rejection or a failed auction.

## 47. Early TPO and one-timeframing (OBSERVED FACT)

**Early TPO**
- A high, low, range and rows; B high, low and rows.
- **A/B overlap** = rows printed by both A and B. **Overlap ratio** =
  overlap rows / rows of the smaller of A and B. It is in [0, 1]: 0 when A
  and B do not overlap, 1 when the smaller period lies inside the larger.
- A+B combined high, low and range.
- A-only rows of the A+B profile (above B, below B); whether B exceeded A's
  high or low.
- A-only rows at the close: in total, and contiguous from the day high / day
  low.
- High overlap is not called "auction"; low overlap is not called "drive".

**One-timeframing**
- The first period whose low is above the previous period's low, and the
  first period whose high is below the previous period's high.
- Runs from A: consecutive periods each with a higher low, and each with a
  lower high (A counts as 1).
- The longest such runs, by reference to the 0Y-C facts.

## 48. Opening quality policy (LABORATORY POLICY)

The opening window for quality is `[08:30, 09:30)` (the IB).

| Grade | When |
|---|---|
| `NOT_AVAILABLE` | the recorded capture interval does not cover the opening window, or there is no eligible trade within 60 s of 08:30:00 CT. No window, crossing or reference fact is computed. |
| `QUALITY_QUALIFIED` | any of: the capture interval was not recorded (opening coverage unverified); a KNOWN_GAP or SUSPECTED_GAP overlaps the opening window (counted separately); the lifecycle is not FINALIZED |
| `UNQUALIFIED` | otherwise |

- Overnight gaps do not affect the grade.
- Gaps later in the study window are counted (`gaps_later_in_study_window`)
  because they can affect the full-window entry/exit facts. They do not
  qualify the opening.
- A future classifier must not issue an unqualified opening type when
  `known_gaps_in_opening_window > 0`.
- The prior day's quality is separate (§42).

## 49. Data model and CLI

- **Data model:**
  - `TpoAnalysisResult.opening: CashOpenSession` holds the current-day facts
    and needs no prior day.
  - `opening_auction_facts(current, candidates, closures)` →
    `OpeningAuctionFacts`, which holds the session, `PriorContext`, location,
    gap, `ReferenceInteraction`s and the value/range `ZoneInteraction`s.
  - Everything is frozen and deterministic.
  - Once the tape is loaded, all opening facts for the 22-dataset corpus are
    computed in well under a second (evidence `timings.tsv`).
- **CLI:** `dicks_lab_tpo_profile.py DB --opening-facts [--prior-database
  PRIOR_DB] [--closure YYYY-MM-DD ...]`.
  - It adds `OPENING AUCTION FACTS` and an A/B-only early TPO matrix, with
    the open and the prior references (pH, pVAH, pPOC, pVAL, pL) marked.
  - Default, `--structure`, `--day-structure` and `--day-strength` output are
    unchanged.
- **Corpus study:** `scripts/dicks_lab_mp_opening_study.py OUT_DIR DBS...`
  writes per-day reports and `opening_study.md`.

**OpeningAuctionFacts != OpeningType.** No opening-type label exists in
code.

## 50. Deferred

- **Opening-type labels:** OPEN_DRIVE, OPEN_TEST_DRIVE,
  OPEN_REJECTION_REVERSE, OPEN_AUCTION, OPEN_AUCTION_IN_RANGE and
  OPEN_AUCTION_OUT_OF_RANGE. Feasibility is assessed in
  `MARKET_PROFILE_OPENING_0YF.md`.
- **Overnight inventory** (long/short/neutral), overnight high/low
  relationships and the overnight profile. *(0Y-G delivered the overnight
  facts as continuous measures, §51–§64; the labels and the overnight
  profile remain deferred.)*
  - LuxAlgo lists the overnight range as an opening reference. None of the
    surveyed *definitions* of the six types requires it.
  - It is the documented **next dependency** for a later classifier: it is
    needed for Dalton-style preparation and for distinguishing a test of the
    overnight extreme from a test of a prior-day reference.
- **Session VWAP as an opening reference** (LuxAlgo).
- **Holiday calendar:** closures are explicit input until one exists.
- **Acceptance, rejection, failed auction, confidence, bias and signals.**

## 51. Reference survey (overnight context) (0Y-G)

Sources are secondary and educational. Dalton's *Mind Over Markets* and
*Markets in Profile* are the lineage; neither was available here in full text.
- marketcalls.in, "Understanding Overnight Trading Inventory" and "Trading
  inventory imbalances and inventory adjustments"
- NexusFi, "Overnight inventory / Globex sessions" (search summary only; the
  page refused automated fetch, HTTP 403)
- LuxAlgo concept library, "Overnight & ETH Levels" and "RTH vs ETH"
- TradingView open-source script "Overnight inventory" (its description)
- Bookmap blog, "Why overnight price action matters"
- amtjoy (Substack), "Let's talk about overnight sessions"

| Concept | REFERENCE DESCRIPTION (sources) | OBSERVED FACT (0Y-G) | LABORATORY POLICY | INTERPRETATION (excluded) |
|---|---|---|---|---|
| Overnight high / low | Highest / lowest price of the extended session, fixed once RTH begins (LuxAlgo, Bookmap). | ONH / ONL over [17:00, 08:30) CT and the time each was first reached (§54). | The window in §52. | "liquidity pool", "stops above ONH" |
| Overnight range | Everything between the regular close and the next regular open (LuxAlgo). | ONH − ONL in ticks and points; HIGH_FIRST / LOW_FIRST. | The window starts at the Globex open (17:00 CT), not the 15:00 cash close: the 15:00–16:00 Globex hour belongs to the prior trading date. | — |
| Inventory long / short / neutral | Net positioning of the overnight session relative to a reference (marketcalls, NexusFi, TradingView, LuxAlgo). | Time, TPO-bracket rows and volume above / below / at each prior reference, reported separately (§55). | **No label.** No threshold. | "counter-auction ~75% of the time", "squeezed in the first 30 minutes", "structural bias" |
| Overnight range extension relative to prior day | Overnight that trades beyond the prior high or out of value (amtjoy statistics; LuxAlgo). | ONH/ONL vs prior high/low/VAH/VAL; overlaps; excursions beyond each (§54). | — | "accepted", "rejected", "initiative", "responsive" |
| Overnight reference tests at the cash open | "The open either rotates inside the overnight range or breaks an overnight extreme" (LuxAlgo). | Open vs ONH/ONL and its percentile; ONH/ONL touch/cross per horizon; reach → open cross facts (§57, §60). | A touch is a trade at the exact tick; no "near". | "test", "poke", "fade", "holds" |

**Which reference "inventory" is measured against.** The sources do not
agree, and the references are not interchangeable:

| Reference | Sources | Available to the Laboratory? |
|---|---|---|
| Prior **settlement** | marketcalls ("closing price of the regular market session, often referred to as the settlement price"); NexusFi ("relative to the prior day's settlement price") | **No.** The Laboratory records trades, not CME settlement. |
| Prior **close** | TradingView script ("volume traded above & below a close"; an earlier version used "a range above & below a previous close") | Partly: the prior *cash terminal* (last eligible trade before 15:00 CT) is measured. It is not the settlement and not the 16:00 Globex close. |
| **Overnight midpoint** | LuxAlgo (inventory corrected "back toward the overnight midpoint") | Derivable from ONH/ONL; not used as an inventory reference in 0Y-G. |
| Prior POC / prior value | No surveyed source uses them for inventory; Dalton-style preparation compares overnight to prior value. | Yes: prior POC, VAH and VAL are measured (§55). |
| None stated | Bookmap, amtjoy | — |

**Which quantity.** Also disputed:
- "positions held at a price higher than the settlement" (marketcalls, a
  price-location description with no metric);
- "the majority of overnight *volume*" above or below settlement (NexusFi,
  TradingView current version);
- the *range* above / below the close (TradingView earlier version).

**No numeric threshold appears in any source.** marketcalls says "no specific
formulas"; the TradingView script reports a signed number. 0Y-G therefore
measures time, TPO rows and volume separately against four named references
and adopts no label.

## 52. Overnight window (LABORATORY POLICY `OVERNIGHT_CONTEXT_V1`)

- **Start:** `resolve_anchor(SESSION_OPEN, trading_date)` = 17:00
  America/Chicago on the previous session evening (Sunday 17:00 for a Monday).
- **End:** `resolve_anchor(US_CASH_OPEN, trading_date)` = 08:30
  America/Chicago on the trading date (the 0Y-F cash open instant).
- **Membership:** [start, end). Canonical timestamps are UTC; presentation is
  America/Chicago. Neither bound is computed by subtracting hours.
- **Tape:** the trading date's scoped effective tape (the same
  `prepare_scoped_dataset` output used by the cash profile), filtered to the
  window; only on-grid trades are eligible.
- **DST:** a US DST change happens at 02:00 on a Sunday, while the Globex
  session is closed, so every window is exactly 15 h 30 min of elapsed time
  (tested for CDT, CST, and both Mondays after a change).
- **Globex open print:** the first eligible trade, claimed as the Globex open
  only when the capture began at or before 17:00 CT **and** the trade is
  within `GLOBEX_OPEN_MAX_DELAY` = 60 s of 17:00 CT. This is a data-coverage
  bound with the same value as the cash-open bound; it is not a market
  concept. Otherwise the first print is still reported, under its own name.
- *(0Y-H PO decision: **no tolerance** for the 17:00 boundary. The capture
  start must be recorded at or before 17:00:00 CT. An unrecorded start
  previously fell through to the 60 s check; it now never allows a claim
  (conformance fix with a test; no corpus day was affected, because every
  corpus start is recorded and late).)*

## 53. Overnight quality (LABORATORY POLICY)

`OvernightQuality.grade`:

| Grade | When |
|---|---|
| `NOT_AVAILABLE` | no eligible trade in the window. Nothing is computed; no price is invented. |
| `QUALITY_QUALIFIED` | facts computed, but one of: capture start or end not recorded (each stated separately, so a recorded late start is never hidden); **capture began after 17:00 CT** (by any amount: a trade before the start cannot be ruled out); capture ended before 08:30 CT; a KNOWN_GAP or SUSPECTED_GAP overlaps the window; lifecycle not FINALIZED. |
| `AVAILABLE` | none of the above. |

- Each reason is listed. Contract consistency is recorded (a dataset holds one
  instrument; scoping rejects a mixed dataset). Cross-day contract identity is
  the prior context's job (CONTRACT_CHANGED).
- **Independence:** an overnight gap qualifies the overnight facts and never
  the cash-opening facts (0Y-F §48 is unchanged), and an opening-window gap
  does not qualify the overnight facts.
- The cash-opening grade is named `UNQUALIFIED` and the overnight grade
  `AVAILABLE`. Both mean "no evidence of incompleteness".

## 54. Core overnight facts and the prior cash profile (OBSERVED FACT)

`OvernightSession` (prior-independent):
- first print and timestamp; Globex open price and delay, or the reason none
  is claimed;
- ONH and ONL (first reached), range in ticks and points, HIGH_FIRST /
  LOW_FIRST / NO_RANGE;
- terminal = the last eligible trade before 08:30 CT, with its timestamp;
- 30-minute brackets from 17:00 CT (every trade, not only price changes);
- volume at each tick.

`OvernightContext` (joined):
- **Cash open vs overnight:** ABOVE / AT ONH / INSIDE / AT ONL / BELOW;
  open − ONH and open − ONL in ticks; percentile = (open − ONL) / (ONH − ONL),
  undefined when the range is 0.
- **Overnight vs prior** (only when the prior context is AVAILABLE, i.e. the
  same contract): ONH − prior high, ONL − prior low, ONH − VAH, ONL − VAL
  (signed ticks and points); overlaps prior value / range; inside prior value
  / range; excursions above prior high, below prior low, above VAH and below
  VAL (each max(0, ·)).
- **Gaps, kept separate** (to − from; ticks, points, UP/DOWN/NONE):

| Gap | From | To |
|---|---|---|
| `GLOBEX_OPEN_VS_PRIOR_TERMINAL` | prior cash terminal | Globex open print (only when claimed, §52) |
| `FIRST_OVERNIGHT_PRINT_VS_PRIOR_TERMINAL` | prior cash terminal | first overnight print |
| `CASH_OPEN_VS_PRIOR_TERMINAL` | prior cash terminal | cash open (= the 0Y-F gap) |
| `CASH_OPEN_VS_OVERNIGHT_TERMINAL` | overnight terminal | cash open |

No word such as accepted, rejected, initiative or responsive is attached.

## 55. Inventory measures — continuous occupancy (OBSERVED FACT)

`OvernightOccupancy`, per reference: `PRIOR_TERMINAL`, `PRIOR_POC`,
`PRIOR_VAH`, `PRIOR_VAL` (prior context AVAILABLE only).

| Family | Facts | Definition |
|---|---|---|
| Time | seconds above / below / at; observed; fraction above / below | The last traded price holds until the next price change, from the first overnight print to 08:30:00 CT (the 0Y-F opening-zone occupancy rule). A gap is not filled: the last price simply carries, which is one reason a gap qualifies the facts. |
| TPO brackets | brackets traded; entirely above / entirely below / touching or spanning; TPO rows above / below / at | 30-minute brackets from 17:00 CT. A bracket's rows are every tick from its low to its high (TPO semantics). |
| Range | ONH − reference and reference − ONL (each ≥ 0); overnight terminal − reference | ticks |
| Volume | contracts at ticks strictly above / below / at | trade sizes, separately |

No family is weighted, combined or turned into LONG / SHORT / NEUTRAL.
`PRIOR_TERMINAL` is never called "settlement".

## 56. Overnight TPO profile — deferred

An `OVERNIGHT_PROFILE_V1` (overnight POC / VAH / VAL) was not built. The 0Y-A
`StudyWindow` and period builder assume a same-date window that the 60-minute
IB tiles. An overnight window crosses midnight, has 31 periods (beyond the
A–Z, a–z lettering rules' design) and has no IB. Supporting it would change
accepted 0Y-A code, which 0Y-G must not alter. The bracket facts in §55
already give a TPO-style description without a POC or value area.

## 57. Overnight extremes as opening references (OBSERVED FACT)

ONH and ONL are added as `ReferenceInteraction`s
(`OpeningPathFacts.overnight_reference_interactions`), computed by the same
function and horizons (5/15/30/60 min) as the 0Y-F prior references: open
offset, minimum distance, touched, first touch, crossed, first cross. The
accepted `OpeningAuctionFacts.reference_interactions` set is unchanged
(tested). A touch is a trade at the exact tick; it is not a "test".

## 58. Multi-scale opening facts and open-cross persistence (OBSERVED FACT)

`OpeningScaleFacts` at fixed observational horizons from 08:30:00 CT: 30 s,
1, 3, 5, 15, 30 and 60 min. The 60-minute row equals the accepted 0Y-F
60-minute window (tested).

| Fact | Definition |
|---|---|
| high, low, last; up / down excursion | ticks from the open print |
| dominant; counter/dominant | as 0Y-F; undefined when both excursions are 0 |
| open crosses; first / last cross | the 0Y-F strict side-change rule |
| open → last cross | last cross − open print |
| seconds above / below / at the open | last-traded-price time |
| longest UP / DOWN residence | A residence runs from the first trade strictly on a side to the next cross (or the horizon end). Trades at the open inside a residence do not interrupt it, consistent with the cross rule. |

These are scales of observation, not thresholds. **OpeningScaleFacts !=
Open Drive.**

## 59. Grace-instant diagnostics (DIAGNOSTIC ONLY)

For each instant open print + 1, 5, 15, 30 and 60 s:
- the last traded price at or before the instant, its offset, and its side
  (UP / DOWN / NONE = at the open);
- the **held side**: the side of the last trade strictly off the open (the
  side the cross rule keeps); NONE if no trade has left the open yet;
- for each opening window [08:30, 08:30 + 5 / 15 / 30 min): whether a later
  trade printed strictly on the other side of the open, when, and the maximum
  excursion beyond the open on the held side (favourable) and on the other
  side (counter), from the grace instant on. With no held side, the first
  side change is reported and favourable/counter are undefined.

No grace period is selected or preferred. **GraceDiagnostic is not a grace
policy.**

## 60. Reference encounters and the event sequence (OBSERVED FACT)

**`ReferenceEncounter`** (the "OpeningProbeFacts" object), for each prior
reference (high, VAH, POC, VAL, low; prior AVAILABLE) and each overnight
extreme (overnight available), over the first 30 minutes:
- side of the reference relative to the open (UP / DOWN; NONE when it is the
  open tick, which is then never a "first reach");
- **reach** = the first trade at or beyond the reference coming from the
  open's side. A jump over the tick reaches it without a touch, so the exact
  first touch is reported separately along with how far beyond the reaching
  trade printed;
- excursion toward the reference before the reach; maximum excursion beyond
  the open on the other side before the reach;
- whether the open was crossed afterwards (a trade strictly on the opposite
  side of the open from the reference), when, and the delay from the reach;
- the maximum excursion beyond the open on that opposite side within
  [cross, cross + 5 / 15 / 30 min);
- if never reached: the minimum distance only. No "near" exists (§18 of the
  0Y-G request).

`OpeningPathFacts.first_reference_reached` is the earliest reach. Ties are
broken by the fixed order prior high, VAH, POC, VAL, low, ONH, ONL.

**`OpeningReferenceSequence`** (first 30 minutes, programmatic): OPEN,
OPEN_CROSS_FIRST, OPEN_CROSS_LAST (if different), REFERENCE_TOUCH and
REFERENCE_CROSS (first occurrence per reference), and
WINDOW_HIGH_FIRST_REACHED / WINDOW_LOW_FIRST_REACHED. Repeated open crosses are
deduplicated to first and last, and the total count is kept. Events at the
same instant are ordered by event kind, then by reference order.

**ReferenceEncounter (OpeningProbeFacts) != Open Test Drive.** The chain
"reach a reference → cross the open → excursion on the other side" is
represented exactly; no label is attached.

## 61. Quality propagation

`OpeningPathFacts.quality: ContextQuality` keeps three trust statements apart:
- `CURRENT_OPEN`: the 0Y-F `OpeningQualityGrade` and reasons;
- `PRIOR_DAY`: the `ContextOutcome`, the prior's 0Y-C quality grade, and the
  reasons;
- `OVERNIGHT`: the `OvernightQualityGrade` and reasons (None when not built).

They are never merged. A later classifier must read each one.

## 62. Prospective-validation requirement

The research corpus has now been inspected in 0Y-D, 0Y-E, 0Y-F and 0Y-G. Any
future opening-type policy threshold — maximum counter excursion, minimum
directional excursion, grace time, minimum reference proximity, maximum open
crossings, minimum A/B overlap, any inventory split — must be
**pre-registered**, then tested **prospectively on unseen future dates**. A
threshold is not validated because it organises the current corpus well.

## 63. Data model and CLI

- `TpoAnalysisResult.overnight: OvernightSession` (prior-independent; built
  with the cash profile).
- `overnight_context(current, candidates, closures)` → `OvernightContext`.
- `opening_path_facts(current, candidates, closures)` → `OpeningPathFacts`.
  It wraps the unchanged `OpeningAuctionFacts` (equal to
  `opening_auction_facts(...)`; tested).
- Policies: `OVERNIGHT_CONTEXT_V1`, `OPENING_PATH_FACTS_V1`.
  `OPENING_AUCTION_FACTS_V1` is unchanged.
- **CLI:** `dicks_lab_tpo_profile.py DB [--opening-facts] [--overnight-facts]
  [--opening-path-detail] [--prior-database PRIOR_DB] [--closure ...]`. The new
  sections print after the opening facts and before the full matrix. Without
  the new flags, output is unchanged (tested).
- **Corpus study:** `scripts/dicks_lab_mp_overnight_study.py OUT_DIR DBS...`.

Explicitly: **OvernightContext != trading bias. OpeningProbeFacts != Open
Test Drive. OpeningScaleFacts != Open Drive.**

## 64. Deferred

- Opening-type labels (all six). Feasibility is in
  `MARKET_PROFILE_OVERNIGHT_0YG.md`. *(0Y-H: OPENING_TYPE_V1 candidates for
  Open Drive, Open Auction In/Out of Range and Open Test Drive, §65–§72; ORR
  remains deferred.)*
- Inventory labels (LONG / SHORT / NEUTRAL) and any inventory threshold.
- `OVERNIGHT_PROFILE_V1` (§56).
- Settlement price as a reference: it requires a new data source.
- Overnight midpoint as an inventory reference (LuxAlgo); derivable when
  wanted.
- Session VWAP as a reference; a holiday calendar.

## 65. OPENING_TYPE_V1 (LABORATORY POLICY, 0Y-H, FROZEN)

**OPENING_TYPE_V1 is a pre-registered Laboratory candidate policy, not an
industry-standard mechanical definition.**

- The normative text is `OPENING_TYPE_V1_POLICY.md`. Its sha256 and the sha256
  of `tpo_opening_type.py` are frozen in `tpo_opening_type_record.py`, and a
  test asserts both.
- Version string: `V1_A_PERIOD_60S_GRACE_EXACT_REFERENCE_TEST_PRIOR_RANGE_ANCHOR`.
- It reads `OpeningPathFacts` only. `OPENING_AUCTION_FACTS_V1`,
  `OVERNIGHT_CONTEXT_V1`, `OPENING_PATH_FACTS_V1`, `DAY_TYPE_V1` and
  `DAY_STRUCTURE_STRENGTH_V1` are unchanged.

## 66. Horizon and grace (PO decisions)

- **Horizon:** period A, [cash open print, end of A). A must be 30 minutes;
  otherwise the result is NOT_CLASSIFIED. Nothing is classified from the
  whole day.
- **Grace:** 60 s after the cash open print, so the +60 s grace-instant
  diagnostic of §59 is the same instant.
  - It is a Laboratory observation scale, chosen because the tick-level open
    is re-crossed within a second on every observed session.
  - It is not from the Market Profile literature and is not validated.

## 67. Candidate rules

| Type | Conditions |
|---|---|
| `OPEN_DRIVE` UP/DOWN | D1 grace price strictly off the open (side = direction); D2 no trade strictly on the other side after the grace instant through the end of A; D3 the A terminal is on the grace side |
| `OPEN_AUCTION_IN_RANGE` | R1 post-grace observation strictly above and strictly below the open; R2 at least one post-grace open cross; L open INSIDE / AT_PRIOR_HIGH / AT_PRIOR_LOW of the prior range |
| `OPEN_AUCTION_OUT_OF_RANGE` | R1, R2; L open strictly above the prior high or strictly below the prior low |
| `OPEN_AUCTION` | R1, R2 with no usable prior range (IN/OUT NOT_CLASSIFIED) |
| `OPEN_TEST_DRIVE` UP/DOWN | T1 the first qualifying reference reached in A (exact: at or through the price); T2 it lies on the probe side; T3 the open is crossed after the reach, in A; T4 a trade strictly on the opposite side after the cross, in A. Direction = post-cross side. |
| `OPEN_REJECTION_REVERSE` | DEFERRED — `REFERENCE_DEFINITION_CONFLICT` |

- No minimum excursion, range, volume, cross count, A/B overlap,
  counter/dominant ratio or proximity is required anywhere.
- Under V1, T2 is implied by T1 and T4 by T3 (`OPENING_TYPE_V1_POLICY.md` §5).
  Both are still stated in the output.

## 68. Candidate-set semantics

- Candidates are not mutually exclusive. There is no precedence and no
  `primary_opening_type`.
- Open Drive and the Open Auction family are mutually exclusive by
  construction: D2 forbids a post-grace cross, and R2 requires one.
- Open Test Drive can coexist with either.

## 69. Dependency-aware quality

- If the current open is QUALITY_QUALIFIED, every candidate is too.
- Otherwise each candidate reads only its inputs:
  - prior-range candidates read the prior day's quality;
  - an Open Test Drive reads the source of its probe reference.
- A qualified overnight (including the Globex boundary, §52) affects only a
  test drive probing ONH / ONL. The observed overnight range is a subset of
  the true range, so a non-reach is robust to it.
- Opening NOT_AVAILABLE gives `OPENING TYPE: NOT_CLASSIFIED`.

## 70. Data model and CLI

- `classify_opening_type(OpeningPathFacts) -> OpeningTypeClassification`
  (frozen dataclasses). It carries:
  - `policy_id`, `policy_version` and `policy_constants`;
  - `status`, `reasons` and `quality` (`ContextQuality`, never merged);
  - `candidates`: one `OpeningTypeCandidate` per type in fixed order. Each has
    `type`, `direction`, `result`, `quality`, `quality_reasons`,
    `conditions` (`OpeningTypeCondition`: code, description, status, detail),
    `evidence` (`GraceObservation` or `TestDriveEvidence`) and `policy_id`;
  - `strength` (`OpeningStrengthFacts`, continuous) and the `facts`.

  `matched` / `matched_types` give the set.
- `opening_type_classification(current, candidates, closures)` in
  `tpo_analysis`.
- **CLI:** `dicks_lab_tpo_profile.py DB --opening-types [--prior-database
  PRIOR_DB] [--closure ...]`. It prints `OPENING-TYPE CANDIDATES` after the
  opening-path section. Without the flag, output is unchanged (tested).

## 71. Prospective validation harness

- `scripts/dicks_lab_mp_opening_type_study.py record OUT_DIR DBS...` writes
  one JSON record per profiled date:
  - the opening-auction, overnight and opening-path facts (tape `path` arrays
    omitted; they are reproducible from the dataset id and database sha256);
  - the classification;
  - the policy-source sha256 and the fact-module sha256 values;
  - the cohort.
- It also writes per-day reports and an audit table.
- `summarize OUT_FILE RECORDS...` aggregates by cohort.
- Cohorts:
  - `DEVELOPMENT`: on or before the 2026-10-09 freeze;
  - `VALIDATION`: unseen later dates scored by the unmodified source;
  - `POLICY_MODIFIED`: the source hash differs, so the record is never
    validation.
- Nothing is scheduled; collection stays disarmed.

## 72. Deferred (after 0Y-H)

- `OPEN_REJECTION_REVERSE` (`REFERENCE_DEFINITION_CONFLICT`).
- A "toward the reference without touching" / proximity variant of Open Test
  Drive.
- Precedence or a primary opening type, and any strength threshold. These
  need prospective evidence first.
- Overnight inventory labels (LONG / SHORT / NEUTRAL): the survey disagrees
  on both the reference and the quantity.
- `OVERNIGHT_PROFILE_V1`, settlement as a reference, and a holiday calendar.

## 73. Unified Market Study State (0Z-A)

- `MARKET_STUDY_STATE_V1` assembles the accepted 0Y-A–0Y-H objects, the
  accepted VWAP studies and the Volume Profile headline into one immutable,
  canonical, hashed state per trading date. Reference: `MARKET_STUDY_STATE_V1.md`.
- No Market Profile concept is added or redefined. The one code change to this
  module family is an optional `context` argument on `analyze_tpo_dataset`, so
  the state builder loads a tape once; the default path is unchanged.
- The state is `FINAL_STUDY_STATE` only. As-of replay snapshots are not
  implemented; the replay-readiness inventory is in `MARKET_STUDY_STATE_V1.md`
  §12.
