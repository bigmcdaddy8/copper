"""Tests for trade constructor (K9-0050 / K9-0070)."""
from __future__ import annotations

from datetime import date

import pytest

from bic.models import OptionContract
from K9.config import TradeSpec
from K9.engine.constructor import build_order, build_tp_order, net_credit


@pytest.fixture
def spec(tmp_path) -> TradeSpec:
    p = tmp_path / "spec.yaml"
    p.write_text(
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
""".strip()
    )
    return TradeSpec.from_file(p)


EXP = date(2026, 1, 5)
SP = OptionContract(5800.0, "PUT", 1.20, 1.35, -0.20)
LP = OptionContract(5795.0, "PUT", 0.60, 0.70, -0.10)
SC = OptionContract(5840.0, "CALL", 0.90, 1.05, 0.18)
LC = OptionContract(5845.0, "CALL", 0.45, 0.55, 0.10)


def test_build_order_iron_condor(spec):
    order = build_order(spec, EXP, SP, LP, SC, LC)
    assert order.symbol == "SPX"
    assert order.strategy_type == "IRON_CONDOR"
    assert len(order.legs) == 4
    assert order.quantity == 1
    assert order.limit_price > 0


def test_build_order_legs_actions(spec):
    order = build_order(spec, EXP, SP, LP, SC, LC)
    actions = {(leg.action, leg.option_type) for leg in order.legs}
    assert ("SELL", "PUT") in actions
    assert ("BUY", "PUT") in actions
    assert ("SELL", "CALL") in actions
    assert ("BUY", "CALL") in actions


def test_mid_price_calculation(spec):
    order = build_order(spec, EXP, SP, LP, SC, LC)
    # put spread: bid=1.20-0.70=0.50, ask=1.35-0.60=0.75
    # call spread: bid=0.90-0.55=0.35, ask=1.05-0.45=0.60
    # combo bid=0.85, ask=1.35, mid=1.10
    assert order.limit_price == pytest.approx(1.10, abs=0.01)


def test_net_credit_equals_limit_price(spec):
    order = build_order(spec, EXP, SP, LP, SC, LC)
    assert net_credit(order) == order.limit_price


def test_build_order_put_credit_spread(tmp_path):
    p = tmp_path / "pcs.yaml"
    p.write_text(
        """
enabled: true
environment: holodeck
underlying: SPX
trade_type: PUT_CREDIT_SPREAD
wing_size: 5
short_strike_selection:
  method: DELTA
  value: 20
position_size:
  mode: fixed_contracts
  contracts: 1
account_minimum: 5000
max_risk_per_trade: 500
minimum_net_credit: 0.20
max_combo_bid_ask_width: 0.40
entry:
  order_type: LIMIT
  limit_price_strategy: MID
  max_fill_time_seconds: 120
exit:
  take_profit_percent: 50
  expiration_day_exit_mode: HOLD_TO_EXPIRATION
constraints:
  max_entries_per_day: 1
  one_position_per_underlying: true
""".strip()
    )
    pcs_spec = TradeSpec.from_file(p)
    order = build_order(pcs_spec, EXP, SP, LP, None, None)
    assert len(order.legs) == 2
    assert order.strategy_type == "PUT_CREDIT_SPREAD"


def test_build_tp_order_price(spec):
    entry_order = build_order(spec, EXP, SP, LP, SC, LC)
    entry_order.limit_price = 1.10
    tp_order = build_tp_order(spec, entry_order, filled_price=1.10)
    # 1.10 * (1 - 0.34) = 0.726 -> nearest $0.05 = $0.75
    assert tp_order.limit_price == pytest.approx(0.75, abs=0.01)


def test_build_tp_order_reverses_legs(spec):
    entry_order = build_order(spec, EXP, SP, LP, SC, LC)
    tp_order = build_tp_order(spec, entry_order, filled_price=1.10)
    entry_actions = {(leg.action, leg.option_type) for leg in entry_order.legs}
    tp_actions = {(leg.action, leg.option_type) for leg in tp_order.legs}
    # every entry SELL becomes a BUY and vice versa
    for action, otype in entry_actions:
        reversed_action = "BUY" if action == "SELL" else "SELL"
        assert (reversed_action, otype) in tp_actions
