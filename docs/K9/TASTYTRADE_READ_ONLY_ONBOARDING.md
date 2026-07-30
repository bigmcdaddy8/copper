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

## Scheduling

After three successful manual production runs on market days, enable the 09:45 CT weekday entry documented in [CRONTAB_K9.md](CRONTAB_K9.md). The shell wrapper invokes only `K9 tastytrade-diagnostic`; it does not call `enter` or `close`.

## Future Trading Gate

Tastytrade order support is intentionally excluded. Before it is designed, confirm that existing production order responses include the custom `source` field and reserve the exact prefix `K9:<environment>:<opaque-run-id>` for automated orders. Any order without that prefix is manual or external and must never be reconciled by K9.