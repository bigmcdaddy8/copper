# Tradier Sniffer – MVP Intent

## 1. Purpose

The purpose of `tradier_sniffer` is to validate that the Tradier API can support the core requirements of an automated trading and journaling system. The 'sniffer' portion of the names means that like a dog sniffing an item to determine what he thinks of it, the program will helps us 'sniff' the 'Tradier' API to see if we think we can built an automated trade system using it.

This program is a **proof-of-concept (POC)** and is not intended for production use.

It exists to answer one key question:

> Can we reliably reconstruct and track logical trades (Trade #) using only brokerage API data?

### Reference Documents

@docs/GLOSSARY.md
@docs/TRADIER_DOCUMENTATION.md
@docs/DICK_WEASEL_MJ.md

---

## 2. MVP Success Criteria

The program is considered successful if it can:

1. Detect when a new order is created (entry or adjustment)
2. Detect when an order transitions:
   * pending → filled
   * filled → closed
3. Correctly group multiple option legs into a single logical trade
4. Persist and recover state across program restarts
5. Detect when a GTC TP order closes a trade
6. Reconstruct trade state **after downtime** using only broker data

---

## 3. Core Concept

A **logical trade** (Trade #) is composed of one or more broker orders.

Example:

* Iron Condor = 4 option legs = 4 broker orders
* System must treat this as **1 trade**

The broker:

* does NOT know about Trade #
* only exposes orders and fills

The system must:

* infer relationships
* persist mappings
* reconstruct state

---

## 4. System Responsibilities

The `tradier_sniffer` system will:

### 4.1 Poll Broker Data

* Orders (open + historical)
* Positions
* Account data (minimal for MVP)

### 4.2 Normalize Data

Convert raw API responses into internal structures:

* Order
* Fill
* Position snapshot

### 4.3 Detect Events

Identify changes between polling cycles:

* New order detected
* Order filled
* Order canceled/rejected
* Position closed

### 4.4 Map Orders to Trades

Core logic:

* Group related orders into a Trade #
* Maintain mapping across lifecycle

### 4.5 Persist State

Store:

* trades
* orders
* mappings
* last poll timestamp

Persistence must survive:

* reboot
* crash

### 4.6 Reconciliation (Critical)

On startup:

* reload last known state
* fetch latest broker data
* reconcile differences
* detect missed events

---

## 5. Execution Model

The system will run as a polling loop:

```
while True:
    fetch broker data
    normalize
    compare with previous state
    detect events
    update trade mappings
    persist state
    sleep(interval)
```

Polling interval:

* configurable (default: 60-120 seconds)

---

## 6. Data Model (MVP)

### Trade

* trade_id (internal)
* underlying
* status (open / closed)
* open_date
* close_date

### Order

* order_id (broker)
* symbol
* side (buy/sell)
* quantity
* price
* status
* timestamp

### TradeOrderMap

* trade_id
* order_id

### Event Log

* timestamp
* event_type
* details

---

## 7. Key Scenarios to Demonstrate

### Scenario 1 – Entry Fill

* place order
  * The key order entry type is a 'Day STO Limit' order (with 1-4 legs)
* detect fill
* assign Trade #

### Scenario 1.5 – Entry Repricing

* place order
  * The key order entry type is a 'Day STO Limit' order (with 1-4 legs)
* timeout
  * who runs the stop watch brokerage or client program ?  TBD
* Reprice trade by
  * if trade is brokerage timed out - then entry a new repriced trade
  * if client timed out can trade be replaced or does it need to be canceled and reentered ? TBD
* assign Trade #

### Scenario 2 – Multi-leg Trade

* detect multiple orders
* group into one trade

### Scenario 3 – TP Hit While Offline

* stop program
* TP executes
* restart program
* system detects closure correctly

### Scenario 4 – Adjustment

* detect closing + opening orders
* associate with existing trade

---

## 8. Non-Goals (MVP)

* No trade signal generation
* No UI
* No real-time streaming
* No advanced risk calculations
* No integration with MJ spreadsheets

---

## 9. Open Questions (Prioritized)

### Critical for MVP

* Can we retrieve full order history reliably?
* Are order IDs stable and unique?
* How are multi-leg orders represented?

### Secondary

* Streaming vs polling
* Price improvement visibility
* Exchange routing

---

## 10. Technology Stack

* Python 3.13
* CLI-based execution
* Local file or SQLite persistence
* Tradier Sandbox API

---

## 11. Design Philosophy

* Favor **simplicity over completeness**
* Optimize for **observability and debugging**
* Assume **failure and recovery are normal**
* Treat broker as **source of truth**

---

## 12. Future Transition

Successful outcomes from this project will directly inform:

* `K9` automated trading engine
* automated trade journal system
* strategy execution framework

---
