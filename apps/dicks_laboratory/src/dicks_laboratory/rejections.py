"""Durable audit evidence for source records rejected during normalization."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class RejectionSourceKind(StrEnum):
    HISTORICAL_TRADE = "HISTORICAL_TRADE"
    CAPTURE_LIFECYCLE = "CAPTURE_LIFECYCLE"


@dataclass(frozen=True)
class NormalizationRejection:
    """A received source record that could not become a canonical observation."""

    rejection_id: UUID
    dataset_id: UUID
    source_kind: RejectionSourceKind
    source_record_ref: str
    source_order: int
    reason: str
    detail: str | None = None

    def __post_init__(self) -> None:
        if not self.source_record_ref.strip():
            raise ValueError("Rejected source record reference is required.")
        if self.source_order < 1:
            raise ValueError("Rejected source order must be positive.")
        if not self.reason.strip():
            raise ValueError("Rejected source reason is required.")