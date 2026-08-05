"""Immutable contracts for electrical load simulation observations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from simulator.core import SimulationStepIdentity
from simulator.validation import require_non_negative_number


@dataclass(frozen=True, slots=True)
class LoadSimulationInput:
    """Preserve explicit facts supplied to one load simulation evaluation.

    ``demand_power_kw`` is a caller-supplied, non-negative finite raw power
    value in kW. It is an exogenous simulation fact, not a forecast, user
    behavior model, demand-response instruction, or device observation.
    """

    step_identity: SimulationStepIdentity
    demand_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.step_identity, SimulationStepIdentity):
            raise TypeError("step_identity must be a SimulationStepIdentity")
        object.__setattr__(
            self,
            "demand_power_kw",
            require_non_negative_number(self.demand_power_kw, "demand_power_kw"),
        )


@dataclass(frozen=True, slots=True)
class LoadSimulationResult:
    """Relate one exact load input to one consumption observation.

    ``actual_power_kw`` is non-negative finite consumed power in raw kW and
    cannot exceed the explicit input demand. The result does not explain or
    calculate how the observation was obtained.
    """

    simulation_input: LoadSimulationInput
    actual_power_kw: float

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_input, LoadSimulationInput):
            raise TypeError("simulation_input must be a LoadSimulationInput")
        actual_power_kw = require_non_negative_number(
            self.actual_power_kw,
            "actual_power_kw",
        )
        if actual_power_kw > self.simulation_input.demand_power_kw:
            raise ValueError(
                "actual_power_kw must be less than or equal to demand_power_kw"
            )
        object.__setattr__(self, "actual_power_kw", actual_power_kw)


class LoadSimulationModelBoundary(ABC):
    """Define a stateless extension point for one load simulation evaluation."""

    __slots__ = ()

    @abstractmethod
    def simulate(
        self,
        simulation_input: LoadSimulationInput,
    ) -> LoadSimulationResult:
        """Return one result without mutating or retaining the input."""
        raise NotImplementedError
