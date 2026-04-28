# Reporting Requirements v2

This document describes the next set of reporting requirements that need to be planned and implemented. It will most likely requirement changes in 4 layers of programs within the 'Copper' project. It is anticipated that the impacted areas are: 'BIC', 'captains_log', 'encyclopedia_galactica' and possibly 'K9'. 

## Requirements

**Trade Number Report**:
- alternate name: 'TradeManagerNotes' Report
- columns: 'Trade #', 'Status', 'Entry Date', 'Underlying'
    - 'Trade #': the XXX_#####_YYY formated trade number string
    - 'Status': 'ACTIVE' or 'CLOSED'
    - 'Entry Date': MM/DD/YYYY of when initial trade entry occurred
    - 'Underlying': for options trades the ticker of underlying equity - (e.g., 'SPX')
- filters:
    - account: the 'XXX' portion of the 'Trade #' - should be 'TRD' by default, 'TRDS' and 'HD" should be valid options that can also be specified
    - 'Trade #': an option should exist so that the specific trade number can be specified
- order: ordered by the '#####' portion of the 'Trade #' in descending order
        
**Daily Notes Report**: This report is a 'Multi-Line Ledger' styled report. It is made up of a 'header' line followed by several 'log lines' associated with that header line.
- alternate name: 'traders_daily_work_notes' Report
- 'header' format: "UUU(XXX_#####_YYY): SSS"
    - 'UUU': is the ticker symbol for the underlying
    - 'XXX+#####_YYY': The 'Trade #'
    - 'SSS': status of the trade 'ACTIVE' or 'CLOSED'
- 'log lines' format: There are 4 types of log lines: 'ENTRY', 'ADJ', 'GTC' and 'EXIT'
    - 'ENTRY' formats: The format depends upon the trade type which is the 'YYY' portion of the 'Trade #'. At this time we will only support 'SIC' format.
        - SIC Format: 'MM/DD/YYYY: ENTRY #N SOLD Nx SIC(PPPP/pppp/cccc/CCCC) DTE:Nd BPR($XXX) DELTA/delta/delta/DELTA $XXXX.XX @-#.## - $#.##'
            - 'MM/DD/YYYY': date the log entry was made, in this case it would also be the entry date of the trade
            - 'ENTRY #N': the 'N' is a number that is a counter of the trade entries that have been made within this trade. We are not supporting multiple entry trades at this time so this number will always be 1.
            - 'Nx': represents the number of SICs that have been sold, at this time we only support selling of 1 SIC in a trade so this is always '1x'
            - 'SIC(PPPP/pppp/cccc/CCCC)': 'PPPP' is the LONG PUT strike, 'pppp' is the SHORT PUT strike, 'cccc' is the SHORT CALL strike and 'CCCC' is the LONG CALL strike
            - 'DTE:Nd': is the DTE at entry, so for a 0DTE trade this would be 'DTE:0d'
            - 'BPR($XXX): Is the BPR required to maintain this trade
            - 'DELTA/delta/delta/DELTA': is the deltas for the LONG PUT/SHORT PUT/SHORT CALL/LONG CALL for example '-.15d/-.20d/.20d/.15d'
            - '$XXXX.XX': last trade price of the underlying at the time of trade entry - for example on a 0DTE trade on SPX this would be the last trade price of SPX
            - '@-#.## - $#.##': option price - entry fees, example '@1.50 - $0.50' represents receiving $150.00 - $0.50 => $149.50
        - SIC Example: '01/05/2026: ENTRY #1 SOLC 1x SIC(6995/7000/7050/7055) DTE:0d BPT($500) .15d/-.20d/.20d/.15d $7025.08 @1.50 - $0.50`
    - 'ADJ' formats: currently trade adjustments are not supported so this format will be skipped for now
    - 'GTC" formats: used to describe the PENDING close data that was created as a 'take profit' close for the trade
        - format: 'MM/DD/YYYY: GTC Quantity:N TP:PP%@-#.## PP:$#.## CB:$###.##
            - 'MM/DD/YYYY': date the GTC PENDING 'take profit' order was entered
            - 'Quantity:N': 'N' is the number of close trade strategies that are to be close, it correlates directly to the 'Nx' clause in the 'SIC ENTRY format'.
            - 'TP:PP%@-#.##': represents the estimate of the percentage of profit of the CREDITs received that we will keep with this 'take profit' order and the pending exit price that this GTC order is being set at. So for example if we entered the trade at 1.50 and wanted to exit at 0.75 - that would be keeping 50% of the CREDIT received -> 'TP:50%@0.75'
            - 'PP:$#.##': The potential profit that this trade will make if this 'take profit' trade is filled, so if $75.00 will be made -> 'PP:$75.00'
            - 'CB:$###.##': Is the CREDIT balance of the trade before this 'take profit' is filled, so if we SOLD an SIC for $150 -> 'CB:$150.00'
        - GTC Example: '01/05/2026: GTC Quantity:1 TP:50%@-0.75 PP:$75.00 CB:$150.00`
    - 'EXIT' format: 'MM/DD/YYYY: EXIT #N RRRR CLOSED TRADE @-#.## - $#.##
        - 'MM/DD/YYYY': date the trade was closed
        - 'EXIT #N': the 'N' is a number that is a counter of the trade exits that have been made within this trade. We are not supporting multiple exit trades at this time so this number will always be 1.
        - 'RRR': String representing the reason for the trade closure: 'GTC', 'MANUALLY' or 'EXPIRED'
            - 'GTC': mean the GTC 'take profit' was hit
            - 'MANUALLY': means the human user manually closed the trade via the brokerage application
            - 'EXPIRED': means that the options expired, thereby closing the trade
        - GTC EXIT Example: '01/05/2026: GTC CLOSED TRADE @-0.75 - $0.50'
    - Additional Thoughts: 
        - Architecture: At the time of this writing the thought is that these log entries would best be formatted in the BIC layer and stored via the captains_log
        - EXIT Types: After a trade is entered it is very common the a GTC LIMIT order will be placed as a 'take profit' mechanism to close the trade at a pre-defined profit level. This order is a 'PENDING' order in the brokerage system. That pending order may or may not get filled, it is also possibly that the trade could be manually closed by the human trader via the brokerage website, desktop application or mobile app. Another alternative is that the options in the trade will expire naturally. It is the job of the BIC layer to be able to detect when one of these close conditions occurs and to update the captains_log appropriately.
    - filters:
        - account: the 'XXX' portion of the 'Trade #' - should be 'TRD' by default, 'TRDS' and 'HD" should be valid options that can also be specified
        - 'Trade #': an option should exist so that the specific trade number can be specified
        - 'Underlying': an option should exist so that the only trades using the specified underlying are to be reported on
    - order: ordered by the '#####' portion of the 'Trade #' in descending order


 **Trade PnL Report**:
- alternate name: 'TradeHistory' Report
- columns: 'Trade #', 'Status', 'Entry Date', 'Exit Date', 'CREDIT Received', 'CREDIT Fees', 'DEBIT Paid', 'DEBIT Fees' and "Total'
    - 'Trade #': the XXX_#####_YYY formatted trade number string
    - 'Status': 'ACTIVE' or 'CLOSED'
    - 'Entry Date': MM/DD/YYYY entry date of the trade
    - 'Exit Date': MM/DD/YYYY exit date of the trade
    - 'CREDIT Received': total amount of dollars received in premium on orders filled for a CREDIT
    - 'CREDIT Fees': on the orders that filled for a CREDIT there are usually associated fees
    - 'DEBIT Paid': total amount of dollars paid on orders that were filled and a DEBIT had to be paid
    - 'DEBIT Fees': on the orders that filled and a DEBIT was paid there are usually associated fees
    - 'Total': sum of the CREDIT Received', 'CREDIT Fees', 'DEBIT Paid', 'DEBIT Fees'
  - filters:
      - account: the 'XXX' portion of the 'Trade #' - should be 'TRD' by default, 'TRDS' and 'HD" should be valid options that can also be specified
      - 'Trade #': an option should exist so that the specific trade number can be specified
      - 'Entry Date': specify that the entry dates with support for ">", ">=", "<" and "<="  example: --entry_date ">=01/01/2026"
      - 'Exit Date': specify that the exit dates with support for ">", ">=", "<" and "<="  example: --exit_date "<02/01/2026"
  - order: ordered by the '#####' portion of the 'Trade #' in descending order
  
**Trade PnL Report**:
  - alternate name: 'TradeHistory' Report
  - columns: 'Trade #', 'Status', 'Entry Date', 'Exit Date', 'DiM', 'CREDIT Received', 'CREDIT Fees', 'DEBIT Paid', 'DEBIT Fees', "Total', 'TP%', 'Annualized Return%'
      - 'Trade #': the XXX_#####_YYY formatted trade number string
      - 'Status': 'ACTIVE' or 'CLOSED'
      - 'Entry Date': MM/DD/YYYY entry date of the trade
      - 'Exit Date': MM/DD/YYYY exit date of the trade
      - 'DiM': Days the trade was in market - only applies to CLOSED trades
      - 'CREDIT Received': total amount of dollars received in premium on orders filled for a CREDIT
      - 'CREDIT Fees': on the orders that filled for a CREDIT there are usually associated fees
      - 'DEBIT Paid': total amount of dollars paid on orders that were filled and a DEBIT had to be paid
      - 'DEBIT Fees': on the orders that filled and a DEBIT was paid there are usually associated fees
      - 'Total': sum of the CREDIT Received', 'CREDIT Fees', 'DEBIT Paid', 'DEBIT Fees'
      - 'TP%': percentage of the premium received that was retained. For loses this will be a negative %
      -'Annualized Return%': the annualized return of this trade.
  - filters:
      - account: the 'XXX' portion of the 'Trade #' - should be 'TRD' by default, 'TRDS' and 'HD" should be valid options that can also be specified
      - 'Status': filter 'ACTIVE', 'CLOSED' or 'BOTH' this default is 'BOTH'
      - 'Trade #': an option should exist so that the specific trade number can be specified
      - 'Entry Date': specify that the entry dates with support for ">", ">=", "<" and "<="  example: --entry_date ">=01/01/2026"
      - 'Exit Date': specify that the exit dates with support for ">", ">=", "<" and "<="  example: --exit_date "<02/01/2026"
  - order: ordered by the '#####' portion of the 'Trade #' in descending order
  - 'trailer' format: 'Closed Trade Count', 'Winning Trade Count', 'Losing Trade Count', 'Win%', 'Total PnL', 'Average PnL', 'Max PnL', 'Max DD', 'Avg. DiM', 'Avg. TP%', 'Profit Factor', 'Profit Expectancy', 'Payoff Ratio', 'Sharpe Ratio', 'Sortino Ratio', 'Calmar Ratio'
      - 'trailer' only applies to 'CLOSED' trades, if there are no closed trades use Zeros or "N/A"


