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
