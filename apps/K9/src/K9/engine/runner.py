"""K9 entry execution runner — orchestration (K9-0060/K9-0070/K9-0090)."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from bic.broker import Broker
from K9.config import TradeSpec
from K9.engine.constructor import build_order, build_tp_order, net_credit
from K9.engine.order import OrderOutcome, TpOutcome, place_tp_order, place_with_retries
from K9.market_calendar import is_regular_session_open_ct, is_us_market_holiday
from K9.engine.validator import validate_trade
from K9.tradier.selector import (
    select_long_call,
    select_long_put,
    select_short_put_preferred,
    select_short_call,
    select_short_put,
)

_CT = ZoneInfo("America/Chicago")

ERR_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
ERR_SELECTION_FAILED = "SELECTION_FAILED"
ERR_ORDER_REJECTED = "ORDER_REJECTED"
ERR_BROKER_ERROR = "BROKER_ERROR"
ERR_CONFIG_ERROR = "CONFIG_ERROR"


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
    quantity: int = 1
    entry_dte: int | None = None
    entry_underlying_last: float | None = None
    bpr: float | None = None
    long_put_delta: float | None = None
    short_put_delta: float | None = None
    short_call_delta: float | None = None
    long_call_delta: float | None = None
    reason: str = ""
    rejection_reason: str | None = None   # normalized BIC code when outcome=="REJECTED"
    trade_tag: str = ""                   # short UUID linking entry + TP to the same trade
    error_category: str = ""
    error_code: str = ""
    dry_run: bool = False
    preflight: bool = False
    entry_attempts: int = 0
    errors: list[str] = field(default_factory=list)


def _set_error(
    result: RunResult,
    *,
    category: str,
    code: str,
    reason: str,
    exc: Exception | None = None,
) -> None:
    """Populate a structured ERROR state on RunResult."""
    result.outcome = "ERROR"
    result.error_category = category
    result.error_code = code
    result.reason = reason
    entry = f"{category}|{code}|{reason}"
    if exc is not None:
        entry = f"{entry}|{exc.__class__.__name__}: {exc}"
    result.errors.append(entry)


def run_entry(
    spec: TradeSpec,
    spec_name: str,
    broker: Broker,
    log_dir: Path | None = None,
    tick: Callable[[], None] | None = None,
    dry_run: bool = False,
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
        tick: Optional callback to advance the broker's virtual time between order
              polls. Pass ``broker.advance_time`` when using HolodeckBroker so
              that limit orders are evaluated during the fill-wait loop.

    Returns:
        RunResult describing the execution outcome.
    """
    result = RunResult(spec_name=spec_name, environment=spec.environment, dry_run=dry_run)
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

        if ct.weekday() >= 5:
            result.outcome = "SKIPPED"
            result.reason = "Market is closed on weekends."
            return result
        if is_us_market_holiday(ct.date()):
            result.outcome = "SKIPPED"
            result.reason = "Market is closed for a U.S. market holiday."
            return result
        if not is_regular_session_open_ct(ct):
            result.outcome = "SKIPPED"
            result.reason = (
                f"Market appears closed at {ct.strftime('%H:%M')} CT. "
                "Regular session is 08:30-15:00 CT."
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
        try:
            _quote = broker.get_underlying_quote(spec.underlying)
        except Exception as exc:  # noqa: BLE001
            _set_error(
                result,
                category=ERR_DATA_UNAVAILABLE,
                code="MARKET_DATA_UNAVAILABLE",
                reason=(
                    f"Market data unavailable for {spec.underlying} at "
                    f"{today.isoformat()}. Check broker dataset/time alignment."
                ),
                exc=exc,
            )
            return result
        result.entry_underlying_last = _quote.last

        # Step 9 — option chain (use today as 0DTE expiration)
        expiration = today
        try:
            chain = broker.get_option_chain(spec.underlying, expiration)
        except Exception as exc:  # noqa: BLE001
            _set_error(
                result,
                category=ERR_DATA_UNAVAILABLE,
                code="OPTION_CHAIN_UNAVAILABLE",
                reason=(
                    f"Option chain unavailable for {spec.underlying} {expiration.isoformat()}. "
                    "Check broker dataset/time alignment."
                ),
                exc=exc,
            )
            return result
        result.expiration = expiration.isoformat()

        # Step 10 — select strikes
        try:
            target_delta = spec.short_strike_selection.value
            if spec.short_put_selection is not None:
                short_put = select_short_put_preferred(
                    chain,
                    delta_preferred=spec.short_put_selection.delta_preferred,
                    delta_range_min=spec.short_put_selection.delta_range_min,
                    delta_range_max=spec.short_put_selection.delta_range_max,
                    underlying_last=result.entry_underlying_last or 0.0,
                )
            else:
                short_put = select_short_put(chain, target_delta)
            short_call = select_short_call(chain, target_delta)
            long_put = select_long_put(chain, short_put, spec.wing_size)
            long_call = select_long_call(chain, short_call, spec.wing_size)
        except Exception as exc:  # noqa: BLE001
            _set_error(
                result,
                category=ERR_SELECTION_FAILED,
                code="STRIKE_SELECTION_FAILED",
                reason=(
                    "Unable to select strategy legs from option chain. "
                    "Review strike-selection constraints and market liquidity."
                ),
                exc=exc,
            )
            return result

        result.short_put_strike = short_put.strike if short_put is not None else None
        result.short_call_strike = short_call.strike if short_call is not None else None
        result.short_put_delta = short_put.delta if short_put is not None else None
        result.short_call_delta = short_call.delta if short_call is not None else None
        result.long_put_delta = long_put.delta if long_put is not None else None
        result.long_call_delta = long_call.delta if long_call is not None else None

        # Step 11 — construct order
        trade_tag = uuid4().hex[:8]
        result.trade_tag = trade_tag
        order = build_order(spec, expiration, short_put, long_put, short_call, long_call)
        order.tag = trade_tag
        credit = net_credit(order)
        result.net_credit = credit
        result.quantity = order.quantity
        result.entry_dte = 0
        result.bpr = round(max(0.0, (spec.wing_size - credit) * 100 * order.quantity), 2)

        # Step 12 — validate trade
        validation = validate_trade(spec, order, short_put, long_put, short_call, long_call)
        if not validation.passed:
            result.outcome = "SKIPPED"
            result.reason = validation.reason
            return result

        if dry_run:
            result.outcome = "SKIPPED"
            result.reason = (
                "Dry-run complete: entry validated and order construction succeeded; "
                "no orders were submitted."
            )
            return result

        # Steps 13–16 — place order and poll
        try:
            outcome: OrderOutcome = place_with_retries(
                broker,
                order,
                max_fill_seconds=spec.entry.max_fill_time_seconds,
                max_entry_attempts=spec.entry.max_entry_attempts,
                retry_price_decrement=spec.entry.retry_price_decrement,
                min_credit_received=spec.minimum_net_credit,
                tick=tick,
            )
        except Exception as exc:  # noqa: BLE001
            _set_error(
                result,
                category=ERR_BROKER_ERROR,
                code="ORDER_FLOW_EXCEPTION",
                reason="Order placement/polling failed unexpectedly.",
                exc=exc,
            )
            return result
        result.outcome = outcome.status
        result.order_id = outcome.order_id
        result.filled_price = outcome.filled_price
        result.reason = outcome.reason
        result.entry_attempts = outcome.attempts_used
        if outcome.status == "REJECTED":
            result.rejection_reason = outcome.rejection_reason
            if result.rejection_reason == "market_closed":
                result.outcome = "SKIPPED"
                result.reason = "Broker rejected entry because market is closed."

        # Step 15 — place take-profit order after fill
        if (
            result.outcome == "FILLED"
            and result.filled_price is not None
            and spec.exit.exit_type == "TAKE_PROFIT"
        ):
            tp_order = build_tp_order(spec, order, result.filled_price)
            tp_order.tag = trade_tag
            try:
                tp: TpOutcome = place_tp_order(broker, tp_order)
            except Exception as exc:  # noqa: BLE001
                _set_error(
                    result,
                    category=ERR_BROKER_ERROR,
                    code="TP_ORDER_EXCEPTION",
                    reason="Take-profit order placement failed unexpectedly.",
                    exc=exc,
                )
                return result
            result.tp_order_id = tp.order_id
            result.tp_price = tp.tp_price
            if tp.status == "FAILED":
                result.errors.append(f"TP order failed: {tp.reason}")

    except Exception as exc:  # noqa: BLE001
        _set_error(
            result,
            category=ERR_BROKER_ERROR,
            code="UNHANDLED_RUN_EXCEPTION",
            reason="Unexpected failure during run execution.",
            exc=exc,
        )

    return result


def run_preflight(spec: TradeSpec, spec_name: str, broker: Broker) -> RunResult:
    """Run non-trading readiness checks for a trade spec and broker.

    Checks:
    - broker current time
    - account retrieval
    - underlying quote retrieval
    - option chain retrieval for today's expiration
    """
    result = RunResult(
        spec_name=spec_name,
        environment=spec.environment,
        preflight=True,
    )

    try:
        now = broker.get_current_time()
        today = now.date()

        account = broker.get_account()
        if account.net_liquidation <= 0:
            _set_error(
                result,
                category=ERR_BROKER_ERROR,
                code="ACCOUNT_INVALID",
                reason="Account snapshot returned non-positive net liquidation.",
            )
            return result

        try:
            quote = broker.get_underlying_quote(spec.underlying)
            result.entry_underlying_last = quote.last
        except Exception as exc:  # noqa: BLE001
            _set_error(
                result,
                category=ERR_DATA_UNAVAILABLE,
                code="MARKET_DATA_UNAVAILABLE",
                reason=(
                    f"Market data unavailable for {spec.underlying} at "
                    f"{today.isoformat()}. Check broker dataset/time alignment."
                ),
                exc=exc,
            )
            return result

        try:
            chain = broker.get_option_chain(spec.underlying, today)
            result.expiration = today.isoformat()
            if not getattr(chain, "contracts", []):
                _set_error(
                    result,
                    category=ERR_DATA_UNAVAILABLE,
                    code="OPTION_CHAIN_EMPTY",
                    reason=(
                        f"Option chain for {spec.underlying} {today.isoformat()} returned no contracts."
                    ),
                )
                return result
        except Exception as exc:  # noqa: BLE001
            _set_error(
                result,
                category=ERR_DATA_UNAVAILABLE,
                code="OPTION_CHAIN_UNAVAILABLE",
                reason=(
                    f"Option chain unavailable for {spec.underlying} {today.isoformat()}. "
                    "Check broker dataset/time alignment."
                ),
                exc=exc,
            )
            return result

        result.outcome = "PREFLIGHT_OK"
        result.reason = "Preflight checks passed."
        return result

    except Exception as exc:  # noqa: BLE001
        _set_error(
            result,
            category=ERR_BROKER_ERROR,
            code="PREFLIGHT_EXCEPTION",
            reason="Unexpected preflight failure.",
            exc=exc,
        )
        return result
