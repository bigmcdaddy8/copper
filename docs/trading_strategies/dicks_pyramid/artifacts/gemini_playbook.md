### Phase 1: Start of Day (The Regime Filter)

The goal of this phase is observation. You are waiting for the market to declare its structural intent before committing capital.

* **Observation Window:** Monitor the first 30 to 60 minutes of the Regular Trading Hours (RTH) session to establish the Initial Balance (IB).


* **Key Structural References:** Map the current price action against yesterday's Time Price Opportunity (TPO) profile, specifically the Value Area High (VAH), Value Area Low (VAL), and Volume Point of Control (VPOC).


* **Decision Gate:**
* *Trend Indication:* Price breaks and holds outside the previous day's Value Area, or slices cleanly through the Initial Balance boundaries with strong order flow. → **Activate Pyramiding Playbook.**


* *Range Indication:* Price chops back and forth across the previous day's VPOC or repeatedly rejects at the edges of the Initial Balance. → **Abort Pyramiding (Revert to Mean-Reversion Playbook).**





### Phase 2: The Initial Entry Trigger (Raw Price Action)

Once a Trend regime is identified, wait for a specific, raw price action trigger to initiate the first leg of the trade.

* **Entry Trigger Choices (Select One):**
* *Option A (Conservative):* **Breakout & Pullback.** Wait for price to break the Initial Balance, then enter on the first pullback that successfully tests the breakout line as new support.
* *Option B (Aggressive):* **Momentum Break.** Enter the exact moment price cleanly breaks the IB high/low with accompanying volume.
* *Option C (Value Migration):* **Return to Value Failure.** If price opened inside value but tries to leave and fails, enter when it rotates back through the VPOC.





### Phase 3: Initial Risk & Execution Mechanics

This phase handles the mechanical execution using the Micro E-mini S&P 500 (/MES) to strictly define risk before pyramiding begins.

* **Contract Sizing:** Calculate backwards from the structural invalidation point. The /MES contract multiplier is $5 per index point. If your maximum risk is $150 and your stop is 10 points away ($50 risk per contract), your initial base size is 3 contracts.


* **Initial Stop-Loss Placement Choices (Select One):**
* *Option A (Structural):* Place the stop just below the lowest tail of the entry pullback or outside the Initial Balance.


* *Option B (Volume-Based):* Place the stop tucked directly behind a heavy Volume Point of Control (VPOC) that should act as defense.




* **Order Type:** Submit a One-Cancels-Other (OCO) Bracket Order. **Crucially:** Remove the Take-Profit limit leg entirely. You only submit the Entry and the Stop-Loss.



### Phase 4: The Pyramiding Protocol (Scaling In)

This is where the *Best Loser Wins* psychology takes over. You press the winners while strictly defending the initial risk parameter.

* **The Golden Rule of Adding:** You absolutely never execute an "add" order until the initial Stop-Loss has been moved to breakeven or better. Total open risk must never exceed the initial defined risk (e.g., $150).
* **Add Trigger Choices (Select One):**
* *Option A (Structural Breakouts):* Add 1 or 2 contracts every time the market consolidates and breaks out to a new higher-high.
* *Option B (Pullbacks):* Add contracts exclusively when the market pulls back to a short-term moving average (like a 9 EMA) and prints a bullish rejection tail.


* **Sizing the Adds:** Use a decreasing scale. If your initial entry was 3 contracts, your first add is 2 contracts, and your final add is 1 contract.

### Phase 5: Trade Invalidation & Exits

With no profit targets, the exit is entirely dictated by trailing stops and market exhaustion.

* **Trailing Stop-Loss Mechanics (Select One):**
* *Option A (Breakout & Pullback Method):* Manually drag the Stop-Loss up the Depth of Market (DOM) ladder to rest just below the most recent swing low every time price makes a new higher-high.


* *Option B (ATR Brick Method):* Set an automated trailing stop based on a multiple of the 5-minute Average True Range (e.g., 2.5x ATR). It trails automatically, ignoring structural pivots.


* **Manual Flattening Triggers (Kill Switches):**
* *Price Action Reversal:* Price prints a massive double top, climax volume spike, or heavy rejection tail into a known higher-timeframe resistance level.


* *Time Stop:* The market dies and chops sideways for hours (building a new TPO point of control). The auction has balanced, and the trend edge is gone.


* *Session Close:* The 4:00 PM EST bell approaches. Close all open /MES contracts to avoid massive overnight margin requirement spikes.





If you were to execute this exact playbook tomorrow, which of the two Entry Triggers (Breakout & Pullback vs. Aggressive Momentum Break) feels most aligned with your personal risk tolerance?