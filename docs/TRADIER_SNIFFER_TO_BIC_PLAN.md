## Plan: BIC Upgrades from Tradier Lessons

Upgrade BIC from a minimal order interface to a full order-lifecycle contract that can represent Tradier realities (async fills, partial fills, rich rejection reasons, trade tagging, and reconciliation), then wire K9 and captains_log to consume those normalized fields. This keeps broker-specific behavior inside adapters while giving K9 deterministic, broker-agnostic control loops.

**Steps**
1. Phase 1 - Requirements Baseline and Scope Lock
1.1. Consolidate Tradier learnings into explicit BIC requirements using docs and proven code references: status taxonomy, reason codes, async polling, tag-based order-to-trade linkage, startup reconciliation, rate-limit behavior, and multi-leg encoding constraints.
1.2. Define scope boundary: BIC normalizes broker data and transport concerns; K9 owns trading policy decisions (retry/decrement/PDT guardrails); captains_log owns persistence and audit timelines.
1.3. Produce a short mapping table from Tradier raw status values to canonical BIC status values. This mapping is the contract for all brokers.

2. Phase 2 - Evolve BIC Contract (blocking step)
2.1. Extend BIC order models with canonical lifecycle fields.
2.2. Expand order status coverage beyond OPEN/FILLED/CANCELED to include at least PENDING, PARTIALLY_FILLED, REJECTED, EXPIRED, and PENDING_CANCEL.
2.3. Add normalized rejection metadata to order responses (reason code and reason text) and preserve broker-native status text for diagnostics.
2.4. Add broker-agnostic order metadata fields for correlation and lifecycle control (time-in-force and external tag/correlation reference).
2.5. Add a broker read method for reconciliation use cases (fetch by status and/or fetch recent orders), keeping current methods for backward compatibility where possible.
2.6. Update BIC tests for model defaults, schema compatibility, and abstract interface changes.

3. Phase 3 - Implement Contract in Broker Adapters (depends on Phase 2)
3.1. Tradier adapter: map all known Tradier order statuses into canonical BIC statuses; include reason_description and rejection category mapping.
3.2. Tradier adapter: include tags in order reads and writes; pass through time-in-force values for DAY/GTC behavior.
3.3. Tradier adapter: replace static inter-call delay with adaptive throttling behavior aligned to Tradier response headers.
3.4. Tradier adapter: harden multi-leg submit encoding by preserving literal bracket keys in form payloads so legs are parsed reliably.
3.5. Holodeck adapter: implement the expanded BIC status model minimally and deterministically (including synthetic partial/rejected paths where feasible for tests).
3.6. Add/expand adapter tests for status mapping, rejection reason propagation, tag round-trip, and encoding edge cases.

4. Phase 4 - K9 Integration of New BIC Signals (depends on Phase 3)
4.1. Update K9 order polling to handle expanded statuses and branch explicitly for partial fill, pending_cancel, rejected, and expired outcomes.
4.2. Replace generic rejection handling with reason-aware handling wired to TradeSpec policy (max attempts and price decrement), now that BIC can return normalized reasons.
4.3. Enable trade tagging end-to-end: generate trade reference before entry, submit tag on entry and TP orders, and preserve in logs.
4.4. Add startup reconciliation pass before new entries: query broker for recent/open orders, detect missed transitions while offline, and reconcile against local journal state.
4.5. Keep strategy policy in K9 only: BIC provides facts, K9 decides retry, cancel, reprice, or skip.

5. Phase 5 - captains_log Persistence and Audit Enrichment (parallel with late Phase 4)
5.1. Add storage fields or event payload conventions for broker status, rejection reason, and reconciled event markers.
5.2. Ensure journal updates can represent the full lifecycle from entry accepted -> fill/partial/cancel/reject -> TP fill/expiration/manual closure.
5.3. Add event lines that distinguish real-time events from reconciliation-replayed events.

6. Phase 6 - Verification and Rollout (depends on Phases 3-5)
6.1. Unit tests: BIC model/interface tests, Tradier adapter tests, Holodeck adapter tests, K9 order-loop tests, captains_log journal tests.
6.2. Smoke tests: run each CLI app smoke target required by repo conventions, including BIC and K9 smoke coverage for changed behavior.
6.3. Integration simulation: Holodeck run validating transitions and reconciliation replay path.
6.4. Tradier sandbox scenario checks: multi-leg submit, asynchronous fill polling, after-hours GTC acceptance, rejection reason propagation, and restart reconciliation.
6.5. Regression gate: verify no behavior regressions in unchanged strategies and existing specs.

**Relevant files**
- /home/temckee8/Documents/REPOs/copper/apps/bic/src/bic/models.py - expand OrderRequest, OrderResponse, and Order lifecycle fields and statuses.
- /home/temckee8/Documents/REPOs/copper/apps/bic/src/bic/broker.py - extend Broker contract for reconciliation-friendly order reads.
- /home/temckee8/Documents/REPOs/copper/apps/bic/tests/test_models.py - add coverage for new BIC model fields and defaults.
- /home/temckee8/Documents/REPOs/copper/apps/bic/tests/test_broker.py - update abstract method expectations and stub behavior.
- /home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/tradier/broker.py - implement expanded mapping, rejection metadata, tag/time-in-force pass-through, adaptive throttle, and payload encoding hardening.
- /home/temckee8/Documents/REPOs/copper/apps/K9/tests/test_tradier_broker.py - add mapping/reason/tag/encoding/throttle behavior tests.
- /home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/order.py - handle expanded status outcomes and reason-aware retry hooks.
- /home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/engine/runner.py - integrate policy-driven retry loop and startup reconciliation sequence.
- /home/temckee8/Documents/REPOs/copper/apps/K9/src/K9/config.py - enable TradeSpec fields already present for retry behavior.
- /home/temckee8/Documents/REPOs/copper/apps/captains_log/src/captains_log/journal.py - persist enriched lifecycle/reconciliation metadata.
- /home/temckee8/Documents/REPOs/copper/apps/captains_log/tests/test_journal.py - add coverage for enriched lifecycle updates and replay markers.
- /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer/src/tradier_sniffer/tradier_client.py - reference implementation for statuses, rejection reasons, adaptive throttling, tags, and multi-leg encoding.
- /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer/src/tradier_sniffer/reconcile.py - reference implementation for startup replay and reconciled markers.
- /home/temckee8/Documents/REPOs/copper/apps/tradier_sniffer/src/tradier_sniffer/assign.py - reference implementation for tag/proximity order-to-trade mapping.
- /home/temckee8/Documents/REPOs/copper/docs/TRADIER_FAQ.md - source of validated broker behavior and scope decisions.

**Verification**
1. Run targeted tests:
1.1. uv run pytest apps/bic/tests
1.2. uv run pytest apps/K9/tests/test_tradier_broker.py apps/K9/tests/test_runner.py apps/K9/tests/test_smoke.py
1.3. uv run pytest apps/captains_log/tests/test_journal.py apps/captains_log/tests/test_smoke.py
2. Run full workspace regression for touched areas: uv run pytest apps
3. Run lint on touched apps: uv run ruff check apps/bic apps/K9 apps/captains_log
4. Manual sandbox verification checklist:
4.1. Submit one multi-leg order and confirm leg keys parse and order accepted.
4.2. Force at least one rejection path and confirm reason is preserved from broker to K9 result to journal.
4.3. Restart between submission and fill, then confirm reconciliation updates local state without duplicate trade records.
4.4. Place TP GTC after-hours and confirm acceptance plus correct lifecycle state.

**Decisions**
- Included: BIC contract enrichment for order lifecycle, Tradier adapter correctness, K9 consumption of normalized lifecycle and reason data, and captains_log persistence needed for reconciliation/audit.
- Excluded: New alpha/strategy logic, streaming market data, portfolio Greeks analytics, live-production-only behavior guarantees.
- Assumption: Existing Tradier sandbox learnings are authoritative for interface design, while production-only differences remain configurable policy in K9.

**Further Considerations**
1. Canonical status model strictness recommendation:
Option A - keep small canonical set with metadata flags.
Option B - mirror Tradier status granularity in canonical enum (recommended).
Option C - broker-specific status passthrough only.
2. Reconciliation API shape recommendation:
Option A - add a new broker method for recent/status-filtered orders (recommended).
Option B - infer from get_open_orders plus point lookups only.
Option C - keep reconciliation entirely outside BIC.
3. Retry policy ownership recommendation:
Option A - policy in K9 config/runner (recommended).
Option B - policy helper utilities in BIC.
Option C - broker adapter auto-retries.

