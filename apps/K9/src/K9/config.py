"""TradeSpec — configuration dataclass loaded from YAML files."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import yaml


@dataclass
class ShortStrikeSelection:
    method: str   # "DELTA"
    value: float  # e.g. 20.0


@dataclass
class PositionSize:
    mode: str       # "fixed_contracts"
    contracts: int


@dataclass
class EntryConfig:
    order_type: str             # "LIMIT"
    limit_price_strategy: str   # "MID"
    max_fill_time_seconds: int
    limit_price_offset: float = 0.0
    max_entry_attempts: int = 1
    retry_price_decrement: float = 0.0


@dataclass
class ShortPutSelection:
    delta_preferred: float
    delta_range_min: float
    delta_range_max: float


@dataclass
class ShortCallSelection:
    delta_preferred: float
    delta_range_min: float
    delta_range_max: float


@dataclass
class ExitConfig:
    exit_type: str = "TAKE_PROFIT"
    take_profit_percent: float | None = None
    expiration_day_exit_mode: str = "HOLD_TO_EXPIRATION"  # "HOLD_TO_EXPIRATION"


@dataclass
class Constraints:
    max_entries_per_day: int
    one_position_per_underlying: bool


@dataclass
class TradeSpec:
    enabled: bool
    environment: str                        # "holodeck" | "sandbox" | "production"
    underlying: str                         # "SPX" | "XSP" | "NDX" | "RUT"
    trade_type: str                         # "IRON_CONDOR" | "PUT_CREDIT_SPREAD" | "CALL_CREDIT_SPREAD"
    wing_size: int
    short_strike_selection: ShortStrikeSelection
    position_size: PositionSize
    account_minimum: float
    max_risk_per_trade: float
    minimum_net_credit: float
    max_combo_bid_ask_width: float
    entry: EntryConfig
    exit: ExitConfig
    constraints: Constraints
    short_put_selection: ShortPutSelection | None = None
    short_call_selection: ShortCallSelection | None = None
    notes: str = ""
    allowed_entry_after: str = "09:25"   # HH:MM CT
    allowed_entry_before: str = "14:30"  # HH:MM CT

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    _ENV_ALIASES = {
        "HD": "holodeck",
        "TRDS": "sandbox",
        "TRD": "production",
    }

    _STRATEGY_ALIASES = {
        "SIC": "IRON_CONDOR",
        "PCS": "PUT_CREDIT_SPREAD",
        "CCS": "CALL_CREDIT_SPREAD",
    }

    @classmethod
    def from_file(cls, path: str | Path) -> "TradeSpec":
        """Load a TradeSpec from a .yaml/.yml file."""
        p = Path(path)
        suffix = p.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return cls.from_yaml(p)
        if suffix == ".json":
            raise ValueError(
                "JSON trade specs are no longer supported. Convert to YAML v2 and retry."
            )
        raise ValueError(f"Unsupported trade spec extension: {suffix!r}. Expected .yaml or .yml.")

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TradeSpec":
        """Load a TradeSpec from a YAML file.

        Supports:
        - v1-compatible YAML (same keys as JSON schema)
        - v2 YAML shape from docs/K9_TRADE_SPEC_CRITERIA_REFERENCE_v2.md
        """
        data = yaml.safe_load(Path(path).read_text())
        if not isinstance(data, dict):
            raise ValueError("Trade spec YAML must be a mapping/object.")

        if "trade" in data:
            return cls._from_v2_yaml_mapping(data)
        return cls._from_v1_mapping(data)

    @classmethod
    def _from_v1_mapping(cls, data: dict) -> "TradeSpec":
        return cls(
            enabled=data["enabled"],
            environment=cls._normalize_environment(data["environment"]),
            underlying=str(data["underlying"]).upper(),
            trade_type=cls._normalize_trade_type(data["trade_type"]),
            wing_size=data["wing_size"],
            short_strike_selection=ShortStrikeSelection(
                **data["short_strike_selection"]
            ),
            position_size=PositionSize(**data["position_size"]),
            account_minimum=data["account_minimum"],
            max_risk_per_trade=data["max_risk_per_trade"],
            minimum_net_credit=data["minimum_net_credit"],
            max_combo_bid_ask_width=data["max_combo_bid_ask_width"],
            entry=EntryConfig(**data["entry"]),
            exit=ExitConfig(
                exit_type="TAKE_PROFIT",
                take_profit_percent=float(data["exit"]["take_profit_percent"]),
                expiration_day_exit_mode=data["exit"]["expiration_day_exit_mode"],
            ),
            constraints=Constraints(**data["constraints"]),
            notes=data.get("notes", ""),
            allowed_entry_after=data.get("allowed_entry_after", "09:25"),
            allowed_entry_before=data.get("allowed_entry_before", "14:30"),
        )

    @classmethod
    def _from_v2_yaml_mapping(cls, data: dict) -> "TradeSpec":
        """Map v2 YAML schema to current K9 internal TradeSpec model."""
        cls._assert_only_keys(
            data,
            {
                "schema_version",
                "enabled",
                "environment",
                "underlying",
                "account_minimum",
                "max_combo_bid_ask_width",
                "notes",
                "trade",
            },
            "root",
        )

        if "schema_version" in data and int(data["schema_version"]) != 2:
            raise ValueError("root.schema_version must be 2 for v2 YAML.")

        trade = data.get("trade")
        if not isinstance(trade, dict):
            raise ValueError("v2 YAML requires 'trade' object.")

        cls._assert_only_keys(
            trade,
            {
                "option_strategy",
                "entry_constraints",
                "entry_criteria",
                "entry_order",
                "leg_selection",
                "exit_order",
            },
            "trade",
        )

        entry_constraints = trade.get("entry_constraints")
        entry_criteria = trade.get("entry_criteria")
        entry_order = trade.get("entry_order")
        exit_order = trade.get("exit_order")
        leg_selection = trade.get("leg_selection")

        if not isinstance(entry_constraints, dict):
            raise ValueError("v2 YAML requires trade.entry_constraints object.")
        if not isinstance(entry_criteria, dict):
            raise ValueError("v2 YAML requires trade.entry_criteria object.")
        if not isinstance(entry_order, dict):
            raise ValueError("v2 YAML requires trade.entry_order object.")
        if not isinstance(exit_order, dict):
            raise ValueError("v2 YAML requires trade.exit_order object.")
        if not isinstance(leg_selection, dict):
            raise ValueError("v2 YAML requires trade.leg_selection object.")

        cls._assert_only_keys(
            entry_constraints,
            {"allow_multiple_trades", "quantity", "max_entries_per_day", "max_risk_dollars"},
            "trade.entry_constraints",
        )
        cls._assert_only_keys(
            entry_criteria,
            {"type", "allowed_entry_after", "allowed_entry_before"},
            "trade.entry_criteria",
        )
        cls._assert_only_keys(
            entry_order,
            {
                "order_type",
                "time_in_force",
                "max_fill_wait_time_seconds",
                "max_entry_attempts",
                "retry_price_decrement",
                "entry_price",
                "min_credit_received",
            },
            "trade.entry_order",
        )
        cls._assert_only_keys(
            exit_order,
            {"exit_type", "order_type", "time_in_force", "exit_price"},
            "trade.exit_order",
        )

        option_strategy = trade.get("option_strategy")
        trade_type = cls._normalize_trade_type(option_strategy)

        if entry_criteria.get("type") != "time_window":
            raise ValueError("Only trade.entry_criteria.type='time_window' is supported.")
        if entry_order.get("order_type") != "LIMIT":
            raise ValueError("Only trade.entry_order.order_type='LIMIT' is supported.")
        if entry_order.get("time_in_force") != "DAY":
            raise ValueError("Only trade.entry_order.time_in_force='DAY' is supported.")
        entry_price_strategy, entry_price_offset = cls._parse_entry_price(
            entry_order.get("entry_price")
        )
        exit_type = str(exit_order.get("exit_type", "")).upper()
        if exit_type not in {"TAKE_PROFIT", "NONE"}:
            raise ValueError("trade.exit_order.exit_type must be TAKE_PROFIT or NONE.")

        exit_take_profit_percent: float | None = None
        if exit_type == "TAKE_PROFIT":
            if exit_order.get("order_type") != "LIMIT":
                raise ValueError("Only trade.exit_order.order_type='LIMIT' is supported.")
            if exit_order.get("time_in_force") != "GTC":
                raise ValueError("Only trade.exit_order.time_in_force='GTC' is supported.")
            exit_price = exit_order.get("exit_price")
            if not isinstance(exit_price, dict):
                raise ValueError("v2 YAML requires trade.exit_order.exit_price object.")
            cls._assert_only_keys(
                exit_price,
                {"type", "value"},
                "trade.exit_order.exit_price",
            )
            if (
                exit_price.get("type") != "PERCENT_OF_INITIAL_CREDIT"
            ):
                raise ValueError(
                    "Only trade.exit_order.exit_price.type='PERCENT_OF_INITIAL_CREDIT' is supported."
                )
            exit_take_profit_percent = float(exit_price["value"])
        else:
            cls._assert_only_keys(exit_order, {"exit_type"}, "trade.exit_order")

        wing_size = cls._extract_wing_size(trade_type, leg_selection)
        delta_target = cls._extract_delta_target(trade_type, leg_selection)
        short_put_selection = cls._extract_short_put_selection(trade_type, leg_selection)
        short_call_selection = cls._extract_short_call_selection(trade_type, leg_selection)

        return cls(
            enabled=data["enabled"],
            environment=cls._normalize_environment(data["environment"]),
            underlying=str(data["underlying"]).upper(),
            trade_type=trade_type,
            wing_size=wing_size,
            short_strike_selection=ShortStrikeSelection(method="DELTA", value=delta_target),
            short_put_selection=short_put_selection,
            position_size=PositionSize(
                mode="fixed_contracts",
                contracts=int(entry_constraints["quantity"]),
            ),
            account_minimum=float(data.get("account_minimum", 0.0)),
            max_risk_per_trade=float(entry_constraints["max_risk_dollars"]),
            minimum_net_credit=float(entry_order["min_credit_received"]),
            # v2 defines spread percent, while current runner expects absolute combo width.
            # Keep permissive default until percent-based liquidity checks are implemented.
            max_combo_bid_ask_width=float(data.get("max_combo_bid_ask_width", 1000.0)),
            entry=EntryConfig(
                order_type="LIMIT",
                limit_price_strategy=entry_price_strategy,
                limit_price_offset=entry_price_offset,
                max_fill_time_seconds=int(entry_order["max_fill_wait_time_seconds"]),
                max_entry_attempts=int(entry_order.get("max_entry_attempts", 1)),
                retry_price_decrement=float(entry_order.get("retry_price_decrement", 0.0)),
            ),
            exit=ExitConfig(
                exit_type=exit_type,
                take_profit_percent=exit_take_profit_percent,
                expiration_day_exit_mode="HOLD_TO_EXPIRATION",
            ),
            constraints=Constraints(
                max_entries_per_day=int(entry_constraints["max_entries_per_day"]),
                one_position_per_underlying=not bool(entry_constraints.get("allow_multiple_trades", False)),
            ),
            notes=str(data.get("notes", "")),
            short_call_selection=short_call_selection,
            allowed_entry_after=str(entry_criteria["allowed_entry_after"]),
            allowed_entry_before=str(entry_criteria["allowed_entry_before"]),
        )

    @classmethod
    def _parse_entry_price(cls, value: object) -> tuple[str, float]:
        """Parse v2 entry_price syntax.

        Supported forms:
        - MIDPOINT
        - MIDPOINT + <decimal>
        """
        raw = str(value or "").strip()
        m = re.fullmatch(r"MIDPOINT(?:\s*\+\s*([0-9]+(?:\.[0-9]+)?))?", raw)
        if not m:
            raise ValueError(
                "trade.entry_order.entry_price must be 'MIDPOINT' or "
                "'MIDPOINT + <decimal>'."
            )
        offset = float(m.group(1)) if m.group(1) is not None else 0.0
        return ("MID", offset)

    @classmethod
    def _extract_wing_size(cls, trade_type: str, leg_selection: dict) -> int:
        cls._validate_leg_selection(trade_type, leg_selection)

        if trade_type == "IRON_CONDOR":
            long_put = leg_selection.get("long_put") or {}
            long_call = leg_selection.get("long_call") or {}
            put_wing = float(long_put.get("wing_distance_points", 0.0))
            call_wing = float(long_call.get("wing_distance_points", 0.0))
            if put_wing <= 0 or call_wing <= 0:
                raise ValueError(
                    "SIC requires positive leg_selection.long_put/long_call.wing_distance_points."
                )
            if abs(put_wing - call_wing) > 1e-9:
                raise ValueError(
                    "SIC requires matching put/call wing_distance_points in v2 mapping."
                )
            return int(round(put_wing))

        if trade_type == "PUT_CREDIT_SPREAD":
            long_put = leg_selection.get("long_put") or {}
            wing = float(long_put.get("wing_distance_points", 0.0))
            if wing <= 0:
                raise ValueError(
                    "PCS requires positive leg_selection.long_put.wing_distance_points."
                )
            return int(round(wing))

        if trade_type == "CALL_CREDIT_SPREAD":
            long_call = leg_selection.get("long_call") or {}
            wing = float(long_call.get("wing_distance_points", 0.0))
            if wing <= 0:
                raise ValueError(
                    "CCS requires positive leg_selection.long_call.wing_distance_points."
                )
            return int(round(wing))

        raise ValueError(f"Unsupported trade_type mapping: {trade_type!r}")

    @classmethod
    def _extract_delta_target(cls, trade_type: str, leg_selection: dict) -> float:
        def midpoint_abs(dr: dict) -> float:
            cls._assert_only_keys(dr, {"min", "max"}, "trade.leg_selection.*.delta_range")
            lo = abs(float(dr["min"]))
            hi = abs(float(dr["max"]))
            return ((lo + hi) / 2.0) * 100.0

        if trade_type == "IRON_CONDOR":
            sp = ((leg_selection.get("short_put") or {}).get("delta_range") or {})
            sc = ((leg_selection.get("short_call") or {}).get("delta_range") or {})
            if not sp or not sc:
                raise ValueError("SIC requires both short_put.delta_range and short_call.delta_range.")
            return round((midpoint_abs(sp) + midpoint_abs(sc)) / 2.0, 2)

        if trade_type == "PUT_CREDIT_SPREAD":
            sp_leg = (leg_selection.get("short_put") or {})
            preferred = sp_leg.get("delta_preferred")
            if preferred is not None:
                return round(abs(float(preferred)) * 100.0, 2)
            sp = ((leg_selection.get("short_put") or {}).get("delta_range") or {})
            if not sp:
                raise ValueError("PCS requires short_put.delta_range.")
            return round(midpoint_abs(sp), 2)

        if trade_type == "CALL_CREDIT_SPREAD":
            sc = ((leg_selection.get("short_call") or {}).get("delta_range") or {})
            if not sc:
                raise ValueError("CCS requires short_call.delta_range.")
            return round(midpoint_abs(sc), 2)

        raise ValueError(f"Unsupported trade_type mapping: {trade_type!r}")

    @classmethod
    def _extract_short_put_selection(
        cls, trade_type: str, leg_selection: dict
    ) -> ShortPutSelection | None:
        if trade_type not in {"PUT_CREDIT_SPREAD", "IRON_CONDOR"}:
            return None

        short_put = leg_selection.get("short_put") or {}
        dr = short_put.get("delta_range") or {}
        if not dr:
            return None

        cls._assert_only_keys(dr, {"min", "max"}, "trade.leg_selection.short_put.delta_range")
        min_delta = float(dr["min"])
        max_delta = float(dr["max"])
        preferred = short_put.get("delta_preferred")
        if preferred is None:
            preferred = (min_delta + max_delta) / 2.0

        return ShortPutSelection(
            delta_preferred=float(preferred),
            delta_range_min=min_delta,
            delta_range_max=max_delta,
        )

    @classmethod
    def _extract_short_call_selection(
        cls, trade_type: str, leg_selection: dict
    ) -> ShortCallSelection | None:
        if trade_type not in {"CALL_CREDIT_SPREAD", "IRON_CONDOR"}:
            return None

        short_call = leg_selection.get("short_call") or {}
        dr = short_call.get("delta_range") or {}
        if not dr:
            return None

        cls._assert_only_keys(dr, {"min", "max"}, "trade.leg_selection.short_call.delta_range")
        min_delta = float(dr["min"])
        max_delta = float(dr["max"])
        preferred = short_call.get("delta_preferred")
        if preferred is None:
            preferred = (min_delta + max_delta) / 2.0

        return ShortCallSelection(
            delta_preferred=float(preferred),
            delta_range_min=min_delta,
            delta_range_max=max_delta,
        )

    @classmethod
    def _normalize_environment(cls, value: str) -> str:
        env = str(value).strip()
        return cls._ENV_ALIASES.get(env, env)

    @classmethod
    def _normalize_trade_type(cls, value: str) -> str:
        raw = str(value).strip().upper()
        return cls._STRATEGY_ALIASES.get(raw, raw)

    @classmethod
    def _assert_only_keys(cls, data: dict, allowed: set[str], path: str) -> None:
        extra = sorted(set(data.keys()) - allowed)
        if extra:
            raise ValueError(
                f"Unsupported field(s) at {path}: {', '.join(extra)}"
            )

    @classmethod
    def _validate_leg_selection(cls, trade_type: str, leg_selection: dict) -> None:
        if trade_type == "IRON_CONDOR":
            required_legs = {"short_put", "short_call", "long_put", "long_call"}
        elif trade_type == "PUT_CREDIT_SPREAD":
            required_legs = {"short_put", "long_put"}
        elif trade_type == "CALL_CREDIT_SPREAD":
            required_legs = {"short_call", "long_call"}
        else:
            raise ValueError(f"Unsupported trade_type mapping: {trade_type!r}")

        cls._assert_only_keys(leg_selection, required_legs, "trade.leg_selection")

        for leg_name, leg_data in leg_selection.items():
            if not isinstance(leg_data, dict):
                raise ValueError(f"trade.leg_selection.{leg_name} must be an object.")
            if leg_name in {"short_put", "short_call"}:
                allowed_keys = {"delta_range"}
                if leg_name in {"short_put", "short_call"}:
                    allowed_keys.add("delta_preferred")
                cls._assert_only_keys(
                    leg_data,
                    allowed_keys,
                    f"trade.leg_selection.{leg_name}",
                )
                if not isinstance(leg_data.get("delta_range"), dict):
                    raise ValueError(
                        f"trade.leg_selection.{leg_name}.delta_range must be an object."
                    )
            else:
                cls._assert_only_keys(
                    leg_data,
                    {"wing_distance_points"},
                    f"trade.leg_selection.{leg_name}",
                )

    def to_v2_yaml_dict(self) -> dict:
        """Render this TradeSpec into v2 YAML dictionary shape."""
        strategy = {
            "IRON_CONDOR": "SIC",
            "PUT_CREDIT_SPREAD": "PCS",
            "CALL_CREDIT_SPREAD": "CCS",
        }.get(self.trade_type)
        if strategy is None:
            raise ValueError(f"Unsupported trade_type for v2 conversion: {self.trade_type!r}")

        env = {
            "holodeck": "HD",
            "sandbox": "TRDS",
            "production": "TRD",
        }.get(self.environment)
        if env is None:
            raise ValueError(f"Unsupported environment for v2 conversion: {self.environment!r}")

        # Build a deterministic delta range around the target (e.g. 20 -> 0.15..0.25).
        center = float(self.short_strike_selection.value) / 100.0
        half_width = 0.05
        low = round(max(0.0, center - half_width), 2)
        high = round(center + half_width, 2)

        leg_selection: dict[str, dict] = {}
        if self.trade_type in {"IRON_CONDOR", "PUT_CREDIT_SPREAD"}:
            short_put_delta_preferred = center
            short_put_min = -high
            short_put_max = -low
            if self.short_put_selection is not None:
                short_put_delta_preferred = self.short_put_selection.delta_preferred
                short_put_min = self.short_put_selection.delta_range_min
                short_put_max = self.short_put_selection.delta_range_max
            leg_selection["short_put"] = {
                "delta_preferred": float(short_put_delta_preferred),
                "delta_range": {
                    "min": float(short_put_min),
                    "max": float(short_put_max),
                },
            }
            leg_selection["long_put"] = {
                "wing_distance_points": float(self.wing_size)
            }
        if self.trade_type in {"IRON_CONDOR", "CALL_CREDIT_SPREAD"}:
            short_call_delta_preferred = center
            short_call_min = low
            short_call_max = high
            if self.short_call_selection is not None:
                short_call_delta_preferred = self.short_call_selection.delta_preferred
                short_call_min = self.short_call_selection.delta_range_min
                short_call_max = self.short_call_selection.delta_range_max
            leg_selection["short_call"] = {
                "delta_preferred": float(short_call_delta_preferred),
                "delta_range": {
                    "min": float(short_call_min),
                    "max": float(short_call_max),
                },
            }
            leg_selection["long_call"] = {
                "wing_distance_points": float(self.wing_size)
            }

        return {
            "schema_version": 2,
            "enabled": self.enabled,
            "environment": env,
            "underlying": self.underlying,
            "account_minimum": float(self.account_minimum),
            "max_combo_bid_ask_width": float(self.max_combo_bid_ask_width),
            "notes": self.notes,
            "trade": {
                "option_strategy": strategy,
                "entry_constraints": {
                    "allow_multiple_trades": not self.constraints.one_position_per_underlying,
                    "quantity": int(self.position_size.contracts),
                    "max_entries_per_day": int(self.constraints.max_entries_per_day),
                    "max_risk_dollars": float(self.max_risk_per_trade),
                },
                "entry_criteria": {
                    "type": "time_window",
                    "allowed_entry_after": self.allowed_entry_after,
                    "allowed_entry_before": self.allowed_entry_before,
                },
                "entry_order": {
                    "order_type": "LIMIT",
                    "time_in_force": "DAY",
                    "max_fill_wait_time_seconds": int(self.entry.max_fill_time_seconds),
                    "max_entry_attempts": int(self.entry.max_entry_attempts),
                    "retry_price_decrement": float(self.entry.retry_price_decrement),
                    "entry_price": (
                        "MIDPOINT"
                        if self.entry.limit_price_offset == 0
                        else f"MIDPOINT + {self.entry.limit_price_offset:.2f}"
                    ),
                    "min_credit_received": float(self.minimum_net_credit),
                },
                "leg_selection": leg_selection,
                "exit_order": (
                    {
                        "exit_type": "NONE",
                    }
                    if self.exit.exit_type == "NONE"
                    else {
                        "exit_type": "TAKE_PROFIT",
                        "order_type": "LIMIT",
                        "time_in_force": "GTC",
                        "exit_price": {
                            "type": "PERCENT_OF_INITIAL_CREDIT",
                            "value": float(self.exit.take_profit_percent or 0.0),
                        },
                    }
                ),
            },
        }

    def to_v2_yaml_text(self) -> str:
        """Render v2 YAML text for writing to file."""
        return yaml.safe_dump(self.to_v2_yaml_dict(), sort_keys=False)

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #

    _VALID_TRADE_TYPES = frozenset(
        {"IRON_CONDOR", "PUT_CREDIT_SPREAD", "CALL_CREDIT_SPREAD"}
    )
    _VALID_ENVIRONMENTS = frozenset({"holodeck", "sandbox", "production"})

    def validate(self) -> None:
        """Raise ValueError on any schema violation."""
        if not str(self.underlying).strip():
            raise ValueError("underlying must be non-empty")
        if self.trade_type not in self._VALID_TRADE_TYPES:
            raise ValueError(
                f"Invalid trade_type {self.trade_type!r}. "
                f"Must be one of {sorted(self._VALID_TRADE_TYPES)}."
            )
        if self.environment not in self._VALID_ENVIRONMENTS:
            raise ValueError(
                f"Invalid environment {self.environment!r}. "
                f"Must be one of {sorted(self._VALID_ENVIRONMENTS)}."
            )
        if self.short_strike_selection.method != "DELTA":
            raise ValueError(
                "Only DELTA strike selection is supported in MVP. "
                f"Got: {self.short_strike_selection.method!r}"
            )
        if self.position_size.contracts != 1:
            raise ValueError(
                "Only 1 contract is supported in MVP. "
                f"Got: {self.position_size.contracts}"
            )
        if self.wing_size <= 0:
            raise ValueError(f"wing_size must be positive. Got: {self.wing_size}")
        if self.minimum_net_credit <= 0:
            raise ValueError(
                f"minimum_net_credit must be positive. Got: {self.minimum_net_credit}"
            )
        if self.entry.max_entry_attempts <= 0:
            raise ValueError("entry.max_entry_attempts must be >= 1")
        if self.entry.retry_price_decrement < 0:
            raise ValueError("entry.retry_price_decrement must be >= 0")
        if self.entry.limit_price_offset < 0:
            raise ValueError("entry.limit_price_offset must be >= 0")
        if self.entry.max_entry_attempts > 1 and self.entry.retry_price_decrement <= 0:
            raise ValueError(
                "entry.retry_price_decrement must be > 0 when max_entry_attempts > 1"
            )
        if self.exit.exit_type not in {"TAKE_PROFIT", "NONE"}:
            raise ValueError("exit.exit_type must be TAKE_PROFIT or NONE")
        if self.exit.exit_type == "TAKE_PROFIT" and self.exit.take_profit_percent is None:
            raise ValueError("exit.take_profit_percent is required when exit_type is TAKE_PROFIT")
