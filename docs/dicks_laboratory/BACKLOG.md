# Dick's Laboratory backlog

Future items recorded by the Product Owner. An item here is not authorized work until the PO opens
it as a phase.

## PRE-ANCHOR CAPTURE READINESS

Recorded 2026-10-11 (0AB-C close-out). Status: **FUTURE — not started**.

**Objective**

```text
establish provable feed/source readiness at or before 17:00 CT
while preserving the canonical session trade population beginning
at 17:00 CT.
```

**Constraints**

- A separate production-engineering phase, **after** the 2026-10-12 → 2026-11-06 /ES corpus
  campaign. Nothing changes during that campaign.
- It must not be satisfied by moving a timestamp earlier. The proof must show that the source
  connection and subscription were genuinely ready before the anchor.
- The canonical session trade population still begins at 17:00 CT. No boundary tolerance, and no
  change to the Globex anchor.

**Background.** The collector opens each dataset at session open, so `capture_started_at` falls a
few hundred microseconds after 17:00:00 CT. Under the strict boundary rule every candidate carries
`CAPTURE_STARTED_AFTER_GLOBEX_ANCHOR`, and `ELIGIBLE_UNQUALIFIED` is unreachable. See
[DRYSDALE_QUALITY_PROPAGATION_0ABC.md](DRYSDALE_QUALITY_PROPAGATION_0ABC.md) §1.

## DRYSDALE VALIDATION HARNESS PERFORMANCE

Recorded 2026-10-12 (0AB-D development shakedown). Status: **FUTURE — not started**. 0AB-D was a correctness /
pre-registration phase; nothing was optimized.

**Finding.** One development date through `scripts/dicks_lab_drysdale_validation.py date` took 13–29 min wall
time and 3.4–4.9 GB peak RSS (six runs; see
[evidence/0AB-D/dev_shakedown/README.md](evidence/0AB-D/dev_shakedown/README.md)). On the 11 GB workstation, with
the desktop applications open, the first attempt was stopped by Claude Code's background memory-pressure handling
while two dates had completed; one-at-a-time runs then completed. The 20-date readout is about 6–10 hours of
sequential runs.

**Constraints.** Any optimization must leave DRYSDALE_V1, the quality policies and every registered outcome
byte-identical (proof: identical `record_sha256` on the development dates), and is a change to the frozen
validation machinery: it needs a recorded addendum, never a silent edit before or during the first readout.
