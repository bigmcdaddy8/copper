# tradier_sniffer — Cron Job Follow-up Plan

Created: 2026-04-11 (Saturday).  First cron runs: Monday 2026-04-13.

---

## What is running

Three cron jobs were installed on this machine (`America/Chicago`, CDT):

| Time (CT) | Time (ET) | Script | What it does |
|---|---|---|---|
| 8:45 AM Mon–Fri | 9:45 AM | `scripts/daily_entry.sh` | Places SPX 0DTE SIC entry order via sandbox |
| 3:10 PM Mon–Fri | 4:10 PM | `scripts/expiry_check.sh` | Polls orders/positions for today's 0DTE expiry status |
| 3:15 PM Mon–Fri | 4:15 PM | `scripts/after_hours_check.sh` | Queries SPY/QQQ/SPX quotes after market close |

All scripts live under `apps/tradier_sniffer/scripts/`.  
All output is appended to `apps/tradier_sniffer/logs/edge_cases_YYYY-MM-DD.log`.

**The poll loop is NOT running** (Option C was chosen — no persistent `tradier_sniffer poll` process).  
This means fills are not detected in real time and Trade #s are not auto-assigned.  
That is fine for this phase — the goal is observing sandbox behaviour, not live trade management.

---

## Status as of 2026-04-26

| Date | Event | Result |
|---|---|---|
| 2026-04-12 (Sun) | Pre-flight: `tradier_sniffer discover` | ✅ Pass — account valid, $100k sandbox balance |
| 2026-04-13 (Mon) | Nickel pricing test (manual, 11:28 AM CT) | ✅ EC-1 complete — order accepted at penny price, status `ok` |
| 2026-04-13 (Mon) | All three cron jobs | ❌ Failed — `uv: command not found` |
| 2026-04-14 (Tue) | All three cron jobs | ❌ Failed — same root cause |
| 2026-04-15 (Wed) | Cron PATH fix applied | ✅ Scripts now export `$HOME/.local/bin` before calling `uv` |
| 2026-04-16–22 | `daily_entry.sh` (7 runs) | ❌ Failed — HTTP 400 "number of legs must be > 1" |
| 2026-04-16–22 | `expiry_check.sh` (EC-2, 7 runs) | ⏸ No data — blocked by `daily_entry.sh` failure |
| 2026-04-16–22 | `after_hours_check.sh` (EC-4, 5 trading days) | ✅ EC-4 complete — consistent data, FAQ answered |
| 2026-04-22 | Fix attempt 1: `_post` encoding fix | ⚠️ Necessary but not sufficient — bracket encoding fixed; wrong key format remained |
| 2026-04-23–24 | `daily_entry.sh` (2 runs) | ❌ Still failed — same HTTP 400 error with fix attempt 1 |
| 2026-04-26 | Fix attempt 2: leg key format corrected | ✅ Changed `leg[N][field]` → `field[N]`; added `symbol=SPX` — matches Tradier's documented multileg format |
| 2026-04-27–29 | `daily_entry.sh` (3 runs) | ❌ Still failed — HTTP 400 "Invalid parameter, type: is not valid." |
| 2026-04-29 | Fix attempt 3: multileg `type` field | ✅ Changed `type=limit` → `type=credit/debit/even` (Tradier multileg API only accepts these values, not `limit`); price sent as `abs(price)` |

**EC-1 finding (nickel pricing):** Tradier sandbox accepted a `$0.06` penny-priced Day STO Limit without rejection or rounding. Production behavior may differ — re-test needed when live account is available.

**EC-4 finding (after-hours quotes):** Tested 5 days (Apr 16–22). `has_extended_trade: False`, `has_post_market: False` every day for SPY, QQQ, SPX. Sandbox does not return extended-hours pricing — `last` is frozen at regular-session close.

**Root cause of `daily_entry.sh` failures (Apr 16–26, two separate bugs):**
1. **Bug 1 (Apr 16–22):** `httpx` percent-encodes `[` and `]` when using `data=dict`. Fixed Apr 22 by building form body manually in `_post` using `content=` with `Content-Type: application/x-www-form-urlencoded`.
2. **Bug 2 (Apr 22–24):** Even with literal brackets, the key structure was wrong. Tradier's multileg API requires flat indexed keys: `option_symbol[0]`, `side[0]`, `quantity[0]` — NOT the nested `leg[0][option_symbol]` format that was being sent. Fixed Apr 26 in `tradier_client.py:place_multileg_order`. Also added `symbol=SPX` (underlying) per Tradier's documented API spec.

---

## Sunday pre-flight (before first Monday cron run)

Run these to confirm credentials are valid:

```bash
cd /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer
uv run tradier_sniffer discover
```

Expected: prints account balances and user profile with no errors.  
If it fails: check that `.env` contains valid `TRADIER_SANDBOX_API_KEY` and `TRADIER_SANDBOX_ACCOUNT_ID`.

Optionally print the edge case checklists (no API calls):

```bash
uv run tradier_sniffer demo edge_cases
```

---

## Monday manual step — nickel pricing test

Run once during market hours (any time 9:30 AM – 3:45 PM CT):

```bash
cd /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer
uv run tradier_sniffer demo edge_cases --run nickel_pricing
```

This is the one edge case that cannot be time-triggered by cron — it just needs the market to be open.  Output is appended to the day's log file automatically.

---

## Monday evening review

After 3:15 PM CT (once all three cron jobs have fired), bring two pieces of data to Claude:

**1. The day's log:**
```bash
cat /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer/logs/edge_cases_$(date +%Y-%m-%d).log
```

**2. The local DB status:**
```bash
cd /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer
uv run tradier_sniffer status
```

Ask Claude to:
- Interpret the results from each cron job
- Fill in `**Answer:**` lines in `docs/TRADIER_FAQ.md` for any questions with observable data
- Flag anything unexpected (errors, empty responses, unexpected order statuses)

---

## What to look for in the log

### daily_entry.sh output
- Should print a Rich table showing the 4-leg SIC order ID, expiry date, strikes, and credit
- **If it fails:** "greeks unavailable" → the option chain returned no delta data (sandbox issue or run outside market hours — shouldn't happen at 8:45 AM CT but possible)
- **If it fails:** "No 0DTE expiration found" → SPX had no expiry today (holiday or non-trading day)
- **If it succeeds:** note the order ID and credit for reference

### expiry_check.sh output (EC-2)
Look for these in the findings dict:
- `today_orders_count` — how many of today's SPX options are still visible in orders
- `order_statuses` — are any showing `expired`?
- `today_positions_count` — are any 0DTE positions still open at 3:10 PM CT / 4:10 PM ET?

Fill in the EC-2 checklist in `docs/stories/trade_sniffer/TS-0095.md`:
```
- [ ] get_orders — status changed to 'expired' at: ______
- [ ] Delay from 4:00 PM close to 'expired' status: ______ minutes
```

### after_hours_check.sh output (EC-4)
Look for these in the findings dict:
- `has_extended_trade: True/False` for SPY and QQQ
- Whether `last` changed from the 3:00 PM close price (compare to your broker's after-hours feed)

Fill in the EC-4 checklist in `docs/stories/trade_sniffer/TS-0095.md`.

### nickel_test.sh output (EC-1)
Look for:
- `order_status: ok` → order was accepted (note whether price was rounded)
- `api_error` with `invalid_price` in the message → Tradier rejected the penny price

Fill in the EC-1 checklist in `docs/stories/trade_sniffer/TS-0095.md`.

---

## Ongoing weekly cadence

Once the first week's results are documented, the cron jobs continue running daily.  
On any subsequent evening you can run:

```bash
cat /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer/logs/edge_cases_$(date +%Y-%m-%d).log
```

and ask Claude to update `docs/TRADIER_FAQ.md` with new findings.

---

## If the Tradier sandbox doesn't fill the SIC order

The Tradier sandbox may not auto-fill limit orders.  If after a week the daily_entry.sh
is placing orders that never show `status: filled` in `get_orders`, the sandbox likely
requires a manual fill trigger via the Tradier developer portal web UI or a special
sandbox-only API endpoint.  Raise this with Claude and we'll address it — the reconciliation
and Trade # assignment logic is already in place and will work correctly once fills do occur.

---

## Poll loop — if you decide to enable it later

Three options were discussed.  The simplest (Option A):

```bash
cd /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer
tmux new -s sniffer
uv run tradier_sniffer poll
# Ctrl-B then D to detach; tmux attach -t sniffer to re-attach
```

Running `poll` automatically runs startup reconciliation, which will catch any fills that
occurred while the loop was not running — so you can start the loop at any time and it will
catch up.

---

## Key file locations

| What | Path |
|---|---|
| Cron scripts | `apps/tradier_sniffer/scripts/` |
| Daily logs | `apps/tradier_sniffer/logs/edge_cases_YYYY-MM-DD.log` |
| Local DB | `apps/tradier_sniffer/tradier_sniffer.db` (created on first poll run) |
| Edge case checklists | `docs/stories/trade_sniffer/TS-0095.md` |
| FAQ answers | `docs/TRADIER_FAQ.md` |
| Story board | `docs/TRADE_SNIFFER_STORY_BOARD.md` |
