# Expired Options Research Notes

# Prompt
In the tradier brokerage API how does one detect expired option contracts ?

# Response
In the Tradier brokerage API, you detect expired option contracts primarily by comparing the contract's embedded OCC expiration date against the current date or by checking active market data availability. The Tradier API does not provide a single "is_expired" boolean flag for contracts, nor does it support active market data queries for expired instruments. [1, 2] 
You can identify expired options using the following data validation methods:
## 1. Parse the OCC Symbol String [3] 
The standard Options Clearing Corporation (OCC) symbol format used by Tradier contains the exact expiration date. You can parse this string programmatically to check if the date has passed.

* Format: ROOT + YYMMDD + C/P + STRIKE (e.g., AAPL260515C00150000)
* Detection Step: Extract the 6-character date string (260515), format it as 2026-05-15, and check if it is prior to today’s date.

## 2. Verify Against the Market Expirations Endpoint
Active options contracts are listed in Tradier's market data directory. Expired contracts are instantly removed. [4] 

* Action: Make a request to the [Get Options Expirations endpoint](https://docs.tradier.com/reference/brokerage-api-markets-get-options-expirations) (GET /v1/markets/options/expirations) for the underlying security.
* Detection Step: If the expiration date of your contract is no longer returned in the date array, the contract has officially expired. [5, 6] 

## 3. Check for Missing Market Data (Quotes and Chains) [7] 
Tradier explicitly states that historical and real-time options market data is restricted to active contracts. [1, 2, 8] 

* Action: Request data from the [Get Quotes endpoint](https://docs.tradier.com/reference/brokerage-api-markets-get-quotes) (GET /v1/markets/quotes) or the [Get Options Chains endpoint](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains) (GET /v1/markets/options/chains) using the specific contract symbol.
* Detection Step: If the contract is expired, the market data response will return empty, show null values, or drop the contract completely. [2, 5, 9, 10, 11] 

## 4. Monitor Account Orders and Balances
If you are tracking options within a user portfolio or order book, you can monitor status shifts.

* Order Tracking: When querying orders via the [Get Account Orders endpoint](https://docs.tradier.com/reference/brokerage-api-accounts-get-account-orders) (GET /v1/accounts/{account_id}/orders), an unexecuted option order that crosses past the market close on expiration day will return a status of expired.
* Position Disappearance: Expired options positions are automatically removed from your active positions list after final clearing settlement. [12, 13, 14, 15] 

If you need to archive and track options long-term, it is recommended to pull and save your target Options Chains daily to a local database before they pass their expiration windows. [9, 16] 
Are you attempting to filter out expired options from an active trading script, or are you looking to retrieve past portfolio data for tax and tracking purposes?

[1] [https://docs.tradier.com](https://docs.tradier.com/docs/historical-data)
[2] [https://docs.tradier.com](https://docs.tradier.com/docs/historical-data)
[3] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-markets-get-timesales)
[4] [https://www.sirion.ai](https://www.sirion.ai/library/contract-insights/automatic-expired-contract-archiving/)
[5] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-markets-get-options-expirations)
[6] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-markets-get-options-expirations)
[7] [https://docs.tradier.com](https://docs.tradier.com/docs/trading)
[8] [https://www.marketdata.app](https://www.marketdata.app/data/options/)
[9] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-markets-get-options-chains)
[10] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-markets-get-quotes)
[11] [https://www.reddit.com](https://www.reddit.com/r/options/comments/1ht6njr/tradier_api_oddity/)
[12] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-accounts-get-account-orders)
[13] [https://docs.tradier.com](https://docs.tradier.com/docs/trading)
[14] [https://docs.tradier.com](https://docs.tradier.com/reference/brokerage-api-accounts-get-account-order)
[15] [https://upstox.com](https://upstox.com/learning-center/futures-and-options/what-is-expiration-time-in-options-trading/article-404/)
[16] [https://www.reddit.com](https://www.reddit.com/r/algotrading/comments/hgji59/free_api_for_option_chains/)

# Prompt
I am trying to determine the best way to reconcile the status of a trade that had options that expired. In other brokerages there is an "Option removed due to expiration" logged in the accounting / order history that can be used. I am trying to determine how best to do this using the tradier API.

# Response
To reconcile expired positions, you should query the Account History endpoint.
Unlike the orders endpoint (which tracks order attempts), the history endpoint records the actual administrative events that remove expired contracts from your holdings.
## The Specific Event to Look For
You are looking for a history event with the type option and the subtype OPTEXP.

* Endpoint: GET /v1/accounts/{account_id}/history
* Event Type: option
* Option Type: OPTEXP (or occasionally expiration in older records)
* Description: Typically "Expired" [1] 

## JSON Example
Here is how an expired option event appears in the Tradier API response. Note that the quantity is negative (indicating removal from the account) and the amount is 0 (indicating no cash changed hands).

{
  "history": {
    "event": [
      {
        "amount": 0,
        "date": "2024-05-17T00:00:00Z",
        "type": "option",
        "trade_type": "Option",
        "symbol": "SPY240517C00500000",
        "option": {
          "option_type": "OPTEXP",
          "description": "Expired",
          "quantity": -1.00000000
        }
      }
    ]
  }
}

## Reconciliation Logic
To fully reconcile the trade status in your system, follow these checks:

   1. Match the Event: Iterate through the history array for events where type == 'option' and option.option_type == 'OPTEXP'.
   2. Confirm Identity: Match the symbol in the event to your local trade record.
   3. Close the Position:
   * Status: Mark your local position as "Expired".
      * P&L Calculation: Treat this as a "Sell to Close" (STC) transaction with a price of $0.00.
      * Realized Loss: Your realized loss is equal to the total cost basis of the contract (Premium Paid × Multiplier × Contracts).
   
## Distinguishing "Expired Orders" vs. "Expired Positions"
Be careful not to confuse this history event with the Orders API.

* Orders API (status: expired): Tells you that an order (e.g., a Limit Sell) was never filled and was cancelled by the exchange at the end of the day. This does not mean your position expired; it means your attempt to trade it failed.
* History API (option_type: OPTEXP): Tells you the actual contract in your portfolio reached its expiration date and was removed by the clearing house. [1, 2] 


[1] [https://docs.tradier.com](https://docs.tradier.com/docs/trading)
[2] [https://docs.tradier.com](https://docs.tradier.com/docs/history)

