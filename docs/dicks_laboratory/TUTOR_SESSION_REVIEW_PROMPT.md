# Tutor Session Review Prompt (0AC-A3E)

Use this prompt to have a capable model (ChatGPT, Claude, or another) evaluate one exported Dick's Laboratory
Tutor session in a consistent way.

How to use it:

1. In the Tutor POC, click **Export Session**. This downloads `tutor_session_<date>_<HHMM>-<HHMM>.zip`.
2. Upload the ZIP to the reviewing model. If the model cannot open ZIPs, upload the extracted files instead,
   `session.md` first.
3. Paste everything below the line as the message.

The prompt is not tied to a particular session. Expect a clear review to take a few minutes to read.

---

You are reviewing one study session between a Human student and the Dick's Laboratory AI Tutor. The Tutor
teaches the Human to read an intraday /ES futures chart in historical replay, using VWAP and its ±1σ / ±2σ
deviation bands. The goal is setup recognition in the style of the Drysdale VWAP method, not trade advice.
The attached export contains these files:

| File | What it is |
|---|---|
| `session.md` | The chronological transcript. Human and Tutor texts are exactly as shown in the app, typos included. |
| `session.json` | The same session in machine-readable form: metadata, totals, replay positions, messages, turns. |
| `turns.csv` | One row per Tutor turn: status, repairs, tokens, cost, latency, grounding counts, texts. |
| `evidence.jsonl` | For each turn, the exact evidence object the Tutor was given at that replay cutoff, plus the grounding result. |
| `market_context.csv` | Completed 5-minute bars of the visited replay window, with Laboratory values: OHLC, volume, VWAP, bands, band region. |
| `manifest.json` | Export versions, file hashes, and flags. |

## Ground rules for your review

1. **Separate observation from judgment.** Tag every point as one of:
   - **[EXPORT]**: something objectively present in the files. Cite the turn id (`turn-0003`), the replay
     cutoff, and the file/field.
   - **[ASSESSMENT]**: your own interpretation, evaluation, or recommendation.
2. **Do not invent market data.** Use only the values in the export. If a value you would need is absent, say
   so and treat it as missing. Do not estimate it, and do not fill it in from general market knowledge.
3. **Respect replay time.** The Tutor at replay cutoff T was given only the evidence in that turn's
   `evidence.jsonl` record. `market_context.csv` can contain bars after an earlier turn's cutoff.
   - Do not criticize a turn for not knowing a later bar. Do flag any turn that appears to use information
     beyond its own cutoff.
   - Check `revised_after_completion` before calling a Tutor value wrong. A late print can revise a bar after
     it completed. In that case the Tutor's value can match `close_at_completion` / `vwap_at_completion`
     rather than the later values.
4. **Wall clock is not replay time.** Wall-clock timestamps are when the Human used the app. Replay times (CT)
   are the historical chart position.
5. **The student's wording is evidence.** Human messages are verbatim. Judge how the Tutor handled their
   approximations, shorthand, mistakes, and uncertainty.
6. **Failed turns count.** Turns with a status other than `GROUNDED` / `FAKE` were not shown as answers. The
   Human saw only the error line. Rejected answer text is intentionally not exported.
7. **Fake sessions.** If `provider` is `fake`, the Tutor texts are scripted test responses. Evaluate the
   export's completeness instead of teaching quality.

## Evaluate each of these

For each item, give a rating (**Strong / Adequate / Weak / Not observable**), the evidence (with
**[EXPORT]** citations), and your **[ASSESSMENT]**.

1. **Teaching progression.** Does the session build understanding step by step, or restart and wander?
2. **Usefulness of Tutor questions.** Do the questions make the Human look at something that matters?
3. **Over-focus on arithmetic.** Does the Tutor turn deterministic arithmetic into unnecessary quiz questions,
   for example asking the Human to compute a distance that the evidence already states? Does it force exact
   numbers when an approximate, conceptual answer was adequate?
4. **Use of recent-bar context.** Does the Tutor reason across the recent bars it was given, or treat each
   candle in isolation?
5. **Noticing misunderstandings.** When the Human is wrong, vague, or half-right, does the Tutor notice and
   address it specifically?
6. **Hint quality.** Does each Hint guide without giving away the answer?
7. **Explain quality.** Does each Explain add understanding beyond restating numbers?
8. **Repetition / circular questioning.** Does the Tutor ask the same thing again, or loop?
9. **Contradictions.** Do any turns contradict each other? Separate genuine contradictions from changes
   caused by moving the replay cutoff.
10. **Grounding quality.** Do the Tutor's stated facts match the turn's evidence? Are the grounding claims
    (`grounding` in `session.json` / `evidence.jsonl`) reasonable?
11. **Available vs claimed-unavailable evidence.** List any place where the Tutor said it lacked information
    that its turn's evidence actually contained, and any place where it needed information the evidence did
    not contain. Include whether band values existed only for the latest bar.
12. **Fact vs interpretation.** Are interpretations clearly labeled and kept apart from facts?
13. **No-lookahead concerns.** Does any turn reference prices, times, or outcomes after its replay cutoff?
14. **Replay-context continuity.** When the replay moves, does the Tutor connect the new position to the
    earlier discussion sensibly?
15. **Verbosity.** Are responses an appropriate length for a live study session?
16. **Latency and cost.** Using `turns.csv`, note slow or expensive turns, repairs, and failures. Note where
    output length drives cost.
17. **Missed teaching opportunities.** What did the chart at those cutoffs offer that the Tutor did not use?
    Use only values in the export.
18. **Narrowing the setup decision.** Does the Tutor help the Human narrow what kind of situation this is
    (where price sits relative to VWAP and the bands, and what that location implies for the setup
    question), or does it leave the decision space wide open?
19. **Instruction vs data narration.** Does the interaction feel like teaching, or like reading numbers aloud?
20. **Recommendations.** Give concrete recommendations for the curriculum and for the evidence. What should
    the Tutor be given or asked to do differently?

## Specific questions (answer each one directly)

- Did the Tutor turn deterministic arithmetic into unnecessary quiz questions?
- Did it force exact numerical answers when an approximate conceptual answer was adequate?
- Did it miss the larger teaching point around VWAP band location?
- Did it fail to reason across recent bars because the evidence lacked something (for example, bands for
  earlier bars)?
- Did it fail to use evidence that was actually available?
- Did it progress toward Drysdale setup recognition, or stay stuck in isolated candle trivia?

## Output format

1. **Session summary.** About 5 lines: date, replay window, number of turns, provider/model, total cost, and
   how many turns failed or needed a repair. All of these are [EXPORT] facts.
2. **Scorecard.** A table of the 20 items above with their ratings.
3. **Findings.** One section per item, each with [EXPORT] evidence and an [ASSESSMENT].
4. **Answers to the specific questions.**
5. **Top 5 recommendations**, ranked by expected impact on learning. Mark each as a *curriculum*, *evidence*,
   *prompt/behavior*, or *UX* change.
6. **Data gaps.** What the export did not contain that would have changed your review.
