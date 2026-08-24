# Session And Anchor Model

## Terms

- **Capture interval**: UTC interval in which the Laboratory retained source events.
- **Trading date**: Futures market date assigned by the ordinary CME equity-index schedule, not a UTC date.
- **Session**: A versioned market-time classification derived from a canonical UTC timestamp.
- **Anchor**: A resolved UTC instant from which a cumulative calculation begins.
- **Session VWAP**: VWAP of retained trades selected from a named session. A bounded capture may not cover the full session.
- **Anchored VWAP**: VWAP of retained trades at or after a specific anchor.
- **Developing VWAP**: VWAP through the latest retained trade, before a session/window is complete.

## Policies

`CME_EQUITY_INDEX_GLOBEX` (`CME_EQUITY_INDEX_STANDARD_V1`) uses CME's ordinary ES Globex hours: Sunday 5:00 PM through Friday 4:00 PM America/Chicago, with a daily 4:00-5:00 PM maintenance interval. Sunday evening is assigned to the following futures trading date. The maintenance interval is between active sessions: it is `CLOSED_INTERVAL` with no active `trading_date`. Holiday and early-close overrides are not yet modeled.

`US_CASH_SESSION` (`US_CASH_SESSION_V1`) is a Laboratory analytical convention based on NYSE core hours, 9:30 AM-4:00 PM America/New_York, expressed as 8:30 AM-3:00 PM America/Chicago. It is not an official CME session identifier.

Session membership and anchors are derived from aware UTC timestamps using `America/Chicago`; they do not rewrite captured observations. An unavailable pre-anchor interval is reported by coverage facts, never silently moved to the first available trade.