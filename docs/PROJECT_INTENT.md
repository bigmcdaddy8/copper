# Project Intent for Copper v2

This document grounds the AI Developer on the business intent, operating assumptions, and initial design direction for Copper. It is intended to support project planning and technical design, not to lock implementation details permanently. Where specific defaults are defined below, they should be treated as the current working rules for initial implementation.

Copper will eventually host multiple programs and utilities that support the trading activity and decision-making of the human trader, Mr. Dick Weasel.

## Goal #1: `trade_hunter`

`trade_hunter` produces potential trade signals from manually downloaded input files plus market data retrieved from the Tradier API. The first implementation focuses on generating ranked BULL-ish and BEAR-ish option-selling candidates.

The output is a workbook containing candidate trades sorted by descending Trade Score.

## Data Root

The business data for this project lives outside the repository.

- Ubuntu data root: `/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading`
- Expected subdirectories under the data root:
  - `downloads/`
  - `worksheets/`
  - `uploads/`

Initial implementation should support explicit input paths via CLI options. If file discovery is added, it should use configurable glob patterns rather than hard-coded filenames.

## Run Behavior Defaults

Unless later changed, `trade_hunter` should follow these operational defaults:

- Required input files missing: fail the run with a clear error.
- Per-ticker data issues: log a warning and continue processing other tickers.
- Output workbook: overwrite the prior `trade_signals.xlsx` on each successful run.
- Run logging: create a per-run log that captures warnings, skips, and API issues.

## Data Sources

Input data comes from two file-based sources and one API-based source.

### 1. SeekingAlpha Screen Data

The trader manually runs screens in SeekingAlpha and downloads Excel files into `downloads/`.

- One file contains BULL-ish candidates.
- One file contains BEAR-ish candidates.

These files are expected to contain at least the following columns:

| Column Name | Use |
| -------- | -------- |
| Rank | Ignore |
| Symbol | Required |
| Company Name | Optional informational field |
| Price | Ignore |
| Change % | Ignore |
| Quant Rating | Required |
| Exchange | Optional |
| Growth | Required for scoring when applicable |
| Momentum | Required for scoring |
| Prev Close | Ignore |
| Upcoming Announce Date | Fallback earnings date |
| SA Analyst Ratings | Ignore for v1 |
| Wall Street Ratings | Ignore for v1 |
| Sector & Industry | Optional for future use |

Notes:

- `Quant Rating` source scale is `1.0` to `5.0`.
- `Growth` and `Momentum` source scale is `A+` to `F`.
- The file names are not yet fixed by business rule, so the program should accept them explicitly or discover them via configurable patterns.

### 2. TastyTrade Data

The trader manually downloads a CSV file from TastyTrade into `downloads/`. This file is the source of the universal tradable ticker universe and several scoring inputs.

This data is assumed to represent Russell 1000 tickers with tradable options. If that assumption later proves incomplete, the TastyTrade file remains the source of truth for the tradable universe used by `trade_hunter`.

Expected columns:

| Column Name | Use |
| -------- | -------- |
| Symbol | Required |
| Last | Present but not used for scoring |
| Volume | Optional for future use |
| Beta | Optional for future use |
| Corr SPY | Optional for future use |
| Liquidity | Output only in v1 |
| IV Idx | Required |
| IV Rank | Required |
| IV %tile | Required |
| Name | Optional informational field |
| Earnings At | Primary earnings date |
| Sector | Required |

### 3. Dick Weasel Trade Data

Active trades are stored in `worksheets/journal.xlsx`, worksheet `daJournal`.

For `trade_hunter`, only the `Symbol` column is required. The worksheet is assumed to already represent active trades, so rows in `daJournal` should be treated as active without additional filtering unless business rules change later.

If multiple rows exist for the same ticker, that ticker is still treated as one active underlying when building open-trade exclusion sets and diversity calculations.

Expected columns:

| Column Name | Use |
| -------- | -------- |
| Symbol | Required |
| M8 Trade # | Ignore |
| Entry Capital Required | Ignore |
| Budget Allocation | Ignore |
| Date Entered | Ignore |
| Date Closed | Ignore |
| Days In Trade | Ignore |
| Calculated Final PnL | Ignore |
| Trade Category | Ignore |

### 4. Tradier API Data

Tradier provides market and options-chain data needed for filtering and scoring.

Reference: `https://docs.tradier.com/docs/getting-started`

The implementation must respect Tradier rate limits and throttle or queue requests as needed. Rate-limit headers returned by Tradier should be used when practical.

## Data Normalization Rules

### Universal Data Set

The Universal Data Set is the TastyTrade file after sector normalization and basic validation.

Any SeekingAlpha candidate not present in the Universal Data Set is out of scope for this run, should be logged as a warning, and should be skipped.

Any open-trade ticker not present in the Universal Data Set should also be logged as a warning but should not stop processing.

### Sector Standardization

TastyTrade sector values must be normalized before any downstream processing.

| TastyTrade Sector Name | Standard Sector Name |
| -------- | -------- |
| Basic Materials | Materials |
| Capital Goods | Industrials |
| Consumer Cyclical | Consumer Discretionary |
| Consumer/Non-Cyclical | Consumer Staples |
| Energy | Energy |
| Financial | Financials |
| Healthcare | Health Care |
| Services | Communication Services |
| Technology | Information Technology |
| Transportation | Consumer Discretionary |
| Utilities | Utilities |
| Real Estate | Real Estate |
| REIT | Real Estate |

If a sector value is unrecognized, log a warning and skip the ticker unless a future mapping rule is added.

### Sector Bucket Mapping

After standardization, each sector must also be assigned to a cyclical bucket.

| Standard Sector Name | Sector Bucket |
| -------- | -------- |
| Materials | Economic |
| Industrials | Economic |
| Consumer Discretionary | Growth |
| Consumer Staples | Defensive |
| Energy | Economic |
| Financials | Economic |
| Health Care | Defensive |
| Communication Services | Growth |
| Information Technology | Growth |
| Utilities | Defensive |
| Real Estate | Economic |

## Processing Pipeline

`trade_hunter` should process data in this order:

1. Load and validate required input files.
2. Load TastyTrade data and build the Universal Data Set.
3. Normalize sectors and assign sector buckets.
4. Load active trade symbols from `journal.xlsx` worksheet `daJournal`.
5. Deduplicate active trade symbols for exclusion and diversity calculations.
6. Load SeekingAlpha BULL-ish candidates.
7. Load SeekingAlpha BEAR-ish candidates.
8. Remove any candidate already present in the open-trade symbol set.
9. Remove any candidate not present in the Universal Data Set.
10. Join remaining candidates to the Universal Data Set.
11. Retrieve required Tradier data for remaining joined candidates.
12. Apply hard filters.
13. Compute scoring inputs.
14. Calculate Trade Score.
15. Sort descending by Trade Score.
16. Write output workbook and per-run log.

## Tradier Data Requirements

For each remaining ticker, gather the following fields from Tradier:

| Column Name | Notes |
| -------- | -------- |
| Ticker | Underlying ticker |
| Expiration Date | Selected monthly expiration with DTE between 30 and 60 calendar days inclusive |
| Last Price | Current underlying last trade price |
| Put Strike | Selected put strike |
| Call Strike | Selected call strike |
| Put Delta | Delta of selected put |
| Call Delta | Delta of selected call |
| Put Open Interest | Open interest of selected put |
| Call Open Interest | Open interest of selected call |
| Put Bid | Bid of selected put |
| Call Bid | Bid of selected call |
| Put Ask | Ask of selected put |
| Call Ask | Ask of selected call |

### Expiration Selection Rule

When multiple monthly expirations qualify, select the nearest monthly expiration whose DTE is between 30 and 60 calendar days inclusive.

### Option Selection Rule

For the selected expiration:

- BULL-ish candidate: use the put whose delta is less than or equal to `-0.21` and is closest to `-0.21`.
- BEAR-ish candidate: use the call whose delta is greater than or equal to `0.21` and is closest to `0.21`.

If no qualifying option exists for the required side, log a warning and skip the ticker.

### Monthly Cycle Rule

The program should use the standard monthly expiration cycle. If Tradier exposes sufficient metadata to identify monthly contracts directly, use that metadata. Otherwise, infer the monthly cycle using the standard monthly expiration convention.

## Hard Filters

Apply these filters to both BULL-ish and BEAR-ish candidates after Tradier enrichment.

For BULL-ish candidates, use the selected put fields.

For BEAR-ish candidates, use the selected call fields.

### Spread% Formula
'Spread%' is calculated as the option price spread as % of Option Mid Price.
- Measures spread relative to what you actually trade
- Scale-invariant across strikes and expirations
- Direct proxy for execution friction

**Formula**:
`Spread% = (option ask - option bid) / ((option ask + option bid)/2)`

Default thresholds for initial implementation:

| Filter | Rule |
| -------- | -------- |
| Monthly Cycle | A valid monthly cycle expiration was found |
| Open Interest | `>= 8` |
| Bid | `>= 0.55` |
| Spread% | `(option ask - option bid) / ((option ask + option bid)/2) <= 13%` |

These thresholds must be configurable through CLI options, config file support, or another convenient configuration mechanism.

Be sure to log the criteria failure as they occur.

## Scoring Methodology
Each surviving candidate receives a Trade Score in the range `0.00` to `5.00`.

### Final Score Formula
Use a weighted average:

`Trade Score = sum(weight * quality) / sum(active weights)`

This keeps the final score normalized to the `0.00` to `5.00` range.

### Active Weight Rule

All listed weights participate unless a metric is explicitly not applicable.

The only planned not-applicable rule in the initial version is:

- `Growth` is only included when the candidate belongs to the `Growth` sector bucket.

If `Growth` is not applicable, remove both its weight and its metric contribution from the weighted average denominator and numerator.

### Metric Weights

| Metric | Weight |
| -------- | -------- |
| IVR | 3.0 |
| IVP | 3.0 |
| Open Interest | 3.0 |
| Spread% | 3.0 |
| BPR | 3.0 |
| Cyclical Diversity | 3.0 |
| Quant Rating | 2.0 |
| Sector Diversity | 1.0 |
| Earnings Date | 1.0 |
| Growth | 1.0 |
| Momentum | 1.0 |
| Bid | 1.0 |
| Liquidity | 1.0 |

## Quality Tables and Metric Rules
### IVR Quality
Source: TastyTrade `IV Rank`

| IVR | Quality |
| -------- | -------- |
| `<= 10.0` | `0.0` |
| `> 10.0` and `<= 20.0` | `1.0` |
| `> 20.0` and `<= 30.0` | `2.0` |
| `> 30.0` and `<= 50.0` | `4.0` |
| `> 50.0` | `5.0` |

### IVP Quality
Source: TastyTrade `IV %tile`

| IVP | Quality |
| -------- | -------- |
| `<= 10.0` | `0.0` |
| `> 10.0` and `<= 20.0` | `1.0` |
| `> 20.0` and `<= 30.0` | `2.0` |
| `> 30.0` and `<= 50.0` | `4.0` |
| `> 50.0` | `5.0` |

### Open Interest Quality
Source: selected Tradier option

| Open Interest | Quality |
| -------- | -------- |
| `<= 10` | `0.0` |
| `> 10` and `<= 100` | `2.0` |
| `> 100` and `<= 1000` | `4.5` |
| `> 1000` | `5.0` |

### Spread% Quality
'Spread%' is calculated as the option price spread as % of Option Mid Price.
- Measures spread relative to what you actually trade
- Scale-invariant across strikes and expirations
- Direct proxy for execution friction

**Formula**:
`Spread% = (option ask - option bid) / ((option ask + option bid)/2)`

| Spread% | Quality   |
| ---------- | ------- |
| ≤ 2%       | **5.0** |
| 2–4%       | **4.5** |
| 4–6%       | **4.0** |
| 6–8%       | **3.0** |
| 8–12%      | **2.0** |
| 12–20%     | **1.0** |
| > 20%      | **0.0** |


### BPR Quality
For initial implementation, `premium` should use the same side-specific option bid that would be used for trade entry, which keeps the estimate conservative and internally consistent.

For naked puts:

`BPR = max(0.20 * underlying_price - OTM_amount + premium, 0.10 * underlying_price + premium, 2.50 + premium) * 100`

Where:

- `OTM_amount = underlying_price - put_strike`

For naked calls:

`BPR = max(0.20 * underlying_price - OTM_amount + premium, 0.10 * underlying_price + premium, 2.50 + premium) * 100`

Where:

- `OTM_amount = call_strike - underlying_price`

| BPR | Quality |
| -------- | -------- |
| `<= 500` | `3.0` |
| `> 500` and `<= 1500` | `5.0` |
| `> 1500` and `<= 3000` | `3.5` |
| `> 3000` and `<= 4500` | `1.5` |
| `> 4500` | `0.0` |

### Cyclical Diversity Quality
This metric evaluates how concentrated the current active trades are within the candidate's sector bucket.

Rules:

- Count each active ticker once.
- Determine each active ticker's standardized sector and sector bucket.
- Compute bucket allocation percentage using the deduplicated active ticker set.

| Sector Bucket Allocation % | Quality |
| -------- | -------- |
| `<= 21%` | `5.0` |
| `> 21%` and `<= 55%` | `2.0` |
| `> 55%` | `0.0` |

### Quant Rating Quality
Source: SeekingAlpha `Quant Rating`

- BULL-ish quality: use the value directly.
- BEAR-ish quality: use `6.0 - quant_rating`.

This preserves a `1.0` to `5.0` scale while flipping directionality.

### Sector Diversity Quality
This metric evaluates how concentrated the current active trades are within the candidate's exact standardized sector.

Rules:

- Count each active ticker once.
- Compute sector allocation percentage using the deduplicated active ticker set.

| Sector Allocation % | Quality |
| -------- | -------- |
| `<= 3%` | `5.0` |
| `> 3%` and `<= 13%` | `2.0` |
| `> 13%` | `0.0` |

### Earnings Date Quality

Earnings date source precedence:

1. TastyTrade `Earnings At`
2. SeekingAlpha `Upcoming Announce Date`
3. If both are blank, assume the earnings date is 70 calendar days after the run date

Formula:

`EaE = earnings_date - expiration_date`

Where `EaE` is measured in calendar days.

| EaE | Quality |
| -------- | -------- |
| `<= -14` | `3.0` |
| `> -14` and `<= 1` | `0.0` |
| `> 1` | `5.0` |

### Growth Quality

Source: SeekingAlpha `Growth`

This metric is only active when the candidate belongs to the `Growth` sector bucket.

Bullish mapping:

| Growth | Quality |
| -------- | -------- |
| `A+` | `5.0` |
| `A` | `4.5` |
| `A-` | `4.0` |
| `B+` | `3.0` |
| `B` | `2.5` |
| `B-` | `2.0` |
| `C+` | `1.25` |
| `C` | `1.0` |
| `C-` | `0.75` |
| `D+` | `0.5` |
| `D` | `0.25` |
| `D-` | `0.1` |
| `F` | `0.0` |

For BEAR-ish candidates, transform quality as `5.0 - bullish_quality`.

### Momentum Quality

Source: SeekingAlpha `Momentum`

Bullish mapping:

| Momentum | Quality |
| -------- | -------- |
| `A+` | `5.0` |
| `A` | `4.5` |
| `A-` | `4.0` |
| `B+` | `3.0` |
| `B` | `2.5` |
| `B-` | `2.0` |
| `C+` | `1.25` |
| `C` | `1.0` |
| `C-` | `0.75` |
| `D+` | `0.5` |
| `D` | `0.25` |
| `D-` | `0.1` |
| `F` | `0.0` |

For BEAR-ish candidates, transform quality as `5.0 - bullish_quality`.

### Bid Quality
Source:

- BULL-ish: selected put bid
- BEAR-ish: selected call bid

| Bid | Quality |
| -------- | -------- |
| `<= 0.55` | `0.0` |
| `> 0.55` and `<= 0.89` | `1.0` |
| `> 0.89` and `<= 1.44` | `2.5` |
| `> 1.44` and `<= 2.33` | `3.5` |
| `> 2.33` and `<= 3.77` | `4.5` |
| `> 3.77` and `<= 6.10` | `2.5` |
| `> 6.10` | `0.0` |

### Liquidity Quality
The liquidity column in the tastytrade data contains binary that represent encoded start symbols that are used to indicate the level of liquidity - from 0 stars (very illiquid) to 4 stars (very liquid).

| Stars | Binary Value |
| ☆☆☆☆ | 0xe29886e29886e29886e29886 |
| ★☆☆☆ | 0xe29885e29886e29886e29886 |
| ★★☆☆ | 0xe29885e29885e29886e29886 |
| ★★★☆ | 0xe29885e29885e29885e29886 |
| ★★★★ | 0xe29885e29885e29885e29885 |

**Liquidity Quality***:
| Binary Value | Quality |
| -------- | -------- |
| 0xe29886e29886e29886e29886 | 0.0 |
| 0xe29885e29886e29886e29886 | 0.5 |
| 0xe29885e29885e29886e29886 | 2.0 | 
| 0xe29885e29885e29885e29886 | 4.5 |
| 0xe29885e29885e29885e29885 | 5.0 |




## Output Workbook

Write the output workbook to `uploads/trade_signals.xlsx`.

Create two worksheets:

- `BULL-ish`
- `BEAR-ish`

Each worksheet should be sorted in descending order by `Trade Score`.

### Output Columns

| Column Name | Format |
| -------- | -------- |
| Ticker | Text |
| Sector Bucket | Text |
| Sector | Text |
| Option Type | Text: `Put` or `Call` |
| Expiration Date | Date `MM/DD/YYYY` |
| Earnings Date | Date `MM/DD/YYYY` |
| DTE | Integer |
| Price | Number `#.##` |
| Strike | Number `#` |
| Bid | Number `#` |
| Ask | Number `#` |
| Spread% | Percent `#.#%` |
| Delta | Number `[-]0.##` |
| Open Interest | Number `#` |
| Trade Score | Number `#.##` |
| Quant Rating | Number `#.##` |
| Liquidity | Text `# Stars` |
| Growth | Text |
| Momentum | Text |
| IVx | Percent `#.##%` |
| IVR | Number `#.##` |
| IVP | Percent `#.##%` |
| BPR | Currency `$#` |

## Logging Expectations

The run log should include at minimum:

- Missing required files
- Input schema problems
- Unknown sector values
- Candidate tickers missing from the Universal Data Set
- Open-trade tickers missing from the Universal Data Set
- Tradier API failures or throttling events
- Tickers skipped because no valid monthly cycle or no qualifying option was found
- Summary counts for loaded, filtered, skipped, scored, and written records

## Concerns Addressed in v2

This revision resolves several issues from the original draft:

- Defines the Trade Score formula explicitly.
- Corrects BEAR-ish Quant Rating inversion to `6.0 - rating`.
- Fixes the sector bucket mapping orientation and content.
- Defines deterministic expiration and strike-selection rules.
- Clarifies failure-vs-warning behavior.
- Clarifies active trade deduplication for exclusion and diversity metrics.
- Clarifies that Growth is excluded from scoring when not applicable.

## Items Intentionally Left for Future Design

These are not blockers for initial planning, but may warrant future refinement:

- Exact CLI parameter names and config-file format
- Exact run-log file location and naming convention
- Caching strategy for Tradier responses
- Whether additional SeekingAlpha ratings should later contribute to scoring
- Whether DTE and earnings calculations should ever use trading days instead of calendar days