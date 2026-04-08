# Backlog File

This is the backlog used in conjunction with the 'trade_hunter' application within the 'copper' project.

## Backlog-0010: Improve Monitoring of API Calls
**Status**: Closed — addressed by [Story-0170](stories/Story-0170.md)

Regarding your verbose flag question: yes, absolutely add it to the backlog. It would print something like [BULL] 12/87 — enriching AAPL... per ticker so you can see exactly where it is and monitor API traffic. The current silence makes it impossible to know if it's stuck or just slow.

## Backlog-0020: Monitor API throughput
**Status**: Closed — addressed by [Story-0170](stories/Story-0170.md)

The documentation for the 'Tradier' API describes some feedback that they provide regarding current usage and it relates to the rate limits. We need to see if we can utilize this data, and also be able to measure our API run rate so that we can possibly run at ~89% of capacity. This would also help us confirm that we are not being too conservative on our throttling.


## Backlog-0030: Ignore "GOOG"
**Status**: Closed — addressed by [Story-0180](stories/Story-0180.md)

'GOOG' and 'GOOGL' are identical for my purposes, use 'GOOGL'

## Backlog-0040: Use SeekingAlpha Sector data
**Status**: Closed — addressed by [Story-0210](stories/Story-0210.md)

We need to redo the manner in which we handle the 'ticker-to-sector' mapping. The 'sector' listing in the TastyTrade data is inconsistent and in some cases incorrect. So I am thinking we need to use another source for our sector data (i.e., yahoo finance) and since sector data doesn't change that often perhaps we could implement a cache on local disk (e.g., local file or sqlite DB).

At this time it is believed that the SeekingAlpha sector data is reliable and consistent, but perhaps it makes sense to use a single source for the sector data.  

Reminder: We have to get the sector data from a 2nd source because for the existing trades that are in the 'journal.xlsx' file, we currently get the sector data for the active trades from the TastyTrade data which we are now deprecating.

Requirement: I would like to keep the conformity to the "standard" 11 sectors in place, so there may need to be some data standardization / normalization between the SeekingAlpha data and the new source (e.g., yahoo fiance) 
Make sector data from SeekingAlpha the primary source and only use the TT sector data if it is missing in the SeekingAlpha data. I also think that the existing

## Backlog-0050: Add Weighting Columns to output spreadsheet
**Status**: Closed — addressed by [Story-0200](stories/Story-0200.md)

Append each of weighting ratings (i.e., the 0.0 to 5.0 ratings) to a column in the output spreadsheet (unless it is already included in the spreadsheet).

**List of All Weighting Metrics**:
| Metric |
| -------- |
| IVR |
| IVP |
| Open Interest |
| Spread% |
| BPR |
| Cyclical Diversity |
| Quant Rating |
| Sector Diversity |
| Earnings Date |
| Growth |
| Momentum |
| Bid |
| Liquidity |


## Backlog-0060: Improve Monthly Cycle Calculation
**Status**: Closed — addressed by [Story-0180](stories/Story-0180.md)

I believe the code "calculates" the upcoming possible monthly cycle dates by using the 3rd Friday of the month. There are times when this is inaccurate when holidays land on the 3rd Friday: Good Friday and Juneteenth are some possibilities. If an option expiration on the 3d Friday of the month can not be found then perhaps a check on the 3rd Thursday should be done ? 


## Backlog-0070: Additional Logging
**Status**: Closed — addressed by [Story-0190](stories/Story-0190.md)

### More logging around rejected tickers
When the user has specified the '--verbose' option some additional logging needs to be added. There should be a log entry every time a a ticker that is in either the BULL or BEAR input file gets rejected and is not part of the output file. Some of the rejection reasons I can think of are 1) no match found in the TastyTrade data 2) the ticker did not pass the hard requirements and there are probably be more reasons as well. Every time that a ticker gets disqualified from the final results there should be a verbose log entry that describes at what stage the ticker got removed and the reason.

# Backlog-0080: Earnings Date Incorrect
**Status**: Closed — fixed in `pipeline/scoring.py` `_resolve_earnings_date`

Noticed in today's run of @scripts/trade_hunter.sh that in the output file '/home/temckee8/Documents/data/copper/trade_hunter/uploads/scripts/trade_hunter.sh' the 'Earnings Date' column had '06/17/2026' for every ticker which is incorrect. And I noticed the 'Earnings Date' metric was always scored as a '5.0' due to this.







