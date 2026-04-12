# Broker Interface Contract — MVP Specification

## Purpose

Define a minimal, stable interface that decouples the trading engine (**K9**) from any specific brokerage implementation (e.g., Tradier sandbox/production) and from the simulation environment (**Holodeck**).

This contract enables K9 to operate identically across:
- Simulation (Holodeck)
- Sandbox broker
- Production broker

The goal is **portability, testability, and consistency**, not completeness.

---

## Design Principles

1. **Minimal Surface Area (MVP)**
   - Only include methods required for K9 MVP

2. **Deterministic Inputs/Outputs**
   - No hidden state; all responses explicit

3. **Time Abstraction**
   - Broker provides "current time" (real or virtual)

4. **Idempotent Reads, Explicit Writes**
   - Reads do not mutate state
   - Writes return clear results

5. **Broker-Agnostic Models**
   - Normalize data structures across implementations

---

## Core Interface

### Class: `Broker`

All implementations must conform to this interface.

```python
class Broker:
    # --- Time ---
    def get_current_time(self) -> datetime:
        """Return current broker time (real or virtual)."""

    # --- Account ---
    def get_account(self) -> AccountSnapshot:
        """Return account state including balances."""

    def get_positions(self) -> list[Position]:
        """Return all open positions."""

    def get_open_orders(self) -> list[Order]:
        """Return all open orders."""

    # --- Market Data ---
    def get_underlying_quote(self, symbol: str) -> Quote:
        """Return latest quote for underlying."""

    def get_option_chain(self, symbol: str, expiration: date) -> OptionChain:
        """Return option chain for symbol and expiration."""

    # --- Orders ---
    def place_order(self, order: OrderRequest) -> OrderResponse:
        """Submit an order."""

    def cancel_order(self, order_id: str) -> None:
        """Cancel an existing order."""

    def get_order(self, order_id: str) -> Order:
        """Retrieve order status."""
```

---

## Data Models (Normalized)

### AccountSnapshot

```python
@dataclass
class AccountSnapshot:
    account_id: str
    net_liquidation: float
    available_funds: float
    buying_power: float
```

---

### Position

```python
@dataclass
class Position:
    symbol: str
    quantity: int
    avg_price: float
    position_type: str  # e.g., OPTION, STOCK
```

---

### Quote

```python
@dataclass
class Quote:
    symbol: str
    last: float
    bid: float
    ask: float
```

---

### OptionChain

```python
@dataclass
class OptionChain:
    symbol: str
    expiration: date
    options: list[OptionContract]
```

### OptionContract

```python
@dataclass
class OptionContract:
    strike: float
    option_type: str  # CALL or PUT
    bid: float
    ask: float
    delta: float
```

---

### OrderRequest

```python
@dataclass
class OrderRequest:
    symbol: str
    strategy_type: str  # e.g., IRON_CONDOR
    legs: list[OrderLeg]
    quantity: int
    order_type: str  # LIMIT
    limit_price: float
```

### OrderLeg

```python
@dataclass
class OrderLeg:
    action: str  # BUY or SELL
    option_type: str
    strike: float
    expiration: date
```

---

### OrderResponse

```python
@dataclass
class OrderResponse:
    order_id: str
    status: str  # ACCEPTED, REJECTED
```

---

### Order

```python
@dataclass
class Order:
    order_id: str
    status: str  # OPEN, FILLED, CANCELED
    filled_price: float | None
    remaining_quantity: int
```

---

## Behavioral Expectations

### Order Lifecycle

States:
- ACCEPTED → OPEN → FILLED
- ACCEPTED → OPEN → CANCELED

K9 must poll `get_order()` to determine status.

---

### Pricing

- All prices normalized to floats
- Implementations must enforce:
  - valid tick sizes (e.g., 0.05)
  - valid strike increments

---

### Time

- `get_current_time()` is authoritative
- Holodeck returns virtual time
- Real brokers return real time

---

### Error Handling

- Invalid requests return `OrderResponse(status="REJECTED")`
- No exceptions for normal business logic failures

---

## Implementations

### 1. HolodeckBroker
- Synthetic data
- Step-based virtual time
- Deterministic fills

### 2. TradierSandboxBroker
- Wraps Tradier sandbox API
- Real-time behavior

### 3. TradierProductionBroker
- Wraps Tradier production API

---

## MVP Scope Limitations

- No support for:
  - streaming data
  - partial fills (optional later)
  - advanced order types
  - margin calculations beyond basic checks

---

## Future Extensions

- Partial fill modeling
- Greeks exposure
- Multi-account support
- Event-driven callbacks
- Async interface

---

## Summary

The Broker Interface Contract is the foundational abstraction layer that enables:

- Fast local development (Holodeck)
- Safe integration testing (Sandbox)
- Controlled real trading (Production)

By standardizing how K9 interacts with a broker, the system gains flexibility, testability, and long-term scalability.
