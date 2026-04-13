"""TradeSpec — configuration dataclass loaded from JSON files (K9-0010)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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


@dataclass
class ExitConfig:
    take_profit_percent: float
    expiration_day_exit_mode: str  # "HOLD_TO_EXPIRATION"


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
    notes: str = ""
    allowed_entry_after: str = "09:25"   # HH:MM CT
    allowed_entry_before: str = "14:30"  # HH:MM CT

    # ------------------------------------------------------------------ #
    # Construction                                                         #
    # ------------------------------------------------------------------ #

    @classmethod
    def from_json(cls, path: str | Path) -> "TradeSpec":
        """Load a TradeSpec from a JSON file."""
        data = json.loads(Path(path).read_text())
        return cls(
            enabled=data["enabled"],
            environment=data["environment"],
            underlying=data["underlying"],
            trade_type=data["trade_type"],
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
            exit=ExitConfig(**data["exit"]),
            constraints=Constraints(**data["constraints"]),
            notes=data.get("notes", ""),
            allowed_entry_after=data.get("allowed_entry_after", "09:25"),
            allowed_entry_before=data.get("allowed_entry_before", "14:30"),
        )

    # ------------------------------------------------------------------ #
    # Validation                                                           #
    # ------------------------------------------------------------------ #

    _VALID_UNDERLYINGS = frozenset({"SPX", "XSP", "NDX", "RUT"})
    _VALID_TRADE_TYPES = frozenset(
        {"IRON_CONDOR", "PUT_CREDIT_SPREAD", "CALL_CREDIT_SPREAD"}
    )
    _VALID_ENVIRONMENTS = frozenset({"holodeck", "sandbox", "production"})

    def validate(self) -> None:
        """Raise ValueError on any schema violation."""
        if self.underlying not in self._VALID_UNDERLYINGS:
            raise ValueError(
                f"Invalid underlying {self.underlying!r}. "
                f"Must be one of {sorted(self._VALID_UNDERLYINGS)}."
            )
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
