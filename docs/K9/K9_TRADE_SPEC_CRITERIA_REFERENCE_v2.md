# K9 Trade Spec Criteria Reference v2

This document describes the Phase 2 YAML format currently supported by K9.

Runtime support is YAML-only:
- `K9 enter` accepts `.yaml` / `.yml` trade specs.
- JSON trade specs are not accepted at runtime.

Strict mode is enabled for v2 parsing:
- Unsupported fields are rejected with field-level error messages.
- Unsupported behaviors (repricing loops, advanced liquidity filters, etc.) are rejected.

## Supported YAML Specification (Phase 2)
```yaml
schema_version: 2

enabled: true
environment: HD   # HD, TRDS, TRD
underlying: SPX

# Optional in Phase 2 (defaults shown)
account_minimum: 0.0
max_combo_bid_ask_width: 1000.0
notes: "optional notes"

trade:
  option_strategy: SIC   # SIC, PCS, CCS

  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 1000.00

  entry_criteria:
    type: time_window
    allowed_entry_after: "08:55"
    allowed_entry_before: "09:09"

  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 15
    max_entry_attempts: 5
    entry_price: MIDPOINT
    retry_price_decrement: 0.02
    min_credit_received: 0.50

  leg_selection:
    # SIC requires short_put, short_call, long_put, long_call
    # PCS requires short_put, long_put
    # CCS requires short_call, long_call

    short_put:
      delta_preferred: -0.13
      delta_range:
        min: -0.25
        max: -0.15

    short_call:
      delta_range:
        min: 0.15
        max: 0.25

    long_put:
      wing_distance_points: 5.00

    long_call:
      wing_distance_points: 5.00

  exit_order:
    exit_type: TAKE_PROFIT   # or NONE
    order_type: LIMIT        # required for TAKE_PROFIT
    time_in_force: GTC       # required for TAKE_PROFIT
    exit_price:              # required for TAKE_PROFIT
      type: PERCENT_OF_INITIAL_CREDIT
      value: 34.0
```

## Environment Mapping

K9 normalizes these values:
- HD -> holodeck
- TRDS -> sandbox
- TRD -> production

Legacy values holodeck, sandbox, production are also accepted.

## Strategy Mapping

K9 normalizes these values:
- SIC -> IRON_CONDOR
- PCS -> PUT_CREDIT_SPREAD
- CCS -> CALL_CREDIT_SPREAD

## Supported Entry Behavior

- Entry is submitted as LIMIT at midpoint.
- K9 waits up to `max_fill_wait_time_seconds` per attempt.
- If timed out and attempts remain, K9 cancel-replaces with
  `retry_price_decrement` lower credit.
- K9 stops retrying when attempts are exhausted or next retry would drop below
  `min_credit_received`.

## Currently Unsupported (Rejected in Phase 2)

The following v2-style fields/behaviors are rejected:
- root.constants
- Any unknown extra fields at root, trade, and nested objects
- Any short_call fields beyond delta_range
- Any short_put fields beyond delta_range and delta_preferred
- Any long leg fields beyond wing_distance_points
- Any delta_range keys beyond min and max

These are intentionally deferred to later phases and should not appear in active specs yet.
