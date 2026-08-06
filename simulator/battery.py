"""Immutable battery simulation actuation contract."""

from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from simulator.validation import require_number


@dataclass(frozen=True, slots=True)
class BatterySimulationActuation:
    """Describe battery actuation supplied to a future simulation model.

    ``source_feasible_decision`` is the exact immutable feasible decision that
    authorized this actuation. ``battery_power_kw`` is a signed finite raw
    value in kW: positive means battery charging, negative means battery
    discharging, and zero means idle.

    This artifact does not derive power from the decision, execute a command,
    apply a constraint, advance state, or communicate with a device.
    """

    source_feasible_decision: FeasibleDecisionIntent
    battery_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.source_feasible_decision, FeasibleDecisionIntent):
            raise TypeError("source_feasible_decision must be a FeasibleDecisionIntent")
        object.__setattr__(
            self,
            "battery_power_kw",
            require_number(self.battery_power_kw, "battery_power_kw"),
        )
