# Tastytrade Read-Only Onboarding

K9's Tastytrade integration currently performs account and market-data diagnostics only. It cannot submit, cancel, replace, or dry-run an order.

## One-Time Setup

1. In `my.tastytrade.com`, open **Manage > My Profile > API > OAuth Applications**.
2. Use the existing personal OAuth application. A dedicated `read`-scope application is optional, not required.
3. Create a personal grant and save its refresh token in the local `.env` file. Tastytrade shows the token once.
4. Set these values in `.env`:

```dotenv
TW_APP_NAME=k9-tastytrade-diagnostic
TW_CLIENT_ID=...
TW_CLIENT_SECRET=...
TW_REFRESH_TOKEN=...
TW_ACCOUNT_NUMBER=...
```

The refresh token is exchanged for a new 15-minute access token on each run, so no daily interactive login is needed. Never commit `.env` or copy token values into logs. The existing application may have `read` and `trade` scope: this release remains safe because its code exposes no order, cancellation, replacement, or order-dry-run route.

## Run It

During regular equity-options hours, run:

```bash
uv run K9 tastytrade-diagnostic
```

The default target is production and probes `XSP` and `SPX`. The command verifies OAuth refresh, the configured account, balances, positions, snapshots, same-day orders and trade transactions, nested option chains, synchronous quotes, and fresh DXLink Quote/Greeks events.

Use certification only for authentication and protocol checks:

```bash
uv run K9 tastytrade-diagnostic --environment tastytrade_certification
```

Certification quotes are delayed and it does not provide all production account-history services. It cannot validate production market-data readiness.

Each run writes a redacted result to `logs/K9/tastytrade_diagnostic_*.json`. It records check outcomes, latency, and counts but omits credentials, account numbers, balances, and manual trading details.

## Interactive Option Chain

Use the terminal viewer to inspect one exact expiration. `dte` is a calendar-day offset from the current America/Chicago date, so `--dte 0` requests today's expiration. `--strikes` is the number of strike increments displayed above and below the nearest ATM strike; the default of 13 produces up to 27 rows including ATM. `--refresh-seconds` defaults to 30 and cannot be set below 15.

```bash
uv run K9 tastytrade-chain SPX --dte 0 --strikes 13 --refresh-seconds 30
```

The table renders strikes in ascending order and has a horizontal ATM divider immediately below the highest displayed strike at or below the live underlying price. This also places the divider below a strike when the underlying price lands exactly on it. Bid, ask, and last prices turn green when they rose since the prior refresh and red when they fell. It uses only Tastytrade read endpoints and a short-lived DXLink subscription. A nontrading-day DTE or unavailable expiration prints an error and exits.

## 0DTE Put Scout

During regular market hours, the diagnostic adds one 0DTE put scout per configured underlying. It selects the closest put strike at or below the underlying price and up to 15 lower strikes, then records a compact option-chain view in the diagnostic JSON.

| Report column | DXLink event field | Notes |
|---|---|---|
| `bid` | `Quote.bidPrice` | Current quoted bid. |
| `ask` | `Quote.askPrice` | Current quoted ask. |
| `delta` | `Greeks.delta` | Current provider-supplied option delta. |
| `last_price` | `Trade.price` | Most recent trade price, when a Trade event is published. |
| `open_interest` | `Summary.openInterest` | Open interest, when a Summary event is published. |
| `volatility` | `Greeks.volatility` | Provider-supplied option implied volatility. |

The diagnostic also stores the exact requested DXLink event fields in its `dxlink_field_catalog` check. A `null` value in `last_price` or `open_interest` means the bounded DXLink subscription did not publish that optional field; it does not mean zero and does not fail a healthy Quote/Greeks diagnostic.

## Scheduling

After three successful manual production runs on market days, enable the 09:45 CT weekday entry documented in [CRONTAB_K9.md](CRONTAB_K9.md). The shell wrapper invokes only `K9 tastytrade-diagnostic`; it does not call `enter` or `close`.

## Future Trading Gate

Tastytrade order support is intentionally excluded. Before it is designed, confirm that existing production order responses include the custom `source` field and reserve the exact prefix `K9:<environment>:<opaque-run-id>` for automated orders. Any order without that prefix is manual or external and must never be reconciled by K9.