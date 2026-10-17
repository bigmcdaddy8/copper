"""Versioned model pricing for Tutor cost estimates (0AC-A3).

Raw provider usage is the record; a cost is an estimate computed from it with one pricing entry, and the
entry's version is stored with every turn. Changing a price means adding an entry with a new version and
effective date, never editing an old one. The table also defines which models the real provider supports.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

MTOK = Decimal(1_000_000)


@dataclass(frozen=True)
class ModelPricing:
    provider: str
    model: str
    pricing_version: str
    effective_from: date
    source: str
    input_per_mtok: Decimal  # uncached input tokens
    output_per_mtok: Decimal  # includes thinking tokens (billed as output)
    cache_read_per_mtok: Decimal  # cache hits and refreshes
    cache_write_per_mtok: Decimal  # 5-minute cache writes (the TTL the Tutor uses)


ANTHROPIC_2026_10_17 = "ANTHROPIC_LIST_2026-10-17"
_SOURCE = ("https://platform.claude.com/docs/en/about-claude/pricing (first-party Claude API list prices, "
           "fetched 2026-10-17)")

PRICING: tuple[ModelPricing, ...] = (
    ModelPricing("anthropic", "claude-opus-5-5", ANTHROPIC_2026_10_17, date(2026, 10, 17), _SOURCE,
                 Decimal("4"), Decimal("20"), Decimal("0.20"), Decimal("5")),
)


class UnsupportedModel(ValueError):
    pass


def pricing_for(provider: str, model: str, on: date | None = None) -> ModelPricing:
    """The latest entry effective on `on` (default: the latest entry)."""
    rows = [p for p in PRICING if p.provider == provider and p.model == model and (on is None or p.effective_from <= on)]
    if not rows:
        raise UnsupportedModel(f"no pricing for {provider} model {model!r}; supported: "
                               f"{', '.join(sorted({p.model for p in PRICING if p.provider == provider}))}")
    return max(rows, key=lambda p: p.effective_from)


def supported_models(provider: str) -> tuple[str, ...]:
    return tuple(sorted({p.model for p in PRICING if p.provider == provider}))


def estimate_cost(p: ModelPricing, input_tokens: int, output_tokens: int, cache_read_tokens: int = 0,
                  cache_write_tokens: int = 0) -> Decimal:
    return (Decimal(input_tokens) * p.input_per_mtok + Decimal(output_tokens) * p.output_per_mtok
            + Decimal(cache_read_tokens) * p.cache_read_per_mtok
            + Decimal(cache_write_tokens) * p.cache_write_per_mtok) / MTOK
