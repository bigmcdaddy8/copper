# Master's Plan — Automated Trading System (MVP Architecture)

## Purpose

The "Master’s Plan" defines the high-level architecture, responsibilities, and phased roadmap for building a personal automated trading ecosystem. The system is designed to evolve from a simple, deterministic execution engine into a broader platform capable of signal generation, portfolio management, journaling, reporting, and simulation.

The MVP focuses on **correctness, safety, and iteration speed**, not optimization or completeness.

---

## Core Principles

1. **Separation of Concerns**
   - Execution, journaling, reporting, and simulation are distinct subsystems

2. **Configuration-Driven Behavior**
   - Trade logic defined in JSON, not hardcoded

3. **Deterministic MVP**
   - Minimal variability, no discretionary logic

4. **Safety First**
   - Hard constraints and guardrails before trade execution

5. **Broker Abstraction**
   - K9 operates against an internal broker interface, not directly against any one API

6. **Simulation for Speed, Not Truth**
   - Synthetic environments accelerate development but do not replace real-market validation

---

## System Architecture

### System of Action
Programs that make decisions and execute behavior:
- **K9** — trade execution engine
- (Future) Signal engine
- (Future) Portfolio allocator

### System of Record
Stores authoritative trade lifecycle data:
- **captains_log** — trade journal

### System of Interpretation
Transforms data into insights:
- **encyclopedia_galactica** — reporting and accounting

### System of Simulation
Provides development and testing environments:
- **Holodeck** — simulated broker and market

---

## Core Subsystems

### 1. Broker Interface Contract

Defines the internal API used by all execution systems.

Responsibilities:
- Abstract away differences between production, sandbox, and simulation
- Provide consistent methods for:
  - current time
  - account snapshot
  - positions
  - option chains
  - order placement/cancellation
  - order status

This is a **Python interface/adapter**, not a REST server.

---

### 2. Holodeck (Simulation Broker MVP)

Purpose:
- Provide a fast, deterministic development environment

Characteristics:
- Synthetic SPX minute-level data (e.g., January 2026)
- Deterministic option chain generation
- Strike increments divisible by 5
- Option prices divisible by 0.05
- Simplified pricing logic (not full market realism)

Virtual Time:
- Step-based (discrete increments, e.g., 1-minute per step)
- Advanced explicitly or via polling

Account Simulation:
- Net liquidity
- Positions
- Orders (open/filled/canceled)

Scope Limitations:
- No attempt at full market realism
- No advanced Greeks or volatility surface modeling

---

### 3. K9 (Trade Execution MVP)

Purpose:
- Execute predefined trades from JSON specifications

Scope:
- 0DTE defined-risk trades only
- 1 contract per trade
- No adjustments
- No stop loss
- TP or expiration only

Responsibilities:
- Load trade spec
- Validate constraints
- Check account readiness
- Retrieve market data via broker interface
- Construct trade
- Apply filters
- Place order
- Manage entry fill timeout
- Place TP order if filled
- Emit trade events to journal

Not Responsible For:
- Signal generation (MVP)
- Portfolio optimization
- Reporting

---

### 4. captains_log (Trade Journal MVP)

Purpose:
- Serve as the authoritative system of record for trades

Responsibilities:
- Record trade attempts
- Record fills and cancellations
- Track TP placement
- Record expiration outcomes
- Maintain full trade lifecycle history

- will want a log entry for each trade entry, adjustment, exit grouped by 'Trade #'
- have a "log" text / blob so that trading system can include a description for the trade examples:
  - "Trade Entry #1: SOLD 1x SIC(6740/6750 6850/6860) Q:STRONG BUY BPR:$2500 PoP:75% PRICE:$6800 .20d WINGS:$10 TP:50% @1.50 - $2.64"
  - "TRADE ADJ #1: ROLLED 1x CCS down to 6805/6815 @0.15 - $1.32"
  - "TRADE EXIT #1: Hit GTC TP @-0.75 - $2.64"

Integration:
- K9 writes directly via a journal library (MVP)

---

### 5. encyclopedia_galactica (Reporting & Accounting MVP)

Purpose:
- Transform journal data into usable outputs

Responsibilities:
- Active trade reports
- Completed trade summaries
- Realized P/L summaries
- Basic accounting outputs


Rule:
- Reads from journal, not directly from broker

Reports:
- report data needs a storage backing in order to retain report history and to be able add to cumulative reports

#### Scheduled Reports
- Monthly Account Report
	- a cumulative report that keeps track of the net. liquidity % and $ gain / loss for each month on a per account basis, including the current month
	- summary: show average, median, best, worst monthly % gain/loss and monthly $ gain/loss
- yearly account report
	- yearly version of the monthly data
- total account report
	- total summation of the yearly data
- report data for 'Holodeck' environment is not that important and is complicated because of virtual time
	- either don't support for 'Holodeck' or support data 'reset'

#### Ad Hoc Reports
   - be able to show a trade's change history, CREDITs / DEBITs per change, log journal descriptions, totals
  
---

## Data Flow

1. K9 loads trade spec
2. K9 queries broker interface (Holodeck / Sandbox / Production)
3. K9 executes trade logic
4. K9 writes events to captains_log
5. encyclopedia_galactica reads captains_log for reporting

---

## Roadmap

### Phase 1 — Broker Interface Contract MVP
- Define internal broker API
- Implement basic adapter structure

### Phase 2 — Holodeck MVP
- Synthetic market data generation
- Step-based virtual time
- Basic account/order simulation
- Implements broker interface

### Phase 3 — K9 MVP
- JSON-driven trade execution
- Deterministic 0DTE strategy
- Entry + TP + expiration handling
- Uses Holodeck

### Phase 4 — captains_log MVP
- Trade lifecycle persistence
- Direct integration with K9

### Phase 5 — encyclopedia_galactica MVP
- Reporting and accounting outputs
- Reads from captains_log

### Phase 6 — Sandbox Integration
- Implement Tradier sandbox adapter
- Validate K9 behavior
- Refine Holodeck based on differences

### Phase 7 — Production Promotion
- Implement production adapter
- Controlled rollout

---

## Constraints (MVP)

- Single contract trades only
- DELTA-based strike selection only
- One position per underlying
- Hold to expiration if TP not hit
- No adjustments
- No stop losses

---

## Risks and Mitigations

### Risk: Holodeck scope creep
Mitigation:
- Limit to execution mechanics only

### Risk: Simulation vs real mismatch
Mitigation:
- Sandbox validation phase
- Iterative refinement

### Risk: Overengineering early
Mitigation:
- Strict MVP boundaries

---

## Naming Summary

- Execution Engine: **K9**
- Simulation Environment: **Holodeck**
- Trade Journal: **captains_log**
- Reporting System: **encyclopedia_galactica**
- Architecture: **Master’s Plan**

---

## Summary

The Master’s Plan defines a modular, scalable architecture for automated trading built from the ground up with:

- Clear subsystem boundaries
- Strong abstraction layers
- Simulation-first development
- Controlled progression to real markets

The MVP prioritizes:
- Speed of iteration
- Safety of execution
- Clarity of behavior

Future enhancements will expand capabilities without requiring architectural rewrites.
