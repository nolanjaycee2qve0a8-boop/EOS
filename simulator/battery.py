"""Immutable contracts for battery simulation."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from kernel.decision.constraint import FeasibleDecisionIntent
from simulator.core import SimulationStepIdentity
from simulator.validation import require_fraction, require_number


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


@dataclass(frozen=True, slots=True)
class BatterySimulationState:
    """Represent one immutable simulated battery state observation.

    ``soc`` is a finite raw unitless fraction in the closed range ``[0, 1]``.
    The state contains no transition behavior, history, device status, or
    mutable storage.
    """

    soc: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "soc", require_fraction(self.soc, "soc"))


@dataclass(frozen=True, slots=True)
class BatterySimulationInput:
    """Preserve exact facts supplied to one Battery model evaluation."""

    step_identity: SimulationStepIdentity
    source_state: BatterySimulationState
    actuation: BatterySimulationActuation

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        if not isinstance(self.source_state, BatterySimulationState):
            raise TypeError("source_state must be a BatterySimulationState")
        if not isinstance(self.actuation, BatterySimulationActuation):
            raise TypeError("actuation must be a BatterySimulationActuation")


@dataclass(frozen=True, slots=True)
class BatterySimulationResult:
    """Relate exact Battery input to an immutable next-state observation.

    ``actual_power_kw`` follows the Battery actuation sign convention: positive
    means charging, negative means discharging, and zero means idle. It is a
    signed finite raw value in kW. The result does not calculate or constrain
    this value and does not mutate either state.
    """

    simulation_input: BatterySimulationInput
    next_state: BatterySimulationState
    actual_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, BatterySimulationInput):
            raise TypeError("simulation_input must be a BatterySimulationInput")
        if not isinstance(self.next_state, BatterySimulationState):
            raise TypeError("next_state must be a BatterySimulationState")
        object.__setattr__(
            self,
            "actual_power_kw",
            require_number(self.actual_power_kw, "actual_power_kw"),
        )


class BatterySimulationModelBoundary(ABC):
    """Define a stateless extension point for one Battery state transition."""

    __slots__ = ()

    @abstractmethod
    def simulate(
        self,
        simulation_input: BatterySimulationInput,
    ) -> BatterySimulationResult:
        """Return one result without mutating or retaining the input."""
        raise NotImplementedError
