"""Pre-trade validation checks (K9-0050)."""
from __future__ import annotations

from dataclasses import dataclass

from bic.models import OptionContract, OrderRequest
from K9.config import TradeSpec
from K9.engine.constructor import combo_bid_ask_width


@dataclass
class ValidationResult:
    passed: bool
    reason: str = ""  # non-empty when passed=False


def validate_trade(
    spec: TradeSpec,
    order: OrderRequest,
    short_put: OptionContract,
    long_put: OptionContract,
    short_call: OptionContract | None,
    long_call: OptionContract | None,
) -> ValidationResult:
    """Run all three pre-trade checks. Returns on the first failure."""
    credit = order.limit_price

    result = check_minimum_credit(credit, spec.minimum_net_credit)
    if not result.passed:
        return result

    width = combo_bid_ask_width(short_put, long_put, short_call, long_call)
    result = check_combo_spread(width, spec.max_combo_bid_ask_width)
    if not result.passed:
        return result

    max_loss = (spec.wing_size - credit) * 100
    return check_max_risk(max_loss, spec.max_risk_per_trade)


# ------------------------------------------------------------------ #
# Individual checks                                                   #
# ------------------------------------------------------------------ #

def check_minimum_credit(net_credit: float, minimum: float) -> ValidationResult:
    if net_credit >= minimum:
        return ValidationResult(passed=True)
    return ValidationResult(
        passed=False,
        reason=f"Net credit {net_credit:.2f} is below minimum {minimum:.2f}.",
    )


def check_combo_spread(width: float, max_width: float) -> ValidationResult:
    if width <= max_width:
        return ValidationResult(passed=True)
    return ValidationResult(
        passed=False,
        reason=f"Combo bid/ask width {width:.4f} exceeds maximum {max_width:.4f}.",
    )


def check_max_risk(max_loss: float, max_allowed: float) -> ValidationResult:
    if max_loss <= max_allowed:
        return ValidationResult(passed=True)
    return ValidationResult(
        passed=False,
        reason=f"Max risk per trade ${max_loss:.0f} exceeds limit ${max_allowed:.0f}.",
    )
