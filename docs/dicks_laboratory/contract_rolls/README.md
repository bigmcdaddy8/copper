# Contract-Roll Provenance Records

**One record per Human-approved production roll.** Each file documents one
explicit change of `production_symbol.PINNED_ES_SYMBOL` (and the matching
`--symbol` in `deploy/dicks_laboratory/systemd/dicks-lab-es-session.service`).
Policy: `../FUTURES_CONTRACT_ROLL_0XA.md` (0X-A) as hardened by 0X-B.

Rules:

1. **Records are immutable historical provenance.** Once committed, a record
   is never edited or deleted. A correction is a new, separate record that
   references the earlier one.
2. **Every draft field must be completed before the production-pin commit is
   accepted.** The pin change, the unit `--symbol` change and the completed
   record land in the same commit. A record with any `null` in `decision`, or
   a missing `broker_metadata_snapshot`, is not acceptable for review.
3. **No automation writes records or changes the pin.** The tool only drafts.
   The Human decides.
4. **No fictitious records.** A record exists only after the Human has
   actually approved a roll. (As of 0X-B no roll has been approved. The
   December 2026 `/ESZ6 → /ESH7` decision is pending.)

## Producing a record

```
uv run --frozen python scripts/dicks_lab_roll_check.py check --roll-record-draft /tmp/roll_draft.json
```

The draft (`LABORATORY_CONTRACT_ROLL`) fills in from live REST metadata: old
and new contract, CME reference (with `CME_PUBLISHED` vs `RULE_DERIVED`
provenance), the assessment at that moment, and an exact timestamped snapshot
of both broker metadata rows. The Human then:

- verifies the CME roll/expiration dates on
  <https://www.cmegroup.com/trading/equity-index/rolldates.html>. Automated
  retrieval is blocked (HTTP 403), so this check is manual and required.
- verifies the successor's broker metadata (listed, tradeable, not
  closing-only, streamer symbol, expiration).
- completes `decision` (see the template below) and saves the file here as
  `<YYYY-MM-DD>_<ROOT>_<OLD>_to_<NEW>.json`, e.g. `2026-12-12_ES_ESZ6_to_ESH7.json`
  (date = decision date, CT).

## Template (shape only — not a decision)

```json
{
  "record_type": "LABORATORY_CONTRACT_ROLL",
  "product": "ES",
  "old_contract": {"broker_symbol": "...", "streamer_symbol": "...", "instrument_id": "...", "expiration_date": "YYYY-MM-DD"},
  "new_contract": {"broker_symbol": "...", "streamer_symbol": "...", "instrument_id": "...", "expiration_date": "YYYY-MM-DD"},
  "cme_reference": {"customary_roll_date": "YYYY-MM-DD", "expiration_date": "YYYY-MM-DD",
                    "source": "CME_PUBLISHED | RULE_DERIVED", "rule": "CME_EQUITY_INDEX_MONDAY_BEFORE_EXPIRATION_V1"},
  "assessment": {"trading_date": "YYYY-MM-DD", "state": "...", "severity": "...", "reasons": ["..."]},
  "broker_metadata_snapshot": {"captured_at_utc": "...Z", "old": {"...": "exact list_futures() row"}, "new": {"...": "exact list_futures() row"}},
  "decision": {
    "approved_by": "Human / PO name or role",
    "decided_at_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "reason": "e.g. CME customary roll; successor verified on CME page and broker metadata",
    "effective_first_trading_date": "YYYY-MM-DD",
    "code_config_commit": "full git hash of the pin-change commit (filled in by an immediate follow-up record-only commit if needed)"
  }
}
```

The `code_config_commit` cannot contain the hash of the commit it is part of.
Record it as the hash of the commit that deploys the pin, added in an
immediate record-only follow-up commit before deployment. That follow-up is
the one permitted completion of the record (rule 1 applies after it).
