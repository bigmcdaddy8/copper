Mr. Weasel, sir — I think your instinct is right, with one important terminology adjustment: **higher lows, lower highs, breakouts, failed breakouts, etc. are really price-action/market-structure patterns rather than candlestick patterns.** For the futures playbook we're building, I actually think those are **more important** than memorizing 30 named Japanese candlestick formations.

For V1 of Dick's Laboratory, I would teach you a deliberately small vocabulary consisting of three layers:

**market structure → candle behavior → location/context.**

That meshes much better with VWAP, Market Profile/value, and Auction Market Theory than a traditional "spot the Morning Star" approach. CME itself emphasizes that candles are useful for recognizing trend, reversal, and consolidation, while their bodies and wicks reveal buying/selling pressure. [CME Group](https://www.cmegroup.com/education/courses/technical-analysis/chart-types-candlestick-line-bar?utm_source=chatgpt.com)

And this is consistent with the broader Copper project goal of building utilities that support the human trader's trading activity and decision-making. PROJECT_INTENT

# The V1 inventory I would learn

I'd divide the material into **10 concepts**, not dozens of named patterns.

## 1. Candle anatomy — mandatory

Before patterns, become comfortable looking at any candle and immediately seeing:

- Open
- High
- Low
- Close
- Body
- Upper wick/tail
- Lower wick/tail
- Total range

Then begin interpreting the relationship between them.

A large body closing near its high tells a very different story from a large-range candle that closes in the middle. CME describes essentially this same distinction: body size gives information about strength, while the wick/body relationship shows whether control remained with buyers or sellers. [CME Group](https://www.cmegroup.com/education/courses/technical-analysis/chart-types-candlestick-line-bar?utm_source=chatgpt.com)

For example:

```text
Strong bullish candle

      │
      │
    ┌───┐
    │   │
    │   │
    │   │
    └───┘
      │

Open near low
Close near high
Large body
Small wicks
```

versus:

```text
Rejection / indecision

      │
      │
      │
    ┌───┐
    │   │
    └───┘
      │
      │
      │

Large range
Small body
Long wick(s)
```

This is more useful than knowing exotic candle names.

---

# 2. Higher highs + higher lows

This is probably the first **market-structure pattern** I'd have you recognize.

```text
                              HH3
                             /\
                   HH2      /  \
                  /\       /    \
        HH1      /  \     /      \
       /\       /    \   /
      /  \     /      \ /
     /    \   /       HL2
    /      \ /
           HL1
```

A healthy uptrend generally exhibits:

**Higher High → Higher Low → Higher High → Higher Low**

Think:

> Buyers are willing to transact progressively higher.

For our purposes, the **higher low is often more interesting than the higher high**.

Suppose ES is above VWAP, pulls back toward VWAP, rejects it, and produces a higher low.

That becomes much more meaningful than:

> "I saw a hammer."

The context is telling you something about the auction.

---

# 3. Lower highs + lower lows

The inverse:

```text
LH
  \
   \
    \       LH
     \      /\
      \    /  \
       \  /    \
        \/      \
        LL       \
                  LL
```

A bearish trend generally gives you:

**Lower Low → Lower High → Lower Low**

Again, I would pay particular attention to the **lower high**.

For example:

> Price below VWAP → rally toward VWAP → sellers appear → lower high → continuation lower.

That could eventually become one of our basic V1 playbook structures.

---

# 4. Range / balance

Extremely important for Auction Market Theory.

```text
Resistance
────────────────────

   /\    /\     /\
  /  \  /  \   /  \
 /    \/    \_/    \
 \                  /
  \__/\____/\______/

────────────────────
Support
```

Price repeatedly moves between two areas without establishing directional acceptance.

Instead of thinking:

> "The market isn't doing anything."

think:

> **The auction is balanced.**

This distinction will become very important with Market Profile.

You should quickly recognize:

- top of range
- bottom of range
- middle of range
- attempted breakouts
- failed breakouts

---

# 5. Breakout / initiative move

This is one of your examples and absolutely belongs in V1.

```text
Resistance
────────────────────
   /\   /\   /\
  /  \_/  \_/  \
                \
                 \   ← breakout
                  \____
                       \____
```

Or bullish:

```text
                     /
                  __/
               __/
──────────────/──────── resistance
    /\   /\
 __/  \_/  \__
```

But don't merely ask:

> Did price cross the line?

Ask:

> **Did price establish acceptance outside the prior area?**

That's a much more useful futures-trading concept.

A candle poking through a level isn't necessarily a breakout.

---

# 6. Failed breakout / rejection

This one may eventually prove even more valuable than the successful breakout.

```text
                    /\
                   /  \
Resistance ───────/────\──────
             /\  /      \
            /  \/        \
                         ↓
                   back inside
```

Price explores beyond a meaningful level and then returns.

In auction-language terms:

> The market advertised higher prices, but participants rejected them.

Examples we'll eventually care about:

- failed breakout above yesterday's high
- failed breakout below yesterday's low
- failed move outside Value Area
- VWAP rejection
- failed Initial Balance breakout
- failed range breakout

This is one of the patterns I would put a **big star beside**.

---

# 7. Breakout → pullback → continuation

This is another fundamental structure.

```text
                 /
                /
      breakout /
──────────────/────────
             /
            /
              \
               \ ← retest
                \
                 /\
                /  \____
```

Instead of chasing the breakout, the trader observes whether price returns toward the breakout area and finds support.

Bullish sequence:

> resistance breaks → pullback → old resistance becomes support → continuation

Bearish is reversed.

This is probably more valuable for our playbook than half the classical candlestick encyclopedia.

---

# 8. Rejection candle / pin bar

Now we get into actual individual candle formations.

Learn this idea very well.

```text
Bearish rejection

      │
      │
      │
      │
    ┌───┐
    │   │
    └───┘
      │
```

Price traded considerably higher but couldn't remain there.

Conversely:

```text
Bullish rejection

    ┌───┐
    │   │
    └───┘
      │
      │
      │
      │
```

Price traded much lower and buyers drove it back upward.

Traditional names include:

- hammer
- shooting star
- pin bar
- inverted hammer
- hanging man

I don't particularly care whether you memorize all those names.

I want you thinking:

> **Price explored down there and was rejected.**

or:

> **Price explored up there and was rejected.**

Location is crucial.

A long lower wick in the middle of nowhere is mildly interesting.

A long lower wick at:

**VWAP + yesterday's VAH + established higher-low structure**

is a completely different proposition.

---

# 9. Engulfing / displacement candle

This one is worth learning by name.

Bullish example:

```text
Bar 1       Bar 2

 ┌──┐        ┌────┐
 │  │        │    │
 └──┘        │    │
             │    │
             └────┘
```

The second candle overwhelms the first.

The important concept isn't really "engulfing."

It's:

> **A sudden change in directional aggression.**

I'd probably use the term **displacement** in our playbook more often.

For example:

Price probes below VWAP → rejects → suddenly produces a large bullish candle closing near its high.

Something changed.

Engulfing formations are among the traditional patterns covered in candlestick education, but even general candlestick references caution that they should be interpreted along with context rather than in isolation. [Investopedia](https://www.investopedia.com/trading/candlestick-charting-what-is-it/?utm_source=chatgpt.com)

---

# 10. Inside bar / compression → expansion

Very useful.

```text
Mother bar

┌─────────┐
│         │
│  ┌───┐  │
│  │   │  │
│  └───┘  │
│         │
└─────────┘
```

The second candle trades entirely inside the prior candle's range.

This represents **compression**.

More generally, learn to recognize:

```text
Large range
    ↓
 smaller
    ↓
 smaller
    ↓
 smaller
```

followed by:

```text
EXPANSION
─────────────→
```

Markets often alternate:

> balance → imbalance → balance → imbalance.

That concept fits Auction Market Theory beautifully.

---

# The traditional candlestick patterns I would actually memorize

Here's where I'd radically simplify your workload.

For V1, memorize only these names:

| Pattern | What I want you to see |
|---|---|
| **Doji** | Indecision |
| **Hammer / bullish pin** | Rejection of lower prices |
| **Shooting star / bearish pin** | Rejection of higher prices |
| **Bullish engulfing** | Buyers suddenly overwhelm sellers |
| **Bearish engulfing** | Sellers suddenly overwhelm buyers |
| **Inside bar** | Compression / temporary balance |
| **Outside bar** | Range expansion / volatility |
| **Strong trend candle** | Directional control |

That's enough.

I would **not** initially spend time memorizing:

Morning Star, Evening Star, Three White Soldiers, Three Black Crows, Harami Cross, Piercing Line, Dark Cloud Cover, Tweezer Top, Tweezer Bottom, Abandoned Baby, Three Inside Up, Three Outside Down, Rising Three Methods...

Those may be interesting later.

They aren't where I'd invest your learning time now.

---

# Here's the hierarchy I want you eventually thinking in

This is probably the single most important thing in this answer.

Don't analyze charts like:

> There's a hammer. BUY.

Instead:

```text
              MARKET CONTEXT
                    ↓
        Where are we in the auction?
                    ↓
      VWAP / Value / important level?
                    ↓
             MARKET STRUCTURE
                    ↓
         HH/HL? LL/LH? Balance?
                    ↓
               PRICE ACTION
                    ↓
       Breakout? Rejection? Retest?
                    ↓
             CANDLE EVIDENCE
                    ↓
       wick / engulfing / strong close
                    ↓
              TRADE DECISION
```

That is much closer to how I'd like **Dick's Laboratory** eventually to reason.

---

# Here's an example using our eventual futures framework

Imagine `/ES`:

```text
Yesterday VAH
────────────────────────

                   /\

VWAP ─────────────────────────

             \       /
              \     /
               \___/
                 ↑
             higher low
             rejection
```

Suppose price:

1. spends the morning above VWAP,
2. makes a higher high,
3. pulls back,
4. reaches VWAP,
5. briefly trades below VWAP,
6. prints a long lower wick,
7. closes back above VWAP,
8. creates a higher low,
9. next candle strongly closes higher.

The candlestick student says:

> "Hammer followed by bullish engulfing."

Our trader should say:

> **Uptrend structure remained intact. Sellers attempted to auction price below VWAP, failed to gain acceptance, buyers reclaimed VWAP, established a higher low, and then showed initiative buying.**

That's the skill I want you to develop.

The candles are evidence.

They aren't the thesis.

---

# Visual reference

These are reasonable quick visual references for recognizing some of the basic formations:



I wouldn't try to memorize everything shown in a large pattern poster. Use it as a **visual dictionary**, not a trading system.

---

# Where I'd study this

Start with **CME Group's candlestick/chart lesson**. For you, I think this is probably the best first resource because it's explicitly written in the context of futures markets. It explains candle construction, wick/body interpretation, time charts versus tick charts, and using charts to see trends, reversals, and consolidation. [CME Group](https://www.cmegroup.com/education/courses/technical-analysis/chart-types-candlestick-line-bar?utm_source=chatgpt.com)

[CME — Candlestick, Line and Bar Charts](https://www.cmegroup.com/education/courses/technical-analysis/chart-types-candlestick-line-bar?utm_source=chatgpt.com)

Then I would go through CME's short **Technical Analysis** course, but selectively. The pieces I'd prioritize are:

**Chart Types → Trend/Continuation Patterns → Reversals → Support and Resistance.**

You can mostly ignore oscillators for now. [CME Group](https://www.cmegroup.com/education/courses/technical-analysis?utm_source=chatgpt.com)

[CME — Technical Analysis Course](https://www.cmegroup.com/education/courses/technical-analysis?utm_source=chatgpt.com)

Schwab also has a good beginner candlestick lesson specifically addressing how candles behave around **support and resistance**, which is much closer to the way I want you thinking than simply memorizing candle names. [Schwab Brokerage](https://www.schwab.com/learn/story/getting-started-with-technical-analysis-lesson-4?utm_source=chatgpt.com)

[Schwab — Candlestick Basics](https://www.schwab.com/learn/story/getting-started-with-technical-analysis-lesson-4?utm_source=chatgpt.com)

---

# What I would learn first, in order

If you sit down with Thinkorswim and `/ES` or `/MES`, I'd learn this sequence:

1. **OHLC and candle anatomy**
2. **Strong close vs weak close**
3. **Higher highs / higher lows**
4. **Lower highs / lower lows**
5. **Balance/ranges**
6. **Breakouts**
7. **Failed breakouts**
8. **Breakout/retest**
9. **Long-wick rejection**
10. **Engulfing/displacement**
11. **Inside bars/compression**
12. **Put all of the above around VWAP**

Once those become visually automatic, we can layer in:

**VAH / VAL / POC → prior-day high/low → Initial Balance → excess → acceptance/rejection → responsive vs initiative activity.**

That starts turning the candles into an **Auction Market Theory playbook** rather than conventional chart-pattern trading.

### One terminology change I'd make for our project

I also suspect we should stop calling this subject merely **"candlestick patterns."**

For Dick's Laboratory I'd probably define a module or study area called:

> **Price Action & Market Structure**

with candlestick interpretation as one component.

That better describes what we're actually trying to learn.

And I think the **first serious practice exercise** should be surprisingly simple: take several historical `/ES` sessions, hide VWAP/Profile initially, and mark nothing but **HH, HL, LH, LL, balance, breakout, failed breakout, and rejection**. Then turn VWAP and Market Profile back on and see *where* those events happened. That would begin connecting these visual concepts directly to the futures playbook rather than turning this into an abstract candlestick course.


# Higher High Discussion
Mr. Weasel, sir — you are correct. **That ASCII graphic was wrong.** The second point labeled `HH` should have been higher than the first `HH`.

A better picture is:

```text
                         HH2
                        /\
                       /  \
              HH1     /    \
             /\      /      \
            /  \    /        \
           /    \  /
          /      \/
                 HL1
```

The basic idea is:

**HH1 → HL1 → HH2**

where:

- `HH2 > HH1`
- `HL1 > the previous significant low`

And then, if the uptrend continues:

```text
                              HH3
                             /\
                   HH2      /  \
                  /\       /    \
        HH1      /  \     /      \
       /\       /    \   /
      /  \     /      \ /
     /    \   /       HL2
    /      \ /
           HL1
```

So your interpretation is close, but there's an important distinction: after the higher low, you **do not necessarily need every subsequent candle to make a higher high**.

You could see something like:

```text
                    eventual HH
                       /\
          /\    /\    /  \
         /  \  /  \__/    \
        /
       /
      /
     HL
```

Individual candles may move up, down, sideways, make tiny lower highs, etc. What matters is whether the next **meaningful swing high** eventually exceeds the previous meaningful swing high.

That brings us directly to your second observation.

## Yes — there is judgment involved

Price Action & Market Structure is **not purely Boolean logic** like:

```text
if candle.high > previous_candle.high:
    higher_high = True
```

That would technically identify higher highs between individual candles, but it wouldn't capture what traders generally mean by market structure.

We're usually looking for **significant swing points**.

Consider this:

```text
                A
               /\
              /  \_
             /     \__
            /         \ B
           /           /\
          /           /  \
```

Is every little wiggle a swing?

Usually not.

The analyst is mentally filtering out noise and saying something like:

> "That was the meaningful impulse high, this was the meaningful pullback low, and now we're testing whether the next impulse establishes a new high."

That does introduce judgment.

But I would not describe it as completely artistic or arbitrary. I prefer:

> **structured judgment**

There are objective facts underneath it:

- exact candle highs and lows
- how far price moved
- elapsed time
- prior swing levels
- VWAP
- volume
- Value Area
- session high/low
- prior-day levels

The judgment comes from deciding **which movements are significant enough to define structure**.

## A useful analogy

Imagine looking at a mountain range.

You can mathematically identify thousands of little rises and dips:

```text
             /\  /\
       /\   /  \/  \      /\
  /\  /  \_/        \_/\_/  \
_/  \/
```

But if someone asks:

> "Where are the major peaks and valleys?"

you naturally ignore many of the tiny bumps.

Market structure works similarly.

You might simplify that price action into:

```text
                 HH
                /\
               /  \
        HH    /    \
       /\    /      \
      /  \  /
     /    \/
          HL
```

You're extracting the **important structure from noisy data**.

---

## This matters enormously for Dick's Laboratory

One thing I expect us eventually to wrestle with programmatically is:

> **How does software identify the same swing highs and swing lows that a human trader sees?**

There are several ways to formalize it.

For example, an extremely mechanical definition could say:

> A swing high occurs when the high of a candle is greater than the highs of the 2 candles before it and 2 candles after it.

Like:

```text
Candle:

        3
       /\
      /  \
     2    4
    /      \
   1        5
```

Candle `3` becomes a swing high because:

```text
High[3] > High[1]
High[3] > High[2]
High[3] > High[4]
High[3] > High[5]
```

That's deterministic.

But then you encounter this:

```text
               /\
              /  \
       /\    /    \
      /  \__/      \
  /\ /
 /  V
```

A 2-bar pivot algorithm might detect several "swing highs," whereas a human looks at it and says:

> "That's basically one upward leg."

So eventually we may incorporate things such as:

- minimum price movement
- ATR-relative movement
- minimum time between swings
- percentage retracement
- volume
- structural significance
- relationship to VWAP/value

That's a fascinating future Dick's Laboratory problem.

For **your current learning**, however, I'd keep it visual and intuitive.

---

## One more distinction that will help

There are really two meanings of "higher high."

### Candle-level higher high

This candle's high:

```text
105
```

is greater than the previous candle's:

```text
104
```

Technically that's a higher high.

### Structural higher high

A meaningful price leg surpasses the prior significant swing high:

```text
                     HH2 = 105
                    /\
                   /  \
        HH1 = 102 /    \
             /\  /
            /  \/
               HL
```

**This is what I generally mean when talking about HH/HL market structure.**

For our playbook, structural highs/lows matter much more than candle-to-candle comparisons.

---

## And here's an especially important wrinkle

Suppose you get:

```text
        HH1
       /\
      /  \
     /    \
    /      \      LH
   /        \    /\
  /          \  /  \
              \/
              HL
```

The bounce after the HL fails to exceed the previous high.

That is **not another higher high**.

It's now a:

> **Lower High — LH**

And that can be the earliest indication that the bullish structure is weakening.

If price then breaks below the prior HL:

```text
        HH
       /\
      /  \
     /    \        LH
    /      \      /\
   /        \    /  \
            HL  /    \
               /      \
                       \___ LL
```

you now have something substantially different:

> Higher-high/higher-low structure has transitioned toward lower-high/lower-low structure.

That's exactly the sort of market-structure transition I want you learning to see.

---

So I would modify our V1 learning vocabulary slightly:

**Don't learn merely "higher highs and higher lows."**

Learn these four together:

```text
HH = Higher High
HL = Higher Low
LH = Lower High
LL = Lower Low
```

and start asking:

> **What sequence of meaningful swing points is the market producing?**

That question is far more useful than trying to label every candle.

And yes, one of the skills you'll develop is deciding what constitutes a **meaningful swing** versus meaningless noise. Early on it will feel somewhat subjective. As we develop the futures playbook—and especially as we begin encoding this in Dick's Laboratory—we can progressively make that judgment more explicit and measurable.

---

# Higher Highs and Using Judgement
Mr. Weasel, sir — your instinct is right.

For **market structure**, the default is usually to use the **true candle high and low**, meaning the wick extremes, not just the body.

So mechanically:

> **Higher high = current significant swing high exceeds the prior significant swing high, using the actual traded high.**

That means a long upper wick can absolutely create a higher high.

But then the second layer is exactly what you suggested: **interpret what that higher high means.**

A doji with a long upper wick might technically print a higher high, but visually it may be telling you:

> Price explored higher, failed to hold there, and was rejected.

That is very different from a strong bullish candle that breaks the prior high and closes near its own high.

For example:

```text
Previous swing high
────────────────────  5000

                  │
                  │   ← trades to 5005
                ┌─┴─┐
                │   │
                └───┘
```

Technically:

```text
New high = 5005
Previous high = 5000
```

So yes, a **higher high occurred**.

But if that candle closes back at 4995, below the prior high, I would not interpret that as strong bullish confirmation.

I would interpret it more like:

> The market attempted a breakout above 5000, but higher prices were rejected.

That's why I think we should eventually separate two concepts in our V1 vocabulary:

**Structural excursion** and **acceptance/confirmation**.

A wick can establish the excursion:

> "Price traded above the previous swing high."

But the body/close can tell us whether price was accepted there.

Consider these two candles.

### Case A — strong higher high

```text
             ┌─────┐
             │     │
Prior high ──┤     │
             │     │
             └─────┘
```

Price exceeds the previous high and closes strongly above it.

That is good evidence of:

> **HH + acceptance above the old high**

Now compare:

### Case B — wick-only higher high

```text
                │
                │
                │
Prior high ─────┼─────
              ┌─┴─┐
              │   │
              └───┘
```

Price trades above the prior high but closes back below it.

Technically:

> **HH occurred**

But contextually:

> **Failed auction / rejection / possible failed breakout**

Those are not equivalent.

That distinction will be especially valuable once we combine price structure with VWAP and Market Profile.

Suppose ES's previous swing high is 6000.

Price prints:

```text
High:   6004
Open:   5997
Close:  5995
Low:    5993
```

We can truthfully say:

> ES traded to a higher high.

But I would probably describe the event as:

> **Price probed above the prior swing high but failed to gain acceptance and closed back below it.**

That's a much richer observation.

Now compare:

```text
High:   6004
Open:   5997
Close:  6003
Low:    5996
```

Same high.

Very different information:

> **Price broke the prior swing high and closed strongly above it.**

That looks much more like successful initiative activity.

So I wouldn't make the rule:

> "Ignore weird wicks."

I would make it:

> **Always respect the actual high/low because those prices really traded, but use the close/body and subsequent price action to interpret whether the excursion represented acceptance or rejection.**

That is a more disciplined approach than selectively ignoring candles that look unusual.

The doji example is actually a perfect case. A doji with a long upper wick making a new structural high could be summarized as:

> **New high achieved, but strong rejection of the new price area.**

Both things can be true simultaneously.

And this gets at an important principle for the entire playbook:

> **Market structure tells us where price went. Candle structure helps tell us what happened when it got there.**

I think that distinction is worth carrying forward into our V1 design.

---
