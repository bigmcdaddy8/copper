"""Explicit dataset lifecycle state (Phase 0V).

`FINALIZED` means the collector closed this dataset's artifact deliberately
and cleanly -- it does NOT mean the market tape is complete. Completeness
remains separate quality evidence (`KNOWN_GAP`/`SUSPECTED_GAP`, coverage
classification). A dataset can be FINALIZED and still contain known gaps.

`INTERRUPTED` means collection ended abnormally and could not continue or
resume cleanly (e.g. reconnect attempts exhausted).

A dataset with no recorded lifecycle state (legacy pre-0V data) is neither of
these -- it is simply untracked; callers must not infer OPEN, FINALIZED, or
INTERRUPTED for datasets captured before this concept existed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class DatasetLifecycleState(StrEnum):
    OPEN = "OPEN"
    FINALIZED = "FINALIZED"
    INTERRUPTED = "INTERRUPTED"


@dataclass(frozen=True)
class DatasetClosingSummary:
    """A frozen snapshot written once, at the moment a dataset is closed.

    Answers "what did the collector record when it finalized?" -- distinct
    from (and not a replacement for) the existing recomputed `DatasetAudit`,
    which answers "what does the database contain right now?" The two
    normally agree; this summary is the collector's own contemporaneous
    account, not a live query.
    """

    dataset_id: UUID
    accepted_trade_count: int
    deferred_event_count: int
    rejected_record_count: int
    known_gap_count: int
    suspected_gap_count: int
    first_source_order: int | None
    last_source_order: int | None
    closed_at: datetime
    collector_version: str | None
    collector_git_commit: str | None
