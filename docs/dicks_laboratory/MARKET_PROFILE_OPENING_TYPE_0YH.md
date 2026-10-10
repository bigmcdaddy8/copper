# Opening-Type V1 Candidates — Descriptive Corpus Audit (0Y-H)

> **OPENING_TYPE_V1 is a pre-registered Laboratory candidate policy, not an
> industry-standard mechanical definition.**
>
> Everything below is **DEVELOPMENT / DESCRIPTIVE EVIDENCE — NOT VALIDATION.**
> The corpus has been inspected in 0Y-D through 0Y-G. Candidates are taxonomy,
> not signals.

- Policy: `OPENING_TYPE_V1_POLICY.md`; design summary in
  `TPO_MARKET_PROFILE_0YA.md` §65–§72.
- Evidence: `evidence/0Y-H/`.

## 1. Order of work (pre-registration)

1. V1 was implemented and tested on hand-built fixtures only.
2. It was then frozen:
   - `tpo_opening_type.py` sha256
     `2b7b571c0b813bd267d8f2591336f4fe2877a8f6c4258cb0427f6e665c798d7c`;
   - `OPENING_TYPE_V1_POLICY.md` sha256
     `1a952478c7ef892de8933a2ad15307ceb2089cadf74a1cfdcd6f3e42ba5af2ec`;
   - committed in `92e0a0cc5266076e51746f8a3510db902711c88a`.
3. Only then was it run over the corpus:

   ```
   uv run python scripts/dicks_lab_mp_opening_type_study.py record OUT_DIR <the 22 corpus databases>
   ```

   - Wall clock was 26 min 52 s, with 4.7 GB peak RSS: 1,603 s of shared tape
     loading, then 8.0 s to classify and record all 17 days.
   - The 22 database sha256 values are identical before and after the run. No
     dragon boot was needed.
4. **V1 was not revised after this output was seen.** Every record carries
   cohort `DEVELOPMENT`.

## 2. Counts (DEVELOPMENT, NOT VALIDATION)

| Item | Count |
|---|---|
| profiled days | 17 |
| NOT_CLASSIFIED (opening NOT_AVAILABLE: both 08-31 datasets) | 2 |
| classified days | 15 |
| classified, no candidate | 0 |
| classified, one candidate | 11 |
| classified, several candidates | 4 |
| `OPEN_DRIVE` | 2 (both DOWN: 09-15, 09-29) |
| `OPEN_AUCTION_IN_RANGE` | 4 (09-25, 09-28, 09-30, 10-01) |
| `OPEN_AUCTION_OUT_OF_RANGE` | 2 (09-24 below, 10-02 above) |
| `OPEN_AUCTION` (no prior range; IN/OUT NOT_CLASSIFIED) | 7 (09-02, 09-07, 09-08, 09-11, 09-21, 09-23, 10-06) |
| `OPEN_TEST_DRIVE` | 4 (all DOWN: 09-25, 09-30, 10-02, 10-06) |
| overlaps | OAIR + OTD 2; OAOR + OTD 1; OA + OTD 1 |
| matched candidates QUALITY_QUALIFIED | 3: 09-08 OA (the current open is qualified); 10-02 and 10-06 OTD (the probe reference is ONH and the overnight is qualified) |
| `OPEN_REJECTION_REVERSE` | DEFERRED on every day |

## 3. Per-day table

| Date | Opening | Prior | Overnight | Open vs prior range / value | Drive | OAIR | OAOR | OA | OTD | Probe ref. | n |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 08-31 befb7b0e | NOT_AVAILABLE | NO_PRIOR_PROFILE | NOT_AVAILABLE | — | NOT_CLASSIFIED | | | | | | 0 |
| 08-31 c9ebc043 | NOT_AVAILABLE | NO_PRIOR_PROFILE | QUALITY_QUALIFIED | — | NOT_CLASSIFIED | | | | | | 0 |
| 09-02 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | no | n/c | n/c | YES | no | — | 1 |
| 09-07 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | no | n/c | n/c | YES | no | — | 1 |
| 09-08 | QUALITY_QUALIFIED | PRIOR_PROFILE_INCOMPLETE | Q-Q | — | no | n/c | n/c | YES (Q-Q) | no | — | 1 |
| 09-11 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | no | n/c | n/c | YES | no | — | 1 |
| 09-15 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | **YES DOWN** | n/c | n/c | no | no | — | 1 |
| 09-21 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | no | n/c | n/c | YES | no (ONH reached, no cross in A) | ONH | 1 |
| 09-23 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | no | n/c | n/c | YES | no (ONL reached, no cross in A) | ONL | 1 |
| 09-24 | UNQUALIFIED | AVAILABLE | Q-Q | BELOW range / BELOW value | no | no | **YES** | — | no | — | 1 |
| 09-25 | UNQUALIFIED | AVAILABLE | Q-Q | INSIDE / INSIDE | no | **YES** | no | — | **YES DOWN** | PRIOR_VAH | 2 |
| 09-28 | UNQUALIFIED | AVAILABLE | Q-Q | INSIDE / BELOW value | no | **YES** | no | — | no | — | 1 |
| 09-29 | UNQUALIFIED | AVAILABLE | Q-Q | INSIDE / INSIDE | **YES DOWN** | no | no | — | no (VAL reached, no cross in A) | PRIOR_VAL | 1 |
| 09-30 | UNQUALIFIED | AVAILABLE | Q-Q | INSIDE / ABOVE value | no | **YES** | no | — | **YES DOWN** | PRIOR_HIGH | 2 |
| 10-01 | UNQUALIFIED | AVAILABLE | Q-Q | INSIDE / BELOW value | no | **YES** | no | — | no | — | 1 |
| 10-02 | UNQUALIFIED | AVAILABLE | Q-Q | ABOVE range / ABOVE value | no | no | **YES** | — | **YES DOWN (Q-Q)** | ONH | 2 |
| 10-06 | UNQUALIFIED | NO_PRIOR_PROFILE | Q-Q | — | no | n/c | n/c | YES | **YES DOWN (Q-Q)** | ONH | 2 |

Key: Q-Q = QUALITY_QUALIFIED; n/c = NOT_CLASSIFIED (no prior range).
- The machine-generated version is `evidence/0Y-H/opening_type_run/opening_type_audit.md`.
- The per-day explanations (every condition, with its detail) are in
  `reports/`, and the full JSON records are in `records/`.

## 4. Open Test Drive evidence

| Date | Probe reference | Open → ref | Reach (CT) | Reach → cross | Opposite excursion in A | A terminal |
|---|---|---|---|---|---|---|
| 09-25 | PRIOR_VAH 7778.00 | +2 ticks | 08:30:00.046 | 0.099 s | 41 ticks | **+40 ticks (UP)** |
| 09-30 | PRIOR_HIGH 7758.50 | +27 ticks | 08:31:51.745 | 91.296 s | 15 ticks | **+63 ticks (UP)** |
| 10-02 | OVERNIGHT_HIGH 7802.75 | +53 ticks | 08:45:14.232 | 548.278 s | 64 ticks | −4 ticks (DOWN) |
| 10-06 | OVERNIGHT_HIGH 7867.75 | +21 ticks | 08:30:53.163 | 230.791 s | 9 ticks | **+65 ticks (UP)** |

## 5. Observations, documented and not tuned

These are recorded for PO review and for any future `OPENING_TYPE_V2`. V1 is
unchanged.

1. **Three of the four Open Test Drive candidates ended A on the probe side.**
   - On 09-25, 09-30 and 10-06 the post-cross (DOWN) auction did not persist:
     the A terminal was 40–65 ticks *above* the open.
   - Only on 10-02 did A end on the candidate's side.
   - The cause is that V1 requires an opposite-side trade after the cross, but
     no persistence and no minimum excursion (PO §12–§13). Under the tick
     cross, T4 is satisfied by the crossing trade itself.
   - The facts that would describe persistence are printed beside every
     candidate: the A terminal, the opposite excursion, and the post-grace
     crosses.
2. **09-25's test took 0.099 s.** The open printed 2 ticks below the prior
   VAH, which traded 46 ms later; the open was crossed 99 ms after that. Test
   Drive has no grace in V1 (PO §12 applies the grace only to Drive and
   Auction), so a sub-second probe qualifies.
3. **Every Test Drive and every Open Drive candidate is DOWN** (4 and 2).
   With 15 classified days this is an observation about the sample, not a
   property of the rule. No probe was DOWN to a reference followed by an UP
   cross inside A.
4. **The Open Auction family covers 13 of 15 classified days.** R1 and R2
   need only one post-grace cross and one trade on each side. The 60-minute
   open-cross counts were 3–66 (0Y-F), and post-grace crosses in A were 5–48
   on the auction days.
   - The two Drive days (09-15, 09-29) are exactly the days whose open stayed
     uncrossed after +60 s through 30 minutes in the 0Y-G grace diagnostics.
     The 60 s scale was chosen before this audit (PO §6), not fitted to it.
5. **No classified day has zero candidates.** Drive and Auction are mutually
   exclusive by construction. If the grace price is off the open, either the
   open is crossed after the grace instant (R1 and R2 hold, so an auction
   candidate) or it is not (D2 holds, so a Drive unless the A terminal is
   exactly at the open). A day therefore escapes both only when:
   - the grace price is exactly at the open, or
   - the A terminal is exactly at the open with no post-grace cross.

   Neither occurred here.
6. **Missing prior context dominates.** 8 of 15 classified days have no
   usable prior range (prior day absent from the corpus or without a
   profile), so 7 auctions are generic `OPEN_AUCTION`. The eighth such day,
   09-15, is a Drive. This is a corpus-coverage property.
7. **Overnight quality and the Globex decision:**
   - The overnight is QUALITY_QUALIFIED on all 16 days that have one: the
     capture begins 0.18–0.36 ms after 17:00 CT, and under the PO's
     no-tolerance decision no Globex open is claimed.
   - This qualified only the two test drives whose probe was ONH (10-02,
     10-06).
   - It did not touch the prior-reference test drives (09-25, 09-30), any
     Drive, or any OAIR / OAOR, as specified (PO §19–§20).
8. 09-21 (ONH), 09-23 (ONL) and 09-29 (prior VAL) reached a reference with
   no open cross before the end of A, so they are not Test Drives.

## 6. Feasibility after V1

| Type | Status |
|---|---|
| OPEN_DRIVE | V1 CANDIDATE implemented; prospective validation pending |
| OPEN_AUCTION_IN_RANGE / OUT_OF_RANGE / generic | V1 CANDIDATE implemented; prospective validation pending |
| OPEN_TEST_DRIVE (exact reference) | V1 CANDIDATE implemented. Observation 1 is the main open question for a V2, which would need its own pre-registration. |
| OPEN_REJECTION_REVERSE | DEFERRED — `REFERENCE_DEFINITION_CONFLICT` |

## 7. Prospective validation

- The validation cohort is trading dates **after 2026-10-09**, collected after
  the freeze and scored by the unmodified frozen source. A record whose policy
  sha256 differs is `POLICY_MODIFIED` and never counts.
- Running `record` over the new databases writes their records. Then
  `summarize OUT.md <record dirs>` aggregates by cohort.
- No sample target is set. A first review is practical after several new
  ordinary trading dates; no rule is changed between them.
- Nothing is scheduled, and collection stays disarmed.
