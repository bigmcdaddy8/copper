## Plan: K9 First Automated XSP PCS

Implement a safe MVP for first automated XSP 0DTE PCS by extending K9 spec parsing and strike selection (`delta_preferred` + strict `delta_range`), adding full entry retry/cancel-replace support from `entry_order`, adding `exit_type: NONE` behavior, creating a new TRDS trade spec, and scheduling both entry and closure cron jobs. Add an explicit market-open guard (including holiday-safe skip behavior) so cron attempts on closed sessions produce SKIPPED outcomes instead of noisy broker rejections/errors. Use a separate post-close closure command now (not intraday monitor) so captains_log/encyclopedia_galactica receive closure data without introducing a long-running process.

**Steps**
1. Phase 1 — Extend trade spec schema for `delta_preferred` and `exit_type: NONE` (blocking)
1. Update v2 parser/validation in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/config.py` to allow `trade.leg_selection.short_put.delta_preferred` alongside `delta_range` for PCS/SIC short put legs while preserving strict-key behavior for unsupported fields.
1. Update extraction mapping in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/config.py` to carry both `delta_preferred` and `delta_range` into runtime selection inputs instead of only midpoint-derived `short_strike_selection.value`.
1. Extend `ExitConfig` and v2 parsing in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/config.py` so `exit_type` supports `TAKE_PROFIT` and `NONE`; enforce that `NONE` requires no TP placement semantics and does not require TP price values.
1. Keep backward compatibility: existing specs with `TAKE_PROFIT` continue unchanged.

1. Phase 1.5 — Implement entry retry/cancel-replace semantics from spec (depends on Phase 1)
1. Extend config model in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/config.py` so `entry_order.max_entry_attempts` and `entry_order.retry_price_decrement` are persisted in `TradeSpec` (currently parsed but effectively ignored at runtime).
1. Update order execution in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/order.py` and `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/runner.py` to support attempt loops:
1. Attempt 1: submit midpoint LIMIT (existing behavior).
1. Wait/poll up to `max_fill_wait_time_seconds`.
1. If not filled and attempts remain: cancel (or cancel-confirm), decrement entry limit credit by `retry_price_decrement`, and resubmit.
1. Stop retrying when attempts exhausted or next price would violate `min_credit_received`.
1. Return a clear terminal outcome/reason when floor is hit before all attempts.
1. Preserve compatibility with current single-attempt specs (`max_entry_attempts: 1`, `retry_price_decrement: 0.0`).

1. Phase 1.6 — Add explicit market-open/holiday-safe skip (depends on Phase 1)
1. Add broker-agnostic market-session check before order submission in K9 flow (likely in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/runner.py`) so off-session runs return `SKIPPED` with explanatory reason.
1. If BIC lacks required session API, extend `/home/temckee8/Documents/REPOs/copper/apps/bic/src/bic/broker.py` with a minimal `is_market_open`/clock capability and implement it in Tradier/Holodeck brokers.
1. Ensure weekend/holiday cron runs do not attempt entry order placement; they should exit cleanly without broker rejection noise.

1. Phase 2 — Implement strike-selection logic with strict range and ATM tie-break (depends on Phase 1)
1. Add/adjust selector APIs in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/tradier/selector.py` to select short put by:
1. Filtering puts to contracts inside `delta_range`.
1. Choosing smallest absolute distance to `delta_preferred`.
1. On ties, choosing strike nearest ATM using absolute strike distance to underlying last price.
1. If no candidate exists in range, return a deterministic failure (selected policy: fail run/skip-error), not fallback.
1. Update runner usage in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/runner.py` so selector gets underlying last (already fetched as quote), and propagate clear failure reason/category when no in-range candidate exists.
1. Keep current call-side behavior unchanged for this story unless SIC compatibility requires no-op plumbing.

1. Phase 3 — Respect `exit_type: NONE` in execution and journal writes (depends on Phase 1)
1. Update `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/runner.py` so TP order placement is conditional:
1. `TAKE_PROFIT`: current behavior unchanged.
1. `NONE`: skip `build_tp_order`/`place_tp_order`, leave `tp_order_id` empty and `tp_price` null.
1. Update CLI journal mapping in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/cli.py` so `tp_status` is explicit for `NONE` (e.g., `NONE`/`NOT_PLACED`) and avoid emitting GTC event lines when no TP order exists.
1. Ensure captains_log/reader semantics remain valid for active-vs-closed determination with no TP order present.

1. Phase 4 — Add closure automation command for MVP (depends on Phase 3)
1. Add a new K9 command (for example `K9 close`) in `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/cli.py` that:
1. Loads filled/open trades from captains_log journal.
1. Reconciles each trade against broker order/position status.
1. Writes closure updates using `journal.update_tp_fill(...)` or `journal.update_expiration(...)`.
1. Appends EXIT lifecycle events for closed trades.
1. Keep this job idempotent so reruns do not duplicate state transitions/events.
1. If BIC broker contract lacks required read APIs for reliable reconciliation, add the minimum needed method(s) in BIC and implement in Tradier/Holodeck brokers before command logic.

1. Phase 5 — Create new XSP spec and scheduling scripts (depends on Phase 3; cron depends on Phase 4 if closure cron is included)
1. Add new spec file under `/home/temckee8/Documents/REPOs/copper/apps/K9/trade_specs/` with your exact payload, environment `TRDS`, and `exit_type: NONE`.
1. Recommended name: `xsp_pcs_0dte_w2_none_0900_trds.yaml` (or repository naming variant consistent with existing conventions).
1. Add/update script(s) under `/home/temckee8/Documents/REPOs/copper/scripts/` to run:
1. Entry at 09:00 CT weekdays via `uv run K9 enter --trade-spec <new_spec_name>`.
1. Closure reconciliation at post-close buffer time (recommend 15:15 CT weekdays) via `uv run K9 close --account TRDS`.
1. Document crontab lines and PATH requirements (include `$HOME/.local/bin` for `uv`, based on prior cron failures).

1. Phase 6 — Tests, docs, and smoke checks (parallel with Phases 4-5 after core code changes)
1. Extend config tests in `/home/temckee8/Documents/REPOs/copper/apps/K9/tests/test_config.py`:
1. Accept `delta_preferred` in short put leg.
1. Reject malformed/extra keys still under strict mode.
1. Accept `exit_type: NONE`.
1. Ensure `TAKE_PROFIT` behavior remains valid.
1. Extend selector tests in `/home/temckee8/Documents/REPOs/copper/apps/K9/tests/test_selector.py`:
1. In-range preferred delta selection.
1. Tie resolved by nearest ATM.
1. No in-range candidate raises deterministic selection error.
1. Add runner/CLI tests in `/home/temckee8/Documents/REPOs/copper/apps/K9/tests/` for:
1. `exit_type: NONE` skips TP order placement.
1. Journal output for no-TP spec (no GTC event).
1. New close command smoke test path (at least one deterministic closure scenario).
1. Update docs in `/home/temckee8/Documents/REPOs/copper/docs/K9_TRADE_SPEC_CRITERIA_REFERENCE_v2.md` and `/home/temckee8/Documents/REPOs/copper/apps/K9/README.md` for new fields/behaviors and cron recommendations.

**Relevant files**
- `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/config.py` — v2 schema validation, extraction, `ExitConfig`, strict key policy.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/tradier/selector.py` — short put selection algorithm and tie-break logic.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/runner.py` — runtime selection invocation and conditional TP placement.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/cli.py` — entry journaling behavior and new closure command wiring.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/order.py` — polling loop refactor to multi-attempt cancel-replace entry flow.
- `/home/temckee8/Documents/REPOs/copper/apps/bic/src/bic/broker.py` — optional market-session API addition if needed for explicit open-check.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/tradier/broker.py` — market-open implementation detail if BIC session API is added.
- `/home/temckee8/Documents/REPOs/copper/apps/holodeck/src/holodeck/clock.py` — market day/open semantics reference (weekday-only; no holiday calendar).

- `/home/temckee8/Documents/REPOs/copper/apps/captains_log/src/captains_log/journal.py` — closure state update methods reused by K9 close flow.
- `/home/temckee8/Documents/REPOs/copper/apps/encyclopedia_galactica/src/encyclopedia_galactica/reader.py` — confirms closed-trade/reporting semantics consuming `closed_at`/`exit_reason`.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/trade_specs/` — new XSP 0DTE PCS spec file.
- `/home/temckee8/Documents/REPOs/copper/scripts/` — cron-invoked entry/closure scripts.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/tests/test_config.py` — schema/validation tests.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/tests/test_selector.py` — selection and tie-break tests.
- `/home/temckee8/Documents/REPOs/copper/docs/K9_TRADE_SPEC_CRITERIA_REFERENCE_v2.md` — criteria/spec contract update.
- `/home/temckee8/Documents/REPOs/copper/apps/K9/README.md` — user/operator guidance.

**Verification**
1. Run targeted K9 tests: `uv run pytest apps/K9/tests/test_config.py apps/K9/tests/test_selector.py`.
1. Add execution tests for multi-attempt entry behavior: midpoint attempt, cancel, decrement by retry_price_decrement, floor at min_credit_received, and max attempts termination.
1. Add market-closed behavior tests: run outside session/weekend/holiday-like no-chain condition should return `SKIPPED` (not `ERROR`/`REJECTED`) before order placement.

1. Run runner/CLI tests including `exit_type: NONE` and closure command scenarios.
1. Run K9 smoke command with new spec in dry-run mode: `uv run K9 enter --trade-spec <new_spec_name> --dry-run`.
1. Run K9 closure smoke command against a controlled account DB fixture: `uv run K9 close --account TRDS` and verify updated fields (`closed_at`, `exit_reason`, `realized_pnl`) plus EXIT events in captains_log.
1. Validate report pipeline reads closed trades: run encyclopedia_galactica report command/test verifying closed trade appears with non-null closure fields.
1. Validate cron scripts manually in shell before installing crontab, then verify crontab entries execute at 09:00 CT and post-close time.

**Decisions**
- Included now:
- Add `delta_preferred` for short put with strict in-range filtering and ATM tie-break.
- Add `exit_type: NONE` support.
- Implement entry retry/cancel-replace from `entry_order` (`max_entry_attempts`, `retry_price_decrement`, `min_credit_received` floor).
- Add explicit market-open guard so off-session/holiday cron runs are skipped cleanly.

- Create new TRDS XSP 0DTE PCS spec scheduled at 09:00 CT.
- Add separate closure automation job (no intraday monitor in this phase).
- Excluded/deferred:
- Real-time intraday TP monitoring loop/process.
- Manual close auto-detection and advanced reconciliation beyond MVP idempotent daily run.

**Further Considerations**
1. Decide exact post-close cron time buffer for closure job based on observed Tradier sandbox expiry lag; recommendation is start at 15:15 CT and adjust after one week of observations.
1. Decide whether `exit_order` schema for `NONE` should still permit `order_type/time_in_force/exit_price` keys (ignored) or require they be omitted to enforce clean specs; recommendation is enforce omission for clarity.
1. Decide whether to add `delta_preferred` for short_call symmetry now or explicitly defer; recommendation is defer for this first PCS-only trade to reduce blast radius.