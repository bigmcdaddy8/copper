import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from bic.models import OrderLeg, OrderRequest, Position
from holodeck.config import HolodeckConfig
from holodeck.ledger import AccountLedger

TZ = "America/Chicago"
START = datetime(2026, 1, 2, 9, 30, tzinfo=ZoneInfo(TZ))
EXP = date(2026, 1, 2)


def make_config():
    return HolodeckConfig(
        starting_datetime=START,
        ending_datetime=datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ)),
    )


def make_pcs_order() -> OrderRequest:
    """A simple put credit spread: SELL 5750P, BUY 5745P."""
    return OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 5750.0, EXP),
            OrderLeg("BUY", "PUT", 5745.0, EXP),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=1.00,
    )


def test_initial_snapshot():
    ledger = AccountLedger(make_config())
    snap = ledger.get_snapshot()
    assert snap.account_id == "holodeck-sim"
    assert snap.net_liquidation == 100_000.0
    assert snap.buying_power == 50_000.0


def test_initial_positions_empty():
    ledger = AccountLedger(make_config())
    assert ledger.get_positions() == []


def test_open_position_reduces_buying_power():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    snap = ledger.get_snapshot()
    # wing_size=5, credit=1.00 → max_loss=(500-100)*1 = 400
    assert snap.buying_power == 50_000.0 - 400.0


def test_close_position_releases_buying_power():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    ledger.close_position("HD-000001", 0.50, START)
    snap = ledger.get_snapshot()
    assert snap.buying_power == pytest.approx(50_000.0, abs=0.01)


def test_close_position_pnl_profit():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    initial_nlv = ledger.get_snapshot().net_liquidation
    ledger.close_position("HD-000001", 0.30, START)
    final_nlv = ledger.get_snapshot().net_liquidation
    # PnL = (1.00 - 0.30) * 100 * 1 = $70
    assert final_nlv == pytest.approx(initial_nlv + 70.0, abs=0.01)


def test_close_position_pnl_loss():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    initial_nlv = ledger.get_snapshot().net_liquidation
    ledger.close_position("HD-000001", 3.00, START)
    final_nlv = ledger.get_snapshot().net_liquidation
    # PnL = (1.00 - 3.00) * 100 * 1 = -$200
    assert final_nlv == pytest.approx(initial_nlv - 200.0, abs=0.01)


def test_has_position_for_true():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    assert ledger.has_position_for("SPX") is True


def test_has_position_for_false():
    ledger = AccountLedger(make_config())
    assert ledger.has_position_for("SPX") is False


def test_expire_position_otm_profit():
    """SPX expires at 5800 — far above our 5750 put short. OTM = zero intrinsic."""
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    initial_nlv = ledger.get_snapshot().net_liquidation
    ledger.expire_position("HD-000001", 5800.0, START)
    # exit_debit = 0, full credit retained → PnL = $100
    assert ledger.get_snapshot().net_liquidation == pytest.approx(initial_nlv + 100.0, abs=0.01)


def test_expire_position_itm_loss():
    """SPX expires at 5740 — below both strikes. Net debit = 5pts, PnL = -$400."""
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    initial_nlv = ledger.get_snapshot().net_liquidation
    # SELL 5750P intrinsic = 10, BUY 5745P intrinsic = 5; exit_debit = 5.00
    # PnL = (1.00 - 5.00) * 100 = -$400
    ledger.expire_position("HD-000001", 5740.0, START)
    assert ledger.get_snapshot().net_liquidation < initial_nlv


def test_get_positions_bic_format():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    positions = ledger.get_positions()
    assert len(positions) == 1
    assert isinstance(positions[0], Position)


def test_closed_positions_excluded_from_get_positions():
    ledger = AccountLedger(make_config())
    ledger.open_position("HD-000001", make_pcs_order(), 1.00, START)
    ledger.close_position("HD-000001", 0.30, START)
    assert ledger.get_positions() == []
