# Glossary 

## Trade Glossary
The terms are common terms that are used in the universe of the human trader (a.k.a, Mr. Dick Weasel) who uses the programs / scripts in the 'copper' project. These terms are specified here for the sake of clarify, often they mimic the standard industry definition but not always. So for the purposes of grounding this projects' definition of these key terms are given here.

**Trade #**: The proprietary naming / numbering convention that is used to track a trade in Mr. Dick Weasel's trading system. The format of this trade # is a text string: 'BBB_#####_TTT' where 'BBB' indicates the brokerage (2-5 characters), '#####' is a sequential trade number (zero filled on the left, min. size is 5 digits) and 'TTT' indicates the trade type at entry (3-10 characters).

### **Valid 'Trade #' Substrings**: 'BBB_#####_TTT'
| Substring | Valid Entries |
| -------- | -------- |
| 'BBB' | 'TRD', 'TRDS', 'TW', 'TDAR', 'TDA' |
| '#####' | '00001', '00002', '00003' and so on |
| 'TTT' | 'SIC', 'PCS', 'CCS', 'NPUT', 'NCALL', 'CCALL', 'STOCK' |

A 'Trade #' is a logical grouping concept that is used for the purposes referring to a grouped set of brokerage orders (either 'filled' or 'pending') throughout the duration of a trade strategy (i.e., 'Entry / Open', 'Adjustment', 'Management' and 'Exit / Close'). It is used in a trading system as a way to keep track of a trade for both management, reporting and accounting purposes.

**TRD**: 'Tradier' production account

**TRDS**: 'Tradier' sandbox account

**TW**: 'TastyTrade' account

**TDAR**: 'TD Ameritrade' Roth account

**TDA**: 'TD Ameritrade' account

**SIC**: Short Iron Condor

**PCS**: Put Credit Spread

**CCS**: Call Credit Spread

**NPUT**: Short Naked Put

**NCALL**: Short Naked Call

**CCALL**: Covered Call

**STOCK**: Stock or ETF

**STO**: "Sell To Open"

**BTC**: "Buy To Close"

**GTC**: A 'TIF' setting - "Good til Cancelled"

**DAY**: A 'TIF' setting - "Good for Today Only"

**TIF**: "Trade in Force" - how long an order is valid before is expired

**BPR**: Buying Power Requirement that is needed to open the trade or to keep the trade open, depending upon the context.

**TP**: 'Take Profit' - is a GTC LIMIT BTC order to close the trade which is used to close the trade once a certain profit level has been reached (e.g., 50% of premium received).

****:

