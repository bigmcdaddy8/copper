from tradier_sniffer.models import (
    EventLog,
    EventType,
    Order,
    OrderLeg,
    OrderStatus,
    Position,
    Trade,
    TradeOrderMap,
    TradeStatus,
    is_valid_trade_id,
)


def test_order_defaults():
    order = Order(
        order_id="12345",
        account_id="ACC001",
        symbol="SPX",
        class_="option",
        order_type="limit",
        side="sell_to_open",
        quantity=1,
        status=OrderStatus.open,
        duration="day",
    )
    assert order.limit_price is None
    assert order.fill_price is None
    assert order.fill_quantity is None
    assert order.option_symbol is None
    assert order.legs == []
    assert order.tag is None
    assert order.updated_at is None


def test_order_multileg_legs():
    legs = [
        OrderLeg(option_symbol="SPX240119P04500000", side="sell_to_open", quantity=1),
        OrderLeg(option_symbol="SPX240119P04400000", side="buy_to_open", quantity=1),
    ]
    order = Order(
        order_id="99999",
        account_id="ACC001",
        symbol="SPX",
        class_="multileg",
        order_type="limit",
        side="",
        quantity=1,
        status=OrderStatus.pending,
        duration="day",
        legs=legs,
    )
    assert len(order.legs) == 2
    assert order.legs[0].option_symbol == "SPX240119P04500000"
    assert order.legs[1].fill_price is None


def test_position_short():
    pos = Position(
        account_id="ACC001",
        symbol="SPX240119P04500000",
        quantity=-1,
        cost_basis=-150.00,
        date_acquired="2024-01-15",
    )
    assert pos.quantity == -1
    assert pos.cost_basis < 0


def test_trade_id_format_valid():
    assert is_valid_trade_id("TRDS_00001_NPUT") is True
    assert is_valid_trade_id("TRDS_00001_SIC") is True
    assert is_valid_trade_id("TRDS_99999_CCALL") is True
    assert is_valid_trade_id("TRDS_000001_PCS") is True  # more than 5 digits ok


def test_trade_id_format_invalid():
    assert is_valid_trade_id("TRD_00001_NPUT") is False   # wrong prefix
    assert is_valid_trade_id("TRDS_1_NPUT") is False       # too few digits
    assert is_valid_trade_id("TRDS_0001_NPUT") is False    # 4 digits — too few
    assert is_valid_trade_id("") is False
    assert is_valid_trade_id("TRDS_00001_nput") is False   # lowercase TTT


def test_trade_defaults():
    trade = Trade(
        trade_id="TRDS_00001_NPUT",
        trade_type="NPUT",
        underlying="SPX",
        opened_at="2024-01-15T14:30:00Z",
    )
    assert trade.status == TradeStatus.open
    assert trade.closed_at is None
    assert trade.notes is None


def test_trade_order_map_fields():
    mapping = TradeOrderMap(
        trade_id="TRDS_00001_NPUT",
        order_id="12345",
        role="entry",
        mapped_at="2024-01-15T14:30:00Z",
    )
    assert mapping.trade_id == "TRDS_00001_NPUT"
    assert mapping.order_id == "12345"
    assert mapping.role == "entry"
    assert mapping.mapped_at == "2024-01-15T14:30:00Z"


def test_event_log_no_event_id():
    evt = EventLog(
        timestamp="2024-01-15T14:30:00Z",
        event_type=EventType.new_order,
        order_id="12345",
    )
    assert evt.event_id is None
    assert evt.trade_id is None
    assert evt.details == "{}"


def test_order_status_enum():
    assert OrderStatus.filled == "filled"
    assert OrderStatus.canceled == "canceled"
    assert OrderStatus.rejected == "rejected"


def test_event_type_enum():
    assert EventType.new_order == "new_order"
    assert EventType.filled == "filled"
    assert EventType.closed == "closed"
    assert EventType.canceled == "canceled"
