"""BIC adapter for the Tastytrade Open API."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from bic.broker import Broker
from bic.models import (
    ORDER_ACTIVE_STATUSES,
    ORDER_STATUS_CANCELED,
    ORDER_STATUS_EXPIRED,
    ORDER_STATUS_FILLED,
    ORDER_STATUS_OPEN,
    ORDER_STATUS_PENDING,
    ORDER_STATUS_PENDING_CANCEL,
    ORDER_STATUS_REJECTED,
    AccountSnapshot,
    BalanceSnapshot,
    OHLCVBar,
    OptionChain,
    OptionContract,
    Order,
    OrderRequest,
    OrderResponse,
    Position,
    Quote,
)

from K9.tastytrade.client import TastytradeClient
from K9.tastytrade.dxlink import DxLinkCollector, DxLinkSnapshot
from K9.tastytrade.settings import TastytradeSettings

_TZ = ZoneInfo("America/Chicago")
_STATUS_MAP = {
    "received": ORDER_STATUS_PENDING,
    "routed": ORDER_STATUS_PENDING,
    "in flight": ORDER_STATUS_PENDING,
    "contingent": ORDER_STATUS_PENDING,
    "live": ORDER_STATUS_OPEN,
    "cancel requested": ORDER_STATUS_PENDING_CANCEL,
    "replace requested": ORDER_STATUS_PENDING_CANCEL,
    "filled": ORDER_STATUS_FILLED,
    "cancelled": ORDER_STATUS_CANCELED,
    "removed": ORDER_STATUS_CANCELED,
    "partially removed": ORDER_STATUS_CANCELED,
    "rejected": ORDER_STATUS_REJECTED,
    "expired": ORDER_STATUS_EXPIRED,
}


class TastytradeBroker(Broker):
    """Map Tastytrade data and orders into the BIC Broker contract."""

    def __init__(
        self,
        settings: TastytradeSettings,
        client: TastytradeClient | None = None,
        dxlink_collector_factory: Callable[[str, str], DxLinkCollector] = DxLinkCollector,
    ) -> None:
        self._settings = settings
        self._client = client or TastytradeClient(settings)
        self._dxlink_collector_factory = dxlink_collector_factory

    def get_current_time(self) -> datetime:
        return datetime.now(tz=_TZ)

    def get_account(self) -> AccountSnapshot:
        balances = self._client.get_balances()
        return AccountSnapshot(
            account_id=self._settings.account_number,
            net_liquidation=_decimal(balances, "net-liquidating-value"),
            available_funds=_decimal(
                balances,
                "cash-available-to-withdraw",
                fallback="available-trading-funds",
            ),
            buying_power=_decimal(
                balances,
                "derivative-buying-power",
                fallback="equity-buying-power",
            ),
        )

    def get_positions(self) -> list[Position]:
        positions: list[Position] = []
        for raw in self._client.get_positions():
            symbol = raw.get("symbol")
            if not isinstance(symbol, str):
                continue
            try:
                quantity = int(float(raw["quantity"]))
                average_price = float(raw["average-open-price"])
            except (KeyError, TypeError, ValueError):
                continue
            if quantity == 0:
                continue
            direction = str(raw.get("quantity-direction", "Long")).lower()
            signed_quantity = -quantity if direction == "short" else quantity
            positions.append(
                Position(
                    symbol=symbol,
                    quantity=signed_quantity,
                    avg_price=average_price,
                    position_type=str(raw.get("instrument-type") or "UNKNOWN").upper(),
                )
            )
        return positions

    def get_open_orders(self) -> list[Order]:
        return [order for order in self.get_orders() if order.status in ORDER_ACTIVE_STATUSES]

    def get_orders(self, statuses: list[str] | None = None) -> list[Order]:
        today = self.get_current_time().date().isoformat()
        orders = [_raw_to_order(raw) for raw in self._client.search_orders(today, today)]
        return orders if statuses is None else [order for order in orders if order.status in statuses]

    def get_underlying_quote(self, symbol: str) -> Quote:
        quote_token = self._client.get_api_quote_token()
        token = quote_token.get("token")
        url = quote_token.get("dxlink-url")
        if not isinstance(token, str) or not isinstance(url, str):
            raise ValueError("Tastytrade API quote-token response was incomplete.")
        streamer_symbol = f".{symbol.upper()}" if symbol.upper() in {"SPX", "XSP"} else symbol.upper()
        snapshot = self._dxlink_collector_factory(url, token).collect_quotes([streamer_symbol])[streamer_symbol]
        if snapshot.bid is None or snapshot.ask is None or snapshot.bid > snapshot.ask:
            raise ValueError(f"DXLink returned an invalid bid/ask for {symbol!r}.")
        if snapshot.quote_received_at is None:
            raise ValueError(f"DXLink did not return a Quote receipt timestamp for {symbol!r}.")
        age_seconds = (datetime.now(tz=timezone.utc) - snapshot.quote_received_at).total_seconds()
        if age_seconds > 60:
            raise ValueError(f"DXLink returned stale Quote data for {symbol!r}: {age_seconds:.1f}s old.")
        last = snapshot.last_price if snapshot.last_price is not None else (snapshot.bid + snapshot.ask) / 2.0
        return Quote(symbol=symbol.upper(), last=last, bid=snapshot.bid, ask=snapshot.ask)

    def get_option_chain(self, symbol: str, expiration: date) -> OptionChain:
        contracts = _chain_contracts(self._client.get_nested_option_chain(symbol), expiration)
        if not contracts:
            return OptionChain(symbol=symbol, expiration=expiration)

        quote_token = self._client.get_api_quote_token()
        token = quote_token.get("token")
        url = quote_token.get("dxlink-url")
        if not isinstance(token, str) or not isinstance(url, str):
            raise ValueError("Tastytrade API quote-token response was incomplete.")
        snapshots = self._dxlink_collector_factory(url, token).collect(
            [contract.streamer_symbol for contract in contracts if contract.streamer_symbol]
        )
        options = [_with_snapshot(contract, snapshots) for contract in contracts]
        return OptionChain(symbol=symbol, expiration=expiration, options=options)

    def get_ohlcv_bars(
        self, symbol: str, start: datetime, end: datetime, resolution: str
    ) -> list[OHLCVBar]:
        raise NotImplementedError("Tastytrade OHLCV support is not enabled in the read-only release.")

    def place_order(self, order: OrderRequest) -> OrderResponse:
        dry_run_response = self.dry_run_order(order)
        if dry_run_response.status != "ACCEPTED":
            return dry_run_response
        payload = _order_payload(order, self._client.get_nested_option_chain(order.symbol))
        response = self._client.submit_order(payload)
        raw_order = response.get("order")
        if not isinstance(raw_order, dict):
            raise ValueError("Tastytrade order response did not contain an order.")
        raw_status = str(raw_order.get("status") or "")
        order_id = str(raw_order.get("id") or "")
        if not order_id:
            raise ValueError("Tastytrade order response did not contain an order id.")
        if raw_status.lower() == "rejected":
            return OrderResponse(
                order_id=order_id,
                status="REJECTED",
                rejection_reason="broker_rejected",
                rejection_text=str(raw_order.get("reject-reason") or "Order rejected."),
            )
        return OrderResponse(order_id=order_id, status="ACCEPTED")

    def dry_run_order(self, order: OrderRequest) -> OrderResponse:
        """Validate an order with Tastytrade without routing it to a venue."""
        payload = _order_payload(order, self._client.get_nested_option_chain(order.symbol))
        dry_run = self._client.dry_run_order(payload)
        warnings = dry_run.get("warnings")
        if not isinstance(warnings, list):
            raise ValueError("Tastytrade order dry-run response did not contain warnings.")
        if warnings:
            return OrderResponse(
                order_id="",
                status="REJECTED",
                rejection_reason="dry_run_warning",
                rejection_text="; ".join(str(warning) for warning in warnings),
            )
        return OrderResponse(order_id="", status="ACCEPTED")

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order(order_id)

    def get_order(self, order_id: str) -> Order:
        return _raw_to_order(self._client.get_order(order_id))

    def get_historical_balances(self, period: str = "WEEK") -> list[BalanceSnapshot]:
        del period
        snapshots: list[BalanceSnapshot] = []
        for raw in self._client.get_balance_snapshots():
            snapshot_date = raw.get("snapshot-date")
            if not isinstance(snapshot_date, str):
                continue
            value = raw.get("net-liquidating-value")
            snapshots.append(
                BalanceSnapshot(date=snapshot_date, value=_float_or_none(value))
            )
        return sorted(snapshots, key=lambda snapshot: snapshot.date)


def _chain_contracts(raw_chains: list[dict], expiration: date) -> list[OptionContract]:
    contracts: list[OptionContract] = []
    for chain in raw_chains:
        expirations = chain.get("expirations")
        if not isinstance(expirations, list):
            continue
        for raw_expiration in expirations:
            if not isinstance(raw_expiration, dict):
                continue
            if raw_expiration.get("expiration-date") != expiration.isoformat():
                continue
            strikes = raw_expiration.get("strikes")
            if not isinstance(strikes, list):
                continue
            for strike in strikes:
                if not isinstance(strike, dict):
                    continue
                strike_price = _float_or_none(strike.get("strike-price"))
                if strike_price is None:
                    continue
                for option_type, symbol_key, streamer_key in (
                    ("CALL", "call", "call-streamer-symbol"),
                    ("PUT", "put", "put-streamer-symbol"),
                ):
                    broker_symbol = strike.get(symbol_key)
                    streamer_symbol = strike.get(streamer_key)
                    if not isinstance(broker_symbol, str) or not isinstance(streamer_symbol, str):
                        continue
                    contracts.append(
                        OptionContract(
                            strike=strike_price,
                            option_type=option_type,
                            bid=0.0,
                            ask=0.0,
                            delta=0.0,
                            broker_symbol=broker_symbol,
                            streamer_symbol=streamer_symbol,
                        )
                    )
    return contracts


def _order_payload(order: OrderRequest, raw_chains: list[dict]) -> dict:
    """Translate a selected K9 multi-leg option order to Tastytrade's order schema."""
    symbols = {
        (contract.option_type, contract.strike): contract.broker_symbol
        for contract in _chain_contracts(raw_chains, order.legs[0].expiration)
    }
    is_closing = order.strategy_type.endswith("_TP")
    legs = []
    for leg in order.legs:
        symbol = symbols.get((leg.option_type, leg.strike))
        if not symbol:
            raise ValueError(
                f"Tastytrade option symbol not found for {leg.option_type} {leg.strike} "
                f"expiring {leg.expiration.isoformat()}."
            )
        action = _tastytrade_leg_action(leg.action, is_closing)
        legs.append(
            {
                "instrument-type": "Equity Option",
                "symbol": symbol,
                "quantity": order.quantity,
                "action": action,
            }
        )
    return {
        "time-in-force": "GTC" if order.duration.lower() == "gtc" else "Day",
        "order-type": "Limit",
        "price": f"{order.limit_price:.2f}",
        "price-effect": "Debit" if is_closing else "Credit",
        "source": f"K9:{order.tag}" if order.tag else "K9",
        "legs": legs,
    }


def _tastytrade_leg_action(action: str, is_closing: bool) -> str:
    if action == "SELL":
        return "Sell to Close" if is_closing else "Sell to Open"
    if action == "BUY":
        return "Buy to Close" if is_closing else "Buy to Open"
    raise ValueError(f"Unsupported K9 order-leg action: {action!r}")


def _with_snapshot(contract: OptionContract, snapshots: dict[str, DxLinkSnapshot]) -> OptionContract:
    if contract.streamer_symbol is None:
        return contract
    snapshot = snapshots.get(contract.streamer_symbol)
    if snapshot is None or not snapshot.is_complete:
        raise ValueError(f"Missing complete DXLink snapshot for {contract.streamer_symbol!r}.")
    if snapshot.bid is None or snapshot.ask is None or snapshot.delta is None:
        raise ValueError(f"Incomplete DXLink fields for {contract.streamer_symbol!r}.")
    return OptionContract(
        strike=contract.strike,
        option_type=contract.option_type,
        bid=snapshot.bid,
        ask=snapshot.ask,
        delta=snapshot.delta,
        broker_symbol=contract.broker_symbol,
        streamer_symbol=contract.streamer_symbol,
    )


def _raw_to_quote(raw: dict) -> Quote:
    bid = _decimal(raw, "bid")
    ask = _decimal(raw, "ask")
    last = _float_or_none(raw.get("last"))
    if last is None:
        last = (bid + ask) / 2.0
    symbol = raw.get("symbol")
    if not isinstance(symbol, str):
        raise ValueError("Tastytrade quote was missing symbol.")
    return Quote(symbol=symbol, last=last, bid=bid, ask=ask)


def _raw_to_order(raw: dict) -> Order:
    raw_status = str(raw.get("status") or "")
    status = _STATUS_MAP.get(raw_status.lower(), ORDER_STATUS_PENDING)
    return Order(
        order_id=str(raw.get("id") or ""),
        status=status,
        filled_price=_order_filled_price(raw),
        remaining_quantity=int(float(raw.get("remaining-quantity") or 0)),
        tag=raw.get("source") if isinstance(raw.get("source"), str) else None,
        raw_status=raw_status,
    )


def _order_filled_price(raw: dict) -> float | None:
    price = raw.get("price")
    return _float_or_none(price) if raw.get("status") == "Filled" else None


def _decimal(raw: dict, key: str, fallback: str | None = None) -> float:
    value = raw.get(key)
    if value is None and fallback is not None:
        value = raw.get(fallback)
    parsed = _float_or_none(value)
    if parsed is None:
        raise ValueError(f"Tastytrade response was missing numeric {key!r}.")
    return parsed


def _float_or_none(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None