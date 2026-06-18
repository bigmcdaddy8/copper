# Tradier Documentation References

## Documentation Links
https://docs.tradier.com/
https://docs.tradier.com/docs/getting-started
https://docs.tradier.com/reference/brokerage-api-user-get-profile
https://docs.tradier.com/recipes


## API Endpoints
The Tradier API has two environments for our users to utilize. The production environment is for trading and real-time market data related to your live account. The sandbox is a paper trading account to test your integration with our API, including working with delayed market data and paper trades. All Tradier users are issued API tokens for both their live and sandbox accounts, both of which can be retrieved from your account API settings.

Our endpoints require SSL encryption (TLS 1.2) and SNI support. Each endpoint corresponds to a particular product or service. All requests should be made using HTTPS.

### Production Brokerage API (Live)
You must have a Tradier Brokerage account, be a Tradier Partner, or a Tradier Advisor to use these APIs.

#### Production Request/Response
Calls such as those for quotes, account details, or trades will utilize this URL as a base:
https://api.tradier.com/v1/

#### Production Streaming
Streaming live data such as trades, quotes, etc, will utilize this URL:
https://stream.tradier.com/v1/

### Sandbox API
Primarily used for paper trading accounts, you must sign up for a Tradier Brokerage account and create a paper trading access token to use these APIs.

#### Sandbox Request/Response
https://sandbox.tradier.com/v1/

## Rate Limiting
We implement rate limiting to make sure the API is responsive for all customers. The rate limits are set in a way to provide substantial functionality while trying to stifle abuse. Most times, a rate limit can be subverted by implementing a different API call or leveraging other API features (i.e. instead of polling for quotes, leverage the streaming API).

### How Rate Limits Work
Two pieces of information to understand as it pertains to our limits:

- Interval: we aggregate limits over 1-minute intervals starting with the first request and reset 1 minute late
- Limit: this can vary as outlined below, but we keep ours to 60 - 120 requests
  
For example: With a rate limit of 120 requests per minute, if you make a /quotes request every second for a minute, you would still have 60 requests left in that minute before hitting the limit.

#### Should you be concerned about rate-limits?
Probably not. Polling for data, while not the best solution, is reasonably supported by our APIs. The limits exist with enough headroom to get up-to-date data and still have room to make other requests. The best way to know if your application will hit the limits is to build it and scale back.

### Limits
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

### Headers
With each request that has a rate limit applied a series of headers will be sent in the response. These headers should help you to gauge your usage and when to throttle your application. For example:
```
X-Ratelimit-Allowed: 120
X-Ratelimit-Used: 1
X-Ratelimit-Available: 119
X-Ratelimit-Expiry: 1369168800001
```

## API Test Examples
**sandbox**:
```
curl -s \
  -H "Authorization: Bearer YOUR_SANDBOX_API_KEY" \
  -H "Accept: application/json" \
  "https://sandbox.tradier.com/v1/markets/quotes?symbols=SPY" \
  | python3 -m json.tool
```
**production**:
```
curl -s \
  -H "Authorization: Bearer YOUR_PRODUCTION_API_KEY" \
  -H "Accept: application/json" \
  "https://api.tradier.com/v1/markets/quotes?symbols=SPY" \
  | python3 -m json.tool
```


