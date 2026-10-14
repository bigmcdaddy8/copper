# Dick's Laboratory — AI Tutor UX Proof-of-Concept Plan

**Canonical repository path**

`docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md`

**Status**

APPROVED — Human-approved Product Owner plan, including the Human
amendments of 2026-10-13 (incorporated throughout; summarized in the
Amendment Record at the end of this document).

**Authority**

```text
This committed plan is the canonical product plan for
the AI Tutor UX POC.

ChatGPT memory and conversation history provide continuity,
but the repository document is the authoritative specification.
```

Future changes to this plan are committed and versioned in the repository
rather than relying solely on conversational memory.

---

# 1. Purpose

The Laboratory has invested heavily in deterministic market evidence, historical replay, VWAP/Market Profile analysis, Drysdale setup candidates, quality semantics, and grounded AI tutoring.

The next product risk is no longer primarily:

> Can the Laboratory calculate these facts?

The important product question is now:

> Can we turn those facts into an AI-assisted learning experience that the Human actually finds useful, understandable, responsive, trustworthy, and pleasant enough to use regularly?

We will answer that question **now**, while the four-week `/ES` prospective-validation corpus continues to accumulate independently.

We will not wait until the validation campaign finishes before discovering whether the user interface or tutor interaction needs substantial work.

---

# 2. Parallel Project Tracks

From this point forward, Dick's Laboratory operates two independent tracks.

## Track A — Prospective Market Corpus

Dragon continues collecting the bounded `/ES` campaign:

```text
2026-10-12 through 2026-11-06
```

Rules:

```text
collection continues autonomously

campaign data remains analytically unseen

operational health checks are allowed

Drysdale candidate analysis is prohibited

DRYSDALE_V1 remains frozen

quality policies remain frozen

prospective validation plan remains frozen
```

This track proceeds mostly unattended.

## Track B — AI Tutor UX POC

Active development begins immediately using only already-inspected development datasets.

Initial development corpus:

```text
2026-09-29
2026-09-30
2026-10-01
2026-10-02
```

These dates may be used freely for:

```text
UI development
chart development
replay development
AI tutor interaction
lesson experimentation
UX evaluation
performance work
cost measurement
Human testing
```

Track B must never open the prospective campaign data.

---

# 3. Product Vision

The AI tutor should feel like:

> A historical market replay application with an AI trading instructor.

It should NOT feel like:

> A generic chatbot with a chart sitting beside it.

The Human should be able to select a historical session, move through that market as it unfolded, see the relevant price structure and Laboratory evidence, and interact naturally with an AI instructor that knows only what was knowable at the selected replay time.

The tutor should teach.

It should ask questions.

It should react to the Human's answers.

It should provide hints when requested.

It should explain mistakes.

It should point the Human toward relevant chart evidence.

It should distinguish deterministic facts from Laboratory rules and discretionary judgment.

It should never silently use future information.

---

# 4. Initial User Experience

The primary POC layout is a two-pane browser application.

Conceptually:

```text
+------------------------------------------------------------------+
| ES | Sep 30 2026 | Replay 09:45 CT | < | +5m | +15m | Next      |
+------------------------------------------+-----------------------+
|                                          |                       |
|              MARKET CHART                |       AI TUTOR        |
|                                          |                       |
|   Candles                                |  Tutor question       |
|   Globex VWAP                            |                       |
|   +1σ / -1σ                              |  Human response       |
|   +2σ / -2σ                              |                       |
|   selected references                    |  Tutor feedback       |
|                                          |                       |
|   optional event / setup markers         |  Hint / Explain       |
|                                          |  Show Evidence        |
+------------------------------------------+-----------------------+
| Replay state | lesson state | quality | AI latency | session cost|
+------------------------------------------------------------------+
```

This is a starting point, not a locked visual design.

Human testing will drive substantial iteration.

---

# 5. POC Target User

Initial POC assumptions:

```text
one Human user

desktop/laptop first

Ubuntu robby is the primary workstation

Chrome / Chromium / Firefox browser

keyboard + mouse

no public users

no mobile optimization requirement yet
```

Phone/tablet support may come later.

---

# 6. Instrument Scope — /ES Only

For this Tutor POC:

```text
instrument = /ES
```

The Human is studying and discussing `/ES` in this tool. The POC does NOT
design around:

```text
chart /ES, trade another contract

Micro-vs-Mini mapping

instrument translation

instrument selector
```

Internal reusable code may remain generic where that costs nothing, but no
user-facing multi-instrument workflow is required.

---

# 7. Runtime Architecture

## Initial POC

During the active `/ES` capture campaign:

```text
ROBBy
 ├── Browser frontend
 │
 └── Local Tutor API
      ├── Laboratory Python code
      ├── replay engine
      ├── development SQLite datasets
      ├── deterministic evidence
      └── AI provider adapter
```

The Human opens a normal browser URL such as:

```text
http://localhost:<port>
```

No X Windows.

No remote desktop.

No direct Python interaction by the Human.

No chart calculations implemented separately in JavaScript.

Python/Laboratory remains the source of market truth.

## Target Client/Server Architecture

After the POC proves useful and when it is operationally safe:

```text
ROBBy Browser
      |
      | HTTPS / private network
      v
DRAGON
      |
      +-- Tutor web/API service
      +-- Laboratory replay engine
      +-- historical market datasets
      +-- tutor session store
      |
      +--> AI model provider API
```

The frontend/API contract should be designed from day one so this move requires little or no UX redesign.

---

# 8. Dragon Non-Interference Rule

While the four-week prospective collection campaign is active:

```text
dragon's primary responsibility =
capture production
```

Do not deploy CPU/memory-heavy tutor experimentation onto dragon during the campaign merely to prove remote hosting.

The collector has higher priority.

Initial tutor development runs on robby.

Remote dragon deployment becomes a later explicit phase.

This avoids jeopardizing the prospective dataset while still allowing rapid tutor development.

---

# 9. Recommended Application Stack

Recommended starting architecture:

```text
Backend:
Python
FastAPI
existing Dick's Laboratory packages

Frontend:
React
TypeScript
Vite

Chart:
browser-native financial chart library
capable of candlesticks, line overlays,
markers, zoom, pan and crosshair

Communication:
HTTP API
plus SSE or WebSocket where streaming improves tutor UX
```

The exact chart package should be selected through a narrow implementation spike.

Preference:

```text
do not build a chart renderer ourselves
```

The chart is presentation.

Laboratory Python owns:

```text
bars
VWAP
bands
references
replay state
setup evidence
quality
```

---

# 10. Source Data Rules

The frontend must never query raw production SQLite structures directly.

Desired flow:

```text
SQLite / replay source
        ↓
Laboratory Python
        ↓
typed application API
        ↓
browser
```

This prevents the frontend from creating an independent interpretation of market evidence.

---

# 11. Replay Model

A replay session contains at least:

```text
trading date

market-time cutoff

knowledge-time cutoff

current 5-minute bars

VWAP state

VWAP bands

reference levels

Drysdale state

quality state

lesson state
```

When the Human advances replay:

```text
+5m
+15m
Next Event
```

the server computes a new deterministic snapshot.

The chart and AI tutor must always refer to the same snapshot.

---

# 12. Hard No-Lookahead Rule

The browser must never reveal future market information accidentally.

At replay time T:

```text
chart bars after T:
hidden

future Drysdale candidates:
hidden

future reference interactions:
hidden

future tutor evidence:
hidden
```

The AI receives only the evidence authorized for the current lesson/replay state.

This applies to:

```text
free-form questions
guided lessons
hints
answers
explanations
```

---

# 13. Chart V1

The first useful chart should support:

```text
5-minute candlesticks

zoom

pan

crosshair

price scale

time scale

Globex VWAP

+1σ
-1σ

+2σ
-2σ

replay cutoff marker
```

Then add selected references such as:

```text
IB high / low

overnight high / low

prior day high / low

other relevant references
```

Do not place every Laboratory fact on the chart by default.

Avoid visual clutter.

## Future Indicator Extensibility

The Tutor UX effort is not an excuse to add new market indicators.

**Volume Profile is NOT part of the initial Tutor POC** and is not
implemented as part of 0AC — regardless of whether backend Volume Profile
primitives already exist elsewhere in the Laboratory.

However, the chart/settings architecture should remain capable of
accommodating future indicators. A likely later example is Volume Profile
with:

```text
current-session:
POC
VAH
VAL

prior-day:
POC extended right
VAH extended right
VAL extended right
```

```text
FUTURE / NOT AUTHORIZED BY THIS PLAN
```

Concretely: overlays and reference lines should be delivered to the chart
as typed, named series/levels from the API rather than as one-off
hardcoded chart code, so that a future indicator is an additional series,
not a chart rewrite.

---

# 14. Minimal Settings Architecture

Do not build a full TradingView-style indicator-settings product.

But design the UI/API so basic display/study settings are not hardcoded
permanently.

Initial/future examples:

```text
VWAP anchor:
- Globex session open
- U.S. cash-equity session open

overlay visibility

VWAP line color

VWAP ±1σ region / line colors

VWAP ±2σ region / line colors

IB high/low line color

other reference-line presentation settings
```

## Presentation Settings vs Study-Semantic Settings

Settings fall into two distinct classes:

```text
PRESENTATION settings
  change how evidence looks
  e.g. colors, line styles, overlay visibility
  never change what the evidence means
  never change what the tutor is told

STUDY-SEMANTIC settings
  change what is computed
  e.g. VWAP anchor
  change the evidence itself
  are computed server-side by Laboratory Python
```

Study-semantic settings are parameters of the server-side snapshot, never a
browser-side recalculation. The chart and the tutor always use the same
semantic settings for a given snapshot.

## Lesson-Semantic Locking

```text
A guided curriculum lesson may lock required study semantics.
```

Example: Drysdale lessons use the source-aligned

```text
Globex-anchored VWAP
```

and must not silently change meaning because the Human happened to choose a
different chart setting.

Therefore:

```text
Free-study mode:
  may eventually allow anchor switching

Guided lesson:
  may explicitly lock the anchor (and any other
  study-semantic setting) required by its curriculum;
  locked settings are visibly indicated as locked
  while the lesson is active

Presentation settings:
  remain Human-adjustable in all modes
```

Keep this architecture simple: a small settings object with the two classes
separated, plus a per-lesson list of locked semantic values. No settings
marketplace, study editor, or per-indicator dialog framework.

---

# 15. Chart Evidence Interaction

A later POC milestone should allow tutor evidence to connect visibly to the chart.

Examples:

```text
Tutor:
"Look at the bar that tested +1σ."

Human clicks:
SHOW EVIDENCE

Chart:
highlights that bar and +1σ line
```

Or:

```text
Tutor:
"Acceptance has not been established."

Evidence panel:
1st outside close ✓
2nd consecutive outside close ✗
```

This chart/evidence linkage is expected to be a major contributor to tutor usefulness.

---

# 16. Student Mode

Default learning mode should hide answers that would spoil the exercise.

Possible Student Mode behavior:

```text
candidate name hidden initially

candidate markers hidden

answer state hidden

future bars hidden

tutor asks Human first
```

Example:

```text
Tutor:
Price has just closed above +1σ.

Does that make this a complete
Price Discovery Continuation candidate?
Why or why not?
```

Human answers naturally.

Tutor evaluates the answer against deterministic evidence.

---

# 17. Instructor Mode

Instructor Mode may expose:

```text
candidate family

candidate condition checklist

evidence references

quality reasons

Laboratory policy names

first-known time

supporting context
```

This is useful for:

```text
review
debugging
deeper study
Human verification
```

Student and Instructor modes may eventually be switchable.

---

# 18. Tutor Interaction Modes

The POC should explore at least three interaction styles.

## Guided Lesson

Tutor controls the lesson progression.

Example:

```text
Question
↓
Human answer
↓
Tutor feedback
↓
Hint if needed
↓
advance replay
↓
next question
```

## Free Chat

Human may ask:

```text
What am I looking at?

Why isn't this a PDC setup?

What does acceptance mean here?

Why is VWAP still rising?

What evidence supports this interpretation?
```

## Review Mode

After an event:

```text
What happened?

What clues were available beforehand?

Which Laboratory conditions were satisfied?

Which were missing?

What should I have noticed?
```

The first POC should determine which modes the Human finds genuinely useful.

---

# 19. Existing Tutor Stage Model

Reuse the accepted lesson semantics where practical:

```text
QUESTION

HINT

ANSWER

POST_REVEAL
```

Do not invent a completely separate lesson architecture without reason.

---

# 20. Grounding Architecture

The AI does not independently calculate market truth.

Flow:

```text
market source
     ↓
deterministic Laboratory
     ↓
TutorEvidenceContext
     ↓
AI model
     ↓
structured response
     ↓
grounding validator
     ↓
Human
```

The AI may:

```text
explain
teach
ask questions
compare evidence
discuss uncertainty
help the Human reason
```

The AI may not silently invent:

```text
prices
VWAP levels
setup conditions
candidate states
quality status
future events
```

---

# 21. Evidence Categories

Tutor responses should continue distinguishing concepts such as:

```text
OBSERVED

DERIVED

POLICY

CANDIDATE

QUALITY

CURRICULUM

AI_INTERPRETATION
```

The UX does not need to show those technical labels constantly.

However:

```text
SHOW EVIDENCE
```

should make provenance inspectable.

---

# 22. Discretionary Judgment

Long-term Drysdale learning requires judgment.

The tutor therefore should not merely turn discretionary concepts into fake deterministic rules.

Preferred progression:

```text
Level 1:
What do the deterministic facts say?

Level 2:
What contextual evidence would Drysdale consider?

Level 3:
What is YOUR interpretation?

Level 4:
Tutor discusses that interpretation.
```

The Human should gradually learn to make the judgment rather than outsourcing all judgment to the model.

---

# 23. Trade-Setup and Potential-Entry Discussion

The tutor's focus is:

```text
identify potential trade setups
understand setup conditions
observe context
apply discretionary judgment
recognize when a setup becomes valid
recognize potential entry locations associated with that setup
```

A valid Tutor discussion may be:

```text
"This bar completed the Laboratory conditions for Setup XYZ.

Under this training framework, that creates a potential
entry location associated with the setup.

What evidence supports or weakens taking that setup?"
```

That is within scope.

## Risk Management Is Outside Tutor Scope

The tutor does NOT provide curriculum or advice involving:

```text
account size
risk percentage
contract sizing
number of contracts
portfolio exposure
maximum daily loss
risk budget
stop-loss dollar budgeting
capital allocation
```

A discussion such as:

```text
"You have $150,000, therefore trade N contracts
with a 20-tick stop."
```

is outside scope.

No risk-management machinery is added to the POC.

---

# 24. Tutor Personality / Teaching Style

Initial target:

```text
concise
curious
evidence-based
patient
non-dogmatic
interactive
```

Avoid:

```text
long lectures after every answer

unnecessary praise

pretending uncertainty does not exist

immediately revealing the answer
```

Prefer:

```text
one question at a time

short feedback

specific chart evidence

follow-up reasoning questions
```

Human feedback will tune this heavily.

---

# 25. AI Provider Architecture

Do not permanently bind the product to one AI provider.

Define a provider boundary conceptually like:

```text
TutorModelProvider
    |
    +-- Anthropic
    +-- OpenAI
    +-- development fake
    +-- possibly other providers later
```

Provider choice is infrastructure.

Grounding semantics belong to the Laboratory.

---

# 26. Model Integration Sequence

Do not spend tokens while building basic UI mechanics.

Recommended progression:

```text
1. Fake / deterministic tutor provider
   for frontend development

2. Existing grounded AI pipeline
   for end-to-end proof

3. Direct model API provider
   for production-like interaction

4. Compare model quality / latency / cost later
```

The development fake should allow the UI to be tested at zero model cost.

---

# 27. Claude Code

Claude Code / `claude -p` has already proven useful for development and earlier model-connected tutor experiments.

It may remain available as a development adapter.

It should not become a required permanent runtime dependency for the finished tutor.

The product should ultimately communicate with model providers through an application-appropriate API/provider abstraction.

---

# 28. Token and Cost Instrumentation

Cost must be visible from the beginning of real-model interaction.

Record every AI turn:

```text
provider

model

prompt version

input tokens

output tokens

cached tokens if applicable

latency

repair attempt count

evidence payload size

estimated dollar cost

session cumulative tokens

session cumulative cost
```

Store raw usage numbers even if provider pricing changes later.

Cost estimation should use a versioned pricing configuration.

---

# 29. Cost UX

During POC testing the Human should be able to inspect something like:

```text
AI response latency: 4.8 sec

Input: 4,230 tokens
Output: 512 tokens

Turn cost: $0.xx
Session cost: $0.xx
```

This need not occupy permanent screen space later.

During development it is important evidence.

---

# 30. Cost Optimization Strategy

Do not send an entire day's evidence to the model on every turn.

Preferred payload:

```text
current snapshot

relevant recent bars

relevant Drysdale evidence

relevant quality state

lesson state

compact conversation context

Human's current message
```

The deterministic server should decide what evidence is relevant before invoking the model.

Later optimization may include:

```text
conversation summarization

prompt caching

smaller routine model

larger model only for complex interpretation
```

But first measure actual behavior.

---

# 31. Tutor Session Persistence

Tutor history should be separate from source market data.

A POC session store should eventually capture:

```text
session id

development trading date

replay positions visited

Human messages

tutor responses

lesson stages

evidence hashes

provider/model

token usage

latency

estimated cost

grounding validation result
```

Do not modify the authentic source dataset.

---

# 32. Human Feedback Persistence

We should explicitly collect UX feedback.

After a study session, optionally ask:

```text
Was this useful?

Was the tutor too verbose?

Was the chart understandable?

Did you trust the explanation?

Was the pacing right?

Was the chart cluttered?

Would you use this again?

What annoyed you?
```

A small 1–5 scale plus free text is sufficient.

This feedback becomes product evidence.

---

# 33. POC Success Question

The most important acceptance question is:

> After using the prototype, does the Human want to use it again to learn futures trading?

Technical correctness is necessary but insufficient.

---

# 34. Initial UX Success Criteria

A useful POC should eventually demonstrate:

```text
Human can launch the application without programming interaction

Human can choose an approved development date

Human can see a usable 5-minute chart

Human can move the replay clock

chart and tutor remain synchronized

Human can ask free-form questions

tutor can ask Human questions

tutor can provide a hint

tutor can explain a wrong answer

tutor can show supporting evidence

future information does not leak

model responses pass grounding validation

cost and latency are measured

Human completes at least one meaningful lesson session
```

---

# 35. Non-Goals for the Initial POC

Do NOT initially build:

```text
broker order entry

live trading

trade execution recommendations
(discussing a setup's potential entry location
 as a training concept remains in scope)

position sizing

risk management of any kind
(account size, risk %, contract count,
 stop-loss dollar budgeting, daily loss limits,
 capital allocation)

automated entries

automated exits

PnL optimization

multi-user accounts

public Internet hosting

mobile application

perfect visual design

all futures instruments
(the POC is /ES only; no instrument selector,
 Micro/Mini mapping or instrument translation)

all trading playbook modules

new market indicators
(e.g. Volume Profile — future, not authorized)

full indicator-settings product
(only the minimal settings architecture)
```

We are proving the learning interaction.

---

# 36. Development Milestone 0AC-A1 — Application Shell + Chart

Goal:

> The Human can open a browser and replay an approved historical session visually.

Deliver:

```text
browser application shell

date selector

one development date initially

5-minute /ES candles

Globex VWAP

±1σ

±2σ

overlay colors/visibility read from the minimal
settings object rather than hardcoded

replay cutoff

+5m control

previous/next controls

no future bars shown

basic responsive two-pane layout
```

Tutor pane may initially be a placeholder.

Human smoke test required.

Do not move forward until the Human has actually used it.

---

# 37. Development Milestone 0AC-A2 — Tutor Interaction Shell

Goal:

> Prove the interaction mechanics before spending meaningful AI tokens.

Add:

```text
chat panel

Human input

Tutor message display

streaming text if appropriate

Hint button

Explain button

Show Evidence button

lesson stage display

fake/deterministic tutor provider
```

Human evaluates:

```text
layout

text size

chat width

chart width

button placement

workflow

pacing
```

Polish based on actual feedback.

---

# 38. Development Milestone 0AC-A3 — Grounded Real AI

Goal:

> Replace the fake tutor with the real grounded AI pipeline.

Add:

```text
provider abstraction

one real provider

structured TutorAnswer

grounding validator

repair path

token instrumentation

cost instrumentation

latency instrumentation
```

The Human runs real conversations.

Primary questions:

```text
Are the answers useful?

Are they too long?

Does the tutor understand the lesson context?

Does it ask good questions?

Does it explain mistakes well?

Does it hallucinate despite grounding controls?

Is latency acceptable?

What does a study session cost?
```

---

# 39. Development Milestone 0AC-A4 — Guided Drysdale Lesson

Goal:

> Demonstrate an actual interactive Drysdale learning sequence.

Implement at least one complete guided lesson around an already-inspected setup.

Example lesson:

```text
replay before breakout
↓
Tutor asks about location relative to ±1σ
↓
Human answers
↓
advance bar
↓
Tutor asks whether acceptance exists
↓
Human answers
↓
hint available
↓
advance
↓
retest discussion
↓
confirmation discussion
↓
POST_REVEAL review
```

Candidate labels may remain hidden until appropriate.

The lesson locks its required study semantics — Globex-anchored VWAP for
Drysdale — regardless of the Human's free-study chart settings.

---

# 40. Development Milestone 0AC-A5 — Chart-to-Evidence Interaction

Goal:

> Make AI explanations visually meaningful.

Add selected functionality such as:

```text
highlight referenced candle

highlight VWAP or deviation band

highlight IB / overnight reference

show condition checklist

click evidence item → focus chart

click chart event → inspect evidence
```

Only implement what Human testing indicates is useful.

---

# 41. Development Milestone 0AC-A6 — Human UX Evaluation & Polish

Conduct repeated real Human sessions.

Do not assume the first UI is acceptable.

Expected iteration areas:

```text
layout

chart size

chat size

color/visibility

overlay clutter

replay controls

message length

lesson pacing

question difficulty

evidence presentation

button terminology

candidate visibility

hint behavior

free-chat behavior
```

Multiple polish cycles are expected.

This is intentional.

---

# 42. Development Milestone 0AC-B — Private Client/Server Deployment

Only after the local Tutor POC proves useful.

Target:

```text
robby browser
      ↓
private network
      ↓
dragon tutor service
```

Preferred security:

```text
private connectivity
no open unauthenticated Internet endpoint
```

Potential mechanisms should be evaluated at deployment time, e.g.:

```text
Tailscale/private network

private reverse proxy

HTTPS
```

No X Windows.

No desktop streaming.

Browser remains the client.

---

# 43. Dragon Deployment Timing

Do not jeopardize the active capture campaign.

Preferred order:

```text
prove UX locally first

allow prospective campaign to finish

evaluate dragon capacity

deploy tutor service

verify resource isolation
```

If earlier remote deployment becomes desirable, it requires a separate operational review.

---

# 44. Performance

Known Laboratory replay and validation operations can be expensive.

Interactive tutor requirements differ from batch validation requirements.

Eventually measure separately:

```text
initial session load

replay step latency

chart data latency

tutor evidence preparation

AI provider latency

total response latency

memory usage
```

The UI should feel interactive even if expensive analyses are prepared/cached in advance.

---

# 45. Caching Strategy

Likely useful:

```text
prepare development date once

cache 5-minute bars

cache invariant references

cache deterministic replay primitives

reuse prepared session

compute only cutoff-dependent state as needed
```

Any caching must preserve:

```text
market-time semantics

knowledge-time semantics

late-arrival behavior

no-lookahead
```

---

# 46. Human Review Cadence

Do not let Claudine disappear for two weeks and return with a finished UI.

Expected cycle:

```text
small implementation
↓
Human uses it
↓
Human feedback
↓
PO interpretation
↓
small corrective phase
```

Human evaluation is part of development, not final acceptance.

---

# 47. Development Process

Roles remain:

```text
Human:
final decision maker
UX evaluator
student

ChatGPT:
Product Owner
architect
curriculum designer

Claudine:
AI developer
implementation
tests
commit / push
```

Work in narrow phases.

Each accepted phase should normally be committed and pushed.

---

# 48. Repository as Canonical Source

```text
This committed plan is the canonical product plan for
the AI Tutor UX POC.

ChatGPT memory and conversation history provide continuity,
but the repository document is the authoritative specification.
```

Future changes are committed/versioned rather than relying solely on
conversational memory.

When there is disagreement:

```text
current committed repository documentation
wins
```

unless the Human explicitly changes direction.

---

# 49. New ChatGPT Thread Transition

After this plan is:

```text
reviewed

Human-approved

stored in repository

committed

pushed
```

we deliberately stop using the current long ChatGPT browser thread for active Tutor POC development.

Active Tutor POC development moves to a **new ChatGPT browser thread**.

No 0AC implementation begins in the current long thread.

The Product Owner (ChatGPT) prepares a concise kickoff/handoff package for
the Human to paste into the new thread. The repository plan carries the
detailed context.

The package should contain:

```text
project name

canonical plan path

current origin/master

current accepted Laboratory state

prospective campaign status

frozen Drysdale status

important constraints

Human/ChatGPT/Claudine roles

first implementation milestone

critical repository documents
```

Do NOT copy months of conversation.

The repository carries detailed history.

---

# 50. New Thread Working Model

The new ChatGPT thread becomes the active Product Owner thread for:

```text
0AC Tutor UX work
```

This existing thread becomes historical context only.

The new thread should begin by reading/relying on the committed canonical plan.

---

# 51. Parallel Capture Campaign

Throughout Tutor UX development:

```text
dragon continues collecting /ES

campaign dates remain analytically unopened

Tutor POC uses development dates only
```

Tutor development must not invalidate the prospective study.

Tutor work (including documentation work) does not analytically inspect any
campaign date:

```text
2026-10-12 through 2026-11-06
```

and does not alter:

```text
Azure schedules
dragon timers
collector
writer
contract pin
Drysdale V1
quality policies
prospective validation plan
```

The capture campaign continues independently.

---

# 52. End of Capture Campaign

When the bounded `/ES` campaign completes:

```text
do not immediately rewrite Tutor code or Drysdale rules
```

Run the already-frozen prospective validation as its own controlled phase.

The Tutor POC and Drysdale validation remain related but distinct efforts.

---

# 53. Expected Outcome by Campaign End

The goal is that by the time the four-week prospective corpus is ready:

we already know:

```text
whether the chart UX works

whether chat + chart is useful

whether guided lessons work

what Tutor response style the Human prefers

whether evidence highlighting is helpful

how the Human wants replay controls arranged

what model latency feels acceptable

approximately what Tutor sessions cost

whether direct API model interaction works

what major polish remains
```

We should NOT reach November and only then begin discovering these issues.

---

# 54. POC Exit Decision

At the end of the UX POC, Product Owner and Human choose:

```text
PROCEED
Tutor concept is useful;
continue toward fuller learning application

REVISE
Concept has value but interaction model needs substantial redesign

STOP
The AI Tutor interaction is not useful enough to justify continued investment
```

Stopping would be an acceptable POC result.

The purpose is to discover that cheaply rather than assume success.

---

# 55. Current Recommended Sequence

```text
NOW
│
├── Track A:
│   dragon keeps collecting unseen /ES data
│
└── Track B:
    finalize this Tutor UX plan
        ↓
    commit plan to repo
        ↓
    switch to fresh ChatGPT thread
        ↓
    0AC-A1 chart + replay shell
        ↓
    HUMAN USES IT
        ↓
    0AC-A2 interaction shell
        ↓
    HUMAN USES IT
        ↓
    0AC-A3 real grounded AI
        ↓
    HUMAN USES IT
        ↓
    0AC-A4 guided Drysdale lesson
        ↓
    HUMAN USES IT
        ↓
    0AC-A5 evidence/chart interaction
        ↓
    repeated UX polish
        ↓
    private client/server deployment
```

---

# 56. First Implementation Target

After the thread transition, the first implementation phase should be:

```text
0AC-A1 — Tutor Application Shell + Historical Replay Chart
```

Its purpose is NOT AI yet.

Its purpose is to let the Human:

```text
open browser

select approved development session

see ES 5-minute candles

see Globex VWAP and deviation bands

move replay forward/backward

prove no future bars leak

evaluate the basic chart/replay experience
```

Only after the Human approves that interaction should we add the actual Tutor conversation UI.

---

# 57. Plan Acceptance

Human approval of this document means:

```text
AI Tutor UX POC:
AUTHORIZED

parallel prospective data collection:
CONTINUES

development campaign data restriction:
UNCHANGED

initial runtime:
ROBBY

target runtime:
PRIVATE CLIENT/SERVER, ROBBY → DRAGON

primary interface:
WEB BROWSER

first implementation:
CHART + REPLAY BEFORE AI CHAT

Human UX testing:
REQUIRED THROUGHOUT

repository:
CANONICAL SOURCE OF TRUTH

new ChatGPT thread:
REQUIRED BEFORE IMPLEMENTATION

instrument:
/ES ONLY

Volume Profile / new indicators:
FUTURE / NOT AUTHORIZED

settings:
MINIMAL; PRESENTATION vs STUDY-SEMANTIC;
GUIDED LESSONS MAY LOCK SEMANTICS

risk management:
OUT OF SCOPE
```

---

# 58. Amendment Record

**2026-10-13 — Human-approved amendments (incorporated above)**

1. Volume Profile is not part of the initial Tutor POC; chart/settings
   architecture remains extensible for future indicators — see *Future
   Indicator Extensibility* and *Non-Goals*.
2. Minimal settings architecture, distinguishing presentation settings from
   study-semantic settings, with lesson-semantic locking — see *Minimal
   Settings Architecture*, 0AC-A1 and 0AC-A4.
3. `/ES` only; no multi-instrument workflow — see *Instrument Scope*.
4. Risk management is outside Tutor scope; trade-setup and potential-entry
   discussion is in scope — see *Trade-Setup and Potential-Entry
   Discussion* and *Non-Goals*.
