"""Immutable observation of power exchanged by an energy system."""

from dataclasses import dataclass
from math import isclose

from kernel.power.validation import require_non_negative_number, require_number

POWER_BALANCE_ABS_TOLERANCE_KW = 1e-9


@dataclass(frozen=True, slots=True)
class PowerFlow:
    """Record a validated power balance without controlling the system."""

    pv_power_kw: float
    load_power_kw: float
    battery_power_kw: float
    grid_power_kw: float

    def __post_init__(self) -> None:
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
            "battery_power_kw",
            require_number(self.battery_power_kw, "battery_power_kw"),
        )
        object.__setattr__(
            self,
            "grid_power_kw",
            require_number(self.grid_power_kw, "grid_power_kw"),
        )

        supplied_power_kw = (
            self.pv_power_kw + self.grid_power_kw + self.battery_power_kw
        )
        if not isclose(
            supplied_power_kw,
            self.load_power_kw,
            rel_tol=0.0,
            abs_tol=POWER_BALANCE_ABS_TOLERANCE_KW,
        ):
            raise ValueError(
                "power balance requires pv_power_kw + grid_power_kw "
                "+ battery_power_kw = load_power_kw"
            )
