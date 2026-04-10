# Tradier Sniffer Intent

The purpose of this file is to define the original intent and ideas that led to the belief that the 'tradier_sniffer' program / utility / script was needed. It will also describe the capabilities that 'tradier_sniffer' will have to demostrate in order to meet its' 'minimum viable product' ("MVP") expectations.

The intent of the 'tradier_sniffer' program is not to become a "production" program but rather used to provide some 'proof-of-concept' use case examples to demonstrate how some required capabilities of an automated trading system and automated trade journal can be supported. This document will make the case for the what and why of these use cases, and the implementation will show the how of these use cases. It is the intent that these use cases can be used as an example and implemented fulling in an automated trading system such as 'K9' to implement its' automated test management and journal requirements. Another way to state the intention of this program is to say its' purpose is to prove to 'Mr. Dick Weasel' that the 'Tradier' API contains enough functionality to programmatically implement the capabilities needed to automate his current manual trading system. This document goes into great effort to document those needed capabilities, so that an AI Developer can plan and implement these 'proof-of-concept' use cases in the 'tradier_sniffer' program so that they can be demonstrated to 'Mr. Dick Weasel' to his satisfaction and then thereby hopefully gain approval to proceed with the design and development of the 'K9' program.

Since the 'tradier_sniffer' program is for 'proof-of-concept' it is anticipated that it will only need to use the 'Tradier' sandbox account. Some documentation and links relevant to using the 'Tradier API' are in this @docs/TRADIER_DOCUMENTATION.md file.

## Glossary

@docs/GLOSSARY.md

## Technology Stack
This is the expected technology stack that will be used for the 'tradier_sniffer' program.
- python 3.13*
- python uv package manager
- Ubuntu OS

## Background

The human trader (a.k.a., Mr. Dick Weasel) has created and uses a 'manual trade journal' system ("MJ"). This journal is used to document trades that are currently active and have been closed. Once a trade has been entered (i.e., filled by a brokerage) it is then "tracked" from a paper trail perspective manually using the spreadsheets and text files in the "MJ". 

Here are the details on on how relevant use cases are manually handled in "MJ":
### 'Trade Entry MJ Documentation Process'
This use case covers the documentation use case after a trade has initially been entered. It does not cover the selection process used to arrive at the decision take make a specific trade involving other specifics such as" 'underlying', 'strike price', 'trade type - options strategy', etc. That is all part of the 'Trade Selection' process which although is important and detailed, it is not part of "MJ". "MJ" begins once the trade entry order process has been filled by the brokerage.

1) A 'Trade #' is manually assigned to the trade once the trade entry has been filled by the broker, the data is maintained in the 'TradeManagerNotes.txt' file. The data in this files is grouped by the 'Trade #' and the data that is kept track of for each trade is the current trade status 'open' or 'closed', date of entry and underlying equity. This is used as the source of record for what the last trade # was so that the next sequential trade number can be determined by incrementing the number portion of the previous 'Trade #'.
2) The trade is entered in the 'traders_daily_work_notes.txt' where the trades are entered and kept track of in two sections. The 1st section groups the 'Trade #' and 'underlying' into "categories" (i.e., 'Option' or 'Stock') (Note: a combination trade such as a 'CCALL' is categorized as a 'STOCK' trade). The 2nd section is only used by trades categorized as 'Option' in the 1st section and groups the 'Trade #' and 'underlying' by the earliest expiration date within all of the trades options legs. The entries in this section holds ad hoc text journal data entered by 'Mr. Dick Weasel' which is grouped by the date that 'Mr. Dick Weasel' entered the data. There may very will be several entries for a single day, and there will be many days where no entries were made. There is a cryptic syntax that 'Mr. Dick Weasel' uses which is outside of the scope for this document but for the same of completeness is shown below.

**Example of 1st section of 'traders_daily_work_notes.txt'
```
Current Trade Status grouped by account and trade category:
-----------------------------------------
TW:
	- Options:
		-- AMZN(003097_TW_NPUT):
		-- FCX(003094_TW_NPUT):
		-- PM(003103_TW_NPUT):

	- Stocks:
		-- OKLO(002475_TW_LSTOCK):
		-- RKLB(002331_TW_LSTOCK):
```

**Example of 2nd section of 'traders_daily_work_notes.txt'
```
Trade Log grouped by earliest option expiration date and sorted by 'underlying' within the group:
-----------------------------------------
######## Trade Log ###############################################################################

########
5/15/2026 expires:
-- BWA(003025_TW_FWHEEL): check 04/17
	12/8/2025: ENTRY #1: SOLD 1x NPUT(40P) - Q:STRONG BUY  DTE:39d BPR($800) PoP:72% $41.92 -.30d @0.80 - $1.11
	12/31: ADJ #1: ROLLED 1x NPUT(40P->42.5P) out and up - Q:STRONG BUY  DTE:51d BPR($700) PoP:75% $45.56 -.27d @0.77 - $1.22
	2/11/2026: ADJ #3: ROLLED 1x NPUT(42.5P->60P) out and up - Q:BUY  DTE:37d BPR($1000) PoP:81% $64.66 -.26d @0.95 - $1.24
	2/20: ADJ #4: ROLLED 1x NPUT(60P->57.5P) out and down - Q:STRONG BUY  DTE:84d BPR($1500) PoP:65% $58.55 -.43d @0.56 - $1.24
	3/03: ADJ #5: ROLLED 1x NPUT(57.5P) into 1x STRANGLE(55P/57.5C) - Q:BUY  DTE:73d BPR($1800) PoP:60% $53.28 17DT @0.80 - $2.37
	NOTE: 1x STRANGLE(55P/57.5C) - Q:BUY  DTE:73d BPR($1800) PoP:60% $53.28 17DT
	GTC quantity:1 TP:~60+%@1.45 PP:~$233.08 CB:$380.82  (3/3)
-- COIN(003098_TDA_NCALL): check 05/01 05/15
	4/7/2026: ENTRY #1: SOLD 1x NCALL(40P) - Q:SELL  DTE:38d BPR($2100) PoP:82% $173.45 .19d
	NOTE: 1x NCALL(40P) - Q:SELL  DTE:38d BPR($2100) PoP:82% $173.45 .19d ADJ TP: 05/01 05/15
	GTC quantity:1 TP:68%@1.10 PP:$233.08 CB:$344.33  (4/7)
## ERO(003069_TDA_FWHEEL):  CLOSED
	1/20/2026: ENTRY #1: SOLD 1x NPUT(30P) - Q:STRONG BUY  DTE:59d BPR($1100) PoP:61% $30.61 -.42d
	3/06: ADJ #1: ROLLED 1x NPUT(30P) out - Q:BUY  DTE:70d BPR($1300) $28.15 -.52d
	NOTE: 1x NPUT(30P) - Q:BUY  DTE:70d BPR($1300) $28.15 -.52d
	GTC quantity:1 TP:37%@2.45 PP:~$144.08 CB:$388.02  (3/6)
	4/08: EXIT #1: Hit GTC TP !!!
```
3) The trade data is entered into the 'ActiveTradeLog' worksheet of the 'TradeHistory.xlsx' workbook. This workbook is used to keep track of the CREDITs and DEBITs accumulated on a per trade basis. There will be several rows associated with a trade, and all of a trades rows are kept together (See Example data below). The rows in this worksheet are 'clustered' together by 'Trade #' and are orders by the number portion of the 'Trade #' in descending order. Open / Active trades are kept in the 'ActiveTradeLog' worksheet. Once a trade is Exited / Closed its' data is manually cut out of the 'ActiveTradeLog' worksheet and into the 'TradeHistoryArchive' worksheet. There are standard formulas within a trade's 'cluster' of rows that calculate items such as current trace balance, each entry, adjustment and exit's CREDIT / DEBIT impact along with associated fees along with some other calculations outside the scope of this discussion.

**Example of a trade entry (multiple rows) in 'ActiveTradeLog' worksheet**:
| Description | # of Contracts | CREDIT/100 per Contract | CREDIT $####.## | Fees $####.## | Total CREDIT $####.## | Entry Adj. eXit |  | Totals $####.## |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ********************************************************************************** |  |  |  |  |  |  |  |  |
| 003072_TDA_NPUT      AMD    $2800 | ROWS BEGIN: | 257 |  |  |  |  | CREDIT Total: | $1,409.00  |
| 1/22/2026: SOLD -1 AMD 100 20 FEB 26 230 PUT @4.70 MIAX # ENTRY #1: SOLD 1x NPUT(230P) - Q:STRONG BUY   DTE:28d  BPR($2800) PoP:79% $261.56 -.19d | 1.00 | 4.70 | $470.00 |	($0.66)	| $469.34 |	E |	CREDIT Fees Total:	| ($3.96) |
| 2/05: SOLD -1 1/1/-1 CUSTOM AMD 100 18 JUN 26/17 APR 26/20 FEB 26 190/190/230 PUT/CALL/PUT @8.17 CBOE # ADJ #1: ROLLED 1x NPUT(230P) into 1x CALENDAR(190P/190C) - Q:STRONG BUY   DTE:71d/133d  BPR($8500) $193.11 .59d/-.40d | 1.00	| 8.17 | $817.00 | ($1.98) | $815.02 | A | DEBIT Total: | $0.00 |
| 2/06: SOLD -1 1/-1 CUSTOM AMD 100 17 JUL 26/17 APR 26 210/190 PUT/CALL @1.22 CBOE # ADJ #2: ROLLED 1x CALENDAR(190P/190C) into 2x NPUT(190P/210P) - Q:STRONG BUY   DTE:132d/161d  BPR($11500) $206.37 -.33d/-.43d | 1.00	| 1.22 | $122.00 | ($1.37) | $120.68 | A | DEBIT Fees Total: | $0.00 |
| GTC quantity:2 TP:24%@5.30 PP:$343.64 CB:$1405.04 (2/6) | | | | | | | | |
| Totals: | ROWs END: | 264 | $1,409.00  | ($3.96) | $1,405.04 | | | |
| ********************************************************************************** | | | | | | | | |

**Example of a trade entry (multiple rows) 'TradeHistoryArchive' worksheet**:
| Description | # of Contracts | CREDIT/100 per Contract | CREDIT $####.## | Fees $####.## | Total CREDIT $####.## | Entry Adj. eXit |  | Totals $####.## |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ********************************************************************************** |  |  |  |  |  |  |  | |
| 003034_TDA_NCALL      KMB      $1500 | ROWS BEGIN: | 549 |  |  |  |  | CREDIT Total: | $95.00  |
| 12/17/2025: SOLD -1 KMB 100 16 JAN 26 110 CALL @.95 CBOE # ENTRY #1: SOLD 1x NCALL(110C) - Q:HOLD   DTE:30d  BPR($1500) PoP:82% $103.26 .21d | 1.00 | 0.95 | $95.00 | ($0.66) | $94.34 | E | CREDIT Fees Total: | ($0.66) |
| 12/22: BOT +1 KMB 100 16 JAN 26 110 CALL @.35 CBOE # EXIT #1: Hit GTC TP !!! | 1.00	| -0.35 | ($35.00) | ($0.66) | ($35.66) | X | DEBIT Total: | ($35.00) |
| | 1.00	| 0.00| $0.00 | $0.00 | $0.00 |  | DEBIT Fees Total: | ($0.66) |
| GTC quantity:1 TP:54%@0.40 PP:$48.84 CB:$94.34  (12/17) | | | | | | | | |
| Totals: | ROWs END: | 556 | $60.00  | ($1.32) | $58.68 | | | |
| ********************************************************************************** | | | | | | | | |

#### TP Calculation
After the current balance is calculated in the 'ActiveTradeLog' worksheet (see above) some of the metrics are then manually copied to another worksheet where the TP exit point is for this trade. The details for this calculation are not important to this document but generally the input criteria is the (CREDIT received - Fees) * (1 - TP%) where TP% is something like 50%. This TP exit point is manually documented in the 'ActiveTradeLog' and in the 2nd section of the 'traders_daily_work_notes.txt' for the trade, and then the TP is manually entered into the brokerage account for this trade as a GTC BTC LIMIT order that is used to close the trade at the calculated TP level.

4) The trade data is entered into the 'daJournal' worksheet of the 'journal.xlsx' workbook. This worksheet is used to keep track of the BPR required to enter the trade, the BPR needed to maintain the trade (set to entry BPR initially), date the trade was entered and the trade category ('Option' or 'Stock') and is grouped by the 'underlying' and 'Trade #'. 
   
**Example of a trade entry (single row) in 'daJournal' worksheet**:
| Symbol | Trade # | Entry BPR | Maintenance BPR | Entry Date | Trade Category |
| --- | --- | --- | --- | --- | --- |
| AMD | 003072_TDA_NPUT | $2800 | $11500 | 1/22/2026 | Option |

5) The trade data is entered into the 'PositionPlanner' worksheet of the 'optionStrategyModels.xlsx' workbook. This worksheet is used to keep of active trades in each sector for each brokerage account along with the 'underlying' symbol. 

**Example of a trade entry (single row) 'PositionPlanner' entry**:
| Sector | Account | Symbol | Category | Strategy | Expiration Date |
| --- | --- | --- | --- | --- | --- |
| Technology | TDA | AMD | Option | NPUT | 6/18/2026 |

### 'Trade Monitoring and Adjustment MJ Documentation Process'
Every day 'Mr. Dick Weasel' goes the the 'traders_daily_work_notes.txt' and for every trade in section 1 he checks the following:
- is the trade still open or has the TP been hit ? 
  - *Source of Truth*: brokerage application
  - Not open - 'Mr. Dick Weasel' manually updates the documentation to reflect this new change in the trade status - see 'Trade Closed MJ Documentation Process' below.
- does the trade need to be manually closed ?
  - *Source of Truth*: 'Mr. Dick Weasel' follows a proprietary set of trade mechanics that are outside of the scope of this document.
  - after closing the trade using the brokerage application 'Mr. Dick Weasel' manually updates the documentation to reflect this new change in the trade status - see 'Trade Closed MJ Documentation Process' below.
- if open, does the trade need to be adjusted ?
  - *Source of Truth*: 'Mr. Dick Weasel' follows a proprietary set of trade mechanics that are outside of the scope of this document.
  - after making the adjustment using the brokerage application 'Mr. Dick Weasel' manually documents the change - see 'Trade Adjustment MJ Documentation Process' below
- No change to an open trade
  - for any documentation tasks required my "MJ" when there are no changes to be made to the trade see 'No Change MJ Documentation Process' below.
### 'No Change MJ Documentation Process'
Even we there are now changes to a trade there are some documentation updates to be made according to the "MJ" process.
1) In the 'daJournal' worksheet the 'Maintenance BPR' is updated with the current margin requirement for the trade according to the brokerage application.
2) The 'Next Check' data in 2nd section of the 'traders_daily_work_notes.txt' is updated to the next trading date after today (i.e., the date of the next day that the market is open)
### 'Trade Adjustment MJ Documentation Process'
The following steps are followed when an adjustment is made to a trade.
**'traders_daily_work_notes.txt' Updates**: in section 2 a note is made as to what the change was and why it was made
**'ActiveTradeLog' Updates**: the orders that were closed and opened to effect the adjustment along with the CREDITs / DEBITs are entered in the ledger for the trade
**'Position Planner' Updates**: if the earliest expiration date changed it is updated in this worksheet
### 'Trade Closed MJ Documentation Process'
The following steps are followed when an adjustment is made to a trade.
**'TradeManagerNotes.txt' Updates**: the trade is marked as 'Closed' in this document
**'traders_daily_work_notes.txt' Updates**:
- in section 1 the trade is removed from this section
- in section 2 the 'Next Check' date is cleared, a note is made as to the reason why the trade was closed
**'ActiveTradeLog' Updates**: the ledger rows that are associated with the closed trade are cut from this worksheet
**''TradeHistoryArchive' Updates**: 
- the ledger rows that were cut from the 'ActiveTradeLog' are pasted into this worksheet
- the orders that closed the trade along with the CREDITs / DEBITs are entered in the ledger for the trade
**'daJournal' Updates**: the row entry for the closed trade is deleted
**'PoP%_Analysis_CLOSED' Updates**: this worksheet in the 'journal.xlsx' workbook contains a row entry for every closed trade along with a PnL summary for the trade.
**'Position Planner' Updates**: the row entry for the closed trade is deleted from this worksheet

## Future State
An overall goal is to build an automated trade program  (i.e., 'K9') and have it contain automated trade journal capabilities. However, that is not the goal of this 'tradier_sniffer' program. The goal of this program is to programmatically demonstrate some of the capabilities that will be needed by the 'K9' program. The purpose of the previous 'Background' section is to give some grounding knowledge on how a manual trade journal process works, which gives a foundation as to why some of the soon to be described capabilities are needed in an automated system.

## Key Concept
The most important concept that needs to be demonstrated is how to keep track of the trade orders in the brokerage application that make up a 'trade' in our trading system. For an example of this concept consider a 'Short Iron Condor' trade, it is composed of 4 option orders (i.e., a short Put, a long Put, a short Call and a long Call). Logically our trading system will consider this a single trade and will associate a home grown 'Trade #' with it for tracking purposes within our data. However the brokerage does not use our 'Trade #' or keep track or reference our 'Trade #'. Which brings up several questions of interest about what capabilities exist within the 'Tradier API' to help us keep track of our logical trade within the brokerage data. How we can keep track of the orders that are in the brokerage and associate / map each one to a 'Trade #' in our trading system data is a 'Key Concept' we have to figure out and be able to demonstrate under various scenarios.

## Our Trade System Environment
Although it is expected that the brokerage runs in scalable, resilient and redundant environment. Our local trading system runs on a personal Ubuntu desktop system using a home WiFi connection and public power (i.e., not UPS). 'Mr. Dick Weasel' plans to keep this system powered on during regular trading hours - but the automated trading program design should take into consideration that it will be on and running most of the time. If it has to be rebooted or the electricity goes out for a short bit, then the automated trade software will have to be able to re-sync with the brokerage data upon resumption. In other words if a trade gets closed because it hit its' GTC BTC Limit TP order, that the automated software would be able to see that the brokerage order history now contains some new closed orders since the last time it looked and it needs to figure out what happened and which trade was impacted and catch up to the current status of that trade and all other trades. A polling model is probably a better fit than a streaming model given the reliability of our trading system. But maybe via streaming there is a mechanism to catch up to missed events ? That is an outstanding question - the design of our communication with the brokerage and the questions answered here will impact the design of the automated trading program.

## Base Trading System Requirements

**Trade Entries**: All trades are entered using a STO Limit order with a TiF of 'Day'. It is expected that the trade will also be able to be 'replaced' with a lower entry price, or at a minimum be able to be 'cancelled' and then a new lower priced trade entered. Trading will only be done during regular market hours - no extended hours trading.

**TP Orders**: Almost all trades will have a GTC BTC Limit order. It is expected that this order can be 'replaced' or at a minimum be 'cancelled' and a new TP order entered.


### Important Questions

The demonstration of answers to these questions will lead directly to an implementation in the 'K9' program that will give it the necessary capabilities to run an automated trading system.

- When a multi-leg option trade is entered (not yet filled) how do we know if / when it gets filled ?
  - Is the API order placed synchronously - so that we don't get a response until it is filled or times out ?
  - Is the API order placed asynchronously - can we poll the brokerage or is there call back functionality ?
  - Can we place a time limit on the fill ?
  - Can we implement a retry loop that brings our required entry price down a few pennies and tries again ?
- How can we associate the various options orders (multiple legs) with a 'Trade #' so that if they get closed - either manually by 'Mr. Dick Weasel' using the desktop application to close the trade or by hitting a GTC BTC order.
  - Does the brokerage have a reference # for each specific order that we can use to map orders to trades ?
  - Does the brokerage support a tagging capability where we can add a tag to an order to indicate which trade it belongs to ?
  - We will want to associate filled orders and pending orders with a trade ?
    - For example we place a Day STO Limit order - it is pending, we reboot the local computer running our automated trade program, during the down time the trade 'fills' on the brokerage side, we bring our trading system up and it knows (according to its' local database) that we have a pending entry order. How can it figure out that the order 'filled' and it needs to update its' status and all related data for the trade with the 'filled' data ?
- Is there a list of error reasons for a order being 'cancelled' or 'rejected' ?
- Some options trade on nickel pricing (i.e., they only trade on 0.05 boundaries such as 1.05, 1.10 etc.)
  - What happens when we place an Day STO Limit order with a penny based entry price (1.08) on a nickel only option ?
- Does the 'Tradier' brokerage support price improvement (i.e., the fill price is better than the Day STO Limit price) ?
  - Does the broker
- In the world of 0DTE trades on cash-settled options letting an option expire is very common. 
  - When does the option expire order status become visible in the order history for the brokerage (e.g., 5 minutes after market close, 5:00 PM, ???)
- If we have a trade that involves Stock, such as a 'CCALL' and we receive a dividend payment what will that 'look' like to the automated trade program from an API perspective ?
- How is the maintenance BPR of a trade (with multiple legs) determined ?
- When adjusting a trade (e.g., rolling the Call side option down towards the Puts in a 'SIC' trade) can all of the adjustment orders (e.g., BTC a Call Spread, and then STO a Call Spread with lower strike prices) be placed into a single Day Limit order ?
- Can a TP trade be placed / adjusted after hours so that it in essence takes effect during the next trading session ?
- Can after hours / extended hours pricing information be retrieved for Stocks ?
- What exchange routing options are available ? Can a person just select a generic 'BEST' ?
- What necessary account information is available via the 'Tradier API' ?
  - A list of needed data points include: Net Liquidity, Cash Balance, PDT Count, Option Buying Power, Beta-weighted delta, Total Theta, account transactions (e.g., withdraws and deposits)
- Is there a flag available when a trade is closed that indicates that the broker is going to count that trade as a 'PDT' ?
- What security is available to lock down my API access ?
  - OAuth password ? Any additional ssh or two-factor authentication or IP white-listing available ?
  - Can a strong authentication mechanism be put in place and still be compatible with a automated trader program ?
- Are there any account level restrictions that can be put in place - max trade size - max BPR - max number of trades ?
- The automated trading system does not need a constant flow of real time pricing data to make its' entry decisions.
  - Entry signals can be hard-coded (e.g, daily 0DTE trades on SPX on the 20 delta with $10 wings and a 20% TP)
  - Other trade signals will come from sources outside of the automated trading system. The details of this interface will be designed later, for now suffice to say streaming price data is not needed by the automated trading system.
    - Do we have any need to stream any data ?
    - Are trades entered into synchronously or asynchronously or something else ?















