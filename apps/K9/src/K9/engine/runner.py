"""K9 entry execution runner — orchestration (K9-0060/K9-0070/K9-0090)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

from bic.broker import Broker
from K9.config import TradeSpec
from K9.engine.constructor import build_order, build_tp_order, net_credit
from K9.engine.order import OrderOutcome, TpOutcome, place_and_poll, place_tp_order
from K9.engine.validator import validate_trade
from K9.tradier.selector import (
    select_long_call,
    select_long_put,
    select_short_call,
    select_short_put,
)

_CT = ZoneInfo("America/Chicago")


@dataclass
class RunResult:
    """Summary of a single K9 entry execution."""

    spec_name: str
    environment: str
    outcome: str = "ERROR"   # "FILLED" | "CANCELED" | "REJECTED" | "SKIPPED" | "ERROR"
    order_id: str = ""
    filled_price: float | None = None
    net_credit: float | None = None
    expiration: str = ""
    short_put_strike: float | None = None
    short_call_strike: float | None = None
    tp_order_id: str = ""
    tp_price: float | None = None
    reason: str = ""
    errors: list[str] = field(default_factory=list)


def run_entry(
    spec: TradeSpec,
    spec_name: str,
    broker: Broker,
    log_dir: Path | None = None,
) -> RunResult:
    """Execute the K9 entry flow for *spec* using *broker*.

    Steps 5–17 of the 17-step execution sequence.
    Steps 1–4 (load spec, validate, check enabled, create broker) happen in the CLI.

    Args:
        spec: Loaded and validated TradeSpec.
        spec_name: Human-readable name for logging (used for daily entry guard).
        broker: Pre-instantiated Broker (HolodeckBroker or TradierBroker).
        log_dir: Path to log directory (used for daily entry count check).
                 Defaults to logs/K9/.

    Returns:
        RunResult describing the execution outcome.
    """
    result = RunResult(spec_name=spec_name, environment=spec.environment)
    _log_dir = log_dir or Path("logs/K9")

    try:
        # Step 5 — current time
        now = broker.get_current_time()
        today = now.date()

        # Step 5b — execution time window check
        ct = now.astimezone(_CT)
        after_h, after_m = (int(x) for x in spec.allowed_entry_after.split(":"))
        before_h, before_m = (int(x) for x in spec.allowed_entry_before.split(":"))
        window_open = ct.replace(hour=after_h, minute=after_m, second=0, microsecond=0)
        window_close = ct.replace(hour=before_h, minute=before_m, second=0, microsecond=0)
        if not (window_open <= ct <= window_close):
            result.outcome = "SKIPPED"
            result.reason = (
                f"Current time {ct.strftime('%H:%M')} CT is outside entry window "
                f"{spec.allowed_entry_after}–{spec.allowed_entry_before} CT."
            )
            return result

        # Step 6 — account minimum
        account = broker.get_account()
        if account.net_liquidation < spec.account_minimum:
            result.outcome = "SKIPPED"
            result.reason = (
                f"Account net liquidation ${account.net_liquidation:,.0f} is below "
                f"required minimum ${spec.account_minimum:,.0f}."
            )
            return result

        # Step 7 — existing positions (one per underlying)
        if spec.constraints.one_position_per_underlying:
            positions = broker.get_positions()
            for pos in positions:
                if spec.underlying.upper() in pos.symbol.upper():
                    result.outcome = "SKIPPED"
                    result.reason = (
                        f"Existing {spec.underlying} position found: {pos.symbol}. "
                        "One position per underlying constraint violated."
                    )
                    return result

        # Step 7b — max entries per day (count today's log files)
        if spec.constraints.max_entries_per_day > 0:
            today_str = today.strftime("%Y%m%d")
            today_logs = list(_log_dir.glob(f"{spec_name}_{today_str}_*.json"))
            if len(today_logs) >= spec.constraints.max_entries_per_day:
                result.outcome = "SKIPPED"
                result.reason = (
                    f"Already ran {len(today_logs)} time(s) today "
                    f"(max_entries_per_day={spec.constraints.max_entries_per_day})."
                )
                return result

        # Step 8 — underlying quote (informational — chain prices are the source of truth)
        _quote = broker.get_underlying_quote(spec.underlying)

        # Step 9 — option chain (use today as 0DTE expiration)
        expiration = today
        chain = broker.get_option_chain(spec.underlying, expiration)
        result.expiration = expiration.isoformat()

        # Step 10 — select strikes
        target_delta = spec.short_strike_selection.value
        short_put = select_short_put(chain, target_delta)
        short_call = select_short_call(chain, target_delta)
        long_put = select_long_put(chain, short_put, spec.wing_size)
        long_call = select_long_call(chain, short_call, spec.wing_size)

        result.short_put_strike = short_put.strike
        result.short_call_strike = short_call.strike

        # Step 11 — construct order
        order = build_order(spec, expiration, short_put, long_put, short_call, long_call)
        credit = net_credit(order)
        result.net_credit = credit

        # Step 12 — validate trade
        validation = validate_trade(spec, order, short_put, long_put, short_call, long_call)
        if not validation.passed:
            result.outcome = "SKIPPED"
            result.reason = validation.reason
            return result

        # Steps 13–16 — place order and poll
        outcome: OrderOutcome = place_and_poll(
            broker,
            order,
            max_fill_seconds=spec.entry.max_fill_time_seconds,
        )
        result.outcome = outcome.status
        result.order_id = outcome.order_id
        result.filled_price = outcome.filled_price
        result.reason = outcome.reason

        # Step 15 — place take-profit order after fill
        if result.outcome == "FILLED" and result.filled_price is not None:
            tp_order = build_tp_order(spec, order, result.filled_price)
            tp: TpOutcome = place_tp_order(broker, tp_order)
            result.tp_order_id = tp.order_id
            result.tp_price = tp.tp_price
            if tp.status == "FAILED":
                result.errors.append(f"TP order failed: {tp.reason}")

    except Exception as exc:  # noqa: BLE001
        result.outcome = "ERROR"
        result.errors.append(str(exc))

    return result
