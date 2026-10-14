"""Approved Tutor development sessions (AI_TUTOR_UX_POC_PLAN.md, Track B).

Only already-inspected /ES dates may be opened by the Tutor POC. The prospective campaign
(2026-10-12 through 2026-11-06) is analytically sealed: it is refused here even if someone
adds it to the registry by mistake.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

INSTRUMENT = "/ES"
CAMPAIGN_FIRST = date(2026, 10, 12)
CAMPAIGN_LAST = date(2026, 11, 6)
DEFAULT_CORPUS_DIR = Path.home() / "secure" / "mp_corpus"


class SealedDateError(ValueError):
    """A date the Tutor POC must not open."""


@dataclass(frozen=True)
class DevSession:
    trading_date: date
    database: str  # file name inside the corpus directory
    database_sha256: str  # recorded in docs/dicks_laboratory/evidence/0AB-B/db_sha_before.txt
    enabled: bool  # A1 exposes one enabled date; the others are approved but not yet prepared


# Development dates already inspected in 0Z-B / 0AA-B / 0AB-B.
APPROVED: tuple[DevSession, ...] = (
    DevSession(date(2026, 9, 29), "es_20260929_6af08205.sqlite3",
               "0b59b7197d486c7ed5fcf5afa08f83e42ec19ed889b44ef421f1eecbf3d07dde", False),
    DevSession(date(2026, 9, 30), "es_20260930_9ac5a21e.sqlite3",
               "61489eea4ace51dee3aafaa1e1dff5fc7d843e491205f42c2e0dbd098a8aa17c", True),
    DevSession(date(2026, 10, 1), "es_20261001_fe280370.sqlite3",
               "58545a1b7507ab0dc934adef9e6699fb11cc17745d7526e413b00897093bd95e", False),
    DevSession(date(2026, 10, 2), "es_20261002_7e8d7b5e.sqlite3",
               "cd47e987c8edbec758d590c7580d4a4bb982ed802da18d21fea338f020c3fae2", False),
)


def is_sealed(d: date) -> bool:
    return CAMPAIGN_FIRST <= d <= CAMPAIGN_LAST


def corpus_dir() -> Path:
    return Path(os.environ.get("TUTOR_POC_CORPUS_DIR", DEFAULT_CORPUS_DIR))


def approved_session(d: date, registry: tuple[DevSession, ...] = APPROVED) -> DevSession:
    """The approved, enabled session for `d`; anything else is refused."""
    if is_sealed(d):
        raise SealedDateError(f"{d} is inside the sealed prospective campaign")
    for s in registry:
        if s.trading_date == d:
            if not s.enabled:
                raise SealedDateError(f"{d} is approved but not enabled in this phase")
            return s
    raise SealedDateError(f"{d} is not an approved Tutor development date")


def discoverable(registry: tuple[DevSession, ...] = APPROVED) -> tuple[DevSession, ...]:
    """Sessions shown in the date selector (sealed dates never appear)."""
    return tuple(s for s in registry if not is_sealed(s.trading_date))
