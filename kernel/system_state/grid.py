"""Immutable factual state of the electrical grid connection."""

from dataclasses import dataclass

from kernel.system_state.validation import (
    require_non_negative_number,
    require_number,
    require_positive_number,
)


@dataclass(frozen=True, slots=True)
class GridState:
    """Observe grid power, voltage, and frequency.

    Grid power is in kW: positive means importing from the grid, negative means
    exporting to the grid, and zero means balanced exchange. Voltage is a
    non-negative value in V and frequency is a positive value in Hz.
    """

    grid_power_kw: float
    voltage_v: float
    frequency_hz: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "grid_power_kw",
            require_number(self.grid_power_kw, "grid_power_kw"),
        )
        object.__setattr__(
            self,
            "voltage_v",
            require_non_negative_number(self.voltage_v, "voltage_v"),
        )
        object.__setattr__(
            self,
            "frequency_hz",
            require_positive_number(self.frequency_hz, "frequency_hz"),
        )
