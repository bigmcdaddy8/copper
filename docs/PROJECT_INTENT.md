
# Project Intent for Copper

The project will eventually be the home of a wide variety of programs / utilities that are used to support the trading activity and decision making of the human trader (a.k.a., 'Mr. Dick Weasel').

## Data Directory Location

External to this project there is an external directory that contains various directory structures that hold the input and output data files that will serve as input to this project. 
**Ubuntu Directory Path**: ```/home/temckee8/OneDriveMount/DropboxClone/ToddStuff/trading```

## Input Data:

Input to the processing will come in 2 forms: input data files and an API to the 'Tradier' brokerage.

#### SeekingAlpha Screen Data:

Dick Weasel will manually run screens that are set up in his SeekingAlpha.com account and download .xlsx files and place them in the 'Directory Path'/'downloads' directory. There will be one file for the potential 'BULL-ish' trade candidates and another for the potential 'BEAR-ish' trade candidates.

**File Format**:
| Column Name | Notes |
| -------- | -------- |
| Rank | Not Used |
| Symbol | Ticker Symbol |
| Company Name| Name of Company |
| Price | Not Used |
| Change % | Not Used |
| Quant Rating | Range: 1.0 (Strong Sell) to 5.0 (Strong Buy) |
| Exchange | 'NYSE' or 'NASDAQ' |
| Growth | Range: 'A+' to 'F' |
| Momentum | Range: 'A+' to 'F' |
| Prev Close | Not Used |
| Upcoming Announce Date | M/D/YYYY |
| SA Analyst Ratings | Range: 1.0 (Strong Sell) to 5.0 (Strong Buy) |
| Wall Street Ratings | Range: 1.0 (Strong Sell) to 5.0 (Strong Buy) |
| Sector & Industry | Industry |


#### TastyTrade Data:

Dick Weasel will manually download a .csv file from his TastyTrade account that contains data like volatility, option liquidity and upcoming earnings date for tickers in the 'Russell 1000' that have tradable options.

**File Format**:
| Column Name | Notes |
| -------- | -------- |
| Symbol | Ticker Symbol |
| Last | Not Used |
| Volume | Stock Volume |
| Beta | Volatility compared to S&P 500, ranges from 0 to over 1.0 (though it can be negative). A Beta > 1 is more volatile than the market, while < 1 is less volatile |
| Corr SPY | Measures directional tendency compared to S&P 500, Range: -1.0 to 1.0 +1.0 (Perfect Positive Correlation): The stock moves in exact lockstep with the S&P 500. If SPY goes up 1%, the stock goes up 1%. Positive (0.1 to 0.9): The stock generally moves in the same direction as the market. Large-cap stocks often have high positive correlations. 0.0 (No Correlation): The stock's price movement is independent of the S&P 500. Negative (-0.1 to -1.0): The stock tends to move in the opposite direction of the market (e.g., inverse ETFs or certain defensive sectors during panic) |
| Liquidity | A binary value that represents a number of stars 1-4, where 1 is illiquid and 4 is very liquid |
| IV Idx | 30 day IVx |
| IV Rank | IV Rank, range 0 to 100 |
| IV %tile | IVP, range 0.0 to 100.0 |
| Name | Company Name |
| Earnings At | M/D/YYYY |
| Sector | Sector |

##### Sector Standardization
Some of the sector names will need to be translated to a standard name, the names that need to be translated are:

| TastyTrade Sector Name | Standard Name |
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

#### Dick Weasel Trade Data:

Dick Weasel keeps his trade data in spreadsheets located in the 'Directory Path'/'worksheets' directory. In workbook 'journal.xlsx' the worksheet 'daJournal' will have the list of active trades. Since multiple trades can be active on the same ticker symbol expect there to be multiple entries for some tickers. Only the first column 'Symbol' is of interest for this program.

**File Format**:
| Column Name | Notes |
| -------- | -------- |
| Symbol | Ticker Symbol |
| M8 Trade # | Not Used |
|	Entry Capital Required | Not Used |
| Budget Allocation | Not Used |	
| Date Entered | Not Used |
| Date Closed	| Not Used |
| Days In Trade | Not Used |
| Calculated Final PnL | Not Used |
| Trade Category | Not Used |

### Trader API

The programs will also get current market data via the API made available through the 'Tradier' brokerage. '''https://docs.tradier.com/docs/getting-started'''. Note that there are rate limits of the 'Tradier' APIs

#### Tradier Rate Limits

The code that calls the 'Tradier' API will need to be aware of the rate limits and be able to throttle / queue requests as needed.

##### Tradier Rate Limit Documentation

###### How Rate Limits Work
Two pieces of information to understand as it pertains to our limits:

- Interval: we aggregate limits over 1-minute intervals starting with the first request and reset 1 minute late
- Limit: this can vary as outlined below, but we keep ours to 60 - 120 requests

For example: With a rate limit of 120 requests per minute, if you make a /quotes request every second for a minute, you would still have 60 requests left in that minute before hitting the limit.

**###### **Should you be concerned about rate-limits?**

Probably not. Polling for data, while not the best solution, is reasonably supported by our APIs. The limits exist with enough headroom to get up-to-date data and still have room to make other requests. The best way to know if your application will hit the limits is to build it and scale back.


###### Limits
Each limit is enforced by the minute and on a per-access-token basis. As such, the limits are enforced on per app and per user basis.

- Standard
  - This includes resources in /accounts, /watchlists, /users and /orders.
  - This does NOT include placing orders.
  - Production: 120 requests per minute.
  - Sandbox: 60 request per minute.
- Market Data
  - This includes resources in /markets.
  - Production: 120 requests per minute.
  - Sandbox: 60 request per minute.
- Trading
  - This includes all resources in the “trade” scope.
  - Production: 60 request per minute.
  - Sandbox: 60 request per minute.

###### Headers
With each request that has a rate limit applied a series of headers will be sent in the response. These headers should help you to gauge your usage and when to throttle your application. For example:
```
X-Ratelimit-Allowed: 120
X-Ratelimit-Used: 1
X-Ratelimit-Available: 119
X-Ratelimit-Expiry: 1369168800001
```

## Goal #1: trade_hunter

This program is used to produce potential trade signals. It will apply a set of rules and a weighting system to the input data and output trade signals. These trade signals will be for tickers that are in the Russell 1000, data that cause join issues because they are not a Russell 1000 ticker can be either ignored or logged as a warning. 

### The Algorithm

Universal Data Set = TastyTrade dataset which is filtered to Russell 1000 tickers.

It is anticipated that not all ticker symbols in the BULL-ish / BEAR-ish data sets will have an entry in the Universal Data Set. These types of issues should be collected in a per run error log but not stop processing because are to be expected. Not all of the tickers in the Open Trades data set will be in the Universal Data set either, because there are open trades in ETFs and non-Russell 1000 stocks. 

#### Filter the BULL-ish and BEAR-ish Data

Filter out any BULL-ish or BEAR-ish tickers that are not in the Universal Dataset. 
Get a data set of all of the possible tradable tickers and associated static data. This comes from the joining of the 'TastyTrade Data'. Any BULL-ish / BEAR-ish ticker not in this Universal data set will be logged as a 'Warning' and then will be skipped over.

### Prepare Open Trades Data Set

Get a list of tickers that are currently involved in an active trade. This comes from the 'Dick Weasel Trade Data'.

### Prepare BULL-ish Data Set

Join the 'SeekingAlpha Screen BULL-ish Data' candidates that are not in the 'Open Trades Data Set' with the 'Universal Data Set`. Be sure to log any errors in the run log.

### Prepare BEAR-ish Data Set

Join the 'SeekingAlpha Screen BEAR-ish Data' candidates that are not in the 'Open Trades Data Set' with the 'Universal Data Set`. Be sure to log any errors in the run log.

### Prepare 'Tradier' Data

For both the BULL-ish and BEAR-ish data additional data needs to be gathered that is needed by the weighting algorithm. This data is acquired from the 'Tradier' brokerage using its' API. 

The additional data that needs to be gathered and correlated with the BULL-ish and BEAR-ish data is defined in the following table:

| Column Name | Notes |
| -------- | -------- |
| ticker | Ticker Symbol |
| Expiration Date | M/D/YYYY of the next monthly cycle has a DTE >= 30d and <= 60d in the option chain |
| Last Price | Last trade price of the underlying stock |
| Put Strike | The strike of the first Put option with the 'Expiration Date' that is <= -.21 delta |
| Call Strike | The strike of the first Call option with the 'Expiration Date' that is >= .21 delta |
| Put Open Interest | The open interest in the first Put option with the 'Expiration Date' that is <= -.21 delta |
| Call Open Interest | The open interest in the first Call option with the 'Expiration Date' that is >= .21 delta |
| Put Bid | The bid for the Put option with the 'Expiration Date' that is <= -.21 delta  |
| Call Bid | The bid for the Call option with the 'Expiration Date' that is >= .21 delta  |
| Put Ask | The ask for the Put option with the 'Expiration Date' that is <= -.21 delta  |
| Call Ask | The ask for the Call option with the 'Expiration Date' that is >= .21 delta  |

### Apply Filters
Apply the following filters to both the BULL-ish and BEAR-ish data sets to remove tickers that do not meet the required criteria. Note where applicable the 'Put' data is used for the 'BULL-ish' data set, and the 'Call' data is used for the 'BEAR-ish' data set. For example if we are inspecting 'AAPL' from the 'BULL-ish' data set then we would use 'Put Open Interest' for the 'Open Interest' check.

For each ticker apply the following checks:
- **Monthly Cycle**: A monthly cycle option was found for the ticker in the 'Tradier' data.
- **Open Interest**: The open interest is >= 8.
- **Bid**: The bid is >= 0.55
- **Spread**: The spread (ask - bid) of the option is <= 8% of the last price of the underlying stock.

Note: This criteria should be easily configurable through either command line parameters, config file or some other convenient method.

### Prepare Additional Weighting Data
For each remaining BULL-ish or BEAR-ish entry calculate a 'trade score' for each entry. The range of this score will be from 0.00 to 5.00 where 0.00 represents a poor quality trade and 5.00 represents the highest quality trade possible.

A weighting algorithm will be created that uses the following weighting table and handles the data normalization that is needed to create a 'trade score'. The 'Weight' value is used to indicate the importance of that particular metric to the weighting algorithm.

Note the 'Growth' metric is only used in the Weighting calculation if the potential trade candidate is in the Growth sector bucket.

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

#### IVR Sourcing Notes
IVR comes from the TastyTrade data and uses the following quality table:
| IVR | Quality |
| -------- | -------- |
| IVR <= 10.0 | 0.0 |
| 10.0 < IVR <= 20.0 | 1.0 |
| 20.0 < IVR <= 30.0 | 2.5 |
| 30.0 < IVR <= 50.0 | 4.0 |
| IVR > 50.0 | 5.0 |

#### IVP Sourcing Notes
IVP comes from the TastyTrade data and uses the following quality table:
| IVP | Quality |
| -------- | -------- |
| IVP <= 10.0 | 0.0 |
| 10.0 < IVP <= 20.0 | 1.0 |
| 20.0 < IVP <= 30.0 | 2.5 |
| 30.0 < IVP <= 50.0 | 4.0 |
| IVP > 50.0 | 5.0 |

#### Open Interest Sourcing Notes
Open Interest comes from the 'Tradier' data and uses the following quality table:
| Open Interest | Quality |
| -------- | -------- |
| Open Interest <= 10 | 0.0 |
| 10 < Open Interest <= 100 | 2.0 |
| 100 < Open Interest <= 1000 | 4.5 |
| Open Interest > 1000 | 5.0 |

#### Spread% Sourcing Notes
Spread% is calculated from the 'Tradier' data using this formula: (ask - bid) / last price of the underlying stock. 

**Spread% Quality**
| Spread% | Quality |
| -------- | -------- |
| Spread% <= 3% | 5.0 |
| 3% < Spread% <= 5% | 3.0 |
| 5% < Spread% <= 8% | 1.0 |
| Spread% > 8% | 0.0 |

#### BPR Sourcing Notes
**BPR Quality**
| BPR | Quality |
| -------- | -------- |
| BPR <= 500 | 3.0 |
| 500 < BPR <= 1500 | 5.0 |
| 1500 < BPR <= 3000 | 3.5 |
| 3000 < BPR <= 4500 | 2.0 |
| BPR > 4500 | 0.0 |


BPR is calculated using the following formula for a Naked Put:
```
MAX(
  20% of underlying price – OTM amount + premium,
  10% of underlying price + premium,
  $2.50 per share + premium
) × 100
```

**Example**: Short Naked Put
Stock = $100
Sell 95 put for $2
```
OTM = 5

Case 1:
20% * 100 = 20
20 - 5 + 2 = 17

Case 2:
10% * 100 = 10
10 + 2 = 12

Case 3:
2.5 + 2 = 4.5

→ BPR = 17 × 100 = $1,700
```

**Example**: Short Naked Call
Similar, but:
```
OTM = strike – stock price
```

Formula:
```
MAX(
  20% of underlying – OTM + premium,
  10% of underlying + premium,
  $2.50 + premium
) × 100
```

#### Cyclical Diversity Sourcing Notes
The Dick Weasel trade data is used to determine how many trades are currently in each of the sectors. Sectors are grouped into 3 distinct buckets. It is advantageous to open a trade in a lightly populated sector bucket. The current sector bucket allocation of the active trades will have to be calculated. When doing this calculation a ticker is only counted once in a sector bucket even if there is more than 1 trade in the ticker active. The 'Cyclical Diversity Quality' depends upon the current allocation percentage of the sector bucket that the potential trade belongs to.

**Sector Bucket Mapping**:
| TastyTrade Sector Name | Standard Name |
| -------- | -------- |
| Economic | Materials |
| Economic | Industrials |
| Growth | Consumer Discretionary |
| Defensive | Consumer Staples |
| Economic | Energy |
| Economic | Financials |
| Defensive | Health Care |
| Growth | Communication Services |
| Growth | Information Technology |
| Transportation | Consumer Discretionary |
| Defensive | Utilities |
| Economic | Real Estate |

**Cyclical Diversity Quality**
| Sector Bucket Allocation% | Quality |
| -------- | -------- |
| Sector Bucket Allocation% <= 21% | 5.0 |
| 21% < Sector Bucket Allocation% <= 55% | 2.0 |
| Sector Bucket Allocation% > 55% | 0.0 |

#### Quant Rating Sourcing Notes
Quant Rating comes directly from the SeekingAlpha data. Note that for BEAR-ish data the smaller the number the better, so we have to flip it (i.e., in order to normalize it) by subtracting it's value from 5.0. 

#### Sector Diversity Sourcing Notes
The Dick Weasel trade data is used to determine how many trades are currently in each of the sectors. It is advantageous to open a trade in a lightly populated sector. The current sector allocation of the active trades will have to be calculated. When doing this calculation a ticker is only counted once in a sector even if there is more than 1 trade in the ticker active. The 'Sector Diversity Quality' depends upon the current allocation percentage of the sector that the potential trade belongs to.

**Sector Diversity Quality**
| Sector Allocation% | Quality |
| -------- | -------- |
| Sector Allocation% <= 3% | 5.0 |
| 3% < Sector Bucket Allocation% <= 13% | 2.0 |
| Sector Bucket Allocation% > 13% | 0.0 |

#### Earnings Date Sourcing Notes
The next earnings date can be found in 2 data sets: the TastyTrade data and the SeekingAlpha data. We will use the earnings date from the TastyTrade data unless that date is blank, then the SeekingAlpha date will be used. If both dates are blank then it will be assumed that the earnings date is 70 days away from the current date. The 'Earnings After Expiration Days (EaE)' is calculated by doing the data math of 'Earnings Date' - 'Expiration Date'.

**EaE Quality**
| EaE | Quality |
| -------- | -------- |
| EaE <= -14 | 3.0 |
| -14 < EaE <= 1 | 0.0 |
| EaE > 1 | 5.0 |

#### Growth Sourcing Notes
The Growth metric is in the SeekingAlpha data and it only matters if the potential trade candidate is in the Growth sector bucket. If the potential trade candidate is not in the Growth sector bucket then we don't use this metric in the weighting calculation. The range of values in the Growth data is 'A+' to 'F'. The table below shows the 'Quality' number to use for BULL-ish trade candidates, for BEAR-ish trade candidates the number is transformed by subtracting the Quality number from 5.

**Growth Quality**
| Growth | Quality |
| -------- | -------- |
| A+ | 5.0 |
| A | 4.5 |
| A- | 4.0 |
| B+ | 3.0 |
| B | 2.5 |
| B- | 2.0 |
| C+ | 1.25 |
| C | 1.0 |
| C- | 0.75 |
| D+ | 0.5 |
| D | 0.25 |
| D- | 0.1 |
| F | 0.0 |

#### Momentum Sourcing Notes
The Momentum metric is in the SeekingAlpha data. The range of values in the Momentum data is 'A+' to 'F'. The table below shows the 'Quality' number to use for BULL-ish trade candidates, for BEAR-ish trade candidates the number is transformed by subtracting the Quality number from 5.

**Momentum Quality**
| Momentum | Quality |
| -------- | -------- |
| A+ | 5.0 |
| A | 4.5 |
| A- | 4.0 |
| B+ | 3.0 |
| B | 2.5 |
| B- | 2.0 |
| C+ | 1.25 |
| C | 1.0 |
| C- | 0.75 |
| D+ | 0.5 |
| D | 0.25 |
| D- | 0.1 |
| F | 0.0 |

#### Bid Sourcing Notes
The Bid data is in the 'Tradier' data. For BULL-ish potential trades the 'Put Bid' is used and for BEAR-ish potential trades the 'Call Bid' is used..

**Bid Quality**
| Bid | Quality |
| -------- | -------- |
| Bid <= 0.55 | 0.0 |
| 0.55 < Bid <= 0.89 | 1.0 |
| 0.89 < Bid <= 1.44 | 2.5 |
| 1.44 < Bid <= 2.33 | 3.5 |
| 2.33 < Bid <= 3.77 | 4.5 |
| 3.77 < Bid <= 6.10 | 2.5 |
| Bid > 6.10 | 0.0 |



## Output Data:

The data will be output to the 'Directory Path'/'uploads' directory into a workbook named 'trade_signals.xlsx' into worksheets named either 'BULL-ish' or 'BEAR-ish'. The sort order will be descending on the 'Trade Score' column.

**WorkSheet Format**:
| Column Name | Format |
| -------- | -------- |
| Ticker | Text |
| Sector Bucket | Text |
| Sector | Text |
| Option Type | Text 'Put' or 'Call' |
| Expiration Date | Date 'MM/DD/YYYY' |
| Earnings Date | Date 'MM/DD/YYYY' |
| DTE | Number '#' |
| Price | Number #.## |
| Strike | Number # |
| Bid | Number # |
| Ask | Number # |
| Spread% | Number '#.#%' |
| Delta | Number '[-]0.##' |
| Open Interest | Number # |
| Trade Score | Number #.## |
| Quant Rating | Number #.## |
| Liquidity | Text '# Stars' |
| Growth | Text |
| Momentum | Text |
| IVx | Number '#.##%' |
| IVR | Number '#.##' |
| IVP | Number '#.##%' |
| BPR | Number '$#' |






