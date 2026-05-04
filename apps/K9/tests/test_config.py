"""Tests for TradeSpec loading and validation (K9-0010)."""
from __future__ import annotations

from pathlib import Path

import pytest

from K9.config import TradeSpec


@pytest.fixture
def valid_spec_path(tmp_path) -> Path:
    path = tmp_path / "test_spec.yaml"
    path.write_text(
        """
enabled: true
environment: holodeck
underlying: SPX
trade_type: IRON_CONDOR
wing_size: 5
short_strike_selection:
  method: DELTA
  value: 20
position_size:
  mode: fixed_contracts
  contracts: 1
account_minimum: 5000
max_risk_per_trade: 500
minimum_net_credit: 0.30
max_combo_bid_ask_width: 0.50
entry:
  order_type: LIMIT
  limit_price_strategy: MID
  max_fill_time_seconds: 120
exit:
  take_profit_percent: 34
  expiration_day_exit_mode: HOLD_TO_EXPIRATION
constraints:
  max_entries_per_day: 1
  one_position_per_underlying: true
notes: test spec
""".strip()
    )
    return path


def test_load_valid_spec(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    assert spec.underlying == "SPX"
    assert spec.trade_type == "IRON_CONDOR"
    assert spec.environment == "holodeck"
    assert spec.wing_size == 5
    assert spec.entry.max_fill_time_seconds == 120
    assert spec.exit.take_profit_percent == 34
    assert spec.constraints.one_position_per_underlying is True


def test_from_file_rejects_json_extension(tmp_path):
  json_path = tmp_path / "legacy.json"
  json_path.write_text("{}")
  with pytest.raises(ValueError, match="no longer supported"):
    TradeSpec.from_file(json_path)


def test_validate_passes_for_valid_spec(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    spec.validate()


def test_validate_allows_non_index_underlying(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    spec.underlying = "AAPL"
    spec.validate()


def test_validate_rejects_empty_underlying(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    spec.underlying = ""
    with pytest.raises(ValueError, match="underlying must be non-empty"):
        spec.validate()


def test_validate_rejects_invalid_environment(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    spec.environment = "paper"
    with pytest.raises(ValueError, match="Invalid environment"):
        spec.validate()


def test_validate_rejects_multi_contract(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    spec.position_size.contracts = 5
    with pytest.raises(ValueError, match="1 contract"):
        spec.validate()


def test_validate_rejects_non_delta_selection(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    spec.short_strike_selection.method = "IV_RANK"
    with pytest.raises(ValueError, match="DELTA"):
        spec.validate()


def test_default_entry_window(valid_spec_path):
    spec = TradeSpec.from_file(valid_spec_path)
    assert spec.allowed_entry_after == "09:25"
    assert spec.allowed_entry_before == "14:30"


def test_load_v2_yaml_spec(tmp_path):
    path = tmp_path / "v2_spec.yaml"
    path.write_text(
        """
schema_version: 2
enabled: true
environment: HD
underlying: SPX

trade:
  option_strategy: SIC
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 1
    entry_price: MIDPOINT
    retry_price_decrement: 0.0
    min_credit_received: 0.30
  leg_selection:
    short_put:
      delta_range:
        min: -0.25
        max: -0.15
    short_call:
      delta_range:
        min: 0.15
        max: 0.25
    long_put:
      wing_distance_points: 5
    long_call:
      wing_distance_points: 5
  exit_order:
    exit_type: TAKE_PROFIT
    order_type: LIMIT
    time_in_force: GTC
    exit_price:
      type: PERCENT_OF_INITIAL_CREDIT
      value: 34
""".strip()
    )

    spec = TradeSpec.from_file(path)
    spec.validate()

    assert spec.environment == "holodeck"
    assert spec.trade_type == "IRON_CONDOR"
    assert spec.wing_size == 5
    assert spec.short_strike_selection.value == 20.0
    assert spec.minimum_net_credit == 0.30


def test_v2_retry_decrement_now_accepted(tmp_path):
    """retry_price_decrement was previously rejected; now it is parsed and accepted."""
    path = tmp_path / "retry_v2.yaml"
    path.write_text(
        """
enabled: true
environment: HD
underlying: SPX
trade:
  option_strategy: PCS
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    entry_price: MIDPOINT
    max_fill_wait_time_seconds: 120
    retry_price_decrement: 0.05
    min_credit_received: 0.30
  leg_selection:
    short_put:
      delta_range:
        min: -0.25
        max: -0.15
    long_put:
      wing_distance_points: 5
  exit_order:
    exit_type: TAKE_PROFIT
    order_type: LIMIT
    time_in_force: GTC
    exit_price:
      type: PERCENT_OF_INITIAL_CREDIT
      value: 50
""".strip()
    )

    spec = TradeSpec.from_file(path)
    assert spec is not None
    assert spec.entry.retry_price_decrement == 0.05
    assert spec.entry.max_entry_attempts == 1


def test_v2_supports_short_put_delta_preferred(tmp_path):
    path = tmp_path / "preferred_v2.yaml"
    path.write_text(
        """
enabled: true
environment: TRDS
underlying: XSP
trade:
  option_strategy: PCS
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 5
    retry_price_decrement: 0.02
    entry_price: MIDPOINT
    min_credit_received: 0.08
  leg_selection:
    short_put:
      delta_preferred: -0.13
      delta_range:
        min: -0.15
        max: -0.10
    long_put:
      wing_distance_points: 2
  exit_order:
    exit_type: NONE
""".strip()
    )

    spec = TradeSpec.from_file(path)
    assert spec.short_put_selection is not None
    assert spec.short_put_selection.delta_preferred == -0.13
    assert spec.exit.exit_type == "NONE"
    assert spec.exit.take_profit_percent is None


def test_v2_supports_midpoint_plus_offset_and_short_call_preferred(tmp_path):
    path = tmp_path / "sic_offset_v2.yaml"
    path.write_text(
        """
enabled: true
environment: TRDS
underlying: NDX
trade:
  option_strategy: SIC
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 1000
  entry_criteria:
    type: time_window
    allowed_entry_after: "08:55"
    allowed_entry_before: "12:21"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 5
    retry_price_decrement: 0.21
    entry_price: MIDPOINT + 0.25
    min_credit_received: 0.34
  leg_selection:
    short_put:
      delta_preferred: -0.25
      delta_range:
        min: -0.41
        max: -0.13
    long_put:
      wing_distance_points: 5
    short_call:
      delta_preferred: 0.25
      delta_range:
        min: 0.13
        max: 0.41
    long_call:
      wing_distance_points: 5
  exit_order:
    exit_type: NONE
""".strip()
    )

    spec = TradeSpec.from_file(path)
    assert spec.trade_type == "IRON_CONDOR"
    assert spec.entry.limit_price_offset == pytest.approx(0.25)
    assert spec.short_call_selection is not None
    assert spec.short_call_selection.delta_preferred == pytest.approx(0.25)


def test_v2_rejects_invalid_entry_price_expression(tmp_path):
    path = tmp_path / "bad_entry_price_v2.yaml"
    path.write_text(
        """
enabled: true
environment: TRDS
underlying: XSP
trade:
  option_strategy: PCS
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 1
    retry_price_decrement: 0.0
    entry_price: MID + 0.25
    min_credit_received: 0.08
  leg_selection:
    short_put:
      delta_range:
        min: -0.15
        max: -0.10
    long_put:
      wing_distance_points: 2
  exit_order:
    exit_type: NONE
""".strip()
    )

    with pytest.raises(ValueError, match="trade.entry_order.entry_price"):
        TradeSpec.from_file(path)


def test_v2_exit_none_rejects_extra_fields(tmp_path):
    path = tmp_path / "exit_none_bad.yaml"
    path.write_text(
        """
enabled: true
environment: TRDS
underlying: XSP
trade:
  option_strategy: PCS
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 1
    retry_price_decrement: 0.0
    entry_price: MIDPOINT
    min_credit_received: 0.08
  leg_selection:
    short_put:
      delta_range:
        min: -0.15
        max: -0.10
    long_put:
      wing_distance_points: 2
  exit_order:
    exit_type: NONE
    order_type: LIMIT
""".strip()
    )

    with pytest.raises(ValueError, match="trade.exit_order"):
        TradeSpec.from_file(path)


def test_reject_v2_constants_block(tmp_path):
    path = tmp_path / "bad_constants.yaml"
    path.write_text(
        """
schema_version: 2
enabled: true
environment: HD
underlying: SPX
constants:
  max_spread_percent: 5.0
trade:
  option_strategy: PCS
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 1
    retry_price_decrement: 0.0
    entry_price: MIDPOINT
    min_credit_received: 0.30
  leg_selection:
    short_put:
      delta_range:
        min: -0.25
        max: -0.15
    long_put:
      wing_distance_points: 5
  exit_order:
    exit_type: TAKE_PROFIT
    order_type: LIMIT
    time_in_force: GTC
    exit_price:
      type: PERCENT_OF_INITIAL_CREDIT
      value: 50
""".strip()
    )

    with pytest.raises(ValueError, match="root: constants"):
        TradeSpec.from_file(path)


def test_reject_v2_unsupported_leg_field(tmp_path):
    path = tmp_path / "bad_leg_field.yaml"
    path.write_text(
        """
enabled: true
environment: HD
underlying: SPX
trade:
  option_strategy: PCS
  entry_constraints:
    allow_multiple_trades: false
    quantity: 1
    max_entries_per_day: 1
    max_risk_dollars: 500
  entry_criteria:
    type: time_window
    allowed_entry_after: "09:00"
    allowed_entry_before: "14:30"
  entry_order:
    order_type: LIMIT
    time_in_force: DAY
    max_fill_wait_time_seconds: 120
    max_entry_attempts: 1
    retry_price_decrement: 0.0
    entry_price: MIDPOINT
    min_credit_received: 0.30
  leg_selection:
    short_put:
      delta_range:
        min: -0.25
        max: -0.15
      min_open_interest: 10
    long_put:
      wing_distance_points: 5
  exit_order:
    exit_type: TAKE_PROFIT
    order_type: LIMIT
    time_in_force: GTC
    exit_price:
      type: PERCENT_OF_INITIAL_CREDIT
      value: 50
""".strip()
    )

    with pytest.raises(ValueError, match="trade.leg_selection.short_put"):
        TradeSpec.from_file(path)
