"""Immutable factual state of the physical battery system."""

from dataclasses import dataclass

from kernel.system_state.validation import (
    require_non_negative_number,
    require_number,
    require_unit_interval,
)


@dataclass(frozen=True, slots=True)
class BatteryState:
    """Observe battery facts without calculation or control.

    ``soc`` and ``soh`` are unitless fractions in ``[0, 1]``. Voltage is in V,
    current is in A, temperature is in degrees Celsius, and available charge
    and discharge power are non-negative values in kW.
    """

    soc: float
    soh: float
    voltage_v: float
    current_a: float
    temperature_c: float
    available_charge_power_kw: float
    available_discharge_power_kw: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "soc", require_unit_interval(self.soc, "soc"))
        object.__setattr__(self, "soh", require_unit_interval(self.soh, "soh"))
        object.__setattr__(
            self,
            "voltage_v",
            require_non_negative_number(self.voltage_v, "voltage_v"),
        )
        object.__setattr__(
            self,
            "current_a",
            require_number(self.current_a, "current_a"),
        )
        object.__setattr__(
            self,
            "temperature_c",
            require_number(self.temperature_c, "temperature_c"),
        )
        object.__setattr__(
            self,
            "available_charge_power_kw",
            require_non_negative_number(
                self.available_charge_power_kw,
                "available_charge_power_kw",
            ),
        )
        object.__setattr__(
            self,
            "available_discharge_power_kw",
            require_non_negative_number(
                self.available_discharge_power_kw,
                "available_discharge_power_kw",
            ),
        )
