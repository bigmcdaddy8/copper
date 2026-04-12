import pytest
from datetime import date, datetime
from zoneinfo import ZoneInfo
from bic.models import OrderLeg, OrderRequest
from holodeck.clock import VirtualClock
from holodeck.config import HolodeckConfig
from holodeck.expiration import ExpirationEngine
from holodeck.ledger import AccountLedger
from holodeck.market_data import MarketDataStore, generate_spx_minutes

TZ = "America/Chicago"
EXP = date(2026, 1, 2)
AT_CLOSE = datetime(2026, 1, 2, 15, 0, tzinfo=ZoneInfo(TZ))
BEFORE_CLOSE = datetime(2026, 1, 2, 14, 59, tzinfo=ZoneInfo(TZ))


@pytest.fixture
def setup(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    config = HolodeckConfig(
        starting_datetime=AT_CLOSE,
        ending_datetime=AT_CLOSE,
        data_path=csv_path,
    )
    clock = VirtualClock(AT_CLOSE, "09:30", "15:00", TZ)
    store = MarketDataStore(csv_path)
    store.load()
    ledger = AccountLedger(config)
    engine = ExpirationEngine(ledger, store, clock)
    return ledger, store, clock, engine, config


def add_pcs_position(ledger, order_id="HD-000001", expiration=EXP):
    """Directly open a PUT credit spread position in the ledger."""
    req = OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 5750.0, expiration),
            OrderLeg("BUY", "PUT", 5745.0, expiration),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=1.00,
    )
    ledger.open_position(order_id, req, 1.00, AT_CLOSE)


def test_run_expiration_no_positions(setup):
    ledger, store, clock, engine, _ = setup
    result = engine.run_expiration()
    assert result == []


def test_run_expiration_otm_profit(setup):
    """SPX at 5842.50 at close — far above 5750 short put. OTM → full credit retained."""
    ledger, store, clock, engine, _ = setup
    initial_bp = ledger.get_snapshot().buying_power
    add_pcs_position(ledger)
    result = engine.run_expiration()
    assert "HD-000001" in result
    # Position should be closed
    assert ledger.get_positions() == []
    # Buying power restored
    assert ledger.get_snapshot().buying_power == pytest.approx(initial_bp, abs=0.01)


def test_run_expiration_itm_loss(setup):
    """Simulate ITM expiry by using strikes above expected close price."""
    ledger, store, clock, engine, config = setup
    # Jan 2 closes at 5842.50. Use a spread ITM at that level: SELL 5900P, BUY 5895P
    req = OrderRequest(
        symbol="SPX",
        strategy_type="PUT_CREDIT_SPREAD",
        legs=[
            OrderLeg("SELL", "PUT", 5900.0, EXP),
            OrderLeg("BUY", "PUT", 5895.0, EXP),
        ],
        quantity=1,
        order_type="LIMIT",
        limit_price=1.00,
    )
    ledger.open_position("HD-000001", req, 1.00, AT_CLOSE)
    initial_nlv = ledger.get_snapshot().net_liquidation
    engine.run_expiration()
    # At 5842.50: SELL 5900P intrinsic = 5900 - 5842.50 = 57.50
    #             BUY 5895P intrinsic = 5895 - 5842.50 = 52.50
    # net_debit = 57.50 - 52.50 = 5.00 → max loss on 5-pt spread
    assert ledger.get_snapshot().net_liquidation < initial_nlv


def test_run_expiration_future_expiry_not_touched(setup):
    """Position with tomorrow's expiration is not expired today."""
    ledger, store, clock, engine, _ = setup
    future_exp = date(2026, 1, 5)
    add_pcs_position(ledger, order_id="HD-000001", expiration=future_exp)
    result = engine.run_expiration()
    assert result == []
    assert len(ledger.get_positions()) == 1  # still open


def test_run_expiration_buying_power_restored(setup):
    ledger, store, clock, engine, _ = setup
    initial_bp = ledger.get_snapshot().buying_power
    # OTM position → should expire worthless and restore bp
    add_pcs_position(ledger)
    engine.run_expiration()
    # Buying power should be restored (minus any P&L adjustment to net liq)
    assert ledger.get_snapshot().buying_power == pytest.approx(initial_bp, abs=0.01)


def test_should_run_false_before_close(tmp_path):
    csv_path = str(tmp_path / "spx.csv")
    generate_spx_minutes(42, csv_path)
    config = HolodeckConfig(
        starting_datetime=BEFORE_CLOSE,
        ending_datetime=AT_CLOSE,
        data_path=csv_path,
    )
    clock = VirtualClock(BEFORE_CLOSE, "09:30", "15:00", TZ)
    store = MarketDataStore(csv_path)
    store.load()
    ledger = AccountLedger(config)
    engine = ExpirationEngine(ledger, store, clock)
    add_pcs_position(ledger)
    assert engine.should_run() is False


def test_should_run_true_at_close(setup):
    ledger, store, clock, engine, _ = setup
    add_pcs_position(ledger)
    # clock is already at AT_CLOSE from fixture
    assert engine.should_run() is True


def test_should_run_false_no_positions(setup):
    ledger, store, clock, engine, _ = setup
    # No positions — should_run returns False even at close
    assert engine.should_run() is False
