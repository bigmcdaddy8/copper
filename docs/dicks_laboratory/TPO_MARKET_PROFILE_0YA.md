# TPO / Market Profile Foundation (0Y-A)

Status: 0Y-A. Deterministic TPO facts only. No interpretation (opening type, day
type, single prints, excess, poor highs/lows, signals) — those are deferred
until PO review (§12).

Code: `apps/dicks_laboratory/src/dicks_laboratory/tpo_profile.py` (pure profile
math), `tpo_analysis.py` (dataset orchestration, quality, rendering),
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
