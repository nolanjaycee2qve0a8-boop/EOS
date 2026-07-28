"""Immutable snapshot of facts available to one future EMS decision."""

from dataclasses import dataclass
from datetime import datetime

from kernel.decision.validation import (
    require_non_negative_number,
    require_number,
    require_positive_number,
    require_timezone_aware_datetime,
    require_unit_interval,
)


@dataclass(frozen=True, slots=True)
class DecisionContext:
    """Describe the world observed at one decision boundary."""

    timestamp: datetime
    soc: float
    battery_power_limit_kw: float
    battery_energy_capacity_kwh: float
    pv_power_kw: float
    load_power_kw: float
    grid_power_kw: float
    electricity_price: float
    reserve_soc: float
    export_limit_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "timestamp",
            require_timezone_aware_datetime(self.timestamp, "timestamp"),
        )
        object.__setattr__(
            self,
            "soc",
            require_unit_interval(self.soc, "soc"),
        )
        object.__setattr__(
            self,
            "battery_power_limit_kw",
            require_non_negative_number(
                self.battery_power_limit_kw,
                "battery_power_limit_kw",
            ),
        )
        object.__setattr__(
            self,
            "battery_energy_capacity_kwh",
            require_positive_number(
                self.battery_energy_capacity_kwh,
                "battery_energy_capacity_kwh",
            ),
        )
        object.__setattr__(
            self,
            "pv_power_kw",
            require_non_negative_number(self.pv_power_kw, "pv_power_kw"),
        )
        object.__setattr__(
            self,
            "load_power_kw",
            require_non_negative_number(self.load_power_kw, "load_power_kw"),
        )
        object.__setattr__(
            self,
            "grid_power_kw",
            require_number(self.grid_power_kw, "grid_power_kw"),
        )
        object.__setattr__(
            self,
            "electricity_price",
            require_number(self.electricity_price, "electricity_price"),
        )
        object.__setattr__(
            self,
            "reserve_soc",
            require_unit_interval(self.reserve_soc, "reserve_soc"),
        )
        object.__setattr__(
            self,
            "export_limit_kw",
            require_non_negative_number(self.export_limit_kw, "export_limit_kw"),
        )
