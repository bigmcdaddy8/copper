# tutor_poc — AI Tutor UX POC (0AC-A1 chart + replay, 0AC-A2 Tutor shell, A2P polish, 0AC-A3 grounded real AI, 0AC-A3E session export)

Canonical plan: [`docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md`](../../docs/dicks_laboratory/AI_TUTOR_UX_POC_PLAN.md).

A local browser app on robby: `/ES` 5-minute candles, Globex VWAP and ±1σ / ±2σ bands, a replay
cutoff you move with Previous / Next / +5m, and a Tutor pane. The Tutor runs on the deterministic fake
provider by default (no model, no credentials, no cost) or, in real mode, on one grounded AI model (A3, below).

## Run

```bash
scripts/tutor_poc.sh            # builds the web app if needed, then serves
# open http://localhost:8765
```

The first run on a machine prepares the approved session once (about 30 minutes for 2026-09-30, ~4 GB RAM)
into `~/.cache/copper/tutor_poc/`. Later starts load that cache in a few seconds. To prepare it ahead of time:
`uv run tutor_poc prepare`.

If `uv run tutor_poc` is not found, install the workspace apps with `uv sync --all-packages` (a plain
`uv sync` at the repo root only syncs the root project and removes the other apps' packages).

Frontend development: `uv run tutor_poc serve` in one terminal, `cd apps/tutor_poc/web && npm run dev` in
another (Vite proxies `/api` to port 8765).

## Layout

| Path | What |
|---|---|
| `src/tutor_poc/dev_sessions.py` | Approved development dates; the 2026-10-12..2026-11-06 campaign is refused |
| `src/tutor_poc/timeline.py` | Prepares the as-of chart timeline with the Laboratory pipeline; local cache |
| `src/tutor_poc/snapshot.py` | Replay stepping (clamped) and the `TUTOR_CHART_SNAPSHOT_V1` payload |
| `src/tutor_poc/api.py` | FastAPI: `/api/sessions`, `/api/sessions/{date}/replay`, `/api/sessions/{date}/snapshot`, `/api/sessions/{date}/tutor/turn`, `/api/sessions/{date}/tutor/evidence`, `/api/sessions/{date}/tutor/export` |
| `src/tutor_poc/tutor.py` | A2: stage transitions, Show Evidence (`snapshot_evidence`), scripted `FakeTutorProvider` text |
| `src/tutor_poc/providers.py` | A3: `TutorModelProvider` seam — `FakeProvider`, `GroundedProvider` (grounding + repair), `AnthropicModelClient`; env config; diagnostics |
| `src/tutor_poc/evidence.py` | A3: the model's as-of evidence for a replay position, as a Laboratory `TutorLesson` |
| `src/tutor_poc/grounding.py` | A3: frozen Laboratory validation + the POC prose number / time guard |
| `src/tutor_poc/prompt.py` | A3: `TUTOR_POC_SYSTEM_V1` (versioned, sha-pinned by a test) |
| `src/tutor_poc/pricing.py` | A3: versioned model pricing |
| `src/tutor_poc/conversation.py` | A3: in-memory per-page conversation context and usage totals; A3E: `TurnRecord` per answered turn |
| `src/tutor_poc/export.py` | A3E: Export Session — builds the `TUTOR_SESSION_EXPORT_V1` ZIP, secret scan |
| `src/tutor_poc/cli.py` | Typer CLI: `prepare`, `serve`, `live-smoke` (opt-in, spends tokens) |
| `web/` | React + TypeScript + Vite; chart: TradingView lightweight-charts 5.1.0 |

## Market truth stays in the Laboratory

The browser never computes bars, VWAP or bands. For every 5-minute cutoff T on the session grid
(17:05 CT the prior evening through 16:00 CT), `timeline.py` runs the accepted pipeline:
`prepare_replay` → `ReplayCutoff.at(T)` → `as_of_evidence` (the effective tape known at T) →
`drysdale.run_pass` / `_bars` (VWAP_BANDS_GLOBEX_V1, BARS_5M_V1), resuming the pass under the 0AB-B
`DrysdaleCache.usable` rule. Each position holds only the complete bars the Laboratory knew at T, so
late prints, corrections and cancels behave exactly as in the Laboratory. The snapshot endpoint
returns one position: future bars are never sent to the browser.

## Settings

```text
presentation (browser only; never changes values or requests)
  candles:  up / down color
  overlays: per group (vwap, sigma1, sigma2): visible, color, lineWidth, lineStyle
  regions:  level1 (-1σ → +1σ), level2 (±1σ → ±2σ): visible, color, opacity (default: line color, 30%)

study-semantic (sent to the server; computed there)
  vwap_anchor = GLOBEX   (locked in A1; the server rejects anything else)
```

Overlays arrive as named series (`id`, `label`, `group`, `points`); the chart renders whatever series
the server sends, so a later reference or indicator is an additional series, not a chart rewrite.
Tradable-price labels follow the Laboratory's `/ES` tick grid (`volume_profile.ES_PRICE_GRID`,
`CME_ES_TICK_GRID_V1`), sent in the snapshot as `price_grid` (`symbol`, `tick_size` 0.25, `price_precision` 2).
The price axis and the crosshair label show the nearest valid tick (an exact half tick rounds up:
7780.125 → 7780.25); the crosshair itself still moves freely. This is formatting only: candle values and
the analytical VWAP / σ levels are sent and plotted unrounded, and the legend and evidence panel keep
showing them to two decimals.

Region fills and the replay-cutoff marker are lightweight-charts series primitives (`web/src/primitives.ts`)
that only pair points the server already sent; the regions never overlap, so opacities do not stack.

## Tutor interaction shell (A2)

```text
POST /api/sessions/{date}/tutor/turn       {action, replay_cutoff_utc, stage, turn, text?}
     -> {turn_id, turn, role: "tutor", action, text, stage, trading_date, replay_cutoff_utc, provider}
GET  /api/sessions/{date}/tutor/evidence?cutoff=...
```

`action` is `question` (opening / New question), `message` (the Human's text, required non-empty), `hint`
or `explain`. The request body is closed (unknown fields are refused); the date is the same approved,
enabled session the chart uses, and the cutoff must be one of its replay positions, so the Tutor API is
no route to another dataset or the sealed campaign.

The provider is fake; the market facts are not. `FakeTutorProvider` returns scripted text (same inputs,
same text; it never evaluates the Human's answer). Any value it or the evidence panel shows is read from
`build_snapshot` at the request's cutoff, the same snapshot that feeds the chart.

Stages reuse the Laboratory vocabulary (`tutor_evidence.LessonStage`) and its monotonic order:

```text
question  -> QUESTION      (starts a new lesson at the current replay position)
message   -> unchanged
hint      -> HINT          (a later stage is kept: ANSWER stays ANSWER)
explain   -> ANSWER
POST_REVEAL is not used: in TUTOR_REVEAL_V1 it releases hidden future evidence, which A2 never has.
```

Every message keeps the trading date, replay cutoff and stage it was produced at. The reply echoes the
request's cutoff and turn; the browser accepts a reply only for the pending turn and the same cutoff, so
a reply that arrives after the replay moved stays labeled with its original time. Moving the replay
changes the Tutor context line but keeps the conversation (a divider marks the change).

Show Evidence opens a compact panel for the current replay position: the latest completed bar's
open / high / low / close and its VWAP, ±1σ, ±2σ, with the cutoff and bar time. No candidate or setup
labels. Chart highlighting is A5.

The conversation lives in the page only: a reload starts a new one. Replies are plain HTTP (no streaming).

Each message also keeps its kind (`question`, `reply`, `hint`, `explain`, `human`, from the action that
produced it), separate from the lesson stage. Hint and Explain replies are labeled `Hint:` / `Explain:`
with a colored edge, so they stay identifiable when scrolling back.

The divider between the chart and the Tutor pane can be dragged (double-click resets). The accepted
width `clamp(240px, 26%, 400px)` is the Tutor minimum; the chart keeps at least 480 px. Resizing is
browser-only (the chart autosizes; no request is made) and the width is remembered in `localStorage`.

## Grounded real AI (A3)

### Fake vs real

```bash
scripts/tutor_poc.sh                                   # fake (default): no model, no network, cost $0

# real: one provider (Anthropic Messages API, official `anthropic` SDK, direct HTTPS)
export TUTOR_PROVIDER=anthropic
export ANTHROPIC_API_KEY=...                           # server-side only; never sent to the browser or logged
export TUTOR_MODEL=claude-opus-5-5                     # optional (default); must have a pricing entry
export TUTOR_EFFORT=low                                # optional (default low): low | medium | high | xhigh | max
scripts/tutor_poc.sh
```

`TUTOR_PROVIDER` unset or `fake` switches back. In real mode the server refuses to start (exit 2, clear message)
when the key is missing or the provider / model / effort is unknown. `GET /api/tutor/config` tells the browser
the mode, provider, model, effort, prompt version and pricing version (never the key). Claude Code is not used
at runtime.

### Flow

```text
replay position T ─ evidence.py ─▶ TUTOR_POC_MODEL_EVIDENCE_V1 (as of T) ─▶ Laboratory TutorLesson (adapter)
                                         │ compact citable items + bounded conversation + the Human message
                                         ▼
                           AnthropicModelClient  (system TUTOR_POC_SYSTEM_V1, output_config json_schema = TutorAnswer)
                                         │ structured TutorAnswer JSON
                                         ▼
 parse_answer → validate_answer_grounding → answer_guards   (dicks_laboratory.tutor_ai / tutor_evidence, frozen, reused)
             → text_guards (POC: numbers / times / dates written in prose must be evidence values)
                                         │
              GROUNDED ─▶ shown          │ else: one repair (same evidence + the validator's reasons), validated again
                                         ▼
              still failing ─▶ "Tutor response could not be grounded in the replay evidence. Please try again."
```

- **Evidence** (`evidence.py`): built from the same prepared chart position as the chart and Show Evidence. The
  latest completed 5m bar (start / end CT, OHLC, Globex VWAP, ±1σ, ±2σ, close vs VWAP, close − VWAP, the band region
  holding the close) and the bars before it, up to the Laboratory's `RECENT_BARS` = 6 in all (OHLC, VWAP, close vs
  VWAP), plus the VWAP anchor / band policy / tick size. Analytical values are given at 0.01 (half-even), as the
  evidence panel shows them. About 8.9 KB on 2026-09-30. No dataset ids, hashes or paths. Bars after T do not exist
  in the document (it is built from position T only).
- **Adapter**: the frozen `TutorEvidenceContext` / `TutorLesson` refer to evidence by (document sha256, RFC 6901
  pointer); here the document is the chart position's evidence (the frozen `PRICE_ACTION` facts use the cash VWAP
  and need a full replay per turn). The frozen `LessonDefinition` needs a `QuestionKind`; free conversation has
  none, so the adapter uses `PRICE_VS_CASH_VWAP` only to satisfy construction — the kind and placeholder answer
  key are never sent to the model or graded.
- **Conversation context**: the last 8 messages of this page's conversation (each ≤ 1,200 characters, each with
  its replay cutoff), only from the same date and **at or before** the current cutoff, so stepping the replay back
  never sends later market facts. Kept in server memory per page (random session id). No summarization.
- **Prose guard** (`grounding.py`): the frozen validator checks values a claim *asserts*; the POC guard also
  rejects any decimal number, any number of three or more digits, any clock time and any ISO date written in the
  answer text, a claim or an uncertainty unless it is (a rounded form of) an authorized evidence value. Numbers the
  Human typed may be echoed. Unsupported claims are not checked (they name what the evidence lacks).
- **Repair**: `tutor_ai.MAX_REPAIR_ATTEMPTS` = 1. Provider timeouts / errors are not repaired.
- **Stages**: unchanged from A2 (`question` → QUESTION, `hint` → HINT, `explain` → ANSWER; POST_REVEAL unused).
  A failed turn leaves the stage where it was.

### Prompt

`TUTOR_POC_SYSTEM_V1` (`prompt.py`): concise (two to four sentences), one question at a time, short specific
feedback, no praise, uncertainty stated, facts vs `AI_INTERPRETATION`, evidence-only facts with exact citations, no
prediction past the cutoff, undefined concepts (acceptance, breakout, …) only as unsupported, no trade / risk talk.
`tests/test_real_provider.py::test_prompt_versions_are_pinned` pins its sha256: a wording change needs a new version.

### Request, timeouts, retries

`claude-opus-5-5`, effort `TUTOR_EFFORT`, `max_tokens` 16,000, `output_config.format` json_schema (the frozen
TutorAnswer shape; type unions as `anyOf`). The fixed system prompt is a prompt-cache breakpoint (5-minute TTL),
so later turns read it from cache. Server-side refusal fallback (`fallbacks: "default"`, beta
`server-side-fallback-2026-07-01`) is on; a turn served by a fallback model keeps its raw usage but is reported
"unpriced". Transport: 60 s per call, one SDK retry (connection errors, 408 / 409 / 429 / 5xx, timeouts); grounding
repair is separate (at most one). The browser gives up after 300 s.

### Diagnostics

Each real turn records (and returns to the browser): provider, model, served model, effort, prompt version and
sha256, pricing version, status, attempts, repair attempts, provider-reported input / output / cache-read /
cache-write tokens (`null` when not reported, never estimated) and the raw usage objects, evidence payload bytes
(the evidence section only), request bytes (the whole user message), latency (evidence preparation, model calls,
validation, total), estimated turn cost, and the page session's cumulative tokens and cost. Failed turns count
too. The Tutor pane shows one summary line (`AI 2.8 s · in 4,000 · out 180 · turn $0.0086 · session $0.0226`); the
line expands into a per-turn table. Accepted answers carry a collapsed "Grounded · N facts · M interpretations"
list of claims and the evidence each cites. Fake mode shows `Provider: fake · cost $0`.

Session totals live in server memory per page: **a page reload (or a server restart) resets them.**

Real turns are also appended to `~/.cache/copper/tutor_poc/runs/tutor_runs_YYYYMMDD.jsonl` (per attempt: status,
validator issues, raw model output, usage, request id, cost). No prompt text and no key.

### Pricing

`pricing.py`, `ANTHROPIC_LIST_2026-10-17`, from https://platform.claude.com/docs/en/about-claude/pricing (fetched
2026-10-17). `claude-opus-5-5`, USD per million tokens: input 4.00, output 20.00 (thinking tokens are output),
cache read 0.20, 5-minute cache write 5.00. Turn cost = Σ over attempts of the provider-reported tokens × these
rates. A price change is a new entry with a new version, never an edit.

### Live check (spends real API tokens)

```bash
TUTOR_PROVIDER=anthropic ANTHROPIC_API_KEY=... uv run tutor_poc live-smoke --yes      # 4 turns at 09:30 CT
```

Not part of `pytest` or `npm test`. Without `--yes` it refuses. It prints per-turn tokens / latency / cost and
appends the run log.

## Export Session (A3E)

**Export Session** (Tutor header) downloads the page's current Tutor session as one ZIP, for keeping it and for
an external review by ChatGPT / Claude / another LLM. It is an export, not session management: the session
still lives only in server memory, so a page reload or a server restart starts a new one. Export it first.

`POST /api/sessions/{date}/tutor/export` `{session_id, replay_cutoff_utc}` returns
`tutor_session_<YYYY-MM-DD>_<HHMM>-<HHMM>.zip`. The times are Chicago replay times: the cutoff of the first
Tutor turn, then the chart's cutoff at export. If the Human stepped back, the second can be earlier.
The button is disabled until a turn has been answered and while a turn is pending. An unknown or empty
session gets a 409 "Nothing to export yet" message, never an empty ZIP. Exporting calls no model and changes
neither the conversation, the totals, nor the replay.

| Member | Content |
|---|---|
| `session.md` | Chronological transcript, grouped by replay cutoff. Human and Tutor texts are exactly as shown. Each turn has its kind (Question / Reply / Hint / Explain), stage, status, grounding counts, and diagnostics. Failed turns show their status and the error the Human saw. |
| `session.json` | `schema_version: TUTOR_SESSION_EXPORT_V1`. Contains session metadata (wall-clock vs replay times kept apart), totals, replay positions, messages, and turns. Each turn has its grounding, diagnostics, safe per-attempt metadata, and `evidence_ref`. |
| `turns.csv` | One row per Tutor turn: status, repairs, tokens, cost, cumulative cost, latency, grounding counts, `human_text`, `text`. Missing values are blank. |
| `evidence.jsonl` | One `TUTOR_SESSION_EVIDENCE_RECORD_V1` per turn. Holds the exact evidence object the provider was given (stored when the turn was answered, never rebuilt), its sha256, the cutoffs of the conversation context, and the grounding result (issue codes only). |
| `market_context.csv` | Completed 5-minute bars, from 6 bars before the first turn's cutoff through the latest visited cutoff. Values are Laboratory values as of that cutoff: OHLC, volume, VWAP, ±1σ / ±2σ, band region. Also `revised_after_completion` with the close / VWAP at completion (late prints), and `tutor_evidence` (latest / recent). No ticks. |
| `manifest.json` | Versions, filename policy, record counts, the sha256 and bytes of each other member, `campaign_data_included: false`, `contains_secrets: false`, and the number of redactions. |

Per-turn records (`TurnRecord`, in memory, at most 200 per session) hold the following, all captured when the
turn was answered:
- what the Human typed and the Tutor text that was shown;
- status, error, grounding, the diagnostics sent to the browser (with the session totals after the turn);
- the provider's exact evidence object, the conversation-context cutoffs, and per-attempt metadata.

Rejected answer text and validator details are not kept, because they can echo a rejected answer. They stay
only in the server-side run log.

**Secrets.** Before the ZIP is written, every member is checked and anything matching is redacted:
- values of secret-named environment variables (`*KEY*`, `*TOKEN*`, `*SECRET*`, ...);
- `sk-ant-…`, `Authorization:` / `x-api-key:` / `Bearer …` shapes;
- the home directory path.

If anything remains after that, the export is refused. Nothing in the record holds credentials, prompts, or
provider bodies to begin with.

**Campaign.** The export route uses the same approved-date gate as every other route, and `build_export` also
refuses sealed dates. 2026-10-12..2026-11-06 can never be exported.

**Review.** Upload the ZIP to a capable model with
[`docs/dicks_laboratory/TUTOR_SESSION_REVIEW_PROMPT.md`](../../docs/dicks_laboratory/TUTOR_SESSION_REVIEW_PROMPT.md).
It is a reusable, 20-point rubric that separates what the export shows from the reviewer's own assessment.

## Future (0AC-A5, not implemented): Tutor chart annotations

The Human wants Tutor actions (Hint, Explain, Show Evidence) to be able to place temporary annotations
on the chart: an arrow at a candle, a circle / highlight around a candle or region, a marker on VWAP / ±σ,
an emphasized area. Intended shape:

```text
Tutor action -> structured annotation intent -> frontend chart rendering -> temporary annotation
             -> cleared or superseded when the replay advances
```

The model must never emit drawing code. It returns a constrained, structured annotation request that refers
to deterministic evidence (identifiers, bar times, prices from the authorized snapshot), and the frontend
renders it. The schema is to be designed in A5.

## Branding and chart attribution (A2P2)

The header shows the company logo (`docs/company_logo.png`, imported by the web build and cropped to the
lettering with CSS; the file itself is unchanged). The chart's built-in TradingView logo link is turned off
with the library's own option `layout.attributionLogo: false` (`web/src/Chart.tsx`).

Lightweight Charts is Apache-2.0; its README requires the attribution notice from its `NOTICE` file and a
link to https://www.tradingview.com/ on a page available to users. The npm package does not ship `NOTICE`,
so the text is taken verbatim from `NOTICE` in tradingview/lightweight-charts at tag `v5.1.0` (the installed
version) and shown in the status bar footer (`web/src/Branding.tsx`):

```text
Charts: TradingView Lightweight Charts™ · Copyright (с) 2025 TradingView, Inc. https://www.tradingview.com/
```

(The URL is a link; "(с)" is reproduced as published, with a Cyrillic "с".) Re-check `NOTICE` when the
chart library is upgraded.

## Development dates

Only already-inspected dates are approved: 2026-09-29, 2026-09-30, 2026-10-01, 2026-10-02. A1/A2 enable
2026-09-30. Each dataset is checked against its recorded sha256 when it is prepared.

## Tests

```bash
uv run pytest apps/tutor_poc/tests -q          # backend (synthetic Laboratory fixture, no corpus file, no model)
cd apps/tutor_poc/web && npm test              # frontend logic + Tutor view render (vitest)
```

Both suites are zero-cost: the real provider is tested with scripted model replies and a stub SDK object (no
network, no credentials). The only live path is `tutor_poc live-smoke --yes`.
